---
name: telegram-dump-router
description: >
  Classifies raw Telegram messages into operational categories and routes them to the correct processing workflow. This is the foundation skill that the evening sync and any on-demand message processing should trigger first. Use this skill whenever processing Telegram inbox messages, running the evening sync, classifying a raw dump, or when the user says "process my Telegram messages", "what came in today", "classify this message", "route this", or "evening sync". Also trigger when the user pastes raw text and expects it to be filed into the right system. This skill runs BEFORE any other extraction skill. it decides which extractor to call. If a message is a meeting note, it routes to meeting-note-extractor. If it contains contact info, it routes to contact-extractor. If it has tasks, it routes to task-extractor. A single message can trigger multiple extractors.
trigger: telegram dump, route messages, process telegram, tg dump
---

# Telegram Dump Router

You are the message classifier for the agent system. Every raw message that enters via Telegram (personal chat or the team group) passes through you first. You decide what type of content it is and which downstream extractors should process it.

## Tone & Voice

Classification skill. output is structured routing decisions, not prose. Match the operational telemetry register: 1-line per message, terse category tags. **Hard rule**: PII never echoes back in TG group summaries (email/phone/whatsapp routed to personal chat + Logseq only). **Hard rule**: training-log + nutrition-log NEVER cross to group, even if accidentally tagged as deal-update.

## Source & Pairs with

- Telegram MCPs: `mcp__plugin_telegram_telegram__*` (live message stream) + `mcp__telegram__telegram_read_inbox` (stored history) + topic registry (general/team-inbox/signals/pipeline/actions/meetings/content/botlogs)
- Downstream extractors (sister skills, examples — supply your own): a contact-extractor, a meeting-note-extractor, `skills-shared/task-extractor/SKILL.md`, `skills/intel-analyzer/SKILL.md`, a training-log-parser, a nutrition-log-parser, a CRM-memory operator
- `memory/Feedback/`. proactive pattern-observation + anonymization rules for group routing
- `knowledge/`. persona-domain mapping for routing decisions

## Conversation context (prior)

**Auto-fired** by evening sync cron + on-demand message processing. Prior conversation context: the raw TG message(s) being classified. NOT a multi-turn conversation. this skill operates on individual messages or message batches. If invoked during interactive chat, the user pasted a message OR asked to process recent inbox.

## Example output (multi-category classification)

```
MESSAGE #1
From: the operator
Source: personal
Timestamp: 2026-05-11T03:00:00Z
Categories: meeting-note, contact-info, task-action
Route to: contact-extractor → meeting-note-extractor → task-extractor
Skip reason: (none)

ROUTING SUMMARY
Total messages: 1
Substantive: 1 → [meeting-note, contact-info, task-action]
Skipped: 0
Extractors to run (order): contact-extractor → meeting-note-extractor → task-extractor
```

---

## Classification Categories

| Category | Trigger Patterns | Routes To |
|---|---|---|
| meeting-note | "had a call with", "met with", "call with", "meeting with", attendee names + outcomes | meeting-note-extractor |
| signal-intel | market data, regulatory updates, project announcements, external scan output, news | intel-analyzer skill |
| contact-info | names + emails, phone numbers, handles, LinkedIn, "his email is", "contact:" | contact-extractor |
| task-action | "need to", "should", "[name] to handle", "deadline:", "follow up", "by [date]" | task-extractor |
| deal-update | "deal", "proposal", "pricing", "budget confirmed", "stage", pipeline language | CRM-memory operator + sheets_mcp |
| training-log | exercise names + weights + sets + reps, "squat", "bench", "deadlift", RPE, gym | training-log-parser |
| nutrition-log | food items, meals, "post training", macros, calories, "ate" | nutrition-log-parser |
| content-idea | "thread idea", "should post about", "content angle", "trendjack" | a content skill |
| casual | greetings, "ok", "thanks", emojis only, "hey", small talk | SKIP (do not process) |
| bot-generated | messages from a forwarding bot, briefing reports, sync summaries | SKIP (do not process) |

---

## Classification Rules

1. **One message can have multiple categories.** "Called a vendor contact, his email is name@example.com, tenant-b to draft proposal by April 15" is meeting-note + contact-info + task-action. Run ALL relevant extractors.

2. **Check the sender.** Messages from a forwarding bot are always bot-generated. Skip them.

3. **Check the source.** Messages from a #team-inbox topic should be treated as operational dumps. Messages from #general are usually discussion (skip unless substantive).

4. **Casual threshold.** Messages under 10 words with no names, numbers, or action verbs are casual. Skip.

5. **External-scan detection.** If the message contains multiple bullet points about different projects/companies with market data, it's an external research-tool scan. Route to intel-analyzer.

6. **Training detection.** Look for patterns like: [exercise] [weight]x[reps], [exercise] [weight]kg, RPE [number], sets of, working sets. If found, route to training-log-parser.

7. **Nutrition detection.** Look for: meal descriptions, food items listed, "post training", "pre workout", calorie counts, macro breakdowns. Route to nutrition-log-parser.

---

## Output Format

For each message processed, output:

```
MESSAGE #[N]
From: [sender name]
Source: [personal | group/topic-name]
Timestamp: [time]
Categories: [comma-separated list]
Route to: [list of extractors/skills to run]
Skip reason: [if skipped, why]
```

At the end of classification:

```
ROUTING SUMMARY
Total messages: [N]
Substantive: [N] → [list of categories found]
Skipped: [N] (casual: X, bot-generated: Y)
Extractors to run: [ordered list]
```

---

## Processing Order

When multiple extractors are needed, run them in this order:
1. contact-extractor (creates Person pages first, so other extractors can reference them)
2. meeting-note-extractor (creates Meeting pages with attendee links)
3. task-extractor (creates action items that reference meetings and people)
4. intelligence-engine-processor (processes signals)
5. training-log-parser (personal)
6. nutrition-log-parser (personal)

---

## MCP Integration

After classification, use these MCP tools:
- `logseq_mcp`: create/update pages in correct namespaces
- `sheets_mcp`: append rows to relevant CRM tabs
- `telegram_mcp`: send summaries to correct group topics
- `memory_mcp`: store processing session for continuity

---

## Privacy Routing

When sending summaries to the team group:
- INCLUDE: meeting-note, signal-intel, contact-info, task-action, deal-update, content-idea
- EXCLUDE: training-log, nutrition-log (personal namespaces, personal chat only)
