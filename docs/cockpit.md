# Cockpit — a read-only window on the whole system

The system runs autonomously between sessions: scheduled jobs fire, watchdogs restart things, harvesters
ingest, counters tick. Without a single place to *see* that, it's a black box — you find out a job has been
silently failing for a week when something downstream breaks. The cockpit is that single place: a
**zero-dependency, read-only, localhost** dashboard that renders the system's current state as a grid of
panels.

Three constraints define it, and each is deliberate:

- **Zero-dependency.** It runs on the language's standard library alone — a stdlib HTTP server, no framework,
  no build step, no `node_modules`. A monitoring tool that itself needs a monitored dependency stack is a
  liability; the cockpit must be the thing that still works when other things don't.
- **Read-only.** It *displays* state, it never mutates it. There are no buttons that do things, no POST
  handlers, no write path. It's a window, not a control panel. This is what makes it safe to leave running:
  it has no state of its own to corrupt and can't be turned into an attack surface for changing the system.
- **Localhost-only.** Bound to the loopback interface, never exposed. No auth to get wrong because there's
  nothing to reach from off-box.

## Architecture — a registry of fail-isolated collectors

The cockpit is a list of **collectors** and a render loop. A collector is a small function that reads some
state and returns a fragment to display. The `PANELS` registry maps each collector to where it renders.

```python
# a collector: read some state, return a small render-ready fragment.
def c_ssot():
    keys = ssot_key_counts_by_namespace()     # read-only
    recent = ssot_recent_changes(limit=4)      # last 4 change-log rows
    return {"title": "SSOT · state", "rows": keys, "log": recent}

# the registry: title + which column + which collector. one row per panel.
PANELS = [
    ("Blocked on you", 1, c_blocked),
    ("Scheduled tasks", 1, c_schedule),
    ("SSOT · state",    2, c_ssot),
    ("Budgets / usage", 2, c_budgets),
    ("Recent errors",   3, c_errors),
    ("Session size",    3, c_session),
]

def render():
    for title, col, collector in PANELS:
        try:
            yield panel(col, title, collector())
        except Exception as e:
            yield error_tile(col, title, e)     # fail-isolated — see below
```

That's the entire model. Every panel is one collector plus one registry row.

## Fail-isolation — one broken collector never blanks the page

The most important property: **each collector is wrapped, and an exception becomes an error tile, not a blank
page.** If the scheduler DB is locked, the errors log is missing, or a collector throws, that *one* panel
renders an error tile with the exception — and every other panel renders normally.

This matters more than it looks. A dashboard that goes blank the moment one data source hiccups is worse than
no dashboard, because it fails exactly when you most need to see the *other* panels. Fail-isolation makes the
cockpit trustworthy under partial failure — which is the only time you're anxiously refreshing it.

It also turns the cockpit itself into a monitor: a panel showing an error *is signal*. **Absence is a
question, not an answer** — an empty "blocked on you" pane might mean nothing's blocked, or it might mean the
collector broke. The error tile disambiguates; a blank page hides it.

## "Add a monitor = one collector + one row"

The extensibility contract is the whole point of the registry shape. To surface something new:

1. **Write one collector** — a function that reads the state and returns a render-ready fragment.
2. **Add one row** to `PANELS` — its title, its column, and the collector.

No wiring, no template surgery, no touching the render loop. The render loop iterates the registry; a new row
appears as a new panel automatically. This keeps the barrier to observing a new thing low enough that you
actually do it, instead of letting a new subsystem run unwatched because instrumenting it was a project.

A collector's only contract is: **read-only, returns quickly, and is safe to throw** (the loop catches it).
It reads whatever it needs — a state store, a log file, a scheduler DB, a size helper — and hands back a
small structure the renderer turns into a tile.

## What the panels show (a starting set)

The cockpit is domain-agnostic; a reasonable default grid:

| Panel | Reads | Answers |
|---|---|---|
| Blocked on you | pending-approval / CONFIRM queue | "What is waiting on a human decision?" |
| Scheduled tasks | the scheduler store | "What's set to run, and did the last run succeed?" |
| SSOT · state | the state store + change-log | "What are the canonical values, and what changed recently, by whom?" |
| Budgets / usage | usage counters | "How close is any rate-limited resource to its ceiling?" |
| Recent errors | the error log | "What has failed since I last looked?" |
| Session size | the active-session helper | "How heavy is the running session?" |

Each is a handful of lines, each independent, each one registry row.

## Refresh model

Collectors run **at request time** — every GET re-reads the underlying state, so the page is always current
and there's no cache to invalidate or background poller to keep alive. Because the cockpit is read-only,
there's nothing to reconcile: it's a pure projection of whatever the state stores say right now. Keeping the
server itself up is a job for a small watchdog (the same pattern that keeps other long-running pieces
alive) — but the cockpit holds no state, so a restart costs nothing.

## Design principles

- **Zero-dependency on purpose.** The tool that watches everything else must not depend on everything else.
  Stdlib only.
- **Read-only, so it's safe to leave on.** No write path means no corruptible state and no attack surface.
- **Fail-isolated collectors.** One broken data source degrades one tile, never the page — and the error tile
  is itself a signal.
- **One collector + one row.** Adding a monitor must be trivial, or subsystems go unwatched.
- **Absence is a question.** An empty or errored pane is something to investigate, not a clean bill of health.

See also: `ssot.md` (the state and change-log the cockpit renders), `security-gates.md` (the approval queue
that feeds "blocked on you"), `session-management.md` (the session-size signal).
