---
name: autoresearch
description: >
  Autoresearch v2. Meta-Harness-informed self-improving skill loop. Upgrades from
  Karpathy hill-climbing to trace-informed diagnosis: full execution trace access,
  counterfactual diagnosis after regressions, additive-only safety valve, multi-candidate
  filesystem. Runs on any skill that produces scoreable output. Also runs on CLAUDE.md
  routing logic itself. If you can score it, you can autoresearch it.
trigger: autoresearch, improve skill, optimize skill, skill loop, self-improving, score my skill, benchmark skill, eval loop, tune prompt, karpathy loop, meta-harness, optimize routing
---

# Autoresearch v2.0. The Self-Improving Skill Loop

> **Lineage**: Karpathy autoresearch (v1) → Stanford Meta-Harness (Lee et al., 2026)
> **Core insight**: Scores-only hill climbing plateaus. Full execution trace access + counterfactual diagnosis converges faster and finds better optima.

## Source & Pairs with

- **Primary lineage refs**: Karpathy autoresearch loop pattern (2025) + Stanford Meta-Harness paper (Lee et al., 2026)
- `skills/loop-experiment.md`. sister autoresearch pattern lift (from a public autoresearch sandbox pilot)
- A trio audit of public autoresearch repos (gepa / uditgoenka / zkarimi22).
- A content-curator pilot's round-1 results (Critic+Generate-B wins)
- `scripts/skill_failure_tracker.py`. the failure ledger that feeds autoresearch's regression diagnosis
- `memory/Decisions.md`. past autoresearch ship decisions for calibration
- Sister skills: `skills/critic.md` (the validated subagent that pairs well with autoresearch's diagnose step), `skills/save.md` (captures insights from autoresearch runs)

## Example output (autoresearch run on a content Critic prompt)

```markdown
# autoresearch run. content Critic prompt, round 3
date: 2026-05-11
baseline_score: 7.2/10 (avg over 5 historical drafts)
candidate_count: 3
winner: Critic-B (score 8.4/10, +1.2pp lift)

## diagnose (regression on round 2):
- root cause: Critic prompt over-indexed on "sourcing" dimension, lost "precision" calibration
- trace: 3 of 5 drafts cited correct sources but missed numerical precision (e.g. "many users" instead of "23 users")
- counterfactual: would Critic-B's score have held with the round-1 Generate? Yes. additive-only valve held.

## next iter:
- candidate-A: tighten precision-numeric prompt fragment
- candidate-B: add "named-entity verification" sub-rule
- candidate-C: combine A+B with weighting
```

The skill always saves trace + score table to `outputs/raw/agent/autoresearch/<date>-<skill>-round-N.md`.
> **Key result**: Scores-only → 34.6 median. Full traces → 50.0. Summaries don't help. Raw traces do.

## What Changed from v1

| v1 (Karpathy) | v2 (Meta-Harness) |
|---|---|
| Score → mutate → keep/revert | Score → diagnose traces → form hypothesis → targeted mutate |
| One candidate at a time | Filesystem of all candidates: skill source, scores, traces |
| Blind hill-climbing | Counterfactual reasoning over prior failures |
| Skill prompts only | Skill prompts + routing logic + context construction |
| Plateau = stop | Plateau = switch to additive-only mode |
| Changelog as output | Full artifact filesystem as searchable history |

## The Loop

```
1. CHECKLIST  . Write 3-6 binary scoring criteria
2. BASELINE   . Run skill on test prompts, score, CAPTURE TRACES
3. DIAGNOSE   . Read traces of worst-scoring outputs
4. HYPOTHESIZE. Form specific causal hypothesis about failure
5. MUTATE     . Change ONE thing, targeted at hypothesis
6. SCORE      . Run again, score, CAPTURE TRACES
7. DECIDE     . Better? Keep. Worse? Diagnose WHY, then revert.
8. SAFETY     . 3 consecutive regressions → additive-only mode
9. REPEAT     . Until 95%+ score, 3x consecutive
10. PERSIST   . Save artifact filesystem to outputs/raw/agent/
```

## Step 1: Define the Checklist

Rules:
- 3-6 items ONLY. More = noise.
- Each item must be BINARY (yes/no) or SCOREABLE (1-5).
- Each item must be INDEPENDENTLY VERIFIABLE.
- Items must be SPECIFIC to the skill.

Template:
```
| Item | Weight | Score |
|------|--------|-------|
| Matches voice profile | 20% | ?/100 |
| No AI slop detected | 20% | ?/100 |
| Output is actionable | 20% | ?/100 |
| Follows format spec | 15% | ?/100 |
| Appropriate length | 15% | ?/100 |
| Uses available context | 10% | ?/100 |
```

## Step 2: Run Baseline + Capture Traces

**THIS IS THE v2 DIFFERENCE.** Don't just score. capture the full execution trace.

For each test prompt, record:
- iteration number + candidate ID
- input (the test prompt)
- skill instructions (current SKILL.md content)
- full output generated
- per-criterion scores
- failure points (specific lines/sections that failed)
- reasoning trace (any chain-of-thought)

### Trace Storage

```
outputs/raw/agent/autoresearch/{skill_name}/
├── candidates/
│   ├── 000_baseline/
│   │   ├── skill.md              # skill source at this iteration
│   │   ├── scores.json           # per-prompt scores
│   │   └── traces/
│   │       ├── prompt_1.json     # full trace for prompt 1
│   │       └── prompt_2.json
│   ├── 001_{mutation_name}/
│   │   ├── skill.md
│   │   ├── scores.json
│   │   └── traces/
│   └── ...
├── checklist.json
├── changelog.json
└── diagnosis_log.json            # causal reasoning history
```

## Step 3: Diagnose (NEW in v2)

**Before proposing any mutation, read the traces.**

Don't guess what's wrong from a score. Read the actual output, find where it fails, trace the failure back to a specific instruction (or missing instruction) in the skill.

### Diagnosis Protocol

1. **Read worst-scoring traces.** Load full output for the 1-2 worst-scoring prompts.
2. **Identify failure mode.** Missing rule? Conflicting instruction? Vague directive? Wrong example?
3. **Check prior candidates.** Did a previous candidate fix this but break something else? Did a similar fix regress before?
4. **Form specific, testable hypothesis.** Not "make it better". something like:
   - "C2 fails because the skill has no voice example. Adding one should fix C2 without affecting C1/C3."
   - "C5 fails because the banned list is one-language-only. Adding the missing-language terms should fix C5."

### Diagnosis Log Entry

Record: iteration, worst prompt, failure mode, root cause, prior candidates checked, confound check, hypothesis, mutation type, risk assessment.

## Step 4: Hypothesize → Mutate

**Every mutation must be tied to a diagnosis.** No blind changes.

Valid mutation types (now hypothesis-driven):
1. **Add a specific rule**: tied to a diagnosed failure mode
2. **Add a worked example**: when model lacks a reference
3. **Add a banned list**: when specific patterns pass through
4. **Reorder instructions**: when critical rules are buried
5. **Tighten a constraint**: when output overshooting
6. **Add a quality gate**: when missing verification step
7. **Remove a conflicting instruction**: when two rules fight

**STILL: CHANGE ONE THING.**

## Step 5: Score + Decide (Enhanced)

Run SAME test prompts, SAME checklist, capture full traces again.

- Better? KEEP. Log which criteria improved and confirm hypothesis.
- Same? KEEP if Pareto improvement, REVERT otherwise.
- Worse? **Don't just revert. diagnose WHY it regressed.**

### Regression Diagnosis (v2)

When a mutation regresses, compare traces:
1. Which criteria got worse?
2. On which specific prompts?
3. What changed in the output between candidates?
4. Is the regression caused by the intended change, or by a confound?

**This counterfactual reasoning is what makes v2 faster.**

If regression was caused by a confound (mutation touched more than intended), isolate the intended change and retry without the confound.

## Step 6: Additive-Only Safety Valve (NEW in v2)

**After 3 consecutive regressions from modifying existing logic, switch to additive-only mode.**

### Additive-Only Mode Rules

1. Do NOT modify existing instructions
2. Do NOT reorder existing content
3. Do NOT remove anything
4. ONLY append new rules, examples, or quality gates
5. Exit additive-only mode after 2 consecutive improvements

### Why This Works

Modifications risk confounds. Additions are isolated by definition. When search is stuck, reducing mutation space to additions-only prevents regression spirals while still allowing progress.

## Step 7: Termination

- Score >= 95% for 3 CONSECUTIVE iterations (stability)
- OR max iterations reached (default: 5 for scheduled, 15 for manual)
- OR score plateau for 3 consecutive iterations AFTER additive-only attempted

## Step 8: Persist

Save full artifact filesystem to outputs/raw/agent/autoresearch/{skill_name}/
Log to logs/session.jsonl.

## Mode A: Routing Search

**Highest-leverage application: optimize CLAUDE.md routing logic itself.**

Meta-Harness proved that optimizing the orchestrator produces larger gains than optimizing downstream components.

### Searchable in CLAUDE.md

| Component | What to test | Impact |
|---|---|---|
| Routing table keywords | Are messages routed to the right knowledge file? | Routing accuracy |
| Skill routing keywords | Are skill triggers matching real usage? | Skill activation |
| Slash command logic | Do commands behave as specified? | Command reliability |
| Pipeline rules | Does the knowledge pipeline flow correctly? | Data quality |

## Mode B: Conversational (Default)

Claude runs the loop within the conversation:
1. Read target skill's .md file
2. Propose checklist (or ask user)
3. Run test prompts. capture full traces
4. Diagnose worst-scoring traces
5. Form hypothesis and explain causal reasoning
6. Propose mutation tied to hypothesis
7. Re-run, re-score, capture traces
8. If regression: diagnose, check for confounds, explain
9. Present diff and changelog after each iteration
10. User can approve/reject/modify mutations

## Constraints

- Maximum 5 iterations per scheduled run (token conservation), 15 for manual
- One change per iteration (atomic)
- Never change a skill's core purpose, trigger keywords, or frontmatter name
- Preserve frontmatter format
- Log every iteration's score + diagnosis for transparency
- Every mutation must have a diagnosed hypothesis. no blind changes
- After 3 regressions → additive-only mode (automatic)
- Token budget: prefer Glob/Grep checks over full file reads. Lazy-load traces.

## Output

When complete, report:
- Starting score → Final score
- Number of iterations + regressions
- Diagnosis insights (what failure modes were found)
- Mutation types that worked vs didn't
- Changes made (1-line each)
- Final skill file saved

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-03 | Initial: Karpathy hill-climbing loop |
| v2.0 | 2026-04-06 | Meta-Harness upgrade: trace-informed diagnosis, counterfactual reasoning, additive-only safety valve, routing search, artifact filesystem |
