#!/usr/bin/env python3
# subagent_reputation.py — track per-(subagent_type, domain) verification outcomes; flag repeat failers.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
Subagent Reputation Tracker. Track per-(subagent_type, domain) verification outcomes.

Adapted from ruvnet/ruflo Pattern 2 (reputation-based degradation). Deliberately does
NOT auto-degrade silently: it surfaces flags in the nightly audit, and the parent agent
decides. Silent degradation hides a regression; a surfaced flag forces a human call.

Usage:
  # Record a verified-pass (the parent agent verified the diff/output and accepted it)
  python subagent_reputation.py pass <subagent_type> <domain> [task_slug]

  # Record a verified-fail (subagent output rejected. wrong answer, hallucinated paths,
  # missed scope, security flag)
  python subagent_reputation.py fail <subagent_type> <domain> "<reason>" [task_slug]

  # Record a partial (subagent did part of the job, parent finished. NOT a fail)
  python subagent_reputation.py partial <subagent_type> <domain> "<note>" [task_slug]

  # Show current state
  python subagent_reputation.py status

  # List flagged (subagent_type, domain) pairs needing review
  python subagent_reputation.py flagged

  # Prune entries older than 90 days
  python subagent_reputation.py prune

  # Mark a flag as reviewed (parent decision logged, no longer in queue)
  python subagent_reputation.py reviewed <subagent_type> <domain>

State: memory/state/subagent_reputation.json
Flag threshold: 3 fails in 14d for a (subagent_type, domain) pair → flag for review
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
STATE_PATH = ROOT / "memory" / "state" / "subagent_reputation.json"
FAIL_THRESHOLD = 3
WINDOW_DAYS = 14
EXPIRY_DAYS = 90


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {
        "_schema": "subagent-reputation-v1",
        "_description": "Per-(subagent_type, domain) verification ledger. Adapted from the ruflo reputation-degradation pattern. Surface-only. no auto-degrade.",
        "events": [],
        "flag_queue": []
    }


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str) + "\n")


def _key(subagent_type: str, domain: str) -> str:
    return f"{subagent_type}::{domain}"


def record_event(outcome: str, subagent_type: str, domain: str, note: str = "", task_slug: str = ""):
    state = load_state()
    now = datetime.now().isoformat()
    state["events"].append({
        "ts": now,
        "subagent_type": subagent_type,
        "domain": domain,
        "outcome": outcome,
        "note": note[:200],
        "task": task_slug[:80]
    })

    if outcome == "fail":
        cutoff = (datetime.now() - timedelta(days=WINDOW_DAYS)).isoformat()
        recent_fails = [
            e for e in state["events"]
            if e["subagent_type"] == subagent_type
            and e["domain"] == domain
            and e["outcome"] == "fail"
            and e["ts"] >= cutoff
        ]
        if len(recent_fails) >= FAIL_THRESHOLD:
            already = [
                f for f in state["flag_queue"]
                if f["subagent_type"] == subagent_type
                and f["domain"] == domain
                and f.get("status") != "reviewed"
            ]
            if not already:
                state["flag_queue"].append({
                    "subagent_type": subagent_type,
                    "domain": domain,
                    "flagged_at": now,
                    "fail_count": len(recent_fails),
                    "recent_reasons": [e["note"] for e in recent_fails[-3:]],
                    "status": "pending"
                })
                print(f"⚠️ FLAGGED: {_key(subagent_type, domain)}. {len(recent_fails)} fails in {WINDOW_DAYS}d")
            else:
                print(f"already flagged: {_key(subagent_type, domain)}")
        else:
            remaining = FAIL_THRESHOLD - len(recent_fails)
            print(f"fail logged: {_key(subagent_type, domain)} ({len(recent_fails)}/{FAIL_THRESHOLD} in window, {remaining} before flag)")
    else:
        print(f"{outcome} logged: {_key(subagent_type, domain)}")

    save_state(state)


