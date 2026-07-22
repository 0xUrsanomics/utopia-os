---
name: plan-design-review
description: Designer's-eye plan review. Rate each design dimension 0-10, explain what would make it a 10, then fix the plan to get there. 7 passes (info architecture / interaction states / journey / slop risk / system alignment / responsive+a11y / unresolved). Backed by 12 cognitive patterns + 3 Laws of Usability + Goodwill Reservoir heuristics from established design canon.
trigger: design plan review, review ux plan, design critique, check design decisions, rate design completeness, plan design review
provenance: adapted from gstack (garrytan/gstack, MIT). expanded after the operator flagged loss of substantive heuristics.
references: knowledge/gstack-cross-cutting-patterns.md
---

# Plan Design Review. 0-10 Rate-Each-Dimension Method

## Why this exists

A plan with UI/UX components is usually 3-5/10 on design completeness even when it reads "complete." Backend behavior is specified down to the function name; what the user sees is one sentence. Result: mid-build discovery that empty states, error states, loading states, and mobile breakpoints were never decided.

This skill rates the plan's design dimensions 0-10 across 7 passes, explains what a 10 looks like, then EDITS THE PLAN to get there. Output is a fixed plan, not a comment thread.

Complement to the `frontend-design` plugin (which generates designs from specs). This skill REVIEWS the design layer of a plan BEFORE the plugin generates anything.

## When to fire

- Pre-implementation when the plan has any UI / UX / visual / interaction component
- Deck / proposal / landing page work before render
- Skills + tools that output to a human surface (chat message format, dashboard, status display)
- When the operator says "review the design plan" or "what's the design rubric here"

Skip for pure backend / API / infrastructure work with no human-facing surface.

## Pre-reading (consult once before Step 0)

Read these sections of `knowledge/gstack-cross-cutting-patterns.md`:
- §2 Cognitive Patterns. How Great Designers See (12 perceptual instincts)
- §3 UX Principles. Three Laws of Usability + behavioral patterns + Goodwill Reservoir
- §1 The structured-user-question decision-brief format (anti-batch rule)

Those are the EYES for this skill. The 7 passes below are the structured walk, but the cognitive patterns determine what you see when you walk.

## Procedure

### Step 0. Scope assessment

**0A. Initial overall rating:** rate the plan's overall design completeness 0-10. Justify with one line.
> *"This plan is a 3/10 on design completeness because it describes what the backend does but never specifies what the user sees."*
> *"This plan is a 7/10. good interaction descriptions but missing empty states + responsive behavior."*

Explain what a 10 looks like for THIS plan specifically.

**0B. Design system status:** is there a brand-guidelines / design-system reference?
- If a canonical brand-guidelines doc exists for this output type → cite it
- Else → flag "no design system, will calibrate against universal principles"

**0C. Existing leverage:** what existing UI patterns / brand assets / prior outputs should this reuse? Don't reinvent. Cite specific paths.

**0D. Focus areas (structured user question per §1 format):**
> *"Rated this plan {N}/10 on design completeness. Biggest gaps: {X, Y, Z}. Want me to run all 7 passes, or focus on specific areas?"*

**STOP.** Wait for a user response. Don't proceed until they've picked scope.

### Step 1. The 7 Review Passes

**Anti-skip rule:** never condense / skip / abbreviate any pass. "This is a strategy doc so design passes don't apply" is always wrong. design gaps are where implementation breaks. If a pass has zero findings, say "No issues found" and move on. Evaluate every pass.

**Anti-batch rule:** ask ONCE per issue. Do not bundle multiple findings into one question. Walk them one at a time per §1.

For each pass: rate 0-10, explain why, propose fix, EDIT the plan to get there, re-rate.

---

**Pass 1. Information Architecture.**
Rate: does the plan define what the user sees first, second, third?
Apply cognitive pattern #3 (Hierarchy as service) + #4 (Constraint worship).
Fix to 10: add information hierarchy. ASCII diagram of screen/page structure + navigation flow. If you can only show 3 things, which 3? Cite Krug's trunk test for navigation: cover everything except the nav. should still know where you are.

**Pass 2. Interaction State Coverage.**
Rate: does the plan specify loading / empty / error / success / partial states?
Apply cognitive pattern #6 (Edge case paranoia).
Fix to 10: add an interaction state table:
```
FEATURE | LOADING | EMPTY | ERROR | SUCCESS | PARTIAL
--------|---------|-------|-------|---------|--------
...
```
For each state: describe what the USER SEES, not backend behavior. Empty states are features. specify warmth, primary action, context. Loading states must indicate progress or estimated time, not just a spinner.

**Pass 3. User Journey & Emotional Arc.**
Rate: does the plan describe how the user FEELS at each step?
Apply cognitive pattern #2 (Empathy as simulation) + #10 (Time-horizon design) + #12 (Storyboard the journey).
Fix to 10: map the emotional arc. Where's the moment of delight (visceral, 5sec)? Where's accepted friction (behavioral, 5min)? Where's the friction to remove (reflective, 5yr)? What does the 5-second first impression communicate? Storyboard each major transition as a scene with a mood. not just a screen with a layout.

