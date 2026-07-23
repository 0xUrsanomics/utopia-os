// Utopia OS guardrail hooks, re-implemented as an OpenClaw typed plugin.
//
// WHY THIS FILE EXISTS
// On Claude Code the six gates in settings.example.json are shell commands the harness
// runs on lifecycle events. OpenClaw has no "run this shell command on PreToolUse and
// block on exit 2" surface: the only place that can BLOCK, REWRITE, or REQUIRE APPROVAL
// is a typed plugin hook registered with api.on(...). So the wiring must be a plugin.
//
// The LOGIC does not move. Each handler spawns the SAME portable Python gate under
// scripts/, hands it the event as stdin JSON (the --from-hook contract those scripts
// already speak), and maps the process result to an OpenClaw decision object. Rewrite
// the ~150 lines below; leave scripts/ untouched.
//
// Load it via  plugins.load.paths  (dev) or  `openclaw plugins install -l <this dir>`.
// Conversation hooks (before_agent_run / before_agent_finalize) need
//   plugins.entries."utopia-guards".hooks.allowConversationAccess = true

import { execFile } from "node:child_process";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

// Claude-Code-tool -> OpenClaw-tool name map. OpenClaw shell tool is `exec` (`bash` alias);
// filesystem tools are `read` / `write` / `edit` / `apply_patch`.
const SHELL_TOOLS = new Set(["exec", "bash", "process", "code_execution"]);
const FS_WRITE_TOOLS = new Set(["write", "edit", "apply_patch"]);
const FS_TOUCH_TOOLS = new Set(["read", "write", "edit", "apply_patch"]);

type GateResult = { code: number; stdout: string; stderr: string };

function utopiaRoot(pluginConfig: Record<string, unknown> | undefined): string {
  const fromCfg = typeof pluginConfig?.utopiaRoot === "string" ? pluginConfig.utopiaRoot : "";
  return fromCfg || process.env.UTOPIA_OS_ROOT || "/path/to/utopia-os";
}

// Spawn a Python gate under scripts/, feeding it the event as stdin JSON, capturing the
// exit code + stdout. execFile with an args array (no shell) avoids injection.
function runGate(root: string, rel: string, payload: unknown, extraArgs: string[] = []): Promise<GateResult> {
  return new Promise((resolve) => {
    const child = execFile(
      "python3",
      [`${root}/${rel}`, "--from-hook", ...extraArgs],
      { timeout: 12_000, maxBuffer: 1_024 * 1_024 },
      (err, stdout, stderr) => {
        const code = err && typeof (err as { code?: unknown }).code === "number" ? (err as { code: number }).code : err ? 1 : 0;
        resolve({ code, stdout: String(stdout ?? ""), stderr: String(stderr ?? "") });
      },
    );
    try {
      child.stdin?.end(JSON.stringify(payload));
    } catch {
      /* gate reads argv only; ignore */
    }
  });
}

export default definePluginEntry({
  id: "utopia-guards",
  name: "Utopia OS Guards",
  description: "Stand-down, skill-lint, verify-after-write, auto-compound, fleet-bus, reply guard.",
  register(api) {
    // === PreToolUse[Bash] -> stand-down registry check ==========================
    // before_tool_call can block, rewrite params, or require approval. Terminal on block:true.
    // Stand-down contract: exit 2 = block, 1 = warn (approve to proceed), 0 = clear, 3 = expired.
    api.on(
      "before_tool_call",
      async (event, ctx) => {
        if (!SHELL_TOOLS.has(event.toolName)) return;
        const root = utopiaRoot(ctx?.pluginConfig ?? event?.context?.pluginConfig);
        const res = await runGate(root, "scripts/security/check_standdown.py", {
          tool_name: event.toolName,
          tool_input: event.params,
          derived_paths: event.derivedPaths ?? [],
        });
        if (res.code === 2) {
          return { block: true, blockReason: res.stdout.trim() || "stand-down: blocked target" };
        }
        if (res.code === 1 || res.code === 3) {
          return {
            requireApproval: {
              title: "Stand-down warning",
              description: res.stdout.trim() || "Target is flagged; confirm before proceeding.",
              severity: "warning",
            },
          };
        }
        return; // exit 0 = clear
      },
      { priority: 90 },
    );

    // === PreToolUse[Read|Edit|Write] -> skill / injection linter ================
    // Matches OpenClaw fs tools. block:true refuses the read/write of a poisoned file.
    api.on(
      "before_tool_call",
      async (event, ctx) => {
        if (!FS_TOUCH_TOOLS.has(event.toolName)) return;
        const root = utopiaRoot(ctx?.pluginConfig ?? event?.context?.pluginConfig);
        const res = await runGate(root, "scripts/security/skill_linter.py", {
          tool_name: event.toolName,
          tool_input: event.params,
          derived_paths: event.derivedPaths ?? [],
        });
        if (res.code !== 0) {
          return { block: true, blockReason: res.stdout.trim() || "skill-linter: injection pattern" };
        }
        return;
      },
      { priority: 80 },
    );

    // === PostToolUse[Write|Edit|MultiEdit] -> verify-after-write ================
    // after_tool_call is observation-only. verify-after-write only re-reads the written
    // value, so it needs no decision surface. Findings go to the gate's own log.
    api.on("after_tool_call", async (event, ctx) => {
      if (!FS_WRITE_TOOLS.has(event.toolName)) return;
      const root = utopiaRoot(ctx?.pluginConfig ?? event?.context?.pluginConfig);
      await runGate(root, "scripts/memory/verify_after_write.py", {
        tool_name: event.toolName,
        tool_input: event.params,
      });
    });

    // === UserPromptSubmit -> reset auto-compound counter + surface fleet-bus =====
    // before_prompt_build fires once per turn and can inject context. It runs the
    // counter reset (side effect) and appends any new hub-addressed bus messages,
    // mirroring Claude Code's two UserPromptSubmit hooks.
    api.on("before_prompt_build", async (event, ctx) => {
      const root = utopiaRoot(ctx?.pluginConfig ?? event?.context?.pluginConfig);
      await runGate(root, "scripts/security/auto_compound_counter.py", {}, ["--reset"]);
      const bus = await runGate(root, "scripts/agents/bus_turn_poll.py", {});
      const text = bus.stdout.trim();
      if (text) return { appendContext: text };
      return;
    });

    // === Stop -> reply / finalize guard =========================================
    // before_agent_finalize is the OpenClaw analog of Claude Code's Stop hook (Codex
    // native Stop hooks are relayed into it). Return { action: "revise" } to force one
    // more model pass; omit to let the natural final answer stand. Needs allowConversationAccess.
    api.on("before_agent_finalize", async (event, ctx) => {
      const root = utopiaRoot(ctx?.pluginConfig ?? event?.context?.pluginConfig);
      const res = await runGate(root, "scripts/security/reply_guard.sh", {});
      if (res.code !== 0) {
        return { action: "revise", reason: res.stdout.trim() || "reply-guard: finalize refused" };
      }
      return; // continue to natural finalization
    });

    // === (optional) SessionStart idempotent boot tasks ==========================
    // The memory "parachute" injection is better done as a workspace bootstrap file
    // (BOOTSTRAP.md / MEMORY.md auto-inject). session_start is observe-only; use it for
    // non-injecting boot side effects.
    api.on("session_start", async (event, ctx) => {
      const root = utopiaRoot(ctx?.pluginConfig ?? event?.context?.pluginConfig);
      await runGate(root, "scripts/memory/session_bootstrap.sh", { reason: (event as { reason?: string }).reason ?? "new" });
    });
  },
});
