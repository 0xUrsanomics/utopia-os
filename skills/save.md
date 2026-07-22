---
name: save
pinned: true
description: Session summary extraction. review recent session, extract preferences/decisions/context/voice/learnings, write to the appropriate memory/ tier files.
trigger: save, session save, memory save, /save
---

# /save. Session Summary Extraction

Run this when the user types `/save`, when session rotation hits ~20 exchanges, or when the Stop-hook signal bridge dispatches `/save` to the live REPL.

## What this does

Review the current session in memory and extract durable facts into the right tier of the memory system. This is the primary preservation step against context compression loss.

## Procedure

### Step 1. Scope the review
Look at the ACTUAL session transcript for this run. Focus on:
- User preferences expressed (explicit or implicit)
- Decisions made with context + reasoning
- Ongoing project / deal / relationship facts that changed
- New writing-style observations
- Insights or learnings worth remembering across sessions

Skip:
- Quick Q&A exchanges
- Ephemeral debugging output
- Things already documented in existing memory files

### Step 1.7. Musing Harvest

Step 1's skip-rule ("skip quick Q&A / ephemeral chat") is correct for everything EXCEPT one signal class. The operator's offhand musings are the richest, most under-captured source of worldview + temperament + cognitive-style modeling (operators systematically under-rate their own tacit output). This step carves out that one exception.

Re-scan the transcript specifically for casual-register musings that reveal: how they think (cognitive style, mental models, what they reach for), what they value / how they decide (temperament, triggers, defaults), or a worldview/thesis position stated offhand rather than in a structured answer.

**Operator-tacit filter (hard gate, this is the anti-bloat valve)**: capture a musing ONLY if "only someone in the operator's exact seat would think or say this." Generic offhand lines, reactions, logistics, jokes-without-signal → still skipped per Step 1. If a musing would be unremarkable coming from any operator, it is not signal.

**Routing**:
- worldview / thesis / market-position musing → append to `memory/projects/<active>.md` under a `## Voice Excerpts (verbatim worldview anchors)` section (dated block, same format as the voice-authoring interview phase, INCLUDING the `topics:: [..]` multi-tag line from the controlled vocab in `knowledge/interview-sharpening.md`). This feeds the interview-sharpening corpus, so it compounds into future interview questions automatically.
- temperament / values / how-they-decide / communication-pattern → `memory/USER.md` (durable model) and/or `memory/user-model.md` (behavioral, dreaming-updated).
- a falsifiable cross-session insight → the normal LEARNINGS path (Step 2 cat 5).

**Discipline**: every harvested musing still passes the Step 2.5 write-gate AND Step 2.6 confidence treatment. no bypass. Verbatim > paraphrase for worldview anchors (capture their actual phrasing). If nothing clears the operator-tacit filter, this step produces nothing. that is the correct outcome for a logistics-only session, not a failure.

### Step 2. Extract into 5 categories

1. **PREFERENCES**: workflow, formatting, behavior rules the user stated
   Format: `key:: value` pairs, append to `memory/Preferences.md` (dedup on key::)
   Wisdom-layer note: when adding a behavioral rule (port from arXiv 2604.11364), include an `evidence::` line tracking `[applied_count, last_applied_date, outcome_distribution]`. Initial state on first save: `evidence:: [1, YYYY-MM-DD, untested]`. graph-hygiene check #12 audits stale rules (zero recent evidence = speculative, may not be working).

2. **DECISIONS**: architectural / strategic / tactical choices with context
   Format: dated block in `memory/Decisions.md` with `context::`, `decision::`, `reasoning::`, `status::`

3. **CONTEXT**: ongoing facts about subjects (deals, projects, relationships, systems)
   If small: append to an existing `memory/Context/<subject>.md` or `memory/Infra/<component>.md`
   If a new subject is big enough: create a new file

4. **VOICE**: writing patterns: sentence length, word choice, tone, language mix, formatting habits
   Append to `memory/Voice-Profile.md`

