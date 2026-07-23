# The Knowledge Graph — namespace taxonomy & page conventions

The **GRAPH** layer of the [knowledge pipeline](knowledge-pipeline.md) is a
[Logseq](https://logseq.com) graph: a folder of plain-markdown pages, one file per entity, organised by
namespace. It is the *canonical* store, the one recall treats as fact, so its structure is deliberate. This
doc is the taxonomy and the page conventions. It carries no real content; every example is a placeholder.

Two things make a Logseq graph more than a pile of markdown files, and both are load-bearing here:

1. **Namespaces** — a page named `Prospect/Acme-Labs` is not a folder path, it's a typed node. The `/`
   separates the *type* (`Prospect`) from the *instance* (`Acme-Labs`). Type-level queries ("every active
   prospect", "every meeting this month") fall out of the naming scheme for free.
2. **Properties + backlinks** — `key:: value` lines at the top of a page are queryable fields, and any
   `[[Other-Page]]` reference is a bidirectional link. The graph is a database that happens to be readable
   as text.

The agent reads and writes this graph through an MCP server (see [MCP interface](#mcp-interface) below); the
runtime wiring lives in the daemon and is not bundled in this repo, but the interface it exposes is
documented here so the design is legible.

---

## Domains

Twenty namespaces group into four domains. The split matters because the operator's life is not just the
business, and the memory system refuses to pretend otherwise.

| Domain | Covers | Example namespaces |
|--------|--------|--------------------|
| **A — Business / BD** | pipeline, network, market signals, regulation | `Prospect`, `Network/Person`, `Signal`, `Regulation` |
| **B — Personal** | training, nutrition, health | `Training`, `Nutrition`, `Health` |
| **C — Life OS** | projects, goals, learning, daily logs | `Project`, `Goal`, `Learning`, `Daily` |
| **D — AI Infra** | the agent's own memory + tooling notes | `Claude-Memory` |

Domain A is the operational core, but a page in `Training` or `Goal` is a first-class citizen of the same
graph and surfaces on the same recall. One brain, not four.

---

## Namespaces

Every namespace has a naming convention and, for most, a page **template** (the skeleton a new page is
seeded with). `protected` namespaces are write-guarded: the agent may read them but must not mutate them
without explicit human action (they hold ground truth that should never be casually overwritten).

| Namespace | Domain | Template | Protected |
|-----------|--------|----------|-----------|
| `Prospect` | A | Prospect Profiler | — |
| `Network/Person` | A | Network Person | — |
| `Network/Partner` | A | Network Partner | — |
| `Meeting` | A | Meeting Node | — |
| `Signal` | A | Signal Node | — |
| `Regulation` | A | — | **yes** |
| `Content` | A | Content Node | — |
| `Concept` | A | Concept Node | — |
| `Prompt` | A | Prompt Node | — |
| `Training` | B | Training Log | — |
| `Nutrition` | B | Nutrition Log | — |
| `Health` | B | Health Check | — |
| `Project` | C | Project Card | — |
| `Goal` | C | Goal Card | — |
| `Learning` | C | Learning Entry | — |
| `Daily` | C | Daily Log | — |
| `Routine` | C | Routine | — |
| `Idea` | C | Idea Node | — |
| `Intel` | C | Intel Brief | — |
| `Claude-Memory` | D | — | — |

### Naming rules

- **Separator:** `/` builds the namespace. `Network/Person/Jane-Doe` is `Person` under `Network`.
- **Word separator:** hyphens, never spaces. `Acme-Labs`, not `Acme Labs` (spaces fragment the page name).
- **Dates:** ISO, embedded in the instance name. `Training/2026-03-25-Push-Day`, `Daily/2026-03-25`.

---

## Page conventions: compiled-truth + timeline

The single most important convention, and the one the [`graph-hygiene`](../skills/graph-hygiene/SKILL.md)
lint enforces, is that an entity page has **two zones**, not one:

```
Prospect/Acme-Labs
├── properties         ← queryable header (status, tier, owner, dates)
├── ## Compiled Truth  ← the synthesised CURRENT state. rewritten in place.
└── ## Timeline        ← dated, append-only log of what happened. never rewritten.
```

Why two zones instead of one running log:

- **Compiled truth** answers *"what is true right now?"* in a few lines. It is overwritten as the situation
  changes, so reading it is O(1) — you never reconstruct the present by replaying history.
- **Timeline** answers *"how did we get here?"* It is append-only and dated, so provenance is never lost to
  a rewrite.

A page with only a timeline forces every reader to re-derive the current state from raw events. A page with
only compiled truth silently loses its own history the first time it's edited. Both zones, always.

### Example (placeholder content)

```markdown
type:: prospect
status:: active
tier:: 2
owner:: <operator>
first-contact:: 2026-02-10
last-touch:: 2026-03-22

## Compiled Truth
Mid-market infra team, warm intro via [[Network/Person/Jane-Doe]]. Evaluating a pilot;
budget confirmed, procurement is the open blocker. Next: proposal by end of month.

## Timeline
- 2026-02-10 — intro call. scoped needs, good fit on X.
- 2026-03-01 — sent one-pager, positive reply.
- 2026-03-22 — pricing pushback, countered with pilot framing.
```

Properties are queryable (`status:: active` powers "list active prospects"); `[[Network/Person/Jane-Doe]]`
links the two nodes bidirectionally, so the person's page shows this deal as a backlink automatically.

---

## How it plugs into the rest of the system

- **Upstream** — nothing writes here directly. Substantive output is staged raw, reviewed, and only then
  promoted into the graph. That one-way valve is the whole point of the [knowledge pipeline](knowledge-pipeline.md);
  raw drafts hitting the canonical graph is the failure mode it exists to prevent.
- **Downstream** — the graph is embedded into the archival vector index, so `recall` retrieves graph pages
  by meaning, not just by exact page name. See [memory-system.md](memory-system.md) for the tiering.
- **Provenance** — promoted entries are tagged with their source (`[[source/<persona>]]`) so a later recall
  hit tells you whether it came from a vetted memo or an unreviewed dump.
- **Maintenance** — the [`graph-hygiene`](../skills/graph-hygiene/SKILL.md) skill lints the graph on a
  schedule across seven categories (stale pages, orphans, missing properties, dead links, missing
  compiled-truth/timeline structure, tag inconsistency, near-duplicate names). It **never auto-deletes** —
  it emits severity-tagged findings and flags them for human review.

---

## MCP interface

The agent touches the graph through a Logseq MCP server (a daemon component, not bundled here). The
operations it exposes, so the interface is legible:

| Operation | Purpose |
|-----------|---------|
| `namespace_registry` | the taxonomy above, as live config |
| `list_namespace` | enumerate pages under a namespace |
| `read_page` / `create_page` | read or create a page (create validates namespace + protection) |
| `append_to_page` / `update_page` | append to the timeline, or rewrite compiled-truth in place |
| `search` | full-text across page names + content |
| `query_by_property` | typed query, e.g. every `Prospect` with `status:: active` |
| `find_links` | incoming + outgoing backlinks for a page |
| `read_journal` | the daily journal entry for a date |

Writes to the graph sit behind the same confirmation gate as any external-facing mutation (see
[security-gates.md](security-gates.md)); protected namespaces are refused outright. The graph is treated as
a source of truth, so nothing writes to it casually.
