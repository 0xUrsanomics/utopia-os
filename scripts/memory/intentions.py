#!/usr/bin/env python3
# intentions.py: plans and promised follow-ups as their own memory type, each with a trigger date.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Intentions: plans and promised follow-ups as their own memory type, each with a trigger date.

Facts say what IS; an intention says what someone PLANS to do and when it should come back up
("check the first automated push tomorrow", "follow up with Alice if no slot by Monday",
"re-evaluate the new library once it is 7 days old"). Kept as prose inside a handoff block or a
dossier, these only resurface if a session happens to read that paragraph. Here each one has a due
date, and a wake-up briefing can list what is due (`due --json`).

Store: memory/state/intentions.json (list of objects; memory/state/ is runtime, gitignored).
Dates are calendar dates in the operator's timezone (AGENT_UTC_OFFSET_HOURS, default 0).

Usage:
  intentions.py add "Check the nightly export landed" --due 2026-10-17 [--owner agent|operator] [--source "chat msg 42"]
  intentions.py list [--all]
  intentions.py due [--days 0]        # overdue + due within N days (default today only)
  intentions.py done ID [--note "..."]
  intentions.py drop ID [--note "..."]
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
STORE = Path(os.environ.get("AGENT_INTENTIONS_FILE", str(ROOT / "memory" / "state" / "intentions.json")))
LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=float(os.environ.get("AGENT_UTC_OFFSET_HOURS", "0"))))
OWNERS = ("agent", "operator")


def today():
    return datetime.datetime.now(LOCAL_TZ).date()


def load():
    try:
        return json.loads(STORE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(items):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(STORE)


def due_items(days=0, items=None):
    """Open intentions that are overdue or due within `days` days, oldest first."""
    items = load() if items is None else items
    limit = today() + datetime.timedelta(days=days)
    out = [i for i in items if i["status"] == "open" and datetime.date.fromisoformat(i["due"]) <= limit]
    return sorted(out, key=lambda i: i["due"])


def fmt(i):
    d = datetime.date.fromisoformat(i["due"])
    delta = (d - today()).days
    when = "today" if delta == 0 else f"{-delta}d overdue" if delta < 0 else f"in {delta}d"
    src = f" [{i['source']}]" if i.get("source") else ""
    return f"#{i['id']} {i['due']} ({when}) {i['owner']}: {i['text']}{src}"


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("text")
    a.add_argument("--due", required=True, help="YYYY-MM-DD (operator's local date)")
    a.add_argument("--owner", default="agent", choices=OWNERS)
    a.add_argument("--source", default="")
    lp = sub.add_parser("list")
    lp.add_argument("--all", action="store_true")
    dp = sub.add_parser("due")
    dp.add_argument("--days", type=int, default=0)
    dp.add_argument("--json", action="store_true")
    for name in ("done", "drop"):
        p = sub.add_parser(name)
        p.add_argument("id", type=int)
        p.add_argument("--note", default="")
    args = ap.parse_args()

    items = load()
    if args.cmd == "add":
        datetime.date.fromisoformat(args.due)  # validate
        nid = max((i["id"] for i in items), default=0) + 1
        items.append({"id": nid, "text": args.text, "due": args.due, "owner": args.owner, "source": args.source,
                      "status": "open", "created": today().isoformat()})
        save(items)
        print(f"added #{nid}")
    elif args.cmd == "list":
        rows = items if args.all else [i for i in items if i["status"] == "open"]
        for i in sorted(rows, key=lambda i: i["due"]):
            print(fmt(i) + ("" if i["status"] == "open" else f"  [{i['status']}]"))
        if not rows:
            print("no open intentions")
    elif args.cmd == "due":
        rows = due_items(args.days, items)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for i in rows:
                print(fmt(i))
            if not rows:
                print("nothing due")
    else:
        hit = next((i for i in items if i["id"] == args.id), None)
        if not hit:
            print(f"no intention #{args.id}")
            return 1
        hit["status"] = "done" if args.cmd == "done" else "dropped"
        hit["closed"] = today().isoformat()
        if args.note:
            hit["note"] = args.note
        save(items)
        print(f"#{args.id} {hit['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
