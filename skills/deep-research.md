---
name: deep-research
description: >
  Multi-phase structured research pipeline with citation tracking, evidence persistence, and knowledge-graph-native output. Use when the user asks for "deep research", "comprehensive analysis", "literature review", "research report", "state of the art on", "structured research pipeline", "multi-source investigation", or wants a citation-tracked report saved to the knowledge graph. Different from a single-pass web-search lookup (quick answers). this skill is for multi-phase work that needs evidence persistence, claim-level verification, and entity cross-references in the knowledge graph. 4 mode tiers (quick / standard / deep / ultradeep) with 3-8 phases each. Outputs to `pages/Research___YYYY-MM-DD___[topic-slug].md` with auto-created `Entity/` and `Source/` cross-link pages.
trigger: deep research, comprehensive research, literature review, research report, state of the art on, structured research pipeline, multi-source investigation, research and save to the graph, deep dive on
---

# Deep Research (knowledge-graph-adapted)

Adapted from `199-biotechnologies/claude-deep-research-skill` (upstream Boris Djordjevic, MIT, ~633★). Verdict on upstream: PARK + adapt. the methodology is sound but its install pattern (`git clone main` + `cp -r`) violates the security-first no-unpinned-bootstrap rule (no unpinned bootstrap, no main-branch clones). This file is the in-tree adaptation. no clone, no external script fetching.

**Distinguishes from a single-pass web-search skill**: a single-pass search skill is for quick "what's the latest on X" questions. This skill is multi-phase with critique/refine cycles and persistent evidence trails. If the question takes <5min and a single search settles it, route to the single-pass skill. If it takes >10min and needs synthesis across sources, route here.

## Decision tree

```
Request analysis
├── Simple lookup?              → STOP: route to a single-pass web-search skill or WebSearch
├── Debugging?                  → STOP: use standard tools
└── Complex multi-source needed → CONTINUE

Mode selection
├── Initial exploration         → quick    (3 phases, 2-5 min)
├── Standard research           → standard (6 phases, 5-10 min)  [DEFAULT]
├── Critical decision           → deep     (8 phases, 10-20 min)
└── Comprehensive review        → ultradeep (8+ phases, 20-45 min)
```

If it's unclear which mode, default to **standard**. Surface the mode pick to the operator in 1 line before starting (e.g. "running standard, will upshift to deep if scope expands").

## Phase pipeline

| # | Phase | Quick | Std | Deep | Ultra |
|---|-------|-------|-----|------|-------|
| 1 | SCOPE. restate the question, list assumptions, define out-of-scope | ✓ | ✓ | ✓ | ✓ |
| 2 | PLAN. decompose into 4-8 sub-questions, plan source classes | – | ✓ | ✓ | ✓ |
| 3 | RETRIEVE. pull evidence (web-search primary, browser-automation for JS-render/auth-gated, WebFetch fallback) | ✓ | ✓ | ✓ | ✓ |
| 4 | TRIANGULATE. cross-check claims across ≥3 cluster-independent sources | – | ✓ | ✓ | ✓ |
| 4.5 | OUTLINE REFINEMENT. re-org structure based on what evidence actually exists | – | ✓ | ✓ | ✓ |
| 5 | SYNTHESIZE. write findings with inline citations | – | ✓ | ✓ | ✓ |
| 6 | CRITIQUE. adversarial pass: weakest claim? sourcing gaps? steel-man counter-thesis? | – | – | ✓ | ✓ |
| 7 | REFINE. fold critique into v2 | – | – | ✓ | ✓ |
| 8 | PACKAGE. write to the knowledge graph with cross-links | ✓ | ✓ | ✓ | ✓ |

Phases 3-5 are an evidence loop per sub-question, NOT strict sequential gates. If a finding falls apart at TRIANGULATE, drop back to RETRIEVE.

## Phase details

### Phase 1: SCOPE

Output a 4-line scope block before any retrieval:
```
QUESTION: <restated in your own words>
ASSUMPTIONS: <2-4 bullets. what's taken as given, flag any that materially change the answer if false>
OUT-OF-SCOPE: <1-3 bullets. what we're NOT answering>
SUCCESS CRITERIA: <what makes the report useful>
```

If high-materiality assumptions exist (e.g. "assuming a specific regulatory interpretation as of a 2024 ruling still holds"), surface them in the final report's Introduction. not buried.

### Phase 2: PLAN

