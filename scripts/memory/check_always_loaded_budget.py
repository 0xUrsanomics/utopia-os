#!/usr/bin/env python3
# check_always_loaded_budget.py — guard the per-session always-loaded context footprint.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Always-loaded context budget guard.

Warns when the per-session ALWAYS-LOADED footprint re-bloats past budget. A one-time
carve can cut this footprint dramatically (e.g. move a rarely-needed file to
on-demand recall; split a bloated file into a terse skeleton + a detail companion).
This guard keeps it from creeping back as session-save appends narrative-heavy entries.

Fix when it fires: move accreted narrative/history/rationale out of the offending
file into a `*-Detail.md` recall companion, keeping only the terse operative rule
always-loaded. Run standalone or from the nightly audit. tokens ~= chars/4.
"""
import glob
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = os.path.expanduser("~")
# name -> (relpath, per-file token budget or None)
FILES = {
    "CLAUDE.md": ("CLAUDE.md", None),
    "SOUL": ("memory/SOUL.md", None),
    "USER": ("memory/USER.md", 9000),
    "Preferences": ("memory/Preferences.md", 32000),
}
TOTAL_BUDGET = 60000


def tok(path):
    try:
        return os.path.getsize(path) // 4
    except OSError:
        return 0


def main():
    total, over = 0, []
    for name, (rel, budget) in FILES.items():
        t = tok(os.path.join(ROOT, rel))
        total += t
        if budget and t > budget:
            over.append(f"{name} ~{t}tok > {budget} budget")
    mm = glob.glob(os.path.join(HOME, ".claude/projects/*/memory/MEMORY.md"))
    if mm:
        total += tok(mm[0])
    if total > TOTAL_BUDGET:
        over.append(f"TOTAL always-loaded ~{total}tok > {TOTAL_BUDGET} budget")
    if over:
        print("always-loaded budget EXCEEDED:")
        for o in over:
            print("  " + o)
        print("  fix: carve narrative to a *-Detail.md recall companion")
        sys.exit(1)
    print(f"ok: always-loaded ~{total}tok within budget ({TOTAL_BUDGET})")
    sys.exit(0)


if __name__ == "__main__":
    main()
