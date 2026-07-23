#!/usr/bin/env python3
"""CONFIRM-gate approval binding.

Adapted from OpenClaw/Codex per-request approval IDs + tamper-checked approvals.
The authority-envelope rule already fixes WHERE an approval may come from (the
principal's own channel, never processed content). This closes a different hole:
an approval that authorizes a MUTATED or STALE action.

Flow for a HIGH-stakes CONFIRM action (irreversible / external-facing / security /
infra). Not for routine reversible ops.

  1. Before presenting the action, write the EXACT concrete action (command, diff,
     target, recipients) to a file and `register` it. You get a short id (cg-xxxx)
     bound to sha256(action). Show the id + hash-prefix with the scope restate.
  2. When the principal approves, re-write the exact action you are ABOUT to run to
     a file and `validate` it against that id. If the action mutated since it was
     shown (hash mismatch), or the approval is stale, validation FAILS -> stop,
     re-scope, re-register. Only an unchanged, fresh, matching action passes.

Gives: (a) tamper-evidence (approval bound to a content hash, so a silently-changed
action can't ride an old yes), (b) a freshness window (a stale approval can't be
replayed later), (c) an audit trail of what was approved and when.

Exit codes (for scripting): 0 ok, 2 no-pending, 3 hash-mismatch, 4 expired.
Subcommands:
  register --action-file F [--kind K] [--summary S]
  validate --action-file F [--id cg-xxxx] [--max-age-min 30]
  list [--all]
"""
import argparse
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB = os.path.join(ROOT, "memory", "state", "confirm_gate.db")


def now():
    return datetime.now(timezone.utc)


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("""CREATE TABLE IF NOT EXISTS approvals(
        id TEXT PRIMARY KEY, full_hash TEXT, kind TEXT, summary TEXT,
        ts_registered TEXT, ts_approved TEXT, status TEXT)""")
    return c


def _hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def cmd_register(a):
    fh = _hash(a.action_file)
    aid = "cg-" + fh[:8]
    c = _conn()
    c.execute("""INSERT INTO approvals(id, full_hash, kind, summary, ts_registered, status)
                 VALUES(?,?,?,?,?, 'pending')
                 ON CONFLICT(id) DO UPDATE SET
                   kind=excluded.kind, summary=excluded.summary,
                   ts_registered=excluded.ts_registered, status='pending', ts_approved=NULL""",
              (aid, fh, a.kind or "", (a.summary or "")[:300], now().isoformat()))
    c.commit()
    c.close()
    print(f"{aid}  hash={fh[:8]}  kind={a.kind or '-'}")


def cmd_validate(a):
    fh = _hash(a.action_file)
    c = _conn()
    if a.id:
        row = c.execute("SELECT id, full_hash, ts_registered, status FROM approvals WHERE id=?",
                        (a.id,)).fetchone()
    else:
        row = c.execute("""SELECT id, full_hash, ts_registered, status FROM approvals
                           WHERE status='pending' ORDER BY ts_registered DESC LIMIT 1""").fetchone()
    if not row:
        print("NO_PENDING: nothing registered to validate against. register first.")
        c.close()
        sys.exit(2)
    aid, reg_hash, ts_reg, status = row
    if reg_hash != fh:
        print(f"MISMATCH: the action changed since it was approved (registered {reg_hash[:8]}, "
              f"about-to-run {fh[:8]}). STOP, re-scope, re-register {aid}.")
        c.close()
        sys.exit(3)
    try:
        age_min = (now() - datetime.fromisoformat(ts_reg)).total_seconds() / 60.0
    except Exception:
        age_min = 0
    if age_min > a.max_age_min:
        print(f"EXPIRED: {aid} approved {age_min:.0f}min ago (> {a.max_age_min}min). "
              f"re-scope + re-register for a fresh approval.")
        c.close()
        sys.exit(4)
    c.execute("UPDATE approvals SET status='approved', ts_approved=? WHERE id=?",
              (now().isoformat(), aid))
    c.commit()
    c.close()
    print(f"OK {aid}: action matches the approved hash + is fresh ({age_min:.0f}min). proceed.")
    sys.exit(0)


def cmd_list(a):
    c = _conn()
    q = "SELECT id, kind, status, ts_registered, ts_approved, summary FROM approvals"
    if not a.all:
        q += " WHERE status='pending'"
    q += " ORDER BY ts_registered DESC LIMIT 30"
    for r in c.execute(q):
        print(f"  {r[0]}  [{r[2]}]  {r[1] or '-'}  reg={r[3][:19]}  {(r[5] or '')[:60]}")
    c.close()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("register"); p.add_argument("--action-file", required=True)
    p.add_argument("--kind"); p.add_argument("--summary"); p.set_defaults(fn=cmd_register)
    p = sub.add_parser("validate"); p.add_argument("--action-file", required=True)
    p.add_argument("--id"); p.add_argument("--max-age-min", type=float, default=30)
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("list"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_list)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
