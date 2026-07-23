// utopia-guard.ts — Utopia OS guardrail shim for opencode (anomalyco/opencode).
//
// TEMPLATE. Copy to  .opencode/plugins/utopia-guard.ts  (project) or
//           ~/.config/opencode/plugins/utopia-guard.ts  (global). Files in those dirs auto-load
//           at startup — there is no shell-hook block to register.
//
// This is the medium-tier rewrite of settings.example.json. opencode's hook layer is in-process
// JS/TS plugin functions, NOT shell commands, so the six Claude Code hooks cannot be pointed at
// the guard scripts directly. This shim is the bridge: every guard script stays UNCHANGED (still
// Python/bash); the plugin only maps opencode's hook I/O onto them via Bun's `$` shell and
// preserves the exit-code contract (exit 2 = block -> throw to abort the tool).
//
// Verified 2026-07-23 against opencode.ai/docs/plugins and the @opencode-ai/plugin `Hooks` type.
// Replace /path/to/utopia-os (or set UTOPIA_OS_ROOT). Credentials via env, never inline.

import type { Plugin } from "@opencode-ai/plugin"

const ROOT = process.env.UTOPIA_OS_ROOT ?? "/path/to/utopia-os"

export const UtopiaGuard: Plugin = async ({ $, directory, worktree }) => {
  // Run a guard script, returning its exit code WITHOUT throwing (Bun Shell `.nothrow()`).
  // Optional `stdin` is piped in for scripts that read a hook payload (verify_after_write).
  const run = async (argv: string[], stdin?: string) => {
    const cmd = stdin === undefined
      ? $`${argv}`.cwd(ROOT).nothrow().quiet()
      : $`${argv} < ${Buffer.from(stdin)}`.cwd(ROOT).nothrow().quiet()
    const res = await cmd
    return { code: res.exitCode, out: res.stdout.toString(), err: res.stderr.toString() }
  }

  return {
    // ── SessionStart -> session.created ; Stop -> session.idle ────────────────────────────────
    // Both are event-bus events: side-effect only, they CANNOT block. (No pre-prompt veto point.)
    event: async ({ event }) => {
      if (event.type === "session.created") {
        await run([`${ROOT}/scripts/memory/session_bootstrap.sh`])
      }
      if (event.type === "session.idle") {
        // reply_guard: end-of-turn delivery/save nudge. Best-effort; can't re-open the turn.
        await run([`${ROOT}/scripts/security/reply_guard.sh`])
      }
    },

    // ── UserPromptSubmit -> chat.message (fires on each operator message) ─────────────────────
    // Reset the auto-compound counter and surface fleet-bus messages. Advisory; no hard block.
    "chat.message": async () => {
      await run(["python3", `${ROOT}/scripts/security/auto_compound_counter.py`, "--reset"])
      await run(["python3", `${ROOT}/scripts/agents/bus_turn_poll.py`])
    },

    // ── PreToolUse -> tool.execute.before ; throw to BLOCK ────────────────────────────────────
    // NOTE opencode tool names are lowercase (bash/read/edit/write) and args live on output.args.
    "tool.execute.before": async (input, output) => {
      // PreToolUse[Bash]: stand-down registry check on the command line (exit 2 = block).
      if (input.tool === "bash") {
        const command = String(output.args?.command ?? "")
        const { code, out } = await run(
          ["python3", `${ROOT}/scripts/security/check_standdown.py`, "--pattern", command],
        )
        if (code === 2) throw new Error(`stand-down: blocked — ${out.trim()}`)
        // code 1 (warn) / 3 (expired): surface to the operator, don't hard-block here.
      }

      // PreToolUse[Read|Edit|Write]: skill-injection linter on the target file.
      // skill_linter verdict_exit: fail/error = 2 (block), warn = 1, pass = 0.
      if (input.tool === "read" || input.tool === "edit" || input.tool === "write") {
        const path = String(output.args?.filePath ?? output.args?.path ?? "")
        if (path) {
          const { code, out } = await run(
            ["python3", `${ROOT}/scripts/security/skill_linter.py`, path, "--json"],
          )
          if (code === 2) throw new Error(`skill-linter: blocked — ${out.trim()}`)
        }
      }
    },

    // ── PostToolUse[Write|Edit] -> tool.execute.after ─────────────────────────────────────────
    // Post-hoc: the write already happened, so this verifies/re-lints but cannot block.
    "tool.execute.after": async (input) => {
      if (input.tool === "write" || input.tool === "edit") {
        const payload = JSON.stringify({ tool: input.tool, sessionID: input.sessionID })
        await run(["python3", `${ROOT}/scripts/memory/verify_after_write.py`, "--from-hook"], payload)
      }
    },

    // ── (optional) PermissionRequest -> permission.ask ────────────────────────────────────────
    // The vetoing hook is `permission.ask` (singular): set output.status to "deny"/"allow"/"ask".
    // (`permission.asked` in the event bus is read-only and fires AFTER — it cannot veto.)
    // Wire scripts/security/confirm_gate.py here to enforce the CONFIRM gate deterministically.
    "permission.ask": async (_input, _output) => {
      // Example: _output.status = "deny"
    },
  }
}
