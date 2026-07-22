# Memory System — compounding, tiered, cache-aware

The point of a memory system is that **the next session starts smarter than the last one**. A stateless
assistant re-derives who you are and what was decided every time; an operator remembers. But "remember
everything" is a trap — a coding-agent runtime reloads its whole context on every single reply, so
anything you always-load is a tax you pay on every turn for the rest of the session.

So memory here is split by **how often a piece of knowledge is needed**, not by topic. Three tiers, from
"in the prompt on every reply" to "searchable but never loaded until asked for." Get the split right and
the agent behaves like it knows everything while only paying for the slice each turn actually touches.

## The three tiers

| Tier | What lives here | Where | How it's reached | Marginal cost per reply |
|---|---|---|---|---|
| **1 · Core** | Voice, operator model, rules, style profile, the index | top-level `memory/*.md` | read once at session start, held in working memory | amortized once, then served from prompt cache |
| **2 · Recall** | Subject dossiers, infra notes, domain feedback | `memory/context/`, `memory/infra/`, `memory/feedback/` | direct read *or* semantic hit, on demand | paid only on turns that touch the subject |
| **3 · Archival** | Everything, embedded | a local vector index | semantic query ("what do we know about X") | paid per query — the hit, not the corpus |

The mental model behind the split is the classic memory taxonomy:

- **Procedural** (how to behave) → Tier 1, always on. Voice, rules, operator model.
- **Episodic** (what happened, dated) → the two append-only logs, indexed into Tier 3, surfaced on recall.
- **Semantic** (subject knowledge) → Tier 2 dossiers.
- **Short-term** (this task, right now) → the session's runtime state and handoff block (see
  `session-management.md`), not the memory tiers at all.

## Tier 1 — Core (always loaded)

Four files carry the ambient "who am I, who are you, how do I behave" layer. They are small, stable, and
read once per session so voice and judgement are present on every reply without a fetch.

| File | Role | Contains | Update rule |
|---|---|---|---|
| `memory/voice.md` | **Voice constitution** | Mandates, not observations. Identity, voice *musts*, anti-patterns (*nevers*), what good vs. bad output looks like, format rules. | Overwrite on a deliberate revision. |
| `memory/operator.md` | **Operator model** | A deep model of you: background, current state, routine, values and decision patterns, temperament, blind spots, triggers, communication style, how to apply it. | Overwrite as the model sharpens. |
| `memory/rules.md` | **Rules** | Global behavior in `key:: value` form (free-first, security-first, archive-first, scope-on-confirm, …). Deduplicated on key; later entry wins. | Append/dedup. |
| `memory/style.md` | **Writing-style profile** | The observation *substrate* — measurable style dimensions (sentence length, diction, tone, formatting habits) that feed the constitution's mandates. | Append new dimensions as observed. |

The constitution and the style profile are complementary, not redundant: the **style profile is what the
system observes**, the **constitution is what it commits to**. Observations accumulate in the profile;
periodically they get distilled into hard mandates in the constitution. One is the sensor, the other is
the policy.

A fifth Tier-1 file, `memory/index.md`, is the map — what lives in which tier and file. It is rewritten
only when the tier structure itself changes.

### The two append-only logs

Two files record durable history: `memory/decisions.md` (choices made, with the context and reasoning
that produced them) and `memory/learnings.md` (insights worth carrying forward, tagged by topic). Both
are **append-only and dated** — you never rewrite history, you add to it.

They are Tier-1 files by *location* but they are **not eager-loaded**. Loading months of dated history on
every session start would be the exact tax the tiering exists to avoid. Instead they are **indexed into
Tier 3**, so a recall query surfaces the relevant entry precisely when the current task references a past
decision or learning — and stays out of the prompt the rest of the time.

A learning entry can name the files it concerns (`affected_files::`). A tool that surfaces
"prior learnings about this file" before you edit it turns the log from a diary into a tripwire: the
lesson finds you at the moment you're about to repeat the mistake.

## Tier 2 — Recall (on demand, vector-indexed)

Subject dossiers: one file per subject that has outgrown a single log entry. A client, an infra component,
a recurring category of feedback. They are **too many to always-load** (dozens to hundreds) but **too
specific to compress** into Tier 1.

```
memory/
  context/   one file per subject that needs a standing page
  infra/     infrastructure state, bugfixes, component notes
  feedback/  domain-specific corrections too big for rules.md
```

