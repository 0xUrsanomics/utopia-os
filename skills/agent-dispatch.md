---
name: agent-dispatch
trigger: dispatch, delegate, subagent, spawn agent, route task, agent-route
description: Domain-aware subagent dispatcher. Maps task → domain (research / build / draft / verify / ops) → recommended subagent_type + tool boundaries + briefing scaffold. Adapted from a phase-based activation pattern.
type: orchestrator
---

# agent-dispatch

Right subagent, right tools, right brief. Pull from the domain registry. don't freestyle.

## When to invoke

About to spawn an Agent AND:
- Task is non-trivial (>3min inline, or 3+ files / 5+ commands per the delegation threshold)
- Fits one of the 5 domains below

Skip dispatch (do inline) if: <3min, depends on active session state, or multi-turn user conversation.

## The 5 domains

Read `memory/Infra/agent-phase-domains.json` (canonical schema). One-line cheat sheet:

| domain | purpose | subagent_type | writes? |
|---|---|---|---|
| **research** | doc-mining, repo audits, web research, codebase exploration | `Explore` | ❌ read-only |
| **build** | code-writing: skills, scripts, configs | `general-purpose` | ✅ filesystem (scope-limited) |
| **draft** | creative content: proposals, briefs, posts, decks | `general-purpose` | ✅ outputs/raw/ only |
| **verify** | smoke tests, validation, audits, output QA | `general-purpose` | ❌ read+exec only |
| **ops** | routine operations: status progression, follow-up, briefings, triage | `general-purpose` | ⚠️ outputs/ only, NO external writes |

## Dispatch flow

1. **Classify** the task. Pick ONE domain. If it spans 2+, decompose into separate subagent calls (one per domain): don't blend.
2. **Load** the domain entry from `agent-phase-domains.json`. Pull: `recommended_subagent_type`, `tools_denied`, `briefing_scaffold`.
3. **Brief** using the scaffold. Fill EVERY placeholder. Don't skip "stack context (paste-in)". subagents have no transcript memory.
4. **Constrain**: explicitly include the `tools_denied` list as "Hard rules: do NOT use these tools" in the briefing. Subagents can't read the schema, you have to inline the rules.
5. **Dispatch** via the Agent tool with `subagent_type` = the recommended one.
6. **Verify the diff** on return. Subagent wrote files? Read them. Don't trust the summary blind. that's the "trust the summary, verify the diff" delegation rule.

## Briefing template (universal)

Every brief answers 6 questions. Domain scaffolds in the JSON add 3-4 domain-tuned lines on top.

1. **Goal?** (one sentence)
2. **Why?** (why this task exists. the subagent has no transcript)
3. **What's known / ruled out?** (don't re-discover)
4. **Scope?** (specific files/paths/questions, NOT "investigate X area")
5. **Out of scope?** (denylist)
6. **Success criteria?** (output format, length budget, pass test)

## Hard rules (inherit from delegation discipline)

- **Max depth = 2.** The parent (this session) can spawn ONE child via the Agent tool. The child must NOT spawn further Agent calls. When briefing, NEVER write "spawn N more agents" or "delegate to other agents" in the prompt.
- **Memory isolation.** Don't paste full memory dumps. Paste the SPECIFIC fact/file path the subagent needs.
- **No MCP write tools in subagents.** The parent owns external writes (chat, spreadsheet, knowledge graph). Always.
- **Verify diffs on return.** Read changed files, don't blindly accept summary text.
- **Skip dispatch for <3min tasks**: overhead exceeds value.

## Anti-patterns (from agent-phase-domains.json)

- ❌ Pasting the full voice constitution / user model into a draft subagent. Paste the specific voice rules + anti-AI-slop subset relevant to the piece.
- ❌ Letting a research subagent edit files. They report findings, the parent writes the reference page.
- ❌ Blending build + verify into one subagent. Build, return the diff, dispatch verify separately if needed.
- ❌ Allowing an outbound-message tool in a draft/build/ops subagent. They write to outputs/, the parent decides if it goes external.

## Example dispatches

### research domain. repo doc-mine
```
subagent_type: Explore
brief includes:
  - Goal: "Deep-mine github.com/X/Y for 5 specific patterns"
  - Stack context: paste the relevant 5-10 lines of your existing infra
  - Specific files to read: explicit URLs/paths
  - Output format: structured markdown with file path + line range cites
  - Tools denied: Edit, Write, npm/pip install, subagent spawning
```

### build domain. new script
```
subagent_type: general-purpose
brief includes:
  - Goal: "Build scripts/foo.py that does X"
  - Files to read first (existing patterns to mirror): list
  - Smoke-test command: single bash invocation
  - Out-of-scope: don't touch skills/, don't add MCP wiring
  - Tools denied: external-write MCP tools, schedule_create
```

### verify domain. output QA
```
subagent_type: general-purpose
brief includes:
  - Goal: "Smoke-test outputs/raw/agent/<file>.md against the rubric"
  - Pass criteria: explicit checks (frontmatter present, no slop phrases, links resolve)
  - Output: pass/fail + line cites for each failure
  - Tools denied: Edit, Write, all MCP writes (verify never mutates)
```

### ops domain. status-progression routine
```
subagent_type: general-purpose
brief includes:
  - Goal: "Run a status-progression check on active items"
  - Data sources: explicit knowledge-graph paths + spreadsheet ranges
  - Output destination: outputs/raw/agent/status-<date>.md
  - CONFIRM-gate flags: any terminal-state candidates require the parent's confirmation BEFORE a knowledge-graph edit
  - Tools denied: outbound message, spreadsheet update, knowledge-graph create (parent writes external)
```

## Logging

Log the dispatch + verification outcome to `logs/session.jsonl`:
```json
{"ts":"<ISO>","persona":"default","category":"agent-dispatch","event":"dispatched","domain":"research","subagent_type":"Explore","verified":true}
```

Verified = the parent read returned files / confirmed claims / accepted the summary. If `verified=false`, also log the discrepancy.

## Cross-references

- `memory/Infra/agent-phase-domains.json`: canonical schema (this skill reads it)
- `memory/Infra/agent-protocols-v1.md`: the broader agent protocol (3 surfaces: persona handoff / subagent briefing / cross-bot handoff)
- The system prompt's `# Session Self-Regulation` → Delegation threshold + Delegation discipline (3 hard rules)

## Adoption

Opt-in. Use for: repo audits, multi-step research, ops routines with a pattern (status-progression, follow-up). Skip for: trivial inline work, multi-turn conversation, single-file ops.
