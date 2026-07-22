#!/usr/bin/env python3
# stake_classifier.py — hardcoded regex/keyword classifier that scores an output draft's stake level.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Stake classifier v1.

Hardcoded regex/keyword classifier on output draft text. Returns a stake-level
verdict (low/medium/high) so downstream layers (Critic dispatch, permission
gating, reality-feedback ledger creation) can route appropriately.

Stake levels:
- high:   regulator named, currency amount, external-publishing destination,
          counterparty-message-draft markers, regulatory-take content, partner-named.
- medium: at least one mid-stake signal but no high-stake match.
- low:    short response, conversational ack, no stake signals.

Usage:
    # CLI: classify text from stdin
    echo "draft about a new licensing rule..." | python3 stake_classifier.py

    # CLI: classify from --text arg
    python3 stake_classifier.py --text "draft proposing a $5M valuation"

    # CLI: emit event to logs/session.jsonl
    echo "..." | python3 stake_classifier.py --emit-event

    # Programmatic
    from stake_classifier import classify
    result = classify("draft about license requirements")
    # -> {"stake": "high", "matched_rules": ["regulator"], ...}

Contract:
- Input:  text (str) + optional tool_calls list of dicts.
- Output: {"stake": "low"|"medium"|"high",
           "matched_rules": [str, ...],
           "confidence": float 0.0-1.0,
           "ts": ISO-8601 UTC,
           "version": "v1.1-doc-type"}

Latency budget: <500ms. Short-circuits cheap obvious-low-stakes first.

The regulator / currency / partner rules below are the CUSTOMIZATION SURFACE:
they ship with neutral examples. Replace them with your own jurisdiction's
regulators, your local currency, and the counterparties you actually work with.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# AGENT_ROOT defaults to the repo root (this file is scripts/eval/stake_classifier.py).
REPO_ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
SESSION_LOG = REPO_ROOT / "logs" / "session.jsonl"

# --- Cheap short-circuit: obvious-low-stakes patterns ---
# These run first before any regex pass to keep latency low on conversational acks.
_LOW_STAKES_ACKS = {
    "noted", "ok", "okay", "thanks", "ty", "got it", "sure", "yes", "no",
    "k", "yeah", "nope", "yep", "yup", "👍", "✅", "🤔", "y", "n",
}

# --- High-stake rules ---
# Match -> stake = high, contributes to confidence.
HIGH_STAKE_RULES: dict[str, re.Pattern[str]] = {
    # Financial / markets regulators (global examples). EXTEND with your own
    # jurisdiction's regulators (central bank, securities + commodities authorities,
    # data-protection body, tax authority): a draft that names a regulator is
    # high-stakes because getting the regulatory claim wrong is expensive.
    "regulator": re.compile(
        r"\b(SEC|FINRA|FCA|MAS|BSP|HKMA|FSA|BaFin|CFTC|"
        r"FATF|FinCEN|OFAC|FSB|IOSCO|Basel|ESMA|MiCA)\b",
    ),
    # Money amounts. USD.
    "money:usd": re.compile(
        r"\$\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:k|K|M|B|million|billion|thousand))?\b",
    ),
    # Local / other currencies (generic example). Replace the codes + symbols with
    # the ones you care about; keep the magnitude-word tail.
    "money:local": re.compile(
        r"\b(?:USD|EUR|GBP|JPY|CNY|SGD|Rp\.?)\s*\d[\d,\.]*"
        r"(?:\s*(?:k|thousand|m|million|b|billion))?\b",
        re.IGNORECASE,
    ),
    # External-publishing intent in draft text
    "external:tweet": re.compile(
        r"\b(?:tweet|thread|x\.com|twitter|post on x|publish to x)\b",
        re.IGNORECASE,
    ),
    "external:kg_intent": re.compile(
        r"\bsave to (?:logseq|obsidian|the graph)\b|\bcreate (?:logseq|graph) page\b|"
        r"\bappend to (?:logseq|the graph)\b|logseq_write|logseq_create|logseq_append",
        re.IGNORECASE,
    ),
    "external:sheets_intent": re.compile(
        r"\bappend to (?:sheet|crm)\b|\bupdate (?:sheet|crm)\b|"
        r"sheets_append_row|sheets_update_cells|\bpipeline (?:tracker|sheet)\b|"
        r"\bcontact (?:database|sheet)\b",
        re.IGNORECASE,
    ),
    "external:counterparty": re.compile(
        r"\bsend (?:email|message|telegram|dm|whatsapp) to\b|"
        r"\bgmail draft\b|\bdraft (?:email|reply) for\b|"
        r"\bsend.*counterparty\b|\bsend.*partner\b",
        re.IGNORECASE,
    ),
    # Counterparty-message draft markers
    "draft:email": re.compile(
        r"^\s*(?:Subject|Re|To):\s+\S",
        re.IGNORECASE | re.MULTILINE,
    ),
    "draft:dm": re.compile(
        r"\b(?:DM draft|TG draft|Telegram draft|message draft for)\b",
        re.IGNORECASE,
    ),
}

