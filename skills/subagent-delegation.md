---
name: subagent-delegation
trigger: delegate, subagent, parallel research, spawn agent, Task tool, background work, explore plan execute, isolate context, independent tasks
description: >
  Reach for the Task tool when work is independent, parallelizable, or context-heavy. Subagents run
  in isolated context windows. their research output comes back as a single summary, keeping the
  main thread lean. Use for: parallel research (2+ independent questions), inventory scans, deep
  dives that would blow context budget, anything where the main thread only needs the conclusion.
  Don't use for: trivial lookups, sequential dependencies, work that requires main-thread state, or
  tasks under ~3 steps.
---

# Subagent Delegation

## When to reach for it

Trigger the Task tool when you observe ANY of:

1. **Parallel-independent work**: 2+ questions that don't depend on each other's answers. Research in parallel = N-way speedup + N-way context isolation.
2. **Context-heavy exploration**: "scan the whole codebase for X", "compare 10 libraries", "audit 30 files". the raw output would blow context budget even if the final answer is small.
3. **Research that ends in a single conclusion**: the user only needs the verdict, not the transcript. Subagent summary comes back in ~300-800 words, vs 5-10K tokens of raw exploration.
4. **Security audits / dep checks / legitimacy scans**: main thread stays clean while the agent does the grunt work.
5. **Anything the user said "go investigate"**: if it's open-ended and needs web + grep + reads, it's probably a subagent job.

## When NOT to delegate

- **Trivial lookups** (single file read, known path): direct tool is cheaper
- **Sequential dependencies**: if step B needs step A's result to even START, running both in parallel wastes compute
- **State mutations**: file edits, git ops, commits. keep in main thread for visibility
- **Tasks under ~3 steps**: subagent overhead > savings
- **User-facing decision threads**: user wants to see your reasoning, not a hidden agent's

## The explore-plan-execute pattern

2026 default for non-trivial work:
1. **Explore**: subagent gathers facts (inventory, comparables, docs, options)
2. **Plan**: main thread synthesizes the exploration into a concrete plan
3. **Execute**: main thread does the edits (with direct tools)

Separation matters: the explore phase is read-heavy and disposable. The execute phase needs your judgment. Don't conflate.

## Parallel vs sequential

**Parallel** (default for independent work): send multiple Agent tool calls in ONE message with `run_in_background: true`. They run concurrently. Notifications arrive as each finishes.

```
Agent 1: research library A security
Agent 2: research library B security
Agent 3: scan our codebase for current usage
```

**Sequential** (only when A→B→C is strict): fire one, wait for result, feed into next. Slower but unavoidable for dependent chains.

## Prompt discipline

Subagents are amnesiac. They see nothing except the prompt you hand them. Brief them like a smart colleague who walked in cold:

- **Goal**: what outcome you want
- **Context**: what's relevant from the session (file paths, prior decisions, constraints)
- **Boundaries**: what NOT to do (don't edit files, don't install, read-only, etc.)
- **Output format**: structured sections, word limit, no fluff
- **Return contract** (mandatory): structured JSON matching the `subagent_return_v1` schema. See `memory/Infra/agent-protocols-v1.md` Surface 2 for full schema. Append the dispatch prompt template at the end of every brief.
- **Anti-slop**: include "no em-dashes, no AI-slop wordlist (leverage/delve/navigate/holistic/seamless/foster/streamlin/unleash), no AI-cliche openers". subagents don't inherit CLAUDE.md (per your anti-slop brief).

Terse command-style prompts produce shallow work. Over-briefed prompts burn tokens. Aim for 150-400 words, precise.

## Return contract (subagent_return_v1)

**Locked.** Every dispatch prompt ends with the JSON return template (see agent-protocols-v1.md). Required fields: summary / exit_status / files_changed / verification_hints / findings / recommendations / context_used / budget_actual.

**Why the contract matters**: trust-but-verify. Subagent's summary describes INTENT; parent must verify actual diff matches output before reporting "done." Without structured return, parent can't programmatically check claims. With it: parser → verifier → confidence verdict.

**Verification helper**: `scripts/verify_subagent_diff.py`. takes claimed `files_changed` list + dispatch timestamp, reports verified / missing-claimed / unexpected-modifications. Run before reporting task completion to user.

## Worktree isolation for code-modifying dispatches

**Lifted from a Kanban-tool audit**. concept-only, no install.

When a subagent is doing **code-modifying work** (writes/edits to repo files, not just research), wrap the dispatch in a fresh `git worktree` so the main working tree stays clean until the parent verifies the diff. Research-only dispatches (read tool calls, web fetches, summary returns) skip this entirely.

### When worktree-wrap applies

✅ Subagent will Write / Edit / Bash-with-redirection on repo files
✅ Parallel subagents both touching the same repo (worktrees give per-dispatch isolation)
✅ Risky refactor where you want a clean rollback if the diff is wrong
❌ Pure research / audit / comparison (no file writes)
❌ Subagent runs in a different repo / external service / sandbox
❌ Single-file edits the parent could just do directly

### 4-step pattern

