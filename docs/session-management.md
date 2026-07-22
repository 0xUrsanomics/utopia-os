# Session Management — surviving the context window

A long-running agent has a problem a chatbot doesn't: it must outlive its own context window. Every reply
reloads the whole transcript, so a session gets more expensive the longer it runs — and worse, when the
runtime compacts or the process restarts, the decision-relevant facts can scroll out of the live window and
**stop influencing the next action.** The agent doesn't announce this. It just quietly forgets the task it
was in the middle of.

Call it **behavioral state decay**: the facts that should drive the next step are technically "in history"
but no longer in the part of context that shapes behavior. Two mechanisms fight it — a parachute for restarts
and a handoff block for mid-task compactions — on top of ordinary size self-regulation.

## Behavioral state decay

The live context is a sliding, lossy window. Three events push in-flight state out of it:

- **Auto-compaction** — the runtime summarizes older turns to reclaim room. Summaries are lossy; the
  specific mid-task detail ("the background job writes to *this* path, and I still need to verify *that*
  file") is exactly the kind of thing a summary drops.
- **Restart** — the process dies and respawns. Whatever wasn't written down is gone.
- **Sheer length** — even without compaction, the relevant fact is now thousands of tokens back and competes
  with everything after it for the model's attention.

The defense is the same in all three cases: **the state that must survive is written to a file, not trusted
to the transcript.**

## The session-bootstrap parachute

On a *fresh* start — a crash respawn or a deliberate clean restart — there is no transcript to resume from.
Naively you'd replay the whole prior session to rebuild continuity, which is slow and expensive. The
parachute replaces that: a single compact file (`memory/bootstrap.md`) read as one of the first actions on a
fresh spawn, holding just enough to re-enter the work.

- **What it holds:** the last few compacted session blocks (a rolling summary of recent work) plus the
  active-handoff block (below).
- **How it's maintained:** a rotation job writes the rolling summary on an interval, and the save routine
  refreshes it at natural breaks.
- **When it's read:** *in full* only on a fresh/crash spawn. On a normal resume the transcript already loads,
  so the parachute is redundant — **except** its active-handoff block, which must be pulled explicitly even
  on a normal resume (see the next section for why).

The parachute is the difference between a crash that loses a morning of work and a crash the agent recovers
from in one read.

## The active-handoff block

This is the subtle one, and it fixes a specific recurring bug. A normal resume-after-compaction loads the
transcript automatically — but the transcript is the *compacted* one, and the in-flight task detail may have
been summarized away. The agent resumes, sees a plausible summary, and **drops the task it was actually in
the middle of**, because the load-bearing mid-task state didn't survive the compaction.

The active-handoff block is a small, explicitly-maintained section (living in the bootstrap file) that holds
**mid-task state**:

- what task is in flight and what step it's on,
- what background work is running (and where its output lands),
- what's blocked, and on what.

Because it's a known file section rather than a transcript fragment, it survives compaction intact and is
pulled on *every* resume — not just fresh starts. That's the fix: continuity of an in-flight task can't
depend on the transcript, because the transcript is exactly what compaction thins.

**Write triggers** — populate or update the handoff block when:

- a task will outlast a single turn (a multi-step job, > a few minutes of work),
- a background process is running,
- context has grown past a working threshold,
- the operator pauses mid-task.

**Clear it when the task is done.** A stale handoff pointing at finished work is its own hazard — it tells the
next resume to pick up something that no longer needs doing.

## Size self-regulation

Because every reply re-sends the context, the agent checks its own session size each turn and acts at
thresholds. The number that matters is **bytes written since the last compaction**, not total file size —
the transcript is append-only, so the raw file keeps growing even after a compact, but only the post-compact
bytes reflect real per-reply cost.

| Bytes since last compaction | Action |
|---|---|
| low | Normal — do nothing. |
| moderate | At a natural break, **save** durable learnings. Don't compact — auto-compaction handles shrinking on its own. |
| high | Save now, at the next reply. Compact manually only if auto-compaction hasn't fired recently. |
| very high | Save, then compact together. |

**Decouple save from compact.** They are independent triggers: *save* extracts durable learnings to memory;
*compact* shrinks the live context. The runtime auto-compacts at a fixed token ceiling on its own, so
manually compacting on top of that is usually pure churn. Save after meaningful work; compact only when you
genuinely need the room. Chain the two only at the end of a long strategy session where you want a clean break
and a durable extraction in one turn.

## Read-depth under context pressure

As context fills, reading behavior should tighten *before* the budget panics:

- **Plenty of room** — full reads are fine.
- **Filling** — prefer frontmatter/summaries; delegate heavy exploration to a sub-agent.
- **Tight** — frontmatter only, stop inlining large files.
- **Near the limit** — checkpoint now (write the handoff), no new reads unless critical.

Early-warning signs that fire before a hard limit: claiming a task is done without checking the must-haves,
rising vagueness ("standard handling" instead of specifics), and skipping steps from an established
procedure. Treat those as a cue to checkpoint, not to push on.

## Restart vs. fresh restart

- **Resume (default).** A restart resumes the last session; the transcript reloads and work continues. Pull
  the active-handoff block; skip the rest of the parachute.
- **Fresh (deliberate).** A clean restart starts with no prior context — used only when the previous session
  is corrupted or you explicitly want a blank slate. Here the parachute is read *in full*, because there is no
  transcript to resume.

The signalling between "kill this session" and "respawn clean vs. continue" is a runtime concern
(a small watchdog respawns a missing session; a signal file distinguishes fresh from continue). The design
point is only this: **the two paths read different amounts** — resume trusts the transcript plus the handoff;
fresh trusts the parachute.

## Design principles

- **What must survive is written down.** Never trust the transcript to carry in-flight state across a
  compaction or restart.
- **The handoff is pulled on every resume.** Because compaction thins exactly the mid-task detail continuity
  depends on.
- **Measure bytes since compaction, not file size.** The append-only transcript keeps growing; only
  post-compact bytes are the real cost.
- **Save and compact are independent.** One is durable extraction, the other is context shrink; don't chain
  them by reflex.
- **Clear stale handoffs.** A checkpoint pointing at finished work misdirects the next resume.

See also: `memory-system.md` (durable memory the save routine writes to), `agent-protocols.md` (delegation as
a pressure valve), `security-gates.md` (the restate/scope step a checkpoint often precedes).
