# Utopia OS on pi (earendil-works/pi)

pi is a **medium-tier** adapter. The portable substrate (MCP daemon, Markdown memory, `SKILL.md`
content) ports, and the instruction file + skills port with almost no change — but pi has **no
`settings.json` hooks block and no built-in MCP**, so the guardrail hooks must be re-authored as an
in-process TypeScript extension and MCP must be routed through a community adapter. Verified against
pi's in-repo docs + source on 2026-07-23. See [`../../docs/adapters.md`](../../docs/adapters.md) for the
model and [`../../AGENTS.md`](../../AGENTS.md) for the portable core.

> **Security note.** pi itself (`earendil-works/pi`, MIT, opened 2025-08, ~76k stars) is well past the
> 7-day age gate. The **MCP adapter is a separate community package** (`nicobailon/pi-mcp-adapter`, MIT,
> created 2026-01, ~1k stars). It clears the age gate, ships a test suite, and depends on the official
> `@modelcontextprotocol/sdk` — but it is single-maintainer and, like every pi extension, runs
> **in-process with pi's full permissions** (pi has no built-in sandbox). Treat it as a real dependency:
> read the source, pin the version, and run your stand-down + OSV check before `pi install` (step 3).

## What ports cleanly, and what doesn't

- **Instruction file — clean.** pi loads `AGENTS.md` **or** `CLAUDE.md` natively (candidate order
  `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD`; first match per directory), from `~/.pi/agent/`
  plus every directory walking up from the cwd. The repo-root [`AGENTS.md`](../../AGENTS.md) is picked up
  as-is.
- **Skills — near clean.** `SKILL.md` (agentskills.io standard). pi natively reads `~/.agents/skills/`
  and `~/.pi/agent/skills/` (plus project `.pi/skills/`, `.agents/skills/`); auto-triggers on the
  `description` and exposes `/skill:name`.
- **Hooks — needs a plugin.** pi's hook layer is **TypeScript extensions**, a superset of CC's hooks
  (a `tool_call` handler can block *and* mutate args, plus request/response HTTP-level interception and
  `/reload` hot-reload) — but there is **no `settings.json` hooks array** to translate into. The six
  guardrail hooks become one extension. This is the medium-tier work; see "What needs a plugin rewrite".
- **MCP — needs the community adapter.** pi's design principles state it *"intentionally does not include
  built-in MCP."* The daemon reaches pi only through `pi-mcp-adapter`, which reads a standard `mcpServers`
  block (so the config still ports 1:1).

## The four-dimension mapping

| Dimension | Claude Code | pi |
|---|---|---|
| Instruction file | `CLAUDE.md` | `AGENTS.md` (`CLAUDE.md` also read; **AGENTS.md wins if both in a dir**) — `~/.pi/agent/AGENTS.md` + walk-up from cwd |
| Hook layer | `settings.json` `hooks` | **TypeScript extension** in `~/.pi/agent/extensions/*.ts` (no hooks-config block; guards become one extension) |
| Skill trigger | `SKILL.md` frontmatter auto-trigger | `SKILL.md`, auto-trigger on `description` + `/skill:name`; native dirs `~/.agents/skills`, `~/.pi/agent/skills` |
| MCP config | `.mcp.json` | **no built-in MCP** — community `pi-mcp-adapter` reads a standard `mcpServers` block (`~/.pi/agent/mcp.json`, `.pi/mcp.json`, `.mcp.json`, `~/.config/mcp/mcp.json`) |

## Steps

1. **Instruction file.** [`AGENTS.md`](../../AGENTS.md) at the repo root is loaded when you run pi from
   the checkout; for a global rule set, copy it to `~/.pi/agent/AGENTS.md`. Keep `CLAUDE.md` and
   `AGENTS.md` from co-existing in the *same* directory expecting both to load — first match wins.
2. **Skills.** Copy the skill folders into `~/.agents/skills/` (the native agentskills.io path) or
   `~/.pi/agent/skills/`, **or** add your existing skills directory to the `skills` array in
   `~/.pi/agent/settings.json`. Auto-trigger is preserved (with the `/skill:name` caveat below).
3. **MCP.** Audit, then install the adapter: run `python3 scripts/security/check_standdown.py
   npm:pi-mcp-adapter` and an OSV check first; if clear, `pi install npm:pi-mcp-adapter` and restart.
   Then copy [`mcp.json.example`](mcp.json.example) to `~/.pi/agent/mcp.json` (or `.pi/mcp.json`), point
   each server at your daemon, and supply credentials via env — never inline a secret.
4. **Guards.** Copy [`utopia-guards.ts.example`](utopia-guards.ts.example) to
   `~/.pi/agent/extensions/utopia-guards.ts` and set `UTOPIA_ROOT` to your checkout. See the next
   section for how it maps the six hooks and what to confirm.

## What needs a plugin rewrite (the medium-tier work)

pi has no hooks-config file, so [`../../settings.example.json`](../../settings.example.json)'s six hooks
cannot be translated field-for-field the way they are for Codex/Kimi/grok. They collapse into **one
TypeScript extension** ([`utopia-guards.ts.example`](utopia-guards.ts.example)) that subscribes to pi's
lifecycle events.