5. **LEARNINGS**: insights worth remembering across sessions, tagged
   Append to `memory/Learnings.md` with date + tags
   Wisdom-layer note: like Preferences, learnings can carry an `evidence::` field. Optional, but useful when the learning makes a falsifiable claim ("X always causes Y").
   Fix-owed tag: when a LEARNINGS entry names a SPECIFIC, SCOPED, un-shipped fix (not a pure observation), add the tag `fix-owed` to its tag line. Meta-memory-review's lens-D worklist is then `grep -l 'fix-owed' memory/Learnings.md` minus anything carrying a `closed_by::` marker. Converts the weekly recurring-failure scan from a full re-read into a deterministic tag-grep. A pure observation ("X tends to cause Y") is NOT fix-owed; only an entry naming a concrete fix that has not shipped. Clear the tag (or add `closed_by::`) once the fix ships.
   Recurrence tag: when a LEARNINGS entry is a REPEAT of a prior failure mode (not a first observation), tag it `#recurrence-Nx` on the tag line, where N = how many times this shape has now fired (e.g. `#recurrence-4x`). Optional `recurrence:: N` field mirrors it as structured data. Forward-only. no reformat of history. This makes the weekly recurrence scan a deterministic `grep '#recurrence-'` sorted by N, instead of guessing from freeform prose ("4th occurrence", "again", "still"). A first-time observation gets NO tag; the tag appears only on the 2nd+ occurrence. Pairs with `fix-owed`: a recurring un-shipped fix carries both (`fix-owed #recurrence-3x`).

### Step 2.5. Write-gate (MemReader port)

Adapted from MemReader (arXiv 2604.07877): actively decide whether to write each candidate, don't just dump everything Step 2 surfaced. Apply this 3-question gate to EVERY candidate before it goes to disk:

1. **Value**: is this novel? Does it add information not already in the same file/section, OR materially refine what's there? If it duplicates an existing entry without adding nuance, **DROP**.
2. **Reference clarity**: are the referents in this entry unambiguous to a future-agent with no session memory? "the operator said yes" without context = ambiguous, drop or expand. "the operator greenlit X for reason Y on 2026-MM-DD" = clear, keep.
3. **Completeness**: is enough context attached for the entry to be useful 30 days later? If the entry is just a fragment that needs the current session to interpret, either expand it OR DROP.

Items failing the gate → don't write. Items passing → proceed to Step 3.

Anti-pattern this guards against: extracting "the operator was friendly today" / "good session, lots done" / "we discussed X". vague low-value chatter that bloats memory tier-2 without ever helping a future query. Memory should be expensive to write so it stays cheap to read.

**4th question, the reject list (from GovMem arXiv 2607.02579).** The three
questions above catch vague chatter. They do NOT catch entries that look like solid technical
lessons but transfer nothing. GovMem's external human adjudication rejected **all 133** candidates
it reviewed, and the failures clustered into four named shapes. That adjudication is the only part
of that paper backed by real human review rather than synthetic data, so it is worth more than its
scoring method. **DROP if the candidate is:**

1. **Boilerplate verification.** Command echoes, test output, warning banners, or an exit code
   presented as if they were the finding. "Ran it, exit 0" is not a lesson. What the exit code
   let you CONCLUDE might be.
2. **Task-local narration.** What was attempted in one specific task, in sequence. "First I tried
   X, then Y worked." Useful in the session, worthless 30 days out unless a transferable rule is
   stated explicitly.
3. **File dumps.** A source listing, config block, or directory tree converted into a procedural
   memory without demonstrating that the procedure is correct or general.
4. **Non-reusable debugging traces.** Read-only inspections and speculative diagnoses stored as
   durable knowledge. "Checked whether it was the cache, it wasn't" is a dead end, not a finding.
   Write it only once you know what it WAS, and only if the mechanism generalises.

When this was measured on a real corpus before adoption, hundreds of existing Learnings entries
scored against the four traps came in very low, and the one high count collapsed to mostly
legitimate entries on manual reading. **So this is preventive, not remedial. Do not launch a
cleanup pass over existing entries on the strength of this list.**

### Step 2.6. Confidence + promotion gate (atomic-instinct lift)

Lifted from a continuous-learning pattern (`affaan-m/everything-claude-code`). Closes the gap where a one-off Learnings entry carries the same weight as a 5-times-confirmed one.

