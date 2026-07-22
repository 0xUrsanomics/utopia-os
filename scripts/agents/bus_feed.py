#!/usr/bin/env python3
# bus_feed.py — one-way notifier: pipe new fleet-bus traffic to a chat topic to watch live.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Pipe NEW fleet-bus traffic to a chat topic so the operator can WATCH the agents talk in
real-time from a phone.

One-way notifier: reads the fleet_bus DB, finds messages published since the last cursor,
batches them into ONE compact digest, and posts to a dedicated relay topic via a
fire-and-forget Bot API call. There is no poller in that group, so it does not reintroduce
the shared-bot transcript pollution that comes from running a full agent poller inside a
team/client group. Intended to run on the same short-interval cron as the dispatcher.

Point it at a PRIVATE relay group (its own bot, its own topic) — internal agent chatter must
never land in a group shared with team or clients.

Cursor = a created_at watermark (ISO 8601 sorts chronologically). First run SEEDS the cursor to
the current max so we don't dump the whole backlog — the feed only shows activity from now
forward. Kill-switch: touch $AGENT_FLEET_HOME/bus_feed.disabled. Per-run cap so a burst can't
flood the topic.

Config via env: TELEGRAM_BOT_TOKEN (or AGENT_NOTIFY_ENV file), FLEET_FEED_CHAT_ID,
FLEET_FEED_THREAD (optional forum-topic id), AGENT_TZ_OFFSET_HOURS (display offset, default UTC).
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Display timestamps in the operator's local offset (bus created_at is UTC). Default 0 = UTC.
DISPLAY_TZ = timezone(timedelta(hours=int(os.environ.get("AGENT_TZ_OFFSET_HOURS", "0"))))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_bus  # noqa: E402

# AGENT_ROOT defaults to the repo root (this file is scripts/agents/bus_feed.py).
ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
FLEET_HOME = Path(os.environ.get("AGENT_FLEET_HOME", str(DATA_DIR / "fleet")))

KILL = str(FLEET_HOME / "bus_feed.disabled")
CURSOR = FLEET_HOME / "bus_feed_cursor.txt"
NOTIFY_ENV = os.environ.get("AGENT_NOTIFY_ENV", str(ROOT / ".env"))
# A private relay group + forum topic dedicated to the fleet bus (its own bot, no team/client eyes).
RELAY_CHAT_ID = os.environ.get("FLEET_FEED_CHAT_ID", "")
RELAY_THREAD = os.environ.get("FLEET_FEED_THREAD", "")  # optional forum-topic id
MAX_PER_RUN = 12
TYPE_EMOJI = {"question": "❓", "task": "🔧", "result": "✅", "note": "📝"}


def _token():
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if tok:
        return tok.strip()
    try:
        with open(NOTIFY_ENV) as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def _gist(payload, cap=140):
    try:
        d = json.loads(payload)
        if isinstance(d, dict):
            payload = d.get("result") or d.get("ask") or d.get("q") or d.get("error") or json.dumps(d)
    except Exception:
        pass
    s = " ".join(str(payload).split())  # collapse whitespace/newlines
    return s[:cap] + ("…" if len(s) > cap else "")


def _hm(ts):
    try:
        return datetime.fromisoformat(ts).astimezone(DISPLAY_TZ).strftime("%H:%M")
    except Exception:
        return "--:--"


def _send(text):
    token = _token()
    if not token or not RELAY_CHAT_ID:
        return False
    fields = {"chat_id": RELAY_CHAT_ID, "text": text, "disable_web_page_preview": "true"}
    if RELAY_THREAD:
        fields["message_thread_id"] = RELAY_THREAD
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        return False


def main():
    if os.path.exists(KILL):
        print(json.dumps({"disabled": True})); return
    rows = fleet_bus.listmsgs(limit=200)
    if not rows:
        print(json.dumps({"new": 0, "seeded": False})); return
    newest = max(r["created_at"] for r in rows)

    # first run: seed cursor to newest, post nothing (no backlog dump)
    if not CURSOR.exists():
        CURSOR.parent.mkdir(parents=True, exist_ok=True)
        CURSOR.write_text(newest)
        print(json.dumps({"new": 0, "seeded": True, "cursor": newest})); return

    last = CURSOR.read_text().strip()
    fresh = sorted([r for r in rows if r["created_at"] > last], key=lambda r: r["created_at"])
    if not fresh:
        print(json.dumps({"new": 0})); return

    shown, overflow = fresh[:MAX_PER_RUN], max(0, len(fresh) - MAX_PER_RUN)
    lines = ["🚌 fleet bus"]
    for m in shown:
        e = TYPE_EMOJI.get(m["msg_type"], "•")
        lines.append(f"{_hm(m['created_at'])} {m['from_agent']}→{m['to_agent']} {e} {_gist(m['payload'])}")
    if overflow:
        lines.append(f"…+{overflow} more")

    ok = _send("\n".join(lines))
    if ok:
        CURSOR.write_text(fresh[-1]["created_at"])  # advance only on successful post
    print(json.dumps({"new": len(fresh), "posted": ok, "overflow": overflow}))


if __name__ == "__main__":
    main()
