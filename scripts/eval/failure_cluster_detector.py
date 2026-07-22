#!/usr/bin/env python3
# failure_cluster_detector.py — group errors.jsonl by category and flag NEW/growing failure clusters.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Failure-cluster detector: auto-convene a review when a failure cluster emerges.

Reads logs/errors.jsonl over a window, groups by `category`, and flags any category with >= THRESHOLD
failures as a CLUSTER. Dedups against a state file so a chronic/known cluster (e.g. an ongoing
critic-dispatch timeout) is NOT re-flagged every run: a cluster is `convene_worthy` only if it is NEW,
grew >= GROWTH since last flagged, or was last flagged > COOLDOWN_DAYS ago. This is the detect-and-surface
half: the convener (e.g. a nightly self-audit session) runs a review panel
(decision-council / plan-ceo-review) on each convene_worthy cluster and surfaces the verdict.

Read-only except its own state file. Deterministic. Usage:
  failure_cluster_detector.py [--hours 24] [--threshold 3]
Exit 1 if any convene_worthy cluster (so a caller can gate on it), else 0.

Config via env:
  AGENT_ROOT       repo root (default: two dirs above this file)
  AGENT_STATE_DIR  where the flagged-state file lives (default: ~/.agent-daemon/state)
"""
import argparse
import collections
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = os.environ.get("AGENT_ROOT") or str(Path(__file__).resolve().parents[2])
ERRORS = os.path.join(ROOT, "logs", "errors.jsonl")
STATE = os.path.join(
    os.environ.get("AGENT_STATE_DIR", os.path.expanduser("~/.agent-daemon/state")),
    "failure_clusters_flagged.json",
)
COOLDOWN_DAYS = 7      # a known cluster re-flags only after this long...
GROWTH = 1.5           # ...OR if it grew >= 50% since last flagged


def _load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def _save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w"), indent=1)


def detect(hours, threshold, commit_state=True):
    cut = datetime.now(timezone.utc) - timedelta(hours=hours)
    counts = collections.Counter()
    samples = {}
    try:
        for ln in open(ERRORS, encoding="utf-8"):
            try:
                d = json.loads(ln)
            except Exception:
                continue
            ts = d.get("ts")
            try:
                if ts and datetime.fromisoformat(ts) < cut:
                    continue
            except Exception:
                pass  # undated line: count it (conservative)
            cat = d.get("category") or d.get("event") or "unknown"
            counts[cat] += 1
            samples.setdefault(cat, d.get("msg") or d.get("detail") or "")
    except FileNotFoundError:
        return {"error": f"no errors.jsonl at {ERRORS}"}, []
    clusters = [{"category": c, "count": n, "sample": samples.get(c, "")[:160]}
                for c, n in counts.most_common() if n >= threshold]
    state = _load_state()
    now = datetime.now(timezone.utc)
    convene, suppressed = [], []
    for cl in clusters:
        prev = state.get(cl["category"])
        worthy, reason = True, "new"
        if prev:
            try:
                age_days = (now - datetime.fromisoformat(prev["last_flagged"])).days
            except Exception:
                age_days = 999
            if cl["count"] >= prev.get("count", 0) * GROWTH:
                reason = f"grew {prev.get('count')}->{cl['count']}"
            elif age_days >= COOLDOWN_DAYS:
                reason = f"recurred after {age_days}d"
            else:
                worthy = False
        cl["reason"] = reason
        (convene if worthy else suppressed).append(cl)
        if worthy and commit_state:
            state[cl["category"]] = {"last_flagged": now.isoformat(), "count": cl["count"]}
    if commit_state:
        _save_state(state)
    return {"window_hours": hours, "threshold": threshold,
            "convene_worthy": convene, "suppressed_known": suppressed}, convene


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--threshold", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true", help="do not update the flagged-state file")
    a = ap.parse_args(argv)
    res, convene = detect(a.hours, a.threshold, commit_state=not a.dry_run)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 1 if convene else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
