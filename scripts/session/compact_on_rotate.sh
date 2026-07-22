#!/bin/bash
# compact_on_rotate.sh — the session-bootstrap parachute mechanism.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
# Compacts the active Claude Code session into memory/session-bootstrap.md
# so fresh sessions can resume context without a full transcript replay.
#
# Strategy:
#   1. Find the active claude session jsonl
#   2. Skip if the transcript hasn't meaningfully advanced since last compaction
#   3. Extract ONLY the new turns since last run (capped), feed to a short haiku call
#   4. Append the dated block to session-bootstrap.md, truncate to last 5 blocks
#   5. Record the new line offset for next run
#
# Run via cron every 30 min (cheap, haiku-only):
#   */30 * * * * /path/to/scripts/session/compact_on_rotate.sh >> /path/to/logs/compact-on-rotate.log 2>&1
#
# DEDUP FIX 2026-07-12 (root cause of the recurring near-duplicate-block bug):
#   The cron used to unconditionally `tail -30` every tick and re-summarize it fresh.
#   On a slow-moving long session the SAME recent turns sat in the tail-30 window
#   across ticks, so consecutive haiku calls summarized the same moment (worded
#   differently), crowding the 5-slot budget with restatements of one story.
#   2nd confirmed recurrence (session-bootstrap.md), see memory/Learnings.md
#   2026-07-11 + 2026-07-12.
#
#   FIX = advancement gate + new-lines-only feed (Learnings option "b", the more
#   correct one): track the last-compacted line offset per session; skip the tick
#   entirely when nothing new arrived (also kills wasted haiku calls on idle
#   sessions), and feed haiku ONLY the turns after the last offset so no line is
#   ever summarized twice. Fail-open: any state/parse problem resets offset to 0,
#   reproducing the original "summarize the tail" behavior, never worse.
#
#   A similarity-based "merge near-duplicate blocks" guard was BUILT AND TESTED
#   2026-07-12 then REJECTED: lexical similarity (difflib and token-Jaccard) cannot
#   separate "same story, reworded" from "different story, same process template"
#   (two distinct voice-tweet blocks share signal/interview/questions/draft wording
#   and scored HIGHER similarity than an actual dup). A lexical merge would collapse
#   distinct stories, which destroys real context, strictly worse than a redundant
#   block. A reliable dedup needs embeddings, out of scope for a haiku-cheap cron.

set -uo pipefail

# WORKSPACE defaults to the repo root (this file is scripts/session/compact_on_rotate.sh).
WORKSPACE="${AGENT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BOOTSTRAP="$WORKSPACE/memory/session-bootstrap.md"
STATE_FILE="$WORKSPACE/memory/state/compact_on_rotate.state"   # "SESSION_ID LINE_COUNT"
LOCKFILE="/tmp/compact_on_rotate.lock"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
RECENT_TURNS=30                 # max recent jsonl lines to feed haiku
MAX_BLOCKS=5                    # keep last N dated blocks
MIN_NEW_LINES=8                 # skip if fewer than this many new turns since last compaction
MIN_SIZE_BYTES=$((512 * 1024))  # skip if session smaller than 512KB (not worth compacting)
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || echo claude)}"
CLAUDE_MODEL="${AGENT_COMPACT_MODEL:-claude-haiku-4-5-20251001}"  # a cheap model for this cron

# Lock so cron doesn't stack runs
exec 200>"$LOCKFILE" || exit 0
flock -n 200 || { echo "$LOG_PREFIX already running, skip"; exit 0; }

# Resolve active session jsonl via shared helper
source "$WORKSPACE/scripts/session/lib_active_session.sh"
if ! find_active_session; then
    echo "$LOG_PREFIX no active session (code $?), skip"
    exit 0
fi
SESSION_ID="$ACTIVE_SESSION_ID"
TRANSCRIPT="$ACTIVE_TRANSCRIPT"
SIZE_BYTES="$ACTIVE_SIZE_BYTES"

if [ "$SIZE_BYTES" -lt "$MIN_SIZE_BYTES" ]; then
    echo "$LOG_PREFIX session ${SIZE_BYTES}B below threshold, skip"
    exit 0
fi

# --- Advancement gate: only summarize genuinely new turns ---
# jsonl is one turn per line, so line count is a clean, cheap offset. On a new or
# unknown session, or any parse failure, LAST_LINES=0 => behaves like the old
# "summarize the tail" path (fail-open).
CUR_LINES=$(wc -l < "$TRANSCRIPT" 2>/dev/null || echo 0)
case "$CUR_LINES" in ''|*[!0-9]*) CUR_LINES=0;; esac

LAST_SESSION=""
LAST_LINES=0
if [ -f "$STATE_FILE" ]; then
    read -r LAST_SESSION LAST_LINES < "$STATE_FILE" 2>/dev/null || { LAST_SESSION=""; LAST_LINES=0; }
fi
# Only trust the stored offset if it belongs to the same session.
if [ "$LAST_SESSION" != "$SESSION_ID" ]; then
    LAST_LINES=0
