#!/usr/bin/env bash
# tenant_run.sh <agent> — launcher for a fleet WORKER tenant.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# A fleet worker is a headless coding-agent CLI session running in tmux that:
#   - has its OWN identity (cwd = its home dir with a role CLAUDE.md)
#   - coordinates via fleet_bus (SQLite) + fleet_brain (shared-brain findings), NOT a chat channel
#   - receives work by `tmux send-keys` (bus_dispatcher.py delivers bus tasks into its pane)
#   - surfaces to the operator THROUGH the hub (hub-and-spoke), so NO chat plugin / channel poller
#
# Auth: creds are SEEDED once from the operator's own logged-in config so a fresh tenant needs NO
# interactive /login. Each tenant then rotates its own token in its isolated CLAUDE_CONFIG_DIR. More
# same-account tenants raise the refresh-race risk (an OAuth 401 class); a single-instance flock +
# per-config sweep mitigate it.
#
# Usage: tenant_run.sh <agent-slug>     (watchdog/manual/provision calls this)
set -euo pipefail

AGENT="${1:-}"
case "$AGENT" in
  ""|*[!a-z0-9-]*) echo "ERROR: usage: $0 <agent-slug>  (lowercase letters/digits/hyphens)" >&2; exit 1 ;;
esac

# AGENT_ROOT = repo root (this file is scripts/agents/tenant_run.sh).
WORKSPACE="${AGENT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
FLEET_BASE="${AGENT_FLEET_HOME:-$WORKSPACE/.data/fleet}"
HOME_DIR="$FLEET_BASE/$AGENT"
CONFIG_DIR="$HOME_DIR/cc-config"
LOG_FILE="$HOME_DIR/session.log"
RUN_DIR="$HOME_DIR/run"
SESSION_NAME="tenant-$AGENT"
SWEEP_TAG="utopia-fleet/$AGENT/cc-config"     # unique per tenant; never matches another tenant's config dir
MCP_CONFIG="${AGENT_MCP_CONFIG:-}"            # optional shared MCP config; flag added only if the file exists
SEED_CREDS="${CLAUDE_SEED_CREDS:-$HOME/.claude/.credentials.json}"
SEED_CLAUDE_JSON="${CLAUDE_SEED_JSON:-$HOME/.claude.json}"

mkdir -p "$CONFIG_DIR" "$RUN_DIR" "$(dirname "$LOG_FILE")"
chmod 700 "$CONFIG_DIR"
export CLAUDE_CONFIG_DIR="$CONFIG_DIR"

# Seed auth ONCE (no interactive login). Two parts are BOTH required:
#  (1) .credentials.json = the OAuth token (copied from the operator's ~/.claude)
#  (2) oauthAccount record in .claude.json = WHICH account is logged in. Creds alone are NOT enough;
#      without a populated oauthAccount the CLI shows the login-method picker and tries to open a
#      browser (headless -> hangs). Verified by diffing against a working seeded tenant.
if [ ! -f "$CONFIG_DIR/.credentials.json" ] && [ -f "$SEED_CREDS" ]; then
  cp "$SEED_CREDS" "$CONFIG_DIR/.credentials.json"
  chmod 600 "$CONFIG_DIR/.credentials.json"
  echo "[tenant_run $AGENT] seeded creds token from $SEED_CREDS"
fi
# Inject oauthAccount + userID if the config's .claude.json lacks a populated account record.
NEEDS_ACCT=1
if [ -f "$CONFIG_DIR/.claude.json" ]; then
  NEEDS_ACCT=$(python3 -c "import json;d=json.load(open('$CONFIG_DIR/.claude.json'));print(0 if d.get('oauthAccount') else 1)" 2>/dev/null || echo 1)
fi
if [ "$NEEDS_ACCT" = "1" ] && [ -f "$SEED_CLAUDE_JSON" ]; then
  python3 - "$SEED_CLAUDE_JSON" "$CONFIG_DIR/.claude.json" <<'PYSEED'
import json, os, sys
master_p, dst_p = sys.argv[1], sys.argv[2]
master = json.load(open(master_p))
dst = {}
if os.path.exists(dst_p):
    try: dst = json.load(open(dst_p))
    except Exception: dst = {}
for k in ("oauthAccount", "userID"):
    if master.get(k):
        dst[k] = master[k]
json.dump(dst, open(dst_p, "w"))
PYSEED
  chmod 600 "$CONFIG_DIR/.claude.json"
  echo "[tenant_run $AGENT] seeded oauthAccount into .claude.json (no /login needed)"
