# Regulatory temporal versioning

A retrieval system over rules must return the version that was valid AT the decision date, not the version that is current today. Idea source: arXiv 2608.09393, "Temporal Misgrounding in Legal RAG": static RAG cites the currently valid text instead of the version that applied on the question's date, and a versioned corpus fixed most of that error.

The same failure is easy to have without noticing. A typical case: a structured registry of rule facts verified six months ago drifts away from a prose knowledge file updated last month, and nothing flags the drift.

All rule names, numbers and dates in the examples below are FABRICATED (the fictional Republic of Veridia and its Digital Asset Authority, DAA).

## The convention: every retrievable rule unit carries its own validity metadata

The metadata must travel WITH the chunk. Retrieval returns a chunk, not a whole file, so a top-level "this file is a snapshot" note never reaches a reader who pulled one entry. Each rule entry carries:

- `effective_date`: when the rule took legal effect.
- `as_of`: when THIS entry's facts were last verified.
- `status`: `current` | `amended` | `superseded`.
- `amended_by` / `amends` / `superseded_by`: pointer to the newer or related instrument.

```json
{
  "id": "daa-rule-12-2024",
  "title": "DAA Rule 12/2024, capital requirements for exchanges",
  "effective_date": "2024-07-01",
  "as_of": "2026-03-10",
  "status": "amended",
  "amended_by": "daa-rule-4-2025"
}
```

## The answer rule (the consumer; this is what makes the metadata worth carrying)

When answering a rule question, grounding a content claim, writing a memo, or filling a dashboard panel:

1. **Resolve the version effective at the DECISION date.** "What is the capital floor" in a 2026 context means Rule 12/2024 as amended by Rule 4/2025, not Rule 12 alone.
2. **Check `status` and `amended_by` / `superseded_by` before quoting.** `status: amended` means read both instruments together.
3. **When two sources disagree, the more recently verified wins**: the higher `as_of`. If a prose knowledge file is fresher than the structured registry, it wins on conflict, and the registry gets fixed.
4. **State the `as_of` with any rule claim that could have moved.** A capital floor or a which-agency-supervises fact carries its verification date.
5. **If `as_of` is old relative to the stakes** (a live deal, a public post), flag it and re-verify against the primary source before relying on it.

## Typical temporal traps (fabricated examples, the shapes are real)

- **Amendment read alone.** Quoting the base rule without its amendment gives the pre-amendment answer.
- **Count drift.** "The single licensed venue" when a second venue was licensed later.
- **Bill vs law.** A revision still described as "in the pipeline" after it passed.
- **Supervisor change.** Supervision moved from one agency to another on a date; a question about an earlier period resolves to the earlier agency.

## Where to wire it

- The rule registry (a JSON file with a top-level `temporal_discipline` block plus the per-entry fields above).
- Any answer path that touches rules: a regulatory-monitor job, content gates that check rule claims (`scripts/pipeline/imported_claim_gate.py` flags LEGAL_STATUS shapes), dashboard panels, memos.
- Pairs with `knowledge/evidence-ladder.md`: a rule claim at L2 (pointed at the primary text) still needs its `as_of`.
