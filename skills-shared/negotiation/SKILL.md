---
name: negotiation
description: >
  Tactical negotiation support with game theory, emotional regulation, EV analysis,
  and structured counter-offer frameworks. Activates on any deal negotiation, pricing
  discussion, contract term pushback, partnership terms, or when the user is in a
  live back-and-forth with a counterparty. Trigger phrases: "negotiate", "counter-offer",
  "he's pushing back", "what should I say", "how do I respond to this", "they want to
  change terms", "they won't pay", "run negotiation analysis", "BATNA", "walk away?",
  "am I getting screwed". Also auto-detect: the user forwarding counterparty messages and
  asking for help responding, the user sounding frustrated/angry about a deal conversation,
  pricing objection patterns.
trigger: negotiate, counter-offer, pushback, terms, pricing, deal, BATNA, walk away
---

# Negotiation Skill

Tactical negotiation support. Game theory, emotional regulation, structured analysis.
Not an academic framework. Built from live deal experience.

## Source & Pairs with

- Your deal-pipeline state file. the live state of every deal (read BEFORE any negotiation analysis to avoid stale-recall on price/scope)
- Your company-context file. your pricing tiers, service-line boundaries, and org context
- Your pushback-discipline feedback. never relay a kickback mid-deal; keep pricing floors
- Sister skills: a pipeline-ops skill (qualification), an outreach-drafter (drafts the email side), `skills-shared/sycophancy-guard/SKILL.md` (catches drift into compliance when pushback is correct)

## Example output (counter-offer analysis)

```markdown
## Situation
Counterparty: Example Corp HQ (their partnerships team)
Their offer: $15K one-time sponsor, no retainer
Our ask: $33K standard + $5K/mo retainer (3 month minimum)
BATNA: walk; another activation on the calendar is more leverage-rich

## Game-theory read
- They've shown an HQ-budget ceiling pattern (evidence: 2x retainer-refusal in 6 weeks)
- Their move isn't disrespect. it's a structural constraint from HQ
- Our walk-away cost: ~$15K one-time event revenue
- Their walk-away cost: lose a market-specific intel feed

## EV table
| option | EV | downside | upside |
|---|---|---|---|
| Accept $15K | +$15K, no retainer | sets precedent | quick close |
| Counter $25K + 1-mo retainer | +$30K + retainer signal | 60% accept | proves the pattern broken |
| Walk | $0 | lose event | preserves the pricing floor |

## Recommendation
Counter $25K + 1-mo retainer. EV-positive vs walk, preserves the pricing floor, surfaces a real constraint signal.
```

## When This Activates

- The user is in a live negotiation (forwarding counterparty messages, asking "what should I say")
- Pricing pushback from a client or partner
- Contract term disputes
- Any back-and-forth where money, scope, or commitments are being discussed
- The user asks for BATNA, EV analysis, or a walk-away assessment

## Phase 0: Emotional Check (ALWAYS FIRST)

Before drafting ANY response for the user to send:

**Scan the user's messages for heat signals:**
- Profanity directed at the counterparty
- "stupid", "idiot", "wtf", "pissed", "annoyed", "can't believe"
- ALL CAPS
- Rapid-fire short messages (frustration cadence)
- "just tell him [aggressive thing]"

**If heat detected:**

1. Acknowledge it: "you're pissed, I get it"
2. Do NOT draft the reply yet
3. Ask: "want to vent first or go straight to the tactical response?"
4. If they say tactical, draft a COOLED version. never match their heat in the outbound message.
5. Flag inline: "your draft would have been [X], I wrote [Y] instead because [reason]"

**Why:** angry messages in negotiations are almost always regretted. the skill's job is to be the 5-second delay between emotion and the send button. this is the single highest-value function.

## Phase 1: Situation Map

Before any analysis, extract these from context:

| Element | Question |
|---------|----------|
| **Parties** | Who is negotiating with whom? |
| **Stakes** | What's the total value on the table? |
| **BATNA (yours)** | What happens if you walk away? Best alternative? |
| **BATNA (theirs)** | What happens if THEY walk? What are their alternatives? |
| **ZOPA** | Zone of possible agreement. Your floor to their ceiling. |
| **Anchor** | Who set the first number? What was it? |
| **Concessions so far** | How many moves has each side made? Direction? |
| **Power balance** | Who needs this deal more? Who has more alternatives? |
| **Relationship value** | One-shot deal or repeated game? |
| **Cultural context** | Counterparty's communication style, business norms |
| **Timeline pressure** | Who has a deadline? |

