---
name: critic
description: Tool-grounded Critic skill (layered eval architecture, Layer 2). Dispatched as a subagent on high-stakes outputs. Grounds the verdict against tool-fetched evidence, not self-reflection. Returns SHIP / SHIP_WITH_FIXES / BLOCK with fixes + reason + confidence. Pairs with the stake classifier (Layer 1) and branching-workflow (Layer 3). Used by content drafts, regulatory-style takes, partner outreach drafts, and proposals.
trigger: critic, ambient critic, run critic on this, verify with critic, critic check, critic verdict, fact check this
---

# Critic skill (tool-grounded)

**TL;DR**: a subagent reads the draft, runs 2 grounding checks (top-3 claim sourcing + one blind-spot probe) via read-only tools, and returns a JSON verdict (SHIP / SHIP_WITH_FIXES / BLOCK). Target 3-5 tool calls, ceiling 8. No tool call = auto-BLOCK. Verdict ≤200 tokens to the caller. Used by content drafts, regulatory-style takes, partner outreach, and proposals.

Layer 2 of the layered eval architecture. Verifies high-stakes drafts by fetching evidence, not by re-reading the draft. Self-critique without tools is noise. Tool-grounded critique is the only lift that survives evals (per arXiv 2510.14942 GroundedPRM, ICLR 2024 CRITIC). A prior inline self-critique missed the ~20% lift by skipping the fetch step. This skill enforces it.

## When to fire

- **Auto-fire on high-stakes turns**: a PostToolUse hook reads the `stake_classified` event from `logs/session.jsonl`. If `stake: high`, it dispatches this skill as a Task subagent.
- **Manual invocation**: any skill that produces external-bound output (content, regulatory-take, partner-outreach, proposal, content-publish) calls this Critic before locking the deliverable.
- **Operator-driven**: the operator invokes `/critic` on a draft to get a verdict before posting.

## Why a subagent (not inline)

Per the architecture's Layer-2 substrate-virtue: the Critic's reasoning stays in the subagent context, only the verdict returns to the main context. The lowest-pollution zoom-out primitive. The Critic burns ~2-3K tokens of grounded analysis; the main context absorbs a ~200-token verdict.

## Restricted tools

The Critic operates on read-only tools. It cannot write, cannot send messages, cannot modify state. The point is verification, not action.

**Allowed:**
- Read (file system)
- Grep / Glob
- WebFetch (verify external claims against sources)
- a research-grade web-search MCP (e.g. `mcp__exa__*`)
- a library-docs MCP (e.g. `mcp__plugin_context7_context7__*`)
- Bash with read-only commands (grep, find, jq, cat, head, tail, wc)
- `mcp__memory__memory_search` + `memory_list` (recall memory writes)
- a knowledge-graph read MCP (read_page / search / query, read-only)

**Forbidden:**
- Write / Edit / NotebookEdit (no file modification)
- spreadsheet append/update tools (no CRM writes)
- knowledge-graph create/append/update tools (no graph writes)
- outbound-message tools (reply / send / edit)
- workspace write tools (Gmail/Calendar/Drive writes)
- scheduler create/delete/update (no scheduler changes)

## Subagent prompt template

When dispatched, the Critic subagent receives this prompt:

