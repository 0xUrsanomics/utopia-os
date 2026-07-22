---
name: plan-ceo-review
description: Product-strategist mode review on a draft plan. 4 scope-modes (EXPAND / SELECTIVE / HOLD / REDUCE) chosen explicitly upfront and committed-to throughout. Catches scope drift, surfaces 10x opportunities, hardens rigor against silent failures. Includes Landscape Check (search-before-building) + Taste Calibration (codebase reference patterns) + 5 Prime Directives.
trigger: ceo review, think bigger, expand scope, strategy review, rethink this, is this ambitious enough, plan review, product strategy
provenance: adapted from gstack (garrytan/gstack, MIT). expanded after the operator flagged loss of substantive heuristics.
references: knowledge/gstack-cross-cutting-patterns.md
---

# Plan CEO Review. Product-Strategist Mode

## Why this exists

A plan can be technically rigorous AND strategically wrong. Engineering review catches "will this work?" CEO review catches "is this the 10-star product?" / "is this the right thing to build?" / "did we silently scope this down because shipping is cheaper than thinking?"

Complements `decision-council` (anonymized peer review). that one finds blind spots in reasoning. This one challenges scope + ambition + strategic framing.

## When to fire

- Pre-build planning when scope is fuzzy or feels small
- Mid-build when shipping the smaller version became the default ("let's punt the hard part")
- Pre-ship review on a proposal, deck, or strategy artifact
- When the operator says "is this ambitious enough" or "rethink this"

Skip for tactical execution (bug fixes, scheduler adjustments, small refactors). The CEO doesn't review your typo fixes.

## Pre-reading (consult once before Step 0)

Read §1 of `knowledge/gstack-cross-cutting-patterns.md` (the decision-brief question format). The 4-mode framework requires structured questions when surfacing scope changes. don't freestyle.

## Procedure

### Step 0. Mode selection (CRITICAL, commit-to-it)

Before ANY review, ask which mode this is. The mode controls posture for the entire review. **Once selected, do not silently drift.**

Ask via a structured user question:

**A) SCOPE EXPANSION**. "We're building a cathedral. Envision the platonic ideal. Push scope UP. Ask 'what would make this 10x better for 2x the effort?'"
- Posture: dreaming-with-rigor. You have permission to recommend enthusiastically.
- Each expansion is the user's opt-in via an explicit question. Never silently add scope.
- Question to ask repeatedly: "what would make this 10x better for 2x the effort?"
- Anti-drift: if EXPANSION is selected and you later find yourself arguing for less work, that's drift. stop and check.

**B) SELECTIVE EXPANSION**. "Hold current scope as baseline + cherry-pick expansions individually."
- Posture: rigorous reviewer with taste.
- Each expansion presented as a separate question. Accepted ones join scope. Rejected ones explicitly go to "NOT in scope."
- Neutral recommendation posture. present effort + risk, let the user decide.

**C) HOLD SCOPE**. "Scope is locked. Make it bulletproof."
- Posture: rigorous reviewer. Catch every failure mode, test every edge case.
- Do NOT silently reduce OR expand.
- Output is hardening + observability + edge cases, not new features.

**D) SCOPE REDUCTION**. "Find the minimum viable version that achieves the core outcome. Cut everything else. Be ruthless."
- Posture: surgeon.
- Anti-drift: don't sneak scope back in mid-review.

### Step 1. Read the artifact + grounding

- Read the plan/draft in full
- Read `CLAUDE.md` for project conventions
- Read the relevant `memory/projects/<slug>.md` if scoped
- `git log --oneline -10` for recent direction
- `recall("<core topic>")` against the recall index for prior decisions / similar work

### Step 2. Taste Calibration (EXPANSION + SELECTIVE EXPANSION only)

Identify 2-3 well-designed reference patterns in the existing codebase / prior outputs that are particularly well-crafted. Note them as style references for THIS context. Also note 1-2 anti-patterns to avoid repeating.

Report findings before proceeding to Step 3:
> *"Reference patterns identified: [X] (this works because Y), [Z] (this works because W). Anti-patterns to avoid: [A] (broken because B)."*

Skip for HOLD / REDUCTION modes.

### Step 3. Landscape Check (EXPANSION + SELECTIVE EXPANSION only)

