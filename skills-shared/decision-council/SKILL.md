---
name: decision-council
pinned: true
description: >
  Forces 5 AI advisor personas to argue about a decision, anonymously peer-review each other, and synthesize a verdict with anti-false-consensus guardrails. Auto-detects high-stakes decisions from context. Trigger on: pricing, deal terms, partnerships, market entry, investments, exit strategies, go/no-go calls, trading decisions, DeFi/protocol entry, market entry/exit, futures positions, training program changes, competition prep, injury decisions, career moves, big purchases, financial planning, macro economic events (central-bank decisions, FX, inflation), geopolitical developments affecting markets, major AI/Web3/tech releases that change capability or competitive landscape, or any question where being wrong costs money, health, or reputation. Also trigger on "run council", "stress test", "what am I missing", "devil's advocate", "sanity check", or when the user leans toward an answer already. Do NOT trigger for brainstorming, writing, code, factual lookups, routine daily choices, or low-stakes ops.
trigger: decision council, multi-perspective, weigh options, decision analysis
---

# Decision Council

A structured adversarial analysis framework that forces cognitive diversity onto strategic decisions. Compensates for the model's sycophancy bias by running 5 constrained personas, anonymous peer review, and anti-false-consensus detection.

> **Looking for forward-failure analysis instead?** If the user wants "every way this could die before I commit" rather than "multi-perspective debate now", route to `skills-shared/premortem/SKILL.md`. Different psychological mechanism, different output. The two skills complement each other; do not run both unless explicitly asked.

## Why This Exists

An assistant model agrees with how you frame questions. Same question, different framing, opposite answers. That's fine for writing. Dangerous for decisions where being wrong costs money or reputation.

This skill forces structured disagreement. It can't eliminate same-model bias entirely (if all 5 personas share one model's weights), but it catches single-frame blindness, logic gaps, and assumption leaks.

## Limitations (Be Honest About These)

- If all 5 personas run on the same model instance, they share training and blind spots at the model level. The cross-provider routing below (Step 2a) mitigates this by routing some seats to a different provider for true cross-architecture diversity.
- The disagreement at same-provider seats is prompt-engineered, not architectural. Mixed-model routing makes 2-3 seats genuinely diverse.
- For triple-redundancy on extremely high-stakes calls, Step 6 still generates copy-paste prompts for a real-time-data model as a third independent check.
- This is a thinking aid, not an oracle. The operator still decides.

---

## Auto-Detection Logic

### TRIGGER (run the council)

Detect these patterns in the conversation:

**Trading and financial decisions:**
- Entry/exit sizing, stop loss, position management
- DeFi protocol entry: LP positions, yield strategy, range decisions
- NFT/collectible buys or sells above a threshold
- Airdrop participation with a meaningful cost (gas, locked capital, time)
- Equity entry/exit decisions
- Futures: leverage decisions, liquidation risk
- Any decision where being wrong costs real capital

**Macro and geopolitical events:**
- Central-bank rate decisions, FX moves, inflation data
- Regional trade developments affecting risk assets
- Political events: policy changes, election dynamics
- Geopolitical escalation affecting risk assets or supply chains
- Global recession signals, credit events, banking-sector stress

**Tech and innovation signals:**
- Major AI model releases (new frontier models, new capabilities)
- New Web3 primitives, L1/L2 launches, DeFi protocol upgrades
- New tooling or frameworks that could be adopted or competed against
- AI regulation developments
- Any tech release the operator should decide whether to adopt, invest in, or ignore

**Revenue decisions:**
- Pricing, deal terms, proposal scope
- Client contract negotiations
- Revenue model changes
- Exit strategies, token sales

**Strategic decisions:**
- Partnership evaluations (should we work with X?)
- Market entry / market exit
- Positioning and competitive strategy
- Go/no-go on projects or initiatives
- Team hires, restructuring
- Architecture decisions with high switching cost
- Marketing strategy with significant budget or reputation stakes

**Personal high-stakes decisions:**
- Training: program overhauls, peaking strategy, competition prep, switching methodologies
- Injury/health: training around injuries, when to push vs back off, surgery decisions
- Career: job offers, certification investments, skill pivots, freelance vs employment
- Finance: large purchases, investment allocations, exit timing, portfolio changes
- Life: relocation, major time commitments, relationship-impacting decisions

