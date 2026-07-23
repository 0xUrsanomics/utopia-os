#!/usr/bin/env python3
"""Fleet board: shared-editable-state coordination for a multi-agent fleet.

Adapts the workbench.md coordination model, self-hosted + zero-egress. Where a
message bus is push/inbox (dispatch a message to a worker), the board is DURABLE
SHARED STATE that N agents + a human collaborate on: a card board, a chat lane,
human-asks, and proposed edits, with an append-only event feed so consumers learn
of changes without re-reading everything.

The 5 primitives:
  1. doc-as-surface  : cards + chat + asks live in one board (render -> markdown view).
  2. event feed      : every mutation appends to `events` with a monotonic seq;
                       `events --since S --wait N` long-polls (blocks until seq advances).
  3. optimistic CAS  : card mutations take --base-version; a mismatch returns EXIT 9
                       (409) so a stale write never clobbers a concurrent one.
  4. capability tiers : view < comment < suggest < edit, per actor (default edit;
                       restrict a tenant with `caps set`). A too-low actor is refused.
  5. suggestions     : an actor with `suggest` proposes an edit; an `edit` actor
                       accept/rejects it (a review-gate on shared state).

sqlite at memory/state/fleet_board.db. Single default board "main" (--board to switch).
CLI + importable. No network, no external deps.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
DB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "..", "memory", "state", "fleet_board.db"))
LEVELS = {"view": 0, "comment": 1, "suggest": 2, "edit": 3}
DEFAULT_LEVEL = "edit"   # actors are the principal's own agents by default; restrict a tenant by exception
EXIT_CONFLICT = 9
EXIT_DENIED = 7


def now():
    return datetime.now(WIB).isoformat()


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
      CREATE TABLE IF NOT EXISTS cards(
        id INTEGER PRIMARY KEY, board TEXT, title TEXT, body TEXT,
        status TEXT DEFAULT 'open', claimed_by TEXT, version INTEGER DEFAULT 1, ts TEXT);
      CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY, board TEXT, author TEXT, text TEXT, ts TEXT);
      CREATE TABLE IF NOT EXISTS asks(
        id INTEGER PRIMARY KEY, board TEXT, author TEXT, text TEXT,
        status TEXT DEFAULT 'open', answer TEXT, ts TEXT);
      CREATE TABLE IF NOT EXISTS suggestions(
        id INTEGER PRIMARY KEY, board TEXT, target TEXT, author TEXT,
        proposed TEXT, status TEXT DEFAULT 'pending', ts TEXT);
      CREATE TABLE IF NOT EXISTS events(
        seq INTEGER PRIMARY KEY AUTOINCREMENT, board TEXT, kind TEXT,
        actor TEXT, detail TEXT, ts TEXT);
      CREATE TABLE IF NOT EXISTS caps(actor TEXT PRIMARY KEY, level TEXT);
    """)
    return c


def _level(c, actor):
    r = c.execute("SELECT level FROM caps WHERE actor=?", (actor,)).fetchone()
    return r[0] if r else DEFAULT_LEVEL


def _require(c, actor, need):
    have = _level(c, actor)
    if LEVELS.get(have, 0) < LEVELS[need]:
        print(json.dumps({"error": "capability_denied", "actor": actor,
                          "have": have, "need": need}))
        c.close()
        sys.exit(EXIT_DENIED)


def _emit(c, board, kind, actor, detail):
    c.execute("INSERT INTO events(board,kind,actor,detail,ts) VALUES(?,?,?,?,?)",
              (board, kind, actor, json.dumps(detail), now()))


# ---- cards ----
def cmd_add_card(a):
    c = _conn(); _require(c, a.actor, "suggest")
    cur = c.execute("INSERT INTO cards(board,title,body,status,version,ts) VALUES(?,?,?,'open',1,?)",
                    (a.board, a.title, a.body or "", now()))
    cid = cur.lastrowid
    _emit(c, a.board, "card_added", a.actor, {"card": cid, "title": a.title})
    c.commit(); c.close()
    print(json.dumps({"card": cid, "status": "open", "version": 1}))


