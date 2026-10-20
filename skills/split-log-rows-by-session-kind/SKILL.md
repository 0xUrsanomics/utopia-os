---
name: split-log-rows-by-session-kind
description: Check whether a hook or error metric is polluted by child sessions (critic, subagent, cron) by joining logged session ids to their transcripts and splitting on the first user message, with a control before naming a mechanism.
trigger: which sessions produced these rows, is this miss rate polluted, hook metric looks too high, rows from critic or subagent sessions, classify session ids by kind
---

# Split log rows by session kind

Use when a counter built from logged session ids (hook misses, error rows, turn rows) reads higher than the experience of the session it is meant to describe. The usual cause: child sessions (a critic subagent, a cron run) share the log with the interactive session and inflate the numerator or the denominator.

## Steps

1. **Pull the numerator rows for the window** from the log that holds them. For the chat reply-miss counter that is `logs/errors.jsonl`, event `stop_hook_tg_reply_miss_caught` (see `skills/telegram-reply-tool/SKILL.md`). Keep `session_id` and the timestamp.
2. **Find each session's transcript** at `~/.claude/projects/<project-key>/<session_id>.jsonl` (`<project-key>` is the working directory path with `/` replaced by `-`). Rows with no transcript cannot be classified. Report that count next to the result; do not drop them silently. It can be most of the rows.
3. **Read the first `type: user` entry of each transcript and bucket by its opening text.** A prompt starting "You are the Critic" (the prompt `scripts/eval/critic_dispatch_hook.py` sends) is a critic child, your cron prompt preamble is a cron session, anything else is interactive. Print the count per bucket.
4. **Run a control before naming a mechanism.** Take ALL sessions of the suspect kind in the same window, including the ones with no row, and check whether the property you blame (for example a chat-channel marker in the child's first prompt) separates flagged from unflagged. A clean split across every session of that kind is the proof. A count taken only over the flagged rows proves nothing.
5. **Recompute the rate on the interactive bucket alone** and state the denominator basis beside the number. Say whether the denominator includes cron runs.
6. **If a guard is missing, do not edit the hook in the same pass.** Record the fix as a proposal with a structural check (the guard string is present in the hook script), not a symptom-absence check ("no misses this week").

## Worked case: reply misses from critic children

A Stop hook that checks "did the session owe a chat reply" can fire inside critic children, because the critic's prompt quotes the draft, and the draft quotes the chat message. Each such child logs a false miss.

1. Pull the miss rows for the window and keep the first 8 characters of each `session_id`.
2. List critic children: transcripts whose mtime falls in the window and whose FIRST user message starts with `You are the Critic`. Large transcripts (several MB) are interactive sessions; skip them.
3. For each child, test its first prompt for a chat marker, case-insensitive: `telegram`, `chat_id`, `<channel`, the reply tool's name.
4. Cross-tab marker against miss row. The control passes when every child with a marker has a miss row and every child without one has none.
5. Any miss `session_id` that is NOT a critic child is an interactive miss. Report it on its own line: it is the only kind that needs action.
6. After a guard ships in the hook (skip the check when the first prompt is a critic prompt), the same procedure is the post-fix test: expect 0 miss rows for children.

```python
import json, re
first = next(json.loads(l) for l in open(f) if '"type":"user"' in l.replace(' ', ''))
text = first['message']['content']
text = text if isinstance(text, str) else ' '.join(x.get('text', '') for x in text)
is_critic = text.startswith('You are the Critic')
has_chat_marker = bool(re.search(r'telegram|chat_id|<channel', text, re.I))
```

## Caveats

- Transcripts past the retention window, or from another machine, are gone, so older rows stay unclassified.
- The first-user-message prefix is a heuristic. Spot-check one session per bucket by hand.
- Transcript mtime is the last write, not the start. Widen the window by the child's runtime (a few minutes).
- Log timestamps may mix UTC and local time. Convert before comparing.

## Output

A small table (bucket, miss rows, turn rows, rate), then the control result and the count of rows that could not be classified. A term like "reply-miss rate" that has been read two ways belongs in the glossary with its basis (`knowledge/glossary.example.md`).
