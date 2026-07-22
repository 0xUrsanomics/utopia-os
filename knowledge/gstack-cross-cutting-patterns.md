---
name: gstack-cross-cutting-patterns
description: Cross-cutting procedural patterns adapted from gstack (garrytan/gstack, MIT). Referenced by review-style skills (office-hours, CEO-review, design-review) and any future review-style skill. Source: ~5 sections that appear in every gstack skill — extracted here as shared substrate instead of duplicated in each skill.
type: knowledge
provenance: gstack (garrytan/gstack, MIT)
---

# Cross-Cutting Patterns from gstack

These patterns appeared as boilerplate in every gstack skill. They are NOT boilerplate — each is a substantive procedural primitive that hardens any review-style or scoping skill. Extracted here as a shared reference so review-style skills (e.g. an office-hours, a CEO-review, a design-review skill) and any future review skill can cite without duplicating.

---

## 1. AskUserQuestion Decision-Brief Format

Every AskUserQuestion fired from a review skill is a decision brief, not a casual question. Follow this shape:

```
D<N> — <one-line question title>
Context: <1 short grounding sentence — project, branch, or current scope>
ELI10: <plain English a 16-year-old could follow, 2-4 sentences, name the stakes>
Stakes if we pick wrong: <one sentence on what breaks, what user sees, what's lost>
Recommendation: <choice> because <one-line reason>
Completeness: A=X/10, B=Y/10  (or "options differ in kind, not coverage" if not comparable)
Pros / cons:
A) <option label> (recommended)
  ✅ <pro — concrete, observable, ≥40 chars>
  ❌ <con — honest, ≥40 chars>
B) <option label>
  ✅ <pro>
  ❌ <con>
```

**Anti-batch rule:** one decision = one AUQ. Never bundle 3 unrelated decisions into one question. Multi-decision questions become "approve everything" rubber-stamps.

**Anti-shortcut rule:** finding-→-plan-write-→-ExitPlanMode without firing AUQ is the precise failure mode where the model "explored, found issues, and dumped them into a deliverable rather than walking the user through them." Every non-trivial finding goes through AUQ. Zero-findings is the only bypass.

---

## 2. Cognitive Patterns — How Great Designers See

For `plan-design-review` and any design-evaluating skill. These are perceptual instincts, not a checklist. Let them run automatically while reviewing.

1. **See the system, not the screen** — never evaluate in isolation. What comes before, after, when things break.
2. **Empathy as simulation** — not "I feel for the user" but mental simulations: bad signal, one hand free, boss watching, first-time-vs-1000th-time.
3. **Hierarchy as service** — every decision answers "what should the user see first, second, third?" Respecting time, not prettifying pixels.
4. **Constraint worship** — limitations force clarity. "If I can only show 3 things, which 3 matter most?"
5. **The question reflex** — first instinct is questions, not opinions. "Who is this for? What did they try before this?"
6. **Edge case paranoia** — what if name is 47 chars? Zero results? Network fails? Colorblind? RTL language?
7. **The 'Would I notice?' test** — invisible = perfect. Highest compliment is not noticing the design.
8. **Principled taste** — "this feels wrong" must be traceable to a broken principle. Taste is *debuggable*, not subjective (Zhuo).
9. **Subtraction default** — "as little design as possible" (Rams). "Subtract the obvious, add the meaningful" (Maeda).
10. **Time-horizon design** — first 5 sec (visceral) / 5 min (behavioral) / 5-yr relationship (reflective) — design for all three (Norman).
11. **Design for trust** — every decision builds or erodes trust. Strangers sharing a home requires pixel-level intentionality (Gebbia).
12. **Storyboard the journey** — before pixels, storyboard the emotional arc. Each moment is a scene with a mood (Gebbia, "Snow White" method).

Key refs: Rams' 10 Principles, Norman's 3 Levels, Nielsen's 10 Heuristics, Gestalt Principles, Krug (3-second scan / trunk test / satisficing / goodwill reservoir), Redish (Letting Go of the Words), Ira Glass on taste-gap, Jony Ive on care/carelessness, Gebbia on trust + storyboarding.

---

## 3. UX Principles — How Users Actually Behave

Observed behavior, not preferences. Apply before/during/after every design decision.

**Three Laws of Usability:**
1. **Don't make me think.** Every page self-evident. User stops to think → design failed.
2. **Clicks don't matter, thinking does.** 3 mindless clicks beat 1 thoughtful click.
3. **Omit, then omit again.** Half the words. Then half of what's left. Happy talk and instructions die.

**How users actually behave:**
- **Scan, don't read.** Design for scanning: hierarchy, defined areas, headings, bullet lists, highlighted terms. Billboards at 60mph, not brochures.
- **Satisfice.** Pick the first reasonable option, not the best. Make the right choice the most visible choice.
- **Muddle through.** Don't figure out how things work. Wing it. If something works by accident, stick to it.
- **Don't read instructions.** Dive in. Guidance must be brief, timely, unavoidable.

**Billboard design rules:**
- **Use conventions** (logo top-left, magnifying-glass search). Don't innovate on nav to be clever.
- **Visual hierarchy is everything.** Related = grouped. Nested = contained. Important = prominent. If everything shouts, nothing is heard.
- **Clickable = obviously clickable.** Shape, location, formatting signal clickability without hover (mobile has no hover).
- **Eliminate noise.** 3 sources: shouting / disorganization / clutter. Fix by removal, not addition.
- **Clarity > consistency.** If clarity makes something slightly inconsistent, choose clarity.

**Navigation as wayfinding:** users have no sense of scale, direction, or location. Nav must always answer: what site is this, what page am I on, what are the major sections, where am I, how can I search. The "trunk test": cover everything except the nav — should still know.

