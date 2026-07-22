---
name: autoresearch-system
description: Karpathy loop for the entire agent architecture. simulate end-to-end workflows, score, find the weakest link, fix, iterate.
trigger: optimize system, improve architecture, autoresearch system, system self-improvement
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
linter_ack: ["dynamic-exec: the inline python3 -c sqlite read against the scheduler DB is a documented read-only diagnostic, not fetched/dynamic code"]
---

# Autoresearch System (Architecture-Level Karpathy Loop)

## When to use
- A nightly scheduled self-improvement run
- Manual trigger: "optimize system", "autoresearch system"
- After major architecture changes to validate everything still works

## Test Scenarios

Simulate these end-to-end workflows against the current config:

### Scenario 1: Basic inbound message
- The user sends a text message via the chat channel
- Expected: the default persona responds, tone matches, response via the chat reply tool

### Scenario 2: Intent routing
- A message contains signal-related keywords ("just saw this alpha on a protocol")
- Expected: routes to `knowledge/research.md`, invokes the signal-scorer skill logic

### Scenario 3: Persona switch + briefing
- The user sends "/persona coach"
- Expected: switch to coach, load `memory/personas/coach.json`, respond with the coach greeting + context
- Note: only the active personas are switchable. Deprecated personas are archived. If the test input is a deleted persona, the expected behavior = inform the user the persona doesn't exist, stay in the default persona.

### Scenario 4: Driving mode activation
- The user sends a voice message saying "I'm driving"
- Expected: driving mode activates, the response includes a TTS voice note, uses the default voice

### Scenario 5: Knowledge pipeline flow
- A substantive output is produced (analysis, draft, plan) from an **interactive session**
- Expected: auto-saves to `outputs/raw/{persona}/`, correct frontmatter, status: raw
- **EXEMPTION (read the CLAUDE.md "Pipeline exemptions" clause before scoring):** Scheduled harvesters and scheduled sync tasks bypass raw/ and write direct to the knowledge graph BY DESIGN. Scheduled meta tasks (nightly dreaming, nightly system audit, weekly graph hygiene) DO save to raw/ as expected. Do NOT flag either class as a pipeline violation. Only interactive-session outputs are subject to the raw/-first rule. If scoring pipeline compliance, verify the CLAUDE.md exemption clause still exists and score against the ACTUAL rule (interactive outputs → raw/), not a hallucinated rule that includes scheduled tasks.

### Scenario 6: Temp mode isolation
- /temp activated, a message processed, /temp off
- Expected: no writes to memory/, logs/, outputs/, or the knowledge graph during temp mode

### Scenario 7: Slash command routing
- The user sends "/review"
- Expected: scans `outputs/raw/`, shows pending items, follows the /review gate (skill: `skills/review-gate.md`, bound via routing.json. there is NO `skills/review.md` and NO `knowledge/review-gate.md`. do not flag those as missing)

### Scenario 8: Error handling + logging
- A tool call fails (simulate)
- Expected: the error is logged to `logs/errors.jsonl` with context, the user is informed gracefully

### Scenario 9: Cross-persona boundary
- The coach persona is active, the user asks about a deal-pipeline question
- Expected: coach acknowledges, suggests switching to the default persona, asks permission

### Scenario 10: Security gate
- A task requires installing a new npm package
- Expected: check download count, age (>7 days), audit, ask if unsure

## Scoring Checklist

| Dimension | Weight | What to check |
|-----------|--------|---------------|
| Routing accuracy | 15% | Did the message route to the correct knowledge file / skill / persona? |
| Persona fidelity | 15% | Did the response match the active persona's tone, verbosity, domain? |
| Pipeline compliance | 15% | For INTERACTIVE sessions only: did substantive output save to raw/? Did the review gate enforce correctly? Scheduled tasks are exempt per the CLAUDE.md "Pipeline exemptions" clause. verify the clause exists, then do NOT score scheduled tasks under this dimension. If the exemption clause is missing from CLAUDE.md, flag THAT as the issue instead of scoring pipeline down. |
| Mode awareness | 10% | Did driving/temp/listen modes activate/deactivate correctly? |
| Security compliance | 10% | Were install/download security checks followed? |
| Logging completeness | 10% | Were session events and errors logged correctly? Scope: logging INFRASTRUCTURE only (errors.jsonl written, session.jsonl written, log rotation working). Scheduler-miss detection belongs to Phase 0 of self-audit.md, NOT this dimension. Do NOT penalize this dimension for stale/missed scheduled tasks. that is a scheduler_reliability signal, not a logging failure. |
| State persistence | 10% | Did state files (active_persona, driving_mode, temp_mode) update correctly? |
| Response quality | 10% | Was the response concise, mobile-friendly, no AI slop? |
| Error resilience | 5% | Did failures degrade gracefully with user notification? |

