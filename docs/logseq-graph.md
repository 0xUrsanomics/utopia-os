# The Knowledge Graph: namespace taxonomy & page conventions

The **GRAPH** layer of the [knowledge pipeline](knowledge-pipeline.md) is a
[Logseq](https://logseq.com) graph: a folder of plain-markdown pages, one file per entity, organised by
namespace. It is the *canonical* store, the one recall treats as fact, so its structure is deliberate. This
doc is the taxonomy and the page conventions. It carries no real content; every example is a placeholder.

Two things make a Logseq graph more than a pile of markdown files, and both are load-bearing here:

1. **Namespaces**, a page named `Prospect/Acme-Labs` is not a folder path, it's a typed node. The `/`
   separates the *type* (`Prospect`) from the *instance* (`Acme-Labs`). Type-level queries ("every active
   prospect", "every meeting this month") fall out of the naming scheme for free.
2. **Properties + backlinks**, `key:: value` lines at the top of a page are queryable fields, and any
   `[[Other-Page]]` reference is a bidirectional link. The graph is a database that happens to be readable
   as text.

The agent reads and writes this graph through an MCP server that ships in this repo,
[`scripts/mcp/graph_mcp/server.py`](../scripts/mcp/graph_mcp/server.py) (see [MCP interface](#mcp-interface)
below). The same server also runs on an Obsidian vault; [obsidian.md](obsidian.md) has the mapping.

---

## Domains

The taxonomy below is one operator's working graph, kept as a worked example: twenty namespaces in four
domains. The registry the server ships with is smaller and generic (`Project`, `Person`, `Meeting`,
`Concept`, `Reference`, `Journal`, in [`namespaces.example.json`](../scripts/mcp/graph_mcp/namespaces.example.json));
copy it and grow it into your own. The domain split matters because the operator's life is not just the
business, and the memory system refuses to pretend otherwise.

| Domain | Covers | Example namespaces |
|--------|--------|--------------------|
| **A, Business / BD** | pipeline, network, market signals, regulation | `Prospect`, `Network/Person`, `Signal`, `Regulation` |
| **B, Personal** | training, nutrition, health | `Training`, `Nutrition`, `Health` |
| **C, Life OS** | projects, goals, learning, daily logs | `Project`, `Goal`, `Learning`, `Daily` |
| **D, AI Infra** | the agent's own memory + tooling notes | `Claude-Memory` |

Domain A is the operational core, but a page in `Training` or `Goal` is a first-class citizen of the same
graph and surfaces on the same recall. One brain, not four.

---

## Namespaces

Every namespace has a naming convention and, for most, a page **template** (the skeleton a new page is
seeded with). `protected` namespaces are write-guarded: the agent may read them but must not mutate them
without explicit human action (they hold ground truth that should never be casually overwritten).

| Namespace | Domain | Template | Protected |
|-----------|--------|----------|-----------|
| `Prospect` | A | Prospect Profiler |, |
| `Network/Person` | A | Network Person |, |
| `Network/Partner` | A | Network Partner |, |
| `Meeting` | A | Meeting Node |, |
| `Signal` | A | Signal Node |, |
| `Regulation` | A |, | **yes** |
| `Content` | A | Content Node |, |
| `Concept` | A | Concept Node |, |
| `Prompt` | A | Prompt Node |, |
| `Training` | B | Training Log |, |
| `Nutrition` | B | Nutrition Log |, |
| `Health` | B | Health Check |, |
| `Project` | C | Project Card |, |
| `Goal` | C | Goal Card |, |
| `Learning` | C | Learning Entry |, |
| `Daily` | C | Daily Log |, |
| `Routine` | C | Routine |, |
| `Idea` | C | Idea Node |, |
| `Intel` | C | Intel Brief |, |
| `Claude-Memory` | D |, |, |

### Naming rules

- **Separator:** `/` builds the namespace. `Network/Person/Jane-Doe` is `Person` under `Network`.
- **Word separator:** hyphens. Write `Acme-Labs`; a space in `Acme Labs` fragments the page name.
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
  changes, so reading it is O(1), you never reconstruct the present by replaying history.
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
- 2026-02-10: intro call. scoped needs, good fit on X.
- 2026-03-01: sent one-pager, positive reply.
- 2026-03-22: pricing pushback, countered with pilot framing.
```

Properties are queryable (`status:: active` powers "list active prospects"); `[[Network/Person/Jane-Doe]]`
links the two nodes bidirectionally, so the person's page shows this deal as a backlink automatically.

---

## How it plugs into the rest of the system

- **Upstream**, nothing writes here directly. Substantive output is staged raw, reviewed, and only then
  promoted into the graph. That one-way valve is the whole point of the [knowledge pipeline](knowledge-pipeline.md);
  raw drafts hitting the canonical graph is the failure mode it exists to prevent.
- **Downstream**, the graph is embedded into the archival vector index, so `recall` retrieves graph pages
  by meaning, not just by exact page name. See [memory-system.md](memory-system.md) for the tiering.
- **Provenance**, promoted entries are tagged with their source (`[[source/<persona>]]`) so a later recall
  hit tells you whether it came from a vetted memo or an unreviewed dump.
- **Maintenance**, the [`graph-hygiene`](../skills/graph-hygiene/SKILL.md) skill lints the graph on a
  schedule across seven categories (stale pages, orphans, missing properties, dead links, missing
  compiled-truth/timeline structure, tag inconsistency, near-duplicate names). It **never auto-deletes**, 
  it emits severity-tagged findings and flags them for human review.

---

## MCP interface

The agent touches the graph through the bundled server,
[`scripts/mcp/graph_mcp/server.py`](../scripts/mcp/graph_mcp/server.py). It is stdlib only and speaks
MCP over stdio. It touches local files only, so it holds no credential.

| Tool | Purpose |
|------|---------|
| `namespace_registry` | the taxonomy, as live config: domains, templates, protection, naming rules |
| `list_namespace` | the pages under a namespace, newest first, with their properties |
| `read_page` | one page in full, plus its parsed properties |
| `search` | case-insensitive full text over page names and content, ranked by match count |
| `query_by_property` | a typed query, e.g. every `Project` with `status:: active` |
| `find_links` | outgoing `[[links]]` and incoming backlinks for a page |
| `read_journal` | the daily journal entry for a date (default: today) |
| `graph_stats` | page counts per namespace and domain, size, journal count |
| `create_page` | a new page in a registered namespace (refuses an existing page) |
| `update_page` | rewrite a page in place, e.g. its compiled truth |
| `append_to_page` | append to the end, e.g. a timeline entry |

### Run it

```bash
python3 scripts/mcp/graph_mcp/server.py --selftest              # temp graph + temp vault, no config
LOGSEQ_GRAPH_DIR=/path/to/graph python3 scripts/mcp/graph_mcp/server.py
```

| Variable | Meaning |
|----------|---------|
| `LOGSEQ_GRAPH_DIR` | **required.** The graph root, the folder that holds `pages/` and `journals/` |
| `GRAPH_NAMESPACES_FILE` | your registry (default: the shipped `namespaces.example.json`) |
| `GRAPH_MCP_WRITES` | `1` turns on the three write tools. Default off |
| `LOCAL_UTC_OFFSET_HOURS` | what "today" means for `read_journal` (default: system local time) |

A missing root, a root with no `pages/`, or an unreadable registry stops the server at startup with a
message naming the variable. It never serves an empty graph. A dead symlink that answers "no such page"
looks exactly like a page that does not exist, and that is the failure this rule prevents.

Register it in your harness's MCP config (`.mcp.json` on Claude Code). Each config example under
[`adapters/`](../adapters/) registers it as `graph` in that harness's own format, and the snippet below
uses the same key. [`settings.example.json`](../settings.example.json) shows a Logseq and an Obsidian
entry side by side, keyed `logseq` and `obsidian`:

```json
"graph": {
  "command": "python3",
  "args": ["/path/to/utopia-os/scripts/mcp/graph_mcp/server.py"],
  "env": { "LOGSEQ_GRAPH_DIR": "/path/to/graph", "GRAPH_NAMESPACES_FILE": "/path/to/namespaces.json" }
}
```

### Writes are opt-in

The three write tools are hidden from `tools/list` and refused when called, until `GRAPH_MCP_WRITES=1`.
In this stack the human confirmation gate for a graph write lives in the harness hook layer (see
[security-gates.md](security-gates.md)), and some supported harnesses have no hook layer. With writes on
by default, any agent on any harness would get an unmediated path into the store recall treats as fact.
Turn writes on where you have wired the `CONFIRM` gate. The read-only memory server makes the same call
for the same reason ([`scripts/memory/memory_server.py`](../scripts/memory/memory_server.py)).

### Safety rules (enforced in the server, not left to the caller)

- **Protected namespaces refuse every write.** The case-folded check covers the namespace's pages and the
  page named exactly as the namespace (`Reference` itself), and it runs again on the resolved file, so
  `reference/x`, a symlink, or a filename spelling cannot reach a protected page by another name.
- **Page names are validated before they become paths.** Refused: `..`, a leading `/`, hidden segments,
  `\`, `:` and control characters. On Logseq, `__` is refused too, because the filename encodes `/` as
  `___` and `Reference___Policy` would otherwise alias `Reference/Policy`.
- **The path jail.** Every path is resolved, then required to sit inside the graph root, so traversal and
  symlinks out are judged by where the path finally lands.
- **Size caps.** Reads over 1 MB are refused; a scan skips them and counts them. Create and update take
  up to 100,000 characters, append up to 50,000, and no write may push a page past 1 MB.
- **No shell.** No tool path spawns a process; the selftest checks the source for it.
- **Writes are atomic** (temp file, then rename), and `create_page` never overwrites a page created in
  the meantime.

The selftest is weighted toward the refusals: traversal, symlinks out, protected-namespace
spellings, oversize payloads, bad dates. Each guard was disabled once to confirm a check goes red.

### The MCP SDK transport

The default transport is a stdlib JSON-RPC loop, the same as the memory server and the Telegram bridge.
`--sdk` serves the identical tool table through the official MCP SDK, pinned in
[`scripts/mcp/graph_mcp/requirements.txt`](../scripts/mcp/graph_mcp/requirements.txt), for clients
that need protocol features the stdlib loop does not implement. `--selftest-sdk` runs a real stdio
handshake through it and fails, rather than skipping, when the SDK is not installed.

The SDK's own dependencies are pinned in [`scripts/constraints.txt`](../scripts/constraints.txt) (identical copy of the root `constraints.txt`). Each pin was on PyPI
for at least 7 days, with no OSV advisory for that version, when it was set. The requirements file
applies the constraints itself, and naming them on the command line does the same:

```bash
pip install -r scripts/mcp/graph_mcp/requirements.txt -c scripts/constraints.txt
python3 scripts/mcp/graph_mcp/server.py --selftest-sdk
```

### What the server does not do

- It does not parse Logseq's block structure, `#tag` links or `{{queries}}`. Properties are `key:: value`
  lines; links are `[[Page]]`.
- It does not write journals. `read_journal` reads them; a journal note is written by Logseq or as a
  page in a namespace of your choice.
- It does not auto-link entity names on write. The page you write is the page stored.
