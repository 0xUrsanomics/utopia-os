#!/bin/bash
# stop_hook_save.sh — the Stop-hook trigger half of the /save mechanism.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
# Writes a save signal file when conditions are met.
#
# Registered as a Claude Code Stop hook (in .claude/settings.json).
# Called by Claude Code after every assistant response ends.
#
# What it does:
#   1. Read hook event JSON from stdin (gives us session_id + transcript_path)
#   2. Check cooldown. skip if last save was < COOLDOWN_SECONDS ago
#   3. Check size delta. skip if session jsonl grew < SIZE_THRESHOLD_BYTES
#      since last save was triggered
#   4. Write a signal file to the agent signals dir with the
#      session details
#   5. Emit empty hookSpecificOutput JSON and exit 0
#
# Must stay well under the 120s Stop hook budget. the real /save work
# happens out-of-band in save_handler.sh (cron-polled). This hook is the
# fast-path trigger only.
#
# FAIL-OPEN: if anything goes wrong, print '{}' and exit 0 so we never
# block the session on a misbehaving hook.

set -uo pipefail

# WORKSPACE defaults to the repo root (this file is scripts/session/stop_hook_save.sh).
WORKSPACE="${AGENT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
STATE_DIR="$WORKSPACE/memory/state"
LAST_SAVE_FILE="$STATE_DIR/last-save.json"
SIGNAL_FILE="${AGENT_SIGNAL_DIR:-$HOME/.agent/signals}/save"
SIGNAL_DIR="$(dirname "$SIGNAL_FILE")"
LOG_FILE="$WORKSPACE/logs/session.jsonl"

COOLDOWN_SECONDS=$((20 * 60))
SIZE_THRESHOLD_BYTES=524288

trap 'echo "{}"; exit 0' ERR

mkdir -p "$STATE_DIR" "$SIGNAL_DIR"

HOOK_EVENT=$(cat)

# Parse hook event with python3 (jq not installed on this system).
# Outputs two tab-separated fields: session_id, transcript_path.
PARSED=$(printf '%s' "$HOOK_EVENT" | python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read() or "{}")
    print((d.get("session_id") or "") + "\t" + (d.get("transcript_path") or ""))
except Exception:
    print("\t")
' 2>/dev/null || printf '\t')

SESSION_ID="${PARSED%%$'\t'*}"
TRANSCRIPT_PATH="${PARSED#*$'\t'}"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
    echo "{}"
    exit 0
fi

NOW_EPOCH=$(date +%s)
LAST_SAVE_EPOCH=0
LAST_SAVE_SIZE=0
if [ -f "$LAST_SAVE_FILE" ]; then
    LAST_STATE=$(python3 -c '
import sys, json
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
    print("%d\t%d" % (int(d.get("epoch", 0)), int(d.get("size_bytes", 0))))
except Exception:
    print("0\t0")
' "$LAST_SAVE_FILE" 2>/dev/null || printf '0\t0')
    LAST_SAVE_EPOCH="${LAST_STATE%%$'\t'*}"
    LAST_SAVE_SIZE="${LAST_STATE#*$'\t'}"
fi

ELAPSED=$((NOW_EPOCH - LAST_SAVE_EPOCH))
if [ "$ELAPSED" -lt "$COOLDOWN_SECONDS" ]; then
    echo "{}"
    exit 0
fi

CURRENT_SIZE=$(stat -c%s "$TRANSCRIPT_PATH" 2>/dev/null || echo 0)
DELTA=$((CURRENT_SIZE - LAST_SAVE_SIZE))
if [ "$DELTA" -lt "$SIZE_THRESHOLD_BYTES" ]; then
    echo "{}"
    exit 0
fi

printf '{"ts":"%s","session_id":"%s","transcript_path":"%s","size_bytes":%s,"delta_bytes":%s}\n' \
    "$(date -Iseconds)" "$SESSION_ID" "$TRANSCRIPT_PATH" "$CURRENT_SIZE" "$DELTA" \
    > "$SIGNAL_FILE"

printf '{"ts":"%s","level":"info","persona":"agent","category":"stop-hook","event":"save signal written","delta_bytes":%s,"size_bytes":%s}\n' \
    "$(date -Iseconds)" "$DELTA" "$CURRENT_SIZE" \
    >> "$LOG_FILE" 2>/dev/null || true

echo "{}"
exit 0
