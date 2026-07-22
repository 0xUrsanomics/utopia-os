#!/usr/bin/env python3
# skill_activity.py — weekly skill usage + downstream-output score from session logs.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
Skill Activity Tracker. Weekly skill usage + downstream-output score.

Activity-based ranking adapted to a log-based architecture (no live curator agent,
just retrospective surfacing). Curator-ranking idea lifted from NousResearch/hermes-agent (MIT).

Reads:
  logs/session.jsonl. trailing 30d window (configurable via --days)

For each entry: extract `category`, `ts`, and any output paths from fields
ending in `_path` or `_file`. Match category to skill files by name.

Per-skill output:
  count          total log entries in window (proxy for invocation count)
  output_count   subset that produced a file (path/file field present)
  distinct_days  days within window when skill was active
  last_seen      most recent activity date
  downstream     output_count / count. higher = more productive per invocation
  pinned         frontmatter pinned: true (exempt from future auto-prune)

Note on count semantics: session.jsonl uses `category` as the skill identifier
loosely. Some skills self-log (e.g. save, dreaming), others have category names
that don't match skill files (stop-hook, system, signal-harvest). Unmatched
categories surface under by_category for diagnostic.

Outputs:
  outputs/raw/skill-activity/YYYY-MM-DD.json   structured report
  stdout (--summary)                           chat-friendly digest

Config via env:
  AGENT_ROOT              repo root (default: two dirs above this file)
  AGENT_UTC_OFFSET_HOURS  local UTC offset for the window (default: 0 = UTC)

Usage:
  skill_activity.py                             generate JSON, no stdout
  skill_activity.py --summary                   include chat digest
  skill_activity.py --days 7                    7-day window
  skill_activity.py --tg                        one-line chat-formatted digest only
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
LOG_PATH = ROOT / "logs/session.jsonl"
SKILLS_DIRS = [
    ROOT / "skills",
    ROOT / "skills-shared",
    ROOT / "skills" / "personas",
]
OUT_DIR = ROOT / "outputs/raw/skill-activity"

# Local timezone as a fixed UTC offset (hours). Default 0 = UTC.
LOCAL_TZ = timezone(timedelta(hours=float(os.environ.get("AGENT_UTC_OFFSET_HOURS", "0"))))

OUTPUT_PATH_FIELDS = re.compile(r"_(path|file|files|paths)$")
OUTPUT_EVENT_SUFFIX = re.compile(
    r"(extracted|created|written|generated|posted|shipped|approved|drafted|"
    r"saved|updated|logged|opened|closed|sent|delivered|published|completed)$"
)
OUTPUT_EVENT_KEYWORDS = re.compile(
    r"\b(wrote|created|posted|extracted|saved|drafted|generated|shipped|"
    r"published|sent|logged|delivered|completed)\b",
    re.IGNORECASE,
)
COUNT_FIELDS = ("count", "total", "items", "items_count", "n_items")


def load_skills() -> dict[str, dict]:
    """Return {skill_name: {path, pinned, dir_label}}.

    Skill name = file stem (e.g. skills/save.md → "save").
    Pinned = frontmatter `pinned: true`.
    """
    skills: dict[str, dict] = {}
    for d in SKILLS_DIRS:
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            if f.stem.startswith("_"):
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            pinned = bool(re.search(r"^pinned:\s*true\s*$", content, re.MULTILINE))
            label = d.name if d.name != "skills" else "skills"
            if d.name == "personas":
                label = "personas"
            skills[f.stem] = {
                "path": str(f),
                "pinned": pinned,
                "dir_label": label,
            }
    return skills


def parse_window(days: int) -> tuple[datetime, datetime]:
    now = datetime.now(LOCAL_TZ)
    start = now - timedelta(days=days)
    return start, now


