# Utopia OS on centaur (paradigmxyz/centaur)

centaur is a **host, not a harness**: it runs a coding-agent CLI (Claude Code / Codex / Amp / pi) inside a
per-thread **Kubernetes sandbox pod**, behind a control plane (Slack/Teams ingress + Postgres state) with
controlled egress via a MITM proxy. So this "adapter" is a **deployment guide** (run Utopia OS as the
Claude Code harness inside a centaur sandbox), not a config translation like the other adapters. Verified
against centaur's docs on 2026-07-23. See [`docs/adapters.md`](../../docs/adapters.md) for the model.

> **Adoption note:** `paradigmxyz/centaur` is Apache-2.0 OR MIT, ~924 stars, but a heavy self-hosted
> Kubernetes + multiplayer platform, pre-1.0. It is oriented at teams, not a solo local CLI. Re-run your
> stand-down and weigh the deployment surface before adopting; for a solo/local setup the low-tier
> adapters (or plain Claude Code) are far lighter.

## Why centaur is a HOST, not a four-dimension mapping

Utopia OS is Claude-Code-native, and centaur runs Claude Code **as** the harness inside its sandbox. So the
four dimensions pass through **unchanged** (it is genuine CC in the pod):

| Dimension | Inside a centaur CC pod |
|---|---|
| Instruction file | `CLAUDE.md` (unchanged) |
| Hook layer | `settings.json` hooks (unchanged, run in-pod) |
| Skill trigger | `SKILL.md` (unchanged) |
| MCP config | `.mcp.json` (unchanged), but egress routes through the proxy (below) |

centaur adds three things **around** the CC harness: a Kubernetes sandbox pod (isolation), an egress proxy
(credential injection), and a multiplayer control plane (ingress + coordination).

## Steps (deploy Utopia OS into a centaur sandbox)

1. **Bake the portable core into the sandbox image:** `CLAUDE.md` + `memory/` scaffolds + `scripts/` +
   `skills/` + `settings.json`, so a CC pod boots with Utopia OS already wired. centaur's "bring your own
   harness" path runs the CC CLI against this workspace.
2. **MCP:** declare the daemon's servers to the pod's CC as usual (`.mcp.json`).
3. **Secrets — use centaur's model, not `.env`:** declare each credential to centaur as a tool secret. The
   agent then sees only a **placeholder**; centaur's egress proxy injects the real value on the outbound
   request, bound to specific hosts + header/query/path locations. This is a security **upgrade** over a
   local `.env` (the agent never holds the plaintext) — adopt it.
4. Let centaur own the sandbox + coordination; Utopia OS's own guardrail hooks still run in-pod.

## What centaur gives you (keep) vs what to drop

- **Keep centaur's:** K8s sandbox isolation, egress-proxy credential injection (agent never holds the
  secret), controlled-egress allowlist. These are a genuine security upgrade.
- **Drop / redundant:** Utopia OS's `bwrap_run.sh` subprocess sandbox (the centaur pod already isolates),
  and the local `.env` credential path (use centaur's tool-secret declaration instead).

## What degrades / confirm

- **Heavy deployment:** self-hosted Kubernetes + Postgres + a Rust control plane. Team-scale infra, not a
  local CLI. A solo/local setup is far better served by the lighter adapters or plain Claude Code.
- **Pre-1.0 (0.1.x):** expect churn.
- **Ephemeral pods:** per-thread sandbox pods are short-lived — persist Utopia OS's `memory/` + state on a
  mounted volume, or the 3-tier memory resets per pod.
- **Multiplayer:** centaur is team-oriented; its capability-scoped permissioning maps onto Utopia OS's
  per-tenant model but is more than a solo operator needs.

## Verified sources (2026-07-23)

- centaur `README.md`, `docs/pages/architecture.mdx`, `docs/pages/security.mdx`, `docs/pages/extend/tools.mdx`