**Signal phrases from the user:**
- "Should I/we..." + any meaningful context
- "Is this a good idea" / "what am I missing"
- "I'm thinking about [X], wdyt?"
- The user presents a plan and seems to want validation
- The user is weighing options with meaningful tradeoffs
- "Pros and cons of..."
- Any framing where the user has already leaned toward an answer

**Explicit triggers:**
- "run council" / "council this" / "stress test"
- "sanity check" / "pressure test" / "devil's advocate"

### DO NOT TRIGGER

- Brainstorming or ideation sessions (the user wants volume, not vetting)
- Writing, drafting, editing tasks
- Code debugging, implementation questions
- Factual lookups, on-chain data queries
- Routine daily decisions: what to eat, when to sleep, daily scheduling
- Low-stakes ops: formatting, file management, log parsing
- When the user explicitly says "just answer" or "quick take"

### When Unsure

If the decision seems borderline, ask:

> "This looks like it could use a council run. Want me to stress-test it with 5 adversarial angles, or do you want a straight answer?"

---

## Execution Flow

### Step 1: Frame the Decision

Before running personas, extract and present:

| Element | What to capture |
|---|---|
| Decision statement | One sentence: what is being decided |
| Stakes | What's lost if wrong (money, time, health, reputation, opportunity) |
| Current lean | Which way the operator is already leaning |
| Key assumptions | What's being taken as given |
| Constraints | Time, budget, regulatory, technical limits |
| Macro/geo context | Any relevant market, political, or tech backdrop |
| Missing info | What would change the answer if known |

Present this frame to the operator. Confirm before proceeding. If the frame reveals they haven't thought through constraints, macro context, or assumptions, flag that first.

### Step 2: Run 5 Personas (In Sequence)

Each persona gets the SAME decision frame. Each operates under strict constraints. Each produces a short, focused analysis (150-250 words max per persona).

#### Step 2a: Cross-Provider Routing (optional, for true cross-architecture diversity)

To break same-model bias at the architecture layer rather than just the prompt layer, route some personas to a DIFFERENT model provider than the one running the orchestrator. A different training corpus produces genuinely different reasoning patterns. actual cognitive diversity, not one-model-pretending-to-disagree.

A good default split: route the CONTRARIAN + OUTSIDER seats to a second provider (finding-what-fails and fresh-eyes benefit most from a non-native perspective), and optionally the EXECUTOR seat to a third provider. Keep the FIRST PRINCIPLES + EXPANSIONIST seats on the orchestrator model, where reframing-depth and upside-pattern-recognition are strongest.

**Dispatch mechanics (generic):**
- Shell out to the second provider's CLI (or its API client) with the full persona prompt + the decision frame from Step 1, asking it to return ONLY the structured output block, no preamble. Use a timeout.
- **Fallback chain**: try the preferred model → on 429/timeout/model-not-found, try a cheaper model on the same provider → if still failing, fall back to the orchestrator model inline for that persona, with an explicit `[fallback: <provider> unavailable, inline]` flag prepended.
- **Scope guard (IMPORTANT)**: if you route a persona to an EXTERNAL provider, the decision frame may carry internal deal/strategy/counterparty data. ANONYMIZE it first: replace real counterparties / deal names / people / specific numbers with generic placeholders (Company A, chain Y, ~$X), preserving only the decision STRUCTURE. The external model needs the operational shape, not the proper nouns. If a frame can't be meaningfully anonymized without losing the decision, keep that persona on the orchestrator model for the run.
- **Attribution in output**: prepend `🤖 via <provider>` to externally-routed persona outputs so the source is clear in the final report. On fallback, switch to `🔄 <orchestrator> (<provider> unavailable)`.
- **Logging**: append every council run's routing decisions to `logs/council-routing.jsonl` (topic, per-persona provider used, whether the frame was anonymized, fallback reasons).

**When ALL external routes fall back to the orchestrator** (a full external-provider outage): proceed with the council on the orchestrator model only, but flag in the chairman synthesis that cross-provider validation is unavailable. Recommend re-running later, or use the Step 6 escalation (copy-paste prompts) for a manual cross-provider check.

---

#### Persona 1: CONTRARIAN  *(externally routed by default)*

**Mandate:** Find what will fail. Your job is to kill this idea.