def load_entries(start: datetime) -> list[dict]:
    """Read session.jsonl, return entries newer than start."""
    if not LOG_PATH.exists():
        return []
    out = []
    with open(LOG_PATH) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("ts", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(LOCAL_TZ)
            except Exception:
                continue
            if dt < start:
                continue
            entry["_dt"] = dt
            out.append(entry)
    return out


def has_output(entry: dict) -> bool:
    """Heuristic: did this log entry represent productive output?

    Counts as productive if ANY of:
    - explicit *_path / *_file field present
    - `breakdown` dict with non-zero summed values (save's category counts)
    - event/event_type field ends with productive verb (-extracted, -posted, etc.)
    - details/event text contains productive verb keywords
    - count/total/items numeric field > 0
    """
    for k, v in entry.items():
        if OUTPUT_PATH_FIELDS.search(k) and v:
            return True
    breakdown = entry.get("breakdown")
    if isinstance(breakdown, dict):
        try:
            if sum(int(x) for x in breakdown.values() if isinstance(x, (int, float))) > 0:
                return True
        except (TypeError, ValueError):
            pass
    for ev_field in ("event", "event_type"):
        ev = entry.get(ev_field, "")
        if isinstance(ev, str):
            if OUTPUT_EVENT_SUFFIX.search(ev.lower()):
                return True
            if OUTPUT_EVENT_KEYWORDS.search(ev):
                return True
    details = entry.get("details", "")
    if isinstance(details, str) and OUTPUT_EVENT_KEYWORDS.search(details):
        return True
    for cf in COUNT_FIELDS:
        v = entry.get(cf)
        if isinstance(v, (int, float)) and v > 0:
            return True
    return False


def aggregate(entries: list[dict], skills: dict[str, dict]) -> dict:
    """Bucket entries by category. Match category to skill name via direct or
    substring lookup. Unmatched categories surface under by_category for ops."""
    by_cat: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "output_count": 0,
        "days": set(),
        "last_seen": None,
    })
    for e in entries:
        cat = (e.get("category") or "").strip()
        if not cat:
            continue
        b = by_cat[cat]
        b["count"] += 1
        if has_output(e):
            b["output_count"] += 1
        b["days"].add(e["_dt"].date().isoformat())
        ts = e["_dt"].isoformat()
        if not b["last_seen"] or ts > b["last_seen"]:
            b["last_seen"] = ts

    by_skill: dict[str, dict] = {}
    used_categories = set()

    # Direct match: category == skill name
    for cat, b in by_cat.items():
        if cat in skills:
            by_skill[cat] = _summarize(b, skills[cat])
            used_categories.add(cat)

    # Substring match for remaining: skill name appears in category or vice versa
    for cat, b in by_cat.items():
        if cat in used_categories:
            continue
        cat_norm = cat.replace("-", "_").lower()
        for skill_name, meta in skills.items():
            if skill_name in by_skill:
                continue
            sn = skill_name.replace("-", "_").lower()
            if sn == cat_norm or sn in cat_norm or cat_norm in sn:
                by_skill[skill_name] = _summarize(b, meta)
                used_categories.add(cat)
                break

    # Unmatched: surface for diagnostic
    unmatched = {
        c: {
            "count": b["count"],
            "output_count": b["output_count"],
            "distinct_days": len(b["days"]),
            "last_seen": b["last_seen"],
        }
        for c, b in by_cat.items()
        if c not in used_categories
    }

    # Skills with zero matches: include with count=0
    for skill_name, meta in skills.items():
        if skill_name not in by_skill:
            by_skill[skill_name] = _summarize(None, meta)

    return {"by_skill": by_skill, "unmatched_categories": unmatched}


def _summarize(b: dict | None, meta: dict) -> dict:
    if b is None:
        return {
            "count": 0,
            "output_count": 0,
            "distinct_days": 0,
            "last_seen": None,
            "downstream": 0.0,
            "pinned": meta["pinned"],
            "dir": meta["dir_label"],
            "path": meta["path"],
        }
    count = b["count"]
    out_count = b["output_count"]
    return {
        "count": count,
        "output_count": out_count,
        "distinct_days": len(b["days"]),
        "last_seen": b["last_seen"],
        "downstream": round(out_count / count, 3) if count else 0.0,
        "pinned": meta["pinned"],
        "dir": meta["dir_label"],
        "path": meta["path"],
    }


