# Utopia OS on Kimi Code (Moonshot AI)

Kimi Code is a **low-cost** adapter (near 1:1 with Claude Code), like Codex. Verified against Kimi's
docs on 2026-07-23. See [`docs/adapters.md`](../../docs/adapters.md) for the model.

## Why Kimi is near 1:1

- **Hooks:** `[[hooks]]` entries in `~/.kimi-code/config.toml` fire on 16 lifecycle events including CC's
  `SessionStart` / `UserPromptSubmit` / `PreToolUse` / `PostToolUse` / `Stop`, with the same stdin-JSON,
  the same `exit 2 = block`, and the same `hookSpecificOutput.permissionDecision` contract (fail-open by
  design). Blockable: `UserPromptSubmit`, `PreToolUse`, `Stop`.
- **MCP:** `~/.kimi-code/mcp.json` uses the same `mcpServers` object as CC's `.mcp.json` (stdio + http/sse).
- **Instruction file:** Kimi reads `AGENTS.md` natively (and its agent loader even parses CC-style
  frontmatter).
- **Skills:** `SKILL.md`, auto-triggered on `description` / `whenToUse` (opt out with `type = "flow"` or
  `disableModelInvocation`).

## The four-dimension mapping

| Dimension | Claude Code | Kimi Code |
|---|---|---|
| Instruction file | `CLAUDE.md` | `AGENTS.md` (`~/.kimi-code/AGENTS.md` + project) |
| Hook layer | `settings.json` `hooks` | `[[hooks]]` in `~/.kimi-code/config.toml` |
| Skill trigger | `SKILL.md` frontmatter auto-trigger | `SKILL.md`, `description`/`whenToUse` auto-trigger |
| MCP config | `.mcp.json` | `~/.kimi-code/mcp.json` (`mcpServers`, CC-shaped) |

## Steps

1. **Instruction file.** [`AGENTS.md`](../../AGENTS.md) is already at the repo root; also works at
   `~/.kimi-code/AGENTS.md`.
2. **MCP.** Copy [`mcp.json.example`](mcp.json.example) to `~/.kimi-code/mcp.json` (or `.kimi-code/mcp.json`
   in the project). Point each server at your daemon; supply credentials via env, never inline.
3. **Hooks.** Merge [`config.toml.example`](config.toml.example)'s `[[hooks]]` blocks into
   `~/.kimi-code/config.toml`. Same guardrail scripts `settings.example.json` runs, re-expressed as TOML.
   Replace the `/path/to/...` placeholders.
4. **Skills.** Copy the skill folders into Kimi's skills dir; auto-trigger is preserved.

## What degrades / confirm

- **`[[hooks]]` allows only four fields** (`event`, `matcher`, `command`, `timeout`) — any extra field
  fails the config load. Keep entries minimal.
- **Scheduler / headless.** Re-point any headless `claude -p` calls to `kimi -p`.
- **Tool-name matchers** (`Bash`, `Read|Edit|Write`, ...) assume Kimi's tool names match CC's; confirm and
  adjust the `matcher` regexes if not.
- Agent-selection / system-prompt overrides sit behind the experimental `KIMI_CODE_EXPERIMENTAL_FLAG=1`
  v2 engine per Kimi's docs.

## Verified sources (2026-07-23)

- Hooks: `MoonshotAI/kimi-code` `docs/en/customization/hooks.md`
- MCP: `docs/en/customization/mcp.md`
- Instruction/skills: `docs/en/customization/{agents,skills}.md`
