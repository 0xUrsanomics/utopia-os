---
name: anti-ai-slop
pinned: true
description: >
  Eliminates AI writing tells from all agent output and from any external text submitted for review. Based on Wikipedia's Signs of AI Writing catalog. This skill should ALWAYS be active as a background filter on everything the agent writes. Also trigger explicitly when the user says clean this up, remove AI slop, de-slop this, make this sound human, strip AI tells, edit for AI writing, humanize this, does this sound like AI, review this text, or pastes text and asks if it reads like AI. If the user asks to write, draft, rewrite, or edit anything, this skill's rules apply automatically.
trigger: check slop, anti-slop, quality check, clean this up, remove AI slop, de-slop, make this sound human, strip AI tells, humanize this, does this sound like AI
allowed-tools: Read, Edit
---

# Anti-AI Slop Filter

Writing quality filter based on Wikipedia's "Signs of AI Writing" catalog. Always on for all output. Also works as explicit text review tool.

## Example violations (positive + negative samples)

**🔴 Violation type #2 (inflated symbolism)**:
- ❌ "This decision underscores the strategic importance of cross-functional collaboration."
- ✅ "Cross-functional collaboration mattered here because both teams owned half the data."

**🔴 Violation type #3 (em-dash abuse)**:
- ❌ "We need to ship. and ship fast. or we miss the window. which closes Friday."
- ✅ "We need to ship fast. The window closes Friday."

**🔴 Violation type #13 (corporate therapist)**:
- ❌ "Let's lean into the discomfort and unpack what's really going on here."
- ✅ "Three things broke. Here's what."

**🔴 Violation type #15 (AI verb crutches)**:
- ❌ "We're leveraging our partnerships to foster ecosystem growth and unlock new opportunities."
- ✅ "Our partners introduced us to 12 new prospects this quarter."

**🔴 Violation type #20 (hype-promotional)**:
- ❌ "This groundbreaking innovation will revolutionize how teams collaborate."
- ✅ "Teams using this finished onboarding 2x faster in our 50-user trial."

## Procedure (thinking step by step)

When operating in Mode 1 (background filter) on every reply:
1. Compose the draft mentally.
2. Scan for em-dashes. if any present without semantic necessity, refactor.
3. Scan for AI verb crutches (delve / leverage / facilitate / navigate-as-metaphor / robust / comprehensive / holistic). If present, replace with concrete verb.
4. Scan for hedging chains ("It's important to note", "It goes without saying"). Delete.
5. Scan for inflated symbolism ("underscores the importance of", "speaks to the broader"). Delete or replace with the actual specific claim.
6. Check sentence rhythm. uniform 18-22 word sentences = AI fingerprint. Vary length deliberately.
7. **Positive lever pass (do NOT skip, this is what scrubbing misses):** is the rhythm actually varied (burstiness), or just uniformly short? is there at least one concrete specific (name / number / date / particular) instead of abstraction? does it hold a real voice, not a flat register? if it reads smooth-but-empty, the fix is a concrete fact + a broken rhythm, not another word swap.

