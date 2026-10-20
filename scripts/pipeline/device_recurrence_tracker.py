#!/usr/bin/env python3
# device_recurrence_tracker.py: cross-day semantic check, holds the 3rd reuse of one rhetorical device in 4 feed-days.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
device_recurrence_tracker.py . cross-day SEMANTIC rhetorical-device recurrence gate.

THE GAP IT CLOSES. Most content gates catch WITHIN-draft and LEXICAL repetition:
  external_slop_gate.py    . word/phrase tells (delve, tapestry, em dash)
  structure_repetition.py  . one sentence skeleton dominating, within one draft
  paraphrase_test.py       . insight-shaped vacancy, within one draft
NONE of them catch CROSS-DAY SEMANTIC device recurrence: the same rhetorical DEVICE reused
across feed-days while the surface words change every day, so a lexical/antithesis probe
reads EMPTY. Example: a 3-feed-day streak of the "negate the obvious variable, name the real
one underneath" redirect ("distribution, not product" / "habit, not price" / "plumbing, not
savings") that a lexical antithesis probe scores empty, while a reader of the feed sees the
same move three days running.

THE RULE. Rolling tally of the rhetorical DEVICE across the POOLED feed (all agents that
post to it, because the reader sees ONE feed); HOLD the 3rd repeat of the SAME device in a
rolling 4-feed-day window. Device = SEMANTIC (a classifier picks it), not lexical. Each
entry records its source agent; other agents feed classifications in via `ingest` (for
example over the fleet bus), never by writing the ledger directly. `--scope agent`
restricts a check to one agent when needed.

WHAT IT IS NOT. Not a voice gate. Not a word-tell gate (external_slop_gate). Not an
AI-detector to game. ADVISORY by default like paraphrase_test: it SURFACES a HOLD and exits
0; only --enforce makes a HOLD exit 1.
Fix a HOLD by choosing a DIFFERENT rhetorical move, never by rewording the same one to
dodge the classifier.

USAGE
  device_recurrence_tracker.py check  --file <draft>  [--agent hub] [--lane social] [--as-of YYYY-MM-DD] [--enforce] [--json]
  device_recurrence_tracker.py check  --stdin ...
  device_recurrence_tracker.py log    --file <draft>  --date YYYY-MM-DD --id <content_id> [--agent hub] [--lane social]
  device_recurrence_tracker.py report [--agent hub] [--as-of YYYY-MM-DD]
  device_recurrence_tracker.py classify --file <draft>          # just print the device
  device_recurrence_tracker.py ingest --file payload.json       # another agent's pre-classified entries
  device_recurrence_tracker.py selftest                         # offline logic check, no LLM
  exit 0 = PASS / advisory HOLD | 1 = HOLD under --enforce | 2 = usage/error

CLASSIFIER: $DEVICE_CLASSIFIER_CMD if set (a command line; the prompt is appended as its last
argument), else `claude --print` if on PATH. Fail-open: no engine = PASS with "not scored".
Ledger: $AGENT_ROOT/memory/state/device-recurrence-ledger.json (runtime state, gitignored).
Dates: local calendar dates (AGENT_UTC_OFFSET_HOURS, default 0).
"""
import sys, os, json, argparse, subprocess, shutil, datetime, re, shlex

REPO = os.environ.get("AGENT_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEDGER = os.environ.get("DEVICE_LEDGER") or os.path.join(REPO, "memory", "state", "device-recurrence-ledger.json")
JKT = datetime.timezone(datetime.timedelta(hours=float(os.environ.get("AGENT_UTC_OFFSET_HOURS", "0"))))
WINDOW_FEED_DAYS = 4     # rolling window size, in distinct feed-days
HOLD_AT = 3              # HOLD when the candidate would be the Nth occurrence

# Controlled DEVICE taxonomy. A "device" is the take's dominant rhetorical MOVE, distinct
# from SPINE (whole-thread architecture) and HOOK (opening line). Kept crisp so the same
# move on different days maps to the same slug. "other" keeps it extensible.
DEVICE_TAXONOMY = {
    "negate-obvious-name-real": "X-not-Y redirect: deny the obvious/surface variable, name the real driver underneath (distribution not product, habit not price, plumbing not savings).",
    "reframe-as-mundane": "recast the hyped thing as a boring mechanism (not innovation, arithmetic; not strategy, accounting).",
    "inversion": "the thing least needing X got the best X, or the apparent winner is actually losing (status flip).",
    "concede-then-turn": "grant the opponent's strongest point by name, then pivot and attack the metric.",
    "scale-shock": "a single cold number IS the whole take; the magnitude carries it.",
    "analogy-transplant": "this is really just Y from another domain (map the subject onto a familiar pattern).",
    "false-consensus-break": "everyone believes X; they are wrong, here is why.",
    "second-order": "the headline is not the effect; the real consequence is one layer downstream.",
    "category-error-callout": "they call A a B; it is neither / the label is wrong.",
    "inevitability": "this was never a choice, it was always going to happen (structural, not agency).",
    "other": "none of the above; a distinct rhetorical move (the classifier describes it).",
}

DASH = re.compile("[" + chr(0x2014) + chr(0x2013) + "]")   # em / en dash, built from codepoints so this source stays dash-clean

# ---------------------------------------------------------------- classifier (semantic)
_CLS_PROMPT = """You classify the DOMINANT rhetorical DEVICE of a social post (tweet or thread). A device is the take's core rhetorical MOVE, not its topic, not its opening line, not its thread structure.

