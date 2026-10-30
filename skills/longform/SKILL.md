---
name: longform
description: Interview-driven long-form pipeline (monthly thesis, essay, X Article, newsletter issue). Every section is anchored in the operator's own interview answers, not AI synthesis. Phases - substrate audit, thesis curate, interrogation, outline review, section draft + critic, gates, review ensemble with a required cold red team, packaging, cross-publish, archive.
trigger: /longform, longform, monthly thesis, x article, long-form draft, monthly piece, longform pipeline, newsletter issue
inputs:
  reference:
    - memory/SOUL.md
    - memory/Voice-Profile.md
    - skills-shared/anti-ai-slop/SKILL.md
    - skills-shared/figurative-playbook/SKILL.md
    - docs/content-gates.md
  working:
    - outputs/raw/longform/audits/YYYY-MM-substrate-audit.md
    - outputs/raw/longform/runs/active/{issue}/content-object.md
    - outputs/raw/longform/runs/active/{issue}/draft-full.md
---

# /longform. Interview-driven long-form pipeline

Long-form drafts that an agent writes from substrate alone (notes, signals, past outputs) read as AI-drafted, because they are anchored in nothing the operator actually thought. The fix is structural: interview the operator first, and draft every section from those answers.

**Core invariant:** no prose is drafted without an interview answer feeding it. A section with no interview anchor does not ship.

**Posture:** the thesis commits to a sharp, debatable position and holds a live tension, not a tidy survey. The opener and title must earn the read standing alone. Bold means a sharper claim, never hype, ragebait or a looser grip on facts.

## Pipeline shape

```
Phase 0   SUBSTRATE AUDIT      -> publishable inventory + topic shortlist
Phase 1   THESIS CURATE        -> 3-5 thesis candidates, each with reader + action declared
                                  operator picks (or rejects -> re-curate)
Phase 2   THESIS INTERROGATION -> 5-8 questions; free-form answers become the spine
Phase 2.5 OUTLINE REVIEW       -> outline from interview + substrate; operator approves before prose
Phase 2.9 TAXONOMY PRE-CHECK   -> every regulatory / framework citation checked for scope
Phase 3   SECTION DRAFT        -> section by section, one brief per section
Phase 3.5 SECTION CRITIC       -> cold critic per section, A / B / hybrid
Phase 4   GATES                -> slop (block), voice (block), structure + paraphrase (warn), rubric, postmortem
Phase 4.3 REVIEW ENSEMBLE      -> adversarial agent + council + cross-model + REQUIRED cold red team
Phase 4.5 WORLDVIEW CAPTURE    -> interview answers -> memory/projects/
Phase 4.6 PACKAGING            -> TLDR at the top + one visual per section
Phase 5   CROSS-PUBLISH        -> paste-ready HTML per surface + promo thread (link in tweet 2)
Phase 5.5 ARCHIVE              -> stamp published, move run active/ -> archive/
```

---

## Phase 0. SUBSTRATE AUDIT

Inventory publishable substrate from the last 30 days: reviewed outputs, daily or weekly synthesis notes, the Voice Excerpts section of `memory/projects/<active>.md`, recent `memory/Decisions.md` entries, approved short-form drafts.

Output `outputs/raw/longform/audits/YYYY-MM-substrate-audit.md`:
1. Publishable substrate inventory (3-7 pieces, brutally honest cap)
2. Thesis topic candidates (3-5 max)
3. Verification anchors (links to the canonical sources for fact-checks)

Cap honestly. Padding to five is a tell. Three strong beat five weak.

## Phase 1. THESIS CURATE

Each candidate is a complete shape, not a topic. Required fields:
- `title` (working, opinionated)
- `claim` (one load-bearing sentence the piece will defend)
- `audience` (a specific reader, never "anyone interested")
- `reader_action` (what the reader DOES after reading; a testable behavior change)
- `forecast` (a 90-day prediction with a falsification condition)
- `counterargument` (the strongest pushback the piece must address)
- `substrate_anchors` (files that feed the claim)

A candidate missing any field is dropped. The claim must be falsifiable in principle. The reader action must be concrete ("revise your Q3 pricing"), never abstract ("think differently"). The operator may pick one, reframe one, reject all and propose their own, or say "none lands" (re-curate, or wait two weeks for thicker substrate).

## Phase 2. THESIS INTERROGATION

5-8 questions on the picked thesis, sent in batches of 2-3. Answers come back free-form (fragments, lists, voice notes all count).

