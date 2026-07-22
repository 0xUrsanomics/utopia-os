---
name: weekly-retro
description: Weekly retrospective across the entire stack. Reviews what shipped, what broke, what to improve over the past 7 days. Use this skill on a Sunday cron or whenever the user says "retro", "weekly review", "what shipped this week", or wants a system-wide health pulse. Operates on log files + git history + scheduler state. produces a 5-category summary report saved to outputs/raw/agent/ and a concise chat digest.
trigger: retro, retrospective, weekly review, what shipped, week-in-review
---

# Weekly Retro

Structured weekly retrospective. Reflects on system health, output quality, and operational patterns. Runs after graph-hygiene on Sundays.

## Tone & Register

This is operational telemetry, not external content. Match the operator's casual register: short fragments, no corporate hype, no inflated symbolism, no em-dashes. Internal log voice. grep-able, scannable on phone. If the week was quiet, say "quiet week". don't invent ceremony. Frontmatter `type: summary` flows through the operational-telemetry exemption in `/review` so the slop gate is advisory not blocking.

## Source Material (background data)

The retro reads from these source-of-truth files. Pair this skill with its inputs:

| Source | Path | What it tells you |
|---|---|---|
| Git history | your repo | Skill / knowledge / config changes |
| Session log | `logs/session.jsonl` | Skills invoked, personas active, commands fired |
| Error log | `logs/errors.jsonl` | Tool failures, MCP issues, unresolved patterns |
| Output queue | `outputs/raw/` + `outputs/reviewed/` | What was produced, what's pending /review |
| Scheduler state | your scheduler database, `execution_log` table | Cron task success/failure rates |
| Graph hygiene | latest `outputs/raw/agent/*-graph-hygiene.md` if present | knowledge-graph drift / orphan signals |
| Skill activity | `outputs/raw/skill-activity/` recent JSONs | Per-skill usage counts |
| Stake classifier | `logs/session.jsonl` rows where `category=stake-classifier` | High-stake output volume |

Cross-reference with `skills/self-audit/SKILL.md` (nightly, finer-grained). weekly-retro is a weekly aggregate, not a duplicate of self-audit.

## When to Run
- Scheduled: weekly (Sunday 09:00 local, after graph-hygiene at 08:00)
- Manual: `/retro` or "run retro"

## Procedure

### 1. Gather Data (automated)
Pull from the past 7 days:
- `git log` on your repo (what changed in skills, knowledge, config)
- `logs/session.jsonl` (commands used, personas activated, skills invoked)
- `logs/errors.jsonl` (unresolved errors, failure patterns)
- `outputs/raw/` and `outputs/reviewed/` (what was produced, what's still pending review)
- Scheduler execution log via `schedule_execution_log` (task success/failure rates)
- Graph hygiene report from earlier today (if available)

### 2. Analyze (5 categories)

**SHIPPED**: What was built, created, or delivered this week?
- New skills, knowledge files, config changes
- Outputs produced (by persona, by type)
- Items progressed, outreach sent, content published

**BROKE**: What failed or caused friction?
- Error patterns from logs
- Failed scheduled tasks
- Tool/MCP issues
- Anything that needed manual intervention

**IMPROVED**: What got better vs. last week?
- Error count trend (up/down)
- Pipeline throughput (raw → reviewed → brain)
- Response quality observations
- System changes that reduced friction

**PATTERNS**: What recurring behaviors are worth noting?
- Most-used personas and skills
- Time-of-day patterns (when is the operator most active?)
- Common intent categories
- Requests that had no matching skill

**NEXT WEEK**: What should change?
- Skills to create or improve
- Knowledge gaps to fill
- System issues to fix
- Scheduled tasks to add/modify/remove

### 3. Output

Save to `outputs/raw/agent/YYYY-MM-DD-weekly-retro.md` with frontmatter:
```yaml
---
title: Weekly Retro. YYYY-MM-DD
persona: agent
type: summary
status: raw
created: YYYY-MM-DDTHH:MM:SS+00:00
week: YYYY-WNN
---
```

### 4. Chat Summary
Send a concise summary to the chat channel:
- 📦 X items shipped
- 🔴 X errors (Y unresolved)
- 📊 top persona: {name}, top skill: {name}
- 💡 recommendation: {one actionable suggestion}

Keep it under 500 chars. Link to the full report.

## Rules & Constraints (detailed task rules)

1. **Data-grounded**: every metric must trace to a source file. If `logs/session.jsonl` doesn't have the data, the report says "data missing". never fabricate counts.
2. **Adversarial stance**: assume the week had problems until evidence proves it was clean. Don't paper over by counting only ships and ignoring breaks.
3. **One improvement per week**: the NEXT WEEK section caps at 1-2 actionable items. Compounding > overhaul.
4. **No external slop**: this is INTERNAL telemetry. Skip the corporate-therapist tone. "shipped 3, broke 1" beats "successfully delivered 3 important capabilities while encountering 1 minor incident".
5. **Time math is in one timezone**: pick the week boundary (e.g. Sunday 00:00 → Saturday 23:59) in your local timezone. Don't mix UTC + local in the same report.
6. **Operational-telemetry exemption**: output goes through `/review` with `type: summary`, the slop scan is advisory only. Em-dashes won't block. But don't add ceremony. internal grep-able prose is the bar.

## Example output (positive)

```markdown
---
title: Weekly Retro. 2026-05-04 → 2026-05-10
persona: agent
type: summary
status: raw
week: 2026-W19
---

## SHIPPED
- 12 substantive items this week (highest: a Saturday build session, 12 ships in 6h+)
- Top categories: skills/, scripts/, knowledge/
- Key ships: temporal-rerank on the recall index + a chat-reply failover + a batch of repo audits + the /prd skill + a 9-element auditor

## BROKE
- 14 MCP disconnect events (a plugin orphan pattern. fix shipped this week)
- 5x a hook-dispatch timeout (fix applied: 10s→25s)
- 2x a stop-hook reply miss (pre-existing fix awaiting operator review)

## IMPROVED
- Error count: 23 (week prior) → 9 (this week). 61% drop. driver: the reply failover + the timeout fix.
- /review queue depth: 8 raw → 0 raw (Sunday flush)

## PATTERNS
- The pattern-lift discipline fired twice (one SHIP, one PARK). gate working
- Verification-over-recitation fired 3x in 10d. now structural, an early-phase lift shipped

## NEXT WEEK
- 1 item: close out the outstanding follow-up flagged as a repeat failure
```

## Example output (anti-pattern, do NOT do this)

```markdown
## SHIPPED
This week proved to be a transformative period in which the stack
successfully delivered numerous important capabilities. leveraging cutting-edge
patterns to ensure operational excellence across all dimensions...
```

If you find yourself writing "transformative" or "cutting-edge" or "leveraging". stop. Start over.

## What NOT To Do
- Don't make up metrics. If data isn't available, say so.
- Don't sugarcoat. If the week was quiet, say "quiet week."
- Don't propose massive overhauls. One small improvement per week compounds.
