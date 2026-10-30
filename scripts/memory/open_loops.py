#!/usr/bin/env python3
# open_loops.py: who is waiting on you, and who you are waiting on, over email.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Open-loop detector over email threads (pattern from gbrain docs/guides/open-loops.md).

Deterministic rules, zero LLM calls, read-only. If your mail access is MCP-only (in-session),
the caller fetches and this script judges. Fetch recipe: skills/open-loops/SKILL.md.

Two detectors, per thread, on the last REAL message:
  waiting_on_you : last real message is someone else's, you are in To:, unanswered >= 24h
  you_waiting    : last real message is yours, it asks a question, no reply >= 72h
Inbound counts only if it asks or requests something (a "?" or a request phrase); an FYI
confirmation is not a loop. Judged on the message snippet (about 200 chars), so a request
buried deeper in a long mail can be missed.
Rules: an ack ("thanks", "got it", "noted") never closes a loop. A follow-up nudge from the
same side does not restart the clock (age runs from the first message of that side's latest
run). A "?" inside a URL is not a question. Automated senders and promo/social/update/forum
categories are ignored. Threads older than 14 days are dropped. Add ack and request phrases in
your own language to ACK and REQUEST.

Input JSON (file or stdin): {"me": ["addr", ...], "messages": [Gmail-API-shaped metadata objects]}
  each message: id, threadId, from, to, subject, date (RFC 2822), snippet or body, labelIds
Usage:
  open_loops.py input.json [--json] [--now ISO]
  open_loops.py --selftest
Env: OPERATOR_EMAILS (comma-separated, used when the input has no "me"), AGENT_ROOT.
Exit: 0 ok, 2 bad or empty input (an empty input is a FAIL, never "no open loops").
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime, getaddresses


def fail(code, msg, fix="", **_):
    """Structured failure: a code, what went wrong, and how to fix it. Exit 2."""
    print(f"FAIL {code}: {msg}" + (f"\n  fix: {fix}" if fix else ""), file=sys.stderr)
    raise SystemExit(2)


DEFAULT_ME = [a.strip() for a in os.environ.get("OPERATOR_EMAILS", "").split(",") if a.strip()]
WAIT_ON_YOU_H, YOU_WAITING_H, MAX_AGE_D = 24, 72, 14
SKIP_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS", "SPAM", "TRASH"}
AUTO_SENDER = re.compile(r"(no-?reply|do-?not-?reply|notifications?@|mailer-daemon|postmaster|"
                         r"statuspage|calendar-notification|@.*\.(hubspot|mailchimp|sendgrid)|newsletter|"
                         r"billing@|receipts?@|support@|research@|alerts?@|marketing@|news@)", re.I)
INVITE = re.compile(r"^(updated )?invitation:|^(accepted|declined|tentative|canceled|cancelled)( event)?:|"
                    r"^meeting invite:", re.I)
