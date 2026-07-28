#!/usr/bin/env python3
"""Read-only MCP server over the Markdown memory tier and the SSOT state store.

WHY READ-ONLY, AND WHY THAT IS WRITTEN INTO THE FILE RATHER THAN LEFT AS A TODO.

This server can read your memory. It cannot write to it, and that is a decision rather than
an unfinished feature. Three reasons, all of which have to stop being true before a write
tool belongs here:

  1. **A tool call is not a confirmation gate.** In this stack the human-in-the-loop gate
     lives in the harness hook layer, and several supported harnesses have no hook layer at
     all. A published write tool would therefore hand any agent, on any harness, an
     unmediated path into the files the whole system treats as ground truth.
  2. **It would forge the audit trail.** `ssot.set_` requires an author (`by`) and refuses an
     anonymous write precisely so that every state change is attributable to a person. A tool
     call can put any string in that field, which does not break the log so much as quietly
     make it lie.
  3. **Memory corruption is the failure this architecture cannot recover from, and it is
     silent.** Everything downstream inherits from these files. A bad write does not raise;
     it just makes the system confidently wrong from then on.

Reading is most of the value anyway, and it is the part `recall` does not cover: recall
returns semantically similar CHUNKS, while this returns a named file exactly and in full.

THE PATH JAIL IS THE SECURITY BOUNDARY. Every read is resolved and then required to sit
inside `memory/`. Traversal (`../`), absolute paths, and symlinks that point outside are all
refused after resolution rather than by pattern-matching the input, because input filtering
is a blocklist and resolution is a decision. Two directories are excluded even inside the
jail: `memory/state/`, which holds the runtime store rather than notes, and anything that is
not a text note by extension. State is reachable, but only through the SSOT API, which reads
the database properly instead of handing out raw bytes.

RUN IT

    python3 scripts/memory/memory_server.py              # speaks MCP on stdin/stdout
    python3 scripts/memory/memory_server.py --selftest   # no memory dir needed

Wire it as the `memory` entry in your harness adapter's MCP config.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("AGENT_ROOT", str(HERE.parents[1])))
MEMORY_ROOT = (ROOT / "memory").resolve()

SERVER_NAME = "utopia-memory"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2025-06-18"

# Notes only. An extension allowlist rather than a blocklist: a blocklist has to predict every
# bad case, an allowlist only has to name the good ones.
ALLOWED_SUFFIXES = {".md", ".markdown", ".txt", ".json"}
# Inside the jail but still off limits: runtime state, not notes. State has a proper reader.
EXCLUDED_DIRS = {"state"}
MAX_BYTES = 400_000


class Refused(PermissionError):
    """A read that the jail declined. Distinct from 'not found' on purpose."""


def _resolve(rel: str) -> Path:
    """Resolve a caller-supplied path and prove it lands inside the jail.

    Resolution FIRST, judgement second. Checking the raw string for '..' would miss a symlink
    and would reject legitimate names; resolving and then asking "is this under memory/" is a
    decision about where the path actually points.
    """
    if not rel or not rel.strip():
        raise ValueError("path is empty")
    p = (MEMORY_ROOT / rel).resolve()
    try:
        inside = p.is_relative_to(MEMORY_ROOT)
    except AttributeError:  # Python 3.8
        inside = str(p).startswith(str(MEMORY_ROOT) + os.sep)
    if not inside:
        raise Refused(f"path escapes the memory jail: {rel!r} resolves outside {MEMORY_ROOT}")
    parts = p.relative_to(MEMORY_ROOT).parts
    if parts and parts[0] in EXCLUDED_DIRS:
        raise Refused(
            f"{parts[0]}/ is runtime state, not notes, and is not readable as a file. "
            f"Use get_state or state_log, which read the store properly.")
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        raise Refused(f"suffix {p.suffix!r} is not a readable note type "
                      f"(allowed: {', '.join(sorted(ALLOWED_SUFFIXES))})")
    return p


def tool_read_memory_file(args: dict) -> str:
    p = _resolve(args.get("path") or "")
    if not p.exists():
        return json.dumps({"path": args.get("path"), "exists": False,
                           "note": "no such file under memory/"}, indent=2)
    if not p.is_file():
        raise ValueError(f"{args.get('path')!r} is not a file")
    size = p.stat().st_size
    if size > MAX_BYTES:
        raise ValueError(f"file is {size} bytes, over the {MAX_BYTES} read cap. "
                         f"Read a smaller file or raise MAX_BYTES deliberately.")
    return json.dumps({
        "path": str(p.relative_to(MEMORY_ROOT)),
        "exists": True, "bytes": size,
        "content": p.read_text(encoding="utf-8", errors="replace"),
    }, indent=2, ensure_ascii=False)


def tool_list_memory(args: dict) -> str:
    sub = (args.get("subdir") or "").strip().strip("/")
    base = MEMORY_ROOT
    if sub:
        base = (MEMORY_ROOT / sub).resolve()
        try:
            inside = base.is_relative_to(MEMORY_ROOT)
        except AttributeError:
            inside = str(base).startswith(str(MEMORY_ROOT) + os.sep)
        if not inside:
            raise Refused(f"subdir escapes the memory jail: {sub!r}")
    if not MEMORY_ROOT.exists():
        # Says which, rather than returning an empty list that reads like "no memory yet".
        return json.dumps({"files": [], "count": 0,
                           "note": f"no memory directory at {MEMORY_ROOT}. Copy "
                                   f"memory/templates/ first (see QUICKSTART.md)."}, indent=2)
    if not base.exists():
        return json.dumps({"files": [], "count": 0,
                           "note": f"no such subdir: {sub!r}"}, indent=2)
    out = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        rel = p.relative_to(MEMORY_ROOT)
        if rel.parts and rel.parts[0] in EXCLUDED_DIRS:
            continue
        out.append({"path": str(rel), "bytes": p.stat().st_size})
    return json.dumps({"files": out, "count": len(out),
                       "excluded": sorted(EXCLUDED_DIRS)}, indent=2)


def _ssot():
    sys.path.insert(0, str(HERE))
    import ssot
    return ssot


def tool_get_state(args: dict) -> str:
    key = (args.get("key") or "").strip()
    s = _ssot()
    if not key:
        return json.dumps({"state": s.dump(args.get("prefix") or "")}, indent=2, default=str)
    return json.dumps({"key": key, "value": s.get(key, args.get("default"))},
                      indent=2, default=str)


def tool_state_log(args: dict) -> str:
    s = _ssot()
    return json.dumps({"log": s.log(args.get("key"), int(args.get("limit") or 20))},
                      indent=2, default=str)


TOOLS = [
    {"name": "read_memory_file",
     "description": ("Read one memory file in full, by path relative to memory/. Use this when "
                     "you need a named file exactly (SOUL.md, USER.md); use recall when you "
                     "want semantically similar passages instead."),
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Relative to memory/, e.g. 'USER.md' or 'Context/foo.md'."}},
         "required": ["path"]}},
    {"name": "list_memory",
     "description": "List readable memory files, optionally under a subdirectory.",
     "inputSchema": {"type": "object", "properties": {
         "subdir": {"type": "string", "description": "Optional subdirectory, e.g. 'Context'."}}}},
    {"name": "get_state",
     "description": ("Read operational state from the SSOT store. Omit key to dump everything "
                     "(optionally filtered by prefix). Read-only."),
     "inputSchema": {"type": "object", "properties": {
         "key": {"type": "string", "description": "Dotted key, e.g. 'persona.active'."},
         "prefix": {"type": "string", "description": "Prefix filter when dumping."},
         "default": {"type": "string", "description": "Returned when the key is unset."}}}},
    {"name": "state_log",
     "description": "Read the SSOT change log: who changed what, when, and why. Read-only.",
     "inputSchema": {"type": "object", "properties": {
         "key": {"type": "string", "description": "Optional key filter."},
         "limit": {"type": "integer", "description": "Max entries. Default 20."}}}},
]

HANDLERS = {"read_memory_file": tool_read_memory_file, "list_memory": tool_list_memory,
            "get_state": tool_get_state, "state_log": tool_state_log}


def handle(req: dict):
    method, req_id = req.get("method"), req.get("id")
    params = req.get("params") or {}
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        fn = HANDLERS.get(params.get("name"))
        if fn is None:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32602, "message": f"unknown tool: {params.get('name')}"}}
        try:
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": fn(params.get("arguments") or {})}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}}
    if req_id is None:
        return None
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> None:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700, "message": "parse error"}}) + "\n")
            stdout.flush()
            continue
        resp = handle(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


def selftest() -> int:
    """Weighted toward what the server must REFUSE.

    A read-only server that reads the right files is easy; one that cannot be talked out of
    the jail is the actual requirement, so most of these assert a refusal.
    """
    import io, tempfile
    checks, failed = [], 0

    def check(label, cond):
        nonlocal failed
        checks.append((label, bool(cond)))
        if not cond:
            failed += 1

    def call(name, args):
        return handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})["result"]

    r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2099-01-01"}})
    check("initialize echoes the client protocol version",
          r["result"]["protocolVersion"] == "2099-01-01")
    check("initialized notification gets no reply",
          handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)
    r = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    check("tools/list returns all four read tools",
          {t["name"] for t in r["result"]["tools"]}
          == {"read_memory_file", "list_memory", "get_state", "state_log"})
    check("NO write tool is exposed",
          not any(w in t["name"] for t in r["result"]["tools"]
                  for w in ("write", "set", "append", "delete", "update")))
    check("unknown method is -32601",
          handle({"jsonrpc": "2.0", "id": 3, "method": "zzz"})["error"]["code"] == -32601)

    # --- the jail, which is the whole security story --------------------------------------
    for bad, why in [
        ("../../../etc/passwd", "parent traversal"),
        ("/etc/passwd", "absolute path"),
        ("../.env", "the .env one directory up"),
        ("../../.ssh/id_rsa", "ssh key by traversal"),
        ("state/ssot.sqlite", "the raw state database"),
        ("state/anything.md", "anything under state/"),
    ]:
        out = call("read_memory_file", {"path": bad})
        check(f"REFUSED: {why}", out.get("isError") and
              ("Refused" in out["content"][0]["text"] or "escapes" in out["content"][0]["text"]))

    out = call("read_memory_file", {"path": "notes.exe"})
    check("REFUSED: non-note file extension", out.get("isError"))
    out = call("read_memory_file", {"path": ""})
    check("REFUSED: empty path", out.get("isError"))

    # --- behaviour with a real jail --------------------------------------------------------
    global MEMORY_ROOT
    saved = MEMORY_ROOT
    try:
        td = Path(tempfile.mkdtemp()) / "memory"
        (td / "Context").mkdir(parents=True)
        (td / "state").mkdir()
        (td / "USER.md").write_text("# user\nhello\n", encoding="utf-8")
        (td / "Context" / "thing.md").write_text("ctx\n", encoding="utf-8")
        (td / "state" / "secret.md").write_text("should never be listed\n", encoding="utf-8")
        MEMORY_ROOT = td.resolve()

        out = call("read_memory_file", {"path": "USER.md"})
        check("reads a real file in full",
              (not out.get("isError")) and "hello" in json.loads(out["content"][0]["text"])["content"])
        out = call("read_memory_file", {"path": "nope.md"})
        body = json.loads(out["content"][0]["text"])
        check("missing file reports exists:false rather than erroring", body["exists"] is False)

        listing = json.loads(call("list_memory", {})["content"][0]["text"])
        paths = {f["path"] for f in listing["files"]}
        check("listing includes notes", "USER.md" in paths and "Context/thing.md" in paths)
        check("listing EXCLUDES anything under state/",
              not any(p.startswith("state/") for p in paths))

        MEMORY_ROOT = (td.parent / "does-not-exist").resolve()
        listing = json.loads(call("list_memory", {})["content"][0]["text"])
        check("absent memory dir says so instead of returning a bare empty list",
              listing["count"] == 0 and "no memory directory" in listing["note"])
    finally:
        MEMORY_ROOT = saved

    out = io.StringIO()
    serve(io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
                      'not json\n'
                      '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'), out)
    lines = [l for l in out.getvalue().splitlines() if l.strip()]
    check("stdio transport: 2 replies for 3 lines (notification is silent)", len(lines) == 2)
    check("malformed line is a parse error and does not kill the loop",
          json.loads(lines[1])["error"]["code"] == -32700)

    width = max(len(c[0]) for c in checks)
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}", file=sys.stderr)
    print(f"\n{len(checks) - failed}/{len(checks)} passed", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    serve()
