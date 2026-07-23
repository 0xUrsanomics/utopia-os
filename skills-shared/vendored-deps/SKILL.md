---
name: vendored-deps
description: Track manually-installed GitHub dependencies (tools/binaries/repos adopted OUTSIDE a package manager) for upstream updates we would otherwise silently miss.
trigger: vendored deps, dependency updates, check for updates, are our tools up to date, outdated tools, tool updates
allowed-tools: Bash, Read, Edit
---

# Vendored Dependency Update Tracker

## Why
We adopt tools from GitHub via MANUAL install (clone+build, release binary, git-source global) OUTSIDE a package manager (bun/npm/pip/cargo-registry). Those have no `update` command watching upstream, so we silently drift behind. A first run commonly catches a tool several releases behind upstream.

## Mechanism
- **Manifest**: `scripts/security/vendored-deps.json` = the inventory. Each dep: `{name, repo (owner/name), current (pinned version), method, check (release|tag), managed_by (manual|pkg-manager), notes}`. Empty `repo` = check disabled until filled.
- **Checker**: `scripts/security/vendored_deps_check.py` gh-api's each repo's latest release/tag, compares to `current`, flags STALE. Flags: `--json`, `--stale` (exit 1 if a MANUAL dep is stale, for cron alerting). It NEVER updates anything; report-only.

## Workflow
1. Run `python3 scripts/security/vendored_deps_check.py`.
2. Review STALE. `managed_by=manual` are the real targets (package-manager-managed deps self-update via their own tooling).
3. For each stale MANUAL dep you choose to update, respect the security gates:
   - **7-day age gate** (the checker shows the upstream release's age; too-new = wait).
   - `python3 scripts/security/check_standdown.py <repo>` (block/warn/clear).
   - READ the diff/changelog before updating. Never blind-update.
4. After updating, bump `current` in the manifest.

## Adding a dep
Whenever you adopt a GitHub tool outside a package manager, append it to `vendored-deps.json` (fill `repo` + pin `current`). Doc-mined *patterns* (one-time adoptions) are NOT tracked here (they do not "update"); only runnable installs. A stale doc-mine source is a re-mine opportunity, a separate call.

## Cadence
Optional weekly cron runs `--stale` and alerts on manual-dep drift (scheduler-create is CONFIRM-gated; offer it, do not auto-create).
