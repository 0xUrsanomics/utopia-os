#!/bin/bash
# precompact_handoff_snapshot.sh, PreCompact hook: keep mid-task state across a compaction.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# Before a context compaction drops mid-task state, three things are saved:
#   1. the current "## Active Handoff" block of memory/session-bootstrap.md, as a timestamped
#      snapshot, so the handoff survives the compact even if the live file drifts;
#   2. exact anchors (paths, hashes, ids, errors, URLs) from the transcript tail via
#      compact_anchor_extract.py; the SessionStart(compact) hook prints them back;
#   3. a slim rg-searchable log of the whole session via session_slimlog.py, run detached
#      because a first full pass can outrun the hook's time cap.
# FAIL-OPEN: never blocks compaction. Keeps only the last 20 snapshots.
#
# Env: AGENT_ROOT (default: two levels up from this file).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${AGENT_ROOT:-$(cd "$HERE/../.." && pwd)}"
BOOT="$ROOT/memory/session-bootstrap.md"
SNAPDIR="$ROOT/memory/state/handoff-snapshots"
EVENT=$(cat 2>/dev/null || echo '{}')
SID=$(printf '%s' "$EVENT" | python3 -c 'import sys,json
try: print(json.loads(sys.stdin.read() or "{}").get("session_id") or "none")
except Exception: print("none")' 2>/dev/null || echo none)
mkdir -p "$SNAPDIR" 2>/dev/null || true
TS=$(date -u +%Y%m%dT%H%M%SZ)
BOOT="$BOOT" OUTF="$SNAPDIR/${TS}-${SID}.md" python3 -c "
import os, sys
try:
    lines = open(os.environ['BOOT'], encoding='utf-8', errors='replace').read().splitlines()
except Exception:
    sys.exit(0)
out = []; grab = False
for ln in lines:
    if ln.startswith('## Active Handoff'):
        grab = True
    elif ln.startswith('## ') and grab:
        break
    if grab:
        out.append(ln)
open(os.environ['OUTF'], 'w', encoding='utf-8').write('\n'.join(out) or '(empty handoff)')
" 2>/dev/null || true
# Exact anchors from the transcript tail. Fail-open, 5 s cap.
printf '%s' "$EVENT" | timeout 5 python3 "$HERE/compact_anchor_extract.py" extract >/dev/null 2>&1 || true
# Slim searchable session log, detached. Later passes are incremental and take well under a second.
TP=$(printf '%s' "$EVENT" | python3 -c 'import sys,json
try: print(json.loads(sys.stdin.read() or "{}").get("transcript_path") or "")
except Exception: print("")' 2>/dev/null || true)
if [ -n "$TP" ] && [ -f "$TP" ]; then
  setsid nohup timeout 300 python3 "$HERE/session_slimlog.py" "$TP" "$SID" >/dev/null 2>&1 &
fi
# prune to the last 20 snapshots
ls -1t "$SNAPDIR"/*.md 2>/dev/null | tail -n +21 | xargs -r rm -f 2>/dev/null || true
echo "{}"
exit 0