_ROOT = os.environ.get("AGENT_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
IGNORE_FILE = os.path.join(_ROOT, "memory", "state", "open-loops-ignore.json")


def load_ignore():
    """Senders/domains you dismissed as never-a-loop. Missing file = empty list."""
    try:
        return [x.lower() for x in json.load(open(IGNORE_FILE)).get("senders", [])]
    except Exception:
        return []
ACK = re.compile(r"^\s*(ok(ay)?|thanks?( you| so much| a lot)?|thx|ty|got it|noted|sounds good|great|perfect|"
                 r"cheers|will do)[\s!.,:)]*(\w+[\s!.,]*)?$", re.I)
URL = re.compile(r"https?://\S+|www\.\S+")
QUOTED = re.compile(r"(\nOn .+wrote:.*|\n>.*)", re.S)


def addrs(field):
    return [a.lower() for _, a in getaddresses([field or ""]) if a]


def when(m):
    try:
        d = parsedate_to_datetime(re.sub(r"\s*\(.*\)$", "", m.get("date", "")))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def text(m):
    t = m.get("body") or m.get("snippet") or ""
    return QUOTED.sub("", t).replace("‌", " ").strip()


def is_ack(m):
    t = re.sub(r"\s+", " ", text(m))
    return len(t) <= 60 and bool(ACK.match(t))


REQUEST = re.compile(r"\b(please|pls|could you|can you|would you|let me know|lmk|kindly|curious|thoughts on|"
                     r"waiting (for|on) your|any update)\b", re.I)


def asks(m):
    return "?" in URL.sub("", text(m))


def requests(m):
    """Inbound counts only if it asks or requests something. FYI confirmations are not a loop."""
    return asks(m) or bool(REQUEST.search(URL.sub("", text(m))))


def judge(data, now):
    me = {a.lower() for a in (data.get("me") or DEFAULT_ME)}
    ignore = data.get("ignore_senders", load_ignore())
    threads = {}
    for m in data["messages"]:
        if SKIP_LABELS & set(m.get("labelIds") or []):
            continue
        d = when(m)
        if d is None:
            continue
        m = dict(m, _when=d, _mine=bool(set(addrs(m.get("from"))) & me))
        frm = m.get("from", "").lower()
        if INVITE.search(m.get("subject", "")):
            continue
        if not m["_mine"] and (AUTO_SENDER.search(frm) or any(x in frm for x in ignore)):
            continue
        threads.setdefault(m.get("threadId") or m["id"], []).append(m)

    waiting_on_you, you_waiting = [], []
    for tid, msgs in threads.items():
        msgs.sort(key=lambda x: x["_when"])
        real = [x for x in msgs if not is_ack(x)]
        if not real:
            continue
        last = real[-1]
        if now - last["_when"] > timedelta(days=MAX_AGE_D):
            continue
        run_start = last["_when"]  # nudges from the same side do not restart the clock
        for x in reversed(real):
            if x["_mine"] != last["_mine"]:
                break
            run_start = x["_when"]
        age_h = (now - run_start).total_seconds() / 3600
        item = {"thread": tid, "subject": last.get("subject", "")[:90],
                "with": (last.get("to") if last["_mine"] else last.get("from", ""))[:80],
                "since": run_start.isoformat(), "age_h": round(age_h)}
        if (not last["_mine"] and age_h >= WAIT_ON_YOU_H and set(addrs(last.get("to"))) & me
                and requests(last)):
            waiting_on_you.append(item)
        elif last["_mine"] and age_h >= YOU_WAITING_H and asks(last):
            you_waiting.append(item)
    key = lambda i: -i["age_h"]
    return {"threads_judged": len(threads), "waiting_on_you": sorted(waiting_on_you, key=key),
            "you_waiting": sorted(you_waiting, key=key)}


def render(r):
    out = [f"open loops ({r['threads_judged']} threads judged)"]
    out.append(f"  waiting on you ({len(r['waiting_on_you'])}):")
    out += [f"    {i['age_h']}h  {i['with']}  {i['subject']}" for i in r["waiting_on_you"]] or ["    none"]
    out.append(f"  you're waiting on them ({len(r['you_waiting'])}):")
    out += [f"    {i['age_h']}h  {i['with']}  {i['subject']}" for i in r["you_waiting"]] or ["    none"]
    return "\n".join(out)


def selftest():
    now = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)
    def msg(i, t, frm, to, body, hours_ago, labels=()):
        d = (now - timedelta(hours=hours_ago)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        return {"id": i, "threadId": t, "from": frm, "to": to, "subject": t, "body": body, "date": d,
                "labelIds": list(labels)}
        # noqa
    me, them = "Sam Doe <sam@example.com>", "Rina <rina@acme.example>"
    data = {"me": ["sam@example.com"], "messages": [
        msg("1", "inbound-30h", them, me, "Can we meet Tuesday?", 30),
        msg("2", "inbound-5h", them, me, "Draft attached", 5),
        msg("15", "fyi", them, me, "You're locked in for Friday.", 40),
        msg("16", "request", them, me, "Please send the signed copy", 40),
        msg("3", "acked", them, me, "Here is the contract, can you sign it", 50), msg("4", "acked", me, them, "Thanks!", 49),
        msg("5", "ask-80h", me, them, "Could you send the deck?", 80),
        msg("6", "ask-nudged", me, them, "Any update on pricing?", 100),
        msg("7", "ask-nudged", me, them, "Bumping this, any update?", 10),
        msg("8", "url-only", me, them, "See https://x.co/a?b=1 for the doc", 90),
        msg("9", "bot", "noreply@statuspage.io", me, "Resolved?", 40),
        msg("10", "promo", them, me, "Sale ends?", 40, labels=["CATEGORY_PROMOTIONS"]),
        msg("11", "cc-only", them, "boss@acme.example", "FYI all?", 40),
        msg("12", "old", them, me, "Ancient?", 24 * 20),
        msg("13", "invite", them, me, "Join with Google Meet?", 40),
        msg("14", "ignored", "Promo <deals@spamco.example>", me, "Bonus deposit?", 40),
    ], "ignore_senders": ["spamco.example"]}
    data["messages"][14]["subject"] = "Updated invitation: 30 Minute Meeting"
    r = judge(data, now)
    woa = {i["thread"] for i in r["waiting_on_you"]}
    aw = {i["thread"]: i["age_h"] for i in r["you_waiting"]}
    checks = {
        "inbound 30h flagged": "inbound-30h" in woa,
        "inbound 5h not yet": "inbound-5h" not in woa,
        "FYI confirmation not a loop": "fyi" not in woa,
        "request without ? flagged": "request" in woa,
        "ack does not close": "acked" in woa,
        "own question 80h flagged": "ask-80h" in aw,
        "nudge keeps original clock": aw.get("ask-nudged") == 100,
        "? in URL ignored": "url-only" not in aw,
        "bot ignored": "bot" not in woa,
        "promo ignored": "promo" not in woa,
        "cc-only not waiting on you": "cc-only" not in woa,
        "older than 14d dropped": "old" not in woa,
        "calendar invite ignored": "invite" not in woa,
        "ignore-list sender ignored": "ignored" not in woa,
    }
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    ok = all(checks.values())
    print(f"selftest: {sum(checks.values())}/{len(checks)} passed")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now", default=None, help="ISO time to judge against (default: now)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    try:
        raw = open(a.input).read() if a.input and a.input != "-" else sys.stdin.read()
        data = json.loads(raw)
    except Exception as e:
        fail("OPEN_LOOPS_BAD_INPUT", f"cannot read input JSON ({e})",
             fix="pass a file shaped {\"me\": [...], \"messages\": [message metadata objects]}")
    msgs = data.get("messages") if isinstance(data, dict) else None
    if not msgs:
        fail("OPEN_LOOPS_EMPTY_INPUT", "0 messages in input. Zero judged is not 'no open loops'",
             fix="re-run the fetch step in skills/open-loops/SKILL.md; it returned nothing, then re-run")
    now = datetime.fromisoformat(a.now) if a.now else datetime.now(timezone.utc)
    if not (data.get("me") or DEFAULT_ME):
        fail("OPEN_LOOPS_NO_ME", "no own address given", fix='add "me": [...] to the input or set OPERATOR_EMAILS')
    r = judge(data, now)
    print(json.dumps(r, indent=2) if a.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
