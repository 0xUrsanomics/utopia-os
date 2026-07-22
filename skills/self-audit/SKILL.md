---
name: self-audit
description: Agent reads its own error logs, identifies recurring failures and capability gaps, proposes and applies fixes
trigger: self audit, fix errors, capability gaps, what's broken, debug system
linter_ack: ["dynamic-exec: inline python3 -c blocks here are static ops one-liners, not eval of fetched content"]
---

# Self-Audit. Error-Driven Self-Improvement

The agent reads its own failure history, identifies patterns, and patches itself.
Inspired by an agent capability-evolver pattern. Runs scheduled or on-demand.

## When to Run
- Scheduled: daily at 02:00 local (after the nightly system audit at 01:30)
- Manual: "audit yourself" or "what's broken"

## Procedure

### Phase 0. Missed-Run Detection
Before reading error logs, check for silent scheduler misses (task never started, no log entry):

**IMPORTANT**: a stale scheduler-list tool can read from a legacy DB. Always query the daemon's live DB directly:
```python
python3 -c "
import sqlite3, os
from datetime import datetime, timezone, timedelta
db = os.path.expanduser('~/.agent-daemon/data/scheduler.db')
conn = sqlite3.connect(db)
now = datetime.now(timezone.utc)
rows = conn.execute('SELECT name, cron_expr, enabled, last_run FROM schedules ORDER BY last_run').fetchall()
for name, cron, enabled, last_run in rows:
    if last_run:
        lr = datetime.fromisoformat(last_run)
        if lr.tzinfo is None: lr = lr.replace(tzinfo=timezone.utc)
        age_h = (now - lr).total_seconds() / 3600
        if age_h > 48: print(f'STALE {age_h:.0f}h: {name} ({cron})')
    else:
        print(f'NEVER_RUN: {name}')
conn.close()
"
```

Also check for stuck "running" executions (>4h):
```python
python3 -c "
import sqlite3, os
from datetime import datetime, timezone, timedelta
db = os.path.expanduser('~/.agent-daemon/data/scheduler.db')
conn = sqlite3.connect(db)
now = datetime.now(timezone.utc)
rows = conn.execute(\"SELECT id, schedule_name, started_at FROM execution_log WHERE status='running'\").fetchall()
for exec_id, name, started in rows:
    lr = datetime.fromisoformat(started)
    if lr.tzinfo is None: lr = lr.replace(tzinfo=timezone.utc)
    age_h = (now - lr).total_seconds() / 3600
    if age_h > 4: print(f'STUCK {age_h:.0f}h: {name} (id={exec_id})')
conn.close()
"
```

Flag stale tasks and stuck runs as `capability_gap` signals into Phase 1.

Key schedules to watch (keep a list of any that have silently missed before):
- a morning-briefing job (e.g. cron `35 8 * * *`)
- a weekly-assembly job (e.g. cron `0 19 * * 5`)
- a graph-hygiene job (e.g. cron `0 8 * * 6`)

### Phase 0.5. Stale-Recall Verification

**MANDATORY before reciting ANY stale / NEVER_RUN / pending-CONFIRM / pending-USER-ACTION item from prior audits, memory, or queue:** cross-reference against the LIVE source of truth. Skipping this step is how stale-recall failures get repeated. first the auditor "remembers" the item, then it gets cited as pending in the report, then the user re-confirms it's already done. Loss of trust per cycle.

**Verification matrix** (run before adding any item to the audit report):

