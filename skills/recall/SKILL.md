---
name: recall
description: "Semantic recall across the agent's full knowledge base via the vector_brain index (knowledge-graph pages, knowledge files, memory, reviewed outputs, persona memory). Trigger whenever the user asks 'what do we have on X', 'find me info about Y', 'search memory for Z', 'do we have a note on W', 'recall X', 'remember anything about Y', 'what do I know about Z', or whenever the current conversation needs grounding against prior work you don't have in active context. Use this BEFORE guessing or saying 'I don't have context on that'. the vector brain likely does. Returns ranked semantic matches with similarity scores."
trigger: recall, remember, find, search memory, what do we have on, do we have, what do I know about
---

# Recall. Semantic search across the knowledge base

## Brain-First 5-Step Protocol (MANDATORY before external calls)

Adapted from a brain-first convention. Before using ANY external API (web search, a research MCP, a spreadsheet MCP for re-fetch, social APIs, web fetches) to research a person, company, deal, or topic, run all 5 steps below. The brain almost always has something. External APIs fill gaps, not start from scratch.

### The 5 Steps

1. **Keyword search (FTS5/BM25)**: `vector_brain.py search "<name>" --mode bm25 --top 5`. Catches exact-match acronyms, names, deal IDs.
2. **Semantic query (hybrid RRF, default)**: `vector_brain.py search "<natural question about the entity>" --top 5 --expand-window 1`. Catches related context, synonyms, multi-entity questions. `--expand-window 1` attaches the neighbor chunks (↑/↓) of each match so context split across adjacent chunks (date/outcome/caveat) is not lost.
3. **Read the full page**: for the top promising result, use the `Read` tool on the source file path. Don't act on the 200-char preview alone.
4. **Check backlinks**: for entities that have a knowledge-graph page (a person / a prospect / a deal), use your knowledge graph's backlink lookup to see who references it. Surfaces upstream + downstream context.
5. **Check the timeline**: for entities active in deals or schedules, scan the knowledge-graph journal pages for recent mentions, OR grep the journals for the last 14-30 days.

If ALL 5 steps return empty → THEN escalate to external (web search / a research MCP). When you do escalate, frame the external query around what's MISSING, not from scratch.

### Why This Matters

- The brain has context external APIs don't (the operator's direct observations, meeting notes, deal history, personal relationships, locked-in agreements, etc.)
- External API calls cost money (query quota) and time (latency, context tokens)
- Brain-first lookups make external queries more targeted (you know what's missing, you're filling gaps)
- The user's direct statements (in memory/, knowledge-graph journals, session transcripts) are the highest-authority data. External sources are the lowest. Don't override durable memory with a web summary.
- The pattern protects against the "stochastic guess" failure mode where the model invents facts because it skipped a recall step.

### When to skip the protocol

