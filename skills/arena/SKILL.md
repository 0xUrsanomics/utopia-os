---
name: arena
description: "Run N parallel candidates at the same high-stakes drafting or design task, with a rubric fixed BEFORE fan-out and a judge from a different model, then pick a base, graft the best 1-2 parts of the losers in by hand, and verify. Use for /arena, 'arena this', or an artifact where one attempt would lock in the wrong shape (a longform section, a CV or cover letter for a top role, a pitch narrative, the design of a new skill or script). Not for quick posts, lookups or anything whose shape is obvious."
trigger: /arena, arena this, throw it in the arena, 3 drafts, multiple drafts, parallel drafts, best of n
provenance: "Adapted from pstack arena (github.com/cursor/plugins, MIT, Lauren Tan). Model routing replaced with generic seats; this repo's ship gates added to Verify."
---

# Arena

One draft plus a critic finds flaws in the shape you already picked. Arena tests the shape itself: N independent attempts, one rubric, a judge from another model, then a synthesis.

## When to use (and not)

Use when the artifact is high-stakes AND has more than one plausible shape:
- a longform section or full piece before the owner reads it
- a CV or cover letter for a top-tier role
- a pitch or proposal narrative, a deck storyline
- the design of a new skill, script or pipeline stage

Do NOT use for short posts or replies, quick answers, factual lookups, or anything where the shape is obvious. Cost is about 4 to 5 subagent runs; one arena replaces a draft-critic-redraft cycle, not a single draft.

## Phase A: Frame (main session)

The prompt is the contract. Every candidate gets the SAME prompt.

1. **Artifact.** One sentence: what each candidate produces, length, register.
2. **Grounding pack.** Paste ONLY the facts the task needs (interview quotes, numbers with basis and date, constraints). Candidates are fresh agents, not forks; they see nothing else. Include the hard constraints every time: no em or en dashes, no invented metrics, the owner's quoted lines stay verbatim, the "never public" list for this piece, and the anti-slop rules (`skills-shared/anti-ai-slop/SKILL.md`).
3. **Rubric.** 3 to 6 gradeable criteria for THIS task, written before fan-out. Candidates never see it. Example for longform: thesis stated in the first 100 words; every number carries its basis; the owner's quotes are load-bearing, not decoration; one concrete test the reader can run; reads like the owner (voice profile).
4. **Seats.** Default 3 candidates:
   - Seat 1: `general-purpose`, the main model
   - Seat 2: `general-purpose`, a second model (a different tier or family)
   - Seat 3: `general-purpose`, the main model again, same prompt (generation variance)
   Use more seats only when the arena is choosing between design directions.
5. **Output paths.** Each candidate writes its own file: `<run-folder>/arena/candidate-<n>.md`. Never a shared file.

## Phase B: Fan out

Spawn all N in ONE message, in the background. Each prompt = task + grounding pack + its own output path + "after the artifact, add a 3-line RATIONALE: the alternatives you considered and what you rejected."

A candidate that produces nothing: continue with N-1 and note the dropout. Re-spawn only if fewer than 2 remain.

Depth rule: candidates are depth 1. They must not spawn subagents.

## Phase C: Cross-judge

After ALL candidates finish (not before), spawn ONE read-only judge on a different model family from the candidates, as a fresh agent (see `skills/advisor/SKILL.md` for why a fork is wrong). If that model is unavailable, use any other second model you have; a model known to invent citations may score, but must not fact-check.

Judge brief: the rubric plus the candidates labeled A, B, C by file path (no seat or model names). Ask for a 1-5 score per criterion per candidate, a recommended base, and the single best part of each non-base candidate. Do not tell the judge which one you lean toward.

## Phase D: Pick a base (main session)

Read every candidate end to end. Score each against the rubric yourself, criterion by criterion, before reading the judge's scores. Then compare.
- Judge agrees on the base: pick it.
- Judge disagrees: read both rationales. The disagreement means either a bias or an ambiguous rubric. Say which in the run note.
- Tie: pick the one that is easier to extend without breaking the constraints (smaller, cleaner structure).

## Phase E: Graft

Walk each losing candidate once more for what is worth porting: usually 1 or 2 things each (a line, a structure, an example), not most of it. Rewrite each graft into the base by hand so it reads as one voice. Never paste paragraphs mechanically.

- Candidates converge on one shape: strong agreement. Note it, ship the consensus shape, skip grafting.
- Candidates diverge wildly: Phase A was under-specified. Fix the frame and re-run. Never average divergent drafts.

## Phase F: Verify

Treat the synthesized artifact like any other output. Run the normal ship gates for its type (`docs/content-gates.md`):
- `python3 scripts/pipeline/external_slop_gate.py --file <draft>` (add `--cv` for CVs and cover letters); zero dashes
- owner-voiced pieces: the voice gate
- CVs: a one-page render check
- the critic pass the pipeline already requires (`skills/critic/SKILL.md`)

Every factual claim in the result carries its level from `knowledge/evidence-ladder.md`; anything only at L1 gets sourced or cut.

If verification finds a problem the arena missed: either Phase A was wrong (reframe, re-run) or a candidate had it right and the graft missed it (back to Phase E). Do not patch over it.

## Run note

Append to the run folder (or `outputs/raw/<persona>/YYYY-MM-DD-arena-<slug>.md`): rubric, seats, dropouts, both scorecards, base picked and why, grafts taken, gate results.
