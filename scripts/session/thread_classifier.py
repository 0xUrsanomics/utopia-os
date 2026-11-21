#!/usr/bin/env python3
# thread_classifier.py: which open thread does an incoming operator message belong to?
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Thread classifier: route an incoming chat message to one of the open threads.

    thread_classifier.py classify --text "..." [--reply-to N] [--json]
    thread_classifier.py --selftest

Returns {verdict, rule, thread_id, title, score, reason, candidates, last_touched}.
verdict is one of:
    continue   same thread as state.current_thread
    return     an open thread other than the current one
    new        no open thread matches
    ambiguous  the top two threads score within AMBIG_MARGIN; ask which one

Order of rules (first hit wins):
  1. reply_to: the quoted message id is in a thread's msg_ids (or last_msg_id) -> that thread.
  2. acknowledgement: a short reply made only of ack words ("ok", "yes", "1 yes 2 no", "approve",
     "push", "draft it") -> state.last_asked_thread (the thread of the agent's latest question).
     An ack-led message ("ok the orchard one") goes there too, unless its other words match a
     different thread at ACK_LEAD_OVERRIDE or better.
  3. similarity: IDF-weighted coverage of the message's content words by each open thread's
     keywords (weight 1.0) and title + where + next (weight CONTEXT_WEIGHT; the title counts 1.0
     only when a thread has no keywords). Cue words ("btw", "also", "anyway", "one more thing")
     or a URL raise the bar for "continue" to CUE_CONTINUE_MIN, so they lean to new or return.
  4. a message with no content words at all ("Pull it", an emoji, an empty caption) continues
     the current thread at a low score.

Vocabulary is English. Writing in another language? Add its acknowledgement words to ACK_WORDS,
its filler words to ACK_FILLER, its short imperatives to ACK_VERBS, its stop words to STOP, its
topic-switch phrases to CUE_RE, and any suffix folding to norm(). Re-run --selftest after.

Embeddings: only when THREAD_EMBED_URL names a local OpenAI-style /v1/embeddings server that
answers within EMBED_TIMEOUT_S; otherwise skipped silently. No model is ever loaded in-process.
The thresholds below were set on TF-IDF scores only; re-check them if you turn embeddings on.

Read-only: classify never writes the store. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thread_tracker as tt  # noqa: E402

# ---------------------------------------------------------------- thresholds (documented)
# Scores are coverage in [0, 1]: the IDF-weighted share of the message's content words that a
# thread explains. 1.0 = every informative word is a title/keyword of that thread.
MATCH_MIN = 0.35          # best score below this -> no thread matches -> "new"
AMBIG_MARGIN = 0.10       # top two both >= MATCH_MIN and closer than this -> "ambiguous"
CUE_CONTINUE_MIN = 0.60   # with a cue word or URL, continuing the current thread needs this much
CURRENT_BONUS = 0.05      # tie-break toward the current thread when there is no cue
CONTEXT_WEIGHT = 0.3      # a word found only in title/where/next counts this much vs a keyword;
                          # below MATCH_MIN on purpose, so context words corroborate but never match alone
ACK_MAX_TOKENS = 8        # a pure acknowledgement has at most this many tokens
ACK_LEAD_MAX_TOKENS = 5   # "ok the orchard one": ack word first, short message
ACK_LEAD_OVERRIDE = 0.60  # an ack-led message's other words must match this well to redirect
ACK_SCORE = 0.90          # score reported for ack and reply-to verdicts (rule hits, not similarity)
NO_CONTENT_SCORE = 0.20   # score reported when a message has no content words
ASK_STALE_H = 12          # an acknowledgement more than this long after the agent's question...
ACK_STALE_SCORE = 0.50    # ...is reported at this lower score (pointer may be out of date)
EMBED_URL = os.environ.get("THREAD_EMBED_URL") or None   # off by default
EMBED_MODEL = os.environ.get("THREAD_EMBED_MODEL", "bge-m3")
EMBED_TIMEOUT_S = 0.35    # whole request budget; the hook must finish under 1.5 s
EMBED_WEIGHT = 0.5        # blended score = (1 - w) * coverage + w * cosine

# ---------------------------------------------------------------- vocabulary
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.I)
SPLIT_RE = re.compile(r"[^a-z0-9]+")

