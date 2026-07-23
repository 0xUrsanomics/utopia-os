"""Utopia OS guardrails — Hermes plugin (stateful / blocking gates).

Reuses the portable-core guard scripts UNCHANGED (subprocess), and adapts their
result to Hermes's hook-return contract. Nothing here forks the core; it is the
thin shim the medium tier calls for.

Hook-return contract (verified 2026-07-23, user-guide/features/hooks.md):
  - pre_tool_call  -> return {"action": "block", "message": str} to VETO the tool;
                      any other return is ignored (tool proceeds).
  - pre_llm_call   -> return {"context": str} (or a plain non-empty str) to inject
                      text into THIS turn's user message; None = no injection.
  - post_tool_call / post_llm_call -> return ignored (observers).

Callbacks receive keyword args and MUST accept **kwargs for forward-compat. A
callback that raises is logged and skipped — it can never crash the agent — so we
also fail OPEN deliberately only where safety allows and fail CLOSED (block) where a
guard positively demanded it.

Set UTOPIA_ROOT to your checkout (or export it in ~/.hermes/.env).
"""

import json
import logging
import os
import subprocess

logger = logging.getLogger("plugin.utopia-guardrails")

UTOPIA_ROOT = os.environ.get("UTOPIA_ROOT", "/path/to/utopia-os")
SEC = os.path.join(UTOPIA_ROOT, "scripts", "security")
MEM = os.path.join(UTOPIA_ROOT, "scripts", "memory")
AGT = os.path.join(UTOPIA_ROOT, "scripts", "agents")

# Hermes tool names -> Utopia stand-down domains. Wire this to your
# permissions.schema.json; the compound-counter uses the same domain keys.
STANDDOWN_TOOLS = {"terminal"}                       # installs / mcp-add / settings live behind terminal
WRITE_TOOLS = {"write_file", "patch"}
# Tool classes that are CONFIRM/BLOCKED in the autonomy schema and must carry a
# fresh confirm_gate approval before they run. Populate from permissions.schema.json.
CONFIRM_TOOLS: set[str] = set()                      # e.g. {"cronjob"} for scheduler mutations


def _run(argv, stdin_text=""):
    """Run a core guard; return (rc, combined_output)."""
    try:
        p = subprocess.run(argv, input=stdin_text, capture_output=True,
                           text=True, timeout=15)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:                            # never let a guard crash the agent
        logger.warning("guard %s failed: %s", argv and argv[0], e)
        return 0, ""


def _cc_payload(event, tool_name=None, tool_input=None):
    """Build the Claude-Code-shaped stdin the --from-hook guards parse."""
    return json.dumps({
        "hook_event_name": event,
        "tool_name": tool_name,
        "tool_input": tool_input or {},
    })