**Sharpen before asking.** Load the operator's prior takes (Voice Excerpts, the last run's `interview.md`) and bind each question to an existing anchor: push an edge, expose a tension, or escalate a prior call. A cold, generic question is rejected.

Question shapes (pick, do not use all):
1. Audience belief: what does the audience currently believe about this?
2. Counter-narrative: where is that belief wrong?
3. Evidence: the cleanest single data point for the claim?
4. Counterargument: the strongest pushback, and why it does not bind?
5. Reader action: what should the audience do this quarter?
6. Forecast: the 90-day prediction, and what would falsify it?
7. Mechanism: what is the structural cause?
8. Operator tell: the insider observation only you have?
9. Local specificity: why does this matter for your market in a way global takes miss?
10. Failure modes: where could the piece misfire?

Log every answer verbatim to `outputs/raw/longform/runs/active/<YYYY-MM-slug>/interview.md`. It is the spine substrate.

## Phase 2.5. OUTLINE REVIEW

Assemble an outline from the interview + substrate. Not prose, just the spine: hook (3-line synopsis), sections A-E (opinionated header, claim sentence, 2-3 evidence anchors, counterargument, implication, the interview quote it lands on), forecast (3-5 testable predictions), closing position.

Every section cites at least one interview anchor. A section without one stops here: re-interrogate that topic. The operator approves the spine before any prose.

## Phase 2.9. TAXONOMY PRE-CHECK

Before prose, extract every regulatory or framework reference from the interview and the outline (laws, regulations, licence classes, standards). Verify each one's scope with one search ("what does X regulate"). Build a citation-vs-actual-scope table.
- A miscite in the operator's own verbatim words: surface it, do not silently fix it.
- A miscite in agent-written outline text: fix it before Phase 3 and log the swap.
- All in scope: log `taxonomy_check:: pass` and proceed.

Long-form is higher risk than a short post here: more claims, more places to slip.

## Phase 3. SECTION DRAFT

Draft one section at a time from a slim brief, never a single-shot 3,000-word ghostwrite.

Run folder:
```
outputs/raw/longform/runs/active/<YYYY-MM-slug>/
  content-object.md    # state machine + phase tracking
  interview.md         # Phase 2 verbatim answers
  outline.md           # Phase 2.5 approved spine
  brief-sectionA.md    # 8-field brief per section
  draft-sectionA.md    # one draft per section
  draft-full.md        # assembled piece, after every section clears critic
  review-ensemble.md   # Phase 4.3 pooled findings
  feedback.md          # post-publish pulls
```

Brief fields (400-900 tokens): `thesis` (the sub-claim), `reader`, `proof` (interview anchors + evidence), `angle` (how it opens), `constraints` (word target, counterargument / forecast / quote required), `voice-anchors` (2-3 register pulls from the interview and `memory/SOUL.md`), `risks`, `open-loops` (what the next section resolves).

Per section: read the brief and the relevant interview answers, draft to target, include at least one interview quote (verbatim or close paraphrase), a counterargument paragraph and an implication paragraph. Then run your voice gate on the section right away (a per-section score is noisy, so treat a fail as a strong nudge to reinject, not a verdict), then the Phase 3.5 critic, then get the operator's section-level approval.

Voice rules: lift the operator's actual phrases (verbatim beats paraphrase), keep their register and code-switching, lead with the point, no preamble, no hedging, zero em or en dashes, strip the anti-slop wordlist. One controlling image per piece if the piece uses figures at all (`skills-shared/figurative-playbook/SKILL.md`).

## Phase 3.5. SECTION CRITIC

Dispatch one foreground subagent per section, cold-start (no author, no intent):

```
You are an adversarial critic in a long-form refinement pipeline. Cold-start context.
NO knowledge of who wrote this.

Candidate (section draft):
---
{section_draft}
---
Section's stated job: sub-thesis {thesis}; audience {reader}; required: counterargument
addressed, interview quote anchored, implication concrete.

RULES:
1. Find at least 3 distinct, substantive weaknesses. Quote the exact claim.
2. Do NOT offer fixes. Only attack.
3. Rate each FATAL | MAJOR | MINOR.
Look for: buried thesis, no reader action, straw-manned counterargument, unfalsifiable
forecast, interview anchor paraphrased away, low named-entity density (under 1 per 200
words), orphan sub-thesis, vague implication.
TOOL-GROUNDING: for each FATAL or MAJOR factual weakness, verify with a tool (web search,
fetch, memory search). Zero tool calls despite factual weaknesses: prefix [GROUNDING-FAIL].
Your own writing: zero em dashes, no slop wordlist, lead with attacks.
Return a numbered list with severity tags, then "Tool calls made: N".
```

