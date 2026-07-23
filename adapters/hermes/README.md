# Utopia OS on Hermes Agent (NousResearch)

Hermes is a **medium-tier** adapter. The portable substrate ports cleanly — Hermes is a
full MCP client, reads `AGENTS.md` natively, and takes `SKILL.md` skills — but the guardrail
layer splits: the stateless per-call guards run as **shell hooks**, while the stateful,
*blocking* gates (autonomy-mode veto, CONFIRM-gate binding, compound-counter threshold) must be
re-implemented as an **in-process Python plugin**. Verified against Hermes docs on 2026-07-23.
See [`../../docs/adapters.md`](../../docs/adapters.md) for the model and [`../../AGENTS.md`](../../AGENTS.md)
for the portable-core boundary.

> **Security note.** `NousResearch/hermes-agent` is an established repo (MIT, Python, created
> 2025-07-22), so it clears the 7-day age gate — but two things still warrant a stand-down check:
> the documented install path is `curl -fsSL …/install.sh | bash` (a curl-pipe-bash our own rules
> refuse blind), and installing a **catalog MCP** runs the entry's upstream `git clone` + bootstrap
> commands + the server's own code. Read the installer and any `optional-mcps/<name>/manifest.yaml`
> before running. The daemon servers you wire in `config.yaml` are your own, so they don't hit this.

## Why Hermes is medium-tier, not low

Three of the four dimensions are near 1:1; the hook layer is the cost.

