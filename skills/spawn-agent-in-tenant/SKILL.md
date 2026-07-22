---
name: spawn-agent-in-tenant
trigger: spawn agent, new agent, add an agent, new bot, new claude bot, stand up a bot, add a bot, clone an agent, new bot on host
description: >
  Stand up a NEW agent (a Claude-Code Telegram bot) on an EXISTING tenant (host/box),
  correctly, from the start. An agent = its own CC session + own config dir + own Claude
  account + own bot token + own launcher, isolated from the orchestrator and the other
  agents on the same host. The host itself is the "tenant"; to prepare a brand-new host use
  spawn-tenant. Encodes every gotcha learned the hard way (PATH/bun ENOENT, concurrent-
  refresh OAuth race, bypassPermissions accept-gate, resume-prompt wall, iatrogenic watchdog).
  Use when the user wants a new bot/agent, or to repair/rebuild an existing one to spec.
linter_ack: >
  This skill documents tenant isolation and the deny-belt, so it necessarily NAMES the
  commands and paths it BLOCKS (curl/wget/rm/sudo/tmux/kill, .env/.ssh, claude_ai_*) and
  the one-time `sudo -u <tenant> -i` OAuth-login step. These are security DOCUMENTATION
  (what to deny / how to log in as the tenant user), not executable exploit patterns.
---

# spawn-agent-in-tenant

An **agent** is a self-contained Claude-Code-as-Telegram-bot: its own `CLAUDE_CONFIG_DIR`,
its own Claude OAuth account, its own BotFather token + @handle, its own launcher, and
(for privacy-isolated agents) its own Linux user. The orchestrator, tenant-a, tenant-b and
tenant-c are agents. The **tenant** is the HOST/box they run on (e.g. a WSL machine); many
agents per tenant. This skill adds ONE agent to an existing tenant. To prepare a brand-new
host, use `spawn-tenant`.

> Terminology note: some steps below say "tenant" where they mean the AGENT's own per-bot
> artifact (its config dir, .env, Linux user). Read those as "the agent's". The only true
> tenant is the host. (Legacy wording from when a single bot was called a "tenant".)

**The golden rule: a new agent must look like the agents that already run for days without
dropping (e.g. a reference agent with 7d+ uptime). Diff against them, don't invent.** Before
declaring done, the new agent's launcher + settings + uptime behaviour should match a known-
stable peer. If it differs, the difference is a bug.

## 0. Security-first gate (NON-NEGOTIABLE, do this first)
- `python3 scripts/security/check_standdown.py <target>` before any install / mcp-add / settings edit.
- Never curl-pipe-bash. Node = official nodejs.org tarball, sha256-verified. claude-code = official `@anthropic-ai/claude-code` npm (CC is 7-day-rule exempt; first-party only).
- Bot token passed at RUNTIME via env var, written only to the tenant's `.env` (chmod 600, tenant-owned), NEVER echoed, NEVER committed.
- This is a CONFIRM-gate action (new infra). Auto-invoke `/scope` + helicopter 3-ripple before executing.

## 1. Decide the isolation level
| level | when | how |
|---|---|---|
| **OS-user isolation** (tenant-b, tenant-c) | external/privacy boundary (an external demo, a separate business) | separate Linux user + jailed 0700 home + tenant-local node/claude. Use a host/user provisioner script as the template. |
| **same-user, own config dir** (tenant-a) | internal-side bot, no privacy wall | same `<user>`, own `CLAUDE_CONFIG_DIR=<proj>/.cc-config` (chmod 700). |

`/home/<user>` must be `0750`/`0700` so OS-isolated tenants cannot traverse it (a symlink does NOT bypass dir-traversal perms - give the tenant its OWN node/claude inside its jail).

