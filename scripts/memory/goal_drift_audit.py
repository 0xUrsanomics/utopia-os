#!/usr/bin/env python3
# goal_drift_audit.py — weekly audit of active goals for drift / overdue / review-due.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
goal_drift_audit.py. Weekly audit of memory/state/active_goals.json.

Surfaces goals that haven't been touched in `drift_threshold_days` (default 14),
goals past their `due` date, and goals past their `review_after` date.

Wired into:
  - a weekly cron (e.g. Sunday morning) via a shell task
  - manual: `python3 scripts/memory/goal_drift_audit.py [--json] [--silent-clean]`

Findings written to:
  - outputs/raw/agent/{date}-goal-drift.md (markdown digest)
  - logs/session.jsonl (one line per run with counts)
  - operator notification (only if findings)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
STATE = REPO / "memory/state/active_goals.json"
LOG = REPO / "logs/session.jsonl"
RAW_DIR = REPO / "outputs/raw/agent"


@dataclass
class Finding:
    goal_id: str
    title: str
    kind: str  # drift | overdue | review-due
    detail: str


def _now() -> datetime:
    return datetime.now().astimezone()


def _today_str() -> str:
    return _now().strftime("%Y-%m-%d")


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def audit() -> tuple[list[Finding], dict]:
    if not STATE.exists():
        return [], {"error": f"missing {STATE}"}

    data = json.loads(STATE.read_text())
    caps = data.get("_caps", {})
    drift_days = int(caps.get("drift_threshold_days", 14))
    goals = data.get("goals", [])
    active = [g for g in goals if g.get("status") == "active"]

    now = _now()
    findings: list[Finding] = []

    for g in active:
        gid = g.get("id", "?")
        title = g.get("title", "?")[:60]

        # drift: zero last_advanced in drift_days
        last_adv = _parse_iso(g.get("last_advanced") or g.get("created", ""))
        if last_adv:
            days_idle = (now - last_adv).days
            if days_idle >= drift_days:
                findings.append(Finding(gid, title, "drift", f"{days_idle}d idle (threshold {drift_days}d)"))

        # overdue: due < today
        due = _parse_iso(g.get("due") or "")
        if due and due.date() < now.date():
            days_over = (now.date() - due.date()).days
            findings.append(Finding(gid, title, "overdue", f"due {g.get('due')} ({days_over}d ago)"))

        # review-due: review_after < today
        rev = _parse_iso(g.get("review_after") or "")
        if rev and rev.date() < now.date():
            days_over = (now.date() - rev.date()).days
            findings.append(Finding(gid, title, "review-due", f"review {g.get('review_after')} ({days_over}d ago)"))

    summary = {
        "active_count": len(active),
        "total_goals": len(goals),
        "drift_count": sum(1 for f in findings if f.kind == "drift"),
        "overdue_count": sum(1 for f in findings if f.kind == "overdue"),
        "review_due_count": sum(1 for f in findings if f.kind == "review-due"),
        "findings_total": len(findings),
    }
    return findings, summary


def render_markdown(findings: list[Finding], summary: dict) -> str:
    lines = []
    lines.append("---")
    lines.append(f"date: {_today_str()}")
    lines.append("type: goal-drift-audit")
    lines.append("persona: agent")
    lines.append("status: approved-internal")
    lines.append("skip_logseq_sync: true")
    lines.append("review_notes: operational-telemetry exemption. weekly drift audit cron output.")
    lines.append("---")
    lines.append("")
    lines.append(f"# Goal Drift Audit. {_today_str()}")
    lines.append("")
    lines.append(
        f"active: {summary.get('active_count', 0)} | "
        f"drift: {summary.get('drift_count', 0)} | "
        f"overdue: {summary.get('overdue_count', 0)} | "
        f"review-due: {summary.get('review_due_count', 0)}"
    )
    lines.append("")
    if not findings:
        lines.append("All active goals advanced within threshold and within deadlines. No action.")
        return "\n".join(lines) + "\n"

    by_kind: dict[str, list[Finding]] = {}
    for f in findings:
        by_kind.setdefault(f.kind, []).append(f)

    for kind in ("overdue", "drift", "review-due"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        lines.append(f"## {kind.upper()}")
        lines.append("")
        for f in items:
            lines.append(f"- `{f.goal_id}` {f.title} . {f.detail}")
        lines.append("")

    lines.append("## Action options")
    lines.append("")
    lines.append("- /goals touch <id> if goal is still active and was advanced (not in this audit's view)")
    lines.append("- /goals pause <id> to take it off the active set without abandoning")
    lines.append("- /goals done <id> if success criteria met")
    lines.append("- /goals abandon <id> if no longer pursuing")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_log(summary: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": _now().isoformat(),
        "level": "info" if summary.get("findings_total", 0) == 0 else "warn",
        "persona": "agent",
        "category": "goal-drift-audit",
        "event": (
            "clean" if summary.get("findings_total", 0) == 0
            else f"{summary['findings_total']} findings"
        ),
        **summary,
    }
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit JSON instead of human-readable summary")
    ap.add_argument("--silent-clean", action="store_true", help="exit 0 with no output if no findings")
    ap.add_argument("--report", type=Path, help="write the markdown report to this path (default: outputs/raw/agent/{date}-goal-drift.md)")
    args = ap.parse_args()

    findings, summary = audit()

    # always log
    write_log(summary)

    if "error" in summary:
        print(f"error: {summary['error']}", file=sys.stderr)
        return 2

    # write markdown report unconditionally (cron surfaces even on clean weeks)
    report_path = args.report or (RAW_DIR / f"{_today_str()}-goal-drift.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(findings, summary))

    if args.json:
        print(json.dumps({"summary": summary, "findings": [f.__dict__ for f in findings]}, indent=2))
    elif args.silent_clean and summary.get("findings_total", 0) == 0:
        return 0
    else:
        print(render_markdown(findings, summary))

    return 0 if summary.get("findings_total", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
