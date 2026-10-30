#!/usr/bin/env python3
# session_slimlog.py: a slim, rg-searchable log of a session so exact details survive compaction.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Write a slim, rg-searchable log of a Claude Code session, so exact details survive compaction.

Pattern from Mainplane (github.com/mainplane-ai/mainplane, pkg/harness/tools.go "Context
Management"): instead of trusting a summary, a continuing session gets a pointer to the full prior
session log and retrieves exact details with rg. The raw transcript is the wrong file for that (it
grows to hundreds of MB of JSONL full of API blobs and base64), so this writes a lean copy:

  memory/state/session-logs/<session_id>.log
  one header line per record:  {"n":12,"t":"2026-01-01T09:00:00Z","role":"user","kind":"channel","tool":""}
  then the body text; tool results keep their first and last 1,000 characters.

Skipped: api-request rows, queue bookkeeping, images and base64, thinking blocks. Lines that look like
secrets are dropped (same filter as compact_anchor_extract.py). Incremental: a sidecar remembers the
byte offset reached, so each run only reads what was added since the last one.

    python3 session_slimlog.py <transcript.jsonl> [<session_id>]
    rg -n 'term' memory/state/session-logs/<session_id>.log   # header = nearest line above starting {"n":
FAIL-OPEN: any error exits 0 without touching the log.
Env: AGENT_ROOT (default: two levels up). Logs live in $AGENT_ROOT/memory/state/session-logs/.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compact_anchor_extract import is_secret  # noqa: E402

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
OUT = REPO / "memory/state/session-logs"
TEXT_CAP, RESULT_EDGE, KEEP = 6000, 1000, 6
B64 = re.compile(r"[A-Za-z0-9+/=]{200,}")


def clip(s: str, edge: int | None = None) -> str:
    s = B64.sub("[base64 dropped]", s)
    if edge and len(s) > 2 * edge:
        return f"{s[:edge]}\n[... {len(s) - 2 * edge} chars cut ...]\n{s[-edge:]}"
    return s if len(s) <= TEXT_CAP else s[:TEXT_CAP] + f"\n[... {len(s) - TEXT_CAP} chars cut ...]"


def clean(body: str) -> str:
    return "\n".join(ln for ln in body.splitlines() if not is_secret(ln))


def blocks(rec: dict):
    """Yield (role, kind, tool, text) for the parts of a transcript record worth keeping."""
    typ = rec.get("type")
    if typ == "attachment":
        att = rec.get("attachment") or {}
        if att.get("type") == "queued_command" and isinstance(att.get("prompt"), str):
            yield "user", "channel", "", att["prompt"]
        return
    if typ not in ("user", "assistant"):
        return
    msg = rec.get("message") or {}
    role, content = msg.get("role") or typ, msg.get("content")
    if isinstance(content, str):
        kind = "channel" if content.lstrip().startswith("<channel") else "text"
        yield role, kind, "", content
        return
    for b in content or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text":
            yield role, "text", "", b.get("text", "")
        elif t == "tool_use":
            yield role, "tool_use", b.get("name", ""), json.dumps(b.get("input"), ensure_ascii=False)
        elif t == "tool_result":
            c = b.get("content")
            if isinstance(c, list):
                c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
            yield role, "tool_result", "", "" if c is None else str(c)


def run(transcript: Path, sid: str) -> int:
    transcript.stat()  # a missing transcript fails here, before anything is created
    OUT.mkdir(parents=True, exist_ok=True)
    log, state = OUT / f"{sid}.log", OUT / f"{sid}.offset.json"
    st = json.loads(state.read_text()) if state.exists() else {"offset": 0, "n": 0}
    if st["offset"] > transcript.stat().st_size:  # transcript replaced: start over
        st = {"offset": 0, "n": 0}
        log.unlink(missing_ok=True)
    n, wrote = st["n"], 0
    with open(transcript, "rb") as fh, open(log, "a", encoding="utf-8") as out:
        fh.seek(st["offset"])
        for raw in fh:
            if not raw.endswith(b"\n"):
                break  # partial line still being written; pick it up next run
            st["offset"] += len(raw)
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            for role, kind, tool, text in blocks(rec):
                body = clean(clip(text, RESULT_EDGE if kind == "tool_result" else None)).strip()
                if not body:
                    continue
                n += 1
                hdr = {"n": n, "t": rec.get("timestamp", ""), "role": role, "kind": kind, "tool": tool}
                out.write(json.dumps(hdr) + "\n" + body + "\n")
                wrote += 1
    st["n"] = n
    state.write_text(json.dumps(st))
    for old in sorted(OUT.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP:]:
        old.unlink(missing_ok=True)
        old.with_suffix(".offset.json").unlink(missing_ok=True)
    print(f"slimlog: +{wrote} records, total {n}, {log}")
    return 0


if __name__ == "__main__":
    try:
        tp = Path(sys.argv[1])
        sys.exit(run(tp, sys.argv[2] if len(sys.argv) > 2 else tp.stem))
    except Exception as e:  # fail-open: never break a compaction
        print(f"slimlog skipped: {e}", file=sys.stderr)
        sys.exit(0)