```
You are the Critic. Verify a draft against tool-fetched evidence, not self-reflection.
Return a structured verdict. Be tight: target 3-5 tool calls, ceiling 8.

Draft to verify:
---
{DRAFT}
---

Stake context (from classifier):
- stake: {STAKE}
- matched_rules: {MATCHED_RULES}
- doc_type: {DOC_TYPE}

Run these 2 grounding checks. Use the FASTEST tool that can verify (priority order:
memory_search > graph_search > Read > Grep > Glob > web-search > WebFetch). Prefer one
targeted call over many; Glob+single-Read beats multi-Grep.

1. **Top-3 source check**. Identify the 3 STRONGEST load-bearing claims (highest stakes
   / most specific / most cited). For each, fetch a source via the fastest tool that
   can verify it. Flag any of the 3 that cannot be grounded. Do NOT source every claim
   in the draft. Sampling the top 3 is the contract.

2. **Blind-spot probe**. Run ONE tool query against what the draft most likely missed
   (search-truncation OR strongest counter-thesis, whichever is more relevant for this
   doc_type). If you find substantive evidence the draft ignores, flag it.

3. **Coherence check (content drafts ONLY: post / thread / article).** If doc_type is a
   post/thread/content article, Read `knowledge/content-structure-reference.md` and apply
   its coherence gate. This exists because a fact-clean draft can still be structurally
   broken (a real miss: a draft passed fact-grounding but stapled two arguments together):
   (a) SPINE. read T1->T2->T3->T4: does every unit advance the SAME single argument,
       or are two arguments stapled together? Two spines = BLOCK.
   (b) BOOKEND. read the open and the close back to back: does the close answer what the
       open raised? A closer that recaps instead of landing = flag.
   (c) HOOK. is the open a real archetype (cold number / position / negation / concede), NOT a
       rhetorical question you then answer (the top AI-tell)?
   (d) AI-TELLS. scan the kill-list (in-conclusion close, Moreover/Furthermore,
       adjective tricolons, uniform paragraphs, roadmap preamble).
   (e) WORD-LEVEL tells. spot-check against `knowledge/content-lexicon-diction-reference.md`
       swap-table: Latinate verbs where a concrete one fits (utilize/leverage/facilitate),
       "seamless/robust/crucial/delve/boasts", floating intensifiers where a number belongs,
       a hype-without-a-confidence-cap forward claim. Flag as SHIP_WITH_FIXES (word swaps are
       in-place fixes), not BLOCK, unless the diction is pervasive.
   Structural incoherence is SHIP-BLOCKING even when every fact is grounded. SKIP this
   check entirely for non-content doc_types (regulatory / deal / outreach / memo).

Output a JSON verdict EXACTLY:

{
  "verdict": "SHIP" | "SHIP_WITH_FIXES" | "BLOCK",
  "fixes": [
    {"issue": "specific issue", "fix": "specific change", "auto_applicable": true|false}
  ],
  "reason": "1-3 sentence summary",
  "confidence": 0.0-1.0,
  "tool_calls_made": <count>,
  "ungrounded_claims": [<list of claims you could not source>]
}

Hard rules:
- BLOCK = at least one specific BLOCKER (factual error, contradicts sourced evidence,
  top-3 claim cannot be grounded).
- SHIP_WITH_FIXES = fixable in-place (citation add, wording refine, scope clarification).
- SHIP = passes both checks AND has >=1 tool call backing the strongest claim.
  SHIP without ANY tool call is forbidden.
- Zero tool calls → return BLOCK with reason "self-reflection only, no tool grounding."
- Graceful degradation: if you hit the 8-turn ceiling with checks incomplete, return
  SHIP_WITH_FIXES + `fixes: [{"issue":"incomplete grounding","fix":"re-run critic with
  narrower scope","auto_applicable":false}]` rather than burning more turns. The
  orchestrator distinguishes this from max_turns errors via the fixes payload.
- If a wall-clock timeout fires, the orchestrator returns OPERATOR_REVIEW fallback on your
  behalf. Don't worry about it.
```

## Verdict format (return contract)

```json
{
  "verdict": "SHIP" | "SHIP_WITH_FIXES" | "BLOCK" | "OPERATOR_REVIEW",
  "fixes": [
    {"issue": "...", "fix": "...", "auto_applicable": true|false}
  ],
  "reason": "...",
  "confidence": 0.0-1.0,
  "tool_calls_made": <int>,
  "ungrounded_claims": ["..."]
}
```

OPERATOR_REVIEW is reserved for orchestrator-level fallback (timeout, dispatch failure). The subagent itself only emits SHIP / SHIP_WITH_FIXES / BLOCK.

## Hard rules

1. **No tool call → BLOCK.** The Critic must have grounded at least one load-bearing claim against an external source. Self-reflection without tool grounding is exactly the failure mode this skill exists to prevent.
2. **10s wall-clock timeout.** The orchestrator (PostToolUse hook) enforces it. On timeout, it returns `OPERATOR_REVIEW` to the caller with `reason: "Critic timeout"`.
3. **No write tools.** The restricted toolset is enforced via subagent dispatch config. If a write tool somehow leaks through, the subagent's grounding contract is broken.
4. **The verdict output must validate as JSON.** The caller (PostToolUse hook orchestrator) parses the verdict. Malformed JSON → fallback to OPERATOR_REVIEW.
5. **Subagent depth ≤2.** The Critic runs at depth 1 (the parent dispatches). The Critic does NOT spawn sub-Critics. If a sub-task needs further grounding, do it inline via tool calls, not subagent recursion.
6. **Token budget ~3K per dispatch.** Above 5K → flag in the verdict, reduce confidence. The Critic should be tight: 1-3 grounding queries, not exhaustive research.

## How to invoke

### Auto (PostToolUse hook)

```bash
# Wired via ~/.claude/settings.json hooks.PostToolUse
# An adapter script reads the stake_classified event, dispatches if high-stakes
python3 scripts/critic_dispatch_hook.py
```

### Manual (from another skill)

```python
# In a skill orchestrator (e.g. a content skill's critic phase)
from scripts.critic_dispatch import dispatch_critic

verdict = dispatch_critic(
    draft=draft_text,
    stake_metadata={"stake": "high", "matched_rules": [...], "doc_type": "..."},
    timeout_seconds=10,
)

if verdict["verdict"] == "BLOCK":
    # queue for operator review
    queue_for_review(draft, verdict)
elif verdict["verdict"] == "SHIP_WITH_FIXES":
    # Apply auto-applicable fixes inline; queue the rest
    apply_fixes(draft, verdict["fixes"])
elif verdict["verdict"] == "SHIP":
    # Pass through silently
    pass
elif verdict["verdict"] == "OPERATOR_REVIEW":
    # Fallback (timeout / dispatch error). Notify the operator via chat.
    notify_operator(draft, verdict)
```

### Operator (slash command)

`/critic <path-to-draft>` invokes the Critic on a specific file. Returns the verdict to chat.

## Pairs with

- **Layer 1**: `scripts/stake_classifier.py` produces the high-stakes verdict that triggers this Critic.
- **Layer 3**: `skills/branching-workflow.md` codifies what to do if the Critic returns BLOCK and the operator chooses branch-and-retry over queue-for-review.
- **A content skill's critic phase**: a prior inline Critic refactored to call this ambient skill.

## Failure modes (observed)

- **Timeout cascade**: a 10s wall-clock is tight when a web-search or WebFetch is slow. The orchestrator returns OPERATOR_REVIEW; downstream skills must treat OPERATOR_REVIEW as "queue, do not auto-ship". If timeouts exceed 20% over a rolling 7-day window, the dispatcher (not this skill) needs a budget bump or a faster grounding tool (memory_search before a web-search).
- **Self-reflection drift**: the subagent returns SHIP with `tool_calls_made: 0`. Hard rule 1 catches this. If it slips through, the dispatcher invalidates the verdict and re-dispatches with a stronger brief.
- **Ungrounded SHIP_WITH_FIXES**: the fix list cites no source. The caller must reject and re-queue. A fix is only valid if it points at evidence the verdict surfaced.
- **JSON parse fail**: a malformed verdict → OPERATOR_REVIEW fallback. Do not silently retry; surface it to the operator.

## Source archive

This is Layer 2 of the layered eval architecture. Anchored to GroundedPRM (arXiv 2510.14942) / ThinkPRM (arXiv 2504.16828) / R-PRM (EMNLP 2025) / GenPRM (arXiv 2504.00891) / CRITIC (ICLR 2024).

## Tunings (lifted from a bank's multi-agent research system)

Source: a public write-up of an investment-research team's 3 lessons from building a supervisor + specialists architecture. Already-have-architecturally, but these 3 lessons remain genuinely portable as Critic-pass tunings.

### 1. Start simple, refactor often

Their team began with a vanilla ReAct agent before scaling up. Same applies here: don't over-engineer Critic dispatch. The current state (single subagent dispatch with an adversarial brief + tool grounding) IS the "vanilla". resist scope-creep into multi-stage refinement until evidence shows single-pass is insufficient.

**Apply**: when a Critic verdict feels weak, FIRST refactor the brief (add the tool-grounding requirement, sharpen severity tags), don't add a second Critic stage. Multi-stage = compounding latency + token cost without a proportional verdict-quality gain.

### 2. Eval-driven dev: the eval phase is longer than the build phase

Their eval phase was longer than their build phase. The same pattern shows up here (an acceptance test caught real classifier gaps; a temporal-rerank pilot validated stale-memo replay via an A/B harness).

**Apply**: when modifying the Critic brief, build the regression set BEFORE editing the brief. Have N historical drafts + their human-verified verdicts. Then mod the brief + rerun. Don't trust "feels better". measure verdict consistency on the regression set.

### 3. Accuracy stair-step (not linear)

Accuracy improvements come in step-functions, not gradients. <50% verdict accuracy isn't worth shipping; the climb to 70% requires a structural change (tool grounding, dual-version surfacing, severity tagging), not parameter tuning.

**Apply**: if Critic accuracy plateaus, the next gain is a structural mod (e.g. add a second specialist subagent for fact-checking vs voice-fidelity), not prompt-tweaking. Recognize the plateau signal: 5+ versions of the brief without movement = a structural change is needed.

### Why these and not the supervisor pattern itself?

The harness IS the supervisor. Skills + subagent dispatch already implement the pattern. There's no need for a separate supervisor layer. The 3 lessons above are operator-discipline tunings that transfer regardless of supervisor implementation.

## Tunings (3-bump rule fix, Path A simplification)

**Trigger**: a nightly self-audit invoked the root-cause-over-bandaid rule. Max-turns had been bumped 3× (4 → 6 → 8) with each bump failing to clear the failure pattern. The audit's hypothesis: the prompt asked for too many tool calls per run, so bumping the turn budget was the wrong axis. The operator picked Path A: simplify the prompt.

**Changes shipped**:
1. **4 checks → 2 checks**: consolidated Search-truncation + Steel-man into a single "Blind-spot probe" (pick whichever framing fits the doc_type). Dropped the meta Self-reflect-vs-tool-verify gate. its substance is already enforced by the ≥1-tool-call hard rule.
2. **EACH claim → TOP 3 claims** in Sourcing: caps the cost for long drafts where claim-count was the variance driver. Top-3 by strength is the Pareto-correct sample; ungrounded #4+ claims that turn out to be load-bearing surface in fixes during human review or downstream Critic runs.
3. **Tool-priority hint added**: an explicit ranking memory_search > graph_search > Read > Grep > Glob > web-search > WebFetch. Steers the subagent away from network-bound tools when a local lookup suffices.
4. **Glob+single-Read pattern hint**: nudges against multi-Grep tool storms that don't actually accelerate verification.
5. **Graceful-degradation rule added**: on the 8-turn ceiling with checks incomplete, return SHIP_WITH_FIXES + an `incomplete grounding` flag, not a max_turns error. The orchestrator distinguishes via the fixes payload.

**Preserved**: the ≥1-tool-call → BLOCK rule, the JSON verdict shape, the restricted tool list, the "self-reflection only" guard. The content-critic-phase + Stop-hook dispatch + manual /critic invocation paths untouched.

**Measurement plan**: track `critic_verdict` events in `logs/session.jsonl` over the next 7 days. Targets:
- Median tool_calls_made: target 3-5 (was 6-8+)
- max_turns errors: target <3/week
- BLOCK rate: should stay roughly flat (catches not lost). if it drops materially, the brief is too lax
- SHIP_WITH_FIXES with the `incomplete grounding` flag: track separately as a new failure mode

**Rollback path**: the prior brief is preserved in git history. A single Edit reverts. Watch for the next 7-day cycle before declaring shipped vs needing revert.

**Open question**: the dispatcher max-turns is still 8 in `critic_dispatch_hook.py`. If the observed turn-count falls comfortably below 6 over a week, consider lowering the ceiling to 6 (further cost discipline). Defer that decision until you have the data.
