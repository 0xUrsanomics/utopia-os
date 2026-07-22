# Session Bootstrap

> **Template.** Copy to `memory/session-bootstrap.md`. This is the SURVIVAL layer: the parachute a
> fresh session opens instead of replaying a full transcript after a crash, restart, or context
> compaction. Long-running agents suffer *behavioral state decay*: the decision-relevant facts scroll
> out of context and stop influencing the next action. This file fights that by holding the mid-task
> state explicitly, in a fixed place, so a resume is clean instead of amnesiac.
>
> Read the whole file on a fresh-start spawn (watchdog restart, `/restart fresh`). On a normal
> `--continue` resume, the transcript reloads automatically but THIS file does not, so at minimum pull
> the `## Active Handoff` block explicitly or an in-flight task silently drops on the floor.

**Read order on session start:**
1. `CLAUDE.md` (always loaded by the runtime)
2. `memory/MEMORY.md` (the index)
3. **this file** (read explicitly per the `CLAUDE.md` instruction)
4. the active persona's memory file

Maintained by: a periodic compaction job (e.g. cron every ~30min) that appends a compaction block,
and by the `/save` skill on demand.

---

## Current Task State
<!-- ONE paragraph: what the operator and agent are mid-way through, right now. Overwritten on each
     compaction. Not a log, a snapshot: if someone read only this paragraph, would they know what's
     in flight? Keep it to a paragraph. Detail belongs in Active Handoff below. -->

`<single-paragraph description of the current in-flight work, or "No single thread mid-task right
now." if the session is between tasks>`

## Active Handoff
<!-- The load-bearing block. Populate when a task will OUTLAST a single turn. Clear it when the task
     is done. This is what a post-compaction resume reads to pick the task back up without re-deriving
     it. Write triggers are listed at the bottom of this file.

     Each open item should answer: what is the state, what is the RESUME action, and what is the
     hard gate (if any). Below is a filled GENERIC example showing the shape. Replace it. -->

**GATED <YYYY-MM-DD HH:MM TZ>: <short title of the in-flight task>.** `<one or two sentences of what
was greenlit and the current phase>`. RESUME: `<the exact next action when the blocker clears>`. HARD
GATE: `<what must happen before proceeding, e.g. operator reviews the diff. no ship until then>`.
Full plan in `<pointer to the project dossier that holds the detail>`.

**DONE this session (<date>):** `<a running list of what already shipped this session, so a resume
doesn't redo it. reversible items note "awaits no action unless vetoed">`.

**Open, unfixed, low priority (carried forward):**
- `<a known issue left as-found for diagnosis, with why it wasn't fixed this pass>`

## Open Threads
<!-- Bullet list of pending items awaiting the operator's reply or a next action. Max ~10 items,
     oldest pruned. These are things blocked on someone else, not things the agent is mid-doing
     (those go in Active Handoff). Refresh on each consolidation pass and prune dead entries. -->

- `<pending item awaiting external/operator response, dated, with "no action needed unless X">`
- `<a strategy fork surfaced to the operator, awaiting their pick>`

## Context Flags
<!-- Transient state that would normally live only in conversation memory. Point to the state files
     rather than caching values here, so this never drifts from the source of truth. -->

- Active persona: (read `memory/state/active_persona.txt`)
- Temp / incognito mode: (read `memory/state/temp_mode.txt`)
- `<other transient mode flag>`: (read `memory/state/<flag>.txt`)
- Last compaction: `<timestamp or "never">`

## Boot tasks
<!-- Run on a fresh-start spawn. Each MUST be idempotent (a no-op if already applied), because a
     fresh start may or may not be a truly clean environment. Keep this list short. -->

- `<idempotent boot command, e.g. reapply a runtime patch that a runtime upgrade may have reverted>`
  Context: `<pointer to the note explaining why this boot task exists>`

---

## Recent Compaction Blocks

<!--
Dated summary blocks, newest first. Max ~5 blocks kept, oldest dropped. Each block is a compressed
view of one "era" between restarts or /save events, so history survives compaction without replaying
the transcript. Format:

  ### YYYY-MM-DD HH:MM TZ. <short title>
  - what happened
  - decisions made
  - open follow-ups

Leave the space below empty in the template; the compaction job fills it.
-->




---

## Write triggers (when to populate / clear this file)

> The parachute only works if it's packed before the fall. These are the moments to write.

**Write / update the Active Handoff when:**
- a task will take more than a few minutes or span multiple turns,
- a background process (a long bash run, an indexing job, a sub-agent) is running,
- the session is getting large (approaching a compaction), or
- the operator pauses mid-task and the thread would otherwise be lost.

**Clear the Active Handoff when:** the task ships, is abandoned, or is fully handed to the operator.
A stale handoff is worse than an empty one, it resumes work that no longer exists.

**Overwrite Current Task State** on every compaction pass. **Prune Open Threads** on every
consolidation pass (drop the dead, keep the newest ~10). **Never cache live deal/project/domain state
here**, point to the Tier-2 dossier that owns it, or the snapshot will outlive its shelf life.
