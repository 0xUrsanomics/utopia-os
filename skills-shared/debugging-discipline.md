---
name: debugging-discipline
description: Evergreen debugging + restart heuristics + cognitive-bias antidotes. Tier-2 (recall-fetched on-demand, NOT always-loaded). Lifted in condensed form from gsd-build/get-shit-done debugger-philosophy + universal-anti-patterns (audit 2026-04-28).
trigger: debug, debugging, stuck, not working, why is this failing, can't figure out, cognitive bias, restart, scope creep
---

# Debugging Discipline

Condensed from GSD v1 (audit 2026-04-28). Tier-2. fetch when actively debugging, not preloaded.

## Conversation context (prior)

**Prior conversation**: skill triggers when actively debugging an issue. The prior turn has: an error message OR an "expected X but got Y" report OR multiple failed fix attempts. Read those, treat user as reporter (knows symptom) not investigator (does not know cause). Don't ask user what's broken. that's the investigator's job.

## Example (cognitive-bias antidote in action)

```
User: "The chat reply tool keeps failing. I've checked the auth token, restarted the daemon, rebuilt the plugin. Nothing works."

Bad response (anchoring trap):
  "Let me check the auth token configuration..." (user already ruled out)

Good response (3-hypothesis generation):
  3 hypotheses BEFORE investigating any:
  H1: plugin orphan procs (PPID=1) holding the connection
  H2: runtime version mismatch
  H3: a getUpdates 409 (multi-poller conflict)

  Cheapest disconfirming test: pgrep for orphan bun procs.
  Run that first. Result will rule out H1 in 5 sec.
```

## Procedure (thinking step by step)

1. **Treat user as reporter**. don't ask "what's causing it"; gather: expected vs actual, error message, when-it-started, what-was-changed-recently
2. **Establish a minimal reproduction first**. a bug you can't trigger on demand can't be confirmed fixed. nail the smallest reliable repro before theorizing. if it only happens intermittently, that IS the first thing to characterize (timing? load? state? order?). no repro = no fix, just guessing.
3. **Generate ≥3 independent hypotheses** before investigating any (anchoring antidote)
4. **For each hypothesis, name the cheapest disconfirming test**. rank by cheap-first. when the recent change set is unknown, bisection (git bisect / binary-search the commits or the toggles) is often the cheapest test of all. halves the search space per step
5. **Run cheapest test first**. eliminate or confirm; update hypothesis set
6. **Track time budget**. every 30 min ask "if I started fresh, would this still be my path?"
7. **At restart-trigger** (2h no progress / 3+ failed fixes / can't explain current behavior / debugging-the-debugger / fix-works-but-don't-know-why): execute restart protocol
8. **When fix lands**: verify ROOT CAUSE not just symptom. "fix works but I don't know why" = luck not fix

## Output format

Skill produces ONE structured diagnostic in chat:

```markdown
## Diagnostic: <issue>

**Reporter says**: <user's symptom report>
**Initial hypotheses (≥3)**:
1. {hypothesis}
2. {hypothesis}
3. {hypothesis}

**Disconfirming test sequence** (cheapest first):
- Test A: {cheap test} → result, eliminates {H#}
- Test B: ...

**Root cause** (after testing): {finding}
**Fix**: {specific change, path:line}
**Why-it-works** (mandatory): {causal explanation, not "it works now"}
**Prevention**: {generalize the lesson. capture as Learning if novel}
```

**Not done until:** the repro now passes, the why-it-works explains the causal chain (not "it stopped happening"), and you can state what WOULD have re-triggered the old bug. Missing any of the three = still open, keep going.

## Core framing

**User = Reporter, Claude = Investigator.**
- User knows: what they expected, what happened, error messages, when it started.
- User does NOT know (don't ask): what's causing it, which file has the problem, what the fix is.
- Ask about experience. Investigate the cause yourself.

**Opaque system? Instrument before guessing.** When you can't see what the code is doing (no logs, async, third-party, intermittent), add observability FIRST: log the inputs/outputs at the boundary, print the actual state, capture the failing case. A guess about a black box is just a more confident guess. Make it visible, then hypothesize.

## Cognitive bias antidotes

| Bias | Trap | Antidote |
|---|---|---|
| Confirmation | Only look for evidence supporting your hypothesis | "What would prove me wrong?". actively seek disconfirming evidence |
| Anchoring | First explanation becomes the anchor | Generate 3+ independent hypotheses before investigating any |
| Availability | Recent bug → assume similar cause | Treat each bug as novel until evidence suggests otherwise |
| Sunk cost | Spent 2hr on path X, keep going despite evidence | Every 30 min: "If I started fresh, is this still the path I'd take?" |

## When to restart (≥1 trigger fires)

1. 2+ hours with no progress
2. 3+ "fixes" that didn't work
3. Can't explain the current behavior
4. Debugging the debugger
5. Fix works but you don't know why ← this isn't fixed, this is luck

**Restart protocol:** close all open files → write down what you know for certain → write down what's ruled out → list NEW hypotheses → restart from evidence gathering.

Walking away from a dead path IS progress, not failure. The sunk cost is already sunk. grinding a broken approach for another hour doesn't unsink it.

## Meta-debugging your own code

When debugging code you wrote, you fight your own mental model. The implementation is a hypothesis, not a fact. Read your own code as if a stranger wrote it. Hardest admission: "I implemented this wrong" (not "requirements were unclear"). Check your ego. the code doesn't care who wrote it, and neither should you.

## Specificity test

Could a different Claude instance execute this task without asking clarifying questions? If not, add more detail. Examples of vague vs just-right:

| Vague | Just right |
|---|---|
| "Add authentication" | "Add JWT auth with refresh rotation, store in httpOnly cookie, 15min access / 7day refresh" |
| "Set up the database" | "Add User + Project models to schema.prisma with UUID ids, email unique constraint, createdAt/updatedAt, run prisma db push" |
| "Handle errors" | "Wrap API calls in try/catch, return {error: string} on 4xx/5xx, show toast via sonner" |

## Scope-reduction prohibited words (in plan/proposal/event-ops drafts)

These words reliably signal hidden scope creep that bites later:
- **"v1"** / "for now" / "static for now". implies v2 will fix it; v2 rarely happens
- **"will be wired later"** / "TODO: integrate with X". wiring is the work
- **"placeholder"** / "stub" → either commit to building it or delete the line
- **"approximate"** / "rough estimate" in budgets → either price it real or flag the unknown
- **"basic"** / "MVP" without scope definition → enumerate exactly what's IN the MVP

When proposal/event-ops drafts ship with these phrases, they create deferred work that gets discovered mid-execution. Delete the phrase OR define what the deferred-state actually is OR remove the feature entirely.

## Cross-references

- Origin: the `gsd-build/get-shit-done` references (debugger-philosophy, universal-anti-patterns, planner-antipatterns) (MIT, doc-mined).
- Sister skills: `skills-shared/anti-ai-slop.md`, `skills-shared/sycophancy-guard.md`, `skills-shared/test-before-bulk.md`
