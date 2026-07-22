#!/usr/bin/env python3
# reality_feedback_create.py — Stop-hook that logs high-stake outputs to a reality-feedback ledger.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Reality-feedback auto-create.

Wired into the harness settings.json Stop hook chain AFTER the critic dispatch hook.
Reads the just-emitted stake_classified + critic_verdict events from session.jsonl.
If stake:high (regardless of Critic verdict), appends an entry to the
reality_feedback.sqlite ledger so a future weekly-review can grade the outcome.

Surface inference (best-effort from output content + matched_rules):
- 'tweet' if matched_rules has external:tweet OR doc_type:public-output
- 'partner_outreach' if matched_rules has draft:email OR draft:dm
- 'regulatory_take' if matched_rules has regulator:* (and not tweet)
- 'deal_pitch' if matched_rules has deal:quote OR money:*
- 'event_positioning' if mentions of events / venues / sponsorship
- 'other' fallback

Window defaults:
- tweet: 2 days
- deal_pitch: 14 days
- regulatory_take: 30 days
- partner_outreach: 30 days
- event_positioning: 14 days
- other: 14 days

Failure mode: any error -> exit 0, log to errors.jsonl. Async-style: writes
should be <50ms (single SQLite insert). Hook MUST NOT block session.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
SESSION_LOG = REPO_ROOT / "logs" / "session.jsonl"
ERRORS_LOG = REPO_ROOT / "logs" / "errors.jsonl"
DB_PATH = REPO_ROOT / "memory" / "state" / "reality_feedback.sqlite"

# How far back to walk session.jsonl looking for current-turn events
LOOKBACK_LINES = 100

# Window defaults per surface (days)
SURFACE_WINDOWS = {
    "tweet": 2,
    "deal_pitch": 14,
    "regulatory_take": 30,
    "partner_outreach": 30,
    "event_positioning": 14,
    "other": 14,
}


def _log_error(msg: str, detail: str = "") -> None:
    """Best-effort error logging. Never raises."""
    try:
        ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ERRORS_LOG.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "category": "reality-feedback-create-hook",
                "event": "hook_failure",
                "msg": msg,
                "detail": detail[:500],
            }) + "\n")
    except Exception:
        pass


def _read_current_turn_events() -> tuple[dict | None, dict | None]:
    """Walk session.jsonl backwards. Stop at turn_boundary. Return (classifier, critic)."""
    if not SESSION_LOG.exists():
        return (None, None)
    try:
        with SESSION_LOG.open() as f:
            lines = f.readlines()[-LOOKBACK_LINES:]
    except Exception as e:
        _log_error("read session.jsonl failed", str(e))
        return (None, None)

    classifier = None
    critic = None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        evt_name = event.get("event", "")
        if evt_name == "turn_boundary":
            break
        if evt_name == "stake_classified" and classifier is None:
            classifier = event
        elif evt_name == "critic_verdict" and critic is None:
            critic = event
        # Cooldown: if we hit a reality_entry_created for current turn, skip
        if evt_name == "reality_entry_created":
            return (None, None)
        if classifier and critic:
            break
    return (classifier, critic)


def _infer_surface(matched_rules: list[str], text: str) -> str:
    """Best-effort surface inference from classifier signals + text content.

    Order matters: more specific signals (draft:email, deal:quote) checked BEFORE
    generic doc-type:public-output -> tweet shortcut to avoid mis-classifying emails
    with Subject lines as tweets.
    """
    rules_str = " ".join(matched_rules).lower()

    # Counterparty draft (most specific: email/DM format)
    if "draft:email" in rules_str or "draft:dm" in rules_str:
        # Could be partner_outreach OR deal_pitch (when money/deal:quote also matches)
        if any(p in rules_str for p in ("deal:quote", "money:usd", "money:local")):
            return "deal_pitch"
        return "partner_outreach"
    if "external:counterparty" in rules_str:
        return "partner_outreach"

    # Tweet (explicit format markers from classifier OR thread numbering)
    if "external:tweet" in rules_str:
        return "tweet"
    # Thread numbering pattern in body
    if "**1/" in text or "**2/" in text:
        return "tweet"
    # Public-output detection without other signals -> likely tweet (default external-bound)
    if "doc-type:public-output" in rules_str:
        return "tweet"

    # Deal pitch (money + partner combination, no email format)
    if any(p in rules_str for p in ("deal:quote", "money:usd", "money:local")):
        return "deal_pitch"

    # Event positioning (venue / sponsorship / hangout language)
    text_lower = text.lower()
    if any(p in text_lower for p in ("watch party", "hangout", "venue", "sponsorship", "side event", "event activation")):
        return "event_positioning"

    # Regulatory take (regulator without tweet/email)
    if "regulator:" in rules_str or "regulator " in rules_str:
        return "regulatory_take"

    return "other"