Search-before-building gate. Use a web-search tool:
- "[product category or comparable] landscape 2026"
- "[key mechanism] alternatives existing"
- domain comparables if scoped to a specific market (map the incumbents' patterns)
- For a given product category: existing solutions to the same problem

If something obvious already exists and we're proposing to rebuild it, surface that finding as the FIRST decision. before any Prime Directive pass. Lift-vs-build is a strategic call (echoes the `repo-audit` 4-option triage: doc-mine / clone-audit / install-direct / park).

For HOLD / REDUCTION modes, skip. landscape is already accepted.

### Step 4. The 5 Prime Directives (apply across all modes)

For each, walk the plan and flag specific issues with line refs or section names. Don't generic-mention them.

1. **Zero silent failures.** Every failure mode must be visible. to the system, to the operator. If a failure can happen silently (a cron didn't fire, an MCP disconnected, a harvester silently produced nothing, the chat plugin flapped), that's a critical defect. Where does the plan say "log this when it happens"?

2. **Every error has a name.** Don't say "handle errors." Name the specific exception class, what triggers it, what catches it, what the user sees, whether it's logged. Catch-all error handling (`except Exception:` / `catch Throwable`) is a code smell. call it out.

3. **Data flows have shadow paths.** Every data flow has 4 paths: happy / null input / empty input / upstream error. Trace all 4 for every new flow.
   - Example: a content curator must handle: inputs=null / inputs=empty / harvester-errored.
   - Example: a daily synthesis job must handle: scratch-file missing / scratch-file stale / 0 inputs today.

4. **Interactions have edge cases.** Every user-visible action has: double-click / navigate-away-mid-action / slow connection / stale state / back button / chat-disconnect-mid-reply / process-respawn. Map them.

5. **Observability is scope, not afterthought.** Logs, alerts, runbooks, scheduler heartbeats are first-class deliverables. Adding them post-ship is the failure mode. Where is the new functionality's heartbeat? Where does it announce a startup ping? What is the silent-failure detection?

### Step 5. Completeness Principle. Boil the Lake

(Adapted from gstack's "Completeness is cheap" principle, aligned with the CLAUDE.md "Boil the Ocean" rule.)

When evaluating "approach A (full, ~150 LOC) vs approach B (90%, ~80 LOC)":
- AI coding compresses implementation time 10-100x
- The 70-line delta costs SECONDS with an AI coding agent
- "Ship the shortcut" is legacy thinking from when human engineering time was the bottleneck
- DEFAULT: prefer the full A unless REDUCTION mode is explicitly selected

Apply this whenever the plan describes a partial-coverage approach.

### Step 6. Mode-specific output

**EXPANSION mode:** propose 3-5 scope-up ideas, each with an effort estimate + value delta. Each one is a separate user question. The user cherry-picks or rejects.

**SELECTIVE EXPANSION mode:** rigorous review of existing scope (Prime Directives) + 2-3 expansion opportunities surfaced individually. The user picks.

**HOLD SCOPE mode:** straight-through rigor pass. 5 Prime Directives × every section. Output a punch list of "this section is at 6/10 because X, would be 10/10 with Y."

**SCOPE REDUCTION mode:** propose the minimum viable cut. What's the smallest version that delivers the core outcome? Strip everything else. Justify each cut with "this isn't load-bearing because Z."

### Step 7. Final scoped plan delta

Write the proposed plan diff to the original artifact OR `outputs/raw/plan-reviews/YYYY-MM-DD-<slug>-ceo-review.md`. Include:
- Mode used (locked since Step 0)
- Scope changes (added/removed/held with reasons)
- Open user-question items (if any)
- Specific Prime Directive flags with line refs

### Step 8. Capture Learnings (per §4 of cross-cutting patterns)

If the review surfaced a non-obvious pattern (e.g. "the operator pushes back on scope creep but prefers full-coverage where authorized", "BD-style plans need a landscape check more than tactical plans"), append to `memory/Learnings.md` per §4 format.

### Step 9. Review Chaining (per §5)

After display, recommend the next review:
- Plan touches UI/UX → `/plan-design-review` next
- Plan is now code-shaped → `/code-review` next
- Plan is now a public deliverable → `/review` pipeline
- Plan needs sharpening BEFORE more review → `/office-hours` back to start

Format as a structured user question per §1.

### Step 10. Completion Status (per §6) + Helicopter check (3 ripples)

Close with an explicit status:
- DONE. Prime Directive flags resolved, mode-output complete
- DONE_WITH_CONCERNS. completed but ≥1 Prime Directive still flagged
- BLOCKED. couldn't proceed
- NEEDS_CONTEXT. missing info to evaluate

Then 3 ripple-effect bullets:
- What other current work does this scope shift affect?
- What memory / knowledge-graph / CRM state needs to update if this ships?
- What downstream skills or crons need to react?

## Hard rules

- Mode commitment is non-negotiable. Don't silently drift between modes mid-review.
- Every scope change is an explicit user question. Never silently add or remove scope.
- Boil-the-lake bias: if approach A (full) vs approach B (90%), prefer A unless explicit REDUCTION mode.
- This is a REVIEW skill. Do NOT start implementation. Output is critique + scoped plan delta.
- Prime Directives apply in ALL modes. EXPANSION isn't permission to skip observability.

## Anti-pattern this guards against

Plan written → review → "looks good, ship it" → mid-build discovering the original scope didn't account for X / didn't include observability / silently swallowed errors / shipped a 6/10 because nobody asked "could this be a 10?" CEO review forces the strategic conversation BEFORE the build commits.

Sub-anti-pattern: silent mode drift. Mid-review, sliding from EXPANSION ("dream big") to HOLD ("let's just lock this") without telling the user. The mode is a contract. Honor it.

## Provenance

Adapted from `gstack/plan-ceo-review/SKILL.md` (Garry Tan, MIT). Restores Landscape Check + Taste Calibration + Completeness Principle + per-mode posture detail. Stripped (and rejected): the upstream telemetry / update-checker / home-dir state / config bin / proactive auto-suggest / cross-project learnings / autoplan integration / branded report format. Adapted to: the existing `/scope`, `decision-council`, `repo-audit` 4-option triage, recall, domain-tactical examples, a web-search tool. The "Completeness is cheap" principle aligns with the existing CLAUDE.md "Boil the Ocean" rule.