| Item type | Source of truth | Check before reciting |
|---|---|---|
| `schedules.last_run IS NULL` ("NEVER_RUN") | `execution_log` table (same DB) | `SELECT MAX(started_at) FROM execution_log WHERE schedule_name=?`. if a row exists, the task DID run, last_run is just stale (recreated task) |
| `STALE >48h` | execution_log + cron expression | Compute the expected next-fire from cron_expr. If next-fire hasn't elapsed yet, it's not stale. |
| `pending-CONFIRM` item from a prior audit | git log on the referenced files + scheduler state | Has the file changed? Has the task been recreated? If yes, the item is RESOLVED, don't re-recite. |
| `pending-USER-ACTION` (CRM adds) | live CRM read via your CRM search tool | Search the target name/identifier in the CRM. If found, the item is DONE. |
| `pending-USER-ACTION` (settings.json edit) | grep settings.json | If the setting key exists with the expected value, the item is DONE. |
| stop-hook / hook drift fix | grep the target hook file | If the fix is present, the item is RESOLVED. |
| MCP server status | runtime test (one tool call to that MCP) | If it responds, the "needs reconnect" memory is stale. |
| dossier claim "task is broken" / "silent-failing" / "needs fix" | `execution_log` table (most recent 3 runs of that schedule) | `SELECT status, output, error FROM execution_log WHERE schedule_name=? ORDER BY started_at DESC LIMIT 3`. If recent runs show status=completed AND output is empty or matches the expected pattern (the script logs internally), the dossier is STALE. An `Infra/*` dossier captures a point-in-time diagnosis. If the underlying daemon code, whitelist, or wrapper has changed since the dossier was written, the claim may no longer hold. Verify before reciting. (A real cascade came from a dossier that was stale by a week: the audit re-recited it as fact, /scope built on it, and several schedule updates shipped on a wrong premise.) |

**Pattern rule** (named, for future recall): *"check before reciting"*. sibling to the brain-first multi-file pattern. When an audit pulls from a prior memo or queued list, the cited items have a HALF-LIFE. they decay relative to the system state. Recite without re-verifying = stale-recall, and the operator has corrected this repeatedly.

**Implementation hint**: if the verification check itself fails (DB down, MCP unreachable), mark the item `unverified-because-source-down` in the report, not `still pending`. Don't fabricate the verification outcome.

**Auto-loop guard**: Phase 0.5 runs AFTER Phase 0 (missed-run detection) but BEFORE Phase 1 (signal collection). Any Phase 0 finding labeled "STALE" or "NEVER_RUN" must pass Phase 0.5 verification before it survives into Phase 2 (pattern analysis). Items that fail verification (= turn out to be already done) drop silently; items that pass verification graduate to Phase 1 as legitimate signals.

### Phase 1. Signal Collection (read-only)
Read the last 48 hours from:
- `logs/errors.jsonl`: tool call failures, MCP issues, timeouts
- `logs/session.jsonl`: commands that didn't work, retries, workarounds
- Recent scheduler execution logs via `schedule_execution_log`
- **Subagent reputation flags**: run `python3 scripts/security/subagent_reputation.py flagged`. Any pending flags = a `(subagent_type, domain)` pair with 3+ verified-fails in 14d. Treat as signals into Phase 1 with `signal_type: subagent_reputation`. Don't auto-resolve. surface in the audit report so the parent decides whether to (a) update `agent-phase-domains.json` (swap the recommended subagent_type), (b) sharpen the briefing scaffold in `skills/agent-dispatch/SKILL.md`, or (c) mark reviewed via `subagent_reputation.py reviewed <subagent_type> <domain>` if it's a false-positive.

Extract typed signals:
- **log_error**: repeated tool/MCP failures (same error 3+ times = pattern)
- **capability_gap**: the user asked for something we couldn't do
- **perf_bottleneck**: tasks that timed out or took abnormally long
- **protocol_drift**: behavior that contradicts CLAUDE.md rules
- **subagent_reputation**: flagged `(subagent_type, domain)` pairs from the reputation tracker

### Phase 2. Pattern Analysis
For each signal type, identify:
- Root cause (not just symptom)
- Frequency (one-off vs recurring)
- Impact (blocks the user vs minor annoyance)
- Affected component (which skill, MCP server, script, or config)

Score each pattern: `severity = frequency × impact`
Rank by severity descending.

