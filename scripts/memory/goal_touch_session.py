#!/usr/bin/env python3
# goal_touch_session.py — bump goals referenced by recent output frontmatter.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
goal_touch_session.py. Scan recent outputs for frontmatter `goal: g-XXX` tags and
bump matching goals in memory/state/active_goals.json (sessions_touched + last_advanced).

Called from skills/save.md. Idempotent. Safe on empty registry.

Usage:
  python3 scripts/memory/goal_touch_session.py [--since-hours 24] [--dry-run] [--verbose]

Default scope: outputs/raw/**/*.md modified in the last 24 hours.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
STATE = REPO / "memory/state/active_goals.json"
OUTPUTS = REPO / "outputs/raw"

GOAL_FRONTMATTER_RE = re.compile(r"^\s*goal:\s*['\"]?(g-\d{4}-\d{2}-\d{2}-\d+)['\"]?", re.MULTILINE)


def find_referenced_goals(since_hours: int, verbose: bool = False) -> set[str]:
    if not OUTPUTS.exists():
        return set()
    cutoff = datetime.now().astimezone() - timedelta(hours=since_hours)
    referenced: set[str] = set()
    for f in OUTPUTS.rglob("*.md"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime).astimezone()
        except Exception:
            continue
        if mtime < cutoff:
            continue
        try:
            head = f.read_text(errors="ignore")[:4000]
        except Exception:
            continue
        # only inspect frontmatter block (between leading --- ... ---)
        if not head.lstrip().startswith("---"):
            continue
        end = head.find("---", 3)
        if end < 0:
            continue
        front = head[3:end]
        for m in GOAL_FRONTMATTER_RE.finditer(front):
            gid = m.group(1)
            referenced.add(gid)
            if verbose:
                print(f"found {gid} in {f.relative_to(REPO)}")
    return referenced


def touch_goals(goal_ids: set[str], dry_run: bool = False) -> dict:
    if not STATE.exists():
        return {"error": f"missing {STATE}", "touched": []}
    data = json.loads(STATE.read_text())
    goals = data.get("goals", [])
    now_iso = datetime.now().astimezone().isoformat()

    touched = []
    not_found = []
    skipped_terminal = []
    for gid in goal_ids:
        match = next((g for g in goals if g.get("id") == gid), None)
        if not match:
            not_found.append(gid)
            continue
        if match.get("status") in ("done", "abandoned"):
            skipped_terminal.append(gid)
            continue
        match["sessions_touched"] = int(match.get("sessions_touched", 0)) + 1
        match["last_advanced"] = now_iso
        touched.append(gid)

    if not dry_run and touched:
        data["_updated"] = now_iso
        STATE.write_text(json.dumps(data, indent=2) + "\n")

    return {
        "touched": sorted(touched),
        "not_found": sorted(not_found),
        "skipped_terminal": sorted(skipped_terminal),
        "dry_run": dry_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-hours", type=int, default=24, help="lookback window in hours (default 24)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    referenced = find_referenced_goals(args.since_hours, args.verbose)
    if not referenced:
        print(json.dumps({"touched": [], "scanned_hours": args.since_hours, "msg": "no goal frontmatter tags in window"}))
        return 0

    result = touch_goals(referenced, dry_run=args.dry_run)
    result["scanned_hours"] = args.since_hours
    print(json.dumps(result, indent=2))
    return 0 if not result.get("error") else 2


if __name__ == "__main__":
    sys.exit(main())
