# Agent Protocols — delegating without sprawl

Multi-agent coordination is where systems quietly rot. It usually starts as prose in the system prompt —
"when you switch personas, save the previous one's state"; "when you spawn a helper, brief it well" — and
prose drifts. The rules get vaguer, the hand-offs get sloppier, and eventually a sub-agent inherits the full
memory it shouldn't have or a delegation spawns delegations three levels deep.

The fix is to treat each hand-off as a **protocol with a machine-readable contract** rather than a habit. The
system has three coordination surfaces, and each is specified along the same four dimensions:

- **Invocation** — how the hand-off is triggered and what travels with it.
- **Lifecycle** — the states it moves through, and how each state is observable.
- **Permissions** — what the receiving party may and may not do.
- **Discovery** — where the participants and their capabilities are registered.

Specifying all three surfaces the same way keeps memory (what knowledge transfers), skills (how the receiver
executes), and protocol (the envelope + lifecycle + permissions) separate — which is what makes the whole
thing auditable.

---

## Surface 1 — Persona hand-off (one agent, switching modes)

A persona is a mode the same agent runs in: a default operations persona, a specialist persona for a
particular domain, and so on. One is active at a time.

**Invocation.** Triggered by an explicit command (`/persona <slug>`), a natural-language match ("switch to
<mode>"), a keyword *hint* (domain keywords suggest a switch), or session resume (the active-persona state
says which). What carries across: the active project, the last operator message, any in-flight task
reference, and the user-state flags.