# Words that only acknowledge or approve (compared after collapsing repeated letters).
ACK_WORDS = {"go", "ok", "okay", "k", "yes", "yep", "yup", "yeah", "y", "sure", "push", "approve",
             "approved", "agreed", "proceed", "deal", "lgtm", "no", "nope", "skip"}
# Words allowed next to ack words without breaking a pure acknowledgement.
ACK_FILLER = {"all", "both", "and", "the", "it", "that", "this", "them", "now", "please", "pls",
              "then", "ahead"}

STOP = set("""
a an the and or but if of to in on at for from with by as is are was were be been being it its this that
these those i me my mine we our you your he she they them his her what which who whom when where why how
all any both each more most other some such no nor not only own same so than too very can could will would
just don should now also well ok okay yes please pls thanks thank do does did done have has had get got
give show tell make made pull check send run add put let want need like about into over up out again then
there here one two three first last new next same still sure maybe really thing things stuff detail details
deet deets info update updates status number numbers figure news quick asap today tomorrow yesterday
btw eh oh anyway
http https www com org net co io html php htm index
""".split())

# Cue phrases that lean toward a topic switch (new or return), matched on whole words.
CUE_RE = re.compile(r"\b(btw|by the way|also|oh and|anyway|side note|separately|one more thing|unrelated)\b",
                    re.I)


def collapse(tok: str) -> str:
    return re.sub(r"(.)\1+", r"\1", tok)


ACK_C = {collapse(w) for w in ACK_WORDS}
# Imperative replies to the agent's last offer ("draft it", "send it", "pull it"). They count only
# in a PURE acknowledgement (every token is ack, verb or filler), never as the lead word of a
# longer message, so "send me the report" or "pull the turbine number" still go through similarity.
ACK_VERBS = {"draft", "send", "check", "run", "build", "install", "post", "publish"}
ACK_VERBS_C = {collapse(w) for w in ACK_VERBS}
FILLER_C = {collapse(w) for w in ACK_FILLER}


def norm(tok: str) -> str:
    """English plural folding, applied to message and thread text alike."""
    if len(tok) > 4 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        tok = tok[:-1]
    return tok


def raw_tokens(text: str) -> list[str]:
    """Lowercased alnum tokens; a URL contributes only its host name words."""
    text = text or ""
    hosts = []
    for u in URL_RE.findall(text):
        host = re.sub(r"^(?:https?://)?(?:www\.)?", "", u.lower()).split("/")[0]
        hosts.append(host)
    text = URL_RE.sub(" ", text)
    toks = [t for t in SPLIT_RE.split(text.lower()) if t]
    for h in hosts:
        toks += [t for t in SPLIT_RE.split(h) if t]
    return toks


def content_tokens(toks: list[str]) -> list[str]:
    out = []
    for t in toks:
        if len(t) < 2 or t.isdigit() or t in STOP:
            continue
        n = norm(t)
        if n in STOP or len(n) < 2:
            continue
        out.append(n)
    return list(dict.fromkeys(out))


def thread_terms(t: dict) -> dict[str, float]:
    """token -> weight (1.0 keywords, CONTEXT_WEIGHT title/where/next only)."""
    w: dict[str, float] = {}
    kw = [x for k in (t.get("keywords") or []) for x in raw_tokens(k)]
    title = raw_tokens(t.get("title", ""))
    strong = kw if kw else title
    weak = (title if kw else []) + raw_tokens(t.get("where", "")) + raw_tokens(t.get("next", ""))
    for tok in content_tokens(weak):
        w[tok] = CONTEXT_WEIGHT
    for tok in content_tokens(strong):
        w[tok] = 1.0
    return w