### Phase 2.5. Failure-Cluster Escalation
Phase 2 proposes single-agent fixes; a CLUSTER of failures warrants an adversarial PANEL instead of another single-agent band-aid (root-cause-over-bandaid). Run the detector:
```
python3 scripts/eval/failure_cluster_detector.py --hours 24
```
It groups errors.jsonl by category and returns `convene_worthy` clusters (>= threshold in the window, DEDUPED against a state file so a chronic/known cluster is not re-escalated every night unless it grew >= 50% or > 7d since the last flag). Exit 1 if any convene_worthy, else 0 (skip this phase silently on exit 0).

For EACH `convene_worthy` cluster: convene a review PANEL via `skills-shared/decision-council/SKILL.md` (dispatch 1 foreground subagent per that skill, feed it the cluster category + count + sample + the recent failing entries for that category). Surface the panel's verdict in the audit summary as `⚠️ cluster: <category> x<count> -> panel: <one-line verdict>`. Do NOT auto-apply the panel's fix (surface + let the operator decide, same ceiling-accept discipline as the rest of the audit). This is where a repeatedly-band-aided cluster (e.g. a chronic dispatch timeout) finally gets a root-cause panel instead of fix #N.

### Phase 3. Mutation Proposals
For the top 3 patterns by severity, propose a specific fix:

| Pattern Type | Fix Category |
|-------------|-------------|
| MCP failure | config change, retry logic, fallback |
| Skill gap | new skill file or skill update |
| Script error | code fix in scripts/ |
| Config drift | CLAUDE.md or settings.json update |
| Timeout | increase timeout, optimize prompt, switch model |

Each proposal must include:
- What to change (specific file + line/section)
- Why it fixes the problem
- Risk level (safe / needs-review / risky)
- Rollback plan

### Phase 4. Apply or Queue
- **Safe fixes** (config tweaks, retry logic): apply immediately with a git-style backup
- **Needs-review fixes** (skill rewrites, new scripts): save to `outputs/raw/agent/` for /review
- **Risky fixes** (CLAUDE.md changes, MCP server edits): flag to the operator via chat, do NOT apply
- **Post-apply verification (mandatory)**: after every file edit, verify the change was actually written. Do NOT report "fix applied" based solely on the Edit tool returning without error. the Edit tool has a known false-success failure mode. Read the relevant section back or use Grep to confirm the change is present before marking done.

### Phase 5. Log
Append to `logs/session.jsonl`:
```json
{"ts":"...","level":"info","persona":"agent","category":"self-audit","event":"N patterns found, M fixes applied, K queued for review"}
```

Save the full audit report to `outputs/raw/agent/YYYY-MM-DD-self-audit.md`.

