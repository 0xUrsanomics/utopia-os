# SSOT — one write path for operational state

Operational state is the small set of fast-changing facts the whole system reads to decide what to do:
which persona is active, what the current project is, how much of a rate-limited budget is left, which
autonomy mode is set, whether a background watchdog is healthy. In a single-process script this is a
variable. In a real system — cron jobs, a fleet of agent processes, an interactive session, all running
at once — it is scattered across a dozen little files, each written by a different script, and it
**drifts**. Ask two processes "what mode are we in" and get two answers.

The single source of truth (SSOT) fixes that with three commitments:

1. **One store.** All operational state lives in one embedded database.
2. **One mutator.** A single `set()` function is the only thing allowed to change state.
3. **Every write is logged** — old value → new value, with an author and an optional reason.

That's the whole design. Everything else is discipline about *what belongs in it*.

## The store and the API

```
memory/state/ssot.sqlite      one embedded DB, WAL mode → concurrent-safe across
                              cron + fleet + interactive readers and writers
scripts/memory/ssot.py        the only sanctioned interface
```

```
ssot get   <key>                       → current value
ssot set   <key> <value> --by <author> [--reason <text>]   → the ONLY mutator
ssot dump                              → every canonical key + value
ssot log   [<key>]                     → the change history
ssot import-scattered                  → one-time pull of legacy files into the store
ssot self-test                         → negative controls (see below)
```

Rules the store enforces, not merely documents:

- **`set()` is the only mutator.** Nothing else writes state. One reducer, one code path to reason about.
- **Every `set()` logs the transition.** `(key, old, new, author, reason, timestamp)` is appended to a
  `state_log` table on every change. A no-op write (new == old) does not spam the log.
- **Anonymous writes are refused.** No `--by`, no write. State changes are attributable by construction.
- **Non-namespaced keys are refused.** Keys are dotted (`persona.active`, `project.active`,
  `budget.config`, `usage.<api>`, `mode.driving`). The namespace is the schema.

### The change log is the feature

The `state_log` is not bookkeeping you tolerate — it is the reason the store is trustworthy. It answers
"who set this, to what, when, and why" for every value in the system, and it has a habit of paying for
itself: the first time a test run clobbers a real counter, you restore the pre-test value straight from
the log instead of guessing.

```
state_log
  ts                    key            old      new      author            reason
  2026-…T09:14:07Z      mode.driving   off      on       driving-skill     operator toggled
  2026-…T09:31:52Z      usage.maps     41       42       maps-hook         geocode call
  2026-…T10:02:11Z      persona.active ranger   coach    persona-switch    keyword + confirm
```

## Legacy-mirror — migrating a live system without a big bang

You almost never get to build the SSOT before the scattered files exist. You build it *into* a running
system that already has thirty writers pointed at thirty files. Rewriting all of them at once is how you
break production. The migration is incremental, and one primitive makes it safe:

**On every `set()`, the store also writes the value back to the legacy file it's replacing.** So a reader
that hasn't been migrated yet still finds a current value in the old place. The store becomes authoritative
while nothing downstream breaks. The cost is one extra file write per `set()` — cheap, and for keys with
crash-safety requirements the mirror uses an atomic write (write-temp-then-rename) so a mirrored counter
never tears.

The order of operations:

1. **Repoint readers first.** Every consumer that read the old file now calls `ssot get <key>`. The legacy
   file is kept live by the mirror, so this step is invisible and reversible.
2. **Repoint writers one at a time.** Each script that used to write the old file now calls `ssot set`,
   with a graceful fallback to its original write if the store import fails. Verify each writer end-to-end
   before moving to the next.
3. **Retire a legacy file only when nothing touches it.** A file is dead only once grep proves no reader
   and no writer reference it. Until then the mirror keeps it honest.
4. **Track progress in the store itself.** `ssot dump` shows what's canonical; a file still written by a
   legacy script simply isn't migrated yet.

The discipline that makes this work: **do not rush a live migration**. A large repoint under context or
time pressure is exactly when a working behavior gets silently broken. Migrate the hottest keys first,
verify each, and let the long tail move on demand rather than pre-emptively.

## Scope — what the SSOT owns, and what it must never absorb

The SSOT owns **current-value operational state** and nothing else. This boundary is the most important
part of the design, because a single canonical store is seductive — the temptation is to put *everything*
in it, which quietly recreates the coupling the store was meant to remove.

| Belongs in the SSOT | Belongs elsewhere | Why |
|---|---|---|
| Active persona, active project | The knowledge corpus (`memory/*.md`) | Prose knowledge is versioned text, not a keyed value. |
| Budgets, usage counters, mode flags | Embeddings / the vector index | A derived index rebuilds from source; it isn't state of record. |
| Watchdog health, session bookkeeping | Message/event streams (append-logs) | Streams are history, not current value. |
| — | Scheduler / cron definitions | Their own store with its own schema. |
| — | Domain data (a namespaced prefix at most) | Partition it (`domain.*`) if it must be co-located; never merge it into ops. |

Two exclusion rules earn special mention because they run against the "one tree" instinct:

- **Event streams stay out.** An append-only log (a message bus, an audit stream) is a *history* of
  events, not a *current value*. Forcing it into a keyed store is cargo-culting the idea of centralization
  onto data that has a different shape.

- **A mandatory change-log is itself a reason to *exclude* zero-trace state.** Some state is contractually
  supposed to leave no trace — an incognito / "off the record" mode whose entire promise is that nothing
  persists. That flag **cannot** live in the SSOT, because the SSOT logs every write forever. Putting a
  zero-trace flag into a store that records `mode.incognito → on` at a timestamp would silently break the
  guarantee it represents. It stays a direct-write flag, outside the canonical store, for the same reason
  the append-logs do: the store's own invariant disqualifies it.

That second rule is the subtle one. The SSOT's strength — total auditability — is precisely what makes it
the wrong home for anything whose correctness depends on *not* being auditable. The boundary isn't drawn by
what's convenient to centralize; it's drawn by which invariants each piece of state actually needs.

## Design principles

- **One store, one mutator, one log.** Every operational value has a single home, a single write path, and
  a recorded history. Drift becomes structurally impossible.
- **Attribution by construction.** No anonymous writes, no un-namespaced keys. The schema and the audit
  trail are enforced, not requested.
- **Mirror, don't cut over.** A live system migrates incrementally behind a write-through mirror; a
  big-bang cutover is how you break it.
- **Centralize current value, not everything.** Event streams, domain data, derived indexes, and zero-trace
  flags each have a reason to live outside. The change-log is a filter as much as a feature.

See also: `security-gates.md` (the counters and mode flags the SSOT stores are read by the gates),
`cockpit.md` (renders the SSOT and its recent change-log as a panel), `memory-system.md` (the knowledge
corpus, which is deliberately *not* in the SSOT).
