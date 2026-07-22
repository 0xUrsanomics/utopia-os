#!/usr/bin/env python3
# reality_review_weekly.py — surface due reality-feedback entries for operator outcome-labeling.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Reality-feedback weekly review.

Cron-fired weekly. Queries reality_feedback.sqlite for entries where
outcome IS NULL AND timestamp + expected_outcome_window_days <= now. Surfaces
N due entries via a chat message for operator labeling.

Operator marks the outcome (positive / negative / neutral / unknown + optional
note). Outcomes feed a future v2 classifier's training data over months.

Output to stdout: human-readable digest + machine-readable JSON for a downstream
chat send. A cron task wraps this in a prompt that pipes output to a chat topic.

Usage:
    python3 reality_review_weekly.py --query
        Show due entries (no side effect).
    python3 reality_review_weekly.py --mark <id> <outcome> [--note "..."]
        Mark a specific entry's outcome.
    python3 reality_review_weekly.py --stats
        Distribution + labeling rate report.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DB_PATH = REPO_ROOT / "memory" / "state" / "reality_feedback.sqlite"

VALID_OUTCOMES = {"positive", "negative", "neutral", "unknown"}


def _open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"ledger DB not found: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def query_due(conn: sqlite3.Connection) -> list[dict]:
    """Return entries due for review: outcome IS NULL AND window has elapsed."""
    now = datetime.now(timezone.utc)
    cur = conn.execute(
        """
        SELECT id, timestamp, surface, summary, prediction,
               expected_outcome_window_days, classifier_metadata, critic_verdict
        FROM entries
        WHERE outcome IS NULL
        ORDER BY timestamp ASC
        """
    )
    due = []
    for row in cur:
        ts = datetime.fromisoformat(row["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        window = row["expected_outcome_window_days"] or 14
        deadline = ts + timedelta(days=window)
        if deadline <= now:
            due.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "surface": row["surface"],
                "summary": row["summary"],
                "prediction": row["prediction"],
                "window_days": window,
                "days_overdue": (now - deadline).days,
            })
    return due


def stats(conn: sqlite3.Connection) -> dict:
    """Return labeling-rate + distribution stats for a decision gate."""
    cur = conn.execute("SELECT outcome, COUNT(*) FROM entries GROUP BY outcome")
    distribution = {row[0] or "NULL": row[1] for row in cur}
    total = sum(distribution.values())
    labeled = total - distribution.get("NULL", 0)
    rate = (labeled / total) if total > 0 else 0.0

    cur = conn.execute("SELECT surface, COUNT(*) FROM entries GROUP BY surface ORDER BY 2 DESC")
    by_surface = {row[0]: row[1] for row in cur}

    cur = conn.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM entries"
    )
    row = cur.fetchone()
    first_ts = row[0]
    last_ts = row[1]

    return {
        "total_entries": total,
        "labeled_entries": labeled,
        "labeling_rate": round(rate, 3),
        "distribution": distribution,
        "by_surface": by_surface,
        "first_entry": first_ts,
        "last_entry": last_ts,
        "decision_gate_hit": rate >= 0.5 if total >= 5 else None,
    }


def mark_outcome(conn: sqlite3.Connection, entry_id: int, outcome: str, note: str | None) -> bool:
    """Mark an entry's outcome. Returns True if updated."""
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"invalid outcome: {outcome}. expected one of {VALID_OUTCOMES}")
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        UPDATE entries
        SET outcome = ?, outcome_marked_at = ?
        WHERE id = ? AND outcome IS NULL
        """,
        (outcome, now, entry_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        return False
    if note:
        # Append note to summary (no separate note column in v1 schema)
        conn.execute(
            """
            UPDATE entries
            SET summary = summary || ' [outcome-note: ' || ? || ']'
            WHERE id = ?
            """,
            (note[:200], entry_id),
        )
        conn.commit()
    return True


def format_digest(due: list[dict], stats_data: dict) -> str:
    """Markdown digest for chat output."""
    if not due:
        return (
            f"📊 *Reality-feedback weekly review*\n\n"
            f"No entries due for review.\n\n"
            f"_Stats: {stats_data['total_entries']} total / "
            f"{stats_data['labeled_entries']} labeled "
            f"({stats_data['labeling_rate']*100:.0f}%)_"
        )

    lines = ["📊 *Reality-feedback weekly review*", "", f"{len(due)} entries due:", ""]
    for e in due[:20]:
        line = (
            f"`#{e['id']}` *{e['surface']}* "
            f"({e['days_overdue']}d overdue): "
            f"{e['summary'][:120]}"
        )
        lines.append(line)
        if e["prediction"]:
            lines.append(f"   _predicted: {e['prediction'][:100]}_")
        lines.append("")

    if len(due) > 20:
        lines.append(f"... +{len(due)-20} more")
        lines.append("")

    lines.extend([
        "",
        "Reply with `/reality-mark <id> <outcome>` to label.",
        "Outcomes: positive | negative | neutral | unknown",
        "",
        f"_Lifetime: {stats_data['total_entries']} entries / "
        f"{stats_data['labeling_rate']*100:.0f}% labeled. "
        f"Decision gate (>=50% at month 1): "
        f"{'PASSING' if stats_data.get('decision_gate_hit') else 'pending'}._",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reality-feedback weekly review")
    parser.add_argument("--query", action="store_true", help="Show due entries")
    parser.add_argument("--stats", action="store_true", help="Show labeling stats")
    parser.add_argument("--mark", nargs=2, metavar=("ID", "OUTCOME"),
                        help="Mark entry id with outcome")
    parser.add_argument("--note", default=None, help="Optional note for --mark")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--digest", action="store_true",
                        help="Chat-formatted digest (default mode for cron)")
    args = parser.parse_args()

    try:
        conn = _open_db()
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    try:
        if args.mark:
            entry_id = int(args.mark[0])
            outcome = args.mark[1]
            ok = mark_outcome(conn, entry_id, outcome, args.note)
            print(json.dumps({"updated": ok, "id": entry_id, "outcome": outcome}))
            return 0 if ok else 1

        due = query_due(conn)
        s = stats(conn)

        if args.json:
            print(json.dumps({"due": due, "stats": s}, indent=2, default=str))
            return 0

        if args.stats:
            print(json.dumps(s, indent=2, default=str))
            return 0

        # Default + --query + --digest: emit chat digest
        print(format_digest(due, s))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