Pick exactly ONE slug from this controlled list:
%s

Rules:
- Judge the SEMANTIC move, not the surface words. "distribution not product", "habit not price", "plumbing not savings" are ALL the same device (negate-obvious-name-real) even though no words repeat.
- If nothing fits, use "other" and describe the move.
- Output ONLY a single-line JSON object, no preamble, no code fence, no em dashes:
  {"slug":"<slug>","label":"<3-6 word human name of the move>","evidence":"<the exact phrase that carries it>"}

POST:
---
%s
---"""


def _classify_llm(text, timeout=150):
    """Return (slug, label, evidence, engine). Fail-open: ('unclassified','','','') on no engine."""
    prompt = _CLS_PROMPT % ("\n".join(f"- {k}: {v}" for k, v in DEVICE_TAXONOMY.items()),
                            text.strip()[:4000])
    engines = []
    custom = os.environ.get("DEVICE_CLASSIFIER_CMD", "").strip()
    if custom:
        parts = shlex.split(custom)
        engines.append((os.path.basename(parts[0]), [shutil.which(parts[0]) or parts[0]] + parts[1:] + [prompt]))
    claude = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    engines.append(("claude", [claude, "--print", prompt]))
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
        from lib_claude_child_env import child_env
        env = child_env()
    except Exception:
        env = dict(os.environ)
    for engine, cmd in engines:
        if not (cmd[0] and os.path.exists(cmd[0])):
            continue
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
            txt = (out.stdout or "").strip()
            low = txt.lower()
            if not txt or any(s in low for s in
                              ("no output produced", "auto-denied", "headless mode cannot prompt")):
                continue
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            if not m:
                continue
            obj = json.loads(m.group(0))
            slug = str(obj.get("slug", "")).strip()
            if slug not in DEVICE_TAXONOMY:
                # accept an unknown slug as "other" but keep the label for review
                obj.setdefault("label", slug)
                slug = "other"
            return (slug,
                    DASH.sub("-", str(obj.get("label", ""))).strip(),
                    DASH.sub("-", str(obj.get("evidence", ""))).strip(),
                    engine)
        except Exception:
            continue
    return ("unclassified", "", "", "")


# ---------------------------------------------------------------- ledger
def _load():
    try:
        with open(LEDGER) as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def _today():
    return datetime.datetime.now(JKT).strftime("%Y-%m-%d")


def _window_dates(entries, as_of):
    """The last WINDOW_FEED_DAYS distinct feed-days on or before as_of."""
    days = sorted({e["date"] for e in entries if e.get("date") and e["date"] <= as_of})
    return set(days[-WINDOW_FEED_DAYS:])


def _all_entries(d):
    """Flatten the POOLED fleet ledger; tag each entry with its source agent."""
    out = []
    for agent, ents in d.items():
        for e in ents:
            e2 = dict(e); e2.setdefault("_agent", agent); out.append(e2)
    return out


def _count_in_window(entries, device, as_of):
    win = _window_dates(entries, as_of)
    return sum(1 for e in entries if e.get("device") == device and e.get("date") in win), win


# ---------------------------------------------------------------- ops
def op_classify(text):
    slug, label, evidence, engine = _classify_llm(text)
    return {"slug": slug, "label": label, "evidence": evidence, "engine": engine}


def op_check(text, agent, lane, as_of, enforce, scope="pooled"):
    c = op_classify(text)
    d = _load()
    entries = _all_entries(d) if scope == "pooled" else d.get(agent, [])
    slug = c["slug"]
    result = {"agent": agent, "lane": lane, "as_of": as_of, "scope": scope, "device": slug,
              "label": c["label"], "evidence": c["evidence"], "engine": c["engine"]}
    if slug in ("unclassified",):
        result.update(verdict="PASS", reason="classifier unavailable (fail-open); device not scored",
                      prior_in_window=0)
        return result, 0
    prior, win = _count_in_window(entries, slug, as_of)
    would_be = prior + 1
    result["prior_in_window"] = prior
    result["window_feed_days"] = sorted(win)
    result["would_be_occurrence"] = would_be
    if would_be >= HOLD_AT:
        result["verdict"] = "HOLD"
        result["reason"] = (f"device '{slug}' would be occurrence #{would_be} in the rolling "
                            f"{WINDOW_FEED_DAYS}-feed-day window (limit {HOLD_AT}). pick a different "
                            f"rhetorical move, do not reword the same one.")
        return result, (1 if enforce else 0)
    result["verdict"] = "PASS"
    result["reason"] = (f"device '{slug}' at #{would_be} of {HOLD_AT} in window; clear to ship.")
    return result, 0


def op_log(text, agent, lane, date, cid):
    c = op_classify(text)
    d = _load()
    d.setdefault(agent, [])
    entry = {"date": date, "content_id": cid, "lane": lane, "device": c["slug"],
             "label": c["label"], "evidence": c["evidence"],
             "logged_at": datetime.datetime.now(JKT).isoformat()}
    # de-dup on (date, content_id)
    d[agent] = [e for e in d[agent] if not (e.get("date") == date and e.get("content_id") == cid)]
    d[agent].append(entry)
    _save(d)
    return entry


def op_report(agent, as_of, scope="pooled"):
    d = _load()
    entries = _all_entries(d) if scope == "pooled" else d.get(agent, [])
    win = _window_dates(entries, as_of)
    tally = {}
    for e in entries:
        if e.get("date") in win:
            tally[e.get("device")] = tally.get(e.get("device"), 0) + 1
    return {"agent": agent, "scope": scope, "as_of": as_of, "window_feed_days": sorted(win),
            "tally": dict(sorted(tally.items(), key=lambda kv: -kv[1])),
            "at_or_over_limit": {k: v for k, v in tally.items() if v >= HOLD_AT - 1}}


def op_selftest():
    """Offline logic check (no LLM). Uses a temp in-memory ledger."""
    ents = [
        {"date": "2026-08-31", "device": "negate-obvious-name-real"},
        {"date": "2026-09-01", "device": "negate-obvious-name-real"},
    ]
    prior, win = _count_in_window(ents, "negate-obvious-name-real", "2026-09-02")
    assert prior == 2, f"expected 2 prior, got {prior}"
    assert (prior + 1) >= HOLD_AT, "3rd should trip HOLD"
    # a different device in the same window is clear
    p2, _ = _count_in_window(ents, "scale-shock", "2026-09-02")
    assert p2 == 0, "unrelated device should be 0"
    # window rolls: an entry 5 feed-days back drops out
    ents2 = [{"date": "2026-08-20", "device": "x"}, {"date": "2026-08-29", "device": "x"},
             {"date": "2026-08-31", "device": "x"}, {"date": "2026-09-01", "device": "x"},
             {"date": "2026-09-02", "device": "x"}]
    p3, w3 = _count_in_window(ents2, "x", "2026-09-02")
    assert "2026-08-20" not in w3, "oldest of 5 feed-days should roll out of a 4-day window"
    assert len(w3) == WINDOW_FEED_DAYS, "window must cap at WINDOW_FEED_DAYS feed-days"
    return "selftest OK: 3rd-repeat HOLD fires, unrelated device clear, window rolls"


def op_ingest(payload):
    """Ingest another agent's per-slate device feed into the pooled ledger.
    payload = {"agent": "<agent>", "entries": [{date, surface, unit, device, evidence}, ...]}.
    Pre-classified: the device slug is taken as given (feeder classifies with our taxonomy),
    NOT re-run through the LLM. Dedup on content_id = agent:date:surface:unit."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    agent = str(payload.get("agent", "")).strip()
    if not agent:
        raise SystemExit("ingest: payload missing 'agent'")
    d = _load()
    d.setdefault(agent, [])
    added, skipped = 0, []
    for it in (payload.get("entries") or []):
        dev = str(it.get("device", "")).strip()
        if dev not in DEVICE_TAXONOMY:
            skipped.append(f"unknown device slug {dev!r}")
            continue
        date = str(it.get("date", "")).strip()
        surface = str(it.get("surface", "")).strip() or "unknown"
        unit = str(it.get("unit", "")).strip() or "u"
        cid = f"{agent}:{date}:{surface}:{unit}"
        d[agent] = [e for e in d[agent] if e.get("content_id") != cid]
        d[agent].append({"date": date, "content_id": cid, "lane": surface, "device": dev,
                         "label": dev, "evidence": DASH.sub("-", str(it.get("evidence", ""))),
                         "source": "bus-ingest", "logged_at": datetime.datetime.now(JKT).isoformat()})
        added += 1
    _save(d)
    return {"agent": agent, "added": added, "skipped": skipped}