fi
case "$LAST_LINES" in ''|*[!0-9]*) LAST_LINES=0;; esac
# Guard against a shrunk/rotated transcript (offset past EOF): reset to 0.
if [ "$LAST_LINES" -gt "$CUR_LINES" ]; then
    LAST_LINES=0
fi

NEW_LINES=$(( CUR_LINES - LAST_LINES ))
if [ "$NEW_LINES" -lt "$MIN_NEW_LINES" ]; then
    # Nothing meaningfully new since last compaction. Do NOT update state, so small
    # increments accumulate across ticks until they cross the threshold.
    echo "$LOG_PREFIX only $NEW_LINES new lines (<$MIN_NEW_LINES) since last compaction, skip"
    exit 0
fi

# Extract only the NEW turns since last run, capped at RECENT_TURNS most-recent.
TURNS_RAW=$(tail -n +"$(( LAST_LINES + 1 ))" "$TRANSCRIPT" 2>/dev/null | tail -n "$RECENT_TURNS")
if [ -z "$TURNS_RAW" ]; then
    echo "$LOG_PREFIX empty new-turn slice, skip"
    exit 0
fi

# Build the prompt for haiku. Keep it short and task-scoped.
read -r -d '' PROMPT <<'EOF' || true
You are a session compactor. Summarize the following Claude Code session turns into a single dated block in exactly this format, no preamble, no code fence:

### {{DATE}}. {{short 3-5 word title}}
- {{what happened: 1-3 bullets, concrete, names + decisions}}
- {{current state / what's mid-way}}
- {{open follow-ups or pending items, if any}}

Rules:
- Under 10 bullets total
- No filler, no recap of conversation structure, no "we discussed"
- Preserve: specific names, file paths, commands, numbers, decisions
- Drop: pleasantries, tool output dumps, repeated greetings

Session turns follow:
===
EOF

DATE_STAMP=$(TZ="${AGENT_TZ:-UTC}" date '+%Y-%m-%d %H:%M')

# Call claude -p with a cheap model, pipe the turns in
BLOCK=$(printf '%s\n%s\n' "$PROMPT" "$TURNS_RAW" | \
    "$CLAUDE_BIN" -p --model "$CLAUDE_MODEL" 2>/dev/null || echo "")

if [ -z "$BLOCK" ]; then
    echo "$LOG_PREFIX haiku call returned empty, skip"
    exit 1
fi

# Substitute the date if the model used the placeholder
BLOCK=$(echo "$BLOCK" | sed "s/{{DATE}}/$DATE_STAMP/")

# Ensure block starts with ### header; if not, prepend a default
if ! echo "$BLOCK" | head -1 | grep -q '^### '; then
    BLOCK=$'### '"$DATE_STAMP"". auto-compaction"$'\n'"$BLOCK"
fi

# Append to bootstrap under "## Recent Compaction Blocks", then truncate to MAX_BLOCKS.
if python3 - "$BOOTSTRAP" "$BLOCK" "$MAX_BLOCKS" <<'PY'
import sys, re, pathlib

path = pathlib.Path(sys.argv[1])
new_block = sys.argv[2].strip()
max_blocks = int(sys.argv[3])

text = path.read_text()
marker = "## Recent Compaction Blocks"
if marker not in text:
    sys.stderr.write(f"marker not found in {path}\n")
    sys.exit(1)

head, _, body = text.partition(marker)

# Split existing blocks by ### headings
existing = re.split(r'(?m)(?=^### )', body)
preamble_chunks = []
blocks = []
for chunk in existing:
    if chunk.strip().startswith('### '):
        blocks.append(chunk.rstrip() + '\n')
    else:
        preamble_chunks.append(chunk)
preamble = ''.join(preamble_chunks).rstrip() + '\n'

# Drop "_(no blocks yet)_" placeholder if present
preamble = re.sub(r'_\(no blocks yet\)_\n?', '', preamble)

# Prepend new block, truncate
blocks.insert(0, new_block.strip() + '\n')
blocks = blocks[:max_blocks]

# Rebuild
rebuilt = head + marker + '\n' + preamble.rstrip() + '\n\n' + '\n'.join(blocks).rstrip() + '\n'
path.write_text(rebuilt)
print(f"compacted: {len(blocks)} blocks kept")
PY
then
    # Only advance the offset when the append actually succeeded.
    # SSOT-canonical write. Fallback to direct file write if ssot unavailable.
    python3 "$WORKSPACE/scripts/memory/ssot.py" set session.compact_on_rotate "$SESSION_ID $CUR_LINES" \
        --by compact-on-rotate --reason "rotate marker" >/dev/null 2>&1 \
        || printf '%s %s\n' "$SESSION_ID" "$CUR_LINES" > "$STATE_FILE"
    echo "$LOG_PREFIX compacted session $SESSION_ID into $BOOTSTRAP (offset -> $CUR_LINES)"
else
    echo "$LOG_PREFIX python append failed (rc $?), state not advanced"
    exit 1
fi
