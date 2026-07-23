# SETUP.md — for the agent setting this up

**You are an AI coding agent.** A user pointed you at this repository and asked you to set up Utopia OS
for them. Follow this runbook. Work in the user's environment; make no outbound network calls beyond
reading this repo; never print or commit a secret. Confirm before overwriting an existing config file.

Utopia OS = a **portable core** (works on any MCP-capable harness) + a small **harness shim** (the
adapter for the user's specific tool). See [`docs/adapters.md`](docs/adapters.md) for the model.

## Step 1 — identify the user's harness

Ask, or infer from what's installed: **Claude Code, Codex, Kimi Code, grok, Hermes, OpenClaw, opencode,
pi**, or *other*. This decides which adapter you use.

| Harness | Adapter | Tier |
|---|---|---|
| Claude Code | none — use the repo as-is (`CLAUDE.md`, `settings.json`, `skills/`) | native |
| Codex / Kimi Code / grok | [`adapters/codex`](adapters/codex/) · [`adapters/kimi`](adapters/kimi/) · [`adapters/grok`](adapters/grok/) | low (config translation) |
| Hermes / OpenClaw / opencode / pi | [`adapters/hermes`](adapters/hermes/) · [`adapters/openclaw`](adapters/openclaw/) · [`adapters/opencode`](adapters/opencode/) · [`adapters/pi`](adapters/pi/) | medium (guardrails become a plugin) |
| other / unknown | portable core + `AGENTS.md` only (skip the hook wiring) | — |

## Step 2 — read the matching adapter

Open `adapters/<harness>/README.md` and follow its **Steps** and **What degrades** sections. It is the
authoritative, schema-verified guide for that harness. The rest of this file is the shared skeleton.

## Step 3 — install the portable core (every harness)

1. **Instruction file.** Copy `AGENTS.md` to the user's project (Claude Code uses `CLAUDE.md`). Fill in
   their operating rules. Keep it within the harness's size cap (e.g. Codex 32 KiB).
2. **Memory scaffolds.** Copy `memory/templates/` and have the user fill `SOUL.md` (voice), `USER.md`
   (who they are), and the indexes. Do NOT copy anyone else's memory content.
3. **Core scripts.** Copy `scripts/` (security gates, memory/recall, cockpit). They are path-relative
   (`AGENT_ROOT`/`WORKSPACE`), no edits needed.
4. **Skills.** Copy `skills/` and `skills-shared/` into the harness's skill directory (the adapter says
   which). `SKILL.md` content is portable; only *triggering* differs per harness.
5. **MCP.** Use the adapter's MCP config template to point the harness at the user's tool servers.
   Supply every credential via the environment or a secret manager — **never inline a token**.

## Step 4 — wire the guardrail hooks (per adapter)

- **Low-tier (Codex/Kimi/grok):** copy the adapter's hooks config template into the harness's config;
  the same guard scripts run, only the wrapper format changes.
- **Medium-tier (Hermes/OpenClaw/opencode/pi):** the harness has no drop-in hook file. Install the
  adapter's **plugin scaffold** (`adapters/<harness>/plugin*`) and wire the portable-core guard scripts
  behind it, as the adapter README describes. This is real work; do it deliberately.
- **Unknown harness:** skip hooks. The prose rules in `AGENTS.md` still apply; note to the user that the
  *automated* gates (stand-down, send-guard, compound-counter) are not enforced until hooks exist.

## Step 5 — verify, then hand off

1. Run `python3 scripts/memory/check_always_loaded_budget.py` (should be within budget).
2. Smoke-test one skill and one MCP tool.
3. Tell the user what was installed, what still needs their input (voice/user model, secrets in `.env`),
   and — for medium/unknown harnesses — which automated guards are not yet enforced.

## Safety rules you must keep

- Never inline, print, or commit a secret; `.env` and credential paths stay out of git.
- Respect the fleet floor in `memory/state/fleet-root-policy.example.json` (email is draft-only, no
  `curl | bash`, honor the 7-day-age + stand-down checks before installing anything).
- If the user runs untrusted-content subprocesses, wrap them with `scripts/security/bwrap_run.sh`.