Present as a compact table. Ask the user to confirm or correct.

## Phase 2: Pattern Detection

Scan the conversation for known negotiation tactics:

### Tactics the counterparty might be using

| Tactic | Signal | Counter |
|--------|--------|---------|
| **Nibbling** | asking for extras after price is agreed | "that's outside scope, happy to quote separately" |
| **Good cop/bad cop** | one person is friendly, another blocks | negotiate only with the decision-maker |
| **Flinching** | exaggerated shock at price ("that's way too much!") | silence. don't rush to fill the gap with a discount. |
| **Belief challenge** | "if you believed in your product you'd work on spec" | "belief isn't the question, operational costs are" |
| **Deadline pressure** | "we need to decide today" | verify if the deadline is real. usually it isn't. |
| **Higher authority** | "I need to check with my boss" | "bring them into the conversation so we align once" |
| **Splitting the difference** | "let's meet in the middle" | only agree if the middle is within your ZOPA |
| **Information fishing** | asking for your cost structure, margins, alternatives | share value delivered, never internal costs |
| **Salami slicing** | small concessions that add up to a large one | track cumulative concessions, flag when total exceeds threshold |
| **Walk-away bluff** | threatening to leave without intending to | call it calmly. "I understand. Door's open if you reconsider." |

### Tactics you should use

| Tactic | When | How |
|--------|------|-----|
| **Anchoring** | first offer | set the first number high. all subsequent negotiation gravitates toward the anchor. |
| **Silence** | after stating your price or position | don't fill the gap. let them respond first. |
| **Labeling** | counterparty is emotional | "it sounds like you're concerned about [X]" (validates without conceding) |
| **Calibrated questions** | counterparty makes an unreasonable demand | "how would you expect that to work on my side?" (makes them solve your problem) |
| **Loss framing** | they're hesitating | frame what they lose by not proceeding, not what they gain |
| **The flinch** | their first offer is low | visible surprise, then silence |
| **Bracketing** | you want $X | ask for $X + margin, expect to land at $X after their counter |
| **Deadline** | you want to force a decision | "offer valid until [date]." then honor it. |
| **Walk-away** | EV goes negative or they don't respect your floor | not a tactic when real. actually walk. |

## Phase 3: Concession Tracking

Log every price/term move by both sides in a table:

| # | Who | Move | From | To | Concession size | Cumulative |
|---|-----|------|------|----|-----------------|------------|
| 1 | You | initial anchor | - | $12,600/mo | - | - |
| 2 | Them | "too expensive" | - | $0 (wants free) | - | - |
| 3 | You | dropped to Tier 2 | $12,600 | $8,400 | $4,200 (33%) | $4,200 |
| 4 | You | trial month | $8,400 | $6,300 M1 | $2,100 (25%) | $6,300 |
| ... | | | | | | |

**Rules:**
- Never make more than 2 concessions without getting one back
- Each concession should be smaller than the last (a diminishing pattern signals the floor)
- If you've made 3+ moves and they've made 0, STOP. say: "I've moved three times. What can you move on?"
- Track cumulative concession as a % of the original ask. Over 40% cumulative = you've given too much

## Phase 4: EV + Bayesian Analysis

Run this whenever the user asks or at major decision points.

### Bayesian Table

Start with a prior P(deal closes on acceptable terms) based on:
- Lead source quality (warm intro = higher prior)
- Counterparty engagement level
- Industry norms for this deal type

Update with each new signal:

```
| Signal | Direction | Weight | P before | P after |
|--------|-----------|--------|----------|---------|
| [evidence] | +/- | weak/moderate/strong | X% | Y% |
```

### EV Table

For each possible outcome:

```
| Scenario | P(%) | Revenue | Time cost | Opp cost | Net EV |
|----------|------|---------|-----------|----------|--------|
| S1: deal on your terms | X | $ | hrs | $ | $ |
| S2: deal on compromise | X | $ | hrs | $ | $ |
| S3: they walk | X | $0 | sunk | freed | $ |
| S4: you walk | X | $0 | sunk | freed | $ |
| S5: you accept bad terms | X | $ | hrs | $ | $ |

Weighted EV = sum of (P * Net EV)
```

**Decision rule:** if the weighted EV of walking > the weighted EV of continuing to negotiate, recommend walk.

## Phase 5: Counter-Offer Drafting

When drafting a response for the user:

1. **Match the channel** (chat = short and direct, email = structured, call = talking points)
2. **Match the user's register** (if the user writes casual, draft casual. if the counterparty is formal, draft formal for their consumption.)
3. **One ask per message.** don't bundle multiple concessions or demands.
4. **Always end with a question or a clear next step.** never end with a statement that lets the conversation die.
5. **Include a deadline when appropriate.** "let me know by [date]" creates urgency.
6. **Offer exactly two options** when possible. binary choices are easier to decide on than open-ended asks.
7. **De-slop every draft.** run it through the anti-ai-slop filter. zero em dashes, zero filler.

### Response templates by situation

**They say "too expensive":**
> "[acknowledge]. I can adjust the structure. here's what the [lower tier] looks like: [specifics]. the scope stays the same / adjusts to [X]. which works better for your budget?"

**They want free work first:**
> "I get the logic. but [deliverable] requires [real costs]. who covers those during the trial? I need a minimum operational commitment to execute. [specific floor number]."

**They use "believe in yourself" / emotional framing:**
> "this isn't about belief. [evidence of work already done]. this is about operational cost. [specific costs]. how do you see that working for both sides?"

**They threaten to walk:**
> "I understand. I don't want to push terms that don't work for you. if things change, my door's open."
(do NOT chase. do NOT counter. silence is the response.)

**They go silent after your offer:**
> Wait 3-5 business days. then ONE follow-up: "hey [name], checking in on [topic]. offer stands until [deadline]. let me know either way."
(ONE follow-up max. after that, radio silence until they come to you.)

## Phase 6: Walk-Away Framework

**Auto-flag walk-away when ANY of these are true:**

1. Weighted EV of the deal < $0
2. You've made 3+ concessions and they've made 0
3. They're asking for free work with no guaranteed payment
4. The deal would set a precedent that damages future pricing
5. Your emotional state has been negative for 3+ exchanges about this deal
6. Opportunity cost: time spent here blocks a higher-EV deal
7. They've disrespected your time or expertise repeatedly

**Walk-away is not failure.** it's a strategic decision that preserves:
- Your pricing integrity for future deals
- Your time for higher-EV opportunities
- Your emotional health
- The possibility of re-engagement on better terms later (they often come back)

**Walk-away message format:**
Keep it short. grateful, firm, door open. never explain why you're walking (that gives them negotiation ammo). just state the outcome.

## Phase 7: Post-Negotiation Debrief

After any negotiation concludes (deal closed OR walked):

1. Log the concession table to Decisions.md
2. Grade each move (A-F)
3. Identify the weakest link
4. Extract a reusable lesson for Learnings.md
5. If it was a new tactic encountered, add it to the tactics table above
6. Update the deal page in your knowledge graph with the outcome

## Game Theory Quick Reference

| Concept | When to apply |
|---------|---------------|
| **Prisoner's Dilemma** | both sides benefit from cooperation but have an incentive to defect. build trust mechanisms (escrow, milestone payments). |
| **Chicken Game** | both sides threatening to walk, neither wants to. whoever blinks first loses leverage. only play chicken if you're genuinely willing to crash. |
| **Repeated Game** | you'll negotiate with this person again (or their network talks). cooperate more, burn bridges less. reputation matters. |
| **One-Shot Game** | you'll never deal with them again. optimize for this deal only. still don't burn bridges (small world). |
| **Asymmetric Information** | you know more about your costs/alternatives than they do (and vice versa). protect your information advantage. |
| **Commitment Device** | "offer valid until Friday" = a commitment device. only works if you honor it. break it once and all future deadlines are meaningless. |
| **Nash Equilibrium** | the point where neither side can improve by changing strategy alone. if you're there, stop negotiating and close. |

## Interaction with Other Skills

| Skill | How they connect |
|-------|-----------------|
| sycophancy-guard | prevents the agent from just agreeing with the user's position in a negotiation |
| decision-council | triggers for high-stakes deal decisions (go/no-go, accept/reject terms) |
| anti-ai-slop | all outbound negotiation drafts pass through de-slop |
| an outreach-drafter | for formal email-based negotiation messages |

## What This Skill Does NOT Do

- Does not negotiate on behalf of the user without approval (all outbound messages are CONFIRM)
- Does not guarantee outcomes. negotiation is probabilistic.
- Does not replace the user's judgment. it surfaces analysis, the user decides.
- Does not make the user confrontational for the sake of it. cooperation is usually higher EV than aggression.