Return to the operator as A (voice fidelity) / B (every critique addressed, may lose voice) / hybrid, with what each addresses. Skip the critic for a section that is almost all operator quote, and for the forecast section (it gets a falsifiability check instead).

### Phase 3.x. VOICE-REINJECTION LOOP (on a voice-gate fail)

A below-floor voice score is structural smoothing, not a nit. Do not hand-tweak the assembled draft:
1. Re-score each section; rank by how much of it traces to `interview.md`.
2. Pull the operator's literal interview sentences back into the weakest sections.
3. Break uniform rhythm: a short sentence after a long one; delete connective scaffolding.
4. First sentence = the claim. Delete the windup.
5. Re-assemble and re-run the gates. Loop until pass.
6. When two gates trade off round after round, run `scripts/eval/gate_controller.py` with each gate as a signed margin: it names the binding gate to protect in the next revise.

Reinjection adds the operator's real words, never invented ones. A section with no feeding answer had no business existing: cut it or re-interrogate.

## Phase 4. GATES

Run on `draft-full.md`, never on single sections.

- **4.0 Slop gate (hard block).** `python3 scripts/pipeline/external_slop_gate.py --file <run>/draft-full.md`. Em and en dashes, the slop wordlist, AI-cliche openers, hedge openers. Any hit blocks; surface the line and offer rewrite, edit, or override-with-log. Also run `scripts/pipeline/imported_claim_gate.py --file <run>/draft-full.md` (advisory): every load-bearing imported claim (legal status, entity counts, existence claims) gets checked against the primary source; block only on a real conflict.
- **4.0b Voice gate (hard block).** Your own voice-fidelity gate, calibrated on the operator's interview: share of sentences that trace to `interview.md`, burstiness, fragment ratio. Pick floors by register (an institutional piece scores lower on casual-register floors and that is not a fail). A fail cannot be overridden: recycle through 3.x. Never make an AI detector the objective; injecting noise or typos to beat a classifier is banned.
- **4.0c Structural tells (warn).** Flag if 2+ fire: over-explains the thesis, tidy single track with no live tension, flat escalation (uniform stakes from section to section), strictly linear structure. `scripts/pipeline/structure_repetition.py --file <run>/draft-full.md` covers repeated sentence skeletons and antithesis density.
- **4.0d Paraphrase / insight-shaped (warn).** `scripts/pipeline/paraphrase_test.py --file <run>/draft-full.md --llm`. A sentence that sounds profound and means nothing: cut it or replace the abstraction with the concrete thing. Never reword to beat the scan.
- **4.1 Bookmarkability rubric.** Seven criteria scored 0-2: thesis clarity, reader-action specificity, counterargument strength, forecast falsifiability, named-entity density, interview-anchor presence, cross-publish readiness. 10/14 or more ships to postmortem. 7-9: fix the weakest two rows and recycle to Phase 3. 6 or less: kill, log the reason.
- **4.2 Viral postmortem.** Which paragraph gets quoted, which section gets screenshotted, which forecast becomes the "you called it" receipt, where a skimmer misreads it. No quotable paragraph is a structural failure.

## Phase 4.3. REVIEW ENSEMBLE

Sections 3.5 and 4.2 are the drafting model reviewing itself, so they share its blind spots. Run on the full draft:

