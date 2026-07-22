---
name: EXAMPLE Feedback Lesson
description: Template for a Tier-2 feedback lesson. A dated correction the operator gave, generalized into a rule.
type: feedback
status: example
created: 2026-01-15
---

> **Example file.** This shows the shape of a Tier-2 feedback lesson (`memory/Feedback/`). A feedback
> lesson captures a specific correction the operator gave, generalized into a reusable rule so the
> same mistake isn't repeated. Copy it to `memory/Feedback/<lesson-slug>.md`, replace the fabricated
> content, and add a one-line pointer in `memory/MEMORY.md`. Structure: state the rule up front, give
> the incident that produced it, explain WHY, then how to apply it. Delete this quote-block in your
> real file.

# <Lesson name, stated as the rule>

**Rule:** `<the one-sentence lesson, phrased as a general instruction the agent can follow next time>`

## Incident

> The concrete moment the correction happened. What the agent did, what the operator said, what the
> right move would have been. Keep the operator's actual correction if it's instructive, it anchors
> the lesson.

`<fill in: on <date>, the agent did X. the operator corrected with "<their words>". the intended
behavior was Y.>`

## Why

> The mechanism behind the rule. Why the corrected behavior is right, not just that it was asked for.
> A rule you understand generalizes; a rule you memorized doesn't.

`<fill in: the reasoning. e.g. "diffing against a working peer is a free controlled experiment; the
delta IS the cause by construction, whereas mechanism-theorizing burns time and biases toward
expensive fixes.">`

## How to apply

> The trigger and the action. When does this rule fire, and what should the agent do the moment it
> recognizes the situation?

- **Trigger**: `<the situation that should make the agent recall this lesson>`
- **Action**: `<what to do instead>`
- **Catch-yourself signal**: `<the tell that you're about to repeat the mistake>`

---

*Related: `<optional pointers to sibling lessons or the Decisions entry that shipped the fix>`.*
