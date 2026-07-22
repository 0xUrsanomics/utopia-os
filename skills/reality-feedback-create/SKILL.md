---
name: reality-feedback-create
description: Layered eval architecture, Layer 4 auto-create. Fires from the Stop hook chain after critic_dispatch. Appends an entry to the reality_feedback.sqlite ledger when the classifier verdict is high-stakes, with surface inference + outcome window + Critic metadata. Operator labels the outcome later via weekly review (skills/reality-review-weekly/SKILL.md). Outcomes feed a Layer 1 v2 classifier's training set over months.
trigger: reality feedback create, log this for review, mark for outcome tracking
---

# Reality-feedback auto-create skill

Layer 4 of the layered eval architecture. Auto-creates ledger entries for high-stakes outputs so their outcome can be graded later. The discipline is: at output time, capture the prediction. At outcome time (days/weeks later), grade actual vs predicted. Over months, the deltas feed a Layer 1 v2 classifier's training set.

## Example output (ledger entry shape)

```json
{
  "id": "rfb-2026-05-11-001",
  "ts_created": "2026-05-11T05:40:00+00:00",
  "session_id": "s_2026-05-11-build",
  "stake_class": "high",
  "stake_signals": ["draft", "outbound", "high-value-proposal"],
  "predicted_surface": "counter-offer should test a higher retainer + shorter term",
  "outcome_window_days": 30,
  "outcome_due": "2026-06-10",
  "outcome": null,
  "critic_metadata": {"score": 8.4, "passes": 3, "concerns": ["could be premature pattern-lock at n=2"]}
}
```

## Conversation context (prior)

**Auto-fired** by the Stop hook chain. runs AFTER classifier_dispatch + critic_dispatch + (optionally) save_handler. The prior conversation is the just-completed turn whose output triggered the high-stake classification. The script walks `logs/session.jsonl` back to find the most-recent `stake_classified` event with `class=high` + the matching tool-output that produced it.

## Output format

Returns ONE row appended to `data/reality_feedback.sqlite` table `outcomes`:

| column | type | description |
|---|---|---|
| id | TEXT PK | `rfb-YYYY-MM-DD-NNN` |
| ts_created | ISO8601 | when created |
| session_id | TEXT | source session identifier |
| stake_class | TEXT | always "high" for entries created by this skill |
| stake_signals | JSON | array of classifier signals |
| predicted_surface | TEXT | prediction this skill captured |
| outcome_window_days | INT | when grading should happen |
| outcome_due | DATE | computed: ts_created + window |
| outcome | TEXT (nullable) | filled in later via `skills/reality-review-weekly/SKILL.md` |
| critic_metadata | JSON | from Critic dispatch (score / passes / concerns) |

## When to fire

**Auto-fired** by `scripts/pipeline/reality_feedback_create.py` from the Stop hook chain (after critic_dispatch). Conditions: stake_classified event in the current turn = high. Cooldown via session.jsonl walk-back: if a `reality_entry_created` event already exists for the current turn, skip.

**Manual invocation** (operator override): use this skill when the classifier missed a high-stakes output but you want it tracked. Run the script with `--manual` flag (TODO: add CLI manual mode).

## Ledger schema

`memory/state/reality_feedback.sqlite`, table `entries`:

| col | type | meaning |
|---|---|---|
| id | INT PK | auto-increment |
| timestamp | TEXT | ISO8601 of output emission |
| surface | TEXT | post / proposal / recommendation / outreach / positioning / other |
| summary | TEXT | 1-3 sentence summary of output |
| prediction | TEXT | nullable: extracted from Critic verdict reason if SHIP/SHIP_WITH_FIXES |
| expected_outcome_window_days | INT | when to surface for review |
| outcome | TEXT | positive / negative / neutral / unknown / NULL (= unmarked) |
| outcome_marked_at | TEXT | ISO8601 of operator marking |
| classifier_metadata | TEXT | JSON of stake_classified event |
| critic_verdict | TEXT | JSON of critic_verdict event (nullable) |

Indexes: `(outcome, timestamp)` for the weekly-review query, `(surface)` for per-surface analysis.

## Surface inference (best-effort)

| Signal | Surface | Window (d) |
|---|---|---|
| matched_rules has external:post OR doc-type:public-output OR `**1/N**` thread numbering | post | 2 |
| matched_rules has draft:email / draft:dm / external:counterparty | outreach | 30 |
| matched_rules has deal:quote / money:amount | proposal | 14 |
| text mentions event / venue / sponsorship / activation | positioning | 14 |
| matched_rules has a domain-authority signal (and not a post) | recommendation | 30 |
| fallback | other | 14 |

A public post wins over a proposal when both signals are present (posts are public-bound, a proposal is an internal draft → different review urgency).

## Hard rules

1. **Async / non-blocking.** Single SQLite insert. Latency budget <50ms. WAL mode handles concurrent writes from a rapid Stop chain.
2. **Cooldown via session.jsonl walk-back.** One entry per turn. If `reality_entry_created` is already in the current turn, skip.
3. **Fail-open silently.** Any error → exit 0, log to errors.jsonl. The hook MUST NOT block the session.
4. **Window defaults are starting points.** Per-surface fine-tuning is a Layer 4 v2 deliverable; v1 ships fixed defaults.
5. **No outcome at create time.** Outcome is operator-marked via the weekly review skill, NOT inferred. Auto-grading is a separate (future) skill.

## Pairs with

- **Layer 1 classifier** (`scripts/eval/stake_classifier.py`): fires this skill when stake:high.
- **Layer 2 Critic** (`skills/critic/SKILL.md`): provides verdict metadata stored in the ledger; SHIP_WITH_FIXES outcomes flagged for special review.
- **Weekly review** (`skills/reality-review-weekly/SKILL.md`): consumes ledger entries where outcome IS NULL and timestamp + window has elapsed.

## Source archive

Layer 4 auto-create deliverable of the layered eval architecture. Pairs with the weekly review skill that grades what this one captures.
