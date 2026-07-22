---
name: scope
description: Assumption-first scoping. Restate the ask, surface assumptions, ask for corrections before acting. MANDATORY before every CONFIRM-gate action. Also use for complex tasks with 5+ assumptions or irreversible multi-hour work. Adapted from gsd-build/get-shit-done `--analyze` pattern.
trigger: scope, walk through, what's your understanding, restate, before you build, analyze this
---

# /scope. Assumption-First Scoping

Before doing a complex or irreversible task, restate the ask + flag assumptions + ask for corrections. Saves rework.

**Source attribution**: adapted from https://github.com/gsd-build/get-shit-done (MIT). Pattern: `--analyze` mode. The operator confirmed auto-trigger on CONFIRM-gate tasks.

## Tone & Voice

Hard-edged, brief, no hedging in the restate. Read like a co-pilot confirming nav, not a customer-service rep. If an assumption is wrong, lead with the wrong one first. No "I think" / "maybe" / "perhaps". state assumption + reasoning.

## Source & Pairs with

- `memory/Infra/permissions-schema.json`. the full tool→autonomy-mode mapping; consult before deciding if /scope auto-fires
- `memory/Feedback/helicopter-check-before-infra.md`. sibling pattern: 3 ripple-bullets before an infra change. /scope handles WHAT, helicopter-check handles BLAST-RADIUS
- `CLAUDE.md` Autonomy Modes section. defines AUTO / INFORM / CONFIRM / BLOCKED tiers
- Sister skills: `skills/critic.md` (post-output adversarial review), `skills-shared/sycophancy-guard.md` (catches drift in subsequent compliance), `skills/agent-dispatch.md` (subagent briefing follows the same restate-pattern)
- `outputs/raw/agent/` past /scope outputs for calibration

## Example output (CONFIRM-gate restate)

```markdown
## /scope restate

**Ask (as I read it)**: ship the notification engine v2 with reviewer routing + chat notify

**Concrete assumptions** (correct any):
1. "engine v2" = the modified version with weekly settlement (not the v1 monthly)
2. "reviewer routing" = route all notifications through a reviewer's inbox before you see them, not parallel-send
3. "chat notify" = personal chat, not a group topic
4. Trigger threshold stays at the $500 minimum per event
5. Storage: data/events.sqlite (existing), no schema change needed

**Out of scope**:
- Vesting logic (separate skill)
- Multi-party splits (v3 territory)
- Public-facing reporting (never auto-public)

**Blast radius**: 1 new daemon scheduler entry + 1 chat message-template addition + writes to the existing sqlite. Reversible by disabling the scheduler entry.

**Anything wrong?** I'll wait.
```

## When to use

**AUTO-TRIGGER. mandatory, no user invocation needed**:

Any task classified as CONFIRM mode per the CLAUDE.md Autonomy Modes. That includes:
- Writes to your knowledge graph
- Writes to your CRM / spreadsheet
- Sending emails or outbound messages on your behalf (drafts staged, not sent)
- Modifying CLAUDE.md
- Creating / deleting scheduled tasks
- Any action visible to external parties
- Financial transactions
- Deleting files or data permanently
- Changes to daemon / MCP / infrastructure

In these cases, ALWAYS run /scope BEFORE the usual CONFIRM-gate ask. Don't just say "I'll write X to Y. OK?". first restate, flag assumptions, list out-of-scope, THEN ask.

**AUTO-TRIGGER. heuristic**:
- Task has 5+ assumptions (default values, scope boundaries, output format choices)
- Task is multi-hour and irreversible (code refactor, schema migration, mass data update)

**USER-invoked**:
- `/scope`
- "walk me through what you understand first"
- "before you build, restate"
- "analyze this"

**DO NOT trigger for**:
- Simple one-shot operations (read this file, edit this line)
- Quick answers to factual questions
- Tasks where the user explicitly says "just do it" / "go" / "build it" (override)
- AUTO-mode tasks (reading, searching, analyzing, answering)
- Re-runs of a task you've already scoped this session

## Procedure

### Step 1. Restate the ask
1-3 sentences, in your own words, not theirs. Capture the goal + the key constraint. Be concrete.

Example:
> "You want a quotation spreadsheet that matches an existing template layout exactly, using the existing cost breakdown (34% markup, USD 6,500 anchor), shipped as a chat attachment tonight."

### Step 2. List concrete assumptions
Bullet format. Concrete values, not hand-wavy. Include the default values you're picking.