# --- Medium-stake rules ---
# Match -> stake = medium (unless any high-stake also matches; high wins).
MEDIUM_STAKE_RULES: dict[str, re.Pattern[str]] = {
    # Regulatory-interpretation language without a specific regulator name
    "regulatory:interp": re.compile(
        r"\b(?:license requirement|compliance gap|regulatory (?:interpretation|risk|filing|reporting)|"
        r"licensing pathway|legal opinion|grandfather clause|safe harbor|sandbox license)\b",
        re.IGNORECASE,
    ),
    # Partner-class language (specific named partners detected via separate rule below)
    "partner:class": re.compile(
        r"\b(?:partnership terms|MOU|memorandum of understanding|contract terms|"
        r"NDA|deal structure|term sheet|LOI|letter of intent)\b",
        re.IGNORECASE,
    ),
    # Pricing/quote/proposal class
    "deal:quote": re.compile(
        r"\b(?:proposal|quote(?:s|ation)?|pricing|retainer|engagement fee|"
        r"advisory fee|kickback)\b",
        re.IGNORECASE,
    ),
    # Public positioning content
    "content:public": re.compile(
        r"\b(?:positioning doc|pitch deck|deck draft|public announcement|press release)\b",
        re.IGNORECASE,
    ),
}

# --- Partner-named rules ---
# EXAMPLE named counterparties. REPLACE with the partners / counterparties YOU
# actually work with (exchanges, protocols, deal counterparties, notable
# individuals). A draft that names a real counterparty is external-facing, so any
# match here escalates to high stake.
KNOWN_PARTNERS: list[str] = [
    "ExampleExchange", "ExampleProtocol", "ExamplePartner", "ExampleCounterparty",
]
PARTNER_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in KNOWN_PARTNERS) + r")\b",
)

# --- Doc-type detection ---
# Internal-meta docs DISCUSS regulators/money/partners but aren't outputs going to
# those surfaces. When detected with confidence, downgrade stake one tier
# (high->medium, medium->low).