**Rules:**
- Assume the plan WILL fail. Work backward from failure.
- Identify the single most likely failure mode
- Name the assumption most likely to be wrong
- Give a concrete scenario where this goes badly
- Do NOT offer fixes. Just expose the weakness.
- If relevant: what macro/geo/tech factor makes this worse than it looks?

**Output format:**
```
CONTRARIAN VERDICT: [KILL / WEAK / PROCEED WITH CAUTION]
Most likely failure mode: [one sentence]
Weakest assumption: [one sentence]
Failure scenario: [2-3 sentences]
What's being ignored: [one sentence]
```

---

#### Persona 2: FIRST PRINCIPLES

**Mandate:** Strip the question to its foundation. Reframe the problem.

**Rules:**
- Ignore the user's framing entirely
- Ask: what is the actual problem being solved?
- Is the user solving the right problem?
- What would you do if you started from zero with no prior commitments?
- Challenge the problem definition, not just the solution
- If relevant: does the macro/geopolitical/tech context reframe what the actual problem is?

**Output format:**
```
FIRST PRINCIPLES REFRAME:
Actual problem: [one sentence]
User is solving: [one sentence, may differ from actual problem]
If starting from zero: [2-3 sentences]
Reframed question: [the question that should be asked instead]
```

---

#### Persona 3: EXPANSIONIST

**Mandate:** Find the upside that was missed. What's the bigger play?

**Rules:**
- Accept the basic premise
- Look for adjacent opportunities the plan enables
- What could this become if it works better than expected?
- What second-order effects does the user not see?
- Find one opportunity that makes the risk worth taking even if the primary plan is marginal
- If relevant: what macro tailwind or tech wave makes this bigger than it looks?

**Output format:**
```
EXPANSIONIST UPSIDE:
Hidden opportunity: [one sentence]
Second-order effect: [one sentence]
Bigger play: [2-3 sentences]
Why this changes the risk calculus: [one sentence]
```

---

#### Persona 4: OUTSIDER  *(externally routed by default)*

**Mandate:** No context, fresh eyes. What does a smart stranger see?

**Rules:**
- Pretend you know nothing about the operator's business, history, or industry
- Read the decision frame as if seeing it for the first time
- What jumps out as weird, unclear, or unjustified?
- What would you ask if someone pitched this to you cold?
- Flag any jargon or insider logic that masks weak reasoning

**Output format:**
```
OUTSIDER VIEW:
First reaction: [one sentence]
This is unclear: [one sentence]
Question I'd ask: [one sentence]
What seems like insider bias: [one sentence]
Red flag for a stranger: [one sentence]
```

---

#### Persona 5: EXECUTOR

**Mandate:** If we do this, what happens Monday morning?

**Rules:**
- Accept the decision as already made
- What are the first 3 concrete actions?
- What's the first thing that will go wrong operationally?
- What resource or dependency is not being accounted for?
- Timeline reality check: is the timeline realistic?
- If relevant: what macro/tech event in the next 30 days could disrupt execution?

**Output format:**
```
EXECUTOR PLAN:
First 3 actions: [numbered list]
First operational problem: [one sentence]
Missing resource/dependency: [one sentence]
Timeline reality: [realistic / optimistic / fantasy]
What breaks first: [one sentence]
```

---

### Step 3: Anonymous Peer Review (chairman view)

After all 5 personas deliver, run the chairman-side review. Present all 5 outputs shuffled (label them A-E, not by persona name). Then answer:

| Review question | Answer |
|---|---|
| Strongest analysis | Which letter, and why in one sentence |
| Weakest analysis | Which letter, and why in one sentence |
| Biggest blind spot | What did ALL FIVE miss |
| Point of sharpest disagreement | Where do the personas contradict each other most |
| Suspicious agreement | Any point where 4+ agree (flag for anti-consensus check) |

### Step 3a: Cross-Persona Anonymous Ranking (llm-council pattern lift)

**Pattern source**: `karpathy/llm-council` (MIT). The novel innovation absorbed here: each persona, after delivering its own answer, ALSO ranks the OTHER 4 anonymous answers. Aggregating those rankings BEFORE the chairman synthesis surfaces a more honest signal than a single-actor peer review can produce. Anonymization at this stage is load-bearing. it kills self-preference bias, which is the single biggest failure mode of LLM peer review.

**Procedure:**

