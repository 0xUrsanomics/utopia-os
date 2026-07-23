# Utopia OS on grok (xAI grok CLI / grok-build)

grok is a **low-cost** adapter (near 1:1 with Claude Code), like Codex. Verified against grok-build's
in-repo docs on 2026-07-23. See [`docs/adapters.md`](../../docs/adapters.md) for the model.

> **Security note:** `xai-org/grok-build` is a young repo (open-sourced 2026-07-14, Apache-2.0, Rust,
> closed-governance / synced from an internal monorepo). Re-run your stand-down + 7-day-age check before
> cloning or installing.

## Why grok is near 1:1

- **Hooks:** grok's hook config is **the Claude Code `settings.json` hooks JSON format**, at
  `~/.grok/hooks/*.json`. Better still, grok reads `~/.claude/settings.json` directly in a
  **compatibility mode**, so an existing CC hooks block can work as-is. Events are a superset of CC's
  (adds `PermissionDenied`, `PreCompact`/`PostCompact`); blockable: `PreToolUse`, `Stop`, `SubagentStop`.
- **MCP:** `[mcp_servers.<name>]` TOML in `~/.grok/config.toml` (stdio + http), the same shape as Codex.
- **Instruction file:** `AGENTS.md` (project root).

## The four-dimension mapping

| Dimension | Claude Code | grok |
|---|---|---|
| Instruction file | `CLAUDE.md` | `AGENTS.md` |
| Hook layer | `settings.json` `hooks` | `~/.grok/hooks/*.json` (CC format) **or** `~/.claude/settings.json` compat |
| Skill trigger | `SKILL.md` frontmatter auto-trigger | `SKILL.md` in `.grok/`, auto-trigger + `/skill` |
| MCP config | `.mcp.json` | `[mcp_servers.*]` in `~/.grok/config.toml` |

## Steps

1. **Instruction file.** Use [`AGENTS.md`](../../AGENTS.md) at the repo root.
2. **MCP.** Copy [`config.toml.example`](config.toml.example)'s `[mcp_servers.*]` tables into
   `~/.grok/config.toml`. Supply credentials via env, never inline in the TOML.
3. **Hooks.** Copy [`hooks.json.example`](hooks.json.example) to `~/.grok/hooks/utopia.json` (or rely on
   the `~/.claude/settings.json` compat path if you already run CC on the same box). Project hooks require
   explicit trust via `/hooks-trust` or `--trust`.
4. **Skills.** Copy the skill folders into grok's `.grok/` skills dir (see "what degrades").

## What degrades / confirm

- **grok does NOT read `~/.claude/skills` or `CLAUDE.md`** (corrects an earlier assumption). Skills must
  live under `.grok/` (still `SKILL.md` format); the instruction file must be `AGENTS.md`, not `CLAUDE.md`.
  It DOES read `~/.claude/settings.json` for hooks in compat mode — that's the only `~/.claude` path it honors.
- **Stdin field names are camelCase** (`hookEventName`, `toolName`, `toolInput`) where CC uses snake_case
  (`hook_event_name`, `tool_name`, `tool_input`). Guardrail scripts that PARSE stdin fields must accept
  both; scripts that only branch on exit code / stderr are unaffected.
- **Tool-name matchers** assume grok's tool names match CC's (grok's is e.g. `run_terminal_command`);
  confirm and adjust the `matcher` regexes.
- **Secrets:** grok's `[mcp_servers.*]` `env = { ... }` table is inline TOML — do not put real tokens
  there; source them from the environment.

## Verified sources (2026-07-23)

- Hooks: `xai-org/grok-build` `crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md`
- MCP/config: `.../05-configuration.md`