```bash
# 1. Parent creates worktree on a throwaway branch off current HEAD
DISPATCH_ID=$(date +%Y%m%d-%H%M%S)-$(openssl rand -hex 2)
git worktree add "sandbox/worktrees/$DISPATCH_ID" -b "subagent/$DISPATCH_ID"

# 2. Brief includes the worktree path. Subagent is told to operate ONLY there.
#    Add to the dispatch prompt:
#    "Working directory: sandbox/worktrees/<DISPATCH_ID>. Do not write outside this path."

# 3. After subagent returns subagent_return_v1.1, parent verifies the diff.
#    verify_subagent_diff.py uses time-based scope (--since + --claimed). Combine with
#    --scope pointing at the worktree dir for containment-aware checks.
DISPATCH_START_ISO="<ISO timestamp captured before step 1>"
python3 scripts/verify_subagent_diff.py \
    --since "$DISPATCH_START_ISO" \
    --claimed <files from subagent_return_v1.1.files_changed[].path> \
    --scope "sandbox/worktrees/$DISPATCH_ID"

# 4a. SUCCESS PATH. merge back to main, remove worktree
#     (If subagent_return_v1.1.exit_status == "success" AND verify passed AND
#     verification_hints.expected_test passes when run.)
cd sandbox/worktrees/$DISPATCH_ID && git add -A && git commit -m "subagent: <one-liner>"
cd - && git merge --ff-only "subagent/$DISPATCH_ID"
git worktree remove "sandbox/worktrees/$DISPATCH_ID"
git branch -D "subagent/$DISPATCH_ID"

# 4b. FAILURE PATH. archive for postmortem, discard from main
#     (If exit_status != "success" OR verify reports unexpected modifications.)
mkdir -p sandbox/archive/failed-worktrees/$DISPATCH_ID
cp -r sandbox/worktrees/$DISPATCH_ID/* sandbox/archive/failed-worktrees/$DISPATCH_ID/
git worktree remove --force sandbox/worktrees/$DISPATCH_ID
git branch -D "subagent/$DISPATCH_ID"
```

### Brief addition

In the dispatch prompt, after the standard sections, add:

```
WORKTREE: sandbox/worktrees/<DISPATCH_ID>
- All file writes MUST be under this path. Do NOT write to the main repo tree elsewhere.
- Your <files_changed> entries in the return contract should be ABSOLUTE paths under the worktree.
- If you need to read files outside the worktree (e.g., reference docs in memory/), Read them but never Write.
```

### What this contains

- **Blast radius**: a runaway subagent that writes wrong files corrupts only the worktree, not the main tree. `git worktree remove --force` is faster + safer than `git reset --hard`.
- **Parallel safety**: 2+ subagents on the same repo can't collide on shared files.
- **Audit trail**: failed dispatches archive to `sandbox/archive/failed-worktrees/` for postmortem instead of disappearing.
- **Verification loop**: pairs cleanly with `verify_subagent_diff.py`. verify before merge, not after.

### Cost

Worktree creation is ~50-200ms. Cleanup is similar. Net overhead per code-modifying dispatch: <1s. Worth it for any non-trivial multi-file write.

## Result handling

When a subagent returns, your job is NOT to relay its findings verbatim. The user doesn't see the agent's raw output. just your synthesis. So:

1. **Absorb the report**: extract the 3-5 facts that matter
2. **Synthesize in your own voice**: what does this mean for the user's task?
3. **Make the decision**: "based on this, I recommend X" or "we should not proceed because Y"
4. **Cite specifics**: file paths, line numbers, version numbers the agent found

Never say "the agent said X". you said X. You own the judgment.

## Common patterns

**Security audit**: new lib / repo / MCP → subagent does the github stars + last commit + contributor check + CVE scan + dep tree read. Returns "PROCEED / CAUTION / HARD-NO" verdict. You make the install call.

**Dedup check**: before building new infra → subagent greps codebase + reads contingency plans + checks if we already have it. Returns "duplicates X at path Y" or "net new, safe to build."

**Comparison research**: "should we use A or B" → subagent builds comparison matrix. You make the pick.

**Inventory scan**: "what's in memory/" "how many skills do we have" → subagent counts + categorizes + flags rot. You synthesize the diagnosis.

**Test harness**: "does feature X work?" → subagent builds minimal repro + runs it + reports pass/fail. You decide if the result is good enough to ship.

## Anti-patterns

❌ **Don't chain subagents for sequential work**. A→B→C in 3 subagents = 3× the latency of just doing it yourself.

❌ **Don't delegate understanding**. Never write "based on the research, implement it." Synthesis is yours.

❌ **Don't spawn agents for single-file reads** that you could do in one Read call.

❌ **Don't run subagents in a loop**. That's a cron job, not a subagent pattern.

❌ **Don't skip the `run_in_background: true` flag** when you have other work to do while the agent works. Blocking waits are wasted cycles.

## Budget reality check

Each subagent is ~5-20K tokens of compute. Weigh that against the alternative:
- Quick exploratory question: direct Glob/Grep is cheaper
- Deep research across 10+ sources: subagent wins every time
- Single decision that requires wide fact-finding: subagent wins
- Parallel N-way work: subagent wins N×

When in doubt, estimate the explore cost in main thread (how many reads / searches / web fetches): if it's >5 tool calls, delegate.
