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
| `skills/` | Reusable agent workflows (save, scope, critic, review-gate, dreaming, and more). |
| `skills-shared/` | Cross-persona skills built from public research (anti-slop, sycophancy guard, premortem). |
| `CLAUDE.md` | The system-prompt skeleton that wires it all together. |

## What's deliberately NOT here

No real memory content, no business data, no personal information, no secrets. Utopia OS is built as a
clean skeleton, not a filtered dump — every file was authored or ported to be free of the operator's
identity. If you're adopting it, you bring your own content.

## Getting started

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