def _card_cas(a, new_status=None, claimed_by=None, kind="card_updated"):
    c = _conn(); _require(c, a.actor, "edit")
    row = c.execute("SELECT status, version FROM cards WHERE id=? AND board=?", (a.card, a.board)).fetchone()
    if not row:
        print(json.dumps({"error": "no_such_card", "card": a.card})); c.close(); sys.exit(1)
    status, version = row
    if a.base_version is not None and int(a.base_version) != version:
        print(json.dumps({"error": "version_conflict", "card": a.card,
                          "your_base": a.base_version, "current": version, "hint": "re-read + retry"}))
        c.close(); sys.exit(EXIT_CONFLICT)
    sets, vals = ["version=version+1"], []
    if new_status is not None: sets.append("status=?"); vals.append(new_status)
    if claimed_by is not None: sets.append("claimed_by=?"); vals.append(claimed_by)
    vals += [a.card, a.board]
    c.execute(f"UPDATE cards SET {','.join(sets)} WHERE id=? AND board=?", vals)
    nv = c.execute("SELECT status, version, claimed_by FROM cards WHERE id=?", (a.card,)).fetchone()
    _emit(c, a.board, kind, a.actor, {"card": a.card, "status": nv[0]})
    c.commit(); c.close()
    print(json.dumps({"card": a.card, "status": nv[0], "version": nv[1], "claimed_by": nv[2]}))


def cmd_claim_card(a):
    _card_cas(a, new_status="claimed", claimed_by=a.actor, kind="card_claimed")


def cmd_done_card(a):
    _card_cas(a, new_status="done", kind="card_done")


# ---- chat / asks ----
def cmd_chat(a):
    c = _conn(); _require(c, a.actor, "comment")
    c.execute("INSERT INTO messages(board,author,text,ts) VALUES(?,?,?,?)", (a.board, a.actor, a.text, now()))
    _emit(c, a.board, "chat", a.actor, {"text": a.text[:120]})
    c.commit(); c.close(); print(json.dumps({"ok": True}))


def cmd_ask(a):
    c = _conn(); _require(c, a.actor, "comment")
    cur = c.execute("INSERT INTO asks(board,author,text,status,ts) VALUES(?,?,?,'open',?)",
                    (a.board, a.actor, a.text, now()))
    _emit(c, a.board, "ask", a.actor, {"ask": cur.lastrowid, "text": a.text[:120]})
    c.commit(); c.close(); print(json.dumps({"ask": cur.lastrowid, "status": "open"}))


def cmd_answer_ask(a):
    c = _conn(); _require(c, a.actor, "edit")
    c.execute("UPDATE asks SET status='answered', answer=? WHERE id=? AND board=?", (a.text, a.ask, a.board))
    _emit(c, a.board, "ask_answered", a.actor, {"ask": a.ask})
    c.commit(); c.close(); print(json.dumps({"ask": a.ask, "status": "answered"}))


# ---- suggestions (review-gate on shared state) ----
def cmd_suggest(a):
    c = _conn(); _require(c, a.actor, "suggest")
    cur = c.execute("INSERT INTO suggestions(board,target,author,proposed,status,ts) VALUES(?,?,?,?,'pending',?)",
                    (a.board, a.target, a.actor, a.proposed, now()))
    _emit(c, a.board, "suggestion", a.actor, {"suggestion": cur.lastrowid, "target": a.target})
    c.commit(); c.close(); print(json.dumps({"suggestion": cur.lastrowid, "status": "pending"}))


def cmd_resolve_suggestion(a, accept):
    c = _conn(); _require(c, a.actor, "edit")
    row = c.execute("SELECT target, proposed, status FROM suggestions WHERE id=? AND board=?",
                    (a.id, a.board)).fetchone()
    if not row or row[2] != "pending":
        print(json.dumps({"error": "no_pending_suggestion", "id": a.id})); c.close(); sys.exit(1)
    target, proposed, _ = row
    applied = None
    if accept:
        # apply proposed to the target if it is a card body/title (target = "card:ID:field")
        parts = target.split(":")
        if len(parts) == 3 and parts[0] == "card" and parts[2] in ("title", "body"):
            c.execute(f"UPDATE cards SET {parts[2]}=?, version=version+1 WHERE id=? AND board=?",
                      (proposed, int(parts[1]), a.board))
            applied = target
        c.execute("UPDATE suggestions SET status='accepted' WHERE id=?", (a.id,))
    else:
        c.execute("UPDATE suggestions SET status='rejected' WHERE id=?", (a.id,))
    _emit(c, a.board, "suggestion_accepted" if accept else "suggestion_rejected", a.actor,
          {"suggestion": a.id, "applied": applied})
    c.commit(); c.close()
    print(json.dumps({"suggestion": a.id, "status": "accepted" if accept else "rejected", "applied": applied}))