**Pass 4. AI Slop Risk.**
Rate: does the plan have specific, named, varied content. or generic placeholders?
Apply Three Laws Law #3 (Omit, then omit again) + behavioral pattern "users don't read instructions."
Fix to 10: replace every "[placeholder]" / "lorem ipsum" / "TODO copy" with actual copy. Strip the AI-slop wordlist (`leverage`, `navigate`, `holistic`, `seamless`, `comprehensive`, `crucial`, `pivotal`, `dive into`, `at the end of the day`). Cut happy talk and instructions. Voice must match the artifact's register. for your outputs, match `memory/SOUL.md` + `memory/Voice-Profile.md`. For chat outputs, use the operator's casual register (code-switch where natural, drop articles, blunt fragments).

**Pass 5. Design System Alignment.**
Rate: does the plan respect the existing brand system / patterns?
Apply cognitive pattern #9 (Subtraction default) + behavioral "Use conventions."
Fix to 10: cite specific brand-guidelines or prior approved outputs. Your outputs → the canonical brand system. Identify where the plan invents new patterns vs reuses canonical ones. Innovate on navigation only when you KNOW you have a better idea, otherwise use conventions. Clarity > consistency: if making something significantly clearer requires slight inconsistency, choose clarity.

**Pass 6. Responsive & Accessibility.**
Rate: does the plan account for the actual viewing surface?
Apply behavioral patterns "users scan" + "mobile: same rules, higher stakes."
Fix to 10: name the primary surface explicitly:
- **Chat mobile**: the 1500-char threshold from the progressive-disclosure skill. Touch targets are line-tap zones (the full message acts as target).
- **Slides desktop**: 1920×1080 default, 16:9 reading distance ~2m for projection.
- **Printed PDF**: A4/Letter, 11pt body minimum, monochrome-safe.
- **Dashboard / web**: name breakpoints, focus states for keyboard nav, contrast ratios.

For a11y: contrast minimum 4.5:1 for body text. Color is never sole signaler. RTL language support flagged if Arabic / Hebrew / RTL in the audience.

**Pass 7. Unresolved Design Decisions.**
Rate: what decisions are still implicit?
Apply cognitive pattern #5 (The question reflex).
Fix to 10: surface every implicit decision as an explicit choice. "Should this be inline or attached?" "Should errors be toast or modal?" "Should this run on hover or click?" Each surfaced as a separate user question per §1 if non-obvious.

### Step 2. Final rating + report

After 7 passes, write the final report to the plan or `outputs/raw/plan-reviews/YYYY-MM-DD-<slug>-design-review.md`:

```
Initial rating: X/10 (Step 0)
Final rating: Y/10 (after edits)
Passes:
  1. Info Architecture: X→Y/10. [one-line summary of change]
  2. Interaction States: X→Y/10. [...]
  ...
  7. Unresolved: X→Y/10. [...]
Open user questions: [count, list IDs]
Recommendation: ship / iterate further / re-scope
```

### Step 3. Capture Learnings (per §4 of cross-cutting patterns)

If this review surfaced a non-obvious pattern (e.g. "the operator prefers no-em-dash even in PDFs", "chat outputs need the 1500-char threshold check up-front, not at the end"), append to `memory/Learnings.md` per §4 format. Don't wait for `/save`.

### Step 4. Review Chaining (per §5)

After display, recommend the next review:
- Started below 4/10 OR surfaced fundamental product questions AND no plan-ceo-review yet → recommend `/plan-ceo-review`
- Changed scope significantly during review → recommend re-running this skill on the revised plan
- Approved + no further review needed → recommend `/code-review` if this becomes code, or `/review` if it becomes raw output

Format as a structured user question per §1.

### Step 5. Completion Status (per §6)

Close with an explicit status:
- DONE. all 7 passes completed, final rating ≥ 8/10
- DONE_WITH_CONCERNS. completed but ≥1 pass below 8 with concerns documented
- BLOCKED. could not proceed (missing context / artifact malformed / etc.)
- NEEDS_CONTEXT. surfaced unknowns that block proceeding

### Step 6. Helicopter check (3 ripples)

- What downstream work does this design lock-in affect (building components, drafting templates)?
- What brand-guideline pages should be updated if new patterns are now canonical?
- What review pipeline sees this output next?

## Hard rules

- 0-10 is honest. Don't grade-inflate. A "7" is "good but missing 1-2 dimensions." A "10" is "every dimension addressed with specifics." Most starting plans are 3-5/10.
- Edit the plan to get to 10 in each pass, don't just critique. Output is a fixed plan.
- Ask once per finding per §1. Never batch.
- Anti-shortcut: never write findings + ExitPlanMode without asking about non-trivial findings.
- Cognitive patterns run automatically while walking the passes. they aren't a separate step.
- Skip passes only when the plan has zero UI scope (pure backend). Strategy docs still get the passes.

## Anti-pattern this guards against

Plan ships with "user sees the dashboard" as the entire UX spec. Build commits. Implementation discovers: nobody specified empty state, error state, loading state, responsive breakpoint, stale-data behavior. Half-spec → half-build → half-ship. The 7 passes + 12 cognitive patterns + 3 Laws of Usability pre-empt this entire class.

## Provenance

Adapted from `gstack/plan-design-review/SKILL.md` (Garry Tan, MIT). Restores the substantive heuristics (Cognitive Patterns + UX Principles + Three Laws) and references the cross-cutting patterns doc separately to avoid duplication. Stripped (and rejected for this stack): the upstream telemetry / update-checker / home-dir state files / packaged binaries / mockup integration / continuous-checkpoint integration / proactive auto-suggest. Adapted to the skill conventions + brand-guidelines + frontend-design plugin + progressive-disclosure skill stack. Key refs: Rams, Norman, Nielsen, Krug, Redish, Gebbia, Maeda. the same canon the source draws on.
