---
name: wave-plan
description: Dependency-wave execution for multi-step tasks. Parse the ask into sub-tasks, build a DAG of dependencies, group into topo-sorted waves, execute each wave as parallel subagents, wait, then fire the next wave. Keeps orchestrator context lean, executors get fresh 200K each. Use for asks with 3+ sub-tasks that have clear parallel/sequential structure.
trigger: wave plan, plan this out, orchestrate, multi-step, parallel build, batch these tasks, wave execution
---

# /wave-plan. Dependency-Wave Execution

Decompose a multi-step ask into a DAG, group independent tasks into parallel "waves", execute wave-by-wave with subagents. The orchestrator (main session) stays lean; executors burn fresh contexts independently.

**Source attribution:** adapted from https://github.com/gsd-build/get-shit-done (MIT). Pattern: dependency-wave execution.

## Tone & Voice

Orchestrator skill. output is a structured plan, not prose. Match the lean register: 1-line per task, no padding. **Hard rule**: the orchestrator stays under 15MB context. If decomposition pushes that bound, prune the plan instead of bloating the orchestrator. Per the delegation discipline.

## Source & Pairs with

- Session-ops delegation threshold + max-depth-2 rule + cache-discipline
- `memory/Infra/agent-protocols-v1.md`. subagent briefing schema v1 (4 dimensions per dispatch)
- Sister skills: `skills/agent-dispatch/SKILL.md` (sends individual subagent briefings within waves), `skills/scope/SKILL.md` (precedes wave-plan when the ask is ambiguous), `skills/subagent-delegation/SKILL.md` (briefing template)
- Your anti-slop constraints, applied in every subagent dispatch

## Output format

The skill produces ONE structured plan artifact:

```markdown
## /wave-plan: <ask>

**Decomposition**: N sub-tasks identified
**DAG depth**: M waves (longest chain)
**Parallelism**: max K tasks in any single wave

### Wave 1 (no deps, run parallel)
- [ ] Task A. {1-line description, subagent_type: explore, est. min: 3}
- [ ] Task B. {1-line, explore, 5}
- [ ] Task C. {1-line, plan, 8}

### Wave 2 (deps: A, B)
- [ ] Task D. {1-line, general-purpose, 10}

### Wave 3 (deps: C, D)
- [ ] Task E. {1-line, code-reviewer, 5}

### Total budget
- wall-clock est: ~25 min
- subagents: 5 total across 3 waves
- orchestrator context overhead: ~3MB

### Execution
After plan approval, dispatch Wave 1 subagents in parallel via a single message with multiple Agent tool uses. Wait for all Wave 1 to return. Then Wave 2. Etc.
```

## When to use

**AUTO-TRIGGER (recommended)** when the ask has all of:
- 3+ distinct sub-tasks
- Clear dependency structure (some tasks independent, others need inputs from earlier ones)
- Each sub-task is substantial enough to justify a subagent (>5 min of focused work OR >3 file reads OR exploratory research)

Example asks that fit:
- "audit these 3 repos and pick the best to adopt" (3 independent audits + 1 decision)
- "build endpoint X, write tests, update docs, open PR" (build → test → (docs ∥ pr))
- "research candidate vendors + draft shortlist + draft outreach" (research parallel → draft serial)

**USER-invoked:**
- `/wave-plan <ask>`
- "plan this out"
- "wave this"
- "multi-step"

**DO NOT USE for:**
- Linear sequential work (task A → task B → task C, nothing parallel): just do it inline
- 2-task asks. An Agent batch in a single message is simpler
- User-interactive work (needs main-context conversation state mid-execution)
- Tasks shorter than a subagent's overhead (~10-30s per spawn)
- CONFIRM-gate work. scope first, then wave-plan the approved scope

## Procedure

### Step 1. Parse the ask into sub-tasks
List every discrete action. Be granular. It's easier to merge later than to split.

Example. "audit 3 repos, pick a winner":
- T1: audit repo A
- T2: audit repo B
- T3: audit repo C
- T4: compare + pick winner

### Step 2. Build the DAG (dependencies)
For each task, list what it depends on (inputs from other tasks):

- T1 (audit A): depends on nothing
- T2 (audit B): depends on nothing
- T3 (audit C): depends on nothing
- T4 (compare): depends on T1, T2, T3

