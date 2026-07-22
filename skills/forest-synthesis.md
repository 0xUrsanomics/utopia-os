---
name: forest-synthesis
description: Weekly cross-corpus synthesis across accumulated daily-forest digests. Cross-day pattern extraction invisible to single-day reading. Use weekly not daily.
trigger: weekly forest synthesis, cross-month read, forest of forests, synthesize daily forest, cross-corpus pattern
tools: [Read, Agent, Bash]
installed: 2026-05-13T10:03:16+07:00
provenance: auto-generated 2026-05-13 dream cycle from 2026-05-11 forest-of-forests synthesis task
depends_on: skills/daily-forest.md (LIVE since 2026-05-11)
---


# Forest Synthesis Skill

## When to Use
When asked for a "forest of forests" synthesis, cross-month pattern extraction, or strategic read across accumulated daily-forest digests. Ideally weekly (not daily. too noisy).

## Prerequisites
- Daily-forest digests at `outputs/daily-forest/YYYY-MM-DD-daily-forest.md` (30+ files)
- Skills system: `skills/daily-forest.md` must exist and be LIVE

## Procedure

### Step 1. Identify the corpus
```bash
ls outputs/daily-forest/*.md | wc -l  # count available files
ls outputs/daily-forest/*.md | head -5  # oldest
ls outputs/daily-forest/*.md | tail -8  # most recent
```

### Step 2. Strategic read via subagent

Spawn a subagent with:
- Read the 8 most recent digests IN FULL
- Read 5-7 selected digests from mid-corpus (pick around sentiment shifts or dates around key events)
- Section-header skim on remaining files
- Goal: identify cross-day patterns invisible to single-day reading

Subagent brief (paste verbatim, replacing N):
```
Read the daily-forest digests at outputs/daily-forest/. Corpus has ~N files.

Strategy: read last 8 in full, skim 5-7 from mid-corpus, section-header skim the rest.

Extract cross-day patterns in 8 categories:
1. Persistent Movers (appeared 3+ times, same direction)
2. Wave Movers (spiked then faded)
3. Multi-Week Silences (present then absent)
4. Tone Arcs (sentiment shift over time)
5. Long Cross-Stitches (two unrelated themes converging)
6. Late Bloomers (absent early, strong later)
7. Focus-Market-Specific (your market's authorities, regulators, corridors, local players)
8. Platform Ecosystem (releases + tool announcements for platforms you depend on)

End with: ONE structural shift paragraph. The biggest macro pattern the corpus reveals that single-day reading misses entirely.

Output to: outputs/raw/<agent>/YYYY-MM-DD-forest-of-forests-synthesis.md
```

### Step 3. Compress for chat delivery
Extract the ONE structural shift + 3 most actionable operator-specific findings. Deliver to chat as a compressed briefing.

### Step 4. Log
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","category":"forest-synthesis","event":"weekly_synthesis_complete","files_read":N,"output":"outputs/reviewed/<agent>/YYYY-MM-DD..."}' >> logs/session.jsonl
```

## Output format
- Full synthesis: `outputs/raw/<agent>/YYYY-MM-DD-forest-of-forests-synthesis.md`
- After operator review: move to `outputs/reviewed/<agent>/`
- Chat message: compressed 8-bullet version, actionable operator-specific first

## Cadence
Weekly (Sunday evening or Monday morning). Not daily. Cross-day pattern visibility requires 5+ digests minimum to be useful.

## Anti-patterns
- Do NOT skim all files equally. recency weighting matters (last 8 in full)
- Do NOT collapse to keyword counts. cross-day narrative shifts are the goal
- Do NOT skip the focus-market-specific section. that's the primary operator-actionable output
