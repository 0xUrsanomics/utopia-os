#!/usr/bin/env python3
# check_dossier_closure.py — gate: is a symptom dossier already CLOSED before re-escalating it?
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""check_dossier_closure.py: decision-cross-check gate for the dreaming/consolidation write-path.

Before the dreaming skill (skills/dreaming.md) appends a "still overdue / not shipped / still owed"
dated entry to a memory/Infra/*.md symptom dossier, it MUST call this to check whether the issue is
already CLOSED, by either (a) the dossier's own `status::` / `closed_by::` frontmatter, or (b) a
closing entry in memory/Decisions.md or memory/Learnings.md. If the issue reads closed AND the
candidate entry carries no NEW failure signature, the skill emits a STATUS-update instead of a
re-escalation. This is the structural forcing-function for the "append-only symptom log silently
diverges from closure state" failure (a meta-memory-review proposal).

FAIL-OPEN by design: any error returns verdict "allow", so a checker bug can never silence memory
consolidation. Over-appending is a tolerable cost; suppressing a real regression is not.

Usage:
  check_dossier_closure.py --dossier memory/Infra/some-recurring-issue.md --topic "some recurring issue" \
      [--signature "new-error-string-if-a-genuinely-new-failure"]

Output (stdout JSON):
  {closed, status, closed_by, decisions_hits, learnings_hits, verdict, reason}
  verdict = "block-reescalation" (closed, no new signature) | "allow"
"""
import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DECISIONS = ROOT / "memory/Decisions.md"
LEARNINGS = ROOT / "memory/Learnings.md"
CLOSE_MARKERS = re.compile(
    r"\b(closed|shipped|resolved|accepted|fixed|done|superseded)\b", re.IGNORECASE
)
CLOSED_FM_VALUES = {"closed", "monitoring", "shipped", "resolved", "done"}
# generic filler tokens that must NOT alone trigger a topic match (else a word like "topic" or
# "issue" false-matches unrelated closed entries and suppresses a legitimate append)
STOPWORDS = {
    "topic", "issue", "issues", "thing", "things", "stuff", "note", "notes", "item", "items",
    "entry", "entries", "this", "that", "then", "than", "with", "from", "into", "about", "been",
    "being", "does", "done", "also", "just", "only", "over", "more", "most", "some", "such",
    "very", "what", "when", "where", "which", "while", "will", "your", "yours", "have", "here",
    "there", "still", "again", "fix", "fixed", "bug", "bugs", "error", "errors",
}


def _frontmatter_status(text):
    """Parse a leading YAML-ish --- ... --- block for status: and closed_by:."""
    status, closed_by = None, None
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                m = re.match(r"\s*status\s*:\s*(.+?)\s*$", line)
                if m:
                    status = m.group(1).strip().lower()
                m2 = re.match(r"\s*closed_by\s*:\s*(.+?)\s*$", line)
                if m2:
                    closed_by = m2.group(1).strip()
    return status, closed_by


def _grep_topic_closure(path, topic):
    """Lines in `path` mentioning a topic token AND sitting within 12 lines of a close marker."""
    hits = []
    if not path.exists():
        return hits
    toks = [t for t in re.split(r"\W+", topic.lower()) if len(t) >= 4 and t not in STOPWORDS]
    if not toks:
        # nothing distinctive left: require the raw topic phrase to appear literally
        toks = [topic.lower().strip()]
    toks = list(dict.fromkeys(toks))  # dedup, preserve order
    need = min(2, len(toks))          # >=2 distinct topic tokens per line (or 1 if only 1 exists)
    lines = path.read_text(errors="replace").splitlines()
    for i, ln in enumerate(lines):
        low = ln.lower()
        if sum(1 for t in toks if t in low) >= need:
            lo, hi = max(0, i - 12), min(len(lines), i + 13)
            window = "\n".join(lines[lo:hi])
            if CLOSE_MARKERS.search(window) or re.search(
                r"status\s*::\s*(closed|shipped|done|resolved|accepted|fixed)", window, re.IGNORECASE
            ):
                hits.append({"line": i + 1, "text": ln.strip()[:160]})
    return hits[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dossier", required=True, help="path to the memory/Infra/*.md dossier")
    ap.add_argument("--topic", required=True, help="topic/keywords to check for closure")
    ap.add_argument("--signature", default="", help="a NEW failure signature, if any, that could re-open")
    args = ap.parse_args()

    out = {
        "closed": False, "status": None, "closed_by": None,
        "decisions_hits": [], "learnings_hits": [], "verdict": "allow", "reason": "",
    }
    try:
        dpath = Path(args.dossier)
        if not dpath.is_absolute():
            dpath = ROOT / args.dossier
        status, closed_by = (None, None)
        if dpath.exists():
            status, closed_by = _frontmatter_status(dpath.read_text(errors="replace"))
        out["status"], out["closed_by"] = status, closed_by

        dh = _grep_topic_closure(DECISIONS, args.topic)
        lh = _grep_topic_closure(LEARNINGS, args.topic)
        out["decisions_hits"], out["learnings_hits"] = dh, lh

        fm_closed = (status in CLOSED_FM_VALUES) or bool(closed_by)
        decision_closed = bool(dh)
        out["closed"] = bool(fm_closed or decision_closed)

        new_sig = args.signature.strip()
        if out["closed"] and not new_sig:
            out["verdict"] = "block-reescalation"
            src = []
            if fm_closed:
                src.append(f"frontmatter status={status} closed_by={closed_by}")
            if decision_closed:
                src.append(f"{len(dh)} closing hit(s) in Decisions.md")
            out["reason"] = (
                "Issue reads CLOSED (" + "; ".join(src) + ") and no new failure signature supplied. "
                "Emit a STATUS-update, not a re-escalation."
            )
        elif out["closed"] and new_sig:
            out["verdict"] = "allow"
            out["reason"] = (
                f"Closed, but a NEW signature was supplied ('{new_sig[:60]}'). A genuinely new "
                "failure mode may re-open the issue. Allow the append, but verify the novelty is real."
            )
        else:
            out["verdict"] = "allow"
            out["reason"] = "No closing decision or status found. Append is fine."
    except Exception as e:
        out["verdict"] = "allow"
        out["reason"] = (
            f"FAIL-OPEN: checker error ({type(e).__name__}: {e}); allowing the append so dreaming "
            "is never blocked by a checker bug."
        )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
