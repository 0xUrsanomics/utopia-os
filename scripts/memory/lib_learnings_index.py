#!/usr/bin/env python3
# lib_learnings_index.py: derived index over memory/Learnings.md (fix-owed worklist, recurrence counts).
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Derived index over memory/Learnings.md. Replaces hand-typed greps in the save skill.

WHY THIS EXISTS
A spec that tells the weekly review to run `grep -l 'fix-owed' memory/Learnings.md` is broken by
construction: run against ONE file, `-l` prints the filename and no entries, so the worklist is
empty and nobody notices, because an empty worklist reads exactly like "nothing owed".

Three more defects in the same convention:
  * bare `fix-owed` also matches an older `structural-fix-owed`, a different token
  * the recurrence tag drifts into several surface forms in a live file:
        `(... reusable) #recurrence-3x`   outside the tag parens
        `(... , recurrence-4x)`           inside a #tags list, no hash
        `tags:: #reusable #recurrence-2x` tag line under the heading
    so `grep '#recurrence-'` silently drops the in-list variant, which is the precise failure the
    tag was invented to prevent
  * the close half (`closed_by::`) is never exercised if closing is done by hand

GENERATE the index from the artifact, never from a hand-kept parallel description of it. A grep
string in a doc is a parallel description.

DENOMINATOR NOTE. This reports ENTRIES, not MARKERS. One entry can carry the tag twice (once in
prose and once on its tag line), so a marker count and an entry count are both correct and answer
different questions. Entry-level is the right unit for a worklist, because the unit of work is an
entry.

Entry schemas read: `## YYYY-MM-DD ...` and `### YYYY-MM-DD ...` headings, plus top-level dated
bullets (`- YYYY-MM-DD #tag: text`, column 0 only; an indented bullet stays inside its entry).

Env (optional): AGENT_ROOT (repo root, default: two levels up from this file).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
LEARNINGS = ROOT / "memory" / "Learnings.md"

# Both heading schemas: `### YYYY-MM-DD (prose)` (A) and `## YYYY-MM-DD. Title` (B). B is the
# canonical form going forward, but the index keeps reading A: a reader that silently skipped
# older entries would recreate the bug it exists to fix.
HEAD_RE = re.compile(r"^(#{2,3})\s+(\d{4}-\d{2}-\d{2})\s*(.*)$")
# Format C, a top-level dated bullet `- YYYY-MM-DD #tag: text`. A reader keyed only on headings
# cannot see these. Column 0 only: an indented bullet stays inside its entry.
BULLET_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2})\b\s*(.*)$")
# One pattern for all three recurrence surface forms. The `#` is optional precisely because the
# in-list variant omits it.
RECUR_RE = re.compile(r"#?recurrence-(\d+)x\b", re.I)
# Word-boundary fix-owed that does NOT match structural-fix-owed.
FIXOWED_RE = re.compile(r"(?<![\w-])fix-owed(?![\w-])", re.I)
CLOSED_RE = re.compile(r"closed_by::", re.I)


def entries(path: Path = LEARNINGS) -> list[dict]:
    """Split the file into dated entries. Each carries its heading, date, schema and body.
    A missing file raises FileNotFoundError: an empty list would read as "nothing owed"."""
    if not path.exists():
        raise FileNotFoundError(f"Learnings file not found: {path}")
    out: list[dict] = []
    cur: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEAD_RE.match(line)
        b = None if m else BULLET_RE.match(line)
        if m:
            if cur:
                out.append(cur)
            cur = {"date": m.group(2), "schema": "B" if m.group(1) == "##" else "A",
                   "title": m.group(3).strip().lstrip(".\u00b7- ").strip(), "lines": []}
        elif b:
            if cur:
                out.append(cur)
            cur = {"date": b.group(1), "schema": "C", "title": b.group(2).strip(), "lines": [line]}
        elif cur is not None:
            cur["lines"].append(line)
    if cur:
        out.append(cur)
    for e in out:
        e["body"] = "\n".join(e["lines"])
    return out


def recurrences(path: Path = LEARNINGS) -> list[dict]:
    """Every entry carrying a recurrence marker, highest N first. Reads all three forms."""
    hits = []
    for e in entries(path):
        ns = [int(n) for n in RECUR_RE.findall(e["title"] + "\n" + e["body"])]
        if ns:
            hits.append({"date": e["date"], "schema": e["schema"], "n": max(ns),
                         "title": (e["title"] or e["body"].strip().split("\n")[0])[:110]})
    return sorted(hits, key=lambda h: (-h["n"], h["date"]))


