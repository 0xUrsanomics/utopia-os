---
name: signal-scorer
description: Score and assess intel signals on 6 dimensions
trigger: signal, score signal, intel assessment, analyze signal
allowed-tools: Read, Write, Edit, Bash(cat:*)
---

# Signal Scorer

## Source & Pairs with

- `memory/Context/`. subject dossiers (read for prior context on the signal's topic/entity before scoring)
- `knowledge/`. published research files for ground-truth domain knowledge
- Knowledge-graph `Signal/` namespace. prior signal scores on the same topic
- Sister skills: `skills/intel-analyzer.md` (front-door analyzer that can invoke this skill for granular grading), plus any downstream pipeline that consumes scored signals for prioritization
- `outputs/raw/skill-activity/`. past scoring decisions for calibration

## Example output (signal score)

```markdown
---
title: Signal Score. Regulatory amendment leak
date: 2026-05-11
source: a trade publication
urgency: 2
---

| Dimension | Score (1-5) | Note |
|---|---|---|
| Relevance to us | 5 | Direct hit. affects every active deal |
| Credibility | 3 | Industry pub, no primary doc yet |
| Actionability | 4 | If true, a monitoring cron should pick up the filing in 7-10d |
| Time-decay | 5 | Window <14d for positioning |
| Competitive surface | 3 | Others will pick this up |
| Risk if true | 4 | Counterparties may pause their roadmap |
| **Composite** | **4.0** | High-urgency, primary source pending |
```

## When to use
User shares a signal. news, rumor, announcement, article, post, or forwarded message. and wants a scored assessment. Also triggered by the intel-analyzer and evening sync workflows for batch scoring.

## Process
1. Identify the signal (topic, source, content)
2. Check the `Signal/` namespace + `memory/Context/` for prior analysis on this topic
   - If a scored signal on the SAME event already exists → reply "dupe. already scored on {date}" and stop
   - If prior signals exist on the same TOPIC but different event → note them for context, continue
3. Read the relevant `knowledge/` file for the scoring framework reference
4. Score on 6 dimensions (1-5 each): integer scores only, no decimals
5. Calculate average (round to 1 decimal) and assign verdict
6. Write "So what?". concrete action, not vague commentary
7. Save to `outputs/raw/<agent>/` with filename: signal-{topic}-{YYYY-MM-DD}.md
8. If HIGH SIGNAL (4.0+): flag for immediate alert to the operator

## Scoring dimensions
| Dimension | What to evaluate |
|-----------|-----------------|
| Source Credibility | Who said it? Official? Verified? |
| Verifiability | Can it be confirmed via primary or official sources? |
| Novelty | Is this new info or rehashed? |
| Actionability | Can the operator act on this? |
| Relevance | Does this affect the operator's focus market? |
| Technical Depth | Surface take or deep analysis? |

## Verdict thresholds
- 4.0+ avg → HIGH SIGNAL
- 3.0-3.9 avg → MODERATE SIGNAL
- 2.0-2.9 avg → LOW SIGNAL
- <2.0 avg → NOISE

## Canonical Tag Taxonomy

Every Signal page gets 1-2 primary tags + up to 2 secondary tags from an approved set.
Keep the set small and curated so tags stay a navigable index, not free-text. Example set
(replace with your own domain's):

**Primary (pick 1-2):**
`#regulatory` `#market` `#product` `#funding` `#institutional` `#competitive` `#macro` `#ai` `#consumer` `#governance`

**Secondary (optional, max 2):**
`#partnership` `#hiring` `#pricing` `#security`

Do NOT invent new tags. If a signal doesn't fit, use the closest primary. All tags lowercase.

## Anti-slop
NEVER use in assessments: "game-changer", "remains to be seen", "only time will tell", "could potentially", "it's worth noting", "significant development", "exciting times", "paradigm shift". If you catch yourself hedging, delete and rewrite with a position.

## Voice
Write assessments like a blunt intel briefer. No hedging, no filler.
- State the verdict first, justify after
- One-line per dimension score. no paragraphs, no qualifiers
- If it's noise, say "noise, skip." If it's high signal, say what to do TODAY.
- "So what?" section = the operator reads this on their phone. Make it worth the scroll.

## Output format
```markdown
# Signal: {topic}
Date: {YYYY-MM-DD}
Source: {who/where}
Tags: {from taxonomy}

## Verdict: {HIGH SIGNAL | MODERATE | LOW | NOISE} ({avg}/5)

## Scores
| Dimension | Score | Note |
|-----------|-------|------|
| Source Credibility | X/5 | one-line reason |
| Verifiability | X/5 | one-line reason |
| Novelty | X/5 | one-line reason |
| Actionability | X/5 | one-line reason |
| Relevance | X/5 | one-line reason |
| Technical Depth | X/5 | one-line reason |

## So what?
{1-3 sentences: what this means for the operator. Concrete next action or "file and move on."}
```
