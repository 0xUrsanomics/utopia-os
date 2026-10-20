# Content gates

Anything that leaves the stack for a human audience runs a scripted check BEFORE it ships. Prose rules live in `skills-shared/anti-ai-slop/SKILL.md`; this doc says which script runs on which surface, and why there is more than one.

## The one idea: different failures need different gates

| Failure | Question | Gate | Needs a voice sample? |
|---|---|---|---|
| **AI slop** | Does this read machine-generated? | `scripts/pipeline/external_slop_gate.py` | No. Works in any register. |
| **Insight-shaped filler** | Does this sentence survive being paraphrased? | `scripts/pipeline/paraphrase_test.py` | No. Advisory. |
| **Structural repetition** | Do the same sentence or paragraph shapes repeat? | `scripts/pipeline/structure_repetition.py` | No. |
| **Voice drift** | Does this sound like the OWNER specifically? | your voice gate, built from `skills-shared/voice-profiler/SKILL.md` | Yes. Anchors on a real sample of the owner's writing or speech. |
| **Imported-claim conflict** | Is a load-bearing claim pulled from memory actually true against the primary source? | `scripts/pipeline/imported_claim_gate.py` | No. Flags shapes; the agent verifies. |
| **Cross-day device recurrence** | Have I used this same rhetorical move across recent posts? | `scripts/pipeline/device_recurrence_tracker.py` | No. Semantic, per-agent ledger, advisory. |
| **Cross-document drift** | Do the docs in one pack agree with each other? | `scripts/pipeline/doc_consistency_check.py` | No. |

The mistake to avoid: running the VOICE gate on a formal document. A client deck, a business email and a CV are formal on purpose. Scoring them against the owner's casual voice sample would flag good formal writing as "not you", and most of them have no sample to score against anyway. So:

- **Lexical gate: universal.** Every external artifact runs it.
- **Voice gate: only where the artifact is meant to be the owner's own voice** (posts, threads, opinion longform).

## `external_slop_gate.py`: the universal lexical gate

No voice sample, stdlib only, register-agnostic. `--file <path>` or `--stdin`. Exit 0 = clean, 1 = HARD hit (block), 2 = usage. `--json`, `--selftest`.

The precision split is deliberate, so a real professional document is not falsely blocked:

- **HARD (exit 1, block):** em or en dash; unambiguous AI tells ("delve", "tapestry", "testament to", "it's worth noting"); assistant openers ("Sure!", "Of course", "As an AI", "In today's"); any claim listed in `knowledge/retracted-claims.json` (see below). With `--cv`: also CV and cover-letter filler ("I am excited to", "proven track record", "results-driven", "detail-oriented").
- **WARN (printed, never blocks):** words that are fine in formal register ("robust", "comprehensive", "streamline") plus structural tells: participial tails, "from X to Y" framing, "not just X but Y", a rhetorical question followed by its answer, three or more colons used as connectors, inline-header lists that restate their label, title-case H2+ headings. The structural tells are adapted from pstack `unslop` (github.com/cursor/plugins, MIT).

Pass `--cv` for CVs and cover letters.

### Retracted claims are hard blocks

A correction recorded only as a text lesson has to be remembered at copy time, and an old draft copied forward will not remember it. So a claim that was shown wrong and had already appeared in an outbound artifact gets a row in `knowledge/retracted-claims.json`. The gate HARD-blocks any match in scope, whichever stale draft the text came from. Format and entry rules: `knowledge/retracted-claims.example.json`. `skills/save/SKILL.md` adds the row when the correction happens.

## Surface routing

| External surface | Lexical gate | Voice gate |
|---|---|---|
| CV, cover letter | `external_slop_gate.py --cv` | none (formal) |
| Business or cold email | `external_slop_gate.py` | none (formal) |
| Client or pitch deck copy | `external_slop_gate.py` | none (formal) |
| Social post or thread | `external_slop_gate.py` | yes, if posted as the owner |
| Longform article | `external_slop_gate.py` + `paraphrase_test.py` + `structure_repetition.py` | yes, if posted as the owner |
| Brand content (company account) | `external_slop_gate.py` | none (brand register) |
| Memo, client doc, published page | `external_slop_gate.py` on the final text | none unless owner-voiced |

**Packs of documents.** When two or more documents ship together (CV plus cover letter plus form answers, a memo plus an annex, a proposal pack), also run `python3 scripts/pipeline/doc_consistency_check.py DOC DOC ... --auto` (contact details, version labels). For packs with key numbers or terms, add `--facts facts.json` (expected values in every doc; forbidden stale values, old names, retired claims; exit 1 = FAIL). The slop gate checks one file; this checks the SET. When writing regex facts, bound windows with `[^.(\n]{0,N}` so a match cannot cross a sentence, a parenthetical or a table cell.

Visual design (decks, landing pages) is a separate axis and not covered here. This doc is the COPY side.

## `imported_claim_gate.py`: the factual-import flag

A third axis, separate from slop and voice: not "does it read like AI" but "is a load-bearing FACT true". It applies conflict-activated verification (arXiv 2608.16515): the costly errors tend to hide in claims IMPORTED from memory or a harvested summary and trusted without a fresh primary check. Typical shapes: "law X made Y legal" when the law only set up a licensing regime; "there is one licence" when there are five.

- Stdlib scanner, `--file`, `--json`, `--selftest`. Exit 0 = clean, 3 = flagged. ADVISORY, never an auto-block.
- It flags claim SHAPES and does not verify: LEGAL_STATUS ("made X legal", named acts and rules), ENTITY_COUNT ("the first", "N issuers"), EXISTENCE ("the only way", "no tool for"). For each flag, the agent checks the claim against the PRIMARY source before shipping and blocks only on a real conflict.
- Use it for factual drafts (a public claim). Skip it for faithfulness tasks (quoting what a document says means trusting the document).
- It is noisy on regulation-dense drafts, because it keys on common verbs like "requires". That bias is deliberate: a missed false claim costs more than triage time. Triage the flags; the count is not a failure score.

## Anti-gaming (non-negotiable)

The gate is not a detector to beat. NEVER inject noise, typos or awkwardness to pass it. A hit means there is a real tell: cut it and say the thing plainly. Third-party AI detectors are diagnostics, never the objective.

## Wiring it in

- Every content-producing skill runs the lexical gate as its last step before handing a draft over.
- A one-line rule in `CLAUDE.md` makes it universal: "any artifact leaving for a human audience runs `external_slop_gate.py` (add `--cv` for CVs) before ship; owner-voiced surfaces also run the voice gate."
- The outbound send path has its own last-line dash guard: `scripts/security/emdash_send_guard.py` (see `docs/security-gates.md`).
