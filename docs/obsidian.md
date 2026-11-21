# Obsidian: the same graph server on a vault

The knowledge-graph server in [`scripts/mcp/graph_mcp/`](../scripts/mcp/graph_mcp/) runs on an
[Obsidian](https://obsidian.md) vault as well as a Logseq graph. You get the same eleven tools, the
same safety rules and the same namespace registry. Only the file format differs. This doc is the
mapping between the two, and the limits of the Obsidian side.

```bash
python3 scripts/mcp/graph_mcp/server.py --selftest          # includes a temp vault
GRAPH_FORMAT=obsidian OBSIDIAN_VAULT_DIR=/path/to/vault python3 scripts/mcp/graph_mcp/server.py
```

---

## Design: one core, one backend per format

The server is one core: the tools, the write gate, the size caps and the transport. Under it sits a
format backend (`graph_backends.py`): `LogseqBackend` or `ObsidianBackend`. A backend answers four
questions: where a page's file is, how its properties are written, what its links look like, and
where today's note is. Everything else is shared.

The alternative was a second server for Obsidian. It was rejected because the jail is the one piece
of code that must never drift. The jail covers name validation, path resolution, the protected-
namespace check and the symlink rules. Two servers would mean two copies of it, and a fix landing in
one but not the other. With one core, each safety rule is written once, and the selftest exercises
it on both formats.

---

## The mapping

| | Logseq graph | Obsidian vault |
|---|---|---|
| root variable | `LOGSEQ_GRAPH_DIR` (holds `pages/`) | `OBSIDIAN_VAULT_DIR` (holds `.obsidian/`) |
| page `Project/Alpha` | `pages/Project___Alpha.md` | `Project/Alpha.md` |
| namespace | the longest registered namespace that prefixes the name | the same rule, read from the folder path |
| properties | `key:: value` lines | YAML frontmatter between `---` lines |
| links | `[[Page]]` | `[[Page]]`, `[[Folder/Page]]`, `[[Page\|alias]]`, `[[Page#Heading]]` |
| daily note | `journals/YYYY_MM_DD.md` | `<GRAPH_DAILY_FOLDER>/<GRAPH_DAILY_FORMAT>.md` |
| spaces in titles | allowed, hyphens recommended | normal |
| hidden folders | n/a | `.obsidian/`, `.trash/` and every dot-folder are skipped and refused |

### Namespaces are folders

Obsidian has no `/` inside a note title, so `/` in a page name is always a folder. `Project/Alpha` is
`Project/Alpha.md`. `Network/Person/Jane Doe` is `Network/Person/Jane Doe.md`. A namespace in the
registry matches its folder, case-folded. Notes outside any registered folder are readable and
searchable, and `graph_stats` counts them as unnamespaced. `update_page` and `append_to_page` work on
them, but `create_page` cannot make a new one, because it requires a registered namespace (the same
rule as on Logseq).

If your folders do not match your namespace names, map them in the registry:

```json
"Person": {"domain": "work", "template": null, "protected": false, "obsidian_folder": "People"}
```

Then `Person/Jane Doe` is `People/Jane Doe.md`. Listings report the namespace name, and writing
through the folder spelling (`People/Jane Doe`) gets the same protection check. If a folder named
`Person` also exists, the server refuses to start. It does not guess which of the two folders the
name means.

### Properties are frontmatter

```markdown
---
status: active
tags: [demo, "sample tag"]
owners:
  - Jane Doe
  - Sam Roe
---
```

The reader is stdlib, with no YAML library. It reads scalars, inline lists (`[a, b]`) and block lists
(`- item` lines). It skips nested maps, multi-line scalars (`|`, `>`) and anchors, and drops the key
rather than return half a value. `query_by_property` matches a list when any element contains the
value, case-insensitive. Dataview inline fields (`key:: value` in the body) are not read on an
Obsidian vault.

### Links and backlinks

`find_links` strips `|alias` and `#heading` (and `#^block` references), and drops a trailing `.md`.
Then a link counts as pointing at page `P` when:

1. it names `P` in full (`[[Person/Jane Doe]]`), or
2. it is a bare name (`[[Jane Doe]]`) and exactly one note in the vault has that basename.

When several notes share a basename, Obsidian picks one by its own rules (shortest path, then the
link's folder). The server does not try to reproduce that. Bare links to a shared basename are
listed under `ambiguous_incoming` and are not counted as backlinks. Use full-path links where
basenames repeat.

### Daily notes

`read_journal` reads `<vault>/<GRAPH_DAILY_FOLDER>/<date>.md`. The folder defaults to the vault root.
The name format is a `strftime` pattern and defaults to `%Y-%m-%d`, which matches Obsidian's default
`YYYY-MM-DD`. A folder with `..` or a hidden segment is refused at startup. A format containing `/` is
refused too.

| Variable | Default | Meaning |
|----------|---------|---------|
| `GRAPH_FORMAT` | `logseq` | set to `obsidian` (or pass `--format obsidian`) |
| `OBSIDIAN_VAULT_DIR` | none, required | the vault root |
| `GRAPH_DAILY_FOLDER` | vault root | daily notes folder, relative to the vault |
| `GRAPH_DAILY_FORMAT` | `%Y-%m-%d` | daily note file name, `strftime` |
| `GRAPH_NAMESPACES_FILE` | shipped example | your registry |
| `GRAPH_MCP_WRITES` | off | `1` turns on the write tools ([why off](logseq-graph.md#writes-are-opt-in)) |

Registration (`.mcp.json` on Claude Code):

```json
"obsidian": {
  "command": "python3",
  "args": ["/path/to/utopia-os/scripts/mcp/graph_mcp/server.py", "--format", "obsidian"],
  "env": { "OBSIDIAN_VAULT_DIR": "/path/to/vault", "GRAPH_DAILY_FOLDER": "Journal" }
}
```

---

## Safety on a vault

On Logseq every page sits in one flat folder. On a vault, `/` is a real folder, so the jail carries
more weight. The selftest checks each of these on a temp vault:

- `../`, absolute paths, and a folder symlink that leaves the vault are refused, for reads and writes.
- `.obsidian/`, `.trash/` and any hidden segment are refused, including through a visible symlink
  that points into `.obsidian/`.
- A protected page reached through a symlinked folder inside the vault is still refused. Protection
  is checked on the resolved file as well as on the name.
- `#`, `^`, `[`, `]` and `|` are refused in names. Obsidian refuses them in note titles, and they
  would break a wikilink.
- `create_page` creates missing subfolders inside a namespace, and re-checks the jail after creating
  them.

---

## Recall over a vault

`scripts/memory/vector_brain.py` indexes the graph as one of its sources. It assumed Logseq: a flat
`pages/*.md` glob, page keys from the filename, `[[link]]` targets taken literally. On a nested vault
it indexed zero files, without an error. Set `AGENT_GRAPH_FORMAT=obsidian` (with `AGENT_GRAPH_DIR` at
the vault root):

- every `.md` under the vault is indexed; hidden folders and symlinks out of the vault are skipped;
- a chunk's title is its vault-relative path (`Person/Jane Doe`), and its `source_type` is `obsidian`;
- the backlink map (used by graph expansion) strips `|alias` and `#heading`, and resolves a bare
  `[[Name]]` by basename when it is unique, the same rule as `find_links`.

`python3 scripts/memory/vector_brain.py graph-selftest` checks both formats on temp graphs, with no
model load.

**Limit:** the tag co-citation map reads Logseq `tags::` lines only. Obsidian frontmatter `tags:` and
inline `#tags` are not read, so on a vault that source stays empty. Both graph-expansion sources are
off by default.