# Weighted markers: (regex, weight). Threshold sum >=1.0 -> internal-meta detected.
# Strong markers (1.0) trigger alone. Weak markers (0.4-0.5) need >=2 to trigger.
INTERNAL_META_MARKERS: list[tuple[re.Pattern[str], float]] = [
    # === STRONG (1.0 alone is sufficient) ===
    # Frontmatter type matching internal-only types
    (re.compile(r"^\s*type:\s*(audit|self-audit|system-audit|dream(?:-reflection)?|plan|research|maintenance|seed-batch|cron-output|session-summary|session-log|meeting-prep|reference|spec(?:ification)?|prd)\b", re.MULTILINE | re.IGNORECASE), 1.0),
    (re.compile(r"^\s*pipeline_exempt:\s*project-internal\b", re.MULTILINE), 1.0),
    (re.compile(r"^\s*skip_logseq_sync:\s*true\b", re.MULTILINE | re.IGNORECASE), 1.0),
    # Internal-doc title patterns (specific titles)
    (re.compile(r"^#{1,2}\s+(Graph\s+Hygiene|Weekly\s+Retro|System\s+Audit|Self-?audit|Dream\s+Reflection|Skill\s+Audit|Skill\s+eval|Skill\s+audit\.|Stack\s+Audit)\b", re.MULTILINE | re.IGNORECASE), 1.0),
    # Architecture / PRD / Implementation Plan title (1-line indicator)
    (re.compile(r"^#{1,2}\s+.*\b(Architecture|Implementation\s+Plan|Roll(?:out)?\s+Plan|PRD|Specification|System\s+Architecture|Punch\s+List)\b", re.MULTILINE | re.IGNORECASE), 1.0),
    # Helicopter view / ripples block
    (re.compile(r"^#{1,3}\s*(Helicopter\s+(?:view|check)|Ripples?\s*Effect|Ripple-effect)\b", re.MULTILINE | re.IGNORECASE), 1.0),
    # Weekly retro structure (3-section pattern)
    (re.compile(r"^#{1,3}\s*SHIPPED\s*$.*?^#{1,3}\s*BROKE\s*$", re.MULTILINE | re.DOTALL), 1.0),
    # Acceptance criteria + Decision gates (engineering plan pattern)
    (re.compile(r"^#{1,3}\s*Acceptance\s+criteria\b", re.MULTILINE | re.IGNORECASE), 1.0),
    (re.compile(r"^#{1,3}\s*Decision\s+gates?\b", re.MULTILINE | re.IGNORECASE), 1.0),
    # Call-brief pattern (When/Who/Context block)
    (re.compile(r"\*\*When:\*\*.*\*\*Who:\*\*.*\*\*Context:\*\*", re.DOTALL), 1.0),
    # PRD/spec format (Audience + Goal + Constraint)
    (re.compile(r"\*\*Audience:\*\*.*\*\*(?:Goal|Constraints?|User|Use\s+case):\*\*", re.DOTALL), 1.0),
    # Plan body (Status: Draft / Goal: / Constraint: opening)
    (re.compile(r"^\*\*Status:\*\*\s*Draft\b", re.MULTILINE | re.IGNORECASE), 1.0),

    # === MEDIUM (0.5-0.6 each, 2+ needed) ===
    (re.compile(r"^#{1,3}\s*(Risks?|Mitigations?|Skipped\s+Checks?)\b", re.MULTILINE | re.IGNORECASE), 0.5),
    (re.compile(r"^#{1,3}\s*Slop\s+(?:Gate\s+)?(?:Summary|Scan)\b", re.MULTILINE | re.IGNORECASE), 0.5),
    (re.compile(r"^#{1,3}\s*(Severity\s+counts?|Total\s+pages?|Stale\s+thresholds?)\b", re.MULTILINE | re.IGNORECASE), 0.5),
    (re.compile(r"^#{1,3}\s*(Layer\s+\d+|Phase\s+\d+|Week\s+\d+|Q\d+\b)", re.MULTILINE), 0.5),
    (re.compile(r"^#{1,3}\s*(IMPROVED|PATTERNS|NEXT\s+WEEK|DATA\s+SOURCES)\b", re.MULTILINE), 0.5),
    (re.compile(r"^#{1,3}\s*(Background|Current\s+State|Proposed\s+(?:Additions?|Architecture)|YOUR\s+POSTURE|WHAT\s+TO\s+NEGOTIATE)\b", re.MULTILINE | re.IGNORECASE), 0.5),
    (re.compile(r"\bv\d+\s*[→]\s*v\d+\b|\bv\d+\s+changelog\b|\bchangelog\s+block\b", re.IGNORECASE), 0.5),

    # === WEAK (0.3-0.4, only contribute when stacked) ===
    (re.compile(r"^\*\*Why:\*\*\b", re.MULTILINE), 0.3),
    (re.compile(r"^\*\*How\s+to\s+apply:\*\*\b", re.MULTILINE), 0.3),
    (re.compile(r"^reasoning::\s|^context::\s|^decision::\s|^status::\s", re.MULTILINE), 0.4),
    (re.compile(r"^#{1,3}\s*(Critical|Warning|Info)\b", re.MULTILINE | re.IGNORECASE), 0.3),
    (re.compile(r"\b(?:9|6|5|4|3)\s+ripple-effect\s+(?:bullets?|surfaces?)\b", re.IGNORECASE), 0.4),
]

