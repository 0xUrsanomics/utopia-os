---
name: branching-workflow
description: When and how to use the coding-agent CLI's `/rewind` to abandon a bad branch and restart from a prior turn. Documents the recovery primitive for the layered eval architecture's Layer 3 (universal recovery toolkit) and the branch-and-retry path. Use when an output is going off the rails, when a Critic verdict says BLOCK, or when a path-of-least-resistance failure has corrupted the conversation context. Pairs with /save (extract insight first), /scope (re-frame after rewind), and the Critic skill (verdict-driven branch trigger).
trigger: branching, rewind, /rewind, branch and retry, abandon this path, branch from before, fork from prior turn, rewind to before
---

# Branching workflow

`/rewind` (Claude Code v2.0.0+): fork from a prior assistant turn, take a different forward path. The abandoned branch's tokens leave context entirely. The cleanest zoom-out primitive available natively in the CLI.

This skill: WHEN to branch, WHAT to preserve first, HOW to recover. Pairs with the Critic skill (a BLOCK verdict often triggers a branch).

## When to branch

Branch (use `/rewind`) when ALL three apply:

1. **The current path is going off the rails.** Output is wrong, the agent is confidently asserting unverified claims, the classifier flagged high-stakes but the Critic says BLOCK, or a path-of-least-resistance failure (closure-bias / search-truncation / sycophancy) has visibly compromised the conversation.
2. **Continuing-with-corrections would be more polluting than rewinding.** "Let me reconsider" + retry-emit will leave the bad branch in context as residue. Rewinding leaves it cleaner.
3. **The bad path started recently enough.** If the divergence is 1-3 turns back, rewind. If it's 10+ turns back, /save the insights + /compact + start fresh with prepended context.

Do NOT branch when:
- The output is acceptable but imperfect (continue-with-revision is cheaper).
- You're in the middle of a long-running task with persistent state (database writes, sent messages, scheduled tasks fired). Branch does NOT undo external side effects.
- You're under 50 turns into the session (the cost of pollution is low; rewind overhead doesn't pay back yet).

## What to preserve before branching

Branch is destructive of the abandoned branch's context. The new-branch agent has no memory of why the old branch was abandoned unless you tell it. Before invoking `/rewind`:

1. **Run /save if there are durable learnings.** Insights from the bad path that should propagate forward must be persisted to disk first (memory/Decisions.md / Learnings.md / Feedback/). Otherwise they vanish with the branch.
2. **Note the divergence point.** Identify which assistant turn started the bad path. The rewind targets THIS turn.
3. **Note WHY the path went bad.** This will be re-injected into the new branch's context as the corrective prompt. Format: "rewinding because [specific failure mode], take this corrected approach: [what should happen instead]."
4. **Mark any side-effects that already fired.** Tools called, files written, messages sent in the bad branch. These persist past the rewind. Note them so the new branch doesn't redo them or assume they didn't happen.

## How to branch (operator workflow)

1. Press `esc esc` (the rewind keypress) to enter the rewind selector.
2. Select the assistant turn before divergence.
3. The CLI discards subsequent turns from active context.
4. Re-prompt with corrective context: "we were about to [bad path], instead [corrective intent]."
5. Continue forward from the new branch.

**Chat-only fallback** (no `esc esc` from a phone). When the operator is on a chat channel and the agent flags branch-needed:
1. The agent runs /save to persist learnings to `memory/Decisions.md` or `memory/Learnings.md`.
2. The agent replies with: "branch recommended. reason: [X]. corrective intent: [Y]. options: (a) /restart fresh, (b) reply 'continue with correction' to revise-in-place, (c) ignore."
3. The operator picks. /restart fresh = clean slate. continue-with-correction = stay in current context, the agent applies the corrective prompt as the next turn.
4. Programmatic /rewind from the agent side: not supported.

## Critic-driven branch trigger

When the Critic returns `verdict: BLOCK`, two paths: queue-for-review or branch-and-retry.

**Branch when:**
- Errors are structural (sourcing gaps, stale facts, contaminated framing). Re-emitting from the same context replicates them.
- The Critic surfaces a category the agent didn't see. Re-emitting WITH the Critic verdict in context tends to produce cosmetic-only changes.
- Pollution cost is high (many turns to undo).

**Queue-for-review when:**
- The operator can supply the fix directly ("missing a source citation, add it").
- The bad path is short. revise-in-place is cheaper.

## Recovery patterns (post-rewind)

After branching, the new branch starts with:
- The old branch's tokens removed from active context
- The corrective prompt as the first turn
- Any /save'd insights available via memory/ recall on next reference
- Any external side effects from the old branch persisted (NOT undone)

Recovery sequence:
1. The new branch generates with corrective context.
2. Verify against /save'd memory writes before locking the output.
3. If the new branch fails too: /save lessons, branch again. Max 3 retries before escalating to an operator-final-gate.
4. Track the branch count. >2 in one session = the classifier or Critic is mis-calibrated. Flag for review.

## Hard rules

1. **Branch does NOT undo external side effects.** Sent messages, DB writes, tool calls fired in the bad branch persist. Note them before branching.
2. **Branch is operator-only.** The agent cannot invoke `/rewind` itself (operator-empowered class). The agent recommends-but-doesn't-execute.
3. **Always /save before branching** if learnings exist. Insights from bad branches are valuable for classifier training and the corrections registry. Don't discard them.
4. **Don't branch trivially.** If <2 high-friction turns of bad path, revise-in-place is cheaper. Branch is reserved for >3-turn drift or structural corruption.
5. **Document the branch** in the corrective prompt. The reason for branching becomes part of the new branch's context. Helps the reality-feedback loop track branch outcomes for classifier training.
6. **Three-strike escalation.** If branched 3 times in the same session on the same problem, the issue is structural (mis-calibrated classifier, weak Critic prompt, ambiguous source data). Stop branching, flag for refinement.

## Out of scope

- Programmatic rewind (agent-triggered): not supported by the CLI as of v2.0.0. Operator-only.
- Cross-session branching: rewind operates within the current session. Cross-session "what would have happened if I had said X 2 days ago" is not supported. Use /save + replay from disk if needed.
- External side-effect compensation: branching does not undo sent messages / DB writes / etc. Substrate reversibility for external side effects is a confirmed literature gap. No general-purpose fix ships anywhere yet.

## Source

Anchors: LangGraph time-travel docs, the CLI's `/rewind` (v2.0.0). This is the Layer 3 recovery primitive of the layered eval architecture.
