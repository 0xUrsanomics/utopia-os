#!/usr/bin/env bash
# hermes_shell_hook.sh — bridge a Utopia OS exit-2 guard into a Hermes shell hook.
#
# WHY THIS EXISTS. Utopia OS guard scripts follow the Claude Code contract:
# "exit code 2 = block" (see settings.example.json). Hermes shell hooks do NOT honor
# exit codes for blocking — a non-zero exit only logs a warning and the tool still
# runs. On Hermes a hook blocks by printing JSON to STDOUT:
#     {"decision":"block","reason":"..."}   (Claude-Code shape, accepted)
#     {"action":"block","message":"..."}    (Hermes-canonical)
# and injects turn context (pre_llm_call only) by printing {"context":"..."}.
# This wrapper runs an unmodified core guard and translates its exit code / output
# into that contract, so the portable core is referenced, never forked.
#
# Verified against Hermes docs (user-guide/features/hooks.md, "Shell Hooks") 2026-07-23.
#
# Usage (from ~/.hermes/config.yaml `hooks:` entries):
#   command: "/path/to/utopia-os/adapters/hermes/hermes_shell_hook.sh python3 /path/to/guard.py --from-hook"
#
# Contract this bridge assumes of a guard:
#   - exit 2                -> BLOCK; captured output (stdout+stderr) becomes the reason.
#   - exit 0, on pre_llm_call, output present -> that output is injected as turn context
#     (so a context-provider like bus_turn_poll.py must print ONLY context text to stdout;
#      send logs/status to stderr).
#   - anything else         -> silent no-op ({}).
# It always emits valid JSON and exits 0, so a guard can never trap the agent loop.

set -u

payload="$(cat -)"

if [ "$#" -eq 0 ]; then
  printf '{}\n'
  exit 0
fi

# Run the guard, feeding it the same JSON payload Hermes handed us on stdin.
# (--from-hook guards parse this; guards that ignore stdin are unaffected.)
out="$(printf '%s' "$payload" | "$@" 2>&1)"
rc=$?

# Translate rc/output into Hermes's stdout JSON contract. python3 does the JSON
# encoding so reasons/context with quotes or newlines are always well-formed.
HOOK_RC="$rc" HOOK_OUT="$out" python3 - "$payload" <<'PY'
import json, os, sys

payload = sys.argv[1] if len(sys.argv) > 1 else "{}"
rc  = int(os.environ.get("HOOK_RC", "0"))
out = os.environ.get("HOOK_OUT", "").strip()

try:
    event = json.loads(payload).get("hook_event_name", "")
except Exception:
    event = ""

# exit 2 = block (Utopia OS / Claude Code contract) -> Hermes block shape.
if rc == 2:
    print(json.dumps({"decision": "block",
                      "reason": out or "blocked by Utopia OS guard"}))
    sys.exit(0)

# pre_llm_call guards that print text want it injected as this turn's context.
if event == "pre_llm_call" and out:
    try:
        print(json.dumps(json.loads(out)))   # already JSON -> pass through
    except Exception:
        print(json.dumps({"context": out}))  # plain text -> wrap as context
    sys.exit(0)

# If the guard already emitted valid JSON (its own decision), forward it; else no-op.
try:
    print(json.dumps(json.loads(out)))
except Exception:
    print("{}")
PY

exit 0
