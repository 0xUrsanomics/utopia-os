# Adapter model: running Utopia OS on any harness

Utopia OS is Claude-Code-native, but it is built as two separable layers. A **portable core** that
moves to any MCP-capable harness unchanged, and a thin **harness shim** that wires the core into a
specific harness. An adapter is just that shim for one harness. This doc defines the boundary every
adapter implements, so a new adapter is a small, well-scoped translation rather than a rewrite.

For the reference implementation, see [`adapters/codex/`](../adapters/codex/) (OpenAI Codex CLI, the
lowest-cost target and the one that validates the boundary).

## The boundary

### Portable core (moves unchanged)

| Piece | Why it is portable |
|---|---|
| The MCP daemon (tools + memory + recall) | MCP is an open standard; any harness that is an MCP client can consume it. |
| `memory/*.md` | Plain Markdown. No harness owns it. |
| Recall + state machinery (`scripts/memory/`) | Plain Python; callable as a tool or over MCP. |
| Skill and knowledge **content** | Prose. Adoptable regardless of how a harness triggers it. |

The core never changes per harness. An adapter points at it; it does not copy it.

### Harness shim (the adapter, four dimensions)

Every adapter maps exactly these four things from Claude Code to the target harness:

1. **Instruction file.** Claude Code reads `CLAUDE.md`. Most other harnesses read `AGENTS.md`. The
   [`AGENTS.md`](../AGENTS.md) at the repo root already covers the common case.
2. **Hook / event layer.** The guardrail and hygiene scripts (`settings.json` hooks: `PreToolUse`,
   `PostToolUse`, `Stop`, `SessionStart`, `UserPromptSubmit`) must fire on the target's event system.
   This is the load-bearing dimension: a harness with no hook layer cannot run the automated gates,
   which raises its adapter cost.
3. **Skill trigger.** Skill *content* is `SKILL.md` everywhere, but *triggering* differs: keyword
   auto-fire (Claude Code frontmatter), LLM-discretionary self-select from a catalog, or manual
   invoke only. The adapter states which mode the target supports and what degrades.
4. **MCP config.** The daemon's server list must be expressed in the target's MCP config format
   (`.mcp.json` JSON on Claude Code; TOML tables on Codex/grok; `mcp.json` on Kimi; and so on).

## Per-harness mapping (from the step-0 audit, 2026-07-23)

| Harness | Instruction file | Hook layer | Skill trigger | MCP config | Adapter tier |
|---|---|---|---|---|---|
| **Codex CLI** | AGENTS.md (32 KiB cap) | 10 events, CC's 5 present by name; same exit-2 contract | auto-trigger + `/skills` | `[mcp_servers.*]` TOML | **low** |
| **Kimi Code** | AGENTS.md | 14 events; 3 blockable; CC exit-code contract | auto-trigger (opt-out `type:flow`) | `mcp.json` (CC-shaped) | **low** |
| **grok** | AGENTS.md | 13 events, superset; reads `~/.claude/settings.json` (hooks compat) | auto-trigger; skills in `.grok/` (NOT `~/.claude/skills`) | `[mcp_servers.*]` TOML | **low** |
| **Hermes** | AGENTS.md native (also detects CLAUDE.md); SOUL.md = voice | 3-tier; blocks via stdout-JSON (not exit-2); no `Stop` analogue | LLM-discretionary + `/skill` | `mcp_servers:` YAML (stdio/HTTP) | **medium** |
| **OpenClaw** | AGENTS.md (+ bundled `migrate` importer, 3 of 4 dims) | file hooks (observe) + typed TS plugins (block) | LLM-discretionary + `/skill` | `mcp.servers` JSON5 (client + server) | **medium** |
| **opencode** | AGENTS.md (falls back to `~/.claude/CLAUDE.md`) | plugin hooks, different taxonomy | **manual invoke only** | JSON `mcp:` block | **medium** |
| **pi** | AGENTS.md or CLAUDE.md (first match) | TS extensions, superset of CC | auto-trigger (own skill dirs, NOT `~/.claude/skills`) | **no built-in MCP** (community adapter) | **medium** |
| **Kilo Code** | AGENTS.md | **none** (lifecycle hooks not supported) | judgment / manual | STDIO/SSE | **high** |

## Adapter contract

Each `adapters/<harness>/` ships:

- **`README.md`** — the four-dimension mapping, step-by-step adoption, and a **"what degrades"**
  section (e.g. skill auto-trigger loss, an instruction-file size cap).
- **Config template(s)** in the target's format (MCP servers, hooks), translating what
  `settings.example.json` and the daemon ship.
- It **references** the portable core by path; it never forks it.

## Tiers

- **Low** — a syntax translation only. The target has an MCP client, a hook layer that maps to CC's
  events, and `SKILL.md` auto-trigger. Config differences are JSON/frontmatter to TOML. (Codex, Kimi,
  grok.)
- **Medium** — the substrate ports, but guardrail scripts must be rewritten as in-process plugins in
  the target's language, and/or skill auto-trigger degrades. (Hermes, OpenClaw, opencode, pi.)
- **High** — the target lacks an agent-lifecycle hook system, so the automated gates have no
  deterministic trigger point and fall back to prose plus a coarse OS sandbox. (Kilo Code.)

Build low-tier first: it proves the portable-core boundary holds before spending real engineering on
the medium tier.
