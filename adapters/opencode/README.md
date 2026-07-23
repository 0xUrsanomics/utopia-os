# Utopia OS on opencode

opencode is a **medium-tier** adapter: the portable substrate (MCP daemon, Markdown memory,
`SKILL.md` content) ports cleanly, but the guardrail hooks must be **re-implemented as an in-process
opencode plugin** — opencode has no shell-hook block — and skill auto-trigger degrades to a native
`skill` tool the model calls. Verified against opencode docs + the `@opencode-ai/plugin` types on
2026-07-23. See [`../../docs/adapters.md`](../../docs/adapters.md) for the model and
[`../../AGENTS.md`](../../AGENTS.md) for the portable-core boundary.

> **Repo note:** the project is now **`anomalyco/opencode`** (MIT, TypeScript, created 2025-04-30;
> the old `sst/opencode` URL redirects to it). Well past the 7-day age gate, but re-run your
> stand-down check before installing, and confirm the owner hasn't moved again.

## Why opencode is medium-tier (not 1:1)

- **MCP: direct.** Full MCP client via the `"mcp"` block in `opencode.json`/`opencode.jsonc`
  (`type:"local"` process or `type:"remote"` HTTP, with auto-OAuth). Ship a config template.
- **Instruction file: direct.** opencode reads `AGENTS.md` (repo root + `~/.config/opencode/AGENTS.md`)
  **and** `CLAUDE.md` in Claude Code compat mode (project `CLAUDE.md` + `~/.claude/CLAUDE.md`). The
  canonical `CLAUDE.md` is read as-is.
- **Hooks: rewrite required.** opencode's hook layer is **in-process JS/TS plugin functions**
  (`tool.execute.before`, `event`, …), not a `settings.json` array of shell commands. The six guard
  scripts can't be pointed at directly; they need a thin plugin shim (shipped here) that shells out
  to them. This is the load-bearing medium-tier cost.
- **Skills: degraded.** `SKILL.md` content ports, but there is **no keyword / frontmatter / semantic
  auto-fire**. opencode exposes a native `skill` tool; the model self-selects from the catalog
  (name + description) by calling `skill({ name })`. Utopia OS's deterministic routing
  (`trigger:` frontmatter, `routing.json`, vector recall) has no equivalent — **this is the sharpest
  degradation**.

## The four-dimension mapping

| Dimension | Claude Code | opencode |
|---|---|---|
| Instruction file | `CLAUDE.md` | `AGENTS.md` + `CLAUDE.md` compat (`~/.claude/CLAUDE.md` global) |
| Hook layer | `settings.json` `hooks` (shell) | **plugin** in `.opencode/plugins/*.ts` (`@opencode-ai/plugin`) |
| Skill trigger | `SKILL.md` frontmatter auto-trigger | `SKILL.md`, **manual `skill({name})` only** (no auto-fire) |
| MCP config | `.mcp.json` | `"mcp"` block in `opencode.json` / `opencode.jsonc` |

## Hook event mapping (the rewrite target)

| Claude Code hook | opencode hook / event | Blocks? |
|---|---|---|
| `SessionStart` | `event` bus → `session.created` | no (side-effect) |
| `UserPromptSubmit` | `chat.message` hook (fires per operator message) | no (advisory) |
| `PreToolUse` [Bash] | `tool.execute.before` (filter `input.tool === "bash"`) | **yes — `throw` aborts the tool** |
| `PreToolUse` [Read/Edit/Write] | `tool.execute.before` (`read`/`edit`/`write`) | **yes — `throw`** |
| `PostToolUse` [Write/Edit] | `tool.execute.after` | no (post-hoc) |
| `Stop` | `event` bus → `session.idle` | no (side-effect) |
| (`PermissionRequest`) | `permission.ask` hook (set `output.status`) | **yes — `"deny"`** |
| (`PreCompact`) | `experimental.session.compacting` | n/a (mutates context) |

## Steps

1. **Instruction file.** Nothing to do — [`AGENTS.md`](../../AGENTS.md) is at the repo root and points
   at `CLAUDE.md`, which opencode reads in compat mode. Optionally pin extra files via the
   `"instructions"` array (see the config example).
2. **MCP.** Copy [`opencode.jsonc.example`](opencode.jsonc.example) to `opencode.jsonc` (or merge the
   `"mcp"` block). Point each server at your daemon; supply credentials with `{env:VAR}`, never inline.
   Note the schema: `command` is a **single array** `["python3", "…"]`, and the env field is
   `"environment"` (not `"env"`).
3. **Hooks → plugin.** Copy [`plugins/utopia-guard.ts`](plugins/utopia-guard.ts) into
   `.opencode/plugins/` (or `~/.config/opencode/plugins/`). It auto-loads at startup and maps the six
   guardrails onto opencode hooks, shelling out to the unchanged guard scripts. Set `UTOPIA_OS_ROOT`
   (or edit the `/path/to/utopia-os` default). See the next section for what it does and its limits.
4. **Skills.** Copy the skill folders into opencode's skills directory. They work, but auto-trigger is
   **lost** — the model invokes each via `skill({ name })`. See "What degrades".

## What needs a plugin rewrite (and how)

The other adapters (Codex, Kimi, grok) are syntax translations: the harness accepts a shell-hook
block, so the same `session_bootstrap.sh` / `check_standdown.py` / … run untouched behind a JSON or
TOML wrapper. **opencode has no such block.** Its only extension point for lifecycle events is a
plugin: a JS/TS module in `.opencode/plugins/` that `export`s an async function returning a `Hooks`
object. So the guardrail *wiring* — not the guard *logic* — must be rewritten in **TypeScript/JavaScript
(Bun runtime)**.

