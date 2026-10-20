#!/usr/bin/env python3
# cron_runcount_probe.py: flag scheduled tasks that were built but never fired.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Flag scheduled tasks that were BUILT but never fired (run_count 0, aged > 7d).

BUILT and LIVE render identically in a scheduler until you look at run_count. A cron created then
never fired (a bad cron_expr, a disabled-and-forgotten task, an unregistered command) sits at
run_count 0 forever and reads as "shipped". This surfaces it on its own instead of waiting for a
periodic review. Report-only: it never disables or edits anything.

Rule: enabled=1 AND run_count=0 AND created_at older than AGE_DAYS (default 7).
next_run + cron_expr are shown so a legitimately-not-yet-due rare cron (monthly) is self-evident
to the reader rather than silently dropped.

Scheduler DB (SQLite, read-only here): $AGENT_SCHEDULER_DB, default $AGENT_DATA_DIR/scheduler.db.
Minimal schema it reads:
  schedules(id, name, cron_expr, enabled INTEGER, run_count INTEGER, created_at TEXT ISO, next_run TEXT)

Usage:
    cron_runcount_probe.py             # human report, exit 1 if any flagged
    cron_runcount_probe.py --json      # machine output
    cron_runcount_probe.py --notify    # chat ping to the operator ONLY if flagged (silent when clean)
    cron_runcount_probe.py --selftest  # fabricated DB in a temp dir
Notify needs TELEGRAM_BOT_TOKEN + OPERATOR_CHAT_ID in the env (or in $AGENT_NOTIFY_ENV).
Exit 2 = the probe itself failed (fail-loud: a broken probe must never read as "clean").
"""
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
DB = Path(os.environ.get("AGENT_SCHEDULER_DB", str(DATA_DIR / "scheduler.db")))
SESSION_LOG = Path(os.environ.get("AGENT_LOG_DIR", str(ROOT / "logs"))) / "session.jsonl"
NOTIFY_ENV = Path(os.environ.get("AGENT_NOTIFY_ENV", str(ROOT / ".env")))
AGE_DAYS = 7


def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def find_flagged(db=None):
    db = Path(db or DB)
    if not db.exists():
        return None, f"scheduler db missing: {db}"
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        cols = [r[1] for r in c.execute("PRAGMA table_info(schedules)")]
        rows = [dict(zip(cols, r)) for r in c.execute("SELECT * FROM schedules")]
        c.close()
    except Exception as e:
        return None, f"scheduler db read failed: {type(e).__name__}: {e}"
    cutoff = now_utc() - timedelta(days=AGE_DAYS)
    flagged = []
    for r in rows:
        if r.get("enabled") != 1 or r.get("run_count") != 0:
            continue
        created = parse_iso(r.get("created_at"))
        if created is None or created >= cutoff:
            continue
        flagged.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "cron_expr": r.get("cron_expr"),
            "created_at": r.get("created_at"),
            "next_run": r.get("next_run"),
            "age_days": (now_utc() - created).days,
        })
    flagged.sort(key=lambda x: x["age_days"], reverse=True)
    return flagged, None


def log(event):
    try:
        SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SESSION_LOG.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _notify_creds():
    tok, cid = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("OPERATOR_CHAT_ID")
    if (not tok or not cid) and NOTIFY_ENV.exists():
        for line in NOTIFY_ENV.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "TELEGRAM_BOT_TOKEN" and not tok:
                tok = v.strip()
            elif k.strip() == "OPERATOR_CHAT_ID" and not cid:
                cid = v.strip()
    return tok, cid


def notify(text):
    """Best-effort chat ping. The bot credential goes in the request body, never argv or logs."""
    tok, cid = _notify_creds()
    if not tok or not cid:
        return
    try:
        data = urllib.parse.urlencode({"chat_id": cid, "text": text}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=15).read()
    except Exception:
        pass


def _selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "scheduler.db"
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE schedules (id TEXT, name TEXT, cron_expr TEXT, enabled INTEGER, "
                  "run_count INTEGER, created_at TEXT, next_run TEXT)")
        old = (now_utc() - timedelta(days=20)).isoformat()
        new = (now_utc() - timedelta(days=2)).isoformat()
        c.executemany("INSERT INTO schedules VALUES (?,?,?,?,?,?,?)", [
            ("1", "never-fired-old", "0 7 * * *", 1, 0, old, None),     # flagged
            ("2", "never-fired-new", "0 7 * * *", 1, 0, new, None),     # too young
            ("3", "fires-fine", "0 7 * * *", 1, 12, old, None),         # has runs
            ("4", "disabled", "0 7 * * *", 0, 0, old, None),            # disabled
        ])
        c.commit(); c.close()
        flagged, err = find_flagged(db)
    ok = err is None and [f["name"] for f in flagged] == ["never-fired-old"]
    missing, err2 = find_flagged(Path(td) / "nope.db")
    ok = ok and missing is None and "missing" in (err2 or "")
    print(f"selftest {'PASS' if ok else 'FAIL'}: flagged={[f['name'] for f in flagged or []]}")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    flagged, err = find_flagged()
    if err:
        print(f"runcount-probe ERROR: {err}", file=sys.stderr)
        log({"ts": now_utc().isoformat(), "category": "runcount_probe",
             "event": "probe_error", "error": err})
        if "--notify" in sys.argv:
            notify(f"runcount-probe ERROR: {err}")
        return 2

    if "--json" in sys.argv:
        print(json.dumps({"flagged": flagged, "count": len(flagged)}, indent=2))
    elif flagged:
        print(f"{len(flagged)} BUILT-but-never-fired cron(s) (run_count 0, aged > {AGE_DAYS}d, enabled):")
        for f_ in flagged:
            print(f"  {f_['name']} ({f_['id']}) cron='{f_['cron_expr']}' "
                  f"created {str(f_['created_at'])[:10]} ({f_['age_days']}d) next_run={f_['next_run']}")
        print("  note: a rare-schedule cron (monthly) may legitimately appear; check cron_expr + next_run.")
    else:
        print(f"runcount-probe clean: no enabled cron at run_count 0 older than {AGE_DAYS}d.")

    log({"ts": now_utc().isoformat(), "category": "runcount_probe",
         "event": "flagged" if flagged else "clean", "count": len(flagged),
         "names": [f_["name"] for f_ in flagged]})

    if flagged and "--notify" in sys.argv:
        lines = "\n".join(
            f"  {f_['name']} cron='{f_['cron_expr']}' ({f_['age_days']}d, run_count 0)"
            for f_ in flagged)
        notify(f"probe: {len(flagged)} cron(s) BUILT but never fired "
               f"(run_count 0, >{AGE_DAYS}d):\n{lines}\n"
               f"check cron_expr (rare/monthly may be legit); else fix or delete.")

    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
