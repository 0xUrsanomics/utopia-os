---
name: spawn-tenant
trigger: spawn tenant, new tenant, new host, provision host, new box, new machine, set up a new server, deploy to a new machine, new agent host, prepare a host, bootstrap a box
description: >
  Prepare a brand-new TENANT (a host / box / VM / WSL instance) so it can run one or more
  Claude-Code Telegram agents. This is the HOST-level substrate: OS users, verified
  toolchain (node + bun + claude CLI + tmux + python), permission/isolation baseline,
  shared infra (memory/logs, optional daemon + MCP), backup + watchdog framework. Once the
  tenant is ready, you add bots to it with spawn-agent-in-tenant. Use when deploying to a
  NEW machine (e.g. a second WSL box, zenbook, Oracle Cloud), NOT when adding a bot to a
  host that already runs agents (that is spawn-agent-in-tenant).
linter_ack: >
  Documents host hardening, so it names the isolation/deny baseline (0700/0750 homes, no
  sudo/docker groups, deny-belt) and the one-time per-user OAuth login. Security
  documentation, not exploit code. Reviewed safe 2026-06-04.
---

# spawn-tenant

A **tenant** is the HOST a fleet of agents runs on: a box / VM / WSL instance (e.g. a primary
WSL machine, a laptop, or a cloud ARM box). A tenant provides the shared substrate; the
individual bots (tenant-a, tenant-b, a coach persona, the orchestrator) are **agents** layered
on top via `spawn-agent-in-tenant`. One tenant, many agents.

Use this skill only to stand up a NEW host. To add a bot to an existing host, skip straight
to `spawn-agent-in-tenant`.

## 0. Security-first gate (NON-NEGOTIABLE)
- `python3 scripts/security/check_standdown.py <target>` before any package install.
- Toolchain from official sources only, verified: node = nodejs.org tarball + sha256 against SHASUMS256.txt; claude CLI = `@anthropic-ai/claude-code` npm (CC is 7-day-exempt, first-party); bun = official installer pinned + checksum. NEVER curl-pipe-bash blind.
- CONFIRM-gate (new infra). Auto-invoke `/scope` + 3-ripple helicopter before executing on the box.

## 1. Host prerequisites
- A reachable machine you control (WSL instance, VM, or bare host) with a normal sudo user for provisioning.
- Outbound network to nodejs.org / npm / Anthropic / Telegram.
- Decide boot-survival: how the host comes up after reboot (Windows Task Scheduler keepalive for WSL; systemd for a real VM). This is the tenant's job, not each agent's.

## 2. Base toolchain (install once per host)
1. **node** (official tarball, sha256-verified) at a stable path. For OS-isolated agents, each agent user gets its OWN node under its jail (a symlink does not bypass dir-traversal perms); for same-user agents, a shared user-level node is fine.
2. **bun** - REQUIRED. The official Telegram plugin spawns its poller via bare `bun` (`.mcp.json` command `bun`). Install bun to `~/.bun/bin` and make sure that dir is reachable from BOTH interactive shells AND cron (see #4). The single most common host-level bug is bun present interactively but absent on cron's PATH.
3. **claude CLI** = `@anthropic-ai/claude-code` (official). One per agent home for isolated agents.
4. **tmux**, **python3 + venv**, git.

## 3. Users + isolation baseline
- For privacy-isolated agents (external / untrusted): one Linux user per agent, jailed `0700` home, NO sudo/docker/adm/wheel groups. Use a host/user provisioner script (write your own) that creates the user, installs a tenant-local node/claude, applies deny-all settings, and runs a perms check.
- Set the provisioning user's home to `0750`/`0700` so jailed agents cannot traverse it.
- For internal same-user agents: each gets its own `CLAUDE_CONFIG_DIR` (chmod 700) under its project dir.

## 4. PATH discipline (host-level, prevents the #1 agent bug)
Cron runs with a minimal PATH (`/usr/bin:/bin`). Any agent launcher or watchdog invoked by cron must export `~/.bun/bin` (and `~/.local/bin`) BEFORE launching claude, or the bun poller hits ENOENT and the agent goes deaf. Bake this into the host's launcher template so every agent inherits it. See `memory/Feedback/diff-against-working-peer-first.md` and `spawn-agent-in-tenant` section 3.

## 5. Shared infra (optional, host-level)
- **Memory + logs**: a per-agent `memory/` + `logs/` tree (agents stay amnesiac of each other unless explicitly bridged).
- **Daemon + MCP**: if the host runs an agent daemon (telegram/memory/graph/scheduler/sheets/etc.), point agents at the cron MCP config. A fresh host may run agents standalone (telegram plugin only) with no daemon.
- **Backup**: register the new host's critical paths into the backup rotation.
- **Watchdog framework**: a GENTLE per-agent watchdog only (boot-start + dead-poller recovery). It MUST respawn via a PATH-exporting launcher and STOP on a 401 (never restart-loop into auth-dead). NO aggressive 2-min kill-sweep, NO Nh preventive recycle (those are iatrogenic churn).

## 6. Verification (host is "ready")
- [ ] `node`, `bun`, `claude`, `tmux`, `python3` all resolve for the intended agent user(s).
- [ ] `bun` resolves under a SIMULATED cron PATH: `env -i PATH=/usr/bin:/bin HOME=<agent_home> bash -c 'export PATH="$HOME/.bun/bin:$PATH"; command -v bun'`.
- [ ] provisioning user home is `0750`/`0700` (isolation holds).
- [ ] boot-survival mechanism in place + tested (reboot brings the host back).
- [ ] a throwaway agent can be stood up via `spawn-agent-in-tenant` and reaches Telegram (+ MCP/daemon if used).

## Anti-patterns
- Installing bun only on the interactive PATH -> every cron-launched agent breaks (a classic multi-day PATH saga, host-level form).
- A host-wide aggressive watchdog -> fleet-wide churn. Keep recovery gentle + per-agent.
- Sharing one Claude account's single `.credentials.json` across agents that both run -> rotating refresh-token race. One account (or at least one credentials file) per running agent.
- Treating "add a bot" as a host task: if the host already runs agents, use `spawn-agent-in-tenant`, do not re-provision the host.

## References
- a host/user provisioner script (write your own: user creation, tenant-local node/claude, OS isolation)
- `skills/spawn-agent-in-tenant.md` (the per-bot half: add an agent to a ready tenant)
- a multi-bot dossier (the PATH root cause + gentle-watchdog rule)
- diff a new host against a working peer before theorizing (a debugging discipline)
