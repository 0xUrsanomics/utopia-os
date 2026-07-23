# AGENTS.md

Utopia OS is **Claude-Code-native**. Its canonical agent instructions live in [`CLAUDE.md`](CLAUDE.md). If your harness reads `AGENTS.md` (opencode, Codex, and others), treat `CLAUDE.md` as the source of truth and this file as the portability guide.

The system splits cleanly into a **portable substrate** that runs on any harness, and a **Claude Code wiring layer** that needs a per-harness adapter.

## Portable substrate (runs on any harness)

- **MCP daemon.** The tools, memory, and recall are exposed over the Model Context Protocol, an open standard. Any MCP-capable harness (opencode, Cline, Cursor, Zed, Hermes) can point its MCP config at the daemon and use them unchanged.
- **Memory files.** Plain Markdown under `memory/templates/`. No harness owns them.
- **Recall and state machinery.** Plain Python under `scripts/memory/`, callable as a tool or over MCP.
- **Skill and knowledge content.** The actual workflows and reference packs are prose, adoptable regardless of how your harness triggers them.

## Claude Code wiring (needs a per-harness adapter)

- **`CLAUDE.md`.** The instruction file, in Claude Code's format. On another harness, mirror it into that harness's convention (this `AGENTS.md`, `.cursorrules`, and so on).
- **`settings.example.json` hooks.** The automated guardrail and hygiene layer (stand-down gate, send guards, compound counter, auto-logging, save/compact, delivery obligations) is wired as Claude Code hooks: PreToolUse, PostToolUse, Stop, SessionStart, UserPromptSubmit. A harness with no equivalent event system cannot run these automatically. Reimplement them on its hook model, or run the gates manually.
- **`SKILL.md` frontmatter routing.** Skills auto-trigger off frontmatter (the Agent Skills convention shared by Claude Code and Hermes). On a harness without it, the skill content still works; you invoke it manually or wire your own router.

## Port cost by harness

| Harness | Cost | Why |
|---|---|---|
| **Hermes, OpenClaw** | Low | Claude-Code-derived. Share the `SKILL.md` and hook conventions. Mostly re-pathing. |
| **opencode, Codex** | Medium | Speak MCP and `AGENTS.md`, but different skill and hook models. Keep the substrate, rewrite the wiring. |
| **pi, Kimi Code, Kilo Code, grok** | Higher, varies | MCP support is inconsistent and some have no hook layer at all. You get tools and memory over MCP, but the automated guardrails need rebuilding. |

## Adopting on a non-Claude-Code harness

1. Point your harness's MCP config at the daemon. Tools, memory, and recall work immediately.
2. Mirror `CLAUDE.md` into your harness's instruction file.
3. Copy the skill and knowledge content. Wire triggering to your harness, or invoke manually.
4. Reimplement the `settings.example.json` hooks on your harness's event system. Until then the guardrails do not fire automatically, so run the critical ones (stand-down, send guards) by hand.

The adapter model (portable core vs harness shim, the four dimensions, per-harness mapping) is in
[`docs/adapters.md`](docs/adapters.md). Adapters shipped: low-cost (near 1:1) —
[`codex`](adapters/codex/) (reference), [`kimi`](adapters/kimi/), [`grok`](adapters/grok/); medium
(guardrails become in-process plugins, each ships a plugin scaffold) — [`hermes`](adapters/hermes/),
[`openclaw`](adapters/openclaw/), [`opencode`](adapters/opencode/), [`pi`](adapters/pi/). Kilo is parked
(no lifecycle hook layer). One HOST adapter — [`centaur`](adapters/centaur/) — is a deploy guide for
running Utopia OS as the Claude Code harness inside a centaur sandbox pod (not a config mapping).
