---
name: schedule
description: "Create a scheduled task that can be run on demand or automatically on an interval. Use when the user says 'schedule X', 'remind me in N minutes', 'every weekday at 9am', or wants to convert a session task into a recurring/one-shot cron job. Outputs a create_scheduled_task tool call with cronExpression OR fireAt fields filled correctly."
trigger: schedule, manage schedule, calendar, scheduling, cron, remind me
---

# Schedule (create reusable session shortcut)

## Tone & Rules

Internal infrastructure skill. output is a tool call, not prose. Keep prompts terse, self-contained, second-person imperative. **Hard rule**: future runs do NOT inherit the current conversation. The drafted prompt must be 100% standalone.

## Source & Pairs with

- `knowledge/scheduled-tasks.md`. model selection rule (haiku/sonnet/opus tiering) + `task_config` schema. **Read this BEFORE drafting any claude_code-type task.**
- `memory/Infra/permissions-schema.json`. autonomy-mode mapping (which task types need CONFIRM)
- Your daemon scheduler's database, table `schedules` (destination)
- Sister tool: `mcp__scheduler__schedule_create` (the actual tool call this skill ends with)

## Conversation context (prior)

The skill EXPECTS prior conversation. that's the WHOLE POINT. It captures the task the user just performed/described in the current session and freezes it into a reusable prompt. Skim the recent turns for: tools used, sequence of steps, corrections, input/output formats.

## Procedure

You are creating a reusable shortcut from the current session. Follow these steps:

### Step 1. Analyze the session

Review the session history to identify the core task the user performed or requested. Distill it into a single, repeatable objective.

### Step 2. Draft a prompt

The prompt will be used for future autonomous runs. it must be entirely self-contained. Future runs will NOT have access to this session, so never reference "the current conversation," "the above," or any ephemeral context.

Include in the description:
- A clear objective statement (what to accomplish)
- Specific steps to execute
- Any relevant file paths, URLs, repositories, or tool names
- Expected output or success criteria
- Any constraints or preferences the user expressed

Write the description in second-person imperative ("Check the inbox…", "Run the test suite…"). Keep it concise but complete enough that another Claude session could execute it cold.

### Step 3. Choose a taskName

Pick a short, descriptive name in kebab-case (e.g. "daily-inbox-summary", "weekly-dep-audit", "format-pr-description").

### Step 4. Determine scheduling

Pick one:
- **Recurring** ("every morning", "weekdays at 5pm", "hourly") → `cronExpression`
- **One-time with a specific moment** ("remind me in 5 minutes", "tomorrow at 3pm", "next Friday") → `fireAt` ISO timestamp
- **Ad-hoc** (no automatic run; user will trigger manually) → omit both
- **Ambiguous** → propose a schedule and ask the user to confirm before proceeding

**cronExpression:** Evaluated in the user's LOCAL timezone, not UTC. Use local times directly. e.g. "8am every Friday" → `0 8 * * 5`.

**fireAt:** Compute the exact moment and emit a full ISO 8601 string with timezone offset, e.g. `2026-03-05T14:30:00-08:00`. Never use cron for one-time tasks. cron has no one-shot semantics.

Finally, call the "create_scheduled_task" tool.

## Example invocation

User: "every weekday at 8am, run my morning briefing"

Drafted prompt: "Run the morning briefing flow per `knowledge/session-ops.md`: fetch overnight email, today's calendar, today's schedule. Output to `outputs/raw/agent/YYYY-MM-DD-morning-briefing.md`. Send a concise chat summary."

taskName: `morning-briefing`
cronExpression: `0 8 * * 1-5`
fireAt: (omit)

## Output format

The skill ends with a single tool call to `create_scheduled_task` (or `mcp__scheduler__schedule_create` for the daemon scheduler). Fields:
- `taskName` (kebab-case)
- `prompt` (self-contained, second-person)
- `cronExpression` OR `fireAt` (mutually exclusive; omit both for ad-hoc)
- `model` (haiku / sonnet / opus per `knowledge/scheduled-tasks.md` tiering)