#!/usr/bin/env python3
# reply_obligations.py — persist + redeliver owed Telegram replies across sessions.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Reply delivery-obligation ledger.

Closes the crash-loss tail of a non-zero Telegram reply-miss rate. When a turn ends
owing a reply that never got sent AND the session gets no further turn to
self-correct (the stop-hook's exit-2 retry only works if the model gets another
turn), the owed reply is persisted here and REDELIVERED on the next SessionStart
via a direct Telegram Bot API call (plain text), independent of the plugin.

Suited to a spawned/killed session model (short-lived CLI sessions, not an
always-on gateway).

Guards:
  - double-send (the real risk): obligations are keyed (session_id, inbound_msg_id);
    redelivery CLAIMS each row atomically (pending -> sending, one winner) BEFORE
    sending, and only ever touches PRIOR-session pendings older than a grace window,
    never the live session's (which can still self-correct). A reply the model
    self-corrects in-session is cancelled by the stop-hook's OK path.
  - token: the bot token is read from an env file at redeliver time, never
    stored in the ledger, never logged, and scrubbed from any error string.
  - fail-open: every subcommand exits 0 on error so a hook can never block a
    session start or stop.

Subcommands:
  persist  --session S --msg-id M --chat-id C --text-file F   (stop-hook, on MISS)
  cancel   --session S --msg-id M                             (stop-hook, on OK/self-corrected)
  redeliver --session S [--grace 90] [--max-attempts 3] [--dry-run]  (SessionStart)
  list     [--all]                                            (inspection)
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB = os.path.join(ROOT, "memory", "state", "reply_obligations.db")
DAEMON_ENV = os.environ.get("BOT_TOKEN_ENV_FILE") or os.path.expanduser("~/.config/agent/.env")
TZ = timezone.utc


def now_iso():
    return datetime.now(TZ).isoformat()


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS obligations(
        id INTEGER PRIMARY KEY,
        session_id TEXT, inbound_msg_id TEXT, chat_id TEXT, text TEXT,
        ts_owed TEXT, status TEXT, attempts INTEGER DEFAULT 0,
        ts_delivered TEXT, err TEXT,
        UNIQUE(session_id, inbound_msg_id))""")
    return c


def cmd_persist(a):
    with open(a.text_file, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if not text.strip() or not a.chat_id:
        return  # nothing worth redelivering / nowhere to send it
    c = _conn()
    # INSERT OR REPLACE resets a prior pending for the same (session,msg) to fresh.
    c.execute("""INSERT INTO obligations
        (session_id, inbound_msg_id, chat_id, text, ts_owed, status, attempts)
        VALUES (?,?,?,?,?, 'pending', 0)
        ON CONFLICT(session_id, inbound_msg_id) DO UPDATE SET
          chat_id=excluded.chat_id, text=excluded.text,
          ts_owed=excluded.ts_owed, status='pending'""",
              (a.session, a.msg_id, a.chat_id, text, now_iso()))
    c.commit()
    c.close()
    print("persisted")


def cmd_cancel(a):
    # The model self-corrected this turn (reply landed): retire the pending owe.
    c = _conn()
    c.execute("""UPDATE obligations SET status='cancelled'
                 WHERE session_id=? AND inbound_msg_id=? AND status='pending'""",
              (a.session, a.msg_id))
    c.commit()
    c.close()


def _bot_token():
    if not os.path.exists(DAEMON_ENV):
        return None
    tok = None
    with open(DAEMON_ENV) as f:
        env = {}
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for key in ("TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TG_BOT_TOKEN"):
        if env.get(key):
            tok = env[key]
            break
    return tok


def _scrub(msg, token):
    # never let the token surface in a logged error string
    if token and msg:
        msg = msg.replace(token, "<token>")
    return msg


def _send(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
            return bool(body.get("ok")), ""
    except Exception as e:
        return False, _scrub(str(e), token)


def cmd_redeliver(a):
    token = _bot_token()
    grace_before = (datetime.now(TZ) - timedelta(seconds=a.grace)).isoformat()
    c = _conn()
    # recover crash-leftover claims: 'sending' is only ever a transient in-process
    # state, so any 'sending' row seen at the start of a run is from a dead prior run.
    c.execute("UPDATE obligations SET status='pending' WHERE status='sending'")
    c.commit()
    rows = c.execute(
        """SELECT id, chat_id, text, attempts FROM obligations
           WHERE status='pending' AND session_id != ? AND ts_owed < ?
                 AND attempts < ? ORDER BY id""",
        (a.session, grace_before, a.max_attempts)).fetchall()
    sent = failed = skipped = 0
    for oid, chat_id, text, attempts in rows:
        # CLAIM atomically: only one runner flips pending->sending, then sends.
        # No attempt increment on claim (a dry-run / missing-token release must not
        # consume a retry); attempts only advances on a real send failure.
        cur = c.execute(
            "UPDATE obligations SET status='sending' "
            "WHERE id=? AND status='pending'", (oid,))
        c.commit()
        if cur.rowcount != 1:
            skipped += 1
            continue
        if a.dry_run or not token:
            c.execute("UPDATE obligations SET status='pending' WHERE id=?", (oid,))
            c.commit()
            skipped += 1
            continue
        ok, err = _send(token, chat_id, text)
        if ok:
            c.execute("UPDATE obligations SET status='delivered', ts_delivered=? "
                      "WHERE id=?", (now_iso(), oid))
            sent += 1
        else:
            new_attempts = attempts + 1
            new_status = "failed" if new_attempts >= a.max_attempts else "pending"
            c.execute("UPDATE obligations SET status=?, attempts=?, err=? WHERE id=?",
                      (new_status, new_attempts, (err or "")[:300], oid))
            failed += 1
        c.commit()
    c.close()
    print(json.dumps({"candidates": len(rows), "sent": sent,
                      "failed": failed, "skipped": skipped,
                      "token": bool(token), "dry_run": a.dry_run}))


def cmd_list(a):
    c = _conn()
    q = "SELECT id, session_id, inbound_msg_id, chat_id, status, attempts, ts_owed, ts_delivered FROM obligations"
    if not a.all:
        q += " WHERE status IN ('pending','sending','failed')"
    q += " ORDER BY id DESC LIMIT 50"
    for r in c.execute(q):
        print(json.dumps(dict(zip(
            ["id", "session", "msg_id", "chat_id", "status", "attempts", "ts_owed", "ts_delivered"], r))))
    c.close()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("persist"); p.add_argument("--session", required=True)
    p.add_argument("--msg-id", required=True); p.add_argument("--chat-id", required=True)
    p.add_argument("--text-file", required=True); p.set_defaults(fn=cmd_persist)
    p = sub.add_parser("cancel"); p.add_argument("--session", required=True)
    p.add_argument("--msg-id", required=True); p.set_defaults(fn=cmd_cancel)
    p = sub.add_parser("redeliver"); p.add_argument("--session", required=True)
    p.add_argument("--grace", type=int, default=90); p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_redeliver)
    p = sub.add_parser("list"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_list)
    a = ap.parse_args()
    try:
        a.fn(a)
    except Exception as e:
        # fail-open: a hook must never block on a broken ledger
        print(json.dumps({"error": str(e)[:200]}), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