def build_report(days: int) -> dict:
    start, now = parse_window(days)
    skills = load_skills()
    entries = load_entries(start)
    agg = aggregate(entries, skills)

    by_skill = agg["by_skill"]
    used = [k for k, v in by_skill.items() if v["count"] > 0]
    unused = [k for k, v in by_skill.items() if v["count"] == 0]

    ranked_used = sorted(used, key=lambda k: by_skill[k]["count"], reverse=True)
    top_used = [{"skill": k, **by_skill[k]} for k in ranked_used[:10]]

    ranked_productive = sorted(
        [k for k in used if by_skill[k]["count"] >= 3],
        key=lambda k: by_skill[k]["downstream"],
        reverse=True,
    )
    top_productive = [{"skill": k, **by_skill[k]} for k in ranked_productive[:10]]

    least_used = [
        {"skill": k, **by_skill[k]}
        for k in sorted(used, key=lambda k: by_skill[k]["count"])[:10]
    ]

    pinned_count = sum(1 for v in by_skill.values() if v["pinned"])

    return {
        "generated_at": now.isoformat(),
        "window_days": days,
        "window_start": start.isoformat(),
        "skills_total": len(skills),
        "skills_used": len(used),
        "skills_unused": len(unused),
        "skills_pinned": pinned_count,
        "total_entries_in_window": len(entries),
        "by_skill": by_skill,
        "top_used": top_used,
        "top_productive": top_productive,
        "least_used": least_used,
        "unused_skills": unused,
        "unmatched_categories": agg["unmatched_categories"],
    }


def save_report(report: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    out = OUT_DIR / f"{today}.json"
    out.write_text(json.dumps(report, indent=2))
    return out


def format_summary(report: dict) -> str:
    lines = [
        f"📊 Skill activity. last {report['window_days']}d "
        f"({report['skills_used']}/{report['skills_total']} skills used)",
        "",
        "**Top 5 by invocations:**",
    ]
    for r in report["top_used"][:5]:
        prod = f" · {int(r['downstream']*100)}% productive" if r["count"] >= 3 else ""
        pin = " 📌" if r["pinned"] else ""
        lines.append(f"  {r['skill']}{pin} — {r['count']}x{prod}")

    lines.append("")
    lines.append("**Bottom 5 active (used but barely):**")
    for r in report["least_used"][:5]:
        pin = " 📌" if r["pinned"] else ""
        lines.append(f"  {r['skill']}{pin} — {r['count']}x · last {r['last_seen'][:10] if r['last_seen'] else 'n/a'}")

    n_unused = report["skills_unused"]
    if n_unused:
        sample = ", ".join(report["unused_skills"][:8])
        more = f" + {n_unused - 8} more" if n_unused > 8 else ""
        lines.append("")
        lines.append(f"**Unused this window:** {n_unused} skills")
        lines.append(f"  {sample}{more}")

    if report["unmatched_categories"]:
        n_unmatched = len(report["unmatched_categories"])
        top = sorted(
            report["unmatched_categories"].items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )[:5]
        lines.append("")
        lines.append(f"**Unmatched log categories** (no skill name match): {n_unmatched}")
        for cat, info in top:
            lines.append(f"  {cat}: {info['count']}x")

    return "\n".join(lines)


def format_one_line(report: dict) -> str:
    """Single-line digest for inline use in a graph-hygiene chat summary."""
    used = report["skills_used"]
    total = report["skills_total"]
    unused = report["skills_unused"]
    top = report["top_used"][0]["skill"] if report["top_used"] else "?"
    return (
        f"skills: {used}/{total} active over {report['window_days']}d. "
        f"top: {top}. {unused} unused"
    )


def main():
    p = argparse.ArgumentParser(description="Skill activity tracker")
    p.add_argument("--days", type=int, default=30, help="Window in days (default 30)")
    p.add_argument("--summary", action="store_true", help="Print full summary to stdout")
    p.add_argument("--tg", action="store_true", help="Print one-line chat digest only")
    p.add_argument("--no-write", action="store_true", help="Skip writing JSON file")
    args = p.parse_args()

    report = build_report(args.days)

    if not args.no_write:
        out = save_report(report)
        if not args.tg:
            print(f"Report: {out}")

    if args.tg:
        print(format_one_line(report))
    elif args.summary:
        print(format_summary(report))


if __name__ == "__main__":
    main()
