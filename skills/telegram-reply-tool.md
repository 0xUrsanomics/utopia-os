---
name: telegram-reply-tool
description: Enforcement protocol for always sending responses via the Telegram reply tool in interactive sessions. Tracks and prevents reply-tool misses.
trigger: telegram reply, reply tool, tg reply, send tg, always reply
allowed-tools: mcp__plugin_telegram_telegram__reply, mcp__telegram__telegram_send_message
---

# Telegram Reply Tool. Enforcement Protocol

## Tone & Voice

Enforcement skill. applies SILENTLY as background discipline. **NON-NEGOTIABLE rule** (CLAUDE.md Rule #1): every chat turn must end with a reply tool call, no exceptions. **NEVER** rely on bare transcript text as the reply. it's invisible to the operator (only the reply tool delivers via the chat channel). **Interactive sessions: NO active fallback** (using the daemon channel as a fallback respawns the poller and leaks a token). Plugin-only for interactive sessions.

## Output format

Behavioral skill. no artifact output. The skill's "output" is correct tool-call sequencing at the end of every chat turn:

1. Primary call: `mcp__plugin_telegram_telegram__reply(chat_id=..., reply_to=..., text=...)`
2. On error → **NO failover** (the daemon channel is blocked for interactive sessions). Log the miss + accept.
3. Log every call (success or failure) to `logs/session.jsonl` for stop-hook validation

**Note for cron/daemon sessions only**: `mcp__telegram__telegram_send_message` IS used for heartbeats (non-interactive). Never use the daemon MCP as an interactive fallback.

The stop-hook (`scripts/tg_reply_check.sh`) validates that every chat turn produced at least one successful reply call. Missing calls trigger a retry.

## Example output (call sequence)

```
Turn N attempt:
  1st: mcp__plugin_telegram_telegram__reply(chat_id=..., text=...)
      → SUCCESS or ACCEPTED MISS (no daemon fallback for interactive sessions)

Log:
  logs/session.jsonl ← {"event":"tg_reply_ok","primary":"plugin","outcome":"sent"}
  on miss: {"event":"reply_tool_miss","skill":"telegram-reply-tool","context":"<what was missed>"}
```

**Policy note**: the daemon fallback (`mcp__telegram__telegram_send_message`) is removed from interactive sessions. Using it respawns the chat poller and causes a token leak. A residual ~10% miss rate is the accepted ceiling. The stop-hook catches and logs misses — that IS the mitigation.

## Core Rule (CLAUDE.md Rule #1)
Every turn that produces output in a chat session MUST end with a reply tool call.
No exceptions. Bare text responses are invisible to the operator (terminal output only).

## When This Fires
- Any interactive session via the chat channel
- After completing any task (read, write, search, analyze)
- After fetching a URL/content the operator pasted
- After a tool-call chain completes (even if intermediate steps had errors)
- After silent-mode exits (driving mode, temp mode)

## Common Miss Patterns (from the failure ledger)
1. **Bare options relay**: listing "what's next" options as terminal text instead of a reply
2. **Silent completion**: finishing a task (file edit, list update) without confirming via chat
3. **URL fetch + no reply**: the operator pastes a URL, content is fetched, but no reply is sent
4. **Mid-task pause**: interrupting a multi-step task for input without a chat confirmation
5. **Session-start miss**: the first turn in a new chat session (context not fully loaded yet) ends without a reply. The stop-hook catches it. Rule applies from turn 1, no grace period.
6. **Multi-turn completion drift**: in tasks spanning 5+ tool calls, the final wrap-up reply gets dropped when the last tool call returns control. Explicit pattern: if you ran 5+ tools this turn, the reply tool is NOT optional regardless of perceived output volume.
7. **Post-reply tool call**: the reply tool fires but then another write (log, report save, session.jsonl append) runs AFTER it. The reply tool must be ABSOLUTE LAST. If you need to log, log BEFORE calling reply.
8. **Security/research chain completion gap**: after any turn involving a security audit, a stand-down write, or a multi-file research chain (5+ Bash+Read+Write tools), the final wrap-up reply is the most-dropped call. Root cause: the agent treats the session.jsonl log write as the "completion signal" and exits. Rule: if this turn touched `sandbox/`, `standdowns.json`, `outputs/raw/`, or ran 3+ security checks — call the reply tool BEFORE logging to session.jsonl, not after.

## HARD ORDERING RULE
The reply tool call MUST be the absolute LAST tool call in the turn. No tools after it. If you realize you need to run another tool (read, write, search), do it FIRST, then call the reply tool. The turn is not complete until the reply tool fires. The stop-hook is a safety net, not the primary guard. don't rely on it to catch the miss.

## Enforcement Checklist (run before ending ANY turn in a chat session)
- [ ] Did I produce any output this turn?
- [ ] Is this a chat session (including the first turn of a fresh session)?
- [ ] Have I called `mcp__plugin_telegram_telegram__reply`? (the daemon send_message is not for interactive sessions)
- [ ] Is the reply tool my LAST tool call (nothing queued after it)?
- [ ] Did this turn involve: a security audit / a stand-down / 3+ Bash security checks / writes to sandbox/ or outputs/raw/? → reply tool BEFORE the session.jsonl log, not after.
- If YES/YES/NO → call the reply tool NOW before finishing
- If YES/YES/YES but the reply tool is not last → move it to the last position

## Tool Priority
1. `mcp__plugin_telegram_telegram__reply`: the only valid tool for interactive sessions
2. `mcp__telegram__telegram_send_message`: cron heartbeats ONLY (not an interactive fallback)

## Cron/Daemon Session Exclusion

Rule #1 enforcement applies ONLY to interactive chat sessions (the operator initiates via the chat channel). Daemon-dispatched cron sessions end with `CRON-DONE <job_id>`, NOT a reply tool call.

**Stop-hook false-positive pattern**: the stop-hook can flag cron sessions as chat-session misses. These are NOT misses. The stop-hook must detect cron sessions before flagging:
- Cron signal: session stdout ends with a `CRON-DONE <job_id>` pattern
- Cron signal: the environment includes a scheduler `JOB_ID`, or the session was launched via the daemon scheduler

If running in a cron context: skip reply enforcement entirely. The heartbeat goes to `mcp__telegram__telegram_send_message` (the daemon MCP), NOT the plugin reply tool.

The stop-hook handles cron sessions via "break at the most-recent user message" logic. Cron sessions return NOT_TG and pass cleanly.

## Failure Logging
When a miss is detected (retroactively or in an audit), log to errors.jsonl:
```json
{"ts":"...","event":"reply_tool_miss","skill":"telegram-reply-tool","session_count":N,"context":"<what was missed>"}
```
3 misses in 14 days → the skill-failure tracker flags it for rewrite.

## Stop-Hook Miss vs Real Miss
A `stop_hook_tg_reply_miss_caught` entry in errors.jsonl = the stop-hook caught a miss AND retried. User impact was mitigated. The failure tracker counts hook catches the same as real misses. This is by design: the tracker threshold drives rewrites, not user-visible failures. ACCEPT CEILING: a ~10% miss rate with stop-hook recovery is the known floor. The goal of rewrites is to push the PRIMARY miss rate down, not to eliminate stop-hook recovery events.

## Known False Positive: Scheduled Sessions on --continue Transcripts
The stop-hook does a backwards walk on the transcript to find the last chat-marked user message. In `--continue` sessions (all scheduled daemon tasks), the transcript includes prior interactive chat-session history. The hook can find old anchors and flag the scheduled turn as a miss. inflating the failure count.

The stop-hook fix: the backwards walk now stops at the most-recent real user message only. Scheduled-session false-positives are largely eliminated. Remaining failures in the window are genuine misses or same-session-id --continue patterns.

**Same-session-id inflation pattern**: several catches sharing one session_id can be a single --continue chat session resumed multiple times, not that many separate behavioral misses. Each resumption triggers the hook against old anchors in the continued transcript. The structural fix above eliminates this class.

## What This Does NOT Do
- Does not fire in scheduled/daemon sessions (those use send_message directly)
- Does not override /temp mode behavior (temp mode = no writes, no chat)
- Does not apply to non-chat CLI sessions
- Does not require zero stop-hook catches (the stop-hook is intentionally a backstop)
