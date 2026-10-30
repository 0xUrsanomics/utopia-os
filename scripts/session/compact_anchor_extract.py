#!/usr/bin/env python3
# compact_anchor_extract.py: keep the exact details a compaction summary drops.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Keep the exact details a compaction summary drops (Compact-Bench, arXiv 2610.31710: LLM summaries kept
about 15% of recurring details, a regex extractor about 79%).

  extract  (PreCompact, event JSON on stdin) -> memory/state/compact-anchors/<session_id>.md
  emit     (SessionStart matcher "compact", event JSON on stdin) -> prints the anchors back as context

Pulls 8 detail types from the last TAIL characters of the transcript, newest first, capped per type:
file paths, commit/sha hashes, PR/issue/chat message ids, error types, URLs, key=value pairs, IPs.
Anything that looks like a secret is dropped before writing. FAIL-OPEN: never blocks compaction or startup.

Wire it as two hooks (see settings.example.json):
  PreCompact                      python3 scripts/session/compact_anchor_extract.py extract
  SessionStart (matcher compact)  python3 scripts/session/compact_anchor_extract.py emit
Env: AGENT_ROOT (default: two levels up). Anchors live in $AGENT_ROOT/memory/state/compact-anchors/.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DIR = REPO / "memory/state/compact-anchors"
TAIL, CAP, MAX_AGE_S, KEEP = 400_000, 30, 6 * 3600, 20

PATTERNS = {
    "paths": r"(?:/(?:home|Users)/[\w./-]+|(?:scripts|sandbox|outputs|memory|knowledge|skills|docs|logs)/[\w./-]+)",
    "hashes": r"(?<![-\w])(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,64}(?![-\w])",
    "ids": r"\b(?:PR|issue|Issue|msg)\s?#?\d{2,6}\b|(?<![\w/&])#\d{2,6}\b",
    "errors": r"\b[A-Z][A-Za-z]+(?:Error|Exception)\b(?::[^\\\"]{0,80})?",
    "urls": r"https?://[^\s\"'\\)<>\]]+",
    "key_values": r"\b[a-z_][a-z0-9_]{2,30}=[^\s\"'\\,;&]{1,60}",
    "ips": r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{2,5})?\b",
}
SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|passw|bearer|authorization|credential|private[_-]?key|"
                    r"sk-[a-z0-9]|ghp_|gho_|xox[abp]-|akia[0-9a-z]|\.env\b|\.ssh|wallet|seed|mnemonic|"
                    r"\b\d{8,10}:[\w-]{30,})")
LONG = re.compile(r"[A-Za-z0-9+_-]{40,}")


def is_secret(v):
    """Secret-looking words, or a long opaque token that is not plain hex (hex hashes are kept)."""
    if SECRET.search(v):
        return True
    return any(not re.fullmatch(r"[0-9a-f]+", m.group(0)) for m in LONG.finditer(v))


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def extract_text(path):
    """Message content only (text, tool inputs, tool results); transcript metadata like uuids is skipped."""
    p = Path(path)
    size = p.stat().st_size
    with open(p, "rb") as f:
        start = max(0, size - TAIL)
        f.seek(start)
        lines = f.read().decode("utf-8", "replace").splitlines()
        if start:
            lines = lines[1:]  # first line may be cut mid-record
    parts = []
    for ln in lines:
        try:
            content = (json.loads(ln).get("message") or {}).get("content")
        except Exception:
            continue
        parts.extend(strings(content))
    return "\n".join(parts)


def anchors(text):
    out = {}
    for kind, pat in PATTERNS.items():
        seen, vals = set(), []
        for m in reversed(list(re.finditer(pat, text))):
            v = m.group(0).rstrip(".,:;)]")
            if v in seen or is_secret(v):
                continue
            seen.add(v)
            vals.append(v)
            if len(vals) >= CAP:
                break
        out[kind] = vals
    return out


def render(a, sid):
    lines = [f"# Compact anchors (session {sid}, {time.strftime('%Y-%m-%d %H:%M:%S')})",
             "Exact strings from the last part of the transcript before compaction, newest first."]
    for kind, vals in a.items():
        if vals:
            lines.append(f"{kind}: " + " | ".join(vals))
    return "\n".join(lines) + "\n"


def event():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def extract():
    ev = event()
    tp, sid = ev.get("transcript_path"), ev.get("session_id") or "none"
    if not tp or not Path(tp).exists():
        return
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{sid}.md").write_text(render(anchors(extract_text(tp)), sid))
    for old in sorted(DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP:]:
        old.unlink(missing_ok=True)


def emit():
    sid = event().get("session_id") or "none"
    f = DIR / f"{sid}.md"
    log = DIR.parent / "session-logs" / f"{sid}.log"
    parts = []
    if f.exists() and time.time() - f.stat().st_mtime <= MAX_AGE_S:
        parts.append(f.read_text())
    if log.exists():  # pattern from Mainplane: point at the full, searchable prior session
        parts.append(f"Full prior session, searchable: {log} (rg -n 'term' on it; a hit's header is the nearest "
                     "line above starting {\"n\":). Retrieve exact details from it instead of trusting the summary.")
    if parts:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "\n".join(parts)}}))


if __name__ == "__main__":
    try:
        {"extract": extract, "emit": emit}[sys.argv[1]]()
    except Exception:
        pass
    sys.exit(0)
