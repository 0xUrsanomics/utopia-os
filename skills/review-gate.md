---
name: review-gate
description: Knowledge quality gate. review raw outputs, approve/flag/merge before writing to the knowledge graph
trigger: review, approve, gate, check outputs, pending review
---

# Review Gate

Quality gate for the knowledge pipeline. Nothing enters the knowledge graph without passing review.

## Commands

| Command | Action |
|---------|--------|
| `/review` | Review all unreviewed items across all personas |
| `/review {persona}` | Review only that persona's raw outputs |
| `/review {file}` | Review a specific file |

## Flow

### 1. Scan
Read `outputs/raw/` for files with `status: raw` in frontmatter.

Also check for **stale-locked items**: any file with `status: reviewing` AND a `reviewing_started:` timestamp older than 24h. These are orphans from a previous /review session that crashed or was abandoned mid-batch. Auto-clear them: revert `status: reviewing` → `status: raw`, remove the `reviewing_started:` field, append a `review_notes:` line "stale lock cleared YYYY-MM-DDTHH:MM:SSZ".

Show a summary: count per persona, oldest item, total pending, stale-lock-recovered count.

**Idempotent resume guard**: if a file in `outputs/raw/` has `status: approved` or `status: flagged` (a partial move from a prior /review that didn't finish the relocation), skip silently. DO NOT re-process. Log a warning so the file can be manually moved to the right destination.

### 2. Review each item
For each raw file, evaluate:

**Checklist:**
- [ ] Factual accuracy. any claims that need verification?
- [ ] Consistency. contradicts existing graph content or other reviewed items?
- [ ] Completeness. enough substance to be useful, or just a fragment?
- [ ] Formatting. clean markdown, proper frontmatter?
- [ ] Actionability. is this reference material, a decision, or noise?
- [ ] Slop scan (auto, see 2a)

### 2a. Slop scan (auto, advisory)

Apply the `anti-ai-slop` skill's Mode 2 (explicit review) to the content body. NOT the frontmatter. Collect any rule violations (em dash abuse, inflated symbolism, promotional tone, hedging, AI verb crutches, etc.. full ruleset in `skills-shared/anti-ai-slop.md`).

This is **advisory**, not a hard gate. it does not auto-reject. Treat it as a "diff" for human-flavor quality:
- ≤2 minor violations → note `slop: clean` in the verdict
- 3+ violations or any major violation (rules #2, #3, #13, #20) → surface the specific passages + rule numbers in the verdict so the user can clean up before the graph write or choose to approve anyway

### 3. Verdict per item
Present to the user with a one-line summary + recommendation + slop advisory:

```
📄 agent/2026-04-06-signal.md
   Signal score for a protocol update
   → APPROVE (factual, complete, no conflicts)
   slop: clean
```

When slop is flagged:

```
📄 content/2026-04-17-thread-draft.md
   A thread draft on an upcoming event
   → APPROVE with cleanup (factual, complete)
   slop:
     - "underscores the importance of" (rule #2. inflated symbolism)
     - "leveraging partnerships to foster..." (rule #15. AI verb crutches, rule #13. corporate therapist)
     - 2 "however" + 1 "furthermore" in 300 words (rule #6. formulaic transitions)
```

Options:
- **approve** → copy to `outputs/reviewed/`, update frontmatter `status: reviewed`, add a `reviewed_at` timestamp
- **flag** → keep in raw/, add `status: flagged` + `review_notes` to frontmatter, explain the issue
- **merge** → combine with another file, move the result to reviewed/
- **discard** → move to `sandbox/archive/discarded/` (never delete)

### 3b. Operational-telemetry exemption

Internal operational telemetry items bypass the public-pipeline slop gate (em-dash, AI-slop wordlist, corporate-therapist tone). The slop scan still runs and counts are still recorded in the review verdict for visibility, but they do NOT block approval.

**Eligible types** (matched on the `type:` frontmatter or filename slug):
- `dream-reflection` (nightly dreaming output)
- `self-audit`, `system-audit` (cron-task audit reports)
- `audit` (any audit-typed output)
- `meeting-prep` (internal pre-meeting briefs, pre-call notes. even if the subject is a deal)
- `session-summary`, `session-log`
- `cron-output` (any harvester / scheduled-task generated content)

**Approval status**: `approved-internal` (NOT `reviewed`). Add `skip_graph_sync: true` to frontmatter. These items move to `outputs/reviewed/<persona>/` like normal but the graph writer skips them.

**Why**: the em-dash zero-tolerance + slop wordlist rules exist for content quality on PUBLIC-FACING pipeline output (the graph, social posts, decks, client docs, briefings). Internal telemetry is grep-able operational data, not human-rhetoric. punctuation hygiene there is purely cosmetic and burns review cycles for zero downstream value.

**What still gets gated** under public-pipeline rules:
- All `signal`, `analysis`, `draft`, `plan`, `summary`, `signal-score` types (default)
- All `coach` persona outputs (training summaries, interaction notes. these can flow to a public/social context)
- Any HTML/PDF doc going through a doc-typeset pipeline (§3a doc-typeset quality gate still applies)
- Any output explicitly marked `audience: external` or `audience: client`

**Why this matters for the adversarial stance**: the exemption is specific by type, not "soft pass when it looks tedious." The adversarial stance still applies WITHIN the public-pipeline scope. Don't widen the exemption silently.

Locked after a /review batch where 100% of cron-generated operational telemetry triggered em-dash blockers, masking the actual content-quality signal.

### 3a. Doc-typeset quality gate (for HTML/PDF client-facing docs)

If the raw item is an HTML doc meant to render to PDF (a one-pager, letter, long-doc, portfolio, resume, or any other doc using the `scripts/doc-typeset/templates/` structure), run the quality gate BEFORE approval:

1. **Placeholder check** (must pass): `python scripts/doc-typeset/build.py --check-placeholders path/to/doc.html` → must return "0 unfilled placeholders". If it fails, flag don't approve.
2. **Render to PDF** (once placeholders are clean): `python scripts/doc-typeset/build.py --render <template-name> --input path/to/doc.html --output outputs/drafts/path/to/doc.pdf`
3. **Verify page count + font embedding**: `python scripts/doc-typeset/build.py --verify <template-name>` → must PASS (no issues listed).
4. Only after all 3 pass: proceed with approve → move to reviewed/, add a reviewed_at stamp.

Scope: this gate applies to **client-facing** typeset docs only (quotations, proposals, resume submissions, etc.). Skip for internal memos, dream entries, audit reports. they don't flow through the doc-typeset pipeline.

Reason: a placeholder leak or an unembedded font in a client-facing doc is public-facing embarrassment. The gate catches both before they leave the drafts folder.

### 4. Graph write (on approve)
After approval, ask: "Write to the knowledge graph now, or stage for a batch write?"
- If write now: determine the target namespace from the content domain, write via your knowledge-graph MCP
- If stage: leave it in `outputs/reviewed/` for batch processing later
- Tag with `[[source/{persona}]]` for traceability

## Batch mode
`/review all approve`: auto-approve everything that passes the checklist (no manual confirm per item). Use for catching up on backlog. Still shows a summary after.

## Auto-save convention
When any persona produces substantive output during a session, save to:
```
outputs/raw/{persona}/YYYY-MM-DD-{slug}.md
```

Frontmatter template:
```yaml
---
title: {descriptive title}
persona: {active persona slug}
type: {analysis | draft | plan | summary | log | signal}
status: raw                    # one of: raw | reviewing | approved | approved-internal | flagged | discarded
created: {ISO 8601}
---
```

**Status state machine** (a langgraph interrupt+resume pattern, lifted from a langgraph audit):

```
raw ──→ reviewing ──→ approved (or approved-internal)
        │              ↓
        │              moved to outputs/reviewed/
        ├──→ flagged   (moved to outputs/raw/{persona}/, status:flagged stays)
        └──→ discarded (moved to sandbox/archive/discarded/)
```

When /review starts processing an item: set `status: reviewing` + `reviewing_started: {ISO}` BEFORE running the checklist. This is the durable checkpoint. If the session crashes or context exhausts mid-batch, the next /review run sees the partial state.

When /review completes the verdict for an item: transition to a terminal state (approved / approved-internal / flagged / discarded) + remove the `reviewing_started:` field + add `reviewed_at: {ISO}`.

**Stale-lock GC** (Step 1): items stuck in `status: reviewing` for > 24h indicate a crashed prior session. Auto-revert to raw on the next /review startup.

**Idempotent resume** (Step 1): items in raw/ with a terminal status (approved/flagged/discarded) shouldn't exist (a terminal state = the file was moved). If one is found, skip silently. don't re-process. Log a warning for manual cleanup.

## What counts as "substantive output"
- Research memos, signal scores, analysis
- Content drafts (threads, posts, emails)
- Plans, proposals, strategy docs
- Meeting prep / post-meeting notes
- Training plans, session summaries
- NOT: quick answers, status checks, casual chat, file reads

## Adversarial Stance (from a GSD audit)

**Starting hypothesis: every raw item is REJECTED until the checklist + slop scan + content quality prove otherwise.** Don't approve out of fatigue. Don't skip the slop scan because "this looks fine." A passed item is one that EARNED approval, not one that didn't actively fail.

**Common ways /review goes soft (catch yourself here):**
1. Approving a flagged item because "the slop is minor". if it has 3+ violations or any major rule (#2 #3 #13 #20), it deserves cleanup or reject, not a silent pass.
2. Treating "factual + complete" as sufficient when the item is actually corporate-therapist tone (rule #13) or hype-promotional (rule #20). Style is part of quality, not optional.
3. Auto-approving everything in `/review all approve` mode. Batch mode = catch up on backlog faster, NOT skip the checklist. The checklist still runs; only the per-item confirm prompt is suppressed.
4. Skipping cross-reference dedup. passing a new item that contradicts an already-reviewed-and-approved item from last week. Inconsistency in the brain is downstream noise.
5. Treating the doc-typeset gate (Step 3a) as optional for "internal" docs that might still leak. A payslip for a contractor = client-facing-via-that-contractor. If it could end up outside the org, it goes through the gate.
6. **Reciting an audit's live-infra BLOCKER without re-verifying it at /review time.** self-audit / system-audit reports are point-in-time snapshots. a BLOCKER about LIVE state (a broken/silent-failing task, config drift, a missing file, a non-whitelisted binary) may be RESOLVED by the time you /review it. the fix can land between the audit run (e.g. the 01:30 nightly) and now. Before relaying or acting on such a BLOCKER, RE-VERIFY against current live state: your scheduler list or the daemon's DB for task config, `execution_log` for the last-3-runs, the filesystem for files. Approve the audit telemetry as a faithful record, but mark the BLOCKER `stale` in the verdict. do NOT propagate it as actionable. A real catch: both nightly audits flagged two schedules as "will silently fail (non-whitelisted python)" when both were already on the whitelisted interpreter and had run clean. The audit-side reconciliation rules were point-in-time-correct; this catch is purely the temporal gap between audit-emit and /review-read.

**Severity classification (mandatory):**
- **BLOCKER**: flag, do not approve: a factual error, contradicts a locked decision, a doc-typeset gate fail (placeholder leak / unembedded font), 3+ slop violations, major slop rules (#2 inflated symbolism / #3 em-dash abuse / #13 corporate therapist / #20 hype) regardless of count.
- **WARNING**: approve-with-cleanup: 1-2 minor slop violations, formatting tweaks, missing inline citations on facts (the cite-your-facts rule).

## LLM/code split discipline (lifted from the VectifyAI/OpenKB compile pipeline)

OpenKB's wiki compilation deliberately splits work between the LLM and deterministic code:
- **LLM does**: synthesis (per-doc summary, concept create/update planning, cross-doc topic detection)
- **Code does**: file writes, cross-ref link insertion, frontmatter management, format normalization

**Why**: don't burn LLM tokens on what code can do deterministically. The LLM is for creative judgment, code is for mechanical operations. Each gets the right tool.

**Apply to the /review pipeline**:

| Step | LLM or code? |
|---|---|
| Factual accuracy check | LLM (judgment) |
| Slop scan | LLM (judgment) |
| Status field set | code (mechanical) |
| File move raw → reviewed | code (mechanical) |
| Frontmatter `reviewed_at` timestamp | code (mechanical) |
| Cross-ref discovery (which other reviewed items relate?) | LLM (synthesis) |
| Cross-ref link insertion (write the [[path]] syntax) | code (mechanical) |
| Verdict per item (approve/flag/discard) | LLM (judgment) |
| Stale-lock detection (>24h `reviewing` items) | code (mechanical) |
| Graph write decision (target namespace, tag) | LLM (judgment) |
| Graph write execution | code (mechanical, via MCP) |

**Anti-pattern**: asking the LLM to "now move the file from raw/ to reviewed/". that's what `mv` is for. Don't pay token cost for an `mv`.

**Anti-pattern reverse**: asking code to make a verdict call ("if a file has 3+ em-dashes, auto-flag"). that's a judgment call masquerading as a deterministic rule. The slop scan flags the violations; the verdict is LLM-judged with context (the operational-telemetry exemption etc).

When designing future pipeline steps, ask: is this judgment or mechanical? Route accordingly.