Example:
- Management fee = 34% (matches the prior anchor, editable in F6)
- Payment method = one method only
- Single package tier
- Quotation No = the next in sequence (confirmed)
- Client total ≈ USD 6,507 (preserving the prior anchor)
- Payment split = 50% upfront / 50% post-delivery (from the prior deck)

### Step 3. List what you're NOT doing
Explicit out-of-scope. Prevents scope creep.

Example:
- NOT modifying the internal costing breakdown content
- NOT re-sourcing vendors
- NOT re-running vendor pricing
- NOT touching the shortlist

### Step 3.5. Helicopter view (mandatory, blast radius + ripple)
Zoom out before zooming in. 2-4 bullets, concrete:
- **What this touches downstream**: which other files / skills / crons / pipelines consume or depend on what I'm changing. Name them.
- **Second-order effects**: what behaves differently AFTER this lands that isn't obvious from the diff (a cron that now reads a new field, a hook that fires more, a memory file that grows every session).
- **Reversibility**: exactly how this is undone if wrong (revert one file / disable one scheduler entry / restore from backup). If NOT cleanly reversible, say so loud.
- **Failure mode**: the most likely way this bites later, and what would catch it.

This is the `memory/Feedback/helicopter-check-before-infra.md` pattern promoted from infra-only into every /scope. /scope answers WHAT, the helicopter view answers WHAT ELSE MOVES. A restate without it under-serves the approval: the operator can only meaningfully approve what they can see the blast radius of. If the change genuinely touches nothing downstream (rare), say "blast radius: contained to {file}, nothing consumes it" explicitly. do not omit the section.

### Step 4. Ask for corrections
One line:
> "Correct any of these before I proceed?"

### Step 5. Wait for the user
- "looks good" / "go" / thumbs-up → proceed
- Any correction → update the brief, re-confirm only if the correction is substantive
- Silence after 30 seconds on a clearly scoped ask → proceed on a good-faith interpretation

## Anti-patterns

- Restate too vaguely ("you want a presentation". not specific enough)
- Skip the "NOT doing" list → scope creeps
- Hide assumptions in paragraphs → the user skims, misses the one wrong assumption
- Use scope mode for simple tasks → annoying, slows down
- Act before waiting for correction on CONFIRM-gate tasks → defeats the purpose entirely
- Restate but skip the assumption list → turns /scope into a summary, not a scoping exercise
- Skip the helicopter view (Step 3.5) → approval is uninformed. the user can't approve a blast radius they can't see

## Example. when scope would have saved rework

**A quotation-rebuild case**:
Without /scope, the agent defaulted the management fee to 25% and started building. It had to reverse-engineer to 34% mid-build to match the prior USD 6,500 anchor. Small save because the operator hadn't yet reviewed. but if they had reviewed at 25%, a full rebuild would have been needed.

**Better flow with /scope**:
1. Restate: "rebuild the quotation spreadsheet in the existing template layout, preserve the prior USD 6,500 anchor"
2. Assumptions: "34% management fee to match the prior anchor, single-method payment, single package tier, next-in-sequence quotation #"
3. NOT doing: "re-sourcing vendors, touching the shortlist, changing the cost breakdown content"
4. "Correct before I build?"
5. Operator confirms → zero mid-build reverse-engineering

## Relationship to other skills

- **CLAUDE.md autonomy modes**: /scope is the execution mechanism for CONFIRM-gate tasks. AUTO tasks skip /scope. INFORM tasks usually skip unless ambiguous (5+ assumptions).
- **Plan tool (ExitPlanMode)**: for architectural decisions (multi-file, multi-step design), use Plan. For scoping a single task, use /scope. Plan is broader-altitude.
- **TaskCreate**: /scope is about one task's brief. TaskCreate is about tracking multiple tasks. Both can coexist.
- **Decision presentation**: /scope is NOT a decision-presentation skill. It's a scoping skill. After /scope confirms, if the task also requires choosing between options, then present a trade-off table.

## Why this skill exists

A session exposed the pattern: the agent was defaulting assumptions on CONFIRM-gate tasks without flagging them. A quotation rebuild + a code-adaptation task both had hidden assumptions that would have been easier to correct upfront than mid-flight. `/scope` codifies the "restate before building" discipline so the auto-trigger happens before the agent ever touches a knowledge-graph / CRM / CLAUDE.md write.
