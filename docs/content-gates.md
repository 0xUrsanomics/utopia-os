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
| **Orphan reference after a cut** | Does the TL;DR, opening or closing still mention something cut from the body? | `scripts/pipeline/orphan_ref_check.py` | No. Compares against the pre-cut copy, advisory. |

The mistake to avoid: running the VOICE gate on a formal document. A client deck, a business email and a CV are formal on purpose. Scoring them against the owner's casual voice sample would flag good formal writing as "not you", and most of them have no sample to score against anyway. So:

- **Lexical gate: universal.** Every external artifact runs it.
- **Voice gate: only where the artifact is meant to be the owner's own voice** (posts, threads, opinion longform).

## `external_slop_gate.py`: the universal lexical gate

No voice sample, stdlib only, register-agnostic. `--file <path>` or `--stdin`. Exit 0 = clean, 1 = HARD hit (block), 2 = usage. `--json`, `--selftest`.

The precision split is deliberate, so a real professional document is not falsely blocked:

- **HARD (exit 1, block):** em or en dash; unambiguous AI tells (`delve`, `tapestry`, `testament to`, `it's worth noting`); assistant openers (`Sure!`, `Of course`, `As an AI`, `In today's`); any claim listed in `knowledge/retracted-claims.json` (see below), matched on its exact pattern or, when the row has a `concept` list, on a reworded copy where every concept group appears in one sentence. With `--cv`: also CV and cover-letter filler (`I am excited to`, `proven track record`, `results-driven`, `detail-oriented`).
- **WARN (printed, never blocks):** words that are fine in formal register ("robust", "comprehensive", "streamline") plus structural tells: participial tails, "from X to Y" framing, "not just X but Y", a rhetorical question followed by its answer, three or more colons used as connectors, inline-header lists that restate their label, title-case H2+ headings. The structural tells are adapted from pstack `unslop` (github.com/cursor/plugins, MIT).

Pass `--cv` for CVs and cover letters.

### Structural checks (line-numbered, can block)

| Check | Blocks when | Warns when |
|---|---|---|
| **Antithesis** ("users, not products", "not X but Y", "isn't X. It's Y", "less X, more Y") | a hit of 12 words or fewer, with no digit, sits in a headline, a TL;DR bullet, the first sentence of a paragraph, or the last sentence of a section | anywhere else (body), or it carries a figure, or (tweets) it is the two-sentence form |
| **Staccato** (3 or more sentences of 6 words or fewer in a row, one paragraph) | any run, prose | tweet register (`--tweet`, or `1/ 2/` numbering in the text) |
| **Opinion marker** ("my reading/read/view/opinion/bet/guess/take/pick is", "my read:", "I read this as") | count over max(1, prose words / 1500), or 2 or more in one section | one marker, or under the density |

- **Not counted:** parentheticals, quoted spans, blockquote lines, tables, code, frontmatter, and anything below a `<!-- not for posting -->` marker. A sentence with a digit never breaks a staccato run (stat readouts).
- **Owner-verbatim escape:** `>` lines are the owner's own words. A `>` line in the text is skipped. A sentence found in a `>` line of `--verbatim FILE` is exempt and printed as `verbatim-exempt`. With `--file`, `verbatim-approved.md`, `interview-quotes.md` and `interview.md` beside the file load on their own. When the owner approves a line in chat, add it to the run's `verbatim-approved.md` as a `>` line ending with the message id. Keep it out of `interview-quotes.md` if a voice gate scores against that file. Limit: the message id is self-attested.
- **Internal digests** sent only to the operator can pass `--structural-warn`: hits print and never block. It does not downgrade rejected phrases.
- **Callers list hits through `hard_reasons()`**, so a new check shows up in their messages and override logs without another edit.
- **Density did not separate good from bad.** On the calibration set, antithesis density in published pieces did not separate good writing from bad, so density is reported and only prominent, slogan-length hits block.
- **Still not caught:** reversals with no negation word, "in my view", rhetorical-question pivots, antithesis split across a paragraph break, and staccato made of 7+ word sentences.

### Copy-edit checks

Added after a second-model copy-edit review caught issues in a draft the gate had passed.