Decompose into 4-8 sub-questions. Each sub-question gets:
- **Source classes expected** (regulatory document / academic paper / on-chain data / news / industry report / first-party project doc)
- **Cluster independence target**. how many cluster-independent sources before a claim is trustable. Default 3.
- **Verification primitive**. what makes a claim verifiable for THIS sub-question (a regulation-number lookup / an on-chain query / cross-source date triangulation / first-party confirmation)

### Phase 3: RETRIEVE

Source order of preference:
1. **A web-search MCP** (e.g. `mcp__exa__web_search_exa`, `mcp__exa__crawling_exa`). primary. Cheap per-query cost.
2. **A browser-automation MCP** (for JS-rendered, auth-gated, or structured-extraction targets. region-specific dashboards or regulator pages that block a plain crawler).
3. **WebFetch**. fallback for known-good static pages.
4. **The local knowledge graph**. `recall` against the recall index + direct read of `memory/Context/` / `knowledge/` / your graph export. Always run BEFORE going external (brain-first per CLAUDE.md).
5. **Domain MCPs** (academic search, docs, clinical trials, etc.). if domain-relevant.

For each retrieval, capture:
- URL or local path
- Fetch timestamp (publication date if available)
- Source type (web / academic / regulatory / on-chain / industry-report / first-party)
- Authors (if attributable)
- Credibility prior (0.0-1.0). based on source class and provenance
- Verification status: `unverified` (just fetched) → `verified` (cluster-independent confirmation) → `conflicted` (sources disagree, flag for Phase 4)

### Phase 4: TRIANGULATE

For every load-bearing claim:
- Are there ≥3 cluster-independent sources?
- Are dates consistent across sources?
- Do regulatory citations resolve in official registries? On-chain claims resolve on a block explorer (e.g. Etherscan) / analytics site (e.g. DeFiLlama)?
- If a conflict is found → flag it, surface it in the Limitations & Caveats section, do NOT silently pick a side.

### Phase 4.5: OUTLINE REFINEMENT

Re-organize before SYNTHESIZE based on what evidence ACTUALLY exists. The original PLAN was a hypothesis; the outline now reflects the evidence shape. If a sub-question turned out unsupportable, demote it to Limitations.

### Phase 5: SYNTHESIZE

Write findings with inline citations. Format per finding:
```
- finding-claim:: <one-sentence claim>
- confidence:: high | medium | low
- sources:: [[Source/<id>]] [[Source/<id>]] [[Source/<id>]]
- ## Evidence
  - <2-4 paragraphs of evidence with inline citation refs>
```

Quality bar:
- ≥10 sources for the full report
- ≥3 cluster-independent per major claim
- All factual claims cited immediately
- Prose-first (≥80% prose, not bullet-spam)
- No fabricated citations. verify every URL still resolves before locking the report

### Phase 5.5: SOURCE-GROUNDING GATE

Lifted from a deep-research checklist (`affaan-m/everything-claude-code`). The quality bar above is a target; this is the hard pass/fail before anything leaves the skill. Run it as an explicit gate, not a vibe check.

Per-claim sweep on the assembled findings:
1. **Every claim sourced**. no asserted-as-fact claim without a `sources::` ref. An unsourced claim = delete or demote to an explicit `(unverified inference)`.
2. **Single-source flag**. any claim resting on exactly one source gets tagged `single_source:: true`. Collect all such claims into a `single_source_claims::` list in the report frontmatter. This list is the explicit handoff to Phase 6 / the Critic (a pre-ship catch, not a post-hoc observation).
3. **Fact vs estimate split**. numbers that are measured/reported stay as-is. Numbers that are extrapolated, modeled, or "directionally" derived get an explicit `(estimate)` marker inline. Never present an estimate with the typographic confidence of a measured figure.
4. **Recency-first**. prefer sources <12mo. Any load-bearing claim resting on a >12mo source gets `date_risk:: <source-date>`.
5. **Gap acknowledgment**. if a sub-question could not be grounded, write it into a `## Open / Ungrounded` section. Do not paper over it with a plausible-sounding unsourced sentence.

The gate fails (block packaging, loop back to RETRIEVE) if: any unsourced asserted-fact remains, OR `single_source_claims::` covers a load-bearing thesis claim with no acknowledgment. The gate passes with `single_source_claims::` populated as long as they are flagged, not hidden.

### Phase 6: CRITIQUE (deep + ultradeep only)

