---
title: MCP Builder Reference (ported from warpdotdev/oz-skills)
source: https://github.com/warpdotdev/oz-skills/tree/main/.agents/skills/mcp-builder
license: Apache-2.0
attribution: Original work © Anthropic + Warp Inc. Ported 2026-05-06.
purpose: Reference docs for building/extending MCP servers when adding or wiring new MCP capabilities.
---

# MCP Builder — Reference Materials

Ported from `warpdotdev/oz-skills` (Apache-2.0). These are Anthropic's published `mcp-builder` skill
docs, redistributed by Warp under Apache-2.0, ported here with full attribution.

Keep the Apache-2.0 attribution (© Anthropic + Warp Inc.) and `LICENSE.txt` intact in any
redistribution.

## Why keep this

Reference material for when you build or extend an MCP server. These docs capture Anthropic's
best-practice patterns for MCP design, server implementation in Python and Node, and
evaluation/testing. They are reference docs, not an auto-loading skill.

## Files

| File | Source | Purpose |
|---|---|---|
| `SKILL.md` | warpdotdev/oz-skills | The "build an MCP server" skill spec: workflow, when-to-use, output format |
| `mcp_best_practices.md` | warpdotdev/oz-skills | MCP server design principles + anti-patterns |
| `python_mcp_server.md` | warpdotdev/oz-skills | Python impl reference (FastMCP, async patterns, tool decorators) |
| `node_mcp_server.md` | warpdotdev/oz-skills | TypeScript impl reference (MCP SDK, transport, schemas) |
| `evaluation.md` | warpdotdev/oz-skills | How to evaluate MCP server quality + test framework |
| `LICENSE.txt` | warpdotdev/oz-skills | Apache-2.0 license text (verbatim) |

## When to use

- Building a new MCP server from scratch.
- Extending an existing MCP server with new tools.
- Reviewing existing MCP code for quality issues per `mcp_best_practices.md`.
- Writing evaluation tests for an MCP per `evaluation.md`.

## When NOT to use

- These are reference docs, not a runnable skill.
- Don't redistribute externally without preserving the Apache-2.0 attribution.
- Don't modify the source files (`mcp_best_practices.md` / `python_mcp_server.md` / `node_mcp_server.md`
  / `evaluation.md`). They're upstream reference material; keep local notes in this README or a separate
  `notes.md`.

## Attribution

Per Apache-2.0:

```
Copyright (c) Anthropic + Warp Inc.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
```

Source: https://github.com/warpdotdev/oz-skills/blob/main/.agents/skills/mcp-builder/
