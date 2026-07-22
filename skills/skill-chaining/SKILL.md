---
name: skill-chaining
description: Execute multiple skills in sequence as a pipeline. context passes between each step
trigger: chain, pipeline, run sequence, multi-step, then
---

# Skill Chaining. Multi-Skill Pipelines

Chain multiple skills into a single pipeline. Each skill's output becomes the next skill's input. Replaces manual step-by-step execution.

## Tone & Voice

Orchestrator meta-skill. output is execution status + step reports, not prose. **Hard rule**: max 5 skills per chain (complexity ceiling). **Hard rule**: never chain skills that modify the same file (race condition). **Hard rule**: NEVER auto-chain without a user request. always explicit invocation.

## Source & Pairs with

- Sister skills: `skills/wave-plan/SKILL.md` (DAG-based parallel-wave dispatch, different shape. chain is sequential, wave is parallel), `skills/agent-dispatch/SKILL.md` (single-subagent dispatch primitive), `skills/scope/SKILL.md` (precedes complex chains)
- `skills/_index.md`. the skill registry validates each chain step exists before execution
- `outputs/raw/`. chain output destination (all step results bundled)
- your anti-slop constraints, carried through every step

## Conversation context (prior)

**Prior conversation**: the user invoked a chain via natural language ("harvest data then draft content") OR explicit syntax (`/chain skill-A → skill-B`). Read the request, parse the chain. If it's ambiguous which skill matches a step, ask ONE clarifying question. Don't auto-pick a wrong skill mid-chain.

## Conversation context within a chain

The `accumulated_output` field in the context object preserves the conversation thread between steps. Each skill in the chain receives all prior step outputs + the original user input. Order matters: step N reads step N-1 output as input.

## Output format

Final chain report:

```markdown
## Chain Complete: <chain-name>

**Steps**: 3 / 3 succeeded
**Duration**: ~12 min total

### Step 1. data-harvester
- input: cron-triggered hourly window
- output: 5 items captured
- status: ✅

### Step 2. item-scorer (run per-item)
- input: 5 items from step 1
- output: 2 HIGH / 2 MODERATE / 1 LOW
- status: ✅

### Step 3. draft-writer (conditional: HIGH only)
- input: 2 HIGH-scored items
- output: 2 drafts at outputs/raw/drafts/
- status: ✅

**Next**: 2 drafts queued for /review (the slop gate)
```

If a step fails: the chain stops, reports which step + why, and no further steps execute.

## Syntax

Natural language triggers:
- "harvest data then draft content then queue for review"
- "profile the entity then score the signal then create a knowledge-graph page"
- "check my calendar then prep the meeting then draft talking points"
- "audit the graph then run the retro then generate the briefing"

Or explicit:
- "/chain item-scorer → draft-writer → review-gate"
- "/chain research → item-scorer → graph-create"

## Chain Execution

### Context Object
A context object passes between skills in the chain:

```json
{
  "chain_id": "uuid",
  "step": 1,
  "total_steps": 3,
  "input": {},
  "accumulated_output": [],
  "current_skill": "item-scorer",
  "next_skill": "draft-writer",
  "status": "running"
}
```

Each skill receives the previous skill's output via `accumulated_output` and adds its own result.

### Execution Modes

**Sequential** (default): skill A → wait → skill B → wait → skill C
- Use when each step depends on the previous output
- Example: score a signal → draft based on the score → review the draft

**Parallel**: skill A + skill B simultaneously → skill C uses both outputs
- Use when two steps are independent but a third needs both
- Example: (fetch calendar + fetch email) → compile the briefing from both

**Conditional**: skill A → if condition → skill B, else → skill C
- Use when the next step depends on the result
- Example: score a signal → if HIGH, draft → if LOW, just log it

### How to Chain

When detecting a chain request:

1. **Parse the chain**: identify skills in order from the natural language request
2. **Validate**: check each skill exists in skills/ or skills-shared/
3. **Initialize context**: create the context object
4. **Execute step by step**:
   - Run skill 1, capture output
   - Add output to accumulated_output
   - Pass context to skill 2
   - Repeat until the chain completes
5. **Report**: summarize what each step produced

### Chain Rules

- Maximum 5 skills per chain (prevents runaway chains)
- Each skill must complete before the next starts (sequential mode)
- If any skill fails, stop the chain and report which step failed + why
- User can interrupt mid-chain (chain pauses, asks whether to continue or abort)
- Chain output saved to outputs/raw/ with all step results
- Never chain skills that modify the same file (race condition)

### Pre-Built Chains

Common workflows that can be triggered by name:

| Chain Name | Steps | Trigger |
|-----------|-------|---------|
| signal-to-content | item-scorer → draft-writer → review-gate | "turn this signal into content" |
| entity-research | research → profile → meeting-prepper | "research this entity" |
| outreach-prep | meeting-prepper → outreach-drafter → review-gate | "prep this outreach" |
| morning-flow | briefing-generator → review-gate | "morning flow" |
| graph-maintenance | graph-hygiene → weekly-retro | "check the graph" |

### Example Chain Execution

User: "harvest the data, score it, and draft outputs for any HIGH items"

Chain detected: data-harvester → item-scorer → draft-writer (conditional: only HIGH)

Step 1: Run the harvester
→ Output: 5 items found

Step 2: Score each item
→ Output: 2 HIGH, 2 MODERATE, 1 LOW

Step 3: Draft for HIGH items only (conditional)
→ Output: 2 drafts saved to outputs/raw/

Report: "Chain complete: 5 items → 2 HIGH → 2 drafts ready for /review"

## What NOT To Do
- Don't chain more than 5 skills (complexity explodes)
- Don't chain skills that contradict each other (e.g. don't chain two opposite rewrite passes on the same content)
- Don't auto-chain without a user request. always explicit
- Don't skip /review at the end of content-producing chains
