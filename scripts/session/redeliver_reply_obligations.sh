#!/bin/bash
# redeliver_reply_obligations.sh — SessionStart hook: redeliver any owed Telegram
# replies left pending by a dead PRIOR session, via a direct Bot API call
# (independent of the plugin). Closes the crash-loss tail of the reply-miss rate.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# FAIL-OPEN + timeout-bounded: this must NEVER block a session from starting.
# The ledger (reply_obligations.py) only ever touches prior-session pendings
# older than the grace window and claims each atomically, so this is safe to run
# on every SessionStart.
set -uo pipefail

WORKSPACE="${AGENT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
OBLIG_PY="$WORKSPACE/scripts/session/reply_obligations.py"
RLOG="$WORKSPACE/logs/reply_redeliver.jsonl"

EVENT=$(cat 2>/dev/null || echo '{}')
SID=$(printf '%s' "$EVENT" | python3 -c 'import sys,json
try: print(json.loads(sys.stdin.read() or "{}").get("session_id") or "none")
except Exception: print("none")' 2>/dev/null || echo "none")

OUT=$(timeout 25 python3 "$OBLIG_PY" redeliver --session "${SID:-none}" --grace 90 2>/dev/null || echo '{"error":"redeliver_failed_or_timed_out"}')
printf '{"ts":"%s","session_id":"%s","result":%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${SID:-none}" "$OUT" >> "$RLOG" 2>/dev/null || true

echo "{}"
exit 0
