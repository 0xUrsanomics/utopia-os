---
title: Glossary. One word, one meaning (example)
status: example
---

# Glossary (example)

Copy this file to `knowledge/glossary.md` and replace the entries with your own. The entries below are fabricated to show the shape.

This is the registry behind a **one word, one meaning** rule: a recurring operational term carries ONE definition, and the agent never swaps in a synonym for variety.

## Entry rules

- **Entry bar: no incident, no entry.** A term earns an entry when it recurs across artifacts AND has already been read two ways by someone. This is not a dictionary of everything you say.
- **One meaning per term.** When the term appears in output, it carries the definition here and no other.
- **Measurements carry their basis.** If a term names a number, the BASIS (method, source, denominator, time bucket) is part of the definition, and it travels with the number in the same sentence or table cell, never in a footnote.
- **Name the look-alike.** Each entry says what the term is NOT, because the failure is almost always two numbers or two states that look the same and are not.
- **Point at where it lives.** Name the script, report or file that produces or consumes the term, so a reader can check it.
- **State machines are not adjectives.** Pipeline states get listed as a set with their transitions.

## Entry format

```
### <term>
**One meaning:** ...
**Not the same as:** ...
**Rule:** ...
**Incident:** what went wrong when it was read two ways.
**Lives in:** the file or script that produces or reads it.
```

---

## Measurement terms

### active users (example)
**One meaning:** distinct accounts that performed at least one write action in the last 30 days, counted from the app's event log.
**Not the same as:** the vendor dashboard's "monthly active users", which counts any session including logged-out page views, and reads about twice as high.
**Rule:** never chart the two on one axis. Label ours "30-day writers (event log)" and say which date range it covers.
**Incident:** an Acme Corp board slide drew both as one series and overstated growth by 40%.
**Lives in:** `reports/build_kpis.py` (the basis caveat in its output is mandatory).

## Pipeline-state terms

### drafted / shipped / posted (example)
**One meaning:** `drafted` = the artifact exists. `shipped` = it left this stack for its destination. `posted` = it is publicly live and has a URL.
**Rule:** three states, never synonyms. A file sitting in an output directory is drafted. Only a fetched URL proves posted.
**Incident:** "posted" counts were read off a directory that no writer ever populated, so the count was always zero and nobody noticed for a month.
**Lives in:** the review gate (`skills/review-gate/SKILL.md`) status frontmatter.

### done (example)
**One meaning:** tested end to end, with the test having actually run.
**Not:** code written, file saved, or "should work".
**Rule:** if the verification did not run, the word is "written", not "done". Cite the level from `knowledge/evidence-ladder.md`.
**Incident:** a scheduled job was reported done when it had been created but had never fired.
**Lives in:** `skills/save/SKILL.md` Step 3.3 (`verified_working::`).

---

## Output type vocabulary

Every substantive file under `outputs/raw/` should carry a frontmatter `type::`. Keep the list of valid types, and whether each is `substantive` (human-facing and fact-checkable), in ONE place: `memory/state/output-types.example.json` shows the shape. Do not copy the list here or into any script. When you emit a new `type::`, add it to the registry in the same change.
