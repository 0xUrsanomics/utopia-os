---
name: loop-experiment
description: Run a Karpathy-loop / autoresearch-style optimization experiment on any task with measurable fitness. Bounds the loop with the stack's discipline (fitness-function gating, branch/worktree isolation, anti-slop, audit logging). Use when running prompt evolution, code optimization, content A/B testing. anywhere with a stable measurable metric and cheap iteration.
trigger: /loop-experiment, autoresearch, prompt evolve, optimize prompt, fitness loop, run loop
---

# /loop-experiment. Disciplined autoresearch-style optimization

Lifts the `setup.md` pattern from `zkarimi22/autoresearch-anything` (public repo; pattern lifted, not installed) and grafts it onto the stack's discipline.

## Phase 0. Fitness-Function Gate (HARD STOP if fail)

Before scaffolding ANY loop experiment, screen the task against 2 conditions. If either fails, refuse to set up the experiment. Push back to the user.

1. **Stable measurable fitness function exists**: a function that maps (input, output) → number. Examples: engagement count, qualified-lead yield, classification accuracy, test pass rate, token count, latency. NOT examples: "the operator's taste", "feels right", "looks better".
2. **Cost-per-iteration cheap enough for 50-700 attempts**: each loop iteration must be runnable in seconds-to-minutes, not hours-to-days. A once-daily content draft is borderline. Most subjective tasks fail this gate.

