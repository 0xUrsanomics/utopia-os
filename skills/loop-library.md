---
name: loop-library
description: Catalog of repeatable agent-loop workflows (goal -> iterate w/ verification -> stopping condition -> output). Each loop is a reusable SOP for autonomous iterative work with quality gates. Run via /loop (self-paced or interval), a loop-until-done runner, a fan-out orchestrator, or manually.
trigger: /loop-library, loop library, run a loop, docs sweep, error sweep, feedback sweep, champion loop, devils advocate loop, quality streak, repo maintainer loop
source: adapted from a public "Loop Library" concept (31 loops). NOT verbatim copies. each loop below is re-authored against your own tools, paths, and conventions.
---

# Loop Library

A loop = an autonomous iterative workflow with a hard **stopping condition** and **evidence-backed output**. The shape is always:

> **GOAL** (one concrete outcome) → **PROCESS** (measurable steps, each verified) → **STOP** (explicit halt criteria, including a max-iterations / dry-rounds backstop) → **OUTPUT** (documented result + proof).

## How to run a loop here
- **`/loop` (self-paced)**: let the model iterate until the stop condition; good for "fix until N pass" / "find until dry." Omit the interval for self-pacing.
- **`/loop <interval>`**: recurring cadence (e.g. a maintainer loop every N hours).
- **loop-until-done runner**: the canonical "keep going autonomously until done" runner.
- **fan-out orchestrator**: when the loop fans out (loop-until-dry, loop-until-count across many items).
- **scheduler (cron)**: for the recurring/overnight ones.
Every loop MUST declare its stop + a backstop (max iterations or K consecutive empty rounds) so it can't run forever. Every loop ends by logging its output + evidence.

---

## 1. Docs sweep  (engineering)
- **Goal:** your repo docs (CLAUDE.md, skills/_index.md, knowledge/, memory/MEMORY.md pointers, READMEs) reflect the current implementation.
- **Process:** scan for drift (a skill/script/cron that exists but isn't documented, or documented-but-removed). For each drift: fix the doc, verify the referenced file/flag still exists (don't trust the memo, check the file).
- **Stop:** zero drift found on a full pass, OR 2 consecutive passes surface nothing new.
- **Output:** updated docs + a one-line `logs/session.jsonl` summary of what was synced.

## 2. Production error sweep  (engineering)
- **Goal:** clear actionable failures from `logs/errors.jsonl` + the skill-failure-tracker (3-fails-in-14-days flags).
- **Process:** read recent errors.jsonl + `skill_failure_tracker.py` flags. group by root cause (not symptom). for each real cause: trace it, fix, verify the fix is live (re-run the path), mark handled. skip benign/known (e.g. a routine credential refresh).
- **Stop:** no un-triaged actionable error remains, OR only known-benign left.
- **Output:** fixes + a triage note; if a fix is the same shape as a prior fix, escalate to root-cause per the root-cause-over-bandaid rule.

## 3. Recent-feedback sweep  (engineering / meta)  ⭐
- **Goal:** turn a single operator correction into a project-wide audit so the same class of mistake is purged everywhere, not just where they caught it.
- **Process:** take the latest correction (or a `memory/Feedback/` entry). derive the general failure class. grep/recall the whole stack (skills, cron prompts, knowledge, pipelines) for other instances of that class. fix each. harden into a gate/standdown if it's recurring.
- **Stop:** all instances of the class addressed; a gate added if it's a 2nd+ occurrence.
- **Output:** the fixes + (if warranted) a new Feedback entry or hook/gate. (this is the formalization of how style, framing, and date-drift corrections get hardened.)

## 4. Five-minute maintainer loop  (engineering, recurring)
- **Goal:** keep the stack tidy on a cadence without interrupting active work.
- **Process:** on interval, light-triage: stale `outputs/raw` past review, orphaned temp files, un-indexed memory, drifted state files, cron misfires. fix the cheap ones, queue the rest as tasks. NEVER touch anything mid-edit / interrupt a running job.
- **Stop:** the tick's checklist is clean (this loop is cadence-bound, not completion-bound).
- **Output:** a short tidy-log line; surface only anomalies.

## 5. Repository cleanup loop  (engineering)
- **Goal:** recover valuable un-committed/stale work and clear dead branches + temp cruft.
- **Process:** scan git for stale branches / uncommitted changes / `[gone]` branches; scan temp + outputs for abandoned artifacts. recover anything valuable (move to archive/reviewed), then remove the dead. CONFIRM before any delete (archive-first).
- **Stop:** no stale branch or orphaned artifact left un-handled.
- **Output:** recovered items + a cleanup summary. deletes only after operator OK.

## 6. Self-improving champion loop  (evaluation)  ⭐
- **Goal:** improve a prompt/skill ONLY when a change provably beats the current champion on a held-out benchmark (no vibes-based "improvements").
- **Process:** define the eval set + metric (e.g. recall-eval, critic catch-rate, content quality). propose a variant. run BOTH champion + challenger on the SAME holdout. promote the challenger only if it beats the champion by a real margin. else discard, keep the champion. version every attempt.
- **Stop:** no challenger beats the champion across N attempts (diminishing returns), or the target metric is hit.
- **Output:** the promoted version + the benchmark delta logged; losers archived with their scores. (pairs with an eval-driven prompt-optimization pilot.)

## 7. Quality-streak loop  (evaluation)
- **Goal:** ship only after a defined streak of realistic checks passes (no shipping on a single lucky pass).
- **Process:** assemble realistic test cases (historical inputs, edge cases). run. fix every failure at root cause. re-run the FULL set. require K consecutive clean full-runs before declaring done.
- **Stop:** K consecutive green full-runs (default K=2-3).
- **Output:** the passing artifact + the streak evidence (which cases, which runs). (this is the smoke-test discipline, formalized.)

## 8. Devil's-advocate loop  (decision / design)  ⭐
- **Goal:** pressure-test a plan/design/take until every real objection is resolved or explicitly accepted (not hand-waved).
- **Process:** generate the strongest objections from independent lenses (correctness, cost, compliance, second-order effects, "what kills this"). for each: resolve it, or document why it's an accepted risk. use the decision-council / Critic for cold-start adversarial passes. don't let an unresolved objection survive silently.
- **Stop:** every surfaced objection is resolved or accept-documented; a fresh adversarial pass finds nothing new.
- **Output:** the hardened plan + an objections ledger (resolved / accepted-with-reason). (extends decision-council + the Critic.)

---

## Deliberately NOT ported (already covered, or N/A to this stack)
- **Nightly changelog** -> already live (a weekly changelog cron + CHANGELOG.md).
- **External adversarial PR-review / autonomy builder-reviewer** -> covered by the Critic + subagent handoff.
- **Loop-harness verification / completion-contract** -> covered by cron draft-only + daemon-verify + the task-completion-standard (end-to-end test = "done").
- **100% test coverage / test-suite speed / sub-50ms page-load / fresh-clone / thumbnail / podcast / customer-deployment** -> N/A (this is a scripts+skills+memory stack, not a perf-critical web/app product).
- **SEO/GEO visibility** -> partial overlap with the seo-aeo audit; revisit if a web presence becomes a focus.

## Provenance
Concept + loop names adapted from a public Loop Library (31 loops). Re-authored against your tools; not copied. If a specific loop's exact upstream process is needed, fetch its detail page.
