#!/usr/bin/env python3
# fleet_bus.py — the multi-agent coordination spine: a tiny typed SQLite message bus.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""fleet_bus — the multi-agent coordination spine.

A tiny SQLite message bus so agent tenants hand off work to each other WITHOUT a
chat channel (design decision: the chat channel is the human/QC edge, NOT the
coordination backbone. N agents on one chat = N x the poller-drift/OAuth/ENOENT pain).

Generalizes a proven write-queue primitive into a typed, bidirectional, status-tracked,
N-agent bus. Own DB file (decoupled from any scheduler DB to avoid lock contention).

Message lifecycle:  pending --claim--> claimed --complete--> done   (or --fail--> failed)
Task->result threading via parent_id (a 'result' msg references the 'task' msg it answers).

Task DEPENDENCIES: a task can declare `--depends-on id1,id2`. It is BLOCKED (hidden from
poll) until every dep is status='done'. So poll = ready-task detection. deps point only at existing ids
=> the graph is append-only + acyclic. `blocked` is the bottleneck view; `critical-path` = longest chain.

CLI (for an inbox-watcher + agents to call from shell; all emit JSON):
  fleet_bus.py init
  fleet_bus.py publish --from hub --to runner --type task --payload '{"do":"..."}' [--priority 5] [--parent <id>] [--depends-on <id1,id2>]
  fleet_bus.py poll --agent runner [--include-blocked]   # READY pending msgs for runner (deps satisfied); --include-blocked shows all
  fleet_bus.py claim --id <id>                     # atomic; prints the claimed row or {} if lost the race
  fleet_bus.py complete --id <id> --result '{...}' # marks done + auto-publishes a 'result' msg back to from_agent
  fleet_bus.py fail --id <id> --err "..."
  fleet_bus.py list [--agent X] [--status pending] [--limit 20]
  fleet_bus.py deps --id <id>                       # a task's deps + statuses + is-it-ready
  fleet_bus.py blocked [--agent X]                  # pending tasks with unmet deps + what blocks them
  fleet_bus.py critical-path                        # longest dependency chain among not-done tasks
