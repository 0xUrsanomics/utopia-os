---
name: office-hours
description: Force assumptions into the open before code is written. 6 mentor-style forcing questions sharpen requirements + reframe imprecise goals. Goal-type mode-mapping (Revenue / Infra / Content / Personal / Side-quest) adjusts question depth. Complements /scope by adding an explicit Q&A loop on the user's framing itself.
trigger: office hours, sharpen requirements, gut-check idea, am i building the right thing, before i build, sharpen this, force the questions
provenance: adapted from gstack (garrytan/gstack, MIT). expanded after the operator flagged loss of substantive heuristics.
references: knowledge/gstack-cross-cutting-patterns.md
---

# Office Hours. Forcing-Question Layer Before Build

## Why this exists

Requirements written by the user are usually imprecise, hypothetical, or carry hidden assumptions. The fix is not better implementation. it's 60 seconds of forcing questions before any code is written. This skill makes those questions explicit and repeatable.

Complement to `/scope` (which surfaces assumptions in the agent's plan). `office-hours` interrogates the USER's framing itself. Use BEFORE `/scope` when the request feels mushy.

## When to fire

- User describes a vague product idea ("I want to build X for Y users")
- Pre-implementation when the brief reads like marketing language ("seamless", "better", "modern")
- User says "I'm thinking about..." or "should I build..."
- Before any new project intake, new client/project scoping

Skip when the ask is concrete, scoped, and has a measurable definition of done. Skip when an explicit "just do it" override is given.

## Pre-reading (consult once before Step 1)

Read §1 (the structured-user-question decision-brief format) of `knowledge/gstack-cross-cutting-patterns.md`. The 6 questions are walked one at a time as decision briefs, not freestyle.

## Procedure

### Step 1. Context gathering (quiet)

Read in this order. Don't print findings. ground yourself.
- `CLAUDE.md` if it exists
- `memory/USER.md` + the active persona memory file
- `memory/SOUL.md` for voice register if output-shaped
- Recent git log: `git log --oneline -15`
- Glob/grep for related prior work in `outputs/raw/`, `memory/Context/`, `memory/projects/`

If the recent timeline shows we just did something similar, surface that to the user upfront: *"Just noting. we did Z 3 days ago. Different problem or same?"*

### Step 2. Goal-type classification (REAL question, not formality)

The category changes everything downstream. Different categories = different question depth and rigor.

Ask via a structured user question per §1 format:

**A) Revenue** (client deal, BD, pipeline progression, deck, proposal)
- Heaviest gate. Strategic implications, money on the line, reputational stakes.
- All 6 questions, all rigorously.

**B) Infrastructure** (the agent stack, daemon, skill build, automation, schedule)
- Heavy gate. Will run for weeks/months. Boil-the-ocean applies.
- All 6 questions, especially #5 (do-nothing) and #6 (what exists).

**C) Content** (a post, thread, positioning artifact, deck section)
- Medium gate. Voice + framing matter most.
- Focus on Q1 (language precision) + Q2 (hidden assumptions) + Q4 (right problem).

**D) Personal** (training, health, life-ops)
- Coach territory mostly. Suggest a persona switch if heavy.
- Light gate. Q1 (language) + Q5 (do-nothing) enough.

**E) Side-quest** (exploratory, learning, "what if we...")
- Lightest gate. Q1 (language) + Q5 (do-nothing) only. Don't burn the full 6 on a weekend experiment.
- Anti-pattern: forcing rigor on play kills exploration.

### Step 3. Product stage assessment (Revenue + Infrastructure only)

Quick context:
- **Pre-product**: idea stage, no users / no deal closed yet
- **Has signal**: warm leads, prospect engagement, partial validation
- **Has paying customers** (or signed deals): real revenue or commitments

Different stages need different framings. Pre-product needs MORE forcing (the assumptions are still cheap to change). Has-customers needs LESS (the assumptions have been priced).

### Step 4. The Six Forcing Questions

Walk one at a time. Don't batch. Each is a real challenge to the user's framing. don't soften them. Each gets a real answer before the next.

For Revenue / Infra: walk all 6. For Content: Q1+Q2+Q4. For Personal: Q1+Q5. For Side-quest: Q1+Q5.

---

**Q1. Language precision.**
Are key terms defined? If they said "the AI space", "seamless experience", "better platform", "market opportunity". challenge: *"What do you mean by [term]? Can you define it so I could measure it?"*

If they used a metric-sounding word without a unit ("a lot of users", "high engagement"), push for the unit. *"How many is 'a lot'? Engagement measured by what. DAU, session length, return rate?"*

If they reframe, you're done. If they can't define, surface the gap and propose a definition.

**Q2. Hidden assumptions.**
What does the framing take for granted?
- *"I need to raise money"* → assumes capital is required vs revenue-funded
- *"The market needs this"* → assumes verified pull vs unvalidated push
- *"A customer will pay for X"* → assumes their budget category covers this
- *"This will scale"* → assumes the bottleneck isn't where they think it is

Name ONE assumption. Ask if it's verified. with evidence, not gut. *"Has any actual customer paid for that specific service line before? Whose budget did it come out of?"*

