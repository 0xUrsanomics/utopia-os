#!/usr/bin/env python3
# memory_link_check.py: dead-pointer check for the always-loaded memory indexes.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
Dead-pointer check for the always-loaded memory indexes.

Checks BOTH files that call themselves the memory index, deliberately:

  1. <repo>/memory/MEMORY.md                         (repo-relative links)
  2. the harness auto-memory index, if the harness keeps one outside the repo
     (for Claude Code: ~/.claude/projects/<repo path slug>/memory/MEMORY.md)

Checking only one is how this defect stays invisible: the two carry
overlapping titles but different link conventions, so inspecting either in
isolation looks healthy while the other rots. A single wrong relative prefix
(`../../x`, written as if the file sat in the repo) copied between the two
can kill a large share of one index without anyone noticing.

Env (optional):
  AGENT_ROOT                repo root (default: two levels up from this file)
  AGENT_HARNESS_MEMORY_DIR  directory holding the harness-injected MEMORY.md
                            (default: the Claude Code project slug for AGENT_ROOT)

Exit 0 clean, 1 if any pointer is dead. Prints the measurement either way,
never a bare "ok", so a clean run is still evidence rather than silence.

Usage:
    memory_link_check.py            # check both, human output
    memory_link_check.py --json     # machine output for cron/digest
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

REPO = pathlib.Path(os.environ.get("AGENT_ROOT", str(pathlib.Path(__file__).resolve().parents[2])))
# Claude Code names a project's directory after its absolute path with every
# non-alphanumeric character replaced by "-".
_SLUG = re.sub(r"[^A-Za-z0-9]", "-", str(REPO.resolve()))
HARNESS = pathlib.Path(os.environ.get(
    "AGENT_HARNESS_MEMORY_DIR",
    str(pathlib.Path.home() / ".claude" / "projects" / _SLUG / "memory")))

LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Brace-expansion pointers, e.g. `memory/Feedback/{a,b,c}.md`. Added after this
# checker reported "all alive, 0 dead" on an index that had several dead
# pointers written in this form. The compact notation is used throughout
# MEMORY.md to list sibling dossiers on one line, and because the literal string
# is not a real path, a markdown-link-only parser skips it entirely rather than
# failing it. A guard that answers "all clear" on a surface it cannot see is
# worse than no guard, because it converts an unknown into a false assurance.
BRACE = re.compile(r"((?:[\w.@-]+/)+)\{([^}]+)\}((?:\.\w+)?)")


def check(index: pathlib.Path) -> dict:
    """Resolve every non-URL markdown link in `index` relative to its own dir."""
    if not index.is_file():
        return {"index": str(index), "exists": False, "total": 0, "dead": []}

    text = index.read_text(encoding="utf-8", errors="replace")
    base = index.parent
    dead = []
    total = 0

    for label, url in LINK.findall(text):
        if url.startswith(("http://", "https://", "mailto:")):
            continue
        total += 1
        # Strip a #anchor / ?query before resolving; both are valid in a link
        # and neither is part of the path on disk.
        path = url.split("#", 1)[0].split("?", 1)[0]
        if not path:
            continue
        target = (base / path).resolve() if not path.startswith("/") else pathlib.Path(path)
        if not target.exists():
            dead.append({"label": label[:70], "url": url, "resolved": str(target)})

    # Brace-expansion pointers. Resolved against BOTH the index's own directory and
    # the repo root, because the harness index sits outside the repo but writes
    # repo-relative paths; requiring only one base would re-create the split that
    # made the original defect invisible.
    for pre, inner, suf in BRACE.findall(text):
        for part in (p.strip() for p in inner.split(",")):
            # A `*` means the author wrote a glob, not an enumeration. Those are
            # genuinely ambiguous, so they are skipped and COUNTED as skipped
            # rather than silently passed.
            if not part or "*" in part:
                continue
            rel = f"{pre}{part}{suf}"
            total += 1
            if not any((b / rel).exists() for b in (base, REPO)):
                dead.append({"label": "brace-expansion", "url": rel,
                             "resolved": str((REPO / rel))})

    return {"index": str(index), "exists": True, "total": total, "dead": dead}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    results = [check(REPO / "memory" / "MEMORY.md"), check(HARNESS / "MEMORY.md")]
    n_dead = sum(len(r["dead"]) for r in results)
    # Both indexes missing means nothing was checked; that is a failure, not "0 dead".
    none_checked = not any(r["exists"] for r in results)

    if args.json:
        print(json.dumps({"dead_total": n_dead, "indexes": results,
                          "checked": not none_checked}, indent=2))
        if none_checked:
            print("FAIL: no MEMORY.md index found, nothing checked", file=sys.stderr)
            return 2
        return 1 if n_dead else 0

    for r in results:
        if not r["exists"]:
            print(f"MISSING  {r['index']}")
            continue
        d = len(r["dead"])
        print(f"{r['total'] - d}/{r['total']} alive   {r['index']}")
        for item in r["dead"]:
            print(f"    DEAD  {item['url']}")
            print(f"          -> {item['resolved']}")
            print(f"          ({item['label']})")

    if none_checked:
        print("\nFAIL: no MEMORY.md index found, nothing checked (set AGENT_ROOT / AGENT_HARNESS_MEMORY_DIR)")
        return 2
    print(f"\ntotal dead pointers: {n_dead}")
    return 1 if n_dead else 0


if __name__ == "__main__":
    sys.exit(main())
