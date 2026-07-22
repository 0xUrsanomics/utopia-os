#!/usr/bin/env bash
# SessionStart-hook stub (Utopia OS). On a fresh session, surface the bootstrap "parachute" so the
# agent resumes cleanly instead of replaying a full transcript: print the Active Handoff, reapply any
# idempotent boot patches. Generic no-op below; wire your own. See docs/session-management.md.
ROOT="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
BOOT="$ROOT/memory/session-bootstrap.md"
[ -f "$BOOT" ] && echo "bootstrap parachute present: $BOOT"
exit 0