def show_status():
    state = load_state()
    cutoff = (datetime.now() - timedelta(days=WINDOW_DAYS)).isoformat()

    by_pair = {}
    for e in state["events"]:
        if e["ts"] < cutoff:
            continue
        k = _key(e["subagent_type"], e["domain"])
        by_pair.setdefault(k, {"pass": 0, "fail": 0, "partial": 0})
        by_pair[k][e["outcome"]] += 1

    print(f"=== Subagent Reputation ({WINDOW_DAYS}d window) ===")
    print(f"Total events (all time): {len(state['events'])}")

    if not by_pair:
        print("no events in window")
    else:
        print(f"\n{'pair':<40}  pass  fail  partial  rate")
        print("-" * 75)
        for k in sorted(by_pair.keys()):
            stats = by_pair[k]
            total = sum(stats.values())
            rate = (stats["pass"] / total * 100) if total else 0
            flag = " ⚠️" if stats["fail"] >= FAIL_THRESHOLD else ""
            print(f"{k:<40}  {stats['pass']:>4}  {stats['fail']:>4}  {stats['partial']:>7}  {rate:>4.0f}%{flag}")

    pending = [f for f in state["flag_queue"] if f["status"] == "pending"]
    if pending:
        print(f"\n⚠️ {len(pending)} pending flag(s): see `flagged` command")


def show_flagged():
    state = load_state()
    pending = [f for f in state["flag_queue"] if f["status"] == "pending"]
    if not pending:
        print("no pending flags")
        return
    print(f"=== {len(pending)} flagged pair(s) for review ===\n")
    for f in pending:
        k = _key(f["subagent_type"], f["domain"])
        print(f"  {k}. {f['fail_count']} fails, flagged {f['flagged_at'][:10]}")
        for i, reason in enumerate(f.get("recent_reasons", []), 1):
            print(f"    {i}. {reason}")
        print()
    print("Resolution options:")
    print("  - mark reviewed (no action): subagent_reputation.py reviewed <subagent_type> <domain>")
    print("  - change the recommended subagent_type for the domain")
    print("  - sharpen the subagent briefing scaffold")


def mark_reviewed(subagent_type: str, domain: str):
    state = load_state()
    matched = False
    for f in state["flag_queue"]:
        if (f["subagent_type"] == subagent_type and f["domain"] == domain
                and f["status"] == "pending"):
            f["status"] = "reviewed"
            f["reviewed_at"] = datetime.now().isoformat()
            matched = True
    if matched:
        save_state(state)
        print(f"marked {_key(subagent_type, domain)} as reviewed")
    else:
        print(f"no pending flag for {_key(subagent_type, domain)}")


def prune_stale():
    state = load_state()
    cutoff = (datetime.now() - timedelta(days=EXPIRY_DAYS)).isoformat()
    before = len(state["events"])
    state["events"] = [e for e in state["events"] if e["ts"] >= cutoff]
    pruned = before - len(state["events"])
    state["flag_queue"] = [
        f for f in state["flag_queue"]
        if f["status"] != "reviewed" or f.get("reviewed_at", "") >= cutoff
    ]
    save_state(state)
    print(f"pruned {pruned} stale events (>{EXPIRY_DAYS}d)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]

    if cmd == "pass" and len(sys.argv) >= 4:
        task = sys.argv[4] if len(sys.argv) >= 5 else ""
        record_event("pass", sys.argv[2], sys.argv[3], task_slug=task)
    elif cmd == "fail" and len(sys.argv) >= 5:
        task = sys.argv[5] if len(sys.argv) >= 6 else ""
        record_event("fail", sys.argv[2], sys.argv[3], note=sys.argv[4], task_slug=task)
    elif cmd == "partial" and len(sys.argv) >= 5:
        task = sys.argv[5] if len(sys.argv) >= 6 else ""
        record_event("partial", sys.argv[2], sys.argv[3], note=sys.argv[4], task_slug=task)
    elif cmd == "status":
        show_status()
    elif cmd == "flagged":
        show_flagged()
    elif cmd == "reviewed" and len(sys.argv) >= 4:
        mark_reviewed(sys.argv[2], sys.argv[3])
    elif cmd == "prune":
        prune_stale()
    else:
        print(__doc__)
        sys.exit(1)
