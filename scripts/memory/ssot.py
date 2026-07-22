#!/usr/bin/env python3
# ssot.py — the single source of truth for OPERATIONAL state: one store, one reducer, one change log.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""SSOT: the single source of truth for OPERATIONAL state.

WHY. Operational state tends to scatter: dozens of small files under memory/state/, written
by dozens of different scripts, with no canonical registry and no unified change log. So "which
value is current" and "who last changed it" have no single answer, which is a drift class that
costs a running system repeatedly (a stale pidfile, a miscounted metric, a duplicated process id).
This store fixes exactly two failures: state was NOT one typed tree, and state changes did NOT go
through one reducer.

SCOPE, deliberately narrow. This owns FAST-CHANGING OPERATIONAL state only: active persona/project,
goals, budgets, mode flags, usage counters, watchdog states. It does NOT own, and must never
absorb:
  - the knowledge corpus (prose .md files)   -> belongs in files, git-tracked
  - embeddings (a vector store)              -> a vector store, not operational state
  - inter-agent messages (a queue)           -> a queue, not state
  - cron definitions (the scheduler's store) -> the daemon owns those
Forcing those into one tree would be cargo-culting a UI reducer onto a distributed system. They are
legitimately separate stores.

THE DESIGN, mapping the principles onto a multi-process reality:
  - "one store"    -> one sqlite file (concurrent-safe; a single JSON would race across many
                      writers + cron + interactive sessions).
  - "one reducer"  -> set() is the ONLY mutator. There is no other write path.
  - "every change written down" -> every set() appends to state_log with old, new, and who.
  - "typed nouns"  -> namespaced dotted keys (persona.active, budget.config, usage.maps).

    ssot.py get <key> [--default X]
    ssot.py set <key> <json-or-string> --by <agent> [--reason "..."]
    ssot.py dump [--prefix persona.]
    ssot.py log [--key <key>] [--limit N]
    ssot.py import-scattered [--apply]    # one-time mirror-in from legacy files
    ssot.py self-test                     # negative controls
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(os.environ.get("AGENT_ROOT", str(pathlib.Path(__file__).resolve().parents[2])))
DB = ROOT / "memory/state/ssot.sqlite"

# Local-time offset for the change log (hours from UTC). Set LOCAL_UTC_OFFSET_HOURS to taste.
_TZ_OFFSET_HOURS = int(os.environ.get("LOCAL_UTC_OFFSET_HOURS", "0"))

# A write must name its author. An anonymous mutation is the drift this store exists to end, so
# `--by` is required on the CLI and defaults are only for internal migration.
VALID_KEY = __import__("re").compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB), timeout=10)
    c.execute("PRAGMA journal_mode=WAL")   # concurrent readers during a write, no corruption
    c.execute("""CREATE TABLE IF NOT EXISTS state(
        key TEXT PRIMARY KEY, value TEXT NOT NULL,
        updated_at TEXT NOT NULL, updated_by TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS state_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, key TEXT NOT NULL,
        old TEXT, new TEXT NOT NULL, by TEXT NOT NULL, reason TEXT)""")
    return c


def _now() -> str:
    # Explicit local time so the log reads in operator time regardless of the host clock.
    import datetime
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=_TZ_OFFSET_HOURS))
    ).isoformat(timespec="seconds")


# During migration, a write through the SSOT also mirrors to the legacy file, so not-yet-migrated
# readers keep working. Retire a mirror entry only once grep proves no reader touches that file.
# This is a small illustrative map; extend it with your own operational keys.
_LEGACY_MIRROR = {
    "persona.active": ("memory/state/active_persona.txt", "text"),
    "project.active": ("memory/state/active_project.txt", "text"),
    "mode.driving": ("memory/state/driving_mode.txt", "text"),
    "budget.config": ("memory/state/budget-config.json", "json"),
    "usage.maps": ("memory/state/maps-usage.json", "json"),
}


def _mirror_legacy(key: str, value) -> None:
    ent = _LEGACY_MIRROR.get(key)
    if not ent:
        return
    rel, kind = ent
    f = ROOT / rel
    body = (value if kind == "text" and isinstance(value, str)
            else json.dumps(value, indent=2) if kind == "json" else str(value))
    try:
        # ATOMIC write (tempfile + os.replace), so a migrated writer that previously used atomic
        # writes (e.g. a usage counter) keeps its crash-safety through the mirror. A plain
        # write_text would silently downgrade that guarantee.
        import os as _os, tempfile
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(mode="w", dir=str(f.parent), delete=False,
                                          suffix=".tmp", encoding="utf-8")
        tmp.write(body); tmp.flush(); _os.fsync(tmp.fileno()); tmp.close()
        _os.replace(tmp.name, f)
    except Exception as e:
        print(f"ssot: legacy mirror for {key} failed: {str(e)[:60]}", file=sys.stderr)


def get(key: str, default=None):
    with _conn() as c:
        r = c.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    if r is None:
        return default
    try:
        return json.loads(r[0])
    except Exception:
        return r[0]


def set_(key: str, value, by: str, reason: str | None = None) -> dict:
    """The ONLY mutator. Every call logs old->new with an author. This is the reducer and the
    write-down log in one place."""
    if not by:
        raise ValueError("every state change must name its author (--by)")
    if not VALID_KEY.match(key):
        raise ValueError(f"key {key!r} must be dotted-namespaced lowercase, e.g. persona.active")
    payload = value if isinstance(value, str) else json.dumps(value)
    with _conn() as c:
        old = c.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        old_v = old[0] if old else None
        if old_v == payload:
            return {"key": key, "changed": False, "value": value}   # no-op, no log spam
        c.execute("INSERT INTO state(key,value,updated_at,updated_by) VALUES(?,?,?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                  "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                  (key, payload, _now(), by))
        c.execute("INSERT INTO state_log(ts,key,old,new,by,reason) VALUES(?,?,?,?,?,?)",
                  (_now(), key, old_v, payload, by, reason))
        c.commit()
    _mirror_legacy(key, value)
    return {"key": key, "changed": True, "old": old_v, "new": payload, "by": by}