# ---- event feed (long-poll) ----
def cmd_events(a):
    deadline = time.time() + (a.wait or 0)
    while True:
        c = _conn()
        rows = c.execute("SELECT seq,kind,actor,detail,ts FROM events WHERE board=? AND seq>? ORDER BY seq",
                         (a.board, a.since)).fetchall()
        c.close()
        if rows or not a.wait or time.time() >= deadline:
            out = [{"seq": r[0], "kind": r[1], "actor": r[2], "detail": json.loads(r[3]), "ts": r[4]} for r in rows]
            print(json.dumps({"events": out, "last_seq": (out[-1]["seq"] if out else a.since)}))
            return
        time.sleep(0.3)


# ---- capabilities ----
def cmd_caps(a):
    c = _conn()
    if a.set_actor:
        if a.level not in LEVELS:
            print(json.dumps({"error": "bad_level", "levels": list(LEVELS)})); c.close(); sys.exit(1)
        c.execute("INSERT INTO caps(actor,level) VALUES(?,?) ON CONFLICT(actor) DO UPDATE SET level=excluded.level",
                  (a.set_actor, a.level))
        c.commit(); print(json.dumps({"actor": a.set_actor, "level": a.level}))
    else:
        rows = c.execute("SELECT actor,level FROM caps ORDER BY actor").fetchall()
        print(json.dumps({"default": DEFAULT_LEVEL, "overrides": {r[0]: r[1] for r in rows}}))
    c.close()


# ---- render (the markdown "doc" view) ----
def cmd_render(a):
    c = _conn()
    L = [f"# Fleet Board: {a.board}", ""]
    L.append("## Cards")
    for st in ("open", "claimed", "done"):
        cards = c.execute("SELECT id,title,claimed_by,version FROM cards WHERE board=? AND status=? ORDER BY id",
                          (a.board, st)).fetchall()
        if cards:
            L.append(f"### {st}")
            for cid, t, by, v in cards:
                who = f" (@{by})" if by else ""
                L.append(f"- [{cid} v{v}] {t}{who}")
    asks = c.execute("SELECT id,author,text,status,answer FROM asks WHERE board=? ORDER BY id", (a.board,)).fetchall()
    if asks:
        L += ["", "## Asks (human-flags)"]
        for i, au, tx, st, ans in asks:
            L.append(f"- [{i}] @{au}: {tx}  ({st}{': ' + ans if ans else ''})")
    sug = c.execute("SELECT id,target,author,proposed,status FROM suggestions WHERE board=? AND status='pending' ORDER BY id",
                    (a.board,)).fetchall()
    if sug:
        L += ["", "## Pending suggestions"]
        for i, tg, au, pr, st in sug:
            L.append(f"- [{i}] @{au} -> {tg}: {pr[:80]}")
    msgs = c.execute("SELECT author,text,ts FROM messages WHERE board=? ORDER BY id DESC LIMIT 10", (a.board,)).fetchall()
    if msgs:
        L += ["", "## Chat (latest 10)"]
        for au, tx, ts in reversed(msgs):
            L.append(f"- {ts[11:16]} @{au}: {tx}")
    c.close()
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="main")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, args):
        p = sub.add_parser(name)
        for an, kw in args:
            p.add_argument(an, **kw)
        p.set_defaults(fn=fn)
        return p

    add("add-card", cmd_add_card, [("--actor", {"required": True}), ("--title", {"required": True}), ("--body", {})])
    add("claim-card", cmd_claim_card, [("--actor", {"required": True}), ("--card", {"type": int, "required": True}), ("--base-version", {"type": int})])
    add("done-card", cmd_done_card, [("--actor", {"required": True}), ("--card", {"type": int, "required": True}), ("--base-version", {"type": int})])
    add("chat", cmd_chat, [("--actor", {"required": True}), ("--text", {"required": True})])
    add("ask", cmd_ask, [("--actor", {"required": True}), ("--text", {"required": True})])
    add("answer-ask", cmd_answer_ask, [("--actor", {"required": True}), ("--ask", {"type": int, "required": True}), ("--text", {"required": True})])
    add("suggest", cmd_suggest, [("--actor", {"required": True}), ("--target", {"required": True}), ("--proposed", {"required": True})])
    add("accept-suggestion", lambda a: cmd_resolve_suggestion(a, True), [("--actor", {"required": True}), ("--id", {"type": int, "required": True})])
    add("reject-suggestion", lambda a: cmd_resolve_suggestion(a, False), [("--actor", {"required": True}), ("--id", {"type": int, "required": True})])
    add("events", cmd_events, [("--since", {"type": int, "default": 0}), ("--wait", {"type": int, "default": 0})])
    add("render", cmd_render, [])
    cp = add("caps", cmd_caps, [("--set-actor", {"dest": "set_actor"}), ("--level", {})])

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