def coverage_scores(q: list[str], threads: list[dict]) -> dict[str, float]:
    terms = {t["id"]: thread_terms(t) for t in threads}
    n = len(threads)
    df: dict[str, int] = {}
    for tw in terms.values():
        for tok in tw:
            df[tok] = df.get(tok, 0) + 1

    def idf(tok):
        return math.log((n + 1) / (df.get(tok, 0) + 0.5))

    total = sum(idf(tok) for tok in q)
    if total <= 0:
        return {tid: 0.0 for tid in terms}
    return {tid: sum(idf(tok) * tw.get(tok, 0.0) for tok in q) / total for tid, tw in terms.items()}


def embed_scores(text: str, threads: list[dict]) -> dict[str, float] | None:
    """Cosine of message vs thread text from a local server, or None if off/slow/broken."""
    if not EMBED_URL or not threads:
        return None
    try:
        import urllib.request
        docs = [" ".join([t.get("title", ""), " ".join(t.get("keywords") or []), t.get("where", "")])
                for t in threads]
        body = json.dumps({"model": EMBED_MODEL, "input": [text] + docs}).encode()
        req = urllib.request.Request(EMBED_URL, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT_S) as r:
            vecs = [d["embedding"] for d in json.loads(r.read())["data"]]
        if len(vecs) != len(threads) + 1:
            return None

        def cos(a, b):
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return sum(x * y for x, y in zip(a, b)) / (na * nb)
        return {t["id"]: max(0.0, cos(vecs[0], v)) for t, v in zip(threads, vecs[1:])}
    except Exception:
        return None


def _result(verdict, thread=None, score=0.0, reason="", candidates=None, rule="similarity") -> dict:
    return {"verdict": verdict,
            "rule": rule,
            "thread_id": thread["id"] if thread else None,
            "title": thread["title"] if thread else None,
            "score": round(float(score), 3),
            "reason": reason,
            "candidates": candidates or [],
            "last_touched": thread.get("last_touched") if thread else None}


def _cont_or_return(thread, current_id) -> str:
    return "continue" if thread and thread["id"] == current_id else "return"