def dump(prefix: str = "") -> dict:
    with _conn() as c:
        rows = c.execute("SELECT key,value,updated_by,updated_at FROM state "
                         "WHERE key LIKE ? ORDER BY key", (prefix + "%",)).fetchall()
    out = {}
    for k, v, by, at in rows:
        try:
            v = json.loads(v)
        except Exception:
            pass
        out[k] = {"value": v, "by": by, "at": at}
    return out


def log(key: str | None = None, limit: int = 20) -> list:
    with _conn() as c:
        if key:
            rows = c.execute("SELECT ts,key,old,new,by,reason FROM state_log WHERE key=? "
                             "ORDER BY id DESC LIMIT ?", (key, limit)).fetchall()
        else:
            rows = c.execute("SELECT ts,key,old,new,by,reason FROM state_log "
                             "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"ts": r[0], "key": r[1], "old": r[2], "new": r[3], "by": r[4], "reason": r[5]} for r in rows]


# ---- one-time mirror-in from the scattered legacy files (additive; does not delete them) --------

# Only the CORE cross-read operational facts. A full migration is incremental and each legacy
# writer is repointed one at a time, verified, before the next.
_SCATTERED = {
    "persona.active": ("memory/state/active_persona.txt", "text"),
    "project.active": ("memory/state/active_project.txt", "text"),
    "mode.driving": ("memory/state/driving_mode.txt", "text"),
    "budget.config": ("memory/state/budget-config.json", "json"),
    "usage.maps": ("memory/state/maps-usage.json", "json"),
}


def import_scattered(apply: bool) -> dict:
    plan = {}
    for key, (rel, kind) in _SCATTERED.items():
        f = ROOT / rel
        if not f.is_file():
            plan[key] = {"source": rel, "status": "source-missing"}
            continue
        raw = f.read_text(encoding="utf-8").strip()
        val = json.loads(raw) if (kind == "json" and raw) else raw
        plan[key] = {"source": rel, "value_preview": str(val)[:60]}
        if apply:
            r = set_(key, val, by="ssot-migration", reason=f"mirror-in from {rel}")
            plan[key]["applied"] = r["changed"]
    return plan


def self_test() -> int:
    """Negative controls. A store that has not been shown to reject bad writes is not a guarantee."""
    import tempfile
    global DB
    orig = DB
    ok = True
    with tempfile.TemporaryDirectory() as td:
        DB = pathlib.Path(td) / "t.sqlite"
        # 1. anonymous write refused
        try:
            set_("persona.active", "default", by="")
            print("  [FAIL] anonymous write allowed"); ok = False
        except ValueError:
            print("  [PASS] anonymous write refused")
        # 2. bad key shape refused
        try:
            set_("badkey", "x", by="test")
            print("  [FAIL] non-namespaced key allowed"); ok = False
        except ValueError:
            print("  [PASS] non-namespaced key refused")
        # 3. write, read back, and log records old->new
        set_("persona.active", "alt", by="test", reason="unit")
        got = get("persona.active")
        r = get("persona.active") == "alt"
        ok &= r
        print(f"  [{'PASS' if r else 'FAIL'}] round-trip: wrote alt, read {got!r}")
        set_("persona.active", "default", by="test", reason="switch back")
        lg = log("persona.active", 5)
        transition = lg and lg[0]["old"] == "alt" and lg[0]["new"] == "default"
        ok &= bool(transition)
        print(f"  [{'PASS' if transition else 'FAIL'}] log captured alt->default with author")
        # 4. no-op write does not spam the log
        before = len(log(limit=100))
        set_("persona.active", "default", by="test")   # same value
        after = len(log(limit=100))
        noop = after == before
        ok &= noop
        print(f"  [{'PASS' if noop else 'FAIL'}] identical re-write logged nothing ({before}->{after})")
    DB = orig
    print("\nself-test:", "all controls behaved" if ok else "A CONTROL MISBEHAVED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("get"); g.add_argument("key"); g.add_argument("--default")
    s = sub.add_parser("set"); s.add_argument("key"); s.add_argument("value")
    s.add_argument("--by", required=True); s.add_argument("--reason")
    d = sub.add_parser("dump"); d.add_argument("--prefix", default="")
    l = sub.add_parser("log"); l.add_argument("--key"); l.add_argument("--limit", type=int, default=20)
    m = sub.add_parser("import-scattered"); m.add_argument("--apply", action="store_true")
    sub.add_parser("self-test")
    a = ap.parse_args()

    if a.cmd == "get":
        v = get(a.key, a.default)
        print(json.dumps(v) if not isinstance(v, str) else v)
    elif a.cmd == "set":
        try:
            val = json.loads(a.value)
        except Exception:
            val = a.value
        print(json.dumps(set_(a.key, val, by=a.by, reason=a.reason)))
    elif a.cmd == "dump":
        print(json.dumps(dump(a.prefix), indent=2))
    elif a.cmd == "log":
        print(json.dumps(log(a.key, a.limit), indent=2))
    elif a.cmd == "import-scattered":
        print(json.dumps(import_scattered(a.apply), indent=2))
    elif a.cmd == "self-test":
        return self_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