Score each dimension 0-100. Weighted average = the system score.

## Token Budget Rules (CRITICAL)
This skill runs on a scheduled session with limited tokens. Optimize aggressively:
- **Lazy-load files**: only read a file when a specific scenario needs it. Never bulk-read everything upfront.
- **Read sections, not files**: use offset/limit on large files (CLAUDE.md). Only read the section relevant to the current check.
- **One persona per scenario**: only read the persona file being tested, not all of them.
- **Skip unchanged**: if a file was read in a previous iteration and not modified, don't re-read it.
- **Terse output**: simulation descriptions = 3-5 lines max per scenario. No verbose walkthroughs.
- **Early exit**: if structural validation finds no issues and the score is 90%+, skip the iteration loop entirely.
- **Audit report**: bullet points only, no prose. Max 30 lines total.

## Skill Failure Tracking (always active, not just during audits)

When a skill invocation fails (tool call error, wrong output, user correction), log it:
```bash
python3 scripts/skill_failure_tracker.py log "<skill-name>" "<error summary>"
```

**Threshold:** 3 failures in 14 days for the same skill → auto-queued for rewrite.
**Ledger:** `memory/Infra/skill-failure-ledger.json`
**What counts as failure:** tool call errors during skill execution, the user explicitly saying the output is wrong, a skill producing empty/malformed output, routing to the wrong skill (log the skill that SHOULD have been invoked).
**What does NOT count:** the user changing their mind, unclear intent, one-off edge cases.

## Process

0. **Rewrite queue check** (before main audit):
   - Run `python3 scripts/skill_failure_tracker.py check`
   - For each pending rewrite: read the skill file, read the 3 most recent errors from the ledger, diagnose the pattern, apply ONE targeted fix to the skill file, mark done via `python3 scripts/skill_failure_tracker.py done "<skill-name>"`
   - This runs BEFORE the main audit loop so rewrites are included in the scoring pass
   - Run `python3 scripts/skill_failure_tracker.py prune` to clean stale entries

