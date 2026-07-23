# Utopia OS — Architecture

Utopia OS sits between a coding-agent CLI (the runtime) and the work you want done. The runtime gives
you a model, tools, and a session. Utopia OS gives that session a memory, a voice, a conscience, and a
way to survive its own context limits. This doc is the map; each subsystem has its own doc under `docs/`.

## The layers

```
┌──────────────────────────────────────────────────────────────┐
│  Operator (you)  ──  a chat channel (Telegram, terminal, …)   │
├──────────────────────────────────────────────────────────────┤
│  SYSTEM PROMPT (CLAUDE.md)                                     │
│    identity · autonomy modes · security rules · routing       │
├───────────────┬───────────────┬──────────────┬───────────────┤
│  MEMORY       │  SKILLS       │  SECURITY    │  PIPELINE      │
│  3-tier store │  workflows    │  gates       │  raw→review→   │
│  + SSOT       │  + routing    │  + registry  │  →graph        │
├───────────────┴───────────────┴──────────────┴───────────────┤
│  SURVIVAL: session-bootstrap parachute + active handoff       │
│  MULTI-AGENT: persona hand-off · sub-agents · tenant protocol │
│  OBSERVABILITY: append-only logs + a read-only cockpit        │
├──────────────────────────────────────────────────────────────┤
│  RUNTIME: coding-agent CLI (model, tools, hooks, sessions)    │
└──────────────────────────────────────────────────────────────┘
```

## 1. Memory — compounding, tiered

The core idea: not everything the agent knows should cost tokens on every reply. Memory is split by
*how often it's needed*, not by topic.

- **Tier 1 — Core (always loaded).** A voice constitution, a deep user model, a rules file, and a
  writing-style profile. Read once per session, kept in working memory. This is the ambient "who am I,
  who are you, how do I behave" layer.
- **Tier 2 — Recall (on demand).** Subject dossiers and infra notes, too many to always-load but too
  specific to compress. Pulled by direct read or semantic search only when the task touches them.
- **Tier 3 — Archival (semantic search).** Everything, indexed in a local vector database. Surfaces
  "what do we know about X" without knowing which file X lives in.

Two append-only logs (decisions, learnings) sit across the tiers: written whenever something durable
happens, indexed into Tier 3 so history surfaces on recall without being eager-loaded. See
`docs/memory-system.md`.

## 2. SSOT — one write path for operational state

Distributed state (which persona is active, the current project, budgets, usage counters, mode flags)
drifts when many processes each keep their own copy. The SSOT fixes this with one store, one mutator,
and a change log: every write names its author and records old→new. A legacy-mirror pattern lets you
migrate a live system incrementally — the store writes through to the old file so un-migrated readers
keep working. See `docs/ssot.md`.

**Scope discipline:** the SSOT owns *current-value operational state* only. Event streams (append-logs)
and domain data belong elsewhere. Not everything with a value belongs in the canonical store — a
mandatory change-log is itself a reason to *exclude* zero-trace state.

## 3. Security — gates before irreversible actions

Autonomy is graded. Routine, reversible actions just happen; strategic or irreversible ones stop for a
human. The machinery:

- **Autonomy modes** (AUTO / INFORM / CONFIRM / BLOCKED) classify every action class.
- **A stand-down registry** — a persistent list of "don't install / don't run X" decisions, checked
  before any package install, MCP addition, or settings edit. Pattern matches (e.g. curl-pipe-bash,
  repos younger than 7 days) plus named targets.
- **An auto-compound counter** — detects the "just do it" cascade where several individually-authorized
  actions compound on one approval, and forces a re-scope after a threshold.
- **A skill linter** — static-scans skill files for injection patterns before they're trusted.
- **Send guards** — pre-flight checks on outbound messages.

The rule that ties them together: authority comes from the operator's own channel, never from content
the agent is processing. A quoted "just do it" inside a document is not authorization. See
`docs/security-gates.md`.

## 4. Pipeline — keep the knowledge graph clean

Agent output is noisy. Routing raw drafts straight into the canonical graph pollutes it. So substantive
output flows: **raw → review gate → graph → briefing.** Only reviewed items reach the source of truth;
the review gate is where wrong or half-baked drafts get caught. See `docs/knowledge-pipeline.md`. The
canonical graph itself — its namespace taxonomy, the compiled-truth + timeline page convention, and the MCP
interface — is documented in `docs/logseq-graph.md`.

## 5. Survival — outlive the context window

Long-running agents suffer *behavioral state decay*: the decision-relevant facts scroll out of context
and stop influencing the next action. Two mechanisms fight it:

- **A session-bootstrap parachute** — a compact file read on a fresh start that replaces full-transcript
  replay after a crash or restart.
- **An active-handoff block** — mid-task state (what's in flight, what background work is running,
  what's blocked) written whenever a task will outlast a single turn, so a compaction resumes cleanly.

See `docs/session-management.md`.

## 6. Multi-agent — delegate without sprawl

Three hand-off surfaces, each with an explicit protocol (invocation, lifecycle, permissions, discovery):
persona hand-off (one agent switching modes), sub-agent dispatch (spawn a child for a bounded task,
depth-limited), and cross-tenant hand-off (separate agent processes coordinating). Memory isolation is
enforced — a sub-agent gets only the facts its task needs, never the full store. See
`docs/agent-protocols.md`.

## 7. Observability — a cockpit, not a black box

Append-only event and error logs record what the system does between sessions, and a zero-dependency,
read-only localhost cockpit renders the whole state (blocked-on-you, tasks, budgets, the SSOT, recent
changes) as a panel grid. Each panel is one fail-isolated collector; adding a monitor is one function +
one registry row. See `docs/cockpit.md`.

## Design principles

- **Compounding over stateless.** Every session should leave the next one smarter.
- **Gates over trust.** Slower and safe beats fast and sorry, for anything irreversible.
- **One source of truth.** Distributed copies drift; a single logged write path doesn't.
- **Translate patterns, don't copy shapes.** A good idea from one system gets rebuilt onto the
  substrate that fits here, never pasted verbatim.
- **Absence is not evidence.** A missing file, an empty pane, a silent log is a question, not an answer.