**The gate scripts do NOT get rewritten.** `check_standdown.py`, `skill_linter.py`,
`auto_compound_counter.py`, `verify_after_write.py`, `session_bootstrap.sh`, and `reply_guard.sh` stay
in the portable core, shared byte-for-byte with the Claude Code deployment. What must be re-authored is
the **wiring**: pi hands your handler a typed event object, not CC's stdin-JSON payload, and expects a
typed return, not an exit code. The extension bridges the two.

**Event → gate mapping (verified event names + blockability):**

| `settings.example.json` hook | pi event | Blockable | Gate | Wiring |
|---|---|---|---|---|
| `SessionStart` | `session_start` | no | `session_bootstrap.sh` | spawn, inject stdout via `pi.sendMessage` |
| `UserPromptSubmit` | `turn_start` (or `input`) | no | `auto_compound_counter.py --reset` + `bus_turn_poll.py` | spawn both; surface bus output |
| `PreToolUse[Bash]` | `tool_call` where `toolName === "bash"` | **yes** | `check_standdown.py` | build stdin from `event.input.command`; exit 2 → `return { block: true, reason }` |
| `PreToolUse[Read\|Edit\|Write]` | `tool_call` where `toolName ∈ {read,edit,write}` | **yes** | `skill_linter.py` | lint skill-corpus paths; exit 2 → `{ block: true }` |
| `PostToolUse[Write\|Edit\|MultiEdit]` | `tool_execution_end` where `toolName ∈ {write,edit}` | no | `verify_after_write.py` | spawn, advisory |
| `Stop` | `agent_end` | no | `reply_guard.sh` | spawn, advisory |

**Why the security guarantee survives.** Only one pi event is blockable — `tool_call` — and it is exactly
the event the two load-bearing **security** gates (stand-down + skill-linter, both `PreToolUse`) map to.
pi's block contract (`{ block?: boolean; reason?: string }`, and mutate `event.input` in place to rewrite
args) is *strictly richer* than CC's exit-2. The other five hooks are advisory in Utopia OS (context
injection, a counter reset, a bus poll, a post-write check, a reply nudge) and map onto pi's observe-only
events (`session_start` / `turn_start` / `tool_execution_end` / `agent_end`) — which is precisely their
role. So the port changes the wiring, not the guarantees.

**Two implementation strategies (the skeleton ships strategy 1):**

1. **Shell-out shim (recommended).** The extension `spawnSync`s the unchanged Python/bash scripts,
   passing the event as JSON on stdin and mapping the exit code back to pi's control shape. ~100 lines of
   glue; the security logic stays in one audited place. Cost: a subprocess per gated tool call (a few ms)
   and you synthesize the stdin JSON pi doesn't hand you.
2. **Native TS for the hot path.** `tool_call` fires on every bash/read/edit/write. If subprocess latency
   matters, port *only* `check_standdown.py`'s registry match and `skill_linter.py`'s rule scan into
   TypeScript (the registry `memory/standdowns.json` and the rule table stay as data). This is the one
   genuine *logic* rewrite — and it is a latency optimization, not a correctness requirement.

**Confirm before relying:** the skeleton uses verified fields (`event.toolName`, `event.input.command`
for bash) but guesses per-tool input field names for write/edit (`input.path` / `input.file_path`).
Confirm against `packages/coding-agent/src/core/extensions/types.ts` for your pi version. The extension
runs with pi's full permissions and, when project-local, loads only after project-trust approval.

## What degrades / confirm

- **No built-in MCP** — the headline friction. Without `pi-mcp-adapter` the daemon (tools, memory,
  recall) is unreachable, which is most of the portable substrate. Audit + install it (step 3) before
  anything else works. Config still ports 1:1 once installed (standard `mcpServers`).
- **Skill auto-trigger is softer than CC.** pi injects skill `description`s into the system prompt and
  auto-loads on match, but pi's own docs warn *models don't always load the full `SKILL.md`* — use
  `/skill:name` or explicit prompting to force a must-fire skill. Deterministic frontmatter keyword-fire
  (CC) becomes model-discretionary.
- **Instruction file is first-match, not merge.** `AGENTS.md` and `CLAUDE.md` are both recognized but
  **not both loaded** when co-located; `AGENTS.md` wins. pi also does **not** read `~/.claude/CLAUDE.md`
  or `~/.claude/skills` automatically — point it at those via a global `~/.pi/agent/AGENTS.md` and the
  settings `skills` array.
- **`reply_guard` Stop analog** (`agent_end`) is observe-only and, in an interactive pi TUI, the reply is
  already visible — safe no-op unless you run pi headless into a delivery channel.
- **Scheduler / headless.** Re-point any headless `claude -p` invocations to pi's non-interactive mode
  (`pi -p` / `--mode json`), which also skips the project-trust prompt (relies on `defaultProjectTrust`).

## Verified sources (2026-07-23)

- Extensions / hook events + `tool_call` block contract: `earendil-works/pi`
  `packages/coding-agent/docs/extensions.md` and `src/core/extensions/types.ts`
- Skills (`SKILL.md`, dirs, `/skill:name`, auto-trigger caveat): `docs/skills.md`
- Instruction files (`AGENTS.md`/`CLAUDE.md` candidates, precedence): `docs/usage.md` and
  `src/core/resource-loader.ts`
- MCP intentionally absent + trust/sandbox model: `docs/usage.md` (design principles), `docs/security.md`
- MCP adapter (install, `mcpServers` config, stdio/HTTP, lazy lifecycle): `nicobailon/pi-mcp-adapter`
  `README.md`