Adversarial pass. Spawn a subagent with this brief (or do inline if <5min):
- Steel-man the OPPOSITE thesis. What would a well-informed skeptic say?
- Weakest claim. which finding has the thinnest evidence?
- Sourcing gaps. where are we relying on a single source?
- Date-stale claims. anything that may have changed in the last 6mo?
- Cluster dependence. sources that look independent but trace to the same primary?

Output: a 5-15 bullet critique. Save as `outputs/raw/agent/research-critique/[topic-slug]-critique.md` if substantive.

### Phase 7: REFINE (deep + ultradeep only)

Fold the critique into v2:
- Strengthen claims where the critique was right
- Add Limitations bullets where the critique was right but research depth doesn't allow a fix
- Push back where the critique was off-base (note the rebuttal in the report)

### Phase 8: PACKAGE (knowledge-graph-native output)

Main page path: `pages/Research___YYYY-MM-DD___[topic-slug].md` (relative to your graph root).

Use the graph's property block format (NOT YAML frontmatter):

```markdown
- type:: [[Research]]
- date-created:: [[YYYY-MM-DD]]
- date-modified:: [[YYYY-MM-DD]]
- mode:: quick | standard | deep | ultradeep
- status:: draft | complete
- source-count:: N
- tags:: #research #[topic-tag] #[topic-tag-2]
- ## Executive Summary
  - <200-400 words>
- ## Introduction
  - ### Scope
    - <restated question>
  - ### Methodology
    - <mode + phase summary>
  - ### Assumptions
    - <high-materiality assumptions>
- ## Findings
  - ### [[Finding/<title-1>]]
    - <inline summary, full content on the linked page>
  - ### [[Finding/<title-2>]]
    - ...
- ## Synthesis
  - <cross-finding insights>
- ## Limitations & Caveats
  - <what we couldn't confirm, conflicting sources, date-stale risks>
- ## Recommendations
  - <if action-oriented>
- ## Bibliography
  - [[Source/<id-1>]]
  - [[Source/<id-2>]]
- ## Methodology Appendix
  - <mode used, sub-questions, source classes, cluster-independence achieved>
```

Per-finding pages at `pages/Finding___YYYY-MM-DD___[finding-slug].md`:
```markdown
- type:: [[Finding]]
- date-created:: [[YYYY-MM-DD]]
- confidence:: high | medium | low
- parent-research:: [[Research/YYYY-MM-DD/topic-slug]]
- sources:: [[Source/<id>]] [[Source/<id>]] [[Source/<id>]]
- tags:: #finding #[topic-tag]
- ## Claim
  - <one-sentence claim>
- ## Evidence
  - <full evidence paragraphs with inline citations>
- ## Counter-evidence
  - <if any, even brief>
```

Per-source pages at `pages/Source___YYYY-MM-DD___[source-slug].md`:
```markdown
- type:: [[Source]]
- url:: <https://...>
- source-type:: web | academic | regulatory | on-chain | industry-report | first-party
- date-published:: [[YYYY-MM-DD]] OR undated
- date-accessed:: [[YYYY-MM-DD]]
- authors:: <names if attributable>
- credibility:: 0.0-1.0
- verification-status:: unverified | verified | conflicted
- tags:: #source #[topic-tag]
- ## Summary
  - <2-3 sentences>
- ## Quoted excerpts
  - <exact quotes used in findings, verbatim>
```

Per-entity stubs at `pages/Entity___[Name].md` (auto-create on first reference):
```markdown
- type:: [[Entity]]
- date-created:: [[YYYY-MM-DD]]
- aliases::
- source-research:: [[Research/YYYY-MM-DD/topic-slug]]
- tags:: #entity #auto-created #needs-review
- ## Summary
  - <2-3 sentences from research context>
```

Cross-link rules:
1. Every organization, project, technology, person, or concept in findings → `[[Entity/<Name>]]` syntax. If the page doesn't exist, create a stub.
2. Every finding → linked from the main report's Findings section.
3. Every source → linked from the main report's Bibliography.
4. If a finding references a concept covered in a previous research run → link to that finding page directly.

## Quality gates (run before status:: complete)

