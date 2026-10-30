---
name: open-loops
description: Find email threads where someone is waiting on you (24h+) or you are waiting on someone (72h+). Read-only, deterministic rules, zero LLM judging.
trigger: open loops, who is waiting on me, unanswered emails, who owes me a reply, email follow-ups, waiting on reply
allowed-tools: Bash, Read
---

# Open loops

Pattern from gbrain `docs/guides/open-loops.md`. Run it inside a morning briefing, or on demand. Read-only: it never drafts, sends or labels anything.

## Fetch (in-session, through your mail MCP's search and get tools)
1. Search with `newer_than:14d (in:inbox OR in:sent) -category:promotions -category:social -category:updates -category:forums`, max 100 results. Results come newest first.
2. Keep the FIRST message id per threadId (that is the thread's latest message). Cap at 30 threads.
3. Get each kept id as metadata (headers + snippet), in one parallel batch.
4. For any thread whose latest message is yours, also fetch the previous message id from step 1, so a nudge does not reset the clock.
5. Write `{"me": ["you@example.com"], "messages": [...metadata objects...]}` to a scratch file. Or set `OPERATOR_EMAILS` and leave `me` out.

## Judge
`python3 -I scripts/memory/open_loops.py <input.json>` (add `--json` for machine output).
- Exit 2 with `OPEN_LOOPS_EMPTY_INPUT` means the fetch returned nothing. That is a FAIL, never "no open loops". Re-fetch.
- Self-check: `python3 -I scripts/memory/open_loops.py --selftest` (14 cases).

## Rules (all in the script)
- Waiting on you: last real message is theirs, you are in To:, it asks or requests something, 24h+ old.
- You waiting: last real message is yours, it has a "?" outside any URL, 72h+ old.
- Acks ("thanks", "got it", "noted") never close a loop. Same-side nudges keep the original clock.
- Ignored: automated senders, calendar invites, promo/social/update/forum categories, threads older than 14 days, and senders in `memory/state/open-loops-ignore.json` (`{"senders": ["domain.example"]}`).
- Writing in another language? Add its ack and request phrases to `ACK` and `REQUEST` in the script.

## What a result does NOT prove
It is judged on the ~200-char snippet, so a request deep in a long mail can be missed. Only the 30 most recent threads are checked. Follow-ups that moved to a chat app are invisible: a thread that moved there can show as open.

## Report
List "waiting on you" first, oldest first, max 5 lines, then "you're waiting on them". When you dismiss a sender as never-a-loop, add the domain to the ignore file (safe to do without asking: it only narrows output).
