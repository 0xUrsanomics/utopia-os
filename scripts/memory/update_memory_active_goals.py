#!/usr/bin/env python3
# update_memory_active_goals.py — regenerate the Active Goals block in MEMORY.md from state.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
update_memory_active_goals.py. Regenerate the `## 🎯 Active Goals` block at the top of
MEMORY.md from `memory/state/active_goals.json`. Idempotent.

Called from skills/goals.md after any state mutation (new / done / pause / abandon).
Also safe to call from cron or manually.

Block markers:
  <!-- active-goals-start -->
  ## 🎯 Active Goals
  ...
  <!-- active-goals-end -->

If markers are absent, inserts the block at the top of the file (after a leading
H1 if present). If present, replaces only the content between markers.

Config via env:
  AGENT_ROOT        repo root (default: two dirs above this file)
  AGENT_MEMORY_MD   path to the MEMORY.md to update. Default: <root>/memory/MEMORY.md.
                    Point this at a harness-managed memory file if yours lives elsewhere.

Usage:
  python3 scripts/memory/update_memory_active_goals.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
STATE = REPO / "memory/state/active_goals.json"
MEMORY_MD = Path(os.environ.get("AGENT_MEMORY_MD", str(REPO / "memory" / "MEMORY.md")))

START_MARKER = "<!-- active-goals-start -->"
END_MARKER = "<!-- active-goals-end -->"


def progress_bar(done: int, total: int, width: int = 10) -> str:
    """ASCII progress bar. [██████░░░░] 6/10."""
    if total <= 0:
        return "[" + "-" * width + "]"
    cells = max(0, min(width, round((done / total) * width)))
    return "[" + "█" * cells + "░" * (width - cells) + "]"


def render_block(state: dict) -> str:
    caps = state.get("_caps", {})
    cap = caps.get("max_active", 10)
    goals = state.get("goals", [])
    active = [g for g in goals if g.get("status") == "active"]

    lines = [
        START_MARKER,
        "## 🎯 Active Goals",
        "",
    ]
    if not active:
        lines.append(f"- (none. /goals new to create. cap {cap})")
    else:
        for g in active:
            gid = g.get("id", "?")
            title = (g.get("title") or "")[:60]
            milestones = g.get("milestones") or []
            ms_total = len(milestones)
            ms_done = sum(1 for m in milestones if m.get("status") == "done")
            bar = progress_bar(ms_done, ms_total)
            tail = ""
            if g.get("due"):
                tail = f" — due {g['due']}"
            elif g.get("review_after"):
                tail = f" — review {g['review_after']}"
            lines.append(f"- `{gid}` {title}  {bar} {ms_done}/{ms_total}{tail}")
    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def update_memory(dry_run: bool = False) -> dict:
    if not STATE.exists():
        return {"error": f"missing {STATE}"}
    if not MEMORY_MD.exists():
        return {"error": f"missing {MEMORY_MD}"}

    state = json.loads(STATE.read_text())
    block = render_block(state)
    content = MEMORY_MD.read_text()

    if START_MARKER in content and END_MARKER in content:
        # Replace existing block in-place
        before = content.split(START_MARKER, 1)[0]
        after = content.split(END_MARKER, 1)[1]
        new_content = before + block + after
        action = "replaced"
    else:
        # Insert at very top. MEMORY.md uses section headers (# User / # Feedback etc),
        # not a document-level H1, so prepending is safe.
        new_content = block + "\n\n" + content
        action = "inserted"

    if dry_run:
        return {"action": f"would {action}", "block_preview": block[:200]}
    MEMORY_MD.write_text(new_content)
    return {"action": action, "wrote": str(MEMORY_MD), "ts": datetime.now().astimezone().isoformat()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    result = update_memory(dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0 if not result.get("error") else 2


if __name__ == "__main__":
    sys.exit(main())
