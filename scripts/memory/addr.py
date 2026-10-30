#!/usr/bin/env python3
# addr.py: findings ledger. Short addresses for subagent reports and cron runs.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Findings ledger: give every subagent report and cron run a short address, then pull it back by id.

Why: subagent and cron results are not addressable across sessions, so a later session re-runs the
work or re-reads whole transcripts. The agent CLI owns the context window, so this cannot be a
model-curated context (the "addressable memory" idea from plurnk); it is the cheap half: an index
with ids and one-line summaries, and the full text on demand.

Sources (read-only; nothing here writes to them):
  subagents  ~/.claude/projects/*/<session>/subagents/agent-*.jsonl  -> id s-<agentId[:9]>
             stores the brief (first user message) and the final report (SubagentHandback, else last text).
             Tool results inside the subagent are NOT stored.
  cron       $AGENT_SCHEDULER_DB execution_log                      -> id c-<execution_log.id>
  manual     addr.py put                                             -> id m-<sha1[:8]>
Store: $AGENT_DATA_DIR/addr.db (SQLite + FTS5). Every read command syncs first (incremental, by mtime/id).

  addr.py list [-n 20] [--kind subagent|cron|manual] [--since 2026-01-01]
  addr.py search "rate limit retry" [-n 10]
  addr.py get <id> [--brief]          full report (and the brief that produced it with --brief)
  addr.py put --title T [--file F]    store a finding by hand (stdin when no --file); prints its id
  addr.py sync                        index new items now; prints counts
  addr.py selftest

Env:
  AGENT_ROOT          repo root (default: two levels up)
  AGENT_DATA_DIR      ledger home (default $AGENT_ROOT/.data)
  AGENT_SCHEDULER_DB  scheduler SQLite with execution_log (default $AGENT_DATA_DIR/scheduler.db)
  ADDR_CRON_NOISE     comma-separated schedule names to skip (high-frequency status pings)
  ADDR_CRON_SINCE     earliest started_at to index on the first build (default: everything)
Check this ledger BEFORE redoing a research or audit task: a past report may already answer it.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(REPO / ".data")))
DB = DATA_DIR / "addr.db"
SCHED_DB = Path(os.environ.get("AGENT_SCHEDULER_DB", str(DATA_DIR / "scheduler.db")))
SUBAGENT_GLOB = str(HOME / ".claude/projects/*/*/subagents/agent-*.jsonl")
SUMMARY_CHARS = 160
MIN_CRON_CHARS = 200
CRON_EXCERPT = 4000  # stored for search; get reads the full output from the scheduler db
CRON_SINCE = os.environ.get("ADDR_CRON_SINCE", "")
# High-frequency status jobs (watchdogs, refreshers) can be most of the rows and carry no finding.
CRON_NOISE = tuple(n.strip() for n in os.environ.get("ADDR_CRON_NOISE", "").split(",") if n.strip())


def connect(path=DB):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript("""
        create table if not exists items(id text primary key, kind text, source text, created text,
            title text, summary text, brief text, body text);
        create virtual table if not exists items_fts using fts5(id unindexed, title, summary, body);
        create table if not exists seen(path text primary key, mtime real);
    """)
    return con


def first_line(text):
    t = re.sub(r"\s+", " ", (text or "").strip())
    m = re.match(r"(.{20,}?[.!?])\s", t[:SUMMARY_CHARS + 40] + " ")
    s = m.group(1) if m else t
    return s[:SUMMARY_CHARS] + ("..." if len(s) > SUMMARY_CHARS else "")


def upsert(con, item):
    """items_fts shares items' rowid, so replacing one row is two indexed deletes, not a scan."""
    old = con.execute("select rowid from items where id = ?", (item["id"],)).fetchone()
    if old:
        con.execute("delete from items_fts where rowid = ?", old)
        con.execute("delete from items where rowid = ?", old)
    cur = con.execute("insert into items values (:id,:kind,:source,:created,:title,:summary,:brief,:body)", item)
    con.execute("insert into items_fts(rowid,id,title,summary,body) values (?,?,?,?,?)",
                (cur.lastrowid, item["id"], item["title"], item["summary"], item["body"]))


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(x.get("text", "") for x in content or [] if x.get("type") == "text")