## Rules
- NEVER modify CLAUDE.md without explicit user approval
- NEVER change API keys, credentials, or .env files
- ALWAYS backup before modifying any file: copy to `sandbox/archive/` first
- Maximum 3 fixes per run (don't over-mutate)
- If the same pattern persists after 3 fix attempts, escalate to the operator
- Read-only on the first run after install (observe before acting)

## What NOT To Do
- Don't fix things that aren't broken
- Don't add complexity to solve simple problems
- Don't refactor code during an audit. only patch specific failures
- Don't suppress errors by catching and ignoring them. fix root causes

## Adversarial Stance (from a GSD audit)

**Starting hypothesis: the system is FAILING quietly until evidence proves it's healthy.** Audit fatigue is the enemy. "Looked at this last week" is not a reason to skip.

**Common ways self-audit goes soft (catch yourself here):**
1. Marking a repeated-failure pattern as "intermittent" instead of root-causing it. 3 same-shape failures in 14 days = systemic, not flaky.
2. Suppressing an error by catching+ignoring instead of fixing the source. The catch is a workaround; the workaround becomes permanent; the bug becomes invisible.
3. Skipping the "is this still relevant?" check on stale items. A 30-day-old TODO with no recent mention should be deleted or escalated, not left dangling.
4. Counting "scheduled task ran" as "scheduled task succeeded." Read the actual output before declaring health.
5. Auto-applying fixes beyond the 3-per-run cap because "they're all small." 10 small fixes compound into unreviewed drift.
6. Trusting a dossier's "task is broken" / "needs fix" claim without checking execution_log. Dossiers freeze a diagnosis on the date written; the underlying daemon code / whitelist / wrapper may have changed since. Per the Phase 0.5 verification matrix: ALWAYS pull the last-3-runs from execution_log before flagging a task as broken in the audit report. A real fiction-cascade caught this: a stale dossier → the audit re-recited it → /scope built on it → several unnecessary schedule updates shipped before pre-flight caught the wrong premise.

**Decisions.md reconciliation (mandatory before emitting a BLOCKER):** before promoting any item to BLOCKER status (or carrying it forward from a prior audit), grep `memory/Decisions.md` for the task ID, decision keyword, or matching context. If a `decision::` block exists with `status:: shipped` or `status:: decided` referencing the matched issue, DROP it from the BLOCKER list. Optionally emit it as INFO: "RESOLVED via Decisions.md 2026-MM-DD: <summary>". Reason: an audit once re-surfaced an already-decided option set as an open BLOCKER when part had shipped + part had been decided.

**Critic phantom-flag rate:** read the JSONL ledger at `memory/Infra/critic-phantom-flags.jsonl` for the last 24h. Tally entries by `failure_class` (max_turns / timeout / envelope_parse / exit_nonzero / cli_missing / unhandled). Surface the counts in the audit report under "## Critic phantom-flag rate (last 24h)". Per the ceiling-accept policy, do NOT propose architectural fixes on these — surfacing the rate IS the action. If the max_turns count > 5/day OR the timeout count > 3/day, append `**watch:** above baseline, may warrant a prompt-simplification round` as an INFO line (NOT a BLOCKER). Baseline expectation: 0-3 failures/day mixed across classes.

**Severity classification (mandatory):**
**MANDATORY falsification test per finding.** Before ANY item is emitted at ANY severity, it must carry:

```
falsification_test:: <the ONE command that would have killed this claim>
test_result:: <what that command actually returned>
```

Not evidence FOR the claim. The check that would have DISPROVED it. An item with no run test is a HYPOTHESIS: emit it as `severity: hypothesis` with the untested field blank and visible. Never promote an untested item to BLOCKER.

Applies equally to root-cause claims, which is where this bites hardest. "X is failing because Y" needs the test that would show Y is not the cause. Two specific traps: (a) a schedule diagnosed as a cron day-of-week decode error when two sibling crons on the same expression had fired that morning (test: diff against a working peer row), and (b) a NULL field read as a bug signature when it was NULL for all rows (test: count how many rows share it). Before theorising about any one broken item, diff it against a peer that works.

**Relationship to the Phase 0.5 "check before reciting" table above (do NOT merge them, they catch different bugs):**
- Phase 0.5 asks *"is this CARRIED-FORWARD item still true?"* It guards against re-reciting a stale finding that has since been resolved.
- This field asks *"is this NEW finding true at all?"* It guards against emitting a plausible claim that was never checked.
An item can pass Phase 0.5 cleanly and still be fabricated, because Phase 0.5 only runs on items that already exist. Both are required.

**Why:** in one incident, ten findings across this skill, graph-hygiene, the dream cycle and the agent's own diagnoses were falsified in a single day; nine reached the operator first, several as confident root causes. Every one died to a single command. Related existing guards this generalises: the Decisions.md reconciliation, a cardinality-sanity check, and a specificity-divergence check. Note the Phase 0.5 table's first row (`last_run IS NULL` -> check `execution_log`) DID hold in that case: execution_log returned 0 rows, so the missed-fire finding was genuine. What failed was the ROOT CAUSE attached to it, which had no test at all. Verified symptom plus untested cause is the exact gap this field closes.

- **BLOCKER**: surface to the operator, do not auto-fix: 3+ same-pattern failures (= rewrite candidate), security findings (credential leak, auth bypass), data integrity issues (CRM column drift, knowledge-graph orphans >5% of a namespace).
- **WARNING**: fix within the 3-per-run cap or note + queue: stale items, single failures, minor lint findings.