"""
from __future__ import annotations
import argparse, json, os, re, sqlite3, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

# AGENT_ROOT defaults to the repo root (this file is scripts/agents/fleet_bus.py).
ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
DB = DATA_DIR / "fleet_bus.db"
# Roster v1. Generic illustrative tenants — rename/extend to taste:
#   hub=orchestrator, runner=cron runner + notifier, research=strategy,
#   marketing=marketing+content, coach=a coaching persona, assistant=a PA.
# Membership is roster VALIDATION (block typos/spoofed senders), NOT authentication:
# all tenants run as the same OS user, so the unix account is the real trust boundary.
AGENTS = {"hub", "runner", "research", "marketing", "coach", "assistant"}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("PRAGMA journal_mode=WAL")  # concurrent readers + 1 writer; fits N watchers
    return c

def init() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS fleet_bus (
            id TEXT PRIMARY KEY, from_agent TEXT NOT NULL, to_agent TEXT NOT NULL,
            msg_type TEXT NOT NULL, payload TEXT, status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 5, created_at TEXT NOT NULL,
            claimed_at TEXT, done_at TEXT, parent_id TEXT, note TEXT, depends_on TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bus_inbox ON fleet_bus(to_agent, status, priority, created_at)")
        # migration (2026-07-18 task-dependency feature): add depends_on to pre-existing DBs. idempotent.
        try:
            c.execute("ALTER TABLE fleet_bus ADD COLUMN depends_on TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        c.commit()

def _row(c, mid):
    r = c.execute("SELECT * FROM fleet_bus WHERE id=?", (mid,)).fetchone()
    return dict(r) if r else None

def _resume_hint(payload):
    """Pull the requester's optional resume_hint/on_answer from a request payload (JSON dict).
    Lets the asker declare 'when answered, do X' so the dispatcher can resume it precisely."""
    try:
        d = json.loads(payload) if isinstance(payload, str) else payload
        if isinstance(d, dict):
            return d.get("resume_hint") or d.get("on_answer")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- pattern from an audited agent bus
# PATTERN 2: BAN BARE ACKNOWLEDGEMENTS.
# An audited agent bus hit infinite agent-to-agent ack loops and fixed it by replacing "always reply"
# with "publish only if the turn produced something worth knowing", explicitly banning "Got it" /
# "Confirmed". A bare ack carries zero state change and invites a reply, which is the loop.
_BARE_ACK = {
    "ok", "okay", "k", "got it", "gotit", "confirmed", "ack", "acked", "ack.", "noted",
    "understood", "roger", "will do", "willdo", "done", "done.", "thanks", "ty", "sure",
    "yes", "no", "yep", "nope", "+1", "👍", "received", "copy", "copy that",
}



# Shell-expansion damage detector. Found in testing, reproduced not guessed.
# `echo "$9.4M"` prints ".4M": bash expands $9 as positional parameter nine, which is empty. Any
# agent publishing a dollar figure inside a DOUBLE-quoted shell string silently loses the $N.
# The loss happens strictly UPSTREAM of publish(), which is a parameterized INSERT and transforms
# nothing, so the only defense available here is to notice the residue and refuse.
# Refuse rather than warn: a mangled number entering the bus and getting quoted downstream is a
# worse outcome than a blocked send — the corruption once landed inside the very message arguing
# that numbers in bus payloads must not be trusted.
_ORPHANED_MAGNITUDE = re.compile(r"(?:^|\s)\.\d+\s*(?:M|B|bn|tn|k)\b", re.I)


def _shell_mangled(payload) -> str | None:
    body = (" ".join(str(v) for v in payload.values()) if isinstance(payload, dict)
            else str(payload or ""))
    m = _ORPHANED_MAGNITUDE.search(body)
    return m.group(0).strip() if m else None


# Placeholder-shaped payloads: text that DESCRIBES a message instead of being one. Found in testing
# when an agent refused a test payload "substantive finding with real state change in it", which
# passed the ack filter on length and vocabulary while carrying no referent at all. The ack ban
# screens known strings; this screens self-reference. Neither is a semantic check, and the receiver
# refusing to invent content for an empty message remains the real backstop.
_PLACEHOLDER = (
    "substantive finding", "real state change", "test message", "placeholder",
    "lorem ipsum", "example payload", "some finding", "a finding", "insert ",
    "todo", "tbd", "xxx", "asdf",
)


def _is_placeholder(payload) -> bool:
    body = (" ".join(str(v) for v in payload.values()) if isinstance(payload, dict)
            else str(payload or "")).lower()
    return any(m in body for m in _PLACEHOLDER)


def _is_bare_ack(payload) -> bool:
    """True when the payload carries no state change worth publishing."""
    if isinstance(payload, dict):
        body = " ".join(str(v) for v in payload.values())
    else:
        body = str(payload or "")
    stripped = body.strip().strip(".!").lower()
    return stripped in _BARE_ACK or len(stripped) < 3


# PATTERN 3: REPLY-BUDGET CIRCUIT BREAKER.
# buzz PROPOSED this and never built it. A pair of agents can ping-pong indefinitely without any
# state changing; each message is individually reasonable and the exchange is pathological.
# Hard-stop a directed pair after N messages in a window with no completed task between them.
REPLY_BUDGET = 6          # messages per ordered pair
REPLY_WINDOW_HRS = 2


def _reply_budget_exceeded(c, frm, to) -> int | None:
    """Return the count if this ordered pair has burned its budget with nothing completed."""
    row = c.execute(
        "SELECT COUNT(*) FROM fleet_bus WHERE from_agent=? AND to_agent=?"
        " AND created_at > datetime('now', ?)", (frm, to, f"-{REPLY_WINDOW_HRS} hours")).fetchone()
    n = row[0] if row else 0
    if n < REPLY_BUDGET:
        return None
    done = c.execute(
        "SELECT COUNT(*) FROM fleet_bus WHERE from_agent=? AND to_agent=? AND status='done'"
        " AND created_at > datetime('now', ?)", (frm, to, f"-{REPLY_WINDOW_HRS} hours")).fetchone()
    return None if (done and done[0]) else n


def publish(frm, to, mtype, payload, priority=5, parent=None, note=None, depends_on=None) -> dict:
    if to not in AGENTS and to != "*":
        print(json.dumps({"error": f"unknown to_agent '{to}' (roster: {sorted(AGENTS)} or '*')"})); sys.exit(2)
    # validate sender too (security review 2026-06-17, MEDIUM): an unvalidated --from let any caller
    # spoof sender identity. roster-constrain it (frm='*' is meaningless for a sender). NOTE: this is
    # roster validation, not authentication — all tenants run as the same OS user, so the real trust
    # boundary is the unix account; this just blocks garbage/typo'd/wildcard senders.
    if frm not in AGENTS:
        print(json.dumps({"error": f"unknown from_agent '{frm}' (roster: {sorted(AGENTS)})"})); sys.exit(2)
    # task dependencies (2026-07-18): a task can list task-ids it DEPENDS ON; it stays BLOCKED (hidden
    # from poll) until every dep is status='done'. deps can only point at ALREADY-existing ids, so the
    # graph is append-only + acyclic by construction (nothing depends on a not-yet-created id).
    dep_ids = [d.strip() for d in (depends_on.split(",") if isinstance(depends_on, str) else (depends_on or []))
               if d.strip()] if depends_on else []
    _mangled = _shell_mangled(payload)
    if _mangled:
        print(json.dumps({
            "refused": "shell-expansion-damage",
            "found": _mangled,
            "reason": "payload contains an orphaned magnitude (e.g. '.4M'), which is what a dollar "
                      "figure looks like after bash ate the $N. `echo \"$9.4M\"` prints '.4M'. "
                      "Re-send using SINGLE quotes around the payload.",
            "from": frm, "to": to})); sys.exit(2)
    if _is_placeholder(payload):
        print(json.dumps({
            "refused": "placeholder-payload",
            "reason": "payload describes a message rather than being one. name the finding and the "
                      "state that changed (inventing content for an empty message is a recurring "
                      "defect).",
            "from": frm, "to": to})); sys.exit(2)
    if _is_bare_ack(payload):
        print(json.dumps({
            "refused": "bare-acknowledgement",
            "reason": "payload carries no state change. publish only if the turn produced something "
                      "worth knowing. bare acks are what create agent-to-agent reply loops.",
            "from": frm, "to": to})); sys.exit(2)
    mid = uuid.uuid4().hex[:12]
    with _conn() as c:
        _burned = _reply_budget_exceeded(c, frm, to)
        if _burned is not None:
            print(json.dumps({
                "refused": "reply-budget-exceeded",
                "reason": f"{_burned} messages {frm}->{to} in {REPLY_WINDOW_HRS}h with nothing "
                          f"completed between them. this is a loop, not progress. escalate to the operator.",
                "budget": REPLY_BUDGET, "window_hrs": REPLY_WINDOW_HRS})); sys.exit(3)
        if dep_ids:
            missing = [d for d in dep_ids if not _row(c, d)]
            if missing:
                print(json.dumps({"error": f"depends_on references unknown task id(s): {missing}"})); sys.exit(2)
        c.execute("INSERT INTO fleet_bus (id,from_agent,to_agent,msg_type,payload,status,priority,created_at,parent_id,note,depends_on)"
                  " VALUES (?,?,?,?,?,'pending',?,?,?,?,?)",
                  (mid, frm, to, mtype, json.dumps(payload) if not isinstance(payload, str) else payload,
                   priority, _now(), parent, note, (",".join(dep_ids) or None)))
        c.commit()
        return _row(c, mid)

def _deps_met(c, row) -> bool:
    """A task is READY iff every id in its depends_on is status='done'. Empty/None deps = ready.
    A missing or never-done dep keeps it blocked forever (surfaced by `blocked`)."""
    dep = (row.get("depends_on") if isinstance(row, dict) else row["depends_on"]) if row else None
    if not dep:
        return True
    for d in [x for x in dep.split(",") if x]:
        r = c.execute("SELECT status FROM fleet_bus WHERE id=?", (d,)).fetchone()
        if not r or r["status"] != "done":
            return False
    return True

def poll(agent, include_blocked=False) -> list:
    """Pending msgs addressed to `agent`. By default only READY ones (dependencies satisfied);
    a task with unmet deps is BLOCKED and hidden until they complete. --include-blocked shows all."""
    with _conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM fleet_bus WHERE (to_agent=? OR to_agent='*') AND status='pending'"
            " ORDER BY priority DESC, created_at ASC", (agent,)).fetchall()]
        if include_blocked:
            return rows
        return [r for r in rows if _deps_met(c, r)]

def claim(mid) -> dict | None:
    # atomic: the WHERE status='pending' guard makes the UPDATE the claim. rowcount==1 => we won.
    with _conn() as c:
        cur = c.execute("UPDATE fleet_bus SET status='claimed', claimed_at=? WHERE id=? AND status='pending'", (_now(), mid))
        c.commit()
        return _row(c, mid) if cur.rowcount == 1 else None


def _route_back_safe(to_agent, from_agent, mtype, payload, priority, parent):
    """Auto-route a result back to the asker WITHOUT letting a content-guard abort the caller.

    The completion/failure is the PRIMARY operation and has already committed. This courtesy
    route-back is secondary: if publish() rejects the auto-generated payload on a guard
    (bare-ack / placeholder / shell-damage / reply-budget) it calls sys.exit, which would kill the
    CLI after the DB write and report failure on a success. Swallow that here and log it instead.
    """
    try:
        publish(to_agent, from_agent, mtype, payload, priority=priority, parent=parent)
    except SystemExit:
        print(json.dumps({"route_back": "suppressed",
                          "reason": "auto-result tripped a publish guard; completion already "
                                    "committed, courtesy route-back skipped", "to": to_agent}),
              file=sys.stderr)
    except Exception as e:
        print(json.dumps({"route_back": "error", "detail": str(e)[:80]}), file=sys.stderr)


def complete(mid, result=None) -> dict:
    with _conn() as c:
        c.execute("UPDATE fleet_bus SET status='done', done_at=?, note=? WHERE id=?",
                  (_now(), (result if isinstance(result, str) else json.dumps(result)) if result is not None else None, mid))
        c.commit()
        orig = _row(c, mid)
    # auto-thread a result msg back to the original sender so the asker gets the answer AND can
    # resume the work that prompted it. 2026-06-24: was task/question-only, which SILENTLY DROPPED
    # answers to custom request types (e.g. 'crosscheck_request' -> the asker never got the reply,
    # it just sat in this row's note). Now routes back for ANY type EXCEPT 'result' itself. That one
    # exclusion is the whole loop-guard: completing a 'result' never spawns another result, so no
    # result-of-result recursion. carry the requester's resume_hint + the original req_type through
    # so the dispatcher can tell the asker exactly what to continue. skip broadcasts (to='*' has no
    # single asker + would trip publish's from-roster guard).
    if orig and orig["msg_type"] != "result" and orig["to_agent"] in AGENTS:
        rp = {"result": result, "for_task": mid, "req_type": orig["msg_type"]}
        hint = _resume_hint(orig["payload"])
        if hint:
            rp["resume_hint"] = hint
        _route_back_safe(orig["to_agent"], orig["from_agent"], "result", rp, orig["priority"], mid)
    return orig

def fail(mid, err) -> dict:
    with _conn() as c:
        c.execute("UPDATE fleet_bus SET status='failed', done_at=?, note=? WHERE id=?", (_now(), str(err), mid))
        c.commit()
        orig = _row(c, mid)
    # mirror complete()'s broadened route-back: any non-'result' type gets its failure routed back
    # (so a failed crosscheck_request etc. surfaces to the asker instead of dying silently).
    if orig and orig["msg_type"] != "result" and orig["to_agent"] in AGENTS:
        rp = {"error": str(err), "for_task": mid, "req_type": orig["msg_type"]}
        hint = _resume_hint(orig["payload"])
        if hint:
            rp["resume_hint"] = hint
        _route_back_safe(orig["to_agent"], orig["from_agent"], "result", rp, orig["priority"], mid)
    return orig

def stale(pending_hrs=12, claimed_hrs=6) -> dict:
    """Delivery-verification gate (CADVP-inspired, P2 lift from arXiv:2606.04896).

    The bus confirms a WRITE (publish reads the row back) but never confirms
    DELIVERY or PROCESSING. Two silent failure modes it could not see before:
      - 'pending' older than pending_hrs  -> nobody is polling that to_agent
        (dead watcher / wrong roster / typo'd recipient). The msg sits forever,
        no error. This is our analogue of the paper's Channel-C cron-delegated
        delivery failure.
      - 'claimed' older than claimed_hrs  -> a worker atomically claimed it then
        died before complete()/fail(). The asker never gets a result, no error.

    Read-only. SURFACE, do not auto-reset (auto-reclaim risks double-processing;
    ceiling-accept + observer-effect: detect, let a human/watchdog decide)."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    pend_cut = (now - timedelta(hours=pending_hrs)).isoformat()
    clm_cut = (now - timedelta(hours=claimed_hrs)).isoformat()
    with _conn() as c:
        pend = [dict(r) for r in c.execute(
            "SELECT * FROM fleet_bus WHERE status='pending' AND created_at < ?"
            " ORDER BY created_at ASC", (pend_cut,)).fetchall()]
        clm = [dict(r) for r in c.execute(
            "SELECT * FROM fleet_bus WHERE status='claimed' AND claimed_at < ?"
            " ORDER BY claimed_at ASC", (clm_cut,)).fetchall()]
    return {"now": now.isoformat(),
            "thresholds": {"pending_hrs": pending_hrs, "claimed_hrs": claimed_hrs},
            "counts": {"pending_stuck": len(pend), "claimed_stuck": len(clm)},
            "pending_stuck": pend, "claimed_stuck": clm}


def listmsgs(agent=None, status=None, limit=20) -> list:
    q, p = "SELECT * FROM fleet_bus WHERE 1=1", []
    if agent: q += " AND (to_agent=? OR from_agent=?)"; p += [agent, agent]
    if status: q += " AND status=?"; p.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"; p.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, p).fetchall()]

# ---- task-dependency views (2026-07-18) ----

def deps(mid) -> dict:
    """A task's dependencies + each dep's status + whether the task is READY."""
    with _conn() as c:
        row = _row(c, mid)
        if not row:
            return {"error": f"no task {mid}"}
        dep_ids = [x for x in (row.get("depends_on") or "").split(",") if x]
        depstat = []
        for d in dep_ids:
            r = c.execute("SELECT id,msg_type,status,to_agent FROM fleet_bus WHERE id=?", (d,)).fetchone()
            depstat.append(dict(r) if r else {"id": d, "status": "MISSING"})
        ready = _deps_met(c, row)
    return {"id": mid, "status": row["status"], "depends_on": dep_ids, "deps": depstat,
            "ready": ready, "blocked_by": [d["id"] for d in depstat if d.get("status") != "done"]}

def blocked(agent=None) -> list:
    """Pending tasks whose deps are NOT all done = the bottleneck view (what is blocking what)."""
    with _conn() as c:
        q = "SELECT * FROM fleet_bus WHERE status='pending' AND depends_on IS NOT NULL AND depends_on != ''"
        p = []
        if agent:
            q += " AND (to_agent=? OR to_agent='*')"; p = [agent]
        rows = [dict(r) for r in c.execute(q, p).fetchall()]
        out = []
        for r in rows:
            if not _deps_met(c, r):
                blk = []
                for d in [x for x in (r["depends_on"] or "").split(",") if x]:
                    dr = c.execute("SELECT status FROM fleet_bus WHERE id=?", (d,)).fetchone()
                    if not dr or dr["status"] != "done":
                        blk.append({"id": d, "status": dr["status"] if dr else "MISSING"})
                out.append({"id": r["id"], "to_agent": r["to_agent"], "msg_type": r["msg_type"], "blocked_by": blk})
    return out

def critical_path() -> dict:
    """Longest dependency CHAIN by depth among not-done tasks (the critical path in its simplest,
    duration-free form). The DAG is acyclic by construction; the `seen` guard is belt-and-suspenders."""
    with _conn() as c:
        rows = {r["id"]: dict(r) for r in c.execute("SELECT id, depends_on, status FROM fleet_bus").fetchall()}
    memo = {}
    def depth(tid, seen):
        if tid in memo:
            return memo[tid]
        row = rows.get(tid)
        if not row or tid in seen:
            return (0, [])
        best = (0, [])
        for d in [x for x in (row.get("depends_on") or "").split(",") if x]:
            sub = depth(d, seen | {tid})
            if sub[0] > best[0]:
                best = sub
        res = (best[0] + 1, best[1] + [tid])
        memo[tid] = res
        return res
    longest = (0, [])
    for tid, row in rows.items():
        if row["status"] != "done":  # critical path of what is still to do
            d = depth(tid, set())
            if d[0] > longest[0]:
                longest = d
    return {"length": longest[0], "chain": longest[1]}

def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    pp = sub.add_parser("publish"); pp.add_argument("--from", dest="frm", required=True); pp.add_argument("--to", required=True)
    pp.add_argument("--type", dest="mtype", default="task"); pp.add_argument("--payload", default="{}")
    pp.add_argument("--priority", type=int, default=5); pp.add_argument("--parent"); pp.add_argument("--note")
    pp.add_argument("--depends-on", dest="depends_on", help="comma-separated task ids this task waits on (stays blocked until all are done)")
    po = sub.add_parser("poll"); po.add_argument("--agent", required=True)
    po.add_argument("--include-blocked", dest="include_blocked", action="store_true", help="also return tasks with unmet dependencies")
    cl = sub.add_parser("claim"); cl.add_argument("--id", required=True)
    co = sub.add_parser("complete"); co.add_argument("--id", required=True); co.add_argument("--result", default=None)
    fa = sub.add_parser("fail"); fa.add_argument("--id", required=True); fa.add_argument("--err", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--agent"); ls.add_argument("--status"); ls.add_argument("--limit", type=int, default=20)
    st = sub.add_parser("stale"); st.add_argument("--pending-hrs", type=int, default=12); st.add_argument("--claimed-hrs", type=int, default=6)
    dp = sub.add_parser("deps"); dp.add_argument("--id", required=True)
    bl = sub.add_parser("blocked"); bl.add_argument("--agent")
    sub.add_parser("critical-path")
    a = ap.parse_args()
    init()  # idempotent, safe to run every call
    if a.cmd == "init": print(json.dumps({"ok": True, "db": str(DB)}))
    elif a.cmd == "publish": print(json.dumps(publish(a.frm, a.to, a.mtype, a.payload, a.priority, a.parent, a.note, a.depends_on)))
    elif a.cmd == "poll": print(json.dumps(poll(a.agent, a.include_blocked)))
    elif a.cmd == "claim": print(json.dumps(claim(a.id) or {}))
    elif a.cmd == "complete": print(json.dumps(complete(a.id, a.result)))
    elif a.cmd == "fail": print(json.dumps(fail(a.id, a.err)))
    elif a.cmd == "list": print(json.dumps(listmsgs(a.agent, a.status, a.limit), indent=1))
    elif a.cmd == "stale": print(json.dumps(stale(a.pending_hrs, a.claimed_hrs), indent=1))
    elif a.cmd == "deps": print(json.dumps(deps(a.id), indent=1))
    elif a.cmd == "blocked": print(json.dumps(blocked(a.agent), indent=1))
    elif a.cmd == "critical-path": print(json.dumps(critical_path(), indent=1))
    return 0

if __name__ == "__main__":
    sys.exit(main())
