# Learnings. <OPERATOR_NAME>

> **Template.** Copy to `memory/Learnings.md`. Append-only, dated, tag-indexed log of durable lessons,
> the things that cost you once and should never cost you again. Read-on-demand (NOT always-loaded)
> and indexed into Tier 3, so `recall("<topic>")` surfaces the relevant lesson when a later task
> touches the same shape of problem. Lead each entry with a one-sentence RULE, then the supporting
> incident. The rule is what future-you greps for; the incident is the evidence.

<!-- Append new learnings below. Tag for searchability.

Entry schema:
  ## YYYY-MM-DD. short title
  ### Rule: <one-sentence lesson, stated as a general rule not a story>
  - bullets: incident (what happened), why (mechanism), detection signal, workaround/fix
  tags: #topic-a #topic-b
  affected_files:: path/one.py, path/two.md    # OPTIONAL, only when the insight is path-specific

The affected_files:: line lets a "learnings by file" helper surface prior lessons when you edit the
same file again. Only add it when the insight is genuinely tied to a specific file. Skip it for
general/operational lessons.

Delete this comment and the example below when you start your real log.
-->

## 2026-01-15. Absence of data is not evidence that work did not happen

### Rule: never treat "thing X is missing" (no output, no log row, no ack) as "action Y never ran" without an explicit positive completion signal. Silence is unobservable, it cannot distinguish "blocked", "slow", "missing", or "complete".

- incident: three independent systems each read their own local silence as proof the work failed. Each
  was right about its own missing signal and wrong about the cause. the real root was a fourth class of
  silence (a blocked prompt) that no output-derived signal could see.
- why: passive absence is consistent with too many world-states. only a positive ack (a returned id, a
  re-read of the written value) narrows it down.
- guard: design hand-offs so completion is OBSERVABLE, not inferred. return an id, re-read the write,
  require an explicit done-signal.
tags: #observability #debugging #async #absence-is-not-evidence

---
