---
name: daily-forest
description: Daily 21:30 (local) skill. Synthesize today's Signal/ harvest into a forest-level read. movers / silences / tone shifts / cross-stitches / anomalies. Indexed back to vector_brain so the synthesis substrate compounds over time.
trigger: daily forest, forest read, signal synthesis, daily digest
---

# Daily Forest. Forest-Level Signal Synthesis

## Why this exists

Signal harvesting (chat channels + RSS + email = 30-80 signals/day) accumulates thousands of Signal/ pages in the knowledge graph. Without sustained reading, the substrate becomes a searchable headline pile. useful for keyword recall, useless for spotting **patterns only visible across time**: themes converging, narratives going quiet, an authority's language shifting tone, cross-domain cross-stitches.

The forest is what you miss when you only see trees. This skill is the daily forest-scan.

## When this fires

- **Scheduled**: daily 21:30 (local) cron (buffer after the evening knowledge-graph sync).
- **Manual**: `/daily-forest` or natural-language ("read me today's forest", "what's the synthesis from today's signals").

## Inputs (read in this order)

1. **Today's harvest**: `$AGENT_SCRATCH_DIR/today-signals.json`. structured summary, 24-30 signals typical.
2. **Yesterday's digest**: `outputs/raw/daily-forest/YYYY-MM-DD.md` (yesterday's local date). Skip if missing.
3. **Last-7-days digests**: `ls -t outputs/raw/daily-forest/*.md | head -7`. for the silence-detection pass (themes hot in last 7d but absent today).
4. **Full source articles for the interesting signals**: for the HIGH-scored signals (up to 8), FETCH AND READ THE ACTUAL ARTICLE via its `source_url` / `urls` (WebFetch), not just the harvester's headline/summary. No url (chat-only) = fall back to the knowledge-graph Signal/ page (`$AGENT_GRAPH_DIR/pages/Signal___<slug>.md`). See Step 3 for the procedure + the anti-headline rationale.

## Synthesis structure (5 sections, in order)

