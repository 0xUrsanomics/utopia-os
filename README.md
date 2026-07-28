# Utopia OS

**An open framework for running a persistent, self-regulating AI operations system on top of a coding-agent CLI.**

Most people use an AI assistant as a stateless chat box: every session starts from zero, nothing
compounds, and the assistant will confidently do irreversible things because nothing stops it. Utopia
OS is the opposite. It's the memory, skills, security, and multi-agent scaffolding that turns a
general coding agent into an *operator* — one that remembers across sessions, follows a voice, gates
its own risky actions, and hands work off to sub-agents without losing the thread.

This repo is the **architecture and the reusable machinery**, with every piece of personal and business
content stripped out. It's a skeleton you fill with your own memory, your own skills, your own fleet.

## Why it exists

A coding agent is a powerful runtime with no operating system around it. Utopia OS adds the parts that
make long-running autonomous work safe and durable:

- **Memory that compounds.** A tiered store (always-loaded core → on-demand recall → semantic archive)
  so the agent knows who you are and what was decided last month without re-reading everything each turn.
- **A single write path for operational state.** One store, one mutator, every change logged — so
  "what mode are we in / what's the active project / how much budget is left" never drifts across a
  distributed fleet of processes.
- **Security-first gates.** A stand-down registry, an auto-compound counter, a skill linter, and a
  CONFIRM gate that force a human check before installs, settings edits, or anything irreversible.
- **A knowledge pipeline.** Raw output → review gate → canonical graph, so the agent's own drafts
  never pollute the source of truth.
- **Multi-agent protocols.** Structured hand-offs between personas and between separate agent tenants,
  with a depth limit and memory isolation so delegation doesn't sprawl.
- **A survival layer.** A session-bootstrap "parachute" and an active-handoff block so a mid-task
  context compaction or a crash resumes cleanly instead of dropping the in-flight work.

## What's in here

| Path | What it is |
|---|---|
| `docs/` | The architecture, one design doc per subsystem. Start here. |
| `memory/templates/` | Empty scaffolds for the memory system (voice constitution, user model, indexes, handoff). |
| `scripts/security/` | The safety gates (stand-down registry, compound counter, skill linter, send guards). |
| `scripts/memory/` | The state store (SSOT), recall, and memory machinery. |
| `scripts/cockpit/` | A zero-dependency, read-only localhost dashboard for the whole system. |
| `skills/` | 42 reusable agent workflows. |
| `skills-shared/` | 18 cross-persona skills built from public research. |
| `CLAUDE.md` | The system-prompt skeleton that wires it all together. |

## The 60 skills, by what they do for you

Every one of these is a real folder in this repo, not a roadmap. Adopt them one at a time.

**Keep yourself honest.** `critic` runs a tool-grounded adversarial pass over your own
output before it ships. `sycophancy-guard` stops the agent agreeing with you because you
said it. `premortem` assumes the plan failed and asks why. `anti-ai-slop` and
`content-humanizer` strip the tells. `review-gate` stands between a draft and your canonical
notes so the agent's own output never becomes its own source of truth. `self-audit` and
`skill-audit` turn that scrutiny on the system itself.

**Remember and compound.** `save` extracts durable preferences, decisions and learnings from
a session instead of letting them evaporate. `recall` searches the archive. `dreaming` and
`meta-memory-review` consolidate memory offline. `memory-offload` gets working state out of
context. `graph-hygiene` keeps the notes from rotting.

**Think before building.** `scope` restates the ask, its assumptions and what is explicitly
out of scope, before any work starts. `decision-council` runs an anonymised panel over a
call. `plan-design-review` and `plan-ceo-review` attack a plan from two different angles.
`prd`, `wave-plan` and `branching-workflow` turn an intent into staged work.
`debugging-discipline` breaks the flailing loop.

**Sound like you.** `voice-profiler` builds a voice profile from your own writing, so the
output reads as yours rather than as a model's. `negotiation` and `marketing-psychology` are
applied-research packs, not prompt tricks.

**Work in parallel.** `agent-dispatch`, `subagent-delegation` and `skill-chaining` hand work
to sub-agents with a depth limit. `spawn-tenant` and `spawn-agent-in-tenant` stand up
isolated agent tenants with their own memory.

