#!/usr/bin/env python3
# verify_stack.py: read-only drive-and-prove harness, proves features reach the operator (L5), not just "up".
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
verify_stack.py . drive-and-prove harness for a long-running agent stack.

Adapted from pstack create-verification-skill (github.com/cursor/plugins, MIT, Lauren Tan), from
"launch an app" to "prove a long-running stack works for the person who uses it". A health check
answers "is it there" (process up, port open: L2 to L4 on the evidence ladder,
knowledge/evidence-ladder.md). This answers "did the feature reach the operator" (L5).

READ-ONLY by design. It never restarts, kills, writes, or sends anything. The one outbound drive
(the chat-reply check) is done by the agent with its own reply tool; this script only proves the
message landed (tg-check --nonce).

Usage:
  verify_stack.py doctor                     # scheduler process alive AND something went out recently
  verify_stack.py cockpit                    # cockpit answers AND serves current code
  verify_stack.py dashboard                  # optional published page: local + public URL, data age
  verify_stack.py cron [--name N]            # last run completed AND delivered a message
  verify_stack.py tg-check --nonce X         # outgoing message with nonce is in the message log
  verify_stack.py mcp                        # every MCP server handshakes + lists tools
  verify_stack.py all [--nonce X]            # everything above, one evidence dir
  verify_stack.py --selftest                 # fabricated DB, no live stack touched
Flags: --json (machine output). Evidence always written to outputs/verify/<ts>/<feature>.json
Exit: 0 all PASS (WARN/SKIP allowed) | 1 any FAIL | 2 usage error

Config (env, all optional):
  AGENT_ROOT, AGENT_DATA_DIR
  AGENT_SCHEDULER_DB    SQLite with schedules + execution_log (default $AGENT_DATA_DIR/scheduler.db)
  VERIFY_MESSAGES_DB    SQLite with the outgoing message log (default: the scheduler DB)
                        table messages(message_id, direction 'outgoing', chat_type, topic_name, text, timestamp ISO)
  VERIFY_DAEMON_PATTERN pgrep -f pattern for the scheduler daemon (default "scheduler")
  VERIFY_CRONS          comma list of schedules that must deliver daily
  COCKPIT_PORT          default 8787
  VERIFY_DASH_LOCAL_URL, VERIFY_DASH_PUBLIC_URL, VERIFY_DASH_DATA_FILE   dashboard check (SKIP when unset)
