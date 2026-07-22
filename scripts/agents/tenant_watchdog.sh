#!/usr/bin/env bash
# tenant_watchdog.sh — keepalive for the fleet worker tenants.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# Runs every 2min via crontab. For each fleet tenant in FLEET_TENANTS:
#   (1) respawn the tmux session via tenant_run.sh if it is dead
#   (2) preventive recycle if the pane-CLI proc has been up > MAX_UPTIME_HOURS
#       (config-freshness: picks up role CLAUDE.md / settings edits within the window)
#
# Recycle is keyed on PANE-CLI uptime, on an odd cadence so recycle time drifts off the cron grid.
#
# crontab: */2 * * * * AGENT_ROOT=/abs/repo /abs/repo/scripts/agents/tenant_watchdog.sh
set -uo pipefail

# AGENT_ROOT = repo root (this file is scripts/agents/tenant_watchdog.sh).
WORKSPACE="${AGENT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
RUN="$WORKSPACE/scripts/agents/tenant_run.sh"
FLEET_BASE="${AGENT_FLEET_HOME:-$WORKSPACE/.data/fleet}"
NOTIFY="${AGENT_NOTIFY_CMD:-}"                       # optional: a command that takes one text arg
TENANTS="${FLEET_TENANTS:-research marketing}"        # space-separated tenant slugs to keep alive
MAX_UPTIME_HOURS="${FLEET_MAX_UPTIME_HOURS:-13}"      # long + odd: stateful workers, recycle mainly for config-freshness
PREVENTIVE_COOLDOWN=3600                              # 1h min between preventive recycles per tenant (anti-loop)

for AGENT in $TENANTS; do
  SESSION_NAME="tenant-$AGENT"
  LOG_DIR="$FLEET_BASE/$AGENT"
  LOG_FILE="$LOG_DIR/watchdog.log"
  PREVENTIVE_LOCK="$LOG_DIR/.preventive-restart.lock"
  mkdir -p "$LOG_DIR"

  # (1) Session-alive check -> respawn if dead.
  if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "[$(date -Iseconds)] $SESSION_NAME dead, respawning..." >> "$LOG_FILE"
    "$RUN" "$AGENT" >> "$LOG_FILE" 2>&1
    echo "[$(date -Iseconds)] respawn complete" >> "$LOG_FILE"
    [ -n "$NOTIFY" ] && [ -x "$NOTIFY" ] && "$NOTIFY" "tenant-$AGENT was down, watchdog respawned it" >/dev/null 2>&1 || true
    continue
  fi

  # (2) Preventive recycle on pane-CLI uptime (config-freshness + bloat cap).
  PANE_PID=$(tmux list-panes -t "$SESSION_NAME" -F '#{pane_pid}' 2>/dev/null | head -1)
  PANE_CLAUDE=$(pgrep -P "${PANE_PID:-0}" -f "claude" 2>/dev/null | head -1)
  [ -z "$PANE_CLAUDE" ] && { echo "[$(date -Iseconds)] $SESSION_NAME: no pane-CLI yet (booting?), skip" >> "$LOG_FILE"; continue; }

  C_START=$(stat -c %Y "/proc/$PANE_CLAUDE" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  UP_H=$(( (NOW - C_START) / 3600 ))
  if [ "$UP_H" -ge "$MAX_UPTIME_HOURS" ]; then
    # cooldown guard
    LAST=0; [ -f "$PREVENTIVE_LOCK" ] && LAST=$(cat "$PREVENTIVE_LOCK" 2>/dev/null || echo 0)
    if [ $(( NOW - LAST )) -ge "$PREVENTIVE_COOLDOWN" ]; then
      echo "[$(date -Iseconds)] $SESSION_NAME up ${UP_H}h >= ${MAX_UPTIME_HOURS}h -> preventive recycle" >> "$LOG_FILE"
      echo "$NOW" > "$PREVENTIVE_LOCK"
      "$RUN" "$AGENT" >> "$LOG_FILE" 2>&1
    fi
  fi
done