1. **Movers**. themes / entities / narratives mentioned by 3+ independent sources today. Use today-signals.json's tag/entity overlap. Be specific: "topic X language: 3 sources (source-a / source-b / source-c), all converging on the same framing".
2. **Silences**. themes that were hot in last 7d (from prior digests' Movers sections) but are conspicuously absent today. This is the highest-signal section because absence is invisible to keyword retrieval. Use grep over `outputs/raw/daily-forest/*.md` Movers sections.
3. **Tone shifts**. language/framing shifts from named entities. Compare today's authority/vendor/influencer messaging tone to last 7d baseline. E.g. "an authority's framing of topic X softened: 'monitoring' → 'pilot frameworks'". Specific quotes preferred when available.
4. **Cross-stitch**. patterns that bridge multiple distinct domains (e.g. product + regulatory + macro). E.g. "a model launch + developer-channel buzz on a new capability + a regulatory clarity milestone = converging substrate for a new use case". 1-2 cross-stitches max, only if the bridge is actually load-bearing.
5. **Anomalies**. single-source signals that read load-bearing despite low confirmation. Flag with explicit "single source" tag + name the source + why it matters. These are the leading-indicator candidates that the forest scan exists to surface.

## Procedure

### Step 1. Heartbeat ping (mandatory, first action)

Load `mcp__telegram__telegram_send_message` via ToolSearch with `select:mcp__telegram__telegram_send_message`. Send ONE message to personal chat (chat_id=`$OPERATOR_CHAT_ID`): `"daily-forest: started. <TODAY local date>"`. Startup ping so missed runs are visible by absence.

### Step 2. Read inputs (TOON-encoded for token efficiency)

Convert today-signals.json to TOON format first (~30% input token savings on the uniform-array signals section). today-signals.json stays JSON on disk. TOON is in-memory only via Read.

```bash
# Encode today-signals.json → /tmp/today-signals.toon (TOON for LLM input only)
python3 "$AGENT_ROOT/scripts/memory/lib_toon.py" \
  "$AGENT_SCRATCH_DIR/today-signals.json" \
  > /tmp/today-signals.toon

# Yesterday's digest path
YESTERDAY=$(TZ="${AGENT_TZ:-UTC}" date -d 'yesterday' +%Y-%m-%d)
ls "$AGENT_ROOT/outputs/raw/daily-forest/${YESTERDAY}.md" 2>/dev/null

# Last 7 digests (skip if dir doesn't exist yet on first run)
ls -t "$AGENT_ROOT"/outputs/raw/daily-forest/*.md 2>/dev/null | head -7
```

Then Read `/tmp/today-signals.toon` (not the JSON original). TOON tabular format is more compact for uniform array of signals. If TOON encoder errors for any reason, it falls back to JSON automatically. read either way works.

For first run (no prior digests), proceed with today-signals only and note in output: `cross_day_baseline: bootstrap (no prior digests)`.

### Step 3. Selective deep-reads (FETCH THE FULL ARTICLE, not the harvester summary)

Identify the interesting signals: all with `score_verdict == "HIGH"` (plus any that read notable on `content_angle == "Yes"`). For EACH, read the ACTUAL SOURCE ARTICLE, not just the harvester's headline/summary:
- Pull its `source_url` (or `urls[0]`) from today-signals.json. If present, `WebFetch` the article with a prompt like "extract the real substance: the specific claims, numbers, named entities, and any nuance the headline flattens or gets wrong." Synthesize from what the article actually says.
- If a signal has NO url (chat-only), fall back to Reading its knowledge-graph Signal/ page (`$AGENT_GRAPH_DIR/pages/Signal___<slug>.md`).
- On fetch failure (paywall / 403 / timeout), note it and fall back to the Signal/ page summary. Do not block.

BUDGET: up to 8 full-article fetches (prioritize by score, then thesis relevance; more than 8 HIGH on a big day means take the top 8). This is the anti-headline rule: synthesize from what the articles ACTUALLY say, because the harvester headlines are exactly where misframes hide.

### Step 4. Synthesize

Write to `outputs/raw/daily-forest/YYYY-MM-DD.md` with frontmatter:

```yaml
---
name: <YYYY-MM-DD daily-forest digest>
type: daily-forest
status: approved-internal
skip_logseq_sync: true
created: <ISO timestamp>
signals_read: <N from today-signals.json>
deep_reads: <count of Signal/ pages Read'd in Step 3>
prior_digests_referenced: <count from Step 2 step c>
---
```

Body: the 5 sections (Movers / Silences / Tone shifts / Cross-stitch / Anomalies). Be concise. bullets over prose, named entities over abstractions, specific quotes over paraphrase. Skip a section if genuinely empty (don't pad).

**Write-time falsifiability gate (before writing each bullet):** every claim must trace to a checkable referent in the substrate, or it gets cut. Drift dies here, not at /review.
- Movers bullet → name ≥2 source slugs from today-signals.json. Can't name 2? It's not a mover, drop to Anomalies or cut.
- Silences bullet → cite the prior-digest date where the theme last appeared (the grep hit from Step 2). No date = no silence.
- Tone-shift bullet → quote or paraphrase BOTH the old framing (with its 7d-baseline source) and today's. One-sided = cut.
- Cross-stitch bullet → name the 3+ distinct-domain signals it bridges. Fewer than 3 domains = it's a Mover, not a stitch.
- Anomaly bullet → name the single source + one sentence on why it's load-bearing despite no confirmation.
If a bullet can't pass its gate, cut it. A short honest digest beats a padded plausible one.

### Step 5. Index to vector_brain

After write, append the new digest to vector_brain index:

```bash
python3 "$AGENT_ROOT/scripts/memory/vector_brain.py" index-append --paths "$(ls -t outputs/raw/daily-forest/*.md | head -1)"
```

`index-append --paths` is the supported incremental path. Do NOT use `index --path`: that flag does not exist on the `index` subparser (it takes `--source`), so it ALWAYS errors, which is what makes "deferred to nightly" a permanent mask instead of a rare fallback. On a GENUINE non-zero exit (lock contention, OOM, transient error), skip and move on. a nightly reindex cron picks it up regardless. Don't retry, don't block the digest. Note `index: deferred to nightly` in the ping only if it actually failed.

### Step 6. TG ping

Send ONE message to personal chat (chat_id=`$OPERATOR_CHAT_ID`) via reply tool with this shape:

```
🌲 daily-forest <YYYY-MM-DD>

**movers** (<N>):
- <theme>: <X sources>. <one-line>
- <theme>: <X sources>. <one-line>
- <theme>: <X sources>. <one-line>

**silence** (most notable):
- <theme>: hot last <N>d, absent today

**cross-stitch**:
- <bridge across domains>

full digest: outputs/raw/daily-forest/<YYYY-MM-DD>.md
```

Render only the sections that have content: drop the `**silence**` block on first-7-runs or any day it's empty, drop `**cross-stitch**` when no load-bearing bridge passed its gate. Never ship an empty header. On a low-volume day (<5 signals) lead with `low-volume day (<N> signals)` so the thin digest reads as a real forest signal, not a failed run.

Cap message at 1500 chars. If full synthesis is longer, paste the headlines + cite the file.

### Step 7. Log

Append one line to `logs/session.jsonl`:
```json
{"ts":"<ISO>","level":"info","persona":"agent","category":"daily-forest","event":"digest written","signals_in":<N>,"movers":<count>,"silences":<count>,"cross_stitches":<count>,"anomalies":<count>,"deep_reads":<N>}
```

## Hard rules

- **No padding**: empty section = skipped section. Don't force a "Movers" if today only had 5 signals all on one topic.
- **No restating headlines**: this is synthesis, not summary. If a section reads like "today these things happened", rewrite.
- **Read the articles, not the headlines**: Step 3 FETCHES the full source article (WebFetch the url), it does NOT synthesize off the harvester's headline/summary. Headlines are where misframes hide. Cap 8 fetches to stay in the 25min budget; no-url signals fall back to the Signal/ page.
- **Named sources**: every claim cites the source channel or page. "3 sources mentioned X" is allowed only if you can name 2 of them in the next bullet.
- **Cross-day required for Silences**: skip Silences entirely on first-7-runs (insufficient baseline). After day 8, mandatory section.
- **Single-pass**: don't iterate. The first synthesis is the synthesis. Token budget keeps this cheap and sustainable.
- **Anti-slop**: NO em-dashes (zero tolerance), NO preamble. The full forbidden wordlist is the canonical one in `skills-shared/anti-ai-slop.md` (leverage / navigate / delve / holistic / seamless / comprehensive / robust / crucial / pivotal / underscores / foster / elevate / etc). Don't maintain a partial copy here. apply that list, plus match the operator's register (see your SOUL + Voice-Profile memory files).
- **Chat anchor**: the daily ping is the only signal the operator sees by default. Make it readable in 15 seconds.

## Failure modes

- **today-signals.json missing or stale** (date != today): send TG `"⚠️ daily-forest skipped: today-signals.json missing or stale (date: <X>). evening-logseq-sync may have failed."` and exit.
- **<5 signals in scratch**: still synthesize (might be a quiet day, which is itself a forest signal). Note "low-volume day" in TG.
- **vector_brain index fails**: write digest anyway, flag in TG. Nightly reindex catches it.

## /review integration

Daily-forest digests go to `outputs/raw/daily-forest/` (raw tier). `/review` picks them up like any other raw output. Approved → `outputs/reviewed/daily-forest/` + indexed permanently. Discarded → `sandbox/archive/discarded/`.

Most digests will probably approve cleanly. The /review pass is the quality gate against synthesis drift (LLM hallucinating themes that aren't actually in the substrate).

## Future iterations (queued, NOT v1)

- **Feed extension**: extend the signal harvester to include more channels/domains as the substrate grows. v1 works with the current substrate.
- **Weekly forest-of-forests**: every Sunday, synthesize last 7 daily-forests into a higher-level pattern read. Different cadence, different LLM budget.
- **Auto-tagging of recurring themes**: track which Movers themes recur N times → promote to "watch list" entity. Manual stub for now.

## Why this exists (long-form rationale)

Operator feedback: "logging without reading = grasping by headlines, missing forest for trees." A Signal/ corpus of thousands of pages, virtually all written by harvester crons, with model retrieval limited to keyword `recall`. Keyword retrieval surfaces what you're already looking for. invisible to the pattern-recognition layer that requires sustained attention across the substrate.

This skill is that sustained attention, ritualized.