def classify(text: str, reply_to=None, data: dict | None = None) -> dict:
    data = data if data is not None else tt.load()
    threads = data.get("threads") or []
    open_ts = [t for t in threads if t.get("status") != "done"]
    by_id = {t["id"]: t for t in threads}
    st = data.get("state") or {}
    current = by_id.get(st.get("current_thread"))
    if current and current.get("status") == "done":
        current = None
    cur_id = current["id"] if current else None

    # 1. reply_to
    if reply_to not in (None, ""):
        try:
            rid = int(reply_to)
        except (TypeError, ValueError):
            rid = None
        if rid is not None:
            for t in open_ts:
                if rid == t.get("last_msg_id") or rid in (t.get("msg_ids") or []):
                    return _result(_cont_or_return(t, cur_id), t, ACK_SCORE,
                                   f"reply to message {rid}, a message in this thread", rule="reply_to")

    toks = raw_tokens(text)
    q = content_tokens(toks)

    # 2. acknowledgements
    ctoks = [collapse(t) for t in toks]
    has_ack = any(c in ACK_C or c in ACK_VERBS_C for c in ctoks)
    pure_ack = (has_ack and len(toks) <= ACK_MAX_TOKENS
                and all(c in ACK_C or c in ACK_VERBS_C or c in FILLER_C or c.isdigit() for c in ctoks))
    ack_led = bool(ctoks) and ctoks[0] in ACK_C and len(toks) <= ACK_LEAD_MAX_TOKENS
    if pure_ack or ack_led:
        asked = by_id.get(st.get("last_asked_thread"))
        if asked and asked.get("status") == "done":
            asked = None
        target = asked or current or (tt.sorted_threads([t for t in open_ts])[:1] or [None])[0]
        if ack_led and not pure_ack and q and open_ts:
            sc = coverage_scores(q, open_ts)
            best_id = max(sc, key=sc.get)
            if sc[best_id] >= ACK_LEAD_OVERRIDE and (target is None or best_id != target["id"]):
                t = by_id[best_id]
                return _result(_cont_or_return(t, cur_id), t, sc[best_id],
                               "ack-led message whose other words match this thread", rule="ack_lead")
        if target is not None:
            score = ACK_SCORE
            why = ("acknowledgement -> thread of the agent's last question" if target is asked
                   else "acknowledgement, no open question recorded -> current thread")
            asked_at = tt.parse_iso(st.get("last_asked_at"))
            if target is asked and asked_at is not None:
                age_h = (datetime.now(tt.LOCAL_TZ) - asked_at).total_seconds() / 3600
                if age_h > ASK_STALE_H:
                    score = ACK_STALE_SCORE
                    why += f" (asked {age_h:.0f}h ago; pointer may be stale)"
            return _result(_cont_or_return(target, cur_id), target, score, why, rule="ack")

    cue = bool(CUE_RE.search(text or "")) or bool(URL_RE.search(text or ""))

    # 4 (checked early). no content words
    if not q or not open_ts:
        if not open_ts:
            return _result("new", None, 0.0, "no open threads", rule="no_content")
        if cue and not current:
            return _result("new", None, 0.0, "cue word and no content words", rule="no_content")
        return _result("continue", current, NO_CONTENT_SCORE,
                       "no topical words; assume the same thread as the previous message", rule="no_content")

    # 3. similarity
    sc = coverage_scores(q, open_ts)
    emb = embed_scores(text, open_ts)
    if emb:
        sc = {k: (1 - EMBED_WEIGHT) * v + EMBED_WEIGHT * emb.get(k, 0.0) for k, v in sc.items()}
    if cur_id in sc and not cue:
        sc[cur_id] += CURRENT_BONUS
    ranked = sorted(sc.items(), key=lambda kv: kv[1], reverse=True)
    cands = [{"id": tid, "title": by_id[tid]["title"], "score": round(s, 3)} for tid, s in ranked[:2]]
    (b_id, b_s) = ranked[0]
    (s_id, s_s) = ranked[1] if len(ranked) > 1 else (None, 0.0)
    src = "keywords+embeddings" if emb else "keywords"

    if b_s < MATCH_MIN:
        return _result("new", None, b_s, f"best {src} match {b_s:.2f} < {MATCH_MIN}", cands)
    if s_id and s_s >= MATCH_MIN and b_s - s_s < AMBIG_MARGIN:
        return _result("ambiguous", None, b_s,
                       f"top two within {AMBIG_MARGIN} ({b_s:.2f} vs {s_s:.2f})", cands)
    best = by_id[b_id]
    if b_id == cur_id:
        if cue and b_s < CUE_CONTINUE_MIN:
            return _result("new", None, b_s,
                           f"cue word/URL and current-thread match {b_s:.2f} < {CUE_CONTINUE_MIN}", cands)
        return _result("continue", best, b_s, f"{src} match to the current thread", cands)
    return _result("return", best, b_s, f"{src} match to an open thread that is not current", cands)


def format_line(res: dict) -> str:
    """One-line hook context."""
    v = res["verdict"]
    if v == "continue":
        if not res["thread_id"]:
            return "thread: same topic as the previous message (not a tracked thread)"
        return f"thread: {res['title']} (continue, {res['score']:.2f})"
    if v == "return":
        d = tt.parse_iso(res.get("last_touched"))
        age = tt.ago({"last_touched": res.get("last_touched")}) if d else "unknown"
        return f"thread: back to {res['title']} (last touched {age}, {res['score']:.2f})"
    if v == "ambiguous":
        c = res["candidates"]
        return f"thread: ambiguous between {c[0]['title']} and {c[1]['title']}, ask"
    return "thread: NEW topic"


# ---------------------------------------------------------------- selftest
# Every thread and message below is invented.

