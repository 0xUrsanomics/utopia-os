#!/usr/bin/env python3
"""Provision the forum topics for the two-surface Telegram layout. Stdlib only, token from env.

WHY THIS EXISTS. `docs/bot-setup.md` describes the two-surface pattern: one private forum group
with an **Ops** topic (your live chat) and a **Cron Reports** topic (scheduled output). Creating
those topics is the one part a bot CAN do, and doing it by hand means copying `message_thread_id`
values out of API responses without a typo. This script does exactly that step and prints the
routing table you wire into the harness. It is not a framework; it is the createForumTopic call
plus honest error handling.

WHAT IT CANNOT DO (by Telegram's design, not ours). A bot cannot create a group and cannot turn
Topics on. Both are owner-only actions in the Telegram app. So before this script works you must,
once, by hand:
  1. create a group,
  2. Group -> Edit -> Topics -> on,
  3. add the bot, promote it to admin, grant Manage Topics.
Then run this. If Topics are still off you get `400 the chat is not a forum`, and the fix is
step 2, not this script.

IT SHIPS NO CREDENTIALS. The token is read from the environment at call time, never written or
logged, and scrubbed out of any error string before it is printed. Same doctrine as
`scripts/mcp/telegram_bridge.py`: document the interface, never the credentials.

RUN IT

    export TELEGRAM_BOT_TOKEN=123456789:AA...          # from BotFather
    python3 scripts/setup/provision_topics.py -100123456789            # the group id (negative)
    python3 scripts/setup/provision_topics.py -100123456789 --topics "Ops,Cron Reports,Signals"

    python3 scripts/setup/provision_topics.py --selftest   # no token needed, no network

NOT IDEMPOTENT. Each run creates NEW topics; running twice gives you duplicates. Run it once. If
you need to add a topic later, pass just that one with --topics.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org"
DEFAULT_TOPICS = ["Ops", "Cron Reports"]


def _token() -> str:
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not t:
        sys.exit("TELEGRAM_BOT_TOKEN is not set. export it (from BotFather) before running.")
    return t


def _scrub(text: str) -> str:
    """Never let the token leak into printed output, including error bodies."""
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if t and t in text:
        text = text.replace(t, "<TELEGRAM_BOT_TOKEN>")
    return text


def _call(method: str, params: dict, timeout: float = 30.0) -> dict:
    url = f"{API}/bot{_token()}/{method}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()
        except Exception:
            pass
        return json.loads(body) if body.strip().startswith("{") else {
            "ok": False, "error_code": e.code, "description": _scrub(body or str(e)),
        }
    except Exception as e:  # network, timeout, decode
        return {"ok": False, "description": _scrub(str(e))}


def create_topic(chat_id: str, name: str) -> tuple[bool, str]:
    """Create one forum topic. Returns (ok, message_thread_id-or-error)."""
    resp = _call("createForumTopic", {"chat_id": chat_id, "name": name})
    if resp.get("ok"):
        return True, str(resp["result"]["message_thread_id"])
    desc = _scrub(str(resp.get("description", "unknown error")))
    if "not a forum" in desc.lower():
        desc += "  <- Topics are OFF on this group. Enable them in-app (Group -> Edit -> Topics), then re-run."
    return False, desc


def provision(chat_id: str, topics: list[str]) -> int:
    print(f"provisioning {len(topics)} topic(s) in chat {chat_id}\n")
    routing: dict[str, str] = {}
    failed = False
    for name in topics:
        ok, val = create_topic(chat_id, name)
        if ok:
            print(f"  created  {name!r:22}  message_thread_id = {val}")
            routing[name] = val
        else:
            print(f"  FAILED   {name!r:22}  {val}")
            failed = True
    if routing:
        print("\nrouting table (wire these into the harness):")
        print(f"  group chat_id            = {chat_id}")
        for name, tid in routing.items():
            print(f"  {name+' thread_id':30} = {tid}")
        print(
            "\nSend live replies with the Ops thread_id and every scheduled task with the Cron\n"
            "Reports thread_id. A sendMessage with no message_thread_id lands in General."
        )
    return 1 if failed else 0


def selftest() -> int:
    """No token, no network: verify arg parsing, URL shape, and token scrubbing."""
    fails = []

    def check(label, cond):
        print(f"  [{'ok' if cond else 'FAIL'}] {label}")
        if not cond:
            fails.append(label)

    ns = _parse(["-100999", "--topics", "A, B ,C"])
    check("chat_id parsed", ns.chat_id == "-100999")
    check("topics split + trimmed", _topics(ns) == ["A", "B", "C"])
    check("default topics", _topics(_parse(["-100999"])) == DEFAULT_TOPICS)

    saved = os.environ.get("TELEGRAM_BOT_TOKEN")
    os.environ["TELEGRAM_BOT_TOKEN"] = "111:AAsecret-should-never-print"
    try:
        scrubbed = _scrub("error at https://api.telegram.org/bot111:AAsecret-should-never-print/x")
        check("token scrubbed from errors", "AAsecret-should-never-print" not in scrubbed)
    finally:
        if saved is None:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        else:
            os.environ["TELEGRAM_BOT_TOKEN"] = saved

    print("\nSELFTEST", "PASS" if not fails else f"FAIL ({len(fails)})")
    return 0 if not fails else 1


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create the two-surface forum topics in a Telegram group.")
    p.add_argument("chat_id", nargs="?", help="the group id (negative, e.g. -100123456789)")
    p.add_argument("--topics", default=",".join(DEFAULT_TOPICS),
                   help='comma-separated topic names (default: "Ops,Cron Reports")')
    p.add_argument("--selftest", action="store_true", help="offline checks, no token or network")
    return p.parse_args(argv)


def _topics(ns: argparse.Namespace) -> list[str]:
    return [t.strip() for t in ns.topics.split(",") if t.strip()]


def main(argv: list[str] | None = None) -> int:
    ns = _parse(sys.argv[1:] if argv is None else argv)
    if ns.selftest:
        return selftest()
    if not ns.chat_id:
        sys.exit("usage: provision_topics.py <group_chat_id> [--topics \"A,B\"]  (or --selftest)")
    return provision(ns.chat_id, _topics(ns))


if __name__ == "__main__":
    sys.exit(main())