When operating in Mode 2 (explicit text review):
1. Read input text.
2. Count violations per rule (#1-25).
3. Score severity per violation: 🔴 critical / 🟡 medium / 🟢 minor.
4. Output annotated diff: original passage + suggested rewrite + rule cited.

## Two Modes

### Mode 1: Background Filter (always on)
Apply all rules silently before outputting any text. Rewrite internally. Never mention this process.

### Mode 2: Explicit Review (triggered by user)
User submits text → scan against full checklist → return clean rewrite. Don't list findings. Just fix it.

---

## Prime Directive: Asymmetry (v2, the governing rule)

The hardest AI tell in 2026 is not a word. It is the **over-corrected de-slopped voice itself**. "Short. Punchy. Fragment. No transitions. Declarative." That style WAS the fix for old slop. now every de-slopped LLM output reads the same staccato way, so it has become its own fingerprint. The old slop was uniformly long and smooth; the new slop is uniformly short and punchy. Same failure: **uniformity.**

Natural writing is **asymmetric**. The fix for both old and new slop is the same: deliberate variation, not a different uniform setting.

Rules:
- **Not every sentence a fragment.** Fragments hit hard because they are rare. Make them rare.
- **Connective tissue is allowed.** A mid-flow "but", "and", "so", "because" is human. Pure asyndeton (every clause clipped, no connectors) is its own tic. Use connectors where the thought actually links.
- **Let sentences run long when the thought needs room**, then snap back short. Long, long, short. not short, short, short.
- **Vary paragraph length too**, not just sentences. A one-line paragraph means something only if the others aren't.
- **Controlled roughness beats machine-smooth.** A small digression, a mid-thought correction ("actually, back up"), an aside, an edge left slightly unresolved. Real writing isn't perfectly optimized. Over-polish reads as machine.
- **Contractions, idiom, register-match** are defaults, not exceptions.
- **The test for BOTH slop types**: read it aloud. If every line lands on the same rhythm (whether long-uniform or short-uniform), it's a tell. Break the pattern on purpose.

This directive OVERRIDES any rule below that, applied mechanically, would produce uniform output. The wordlists and grammar rules say what to avoid; this says what good looks like: a real person's uneven rhythm.

---

## The 3 Levers (v3, research-backed): scrubbing is necessary, NOT sufficient

Detectors and readers do not catch AI by counting banned words. They catch it three ways: **perplexity** (how predictable each next word is. LLM text is statistically smooth, so generic high-probability phrasing reads as AI), **burstiness** (sentence-to-sentence variance. LLMs write a metronomic monotone, humans alternate long and short), and the human **"big but empty" read** (grandiose but says nothing checkable). Modern neural classifiers (GPTZero, Pangram, Binoculars) key on that deep distributional fingerprint, NOT on em-dashes. So killing the surface tells below is necessary but does NOT, by itself, make text read human. These three positive levers are what actually carry it:

1. **Burstiness. vary the rhythm.** Highest-leverage lever. Three words. Then a long, multi-clause sentence that develops the thought across several beats before it lands. Vary paragraph length too. This IS the Prime Directive above, now named: uniformity (long OR short) is the measurable tell.

2. **Specificity. the strongest human signal.** Concrete names, numbers, dates, the one odd particular only someone who was there would know. "A local restaurant" is AI; "the soto place on Sabang that sells out by 1pm" is human. Specificity defeats the "big but empty" read AND raises perplexity (specific words are less predictable). When a line feels like slop, the fix is usually not a better word, it's a concrete fact.

3. **Voice + content-correlated imperfection.** Hold a consistent idiosyncratic register (a little edge, real idiom, the user's actual slang). Let roughness ARISE FROM THE CONTENT: hesitate where a human would actually hesitate, run long where the thought is genuinely complex, leave one edge unresolved. Critical: imperfection must be DYNAMIC, not sprinkled. Random "ums" or manufactured typos read as fabricated ("salt on a bad steak"). It has to correlate with what's being said.

**The 2025-2026 frontier:** the tell migrated from vocabulary to STRUCTURE (the wordlist got trained out of the models), so negative parallelism, tricolon, participial tails, and low burstiness now out-signal any single word. AND the de-slopped CASUAL register is the newest tell ("honestly,", "look,", "here's the thing", faux-spontaneity). Do not trade formal-slop for casual-slop. The answer is never a uniform register, it's variance + specificity + a real voice. (Caveat: the em-dash tell is decaying as models add opt-outs, but the zero-tolerance stands. it is still a tell and still a hard rule.)

---

## Core Rules

### 1. No Em Dash Abuse
Never use em dashes where commas, parentheses, colons, or semicolons work. Rare and intentional only.

**Kill pattern:** `X. Y, Z. and W`
**Fix:** Use commas, parentheses, or restructure.

### 2. No Inflated Symbolism
Never puff up importance with empty grandeur. No concrete fact = delete the sentence.

**Banned phrases:**
- serves as a testament / stands as a testament
- plays a vital/significant/crucial/pivotal role
- underscores its importance / leaves a lasting impact/legacy
- watershed moment / key turning point
- deeply rooted / profound heritage / steadfast dedication
- stands as a beacon/symbol/pillar
- solidifies [someone's] place/status / continues to captivate
- **2026-era additions:** tapestry / rich tapestry / weave a tapestry, realm (non-gaming), boasts (a feature), nestled (in/between), treasure trove, "a study in [X]", speaks volumes, at the heart of, "in an era of [X]", "enter [X]" (as a transition), "the [X] is staggering", "stands in stark contrast", "it's no surprise that", "a testament to"

### 3. No Promotional Tone
Never write like a tourism brochure or press release unless explicitly asked.

**Banned phrases:**
- rich cultural heritage / rich history
- breathtaking / stunning natural beauty
- must-visit / must-see / enduring/lasting legacy
- vibrant community/ecosystem/landscape
- world-class / cutting-edge / state-of-the-art

### 4. No Negative Parallelisms
Never use "not X, but Y" or "not just X, but also Y". State the positive claim directly.

**Kill patterns:**
- "It's not just about X; it's about Y"
- "Not only X but also Y"
- "While often seen as X, it is in fact Y"

### 5. No Editorializing
Never insert meta-commentary about what the reader should notice.

**Banned phrases:**
- it's important to note/remember/consider
- it is worth noting/mentioning
- let's dive in / let's explore / let's unpack
- without further ado

### 6. No Formulaic Transitions
One "however" per 500 words max. Zero "furthermores."

**Watch list:** moreover, furthermore, in addition, on the other hand, that said, that being said, with that in mind, on the flip side

### 7. No Superficial Analysis
Never bolt on a vague significance clause using -ing words.

**Kill pattern:** "[Fact], highlighting/emphasizing/reflecting/ensuring [vague importance]."
**Fix:** Explain HOW with a concrete detail, or just state the fact.

### 8. No Vague Attribution
Either cite a specific source or state the claim without attribution.

**Banned:** "industry reports suggest", "studies have shown", "many believe", "it is widely believed"

### 9. No Bolded Bullet Title Pattern
Never use `**Bold Title:** sentence that restates the title.`
**Example kill:** "**Scalability:** The system is designed for scalability." → Just say how it scales.

### 10. No Uniform Sentence Structure
Vary sentence length and rhythm. Mix short punchy sentences with longer ones.

### 11. No Sycophantic Openers
Never start with:
- "Great question!" / "That's really interesting"
- "Absolutely!" / "Of course!" / "Certainly!"
- "Tentu!" / "Tentu saja!" / "Saya dengan senang hati..."

Just answer.

**Also kill the assistant CLOSERS + self-reference (same tell, other end):**
- "I hope this helps!" / "Let me know if you have any questions" / "Feel free to reach out" / "Happy to help"
- "As an AI..." / "I cannot..." / "based on the information provided" / "as a language model"
End on the last substantive point. No wrap-up pleasantry, no machine self-reference.

### 12. No Hollow Summarization Closers
Never end with a paragraph that restates what was already said.

**Kill patterns:** "In conclusion...", "Overall...", "In summary...", "By [doing X], we can [vague outcome]"

### 13. No Corporate Therapist Voice
Never write like a motivational HR memo.

**Kill patterns:**
- "lean into..." / "foster a culture of..."
- "align on our collective vision"
- "double down on what matters"
- "moving forward" / "going forward" / "as we move forward"
- "level up" / "take it to the next level"

### 14. No "Says Everything, Means Nothing" Paragraphs
If you can't summarize a paragraph in one plain sentence, rewrite or cut it.

### 15. No AI Verb Crutches
**Banned verbs:**
- delve/delving → "look at", "examine", "break down"
- unpack → "break down", "explain"
- navigate (non-physical) → "deal with", "handle"
- foster → "build", "create"
- harness → "use"
- streamline → "simplify", "speed up"
- empower → "let", "enable"
- **2025-26 live-shift verbs (replaced the burned-out "delve/tapestry" as the current crutch set):** enhance, showcase, highlight, emphasize, "align with", embark, unlock, unleash, amplify, illuminate, cultivate, elevate, resonate, bolster, garner, underscore → use the plain equivalent (improve, show, stress, start, open, boost, raise, connect, back up, get).

### 16. No Corporate Buzzword Clusters
Any 2+ of these in one sentence = rewrite:
synergies, leverage (noun), holistic, ecosystem (non-bio), paradigm, scalable, robust, agile, resilient, stakeholders, alignment, actionable, deliverables

### 17. No Excessive Adverbs Before Verbs
**Kill patterns:** quietly/fundamentally/profoundly/seamlessly/meticulously + [verb]
**Fix:** Say the verb alone, or show the effect concretely.

### 18. No "This Signals" Connector Pattern
**Banned:** "This signals...", "This underscores...", "This highlights...", "This reflects a growing..."
**Fix:** State the causal connection explicitly, or just state the fact.

### 19. No "Landscape" Filler
**Banned:** "in today's [X] landscape", "in the current landscape", "the evolving landscape of", "across the [X] landscape"
**Fix:** Name the actual context or drop it entirely.

### 20. No Hype Words
**Banned:** game-changer, groundbreaking, revolutionary, transformative, disruptive (unless quoting someone)
**Fix:** State the concrete impact instead.

### 21. Sentence Length Distribution Check
Flag if fewer than 40% of sentences are under 10 words. Short sentences create rhythm and punch. If a block of text is all 20+ word sentences, break some up.

### 22. No Hedging Language
Be direct. Strip weasel qualifiers unless genuine uncertainty exists.

**Banned:** "could potentially", "it seems like", "it appears that", "arguably", "it could be said that", "at the end of the day", "when it comes to", "the reality is", "at its core", "key takeaway"
**Fix:** State the claim. If you're uncertain, say "I'm not sure" once, then state your best read.

---

## Grammar & Syntax Tells (v2)

The rules above catch WORDS. These catch SENTENCE SHAPES, which survive a clean wordlist and still read as AI.

### 23. No Compulsive Tricolon (rule of three)
LLMs reflexively make every list three balanced items. **Kill:** "fast, cheap, and reliable" / "X, Y, and Z" as the default cadence / three parallel clauses in a row. **Fix:** use the number of items the thought actually has (2, 4, 5). break the parallelism so they aren't all the same shape.

### 24. No Participial Tails
The bolt-on present-participle clause that fakes consequence. **Kill:** "..., creating a seamless experience", "..., making it easier to scale", "..., allowing teams to focus", "..., ensuring success", "..., driving growth", "..., helping you X". **Fix:** end the sentence at the fact, OR give the consequence its own clause with a real subject ("that cut onboarding to two days").

### 25. No "From X to Y" Range Framing
**Kill:** "from startups to enterprises", "from onboarding to churn", "everything from A to B". **Fix:** name the actual scope or drop it.

### 26. No Colon-Elaborate as Default Rhythm
A real device, now LLM-reflexive. **Kill (when repeated):** "The problem: X. The fix: Y. The result: Z." **Fix:** one per piece max. otherwise write the sentence.

### 27. No Casual-AI Openers (the NEW slop)
These READ human but are now the dead de-slopped-LLM tell. **Kill:** "Here's the thing.", "The truth is", "Let's be honest", "I'll be honest", "Here's what nobody tells you", "Make no mistake", "Let that sink in", "Plot twist", "Spoiler", "Here's the kicker", "And honestly,", "Real talk". **Fix:** just make the point. the point is the hook. **Note (the GPT-5-era trap):** performative casualness is the NEWEST signature. faux-spontaneity openers ("honestly,", "look,", "ok so", "real quick") sprinkled for fake voice are the casual-register version of slop. a genuine voice is consistent and earned, not a costume of casual markers.

### 28. No Rhetorical-Question-Then-Answer Filler
**Kill (when reflexive):** "Why? Because...", "The result? X.", "What does this mean? Y.", "The catch? Z." **Fix:** one per piece max. state it as a sentence.

### 29. No Anaphora-for-Fake-Rhetoric
Three+ consecutive sentences/clauses opening with the same word for "punch". **Kill:** "It's X. It's Y. It's Z." / "No A. No B. No C." **Fix:** once is fine. reflexive is a tell. vary the openers.

## Structural Tells (v2)

### 30. No Setup → 3 Bullets → Wrap Template
The reflexive document shape. **Fix:** let structure fit content. sometimes prose-only, sometimes a 5-item list, sometimes no closing wrap. if every section is the same shape, that IS the tell.

### 31. No Bold-Everywhere
Bolding every other phrase kills emphasis. if everything is bold, nothing is. **Fix:** ≤1 bolded phrase per ~5 lines, only the genuinely load-bearing one.

### 32. No Over-Signposting
**Kill:** "First... Second... Third..." on a 3-sentence idea / numbering every micro-point. **Fix:** signpost only when the reader needs to track genuinely parallel items.

### 33. No Emoji-as-Bullet (public content)
Emoji as semantic signal (✅ ❌ ⚠️ 🔴) is fine. emoji replacing list markers is a tell. **Scope:** public-facing content. Your operator chat channel keeps its emoji-OK register (see Preferences).

### 34. No Forced Both-Sides Balance
RLHF trains compulsory neutrality. the model dodges a stance by manufacturing symmetry. **Kill:** "while there are challenges, there are also opportunities", "on one hand X, on the other hand Y", "it's a double-edged sword", "despite the challenges, the future looks bright", the compliment-sandwich ("X is a step in the right direction, but..."). **Fix:** take the position. lead with the actual problem or the actual call. balance is not the same as having no view.

### 35. No Copula-Avoidance Significance
Pompous "serves as / stands as / represents / acts as" instead of plain "is" (close cousin of rule 2). **Kill:** "the building serves as a reminder", "this stands as proof", "X represents a shift". **Fix:** "the building reminds", "this proves", "X is a shift" (or name what shifted). also kill invented concept-labels coined as if established ("the supervision paradox", "the acceleration trap") when you mean to make an argument, not name a thing.

---

## Narrative-Construction Tells (v3.1, the THIRD axis, StoryScope lift 2026-07-02)

The lexical axis (banned words / rules above) and the statistical axis (perplexity + burstiness, the 3 Levers) both miss a third, separable axis: how the piece is CONSTRUCTED as a narrative or argument. StoryScope (arXiv 2604.03136) trained a detector on 61k stories and hit 93% F1 on narrative STRUCTURE alone, and named the AI tells below (they persist across genres, not just fiction). These are JUDGMENT calls (semantic), not regex: flag for review if 2+ fire; never mechanically ban. Same anti-evasion rule as the 3 Levers, the fix is real narrative sharpening (build a spine, hold a tension), NEVER perplexity-noise to fool a classifier.

### 36. No Over-Explaining the Thesis
AI states the take, then re-spells it in plainer words and spells out every implication. **Kill:** the gloss sentence that restates the point you just made. Trust the reader. (StoryScope's #1 AI tell.)

### 37. No Tidy Single-Track
One clean argument line, no live tension, counter-positions absent or strawmanned, everything resolves. Human writing holds an ambiguity. **Fix:** hold a real counterweight or an open question; don't resolve what shouldn't be.

### 38. No Flat Escalation (the CLAUDE fingerprint)
Every section / tweet / paragraph at the same energy and stakes; the piece accumulates instead of building. StoryScope names flat event-escalation as Claude's SPECIFIC signature, so this stack (Claude-run) is the most prone to it. **Fix:** later beats raise the stakes over earlier ones, they do not restate them.

### 39. No Missing Open Loop (threads / serialized only)
Everything closes; no reason to read on, reply, or quote. **Fix:** leave a gap the next beat closes. Scope: threads + serialized content, not every standalone piece.

### 40. Low Temporal / Structural Complexity (long-form)
Strictly linear, no time-shifts / callbacks / non-obvious ordering. Human long-form varies structure. **Fix:** vary it where it serves.

Provenance: the StoryScope take (arXiv 2604.03136), lifted into the content-authoring phases.

---

## Secondary Rules

### Latinate Word Inflation
| Instead of | Use |
|---|---|
| utilize | use |
| facilitate | help, enable |
| commence | start, begin |
| subsequently | then, later |
| approximately | about, around |
| demonstrate | show |
| implement | do, build, set up |
| leverage (verb) | use |
| prior to | before |
| in order to | to |
| due to the fact that | because |

### Register Consistency
Match the user's register. Never default to "professional AI assistant" tone. If voice profile exists, apply it.

---

## Voice Profile Integration

If `memory/Voice-Profile.md` exists, read it before writing any output. Apply as a positive layer ("write like this") on top of the de-slop rules ("don't write like that"). When there is a conflict, de-slop rules win.

Voice profile is generated and maintained by the `voice-profiler` skill.

---

## When Reviewing External Text

1. Read the full text.
2. Scan against all rules above.
3. Rewrite with violations fixed. Preserve meaning, structure, intent.
4. Do not add content. Do not change technical terms, proper nouns, or quotes.
5. Return clean version only. If user wants a diff, they'll ask.
6. If text is already clean (≤2 minor violations), say so and make the fixes inline.

---

## Sibling skill (visual-side gate)

For VISUAL deliverables (decks, HTML, sponsor PDFs, landing pages), pair this skill with `skills/anti-ai-design.md`. That sibling catches typography / palette / layout / numbered-grid / equal-bullet-parallelism visual tells that this skill (copy-only) cannot see. Both gates fire together as pre-publish checks for any external-facing visual deliverable. Standard chain order:

```
deck-design → pitch-deck-builder → anti-ai-slop (this skill, copy) → anti-ai-design (visual) → html-to-pdf-deck
```

See `skills/deck-design.md` Integration section + `skills/anti-ai-design.md` for the full audit checklist.

---

## Provenance (v3, 2026-06-13)

v1 = Wikipedia "Signs of AI Writing". v2 = the asymmetry / over-correction Prime Directive. v3 = a deep web-research pass (4 parallel agents: lexical / syntactic / rhetorical-structural / punctuation-and-detection). Key sources cross-validated: Wikipedia Signs-of-AI-Writing; Kobak et al. "excess vocabulary" (Science Advances / arXiv 2406.07016, the verb-heavy POS-shift finding); Reinhart et al. "Do LLMs write like humans?" (PMC11874169, participial clauses at 5.3x human rate); the burstiness/perplexity detection literature (GPTZero, Pangram hard-negative mining, Binoculars cross-perplexity, ICML/ICLR 2024); practitioner field guides (tropes.fyi, sh-reya, louisbouchard). Durable findings: (1) the tell migrated from vocabulary to STRUCTURE; (2) surface-scrubbing is necessary-not-sufficient, the real levers are burstiness + specificity + voice; (3) single occurrences are noise, the signature is DENSITY + co-occurrence (don't mechanically ban a device used once); (4) the de-slopped casual register is the newest tell. Full agent findings archived in the session log + outputs.
