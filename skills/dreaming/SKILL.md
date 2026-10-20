---
name: dreaming
description: Automated memory consolidation. 3-phase process that promotes high-quality memories and decays stale ones
trigger: dream, consolidate memory, memory cleanup, dreaming
---

# Dreaming. Automated Memory Consolidation

Three-phase background process that turns raw session data into durable long-term knowledge.
Like sleep for AI. consolidates, scores, promotes, and prunes memory.

Default outcome is promote nothing. The gates exist to keep memory small, not to be satisfied. A cycle that promotes 0 and prunes 2 did its job.

## When to Run
- Scheduled: daily at 03:00 local
- Manual: `/dream` or "consolidate memory"

## Phase 1. LIGHT (Ingest + Deduplicate)

Read all inputs:
- `logs/session.jsonl`: last 24h of session events
- `memory/*.json`: all persona memory files
- The PROJECT memory/ tree (`memory/`: MEMORY.md, Context/, Learnings.md, user-model.md, etc.) AND the harness auto-memory tree (read-only). NOTE: dreaming WRITES only to the project memory/ tree, never under the harness home dir (see Phase 3, the cron-tier session hangs on the CLI's home-dir self-edit guard).

Actions:
1. Extract memory candidates from session logs (decisions, preferences, context, learnings)
2. Deduplicate against existing memory entries (fuzzy match on content)
3. Stage unique candidates with metadata: source, timestamp, category
4. Count recall traces. Do not estimate. Derive `recall_count` and `unique_topics` from disk:
```bash
# recall_count: mentions of the candidate's key term across the last 30d of session logs
grep -ic "<key term>" logs/session.jsonl
# unique_topics: distinct categories the term appeared under
grep -i "<key term>" logs/session.jsonl | grep -o '"category": *"[^"]*"' | sort -u | wc -l
```
If `logs/session.jsonl` is missing or the term returns 0, set both to 0 and let the gate reject it. Never substitute a guessed count.

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

### Dimension rubric (score each 0.0 to 1.0, then weight and sum)

Do not eyeball these. Pick the nearest anchor. A candidate with no evidence for a dimension scores 0.0 on it, not 0.5.

| Dimension | 0.0 | 0.5 | 1.0 |
|-----------|-----|-----|-----|
| Relevance | one-off task state, already-resolved ticket | useful if the same subject comes back | changes how a future session acts on a recurring subject |
| Frequency | recall_count 0-1 | recall_count 2-4 | recall_count 5+ |
| Query Diversity | surfaced under 1 topic | 2 topics | 3+ unrelated topics |
| Recency | underlying event 90d+ old | 8-90d | within 7d |
| Consolidation | orphan, links to nothing | shares a subject with 1 existing entry | extends a named existing cluster in MEMORY.md |
| Conceptual Richness | bare assertion, no why | claim plus one reason | claim, why, and how to apply |

Worked example: "the operator wants cron heartbeats on both start and finish" = Relevance 1.0, Frequency 1.0 (recall_count 7), Diversity 1.0, Recency 0.5 (21d), Consolidation 1.0, Richness 0.5. Weighted: 0.30+0.24+0.15+0.075+0.10+0.03 = 0.895. Passes minScore.

### Promotion Gates (ALL must pass)
- minScore: 0.8
- minRecallCount: 3 (referenced at least 3 times)
- minUniqueQueries: 3 (relevant to 3+ different contexts)

### Actions

**Promote**: candidates passing all gates → write to the appropriate file in the PROJECT memory/ tree
- New files: create under the project memory/ tree (e.g. `memory/Context/<subject>.md`) with proper frontmatter. NEVER create or edit anything under the harness home dir: this skill runs in a cron-tier session that hangs on the CLI's home-dir self-edit permission guard.
- Existing files: update content, refresh description

**Re-escalation gate (NON-NEGOTIABLE):** before appending any "still overdue / not shipped / still owed / N weeks late" dated entry to a `memory/Infra/*.md` symptom dossier, you MUST first run the deterministic closure check:
```bash
python3 scripts/pipeline/check_dossier_closure.py --dossier memory/Infra/<file>.md --topic "<specific multi-word topic being escalated>" [--signature "<a genuinely NEW error string, only if this is a new failure mode>"]
```
- Pass a SPECIFIC multi-word topic (e.g. "reconciler staleness gate", not just "reconciler") so the match is precise.
- verdict `block-reescalation`: the issue reads CLOSED (via the dossier's `status::` frontmatter or a closing entry in Decisions.md). Do NOT append a re-escalation. Either do nothing, or append one STATUS-update line noting it stays closed. Read the returned `reason` + `decisions_hits` and confirm they actually match your escalation. If the closing hits are about a DIFFERENT sub-item, or a genuinely NEW failure signature has appeared, re-run with `--signature "<new signature>"` (returns `allow`) and proceed.
- verdict `allow`: proceed with the append.
- FAIL-OPEN by design (any error returns `allow`), so it can never block consolidation. This gate replaces the failed "remember to grep Decisions.md" prose lesson with a script you must run. It exists because closed issues kept getting re-escalated across multiple dreaming cycles.
- A fix-owed that keeps recurring while OPEN is the other half of the trap. If the same unbuilt fix has already been appended 3 or more times, do NOT append another "still owed" line. Move it into whatever decision ledger your review cycle reads (build, decline or reassign), so a person has to decide. An N+1th text entry while the fix stays unbuilt is silent divergence, not progress.

**Zero-promotion path (expected, not a failure):** most cycles promote nothing. If no candidate clears all three gates, write the dream state file with `promoted: 0` and a one-line `reflection` naming the closest candidate and which gate it missed. Still run Prune and Decay. Do NOT lower a gate, do NOT promote the best of a bad batch, and do NOT report the cycle as errored. Same rule if `logs/session.jsonl` is empty or absent: log `candidates_staged: 0`, skip Phases 2 to 3C, exit clean.

**Merge**: overlapping memories → combine into one richer entry

**Prune**: existing memories that score below 0.3 on relevance + recency
- Don't delete. move to `memory/.archive/pruned-YYYY-MM-DD.json`
- Recoverable if needed

**Decay**: apply a forgetting curve, not a 30-day cliff (MemoryBank, arXiv 2305.10250, uses the Ebbinghaus curve for this)
- `confidence = confidence * 0.5 ** (days_since_access / 45)`, floor 0.05
- Recompute on every cycle. Any access resets `days_since_access` to 0
- Not deletion, just de-prioritization. A decayed entry stays readable
- **Input:** run `python3 scripts/memory/memory_decay.py --json memory/.dreams/decay-YYYY-MM-DD.json`. It computes the curve per memory FILE from the last access, which is the later of a recall-log hit or the file's mtime. Report the `decayed` count from it (weight < 0.25) instead of 0, and pick re-check or distil candidates from its most-decayed list. Report only: it never edits or moves a file. Caveat: files that arrived in one bulk copy share one mtime, so for those the edit date is a weak signal; prefer recall hits.

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
2. Create a draft skill at `outputs/raw/agent/auto-skill-{slug}.md`, then verify the file exists on disk (Read or `ls` it back) before recording `auto_skills_drafted: 1` anywhere. A narrated write that was never invoked is not proof of success. If verification fails, report 0 drafted, not the intended file. (Failure mode this blocks: consecutive cycles recorded a drafted filename and rationale in the dream state file and the index, and the file never existed.)
3. Include: trigger phrases, procedure steps, tools used, output format
4. Tag as `status: raw` for /review

Maximum 1 auto-generated skill per dream cycle. Quality over quantity.

**Skill shape (arXiv 2608.20274, "Break It Down, Pass It On"):** (1) SUB-PROCEDURE level, not whole-session. Emit a small skill scoped to ONE reusable sub-procedure that could recur in a different task, and drop steps that only made sense for this session. Whole-session skills scored below the no-memory baseline in the paper. (2) TEXT workflow note, not a code monolith. Numbered prose steps plus caveats; code only as an example inside a step. Phrase the description like a future request's task, since the router matches on it.

## Rules
- Run AFTER self-audit and BEFORE the morning briefing
- Never promote memories about sensitive/private content flagged by the user
- Never promote temporary task state (that's for tasks, not memory)
- Maximum 5 promotions per run (prevent memory flood)
- If MEMORY.md exceeds 200 lines after promotion, prune to 180: archive lowest `relevance x recency` first, oldest as tie-break, until the line count drops. Archive, never delete. Report the count pruned in the dream state file
- When a dreaming bullet corrects or replaces an earlier entry, indent `  supersedes:: <file> <date> "<old heading or bullet start>"` under it (validity convention in `skills/save/SKILL.md` Step 3.1). Do NOT edit the old entry's `status::` yourself: that stays a proposal for the operator. Run `python3 scripts/memory/memory_supersession_check.py` and put any new contradicted-unmarked flags in the dream state file.
- Persona memory files follow their own prune rules (defined in the persona skill file)
