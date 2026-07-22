---
name: inline-tags
description: Append 1-3 hashtag tags to the end of every TG reply for native TG search. Domain + project + status taxonomy. Replaces full TG-Topics migration without rebuild cost.
trigger: tag this, tag reply, hashtag, #deal, #infra
---

# Inline Tags for TG Search

Every TG reply ends with 1-3 hashtags so TG's native full-text search becomes effective topic-replacement. No migration cost.

## Source & Pairs with

- `memory/Context/`. project/deal canonical names (for #deal tag accuracy)
- `memory/Context/`. event slugs (for #event tag)
- `memory/Infra/routing.json`. domain keywords map to tag categories
- Sister skill: `skills/progressive-disclosure/SKILL.md` (long replies → file attach; inline tags STILL apply on the chat summary)

## Conversation context (prior)

**Prior conversation**: applies AUTOMATICALLY to every TG reply. No invocation needed. The skill reads the reply content + recent conversation context to pick relevant tags from the taxonomy below. If the tag should be entity-specific (e.g. a specific project), confirm the entity from prior turns before tagging.

## Taxonomy

### Domain tags (always include 1)

| Tag | When |
|---|---|
| `#deal` | a client, an exchange, a token project, BD outreach, partnership negotiation |
| `#infra` | daemon, MCP servers, WSL, scheduler, watchdog, VPN, scripts |
| `#personal` | groceries, gym, coach, family, health, a side business |
| `#job` | personal job applications, career exploration, salary nego |
| `#content` | content drafts, threads, content-producer outputs, positioning docs |
| `#research` | research digests, library audits, market research, regulatory reads |
| `#review` | /review queue work, approve/flag/discard decisions |
| `#signal` | Signal/ entries, market intel, news triage |
| `#meta` | skills, persona system, session ops, /save /compact /restart |

### Project tags (include if relevant)

Use short slugs for your own recurring projects / counterparties, e.g.
`#project-a` `#project-b` `#vendor-a` `#vendor-b` `#initiative-x`

Persona / system: `#agent` `#coach` `#tenant-a`

### Status tags (include if state changes)

`#submitted` `#shipped` `#waiting` `#ghosted` `#parked` `#blocked` `#resolved` `#approved` `#flagged` `#discarded`

### Type tags (rare, include for clarity)

`#decision` `#learning` `#brief` `#brainstorm` `#scope` `#audit` `#alert` `#confirm-gate`

## Rules

1. **Always include 1 domain tag**: every reply lands in at least one bucket
2. **0-2 additional tags**: project tag if specific company/initiative, status tag if it's a state change, type tag for clarity
3. **Tag line goes at the END**: separated from body by a blank line. Format: ` ` (space) then tags space-separated:
   ```
   ...message body ends here.
   
   #deal #project-a #submitted
   ```
4. **Stay under 4 tags per reply**: over-tagging defeats search. Pick the most relevant 1-3.
5. **Skip tags only when**: 
   - Reply is a single-line acknowledgment ("👌 noted")
   - User explicitly asks "no tags"
   - In /driving mode (TTS doesn't need them; tags get stripped pre-render)

## Search workflow (the operator's side)

In TG search bar:
- `#project-a` → all threads about that project from history
- `#deal #waiting` → all deals currently awaiting external response
- `#infra #shipped` → recently completed infra work
- `#initiative-x` → that initiative's trail
- `#job #ghosted` → applications gone silent

This replaces TG Topics migration (~6hr cost) with hashtag taxonomy (~0 ongoing cost). Loses: per-topic mute, threaded scrolling. Gains: zero migration, search-precision parity, full-history retroactive.

## Example applications

**Single-domain reply:**
> Application submitted. Confirmation ticket logged in tracker.
> 
> #job #vendor-a #submitted

**Multi-domain reply (deal + infra):**
> The counterparty's framing accepted. Pattern library shipped at outputs/drafts/...md.
> 
> #deal #initiative-x #shipped

**Decision-class reply:**
> My pick is 🅱 (option B over option A). Reason: the account discrepancy.
> 
> #infra #wsl #decision

**Personal class:**
> Grocery inventory updated. Restock soon.
> 
> #personal

## Edge cases

- **Channel-source forwards** (digest bots, alerts, daemon ping): they tag themselves; my reply just routes the response. Tag mine normally.
- **Multi-message threads** (when I send 2 TG messages in one turn): tag each message independently. each is a search target on its own.
- **File attachments**: tags go in the text caption, not the attached file's content.
- **Tags collide with markdown syntax**: TG renders `#tag` as plaintext, NOT as a link unless preceded by space. Always have space + tag (or newline + tag).

## Why this works in TG

TG's search engine indexes hashtags natively. `#project-a` typed in search bar surfaces every message with that hashtag chronologically. No special UI needed. Works on mobile + desktop. Works retroactively from when tagging starts (no historical tags = no historical hits, but going forward it's a clean filter).
