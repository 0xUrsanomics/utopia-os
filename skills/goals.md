---
name: goals
description: Active-goal registry. Tier-1 north star steering. Maintains memory/state/active_goals.json with goals + milestones + requirements. Slash command for list/new/done/pause/abandon/touch/note/show + milestone CRUD + req CRUD. Drift-audited weekly. v2 adds work breakdown + ASCII progress bars.
trigger: /goals, active goals, current goals, what are we driving toward, north star, goal, milestones, work breakdown
---

# /goals. Active Goal Registry

Persistent tier-1 active-goal tracking that steers per-session work toward stated outcomes. Adapted from a coding-agent /goal pattern. v2 adds milestones + requirements + ASCII progress visualization.

## State file

**SSOT-canonical.** The registry lives under the `goals.active` key in the operational SSOT.
For every CRUD op below:
- READ the current registry: `python3 scripts/ssot.py get goals.active`
- After editing the structure, WRITE it back atomically:
  `python3 scripts/ssot.py set goals.active '<full json>' --by agent --reason "<op>"`

`ssot.set` mirrors `memory/state/active_goals.json` atomically, so the Step-5 refresh
(`update_memory_active_goals.py`, which derives the MEMORY.md block FROM that file) keeps working
unchanged. Do NOT hand-edit `active_goals.json` directly anymore; the mirror owns it.

Schema v2 (additive over v1).

**Goal entry shape** (full v2):

```json
{
  "id": "g-2026-05-09-001",
  "title": "ship the content pipeline to 5 daily posts",
  "why": "build the distribution loop before the BD ramp",
  "success_criteria": ["5/day for 14 consecutive days", "engagement >= 3 replies/post avg"],
  "created": "2026-05-09T09:30:00+00:00",
  "due": null,
  "review_after": "2026-06-08",
  "status": "active",
  "sessions_touched": 0,
  "last_advanced": null,
  "tags": ["distribution", "content"],
  "notes": [],
  "milestones": [
    {"id": "m-1", "title": "ship the Critic gate", "due": "2026-05-15", "status": "done", "completed_at": "2026-05-08T...", "depends_on": [], "notes": []},
    {"id": "m-2", "title": "5/day consecutive 7d", "due": "2026-05-23", "status": "in_progress", "completed_at": null, "depends_on": ["m-1"], "notes": []},
    {"id": "m-3", "title": "engagement >= 3 replies/post avg", "due": "2026-05-30", "status": "open", "completed_at": null, "depends_on": ["m-2"], "notes": []}
  ],
  "requirements": [
    {"id": "r-1", "type": "infra", "description": "external API wired", "status": "blocked", "blocker": "API access pending", "owner": "operator", "blocked_at": "2026-05-09T...", "notes": []},
    {"id": "r-2", "type": "user-action", "description": "review the batch every week", "status": "open", "blocker": null, "owner": "operator", "blocked_at": null, "notes": []}
  ]
}
```

**Caps** (in `_caps`):

- `max_active`: 10
- `review_after_default_days`: 30
- `drift_threshold_days`: 14
- `archive_after_terminal_days`: 30
- `milestone_stale_days`: 14 (an in_progress milestone with no progress = stale)
- `requirement_block_stale_days`: 7 (a blocked requirement past this = escalate)

**Status states**:
- Goal: `active` / `paused` / `done` / `abandoned`. Terminal: `done` / `abandoned`.
- Milestone: `open` / `in_progress` / `done` / `skipped`. Terminal: `done` / `skipped`.
- Requirement: `open` / `done` / `blocked`. Terminal: `done`.

## Commands

### `/goals` (no args) → list active

Read `active_goals.json`. Show a table with progress bars per goal:

```
🎯 active goals (2/10)

g-2026-05-09-001 ship content to 5/day                    review 2026-06-08
  milestones: [█████░░░░░] 1/3 done  (m-1 ✅ / m-2 ⏳ / m-3 ◻)
  reqs:       [░░░░░░░░░░] 0/2 done  (r-1 🚧 blocked / r-2 ◻)

g-2026-05-08-002 close a client delivery                  due 2026-05-11
  milestones: [██████████] 3/3 done
  reqs:       [█████████░] 2/3 done
```

If empty → "no active goals. /goals new to create one."

### `/goals new` → interactive create with **auto-proposed** breakdown

This is the BIG v2 flow. Steps:

1. **Phase A: gather basics** via conversational prompts:
   - title (1-line outcome)
   - why (1-sentence motivation)
   - success_criteria (1-3 bullets, what does done look like?)
   - due (optional, YYYY-MM-DD or "none")
   - tags (optional)

2. **Phase B: AUTO-PROPOSE milestones + requirements**. Inline reasoning, NOT a subagent. Steps:
   - Read the title + why + success_criteria.
   - Propose 3-5 sequential milestones that would walk from "started" to "all success_criteria met". Each milestone has: title, suggested due (back-calculated from the goal due if set, else from review_after), status=open, depends_on (chain milestones in order: m-1 has none, m-2 depends on m-1, etc).
   - Propose 3-5 requirements (skills / infra / content / user-action / external / budget / other categories). For each: type, description, suggested owner. but **ALWAYS ASK the user** to confirm the owner per req. Propose `agent` for skill/infra/content tasks, `operator` for user-action / external / budget tasks; the user can override.
   - Surface the proposed breakdown as a numbered list:
     ```
     proposed milestones for "{title}":
     m-1. {title} (due {date})
     m-2. {title} (due {date}, depends m-1)
     m-3. {title} (due {date}, depends m-2)

     proposed requirements:
     r-1. {type}: {desc}        owner? [agent/operator/external]
     r-2. {type}: {desc}        owner? [agent/operator/external]
     r-3. {type}: {desc}        owner? [agent/operator/external]

     reply: 'accept' / edit (e.g. 'r-1 owner operator, drop m-3, add milestone X') / 'skip breakdown' (create the goal without milestones/reqs)
     ```

3. **Phase C: iterate on the user response**. Apply edits. If the user says 'skip breakdown', create the goal with empty milestones/requirements arrays. they can add them later via /goals milestone add or /goals req add.

4. **Phase D: persist**. Generate `id` as `g-{YYYY-MM-DD}-{NNN}`. Append to state. Set defaults. Save.

5. **Post-save**: run `python3 scripts/update_memory_active_goals.py` to refresh the MEMORY.md block.

**Cap check**: if the active count == 10 before append → error "10 active goal cap hit. pause / done / abandon one before creating another. /goals list to see them."

### `/goals show <gid>` → full breakdown view

Single-goal deep view. Format:

```
🎯 g-2026-05-09-001  ACTIVE  review 2026-06-08
title: ship the content pipeline to 5 daily posts
why: build the distribution loop before the BD ramp
tags: distribution, content

success criteria:
  ✅ none yet (no milestone metrics auto-mapped. manual flip on /goals done <gid>)
  - 5/day for 14 consecutive days
  - engagement >= 3 replies/post avg

milestones [█████░░░░░] 1/3 done
  ✅ m-1  ship the Critic gate                completed 2026-05-08
  ⏳ m-2  5/day consecutive 7d                due 2026-05-23 (depends m-1)
  ◻  m-3  engagement >= 3 replies/post avg    due 2026-05-30 (depends m-2)

requirements [░░░░░░░░░░] 0/2 done
  🚧 r-1  infra: external API wired           owner operator. blocker: API access pending (blocked 0d ago)
  ◻  r-2  user-action: review the batch weekly   owner operator

session activity:
  sessions_touched: 0
  last_advanced: never
  drift: ⚠️ 14d idle threshold (currently 0d, healthy)

notes: (none)
```

### `/goals done <gid>` / `/goals pause <gid>` / `/goals abandon <gid>`

Mark the goal terminal/paused. Record `<status>_at: now`.

If the id is not found → "no goal {id}. /goals list to see ids."
If the goal has open milestones at /goals done → ask "this goal still has 2 open milestones. mark done anyway? y/n".

### `/goals touch <gid>` → bump sessions_touched + last_advanced

Manual touch. Auto-called by /save (Step 3.7).

### `/goals note <gid> "<text>"` → append a note to the goal

Append `{"ts": now, "note": "<text>"}` to `notes[]`.

### Milestone CRUD (v2)

- `/goals milestone <gid> add "<title>" [--due YYYY-MM-DD] [--depends m-X]`
  - Generate `m-N` where N = max(existing m-ids) + 1.
  - Default depends_on = the last open or in_progress milestone (so the chain extends naturally).
- `/goals milestone <gid> in-progress <mid>`
  - Mark in_progress. Auto-touch the parent goal.
