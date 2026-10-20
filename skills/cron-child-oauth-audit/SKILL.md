---
name: cron-child-oauth-audit
description: Diagnose a cron or daemon-spawned "claude --print" child that fails silently because it launched without an auth token, when a scheduled task's critic or subprocess returns ERROR or GATE_DOWN with duration_api_ms 0 on every firing.
trigger: cron child silent error, critic verdict ERROR, GATE_DOWN, tokenless claude child, spawned claude --print failing silently, cron critic error
---

# Cron-child OAuth audit: a silently tokenless spawned Claude child

## When to run this

A scheduled or daemon-spawned `claude --print` (or `-p`) subprocess fails the same way on every firing, with no reason string in `logs/errors.jsonl`, and the failure looks like: `rc != 0`, `duration_api_ms: 0`, `num_turns: 1`, `stop_reason: "stop_sequence"`. Auth fails before any real API call registers. In a long-running stack this shape tends to recur once per spawn site (the critic hook, the scheduler's own child launcher, a cron wrapper), so treat a new occurrence as this bug class first, before inventing a new theory.

## Procedure

1. **Find the spawn site.** Grep the daemon or scheduler code for the failing schedule's dispatch path (usually `subprocess.run` or `Popen` calling `claude --print` or `claude -p`). Check whether `env=` is passed explicitly.
2. **Check the parent's own environment.** With no `env=`, the child inherits the PARENT process's environment, not a login shell's. For a long-running daemon, check directly (`/proc/<daemon_pid>/environ`) whether `CLAUDE_CODE_OAUTH_TOKEN` is present. It usually is not: the setup-token file is loaded by interactive shells and by launchers that source it on purpose, not by every process a daemon forks.
3. **Confirm the failure signature before touching anything.** Pull a handful of the failing events' raw log lines. The tokenless shape is `duration_api_ms: 0` with `num_turns: 1` (fails before the first API call, not after running out of turns). A different shape (real `duration_api_ms` above 0, then a failure) is a different bug; do not apply this fix blind.
4. **Apply the fix with the shared helper, not a per-file copy.** In Python: `from lib_claude_child_env import child_env`, then pass `env=child_env()` to the subprocess call (`scripts/lib/lib_claude_child_env.py`). In shell launchers, source `scripts/lib/lib_claude_setup_auth.sh` before calling `claude`. Both load the long-lived setup token into a COPY of the environment and fail open (if the token is missing, the child still launches on whatever credentials exist). If the child could re-trigger the same critic or hook (recursion risk), also set the disable-guard env var the child's entry point already honors. One-time setup of the token: `scripts/session/install_setup_auth.sh`.
5. **Make future failures loud.** Add a failure branch that logs the real `rc` and stderr (or the parsed error) on a non-zero exit, instead of returning a generic `ERROR` or `OPERATOR_REVIEW` verdict with no reason. A logged reason turns a multi-day silent run into a same-day root cause.
6. **Validate before calling it done.** `py_compile` the changed file. Simulate both paths if you can (a good token gives a real API call; a forced bad token hits the new named failure branch with a captured reason). Restart whatever process holds the old module in memory: daemons cache imports, so editing the file alone does not apply the fix.
7. **Confirm live, not just in theory.** Watch the next 1 or 2 real firings of the affected schedules for a clean verdict (PASS, WARN or SHIP, not ERROR). Also check sibling schedules that share the same dispatch function: this bug class is usually function-wide, so a real fix shows up as a flip across every caller, not only the schedule that was noticed first. Cite the level from `knowledge/evidence-ladder.md` (the live firing is L5).

## Why a setup token and not copied credentials

A copied interactive credentials file refreshes on its own schedule. Several same-account processes refreshing independently invalidate each other, which shows up as random 401s and repeated re-login prompts. A `claude setup-token` credential has no refresh cycle, so there is nothing to race. Details in the header of `scripts/lib/lib_claude_setup_auth.sh`.

## Caveat

This is specifically the tokenless-child signature. Do not reach for this fix on a generically failing cron without first confirming the step 3 signature. A different bug wearing the same "verdict: ERROR" costume would get the wrong fix and stay hidden.
