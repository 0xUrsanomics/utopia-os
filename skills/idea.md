---
name: idea
description: Capture ad-hoc thought into the active project's Inbox section. Falls back to side-quests if no active project. Lightweight quick-drop primitive. no friction, no clarifying questions.
trigger: /idea, /idea <text>
---

# /idea. Quick capture into project inbox

Drop ideas, half-formed thoughts, junk, or maybe-junk into a project-scoped inbox without context-switching the current task.

## Tone & Voice

Zero-friction primitive. **NEVER** ask clarifying questions on a valid /idea call. that defeats the entire point. The whole reason this skill exists is to short-circuit context-switching. If the body is empty, ONE single-line prompt ("what's the idea?") is OK; otherwise capture verbatim and acknowledge with one line max.

## Conversation context (prior)

**Prior conversation: N/A**. /idea is a one-shot command. The body after `/idea` IS the entire input. Don't pull context from prior turns to interpret or reframe the idea. capture it as-is.

## Routing rule

1. Read `memory/state/active_project.txt`.
2. If non-empty AND `memory/projects/<active>.md` exists → route there.
3. Else → route to `memory/projects/side-quests.md` (default incubator per spec).

## Procedure

1. **Parse text**: everything after `/idea` is the idea body. Trim whitespace. If empty, ask: "what's the idea?" (one line, don't ramble).
2. **Determine target file** via routing rule above.
3. **Read target file**, locate `## Inbox` heading section.
4. **Append entry** in this format:
   ```
   - {YYYY-MM-DD HH:MM}. {idea text}
   ```
   - Use your local timezone for the timestamp.
   - If section currently has the placeholder `(empty. awaiting...)` text → REPLACE it with the new entry as the first list item.
   - Otherwise → append as a new bullet at the bottom of the Inbox section (before the next `##` heading).
5. **Update `last_updated`** in target file's frontmatter to today's date.
6. **Confirm**: one short line, format:
   - `📂 idea → {project-name}: "{first 50 chars of idea}{... if longer}"`
   - If empty active project → `📂 idea → side-quests (no active project): "..."`
7. **Skip semantic reindex**: inbox entries get picked up on the next nightly reindex. Don't burn time for a one-line capture.

## Edge cases

- **Multi-line idea** (idea text contains newlines): collapse to single line with `;` separator. Chat messages mostly come single-line anyway, but the heuristic handles paste-edge-cases.
- **Active project file missing**: log warning, fall back to side-quests.md.
- **Inbox section missing in target file**: warn ("project file structure broken. falling back to side-quests"), append to side-quests instead. Don't try to repair the broken file mid-flow.
- **Idea references a specific project via @-mention** (e.g. `/idea @project-alpha someconcept`): override active-project routing, target the @-mentioned project. Validate the project exists; else error.

## Graduation hook

When an idea entry triggers a longer thread (the operator explicitly references it later, or it accumulates >3 sub-bullets via subsequent /idea or in-context expansion), surface the question: "this looks substantive. graduate to its own project file? (`memory/projects/<slug>.md`)". See `skills/project.md` § Graduation criteria for the 4-condition test.

## What this is NOT

- Not a TODO list. there's a task tracker for that. Ideas are unscoped musings; tasks are scoped commitments.
- Not a journal. that's the natural session log. /idea is for "noise that might be signal" only.
- Not a memory-write. doesn't touch Preferences/Decisions/Learnings. Pure inbox capture.

## Example flow

```
> /idea what if we wrap the daily digest cycle output as a chat notification
📂 idea → project-alpha: "what if we wrap the daily digest cycle output as a..."

> /project clear
> /idea note-taking template for the weekly review
📂 idea → side-quests (no active project): "note-taking template for the weekly..."

> /idea @project-beta reduce scope on phase 3-4
📂 idea → project-beta: "reduce scope on phase 3-4"
```

## Pairs with

Pairs with `skills/project.md` (the project context switcher) — same filesystem-projects layer.