## 2. Prerequisites (gather before building)
1. **BotFather token** for the new bot (@handle).
2. **A DEDICATED Claude account for the tenant.** Each tenant does its OWN fresh `/login`. Account identity was proven NOT to be the cause of drops (a stable OS-isolated agent can share an account with another agent and stay stable) - so a dedicated account is for clean separation, not a churn fix. Do NOT put a churny tenant on a human's interactively-used account if avoidable, and NEVER share one credentials.json across two running instances.
3. **bun must be installed and on PATH** for the tenant (the telegram plugin spawns bare `bun`; see gotcha #1).
4. Allowed Telegram user IDs (operator + anyone permitted). Default deny everyone else.

## 3. The launcher (`run.sh`) - copy the WORKING pattern
All current tenants launch identically:
`claude --continue --name <tenant>-main --channels plugin:telegram@claude-plugins-official`
inside a tmux session. The launcher MUST do, in order:

1. `export CLAUDE_CONFIG_DIR=<dir>` (into the tmux shell, before claude).
2. **`export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"` BEFORE launching claude** - gotcha #1, the single most important line. Working launchers have it; the bug that cost a multi-day saga was a launcher missing it.
3. `--channels plugin:telegram@claude-plugins-official` (REQUIRED for inbound DMs; without it the bot can send but not receive).
4. **Single-instance enforcement**: sweep all procs tagged with this tenant's `CLAUDE_CONFIG_DIR` (TERM then KILL) + a `flock -n` mutex around the launch, so two launches can never interleave. Concurrent instances sharing one rotating refresh-token = the OAuth race = 401.
5. **Resume-prompt handling**: `--continue` on a large/old session shows an interactive "Resume from summary?" prompt that blocks headless boot. Mirror a working agent: a backgrounded `sleep 12; tmux send-keys "" Enter` auto-Enter, plus a stale-session guard (drop `--continue` if the newest session jsonl is too old/large).

Reference launcher: a working agent's `run.sh` (one that has the PATH fix). OS-isolation half: a host/user provisioner script.

## 4. Permissions (`settings.local.json`)
- Mode = **acceptEdits** (NOT bypassPermissions - gotcha #3: bypass has a startup accept-gate that defaults to "exit" and is not persisted, so it kills headless boot).
- **allow-list** (broaden to kill prompts): `Read(**)`, `Bash(*)`, `mcp__plugin_telegram_telegram__*`, scoped `Write` to the tenant's own dirs.
- **deny-belt** (the real guardrail, deny always wins even in bypass): `curl`, `wget`, `rm`, `sudo`, `crontab`, `systemctl`, `tmux`, `kill`, `pkill`, Write to OTHER tenants' dirs / `.agent-daemon` / `.claude`, Read `.env` / `.ssh` / wallet, `claude_ai_*` connectors.
- Edit settings via python `json.load`/`dump` (not manual, avoid fail-open). Back up first.

## 5. Optional watchdog - GENTLE only (gotcha #4: iatrogenic churn)
Reference agents run for days with NO watchdog. If you add one (boot-start + rare-death recovery):
- It MUST respawn via a `run.sh` that exports PATH (else every cron-respawn = bun ENOENT = dead-plugin loop = the 401 saga).
- **STOP on a 401 / "Please run /login"** - alert + halt, never restart-loop into an auth failure (restart cannot fix auth and each restart feeds the refresh race).
- NO aggressive preventive recycling (no "restart every Nh"). The "silent drop" such recycles chase is usually the PATH bug, not real.
- Prefer dead-plugin recovery + drift recovery only. Cron runs with minimal PATH - that is exactly why #3 PATH export matters.

## 6. OAuth login (interactive, user-action)
`tmux attach -t <tenant>-cc` (or `sudo -u <user> -i` then `claude`) → `/login` → pick the dedicated account → complete browser/device flow → detach. Cannot be done headlessly.

## 7. Verification checklist (must all pass before "done")
- [ ] exactly ONE tenant claude session + ONE bun poller (`pgrep`/`ps`, match by `CLAUDE_CONFIG_DIR`).
- [ ] `bun` resolves from the tenant's launch PATH (`env -i PATH=/usr/bin:/bin HOME=$HOME bash -c 'export PATH="$HOME/.bun/bin:$PATH"; command -v bun'`).
- [ ] auth token valid (`expiresAt` in `.credentials.json`, identity-only, never print the token).
- [ ] deny-belt intact (curl/rm/sudo/tmux/kill + Read .env/.ssh + claude_ai_* all denied).
- [ ] launcher has the PATH export line BEFORE the claude launch.
- [ ] smoke-test: DM the bot from an allowed account → it answers; DM from a non-allowed account → rejected.
- [ ] uptime behaviour matches a stable peer (launch once, runs; not recycling every few minutes).

## Anti-patterns (the saga, so nobody repeats it)
- ❌ Launcher missing the `.bun/bin` PATH export → cron-respawn `bun` ENOENT → poller dies → watchdog loop → refresh-token race → 401. **THE bug.**
- ❌ Aggressive watchdog (kill-sweep + relaunch every 2 min, "restart every 4h") → self-inflicted churn that races the OAuth token. The recovery mechanism becomes the failure source.
- ❌ `--permission-mode bypassPermissions` for a headless bot → startup accept-gate kills it. Use acceptEdits + allow-list.
- ❌ Two instances sharing one `.credentials.json` → rotating refresh-token race → both forced to `/login`.
- ❌ Blaming the OAuth account / API-key escalation before diffing the launcher against a working tenant. Diff against a working peer first.

## References
- a host/user provisioner script (OS-isolation provisioner — write your own)
- a working agent's PATH-fixed `run.sh` (the launcher pattern)
- a multi-bot dossier (full tenant history + the PATH root cause)
- diff against a working peer first (the meta-lesson)
- `docs/agent-protocols.md` (cross-tenant handoff)
