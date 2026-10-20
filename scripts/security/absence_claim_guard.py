#!/usr/bin/env python3
# absence_claim_guard.py: PreToolUse hook, an "X is not set up" reply must name the scope it searched.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Absence-claim detector on the operator reply path. Blocks once per message on high-precision
phrases only; everything else is log-only.

Why: one error class keeps recurring and keeps getting banked as a prose lesson: "X is not set up",
"X is not in our list", said from a search that was narrower than the claim (the tool WAS installed,
the doc DID mention it, under a name the search did not try). Every miss goes out as a chat reply to
the operator, where nothing checks. Prose lessons do not gate anything; this hook does.

Wired as a PreToolUse hook on the chat reply tool (same matcher as emdash_send_guard.py). Logs one
row per match to logs/absence_claims.jsonl (phrase + a short context window, never the full message).

Rollout that produced the HIGH list: phase 1 logged only, for 7 days. The HIGH phrases were real
absence claims 11 of 11 times; softer wordings ("isn't covered") were plain negation, so they stay
log-only. A HIGH hit passes when its sentence names its scope (a path, a doc, a registry, a command)
or sits inside quotes (a reply that quotes the detector). Otherwise exit 2 once, asking for the
source and the key searched; the next send from the same session within GRACE_S passes, so a
rewrite is never blocked twice. Re-measure precision on your own logs before widening HIGH.

Extend for other languages: ABSENCE_EXTRA_RE (log-only) and ABSENCE_HIGH_EXTRA_RE (can block) are
optional regex alternations appended to the built-in English lists.

Contract: stdin = hook JSON. Exit 0 or 2. Fail open (exit 0) on any error (a crash on this matcher
could otherwise block every reply). Self-test: absence_claim_guard.py --selftest
Env: AGENT_ROOT (logs under $AGENT_ROOT/logs), AGENT_RUN_DIR (grace state, default ~/.agent-daemon/run).
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
LOG = Path(os.environ.get("AGENT_LOG_DIR", str(ROOT / "logs"))) / "absence_claims.jsonl"
STATE = Path(os.environ.get("AGENT_RUN_DIR", str(Path.home() / ".agent-daemon" / "run"))) / "absence_guard_state.json"
TEXT_FIELDS = ("text", "message", "caption")
GRACE_S = 600


def _extra(name):
    v = os.environ.get(name, "").strip()
    return f"|{v}" if v else ""


ABSENCE = re.compile(
    r"\b(?:is|are|was|were)?\s*not\s+(?:in\s+(?:our|the)|set\s*up|installed|available|wired|configured|"
    r"found|connected|there|supported|listed)\b"
    r"|\b(?:isn't|aren't|wasn't|doesn't|don't|didn't)\s+(?:installed|set\s*up|available|exist|there|have|support)\b"
    r"|\bthere\s+is\s+no\b|\bno\s+such\b|\bwe\s+(?:don't|do\s+not)\s+have\b|\bnever\s+(?:checked|wired|set\s*up)\b"
    # document-set absence wordings ("the memo doesn't mention X")
    r"|\b(?:is|are|was|were)?\s*not\s+(?:mentioned|named|cited|covered|included)\b"
    r"|\b(?:isn't|aren't|wasn't|weren't)\s+(?:mentioned|named|cited|included|listed)\b"
    r"|\b(?:doesn't|don't|didn't)\s+(?:name|mention|cite|cover|include|appear|list)\b"
    r"|\bno\s+mention\s+of\b|\bnowhere\s+in\b|\bnot\s+anywhere\s+in\b"
    + _extra("ABSENCE_EXTRA_RE"),
    re.I)

# The phrases whose non-meta hits were real claims 11 of 11. Only these can block.
HIGH = re.compile(
    r"\b(?:isn't|isn’t|is\s+not)\s+installed\b|\bnot\s+in\s+(?:our|the)\b|\bthere\s+is\s+no\b"
    r"|\b(?:doesn't|doesn’t)\s+name\b|\b(?:isn't|isn’t)\s+listed\b"
    + _extra("ABSENCE_HIGH_EXTRA_RE"),
    re.I)
SCOPE = re.compile(
    r"[\w.-]+/[\w./-]+|\.(?:md|json|jsonl|py|sh|csv|xlsx|pdf)\b|`[^`]+`"
    r"|\b(?:docs?|document|registry|pre-?read|file|folder|repo|sheet|index|log|drive|inbox|report|memo|crontab)\b",
    re.I)

_END = re.compile(r"[.!?](?=\s|$)|\n")  # a dot inside a filename like run.sh is not a sentence end


def _sentence(text, a, b):
    starts = [m.end() for m in _END.finditer(text, 0, a)]
    end = _END.search(text, b)
    return text[(starts[-1] if starts else 0):(end.start() if end else len(text))]


def _quoted(text, a):
    return text[:a].count('"') % 2 == 1 or text[:a].count("“") > text[:a].count("”")


def _unscoped_high(text):
    for m in HIGH.finditer(text):
        if _quoted(text, m.start()) or SCOPE.search(_sentence(text, m.start(), m.end())):
            continue
        return m.group(0)
    return None


def _in_grace(session):
    try:
        st = json.loads(STATE.read_text())
        return st.get("session") == session and datetime.now(timezone.utc).timestamp() - st.get("ts", 0) < GRACE_S
    except Exception:
        return False


def _arm_grace(session):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"session": session, "ts": datetime.now(timezone.utc).timestamp()}))


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        ti = data.get("tool_input") or {}
        text = " ".join(str(ti.get(k) or "") for k in TEXT_FIELDS)
        hits = []
        for m in ABSENCE.finditer(text):
            a, b = max(0, m.start() - 60), min(len(text), m.end() + 60)
            hits.append({"phrase": m.group(0).strip(), "context": text[a:b].replace("\n", " ")})
        session = str(data.get("session_id", ""))[:12]
        high = _unscoped_high(text)
        block = bool(high) and not _in_grace(session)
        if hits or high:
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with LOG.open("a") as f:
                f.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "event": "absence_claim_seen", "phase": 2,
                    "decision": "block" if block else ("grace_pass" if high else "log"),
                    "tool": data.get("tool_name"), "session": session,
                    "hits": hits[:5],
                }, ensure_ascii=False) + "\n")
        if block:
            _arm_grace(session)
            sys.stderr.write(
                f"Absence claim without a named source: \"{high}\". Before saying something is missing, "
                "name where you looked and the key you searched (file, doc, registry, command), or soften it "
                "to what the search actually covered. This blocks once; the next send passes.\n")
            sys.exit(2)
    except Exception:
        pass
    sys.exit(0)


def _selftest():
    cases = [
        ("The search tool is not installed.", True),                                  # unscoped HIGH: blocks
        ("The search tool is not installed (checked `which search-cli` and PATH).", False),  # scoped
        ("Acme is not in the registry file knowledge/vendors.json.", False),           # names a path
        ('The detector flags "there is no" phrasing.', False),                         # quoted meta
        ("The memo doesn't mention Alice.", False),                                    # log-only wording
        ("Not in our list, sorry.", True),
    ]
    bad = 0
    for text, want in cases:
        got = _unscoped_high(text) is not None
        ok = got == want
        bad += not ok
        print(f" {'PASS' if ok else 'FAIL'}  block={got!s:5}  {text}")
    print("selftest: PASS" if not bad else f"selftest: {bad} FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    main()
