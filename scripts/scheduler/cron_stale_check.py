#!/usr/bin/env python3
# cron_stale_check.py: cron-aware missed-run detector, judged against the last expected fire.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Cron-aware missed-run detector for a self-audit pass.

Replaces a flat `last_run > 48h` gate, which false-positives every weekly/monthly schedule on
every nightly run (on one real scheduler: 18 of 59 schedules flagged, all on cadence). This parses
each cron_expr (in the scheduler's local timezone), computes the most recent expected fire before
now, and flags STALE only if last_run predates that fire by more than GRACE_H. A genuinely missed
weekly/monthly run still trips (its last_run is older than the last expected fire); an on-cadence
one does not. NEVER_RUN (null last_run) is still emitted so the audit can verify it against
execution_log. An unparseable cron falls back to the flat 48h gate so nothing is silently skipped.
Stdlib only (no croniter dependency).

NEVER_RUN is cron-aware too: a schedule created after its last expected fire but before its next
one has had zero opportunity to run yet (e.g. created Wednesday for a Sunday-only cron). Flagging
that as NEVER_RUN is a false positive the audit then has to spend a cycle discharging. It is
reported as PENDING_FIRST_FIRE (informational, not counted in the flagged total) instead.

Scheduler DB (SQLite, read-only here): $AGENT_SCHEDULER_DB, default $AGENT_DATA_DIR/scheduler.db.
Minimal schema it reads:
  schedules(name, cron_expr, enabled INTEGER, last_run TEXT ISO, created_at TEXT ISO)
Cron timezone: AGENT_UTC_OFFSET_HOURS (default 0 = UTC). Naive timestamps in the DB read as UTC.

Usage:
  cron_stale_check.py              # report; exit 1 if anything is flagged
  cron_stale_check.py --selftest
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
DB = os.environ.get("AGENT_SCHEDULER_DB", str(DATA_DIR / "scheduler.db"))
LOCAL_TZ = timezone(timedelta(hours=float(os.environ.get("AGENT_UTC_OFFSET_HOURS", "0"))))
GRACE_H = 2  # do not flag a fire that just elapsed and may still be about to run


def _field(expr, lo, hi):
    """One cron field -> set of allowed ints. Handles *, a-b, */n, a,b, a-b/n."""
    vals = set()
    for part in expr.split(","):
        step = 1
        rng = part
        if "/" in part:
            rng, s = part.split("/")
            step = int(s)
        if rng == "*":
            start, end = lo, hi
        elif "-" in rng:
            a, b = rng.split("-")
            start, end = int(a), int(b)
        else:
            start = end = int(rng)
        v = start
        while v <= end:
            vals.add(v)
            v += step
    return vals


def _matches(dt, mins, hrs, doms, mons, dows, dom_star, dow_star):
    if dt.minute not in mins or dt.hour not in hrs or dt.month not in mons:
        return False
    dom_ok = dt.day in doms
    cron_dow = (dt.weekday() + 1) % 7  # py Mon=0..Sun=6 -> cron Sun=0..Sat=6
    dow_ok = cron_dow in dows
    if dom_star and dow_star:
        return True
    if dom_star:
        return dow_ok
    if dow_star:
        return dom_ok
    return dom_ok or dow_ok  # both restricted -> OR (standard cron semantics)


def prev_fire(cron, now_local):
    """Most recent scheduled fire time <= now, in local time. None if cron unparseable."""
    try:
        mn, hr, dom, mon, dow = cron.split()
        mins = _field(mn, 0, 59)
        hrs = _field(hr, 0, 23)
        doms = _field(dom, 1, 31)
        mons = _field(mon, 1, 12)
        dows = _field(dow, 0, 7)
    except Exception:
        return None
    if 7 in dows:
        dows.add(0)  # cron allows 7 for Sunday
    dom_star = dom.strip() == "*"
    dow_star = dow.strip() == "*"
    t = now_local.replace(second=0, microsecond=0)
    for _ in range(40 * 24 * 60):  # walk back up to 40 days (covers weekly + monthly)
        if _matches(t, mins, hrs, doms, mons, dows, dom_star, dow_star):
            return t
        t -= timedelta(minutes=1)
    return None


def _aware(s):
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def check(rows, now=None):
    """rows: (name, cron, enabled, last_run, created_at). Returns (lines, flagged)."""
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(LOCAL_TZ)
    out, flagged = [], 0
    for name, cron, enabled, last_run, created_at in rows:
        if not enabled:
            continue  # disabled schedules cannot fire; not a missed run
        pf = prev_fire(cron, now_local)
        pf_utc = pf.astimezone(timezone.utc) if pf is not None else None
        if last_run:
            lr = _aware(last_run)
            if pf_utc is None:
                age_h = (now - lr).total_seconds() / 3600
                if age_h > 48:
                    out.append(f"STALE {age_h:.0f}h (cron unparsed): {name} ({cron})")
                    flagged += 1
                continue
            if lr < pf_utc and (now - pf_utc).total_seconds() / 3600 > GRACE_H:
                missed_h = (now - pf_utc).total_seconds() / 3600
                out.append(f"STALE: {name} ({cron}) last_run {lr.isoformat()[:16]} "
                           f"missed fire {pf.isoformat()[:16]} local ({missed_h:.0f}h ago)")
                flagged += 1
        else:
            ca = None
            if created_at:
                try:
                    ca = _aware(created_at)
                except Exception:
                    ca = None
            if pf_utc is not None and ca is not None and ca > pf_utc:
                out.append(f"PENDING_FIRST_FIRE: {name} ({cron}) created {ca.isoformat()[:16]}, "
                           f"next fire not yet reached")
                continue
            out.append(f"NEVER_RUN: {name}")
            flagged += 1
    return out, flagged


def _selftest():
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)  # a Wednesday
    rows = [
        ("daily-ok", "0 7 * * *", 1, "2026-10-21T07:00:10+00:00", "2026-09-01T00:00:00+00:00"),
        ("daily-missed", "0 7 * * *", 1, "2026-10-19T07:00:10+00:00", "2026-09-01T00:00:00+00:00"),
        ("weekly-ok", "0 7 * * 0", 1, "2026-10-18T07:00:05+00:00", "2026-09-01T00:00:00+00:00"),
        ("sunday-new", "0 7 * * 0", 1, None, "2026-10-20T00:00:00+00:00"),   # created after last Sunday
        ("never", "0 7 * * *", 1, None, "2026-09-01T00:00:00+00:00"),
        ("disabled", "0 7 * * *", 0, None, "2026-09-01T00:00:00+00:00"),
    ]
    lines, flagged = check(rows, now)
    text = "\n".join(lines)
    ok = (flagged == 2 and "STALE: daily-missed" in text and "NEVER_RUN: never" in text
          and "PENDING_FIRST_FIRE: sunday-new" in text and "weekly-ok" not in text)
    print(text)
    print(f"selftest {'PASS' if ok else 'FAIL'}: flagged={flagged}")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    if not os.path.exists(DB):
        print(f"cron-aware stale check: scheduler db missing: {DB}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT name, cron_expr, enabled, last_run, created_at FROM schedules ORDER BY last_run"
    ).fetchall()
    conn.close()
    lines, flagged = check(rows)
    for ln in lines:
        print(ln)
    print(f"cron-aware stale check: {flagged} flagged of {len(rows)} schedules")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