### Step 3. Topo-sort into waves
Group tasks by max dependency depth:

- **Wave 1** (depth 0, independent): [T1, T2, T3]
- **Wave 2** (depth 1, depends on Wave 1): [T4]

### Step 4. Present the plan
Show the user the wave plan before executing. One short block:

```
Wave plan (3 tasks + 1 synthesis):
  Wave 1 (parallel): T1 audit A, T2 audit B, T3 audit C  [~3 min]
  Wave 2 (serial):   T4 compare + pick winner            [~2 min]
Total ETA: ~5 min. Ship? (y/interrupt)
```

Wait briefly for correction. If no interrupt, proceed.

### Step 5. Execute Wave 1
Spawn each Wave-1 task as a subagent. **all in a single message** so they run in parallel. Use the Agent tool with clear isolated prompts per task.

Each subagent prompt should:
- State what it's doing
- Give it whatever context it needs (file paths, URLs, parameters)
- Ask for a bounded output ("report under 300 words")
- Tell it NOT to make external changes (read-only where possible)

### Step 6. Wait for Wave 1 to finish, then Wave 2
The runtime handles the await automatically when multiple Agent calls are issued in one turn. When all Wave-1 results return, spawn Wave 2 with the Wave-1 outputs embedded in the prompts.

Repeat for subsequent waves.

### Step 7. Synthesize + deliver
The main session reads all wave outputs and assembles the final answer. Don't delegate synthesis if the task is decisional (pick a winner, make a recommendation): that's orchestrator work.

### Step 8. Report briefly
One summary message: which waves fired, how long each took, final verdict.

## Anti-patterns

- Spawning Wave 2 before Wave 1 finishes (defeats the dependency structure. just do it sequentially in the first place)
- Using wave-plan for 2 tasks (an Agent batch in one message is simpler, skip the ceremony)
- Delegating a decision to a subagent when synthesis is the actual value
- Sub-tasks too small (<30s each): subagent overhead dominates
- Waves that are all length-1 (just sequential execution dressed up as waves. not actually parallel)
- Missing the "don't modify files" guardrail. subagents should default read-only unless the task is explicitly "build this file"

## Example. a 3-repo audit

**Ask**: "audit github.com/example-org/repo-a, github.com/example-org/repo-b, github.com/example-org/repo-c. anything worth adapting?"

**Without wave-plan**: 1 general-purpose agent runs 3 audits serially → takes ~2 min total. Lost parallel opportunity.

**With wave-plan**:
```
Wave plan:
  Wave 1 (parallel): audit-a, audit-b, audit-c  [~45s each]
  Wave 2 (serial):   synthesize + rank + summary  [~30s]
Total ETA: ~75s. Ship?
```

Wave 1: 3 Agent calls in one message, each with a narrow audit prompt + repo URL + your security rules. Returns 3 per-repo reports in parallel. Wave 2: synthesize in the main context, rank, draft the reply.

**Real saving**: ~1 minute on this specific task. Compound over multi-task days.

## Relationship to other skills

- **`Agent` tool**: wave-plan is a discipline layer on top of Agent. Without wave-plan, you batch parallel calls ad-hoc. With wave-plan, you plan explicitly.
- **`/scope` (skills/scope/SKILL.md)**: if the ask is CONFIRM-gate, /scope first to confirm the scope, THEN wave-plan the approved scope. Don't combine.
- **`Plan` tool (ExitPlanMode)**: Plan is for architectural decisions. how to structure a codebase, which approach to take. wave-plan is execution-layer. once you know what to do, how to parallelize it. Different altitude.
- **`TaskCreate`**: if the user also wants tasks tracked on the task list, create them via TaskCreate in Step 4. Otherwise the wave plan is ephemeral to the turn.

## Triggers NOT to include

Do NOT wave-plan:
- The /save flow itself (single-pass extraction)
- Reading a file
- Editing one line
- Responding to a simple question
- Answering a clarifying question

The overhead kills the value for small tasks.

## Why this skill exists

Concrete repeated case: multi-repo audits and multi-pattern adaptation work that are naturally wave-shaped but get executed sequentially in a single agent or the main context. Wave-plan codifies the DAG → topo → parallel execution so future sessions default to the efficient pattern when the ask justifies it.