- Pure world-knowledge questions (capitals of countries, programming syntax) where the brain demonstrably won't have it.
- Real-time data (a current market price, today's news headline) that the brain can't store.
- Trivial conversational turns ("what's 2+2", "thanks") where the protocol overhead exceeds the value.

Default: run the protocol. Skip is the exception, not the rule.

## What this wraps

Invokes `scripts/memory/vector_brain.py search "<query>"` against a LanceDB index built over:
- **Knowledge-graph pages**: chunks from your graph (pages across all namespaces)
- **Knowledge files**: `knowledge/*.md`
- **Memory files**: top-level `memory/*.md` + `memory/Context/*.md`
- **Reviewed outputs**: `outputs/reviewed/**/*.md`
- **Persona memory**: `memory/*.json` entries

No API calls, 100% local embeddings (a sentence-transformers model, e.g. `all-MiniLM-L6-v2` or `BAAI/bge-m3` for multilingual) running locally on GPU.

## When to invoke (proactively)

Trigger recall BEFORE answering any of these patterns, not after:

| User intent | Example phrases |
|---|---|
| **Explicit lookup** | "what do we have on X", "find me the note about Y", "recall X", "search memory for Z", "do we have anything on W" |
| **Contextual grounding** | User mentions a person/deal/project by name you don't immediately recognize in active context |
| **"Did I write that"** | "I think I drafted a brief on X", "didn't we decide something about Y already" |
| **"Who/what is"** | "who is <name>", "what's the status on <deal>", "remind me about <topic>" |
| **Regulatory/precedent** | "have we analyzed <regulation>", "what's our take on <policy>", "did we write about <topic>" |

Don't invoke for:
- General world-knowledge questions (use web search or internal reasoning)
- Current session context (you already have it)
- Purely creative tasks (generate, don't recall)

## How to invoke

```bash
python3 scripts/memory/vector_brain.py search "<query>" --top 5 --expand-window 1
```

Rerank is **default-ON** for this CLI/recall path. Add `--no-rerank` to opt out for speed (see below).

- Use `--top 5` as the default. Bump to 10 for broad "what do we have on..." queries.
- The query should be in natural language, not keyword form. Embeddings work better on phrases.
- Example: `"partner token listing status in market X"` beats `"token listing"`.
- Results return as a ranked list with similarity scores (0-1, higher = more similar).

## Rerank is default-ON. when to add `--no-rerank` (opt out)

A cross-encoder reranker (e.g. `BAAI/bge-reranker-v2-m3`) rescores the top-20 RRF candidates and keeps the top-k by cross-encoder score. It reorders the #1 result a large fraction of the time — the biggest quality-per-keystroke win — and self-reflection-free relevance is exactly what recall needs. Adds ~100-300ms latency. Programmatic `vector_brain.search()` callers are unaffected (the function default stays `rerank_enable=False`); only the CLI/recall path defaults on.

**Keep rerank (default, do nothing) when:**
- The query is short or ambiguous. `"project status"`, `"partner update"`, `"candidate interview"`
- The query spans multiple entities. `"who's handling X for Y"`
- You plan to act on the top-1 or top-2 result directly
- The query mixes languages. the reranker is multilingual and handles this cleanly
- Vector and BM25 disagree: the reranker tiebreaks

**Add `--no-rerank` only when:**
- Latency genuinely matters (a tight real-time loop, not interactive recall)
- You're doing a deliberately raw RRF browse to inspect fusion behavior

**Reading rerank scores:**
Each result shows `rerank: 0.XXX` alongside the RRF score.
- 0.8+ → strong match, the reranker is confident
- 0.3-0.8 → topical but imperfect match
- <0.3 → the reranker is not confident. treat results skeptically, may be no good match in the index

## Query expansion + intent (default-ON)

The recall/CLI path expands one query into up to 4 heuristic variants (original + keyword-core + conjunction decomposition), runs hybrid+RRF per variant, and RRF-merges. Pure recall-union: the original query is always variant[0], variants only add candidates. The header shows `[⊕expand Nq]`. Add `--no-expand` for a raw single-query search (debugging fusion, or when the query is already one tight phrase and you want zero variant noise).

Intent is auto-classified (`[🎯person|timeline|howto|concept]` in the header). v1 only acts on **timeline** intent: it auto-enables `--temporal` (so "latest status of X" / "progress on Y" surface recent chunks without you remembering the flag). Explicit `--temporal` always wins. Other intents are informational labels only in v1. Programmatic `vector_brain.search()` callers are unaffected (function default `expand_enable=False`); only the CLI/recall path defaults on.

## Confidence + stance rank signal (default-ON)

Learnings/Decisions entries carry inline `confidence:: 0.3-0.9` and supersede/reaffirm markers, and those lines are in the indexed chunk text (no reindex needed). The recall path soft-boosts by them post-RRF: a high-confidence reaffirmed non-superseded anchor (factor up to ×1.18) outranks a stale low-confidence one (down to ×0.85), and a chunk whose text says it was *superseded* is demoted ×0.6. Bounded so it nudges, never dominates RRF. Chunks with no `confidence::` marker (most of the corpus) are untouched. The header shows `[★conf N]`, boosted results show `★<factor>`. `--no-confidence-boost` for raw RRF. Function default `confidence_boost_enable=False` (programmatic callers unaffected).

## Graph expansion (default-OFF, opt-in)

`--graph-expand` enables a co-citation boost (soft ×1.08) from **two unioned sources**:
- **#1 entity backlinks**: a pooled chunk whose page is a 1-hop `[[wikilink]]` neighbour of a top hit / query-named entity (your entity subgraph). The map is cached on disk. Tag-hubs + over-degree hubs (>12) are excluded.
- **#2 tag/pillar co-citation**: a pooled chunk sharing a *discriminating* `tags::`/`content-pillar::` value (doc-freq ≤120) with a top hit. This wires your signal/news archive's existing metadata web into recall so a news item carries its topic cluster, not just its headline. The map is cached on disk. Over-broad tags are filtered so a tag-hub can't flood.

The header shows `[🕸 boosted/anchorsA]`; boosted results show `🕸`, and provenance carries `graph_src` (entity|tag). ZERO canonical writes for either source (both are query-time over cached metadata).

**DEFAULT-OFF on purpose.** Entity-link coverage is often sparse until a densification pass lands, so the entity source alone is mostly a no-op early on. The tag source makes most of a tagged archive reachable, but the whole thing stays opt-in until an A/B recall eval (with vs without `--graph-expand`) shows top-3 relevance improves with no regression. v1 is boost-in-pool only; v2 (inject neighbour chunks absent from the pool) is intentionally not built. Function default `graph_expand_enable=False` (programmatic callers unaffected).

## Reading the results

Each result block shows:

```
[N] Score: 0.XXX | <source_type> | <title>
    Source: <file path>
    <first ~200 chars of the chunk>
```

**Score interpretation:**
- 0.50+ → strong match, probably has what you want, read the source file
- 0.30-0.49 → topical match, might have supporting context
- <0.30 → likely noise, treat skeptically unless the other signals line up

**After getting results**: if a result looks promising, `Read` the source file directly for the full context. The 200-char preview is just for deciding which file to open.

## Example workflow

User: "do we have anything on a partner's token listing status?"

```bash
python3 scripts/memory/vector_brain.py search "partner token listing status in market X" --top 5
```

Top result (score 0.51): `outputs/reviewed/agent/2026-04-07-token-listing-reference.md`: a listing-status reference prepared for a partner contact.

Action: `Read` that file for the full context. Then answer based on the file content, not the 200-char preview.

## Index maintenance

The index is NOT updated automatically. When you've written meaningful new memory/knowledge/output that should be findable, rebuild:

```bash
# full rebuild
python3 scripts/memory/vector_brain.py index

# add NEW docs without a rebuild (safe incremental, this is what you usually want)
python3 scripts/memory/vector_brain.py index-append --paths <file.md> ...
```

⛔ **NEVER `index --source <x>`.** It is NOT a partial/incremental rebuild despite the name. `build_index()`
does `create_table(mode="overwrite")`, so `--source memory` rebuilds the whole brain containing ONLY memory
and **silently destroys every other source**. This mislabel ("partial rebuild") caused two self-inflicted
index wipes before it was fixed. It now requires `--force` and refuses otherwise. To refresh everything use
plain `index`; to add docs use `index-append`.

After a big work session with lots of new outputs/memory entries, rebuild the index so future recall finds them.

Consider scheduling a nightly rebuild via cron if drift becomes a problem. but don't wire that up speculatively. Only if you notice recall missing recent content.

## Stats

```bash
python3 scripts/memory/vector_brain.py stats
```

Shows total vectors, breakdown by source type, unique source files, and the DB path.

## Why this skill exists

From a stack audit: `vector_brain.py` existed with vectors indexed but was never wired as a callable tool. it was archival storage that nothing read. This skill exposes it as a first-class recall primitive so the session can ground answers against prior work instead of fabricating or saying "I don't have context on that."
