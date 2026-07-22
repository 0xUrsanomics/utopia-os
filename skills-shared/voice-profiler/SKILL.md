---
name: voice-profiler
description: Extract voice patterns from session history and update Voice-Profile.md
trigger: voice profile, update voice, analyze my voice
allowed-tools: Read, Write, Edit
---

# Voice Profiler

## Tone & Voice

Diagnostic observation skill. output is structured pattern data, not advisory prose. **Hard rule**: profile based on actual samples only, never inferred from assumptions. Each dimension needs ≥3 supporting examples. **NEVER** fabricate dimensions to fill perceived gaps.

## Source & Pairs with

- `memory/Voice-Profile.md`. destination + prior-state baseline (read BEFORE re-profiling to track deltas)
- `memory/SOUL.md`. voice constitution; profile observations feed into SOUL refinement (rare)
- Telegram message history (logs/session.jsonl + plugin storage). primary writing sample source
- `outputs/` directories. user-written/edited content samples (NOT generated samples)
- Sister skills: `skills-shared/anti-ai-slop/SKILL.md` (different abstraction: voice vs slop), `skills/save/SKILL.md` (captures observations during sessions)
- A voice-profile-update script (one you provide). automation helper if scripted

## Example output (dimension entry)

```markdown
dimension:: sentence-length
pattern:: short-fragment dominant. the operator's messages avg 7-12 words, with ~30% under 5 words. Long sentences appear when explaining technical concepts (avg 20-25 words for those).
  examples:
    - "Yes." (1 word, dismissal)
    - "Go." (1 word, authorization)
    - "ya fix the broken tasks / the wallet payout, nudged already, still in production they said" (15 words, multi-clause directive. note slash-as-delimiter)
confidence:: high
```

## Conversation context (prior)

**Prior conversation**: skill triggers AFTER ~20 sessions of accumulated writing OR explicit "update voice" request. Reads the entire recent session log (or batch user provides), not just current turn. Sister to `skills/save/SKILL.md`. save captures specific observations during sessions, voice-profiler aggregates them into structured dimensions.

## Procedure (thinking step by step)

1. Read existing `memory/Voice-Profile.md` to baseline current dimensions + confidence levels
2. Gather samples: recent TG messages from user, content in outputs/ written/edited by user, any provided reference text
3. Analyze across dimensions (10 categories from existing list: sentence-length / transitions / articles / punctuation / vocab / tone-hedging / lang-mix / formatting / anti-patterns / structure)
4. Per dimension: ≥3 supporting examples or skip the dimension this pass
5. Compare with existing profile; flag NEW patterns + REINFORCE existing patterns + RETIRE patterns that no longer hold
6. Update `memory/Voice-Profile.md` with deltas
7. Log changes to `memory/Learnings.md` if a new dimension is added or an existing one is retired

## When to use
- User explicitly asks to update their voice profile
- Auto-triggered after ~20 sessions with sufficient writing samples
- After user provides a batch of their own writing for analysis

## Process
1. Gather writing samples:
   - Recent Telegram messages from user
   - Content in outputs/ written/edited by user
   - Any provided reference text
2. Analyze across dimensions:
   - Sentence length distribution
   - Transition patterns
   - Article usage (dropped or consistent)
   - Punctuation preferences
   - Vocabulary and abbreviations
   - Tone and hedging patterns
   - Language mix (primary/secondary language ratio)
   - Formatting preferences
   - Anti-patterns (what they never do)
   - Structure (lead with point or build up?)
3. Compare with existing memory/Voice-Profile.md
4. Update Voice-Profile.md with new patterns
5. Log changes to memory/Learnings.md

## Dimension format
```
dimension:: [dimension-name]
pattern:: [observed pattern with examples]
```

## Quality checks
- Profile based on actual samples, not assumptions
- Each dimension has at least 3 supporting examples
- Anti-patterns confirmed by absence across multiple samples
- Profile is concise (~150 tokens when loaded)

## Output
- Updated memory/Voice-Profile.md
- Summary of changes made
- Confidence level for each dimension (low/medium/high)