Important: point the message DB at the LIVE log. A frozen copy passes every check on old data.
"""
import argparse, glob, json, os, sqlite3, subprocess, sys, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.environ.get("AGENT_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.environ.get("AGENT_DATA_DIR") or os.path.join(ROOT, ".data")
SCHED_DB = os.environ.get("AGENT_SCHEDULER_DB") or os.path.join(DATA_DIR, "scheduler.db")
MSG_DB = os.environ.get("VERIFY_MESSAGES_DB") or SCHED_DB
EVIDENCE_DIR = os.path.join(ROOT, "outputs/verify")
COCKPIT_PORT = int(os.environ.get("COCKPIT_PORT", "8787"))
DEFAULT_CRONS = [c.strip() for c in os.environ.get("VERIFY_CRONS", "").split(",") if c.strip()]
DELIVERY_GRACE_S = 120


def _db(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _http(url, timeout=8):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "verify-stack/1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Last-Modified") or r.headers.get("Date"), len(r.read(4096))
    except Exception as e:  # noqa: BLE001 . any failure is the evidence
        return 0, str(e)[:120], 0


def _listener_pids(port):
    try:
        out = subprocess.run(["ss", "-ltnpH", f"sport = :{port}"], capture_output=True, text=True).stdout
    except OSError:
        return [], ""
    pids = sorted({p.split(",")[0] for p in out.split("pid=")[1:]})
    bind = out.split()[3] if out.split() else ""
    return pids, bind


def _proc_start(pid):
    """Process start as a UTC datetime (from /proc, no ps parsing)."""
    ticks = int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[19])
    boot = float([ln for ln in open("/proc/stat") if ln.startswith("btime")][0].split()[1])
    return datetime.fromtimestamp(boot + ticks / os.sysconf("SC_CLK_TCK"), timezone.utc)


def _aware(s):
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _r(feature, status, level, facts, fix=""):
    return {"feature": feature, "status": status, "level": level, "facts": facts, "fix": fix}


# ---------------------------------------------------------------- features
def f_doctor():
    pat = os.environ.get("VERIFY_DAEMON_PATTERN", "scheduler")
    pids = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True).stdout.split()
    pids = [p for p in pids if p != str(os.getpid())]
    last_out = None
    if os.path.exists(MSG_DB):
        try:
            with _db(MSG_DB) as c:
                last_out = c.execute("select max(timestamp) from messages where direction='outgoing'").fetchone()[0]
        except sqlite3.Error:
            last_out = None
    facts = {"daemon_pattern": pat, "daemon_pids": pids, "last_outgoing_message": last_out}
    if not pids:
        return _r("doctor", "FAIL", "L4", facts, "start the scheduler daemon first")
    if not last_out or _aware(last_out) < datetime.now(timezone.utc) - timedelta(hours=26):
        return _r("doctor", "WARN", "L4", facts, "no outgoing message in 26h: check the daemon's delivery path")
    return _r("doctor", "PASS", "L4", facts)


def f_cockpit():
    code, hdr, _ = _http(f"http://127.0.0.1:{COCKPIT_PORT}/")
    pids, bind = _listener_pids(COCKPIT_PORT)
    srcs = glob.glob(os.path.join(ROOT, "scripts/cockpit/*.py"))
    facts = {"http": code, "bind": bind, "pids": pids}
    if not srcs:
        return _r("cockpit", "SKIP", "L1", facts, "no cockpit source in scripts/cockpit/")
    newest = max(srcs, key=os.path.getmtime)
    newest_mt = datetime.fromtimestamp(os.path.getmtime(newest), timezone.utc)
    facts.update(newest_source=os.path.basename(newest), source_mtime=newest_mt.isoformat(timespec="seconds"))
    if code != 200 or not pids:
        return _r("cockpit", "FAIL", "L5", facts, "cockpit down: start it (or let its watchdog respawn it)")
    start = _proc_start(pids[0]); facts["process_start"] = start.isoformat(timespec="seconds")
    if not bind.startswith("127.0.0.1"):
        return _r("cockpit", "FAIL", "L5", facts, "cockpit bound beyond loopback (LAN exposed)")
    if start < newest_mt:
        return _r("cockpit", "FAIL", "L5", facts,
                  "serving STALE code (process older than source). Restart the cockpit, then re-run this check")
    return _r("cockpit", "PASS", "L5", facts)


def f_dashboard():
    local = os.environ.get("VERIFY_DASH_LOCAL_URL", "")
    public = os.environ.get("VERIFY_DASH_PUBLIC_URL", "")
    data = os.environ.get("VERIFY_DASH_DATA_FILE", "")
    if not (local or public):
        return _r("dashboard", "SKIP", "L1", {}, "set VERIFY_DASH_LOCAL_URL / VERIFY_DASH_PUBLIC_URL to check one")
    facts = {}
    if public:
        pcode, plast, _ = _http(public)
        facts.update(public_http=pcode, public_hdr=plast)
        if pcode != 200:
            return _r("dashboard", "FAIL", "L5", facts, "public URL not 200: check the hosting project")
    if local:
        lcode, _, _ = _http(local)
        facts["local_http"] = lcode
        if lcode != 200:
            return _r("dashboard", "WARN", "L5", facts, "local server down; decide if local serving is still wanted")
    if data and os.path.exists(data):
        built = datetime.fromtimestamp(os.path.getmtime(data), timezone.utc)
        age_d = (datetime.now(timezone.utc) - built).days
        facts.update(data_built=built.isoformat(timespec="seconds"), data_age_days=age_d)
        if age_d > 7:
            return _r("dashboard", "WARN", "L5", facts, f"page serves but its data is {age_d} days old: rebuild it")
    return _r("dashboard", "PASS", "L5", facts)


def f_cron(names=None, sched_db=None, msg_db=None, now=None):
    names = names or DEFAULT_CRONS
    sched_db, msg_db = sched_db or SCHED_DB, msg_db or MSG_DB
    now = now or datetime.now(timezone.utc)
    if not names:
        return _r("cron", "SKIP", "L1", {}, "pass --name or set VERIFY_CRONS to the schedules that must deliver")
    if not os.path.exists(sched_db):
        return _r("cron", "FAIL", "L4", {"db": sched_db}, "scheduler DB missing")
    rows, worst = [], "PASS"
    with _db(sched_db) as c, _db(msg_db) as m:
        for n in names:
            run = c.execute("select started_at, completed_at, status, substr(coalesce(error,''),1,160) "
                            "from execution_log where schedule_name=? order by started_at desc limit 1", (n,)).fetchone()
            if not run:
                rows.append({"name": n, "status": "FAIL", "why": "no execution_log row"}); worst = "FAIL"; continue
            st, done, status, err = run
            hi = (_aware(done) + timedelta(seconds=DELIVERY_GRACE_S)).isoformat() if done else st
            sent = m.execute("select count(*), min(message_id), max(message_id) from messages where direction='outgoing' "
                             "and timestamp between ? and ?", (st, hi)).fetchone()
            age_h = (now - _aware(st)).total_seconds() / 3600
            ok = status == "completed" and sent[0] > 0
            row = {"name": n, "started": st, "completed": done, "run_status": status, "error": err,
                   "messages_in_window": sent[0], "message_ids": [sent[1], sent[2]], "age_h": round(age_h, 1)}
            row["status"] = "PASS" if ok and age_h < 26 else ("WARN" if ok else "FAIL")
            if row["status"] == "WARN": row["why"] = "delivered but last run >26h ago (missed fires?)"
            if not ok: row["why"] = "run not completed" if status != "completed" else "completed but NOTHING was sent"
            rows.append(row)
            worst = "FAIL" if row["status"] == "FAIL" else ("WARN" if row["status"] == "WARN" and worst == "PASS" else worst)
    return _r("cron", worst, "L5", {"runs": rows},
              "" if worst == "PASS" else "open the failing run's error / output in execution_log")


def f_tg_check(nonce, window_min=15, msg_db=None, now=None):
    msg_db = msg_db or MSG_DB
    now = now or datetime.now(timezone.utc)
    if not nonce:
        return _r("tg-reply", "SKIP", "L1", {}, "drive first: send a log-channel message containing a nonce, then --nonce")
    since = (now - timedelta(minutes=window_min)).isoformat()
    with _db(msg_db) as c:
        hit = c.execute("select message_id, chat_type, topic_name, timestamp from messages where direction='outgoing' "
                        "and timestamp > ? and text like ? order by timestamp desc limit 1", (since, f"%{nonce}%")).fetchone()
    if not hit:
        return _r("tg-reply", "FAIL", "L5", {"nonce": nonce, "window_min": window_min},
                  "message not in the outgoing log: the send failed or the daemon is not logging")
    return _r("tg-reply", "PASS", "L5", {"nonce": nonce, "message_id": hit[0], "chat_type": hit[1],
                                          "topic": hit[2], "timestamp": hit[3]})


def f_mcp():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/mcp/mcp_smoke_test.py"), "--json", "--project"],
                         capture_output=True, text=True, timeout=180)
    try:
        d = json.loads(out.stdout)
    except Exception:  # noqa: BLE001
        return _r("mcp", "FAIL", "L4", {"error": (out.stderr or out.stdout)[-300:]}, "run mcp_smoke_test.py by hand")
    res = d.get("results", [])
    failed = [x.get("server") for x in res if x.get("ok") is False]   # ok None = spawn-skipped single consumer
    facts = {"servers": len(res), "failed": failed,
             "summary": {x.get("server"): f"{x.get('transport')}: {str(x.get('detail'))[:60]}" for x in res}}
    return _r("mcp", "FAIL" if failed else "PASS", "L4", facts,
              "" if not failed else "check the failing server's config in ~/.claude.json / .mcp.json")


FEATURES = {"doctor": f_doctor, "cockpit": f_cockpit, "dashboard": f_dashboard, "mcp": f_mcp}


def _save(ts_dir, res):
    os.makedirs(ts_dir, exist_ok=True)
    with open(os.path.join(ts_dir, f"{res['feature']}.json"), "w") as f:
        json.dump(res, f, indent=2, default=str)


def _selftest():
    import tempfile
    now = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "s.db")
        c = sqlite3.connect(db)
        c.execute("create table execution_log (schedule_name, started_at, completed_at, status, error)")
        c.execute("create table messages (message_id, direction, chat_type, topic_name, text, timestamp)")
        c.executemany("insert into execution_log values (?,?,?,?,?)", [
            ("morning-brief", "2026-10-21T07:00:00+00:00", "2026-10-21T07:03:00+00:00", "completed", None),
            ("silent-job", "2026-10-21T08:00:00+00:00", "2026-10-21T08:01:00+00:00", "completed", None)])
        c.executemany("insert into messages values (?,?,?,?,?,?)", [
            (101, "outgoing", "private", None, "brief text", "2026-10-21T07:02:30+00:00"),
            (102, "outgoing", "group", "logs", "probe zz-nonce-42", "2026-10-21T08:55:00+00:00")])
        c.commit(); c.close()
        cr = f_cron(["morning-brief", "silent-job", "missing-job"], db, db, now)
        tg = f_tg_check("zz-nonce-42", msg_db=db, now=now)
        tg_miss = f_tg_check("zz-absent", msg_db=db, now=now)
    st = {r["name"]: r["status"] for r in cr["facts"]["runs"]}
    ok = (st == {"morning-brief": "PASS", "silent-job": "FAIL", "missing-job": "FAIL"} and cr["status"] == "FAIL"
          and tg["status"] == "PASS" and tg["facts"]["message_id"] == 102 and tg_miss["status"] == "FAIL")
    print(f"selftest {'PASS' if ok else 'FAIL'}: cron={st} tg={tg['status']}/{tg_miss['status']}")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    ap = argparse.ArgumentParser()
    ap.add_argument("feature", choices=["doctor", "cockpit", "dashboard", "cron", "tg-check", "mcp", "all"])
    ap.add_argument("--name", action="append", help="cron schedule name (repeatable)")
    ap.add_argument("--nonce")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ts_dir = os.path.join(EVIDENCE_DIR, datetime.now().strftime("%Y-%m-%d-%H%M%S"))
    if a.feature == "all":
        results = [f() for f in FEATURES.values()] + [f_cron(a.name), f_tg_check(a.nonce)]
    elif a.feature == "cron":
        results = [f_cron(a.name)]
    elif a.feature == "tg-check":
        results = [f_tg_check(a.nonce)]
    else:
        results = [FEATURES[a.feature]()]
    for r in results:
        _save(ts_dir, r)
    if a.json:
        print(json.dumps({"evidence_dir": ts_dir, "results": results}, indent=2, default=str))
    else:
        for r in results:
            print(f"[{r['status']:4}] {r['feature']:9} ({r['level']}) {json.dumps(r['facts'], default=str)[:300]}")
            if r["fix"]:
                print(f"         fix: {r['fix']}")
        print(f"evidence: {ts_dir}")
    sys.exit(1 if any(r["status"] == "FAIL" for r in results) else 0)


if __name__ == "__main__":
    main()
