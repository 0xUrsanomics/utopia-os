# Knowledge Pipeline — keep the canonical graph clean

The agent produces a lot of text: research memos, plans, drafts, signal scores, meeting notes. Some of it
is good. Some of it is confidently wrong, half-baked, or duplicated. The canonical knowledge graph — the
store that later gets queried as *fact* — is only as trustworthy as the worst thing allowed into it. If raw
drafts flow straight in, the graph stops being a source of truth and becomes a junk drawer that happens to
be searchable.

So substantive output flows through a gate. Four layers, one direction:

```
  WORK ──────────► REVIEW ──────────► GRAPH ──────────► BRIEF
  raw drafts       approve / flag /   only reviewed      what got
  auto-saved       discard            items, tagged      approved, fed
  with provenance                     with provenance    to next session
       │                │                                     ▲
       │                └── discarded → archive (not deleted) │
       └─────────────────────────────────────────────────────┘
                     the loop that compounds
```

## Layer 1 — WORK: capture raw, don't trust it yet

When the agent produces **substantive output**, it is auto-saved to a raw staging area
(`outputs/raw/<persona>/YYYY-MM-DD-<slug>.md`) with frontmatter recording who produced it, when, and what
it is. This happens *before* the agent replies — capture is cheap and losing good work is expensive.

"Substantive" is a real filter, not everything: research memos, plans, proposals, drafts, structured notes,
scored analyses. **Not** quick answers, casual chat, or one-off lookups. The raw layer is a holding pen —
saved, timestamped, but explicitly **not yet trusted**.

## Layer 2 — REVIEW: the gate

A review step evaluates raw items and routes each to one of three fates:

- **Approve** → moves to `outputs/reviewed/`, cleared for the graph.
- **Flag / merge** → needs edits or should be folded into an existing entry; back for rework.
- **Discard** → moved to an archive of discarded items — **archived, not deleted**, so a rejected draft can
  be revisited and a bad call can be reviewed.

This is the layer where wrong, stale, or duplicative drafts get caught. It is deliberately a *separate step*
from producing the work: the same context that wrote a draft is the worst judge of it, and a gate the author
walks through on the way out is where quality is actually decided.

## Layer 3 — GRAPH (BRAIN): only reviewed items become canonical

Only items that passed review are written into the canonical knowledge graph, and every entry is tagged with
its **provenance** (`source/<persona>`, a date, the originating raw file). Provenance is not decoration: when
a graph entry later surfaces on recall, you need to know whether it came from a vetted memo or an
experimental draft, and which review pass cleared it. Untagged knowledge is unfalsifiable knowledge.

## Layer 4 — BRIEF: close the loop

Approved knowledge is distilled into per-persona briefings, read on session start and on persona switch.
This is the step that makes the pipeline *compound* rather than merely *accumulate*: the next session opens
already knowing what the last one concluded, instead of re-deriving it. Without the brief loop the graph
grows but the agent doesn't get smarter; with it, every approved item raises the floor for the next run.

## Why raw drafts must never hit the graph directly

It's worth stating the failure mode plainly, because "just write it to the graph" always looks simpler:

1. **The graph is read as truth.** It's the substrate the archival index embeds and recall retrieves. A
   wrong entry there doesn't sit quietly — it gets surfaced, confidently, as an established fact, possibly
   months later, in a context where nobody remembers it was an unreviewed guess.
2. **Errors compound through retrieval.** One bad entry becomes a premise for the next memo, which cites it,
   which reinforces it. The cost of a bad write isn't one row; it's every future answer that leans on it.
3. **Volume is not value.** An agent can generate drafts faster than anyone can trust them. Without a gate,
   graph size and graph quality diverge, and the whole store loses its authority.

The review gate is the one-way valve that keeps the graph a *source of truth* instead of an *append-only pile
of everything the agent ever typed.*

## Exemptions — automated ingestion bypasses the gate by design

Scheduled ingestion jobs — harvesters that pull external signals, sync jobs, automated digesters — write
straight to their own stores without passing through raw → review. This is **not** a hole in the gate; it's a
recognition that the gate exists to catch *human-authored drafts that might be wrong*. Machine ingestion of
external data is a different thing: it isn't a draft with a point of view, it's a feed. It gets its own
handling (dedup, source tagging, freshness) rather than an editorial review it has no author to answer for.
The rule is: **the review gate governs authored output; automated feeds are governed at ingestion instead.**

## Design principles

- **Capture raw, trust reviewed.** Auto-save everything substantive; let nothing into the graph until it
  clears the gate.
- **The gate is a separate step.** The author's own context can't judge the draft; make quality a distinct
  pass, not a self-assessment.
- **Discard by archiving.** Rejected drafts move aside, never vanish — a bad call must remain reviewable.
- **Tag provenance always.** Canonical knowledge without a source is knowledge you can't audit.
- **Close the loop.** Briefings feed approved knowledge back in, so the pipeline compounds instead of merely
  filling up.

See also: `memory-system.md` (the graph is embedded into archival memory), `agent-protocols.md`
(per-persona provenance tags), `security-gates.md` (the same "gate before trust" instinct applied to
skills).