1. Re-show each persona the OTHER 4 outputs ONLY (not their own), labeled randomly as W / X / Y / Z. Each persona answers, in private:
   - Best analysis: which letter, one-sentence reason
   - Worst analysis: which letter, one-sentence reason
   - Most novel point made by any of the four: which letter + the point itself
   - Strongest argument they personally disagree with: which letter + their counter
2. Aggregate the 5 sets of rankings into a tally:
   - Best votes per letter (e.g. W:2, X:1, Y:0, Z:2)
   - Worst votes per letter
   - Novel-point catalog (5 entries, one from each persona)
   - Disagreement map (5 counter-arguments)
3. Surface to the chairman in Step 4:
   - **Consensus best**: the letter that received the most "best" votes from peers
   - **Consensus weak**: the letter that received the most "worst" votes
   - **Tied / split votes**: flag if rankings are dispersed (no clear winner or loser. signals genuine ambiguity, not a clear answer)
   - **Most cited novel point**: the insight peers found most original
   - **Sharpest unresolved disagreement**: the cross-persona counter-argument with no resolution

**Why this matters more than Step 3 alone**: Step 3 is one chairman reading all 5 (single-actor judgment). Step 3a is 5 reviewers each judging 4 anonymized peers (5x the cross-checks, with anonymization preventing the chairman's own bias from cascading). For high-stakes decisions, the cross-persona ranking has caught false-consensus that single-chairman review missed.

**Skip exception**: for fast-turnaround decisions where 5x extra LLM calls aren't worth the latency, run only Step 3 + skip 3a. Default for CONFIRM-gate decisions (deal pricing, partnership terms, market entry, irreversible actions): run both.

**Cost note**: Step 3a adds 5 extra LLM calls (1 per persona). At a cheap-model price this is negligible. At a top-tier model, allocate the budget upfront in /scope.

### Step 4: Chairman Synthesis

Read everything. Produce:

```
VERDICT: [GO / NO-GO / CONDITIONAL GO / NEED MORE INFO]

One-sentence summary: [the actual answer]

Key risk: [the single biggest risk, drawn from the strongest persona argument]

Conditional on: [if CONDITIONAL GO, what must be true for this to work]

Recommended next action: [one concrete thing to do this week]

Confidence level: [HIGH / MEDIUM / LOW]
Confidence note: [why this confidence level, 1-2 sentences]
```

**Model:** a top-tier model preferred. If running on a mid-tier model, flag it.

### Step 4.5: EV + Bayesian Sanity Check (MANDATORY)

The Chairman Synthesis is qualitative. This step gives the verdict numerical backup. Without it, the council reads as opinion-aggregation rather than structured analysis.

**Always include in council output. Skipping this step is a council miss.**

#### A. Outcome states + priors

Identify the 2-5 distinct outcome states the decision faces (e.g. for a deal: close / slip / no-go / counter-walk). Assign honest operator priors P(state) summing to 1.0. Anchor on:
- Recent calibration points from this stack (see footnote)
- Counterparty patterns
- Known constraints

Format as a table: state / P / one-sentence description.

#### B. Decision options × outcome × payoff matrix

List 3-5 distinct decision options (broader than the council's binary if applicable). For each option, project the payoff per outcome state across relevant dimensions:

- $ impact (12-month or whatever the natural horizon is)
- Runway impact (months, if cash-flow relevant)
- Network/identity tier (qualitative +++, ++, +, 0, −, −−, −−−)
- Optionality preserved or burned

Build the matrix. E[option] is the qualitative read across the row weighted by column priors. Identify which option dominates which outcome branch.

#### C. Bayesian: identify the prior-adjuster

What single piece of missing info would collapse the option matrix to a clear pick?

Often this is the "biggest blind spot all 5 missed" from peer review. Make it explicit:

| Data point value | Posterior P(verdict is right) | Reasoning |
|---|---|---|
| (low value) | (low confidence) | (one sentence) |
| (med value) | (mid confidence) | (one sentence) |
| (high value) | (high confidence) | (one sentence) |

This forces the user to identify the missing info AND quantifies how much it matters.

#### D. Calibration footnote

Include 3-5 recent prior calibration points from this stack with the prior estimate vs the actual outcome. Pattern detection (overconfident / underconfident / calibrated on which axis). Apply the pattern adjustment to the current council's priors and note the adjusted range.

This anchors confidence levels in a track record, not vibes.

#### E. Re-state the verdict with quant backing

After the matrix and Bayesian table, re-state the Chairman Verdict with explicit conditionality on the prior-adjuster data point. Example:

> CONDITIONAL GO on Option A, conditional on [missing data] ≥ [threshold]. If [missing data] < [threshold]: drop to Option B. If [missing data] < [lower threshold]: Option D becomes correct.

The confidence level should match between the qualitative synthesis (Step 4) and the quant backing (Step 4.5). If they diverge, flag it explicitly. that's a tell that one of them is wrong.

---

### Step 5: Anti-False-Consensus Check

**This is the guardrail against same-model bias.**

After synthesis, check:

| Check | Condition | Action |
|---|---|---|
| Unanimous agreement | All 5 personas lean the same direction | Trigger warning |
| Near-unanimous | 4 of 5 agree | Trigger soft warning |
| Healthy disagreement | 2-3 way split | No warning needed |

**If unanimous or near-unanimous:**

Display this warning:

> CONSENSUS WARNING: [4 or 5] of 5 personas reached the same conclusion. If personas share a single model instance, this agreement may reflect shared model bias rather than genuine robustness. Generating multi-model verification prompts below.

Then proceed to Step 6.

### Step 6: Multi-Model Escalation Prompts

Generate ready-to-copy prompts for a second and third model provider. These should:

1. Include the full decision frame from Step 1
2. Include the council's verdict and reasoning
3. Explicitly ask the other model to DISAGREE with the verdict and find what the personas all missed
4. Be formatted as a single copy-paste block

**Second-model prompt template:**

```
CONTEXT: I ran an adversarial decision council (5 personas: contrarian, first principles, expansionist, outsider, executor). They reached [VERDICT] with [X/5] agreement.

DECISION: [decision statement from Step 1]

STAKES: [stakes from Step 1]

MACRO/GEO/TECH CONTEXT: [any relevant backdrop from Step 1]

COUNCIL VERDICT: [full chairman synthesis from Step 4]

YOUR TASK: You are a second opinion. The personas may share the same training and correlated blind spots. Your job:
1. What did all 5 personas likely miss due to shared training bias?
2. Do you agree with the verdict? If not, why specifically?
3. What's the strongest counterargument that none of them made?
4. Rate the council's confidence level: justified or inflated?

Be direct. Don't validate their work. Find what's wrong.
```

**Real-time-data-model prompt template:**

Same structure as above, but add:

```
ADDITIONAL CONTEXT: Use real-time data if relevant. Check current market conditions, recent news, on-chain data, political developments, or social sentiment that a training-cutoff-limited model would miss. What has changed recently that makes this decision look different from what the council assumed?
```

---

## Output Formatting Rules

- No em dashes. Use commas, colons, or restructure.
- No "it's important to note" or similar editorializing.
- Match the operator's register: short, direct, casual-analytical.
- Tables over prose for structured comparisons.
- No sycophantic framing. The council disagrees with the operator by design.
- Persona outputs should feel like different people wrote them, not the same AI with different labels. Vary sentence length, vocabulary, and analytical style across personas.

---

## Log After Council

Save to your knowledge graph at `Decision-Council/YYYY-MM-DD-[topic]`:
```
- Decision: [topic]
- Verdict: [one sentence]
- Confidence: [HIGH/MEDIUM/LOW]
- Macro/geo/tech context at time of decision: [brief]
- Outcome: [fill in later]
- Key insight that proved right/wrong: [fill in later]
```

---

## Override Protocol

If the operator says "override", proceed and log the override. The council is advisory, not binding.

---

## Quick Reference

| Stage | What happens | Token cost |
|---|---|---|
| Frame | Extract decision, stakes, lean, assumptions, macro context | Low |
| 5 Personas | 150-250 words each | ~1,250 words |
| Peer Review | Shuffled evaluation | ~200 words |
| Chairman | Verdict + next action | ~150 words |
| **EV + Bayesian** | Outcome priors, option × outcome matrix, prior-adjuster, calibration | ~600 words |
| Consensus Check | Flag if 4-5 agree | ~50 words |
| Escalation | Second/third-model prompts if needed | ~400 words |
| **Total** | | **~2,500-3,100 words** |
