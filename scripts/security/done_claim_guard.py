#!/usr/bin/env python3
# done_claim_guard.py: warn-only detector for "done" claims made with no verification after the last edit.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Done-claim detector on the chat reply path. Warn-only, log-only.

Why: AGENT '26 "Beyond Task Completion" (arXiv 2512.12791) showed an LLM judge scoring a run 100%
that the logs put at 33%. The common failure is the same shape: "done / fixed / live" said after an
edit with no test or readback after it. Scheduled jobs can get a verify-before-ship step from the
daemon; interactive chat turns have no such check. This pairs with the CLAUDE.md rule "every done
says what the green result does NOT prove".

What it does: when a reply says done / fixed / shipped / live / deployed / patched / resolved, it
reads the tail of this session's transcript. If the last Edit/Write/NotebookEdit came AFTER the last
verification call (Bash or Read), it logs one row to $AGENT_LOG_DIR/done_claims.jsonl with the
matched phrase only. Message content is not logged unless DONE_GUARD_LOG_CONTEXT=1, which adds
about 120 chars around the phrase for a precision review. It never blocks.

Wire it as a PreToolUse hook on the channel's reply tool. Run it warn-only for a week or two, read
precision from the log, and only then decide whether it should block.

Contract: stdin = hook JSON. Always exit 0. Fail open on any error.

Env (optional):
  AGENT_ROOT     repo root (default: two levels up from this file)
  AGENT_LOG_DIR  logs dir (default: $AGENT_ROOT/logs)
  DONE_GUARD_LOG_CONTEXT  set to 1 to log ~120 chars of reply text around the phrase (default off)
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
LOG = Path(os.environ.get("AGENT_LOG_DIR", str(ROOT / "logs"))) / "done_claims.jsonl"
TAIL_BYTES = 3_000_000
TEXT_FIELDS = ("text", "message", "caption")

DONE = re.compile(
    r"\b(?:done|fixed|shipped|deployed|patched|is\s+live|are\s+live|now\s+live|went\s+live|resolved)\b",
    re.I)
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
VERIFY_TOOLS = {"Bash", "Read"}


def last_positions(transcript: Path):
    """Return (index of last edit tool_use, index of last verify tool_use) in the transcript tail."""
    with transcript.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        lines = f.read().decode(errors="replace").splitlines()
    last_edit = last_verify = -1
    for i, ln in enumerate(lines):
        if '"tool_use"' not in ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        content = (rec.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if name in EDIT_TOOLS:
                last_edit = i
            elif name in VERIFY_TOOLS:
                last_verify = i
    return last_edit, last_verify


def main():
    try:
        data = json.load(sys.stdin)
        tin = data.get("tool_input") or {}
        text = " ".join(str(tin.get(k, "")) for k in TEXT_FIELDS)
        m = DONE.search(text)
        if not m:
            return
        tp = data.get("transcript_path")
        if not tp or not Path(tp).exists():
            return
        last_edit, last_verify = last_positions(Path(tp))
        if last_edit < 0 or last_verify > last_edit:
            return  # nothing edited in the tail, or verified after the last edit
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "phrase": m.group(0),
            "session": data.get("session_id", ""),
            "verdict": "unverified_after_edit",
        }
        if os.environ.get("DONE_GUARD_LOG_CONTEXT") == "1":
            s, e = max(0, m.start() - 60), min(len(text), m.end() + 60)
            row["context"] = text[s:e].replace("\n", " ")
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
