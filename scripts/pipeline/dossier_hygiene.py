#!/usr/bin/env python3
# dossier_hygiene.py — scan memory dossiers for single-project inline candidates + staleness.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Dossier hygiene. Scan memory/Context/ + memory/Infra/ for dossiers that
should migrate into project files (single-project tags) or are stale.

Complements skills/graph-hygiene.md, which lints the knowledge-graph side.

Reports:
- INLINE CANDIDATES. dossiers with exactly one `projects:` tag. Should
  consider migrating their content into the project file directly, since
  they're not actually shared cross-project (which is the point of Context/).
- STALE. last_updated frontmatter or mtime older than 30 days.
- UNTAGGED. no `projects:` field (info only. not all dossiers need tagging).

Config via env:
  AGENT_ROOT  repo root (default: two dirs above this file)
  AGENT_TZ    IANA timezone name for age math (default: UTC)

Usage:
    dossier_hygiene.py           # text report (default)
    dossier_hygiene.py --json    # machine-readable
    dossier_hygiene.py --tg      # short summary for a chat digest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
TZ = ZoneInfo(os.environ.get("AGENT_TZ", "UTC"))
SCAN_DIRS = [ROOT / "memory/Context", ROOT / "memory/Infra"]
STALE_DAYS = 30


def parse_frontmatter(content: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    fm = m.group(1)
    out: dict = {}
    for line in fm.splitlines():
        kv = re.match(r"^(\w+):\s*(.*)$", line)
        if kv:
            out[kv.group(1)] = kv.group(2).strip()
    # Inline projects: [a, b]
    pm = re.search(r"^projects:\s*\[([^\]]*)\]", fm, re.MULTILINE)
    if pm:
        slugs = [s.strip().strip('"').strip("'") for s in pm.group(1).split(",")]
        out["projects"] = [s for s in slugs if s]
    else:
        # Block: projects:\n  - a\n  - b
        bm = re.search(r"^projects:\s*\n((?:\s+-\s+\S+\s*\n?)+)", fm, re.MULTILINE)
        if bm:
            slugs = []
            for line in bm.group(1).splitlines():
                im = re.match(r"\s*-\s+(.+)", line)
                if im:
                    slugs.append(im.group(1).strip().strip('"').strip("'"))
            out["projects"] = slugs
    return out


def get_last_modified(filepath: Path, fm: dict) -> tuple[datetime, str]:
    """Return (timestamp, source). Prefers frontmatter last_updated, falls back to mtime."""
    val = fm.get("last_updated") or fm.get("created")
    if val:
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt, "frontmatter"
        except Exception:
            pass
    mtime = filepath.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=TZ), "mtime"


def scan() -> dict:
    inline_candidates = []
    stale = []
    untagged = []
    multi_project = []
    now = datetime.now(TZ)

    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for fp in sorted(d.glob("*.md")):
            try:
                content = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            fm = parse_frontmatter(content)
            rel = str(fp.relative_to(ROOT))

            projects = fm.get("projects", [])
            last_dt, src = get_last_modified(fp, fm)
            age_days = (now - last_dt).days

            entry = {
                "path": rel,
                "projects": projects,
                "last_updated": last_dt.isoformat(),
                "age_days": age_days,
                "age_source": src,
            }

            if not projects:
                untagged.append(entry)
            elif len(projects) == 1:
                inline_candidates.append(entry)
            else:
                multi_project.append(entry)

            if age_days >= STALE_DAYS:
                stale.append(entry)

    return {
        "scanned_at": now.isoformat(),
        "stale_threshold_days": STALE_DAYS,
        "inline_candidates": inline_candidates,
        "stale": stale,
        "untagged": untagged,
        "multi_project": multi_project,
    }


def render_text(report: dict) -> str:
    lines = []
    lines.append(f"== DOSSIER HYGIENE. {report['scanned_at'][:10]} ==\n")

    ic = report["inline_candidates"]
    lines.append(f"[INLINE CANDIDATES] ({len(ic)}): single-project tag, consider migrating content into project file")
    if ic:
        for e in ic:
            lines.append(f"  • {e['path']} → {e['projects'][0]} (age {e['age_days']}d, {e['age_source']})")
    else:
        lines.append("  none")
    lines.append("")

    st = report["stale"]
    lines.append(f"[STALE] ({len(st)}): >{report['stale_threshold_days']}d since update")
    if st:
        for e in st:
            tag = ",".join(e["projects"]) if e["projects"] else "untagged"
            lines.append(f"  • {e['path']} ({tag}): age {e['age_days']}d")
    else:
        lines.append("  none")
    lines.append("")

    mp = report["multi_project"]
    lines.append(f"[MULTI-PROJECT] ({len(mp)}): correctly shared cross-project, healthy state")
    if mp:
        for e in mp:
            lines.append(f"  • {e['path']} → {','.join(e['projects'])}")
    lines.append("")

    ut = report["untagged"]
    lines.append(f"[UNTAGGED] ({len(ut)}): no projects: field. Info only. not all dossiers need tagging")
    if ut:
        for e in ut:
            lines.append(f"  • {e['path']} (age {e['age_days']}d)")
    lines.append("")

    return "\n".join(lines)


def render_tg(report: dict) -> str:
    """One-line summary for a daily digest. Quiet when nothing to report."""
    ic = len(report["inline_candidates"])
    st = len(report["stale"])
    if ic == 0 and st == 0:
        return "🧹 dossier hygiene. clean. all multi-project or healthy."
    parts = []
    if ic:
        parts.append(f"{ic} inline-candidate")
    if st:
        parts.append(f"{st} stale")
    return f"🧹 dossier hygiene. {' / '.join(parts)}. run dossier_hygiene.py for details."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--tg", action="store_true", help="one-line summary")
    args = ap.parse_args()

    report = scan()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.tg:
        print(render_tg(report))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