| Check | Rule | Verdict |
|---|---|---|
| **Aphorism closer** | a `##` section whose last paragraph is exactly two sentences of 8 words or fewer, no digit, with a turn (negation, a pivot word such as but/later/first, a comparative in the second, or an equal-length pair). A cue list, not real reversal detection. | BLOCK at 3 or more sections in one piece; WARN at 1 or 2, and in tweet register. Owner-verbatim pairs are exempt. |
| **Unused term** | "which/what I (will) call X", "I will call it X", "(X from here / for short / hereafter)" where X is capitalised, quoted or emphasised and never appears again. A definitional cue is required, so "I'll call Sarah on Monday" is ignored. | BLOCK |
| **Forward reference** | "(same report)", "same source", "the report above", "ibid" with no named source earlier in the same section ("above" looks back over the whole text) | WARN |
| **Stray contractions** | 1 to 3 contractions in a text of 1,500+ prose words that otherwise has none | WARN |
| **One word, two spellings** | hyphen variants (start-up/startup) and -ise/-ize (tokenised/tokenized) in one text | WARN |
| **Hedge drift** | the same percentage hedged ("about 72%") in one place and bare in another; range ends skipped | WARN |

Spelling and hedge drift only warn because a wider run over CVs, cover letters, tweets and briefings found legitimate pairs (presale vs pre-sales are different words) and the same figure describing two quantities. `--structural-warn` downgrades the copy-edit blocks too. Still not caught: mixed metaphors, non sequiturs, a back-reference to the wrong source, dangling citations, single-sentence kickers.

### Rejected phrases are hard blocks

Phrases the owner has rejected in their own voice (for example "needless to say" or "it goes without saying") go in `knowledge/rejected-phrases.json` (start from `knowledge/rejected-phrases.example.json`, or point `$AGENT_REJECTED_PHRASES` at your file). Every occurrence blocks, with no quota, which overrides the opinion-marker quota for the listed phrases. Only `>` lines in the text and sentences found in `>` lines of `verbatim-approved.md` are exempt; `interview.md` is not. No file means the check is off and the gate prints a note saying so. A file that exists but cannot be read, or lists no phrase, blocks every scan: a check that ran nothing is not a pass.

### Retracted claims are hard blocks

A correction recorded only as a text lesson has to be remembered at copy time, and an old draft copied forward will not remember it. So a claim that was shown wrong and had already appeared in an outbound artifact gets a row in `knowledge/retracted-claims.json`. The gate HARD-blocks any match in scope, whichever stale draft the text came from. Format and entry rules: `knowledge/retracted-claims.example.json`. `skills/save/SKILL.md` adds the row when the correction happens.

## Surface routing

| External surface | Lexical gate | Voice gate |
|---|---|---|
| CV, cover letter | `external_slop_gate.py --cv` | none (formal) |
| Business or cold email | `external_slop_gate.py` | none (formal) |
| Client or pitch deck copy | `external_slop_gate.py` | none (formal) |
| Social post or thread | `external_slop_gate.py` (`--tweet` for a single post; a `1/ 2/` thread is detected) | yes, if posted as the owner |
| Longform article | `external_slop_gate.py` + `paraphrase_test.py` + `structure_repetition.py` | yes, if posted as the owner |
| Brand content (company account) | `external_slop_gate.py` | none (brand register) |
| Memo, client doc, published page | `external_slop_gate.py` on the final text | none unless owner-voiced |

**Packs of documents.** When two or more documents ship together (CV plus cover letter plus form answers, a memo plus an annex, a proposal pack), also run `python3 scripts/pipeline/doc_consistency_check.py DOC DOC ... --auto` (contact details, version labels). For packs with key numbers or terms, add `--facts facts.json` (expected values in every doc; forbidden stale values, old names, retired claims; exit 1 = FAIL). The slop gate checks one file; this checks the SET. When writing regex facts, bound windows with `[^.(\n]{0,N}` so a match cannot cross a sentence, a parenthetical or a table cell.

**After a cut.** Long pieces get cut late (critic fixes, length trims), and the summary keeps promising what the body lost. Save the pre-cut copy as `<draft>.vN.md`, then run `python3 scripts/pipeline/orphan_ref_check.py <draft>.md`: it warns on each heading or key phrase gone from the body that the TL;DR, the opening paragraph or the last section still mention. Exit 2 means nothing was compared.

**PDF output.** `scripts/pipeline/md_to_pdf.py` (pandoc + weasyprint) deletes the old PDF before rendering and exits 1 if no fresh, non-empty file was written, so a failed render cannot leave last version's PDF looking current.

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