Any LEARNINGS or PREFERENCES candidate that makes a **falsifiable behavioral claim** ("X causes Y", "always do Z", "pattern P recurs") gets two extra fields appended to its entry:

- `confidence:: <0.3-0.9>`. start at **0.3** on the first single observation. On each independent re-confirmation in a later session, bump +0.1 to +0.2. Cap at **0.9**, never 1.0 (predictive not certain, same collusion-floor reasoning as the content critic: an LLM-derived pattern is never proven).
- `scope:: project:<name> | global`. `project:<name>` if the claim was only observed inside one project/context (prevents cross-project contamination: a content pattern is not automatically a pipeline pattern). `global` only if observed across 2+ distinct contexts.

**Promotion gate** (atomic-instinct rule): a Learnings entry only hardens into a **Preference** (always-active rule) or a **skill edit** when ALL of:
1. `confidence:: >=0.8`
2. `scope:: global` (observed across 2+ distinct projects/contexts)
3. `>=20` cumulative observations OR explicit operator confirmation ("yes, always do this")

Until the gate passes, it stays an episodic Learnings entry (recall-fetched, not always-loaded). This keeps speculative single-observation patterns out of tier-1 reply-cost. The existing `evidence:: [applied_count, last_date, outcome]` array (Step 2 items 1+5) is the raw substrate; `confidence::` is the derived scalar the gate reads. graph-hygiene check #12 already audits stale rules; this gate is the inbound side of the same discipline.

**Skip** for non-falsifiable entries (pure factual context, dated decisions, subject dossiers). Confidence only applies to claims that could later be proven wrong.

### Step 3. Write

For each extracted item that passed the Step 2.5 gate:
- Prefer UPDATING existing files over creating new ones
- Dedup: check if the fact is already stored before writing
- Keep entries concise. future sessions pay cost to read them
- Use the existing file format (`key:: value` for Preferences, dated entries for Decisions/Learnings)

### Step 3.2. Provenance stamp

Every NEW `##` entry written to `Learnings.md`, `Decisions.md`, or a `Context/`/`Infra/`/`Feedback/`
dossier gets a provenance line on the line immediately BELOW its heading:

```
python3 scripts/lib_provenance.py stamp --support once --ingest clean
# -> provenance:: agent=<name> session=2026-07-20 support=once ingest=clean
```

Placement is not cosmetic: `vector_brain` chunks on `##` boundaries, so a line directly under the
heading rides inside that chunk and shows up in `recall` output for free. Put it anywhere else and
the stamp can end up in a different chunk than the claim it describes, which is worse than no stamp.

Set the two fields honestly, they are the whole point:
- **`--support`** `once` for something observed one time. `Nx` ONLY when N *independent* incidents
  support it. Restating the same incident in three entries is still `once` in each. Do not inflate.
- **`--ingest untrusted`** when the entry's reasoning leaned on external content pulled this
  session (a fetched page, a paper, an email, OSINT, an external research digest). `clean` when it
  came from your own code, data, files, or observed tool behaviour. This is the belief-path flag:
  "authority is the envelope" blocks the instruction path, but untrusted content can still shift
  what you CONCLUDE, and that conclusion then gets written with genuinely legitimate agent
  provenance that no provenance check can catch.

Do NOT backfill stamps onto older entries. Their true origin is unrecoverable and inventing one
manufactures exactly the false confidence this exists to prevent. Unstamped means unknown.

Sanity check after a run: `python3 scripts/lib_provenance.py audit`. It reports coverage
and, more usefully, **same-session clusters**: k entries sharing one session are k restatements of
one origin, not k independent confirmations. Expect your own run to appear there. That is correct.

### Step 3.5. Active Handoff block management (GSD pattern)

Check `memory/session-bootstrap.md` for an `## Active Handoff` block:

- **If the current /save run is at task completion**: clear the block (replace content with `(none. no active handoff)`). The work is done, the extract went to Decisions/Learnings, the handoff is no longer needed.
- **If the current /save run is mid-task and long work continues**: update the block with the latest timestamp + revised status + revised next_action. This is your resume anchor if a watchdog restart fires.
- **If no handoff block exists and work is paused / long-running**: write a fresh block using the template in session-bootstrap.md (`## Active Handoff` section `### Handoff block format`). Fill in task, status, artifacts, pending, relevant_paths, next_action.
- **If no handoff block exists and work is complete**: do nothing. The block is only for ongoing work.

This keeps session-bootstrap.md's Active Handoff section synced with reality at every /save cycle.

### Step 3.6. Skill crystallization check (GenericAgent-pattern port)

Scan the session for tasks where the agent executed **3+ novel steps that don't map to an existing skill** in `skills/_index.md`. "Novel" = a sequence of tool calls / file ops / scripts figured out from scratch, not from following a documented skill procedure.

When found, draft a SKILL CANDIDATE at `outputs/raw/skill-candidates/<slug>.md` with frontmatter:
```yaml
---
name: <slug>
description: <one-line. what task does this enable>
trigger: <natural-language phrases that should invoke it>
status: candidate (drafted by /save 2026-MM-DD, awaiting /review)
parent_session: <jsonl filename or short id>
---

# <Skill Name>

## When to use
<2-3 sentences>

## Procedure
1. Step description (with the actual tool/command used)
2. ...
3. ...

## Notes / gotchas
- <whatever surprised me / what I wish I'd known>
```

**Don't auto-promote** to `skills/`. The candidate sits in `outputs/raw/skill-candidates/` until /review approves and the operator moves it. Same review pipeline as raw outputs.

**Skip if**: the novel sequence was a one-time investigation (debugging, audit, sweep) unlikely to recur. Skill creation should serve future runs, not document one-off work.

**Anti-pattern this guards against**: institutional knowledge bleeding out on every compact. Without this check, the agent solves the same novel problem multiple times because the previous solve only existed in the transcript.

### Step 3.7. Touch active goals (/goals integration)

After the write step, run:
```bash
python3 scripts/goal_touch_session.py --since-hours 24
```

The script scans `outputs/raw/**/*.md` modified in the last 24h for frontmatter `goal: g-XXXX-XX-XX-NNN` tags. For each unique goal id found, it bumps `sessions_touched` + `last_advanced` in `memory/state/active_goals.json`. Idempotent. Safe on an empty registry.

If the script reports `touched: [g-..., ...]`, include them in the Step 5 confirm message ("💾 saved. ... touched goals: g-X, g-Y."). If touched is empty, no surface needed.

**Skip this step** if: no `outputs/raw/` writes happened in the session (e.g. pure conversation, no substantive output). The goal-touch is for outputs that explicitly tag a goal, not session-level metadata.

### Step 4. Log

Append a one-line summary to `logs/session.jsonl`:
```json
{"ts":"<ISO>","level":"info","persona":"agent","category":"save","event":"session save. N items extracted","breakdown":{"preferences":X,"decisions":Y,"context":Z,"voice":A,"learnings":B}}
```

### Step 5. Confirm briefly

One short message (not a wall of text):
> "💾 saved. N items across {categories with content}. {1-sentence highlight of the most important extract}."

### Step 5.5. Self-Judge (LLM-as-Judge pattern, MVP spec)

After extraction completes (Step 1-3) but BEFORE the Step 6 chat send, score the extraction on 3 dimensions. This is a self-judgement, NOT a separate model call (the model is already running this skill, this just adds a meta-cognition step).

Dimensions to score (1-5 each):

- **Completeness**: did this run capture all preference shifts / decisions / context updates that happened in the session? Is anything important left in the transcript that should have been extracted? Be honest: 5 = full coverage, 3 = missed 1-2 minor items, 1 = missed something obvious.
- **Dedup quality**: did the writes correctly check existing files for duplicates before append? Are any new entries actually rephrased duplicates of existing entries? 5 = clean dedup, 3 = 1-2 near-duplicates slipped, 1 = significant duplication.
- **Relevance**: are the extracted items genuinely worth durable storage, or padding the count? 5 = every item earns its place, 3 = 1-2 borderline items, 1 = ≥3 items shouldn't have been saved.