1. **Structural validation** (lightweight, no full file reads):
   - Use Glob to verify all expected files/dirs exist (outputs/raw/*, skills/, personas/, memory state files, log files)
   - Use Grep to spot-check that CLAUDE.md routing-table entries reference real files
   - Use `wc -l` on log files to check they're valid (non-empty, reasonable size)
   - **Scheduler shell-task check** (HEURISTIC, type-gated):
     - **HARD GATE**: ONLY apply this check to schedules where `task_type == "shell"`. SKIP entirely for `task_type == "claude_code"` and `task_type == "telegram"`. Read the `task_type` field from the schedule BEFORE inspecting any command/prompt content.
     - For confirmed `shell`-type schedules: verify the `task_config.command` field only uses whitelisted commands. **CRITICAL: the daemon applies `os.path.basename()` before whitelist-checking**. so `/usr/bin/python3` resolves to `python3` and IS whitelisted. When checking, always apply basename to the first token before comparing against the whitelist. Only flag as BROKEN CONFIG if the basename is not in the whitelist (e.g. a `.sh` script path, `pip`, `node`, `curl`).
     - For `claude_code`-type schedules: the `task_config.prompt` field is an agent prompt, NOT a shell command. It may legitimately reference any binary because the agent executes via the Bash tool which has its own permissions layer (not the daemon shell whitelist). **Flagging `cp` / `python3` / `curl` / etc inside a claude_code task's prompt is a FALSE POSITIVE** and creates unnecessary review-queue churn. DO NOT FLAG.
     - **Recurring false-positive lesson**: a backup task of `task_type: claude_code` whose prompt does `cp` via Bash kept getting flagged as broken-shell-config across multiple audits. It is NOT broken. The audit was reading the prompt content as if it were a shell command. The hard-gate above prevents this.
     - **DB source warning**: a stale scheduler-list tool can read from a legacy DB. For authoritative shell-task checks, query the daemon's live DB directly: `python3 -c "import sqlite3,os; conn=sqlite3.connect(os.path.expanduser('~/.agent-daemon/data/scheduler.db')); rows=conn.execute(\"SELECT name,task_type,task_config FROM schedules WHERE task_type='shell' AND enabled=1\").fetchall(); [print(r) for r in rows]; conn.close()"`. Always verify `task_type` before inspecting content.
     - Quick verification before flagging: the `task_type` field is present for every entry. If you can't see `task_type` for a schedule, do not flag. read the schedule first.
   - Only flag missing/broken items. Don't read file contents here.

2. **Simulate** each scenario:
   - Read ONLY the config sections relevant to that scenario (e.g. for the driving-mode test, read only the Driving Mode section of CLAUDE.md, not the whole file)
   - Describe the expected behavior in 3-5 lines
   - Score against the checklist dimensions (only the relevant ones per scenario)

3. **Score**: compute the weighted average across all scenarios

4. **Early exit check**: if the score >= 90%, save the report and exit. Don't iterate.

4.4. **Decisions.md reconciliation (mandatory, before diagnose)**: the audit must NOT re-emit a BLOCKER if the underlying decision has already shipped.
   - **For every candidate BLOCKER, carry-forward, or "options for the operator" entry** under consideration: grep `memory/Decisions.md` for the task ID, the decision keyword, or matching context.
   - **If a `decision::` block exists with `status:: shipped` (or `status:: decided`) referencing the matched context**: DROP the BLOCKER from the carry-forward list. Optionally include it as an INFO line in the report: "RESOLVED via Decisions.md 2026-MM-DD: <one-line decision summary>".
   - **If still uncertain**: leave the BLOCKER but append `[reconcile-needed: grep Decisions.md before re-emit]` so future audits know to re-check.
   - **Why this exists**: an audit once re-surfaced an already-decided option set as an open "your call" when part had shipped AND part had been decided. Carry-forward state was tracked independently from Decisions.md, so resolved options became zombie BLOCKERs.

4.5. **Phantom-flag check (do-nothing vote)**: pattern adapted from a public autoreason project. Before diagnosing the weakest scenario, prevent the "hallucinated flaw under critique pressure" failure mode.
   - **Load the phantom ledger**: read `memory/Infra/audit-phantom-flags.json` (create if missing). This ledger tracks dimensions flagged as weakest across multiple audits without measurable improvement.
   - **Check if the current weakest has a phantom entry**: if the weakest dimension matches a ledger entry AND the entry's `cleared` flag is false, SKIP this dimension automatically and move to the NEXT weakest for diagnosis. Log: "phantom-flag auto-skipped: {dimension} (ledger entry from {date})".
   - **Cross-reference prior audits**: read the last 2 audit reports from `outputs/reviewed/agent/*-system-audit.md` (fall back to `outputs/raw/agent/` if reviewed is missing). If the current weakest dimension was ALSO the weakest in BOTH prior audits AND the score hasn't moved, this is a phantom:
     - Append to the phantom ledger: `{dimension, first_flagged: <date>, consecutive_count: N, last_score: X, cleared: false, reason: "flagged N times consecutively with no score delta, do-nothing vote wins"}`
     - SKIP this dimension, diagnose the next weakest instead
     - Log: "phantom-flag created: {dimension} → skipped (3rd consecutive flag)"
   - **Human override**: if the operator has manually cleared a phantom ledger entry (set `cleared: true` with a reason), the dimension becomes eligible for diagnosis again.
   - **Why this matters**: do-nothing (the status quo) must be a first-class vote against proposed changes. If the auditor keeps flagging the same gap but can't improve the score, the gap is probably hallucinated. the exemption clause already exists, the rule already fires correctly, or the weakness is inside a non-negotiable constraint (e.g. "pipeline compliance 72%" where the remaining 28% is scheduled tasks legitimately exempt from raw/).

5. **Diagnose** (v2. trace-informed):
   - Read the simulation traces for the worst-scoring scenarios
   - Identify the specific failure mode (missing rule? conflicting instruction? wrong routing keyword?)
   - Check if prior iterations already tried a similar fix
   - Form a **specific, testable hypothesis** about the root cause
   - Log the diagnosis: failure mode, root cause, hypothesis, risk assessment

6. **Fix**: make ONE targeted change, tied to the diagnosis hypothesis:
   - If routing: update the CLAUDE.md routing table
   - If persona: update the specific persona skill file
   - If pipeline: update `skills/review-gate.md` or the CLAUDE.md pipeline section
   - If mode: update the mode rules in CLAUDE.md
   - If logging: update logging-ops.md
   - If security: tighten security rules (never weaken)

7. **Re-simulate** ONLY the affected scenarios (not all 10). Capture traces.

8. **Re-score + Decide**:
   - If improved: KEEP. Log which dimensions improved and confirm the hypothesis.
   - If regression: **Don't just revert.** Compare traces between before/after to diagnose WHY it regressed. Was it the intended change or a confound? Log the regression diagnosis. Then revert.

9. **Additive-only safety valve**: after 3 consecutive regressions from modifying existing rules, switch to additive-only mode:
   - Do NOT modify existing rules
   - ONLY append new rules, examples, or checks
   - Exit additive-only after 2 consecutive improvements

10. **Loop** until 90%+ average OR 5 iterations (token conservation) OR **the incumbent wins twice** (the same "do nothing" vote beats proposed changes on two consecutive iterations. this is the autoreason stopping criterion; halt with no further attempts on that dimension).

11. **Report**: save to `outputs/raw/agent/YYYY-MM-DD-system-audit.md`:
    ```
    # System Audit. {date}
    Score: X% → Y% | Iterations: N | Regressions: R
    Diagnoses:
    - {failure mode → root cause → hypothesis → result}
    Changes applied:
    - {change 1 (hypothesis: X, confirmed: Y/N)}
    - {change 2}
    Additive-only triggered: Y/N
    Weakest: {dimension} ({score}%)
    Manual review needed:
    - {item}
    ```

12. **Log** one line to `logs/session.jsonl`

## Constraints
- Maximum 5 iterations per run (token conservation)
- One change per iteration (atomic)
- Every change must be tied to a diagnosed hypothesis. no blind fixes
- After 3 consecutive regressions → additive-only mode (automatic)
- Never change core identity rules or security rules without flagging for manual review
- Never weaken security posture (only tighten)
- Never delete persona files or memory files
- If a fix requires the operator's decision, log it as a recommendation instead of auto-applying
- All changes must be logged with diagnosis + before/after in the audit report
- Regression = diagnose WHY before reverting. Log the counterfactual analysis.
- Total token-budget mindset: prefer Glob/Grep checks over full file reads. Every Read costs tokens. make it count.
- **Phantom-flag ledger persistence**: entries in `memory/Infra/audit-phantom-flags.json` persist across audit runs. Only manual clearance (the operator setting `cleared: true`) re-enables a dimension for diagnosis. This prevents the multi-consecutive-audit phantom cycle.
- **Do-nothing is a vote**: every iteration's proposed change must beat the status quo, not just be "different from" it. If the re-simulation shows status quo === proposed change, the status quo wins and no write happens.

## Nightly run behavior
When triggered by the scheduler:
- Run silently (no chat messages during execution)
- On completion, send ONE summary to chat:
  "🔧 nightly system audit: {score}% (+{delta} from last). {N} changes applied. check outputs/raw/agent/ for details."
- If the score drops below 80%, flag it as a warning in the chat message
- If a critical issue is found (broken routing, missing files), send an immediate alert

## What this does NOT do
- Does not test actual chat message sending (simulation only)
- Does not modify persona memories
- Does not touch the knowledge graph or CRM
- Does not install any packages
- Does not make changes that affect active user sessions (read-only during simulation, write only on the fix step)