**Q3. Real vs hypothetical pain.**
Is there evidence of actual pain, or is this a thought experiment?
- *"I think people would want..."*. HYPOTHETICAL
- *"3 specific people told me they spend 5hr/week on this"*. REAL
- *"A named customer's BD said in our last meeting they were burning $X on Y"*. REAL
- *"The market is huge"*. HYPOTHETICAL FRAMING

Push for at least one named witness or a number. *"Who said it? When? What did they describe?"*

**Q4. Is this the right problem?**
Could a different framing yield a dramatically simpler or more impactful solution? Pattern-match against prior similar problems we've handled or shipped.
- Sometimes the right move is to reframe the question, not answer it as asked
- Sometimes the user is asking how to ship a deliverable when they should be asking why this deliverable
- *"You're asking for X. But what if the actual blocker is Y? Different solve."*

**Q5. What happens if we do nothing?**
- Real pain → the 1mo-from-now picture is bad (deal expires, customer churns, a deadline hits, capacity exceeded)
- Hypothetical → the 1mo-from-now picture is identical to today

Push for the bad outcome that motivates this. If there isn't one, this is curiosity not need.
*"If we don't do this, what specifically breaks? What does next month look like?"*

**Q6. What already partially solves this?**
- Existing skills: `skills/_index.md`
- Existing scripts: `scripts/`
- Prior decisions: `memory/Decisions.md` via recall
- Prior outputs: `outputs/raw/` + `outputs/reviewed/`

Don't reinvent. Map what's already partial and ask if EXTENDING beats greenfield.
*"We already have the /X skill that does 60% of this. Should we extend it or rebuild?"*

### Step 4.5. Reframe if needed (don't dissolve)

If the answers expose that the user is asking the wrong question, reframe constructively:
> *"Let me try restating what I think you're actually building: [reframe]. Does that capture it better?"*

Then proceed with the corrected framing. Takes 60 seconds. **Don't kill the question by interrogating it to death**. re-aim and proceed. The skill is forcing questions, not torpedo questions.

### Step 5. Output the calibrated brief

5-7 line summary back to the user:

```
Goal category: [A/B/C/D/E from Step 2]
Product stage: [pre-product / has signal / has customers]
What you're actually building: [reframed, 1 line]
Key terms defined: [3-5 lines, definitions extracted]
Verified vs assumed: [list which is which, with sources for verified]
Existing partial solves: [what to extend, with paths]
Next step: [explicit handoff. /scope, build directly, park, or back-to-shaping]
```

### Step 6. Capture Learnings (per §4)

If office-hours surfaced a recurring user pattern (e.g. "the operator tends to skip the Q3 evidence requirement when excited about an idea. push harder there next time"), append to `memory/Learnings.md` per §4.

### Step 7. Review Chaining (per §5)

After the calibrated brief:
- If the brief is clean + scope is defined → recommend `/scope` next (or proceed to build)
- If the brief surfaces strategic ambiguity → recommend `/plan-ceo-review`
- If the brief surfaces "this isn't the right problem" → reframe + re-fire office-hours on the new framing
- If the brief surfaces "we don't have evidence" → park, send back to the user for evidence-gathering

Format as a structured user question per §1.

### Step 8. Completion Status (per §6)

Close with an explicit status:
- DONE. brief calibrated, next step clear
- DONE_WITH_CONCERNS. calibrated but ≥1 question got a weak answer (note which)
- BLOCKED. user can't answer ≥3 questions = brief isn't ready
- NEEDS_CONTEXT. missing context to ask the questions properly

## Hard rules

- Don't batch the 6 questions. Walk them one at a time. Each gets a real answer before the next.
- Reframe ≠ dissolve. Re-aim the question, don't kill it.
- Verified > assumed. Push for evidence at every step.
- Match question depth to goal-type (Revenue=all 6, side-quest=2). Forcing rigor on play kills exploration. Forcing levity on revenue work is sloppy.
- If the user says "skip office-hours" or "just do it". exit immediately. Override accepted.
- Don't lecture. Q1 isn't "let me explain what language precision means." Q1 is *"What do you mean by [term]?"* That's it.

## Anti-pattern this guards against

Building from a vague brief, hitting the late phase of any pipeline, then discovering the original request didn't define what "done" means. ~40% of unscoped work hits this by hour 4. 60 seconds of forcing questions pre-empts the entire class.

Sub-anti-pattern: interrogation-to-death. The skill is FORCING, not torpedo. If the user gives a real answer, accept it and move to the next Q. Don't push 5x on the same Q hoping they'll say something different.

## Provenance

Adapted from `gstack/office-hours/SKILL.md` (Garry Tan, MIT). Restores the goal-type mode-mapping (the source's startup-vs-builder mode applied to the Revenue/Infra/Content/Personal/Side-quest taxonomy) + product-stage assessment + per-question depth detail + the interrogation-to-death anti-pattern. Stripped (and rejected): the upstream telemetry / update-checker / home-dir state / packaged binaries / proactive auto-suggest / cross-project learnings / sticker-mode templates / wild-exemplar gallery. Adapted to: the personas, `/scope`, the memory architecture, domain-tactical examples, the raw outputs pipeline.
