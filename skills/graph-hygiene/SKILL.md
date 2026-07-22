---
name: graph-hygiene
description: Logseq knowledge-graph maintenance lint. scans 7 categories (stale pages, orphans, missing properties, dead links, missing compiled-truth/timeline structure, tag inconsistency, duplicate near-names), emits severity-tagged findings. Never auto-deletes. flags for /review only. Read by graph-hygiene-weekly cron.
trigger: graph hygiene, logseq lint, graph cleanup, orphan pages, dead links, stale pages, graph health
---

# Graph Hygiene. Logseq Knowledge Graph Maintenance

## Tone & Voice

Diagnostic operational telemetry. Output is structured findings + actionable severity tags, not advisory prose. Match the self-audit register: terse, evidence-grounded, severity classified. **Hard rule**: never auto-delete pages. flag for `/review` always, deletion is human-approved only.

## Invocation patterns

How to invoke:
- Scheduled cron: `graph-hygiene-weekly` fires weekly (e.g. Sat 08:00 local) → invokes this skill autonomously
- Manual: `/review graph`, "run graph hygiene", or "graph health check" in chat
- Trigger keywords: graph, hygiene, lint logseq, orphan check, stale pages

## Purpose
Automated lint and health check for the Logseq knowledge graph. Detects entropy before it compounds: stale pages, broken links, orphans, missing properties, inconsistent tags.

## When to Run
- Scheduled: weekly (e.g. Sunday 08:00 local)
- Manual: `/review graph` or when the operator asks about graph health

## Checks

### 1. Stale Pages. `severity: critical` (Pipeline/Client) / `warning` (Prospect)
Pages in active namespaces (Pipeline/, Client/, Prospect/) where `updated::` property is older than 30 days.
- **Action:** List with last-updated date. Flag as "needs review or archive."
- **Threshold:** Pipeline/Client >30d = critical; Prospect >60d = warning.

### 2. Orphan Pages. `severity: warning`
Pages with zero inbound links (no other page references them).
- **Exclude:** Journal/, Template/, Meta/, Archive/ (expected orphans)
- **Action:** List and suggest linking or archiving.

### 3. Missing Properties. `severity: critical`
Pages missing required properties for their namespace:
- Pipeline/: status, updated, contact
- Prospect/: status, updated, source
- Client/: status, updated, contract-start
- Network/Person/: role, org, last-contact
- Signal/: score, source, date
- **Action:** List with missing fields.

### 4. Dead Links. `severity: critical`
Internal links `[[Namespace/page-name]]` pointing to pages that don't exist.
- **Action:** List broken links with the page they appear on.

### 5. Missing Compiled Truth / Timeline Structure. `severity: warning`
Pages in namespaces that should follow the compiled truth + timeline pattern (see logseq-ops.md) but lack the `---` separator or have no "Compiled Truth" / "Timeline" headers.
- **Action:** List pages needing structural update.

### 6. Tag Inconsistency. `severity: info`
Pages using tags not in the standard tag set for their namespace. Surface novel tags for approval or correction.
- **Action:** List non-standard tags grouped by namespace.

### 7. Duplicate Near-Names. `severity: warning`
Pages with very similar slugs that might be duplicates (e.g., `acme-protocol` and `acme-protocl`).
- **Action:** List suspected duplicates for manual review.
- **Heuristic:** Levenshtein distance ≤2 OR shared 80%+ token overlap.

