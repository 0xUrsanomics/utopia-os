# MEMORY.md. Index of the 3-tier memory system

> **Template.** Copy to `memory/MEMORY.md` and fill in as you build out your memory. This is the
> navigation index for the whole memory system, NOT the memory itself. See `CLAUDE.md` "Memory System"
> and `docs/memory-system.md` for the full design. Keep it under a line budget (e.g. 200 lines) and
> prune the oldest/stalest pointers when it grows past that. Each pointer is one line: link + a
> one-clause description of current state.

The tiers are split by *how often a thing is needed*, not by topic:
- **Tier 1** is always loaded (paid for on every reply). Keep it tiny.
- **Tier 2** is read on demand (pulled by direct read or semantic recall).
- **Tier 3** is semantic search over everything.

---

## Tier 1. Core (always loaded)

> The handful of files read once per session and kept in working memory. Do NOT let this list grow.

- [SOUL.md](../SOUL.md): voice constitution. identity, voice mandates, anti-patterns, format mandates.
- [USER.md](../USER.md): deep model of the operator. background, current state, temperament, triggers.
- [Preferences.md](../Preferences.md): `key:: value` behavior rules, deduped on key.
- [Voice-Profile.md](../Voice-Profile.md): writing-style dimension substrate that feeds SOUL mandates.
- [user-model.md](../user-model.md): behavioral predictions, auto-updated by the consolidation job.
- [session-bootstrap.md](../session-bootstrap.md): fresh-start parachute + active-handoff block.
- [Decisions.md](../Decisions.md): append-only decision log. read-on-demand, indexed into Tier 3.
- [Learnings.md](../Learnings.md): append-only lessons log. read-on-demand, indexed into Tier 3.

## Tier 2. Recall (read on-demand, semantically indexed)

> Subject dossiers and notes. Too many to always-load, too specific to compress into Tier 1. Grouped
> by folder. Add a pointer here when you create a dossier, or it goes silently unindexed.

### Context/. subject dossiers
- [EXAMPLE-dossier](../Context/EXAMPLE-dossier.md): `<one-clause current-state summary of the subject>`.
- `<[Subject Name](../Context/subject-slug.md): compiled-truth + timeline dossier for X.>`

### Infra/. technical infrastructure notes
- [EXAMPLE-note](../Infra/EXAMPLE-note.md): `<one-clause: what broke, what the fix was, current state>`.
- `<[Component Name](../Infra/component-slug.md): problem/root-cause/fix note for Y.>`

### Feedback/. domain-specific lessons from the operator
- [EXAMPLE-lesson](../Feedback/EXAMPLE-lesson.md): `<one-clause: the rule this lesson encodes>`.
- `<[Lesson Name](../Feedback/lesson-slug.md): the correction/preference it captures.>`

## Tier 3. Archival (semantic search)

> Not files. A local vector index (e.g. LanceDB/SQLite-VSS) at `<VECTOR_DB_PATH>`, containing
> embeddings of everything above plus any reviewed outputs and graph pages. Query via the `recall`
> skill. Rebuild after big work sessions with `<your index command, e.g. scripts/memory/vector_brain.py index>`.

## Sidecars

> Runtime state that isn't prose memory.

- `memory/personas/<slug>.json`: per-persona memory (one file per persona).
- `memory/state/*`: runtime flags, counters, budgets, registries (see `memory/state/*.example.json`).