PUBLIC_OUTPUT_MARKERS: list[re.Pattern[str]] = [
    # Tweet thread numbering
    re.compile(r"^\*\*\d+\s*/\s*\d+\*\*\s*$", re.MULTILINE),
    # Email format (Subject + body)
    re.compile(r"^\s*Subject:\s+\S", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*Dear\s+\w+\s*[,.]\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*(?:Best|Regards|Sincerely|Cheers|Thanks),?\s*\n+\s*\w+\s*$", re.MULTILINE | re.IGNORECASE),
    # Message-draft frame
    re.compile(r"^\*\*(?:Draft|TG\s+draft|Telegram):\*\*", re.MULTILINE | re.IGNORECASE),
]

# Automated-harvester ingest exemption. Scheduled harvester crons write pages that
# MENTION tweet/twitter/regulators/$ as SUBJECT MATTER (automated ingest), not as
# authored public output. The bare-word external:tweet rule + high-stake rules
# false-positive these to stake:high, which a cron model then "clears" with an
# ungrounded self-emitted verdict (the exact self-reflection-without-grounding
# failure the Critic gate exists to block). Self-identifying harvester markers =>
# stake low. Only fires on text that literally names the harvester, which authored
# public content never contains.
_HARVESTER_INGEST_MARKERS = re.compile(
    r"\bsignal-harvester(?:-\w+)?\b|harvested-by::|category[\"'=:\s]+signal-harvester",
    re.IGNORECASE,
)


def detect_doc_type(text: str) -> tuple[str, float]:
    """Detect whether draft is internal-meta vs public-output vs unknown.

    Weighted scoring: each internal marker has a weight (1.0 strong / 0.5 medium /
    0.3-0.4 weak). Sum >=1.0 -> internal-meta detected. Public-output detection
    (tweet/email/dm format) wins regardless to preserve Critic firing on actual
    external-bound content.

    Returns (doc_type, confidence). 0.7+ confidence triggers stake downgrade.
    """
    public_score = sum(1 for p in PUBLIC_OUTPUT_MARKERS if p.search(text))

    # Public output wins on any public marker (high specificity: tweet/email format
    # is unambiguous, while internal markers can co-occur with public content).
    if public_score >= 1:
        return ("public-output", min(0.95, 0.7 + 0.1 * public_score))

    # Internal-meta weighted score
    internal_weight = sum(weight for pattern, weight in INTERNAL_META_MARKERS if pattern.search(text))
    if internal_weight >= 1.0:
        # Confidence: 0.7 base + 0.1 per additional weighted unit
        confidence = min(0.95, 0.7 + 0.1 * (internal_weight - 1.0))
        return ("internal-meta", round(confidence, 2))

    return ("unknown", 0.5)


def _is_obvious_low_stakes(text: str) -> bool:
    """Cheap short-circuit. <30 chars + matches a one-word ack OR pure emoji."""
    stripped = text.strip().lower()
    if not stripped:
        return True
    if len(stripped) < 30:
        # Strip punctuation for comparison
        compact = re.sub(r"[^\w\s]", "", stripped).strip()
        if compact in _LOW_STAKES_ACKS:
            return True
        # Pure emoji-only response
        if re.fullmatch(r"[\W\d_]+", stripped) and len(stripped) <= 5:
            return True
    return False


def classify(text: str, tool_calls: list[dict] | None = None) -> dict[str, Any]:
    """Classify a draft output. Returns stake-level verdict + matched rules."""
    ts = datetime.now(timezone.utc).isoformat()

    # Cheap short-circuit
    if _is_obvious_low_stakes(text):
        return {
            "stake": "low",
            "matched_rules": ["short-circuit:obvious-low-stakes"],
            "confidence": 0.95,
            "doc_type": "ack-or-emoji",
            "ts": ts,
            "version": "v1.1-doc-type",
        }

    # Automated-harvester ingest exemption. Self-identifying harvester output is
    # automated ingest, NOT authored public output. Treat as low-stakes. Prevents the
    # external:tweet false-positive that provokes a cron model's ungrounded self-SHIP.
    if _HARVESTER_INGEST_MARKERS.search(text):
        return {
            "stake": "low",
            "matched_rules": ["exempt:automated-harvester-ingest"],
            "confidence": 0.9,
            "doc_type": "automated-ingest",
            "ts": ts,
            "version": "v1.1-doc-type",
        }

    matched: list[str] = []
    high_hits = 0
    medium_hits = 0

    # High-stake regex pass
    for rule_name, pattern in HIGH_STAKE_RULES.items():
        if pattern.search(text):
            matched.append(rule_name)
            high_hits += 1

    # Partner-named rule (high-stake)
    partner_match = PARTNER_PATTERN.search(text)
    if partner_match:
        matched.append(f"partner:{partner_match.group(1)}")
        high_hits += 1

    # Medium-stake regex pass (only if no high yet, or in addition)
    for rule_name, pattern in MEDIUM_STAKE_RULES.items():
        if pattern.search(text):
            matched.append(rule_name)
            medium_hits += 1

    # Tool-call-based escalation
    if tool_calls:
        for call in tool_calls:
            tool_name = (call or {}).get("name", "")
            if any(s in tool_name for s in (
                "logseq_write", "logseq_create", "logseq_append",
                "sheets_append", "sheets_update", "sheets_create",
                "telegram_send_message", "gmail_create_draft",
                "schedule_create", "memory_store",
            )):
                matched.append(f"tool:{tool_name}")
                high_hits += 1

    # Verdict logic
    if high_hits > 0:
        stake = "high"
        # Confidence scales with hit count, capped at 0.95
        confidence = min(0.95, 0.7 + 0.05 * high_hits + 0.02 * medium_hits)
    elif medium_hits >= 2:
        stake = "medium"
        confidence = min(0.85, 0.6 + 0.05 * medium_hits)
    elif medium_hits == 1:
        stake = "medium"
        confidence = 0.55
    else:
        stake = "low"
        confidence = 0.85  # high confidence-of-low when no signals match

    # Doc-type downgrade: internal-meta docs DISCUSS high-stake topics but aren't
    # outputs going to those surfaces. Downgrade one tier when detected with
    # confidence >=0.7. Public-output detection blocks downgrade (preserves Critic
    # firing on actual external-bound content).
    doc_type, doc_conf = detect_doc_type(text)
    if doc_type == "internal-meta" and doc_conf >= 0.7:
        original_stake = stake
        if stake == "high":
            stake = "medium"
            matched.append(f"doc-type:internal-meta(downgrade:high->medium,conf={doc_conf:.2f})")
        elif stake == "medium":
            stake = "low"
            matched.append(f"doc-type:internal-meta(downgrade:medium->low,conf={doc_conf:.2f})")
        # Confidence reflects the downgrade certainty
        if original_stake != stake:
            confidence = max(confidence * 0.9, 0.6)
    elif doc_type == "public-output":
        # Public-output (tweet thread / email format / DM draft) is external-bound by
        # definition. Audience surface alone is high-stakes enough to warrant Critic
        # verification. There is no "kinda public" -- full upgrade.
        matched.append(f"doc-type:public-output(conf={doc_conf:.2f}, upgrade-to-high)")
        if stake == "low":
            stake = "high"
            confidence = max(confidence, 0.75)
        elif stake == "medium":
            stake = "high"
            confidence = max(confidence, 0.8)

    return {
        "stake": stake,
        "matched_rules": matched,
        "confidence": round(confidence, 3),
        "doc_type": doc_type,
        "ts": ts,
        "version": "v1.1-doc-type",
    }


def emit_event(verdict: dict[str, Any]) -> None:
    """Append stake_classified event to logs/session.jsonl."""
    event = {
        "ts": verdict["ts"],
        "category": "stake-classifier",
        "event": "stake_classified",
        "stake": verdict["stake"],
        "matched_rules": verdict["matched_rules"],
        "confidence": verdict["confidence"],
        "version": verdict["version"],
    }
    SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SESSION_LOG.open("a") as f:
        f.write(json.dumps(event) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stake classifier v1")
    parser.add_argument("--text", help="Text to classify (alternative to stdin)")
    parser.add_argument(
        "--tool-calls",
        help="JSON array of tool calls planned (optional)",
    )
    parser.add_argument(
        "--emit-event",
        action="store_true",
        help="Also append stake_classified event to logs/session.jsonl",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run smoke test against outputs/raw/agent/ historical files",
    )
    args = parser.parse_args()

    if args.smoke_test:
        return run_smoke_test()

    text = args.text if args.text is not None else sys.stdin.read()
    tool_calls = None
    if args.tool_calls:
        try:
            tool_calls = json.loads(args.tool_calls)
        except json.JSONDecodeError:
            print("warning: --tool-calls JSON parse failed", file=sys.stderr)

    verdict = classify(text, tool_calls=tool_calls)
    print(json.dumps(verdict, indent=2))

    if args.emit_event:
        emit_event(verdict)

    return 0


def run_smoke_test() -> int:
    """Smoke test against historical outputs at outputs/raw/agent/."""
    raw_dir = REPO_ROOT / "outputs" / "raw" / "agent"
    reviewed_dir = REPO_ROOT / "outputs" / "reviewed" / "agent"
    if not raw_dir.exists() and not reviewed_dir.exists():
        print("smoke test: outputs dirs not found", file=sys.stderr)
        return 1

    # Pull from both raw + reviewed for breadth (~20 total)
    raw_files = sorted(raw_dir.rglob("*.md")) if raw_dir.exists() else []
    reviewed_files = sorted(reviewed_dir.rglob("*.md")) if reviewed_dir.exists() else []
    # Take all raw (small set) + sample reviewed up to 20 total
    files = raw_files + reviewed_files[: max(0, 20 - len(raw_files))]
    if not files:
        print(f"smoke test: no .md files in {raw_dir} or {reviewed_dir}", file=sys.stderr)
        return 1

    print(f"smoke test: classifying {len(files)} historical outputs")
    print("=" * 80)
    results: list[dict] = []
    for fp in files:
        text = fp.read_text(errors="replace")
        # Trim to first 4000 chars for classification (head matters most)
        verdict = classify(text[:4000])
        results.append({"file": fp.name, **verdict})
        print(f"{verdict['stake']:>6}  conf={verdict['confidence']:>4}  {fp.name}")
        if verdict["matched_rules"]:
            for r in verdict["matched_rules"][:5]:
                print(f"        -> {r}")
    print("=" * 80)
    high = sum(1 for r in results if r["stake"] == "high")
    med = sum(1 for r in results if r["stake"] == "medium")
    low = sum(1 for r in results if r["stake"] == "low")
    print(f"summary: high={high} medium={med} low={low} total={len(results)}")
    print()
    artifact = raw_dir / "stake-classifier-smoke.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(results, indent=2))
    print(f"smoke test artifact saved (review for accuracy): {artifact}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