### 9. Citation Completeness. `severity: warning` (Iron Law port, 2026-04-28)
Audit pages in fact-bearing namespaces (Prospect/, Network/Person/, Network/Partner/, Signal/, Deal/) for inline `[Source: ...]` citations on factual claims. Heuristic: pages whose body has bullet-list facts but ZERO `[Source:` substrings = uncited content.
- **Action:** List pages missing citations entirely. Sample: paragraphs that read like compiled facts but lack source tags.
- **Don't auto-fix:** flag for the operator's review. Citation discipline requires knowing the actual source. can't be guessed.
- **Exempt:** Concept/, Template/, Meta/, Journal/ (concepts and journals don't need formal citations).

### 10. Tier Mismatch. `severity: warning` (Tiered Enrichment port, 2026-04-28)
Count inbound Logseq backlinks per Network/Person + Network/Partner page. Compare against current `tier::` property (if set) or estimate from page depth.
- **Tier 3 → 2 escalation:** 3+ inbound mentions OR has Meeting/ entry OR named in Deal/ page
- **Tier 2 → 1 escalation:** 8+ inbound mentions OR named in signed engagement OR explicit operator promotion
- **Action:** List tier-mismatch candidates with current count. Suggest enrich-up via a CRM-enrichment skill at next /review pass.
- **Reverse case** (Tier 1 with <2 mentions, stale): flag as "tier inflation". may have been over-classified or relationship cooled.

### 13. Skill Activity Tracker. `severity: info` (a curator-skill lift)
Surface skill usage stats from past 30 days. Identify dormant skills (prune candidates) + most-active skills (hot path). Read-only. no auto-prune.

- **Run via**:
  ```bash
  python3 scripts/pipeline/skill_activity.py --tg     # one-line digest
  python3 scripts/pipeline/skill_activity.py --summary  # full digest to stdout
  ```
- **Output**: `outputs/raw/skill-activity/YYYY-MM-DD.json` + chat summary line.
- **Pinned skills** (`pinned: true` frontmatter) are flagged in the report with 📌 and exempt from any future auto-prune. Pinned list documented in `skills/_index.md`.
- **Action**: if a non-pinned skill shows zero activity for 60+ days, surface as prune candidate at next /review pass. Manual decisions only. graph-hygiene reports, doesn't act.
- **Bake into the weekly cron**. emit one-line digest into the Telegram summary section.

### 8. Dossier Reaper. `severity: info` / `warning` (filesystem-projects v2)
Local lint over `memory/Context/` + `memory/Infra/` for dossiers that should consolidate or refresh.
- **Inline candidates** (info): single-project `projects:` tag → consider migrating content directly into the project file. Heuristic flag. large dossiers (>5K) may stay in Context/ for manageability.
- **Stale dossiers** (warning): `last_updated` (frontmatter) or mtime older than 30d → review for archive or refresh.
- **Untagged** (info-only): missing `projects:` field. not always a problem (some dossiers are genuinely cross-project or general-reference).
- **Run via**:
  ```bash
  python3 scripts/pipeline/dossier_hygiene.py
  python3 scripts/pipeline/dossier_hygiene.py --tg   # one-line digest
  ```
- Bake into the weekly hygiene cron. feed the `--tg` line into the chat summary section.

## Procedure

1. `logseq_graph_stats` → total counts (pages, blocks, refs). Cache for summary.
2. `logseq_list_namespace` for each: Pipeline, Client, Prospect, Network/Person, Signal.
3. For each page in active namespaces: `logseq_query_by_property` to fetch `updated::` and required properties in bulk. Avoid per-page reads.
4. `logseq_find_links` → build inbound-ref index. Pages with `inbound=0` outside excluded namespaces = orphans.
5. Cross-reference link targets against page list → dead links.
6. `logseq_read_page` ONLY for spot-checks on flagged items (structure/tag checks).
7. Compile report.

**Error handling:** if any MCP call fails, log the failure under `logs/errors.jsonl`, mark that check as `status: skipped` in the report, continue with remaining checks. Never abort the full audit on a single check failure.

## Output Format

Save report to `outputs/raw/<agent>/YYYY-MM-DD-graph-hygiene.md` with frontmatter:
```yaml
---
title: Graph Hygiene Report. YYYY-MM-DD
persona: agent
type: maintenance
status: raw
created: YYYY-MM-DDTHH:MM:SSZ
---
```

Report sections (bucket findings by severity tag from each check):
- **Summary:** total pages, blocks, refs (from stats); count per severity; checks run vs skipped
### MANDATORY: every finding ships with a falsification test (added 2026-07-20)

Before a finding is written into the report at ANY severity, it must carry two extra fields:

```
falsification_test:: <the ONE command that would have killed this claim>
test_result:: <what that command actually returned>
```

This is not evidence FOR the finding. It is the check that would have DISPROVED it. A finding without a run test is a HYPOTHESIS and must be labelled `severity: hypothesis`, never critical or warning.

**Test-selection guide by finding shape:**
| finding shape | the test |
|---|---|
| "key X is the canonical/standard one" | grep the CONSUMER (the skill or script that reads it) for which key it gates on. Page count is NOT evidence. |
| "automation A writes wrong value V" | read a page A actually harvested (`harvested-by::`) and check what V is there |
| "page P was never archived / P contradicts Q" | read P's PAGE-LEVEL header, not the property parser's merged view. Block properties inside dated history blocks are not current state. |
| "field F is missing on N records" | grep for the same data under a DIFFERENT key before scoping a backfill |
| "source S is dead/broken" | check whether S was decommissioned BY DESIGN before calling it a fault |
| "P is orphaned/unused" | stat mtime. Recent writes mean misrouted, not dead. |
| "two paths / two copies diverged" | compare inodes. Different-looking paths are often one directory. |

**Why this exists:** in one real case, ten findings from this skill, the self-audit, the dream cycle and the agent's own diagnoses were falsified in a single day, and nine reached the operator first. Every one died to a single command. One named the wrong canonical key and its recommended fix would have broken a downstream skill; another read a correctly-dated timeline block as live state and called an archived page unarchived. The defect is not effort: a plausible mechanism FEELS like a finding, so the distinction has to be mechanical and attached to the artifact.

- **Critical** (block-merge tier. fix before next sync): items tagged `severity: critical`: stale Pipeline/Client, dead links, missing required properties
- **Warning** (review suggested): items tagged `severity: warning`: orphans, stale Prospect, structure gaps, near-duplicates
- **Info** (FYI only): items tagged `severity: info`: tag variations, stats deltas vs prior week
- **Skipped:** any check with `status: skipped` and the underlying error

## Notification
After generating report, send summary to Telegram. Mobile-first, no preamble, fragments OK.
- Header: `graph audit YYYY-MM-DD. N critical / M warning`
- One-liner per critical: `[check] page-slug. reason`
- Warnings folded into a count unless ≤3 (then list)
- Info bucket: count only, no list
- Footer: report path
- Zero issues: `graph clean. report: <path>`: no emoji, no fluff

## What NOT To Do
- DO NOT auto-fix anything. This is a read-only audit.
- DO NOT modify pages. Only report findings.
- DO NOT read Regulation/ namespace content (protected).
- All fixes require the operator's approval via /review.

### 11. Doc Conflict Detection. `severity: warning` / `critical` (Doc-Conflict port, 2026-04-28)
Detect contradictions between memory/knowledge files using the doc-precedence ladder defined in `knowledge/workspace-routing.md`. Bucket each conflict:
- **auto-resolved** (info): newer same-tier supersedes older, or higher-tier wins over lower-tier. log + continue with winner.
- **competing-variants** (warning): two equal-precedence files contradict (e.g. two Context/ dossiers on same subject with conflicting facts). Surface for /review.
- **unresolved-blocker** (critical): locked Decisions.md entry contradicts another locked Decisions.md entry, or active Feedback rule. HARD BLOCK on derived content (quotations, deck regen, etc.) until reconciled.
- **Heuristic for detection:** for each entity-page in Logseq + Context/ dossier in memory/, scan for fact-shaped statements (numbers, dates, titles, payment terms) and cross-reference against any other doc mentioning the same entity. Flag contradictions.
- **Don't auto-fix:** read-only, surface to /review for the operator's reconciliation.

### 12. Wisdom-Layer Audit. `severity: warning` (port 2026-04-28 from arXiv 2604.11364 "Missing Knowledge Layer")
Audit `memory/Preferences.md` + `memory/Feedback/*.md` + `memory/Learnings.md` for `evidence::` field freshness on behavioral rules.
- **Rule with `evidence::` field** showing `last_applied` >30 days ago AND `applied_count` <2 → flag as **speculative** (was rule actually working, or just stored?). Surface for /review.
- **Rule with `outcome:: failed` or `outcome:: caused-regression`** → flag as **revision candidate**: the rule didn't earn its place.
- **Rule with `evidence::` missing entirely** → flag as **unaudited** (no Wisdom-layer tracking yet, was added pre-Apr-28 or by a session that skipped the field).
- **Action**: list with last-applied date + applied count + outcome history. Don't auto-prune. surface for the operator's manual revise/keep/delete call at /review pass.
- **Why this matters**: behavioral rules accumulate as Knowledge but never get evidence-gated. Speculative rules pollute the trust signal. old "always do X" rules that nobody actually applies look as authoritative as live working rules. Wisdom-layer audit forces revision based on actual evidence.