fi

# Permission allow-list (idempotent, self-heals each launch). acceptEdits so file writes don't
# prompt; explicit tool allow so a headless session never hangs on a permission gate. The deny-belt
# protects secrets. Bash/Read cover the fleet_bus.py + fleet_brain.py + recall calls. Tighten to taste.
cat > "$CONFIG_DIR/settings.json" <<'SETTINGS'
{
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [
      "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch",
      "Task", "TodoWrite", "NotebookEdit"
    ],
    "deny": [
      "Read(**/.env)", "Read(**/.env.*)", "Read(**/.credentials.json)",
      "Read(**/.ssh/**)", "Read(**/wallet*)", "Read(**/*secret*)"
    ]
  }
}
SETTINGS

# Enforce the fleet-tenant design invariant: NO plugins. A coding-agent CLI's marketplace
# auto-install can re-add a chat plugin into a seeded config -> a long-poller on the OPERATOR's bot
# token -> stolen inbound from the operator session. Fleet workers are headless (bus + brain, no chat
# plugin). Wiping installed_plugins.json is a RECORD wipe only — the CLI can re-install the plugin
# from the registered marketplace AFTER the wipe, mid-startup, and the poller runs from the
# marketplace/cache dir. Kill source + code + record: no source, no code, no record.
mkdir -p "$CONFIG_DIR/plugins"
printf '{"version":2,"plugins":{}}' > "$CONFIG_DIR/plugins/installed_plugins.json"   # no record
printf '{}' > "$CONFIG_DIR/plugins/known_marketplaces.json"                          # no source (deregister marketplace)
rm -rf "$CONFIG_DIR/plugins/marketplaces"/* "$CONFIG_DIR/plugins/cache"/* 2>/dev/null || true  # no code (poller can't spawn)

cd "$HOME_DIR"

# Single-instance mutex (anti OAuth refresh-race: never two procs on one config dir).
exec 9>"$RUN_DIR/launch.lock"
if ! flock -n 9; then
  echo "[tenant_run $AGENT] launch already in progress (mutex held) -> skip" >&2
  exit 0
fi

# Sweep leftover procs for THIS agent only (matched by the unique config-dir env tag). Skips self.
_sweep() {
  local sig="$1" pid
  for pid in $(pgrep -u "$(id -u)" -f "claude" 2>/dev/null); do
    [ "$pid" = "$$" ] && continue
    if { tr '\0' '\n' < "/proc/$pid/environ"; } 2>/dev/null | grep -q "CLAUDE_CONFIG_DIR=.*$SWEEP_TAG"; then
      kill "-$sig" "$pid" 2>/dev/null || true
    fi
  done
}
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
_sweep TERM; sleep 3
_sweep KILL; sleep 1

# Launch the CLI in tmux (empty detached shell first, then send-keys -> real PTY).
tmux new-session -d -s "$SESSION_NAME" -c "$HOME_DIR" -x 220 -y 50
tmux pipe-pane -t "$SESSION_NAME" -o "cat >> $LOG_FILE"
tmux send-keys -t "$SESSION_NAME" "export CLAUDE_CONFIG_DIR=$CONFIG_DIR" Enter
tmux send-keys -t "$SESSION_NAME" 'export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"' Enter

# Conditional --continue: resume if a session exists, else cold-start fresh. `claude --continue`
# exits non-zero when there's nothing to continue -> `|| claude` starts fresh. Add --mcp-config
# only when a shared MCP config was provided AND the file exists.
FLAGS="--name tenant-$AGENT"
[ -n "$MCP_CONFIG" ] && [ -f "$MCP_CONFIG" ] && FLAGS="$FLAGS --mcp-config $MCP_CONFIG"
tmux send-keys -t "$SESSION_NAME" "claude --continue $FLAGS || claude $FLAGS" Enter

# Auto-Enter to clear the CLI's "Resume from summary?" gate on --continue.
( exec 9>&-
  sleep 12; tmux send-keys -t "$SESSION_NAME" "" Enter 2>/dev/null || true
  sleep 8;  tmux send-keys -t "$SESSION_NAME" "" Enter 2>/dev/null || true ) &

sleep 3
echo "started $SESSION_NAME (cwd=$HOME_DIR, config=$CONFIG_DIR)"
echo "attach: tmux attach -t $SESSION_NAME   log: tail -f $LOG_FILE"
