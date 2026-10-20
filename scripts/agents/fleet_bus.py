#!/usr/bin/env python3
# fleet_bus.py: the multi-agent coordination spine, a tiny typed SQLite message bus.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""fleet_bus: the multi-agent coordination spine.

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

Bus v2 PROVENANCE (CaMeL-style, warn-only). Every row also carries:
  instruction  one of two typed forms: {"template": <registered id>, "args": {<id-shaped values>}}
               or {"operator": "<verbatim>", "ref": "tg:<chat>:<msg>"} (hub only)
  data         opaque named values, never an instruction
  origin       operator:tg:<chat>:<msg> | agent:<name> | external:<kind>:<locator>
  hops         the agents the content passed through
  trust        COMPUTED in publish(), never claimed: min(declared origin level, every row it links
               via parent/cites/depends_on, the sender's taint file). It never rises across a hop.
               Rows without trust (v1) read as 'external' (fail closed).
Rule violations are logged to fleet_bus_warn, not refused, so a week of data can show the
false-refusal rate before anything is enforced. Taint state (which bus rows an agent currently holds
in context) is written per agent to <db dir>/bus_taint/<agent>.json as hashes only; the PreToolUse
hook scripts/security/bus_taint_gate.py reads it.

CLI (for an inbox-watcher + agents to call from shell; all emit JSON):
  fleet_bus.py init
  fleet_bus.py publish --from hub --to runner --type task --payload '{"do":"..."}' [--priority 5] [--parent <id>] [--depends-on <id1,id2>]
                       [--instruction JSON] [--data JSON] [--origin O] [--cites id1,id2] [--resume-template ID]
  fleet_bus.py poll --agent runner [--include-blocked]   # READY pending msgs for runner (deps satisfied); --include-blocked shows all
  fleet_bus.py claim --id <id> [--by runner]       # atomic; prints the claimed row or {} if lost the race
  fleet_bus.py complete --id <id> --result '{...}' [--by runner] [--usage JSON] [--origin O]
                                                   # marks done + auto-publishes a 'result' msg back to from_agent
  fleet_bus.py fail --id <id> --err "..."
  fleet_bus.py list [--agent X] [--status pending] [--limit 20]
  fleet_bus.py deps --id <id>                       # a task's deps + statuses + is-it-ready
  fleet_bus.py blocked [--agent X]                  # pending tasks with unmet deps + what blocks them
  fleet_bus.py critical-path                        # longest dependency chain among not-done tasks
  fleet_bus.py stale | cost [--since ISO] | warns [--days 7] | taint --agent X | taint-clear --agent X [--id ID]

Env: AGENT_ROOT, AGENT_DATA_DIR, FLEET_BUS_DB (point a test harness at a scratch DB),
FLEET_BUS_TAINT_DIR, FLEET_BUS_TEMPLATES (template registry JSON), FLEET_HUB_AGENT (default 'hub').
"""
from __future__ import annotations
import argparse, json, os, re, sqlite3, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# bus_taint_gate (shared token hashing) lives in scripts/security/.
for _p in (_HERE, _HERE.parent / "security"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# AGENT_ROOT defaults to the repo root (this file is scripts/agents/fleet_bus.py).
ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
LIVE_DB = DATA_DIR / "fleet_bus.db"
# FLEET_BUS_DB lets a test harness point every call at a scratch DB. Unset = the live bus.
DB = Path(os.environ.get("FLEET_BUS_DB") or LIVE_DB)
# Roster v1. Generic illustrative tenants, rename/extend to taste:
#   hub=orchestrator, runner=cron runner + notifier, research=strategy,
#   marketing=marketing+content, coach=a coaching persona, assistant=a PA.
# Membership is roster VALIDATION (block typos/spoofed senders), NOT authentication:
# all tenants run as the same OS user, so the unix account is the real trust boundary.
AGENTS = {"hub", "runner", "research", "marketing", "coach", "assistant"}
# The only sender allowed to relay an operator instruction (operator trust level).
HUB = os.environ.get("FLEET_HUB_AGENT", "hub")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------- bus v2 provenance
# trust is COMPUTED in publish(), never claimed, and never rises across a hop:
#   trust = min(declared origin level, every row in parent/cites/depends_on, sender's taint file).
# Rows with no trust (v1) read as 'external' (fail closed).
V2_COLS = ("instruction", "data", "origin", "hops", "trust", "cites", "resume_template")
TRUST_LEVELS = {"external": 0, "fleet": 1, "operator": 2}
ORIGIN_KINDS = {"web", "email", "tg_group", "tg_dm_other", "rss", "file", "brain"}
TEMPLATES = Path(os.environ.get("FLEET_BUS_TEMPLATES") or (_HERE / "bus_templates.json"))
TAINT_TTL_HRS = 6
_ID_SHAPE = re.compile(r"^[A-Za-z0-9_.:/@-]{1,200}$")  # typed slot: no whitespace = no free text


def _row_trust(r) -> str:
    t = (r or {}).get("trust")
    return t if t in TRUST_LEVELS else "external"


def _min_trust(*ts) -> str:
    return min((t for t in ts if t in TRUST_LEVELS), key=TRUST_LEVELS.get, default="external")


def _jload(v):
    if v is None or not isinstance(v, str):
        return v
    try:
        return json.loads(v)
    except Exception:
        return v


def _declared_trust(frm, origin, instruction):
    """Trust level the ORIGIN claim earns on its own, plus a warn reason if the claim was cut down.
    operator is reachable only via instruction form 2 from the hub with a matching tg ref."""
    if not origin:
        return "external", None
    o = str(origin)
    if o.startswith("operator:"):
        ins = instruction if isinstance(instruction, dict) else {}
        ref = ins.get("ref")
        if (frm == HUB and isinstance(ins.get("operator"), str) and isinstance(ref, str)
                and re.fullmatch(r"tg:\d+:\d+", ref) and o == f"operator:{ref}"):
            # NOTE: ref is format-checked only; matching it against the hub's operator transcript
            # is a later phase (it needs a transcript index).
            return "operator", None
        return "external", "operator-claim-unverified"
    if o.startswith("agent:"):
        return ("fleet", None) if o[6:] in AGENTS else ("external", "origin-invalid")
    if o.startswith("external:") and o.split(":")[1:2] and o.split(":")[1] in ORIGIN_KINDS:
        return "external", None
    return "external", "origin-invalid"


def _validate_instruction(instruction):
    """None if `instruction` is one of the two allowed forms, else a short reason. The warn-only
    phase logs a bad one; the enforcement phase will refuse it."""
    if instruction is None:
        return "free-text-instruction"
    if not isinstance(instruction, dict):
        return "instruction-not-object"
    if "operator" in instruction:
        return None if (isinstance(instruction.get("operator"), str)
                        and isinstance(instruction.get("ref"), str)) else "operator-form-malformed"
    tid, args = instruction.get("template"), instruction.get("args", {})
    if not isinstance(tid, str) or not isinstance(args, dict):
        return "template-form-malformed"
    try:
        reg = json.loads(TEMPLATES.read_text())
        reg = reg.get("templates", reg) if isinstance(reg, dict) else {}
    except Exception:
        return "template-registry-missing"
    if tid not in reg:
        return "template-unregistered"
    for v in args.values():
        if isinstance(v, (int, float, bool)) or v is None:
            continue
        if not isinstance(v, str) or not _ID_SHAPE.match(v):
            return "template-free-text-slot"
    return None


def _hops_of(r) -> list:
    h = _jload((r or {}).get("hops"))
    return [x for x in h if isinstance(x, str)] if isinstance(h, list) else [r.get("from_agent") or "?"]


def _taint_dir() -> Path:
    return Path(os.environ.get("FLEET_BUS_TAINT_DIR") or (DB.parent / "bus_taint"))


def _taint_load(agent) -> dict:
    try:
        d = json.loads((_taint_dir() / f"{agent}.json").read_text())
        return d if isinstance(d, dict) and isinstance(d.get("entries"), dict) else {"entries": {}}
    except Exception:
        return {"entries": {}}


def _taint_save(agent, d) -> None:
    try:
        td = _taint_dir(); td.mkdir(parents=True, exist_ok=True)
        tmp = td / f".{agent}.{uuid.uuid4().hex[:6]}.tmp"
        tmp.write_text(json.dumps(d))
        os.replace(tmp, td / f"{agent}.json")
    except Exception:
        pass


def _taint_live(d) -> dict:
    from datetime import timedelta
    cut = (datetime.now(timezone.utc) - timedelta(hours=TAINT_TTL_HRS)).isoformat()
    return {k: v for k, v in d.get("entries", {}).items()
            if isinstance(v, dict) and str(v.get("ts", "")) >= cut}


def taint_level(agent):
    """Lowest trust among this agent's live taint entries, or None when untainted."""
    live = [v.get("trust") for v in _taint_live(_taint_load(agent)).values()
            if v.get("trust") != "operator"]
    return _min_trust(*live) if live else None


def taint_add(agent, rows) -> None:
    """Record that `agent` now holds these rows' text in context (taint state). Stores the
    trust, ids and HASHED tokens only; never payload text. Fail-safe: never breaks a bus call."""
    if agent not in AGENTS or not rows:
        return
    try:
        try:
            import bus_taint_gate as _g
            tok = _g.taint_tokens
        except Exception:
            tok = lambda _t: []  # noqa: E731
        d = _taint_load(agent)
        live = _taint_live(d)
        for r in rows:
            if not r or not r.get("id"):
                continue
            text = " ".join(str(r.get(k) or "") for k in ("payload", "data"))
            live[r["id"]] = {"trust": _row_trust(r), "ts": _now(), "tok": tok(text)[:200]}
        _taint_save(agent, {"agent": agent, "entries": live})
    except Exception:
        pass


def taint_clear(agent, ids=None) -> None:
    """Drop taint entries (all of them when ids is None, e.g. on a new operator turn)."""
    if agent not in AGENTS:
        return
    d = _taint_load(agent)
    live = {} if ids is None else {k: v for k, v in _taint_live(d).items() if k not in set(ids)}
    _taint_save(agent, {"agent": agent, "entries": live})


def _warn(c, rule, mid, frm, to, mtype, via, detail="") -> None:
    try:
        c.execute("INSERT INTO fleet_bus_warn (ts,rule,bus_id,from_agent,to_agent,msg_type,via,detail)"
                  " VALUES (?,?,?,?,?,?,?,?)", (_now(), rule, mid, frm, to, mtype, via, str(detail)[:160]))
    except sqlite3.Error:
        pass  # warn table missing (half-migrated) must never break a publish

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
        # token-cost columns: additive; populated on complete --usage.
        for _col in ("tokens_in", "tokens_out", "cache_read"):
            try:
                c.execute(f"ALTER TABLE fleet_bus ADD COLUMN {_col} INTEGER")
            except sqlite3.OperationalError:
                pass  # column already exists (idempotent)
        # migration (task-dependency feature): add depends_on to pre-existing DBs. idempotent.
        try:
            c.execute("ALTER TABLE fleet_bus ADD COLUMN depends_on TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        # identity-pinned claim/complete: record WHO holds a claim so a
        # replacement or a different agent cannot satisfy a completion it does not own. additive +
        # idempotent, same shape as the columns above.
        try:
            c.execute("ALTER TABLE fleet_bus ADD COLUMN claimed_by TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        # bus v2 provenance: additive + nullable + idempotent.
        # A concurrent init() that loses the race gets 'duplicate column' (swallowed); one that times
        # out on the lock gets 'database is locked' (also swallowed, retried on its next call).
        # publish() only writes v2 columns that actually exist, so a half-migrated DB still works.
        for _col in V2_COLS:
            try:
                c.execute(f"ALTER TABLE fleet_bus ADD COLUMN {_col} TEXT")
            except sqlite3.OperationalError:
                pass
        # warn rows for the refusals that are NOT enforced yet (free-text instruction, CLI
        # --type result, bad instruction/origin). Gathers a week of data before anything is refused.
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS fleet_bus_warn (
                ts TEXT NOT NULL, rule TEXT NOT NULL, bus_id TEXT, from_agent TEXT, to_agent TEXT,
                msg_type TEXT, via TEXT, detail TEXT)""")
        except sqlite3.OperationalError:
            pass
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
# worse outcome than a blocked send. The corruption once landed inside the very message arguing
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
    "lorem ipsum", "example payload", "some finding", "a finding",
    "insert your", "insert the finding", "insert finding", "<insert",
    "asdf",
)

# Short tokens must match as WHOLE WORDS. As bare substrings they refuse real engineering traffic:
# 'insert ' refused a message explaining that a bare SQL INSERT would trip a circuit breaker, and
# 'xxx'/'tbd' hit inside ordinary words, hashes and URLs. A guard that blocks legitimate messages
# gets worked around, which costs more than the placeholders it catches. Precision is part of the
# guard's job, not a nicety.
_PLACEHOLDER_WORDS = ("todo", "tbd", "xxx", "fixme")
# Word boundary that also treats '_' as a word char, so 'todo' does not hit the identifier 'todo_list'.
_PLACEHOLDER_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, _PLACEHOLDER_WORDS)) + r")(?![A-Za-z0-9_])", re.I)


def _is_placeholder(payload) -> bool:
    body = (" ".join(str(v) for v in payload.values()) if isinstance(payload, dict)
            else str(payload or "")).lower()
    # Template phrases are matched as substrings (they have spaces / no boundaries); short tokens
    # are matched as whole WORDS, so 'todo' does not hit 'todo_list' and 'xxx' does not hit a hash.
    if any(m in body for m in _PLACEHOLDER):
        return True
    return _PLACEHOLDER_WORD_RE.search(body) is not None


def _is_bare_ack(payload) -> bool:
    """True when the payload carries no state change worth publishing."""
    if isinstance(payload, dict):
        body = " ".join(str(v) for v in payload.values())
    else:
        body = str(payload or "")
    stripped = body.strip().strip(".!").lower()
    return stripped in _BARE_ACK or len(stripped) < 3


# PATTERN 3: REPLY-BUDGET CIRCUIT BREAKER.
# The audited bus PROPOSED this and never built it. A pair of agents can ping-pong indefinitely without any
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


def publish(frm, to, mtype, payload, priority=5, parent=None, note=None, depends_on=None,
            instruction=None, data=None, origin=None, cites=None, resume_template=None,
            via="api") -> dict:
    """v1 callers pass only `payload` and get v1 behavior plus computed v2 provenance.
    v2 callers add instruction/data/origin/cites/resume_template. `via` says who
    built the row (api / cli / complete / fail) so CLI-made results can be warned on."""
    instruction, data = _jload(instruction), _jload(data)
    if payload is None:
        # v1 readers (dispatcher file-drop, pollers, turn hook) only read `payload`, so a v2-only
        # publish gets a synthesized one. The content guards below then screen it as usual.
        payload = ({k: v for k, v in (("instruction", instruction), ("data", data)) if v is not None}
                   or "{}")
    if to not in AGENTS and to != "*":
        print(json.dumps({"error": f"unknown to_agent '{to}' (roster: {sorted(AGENTS)} or '*')"})); sys.exit(2)
    # validate sender too (security review, MEDIUM): an unvalidated --from let any caller
    # spoof sender identity. roster-constrain it (frm='*' is meaningless for a sender). NOTE: this is
    # roster validation, not authentication. All tenants run as the same OS user, so the real trust
    # boundary is the unix account; this just blocks garbage/typo'd/wildcard senders.
    if frm not in AGENTS:
        print(json.dumps({"error": f"unknown from_agent '{frm}' (roster: {sorted(AGENTS)})"})); sys.exit(2)
    # task dependencies: a task can list task-ids it DEPENDS ON; it stays BLOCKED (hidden
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
        # ---- v2 provenance: computed here, never taken from the caller ----
        warns = []
        trust, why = _declared_trust(frm, origin, instruction)
        if why:
            warns.append((why, str(origin)[:80]))
        cite_ids = [x.strip() for x in (cites.split(",") if isinstance(cites, str) else (cites or []))
                    if x and x.strip()]
        linked, hops = [], []
        for lid in ([parent] if parent else []) + cite_ids + dep_ids:
            r = _row(c, lid)
            if r is None:
                trust = "external"  # an unknown cite cannot vouch for anything: fail closed
                warns.append(("cites-unknown", lid[:40]))
                continue
            linked.append(r)
            hops += _hops_of(r)
        trust = _min_trust(trust, *[_row_trust(r) for r in linked])
        tl = taint_level(frm)
        if tl is not None and TRUST_LEVELS[tl] < TRUST_LEVELS[trust]:
            warns.append(("trust-capped-by-taint", f"{trust}->{tl}"))
            trust = tl
        hops = [h for i, h in enumerate(hops) if i == 0 or h != hops[i - 1]]
        if not hops or hops[-1] != frm:
            hops.append(frm)
        # future refusals, WARN-ONLY until a week of data exists
        if via == "cli" and mtype == "result":
            warns.append(("cli-result-type", "result built outside complete()/fail()"))
        if mtype != "result":  # results are data by nature; they carry no instruction
            bad = _validate_instruction(instruction)
            if bad:
                warns.append((bad, ""))  # rule name only: never copy instruction text into the log
        rt = None
        if resume_template is not None:
            if isinstance(resume_template, str) and _ID_SHAPE.match(resume_template):
                rt = resume_template
            else:
                warns.append(("resume-template-invalid", "dropped"))
        v2 = {"instruction": json.dumps(instruction) if instruction is not None else None,
              "data": json.dumps(data) if data is not None else None,
              "origin": str(origin)[:300] if origin else None,
              "hops": json.dumps(hops[-16:]), "trust": trust,
              "cites": ",".join(cite_ids) or None, "resume_template": rt}
        have = {r[1] for r in c.execute("PRAGMA table_info(fleet_bus)").fetchall()}
        v2 = {k: v for k, v in v2.items() if k in have}  # half-migrated DB: write what exists
        cols = ["id", "from_agent", "to_agent", "msg_type", "payload", "status", "priority",
                "created_at", "parent_id", "note", "depends_on"] + list(v2)
        vals = [mid, frm, to, mtype, json.dumps(payload) if not isinstance(payload, str) else payload,
                "pending", priority, _now(), parent, note, (",".join(dep_ids) or None)] + list(v2.values())
        c.execute(f"INSERT INTO fleet_bus ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        for rule, detail in warns:
            _warn(c, rule, mid, frm, to, mtype, via, detail)
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

def claim(mid, by=None) -> dict | None:
    # atomic: the WHERE status='pending' guard makes the UPDATE the claim. rowcount==1 => we won.
    # `by` records WHO holds the claim (identity pin). Optional for
    # back-compat; when supplied it lets complete() refuse a completer that is not the recipient.
    with _conn() as c:
        cur = c.execute("UPDATE fleet_bus SET status='claimed', claimed_at=?, claimed_by=? WHERE id=? AND status='pending'",
                        (_now(), by, mid))
        c.commit()
        r = _row(c, mid) if cur.rowcount == 1 else None
    if r:  # the claimer now holds this row's text: record taint (read by the warn-only gate)
        taint_add(r["to_agent"] if r["to_agent"] in AGENTS else by, [r])
    return r


def _route_back_safe(to_agent, from_agent, mtype, payload, priority, parent, origin=None, via="complete"):
    """Auto-route a result back to the asker WITHOUT letting a content-guard abort the caller.

    The completion/failure is the PRIMARY operation and has already committed. This courtesy
    route-back is secondary: if publish() rejects the auto-generated payload on a guard
    (bare-ack / placeholder / shell-damage / reply-budget) it calls sys.exit, which would kill the
    CLI after the DB write and report failure on a success. Swallow that here and log it instead.
    """
    try:
        publish(to_agent, from_agent, mtype, payload, priority=priority, parent=parent,
                origin=origin, via=via)
    except SystemExit:
        print(json.dumps({"route_back": "suppressed",
                          "reason": "auto-result tripped a publish guard; completion already "
                                    "committed, courtesy route-back skipped", "to": to_agent}),
              file=sys.stderr)
    except Exception as e:
        print(json.dumps({"route_back": "error", "detail": str(e)[:80]}), file=sys.stderr)


def complete(mid, result=None, usage=None, by=None, origin=None) -> dict:
    with _conn() as c:
        # Identity pin: a task may be completed only by its intended
        # recipient (to_agent). Enforced ONLY when `by` is supplied, so legacy callers that omit it
        # keep working unchanged; a caller that passes --by gets the guard. This blocks a respawned
        # duplicate or a DIFFERENT agent from satisfying a completion it does not own. Pins to ROSTER
        # identity (agent name) = our coordination granularity (normally one live pane per name).
        if by is not None:
            _orig = _row(c, mid)
            if _orig is None:
                print(json.dumps({"refused": "no-such-task", "id": mid, "by": by})); sys.exit(2)
            _to = _orig.get("to_agent")
            if _to in AGENTS and by != _to:
                print(json.dumps({"refused": "completer-mismatch", "id": mid, "by": by,
                                  "addressed_to": _to,
                                  "reason": "only the addressed agent may complete this task; a "
                                            "replacement or wrong agent cannot satisfy another's claim"}))
                sys.exit(3)
        c.execute("UPDATE fleet_bus SET status='done', done_at=?, note=? WHERE id=?",
                  (_now(), (result if isinstance(result, str) else json.dumps(result)) if result is not None else None, mid))
        if usage:  # optional per-task token cost {"in":N,"out":N,"cache_read":N}
            try:
                u = json.loads(usage) if isinstance(usage, str) else usage
                c.execute("UPDATE fleet_bus SET tokens_in=?, tokens_out=?, cache_read=? WHERE id=?",
                          (u.get("in") or u.get("tokens_in") or u.get("prompt"),
                           u.get("out") or u.get("tokens_out") or u.get("completion"),
                           u.get("cache_read") or u.get("cache_read_tokens"), mid))
            except Exception:
                pass
        c.commit()
        orig = _row(c, mid)
    # auto-thread a result msg back to the original sender so the asker gets the answer AND can
    # resume the work that prompted it. It used to be task/question-only, which SILENTLY DROPPED
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
        # v2: result trust = min(task trust, completer's declared origin); publish() computes it
        # from parent=mid + origin, and hops = task hops + completer.
        _route_back_safe(orig["to_agent"], orig["from_agent"], "result", rp, orig["priority"], mid,
                         origin=origin, via="complete")
    if orig:
        if orig["msg_type"] == "result":
            # a delivered/acked result puts its text in the asker's context: taint the asker
            taint_add(orig["to_agent"], [orig])
        else:
            taint_clear(orig["to_agent"], [mid])  # the task is finished: its taint entry goes
    return orig

def cost(since=None) -> dict:
    """Per-agent / per-type token-cost rollup over done tasks. Tokens are captured
    on `complete --usage`; tasks completed without --usage show as untracked. `assignee`
    = to_agent (who the task was routed to / who did the work)."""
    with _conn() as c:
        where, params = "status='done'", []
        if since:
            where += " AND done_at >= ?"; params.append(since)
        rows = c.execute(
            f"""SELECT to_agent, msg_type, COUNT(*),
                   COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0), COALESCE(SUM(cache_read),0),
                   SUM(CASE WHEN tokens_in IS NULL AND tokens_out IS NULL THEN 1 ELSE 0 END)
                FROM fleet_bus WHERE {where}
                GROUP BY to_agent, msg_type ORDER BY to_agent, msg_type""", params).fetchall()
    total = {"tasks": 0, "tokens_in": 0, "tokens_out": 0, "cache_read": 0, "untracked": 0}
    by_agent, breakdown = {}, []
    for ta, mt, n, ti, to, cr, unt in rows:
        breakdown.append({"assignee": ta, "type": mt, "tasks": n,
                          "tokens_in": ti, "tokens_out": to, "cache_read": cr, "untracked": unt})
        ag = by_agent.setdefault(ta, {"tasks": 0, "tokens_in": 0, "tokens_out": 0, "cache_read": 0, "untracked": 0})
        for k, v in (("tasks", n), ("tokens_in", ti), ("tokens_out", to), ("cache_read", cr), ("untracked", unt)):
            ag[k] += v; total[k] += v
    return {"since": since, "total": total, "by_agent": by_agent, "breakdown": breakdown}

def fail(mid, err, origin=None) -> dict:
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
        _route_back_safe(orig["to_agent"], orig["from_agent"], "result", rp, orig["priority"], mid,
                         origin=origin, via="fail")
    if orig and orig["msg_type"] != "result":
        taint_clear(orig["to_agent"], [mid])
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


def warns(days=7) -> dict:
    """Enforcement-readiness data: how many publishes WOULD be refused, by rule and sender."""
    from datetime import timedelta
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as c:
        try:
            rows = c.execute("SELECT rule, from_agent, COUNT(*) FROM fleet_bus_warn WHERE ts >= ?"
                             " GROUP BY rule, from_agent ORDER BY 3 DESC", (cut,)).fetchall()
        except sqlite3.Error:
            rows = []
    by_rule = {}
    for rule, frm, n in rows:
        by_rule.setdefault(rule, {})[frm] = n
    return {"days": days, "total": sum(r[2] for r in rows), "by_rule": by_rule}


def listmsgs(agent=None, status=None, limit=20) -> list:
    q, p = "SELECT * FROM fleet_bus WHERE 1=1", []
    if agent: q += " AND (to_agent=? OR from_agent=?)"; p += [agent, agent]
    if status: q += " AND status=?"; p.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"; p.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, p).fetchall()]

# ---- task-dependency views ----

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
    pp.add_argument("--type", dest="mtype", default="task"); pp.add_argument("--payload", default=None, help="v1 free-text JSON payload (default '{}')")
    pp.add_argument("--priority", type=int, default=5); pp.add_argument("--parent"); pp.add_argument("--note")
    pp.add_argument("--depends-on", dest="depends_on", help="comma-separated task ids this task waits on (stays blocked until all are done)")
    # bus v2, all optional. trust is computed, there is deliberately no --trust flag.
    pp.add_argument("--instruction", default=None, help='v2: {"template":"<id>","args":{...}} or {"operator":"<verbatim>","ref":"tg:<chat>:<msg>"}')
    pp.add_argument("--data", default=None, help="v2: JSON object of opaque named values (never an instruction)")
    pp.add_argument("--origin", default=None, help="v2: operator:tg:<chat>:<msg> | agent:<name> | external:<kind>:<locator>; omitted = external")
    pp.add_argument("--cites", default=None, help="v2: comma-separated bus ids whose content this message uses (trust is inherited)")
    pp.add_argument("--resume-template", dest="resume_template", default=None, help="v2: template id the dispatcher resumes with (replaces free-text resume_hint)")
    po = sub.add_parser("poll"); po.add_argument("--agent", required=True)
    po.add_argument("--include-blocked", dest="include_blocked", action="store_true", help="also return tasks with unmet dependencies")
    cl = sub.add_parser("claim"); cl.add_argument("--id", required=True); cl.add_argument("--by", default=None, help="agent claiming this task (identity pin)")
    co = sub.add_parser("complete"); co.add_argument("--id", required=True); co.add_argument("--result", default=None); co.add_argument("--usage", default=None); co.add_argument("--by", default=None, help="completing agent; if set, must equal the task's to_agent or it is refused")
    co.add_argument("--origin", default=None, help="v2: completer's data origin; the result's trust is min(task trust, this)")
    fa = sub.add_parser("fail"); fa.add_argument("--id", required=True); fa.add_argument("--err", required=True)
    fa.add_argument("--origin", default=None)
    tc = sub.add_parser("taint-clear", help="v2: drop an agent's bus taint (e.g. on a new operator turn)")
    tc.add_argument("--agent", required=True); tc.add_argument("--id", default=None)
    tl = sub.add_parser("taint", help="v2: show an agent's current taint level and ids (no payload text)")
    tl.add_argument("--agent", required=True)
    wn = sub.add_parser("warns", help="v2: summarize fleet_bus_warn rows (would-refuse data)")
    wn.add_argument("--days", type=int, default=7)
    ls = sub.add_parser("list"); ls.add_argument("--agent"); ls.add_argument("--status"); ls.add_argument("--limit", type=int, default=20)
    st = sub.add_parser("stale"); st.add_argument("--pending-hrs", type=int, default=12); st.add_argument("--claimed-hrs", type=int, default=6)
    dp = sub.add_parser("deps"); dp.add_argument("--id", required=True)
    bl = sub.add_parser("blocked"); bl.add_argument("--agent")
    sub.add_parser("critical-path")
    cs = sub.add_parser("cost"); cs.add_argument("--since", default=None)
    a = ap.parse_args()
    init()  # idempotent, safe to run every call
    if a.cmd == "init": print(json.dumps({"ok": True, "db": str(DB)}))
    elif a.cmd == "publish": print(json.dumps(publish(a.frm, a.to, a.mtype, a.payload, a.priority, a.parent, a.note, a.depends_on,
                                                      instruction=a.instruction, data=a.data, origin=a.origin, cites=a.cites,
                                                      resume_template=a.resume_template, via="cli")))
    elif a.cmd == "poll":
        rows = poll(a.agent, a.include_blocked)
        taint_add(a.agent, rows)  # CLI poll = the agent is reading these payloads now
        print(json.dumps(rows))
    elif a.cmd == "claim": print(json.dumps(claim(a.id, a.by) or {}))
    elif a.cmd == "complete": print(json.dumps(complete(a.id, a.result, a.usage, a.by, a.origin)))
    elif a.cmd == "fail": print(json.dumps(fail(a.id, a.err, a.origin)))
    elif a.cmd == "taint-clear":
        taint_clear(a.agent, [a.id] if a.id else None); print(json.dumps({"ok": True, "agent": a.agent}))
    elif a.cmd == "taint":
        live = _taint_live(_taint_load(a.agent))
        print(json.dumps({"agent": a.agent, "level": taint_level(a.agent), "ids": sorted(live)}))
    elif a.cmd == "warns": print(json.dumps(warns(a.days), indent=1))
    elif a.cmd == "list": print(json.dumps(listmsgs(a.agent, a.status, a.limit), indent=1))
    elif a.cmd == "stale": print(json.dumps(stale(a.pending_hrs, a.claimed_hrs), indent=1))
    elif a.cmd == "deps": print(json.dumps(deps(a.id), indent=1))
    elif a.cmd == "blocked": print(json.dumps(blocked(a.agent), indent=1))
    elif a.cmd == "critical-path": print(json.dumps(critical_path(), indent=1))
    elif a.cmd == "cost": print(json.dumps(cost(a.since), indent=1))
    return 0

if __name__ == "__main__":
    sys.exit(main())
