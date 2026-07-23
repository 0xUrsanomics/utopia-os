# Utopia OS on OpenClaw

OpenClaw ([`openclaw/openclaw`](https://github.com/openclaw/openclaw), TypeScript) is a **medium-tier**
adapter. The portable substrate ports cleanly — the MCP daemon, the Markdown memory, and the `SKILL.md`
content all move unchanged — but the guardrail scripts do **not** port as-is. OpenClaw has no
"run a shell command on `PreToolUse` and block on exit 2" surface, so the six gates in
[`settings.example.json`](../../settings.example.json) must be re-expressed as one in-process
**TypeScript plugin**. That rewrite is what makes this medium, not low. See
[`docs/adapters.md`](../../docs/adapters.md) for the tier model. Verified against OpenClaw docs on 2026-07-23.

## Why OpenClaw is medium-tier

- **Instruction file, MCP, skills port directly.** `AGENTS.md` (plus `SOUL.md` / `USER.md`) is a
  recognized workspace bootstrap file; the daemon is a normal `mcp.servers` client entry; skills stay
  `SKILL.md` with YAML frontmatter and self-select. No rewrite.
- **Hooks are two layers, and the blocking layer is code.** OpenClaw's file-based `HOOK.md` + `handler.ts`
  hooks fire on coarse command/lifecycle events (`command:new`, `agent:bootstrap`, `message:sent`, …) and
  are **observation/side-effect only for policy — they cannot block a tool call**. Every gate that must
  block, rewrite params, require approval, or force one more pass is a **typed plugin hook** registered
  with `api.on(...)` inside a Plugin-SDK plugin. So the guard scripts become a plugin.
- **The logic still moves; only the wiring is new.** The plugin is a thin shim: each handler spawns the
  same portable Python gate under `scripts/` and maps its exit code / stdout to an OpenClaw decision. The
  ready-to-edit skeleton is in [`plugin/`](plugin/).

## The four-dimension mapping

| Dimension | Claude Code | OpenClaw |
|---|---|---|
| Instruction file | `CLAUDE.md` | [`AGENTS.md`](../../AGENTS.md) as a workspace bootstrap file (`SOUL.md`, `USER.md`, `MEMORY.md`, `BOOTSTRAP.md` also auto-inject) |
| Hook layer | `settings.json` `hooks` (shell commands) | typed plugin hooks via `api.on(...)` in a TS plugin ([`plugin/`](plugin/)); file-based `HOOK.md` only for coarse observe-only lifecycle |
| Skill trigger | `SKILL.md` frontmatter auto-trigger | `SKILL.md` + YAML frontmatter, LLM self-select + `/<name>`; ClawHub registry |
| MCP config | `.mcp.json` | `mcp.servers` in `~/.openclaw/openclaw.json` (JSON5) |

## Fast start: import from Claude Code

OpenClaw ships a **bundled** Claude migration provider (it is not a separately installed
`@openclaw/migrate-claude` package — invoke it directly):

```bash
openclaw migrate claude --dry-run          # preview the plan
openclaw migrate apply claude --yes        # apply
# or, on a fresh install:  openclaw onboard --import-from claude --import-source ~/.claude
```

It imports three of the four dimensions: project `CLAUDE.md` / `.claude/CLAUDE.md` → workspace `AGENTS.md`,
user `~/.claude/CLAUDE.md` → `USER.md`, MCP servers from `.mcp.json` / `~/.claude.json`, and skill
directories containing `SKILL.md` (Claude *commands* import as manual-invoke-only skills). It explicitly
does **not** import hooks — Claude hooks are copied into the migration report as manual-review items and
never executed. **That gap is exactly the plugin you write below.** Treat migrate as the substrate
fast-path, then add the guard plugin by hand.

## Steps

1. **Instruction file.** Put [`AGENTS.md`](../../AGENTS.md) in the agent workspace root. OpenClaw
   auto-injects recognized bootstrap basenames (`AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`,
   `HEARTBEAT.md`, `BOOTSTRAP.md`, `MEMORY.md`) every session — no hook needed. Drop the Utopia OS memory
   "parachute" in as `BOOTSTRAP.md` or `MEMORY.md` so it loads on every session start.
2. **MCP.** Copy [`openclaw.json.example`](openclaw.json.example)'s `mcp.servers` block into
   `~/.openclaw/openclaw.json`, or add each server with `openclaw mcp add <name> ...`. Point each at your
   daemon; supply credentials via env, never inline.
3. **Guard plugin.** Load [`plugin/`](plugin/) — for dev, add its `index.ts` to `plugins.load.paths`;
   to install, `openclaw plugins install -l /path/to/utopia-os/adapters/openclaw/plugin`. Set
   `plugins.entries."utopia-guards".hooks.allowConversationAccess: true` (the finalize/run gates are inert
   without it). Point the plugin at your checkout via the `utopiaRoot` config value or the `UTOPIA_OS_ROOT`
   env var. Read the next section before relying on it.
4. **Skills.** Copy the skill folders into a skill root (`<workspace>/skills`, `~/.openclaw/skills`, or a
   `skills.load.extraDirs` entry). Self-select and the `/<name>` slash command are preserved; the slash
   command comes from the frontmatter `name`. Publish/pull shared skills through ClawHub
   (`openclaw skills install @owner/<slug>`).

## What needs a plugin rewrite (the medium-tier work)

All six `settings.example.json` hooks collapse into the single plugin in [`plugin/index.ts`](plugin/index.ts).
Each Claude Code shell hook maps to a typed `api.on(...)` handler:

| `settings.example.json` hook | CC event | OpenClaw hook (`api.on`) | Decision surface |
|---|---|---|---|
| `check_standdown.py` | `PreToolUse[Bash]` | `before_tool_call` where `toolName ∈ {exec, bash}` | `{ block, blockReason }` / `{ requireApproval }` |
| `skill_linter.py` | `PreToolUse[Read\|Edit\|Write]` | `before_tool_call` where `toolName ∈ {read, write, edit, apply_patch}` | `{ block, blockReason }` |
| `verify_after_write.py` | `PostToolUse[Write\|Edit\|MultiEdit]` | `after_tool_call` where `toolName ∈ {write, edit, apply_patch}` | observe-only |
| `auto_compound_counter.py --reset` | `UserPromptSubmit` | `before_prompt_build` (per-turn side effect) | — |
| `bus_turn_poll.py` | `UserPromptSubmit` | `before_prompt_build` → `{ appendContext }` | context inject |
| `reply_guard.sh` | `Stop` | `before_agent_finalize` → `{ action: "revise" }` | force one more pass |
| `session_bootstrap.sh` | `SessionStart` | workspace bootstrap file + `session_start` (observe) for boot side-effects | — |

**The shim pattern.** Do not re-implement the gate logic in TypeScript. Each handler spawns the existing
Python script with `child_process.execFile`, writes the event to the child's stdin as JSON (the same
`--from-hook` contract the scripts already read), and translates the result:

- **`before_tool_call`** returns `{ block: true, blockReason }` to refuse, `{ params }` to rewrite the
  call, or `{ requireApproval: { title, description, severity } }` to pause for `/approve`. `block: true`
  is terminal and skips lower-priority handlers. Map the stand-down contract onto it: exit `2` → `block`,
  exit `1`/`3` (warn / expired) → `requireApproval`, exit `0` → allow.
- **`after_tool_call`** is observation-only — correct for verify-after-write, which only re-reads the
  written value and logs.
- **`before_agent_finalize`** is the `Stop` analog (OpenClaw states Codex-native `Stop` hooks are relayed
  into it). Return `{ action: "revise", reason }` to send the turn back for one more model pass, or omit a
  result to accept the natural final answer.
- **`before_prompt_build`** runs per turn and returns `{ prependContext | appendContext }` — the analog of
  a `UserPromptSubmit` hook that prints context to inject. Use it for both the counter reset (side effect)
  and the fleet-bus surface (`appendContext`).

**Tool-name rename is load-bearing.** OpenClaw's tools are `exec` (alias `bash`), `read`, `write`, `edit`,
`apply_patch` — not `Bash` / `Read` / `Edit` / `Write` / `MultiEdit`. The matcher sets in `index.ts`
already use the OpenClaw names; keep them in sync with your `tools.profile` (`group:fs`, `group:runtime`).

**Conversation access is opt-in.** `before_agent_run`, `before_agent_reply`, and `before_agent_finalize`
are inert unless the plugin sets `plugins.entries."utopia-guards".hooks.allowConversationAccess: true`.
`before_tool_call`, `after_tool_call`, and `before_prompt_build` need no such flag.

**Timeouts fail OPEN — the one real security caveat.** A per-hook `timeoutMs` budget only stops OpenClaw
*awaiting* the handler; it does not cancel it, and the decision is **dropped**, so a slow `before_tool_call`
gate lets the tool proceed. This is the opposite of Claude Code's `PreToolUse`, where a hung/`exit 2` hook
blocks. Keep the Python gates fast, give them a generous `timeoutMs` (the example sets 15 s), and never
rely on a slow gate to hold a block. Set budgets with `plugins.entries.<id>.hooks.timeouts.<hookName>`.

**Stand-down has a second, native surface.** The `before_tool_call[exec]` gate only sees installs run
through the shell (`npm`/`pip`/`cargo`). OpenClaw-native installs go through `openclaw plugins install` /
`openclaw skills install`, gated by the operator-owned, fail-closed **`security.installPolicy`** config
(and the observe-only `before_install` plugin hook). Wire the stand-down check into `security.installPolicy`
too so both install paths are covered. (Its exact field schema is not reproduced here — configure it from
the OpenClaw security docs; the adapter only asserts the surface exists and fails closed.)

## What degrades / confirm before relying on it

- **No shell-hook fallback.** Unlike the low-tier adapters, you cannot point OpenClaw at the Python scripts
  as commands. The plugin is mandatory for any gate that blocks. Budget the TS work.
- **Reply-guard is mostly redundant.** OpenClaw delivers the agent's final answer to the bound channel
  natively, so the Claude-Code-specific "the turn must end with a reply-tool call" concern largely
  dissolves. Keep `before_agent_finalize` only to enforce a non-empty / well-formed final answer.
- **Per-path secret denies don't map to `tools.deny`.** `tools.deny` is tool-name / group granularity, not
  path glob. `Read(./.env)` / `curl … | bash` protection is enforced by the guard plugin (`before_tool_call`
  inspecting `event.params` / `event.derivedPaths`) plus workspace sandboxing — not a config deny line.
- **Plugin API version pins.** `package.json` targets `openclaw >= 2026.3.24-beta.2`; OpenClaw moves fast
  and marks compatibility fields `@deprecated`. Confirm `api.on` hook names against your installed version
  (`openclaw plugins inspect utopia-guards --runtime --json`) before trusting the wiring.
- **Security gate before install.** OpenClaw is a large, fast-moving repo; run the Utopia OS stand-down /
  7-day-age check on OpenClaw itself and on any ClawHub plugin or skill before installing.

## Verified sources (2026-07-23)

- Plugin hooks (`api.on`, `before_tool_call` / `before_agent_run` / `before_agent_finalize` / `after_tool_call`, decision shapes, `allowConversationAccess`, timeout behavior): https://docs.openclaw.ai/plugins/hooks
- Internal file-based hooks (`HOOK.md` + `handler.ts`, event catalog, observe-only): https://docs.openclaw.ai/automation/hooks
- Building plugins (manifest, `definePluginEntry`, `openclaw plugins install`, ClawHub): https://docs.openclaw.ai/plugins/building-plugins
- MCP config (`mcp.servers`, stdio + HTTP fields, `openclaw mcp add`): https://docs.openclaw.ai/cli/mcp
- Configuration reference (JSON5, `~/.openclaw/openclaw.json`): https://docs.openclaw.ai/gateway/configuration-reference
- Tool names / groups (`exec`, `read`, `write`, `edit`, `apply_patch`; `tools.profile`): https://docs.openclaw.ai/gateway/config-tools
- Skills (`SKILL.md` frontmatter, precedence, `/<name>`, ClawHub): https://docs.openclaw.ai/tools/skills
- Claude migration (bundled provider; imports `AGENTS.md`/`USER.md`/MCP/skills, **not** hooks): https://docs.openclaw.ai/cli/migrate

---

Portable core: [`../../docs/adapters.md`](../../docs/adapters.md) · [`../../AGENTS.md`](../../AGENTS.md). This
adapter references the core by path; it never forks it.
