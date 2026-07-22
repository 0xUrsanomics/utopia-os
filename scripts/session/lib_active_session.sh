#!/bin/bash
# lib_active_session.sh — session-size self-regulation helper.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
# Shared helpers for finding the active Claude Code session transcript.
#
# Historical bug (fixed 2026-04-11): previous version trusted
# ~/.claude/sessions/${PID}.json sessionId directly, but /clear creates a NEW
# jsonl on disk while leaving that metadata pointing at the PRE-clear session.
# All consumers (session_bloat_check.sh, etc.) read the wrong (stale) file after
# any /clear. Fix: derive project dir from PID metadata cwd, then pick the
# NEWEST jsonl in that dir by mtime.
#
# Usage:
#   source "$(dirname "$0")/lib_active_session.sh"   # or the scripts/session/ path
#   if find_active_session; then          # defaults to this lib's own repo root
#       echo "session $ACTIVE_SESSION_ID at $ACTIVE_TRANSCRIPT ($ACTIVE_SIZE_BYTES bytes)"
#   fi
#   # Optional: target a different project ->  find_active_session /path/to/cwd
#   #           or set AGENT_ACTIVE_CWD=/path/to/cwd
#
# On success, sets:
#   ACTIVE_CLAUDE_PID       - pid of the live claude process whose cwd matches the
#                             target project (empty if none matched; non-fatal)
#   ACTIVE_PROJECT_DIR      - ~/.claude/projects/<slug>/ for that process cwd
#   ACTIVE_TRANSCRIPT       - absolute path to the newest jsonl in that dir
#   ACTIVE_SESSION_ID       - sessionId parsed from the newest jsonl filename
#   ACTIVE_SIZE_BYTES       - stat size of ACTIVE_TRANSCRIPT (whole-file, append-only)
#   ACTIVE_BYTES_SINCE_COMPACT - bytes written since the LAST compact_boundary marker
#                                in the jsonl (= size if no marker exists). This is the
#                                number self-regulation thresholds should actually check
#                                after 2026-04-15: /compact is in-place and the disk
#                                file keeps growing append-only, so total size stops
#                                reflecting reply cost. Claude Code writes a
#                                `type:system, subtype:compact_boundary` line at every
#                                compact (TG-dispatched or native REPL /compact), so
#                                this is a robust marker regardless of compact entry point.
#   ACTIVE_META_SESSION_ID  - sessionId from PID metadata (may be stale; exposed for debugging)
#
# Returns:
#   0 on success (transcript found for the target project)
#   3 target cwd could not be resolved
#   4 project dir does not exist for the target cwd
#   5 no jsonl files in project dir
#
# rc 1/2 retired: the old single-process `pgrep -x claude | head -1` broke once a
# SECOND claude ran under the same user (e.g. a second bot). head -1 grabbed the
# lower PID (the wrong one), then died with rc=2 because it had no
# ~/.claude/sessions/<pid>.json. Fix: the project dir is now derived directly
# from the target cwd (no PID-metadata dependency at all), and the live PID is
# matched by cwd via /proc/<pid>/cwd (ground truth) rather than head -1. Missing
# PID metadata is non-fatal.

find_active_session() {
    ACTIVE_CLAUDE_PID=""
    ACTIVE_PROJECT_DIR=""
    ACTIVE_TRANSCRIPT=""
    ACTIVE_SESSION_ID=""
    ACTIVE_SIZE_BYTES=0
    ACTIVE_BYTES_SINCE_COMPACT=0
    ACTIVE_META_SESSION_ID=""

    # Target project cwd. Priority: explicit arg > AGENT_ACTIVE_CWD env > this lib's
    # own repo root (lib lives at <repo>/scripts/session/, so repo root is two up).
    local target_cwd="${1:-${AGENT_ACTIVE_CWD:-}}"
    if [ -z "$target_cwd" ]; then
        local self_dir
        self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
        target_cwd="$(cd "$self_dir/../.." 2>/dev/null && pwd)"
    fi
    if [ -z "$target_cwd" ]; then
        return 3
    fi

    # Project dir is derived DIRECTLY from the target cwd. No PID-metadata
    # dependency: this is the part that used to fail (rc=2) when the wrong claude
    # process was picked. CC project dir naming: replace both / and _ with -.
    # e.g. /home/user/projects/my-agent -> -home-user-projects-my-agent
    local slug
    slug=$(echo "$target_cwd" | sed 's|[/_]|-|g')
    ACTIVE_PROJECT_DIR="$HOME/.claude/projects/${slug}"
    if [ ! -d "$ACTIVE_PROJECT_DIR" ]; then
        return 4
    fi

    # Best-effort: identify the live claude PID for THIS project. Multiple claude
    # processes can run under one user (e.g. several bots), so match by cwd via
    # /proc/<pid>/cwd (ground truth) instead of `pgrep | head -1`. Non-fatal if
    # none match (e.g. checking from a cron when no interactive session is live).
    local pid pcwd meta
    for pid in $(pgrep -u "$(id -un)" -x claude 2>/dev/null); do
        pcwd=$(readlink "/proc/$pid/cwd" 2>/dev/null)
        if [ "$pcwd" = "$target_cwd" ]; then
            ACTIVE_CLAUDE_PID="$pid"
            meta="$HOME/.claude/sessions/${pid}.json"
            if [ -f "$meta" ]; then
                ACTIVE_META_SESSION_ID=$(python3 -c "
import json, sys
try:
    print(json.load(open('$meta')).get('sessionId',''))
except Exception:
    sys.exit(1)
" 2>/dev/null)
            fi
            break
        fi
    done

    # Pick the newest jsonl by mtime. this is the live session, which may
    # differ from the PID metadata sessionId after /clear.
    ACTIVE_TRANSCRIPT=$(ls -1t "$ACTIVE_PROJECT_DIR"/*.jsonl 2>/dev/null | head -1)
    if [ -z "$ACTIVE_TRANSCRIPT" ] || [ ! -f "$ACTIVE_TRANSCRIPT" ]; then
        return 5
    fi

    # Derive sessionId from filename (strip path and .jsonl)
    local base
    base=$(basename "$ACTIVE_TRANSCRIPT")
    ACTIVE_SESSION_ID="${base%.jsonl}"
    ACTIVE_SIZE_BYTES=$(stat -c '%s' "$ACTIVE_TRANSCRIPT")

    # Compute bytes since the LAST compact_boundary marker. Claude Code writes
    # `{"type":"system","subtype":"compact_boundary",...}` at every compact.
    # If no marker exists (fresh session, never compacted), falls back to full size.
    ACTIVE_BYTES_SINCE_COMPACT=$(python3 -c "
import sys
path = '$ACTIVE_TRANSCRIPT'
try:
    last_off = 0
    off = 0
    with open(path, 'rb') as f:
        for line in f:
            if b'compact_boundary' in line:
                last_off = off
            off += len(line)
    size = off
    print(size - last_off)
except Exception:
    sys.exit(1)
" 2>/dev/null)
    if [ -z "$ACTIVE_BYTES_SINCE_COMPACT" ]; then
        ACTIVE_BYTES_SINCE_COMPACT="$ACTIVE_SIZE_BYTES"
    fi

    return 0
}