- `/goals milestone <gid> done <mid>`
  - Mark done, set completed_at. If all milestones done, suggest "all milestones complete. /goals done <gid>?"
- `/goals milestone <gid> skip <mid>`
  - Mark skipped. Note the reason.
- `/goals milestone <gid> note <mid> "<text>"`

### Requirement CRUD (v2)

- `/goals req <gid> add <type> "<description>"`
  - Generate `r-N`. **Always ask** for the owner: prompt the user [agent/operator/external].
  - status defaults to `open`.
- `/goals req <gid> done <rid>`
- `/goals req <gid> block <rid> "<text>"`
  - Set status=blocked, blocker=text, blocked_at=now.
- `/goals req <gid> unblock <rid>`
  - Set status=open, blocker=null, blocked_at=null.
- `/goals req <gid> note <rid> "<text>"`

## ASCII Progress Bar render (v2)

10-cell bar: `[██████░░░░]`. Each cell represents 10% (so 0-10 cells filled).
`[██████████] 6/6 done` → all done. `[░░░░░░░░░░] 0/3 done` → none.

Render formula: `cells_filled = round((done / total) * 10)`, clamp 0-10. If total=0, show `[----------] 0/0` (gray dashes).

Used in:
- `/goals` list (one per goal: milestones + reqs)
- `/goals show <gid>` (one per group)
- MEMORY.md `## 🎯 Active Goals` block (compact, milestones bar only)
- Wake-up briefing section [10] (compact, milestones bar only)

## Surfacing

### Layer 1. MEMORY.md (ambient, ASCII bar inline)

`<!-- active-goals-start -->` ... `<!-- active-goals-end -->` markers preserved. Format v2:

```markdown
## 🎯 Active Goals

- `g-2026-05-09-001` ship content to 5/day  [█████░░░░░] 1/3 . review 2026-06-08
- `g-2026-05-08-002` close a client delivery [██████████] 3/3 . due 2026-05-11
```

After ANY state mutation (new / done / pause / abandon / touch / milestone-* / req-*), run:
```bash
python3 scripts/update_memory_active_goals.py
```
Idempotent. Replaces the block in-place if markers present, prepends if not.

### Layer 2. Wake-up briefing (explicit)

Section [10] ACTIVE GOALS. Per goal:
```
🎯 g-2026-05-09-001 ship content to 5/day   [█████░░░░░] 1/3   idle 0d
   ⚠️ r-1 blocked 3d on "API access pending"
```

Auto-flagged inline:
- `⚠️ drift Nd` if days_idle ≥ 14
- `⚠️ overdue Nd` if past due
- `🚧 r-X blocked Nd on "<reason>"` for each requirement blocked >0d

## Integration with /save

`skills/save.md` Step 3.7 runs `goal_touch_session.py` which scans outputs/raw/**/*.md (last 24h) for frontmatter `goal: g-XXX` tags and bumps `sessions_touched` + `last_advanced` for matching active goals.

## Drift cron (v2 extends)

`scripts/goal_drift_audit.py` (weekly). Findings:
- **drift**: zero last_advanced for ≥ drift_threshold_days
- **overdue**: due < today
- **review-due**: review_after < today
- **milestone-stale** (v2): milestone status=in_progress, last touch ≥ milestone_stale_days
- **requirement-block-stale** (v2): requirement status=blocked, blocked_at ≥ requirement_block_stale_days ago

Writes to `outputs/raw/agent/{date}-goal-drift.md`. Chat digest only on findings.

## Hard rules

- Never auto-delete. Mark terminal + archive after 30d via a dedicated script.
- Never auto-promote paused → active.
- Terminal status is sticky.
- No scoring (Bayesian/EV) in v2. Just count + status. v3 if the drift signal proves not enough.
- Always ask for the req owner per add.
- Auto-propose milestones + reqs on /goals new but ALWAYS surface for user edit before persist.

## Persona scope

Unified (not persona-split). The default persona + coach read/write the same registry. The time budget is shared across personas.

## Source references

- Design params: cap=10, due=optional, drift=14d, scope=unified, drift_cron ships day 1.
- v2: auto-propose breakdown, visible-only allocation with an ASCII bar, always-ask owner.
- Existing patterns lifted: the stand-down registry shape, the `state/` convention, the `skills/save.md` extraction discipline.
