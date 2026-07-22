---
name: progressive-disclosure
description: When a chat reply exceeds the wall-of-text threshold, attach as a .md file with a 3-line summary in chat instead. Reduces mobile reading friction + token tax on future sessions reloading the transcript.
trigger: long reply, attach instead, condense reply, file disclosure
---

# Progressive Disclosure for Long Chat Replies

Attach long replies as files; show only the summary in chat.

## Tone & Voice

Operational convention. applies AUTOMATICALLY without a user prompt. The chat summary should be terse, 3 lines max, with an explicit "full content in attached file" pointer. **Hard rule**: when triggered, do NOT ask "should I attach?". just attach. Asking defeats the friction-reduction purpose.

## Procedure (thinking step by step)

1. Compose the full reply mentally.
2. Count chars (excluding markdown table chars). If >1500 → trigger. Count table rows. If 8+ → trigger.
3. Save full content to `outputs/tg/reply-<ISO>-<slug>.md` (auto-generated path).
4. Generate a 3-line summary: (a) topline result, (b) key tradeoff or finding, (c) "see attached for full details".
5. Reply via the chat reply tool with the summary text + `files: ["<path>"]` attached.

## Rule (apply automatically, no user invocation needed)

**Trigger any of:**
- Reply text exceeds **1,500 characters** (excluding markdown table chars)
- Markdown table has **8+ data rows**
- Code block exceeds **30 lines**
- Total markdown structure has **5+ headed sections**

**When triggered:**
1. Write the full reply content to `outputs/tg/reply-YYYY-MM-DDTHH-MM-SSZ-{slug}.md` with frontmatter (date, type=chat-reply, related-thread-context)
2. Send via the reply tool with:
   - `text` = 3-line summary describing what's in the file + the headline takeaway
   - `files` = `[<absolute path to the .md>]` so it attaches as a doc
3. The summary text MUST include: (a) what the file contains, (b) the 1-line headline / decision / rec, (c) any explicit ask of the user

**When NOT to trigger:**
- Tables under 8 rows or under 1,500 char total
- User explicitly says "give me the full thing inline" / "paste it here"
- Code snippets with under 30 lines
- Quick lookups, status updates, single-decision answers
- Replies that are inherently a wall (e.g. JSON dumps for verification): those go in the file regardless of length

## Why this rule exists

Long replies in a mobile chat are friction:
- Mobile-readable only by scrolling endlessly
- Chat message format hides nested structure (markdown tables get cramped)
- Every long reply re-renders into the conversation transcript = future-session token cost
- File attachments are first-class on mobile (open in a markdown viewer or files app)

Saving the wall as a .md attachment is **archival-ready** (you can drop it in `outputs/reviewed/` if it's worth keeping) and **mobile-friendly** (one tap to open, native scroll, formatting preserved).

## Example application

User asks for a "component pattern library scan". The reply would be 800+ lines, 4 sections, tables.

❌ Old behavior: paste the entire library in the chat message, mobile reading nightmare.
✅ New behavior:
1. Save the library to `outputs/drafts/component-pattern-library-2026-04-24.md`
2. Reply: "📎 Component pattern library shipped. `component-pattern-library-2026-04-24.md` attached. 10 patterns / 4 domains, 47% low-complexity can deploy within 90 days. Quick-match index at the bottom."
3. files = ["/abs/path/component-pattern-library-2026-04-24.md"]

## Source-of-truth

This rule supersedes the implicit "should I attach or paste" judgment call. Apply consistently. If unsure, attach. bias toward file delivery for anything that isn't trivially short.

## Edge cases

- **CONFIRM-gate /scope responses**: those are short by design (restate + assumptions + NOT-doing + ask). Stay in chat.
- **Multi-step plans**: if the plan needs your pick from N options, paste in chat (you need to see options + reply quickly). Save the EXPANDED rationale to a file if it would push the chat reply over 1,500 chars.
- **File contents you asked to read**: if you paste a doc and ask for a review, reply summary in chat + attach annotated diff or review notes as .md.
- **Cover letter / resume / proposal drafts**: ALWAYS attach as a file. these get edited iteratively, file is the canonical artifact.

## Implementation notes (for the default persona)

- `outputs/tg/` directory exists; create if missing on first use
- File naming: ISO timestamp + 3-5 word kebab-case slug (e.g. `reply-2026-04-25T10-15-00Z-audit-summary.md`)
- Summary line format: `📎 {filename}.md. {1-line takeaway}.` (3 lines max if context calls for more)
