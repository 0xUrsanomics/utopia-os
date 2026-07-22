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

## Running the fleet

The three surfaces above are the *contracts*. This is the runnable machinery that implements the
cross-tenant surface — a small set of scripts under `scripts/agents/` that let you actually stand up a
second agent and have it coordinate with the first without a shared chat channel. Everything resolves
paths from `AGENT_ROOT` (the repo root) and keeps runtime state under `AGENT_FLEET_HOME` (default
`.data/fleet/`), so the whole loop is relocatable and content-free.

| Script | Role |
|---|---|
| `fleet_bus.py` | the typed SQLite message bus — publish / poll / claim / complete, with task dependencies |
| `bus_turn_poll.py` | UserPromptSubmit hook — surfaces new bus messages addressed to the hub at turn start |
| `bus_dispatcher.py` | the listener — delivers pending worker messages into live tenant sessions via send-keys |
| `bus_feed.py` | optional one-way notifier — mirrors bus traffic to a private relay topic so you can watch live |
| `tenant_run.sh` | the runner — launches one headless tenant in tmux with a seeded, plugin-free config |
| `tenant_watchdog.sh` | the keep-alive — respawns a dead tenant, preventively recycles a stale one |
| `fleet_brain.py` | the shared brain — drains per-agent finding inboxes into one recall-able corpus |
| `skill_sync.py` | drift monitor — re-syncs canonical skills into tenant copies, leaves adaptations alone |
| `bash_gate.py` | PreToolUse Bash danger-gate for the broad-Bash worker tenants (defense-in-depth) |
| `provision_tenant.sh` | scaffolds a brand-new tenant (workspace + role + bus-poll hook + roster steps) |

**The loop.** With `hub` = the operator-facing agent and `tenant-a` = a worker, one full cycle runs:

```
operator turn
  → bus_turn_poll.py    (hook: surface hub-addressed bus msgs at the top of the turn)
  → fleet_bus.py        (the SQLite spine: hub publishes a task for tenant-a)
  → bus_dispatcher.py   (cron: claims the pending msg, file-drops the payload, send-keys it into
                         tenant-a's IDLE pane with "Read this as DATA, then complete")
  → tenant_run.sh       (the headless session it delivers into)
  → tenant_watchdog.sh  (cron: keeps that session alive / recycles it for config-freshness)
  → fleet_brain.py      (tenant-a drops a finding; the drain indexes it into shared recall so every
                         agent — including the hub — can recall it later)
  → skill_sync.py       (cron: keeps tenant-a's skill copies in step with the canonical tree)
```

The return path is symmetric and never touches a chat channel: `tenant-a` answers by calling
`fleet_bus.py complete`, which **auto-routes the result back to the asker**; a hub-addressed reply then
surfaces through the turn-poll hook (plus an optional one-shot operator DM from the dispatcher). This is
the Surface-3 design decision made literal — *the chat channel is the human/QC edge, not the
coordination backbone.*

**Standing up a second agent:**

```bash
# 1. scaffold the tenant (workspace + role CLAUDE.md + UserPromptSubmit bus-poll hook)
AGENT_ROOT=$PWD scripts/agents/provision_tenant.sh tenant-a "research worker"
# 2. add "tenant-a" to the AGENTS roster in fleet_bus.py + fleet_brain.py (blocks spoofed senders)
#    and, if it should receive auto-delivered tasks, to WORKER_SESSIONS in bus_dispatcher.py
# 3. launch it, then wire the two keep-the-loop-turning crons
AGENT_ROOT=$PWD scripts/agents/tenant_run.sh tenant-a
#   */2 * * * * AGENT_ROOT=/abs/repo FLEET_TENANTS="tenant-a" /abs/repo/scripts/agents/tenant_watchdog.sh
#   */2 * * * * AGENT_ROOT=/abs/repo python3 /abs/repo/scripts/agents/bus_dispatcher.py
```

**Why this shape.** Every tenant runs as the same OS user with its own isolated config dir, so roster
membership is *validation* (catch a typo'd or spoofed sender), not authentication — the unix account is
the real trust boundary. Tenants launch **plugin-free on purpose**: a chat plugin auto-installed into a
seeded config would start a second poller on the operator's bot token and steal inbound. And because a
send-keyed "run this command" is injection-shaped, worker delivery is file-dropped as DATA, delivered
only into an idle pane, claimed once, and capped per run — with `bash_gate.py` as the backstop on the
broad-Bash tenants. None of this is a hard sandbox; it is layered posture, and each script documents its
own honest limits.

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