**Lifecycle.** `triggered → accepted` (the target persona has a memory file) `→ active` (the active-persona
state is updated and the target's brief is loaded) `→ completed` (back to the default). Observable via the
active-persona state file's timestamp and a persona-switch event in the session log.

> **Never auto-switch on a keyword alone.** A keyword hint raises a *suggestion* ("this looks like <mode>
> territory — switch?") and waits for an explicit nod. Suggest once per thread; if ignored, don't nag.

**Permissions.** Only the operator invokes a hand-off — from their own channel (see `security-gates.md`).
Each persona reads and writes **only its own** memory sidecar (`memory/personas/<slug>.json`); the shared
Tier-1 procedural layer (voice, operator model, rules) is **read-only** to every persona. Voice and safety
inheritance (anti-slop, sycophancy guard, security-first) auto-loads to all personas — a persona defines only
what *differs* from the default.

**Discovery.** Active slug in `memory/state/` (defaulting to the base persona); persona definitions in
`skills/personas/<slug>.md`; per-persona memory in `memory/personas/<slug>.json`; trigger keywords declared
inline in each persona's own file, so they stay colocated with the persona they trigger.

---

## Surface 2 — Sub-agent dispatch (spawn a child for a bounded task)

When a task needs heavy independent exploration — many unrelated file reads, a large repo audit, parallel
queries — the agent spawns a **child** with a fresh context, so the orchestrator's own context stays lean.

**Invocation (the briefing grammar):**

```yaml
type: subagent_dispatch
parent: <the orchestrator>       # depth-2 max — see the hard rule below
child: fork | named:<agent_type>
task: <one-sentence ask>
budget:
  max_tokens: <estimate>         # warn past a ceiling
  max_wall_time: <minutes>
  forbidden_tools: [remove-file, force-push, confirm-gate-writes, ...]
context_payload:
  paste_ins:   [<path:lines>, <inline fact>]   # only what the task needs
  task_context: <2-3 sentences: why this matters, the surrounding problem>
  not_in_scope: [<explicit exclusions>]
return_shape:
  format: structured            # a verifiable contract, not freeform prose
```

**The return contract.** Every dispatch requires a structured return the parent can *verify*, not a prose
summary it must trust:

```yaml
summary: <verdict + key facts, not a transcript>
exit_status: success | partial | failure
files_changed:                  # exhaustive — every file the child touched
  - {path, action, lines_added, lines_removed, purpose}
verification_hints:
  diff_command: <how the parent independently checks the change>
  expected_test: <a command that should pass, or null>
  expected_signal: <a string the parent can grep for, or null>
findings: [...]                 # for research tasks
recommendations: [...]          # parent decides whether to act
context_used: [...]             # every source the child read
```

**Lifecycle.** `briefed → dispatched → running` (parent backgrounds it, doesn't poll) `→ returned → verified`
(parent reads the diff/files to confirm intent matched output) `→ merged`. Verification is not optional:
the child's summary describes what it *intended*; the parent confirms what actually changed before reporting
"done."

> **Two hard rules.**
> **Max depth 2** — the parent spawns a child; the child must **not** spawn grandchildren. Never brief a
> child to "delegate further." If a child finds it needs more parallelism, it returns that finding and the
> parent decides. Recursive delegation explodes cost and hides failure modes behind a summary of a summary.
> **Trust the summary, verify the diff** — the parent's job is verification, not blind acceptance.

**Permissions.** The child inherits the parent's filesystem access (no escalation) but **not** the operator
channel — only the parent can message the operator. A forbidden-tools denylist travels with the briefing
(destructive commands, force-push, CONFIRM-gate writes); for those the child must escalate to the parent.
And **memory isolation** (below) is enforced.

**Discovery.** Available child types come from the runtime's agent schema; per-agent capabilities live in the
agent definition files. A soft cap keeps concurrent children to a handful.

---

## Surface 3 — Cross-tenant hand-off (separate agent processes)

Distinct agent processes — separate identities, separate channels, sharing a workspace — sometimes need to
route work between each other.

**Invocation.** Triggered when the operator directs a specific tenant ("@<tenant> do X"), when a scope
classifier routes a request, or when a shared state block flips. The payload carries the originating message
id (for traceability), the query, the context already read (to avoid re-fetching), and the conversation
thread reference.

**Lifecycle.** `routed → acknowledged → processing → replied → logged`. Routing is **soft**: both tenants may
see the inbound message, but only the routed one replies; the other stays silent. The **source of truth for
"who replies" is the scope classifier** — one component owns the routing decision so two tenants never both
answer or both stay quiet.

**Permissions.** Each tenant writes only its own namespace. Shared blocks (active persona, active project)
are last-writer-wins under a file lock, with the change recorded so "who wrote what when" is answerable.
Outbound messaging is identity-bound: each tenant can message only through its **own** channel credential —
no tenant can spoof another's identity. (This is the envelope rule from `security-gates.md`, applied between
agents.)

**Discovery.** A tenant registry names each participant and its channel identity. Early on these can be
hard-coded; the growth path is a declarative registry per tenant plus a routing decision log for audit and
replay.

---

## Memory isolation (cross-cutting)

A sub-agent or a peer tenant gets **only the facts its task needs — never the full store.** Two reasons:

1. **Cost.** A child already starts with a fresh context; smuggling the entire operator model and memory
   into its briefing re-pays for context the task doesn't use.
2. **Trust.** A child reasons on its briefing alone. It should not carry the same trust level as the main
   session for interpreting the operator's preferences and decisions — so paste the *specific* file path or
   fact the task requires, not "here is everything we know about the operator."

The discipline: brief the minimum. If a task genuinely needs a piece of the operator model, paste that piece.
The default is exclusion, and the briefing is the entire trust boundary.

## Design principles

- **Contracts over habits.** A machine-readable schema per surface resists the drift that prose coordination
  rules suffer.
- **Separate memory, skills, and protocol.** What transfers, how the receiver executes, and the envelope are
  three different concerns — keeping them apart is what makes hand-offs auditable.
- **Bound the depth.** Delegation stops at depth 2. No grandchildren, ever.
- **Verify the diff.** A returned summary is a claim; the parent confirms it against the actual changes.
- **Brief the minimum.** Memory isolation is the default — the briefing is the whole trust boundary, so it
  carries only what the task needs.
- **Don't over-formalize.** For a small fleet, a short schema per surface is enough; a protocol heavier than
  the coordination it governs is its own failure.

See also: `security-gates.md` (the envelope rule and forbidden-tool lists), `session-management.md` (when to
delegate vs. keep work in the main context), `ssot.md` (the shared state blocks tenants coordinate on).
