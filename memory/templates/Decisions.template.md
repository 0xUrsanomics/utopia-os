---
name: Decisions. <OPERATOR_NAME>
description: Architectural & strategic decisions, dated, append-only. Indexed into the vector store.
type: decision
---

# Decisions

> **Template.** Copy to `memory/Decisions.md`. Append-only, dated log of decisions worth not
> re-litigating. Each entry is a block of `key:: value` fields separated by `---`. This file is
> read-on-demand (NOT always-loaded) and indexed into Tier 3, so `recall("<topic>")` surfaces the
> relevant decision when a later conversation touches it. Never rewrite history here, append a new
> entry that supersedes an old one and flip the old one's `status::` to `superseded`.
>
> Entry schema:
> ```
> category:: decision
> user:: <operator-slug>
> date:: YYYY-MM-DD
> context:: <the situation the decision was made in>
> decision:: <what was chosen>
> reasoning:: <why, in one or two clauses>
> status:: active | superseded | reversed
> ```
> Delete this quote-block and the example below when you start your real log.

---

category:: decision
user:: <operator-slug>
date:: 2026-01-15
context:: choosing where operational runtime state lives across a multi-process setup
decision:: single source-of-truth store with one mutator and a change log, over per-process copies
reasoning:: distributed copies drift; a single logged write path with old->new records does not.
  migrate incrementally via a legacy-mirror so un-migrated readers keep working
status:: active

---
