---
name: eod-summary
description: End-of-day digest pulling today's wins, decisions, status changes, follow-ups, new artifacts, tomorrow's queue from session.jsonl + tasks + tracker files. User-invoked via /eod or auto-fire at end of day.
trigger: eod, end of day, daily wrap, today summary, /eod
---

# EOD Auto-Summary

Pull today's firehose into one structured digest. Mobile-readable wrap.

## Trigger

- `/eod`: manual, any time. Compiles "today so far" snapshot.
- Auto-fire end of day. NOT WIRED. Manual only.

## Source data

The compiler pulls from these locations for today (`date -d "today" +%Y-%m-%d`):

1. **`logs/session.jsonl`**: events logged (commands, tasks, mode toggles, skills invoked, /save events): filter where ts starts with today's ISO date
2. **Task-list state**: all tasks added/completed/changed today (compare against yesterday's snapshot if available)
3. **Git status of `memory/`**: files modified/created today (memory writes durable across sessions)
4. **`outputs/raw/` and `outputs/reviewed/`**: files created today (work shipped)
5. **A personal follow-up tracker** (e.g. `workspace/personal/tracker.md`): items submitted, status changes, follow-up due dates
6. **`logs/errors.jsonl`**: errors logged today (surfaces unresolved or pending)

## Format

```
🌙 EOD. Friday 2026-04-25

🎯 Shipped today (N):
- ...

📋 Decisions made (N):
- ...

🔄 Status changes (N):
- ...

⚠️ Open follow-ups (N):
- Due today: ...
- Due this week: ...
- Awaiting reply: ...

📝 New durable artifacts (N):
- memory/...: ...
- outputs/...: ...
- skills/...: ...

💤 Tomorrow's queue:
- ...

#meta #eod
```

Sections with zero items are omitted entirely (don't show empty headers).

## Compilation (current: manual, model-driven)

When `/eod` fires, compile by:
1. Filter today's `logs/session.jsonl` events (ts startswith today's ISO date)
2. `git status memory/` → new/modified files since 00:00 local
3. List files in `outputs/raw/` and `outputs/reviewed/` with mtime today
4. Read the personal follow-up tracker for state changes
5. Pull task-list state (added/completed today)
6. Render into the format above
7. Save as `outputs/tg/eod-YYYY-MM-DD.md`, send via the reply channel

**Automation (parked):** an `eod_digest.py` script would do steps 1-7 + auto-fire at end of day. NOT BUILT. Build trigger: after manual /eod proves stable for 5+ days.

## Duration / size

Target: 800-1200 char digest. If the day was huge (a big ship day + two applications + a partner brief + infra patches), the digest can stretch to 1500. Beyond that → attach as .md per progressive-disclosure.

## Cadence

- Any time during the day. Re-runs regenerate fresh from current state.
- Soft-cap one send per day. Mid-day re-runs save to `outputs/tg/` only (no spam).

## Why

50-100 scattered chat messages/day → one mobile-readable artifact. Closes the loop, kills "what did I do today" decay.

## Composition with other skills

- **progressive-disclosure**: if EOD digest >1500 chars, auto-attach as `.md` instead of pasting
- **inline-tags**: EOD always tagged `#meta #eod` for retroactive search
- **/save**: EOD does NOT replace `/save`. /save extracts durable learnings to memory; /eod is a transient daily wrap. Both can run.
- **Stop-hook /save integration** (parked): when the stop-hook runs at session end, /save fires; /eod is separate (could optionally chain at end of day, but not required).

## Scope discipline

- Don't speculate or pad. If a section has nothing, skip it.
- Don't include yesterday's leftovers unless they materially advanced today.
- Open follow-ups: only those genuinely actionable tomorrow. "Awaiting a contact's reply Mon/Tue" = correct. "Maybe think about a side idea sometime" = skip.
- Decisions: include only consequential ones. "Picked B over A on a UI option" = skip. "Chose Path 1 over Path 2 for a boot-survival fix" = include.

## Edge cases

- **Empty day** (no shipped, no decisions, no status changes): single-line digest `🌙 EOD. {date}: quiet day. {N} open follow-ups carry to tomorrow.` Skip all empty sections, no padding.
- **Timezone**: always your local timezone. Use `date -d "today" +%Y-%m-%d` for filtering.
- **Mid-day re-run**: regenerate fresh from current state, do NOT diff against prior /eod output. Each run = snapshot.
- **Partial source data** (e.g. session.jsonl missing): note `⚠️ source: session.jsonl unavailable` in the digest header, continue with what's readable. Don't fail the whole digest.
- **Tomorrow is weekend/OOO**: `💤 Tomorrow's queue` becomes `💤 Mon queue` (next working day): don't pad with weekend filler unless something is genuinely due Sat/Sun.