1. **Adversarial agent.** The Phase 3.5 brief run on the whole piece (`skills/critic/SKILL.md` for a SHIP / SHIP_WITH_FIXES / BLOCK verdict).
2. **Council.** `skills-shared/decision-council/SKILL.md`: attacks the framing where the critic attacks the claims.
3. **Cross-model reviewer.** A different model family (`skills/advisor/SKILL.md`) with an adversarial prompt: weakest three claims, AI tells, logic gaps. Cross-verify any citation it raises; external models invent references too.
4. **Cold red team (REQUIRED).** A read-only subagent on the strongest available model (for example `model: fable`), briefed with the draft path, the live or preview URL, the promo thread and the research file the piece drew on, and nothing about intent. It attacks six axes: facts and numbers against sources; internal consistency of the calls and odds; argument quality and the obvious counterarguments (regulator objections especially); exposure (anything that reads as financial or legal advice, the author's identity, claims about named firms, tone toward regulators); writing tells and metaphor coherence; and whether the thread stands alone. Output: findings by severity with the quoted span and the smallest fix. **FATAL is fixed before anything is deployed or posted. MAJOR goes to the operator.** Order matters: red team first, publish second. Running it after publication only tells you what is already public.

Paste the zero-dash and no-slop constraint into every reviewer brief, so a suggested rewrite cannot smuggle tells back in.

Reconcile into `review-ensemble.md`: dedupe, rank by severity and cross-reviewer agreement (a weakness every reviewer hit independently is load-bearing; a lone flag is a lead). Consensus FATAL recycles to Phase 3. MAJOR-only is the operator's call. Minimum bar to ship: the cold red team plus the adversarial agent, council and cross-model reviewer all ran.

## Phase 4.5. WORLDVIEW CAPTURE

Append the interview substrate to `memory/projects/<active>.md`: the verbatim answers on the audience's current model, the counter-narrative and the forecast, plus 3-6 bullets of modelable belief structure (not the published take). Long-form interviews are the richest substrate the voice model gets.

## Phase 4.6. PACKAGING

- **TLDR at the top, every surface.** 4-6 bullets, one load-bearing claim each, the whole thesis skimmable in 20 seconds. One canonical block reused everywhere.
- **One visual per section.** Each encodes that section's one idea (diagram, comparison, flow, data cut); a pull-quote card is the fallback. Build as HTML, render PNG headless. Frame per surface: X at 5:2 (1500x600), newsletter at 16:9 or 21:9. One design, exported at each ratio.

## Phase 5. CROSS-PUBLISH

**Paste-ready conversion.** Rich-text editors (X Articles, newsletter platforms) map clipboard HTML to their own blocks; they do not parse raw markdown, so a `.md` paste lands as literal `##` and `**`. Render each surface's markdown to clean semantic HTML (pandoc works), open it in a browser, select all, copy, paste. Pull the H1 out into the platform's title field and the subtitle into its subtitle field. Images do not ride along in the paste: leave a visible "drop image here" marker at each spot.

Surfaces: the X Article (primary, TLDR on top, 5:2 visuals), a newsletter mirror (subtitle required, 16:9 visuals), a PDF if you need a pitchable artifact.

**Promotional thread.** 5-7 posts cut from the article, written as independent marketing, not chopped paragraphs.
- **Link placement:** if the thread links out, the link goes in POST 2, never the last post; nobody scrolls past ten posts to find it. Structure: post 1 = the TL;DR with no link, post 2 = the hook plus the link, post 3 onward = the content.
- On an account where outbound links get suppressed, keep the thread link-free and post the link as a reply instead. Decide per account and write the rule down.

Never auto-publish: the agent drafts, the operator approves and posts.

## Phase 5.5. ARCHIVE (terminal, not optional)

Cross-publish is not done until the run leaves `active/`: stamp `content-object.md` (`phase: PUBLISHED`, `archived:`, `published_url:`) and move the run to `outputs/raw/longform/runs/archive/<slug>/`. Make it a script, idempotent. A terminal transition that depends on someone remembering has no trigger and no consequence when skipped, so a live article ends up indistinguishable from an unfinished draft.

## content-object.md state

```yaml
---
issue: YYYY-MM
slug: {slug}
phase: 0|1|2|2.5|2.9|3|3.5|4|4.3|4.5|4.6|5|5.5
section_state: {A: [brief, draft, critic, approved]}
gates: {slop: pending|passed, voice: pending|passed, rubric: N/14, postmortem: pending|passed}
review_ensemble: {adversarial: pending|clear|flags, council: ..., cross_model: ..., red_team: pending|clear|fatal|major}
packaging: {tldr: pending|done, visuals: N-of-M}
publish: {x_article: pending|published, newsletter: pending|sent, pdf: pending|generated}
---
```

## Rules

- Never ship a section without an interview anchor.
- Never write the piece from substrate alone.
- Never publish without the operator's section-by-section approval, and never auto-publish.
- Never smooth the operator's voice into bland prose; prefer length over a register rewrite.
- Never override a voice-gate fail; recycle through 3.x.
- Never make an AI detector the objective function.
- Never ship without the cold red team, and never run it after publishing instead of before.
- Never ship a wall of text: TLDR plus one visual per section.
- Never hand the operator raw markdown for a rich-text editor; hand them paste-ready HTML.