- [ ] ≥10 sources, ≥3 cluster-independent per major claim
- [ ] All factual claims cited immediately
- [ ] No placeholders, no fabricated URLs
- [ ] Prose-first (≥80%)
- [ ] All entity references wiki-linked
- [ ] The Bibliography lists EVERY source actually cited
- [ ] The Limitations section honestly enumerates what we couldn't confirm
- [ ] Date-published captured for every source (or "undated" explicit)
- [ ] Regulatory citations cross-checked in official registries
- [ ] On-chain claims cross-checked on-chain (a block explorer / analytics site)

If any gate fails → status remains `draft`, surface the failures in a `- ## Open issues` block at the bottom of the main page.

## When to use / NOT use

**Use:**
- Comprehensive analysis spanning multiple sources (>5 sources expected)
- Technology comparisons requiring structured findings
- Regulatory landscape analysis (multi-jurisdiction or evolving regimes)
- State-of-the-art reviews
- Pre-deal due diligence on a protocol or counterparty
- Literature reviews
- Multi-perspective investigation where conclusions matter to a downstream decision

**Do NOT use:**
- Simple lookups → a single-pass web-search skill or WebSearch
- Debugging → standard tools
- 1-2 search answers → a single-pass web-search skill
- Quick time-sensitive queries → a single-pass web-search skill
- Code review → a code-review skill
- Skill audit → `skill-audit`
- Pre-existing knowledge in your graph → `recall` first

## Hard rules

1. **Brain-first**: ALWAYS run `recall("<topic>")` and check `memory/Context/`, `knowledge/`, your graph export before external retrieval. If we already know the answer or have prior research, surface that, don't regenerate.
2. **Cite or omit**: every load-bearing claim has an inline source citation. If you can't cite it, don't write it.
3. **No fabricated citations**: instant credibility loss + risk of poisoning the graph. Verify every URL resolves before locking.
4. **Prose-first**: bullet-soup is a tell of shallow research. Aim ≥80% prose.
5. **Date everything**: undated sources flagged explicitly, never silently treated as current.
6. **Cluster independence**: 3 sources tracing to the same primary = 1 source. Track upstream.
7. **Surface high-materiality assumptions**: in the Introduction, not buried.
8. **CONFIRM-gate on knowledge-graph writes**: per CLAUDE.md, knowledge-graph writes require the operator's confirmation. After Phase 7 (or 5 in std mode), present the structured output for approval BEFORE writing to the graph. Show: main report path + N finding pages + N source pages + N new entity stubs.
9. **Heavy retrieval flags cost**: ultradeep mode can burn $0.50+ in web-search auto-queries + browser-automation steps. Surface the estimated cost before running ultradeep.
10. **Honest negatives**: if research can't reach a confident answer, the report says so. Do NOT pad to look complete.

## Out of scope

- Skill audit (use `skill-audit`)
- App-level OWASP / STRIDE (use a CSO skill)
- Single-fact lookups (use a single-pass web-search skill or WebSearch)
- Pre-existing knowledge retrieval (use `recall`)
- Code-context research (use a docs MCP such as `mcp__plugin_context7_context7__query-docs`)

## Future ship: verify_citations.py

The upstream had a `scripts/verify_citations.py` that programmatically resolved every cited URL and flagged dead links. Not yet ported. Intended location: `scripts/verify_citations.py`. Until shipped, do the URL-resolve check manually as part of the quality gates.

## Source archive

The original SKILL.md is archived under `sandbox/archive/skill-files/`. Verdict during the audit: PARK + adapt. Adaptations made for this stack:

1. **Output path**: an Obsidian vault path → a knowledge-graph `pages/Research___...md` path
2. **Frontmatter format**: YAML → the graph's `key:: value` property block
3. **Wiki-link namespacing**: generic `[[Entities/Name]]` → namespaced `[[Entity/Name]]` matching the graph's namespace structure (`Source/`, `Finding/`, `Entity/`, `Research/`)
4. **Install pattern**: removed `git clone main + cp -r` (a Chain C violation). Methodology inlined here, scripts deferred.
5. **Retrieval order**: added web-search-primary + browser-automation-secondary + a brain-first preamble per the MCP stack
6. **CONFIRM-gate**: added hard rule 8. knowledge-graph writes pause for confirmation per CLAUDE.md
7. **Trigger scoping**: dropped bare "research" (collides with a single-pass skill); kept "deep research" / "literature review" / "comprehensive research" / etc.
8. **Cost flagging**: added hard rule 9 (estimate cost before ultradeep)
9. **Dropped the Obsidian-Dataview-compatibility clause** (irrelevant to the target graph)
