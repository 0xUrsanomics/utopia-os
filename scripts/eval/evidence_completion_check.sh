#!/bin/bash
# SOFT completion-evidence nudge. If this turn edited code files but the session
# has recorded ZERO verification evidence (evidence_ledger.py), emit a ONE-TIME
# soft reminder to test before claiming done ("done = tested end-to-end, not code
# written"). NEVER blocks (always exit 0). Once per session via a flag file.
set -uo pipefail
ROOT="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
LEDGER="$ROOT/scripts/eval/evidence_ledger.py"
FLAGDIR="$ROOT/memory/state/evidence_warned"
EVENT=$(cat 2>/dev/null || echo '{}')
PARSED=$(printf '%s' "$EVENT" | python3 -c 'import sys,json
try:
    d=json.loads(sys.stdin.read() or "{}"); print((d.get("session_id") or "")+"\t"+(d.get("transcript_path") or ""))
except Exception: print("\t")' 2>/dev/null || printf '\t')
SID="${PARSED%%$'\t'*}"; TP="${PARSED#*$'\t'}"
[ -z "${SID:-}" ] && { echo "{}"; exit 0; }
mkdir -p "$FLAGDIR" 2>/dev/null || true
FLAG="$FLAGDIR/$SID"
[ -f "$FLAG" ] && { echo "{}"; exit 0; }          # already nudged this session
{ [ -z "${TP:-}" ] || [ ! -f "$TP" ]; } && { echo "{}"; exit 0; }

# did this turn edit code files since the last user message?
EDITED=$(tail -n 300 "$TP" 2>/dev/null | python3 -c '
import sys, json
lines = sys.stdin.readlines()
anchor = 0
for i in range(len(lines)-1, -1, -1):
    try: d = json.loads(lines[i])
    except Exception: continue
    if d.get("type") == "user":
        c = d.get("message", {}).get("content")
        if isinstance(c, str):
            anchor = i; break
code = (".py", ".sh", ".js", ".ts", ".mjs")
edited = False
for i in range(anchor+1, len(lines)):
    try: d = json.loads(lines[i])
    except Exception: continue
    if d.get("type") != "assistant": continue
    mc = d.get("message", {}).get("content")
    if not isinstance(mc, list): continue
    for b in mc:
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in ("Write","Edit","MultiEdit"):
            fp = str((b.get("input") or {}).get("file_path",""))
            if fp.endswith(code): edited = True
print("1" if edited else "0")
' 2>/dev/null || echo 0)

if [ "$EDITED" = "1" ]; then
    if ! python3 "$LEDGER" check --session "$SID" >/dev/null 2>&1; then
        touch "$FLAG" 2>/dev/null || true
        echo "note: this session edited code but recorded no verification. Before claiming done, run a check + record it (python3 scripts/eval/evidence_ledger.py record ...). done = tested, not written. (soft, once per session)" >&2
    fi
fi
echo "{}"
exit 0
