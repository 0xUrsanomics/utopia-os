#!/usr/bin/env python3
# self_audit_prior_record.py: print prior decisions and the 14-day run series under each self-audit item.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Prior-record check for self-audit items.

Why: a nightly self-audit keeps misreading items that already have a history. Typical misses: runs
killed by their own timeout read as "a hang", a decision already shipped gets re-queued, a timeout
called "isolated" when the run log shows four in a row. A prose rule ("reconcile against
Decisions.md first") exists and does not fire. A printout under each item is checkable; a rule deep
inside a long skill file is not.

For each queued or BLOCKER item it prints:
  1. matches in memory/Decisions.md, the open proposal ledger (memory/state/meta_review_proposals.json)
     and memory/Infra/cron-persistent-misses.md, when those exist
  2. for every schedule the item names, the 14-day execution_log series, each run's duration against the
     schedule's timeout, and whether output landed (a run whose minutes equal its timeout is a cap-kill)

Scheduler DB (SQLite, read-only): $AGENT_SCHEDULER_DB, default $AGENT_DATA_DIR/scheduler.db.
Minimal schema it reads:
  schedules(name, task_config TEXT JSON with optional timeout_seconds or timeout)
  execution_log(schedule_name, started_at TEXT ISO, completed_at TEXT ISO, status TEXT, output TEXT)
  status 'completed' = a good run; anything else is listed.

Usage:
  self_audit_prior_record.py "rss 07:30 timeout" "email-harvester failing"
  self_audit_prior_record.py --items-file /path/items.txt      # one item per line
  self_audit_prior_record.py --selftest
Read-only. Exit 0 always (it informs the audit, it never blocks it).
"""
import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DECISIONS = REPO / "memory/Decisions.md"
LEDGER = REPO / "memory/state/meta_review_proposals.json"
MISSES = REPO / "memory/Infra/cron-persistent-misses.md"
DB = Path(os.environ.get("AGENT_SCHEDULER_DB",
                         str(Path(os.environ.get("AGENT_DATA_DIR", str(REPO / ".data"))) / "scheduler.db")))
STOP = set("the and for with that this from into not are was were has have had but its our any all one two "
           "item items run runs ran cron fail failed failing error errors issue check slot again still open "
           "queued blocker warning new old fix fixed today daily weekly".split())
CAP_SLACK_S = 60


def keywords(item):
    toks = re.findall(r"[A-Za-z0-9][\w.:/-]{2,}", item.lower())
    return [t for t in dict.fromkeys(toks) if t not in STOP and not t.isdigit()][:8]


def grep(path, kws, limit=4):
    if not path.exists():
        return [f"(missing: {path})"]
    hits = []
    for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        low = line.lower()
        score = sum(k in low for k in kws)
        if score >= min(2, len(kws)):
            hits.append((score, n, line.strip()[:160]))
    hits.sort(key=lambda h: (-h[0], -h[1]))
    return [f"L{n} [{s}/{len(kws)}] {t}" for s, n, t in hits[:limit]]


def ledger_hits(kws):
    try:
        d = json.loads(LEDGER.read_text())
    except Exception:
        return ["(ledger unreadable)"]
    rows = d if isinstance(d, list) else d.get("proposals", d)
    rows = rows.values() if isinstance(rows, dict) else rows
    out = []
    for r in rows:
        blob = json.dumps(r).lower()
        if sum(k in blob for k in kws) >= min(2, len(kws)):
            out.append(f"{r.get('id')} state={r.get('state')} :: {str(r.get('title', ''))[:110]}")
    return out[:4]


def schedule_series(item, con):
    names = [n for (n,) in con.execute("select name from schedules")]
    low = item.lower()
    named = [n for n in names if n in low] or [n for n in names if n.replace("-", " ") in low]
    out = []
    since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    for n in named:
        cfg = json.loads(con.execute("select task_config from schedules where name=?", (n,)).fetchone()[0] or "{}")
        cap = cfg.get("timeout_seconds") or cfg.get("timeout")
        rows = con.execute("select started_at, completed_at, status, length(coalesce(output,'')) from execution_log "
                           "where schedule_name=? and started_at>=? order by started_at", (n, since)).fetchall()
        bad = [r for r in rows if r[2] != "completed"]
        out.append(f"{n}: {len(rows)} runs in 14d, {len(bad)} not completed, timeout {cap or 'unset'} s")
        for a, b, st, olen in rows:
            if st == "completed":
                continue
            try:
                dur = (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() if b else None
            except Exception:
                dur = None
            capkill = cap and dur is not None and abs(dur - float(cap)) <= CAP_SLACK_S
            # a run that stops on an exact whole minute is a leash, even if the leash has since changed
            exact = dur is not None and dur >= 600 and abs(dur - round(dur / 60) * 60) <= 5
            flag = "  CAP-KILL (duration = timeout)" if capkill else ("  likely CAP-KILL (exact whole-minute run, older leash?)" if exact else "")
            out.append(f"   {a[:16]}Z {st:<9} {('%.1f min' % (dur / 60)) if dur else 'open':>9}  output {olen} B{flag}")
    return out


def _selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        con = sqlite3.connect(os.path.join(td, "s.db"))
        con.execute("create table schedules (name text, task_config text)")
        con.execute("create table execution_log (schedule_name text, started_at text, completed_at text, "
                    "status text, output text)")
        con.execute("insert into schedules values ('rss-poll', ?)", (json.dumps({"timeout_seconds": 900}),))
        t0 = datetime.now(timezone.utc) - timedelta(days=1)
        rows = [(t0, 900, "failed", ""), (t0 + timedelta(hours=1), 120, "completed", "ok")]
        for st, dur, status, out in rows:
            con.execute("insert into execution_log values ('rss-poll', ?, ?, ?, ?)",
                        (st.isoformat(), (st + timedelta(seconds=dur)).isoformat(), status, out))
        con.commit()
        ser = schedule_series("rss-poll timed out again", con)
        con.close()
    text = "\n".join(ser)
    ok = "2 runs in 14d, 1 not completed" in text and "CAP-KILL (duration = timeout)" in text
    print(text)
    print(f"selftest {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items", nargs="*")
    ap.add_argument("--items-file")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    items = list(a.items)
    if a.items_file:
        items += [l.strip() for l in Path(a.items_file).read_text().splitlines() if l.strip()]
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True) if DB.exists() else None
    except Exception:
        con = None
    for it in items:
        kws = keywords(it)
        print(f"## Prior record: {it}\nkeywords: {', '.join(kws)}")
        for label, lines in (("Decisions.md", grep(DECISIONS, kws)), ("open ledger", ledger_hits(kws)),
                             ("cron-persistent-misses.md", grep(MISSES, kws))):
            print(f"- {label}: " + ("none" if not lines else ""))
            for l in lines:
                print(f"    {l}")
        if con:
            try:
                ser = schedule_series(it, con)
            except Exception as e:
                ser = [f"(execution_log read failed: {e})"]
            if ser:
                print("- 14-day slot series:")
                for l in ser:
                    print(f"    {l}")
        print()


if __name__ == "__main__":
    raise SystemExit(main() or 0)
