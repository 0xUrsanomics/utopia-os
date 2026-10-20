#!/usr/bin/env python3
# email_research_senders.py: sender allowlist + processed-id state for an email signal harvester.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Sender allowlist + processed-message state for an email signal harvester.

Replaces an `is:unread` gate, which silently skips any mail the operator has already opened.
Dedup is by mail message id in a state file, so reading the mail first no longer hides it.

Config: $AGENT_EMAIL_SENDERS, default $AGENT_ROOT/knowledge/email-research-senders.json; falls
back to email-research-senders.example.json next to this script. Shape:
  {"senders": [{"match": "newsletter@example.com", "firm": "Example Research", "status": "active",
                "note": "optional"}]}
State: $AGENT_DATA_DIR/state/email-harvest-seen.json ({message id: first-seen ISO time}).

  email_research_senders.py query [--days 2]   -> prints the Gmail search query
  email_research_senders.py senders            -> prints one 'match | firm | status' line per sender
  email_research_senders.py filter ID [ID...]  -> prints the ids NOT yet processed (one per line)
  email_research_senders.py mark ID [ID...]    -> records ids as processed (prunes entries > 30 days)
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
CONFIG = Path(os.environ.get("AGENT_EMAIL_SENDERS", str(ROOT / "knowledge" / "email-research-senders.json")))
EXAMPLE = Path(__file__).resolve().parent / "email-research-senders.example.json"
STATE = DATA_DIR / "state" / "email-harvest-seen.json"
KEEP_DAYS = 30


def senders():
    path = CONFIG if CONFIG.exists() else EXAMPLE
    return json.loads(path.read_text())["senders"]


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(st):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    st = {k: v for k, v in st.items() if v >= cutoff}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=0))
    tmp.replace(STATE)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "query":
        days = int(rest[rest.index("--days") + 1]) if "--days" in rest else 2
        terms = " OR ".join(f"from:{s['match']}" for s in senders())
        print(f"({terms}) newer_than:{days}d")
    elif cmd == "senders":
        for s in senders():
            print(f"{s['match']} | {s['firm']} | {s['status']}" + (f" | {s['note']}" if s.get("note") else ""))
    elif cmd == "filter":
        st = load_state()
        for i in rest:
            if i not in st:
                print(i)
    elif cmd == "mark":
        st = load_state()
        now = datetime.now(timezone.utc).isoformat()
        for i in rest:
            st[i] = now
        save_state(st)
        print(f"marked {len(rest)}", file=sys.stderr)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
