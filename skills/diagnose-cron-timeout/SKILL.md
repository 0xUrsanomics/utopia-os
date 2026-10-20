---
name: diagnose-cron-timeout
description: Decide whether a scheduled claude_code cron that ended "timed out" with an empty trace was cut at its time cap while still working, or truly hung, by reading the run's session transcript and any foreground subagent transcript. Read-only.
trigger: cron timed out, 0-byte trace, partial trace empty, cron trace out.log empty, did the cron hang or just run long, run hit the timeout cap
---

# Cron timeout: cap-kill or hang?

Use when the scheduler's `execution_log` shows `status=error` with output like "Claude Code session timed out (partial trace: <name>.out.log)". Read-only procedure, no daemon changes. The scheduler tables (`schedules`, `execution_log`) are the ones the scheduler MCP exposes (`docs/mcp-layer.md`); the paths below are placeholders for wherever your scheduler keeps its database and trace files.

## Steps

1. **Read the row.** Take `schedule_name`, `started_at`, `completed_at` and `task_config.timeout_seconds` from the scheduler database. Open it read-only: `sqlite3.connect("file:<scheduler.db>?mode=ro", uri=True)` from Python works even where the `sqlite3` CLI is not installed. A run time equal to `timeout_seconds` (for example exactly 25.0 min against a 1500 s cap) is a cap-kill, not a crash.
2. **Ignore the empty trace.** A `<traces>/<name>.out.log` of 0 bytes is expected: `claude --print` writes stdout once, at exit. It says nothing about where the run stalled.
3. **Find the session transcript:** `find ~/.claude/projects/<project-key> -maxdepth 1 -name '*.jsonl' -newermt "<start>" ! -newermt "<end>"`. A cron run is the one whose first user prompt is your cron prompt preamble and whose rows carry `entrypoint: sdk-cli`. The `<project-key>` is the working directory path with `/` replaced by `-`, so it differs per machine.
4. **Read the last `tool_use` in that transcript and its timestamp.**
   - A Write or Bash call shortly before the kill: the run was working and ran out of budget mid-step.
   - A foreground `Agent` call (`run_in_background: false`) as the last parent row: go to step 5.
5. **Open the subagent transcripts:** `<session-id>/subagents/agent-*.jsonl` (the `.meta.json` next to each names its task). Compare its last timestamp with the kill time and count its tool calls by name. Active within about a minute of the kill: budget exhaustion. Idle for minutes before the kill: a real hang in that tool call.
6. **Put the run in context before proposing a fix.** Take the last N durations for the same schedule from `execution_log` (median against the cap), and name what scales the slow step (new-item count, article count, channel count).
7. **Record it** in an Infra dossier for cron misses (`memory/Infra/<cron-misses>.md`) with the session ids and the verdict. Fixes (raise `timeout_seconds` and verify by reading it back, cap the slow step, split it into its own schedule) are CONFIRM-gated.

## Tools

Bash (`find`, `python3` with `sqlite3` read-only), Read. No Claude, chat or scheduler write calls.

## Output

A one-line verdict per run (cap-kill mid-write, cap-kill with a live subagent, or hang) plus the median-against-cap margin, appended to the dossier.

## Caveat

Step 3 depends on the transcript still existing. Transcripts and trace files are usually pruned on different schedules, so check both before concluding a run left no record.