def parse_subagent(path):
    rows = []
    for line in open(path, errors="ignore"):
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    brief = next((text_of(r["message"].get("content")) for r in rows if r.get("type") == "user"), "")
    report, created = "", ""
    for r in reversed([r for r in rows if r.get("type") == "assistant"]):
        for x in r["message"].get("content") or []:
            if x.get("type") == "tool_use" and x.get("name") == "SubagentHandback":
                report = str(x.get("input", {}).get("message", ""))
            elif x.get("type") == "text" and x.get("text", "").strip() and not report:
                report = x["text"]
        if report:
            created = r.get("timestamp", "")
            break
    if not report:
        return None
    meta = {}
    mp = Path(path).with_suffix(".meta.json")
    if mp.exists():
        try:
            meta = json.loads(mp.read_text())
        except ValueError:
            pass
    agent = Path(path).stem.replace("agent-", "")
    return {"id": f"s-{agent[:9]}", "kind": "subagent", "source": str(path), "created": created[:19],
            "title": meta.get("description") or first_line(brief), "summary": first_line(report),
            "brief": brief, "body": report}


def sync(con, subagent_glob=SUBAGENT_GLOB, sched_db=SCHED_DB):
    new_s = new_c = 0
    seen = dict(con.execute("select path, mtime from seen"))
    for p in glob.glob(subagent_glob):
        mt = os.path.getmtime(p)
        if seen.get(p) == mt:
            continue
        item = parse_subagent(p)
        if item:
            upsert(con, item)
            new_s += 1
        con.execute("insert or replace into seen values (?,?)", (p, mt))
    if Path(sched_db).exists():
        # execution_log ids are random hex, so the watermark is started_at, not id.
        last = con.execute("select max(created) from items where kind='cron'").fetchone()[0] or CRON_SINCE
        src = sqlite3.connect(f"file:{sched_db}?mode=ro", uri=True)
        try:
            for eid, name, started, status, out, err in src.execute(
                    "select id, schedule_name, started_at, status, output, error from execution_log "
                    "where started_at > ? and completed_at is not null order by started_at", (last,)):
                body = (out or "") + (f"\n[error] {err}" if err else "")
                if len(body.strip()) < MIN_CRON_CHARS or name in CRON_NOISE:
                    continue  # heartbeats, "message sent" lines and status pings carry no finding
                upsert(con, {"id": f"c-{eid}", "kind": "cron", "source": f"scheduler execution_log {eid}",
                             "created": started or "", "title": f"{name} ({status})",
                             "summary": first_line(out or err), "brief": "", "body": body[:CRON_EXCERPT]})
                new_c += 1
        finally:
            src.close()
    con.commit()
    return new_s, new_c


