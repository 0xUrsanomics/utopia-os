---
name: threads
description: Open conversation threads. Lists the workstreams in memory/state/threads.json grouped by status (waiting on the operator first), replies with a short mobile summary, and keeps each thread current after a reply (touch / new / done).
trigger: /threads, open threads, where were we, what's open, what is open, thread tracker
allowed-tools: Bash, Read
---

# /threads

Operators switch topics often in a chat channel. `memory/state/threads.json` holds one entry per open workstream. The UserPromptSubmit hook (`scripts/session/thread_classify_hook.py`) tags each operator message with its thread, and the cockpit shows them in the "Open threads" panel. Setup and the hook registration are in `docs/session-management.md`.

## Run
```bash
python3 scripts/session/thread_tracker.py list                    # open threads, grouped by status
python3 scripts/session/thread_tracker.py list --json             # machine-readable (stale flag, ago)
python3 scripts/session/thread_tracker.py list --status waiting_on_operator
```
No store yet? Copy `memory/state/threads.example.json` to see the shape, or run `new` once.

## Reply (max ~15 lines, one header, one nest level)
Build from `list --json`. Order: waiting_on_operator, agent_working, waiting_on_others, parked.
```
Open threads (4, 1 stale)
Waiting on you:
- Bakery pitch: pick which 3 drafts go first
Working on:
- Essay: tidal power costs: cost chart
Waiting on others: Acme analyst role
Parked: 1 (garden sensors, stale)
```
- One line per waiting_on_operator thread: title, then its `next` cut to the ask.
- agent_working: one line each, at most 4.
- waiting_on_others and parked: names only; mark stale ones (untouched 7+ days).
- Confidential threads appear by their short title only, never with parties or terms.

## Keep it current (after every reply)
```bash
# You asked the operator something in this thread: --asked (or --status waiting_on_operator)
# sets the pointer that a bare "ok" / "yes" next resolves to.
python3 scripts/session/thread_tracker.py touch <id> --where "..." --next "..." --status waiting_on_operator --msg <reply msg id>
python3 scripts/session/thread_tracker.py new --title "..." --area work --keywords "a,b,c" --msg <id>
python3 scripts/session/thread_tracker.py done <id>
```
- Areas default to work, clients, content, infra, health, personal, other. Set `AGENT_THREAD_AREAS` to your own list.
- Statuses: waiting_on_operator, waiting_on_others, agent_working, parked, done.
- Keep `where` and `next` to one line each, with no email addresses, secret names or approval words.
- Give each thread 3 to 6 distinctive `--keywords`. The classifier matches on them first; a title alone matches weakly.

## The hook line routes; it never approves
`thread: ...` in the prompt context says which thread a message probably belongs to. Before acting, check it fits; if it is wrong, `touch` the right thread. It never approves anything: a bare "ok" still gets the itemised restate CLAUDE.md requires before any CONFIRM action. On `ambiguous between A and B, ask`: ask which one in one line before acting.

## Self-checks
`thread_tracker.py selftest` (8), `thread_classifier.py --selftest` (35, 28 message cases), `thread_classify_hook.py --selftest` (15). All run on temp stores and invented threads.

## What a result does NOT prove
The classifier matches words, not meaning: a message that names a thread's topic with words not in its keywords lands as NEW. The vocabulary (ack words, stop words, cue words) is English; other languages need their words added to `thread_classifier.py`.