**Goodwill reservoir:** users start with goodwill. Friction depletes it.
- **Deplete:** hiding info wanted (pricing, contact), punishing non-conformance, asking for unnecessary info, sizzle (splash screens), sloppy appearance.
- **Replenish:** make right action obvious, tell upfront, save steps, easy error recovery, apologize when wrong.

**Mobile:** same rules, higher stakes. Real estate scarce but never sacrifice usability for space. Affordances must be VISIBLE — no cursor hover. Touch targets 44px+.

---

## 4. Capture Learnings (inline during review)

If a review uncovers a non-obvious pattern / pitfall / preference / architectural insight, log it for future sessions. Don't wait for /save — log immediately, /save will reconcile.

**Format** (append to `memory/Learnings.md` with the same date-tag-block shape used elsewhere):

```yaml
type: pattern | pitfall | preference | architecture | tool | operational
key: short-slug-for-recall
insight: 2-3 sentence description
confidence: 1-10 (be honest)
source: observed | user-stated | inferred | cross-model
files: [relevant paths]
```

**Confidence calibration:**
- 10 = user explicitly stated preference
- 8-9 = observed in code, verified
- 4-5 = inference, not sure
- 1-3 = guess, hedging

**Test before logging:** would this insight save time in a future session? If yes → log. If "everyone knows this" → don't log. Don't log obvious things.

---

## 5. Review Chaining — Recommend Next Skill

After a review skill completes, recommend the next review based on what THIS review surfaced. Don't blindly fire the full chain.

**Default chain** (sequence when full review is in scope):
`office-hours` (sharpen requirements) → `plan-ceo-review` (strategic) → `plan-eng-review` (architecture; or your own code-review skill) → `plan-design-review` (UX/UI)

**Conditional triggers:**
- If `plan-design-review` started below 4/10 OR surfaced fundamental product questions → recommend `plan-ceo-review` (only if no CEO review exists).
- If `plan-ceo-review` changed scope significantly → re-run `plan-design-review` (the design rubric needs to revalidate against new scope).
- If `office-hours` reveals the user wasn't ready (vague brief, no evidence) → recommend NO further skills, send brief back for sharpening.

**Format the recommendation as AUQ** with explicit options:
- A) Run /<next-skill> next (recommended because X)
- B) Skip — handle next steps manually
- C) Run /<other-skill> instead

**Hard rule:** if eng-review-equivalent (`/code-review`) is the required ship-gate for this artifact type, it goes BEFORE optional design/ceo passes when both are needed.

---

## 6. Completion Status Protocol

When closing any review skill, declare status explicitly. Don't end with vague "looks good."

**One of:**
- **DONE** — completed with evidence (cite the evidence inline).
- **DONE_WITH_CONCERNS** — completed but list specific concerns.
- **BLOCKED** — cannot proceed; state the blocker + what was tried.
- **NEEDS_CONTEXT** — missing info; state exactly what's needed.

**Format:**
```
STATUS: <one of the 4>
REASON: <one sentence>
ATTEMPTED: <what was tried, if BLOCKED>
RECOMMENDATION: <what to do next>
```

**Escalate to BLOCKED** after 3 failed attempts at the same sub-step, for uncertain security-sensitive changes, or for scope that can't be verified.

---

## 7. Context Recovery (session-start primitive)

For any skill that starts a new session (not continuation), recover recent project context before the substantive work. Adapt to your own stack. If you keep a session-bootstrap/handoff file + a watchdog, the gstack-equivalent flows are:

1. **Read latest checkpoint** — e.g. a `memory/session-bootstrap.md` Active Handoff block.
2. **Recent timeline** — `tail -50 logs/session.jsonl` for last 24h of skill executions.
3. **Branch + repo context** — `git branch --show-current` + `git log --oneline -10`.
4. **Last 3 outputs from this skill type** — `ls -t outputs/raw/<skill-type>/ | head -3`.

If 2+ artifacts recovered, give 2-sentence "welcome back" summary before launching the skill. If recent skill-execution pattern implies a next step, mention once (don't pressure).

---

## What we did NOT lift from gstack (with reason)

- **Telemetry** (`~/.gstack/analytics/skill-usage.jsonl`): observable + analytics phone-home. Prefer a local event log (e.g. `logs/session.jsonl`); no external analytics, no new infra needed.
- **gstack-update-check**: network call per skill fire to check upstream version. Don't auto-update from external repos; a periodic re-audit cadence is safer.
- **bin/gstack-*** compiled binaries: source-audit burden. Native python/bash equivalents avoid it.
- **Continuous checkpoint mode** (auto-commit WIP): conflicts with a clean-commit preference + a periodic git-push cadence. The `[gstack-context]` block format is interesting — a candidate pattern for a save/checkpoint skill, but not auto-applied.
- **Question tuning** (per-question preference learning): requires a `gstack-question-preference` + `question-registry.ts` infrastructure. The concept (adaptive friction reduction) is valuable but the implementation is tool-coupled. Re-evaluate once you have 50+ AUQ-fired data points in your own logs.
- **Proactive auto-suggest config**: gstack auto-suggests skills based on context. If your model already auto-routes via skill frontmatter triggers, doubly-applying would create noise.
- **Cross-project learnings**: shared learnings across all projects on the machine. An alternative is per-persona memory + a global Learnings file. Different architecture, intentional.

---

## When to consult this file

When invoking any of: `/office-hours`, `/plan-ceo-review`, `/plan-design-review`, or building any new review-style skill. Read sections 1, 4, 5, 6 always. Read 2-3 for design-specific work. Read 7 on session start only.

If you're building a NEW review-style skill, reference this file rather than duplicating its content. Add new patterns here (with provenance) if they emerge.
