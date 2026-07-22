---
name: EXAMPLE Infra Note
description: Template for a Tier-2 infra note. Problem / root-cause / fix / recurrence-log.
type: infra
status: example
created: 2026-01-15
---

> **Example file.** This shows the shape of a Tier-2 infra note (`memory/Infra/`). An infra note is
> the durable record of a technical problem: what broke, why, how it was fixed, and every time it has
> recurred. Copy it to `memory/Infra/<component-slug>.md`, replace the fabricated content, and add a
> one-line pointer in `memory/MEMORY.md`. The recurrence log is the highest-value part: same-shape
> bugs that recur are the signal that a text-lesson alone never fixed the root cause. Delete this
> quote-block in your real file.

# <Component / Bug Name>

## The bug

> What is observed to go wrong, concretely. Include the exact symptom, where it fires, and how it was
> spotted. A future reader hitting the same symptom should recognize it here.

`<fill in: the observable failure. e.g. "Tool X writes to the wrong location when condition Y holds.
Observed <date> doing Z.">`

## Root cause

> The actual mechanism, once diagnosed. Distinguish this from the symptom. If unknown, say "root cause
> UNKNOWN as of <date>" rather than guessing, an unconfirmed theory logged as fact is its own trap.

`<fill in: the mechanism. e.g. "The API uses a bounding-box heuristic that a side-block of data
extends, pushing writes out of range.">`

## Fix / workaround

> The permanent fix if it exists, otherwise the workaround plus what the permanent fix WOULD be and
> its cost. Be explicit about which one this is.

`<fill in the steps>`
1. `<step>`
2. `<step>`
3. `<verify: re-read / re-check that the fix actually took>`

## Scope

> Where this applies and where it's unconfirmed. Default to the cautious assumption for the untested
> cases.

- **`<confirmed-affected surface>`**: confirmed broken.
- **`<other surfaces>`**: unknown, presumed affected until proven safe.

---

## Recurrence log

> Every time this bug (or its exact shape) reappears, append a dated line. Three same-shape
> recurrences is the signal that the fix was a bandaid and the real root cause is still live, stop
> patching and re-diagnose.

- **2026-01-15** — first observed and fixed per above.
- `<YYYY-MM-DD — recurrence: what fired it again, whether the prior fix held>`
