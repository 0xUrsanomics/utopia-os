#!/bin/bash
# save_handler.sh — the /save dispatch half of the Stop-hook save mechanism.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# Mirrors the compact-on-rotate pattern. Runs from cron every 60s. Watches for a
# save signal file (written by stop_hook_save.sh) and types /save into the running
# agent tmux REPL so the live Claude Code session executes its /save extraction natively.
#
# Why tmux send-keys instead of spawning `claude --print`:
#   Running a second `claude` in this project dir would load the telegram
#   plugin, which would fight the currently running plugin for the bot
#   token (a known 409 conflict). Reusing the live session avoids this.
#   the session already owns the plugin lock.
#
# Recursion protection:
#   After dispatching /save, we immediately update memory/state/last-save.json
#   with the current epoch + session size. The Stop hook checks this on its
#   next fire (which will happen right after /save's response) and skips
#   because the 20-minute cooldown hasn't elapsed. No loop.
#
# Cron line (add via `crontab -e` when ready):
#   * * * * * /path/to/scripts/session/save_handler.sh >> /path/to/logs/save-handler.log 2>&1

set -e

# WORKSPACE defaults to the repo root (this file is scripts/session/save_handler.sh).
WORKSPACE="${AGENT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SIGNAL_FILE="${AGENT_SIGNAL_DIR:-$HOME/.agent/signals}/save"
TMUX_SESSION="${AGENT_TMUX_SESSION:-agent}"
STATE_DIR="$WORKSPACE/memory/state"
LAST_SAVE_FILE="$STATE_DIR/last-save.json"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

[ -f "$SIGNAL_FILE" ] || exit 0

SIGNAL_CONTENT=$(cat "$SIGNAL_FILE" 2>/dev/null || echo "{}")
SESSION_SIZE=$(printf '%s' "$SIGNAL_CONTENT" | python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read() or "{}")
    print(int(d.get("size_bytes", 0)))
except Exception:
    print(0)
' 2>/dev/null || echo 0)

if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "$LOG_PREFIX signal present but tmux session '$TMUX_SESSION' missing. leaving signal for retry"
    exit 0
fi

if ! pgrep -u "$(id -un)" -f "claude-plugins-official/telegram" > /dev/null 2>&1; then
    echo "$LOG_PREFIX signal present but telegram plugin not running. leaving signal for retry"
    exit 0
fi

rm -f "$SIGNAL_FILE"
tmux send-keys -t "$TMUX_SESSION" "/save" Enter
echo "$LOG_PREFIX /save dispatched to tmux session '$TMUX_SESSION' (trigger size: $SESSION_SIZE bytes)"

mkdir -p "$STATE_DIR"
NOW_EPOCH=$(date +%s)
NOW_ISO=$(date -Iseconds)
LAST_SAVE_JSON=$(printf '{"ts":"%s","epoch":%s,"size_bytes":%s,"method":"stop-hook + save-handler"}' \
    "$NOW_ISO" "$NOW_EPOCH" "$SESSION_SIZE")
# SSOT-canonical write. Fallback to direct file write if ssot unavailable.
python3 "$WORKSPACE/scripts/memory/ssot.py" set session.last_save "$LAST_SAVE_JSON" \
    --by save-handler --reason "save dispatched" >/dev/null 2>&1 \
    || printf '%s\n' "$LAST_SAVE_JSON" > "$LAST_SAVE_FILE"
