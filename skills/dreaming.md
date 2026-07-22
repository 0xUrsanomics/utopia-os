---
name: dreaming
description: Automated memory consolidation. 3-phase process that promotes high-quality memories and decays stale ones
trigger: dream, consolidate memory, memory cleanup, dreaming
---

# Dreaming. Automated Memory Consolidation

Three-phase background process that turns raw session data into durable long-term knowledge.
Like sleep for AI. consolidates, scores, promotes, and prunes memory.

## When to Run
- Scheduled: daily at 03:00 local
- Manual: `/dream` or "consolidate memory"

## Phase 1. LIGHT (Ingest + Deduplicate)

Read all inputs:
- `logs/session.jsonl`: last 24h of session events
- `memory/*.json`: all persona memory files
- The PROJECT memory/ tree (`memory/`: MEMORY.md, Context/, Learnings.md, user-model.md, etc.) AND the harness auto-memory tree (read-only). NOTE: dreaming WRITES only to the project memory/ tree, never under the harness home dir (see Phase 3 — the cron-tier session hangs on the CLI's home-dir self-edit guard).

Actions:
1. Extract memory candidates from session logs (decisions, preferences, context, learnings)
2. Deduplicate against existing memory entries (fuzzy match on content)
3. Stage unique candidates with metadata: source, timestamp, category
4. Count recall traces. how many times was this info referenced in sessions?

Output: staged candidates list (in-memory, not written yet)

## Phase 2. REM (Pattern Recognition + Reflection)

Analyze staged candidates for:
1. **Thematic clusters**: group related memories (e.g. "the operator prefers X" + "the operator said do Y" = same theme)
2. **Contradictions**: flag memories that conflict with each other (newer wins)
3. **Staleness**: memories referencing dates/states that have passed
4. **Reinforcement**: memories that were recalled/used multiple times get boosted

Generate a reflection summary:
- What themes emerged this week?
- What knowledge decayed (no longer relevant)?
- What gaps exist (frequently asked but not memorized)?

Output: scored candidates + reflection draft

**NEVER write to permanent memory in this phase.**

## Phase 3. DEEP (Score + Promote + Prune)

### Scoring Algorithm
Each memory candidate scored on 6 dimensions:

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Relevance | 0.30 | How useful for future sessions? |
| Frequency | 0.24 | How often was this recalled/referenced? |
| Query Diversity | 0.15 | Was it relevant to multiple different topics? |
| Recency | 0.15 | How recent is the underlying event? |
| Consolidation | 0.10 | Does it connect to existing memory clusters? |
| Conceptual Richness | 0.06 | How much context does it carry? |

### Promotion Gates (ALL must pass)
- minScore: 0.8
- minRecallCount: 3 (referenced at least 3 times)
- minUniqueQueries: 3 (relevant to 3+ different contexts)

### Actions

**Promote**: candidates passing all gates → write to the appropriate file in the PROJECT memory/ tree
- New files: create under the project memory/ tree (e.g. `memory/Context/<subject>.md`) with proper frontmatter. NEVER create or edit anything under the harness home dir — this skill runs in a cron-tier session that hangs on the CLI's home-dir self-edit permission guard.
- Existing files: update content, refresh description

**Re-escalation gate (NON-NEGOTIABLE):** before appending any "still overdue / not shipped / still owed / N weeks late" dated entry to a `memory/Infra/*.md` symptom dossier, you MUST first run the deterministic closure check:
```bash
python3 scripts/check_dossier_closure.py --dossier memory/Infra/<file>.md --topic "<specific multi-word topic being escalated>" [--signature "<a genuinely NEW error string, only if this is a new failure mode>"]
```
- Pass a SPECIFIC multi-word topic (e.g. "reconciler staleness gate", not just "reconciler") so the match is precise.
- verdict `block-reescalation`: the issue reads CLOSED (via the dossier's `status::` frontmatter or a closing entry in Decisions.md). Do NOT append a re-escalation. Either do nothing, or append one STATUS-update line noting it stays closed. Read the returned `reason` + `decisions_hits` and confirm they actually match your escalation. If the closing hits are about a DIFFERENT sub-item, or a genuinely NEW failure signature has appeared, re-run with `--signature "<new signature>"` (returns `allow`) and proceed.
- verdict `allow`: proceed with the append.
- FAIL-OPEN by design (any error returns `allow`), so it can never block consolidation. This gate replaces the failed "remember to grep Decisions.md" prose lesson with a script you must run. It exists because closed issues kept getting re-escalated across multiple dreaming cycles.

**Merge**: overlapping memories → combine into one richer entry

**Prune**: existing memories that score below 0.3 on relevance + recency
- Don't delete. move to `memory/.archive/pruned-YYYY-MM-DD.json`
- Recoverable if needed

**Decay**: reduce confidence score on memories not accessed in 30+ days
- Not deletion, just de-prioritization

### Output

Write results:
1. Update `memory/MEMORY.md` (the PROJECT index) if entries added/removed
2. Save reflection summary to `outputs/raw/agent/YYYY-MM-DD-dream.md`
3. Log to session.jsonl: promoted N, merged M, pruned K, decayed J

## Dream State File
Save machine state to `memory/.dreams/dream-YYYY-MM-DD.json`:
```json
{
  "date": "2026-04-08",
  "phase_completed": "deep",
  "candidates_staged": 12,
  "promoted": 3,
  "merged": 2,
  "pruned": 1,
  "decayed": 4,
  "top_themes": ["project pipeline", "system architecture"],
  "gaps_identified": ["no memory of counterpart meeting preferences"],
  "reflection": "..."
}
```

## Phase 3B. USER MODEL (Predictions)

After the DEEP phase, generate or update `memory/user-model.md` with behavioral predictions:

This is NOT a fact file (that's Preferences.md). This is a PREDICTION file. what the operator is LIKELY to do based on observed patterns.

Structure:
```markdown
# User Model. Behavioral Predictions
*Auto-generated by dreaming. Updated nightly.*

## Time Patterns
- [when do they usually wake up?]
- [when are they most productive?]
- [when do they procrastinate?]

## Task Patterns
- [what do they avoid?]
- [what do they jump on immediately?]
- [what triggers deep work vs shallow work?]

## Communication Patterns
- [when do they code-switch languages?]
- [what tone signals serious vs joking?]
- [what phrases mean "I'm done" vs "keep going"?]

## Persona Predictions
- [which persona fits which time/context?]
- [when to suggest switching?]

## Follow-up Behavior
- [how do they handle follow-ups?]
- [what makes them procrastinate on outreach?]
- [negotiation style patterns]
```

Update predictions based on observed patterns from session logs. Mark confidence level (high/medium/low) per prediction. Remove predictions that proved wrong.

## Phase 3C. AUTO SKILL EXTRACTION

Review the last 24h of session activity. If any complex multi-step task was completed successfully (3+ tool calls, novel workflow, not an existing skill), extract a skill template:

1. Identify the workflow pattern
2. Create a draft skill at `outputs/raw/agent/auto-skill-{slug}.md`
3. Include: trigger phrases, procedure steps, tools used, output format
4. Tag as `status: raw` for /review

Maximum 1 auto-generated skill per dream cycle. Quality over quantity.

## Rules
- Run AFTER self-audit and BEFORE the morning briefing
- Never promote memories about sensitive/private content flagged by the user
- Never promote temporary task state (that's for tasks, not memory)
- Maximum 5 promotions per run (prevent memory flood)
- If MEMORY.md exceeds 200 lines after promotion, trigger aggressive pruning
- Persona memory files follow their own prune rules (defined in the persona skill file)