def _extract_summary(text: str, max_chars: int = 300) -> str:
    """Extract a 1-3 sentence summary. Best-effort: first non-empty paragraph or first N chars."""
    if not text:
        return ""
    # Strip leading whitespace + frontmatter
    stripped = text.strip()
    if stripped.startswith("---"):
        # Skip frontmatter
        end = stripped.find("\n---", 3)
        if end > 0:
            stripped = stripped[end + 4 :].strip()
    # Take first paragraph
    para = stripped.split("\n\n", 1)[0].strip()
    if len(para) <= max_chars:
        return para
    return para[: max_chars - 3] + "..."


def _extract_prediction_from_critic(critic: dict | None) -> str | None:
    """Best-effort: Critic verdict's reason field often captures predicted outcomes."""
    if not critic:
        return None
    reason = critic.get("reason", "")
    if not reason:
        return None
    # If Critic verdict is BLOCK or OPERATOR_REVIEW, the reason is a flag, not a prediction
    verdict = critic.get("verdict", "")
    if verdict in ("BLOCK", "OPERATOR_REVIEW"):
        return None
    return reason[:300]


def _extract_last_assistant_text(transcript_path: Path) -> str:
    """Read the .jsonl session transcript and return the last assistant message text."""
    if not transcript_path.exists():
        return ""
    last_text = ""
    try:
        with transcript_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, str):
                    last_text = content
                elif isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                    if parts:
                        last_text = "\n".join(parts)
    except Exception as e:
        _log_error("transcript read failed", str(e))
        return ""
    return last_text


def _emit_event(entry_id: int, surface: str, window_days: int) -> None:
    """Append reality_entry_created event to session.jsonl for telemetry + cooldown."""
    try:
        SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SESSION_LOG.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "category": "reality-feedback",
                "event": "reality_entry_created",
                "entry_id": entry_id,
                "surface": surface,
                "window_days": window_days,
            }) + "\n")
    except Exception:
        pass


def main() -> int:
    try:
        payload_raw = sys.stdin.read()
        if not payload_raw.strip():
            return 0
        payload = json.loads(payload_raw)
    except Exception as e:
        _log_error("payload parse failed", str(e))
        return 0

    transcript_path_str = payload.get("transcript_path", "")
    if not transcript_path_str:
        return 0

    classifier, critic = _read_current_turn_events()
    if classifier is None:
        # No classifier event in current turn OR cooldown active
        return 0

    if classifier.get("stake") != "high":
        return 0

    if not DB_PATH.exists():
        _log_error("ledger DB not initialized", str(DB_PATH))
        return 0

    transcript_path = Path(transcript_path_str)
    text = _extract_last_assistant_text(transcript_path)
    if not text or len(text.strip()) < 50:
        return 0

    matched_rules = classifier.get("matched_rules", [])
    surface = _infer_surface(matched_rules, text)
    window_days = SURFACE_WINDOWS.get(surface, 14)
    summary = _extract_summary(text)
    prediction = _extract_prediction_from_critic(critic)
    classifier_metadata = json.dumps(classifier)
    critic_verdict_json = json.dumps(critic) if critic else None
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        conn = sqlite3.connect(str(DB_PATH))
        # WAL mode set at init time
        conn.execute(
            """
            INSERT INTO entries (
                timestamp, surface, summary, prediction,
                expected_outcome_window_days, outcome, outcome_marked_at,
                classifier_metadata, critic_verdict
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (timestamp, surface, summary, prediction, window_days, classifier_metadata, critic_verdict_json),
        )
        conn.commit()
        entry_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        _emit_event(entry_id, surface, window_days)
    except Exception as e:
        _log_error("ledger insert failed", str(e))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