Append a JSON block to `logs/session.jsonl` immediately after the Step 4 log line:

```json
{"ts":"<ISO>","level":"info","persona":"agent","category":"save_judge","event":"self-judge complete","scores":{"completeness":N,"dedup":N,"relevance":N},"avg":N.N,"notes":"<one-line if avg <4>"}
```

If `avg < 4`: include a single-clause flag in the Step 6 chat reply, e.g. `"💾 saved. 2 items across {categories}. {highlight}. (self-judge avg 3.3, may need re-pass)"`. Don't dwell. If `avg >= 4`: skip the score mention in chat, just log it.

**Why self-judge instead of a separate Judge model**: per the LLM-as-Judge literature, scoring requires a model call, but external print-mode invocations can have harness boundary issues. Until that's solved, the cheap reliable path is self-judgement inside the running skill. Imperfect but ships now.

**Future v0.2** (when external model invocations work cleanly): replace the self-judge with a separate sub-agent dispatch that scores against the original transcript + the saved files. More objective, more expensive.

**Future v0.3** (when a skill-eval cron ships): aggregate save_judge scores over time. Surface the trend (is /save quality drifting?). Flag systemic dedup failures.

**Boundary**: if the session was brief / temp-mode was on / the "nothing worth saving" path triggered → skip Step 5.5 entirely. The judge has nothing to score.

### Step 6. ALWAYS send a chat confirmation (mandatory)

Regardless of how `/save` was invoked (the operator typed it, the stop-hook dispatched it, or it self-initiated), **end with a chat reply** using `mcp__plugin_telegram_telegram__reply` to the operator's chat_id. This is non-negotiable.

**Why:** when save is dispatched via tmux send-keys (the stop-hook path), the REPL's terminal output doesn't reach the chat channel. Without this step, the operator sees nothing. and if native auto-compact fires right after save (common, because save's tool-call burst pushes the jsonl size over the native threshold), the conversation goes silent from their perspective.

**Heads-up requirement:** if `ACTIVE_BYTES_SINCE_COMPACT` is >8MB at the start of Step 5 (check via `source scripts/lib_active_session.sh && find_active_session`), append a note to the chat reply: `"⚠️ session thick ({X}MB since compact), native auto-compact may fire next turn. I'll ping when I'm back."`

**Template:**
```
💾 saved. {N items across categories}. {1-sentence highlight}.
[optional: ⚠️ session {X}MB, compact incoming.]
```

No reply_to needed unless responding to a specific message.

## Category discipline (from the 4-type mental model)

When writing a new fact, ask *what KIND of memory is it?*

- Behavior rule (always active) → `Preferences.md` or `CLAUDE.md`
- Writing style pattern → `Voice-Profile.md`
- Decision with context/reasoning → `Decisions.md` (episodic, recall-fetched)
- Insight/learning tagged by topic → `Learnings.md` (episodic, recall-fetched)
- Subject dossier (deal, company, person) → `memory/Context/<subject>.md`
- Infra state change → `memory/Infra/<component>.md`
- Persona-specific → `memory/personas/<slug>.json`

## Rules

- **NEVER** store message content verbatim, API keys, credentials, or sensitive personal data
- **NEVER** create empty files or placeholder entries. if nothing new to save in a category, skip it
- **NEVER** duplicate existing entries. check Preferences.md / Decisions.md / Learnings.md first
- Maximum 5 new files per save run to avoid bloat (update existing files freely)
- If the session was brief / nothing substantive happened / temp mode was on: respond "nothing worth saving" and exit
- If the session was heavy (multiple decisions / substantive work): multiple categories will have entries, that's expected

## Why this skill exists

`/save` was originally a documented convention in CLAUDE.md without a registered skill file. When the Stop-hook signal bridge (`scripts/stop_hook_save.sh` + `save_handler.sh`) started dispatching `/save` to the live REPL, the CLI returned "Unknown skill: save" because the convention wasn't wired as an actual skill. This file closes that gap. `/save` is now a real command the REPL can resolve.

Reference: `memory/Infra/stop-hook-save-integration.md` for the full Stop-hook → handler → send-keys chain.
