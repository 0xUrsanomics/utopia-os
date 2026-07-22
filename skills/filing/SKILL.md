---
name: filing
trigger: file this, archive this, where does this go, file intake, drain the inbox, canonical home, filing
description: Give received artifacts a canonical home AND an index entry so recall can reach them. Intake, placement, indexing. Not a filesystem beautification pass.
---

# filing

## Why this exists

A whole class of confident false negatives has one root cause. In one session, four separate
"we don't have that" assertions were all wrong: a log, two record entries, and a batch of scanned
reports. Every one existed. The cause was not carelessness. It was that **hundreds of files sat in
the inbox referenced by zero scripts and indexed in zero recall sources.**

Artifacts with no canonical home and no index produce confident false negatives, which is
the most expensive kind of wrong: it looks like an answer.

## The one rule that matters

**The index is the point, not the tidy tree.** Moving a file to a prettier path fixes
nothing on its own. What failed was RECALL. So:

- Every artifact gets an `archive/INDEX.jsonl` row **even when it cannot be classified**.
- `archive/unsorted/` is a first-class destination, not a failure state.
- An indexed unsorted file is findable. A perfectly-filed unindexed file is not.

If you ever have to choose between placing something correctly and indexing it at all,
index it.

## Procedure

### 1. Dry run first, always

```bash
python3 scripts/pipeline/file_intake.py --verbose
```

Dry run is the default and `--apply` is required to write anything. Read the subject and
label distribution before applying. If the distribution looks wrong, the signatures are
wrong; fix `SIGNATURES` / `OCR_SIGNATURES` in the script rather than hand-filing.

### 2. Apply

```bash
python3 scripts/pipeline/file_intake.py --apply           # COPY into archive/ + index
python3 scripts/pipeline/file_intake.py --apply --drain   # MOVE (inbox becomes staging)
```

Copy is the safe default. Use `--drain` only once a copy run has been eyeballed, because
that is what turns the inbox from a store into a staging area.

### 3. Confirm, then index into the recall store

```bash
wc -l archive/INDEX.jsonl
python3 scripts/memory/vector_brain.py index-append --paths archive/INDEX.jsonl
```

An artifact is only genuinely filed once `recall` can reach it. Skipping this step
reproduces the exact defect this skill exists to fix.

## How classification works, and its real limits

Three tiers, cheapest first. Every tier records a **confidence** and a **basis** string, so
a low-confidence placement stays visibly provisional instead of pretending to be filed.

| tier | applies to | signal |
|---|---|---|
| filename | everything | 13-digit epoch-ms prefix gives a reliable arrival date even when content is unreadable |
| text extract | pdf / md / txt / html / docx | `pdftotext -layout`, then exact subject signatures |
| OCR | jpg / png | tesseract psm 3, then OCR-TOLERANT signatures |

**OCR signatures are deliberately not the text signatures.** Photos of printouts OCR badly.
A scanned report's brand header can come back garbled, so exact brand matching can score
**0 of 7** on files you know belong to that class. Matching instead on domain vocabulary
(the field terms that report always contains) with a minimum of N distinct terms recovers
most of them. OCR-derived confidence is capped below text-derived confidence because the
input is noisier.

**Known limits, stated so nobody over-trusts the output:**
- A large share of a typical corpus is photos with no recoverable text. Most stay `unsorted`.
  That is honest, not a bug. They are still dated and indexed.
- Voice notes and video are **not** transcribed at intake. Filing places and indexes;
  extraction stays a per-domain concern (a separate domain-specific extractor's job).
- Signatures are hand-written and will miss new artifact classes. When you notice a miss,
  add a signature. Do not hand-file around it, or the next batch misses too.

## Hard rules

1. **Never delete.** Retention is option A, keep everything. Disk is cheap, wrong deletions
   are not. Revisit only once the index shows what is actually dead.
2. **Never overwrite.** An existing destination is refused and counted, not clobbered.
3. **Every applied op appends to `archive/OPERATIONS.jsonl`**, so a bad run is undone by
   replaying it backwards.
4. **The binaries do not enter git.** `archive/` is gitignored except `INDEX.jsonl`, which
   IS committed. Backups cover the binaries; git covers the index.
5. **Worktrees are out of scope for this skill.** Orphaned worktree dirs with no git
   registration have no `git worktree remove` path; deleting them is a bare `rm -rf` with no
   undo. That is a user-gated decision, not an intake operation.
6. **Do not restructure `memory/`, the knowledge graph, or the `outputs/` review pipeline.**
   This skill sits UNDER those conventions.

## Adding a subject

Edit `SIGNATURES` (text) or `OCR_SIGNATURES` (images) in
`scripts/pipeline/file_intake.py`. Order matters, first match wins, so put specific patterns
above generic ones. Then re-run a dry run and check the distribution moved the way you
expected before applying.