# ---------------------------------------------------------------- CLI
def _read_text(args):
    if getattr(args, "stdin", False):
        return sys.stdin.read()
    if getattr(args, "file", None):
        with open(args.file) as f:
            return f.read()
    print("error: need --file or --stdin", file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description="cross-day semantic device-recurrence gate")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_io(p):
        p.add_argument("--file")
        p.add_argument("--stdin", action="store_true")
        p.add_argument("--agent", default=os.environ.get("FLEET_HUB_AGENT", "hub"))
        p.add_argument("--lane", default="social")
        p.add_argument("--json", action="store_true")

    pc = sub.add_parser("check"); add_io(pc)
    pc.add_argument("--as-of", default=None); pc.add_argument("--enforce", action="store_true")
    pc.add_argument("--scope", choices=["pooled", "agent"], default="pooled")
    pl = sub.add_parser("log"); add_io(pl)
    pl.add_argument("--date", default=None); pl.add_argument("--id", required=True)
    pcl = sub.add_parser("classify"); add_io(pcl)
    pr = sub.add_parser("report"); pr.add_argument("--agent", default=os.environ.get("FLEET_HUB_AGENT", "hub"))
    pr.add_argument("--as-of", default=None); pr.add_argument("--json", action="store_true")
    pr.add_argument("--scope", choices=["pooled", "agent"], default="pooled")
    pi = sub.add_parser("ingest"); pi.add_argument("--file"); pi.add_argument("--stdin", action="store_true")
    sub.add_parser("selftest")

    args = ap.parse_args()

    if args.cmd == "selftest":
        print(op_selftest()); return 0

    if args.cmd == "ingest":
        r = op_ingest(_read_text(args))
        print(f"ingested {r['added']} entry(ies) under {r['agent']}"
              + (f"; skipped {len(r['skipped'])}" if r['skipped'] else ""))
        for why in r["skipped"]:
            print(f"  skip: {why}")
        return 0

    if args.cmd == "report":
        as_of = args.as_of or _today()
        r = op_report(args.agent, as_of, args.scope)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
        print(f"== device-recurrence report . {args.agent} . window {r['window_feed_days']} ==")
        if not r["tally"]:
            print(" (no entries in window)")
        for dev, n in r["tally"].items():
            flag = "  <-- at/over limit" if n >= HOLD_AT - 1 else ""
            print(f"  {n}x  {dev}{flag}")
        return 0

    if args.cmd == "classify":
        c = op_classify(_read_text(args))
        if args.json:
            print(json.dumps(c, ensure_ascii=False)); return 0
        print(f"device: {c['slug']}  ({c['label']})  [{c['engine'] or 'no-engine'}]  evidence: {c['evidence']}")
        return 0

    if args.cmd == "log":
        date = args.date or _today()
        e = op_log(_read_text(args), args.agent, args.lane, date, args.id)
        print(f"logged: {date} {args.agent}/{args.lane} device={e['device']} id={args.id}")
        return 0

    if args.cmd == "check":
        as_of = args.as_of or _today()
        r, code = op_check(_read_text(args), args.agent, args.lane, as_of, args.enforce, args.scope)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2)); return code
        print(f"== device-recurrence gate . {r['verdict']} . {r['agent']} ==")
        print(f"  device: {r['device']}  ({r.get('label','')})  [{r.get('engine') or 'no-engine'}]")
        if r.get("evidence"):
            print(f"  evidence: {r['evidence']}")
        if "prior_in_window" in r:
            print(f"  window {r.get('window_feed_days')}: {r['prior_in_window']} prior, this would be #{r.get('would_be_occurrence')}")
        print(f"  {r['reason']}")
        return code

    return 2


if __name__ == "__main__":
    sys.exit(main())