# --------------------------------------------------------------------------- #
# pre_tool_call — the one authoritative veto point.
# --------------------------------------------------------------------------- #
def guard_tool_call(tool_name: str, args: dict, task_id: str = "", **kwargs):
    payload = _cc_payload("PreToolUse", tool_name, args)

    # 1) Stand-down registry (install / mcp-add / settings / scheduler classes).
    if tool_name in STANDDOWN_TOOLS:
        rc, out = _run(["python3", os.path.join(SEC, "check_standdown.py"), "--from-hook"], payload)
        if rc == 2:
            return {"action": "block", "message": out or "stand-down registry: refused."}

    # 2) Skill-file injection lint on reads/writes of skill files.
    if tool_name in WRITE_TOOLS or tool_name == "read_file":
        rc, out = _run(["python3", os.path.join(SEC, "skill_linter.py"), "--from-hook"], payload)
        if rc == 2:
            return {"action": "block", "message": out or "skill linter: injection pattern refused."}

    # 3) Autonomy-mode + CONFIRM-gate: a CONFIRM/BLOCKED-class tool must have a
    #    fresh, hash-matching approval registered (confirm_gate.py). No approval
    #    on record -> veto and force the /scope restate.
    if tool_name in CONFIRM_TOOLS:
        # Write the exact about-to-run action, then validate it against a pending
        # approval. MISMATCH/EXPIRED/NO_PENDING all exit non-zero -> block.
        action_file = os.path.join(UTOPIA_ROOT, "memory", "state", "hermes_pending_action.json")
        try:
            os.makedirs(os.path.dirname(action_file), exist_ok=True)
            with open(action_file, "w") as f:
                json.dump({"tool": tool_name, "args": args}, f, sort_keys=True)
            rc, out = _run(["python3", os.path.join(SEC, "confirm_gate.py"),
                           "validate", "--action-file", action_file])
            if rc != 0:
                return {"action": "block",
                        "message": f"CONFIRM gate: {out or 'no fresh approval'}. "
                                   "Run /scope, restate the ask + assumptions, and get "
                                   "operator approval on THIS action before retrying."}
        except Exception as e:
            logger.warning("confirm_gate wiring error: %s", e)

    # 4) Compound-counter: catch the approval cascade. Over threshold -> block.
    domain = "install" if tool_name in STANDDOWN_TOOLS else None
    if domain:
        rc, _ = _run(["python3", os.path.join(SEC, "auto_compound_counter.py"), "--check"])
        if rc == 1:
            return {"action": "block",
                    "message": "Auto-compound threshold hit (3+ AUTO ops on one "
                               "authorization). STOP: /scope restate what's done + queued, "
                               "get explicit re-authorization before continuing."}
        _run(["python3", os.path.join(SEC, "auto_compound_counter.py"), "--bump", domain, tool_name])

    return None  # allow


# --------------------------------------------------------------------------- #
# pre_llm_call — inject bootstrap parachute (first turn) + fleet-bus; reset counter.
# (This is Claude Code's UserPromptSubmit + SessionStart-context, merged: Hermes
#  fires pre_llm_call at the same place and it is the only context-injection hook.)
# --------------------------------------------------------------------------- #
def inject_turn_context(session_id: str = "", user_message: str = "",
                        is_first_turn: bool = False, **kwargs):
    _run(["python3", os.path.join(SEC, "auto_compound_counter.py"), "--reset"])

    chunks = []
    if is_first_turn:
        rc, out = _run(["bash", os.path.join(MEM, "session_bootstrap.sh")])
        if out:
            chunks.append(out)
    rc, bus = _run(["python3", os.path.join(AGT, "bus_turn_poll.py")])
    if bus:
        chunks.append(bus)

    return {"context": "\n\n".join(chunks)} if chunks else None


# --------------------------------------------------------------------------- #
# post_tool_call — verify-after-write (observer; return ignored).
# --------------------------------------------------------------------------- #
def verify_after_write(tool_name: str, args: dict, result: str = "",
                       task_id: str = "", **kwargs):
    if tool_name in WRITE_TOOLS:
        _run(["python3", os.path.join(MEM, "verify_after_write.py"), "--from-hook"],
             _cc_payload("PostToolUse", tool_name, args))


# --------------------------------------------------------------------------- #
# post_llm_call — DEGRADED Stop/reply_guard. Hermes has no blocking Stop hook, and
# post_llm_call's return is IGNORED, so this can only OBSERVE/log a missed delivery
# obligation, not force a retry the way Claude Code's Stop hook does. See README.
# --------------------------------------------------------------------------- #
def reply_obligation_log(session_id: str = "", assistant_response: str = "",
                         platform: str = "", **kwargs):
    _run(["bash", os.path.join(SEC, "reply_guard.sh")])


def register(ctx):
    """Called once at startup. Wire the gates to Hermes lifecycle hooks."""
    ctx.register_hook("pre_tool_call", guard_tool_call)
    ctx.register_hook("pre_llm_call", inject_turn_context)
    ctx.register_hook("post_tool_call", verify_after_write)
    ctx.register_hook("post_llm_call", reply_obligation_log)
    logger.info("utopia-guardrails: registered pre/post tool + llm hooks")
