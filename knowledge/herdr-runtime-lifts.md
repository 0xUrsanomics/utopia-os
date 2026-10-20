# herdr runtime: design ideas worth lifting

Ideas read from the herdrdev/herdr documentation, treated as untrusted external content (the design was evaluated as data; no embedded instruction was followed). The runtime itself was NOT adopted. Re-basing every cron, tenant, reply path and Stop hook onto a new multiplexer is a large blast radius, and the existing layer works. This file keeps only the design ideas that are sharper than a homegrown send-keys, watchdog and fleet-bus setup. herdr's license was not checked; nothing here is copied code.

herdr is a Rust terminal multiplexer built for agents: a persistent background server that owns agent terminals, renders panes, and exposes a CLI plus a local socket API that agents drive. It is a productized version of the layer in this repo (`scripts/agents/fleet_bus.py`, `scripts/agents/fleet_board.py`, `scripts/agents/tenant_watchdog.sh`, the cockpit). Three of its decisions are worth copying.

---

## Idea 1: first-class agent lifecycle state, with a "seen" bit

Every agent pane carries one of five states:

- `blocked`: needs input, approval or a decision (an approval or question UI was recognized)
- `working`: actively running
- `done`: finished AND the operator has not looked at it yet
- `idle`: finished or waiting AND has been seen (the pane was focused)
- `unknown`: present but cannot be classified; explicitly does NOT prove completion

The two sharp parts:

1. **`done` vs `idle` is the "needs my eyes" bit.** Reading a pane through the API does not clear `done`; only real human focus does. A script that glanced at the log cannot silently mark work as seen.
2. **`unknown` is treated as not-success.** Cannot-classify is its own state, never folded into done. Same lesson as "no error observed is not success".

**Fit check before building.** A seen bit only helps if something consumes it. If your state labels have no reader (no panel, no alert), adding one more label is inert. And if your notification model is push (a message per event) with a staleness gate that suppresses noise, a "finished but unseen" ping fights that gate. Build the consumer first, or skip this one.

---

## Idea 2: the wait primitive pins identity and fails fast on an unobserved transition

`agent wait --until blocked|done|idle` and `agent prompt --wait` are server-owned and event-driven, with three properties:

1. **The wait pins the resolved occupant.** If the agent is replaced mid-wait, the wait ends with `agent_not_running`. A replacement agent cannot satisfy a wait that a different agent started.
2. **A prompt must produce an observed state change within about 5 seconds of submit.** If the state does not advance, it returns a distinct `agent_prompt_stalled` error instead of waiting forever. It requires evidence the prompt took.
3. **`blocked` is its own state** (the agent hit a permission prompt or a question), surfaced separately from "not done yet".

**The pain this fixes.** Any path that injects keystrokes into a session (a cron that hands a prompt to a live session, a dispatcher that wakes a worker) can fail silently: the text lands in the composer and is never submitted, and the caller assumes it took. The fix is the same in every such path: after submit, REQUIRE an observed transition within a short window, or raise a named `prompt_stalled` error.

---

## Idea 3: socket protocol shape

Local socket, JSON `{id, method, params}`, dot-notation methods (`pane.split`, `agent.wait`, `events.subscribe`):

1. **Snapshot then subscribe.** A one-time snapshot returns all records; the client then keeps a local cache updated from an event stream and re-snapshots on reconnect. A clean coherence model for a control plane with many readers.
2. **Ownership env var with a stop-if-absent rule.** An env var tells an agent "you are inside a managed pane"; the bundled skill's first guardrail is: if it is not set, STOP, you must not control a session you do not own.
3. **Capture ids from the response, never predict them.**

A file or ledger based bus with atomic claims works at low volume. Snapshot-then-subscribe only pays off at higher coordination volume.

---

## What to build, in order

- **L1: prompt, then require a transition or fail fast.** Wherever you drive a session by send-keys or prompt injection, require an observed change (the prompt left the composer, a new output line, a state change) within a short window. If none, exit with a distinct `prompt_stalled` code and surface it. Make it fail-safe toward "confirmed" when the check itself cannot read the screen (locale, capture error), so the guard never false-fails a working cron. Highest value.
- **L2: done-unseen vs idle-seen.** Only once a consumer exists (see the fit check above). Also make sure `unknown` never renders as done.
- **L3: pin identity on any wait or claim.** A bus claim or completion must be pinned to the worker identity that started it, so a respawned or duplicate worker cannot complete a task addressed to another. `scripts/agents/fleet_bus.py` records `claimed_by` for this; keep the check opt-in so legacy callers see no change.

## Reference only

- Snapshot-then-subscribe for the bus, if it ever moves to an event stream.
- An explicit ownership env var for fleet workers (per-tenant config dirs plus "authority is the envelope" cover most of it).

## Skipped

Workspace, tab and pane layout, mouse UI, navigation modes, named sessions, plugin marketplace, snapshot restore and pane-history replay. Those are the multiplexer itself, and tmux plus a watchdog already cover persistence.