def _fixture() -> dict:
    def th(i, title, area, kw, where="", status="waiting_on_operator", msg=()):
        return {"id": i, "title": title, "area": area, "status": status, "where": where, "next": "",
                "last_touched": "2026-01-05T10:00:00+00:00", "last_msg_id": (msg[-1] if msg else None),
                "msg_ids": list(msg), "keywords": kw, "created": "2026-01-04T10:00:00+00:00"}
    return {"version": 1,
            "state": {"current_thread": "essay", "last_asked_thread": "pitch",
                      "last_asked_at": datetime.now(tt.LOCAL_TZ).isoformat()},
            "threads": [
                th("orchard", "Orchard sensor shortlist", "work",
                   ["orchard", "sensor", "shortlist", "rainfall", "soilprobe", "filter"], msg=(500, 501)),
                th("pitch", "Bakery wholesale pitch", "clients",
                   ["pitch", "drafts", "bakery", "wholesale", "croissant", "inbox"],
                   where="Two replies bounced"),
                th("essay", "Essay: tidal power costs", "content",
                   ["essay", "tidal", "turbine", "levelised", "draft", "newsletter"], status="agent_working"),
                th("running", "Weekly running log", "health",
                   ["running", "tempo", "pace", "mileage", "session", "log"], status="agent_working"),
                th("acme", "Acme analyst opening (via recruiter)", "work", ["acme", "recruiter", "resume"],
                   status="waiting_on_others"),
                th("globex", "Globex screening call (via recruiter)", "work", ["globex", "recruiter", "lisbon"]),
                th("lease", "Lab equipment lease", "clients",
                   ["lease", "rider", "schedule", "merge in"], status="agent_working"),
                th("old", "Old closed thing", "other", ["orchard"], status="done"),
            ]}


SELFTEST_CASES = [
    # (text, reply_to, expected verdict, expected thread id or None)
    ("ok", None, "return", "pitch"),
    ("yes", None, "return", "pitch"),
    ("1 yes 2 no", None, "return", "pitch"),
    ("approve", None, "return", "pitch"),
    ("push", None, "return", "pitch"),
    ("Yesss", None, "return", "pitch"),                      # repeated letters collapse
    ("Ok yes, go ahead now please", None, "return", "pitch"),  # ack words + filler only
    ("yes", 501, "return", "orchard"),                          # reply_to wins over the ack rule
    ("what about this?", 99999, "continue", "essay"),           # unknown reply_to, no content words
    ("btw how is the orchard sensor shortlist doing?", None, "return", "orchard"),
    ("oh and a new opening https://example.com/careers/123", None, "new", None),
    ("Pull it", None, "continue", "essay"),                     # no content words
    ("Draft it", None, "return", "pitch"),                   # ACK_VERBS in a pure ack
    ("send it please", None, "return", "pitch"),
    ("send me the report", None, "new", None),                  # ACK_VERBS never lead a longer message
    ("put the tidal turbine numbers in the draft", None, "continue", "essay"),
    ("anyway, did the running session get logged?", None, "return", "running"),
    ("any news from the recruiter?", None, "ambiguous", None),  # shared keyword, two threads
    ("find a wedding venue in the mountains for next month", None, "new", None),
    ("btw tidal turbine in the essay draft", None, "continue", "essay"),  # cue, but a strong match
    ("", None, "continue", "essay"),
    ("ok the orchard sensor shortlist", None, "return", "orchard"),     # ack-led override
    ("also, the meeting notes: merge in the rider and the schedule", None, "return", "lease"),
    ("what about the riders?", None, "return", "lease"),     # plural folding
    ("are the pitch drafts ready?", None, "return", "pitch"),
    # everyday messages that share a generic word with a thread must not match it
    ("can we jump on a call tomorrow", None, "new", None),
    ("reply to that email from the bank", None, "new", None),
    ("send me the slides", None, "new", None),
]


