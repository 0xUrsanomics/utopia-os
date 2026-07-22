---
name: test-before-bulk
description: Mandatory gate before any batch operation that writes to a CRM, a knowledge graph, a spreadsheet, a vector index, or any other durable store. Test 3-5 first, fix the SKILL not a one-off script, then bulk-execute with throttling and a kill switch.
trigger: bulk, batch, run X for all, backfill, mass update, populate Y for everyone, run on the whole list, sync everything
---

# Test Before Bulk Convention

Lifted from a shared brain-conventions repo as a convention applied across CRM, knowledge-graph, spreadsheet, vector-index, and any other durable-write skill. **Never run a batch operation without testing one first.**

## Tone & Voice

Adversarial convention. applies as a gate, not a suggestion. **NON-NEGOTIABLE**: if the user says "just run it on all 170" without a test-on-1 step, push back. The test-first discipline exists because durable writes (CRM rows, knowledge-graph pages, vector embeddings) compound errors at scale and are hard to unwind. One failed bulk = hours of cleanup.

## Output format

The skill enforces a procedural gate, not an artifact. The outcome is:
1. Confirmed-good output from test-on-1 (artifact pinned + diffed against the expected format)
2. Updated skill code/prompt (if the test revealed a bug. fix the SKILL, not a one-off script)
3. Bulk run with throttling + kill switch (e.g. `--limit N` or `--dry-run` first)
4. Post-bulk: spot-check 3 random items from the bulk output to verify the pattern held

## The Process (6 steps)

1. **Read the existing skill first.** Don't write throwaway scripts. If a skill exists for the operation (e.g. a CRM operator, an ingestion processor, a contact extractor), use it. If a skill doesn't exist and the bulk op will be repeated, the right move is to BUILD a skill, not a one-off bash.

2. **Hone the prompt/logic on a single item.** Get the output format right before running anything. If the output structure is wrong on item 1, it'll be wrong on items 2-170.

3. **Test on 3-5 items.** Run in `--test`/`--dry-run`/`--limit 5` mode if available. Don't commit, don't push, don't write to durable stores yet. The 3-5 should span variation (not all the same shape).

4. **Check the work yourself.** Read the actual output for each test item. Quality pristine? Titles clean? Entities extracted correctly? Backlinks created? Format matches the schema? Currency / date / numeric formats right?

5. **Fix what's wrong in the SKILL, not in a one-off script.** The skill is the durable artifact. A bash patch is throwaway. If the skill has a bug, fix the skill so the next bulk run inherits the fix.

6. **Only then: bulk execute.** With throttling (rate-limit per minute), commits every N items (so partial failures are recoverable), and a kill switch (Ctrl+C cleanly aborts mid-run, not a corrupt half-write).

## Why This Matters

One bad bulk run can write 170 mediocre pages that are harder to fix than to do right the first time. The marginal cost of testing 5 first is near zero (~5 min). The cost of cleaning up a bad bulk run is enormous (potentially hours of grep + manual edits + re-runs).

Real incidents this guards against:
- **A spreadsheet batch append**: a bulk append misplaced data because a secondary block caused column drift. Discovered only after multiple rows had wrong-column data. Fix: always write with an explicit column range, not a bare append.
- **A tool-annotation batch**: the initial pass had the wrong tier on ~25% of items because the skill prompt was ambiguous. Caught only because 3 were test-run first; without test-before-bulk it would have shipped a quarter of the tagging wrong.

## Applies To

- **CRM batch enrichment** (spreadsheet row updates across hundreds of contacts)
- **Knowledge-graph page backfills** (creating 50+ pages from a CSV/JSON source)
- **Vector-index backfill operations** (reindex with new metadata fields)
- **Any cron job being deployed for the first time**: the first run = test mode; switch to live only after manual review of the first 5 outputs.
- **Any new skill being run at scale**: the first 5 invocations of a new skill = test mode by default.
- **Ingestion / harvest batches**: when processing >5 items in one run.

## Anti-Patterns (catch yourself here)

- ❌ Writing a bash/python script from scratch instead of using an existing skill.
- ❌ Running 170 items without testing 5 first because "it should work."
- ❌ Skipping entity extraction or backlink propagation "as a separate step later." (Later never comes; the data is now stale at scale.)
- ❌ Committing bulk work without reading any of the output.
- ❌ "I'll fix the quality later". see the incidents above for what "later" actually costs.
- ❌ Testing with all-similar items (5 records all of the same shape). Test diversity = test surface area.

## Pre-flight checklist (paste into a scratch note before a bulk run)

```
Bulk operation: <name>
Skill used: <path/to/skill.md>  ← if blank, STOP and use/build a skill
Test items run: <list of 3-5 IDs>
Test outputs reviewed: [ ] yes
Issues found in test: <list, or "none">
Fixes applied to SKILL (not script): [ ] yes / n/a
Throttle: <X items/minute>
Commit cadence: <every N items>
Kill switch verified: [ ] yes
Estimated total items: <N>
Estimated runtime: <duration>
```

If any field is unfilled or any checkbox is unchecked, do NOT bulk execute.

## Cross-references

- Origin: a shared brain-conventions repo (doc-mined).
- Linked from: any skill that writes in bulk (a CRM operator, an ingestion processor, a discovery pipeline, a contact extractor, a library updater).
