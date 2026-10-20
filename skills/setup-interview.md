---
name: setup-interview
description: Onboarding interview that fills a new operator's memory files by asking, not by handing them blank templates. Run when setting Utopia OS up for someone: it interviews the operator, then writes USER.md, SOUL.md, the CLAUDE.md operating rules, and the MEMORY.md seed from their answers.
trigger: /setup-interview, onboard me, set up utopia os, run the setup interview, fill my templates, new operator onboarding
---

# setup-interview

`SETUP.md` copies the templates and tells the operator to fill `SOUL.md` and `USER.md` themselves. Almost nobody does, and a blank `SOUL.md` means the agent has no voice and a blank `USER.md` means it has no model of who it serves. This skill closes that gap: you INTERVIEW the operator and write the files from their answers, the same way a good assistant learns a new boss by asking, not by mailing them a form.

You are the agent that a person just asked to set up Utopia OS. Run this once, early, before the operator relies on the system for anything real.

## Rules that do not bend

- **Ask, do not assume.** Every value below comes from the operator's own words. If they skip a question, leave the template's placeholder and say which file is still thin, do not invent a plausible answer. A fabricated `USER.md` is worse than an empty one, because it reads as known.
- **One file at a time, confirm before overwrite.** If `memory/USER.md` (etc.) already exists with real content, show what you would change and get a yes first. Never clobber a filled file with interview output.
- **Never write a secret into a memory file.** Tokens, chat IDs, and keys go in `.env` (gitignored) per `docs/bot-setup.md`, never in `USER.md`/`MEMORY.md`/`CLAUDE.md`.
- **Voice is copied from the operator, not imposed.** Lift their actual phrasing, register, and language mix into `SOUL.md`. If they write to you in mixed English and another language, that mix IS the voice. Do not standardize it to neutral English.

## The interview

Ask these in blocks, conversationally, not as a numbered form dump. Follow up where an answer is thin. Aim for enough to write a dense file, not an exhaustive intake.

### Block 1: IDENTITY (fills `USER.md`)
- Name or handle, and any pseudonym they operate under publicly.
- Location and timezone (the agent needs this for every scheduled thing).
- Primary venture / role, and what they actually spend their days doing.
- Languages, with honest proficiency (an overclaim here causes real downstream harm).
- The one or two formative pivots in their path (not a resume, the shape).
- Current state: what they are heads-down on right now, what is stressing them, what "a good week" looks like.
- Temperament + triggers: what earns their trust, what makes them disengage, how blunt they want you.

### Block 2: VOICE (fills `SOUL.md`)
- What is this agent TO them: a peer with taste, a tool, a presence? Name the relationship (peer vs servant), everything downstream inherits it.
- How should it talk: sentence length, formality, emoji, swearing, humor.
- Language: English only, or a code-switch mix? Capture the exact mix and any recurring words.
- What should it NEVER sound like (the anti-patterns that make them cringe).
- Give it a name.

### Block 3: AUTONOMY (fills the `CLAUDE.md` operating rules + Autonomy Modes table)
- Default posture: mostly act-then-tell (AUTO/INFORM), or mostly ask-first (CONFIRM)?
- The CONFIRM list: what must it ALWAYS ask before doing (spend money, send anything outbound, touch a specific system, publish)?
- The hard-blocked list: what must it NEVER do, even when told to in the moment (e.g. send email directly, force-push, anything irreversible-and-external).
- Their "just do it" override words, if any (so a green light is unambiguous).

### Block 4: DOMAINS + SURFACES
- The lanes it works in (their projects, the recurring kinds of work).
- The Telegram/Discord surfaces they want (see `docs/bot-setup.md` and the topic-group flow there): at minimum an **Ops** surface (live chat) and a **Cron Reports** surface (scheduled output). Ask if they want more topics (signals, briefings, pipeline).

### Block 5: SECURITY POSTURE (fills the `CLAUDE.md` security section)
- Confirm the fleet floor holds (email is draft-only, no `curl | bash`, 7-day-age + stand-down before installing anything). These are defaults, not up for negotiation; you are confirming they understand them, not asking permission to weaken them.
- Any extra hard rules specific to their work (a regulated domain, a client-confidentiality line, a service they must never touch).

### Block 6: SEED (fills `MEMORY.md` + a first `Context/` note)
- Any existing facts, decisions, or context worth seeding so the agent does not start blind. A few key project facts, active goals, people it should know.

## Writing the files

After the interview, write each file from its template, deleting the `<fill in>` placeholders and the guidance quote-blocks:

| From answers in | Write |
|---|---|
| Block 1 | `memory/USER.md` (from `USER.template.md`) |
| Block 2 | `memory/SOUL.md` (from `SOUL.template.md`) |
| Block 3 + 5 | the operating-rules + Autonomy + Security sections of `CLAUDE.md` (Claude Code) or `AGENTS.md` (other harnesses) |
| Block 4 | the surface wiring in `.env` + the routing note; topics per `docs/bot-setup.md` |
| Block 6 | `memory/MEMORY.md` seed + one `memory/Context/<slug>.md` |

Keep Tier-1 files (`USER.md`, `SOUL.md`, `Preferences.md`) DENSE, not exhaustive: they are paid for on every reply.

## Close

Tell the operator, in plain language:
- which files you wrote and which are still thin (any block they skipped),
- what still needs THEM: secrets in `.env`, the bot/group creation steps in `docs/bot-setup.md` that only they can do (create the group, enable Topics, add the bot as admin), and
- one line on how to change any of it later (edit the file, or re-run this skill).

Then hand off. The system is theirs now.