Example screen:
- ✅ a content pipeline (engagement = likes+replies+bookmarks; iter = 1 draft/day, batch on 30+ days)
- ✅ lead-gen prompts (qualified-lead yield per query; iter = batch query)
- ✅ a sub-agent's scope classifier (HANDLE/ESCALATE accuracy; iter = prompt rerun)
- ✅ skill prompt optimization (`skill_failure_tracker.py` count; iter = tracked over usage)
- ❌ sourcing, intel, subjective outreach drafts (no stable fitness. the operator's taste IS the metric)

If the user requests a loop experiment for a non-fit task: refuse politely, explain the gate, suggest hand-tuning instead.

## Phase 1. Setup

Create the experiment in an isolated working directory. NEVER run loops in the main repo cwd.

### 1a. Pick isolation strategy

| Loop scope | Isolation method |
|---|---|
| Single mutable text file (prompt, doc, config) | git worktree on a fresh `loop/<tag>` branch |
| Multiple files (skill bundle, scripts) | git worktree on `loop/<tag>` branch |
| External script + dataset (no repo files mutated) | plain isolated dir under `sandbox/loop-experiments/<tag>/` |

```bash
# Worktree path (preferred when mutating tracked files)
git worktree add ../repo-loop-<tag> -b loop/<tag>

# Plain dir path (when mutating untracked or external)
mkdir -p sandbox/loop-experiments/<tag>
```

### 1b. Write `setup.md` template

Drop a `setup.md` into the experiment dir. Use this template, fill in EVERY field. Refuse to start if any field is `<TBD>`.

```markdown
# Loop experiment: <tag>

date: <YYYY-MM-DD>
fitness_function: <one-line description, must be measurable>
mutable_path: <single file or glob>
no_touch: <list of paths NEVER to modify; protect main brain, env, secrets>
eval_command: <shell cmd that runs fitness eval; prints score>
score_regex: <regex extracting the numeric score from eval stdout>
secondary_constraint: <optional. e.g. "output stays under 280 chars">
secondary_regex: <optional regex for secondary>
timeout_per_iter_seconds: <hard cap per attempt; default 60>
max_iterations: <50-700 range; refuse <50 or >700>
target_score: <optional early-stop threshold>
extra_rules:
  - NEVER touch files in no_touch list
  - NEVER skip hooks (--no-verify) or escalate (sudo, gh api PUT)
  - NEVER write outside the experiment dir
  - Apply anti-AI-slop rules to ANY generated text (em-dash zero-tolerance, no slop wordlist)
  - Stop on N consecutive non-improving iterations (default N=10)
log_path: logs/loop-experiment-<tag>.jsonl
```

### 1c. Anti-AI-slop preamble (mandatory)

If the loop generates ANY text artifact (prompts, content, docs), the experiment's instruction prompt MUST include:

```
ZERO em dashes. Use periods, commas, parens, line breaks.
No slop wordlist: genuinely / leverage / streamline / unlock / comprehensive / let's dive in / at the end of the day / it's worth noting / dive deep / robust / seamless / cutting-edge / game-changer / state-of-the-art / underscore.
No preamble. No "here's my analysis". Lead with the point. Terse > flowery.
Fragment sentences OK. Casual register OK.
```

Cross-ref: `memory/SOUL.md` voice mandates + `memory/Preferences.md` em-dash-zero-tolerance rule.

### 1d. Sanity-check eval before iterating

Before running the loop, run `eval_command` ONCE on the seed candidate. Verify:
- exit code 0
- score_regex matches stdout
- score is a number
- timeout doesn't fire

If any fail, fix the eval BEFORE iterating. A broken eval makes 100 iterations theatrical.

## Phase 2. Loop

```
for iter in 1..max_iterations:
  1. Read current state of mutable_path
  2. Propose a targeted edit (LLM or scripted mutation)
  3. Apply edit to mutable_path
  4. Run eval_command. Capture stdout, exit code, latency.
  5. Extract score via score_regex. Apply secondary_regex if defined.
  6. If score improves: keep edit. git add + commit on loop/<tag> branch with message "loop iter <N> score <X>"
  7. If score regresses or violates secondary: git reset --hard HEAD. Revert.
  8. Append iter record to log_path: {iter, ts, score, delta, kept|reverted, edit_summary}
  9. Stop if score >= target_score OR N consecutive non-improvements OR max_iterations reached
```

Per-iter log line (jsonl):

```json
{"ts":"<ISO>","tag":"<tag>","iter":<N>,"score":<float>,"delta":<float>,"action":"keep|revert","secondary_pass":true,"edit_summary":"<short>","latency_sec":<float>}
```

## Phase 3. Stop + Report

When the loop terminates (target hit, N non-improvements, or cap):

1. Read all iter records from `log_path`. Build a summary:
   - total iterations run
   - best score + iter number
   - score progression (initial → final)
   - revert rate (% of iters reverted)
   - total wall-clock time
   - estimated API cost if applicable

2. Compare the best candidate vs baseline on a HOLDOUT eval set (separate from training fitness). Verify the gain generalizes.

3. Send a report to the chat channel via the reply tool. Format:

```
🔬 loop-experiment <tag> done

iters: <N>/<max>
best score: <X> (iter <Y>) vs baseline <Z>
holdout: <gain | flat | regression>
revert rate: <pct>%
wall-clock: <duration>
verdict: SHIP | PARK | RETRY

best candidate: <path or excerpt>
log: <log_path>
```

4. If verdict = SHIP: surface to the operator for the CONFIRM gate before merging the loop branch into main. Show the diff.
5. If verdict = PARK: keep the worktree/sandbox for re-run if needed. Document the next-step blocker.
6. If verdict = RETRY: propose an adjusted setup.md (different mutator, looser secondary, more iters) and ask the operator.

## Hard rules

- **NEVER auto-merge** the loop branch to main. A ship verdict requires explicit operator approval (CONFIRM gate).
- **NEVER write outside the experiment dir** during iterations. The no_touch list is enforced by Edit/Write hooks if available, otherwise by inspection.
- **NEVER skip the holdout check**. A loop that overfits training fitness without a holdout is theatrical.
- **NEVER run loops without fitness-function gating**. Refuse the request if Phase 0 fails.
- **NEVER skip the eval-sanity-check** in 1d. Broken eval = wasted iterations.
- **NEVER chain loops** (one loop's output feeding another's input) without showing the chain to the operator first. Compounding hidden state is hard to debug.

## Cost discipline

- Each iteration costs LLM tokens if the mutator is LLM-driven. Budget: $5 max per loop run unless explicitly authorized.
- Use a cheap fast model (e.g. a Haiku-tier model) as the default mutator for cost. Only escalate to a stronger model (e.g. a Sonnet-tier model) if the cheap one fails to produce useful edits.
- Track `latency_sec` and `tokens_used` per iter in the log. Stop early if the cost extrapolation exceeds budget.
- For free-tier compatibility: use a local model or a free-tier hosted model as the mutator if paid API budget is unavailable.

## Examples (when filled in by future runs)

`outputs/loop-experiments/<tag>/`. completed loop reports per experiment.

## Cross-references

- Source pattern: `zkarimi22/autoresearch-anything` (public repo, pattern lifted, not installed).
- Original origin: `karpathy/autoresearch`. single-file edit-loop with fitness eval.
- Anti-AI-slop substrate: `memory/SOUL.md` + `memory/Preferences.md` em-dash-zero-tolerance.
- Subagent verification discipline (port to loops): `skills/subagent-delegation.md` "trust the summary, verify the diff".
- Future upgrade path: `gepa-ai/gepa` (eval-driven prompt optimization, deferred pending API budget).

## When NOT to use this skill

- Subjective tasks where the operator's taste is the metric (proposal drafts, deck reviews, content tone)
- Tasks where one iteration costs hours (training a model, running a full backtest)
- One-shot decisions (which opportunity to take, who to hire)
- Tasks already known to be solved by hand-tuning (don't loop-ify what works)

For those: hand-tune, ask the operator, or use a different skill.