**Run on a clock.** `daily-forest` and `forest-synthesis` compress a day into something
readable. `eod-summary`, `weekly-retro` and `reality-review-weekly` close the loop by
grading what the system actually predicted against what happened. `goals` keeps a small,
capped, live goal registry instead of an aspirational backlog.

**Handle real inputs.** `deep-research` and `autoresearch` for open questions.
`intel-analyzer` and `signal-scorer` for noisy feeds. `telegram-dump-router` and
`task-extractor` for the mess that arrives from chat. `redact` for anything that leaves.

A full index is in [`skills/`](skills/) and [`skills-shared/`](skills-shared/); each is a
standard `SKILL.md`.

## What's deliberately NOT here

No real memory content, no business data, no personal information, no secrets. Utopia OS is built as a
clean skeleton, not a filtered dump — every file was authored or ported to be free of the operator's
identity. If you're adopting it, you bring your own content.

## Set it up (point your agent at this repo)

The fastest path: open your coding agent in an empty project and tell it

> Read `SETUP.md` from https://github.com/0xUrsanomics/utopia-os and set up Utopia OS for my harness.

[`SETUP.md`](SETUP.md) is a runbook written for the agent: it detects your harness (Claude Code, Codex,
Kimi, grok, Hermes, OpenClaw, opencode, pi, or other), reads the matching [`adapters/`](adapters/) guide,
and wires the portable core + MCP config + hooks + skills, filling in your voice and user model as it
goes. It never inlines a secret and tells you what still needs your input. Prefer to do it by hand? The
manual path is below.

## Getting started

**New to this? Start with [`QUICKSTART.md`](QUICKSTART.md)** — a human first-run path,
fifteen minutes to a working core, with the platform matrix and the dependency answer.

**Requirements: Python 3.9+, and nothing else.** The core has no third-party dependencies.
Memory is Markdown, the state store is stdlib `sqlite3`, the gates are stdlib, the cockpit
is stdlib `http.server`; all 49 modules under `scripts/` import with an empty environment.
Semantic recall is the one heavy piece and it is opt-in
([`requirements-memory.txt`](requirements-memory.txt)), because a multi-gigabyte download
should not stand between you and a Markdown memory system you have not decided on yet.

Setting up the chat bridge is the other thing worth doing early, since it is what puts the
system on your phone. A working reference MCP server ships at
[`scripts/mcp/telegram_bridge.py`](scripts/mcp/telegram_bridge.py): stdlib only, credentials
read from the environment and never stored, and an allowlist it refuses to run without.
[`docs/bot-setup.md`](docs/bot-setup.md) has the click-by-click path for the credentials, and
is explicit that Telegram ships a server while Discord is yours to build.

Then, the manual route:

1. Read `docs/ARCHITECTURE.md` for the whole-system picture, then the subsystem docs.
2. Copy `CLAUDE.md` and the `memory/templates/` scaffolds, and fill them with your own voice + user model.
3. Wire the security gates as hooks (see `docs/security-gates.md`).
4. Adopt skills incrementally — each lives in `skills/<name>/SKILL.md` (the standard Agent Skills
   format). To use one in Claude Code, copy its folder into your `.claude/skills/`. Shared helper
   scripts live under `scripts/` and are referenced by repo-root-relative path.

## Harness compatibility

Utopia OS is Claude-Code-native, but it splits into two layers. A **portable substrate** (the MCP daemon,
the Markdown memory, the recall machinery, and all skill and knowledge content) runs on any MCP-capable
harness. A **Claude Code wiring layer** (`CLAUDE.md`, the `settings.json` hooks, `SKILL.md` routing) needs
a per-harness adapter. Hermes and OpenClaw port cheapest; opencode and Codex are a medium lift; pi, Kimi
Code, and Kilo Code vary. See [AGENTS.md](AGENTS.md) for the full portability guide and adoption steps.

## Acknowledgments

Utopia OS adapts patterns, skills, and reference packs from a lot of open-source work and public
research, and leans on token-efficiency tooling (TOON, RTK, caveman) to run affordably. See
[CREDITS.md](CREDITS.md) for the full list. If your work is used here and isn't credited, open an issue.

## License

MIT © 0xUrsanomics. Use it, fork it, make it yours.
