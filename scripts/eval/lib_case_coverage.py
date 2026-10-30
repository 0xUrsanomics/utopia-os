#!/usr/bin/env python3
# lib_case_coverage.py: did an eval report score exactly the cases it selected?
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Did an eval or backtest report score exactly the cases it selected?

A run that silently drops, repeats or adds cases still prints a clean-looking score.
Pattern from the elizaOS benchmark rule that a result must contain exactly the selected
case IDs or it is not published (packages/benchmarks/orchestrator README, plus the
exact-count check in registry/scores.py). Same family as the rule that a check that ran
nothing is a FAIL.

    from lib_case_coverage import coverage
    cov = coverage(selected_ids, scored_ids)   # cov["status"] is "complete" or "partial"

    python3 lib_case_coverage.py --selftest
"""
from __future__ import annotations

import sys
from collections import Counter


def coverage(selected, scored) -> dict:
    """Compare the case IDs a run selected with the IDs it actually scored."""
    sel, got = Counter(selected), Counter(scored)
    missing = sorted(set(sel) - set(got))
    extra = sorted(set(got) - set(sel))
    duplicate = sorted(k for k, n in got.items() if n > 1)
    dup_selected = sorted(k for k, n in sel.items() if n > 1)
    ok = bool(sel) and not (missing or extra or duplicate or dup_selected)
    return {"status": "complete" if ok else "partial", "selected": sum(sel.values()),
            "scored": sum(got.values()), "missing": missing, "extra": extra,
            "duplicate": duplicate, "duplicate_selected": dup_selected,
            "empty": not sel}


def summary(cov: dict) -> str:
    if cov["status"] == "complete":
        return f"coverage complete: {cov['scored']}/{cov['selected']} selected cases scored"
    parts = [f"{k}: {', '.join(map(str, cov[k]))}" for k in
             ("missing", "extra", "duplicate", "duplicate_selected") if cov[k]]
    if cov["empty"]:
        parts.append("no cases selected")
    return (f"coverage PARTIAL, score is diagnostic only ({cov['scored']} scored of "
            f"{cov['selected']} selected; " + "; ".join(parts) + ")")


def _selftest() -> int:
    cases = [(["a", "b"], ["b", "a"], "complete"),
             (["a", "b"], ["a"], "partial"),            # dropped case
             (["a"], ["a", "a"], "partial"),            # scored twice
             (["a"], ["a", "z"], "partial"),            # unselected case
             ([], [], "partial")]                       # ran nothing
    bad = [c for c in cases if coverage(c[0], c[1])["status"] != c[2]]
    print(f"coverage selftest: {len(cases) - len(bad)}/{len(cases)} pass")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(_selftest() if "--selftest" in sys.argv else 2)
