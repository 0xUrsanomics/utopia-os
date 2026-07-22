---
name: meta-memory-review
description: Periodic self-optimization of the memory STRUCTURE (not its content). Review tier layout, dedupe, prune, and re-index the memory system.
trigger: /meta-memory-review, meta memory review, memory self-review, review memory structure
---

# Meta-Memory Review

**Purpose**: periodic self-optimization of the memory STRUCTURE (not its content). A strong-model pass reads recent session trajectories + recurring-failure signals and PROPOSES concrete edits to the memory rules / schema / tiers. Proposals are surfaced to the operator; **NEVER auto-applied** (memory-rule/schema/tier edits are CONFIRM-gated).

**Lift provenance**: AutoMem (arXiv 2607.01224) loop-1 = "a strong LLM reviews complete agent trajectories and iteratively revises the memory structure." Take loop-1 (structure-revision-by-review) and SKIP loop-2 (RL fine-tuning, impossible on a frozen model). The problem it targets: "a single memory mistake hides long before it surfaces" = recurring drift / over-hardening / noop-loop pains, which more text-lessons have failed to fix.

## Inputs (READ-ONLY)
1. `logs/session.jsonl` — last ~7 days of session events (categories, save extractions, failures, event mix).
2. `memory/Learnings.md` — tail + scan for RECURRENCE markers ("Nx", "N-th occurrence", "3rd/4th instance"). Repeated failure modes are the highest-signal targets.
3. `logs/errors.jsonl` + skill-failure tracker (`scripts/eval/skill_failure_tracker.py` output, or its store) — skills failing 3x/14d.
4. reality-feedback ledger (`reality_feedback.sqlite` if present) — verdicts + friction signals.
5. The CURRENT rules to propose AGAINST: `skills/save/SKILL.md` (extraction rules), `memory/MEMORY.md` (tier-1 index + bloat), frontmatter conventions across `memory/Context|Infra|Feedback`.

## Review lenses (produce proposals under each; SKIP a lens with no evidence)
- **A. Extraction gaps**: patterns that recurred in sessions but `save.md` did NOT capture, or mis-categorized. → propose a save.md rule edit.
- **B. Schema**: frontmatter/format inconsistencies or a missing field that would improve recall/dedup. → propose the schema change.
- **C. Tier misassignment**: tier-1 (always-loaded) entries that are stale / low-value (every line is reply-cost tax), or tier-2 items that should be promoted. → propose move/prune (cross-check MEMORY.md detox + reaper history).
- **D. Recurring-failure → STRUCTURAL guard (the AutoMem core)**: for each Learnings recurrence (e.g. over-hardening 4x, continue-turn-drop 3x), ask: is there a memory/skill STRUCTURE change (hook, gate, schema field, a load-order fix) that would actually guard it, versus appending an (N+1)th text lesson that already failed N times? Propose the structural fix.

## Output + GATE
- **If substantive proposals found**: write the full review to `outputs/raw/agent/YYYY-MM-DD-meta-memory-review.md` (frontmatter `status: raw`), then surface a CONCISE summary to the operator: the top 3-5 proposals, each = observed pattern + the specific edit + why. Ask which to apply.
- **NEVER auto-apply.** Only after the operator approves specific proposals are they edited in.
- **SILENT ON CLEAN**: if no substantive proposal (a quiet week), log ONE line to session.jsonl and do NOT ping the operator. Evidence-gated (per the "no evidence-on-clean-path" rule). No noise.

## Cadence
Weekly cron `meta-memory-review-weekly` (Sunday 05:00 local, strong model / high effort). Also manual via `/meta-memory-review`.