def show_rows(rows):
    for id_, kind, created, title, summary in rows:
        print(f"{id_:13} {created[:16].replace('T', ' '):16} {kind[:4]:4} {title[:60]}")
        print(f"{'':36}{summary}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("-n", type=int, default=20); p.add_argument("--kind"); p.add_argument("--since")
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("-n", type=int, default=10)
    p = sub.add_parser("get"); p.add_argument("id"); p.add_argument("--brief", action="store_true")
    p = sub.add_parser("put"); p.add_argument("--title", required=True); p.add_argument("--file")
    sub.add_parser("sync")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    con = connect()
    if a.cmd == "put":
        body = Path(a.file).read_text() if a.file else sys.stdin.read()
        id_ = "m-" + hashlib.sha1(body.encode()).hexdigest()[:8]
        upsert(con, {"id": id_, "kind": "manual", "source": a.file or "stdin",
                     "created": __import__("datetime").datetime.now().isoformat()[:19],
                     "title": a.title, "summary": first_line(body), "brief": "", "body": body})
        con.commit()
        print(id_)
        return 0
    s, c = sync(con)
    if a.cmd == "sync":
        total = con.execute("select count(*) from items").fetchone()[0]
        print(f"indexed {s} subagent, {c} cron item(s); {total} in ledger")
    elif a.cmd == "list":
        q, args = "select id, kind, created, title, summary from items where 1=1", []
        if a.kind:
            q += " and kind = ?"; args.append(a.kind)
        if a.since:
            q += " and created >= ?"; args.append(a.since)
        show_rows(con.execute(q + " order by created desc limit ?", args + [a.n]).fetchall())
    elif a.cmd == "search":
        terms = " ".join(f'"{t}"' for t in re.findall(r"\w+", a.query))
        rows = con.execute("select i.id, i.kind, i.created, i.title, i.summary from items_fts f "
                           "join items i on i.id = f.id where items_fts match ? order by rank limit ?",
                           (terms, a.n)).fetchall()
        show_rows(rows) if rows else print("no match")
    elif a.cmd == "get":
        r = con.execute("select id, kind, source, created, title, brief, body from items where id = ? or id like ?",
                        (a.id, a.id + "%")).fetchall()
        if len(r) != 1:
            print(f"{len(r)} items match {a.id!r}" + ("; give more characters" if r else ""))
            return 1
        id_, kind, source, created, title, brief, body = r[0]
        if kind == "cron" and SCHED_DB.exists():
            src = sqlite3.connect(f"file:{SCHED_DB}?mode=ro", uri=True)
            full = src.execute("select output, error from execution_log where id = ?", (id_[2:],)).fetchone()
            src.close()
            if full:
                body = (full[0] or "") + (f"\n[error] {full[1]}" if full[1] else "")
        print(f"# {id_} · {kind} · {created}\n# {title}\n# source: {source}\n")
        if a.brief and brief:
            print(f"## Brief\n{brief}\n\n## Report")
        print(body)
    return 0


def selftest():
    """Control pair: a planted subagent transcript and a planted cron row must both become addressable."""
    tmp = Path(tempfile.mkdtemp())
    sess = tmp / "proj" / "sess" / "subagents"
    sess.mkdir(parents=True)
    t = sess / "agent-zzselftest123.jsonl"
    rows = [{"type": "user", "message": {"content": "Brief: count the zebras."}},
            {"type": "assistant", "timestamp": "2026-10-20T10:00:00Z",
             "message": {"content": [{"type": "tool_use", "name": "SubagentHandback",
                                      "input": {"message": "Found 7 zebras in the planted file. Done."}}]}}]
    t.write_text("\n".join(json.dumps(r) for r in rows))
    udb = tmp / "scheduler.db"
    u = sqlite3.connect(udb)
    u.execute("create table execution_log(id integer primary key, schedule_id, schedule_name, started_at, completed_at, status, output, error)")
    u.execute("insert into execution_log values (41, 'x', 'zebra-cron', '2026-10-20T09:00:00', '2026-10-20T09:01:00', 'success', ?, null)",
              ("Counted okapis today. " + "detail " * 40,))
    u.execute("insert into execution_log values (42, 'x', 'ping', '2026-10-20T09:02:00', '2026-10-20T09:02:01', 'success', 'Message sent', null)")
    u.commit(); u.close()
    con = connect(tmp / "addr.db")
    s, c = sync(con, str(tmp / "*" / "*" / "subagents" / "agent-*.jsonl"), udb)
    again = sync(con, str(tmp / "*" / "*" / "subagents" / "agent-*.jsonl"), udb)
    got_s = con.execute("select body, brief from items where id = 's-zzselftes'").fetchone()
    got_c = con.execute("select title from items where id = 'c-41'").fetchone()
    hit = con.execute("select id from items_fts where items_fts match '\"okapis\"'").fetchone()
    ok = (s, c) == (1, 1) and again == (0, 0) and got_s and "7 zebras" in got_s[0] and "zebras" in got_s[1] \
        and got_c == ("zebra-cron (success)",) and hit == ("c-41",)
    print(f"selftest {'PASS' if ok else 'FAIL'}: first sync {s}+{c}, resync {again}, subagent={bool(got_s)}, cron={got_c}, fts={hit}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
