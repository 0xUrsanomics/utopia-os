---
name: reality-review-weekly
description: Layered eval architecture, Layer 4 weekly review. Cron-fired weekly. Queries reality_feedback.sqlite for entries where outcome IS NULL AND timestamp + window has elapsed. Surfaces N due entries via a chat message for operator labeling. Outcomes feed a Layer 1 classifier's training set over months. Decision gate at month 1 - >=50% labeling rate then continue Layer 4; else DROP.
trigger: reality review, reality feedback review, weekly reality review, mark outcome, /reality-review
---

# Reality-feedback weekly review skill

Layer 4's labeling cadence. Once per week, surfaces high-stakes outputs whose outcome window has elapsed but the operator hasn't yet labeled. The discipline is: a 5-minute weekly review session, mark outcomes via reply, accumulate labeled training data over months.

## Conversation context (prior)

**Prior conversation: N/A**. cron-fired, no prior turn context. Operator interaction happens via `/reality-review` replies AFTER the skill surfaces due entries.

## Output format

The skill produces a chat message with bulleted due-entries (one per line: timestamp + skill + output summary + days-elapsed), each with an inline label-reply suggestion. Format:

```
🔍 reality-review (5 due, week of YYYY-MM-DD):

1. {skill} ({N}d ago)
   "{output summary 80 chars}"
   reply: /label 1 win | loss | neutral

2. ...
```

Updates `reality_feedback.sqlite` table `outcomes` only when the operator replies with `/label N <outcome>`. this skill itself does NOT auto-mark anything.

## When to fire

**Auto-fired** by cron task `reality-review-weekly` (weekly). Cron config:
- `cron_expr`: `0 9 * * 0`
- `task_type`: `claude_code`
- `task_config.prompt`: "Run skills/reality-review-weekly/SKILL.md. Surface due entries to the inbox channel."

**Manual invocation**: operator can run `python3 scripts/pipeline/reality_review_weekly.py --digest` anytime to see the pending review queue.

## Weekly flow

1. **Cron fires** weekly
2. **Skill runs** `scripts/pipeline/reality_review_weekly.py --digest`
3. **Digest sent** to the inbox channel with N due entries
4. **Operator labels** each entry via reply: `/reality-mark <id> <outcome> [note]`
5. **Skill updates** ledger, emits telemetry
6. **Stats refresh** weekly stats summary at end

## Outcomes

| outcome | meaning |
|---|---|
| `positive` | Output achieved its predicted/intended effect (goal met, message resonated, recommendation adopted) |
| `negative` | Output failed (goal missed, message flopped, recommendation was wrong) |
| `neutral` | No signal either way (no response, indeterminate) |
| `unknown` | Outcome can't be determined (lost track, no feedback channel) |

## Decision gate (after 1 week of operation)

After 1 week:
- IF labeling rate ≥50% AND ≥5 entries → Layer 4 continues, dataset grows
- IF labeling rate <50% → DROP Layer 4. The architecture reverts to its prior layer + tool-grounded Critic. Long-game requires sustainable discipline; dead weight if not.

The decision gate exists because reality-feedback only has value if the operator actually labels outcomes. Self-grading by the Critic is unreliable (the failure mode this layer was meant to fix).

## Hard rules

1. **One digest per week.** Don't double-fire if cron retries.
2. **Operator labels via reply, never auto-label.** No "infer outcome from later signals" v1; that's a future Layer 4 v2 feature.
3. **No deletion.** Even labeled entries stay in the ledger forever (for classifier v2 training).
4. **Don't surface entries less than 1 day old** even if window elapsed. Outcome signal needs time.
5. **Cap digest at 20 entries** to keep the message readable. Backlog beyond 20 is a red flag for the labeling cadence. flag in the stats footer.

## CLI usage

```bash
# Show due entries (digest format)
python3 scripts/pipeline/reality_review_weekly.py --digest

# Show stats / labeling rate
python3 scripts/pipeline/reality_review_weekly.py --stats

# Mark an entry
python3 scripts/pipeline/reality_review_weekly.py --mark 42 positive --note "goal met"

# JSON for scripting
python3 scripts/pipeline/reality_review_weekly.py --json
```

## Pairs with

- **Auto-create** (`skills/reality-feedback-create/SKILL.md`): writes the entries that this skill reviews.
- **Layer 1 classifier** (`scripts/eval/stake_classifier.py`): outcomes feed v2 classifier training data over months.

## Source archive

Layer 4 weekly-review deliverable of the layered eval architecture. The decision gate at end of the trial window is recorded in the project decision log.