The good news: it's a **thin shim, not a port of the logic**. Every guard script stays in Python/bash.
The plugin's whole job is to translate opencode's hook I/O into the scripts' existing CLI/stdin/exit-code
contract, using Bun's `$` shell (injected into the plugin as `$`). The shipped
[`plugins/utopia-guard.ts`](plugins/utopia-guard.ts) does exactly this. What the rewrite has to get
right, guard by guard:

- **`session_bootstrap.sh` (SessionStart).** No dedicated hook; subscribe to the `event` bus and match
  `event.type === "session.created"`. Side-effect only — it loads the parachute, it can't gate the turn.
- **`auto_compound_counter.py --reset` + `bus_turn_poll.py` (UserPromptSubmit).** Map to the
  `chat.message` hook, which fires on each operator message. Advisory: opencode has no stdout-injection
  contract like CC's `UserPromptSubmit`, so surface results, don't expect a hard pre-prompt block.
- **`check_standdown.py` (PreToolUse[Bash]).** In `tool.execute.before`, filter `input.tool === "bash"`,
  read the command off `output.args.command`, run `check_standdown.py --pattern <cmd>`, and **`throw` on
  exit 2** — throwing in `tool.execute.before` aborts the tool (opencode's documented `.env`-block
  pattern). Warn (exit 1) / expired (exit 3) are surfaced, not thrown.
- **`skill_linter.py` (PreToolUse[Read|Edit|Write]).** Same hook, filter `read`/`edit`/`write`, take the
  path off `output.args.filePath`, run the linter, `throw` on the fail tier (`verdict_exit`: fail/error
  = 2). This is a real, enforced block.
- **`verify_after_write.py` (PostToolUse).** Map to `tool.execute.after` for `write`/`edit`. The write
  already landed, so this is verification only — it **cannot block**. The script reads a hook payload on
  stdin, so the shim pipes a small JSON in (`< ${Buffer.from(...)}`).
- **`reply_guard.sh` (Stop).** Subscribe to `event.type === "session.idle"` (opencode's documented
  end-of-turn signal). Best-effort nudge; it can't re-open a finished turn.

Two contract details the rewrite must honor, both different from Claude Code:

- **Tool names are lowercase** (`bash`, `read`, `edit`, `write`) and arguments live on `output.args`
  (`output.args.command`, `output.args.filePath`) — not CC's capitalized `Bash`/`Read` and
  `tool_input`. Matchers that assume CC names silently never fire.
- **Blocking is `throw`, not exit-2-on-stdin.** A guard's exit code has no meaning to opencode; the
  plugin reads it (via Bun `$`'s `.nothrow().exitCode`) and decides whether to `throw`. For
  permission-style gates use the `permission.ask` hook and set `output.status = "deny"`.

If you'd rather not maintain a plugin, the fallback is the same as any hookless target: run the two
critical gates (`check_standdown.py`, the send guards) manually before installs and outbound actions.
The plugin exists so they fire automatically.

## What degrades / confirm before relying on it

- **Skill auto-trigger is gone (sharpest).** No `trigger:` frontmatter, no `routing.json`, no semantic
  recall routing. The model must pick from the `skill` tool's description catalog and call
  `skill({ name })`. Keep skill `description` fields sharp — they are now the *only* selection signal.
- **UserPromptSubmit / Stop can't block.** `chat.message`, `session.created`, and `session.idle` are
  advisory. Only `tool.execute.before` (throw) and `permission.ask` (`output.status`) are hard gates.
- **`permission.ask` vs `permission.asked`.** The veto hook is `permission.ask` (singular). The
  `permission.asked` *event* is read-only and fires after — do not wire a gate to it.
- **`permission.ask` is under-documented.** Its `output.status` control comes from the plugin `Hooks`
  type, not the prose docs; smoke-test a deny before relying on it.
- **MCP schema differs from CC.** `command` is one array; env is `"environment"`; per-server `type` is
  required. A `.mcp.json` copied verbatim will not load.
- **Bun-only APIs.** The shim uses Bun's `$` (`.cwd`/`.nothrow`/`.quiet`, `< ${Buffer}` stdin). It runs
  inside opencode (Bun); it is not portable to a plain Node plugin loader.
- **`reply_guard.sh` assumes a Telegram channel.** On a non-Telegram opencode session it is a safe no-op.

## Verified sources (2026-07-23)

- MCP config: https://opencode.ai/docs/mcp-servers/
- Plugins (hooks, `.opencode/plugins/`, `event`/`session.idle`, throw-to-block, `$` shell): https://opencode.ai/docs/plugins/
- `Hooks` type (`permission.ask`, `chat.message`, `tool.execute.*`, `experimental.session.compacting`): `@opencode-ai/plugin` (`anomalyco/opencode`, `packages/plugin`)
- Rules / instruction files (`AGENTS.md` + `CLAUDE.md` compat): https://opencode.ai/docs/rules/
- Skills (`SKILL.md`, manual `skill({name})` invoke): https://opencode.ai/docs/skills/
- Config (`{env:VAR}`/`{file:}` substitution, `opencode.jsonc`): https://opencode.ai/docs/config/
- Repo owner / license / age: `gh api repos/anomalyco/opencode`