- **Instruction file — ports as prose (correction to earlier recon).** Hermes reads `AGENTS.md`
  natively *and detects `CLAUDE.md` directly* (context-file priority `.hermes.md` → `AGENTS.md` →
  `CLAUDE.md` → `.cursorrules`, first match wins). `SOUL.md` is a separate **identity/voice** file
  (system-prompt slot #1, loaded from `HERMES_HOME` only) — it maps 1:1 to our `SOUL.md`, it is *not*
  the operational ruleset. So the ruleset prose is carried, not rewritten. The catch is that a context
  file is **prose, not enforcement**, and is truncated at `context_file_max_chars` (default 20,000).
- **Skill trigger — degrades to LLM-discretionary.** `SKILL.md` (agentskills.io-compatible) works, but
  Hermes selects skills by having the model read the `description` (progressive disclosure), plus explicit
  `/skill`. There is **no keyword-regex auto-fire**, so our `trigger:` frontmatter field is inert.
- **Hook layer — the real work.** Hermes has no `SessionStart`/`UserPromptSubmit`/`PreToolUse`/
  `PostToolUse`/`Stop` events, blocks via **stdout JSON not exit-code-2**, and names tools
  `terminal`/`read_file`/`write_file`/`patch`. Stateless guards survive that with a bridge; the
  stateful blocking gates want a Python plugin. This is the whole medium-tier delta — see
  [What needs a plugin rewrite](#what-needs-a-plugin-rewrite-and-how).

## The four-dimension mapping

| Dimension | Claude Code | Hermes |
|---|---|---|
| Instruction file | `CLAUDE.md` | `AGENTS.md` (native; `CLAUDE.md` also detected) + `SOUL.md` for voice; ~20K-char context cap |
| Hook layer | `settings.json` `hooks` | **shell hooks** (`hooks:` in `~/.hermes/config.yaml`) for stateless guards **+ Python plugin hooks** (`ctx.register_hook`, `pre_tool_call` can block) for the stateful gates; gateway hooks are observer-only |
| Skill trigger | `SKILL.md` frontmatter auto-trigger | `SKILL.md`, **LLM-discretionary** on `description` + `/skill` + bundles (no keyword regex) |
| MCP config | `.mcp.json` | `mcp_servers:` in `~/.hermes/config.yaml` (stdio + HTTP + OAuth) |

## Steps

1. **Instruction file.** Use [`../../AGENTS.md`](../../AGENTS.md) at the repo root; Hermes discovers it
   from the working directory at startup (and progressively in subdirectories). Map our voice file to
   `~/.hermes/SOUL.md`. Keep `AGENTS.md` under ~20K chars or it is head/tail truncated — trim to the
   always-on rules; the rest already lives in on-demand memory.
2. **MCP.** Copy the `mcp_servers:` block from [`config.yaml.example`](config.yaml.example) into
   `~/.hermes/config.yaml`. Point each server at your daemon; put every secret in `~/.hermes/.env` and
   reference it as `${VAR}` — never inline a token.
3. **Shell hooks (stateless guards).** Copy the `hooks:` block from
   [`config.yaml.example`](config.yaml.example). Each entry runs a core guard through
   [`hermes_shell_hook.sh`](hermes_shell_hook.sh), which translates our exit-2 block into Hermes's
   stdout-JSON block contract. Replace the `/path/to/…` placeholders. On first run Hermes prompts once
   per `(event, command)` and persists consent to `~/.hermes/shell-hooks-allowlist.json`; for a headless
   gateway/cron deployment set `hooks_auto_accept: true` (or `HERMES_ACCEPT_HOOKS=1`).
4. **Plugin (stateful/blocking gates).** Copy [`plugin.example/`](plugin.example/) to
   `~/.hermes/plugins/utopia-guardrails/` and set `UTOPIA_ROOT`. This carries the autonomy-mode veto,
   the CONFIRM-gate binding, and the compound-counter threshold-block — see below.
5. **Skills.** Point Hermes at the repo's `skills/` via an external skill directory (or copy into
   `~/.hermes/skills/`). Because triggering is LLM-discretionary, make each skill's `description`
   self-sufficient — the `trigger:` keyword list is not read.

## What needs a plugin rewrite (and how)

This is the medium-tier core. Two mechanical facts about Hermes drive everything:

**A. Event names don't exist; you remap to plugin-hook events.** Shell-hook and plugin-hook events are
the same set (`VALID_HOOKS`), and it is *not* Claude Code's set:

| Claude Code event | Utopia hook | Hermes event | Notes |
|---|---|---|---|
| `SessionStart` | `session_bootstrap.sh` | `on_session_start` | side effects only — **output is ignored**, so it can't inject the parachute text; inject that via `pre_llm_call` gated on `is_first_turn` |
| `UserPromptSubmit` | `auto_compound_counter --reset`, `bus_turn_poll` | `pre_llm_call` | docs are explicit: "UserPromptSubmit is intentionally not a separate Hermes event — `pre_llm_call` fires at the same place"; it is the **only** context-injection hook (`{"context": …}`) |
| `PreToolUse` | `check_standdown`, `skill_linter` | `pre_tool_call` | `matcher` (regex) supported; **can block** |
| `PostToolUse` | `verify_after_write` | `post_tool_call` | `matcher` supported; return ignored |
| `Stop` | `reply_guard.sh` | *(none)* | **degrades** — see below |

**B. Blocking is stdout JSON, not exit code 2.** On Hermes a non-zero exit only logs a warning; the
tool still runs. To veto, a hook prints `{"decision":"block","reason":"…"}` (Claude-Code shape,
accepted) or `{"action":"block","message":"…"}`. Context injection is `{"context":"…"}`. The stdin
payload *is* snake_case (`hook_event_name`/`tool_name`/`tool_input`), matching Claude Code — so our
`--from-hook` parsers work unchanged; only the **output** side needs translating.

### Stateless guards → shell hooks (via the bridge)

`check_standdown`, `skill_linter`, `verify_after_write`, `auto_compound_counter --reset`, and
`bus_turn_poll` are per-call and hold no cross-call decision state. They stay as the portable-core
scripts, invoked through [`hermes_shell_hook.sh`](hermes_shell_hook.sh), which:
runs the unmodified guard on the same stdin → maps **exit 2 → `{"decision":"block",…}`** → maps a
`pre_llm_call` guard's stdout → `{"context":…}` → otherwise emits `{}`. Tool matchers are rewritten to
Hermes names: `Bash`→`terminal`, `Read|Edit|Write`→`read_file|write_file|patch`,
`Write|Edit|MultiEdit`→`write_file|patch`.

### Stateful / blocking gates → Python plugin

These need shared in-process state and a single authoritative veto, so they move into
[`plugin.example/`](plugin.example/) (Hermes plugins are **Python-only**; ours already are, so this is
a wiring job — wrap each guard behind a `register_hook` callback and return the block dict instead of
exiting 2):

- **Autonomy-mode veto + CONFIRM-gate binding.** A `pre_tool_call` callback classifies the tool via
  `permissions.schema.json`; for a CONFIRM/BLOCKED-class tool it validates a fresh, hash-matching
  approval (`confirm_gate.py register`/`validate`) and returns `{"action":"block", …}` with a `/scope`
  restate when there is none. Prose in `AGENTS.md` documents the modes; this hook *enforces* them — the
  security-gates thesis is that a gate must live in the runtime, not the prompt.
- **Compound-counter threshold-block.** The `--reset` runs as a `pre_llm_call` shell hook, but the
  *block-on-threshold* wants the same `pre_tool_call` veto point holding per-domain counts, so the 4th
  AUTO op in a cascade returns a block, not a warning.

One plugin registers all four surfaces: `pre_tool_call` (the veto), `pre_llm_call` (bootstrap parachute
on first turn + fleet-bus + counter reset), `post_tool_call` (verify-after-write), `post_llm_call`
(reply-obligation logging).

### The one genuine loss: the `Stop` gate

Claude Code's `Stop` hook can force the agent to keep going (exit 2) when a turn ends without a
user-visible send — that's how `reply_guard` guarantees delivery. Hermes has **no blocking end-of-turn
hook**: `post_llm_call` fires once per turn but its return is ignored, and `pre_verify` *can* force a
continue but only fires when the agent edited code (and is capped by `agent.max_verify_nudges`). So
`reply_guard` degrades to an **observer** on `post_llm_call` — it can log a missed obligation, not
compel a retry. If delivery enforcement matters, put the send inside a tool and block its *absence* at
the `pre_tool_call`/`pre_verify` layer instead, or rely on the gateway's own delivery path.

## What else degrades / confirm

- **Skill auto-trigger.** LLM-discretionary only. Rewrite thin `trigger:`-dependent descriptions to be
  self-describing; consider a **bundle** for skill combos you fire together.
- **Instruction-file truncation.** ~20K-char default (`context_file_max_chars`) vs Codex's 32 KiB —
  smaller. Keep `AGENTS.md` lean.
- **Shell-hook consent on headless hosts.** A gateway/cron run with no TTY silently skips un-approved
  hooks unless `hooks_auto_accept: true` / `HERMES_ACCEPT_HOOKS=1` / `--accept-hooks` is set. Confirm
  before relying on a guard in production.
- **Config filename.** The live file is `~/.hermes/config.yaml`; the repo also ships a
  `cli-config.yaml.example` reference — same schema, don't confuse the two.
- **Tool-name matchers.** Verified from the docs as `terminal`/`read_file`/`write_file`/`patch`; if a
  Hermes release renames a tool, update the `matcher` regexes.
- **`command` runs `shell=False`** (`shlex.split`) — no inline pipes in a hook `command`; point at a
  script (the bridge is one).

## Verified sources (2026-07-23)

- Hooks (3 systems, events, block/inject contract, shell-hook schema): `NousResearch/hermes-agent`
  `website/docs/user-guide/features/hooks.md`
- Plugins (`register(ctx)`, `ctx.register_hook`, `plugin.yaml`): `.../developer-guide/plugins/index.md`
- MCP (`mcp_servers:` stdio/HTTP/OAuth, `${VAR}` substitution): `.../user-guide/features/mcp.md`
- Instruction/context files (`AGENTS.md` + `CLAUDE.md` detection, priority, 20K cap): `.../user-guide/features/context-files.md`
- Personality (`SOUL.md` identity, `HERMES_HOME`): `.../user-guide/features/personality.md`
- Skills (agentskills.io, `/skill`, bundles, LLM-discretionary): `.../user-guide/features/skills.md`
- Tool names / config (`~/.hermes/config.yaml`, `.env`, profiles): `.../user-guide/features/tools.md`, `.../user-guide/configuration.md`
- Repo metadata (MIT, created 2025-07-22): `gh api repos/NousResearch/hermes-agent`
