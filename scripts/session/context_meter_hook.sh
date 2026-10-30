#!/bin/bash
# context_meter_hook.sh, UserPromptSubmit hook: tell the model how full its context window is.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
#
# Pattern from Mainplane (context management). A UserPromptSubmit hook's stderr is not shown
# to the model on exit 0, so the meter is returned as additionalContext instead.
# Prompt size = the last assistant step's input + cache-read + cache-write tokens, read from the
# transcript tail. Silent below 60% of the window.
#
#   >= 60%  one-line meter
#   >= 75%  save at the next natural break, keep the handoff current
#   >= 85%  compaction is close: write the session-bootstrap handoff and /save now
#
# Env: CONTEXT_WINDOW (tokens, default 200000; set it to your model's window).
# Wire under UserPromptSubmit in settings.json (see settings.example.json).
# FAIL-OPEN: any error prints "{}" and exits 0. Sub-second budget (3 s cap on the parse).
set -uo pipefail
trap 'echo "{}"; exit 0' ERR

HOOK_EVENT=$(cat 2>/dev/null || echo '{}')
TRANSCRIPT=$(printf '%s' "$HOOK_EVENT" | python3 -c 'import sys,json
try: print(json.loads(sys.stdin.read() or "{}").get("transcript_path") or "")
except Exception: print("")' 2>/dev/null || true)

METER=$(TP="$TRANSCRIPT" WIN="${CONTEXT_WINDOW:-200000}" timeout 3 python3 -c '
import json, os
tp, win = os.environ.get("TP", ""), int(os.environ.get("WIN", "200000"))
if not tp or not os.path.exists(tp):
    raise SystemExit
size = os.path.getsize(tp)
start = max(0, size - 4_000_000)
with open(tp, "rb") as f:
    f.seek(start)
    lines = f.read().splitlines()
if start:
    lines = lines[1:]  # first line may be cut mid-record
used = 0
for ln in reversed(lines):
    try:
        d = json.loads(ln)
    except Exception:
        continue
    u = (d.get("message") or {}).get("usage") if d.get("type") == "assistant" else None
    if u:
        used = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
        break
pct = used * 100 // win if win else 0
if pct >= 85:
    print(f"CONTEXT {used // 1000}k of {win // 1000}k ({pct}%). Compaction is close: write the session-bootstrap handoff and /save now.")
elif pct >= 75:
    print(f"CONTEXT {used // 1000}k of {win // 1000}k ({pct}%). Save at the next natural break and keep the handoff current.")
elif pct >= 60:
    print(f"CONTEXT {used // 1000}k of {win // 1000}k ({pct}%).")
' 2>/dev/null || true)

if [ -n "$METER" ]; then
    METER="$METER" python3 -c 'import json,os;print(json.dumps({"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":os.environ["METER"]}}))'
else
    echo "{}"
fi
exit 0