def selftest() -> int:
    results: list[tuple[str, bool, str]] = []
    fx = _fixture()
    for text, rt, ev, eid in SELFTEST_CASES:
        r = classify(text, rt, data=fx)
        ok = r["verdict"] == ev and r["thread_id"] == eid
        results.append((f"{text!r} rt={rt}", ok, f"got {r['verdict']}/{r['thread_id']} ({r['score']}) "
                                                 f"want {ev}/{eid}; {r['reason']}"))

    # no last_asked and no current: an ack falls back to the most recently touched open thread
    fx2 = _fixture()
    fx2["state"] = {"current_thread": None, "last_asked_thread": None}
    fx2["threads"][3]["last_touched"] = "2026-01-06T10:00:00+00:00"   # running newest
    fx2["threads"][3]["status"] = "waiting_on_operator"
    r = classify("ok", None, data=fx2)
    results.append(("ack with no pointers -> newest waiting thread", r["thread_id"] == "running",
                    f"got {r['thread_id']}"))

    # an acknowledgement long after the question keeps the thread but drops the score
    fx3 = _fixture()
    fx3["state"]["last_asked_at"] = "2026-01-01T10:00:00+00:00"
    r = classify("ok", None, data=fx3)
    results.append(("stale question -> same thread, lower score",
                    r["thread_id"] == "pitch" and r["score"] == ACK_STALE_SCORE, f"{r['score']}"))

    # rule field tells the hook which path decided
    rules = [classify(t, rt, data=fx)["rule"] for t, rt in
             (("yes", 501), ("ok", None), ("Pull it", None), ("turbine", None), ("ok the orchard sensor", None))]
    results.append(("rule field: reply_to/ack/no_content/similarity/ack_lead",
                    rules == ["reply_to", "ack", "no_content", "similarity", "ack_lead"], str(rules)))

    # done threads are never matched
    r = classify("orchard", None, data=fx)
    results.append(("done thread never returned", r["thread_id"] != "old", f"got {r['thread_id']}"))

    # corrupt store raises instead of returning a guess
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "threads.json"
        p.write_text("[broken", encoding="utf-8")
        try:
            tt.load(p)
            ok = False
        except tt.CorruptStore:
            ok = True
        results.append(("corrupt store raises CorruptStore", ok, ""))

    # embedding server down: falls back to keywords quickly with the same verdict
    global EMBED_URL
    saved = EMBED_URL
    EMBED_URL = "http://127.0.0.1:9/v1/embeddings"
    t0 = time.monotonic()
    r = classify("put the tidal turbine numbers in the draft", None, data=fx)
    dt = time.monotonic() - t0
    EMBED_URL = saved
    results.append(("embed server down -> keyword verdict within budget",
                    r["thread_id"] == "essay" and dt < EMBED_TIMEOUT_S + 0.2, f"{dt * 1000:.0f} ms"))

    # format_line covers every verdict
    lines = [format_line(classify(t, rt, data=fx)) for t, rt in
             (("Pull it", None), ("ok", None), ("any news from the recruiter?", None),
              ("find a wedding venue", None))]
    results.append(("format_line for continue/return/ambiguous/new",
                    lines[0].startswith("thread: Essay") and lines[1].startswith("thread: back to")
                    and "ambiguous between" in lines[2] and lines[3] == "thread: NEW topic", " | ".join(lines)))

    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   [{detail}]"))
    passed = sum(ok for _, ok, _ in results)
    case_n = len(SELFTEST_CASES)
    print(f"{passed}/{len(results)} passed ({case_n} message cases)")
    if case_n < 15 or not results:
        print("FAIL: fewer than 15 message cases ran")
        return 1
    return 0 if passed == len(results) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("classify")
    p.add_argument("--text", required=True)
    p.add_argument("--reply-to")
    p.add_argument("--json", action="store_true", help="pretty-print (default: one JSON line)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd != "classify":
        ap.print_help()
        return 2
    try:
        r = classify(a.text, a.reply_to)
    except tt.CorruptStore as e:
        print(f"error: threads.json is unreadable ({e})", file=sys.stderr)
        return 2
    r["line"] = format_line(r)
    print(json.dumps(r, ensure_ascii=False, indent=2 if a.json else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