Every Tier-2 file is embedded into the archival index on the next rebuild, so a dossier is reachable two
ways: by path (you know the file) or by meaning (you describe the subject and let search find it). On-demand
paging is the whole point — it keeps the prompt cache stable while leaving the long tail one query away.

## Tier 3 — Archival (semantic search)

A local vector index over Tier 1 + Tier 2 + the canonical knowledge graph + reviewed outputs. It answers
**"what do we know about X"** without you needing to know which file X lives in, and it surfaces
cross-references between dossiers that a direct read would miss.

Any local embedding index works (LanceDB, sqlite-vss, Chroma, …); the design assumption is only that it
runs on your own machine — archival memory should never be a third-party dependency. Rebuild it after
sessions that produced substantial new memory.

Tier 3 exists because Tiers 1 and 2 both require *knowing the path*. Semantic search is the fallback for
the case where the conversation raises a subject and nobody remembers where — or whether — it was written
down.

## What's loaded when — the prompt-cache economics

Every reply re-sends the context to the model. Runtimes cache a **stable prefix** so an unchanged prompt
head is cheap to re-read — but the cache only helps if the always-loaded part stays small and stable. The
tiering is, underneath, a cache-management strategy.

```
             cost profile across a session
  ┌─────────────────────────────────────────────────────────────┐
  │ harness-injected  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  every reply, cached │
  │ Tier-1 core       ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  read once, cached   │
  │ parachute         ▓                        fresh-start only    │
  │ episodic logs     ░░▓░░░░▓░░░░░░░░░▓░░░░░  only on recall      │
  │ Tier-2 dossiers   ░░░░▓░░░░░▓░░░░░░░░░░░░  only when touched   │
  │ Tier-3 archival   ░▓░░░░░░░░░░▓░░░░░░░▓░░  per query           │
  └─────────────────────────────────────────────────────────────┘
```

| Layer | Loaded | Why it's placed there |
|---|---|---|
| System prompt, index, date, tool defs | Injected by the runtime every session | Zero marginal cost — you don't load it, the harness does, and it sits in the cached prefix. |
| Tier-1 core (voice, operator, rules, style) | Read once at session start | Small + stable → written to cache once, then re-read cheaply. This is *why* Tier 1 must stay lean. |
| Fresh-start parachute (`memory/bootstrap.md`) | Only on a fresh/crash spawn | On a normal resume the transcript already carries continuity, so the parachute is skipped. See `session-management.md`. |
| Episodic logs (decisions, learnings) | Not eager-loaded — via recall | Dated history is large and rarely all-relevant; pay for the one entry you need, when you need it. |
| Tier-2 dossiers | On-demand read or semantic hit | Too many to always-load; paged in only when the task touches the subject. |
| Tier-3 archival | Per semantic query | You pay for the retrieved hit, never the whole corpus. |

The failure this prevents: eager-loading everything "so the agent has full context." That bloats the
cached prefix, thrashes the cache every time a dossier changes, and spends the token budget on knowledge
the current turn doesn't use. Keep Tier 1 small and stable; page the rest.

## Write discipline — routing new knowledge

| The new knowledge is… | Write it to |
|---|---|
| A stated preference about how to work | `memory/rules.md` (dedup on key) |
| A choice with context + reasoning to preserve | `memory/decisions.md` (append, dated) |
| An insight useful in future sessions | `memory/learnings.md` (append, dated, tagged) |
| A newly observed style pattern | `memory/style.md` |
| A subject that now needs a standing page | `memory/context/<subject>.md` |
| An infra change or bugfix | `memory/infra/<component>.md` |
| Domain-specific feedback too big for a rule | `memory/feedback/<domain>.md` |

Extraction runs at session rotation or on an explicit save: scan the session, pull out preferences,
decisions, context, voice patterns, and learnings, and append each to the right file — skipping any
category with nothing new. Rebuild the archival index after sessions that added substantial memory.

## Design principles

- **Split by access frequency, not by topic.** The tier a fact lives in is decided by how often a reply
  needs it, not what it's about.
- **Always-loaded must stay small and stable.** Every file in Tier 1 is a per-reply tax and a cache
  dependency. Earn its place.
- **History is indexed, not injected.** Dated logs surface on recall; they never ride in the prompt by
  default.
- **Observe, then commit.** The style profile records; the constitution mandates. Keep the two separate so
  observations can accumulate before they harden into rules.
- **Archival is local.** Semantic memory is infrastructure you own, not a service you rent.

See also: `session-management.md` (short-term state + the parachute), `knowledge-pipeline.md` (how outputs
become durable knowledge), `ssot.md` (runtime state, which is *not* memory).
