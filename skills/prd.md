---
name: prd
description: Structured PRD/spec generator. Transforms vague ideas (skill / infra / process / feature) into requirements, success metrics, build phases, and go-or-park gates BEFORE implementation starts. Lifted from wwwazzz/senior-pm-prompt, adapted to the stack (helicopter-check + ship-discipline native).
trigger: /prd, /spec, /requirements, write a prd, draft spec, scope this out, what's the spec
---

# /prd. Structured spec generator

Transforms vague ideas → a structured spec with verifiable success criteria, explicit blast radius, and ship-or-park gates BEFORE writing any code. Replaces the failure mode where vague-idea → impl skips the intermediate spec and you ship the wrong thing.

**When to use**: any new substantive build. a new skill, a new cron task, a new infra change, a new process, a content-pipeline change, anything that touches multiple files or spans >1 turn. NOT for: bug fixes, micro-edits, single-line corrections, casual Q&A.

**When NOT to use**: when scope is already obvious + 1-step (e.g. "kill these 4 orphan procs"). Don't bloat single-step work with PRD ceremony.

## Lifted from

`wwwazzz/senior-pm-prompt` (GitHub, MIT-spirit). Pattern lift, not a full ship. adapted to the stack with helicopter-check + sycophancy-guard + scope-discipline native. Source patterns: aggressive first-pass mining / slot-filling / consistency PASS-FAIL / opinionated defaults marking `_TBD_` explicitly (vs fabricating).

## 4-Phase procedure

### Phase 1. AGGRESSIVE FIRST-PASS MINING

When the user surfaces a vague idea ("we should build X" / "let's spec out Y"), extract whatever structure is implicit in their phrasing BEFORE asking questions. Do NOT immediately ask "what do you want?". mine first.

Extract:
- **Title** (slug-form). what to call this
- **Goal** (1-sentence outcome). what it accomplishes when done
- **Stakeholder** (who cares). The operator? A persona? A sub-agent? External?
- **Trigger condition** (when does this fire). manual? cron? event-driven?
- **Adjacent stack**. which existing files / skills / scripts does this touch?

Surface this back to the user as an "I read your ask as: ..." paragraph BEFORE Phase 2. Lets the user correct mining errors fast.

### Phase 2. SLOT-FILLING DIALOGUE

Walk through these slots SEQUENTIALLY. Don't ask all at once (overwhelming). One slot per question, each question 1-3 lines max. If the user gives multi-slot answers, accept + move on.

#### Slot 2.1: Outcome verifiability

"How will we know this is working? A specific observable signal. a log entry, a file output, a downstream metric, a user-visible behavior."

If the answer is vague: rephrase it as a measurement. "Faster" → "p50 latency under 500ms". "Better recall" → "a stale-memo replay returns the fresh chunk in top-3".

#### Slot 2.2: Failure mode

"What's the dominant way this fails? The most-likely bug, edge case, regression risk."

This is the load-bearing question. If the user can't name a failure mode, the spec is too vague. push back: "if there's no way for this to fail, there's nothing to verify; what does broken look like?"

#### Slot 2.3: Blast radius

"What does this touch? Settings, scheduler, a hot path, hooks, shared state, external comms?"

Map the blast radius to an autonomy mode: AUTO (low blast) / INFORM (moderate) / CONFIRM (high or external-facing). Reference: `memory/Infra/permissions-schema.json`.

#### Slot 2.4: Existing equivalents

"Is something already doing this OR similar? Search the recall index + grep + skills/_index.md before answering."

If yes: surface it for either (a) extend the existing, (b) fork the pattern, (c) replace the existing. The DEDUP gate. Per the pattern-lift discipline: always survey before building.

#### Slot 2.5: Effort + ROI honest estimate

"Build effort (hours), maintenance ongoing (hours/month), value delivered (concrete outcome)."

If effort > value × 5, push back on whether this is worth it now vs queue/park. Per sycophancy-guard Rule 3: state confidence + the weakest assumption.

### Phase 3. CONSISTENCY VALIDATION (PASS/FAIL gates)

Before ANY implementation, run these gates. Each is binary PASS/FAIL.

| Gate | PASS criterion | FAIL means |
|---|---|---|
| Outcome verifiable? | Slot 2.1 has a SPECIFIC observable | Spec too vague, rewrite |
| Failure mode named? | Slot 2.2 has at least 1 named failure | Can't test what we can't break |
| Blast radius bounded? | Slot 2.3 maps to an autonomy mode | Unknown blast = needs scope clarification |
| Dedup checked? | Slot 2.4 surfaces existing equivalents | Possible reinvent-the-wheel |
| ROI defended? | Slot 2.5 has effort vs value | Can't prioritize without numbers |
| Helicopter ripples? | 3 ripple bullets on infra/scheduler/hooks/shared-state | Per the helicopter-check discipline |

If ANY gate FAILS, the PRD is not done. Either fill the gap OR explicitly mark `_TBD_` with rationale (e.g. "_TBD_. outcome verifiability deferred to the pilot run, will define after seeing the first real data").

**`_TBD_` discipline (from senior-pm-prompt)**: NEVER fabricate values to fill slots. Better to mark `_TBD_` than to invent. Future-you reading the PRD needs to know which assumptions were defended vs deferred.

### Phase 4. OUTPUT FORMAT

Produce a structured PRD doc. Save to `outputs/raw/agent/prds/YYYY-MM-DD-{slug}-prd.md` (creates the dir if missing). Format:

```markdown
---
title: {Title}
slug: {slug}
date: {YYYY-MM-DD}
status: draft | reviewed | approved | shipped | parked
stakeholder: {operator / persona / sub-agent / external}
autonomy_mode: AUTO | INFORM | CONFIRM
estimated_effort_hours: {N}
maintenance_hours_per_month: {N}
go_or_park_threshold: {effort * value calc}
---

# {Title}

## 1. Goal
{One-sentence outcome statement}

## 2. Stakeholder + Trigger
- **Who cares**: {stakeholder}
- **When fires**: {manual / cron / event}
- **Adjacent stack**: {existing files/skills/scripts touched}

## 3. Outcome (verifiable)
{Specific observable signal. Log entry / file / metric / behavior. Include measurement.}

## 4. Failure mode
{Dominant failure. Edge case. Regression risk. What does broken look like?}

## 5. Blast radius + ripples
- Autonomy mode: {AUTO/INFORM/CONFIRM} (rationale)
- Ripple 1: {what else this touches}
- Ripple 2: {downstream effect}
- Ripple 3: {forward-compat or upstream-block consideration}

## 6. Dedup check
- Existing equivalent: {none / extend X / fork Y / replace Z}
- Survey method: {grep / recall / skills/_index.md scan}

## 7. Effort + ROI
- Build hours: {N} (or _TBD_ until prototype)
- Maintenance hours/month: {N}
- Value delivered: {concrete outcome. saved cycles, prevented failures, unlocked capability}
- Confidence: {N%}, weakest assumption: {what's most likely wrong}

## 8. Build phases
1. {Phase 1, with a verification checkpoint}
2. {Phase 2, with a verification checkpoint}
3. ...

## 9. Go-or-park gate
- **Ship if**: {N of 6 PASS gates + helicopter ripples surfaced + operator authorization}
- **Park if**: {failure mode unclear / no real failure replay / dedup conflict / blast radius too high}
- **Re-eval cadence if parked**: {date or trigger condition}

## 10. Out of scope
- Explicit list of what this PRD does NOT cover. Prevents scope creep mid-build.
```

### Phase 4.5. APPROVAL GATE

After the PRD draft is written:
1. Surface it to the user via the chat channel with a summary table (gates / passed-failed / `_TBD_` count).
2. User options: APPROVE → status=approved, ship next; EDIT → user revises a specific section; PARK → status=parked, log rationale; KILL → discard, archive.
3. Only on APPROVE proceed to implementation. Status changes to `shipped` after ship + smoke test.

## Hard rules

1. **NEVER skip the Phase 3 gates**. The whole point is forcing the spec discipline. Skipping gates = back to the vague-idea → impl failure mode.
2. **NEVER fabricate slot values**. `_TBD_` with rationale > a fake number. Future-you reading this needs to distinguish defended vs deferred.
3. **NEVER produce a PRD without the Phase 4.5 approval gate**. Auto-shipping a PRD without an explicit go = unilateral scope expansion. CONFIRM-gate.
4. **NEVER bloat single-step work**. If the ask is "kill 4 orphan procs", don't write a PRD. PRDs are for substantive multi-file/multi-phase builds.
5. **ALWAYS dedup BEFORE drafting**. Slot 2.4 is the survey gate. Lifted patterns get cited; reinvented work gets caught here.

## Pairs with

- **`/scope`** (auto-invoke before CONFIRM-gate actions): /scope is the inline scope restate. /prd is the structured-doc version for substantive builds.
- **`memory/Infra/permissions-schema.json`**: the blast-radius → autonomy-mode mapping reference.
- **the helicopter-check discipline**: the 3-ripple check that Slot 2.3 surfaces.
- **the pattern-lift discipline**: the alternatives audit happens at the Slot 2.4 dedup check.
- **`skill-creator.md` 9-element quality gate**: when the PRD is FOR a new skill, the resulting skill body should pass that 9-element checklist.

## Source archive

Lifted from `wwwazzz/senior-pm-prompt`. Adapted: replaced the PM-centric "user personas + UX flows" with stakeholder + autonomy-mode + helicopter-ripple slots that match the internal stack. The source ships Markdown-formatted PRD output for direct ingestion by AI coding agents (Claude Code, Cursor); the adaptation keeps that property + adds the CONFIRM-gate approval flow.

## Example invocation

```
> /prd new skill: temporal rerank for the recall index

Phase 1 mining:
"I read your ask as: a new skill that adds time-decay to recall.
Title: lib_temporal_rerank
Goal: stale-memo recall failures get fixed by time-aware reranking
Stakeholder: the operator (recall consumer)
Trigger: a --temporal flag on the recall search command
Adjacent stack: the recall index, memory tier files (Decisions/Learnings/Context/Infra)
Sound right?"

User: yes proceed

Phase 2 slot-filling (one Q at a time)...
[slot 2.1 outcome: "a stale-memo replay returns the RESOLVED memo top-3 instead of the OLD claim"]
[slot 2.2 failure: "doc-kind misclassification → wrong decay applied"]
[slot 2.3 blast: "AUTO. opt-in flag, default-off, no hot-path change"]
[slot 2.4 dedup: "8 alternatives surveyed. one external pattern was the best fit, no internal equivalent"]
[slot 2.5 effort: "~half a day build, ~5min/month maintenance, value = the stale-memo class fixed"]

Phase 3 gates: 6/6 PASS

Phase 4 PRD output → outputs/raw/agent/prds/2026-05-10-temporal-rerank-prd.md
status=approved (operator green-lit)

Phase 4.5 approval: APPROVED → ship.
```
