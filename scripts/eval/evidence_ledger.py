#!/usr/bin/env python3
"""Verification-evidence ledger.

Mechanizes the task-completion standard ("done = tested end-to-end, not code
written") into something checkable. When you actually RUN a check (compile, unit
test, smoke test, e2e), record it here. The completion nudge (evidence_completion_
check.sh, a Stop hook) then knows whether this session produced ANY verification
before you claim work done.

Deliberately SOFT: a record + a nudge, never a hard block. Blocking every code-edit
turn on a missing test would false-fire on doc edits and mid-task turns.

Usage:
  evidence_ledger.py record --session S --what "compile foo.py" --result pass
  evidence_ledger.py check  --session S      # {has_evidence, pass, fail, last}
  evidence_ledger.py list   --session S
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB = os.path.join(ROOT, "memory", "state", "evidence_ledger.db")


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("""CREATE TABLE IF NOT EXISTS evidence(
        id INTEGER PRIMARY KEY, session_id TEXT, what TEXT, result TEXT, ts TEXT)""")
    return c


def cmd_record(a):
    c = _conn()
    c.execute("INSERT INTO evidence(session_id, what, result, ts) VALUES(?,?,?,?)",
              (a.session, (a.what or "")[:400], (a.result or "pass"),
               datetime.now(timezone.utc).isoformat()))
    c.commit()
    c.close()
    print("recorded")


def cmd_check(a):
    c = _conn()
    rows = c.execute("SELECT result, ts, what FROM evidence WHERE session_id=? ORDER BY id DESC",
                     (a.session,)).fetchall()
    c.close()
    out = {"has_evidence": bool(rows),
           "pass": sum(1 for r in rows if r[0] == "pass"),
           "fail": sum(1 for r in rows if r[0] == "fail"),
           "last": (rows[0][2] if rows else None)}
    print(json.dumps(out))
    sys.exit(0 if rows else 1)


def cmd_list(a):
    c = _conn()
    for r in c.execute("SELECT ts, result, what FROM evidence WHERE session_id=? ORDER BY id DESC LIMIT 30",
                       (a.session,)):
        print(f"  {r[0][:19]}  [{r[1]}]  {r[2]}")
    c.close()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record"); p.add_argument("--session", required=True)
    p.add_argument("--what", required=True); p.add_argument("--result", default="pass",
                                                            choices=["pass", "fail"])
    p.set_defaults(fn=cmd_record)
    p = sub.add_parser("check"); p.add_argument("--session", required=True); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("list"); p.add_argument("--session", required=True); p.set_defaults(fn=cmd_list)
    a = ap.parse_args()
    try:
        a.fn(a)
    except Exception as e:
        print(json.dumps({"error": str(e)[:200]}), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