def fix_owed(path: Path = LEARNINGS) -> list[dict]:
    """Entries naming an un-shipped fix: tagged fix-owed, not structural-fix-owed, not closed."""
    out = []
    for e in entries(path):
        blob = e["title"] + "\n" + e["body"]
        if FIXOWED_RE.search(blob) and not CLOSED_RE.search(blob):
            ns = [int(n) for n in RECUR_RE.findall(blob)]
            out.append({"date": e["date"], "schema": e["schema"], "recurrence": max(ns) if ns else 0,
                        "title": (e["title"] or e["body"].strip().split("\n")[0])[:110]})
    return sorted(out, key=lambda h: (-h["recurrence"], h["date"]))


def close_fix_owed(date: str, note: str, match: str | None = None,
                   path: Path = LEARNINGS) -> str:
    """Close an open fix-owed entry by appending `closed_by:: <note>` to it.

    The drain half of the fix-owed contract: an index that can only LIST owed fixes
    leaves closing to hand edits, so `closed_by::` is never exercised and the open
    count only grows. Refuses to guess: errors on
    zero matches or on ambiguity (multiple open fix-owed entries share the date),
    where `--match <substring>` disambiguates. Never closes an already-closed entry.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    heads = [(i, m) for i, l in enumerate(lines) if (m := HEAD_RE.match(l) or BULLET_RE.match(l))]
    cands = []
    for idx, (i, m) in enumerate(heads):
        if (m.group(2) if m.re is HEAD_RE else m.group(1)) != date:
            continue
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        blob = "\n".join(lines[i:end])
        if not FIXOWED_RE.search(blob) or CLOSED_RE.search(blob):
            continue
        if match and match.lower() not in blob.lower():
            continue
        cands.append((i, end, lines[i]))
    if not cands:
        raise SystemExit(f"no OPEN fix-owed entry on {date}"
                         + (f" matching '{match}'" if match else "")
                         + " (already closed, or not fix-owed, or wrong date)")
    if len(cands) > 1:
        raise SystemExit(f"ambiguous: {len(cands)} open fix-owed entries on {date}; "
                         f"add --match '<substring>' to pick one:\n  "
                         + "\n  ".join(h[:88] for _, _, h in cands))
    i, end, head = cands[0]
    # insert after the entry's last non-blank line, before the next heading
    at = end
    while at - 1 > i and not lines[at - 1].strip():
        at -= 1
    lines.insert(at, f"closed_by:: {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return head


def schema_split(path: Path = LEARNINGS) -> dict:
    """Per-schema counts. The canonical format is forward-only, so this is how drift gets watched."""
    es = entries(path)
    return {"total": len(es),
            "A": sum(e["schema"] == "A" for e in es),
            "B": sum(e["schema"] == "B" for e in es),
            "C": sum(e["schema"] == "C" for e in es)}


def main() -> int:
    ap = argparse.ArgumentParser(description="derived index over memory/Learnings.md")
    ap.add_argument("what", choices=["recurrences", "fix-owed", "schema", "all", "close"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--path", type=Path, default=LEARNINGS)
    ap.add_argument("--date", help="YYYY-MM-DD of the fix-owed entry to close (with `close`)")
    ap.add_argument("--note", help="closed_by note, e.g. 'SHIPPED YYYY-MM-DD ...' (with `close`)")
    ap.add_argument("--match", help="title/body substring to disambiguate same-date entries")
    a = ap.parse_args()

    if not a.path.is_file():
        # An empty worklist from a missing file reads exactly like "nothing owed". Fail loud.
        print(f"FAIL: Learnings file not found: {a.path} (set AGENT_ROOT or pass --path)",
              file=sys.stderr)
        return 2

    if a.what == "close":
        if not a.date or not a.note:
            raise SystemExit("close requires --date YYYY-MM-DD and --note '<closed_by text>'")
        head = close_fix_owed(a.date, a.note, a.match, a.path)
        print(f"closed: {head[:90]}\n  closed_by:: {a.note[:90]}")
        return 0

    data = {}
    if a.what in ("recurrences", "all"): data["recurrences"] = recurrences(a.path)
    if a.what in ("fix-owed", "all"):    data["fix_owed"] = fix_owed(a.path)
    if a.what in ("schema", "all"):      data["schema"] = schema_split(a.path)

    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    for r in data.get("recurrences", []):
        print(f"  {r['n']}x  {r['date']}  [{r['schema']}]  {r['title']}")
    for f in data.get("fix_owed", []):
        mark = f"{f['recurrence']}x" if f["recurrence"] else "--"
        print(f"  OWED {mark:>3}  {f['date']}  [{f['schema']}]  {f['title']}")
    if "schema" in data:
        s = data["schema"]
        print(f"  entries {s['total']}  |  A-format {s['A']}  B-format {s['B']}  C-format (dated bullet) {s['C']}")
    if not any(data.values()):
        print("  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
