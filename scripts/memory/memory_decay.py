#!/usr/bin/env python3
# memory_decay.py: report-only forgetting curve over memory files, from recall hits and edits.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Report-only forgetting curve over memory files.

The dreaming skill prescribes Decay as `confidence = confidence * 0.5 ** (days_since_access / 45)`,
floor 0.05, "any access resets days_since_access to 0". Without a record of access, Decay always
reports 0. This supplies the input at FILE level:

  last access = the later of
    - the newest logs/vector_brain_recall.jsonl row whose top_sources include the file (a recall hit;
      scripts/memory/vector_brain.py writes this log), and
    - the file's own mtime (an edit is an access).
  weight = max(0.05, 0.5 ** (days_since_access / 45))

It reads, it never writes memory. Dreaming uses the report to choose what to re-check or distil, and to
fill `decayed` honestly (files under the 0.25 weight line). Nothing is deleted or moved here.

  memory_decay.py                 human report: buckets + the 15 most decayed files
  memory_decay.py --json PATH     also write the full table (dreaming: memory/.dreams/decay-YYYY-MM-DD.json)

Env: AGENT_ROOT, AGENT_LOG_DIR, AGENT_AUTO_MEMORY_DIR (an extra memory dir, e.g. the CLI's
per-project auto-memory folder, also scanned when set).
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
RECALL_LOG = Path(os.environ.get("AGENT_LOG_DIR", str(REPO / "logs"))) / "vector_brain_recall.jsonl"
ROOTS = [REPO / "memory"] + ([Path(os.environ["AGENT_AUTO_MEMORY_DIR"]).expanduser()]
                             if os.environ.get("AGENT_AUTO_MEMORY_DIR") else [])
SKIP_PARTS = {".archive", ".dreams", "state", "Archive", "handoff-snapshots"}
HALF_LIFE_DAYS = 45
FLOOR = 0.05
DECAYED_LINE = 0.25  # weight below this = "decayed" in the dreaming count (about 90 days without access)


def memory_files():
    out = []
    for root in ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.md"):
            if SKIP_PARTS & set(p.relative_to(root).parts):
                continue
            out.append(p.resolve())
    return sorted(set(out))


def recall_hits():
    """{resolved path: (last hit datetime, hit count)} from the recall log."""
    hits = {}
    if not RECALL_LOG.exists():
        return hits
    for line in RECALL_LOG.open():
        try:
            row = json.loads(line)
            ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
        except Exception:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        for s in row.get("top_sources") or []:
            src = s.get("source") if isinstance(s, dict) else s
            if not src:
                continue
            try:
                key = Path(src).expanduser().resolve()
            except Exception:
                continue
            last, n = hits.get(key, (None, 0))
            hits[key] = (ts if last is None or ts > last else last, n + 1)
    return hits


def table(now=None):
    now = now or datetime.now(timezone.utc)
    hits = recall_hits()
    rows = []
    for p in memory_files():
        mtime = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
        last_hit, n = hits.get(p, (None, 0))
        last = max(x for x in (mtime, last_hit) if x is not None)
        days = max(0.0, (now - last).total_seconds() / 86400)
        rows.append({"file": str(p), "days_since_access": round(days, 1),
                     "weight": round(max(FLOOR, 0.5 ** (days / HALF_LIFE_DAYS)), 3),
                     "recall_hits": n, "last_recall": last_hit.isoformat(timespec="minutes") if last_hit else None,
                     "last_edit": mtime.isoformat(timespec="minutes"),
                     "access_by": "recall" if last_hit and last_hit >= mtime else "edit"})
    rows.sort(key=lambda r: r["weight"])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = table()
    buckets = {"fresh (>=0.75, under ~19 d)": 0, "fading (0.25-0.75)": 0, "decayed (<0.25, ~90 d+)": 0}
    for r in rows:
        k = 0 if r["weight"] >= 0.75 else 1 if r["weight"] >= DECAYED_LINE else 2
        buckets[list(buckets)[k]] += 1
    never = sum(1 for r in rows if r["recall_hits"] == 0)
    print(f"memory decay report: {len(rows)} files, {never} never surfaced by recall "
          f"(recall log: {RECALL_LOG.name}). Report only, nothing changed.")
    for k, v in buckets.items():
        print(f"  {k:30} {v}")
    print("most decayed:")
    for r in rows[:15]:
        print(f"  {r['weight']:.2f}  {r['days_since_access']:6.1f} d  hits {r['recall_hits']:3}  "
              f"{r['file'].replace(str(REPO) + '/', '').replace(str(Path.home()), '~')}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                                            "half_life_days": HALF_LIFE_DAYS, "floor": FLOOR,
                                            "decayed_line": DECAYED_LINE, "buckets": buckets,
                                            "decayed": buckets["decayed (<0.25, ~90 d+)"], "rows": rows}, indent=1))
        print(f"json -> {a.json}")


if __name__ == "__main__":
    main()
