---
name: reconcile-extraction
description: Check that a scan, scrape or aggregator pull is complete and in the right unit by reconciling what the parser produced against a number the source states about itself, instead of trusting the parser's own row count.
trigger: scan found fewer rows than the site says, scraper count looks low, two sources disagree by 10 to 15 percent, is this scan complete, can we trust this aggregator column, parsed rows vs stated total, field name says one unit
---

# Reconcile an extraction against a control total

Use when a parser, scraper or API pull has produced a number or a table and someone is about to build on it. The parser's own row count only says how many rows matched its pattern. A control total from outside the parser says how many rows exist.

Two cases with the same shape (numbers are illustrative):
- A careers-page scan matched only UUID-style posting ids and read 576 of the 847 roles the site listed. Every posting from one job-board platform used numeric ids, so all of them were dropped, including every role at several companies.
- An aggregator endpoint named a field `peggedEUR` but returned its USD value. One coin read 21.5M EUR when the issuer's own figure was 3.4B EUR, and most of the "sources disagree by 10 to 15 percent" gaps turned out to be that unit error.

In both, the output looked fine until something independent was compared with it.

## Steps

1. **Name the extraction and its control.** A control is a number the source states about itself that the parser did not produce: a per-company or per-board count on the page, a total banner, an API `total` field, an issuer's published supply, a filer's stated total. If the source states none, say so and downgrade the claim from "scan" to "sample".
2. **Count what the parser produced, grouped the way the control is grouped** (per company, board, chain, currency), not only overall. A matching grand total can hide offsetting gaps, and a per-group table points at the missing group first.
3. **Diff per group, parsed against stated.** A group with 0 parsed and a nonzero stated count is a format miss (id shape, pagination, a platform-specific selector). A group off by a steady ratio is a unit or basis miss (value against native units, circulating against total supply).
4. **Diagnose the cheapest cause first.** For a count gap, list the raw ids or links of one missing group and compare their shape with the parser's pattern. For a value gap, take one item and compare it with the primary figure for that item, naming the unit and the basis on both sides.
5. **Fix the parser or the conversion and re-run.** Every group has to reconcile to the control: exactly for counts; for values, within a named tolerance with a stated reason for any residual (timing, rounding).
6. **Put the coverage in the output.** Print "parsed N of stated M, groups reconciled k of g" at the top of the result and keep the per-group table in the run folder, so the next reader sees how complete it is.

## Caveats

- A control from the same system that feeds the parser (same API, same cache) is not independent. Prefer the page's rendered count or the primary document.
- Check the control's date. A cached count can lag the data by a day.
- Never close on "close enough" without naming the residual and its cause.
- A field name that suggests a unit (`peggedEUR`, `supply`, `value`) is unverified until one item has been checked against its primary source.
- Basis words (circulating, total, active) belong in a glossary entry once they have been misread once: `knowledge/glossary.example.md`.

## Tools and output

Tools: HTTP fetch of the page or API, a short Python or jq grouping step, one spot check against the primary document.
Output: a three-line coverage header, a per-group diff table, and a one-line note on the fix.

Related but different: `skills-shared/test-before-bulk/SKILL.md` tests a write on a few rows before a bulk run; this skill tests an extraction's completeness and units.
