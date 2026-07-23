# Utopia OS on OpenAI Codex CLI (reference adapter)

Codex is the **lowest-cost** adapter and the reference that validates the portable-core / harness-shim
boundary in [`docs/adapters.md`](../../docs/adapters.md). Verified against Codex docs on 2026-07-23.

## Why Codex is near 1:1

- **Hooks:** Codex's lifecycle hooks include Claude Code's exact five events by the same names
  (`SessionStart`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`), with the same
  stdin-JSON payload, the same `exit code 2 = block` rule, and the same `hookSpecificOutput.permissionDecision`
  control shape. The guardrail scripts port with only a wrapper-format change.
- **MCP:** Codex is a full MCP client via `[mcp_servers.*]` TOML tables (stdio and HTTP).
- **Instruction file:** Codex reads `AGENTS.md` (already at the repo root).
- **Skills:** `SKILL.md`, auto-triggered on the `description` field plus `/skills`.

So this adapter is a **syntax translation, not a rewrite**.

## The four-dimension mapping

| Dimension | Claude Code | Codex CLI |
|---|---|---|
| Instruction file | `CLAUDE.md` | `AGENTS.md` (`~/.codex/AGENTS.md` + project chain, 32 KiB cap) |
| Hook layer | `settings.json` `hooks` | `hooks.json` or `[hooks]` in `config.toml` |
| Skill trigger | `SKILL.md` frontmatter auto-trigger | `SKILL.md`, auto-trigger on `description` |
| MCP config | `.mcp.json` | `[mcp_servers.*]` in `config.toml` |

## Steps

1. **Instruction file.** [`AGENTS.md`](../../AGENTS.md) is already at the repo root. **Gotcha:** Codex
   caps the instruction file at **32 KiB** (`project_doc_max_bytes`). A full always-loaded ruleset is
   usually larger, so trim `AGENTS.md` to the essential always-on rules (the rest already lives in
   on-demand memory), or raise `project_doc_max_bytes` in `config.toml`.
2. **MCP.** Copy [`config.toml.example`](config.toml.example) into `~/.codex/config.toml` (or merge
   the `[mcp_servers.*]` tables). Point each server at your daemon; set the referenced env vars for any
   credentialed server. Never inline a secret in the TOML.
3. **Hooks.** Copy [`hooks.json.example`](hooks.json.example) into `~/.codex/hooks.json` (or inline it
   as `[[hooks.*]]` in `config.toml`). These are the same guardrail scripts `settings.example.json`
   runs; only the wrapper changed. Replace the `/path/to/...` placeholders with your checkout path.
4. **Skills.** Copy the skill folders into Codex's skills directory; auto-trigger is preserved
   (matched on `description`).

## What degrades / confirm before relying on it

- **32 KiB instruction cap** (see step 1) — the single real constraint versus Claude Code.
- **Tool-name matchers.** `hooks.json.example` matches `Bash`, `Read|Edit|Write`, `Write|Edit|MultiEdit`.
  Confirm Codex uses the same tool names; if it renames tools, update the `matcher` regexes.
- **Multiple hooks per event.** Codex runs an array per event, so both `UserPromptSubmit` hooks port;
  confirm ordering if one must precede the other.
- **`reply_guard` Stop hook** assumes a Telegram channel; on a non-Telegram Codex session it is a
  safe no-op.
- **Skills dir path.** Docs show both `~/.codex/` and `~/.agents/skills` rooting; confirm against your
  Codex version.

## Verified sources (2026-07-23)

- Hooks: https://learn.chatgpt.com/docs/hooks
- MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
- AGENTS.md: https://learn.chatgpt.com/docs/agent-configuration/agents-md
