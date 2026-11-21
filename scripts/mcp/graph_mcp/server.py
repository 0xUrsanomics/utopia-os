#!/usr/bin/env python3
# server.py: MCP server over a Logseq graph or an Obsidian vault.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Knowledge-graph MCP server: read, search, query and (opt-in) write a Logseq graph or an
Obsidian vault. One core, one format backend per tool (see graph_backends.py).

TOOLS

  read      read_page, search, list_namespace, query_by_property, find_links,
            graph_stats, namespace_registry, read_journal
  write     create_page, update_page, append_to_page     (off unless GRAPH_MCP_WRITES=1)

WHY THE WRITE TOOLS ARE OPT-IN. The graph is the store recall treats as fact. In this stack the
human confirmation gate for a graph write lives in the harness hook layer (docs/security-gates.md),
and several supported harnesses have no hook layer. With writes on by default, any agent on any
harness would get an unmediated path into ground truth. So a fresh install is read-only, and
turning writes on is a deliberate act (one env var) on a harness where you have wired the gate.
The same argument is spelled out in scripts/memory/memory_server.py, which has no write tools.

SAFETY RULES, ALL ENFORCED HERE, NONE LEFT TO THE CALLER

  - Protected namespaces refuse every write. The check is case-folded, covers the page named
    exactly as the namespace, and is repeated on the resolved file, so 'reference/x', a symlinked
    folder, or an Obsidian folder alias cannot reach a protected page by another spelling.
  - Page names are validated before they become paths: no '..', no leading '/', no hidden
    segments, no '\\' or ':' and no control characters; Logseq also refuses '__', the filename
    encoding of '/'.
  - The path jail: every path is resolved, then required to sit inside the graph root. Traversal
    and symlinks out are decided by where the path lands, not by pattern-matching the input.
  - Size caps on reads, on write payloads, and on a page's total size after an append.
  - No shell. Nothing on a tool path spawns a process; the selftest checks the source for it.
  - A missing or non-directory graph root is a startup error, never an empty graph. A dead
    symlink that silently answers "no such page" is the failure this rule exists for.

CONFIGURATION (environment)

  GRAPH_FORMAT            logseq (default) or obsidian. --format overrides it.
  LOGSEQ_GRAPH_DIR        the Logseq graph root (holds pages/ and journals/). Required for logseq.
  OBSIDIAN_VAULT_DIR      the vault root (holds .obsidian/). Required for obsidian.
  GRAPH_NAMESPACES_FILE   the namespace registry (default: namespaces.example.json next to this file)
  GRAPH_MCP_WRITES        1 turns on create_page, update_page, append_to_page. Default off.
  GRAPH_DAILY_FOLDER      Obsidian daily notes folder, relative to the vault (default: vault root)
  GRAPH_DAILY_FORMAT      Obsidian daily note file name, strftime (default: %Y-%m-%d)
  LOCAL_UTC_OFFSET_HOURS  what "today" means for read_journal (default: the system's local time)

RUN IT

    python3 scripts/mcp/graph_mcp/server.py                     # MCP over stdio, stdlib only
    python3 scripts/mcp/graph_mcp/server.py --format obsidian
    python3 scripts/mcp/graph_mcp/server.py --sdk               # same tools via the pinned MCP SDK
    python3 scripts/mcp/graph_mcp/server.py --selftest          # temp graph + temp vault, no config
    python3 scripts/mcp/graph_mcp/server.py --selftest-sdk      # real stdio handshake through --sdk

The default transport is a stdlib JSON-RPC loop, the same as memory_server.py and
telegram_bridge.py, so the server runs on a bare Python. --sdk serves the identical tool table
through the official MCP SDK (requirements.txt in this folder pins the version) for clients that
need protocol features the stdlib loop does not implement.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import graph_backends as gb  # noqa: E402

SERVER_NAME = "utopia-graph"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2025-06-18"
DEFAULT_REGISTRY = HERE / "namespaces.example.json"
WRITE_TOOLS = {"create_page", "update_page", "append_to_page"}


class ConfigError(Exception):
    """Startup configuration is missing or wrong. The server refuses to start on it."""


CTX = {"backend": None, "writes": False}


# --- configuration ---------------------------------------------------------------------------

def load_registry(path) -> dict:
    p = Path(path).expanduser()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"namespace registry not found: {p}")
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"namespace registry unreadable ({p}): {e}")
    ns = data.get("namespaces") if isinstance(data, dict) else None
    if not isinstance(ns, dict) or not ns:
        raise ConfigError(f"namespace registry has no 'namespaces' object: {p}")
    for name, info in ns.items():
        if not isinstance(info, dict) or not isinstance(info.get("protected"), bool):
            raise ConfigError(f"namespace {name!r} needs an object with a boolean 'protected'")
        if info.get("template") is not None and not isinstance(info["template"], str):
            raise ConfigError(f"namespace {name!r}: 'template' must be a string or null")
        if "/" in name.strip("/") and name != name.strip("/"):
            raise ConfigError(f"namespace {name!r} may not start or end with '/'")
    data.setdefault("domains", {})
    return data


def load_backend(fmt=None, env=None) -> gb.Backend:
    env = os.environ if env is None else env
    fmt = (fmt or env.get("GRAPH_FORMAT") or "logseq").strip().lower()
    var = {"logseq": "LOGSEQ_GRAPH_DIR", "obsidian": "OBSIDIAN_VAULT_DIR"}.get(fmt)
    if var is None:
        raise ConfigError(f"GRAPH_FORMAT must be logseq or obsidian, got {fmt!r}")
    raw = (env.get(var) or "").strip()
    if not raw:
        raise ConfigError(f"{var} is not set. Point it at your {fmt} "
                          f"{'graph root (the folder holding pages/)' if fmt == 'logseq' else 'vault root'}.")
    root = Path(raw).expanduser()
    if not root.is_dir():
        raise ConfigError(f"{var} is not a directory: {raw}. A dead symlink or an unmounted drive "
                          f"looks like this; the server will not serve it as an empty graph.")
    registry = load_registry(env.get("GRAPH_NAMESPACES_FILE") or DEFAULT_REGISTRY)
    try:
        if fmt == "logseq":
            if not (root / "pages").is_dir():
                raise ConfigError(f"{var} has no pages/ folder: {raw}. Is this a Logseq graph root?")
            return gb.LogseqBackend(root, registry)
        return gb.ObsidianBackend(root, registry,
                                  daily_folder=env.get("GRAPH_DAILY_FOLDER", ""),
                                  daily_format=env.get("GRAPH_DAILY_FORMAT", "%Y-%m-%d"))
    except gb.Refused as e:
        raise ConfigError(str(e))


def writes_enabled(env=None) -> bool:
    env = os.environ if env is None else env
    return (env.get("GRAPH_MCP_WRITES") or "").strip().lower() in ("1", "true", "yes", "on")


def _today():
    off = os.environ.get("LOCAL_UTC_OFFSET_HOURS")
    if off:
        try:
            return datetime.now(timezone(timedelta(hours=float(off)))).date()
        except ValueError:
            pass
    return datetime.now().date()


# --- helpers ---------------------------------------------------------------------------------

def _b() -> gb.Backend:
    if CTX["backend"] is None:
        raise RuntimeError("no graph configured")
    return CTX["backend"]


def _read(p: Path) -> str:
    size = p.stat().st_size
    if size > gb.MAX_PAGE_BYTES:
        raise gb.Refused(f"page is {size} bytes, over the {gb.MAX_PAGE_BYTES} read cap")
    return p.read_text(encoding="utf-8", errors="replace")


def _meta(p: Path) -> dict:
    st = p.stat()
    return {"size_bytes": st.st_size, "modified": datetime.fromtimestamp(st.st_mtime).isoformat()}


def _domain(ns):
    return _b().namespaces.get(ns, {}).get("domain", "unknown") if ns else None


def _need_writes():
    if not CTX["writes"]:
        raise gb.Refused("writes are off. Set GRAPH_MCP_WRITES=1 on a harness where graph writes "
                         "go through your confirmation gate (see docs/logseq-graph.md).")


def _write_target(name: str) -> Path:
    """Validate a write: protection by name AND by resolved file, and no symlinked page file."""
    b = _b()
    if b.is_protected(name):
        raise gb.Refused(f"'{name}' is in a protected namespace. Writes are refused.")
    if b.raw_path(name).is_symlink():
        raise gb.Refused("the page file is a symlink. Writes through symlinks are refused.")
    p = b.page_path(name)
    if b.is_protected(b.name_for_path(p)):
        raise gb.Refused(f"'{name}' resolves to a protected page. Writes are refused.")
    return p


def _check_payload(content, cap: int) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content is empty")
    if len(content) > cap:
        raise ValueError(f"content is {len(content)} characters, over the {cap} limit")
    return content


def _atomic_write(p: Path, text: str):
    if len(text.encode("utf-8")) > gb.MAX_PAGE_BYTES:
        raise gb.Refused(f"the page would exceed the {gb.MAX_PAGE_BYTES}-byte cap")
    tmp = p.with_name(f".{p.name}.tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, p)


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


# --- tools -----------------------------------------------------------------------------------

def tool_read_page(a: dict) -> str:
    b = _b()
    name = b.validate_name(a.get("page_name"))
    p = b.page_path(name)
    if not p.is_file():
        return _dump({"status": "not_found", "page_name": name,
                      "hint": "check the namespace and the spelling" +
                              (", hyphens not spaces" if b.fmt == "logseq" else "")})
    text = _read(p)
    ns = b.namespace_of(name)
    return _dump({"page_name": name, "namespace": ns, "domain": _domain(ns),
                  "properties": b.properties(text), "content": text, **_meta(p)})


def tool_create_page(a: dict) -> str:
    _need_writes()
    b = _b()
    name = b.validate_name(a.get("page_name"))
    content = _check_payload(a.get("content"), gb.MAX_CONTENT_CHARS)
    ns = b.namespace_of(name)
    if not ns:
        raise ValueError(f"unknown namespace in '{name}'. Valid: {', '.join(sorted(b.namespaces))}")
    p = _write_target(name)
    if p.exists():
        raise ValueError(f"page '{name}' already exists. Use update_page or append_to_page.")
    template = b.namespaces[ns].get("template") if a.get("use_template") else None
    text = content.rstrip("\n") + "\n" + (("\n" + template) if template else "")
    if len(text.encode("utf-8")) > gb.MAX_PAGE_BYTES:
        raise gb.Refused(f"the page would exceed the {gb.MAX_PAGE_BYTES}-byte cap")
    p.parent.mkdir(parents=True, exist_ok=True)
    b.jail(p)  # re-check after mkdir: the parent chain must still resolve inside the root
    with open(p, "x", encoding="utf-8") as fh:  # 'x': never clobber a page created meanwhile
        fh.write(text)
    return _dump({"status": "created", "page_name": name, "namespace": ns, "domain": _domain(ns),
                  "template_used": bool(template), **_meta(p)})


def tool_update_page(a: dict) -> str:
    _need_writes()
    b = _b()
    name = b.validate_name(a.get("page_name"))
    content = _check_payload(a.get("content"), gb.MAX_CONTENT_CHARS)
    p = _write_target(name)
    if not p.is_file():
        return _dump({"status": "not_found", "page_name": name})
    _atomic_write(p, content if content.endswith("\n") else content + "\n")
    return _dump({"status": "updated", "page_name": name, **_meta(p)})


def tool_append_to_page(a: dict) -> str:
    _need_writes()
    b = _b()
    name = b.validate_name(a.get("page_name"))
    content = _check_payload(a.get("content"), gb.MAX_APPEND_CHARS)
    p = _write_target(name)
    if not p.is_file():
        return _dump({"status": "not_found", "page_name": name})
    existing = _read(p)
    new = existing.rstrip("\n") + "\n" + content.rstrip("\n") + "\n"
    _atomic_write(p, new)
    return _dump({"status": "appended", "page_name": name, "appended_chars": len(content), **_meta(p)})


def _ns_filter(raw):
    if raw in (None, ""):
        return None
    ns = _b().canonical_namespace(raw)
    if ns is None:
        raise ValueError(f"unknown namespace {raw!r}. Valid: {', '.join(sorted(_b().namespaces))}")
    return ns


def _in_ns(name: str, ns: str) -> bool:
    b = _b()
    canon = b._name(name) if isinstance(b, gb.ObsidianBackend) else name
    return canon.casefold().startswith(ns.casefold() + "/")


def tool_search(a: dict) -> str:
    b = _b()
    q = (a.get("query") or "").strip()
    if not q:
        raise ValueError("query is empty")
    if len(q) > 500:
        raise ValueError("query is over 500 characters")
    ns = _ns_filter(a.get("namespace"))
    limit = max(1, min(int(a.get("limit") or 20), 100))
    ql, results, skipped = q.casefold(), [], 0
    for name, p in b.iter_pages():
        if ns and not _in_ns(name, ns):
            continue
        try:
            text = _read(p)
        except (gb.Refused, OSError):
            skipped += 1
            continue
        if ql not in text.casefold() and ql not in name.casefold():
            continue
        hits = [{"line_num": i + 1, "text": line.strip()[:200]}
                for i, line in enumerate(text.split("\n")) if ql in line.casefold()]
        results.append({"page_name": name, "namespace": b.namespace_of(name),
                        "matches": len(hits), "context": hits[:5], **_meta(p)})
    # Rank the whole match set, THEN truncate. Stopping the scan at `limit` would return the
    # first N files in directory order and silently drop newer, better matches.
    results.sort(key=lambda r: (r["matches"], r["modified"]), reverse=True)
    return _dump({"query": q, "namespace_filter": ns, "count": len(results[:limit]),
                  "total_matches": len(results), "skipped_over_cap": skipped,
                  "results": results[:limit]})


def _pages_in(ns: str) -> list:
    b, out = _b(), []
    for name, p in b.iter_pages():
        if not _in_ns(name, ns):
            continue
        try:
            props = b.properties(_read(p))
            out.append({"page_name": name, "properties": props, **_meta(p)})
        except (gb.Refused, OSError) as e:
            out.append({"page_name": name, "error": f"unreadable: {e}", **_meta(p)})
    out.sort(key=lambda r: r.get("modified", ""), reverse=True)
    return out


def tool_list_namespace(a: dict) -> str:
    ns = _ns_filter(a.get("namespace"))
    if ns is None:
        raise ValueError("namespace is required")
    limit = max(1, min(int(a.get("limit") or 50), 200))
    pages = _pages_in(ns)
    return _dump({"namespace": ns, "domain": _domain(ns), "total": len(pages),
                  "count": len(pages[:limit]), "pages": pages[:limit]})


def _prop_matches(val, want: str) -> bool:
    w = want.casefold()
    if isinstance(val, list):
        return any(w in str(v).casefold() for v in val)
    return w in str(val).casefold()


def tool_query_by_property(a: dict) -> str:
    ns = _ns_filter(a.get("namespace"))
    if ns is None:
        raise ValueError("namespace is required")
    key = (a.get("property_name") or "").strip()
    want = (a.get("property_value") or "").strip()
    if not key or not want:
        raise ValueError("property_name and property_value are required")
    limit = max(1, min(int(a.get("limit") or 20), 100))
    matching = [pg for pg in _pages_in(ns)
                if key in pg.get("properties", {}) and _prop_matches(pg["properties"][key], want)]
    return _dump({"query": f"{ns} where {key} contains '{want}'",
                  "count": len(matching[:limit]), "results": matching[:limit]})


def tool_find_links(a: dict) -> str:
    b = _b()
    name = b.validate_name(a.get("page_name"))
    p = b.page_path(name)
    outgoing = b.links(_read(p)) if p.is_file() else []
    pages = list(b.iter_pages())
    base_count: dict = {}
    for n, _ in pages:
        k = n.rsplit("/", 1)[-1].casefold()
        base_count[k] = base_count.get(k, 0) + 1
    unique = {k for k, c in base_count.items() if c == 1}
    my_base = name.rsplit("/", 1)[-1].casefold()
    incoming, ambiguous = [], []
    for other, op in pages:
        if other.casefold() == name.casefold():
            continue
        try:
            targets = b.links(_read(op))
        except (gb.Refused, OSError):
            continue
        if any(b.link_points_to(t, name, unique) for t in targets):
            incoming.append(other)
        elif (b.fmt == "obsidian" and my_base not in unique
              and any("/" not in t and t.casefold() == my_base for t in targets)):
            ambiguous.append(other)
    out = {"page_name": name, "exists": p.is_file(), "outgoing_links": sorted(outgoing),
           "incoming_links": sorted(incoming), "total_connections": len(outgoing) + len(incoming)}
    if b.fmt == "obsidian":
        out["ambiguous_incoming"] = sorted(ambiguous)
        out["ambiguous_note"] = ("bare [[Name]] links where several notes share the basename; "
                                 "Obsidian picks one by its own rules, so these are not counted")
    return _dump(out)


def tool_graph_stats(a: dict) -> str:
    b = _b()
    per_ns = {ns: 0 for ns in b.namespaces}
    total = size = unnamespaced = 0
    for name, p in b.iter_pages():
        total += 1
        size += p.stat().st_size
        ns = b.namespace_of(name)
        if ns:
            per_ns[ns] += 1
        else:
            unnamespaced += 1
    domains: dict = {}
    for ns, c in per_ns.items():
        d = b.namespaces[ns].get("domain", "unknown")
        domains[d] = domains.get(d, 0) + c
    return _dump({"format": b.fmt, "root": str(b.root), "writes_enabled": CTX["writes"],
                  "total_pages": total, "total_size_mb": round(size / (1024 * 1024), 2),
                  "unnamespaced_pages": unnamespaced, "journal_entries": b.journal_count(),
                  "domains": domains,
                  "namespaces": {ns: {"count": c, "domain": b.namespaces[ns].get("domain"),
                                      "protected": b.namespaces[ns]["protected"]}
                                 for ns, c in per_ns.items()}})


def tool_namespace_registry(a: dict) -> str:
    b = _b()
    ns = {k: {"domain": v.get("domain"), "template": v.get("template"),
              "protected": v["protected"], "example_page": f"{k}/Example-Name",
              **({"obsidian_folder": v["obsidian_folder"]} if v.get("obsidian_folder") else {})}
          for k, v in b.namespaces.items()}
    return _dump({"format": b.fmt, "total_namespaces": len(ns),
                  "domains": b.registry.get("domains", {}), "naming_rules": b.naming_rules(),
                  "writes_enabled": CTX["writes"], "namespaces": ns})


def tool_read_journal(a: dict) -> str:
    b = _b()
    raw = a.get("date")
    d = gb.parse_date(raw) if raw else _today()
    p = b.journal_path(d)
    if not p.is_file():
        return _dump({"status": "not_found", "date": d.isoformat()})
    text = _read(p)
    return _dump({"date": d.isoformat(), "properties": b.properties(text), "content": text, **_meta(p)})


def _schema(props: dict, required=()):
    return {"type": "object", "properties": props, "required": list(required),
            "additionalProperties": False}


_NAME = {"type": "string", "description": "Page name with namespace, e.g. 'Project/Example-Name'."}
_NS = {"type": "string", "description": "A namespace from namespace_registry, e.g. 'Project'."}

TOOLS = [
    {"name": "read_page", "description": "Read one page in full: content plus parsed properties.",
     "inputSchema": _schema({"page_name": _NAME}, ["page_name"])},
    {"name": "search", "description": ("Case-insensitive full-text search over page names and "
                                       "content, ranked by match count."),
     "inputSchema": _schema({"query": {"type": "string"}, "namespace": _NS,
                             "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["query"])},
    {"name": "list_namespace", "description": "List the pages under a namespace, newest first, with properties.",
     "inputSchema": _schema({"namespace": _NS, "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
                            ["namespace"])},
    {"name": "query_by_property",
     "description": ("Pages in a namespace whose property contains a value (case-insensitive). "
                     "A list property matches when any element does."),
     "inputSchema": _schema({"namespace": _NS, "property_name": {"type": "string"},
                             "property_value": {"type": "string"},
                             "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                            ["namespace", "property_name", "property_value"])},
    {"name": "find_links", "description": "Outgoing [[links]] from a page and the pages that link to it.",
     "inputSchema": _schema({"page_name": _NAME}, ["page_name"])},
    {"name": "graph_stats", "description": "Page counts per namespace and domain, size, journal count.",
     "inputSchema": _schema({})},
    {"name": "namespace_registry",
     "description": "The namespace taxonomy, templates, protection flags and naming rules. Read it before writing.",
     "inputSchema": _schema({})},
    {"name": "read_journal", "description": "Read the daily journal note for a date (default: today).",
     "inputSchema": _schema({"date": {"type": "string", "description": "YYYY-MM-DD or YYYY_MM_DD"}})},
    {"name": "create_page",
     "description": ("Create a new page in a registered, unprotected namespace. Fails if it exists. "
                     "use_template appends the namespace skeleton after content."),
     "inputSchema": _schema({"page_name": _NAME, "content": {"type": "string"},
                             "use_template": {"type": "boolean"}}, ["page_name", "content"])},
    {"name": "update_page", "description": "Replace a page's full content. Read it first. Protected pages refuse.",
     "inputSchema": _schema({"page_name": _NAME, "content": {"type": "string"}}, ["page_name", "content"])},
    {"name": "append_to_page", "description": "Append to the end of an existing page (e.g. a timeline entry).",
     "inputSchema": _schema({"page_name": _NAME, "content": {"type": "string"}}, ["page_name", "content"])},
]

HANDLERS = {
    "read_page": tool_read_page, "search": tool_search, "list_namespace": tool_list_namespace,
    "query_by_property": tool_query_by_property, "find_links": tool_find_links,
    "graph_stats": tool_graph_stats, "namespace_registry": tool_namespace_registry,
    "read_journal": tool_read_journal, "create_page": tool_create_page,
    "update_page": tool_update_page, "append_to_page": tool_append_to_page,
}


def visible_tools() -> list:
    return [t for t in TOOLS if CTX["writes"] or t["name"] not in WRITE_TOOLS]


def call_tool(name: str, args: dict):
    """(text, is_error). Shared by both transports so they cannot disagree."""
    fn = HANDLERS.get(name)
    if fn is None:
        return f"unknown tool: {name}", True
    try:
        return fn(args or {}), False
    except Exception as e:
        return f"{type(e).__name__}: {e}", True


# --- stdlib JSON-RPC transport ---------------------------------------------------------------

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
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": visible_tools()}}
    if method == "tools/call":
        name = params.get("name")
        if name not in HANDLERS:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32602, "message": f"unknown tool: {name}"}}
        text, err = call_tool(name, params.get("arguments") or {})
        res = {"content": [{"type": "text", "text": text}]}
        if err:
            res["isError"] = True
        return {"jsonrpc": "2.0", "id": req_id, "result": res}
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
        resp = handle(req) if isinstance(req, dict) else None
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


# --- MCP SDK transport (optional, pinned in requirements.txt) --------------------------------

def serve_sdk() -> int:
    try:
        import anyio
        import mcp.types as types
        from mcp.server.lowlevel import Server
        from mcp.server.stdio import stdio_server
    except ImportError as e:
        print(f"--sdk needs the MCP SDK: pip install -r {HERE / 'requirements.txt'} ({e})", file=sys.stderr)
        return 2
    server = Server(SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def _list():
        return [types.Tool(name=t["name"], description=t["description"], inputSchema=t["inputSchema"])
                for t in visible_tools()]

    @server.call_tool()
    async def _call(name, arguments):
        if name not in HANDLERS:
            raise ValueError(f"unknown tool: {name}")
        text, err = call_tool(name, arguments or {})
        if err:
            raise RuntimeError(text)  # the SDK turns this into an isError result
        return [types.TextContent(type="text", text=text)]

    async def _main():
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())

    anyio.run(_main)
    return 0


# --- selftests -------------------------------------------------------------------------------

def _fixture(root: Path):
    """A Logseq graph and an Obsidian vault with invented content, plus an outside 'secret'."""
    outside = root / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("status:: leaked\nOUTSIDE-SECRET\n", encoding="utf-8")

    lg = root / "lgraph"
    (lg / "pages").mkdir(parents=True)
    (lg / "journals").mkdir()
    pg = lg / "pages"
    (pg / "Project___Alpha.md").write_text(
        "status:: active\ntags:: demo, sample\n\n## Compiled Truth\nWorking with [[Person/Jane-Doe]].\n"
        "\n## Timeline\n- 2026-01-10 kickoff\n", encoding="utf-8")
    (pg / "Project___Beta.md").write_text("status:: paused\n\nNo links, mentions alpha once.\n", encoding="utf-8")
    (pg / "Person___Jane-Doe.md").write_text("role:: engineer\n\nSee [[Project/Alpha]].\n", encoding="utf-8")
    (pg / "Reference___Policy.md").write_text("kind:: policy\n\nGround truth.\n", encoding="utf-8")
    (pg / "Reference.md").write_text("The namespace page itself.\n", encoding="utf-8")
    (pg / "Loose-Note.md").write_text("Mentions [[Person/Jane-Doe]] too.\n", encoding="utf-8")
    (pg / "Project___Huge.md").write_text("alpha " * (gb.MAX_PAGE_BYTES // 6 + 10), encoding="utf-8")
    os.symlink(outside / "secret.md", pg / "Project___Leak.md")
    (lg / "journals" / "2026_01_15.md").write_text("- journal entry for the fifteenth\n", encoding="utf-8")

    v = root / "vault"
    for d in (".obsidian", ".trash", "Project", "Person", "Concept", "Meeting", "Reference", "Daily", "People"):
        (v / d).mkdir(parents=True)
    (v / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
    (v / ".obsidian" / "hidden.md").write_text("alpha hidden config note\n", encoding="utf-8")
    (v / ".trash" / "old.md").write_text("alpha trashed\n", encoding="utf-8")
    (v / "Project" / "Alpha.md").write_text(
        "---\nstatus: active\ntags: [demo, \"sample tag\"]\nowners:\n  - Jane Doe\n  - Sam Roe\n"
        "summary: |\n  multi line\n  scalar\nnested:\n  a: 1\n---\n# Alpha\nWorking with [[Jane Doe]].\n",
        encoding="utf-8")
    (v / "Person" / "Jane Doe.md").write_text("---\nrole: engineer\n---\nSee [[Project/Alpha#Timeline|the project]].\n",
                                              encoding="utf-8")
    (v / "Concept" / "Graph.md").write_text("Links: [[Jane Doe|JD]], [[Alpha#Status]], [[Graph]].\n", encoding="utf-8")
    (v / "Meeting" / "Graph.md").write_text("A second note named Graph.\n", encoding="utf-8")
    (v / "Inbox.md").write_text("Bare link to [[Graph]] and to [[Person/Jane Doe.md]].\n", encoding="utf-8")
    (v / "Reference" / "Policy.md").write_text("---\nkind: policy\n---\nGround truth.\n", encoding="utf-8")
    (v / "Daily" / "2026-01-15.md").write_text("Daily note.\n", encoding="utf-8")
    os.symlink(outside, v / "Project" / "linked")
    os.symlink(v / "Reference", v / "Concept" / "refalias")
    os.symlink(v / ".obsidian", v / "Concept" / "cfg")
    return lg, v, outside


def selftest() -> int:
    import io
    import tempfile
    checks, failed = [], 0

    def check(label, cond):
        nonlocal failed
        checks.append((label, bool(cond)))
        if not cond:
            failed += 1

    def call(name, args=None):
        return handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args or {}}})["result"]

    def body(r):
        return json.loads(r["content"][0]["text"])

    def refused(r):
        return bool(r.get("isError")) and "Refused" in r["content"][0]["text"]

    def errored(r):
        return bool(r.get("isError"))

    saved = dict(CTX)
    td = Path(tempfile.mkdtemp())
    try:
        lg, v, outside = _fixture(td)

        # --- configuration ----------------------------------------------------------------
        for env, label, needle in [
            ({}, "missing LOGSEQ_GRAPH_DIR is a clear startup error", "LOGSEQ_GRAPH_DIR is not set"),
            ({"GRAPH_FORMAT": "obsidian"}, "missing OBSIDIAN_VAULT_DIR is a clear startup error",
             "OBSIDIAN_VAULT_DIR is not set"),
            ({"LOGSEQ_GRAPH_DIR": str(td / "nope")}, "a non-directory root refuses to start", "not a directory"),
            ({"LOGSEQ_GRAPH_DIR": str(v)}, "a Logseq root without pages/ refuses to start", "no pages/"),
            ({"GRAPH_FORMAT": "notion", "LOGSEQ_GRAPH_DIR": str(lg)}, "unknown format is refused", "logseq or obsidian"),
            ({"LOGSEQ_GRAPH_DIR": str(lg), "GRAPH_NAMESPACES_FILE": str(td / "none.json")},
             "a missing registry file fails closed", "not found"),
            ({"GRAPH_FORMAT": "obsidian", "OBSIDIAN_VAULT_DIR": str(v), "GRAPH_DAILY_FOLDER": "../outside"},
             "a daily folder outside the vault is refused", "'..'"),
        ]:
            try:
                load_backend(env=env)
                check(label, False)
            except ConfigError as e:
                check(label, needle in str(e))
        bad = td / "bad.json"
        bad.write_text('{"namespaces": {"Project": {"protected": "no"}}}', encoding="utf-8")
        try:
            load_registry(bad)
            check("a registry with a non-boolean 'protected' fails closed", False)
        except ConfigError:
            check("a registry with a non-boolean 'protected' fails closed", True)
        bad.write_text("{not json", encoding="utf-8")
        try:
            load_registry(bad)
            check("a malformed registry fails closed", False)
        except ConfigError:
            check("a malformed registry fails closed", True)
        check("writes are off unless GRAPH_MCP_WRITES is set",
              not writes_enabled({}) and writes_enabled({"GRAPH_MCP_WRITES": "1"}))

        # --- protocol ---------------------------------------------------------------------
        CTX["backend"] = load_backend(env={"LOGSEQ_GRAPH_DIR": str(lg)})
        CTX["writes"] = False
        r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}})
        check("initialize echoes the client protocol version", r["result"]["protocolVersion"] == "2099-01-01")
        check("initialized notification gets no reply",
              handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)
        names = {t["name"] for t in handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
        check("writes off: tools/list shows the 8 read tools and no write tool",
              names == set(HANDLERS) - WRITE_TOOLS)
        check("writes off: create_page is refused with the reason",
              refused(call("create_page", {"page_name": "Project/X", "content": "x"}))
              and "GRAPH_MCP_WRITES" in call("create_page", {"page_name": "Project/X", "content": "x"})["content"][0]["text"])
        CTX["writes"] = True
        names = {t["name"] for t in handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
        check("writes on: tools/list shows all 11 tools", names == set(HANDLERS) and len(names) == 11)
        check("unknown method is -32601", handle({"jsonrpc": "2.0", "id": 3, "method": "zzz"})["error"]["code"] == -32601)
        check("unknown tool is -32602", handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                                "params": {"name": "rm_rf"}})["error"]["code"] == -32602)

        # --- Logseq: reads ----------------------------------------------------------------
        r = body(call("read_page", {"page_name": "Project/Alpha"}))
        check("logseq read_page returns content and key:: properties",
              r["properties"].get("status") == "active" and "Compiled Truth" in r["content"]
              and r["namespace"] == "Project" and r["domain"] == "work")
        check("logseq read_page on a missing page is not_found, not an error",
              body(call("read_page", {"page_name": "Project/Nope"}))["status"] == "not_found")
        r = body(call("search", {"query": "ALPHA"}))
        found = [x["page_name"] for x in r["results"]]
        check("logseq search is case-insensitive and ranks by match count",
              "Project/Alpha" in found and "Project/Beta" in found)
        check("search skips a page over the read cap and counts it", "Project/Huge" not in found
              and r["skipped_over_cap"] >= 1)
        check("search never returns a symlink that leaves the graph",
              "Project/Leak" not in found and body(call("search", {"query": "OUTSIDE-SECRET"}))["count"] == 0)
        r = body(call("search", {"query": "jane", "namespace": "project"}))
        check("search namespace filter is case-folded and restricts results",
              [x["page_name"] for x in r["results"]] == ["Project/Alpha"])
        check("search with an unknown namespace is an error", errored(call("search", {"query": "a", "namespace": "Zzz"})))
        r = body(call("list_namespace", {"namespace": "Project"}))
        check("logseq list_namespace lists the namespace and skips the escaping symlink",
              {p["page_name"] for p in r["pages"]} >= {"Project/Alpha", "Project/Beta"}
              and "Project/Leak" not in {p["page_name"] for p in r["pages"]})
        check("list_namespace on an unknown namespace is an error", errored(call("list_namespace", {"namespace": "Zzz"})))
        r = body(call("query_by_property", {"namespace": "Project", "property_name": "status", "property_value": "ACTIVE"}))
        check("logseq query_by_property matches case-insensitively",
              [x["page_name"] for x in r["results"]] == ["Project/Alpha"])
        r = body(call("query_by_property", {"namespace": "Project", "property_name": "status", "property_value": "archived"}))
        check("query_by_property with no match returns 0", r["count"] == 0)
        r = body(call("find_links", {"page_name": "Person/Jane-Doe"}))
        check("logseq find_links finds incoming links from namespaced and loose pages",
              r["incoming_links"] == ["Loose-Note", "Project/Alpha"] and r["outgoing_links"] == ["Project/Alpha"])
        r = body(call("read_journal", {"date": "2026-01-15"}))
        check("logseq read_journal reads journals/YYYY_MM_DD.md", "fifteenth" in r["content"])
        check("read_journal accepts the underscore form", "fifteenth" in body(call("read_journal", {"date": "2026_01_15"}))["content"])
        check("read_journal on a date with no note is not_found",
              body(call("read_journal", {"date": "2026-01-16"}))["status"] == "not_found")
        s = body(call("graph_stats"))
        check("logseq graph_stats counts pages, namespaces and journals",
              s["namespaces"]["Project"]["count"] == 3 and s["unnamespaced_pages"] == 2
              and s["journal_entries"] == 1 and s["format"] == "logseq")
        reg = body(call("namespace_registry"))
        check("namespace_registry exposes the protected flag", reg["namespaces"]["Reference"]["protected"] is True)

        # --- traversal and name validation (logseq) ---------------------------------------
        for bad_name, why in [
            ("../../outside/secret", "parent traversal"), ("/etc/passwd", "absolute path"),
            ("Project/../../outside/secret", "traversal inside a namespace"), ("..\\outside", "backslash"),
            ("Project/.hidden", "hidden segment"), ("Project//Alpha", "empty segment"),
            ("Project/Al\x00pha", "NUL byte"), ("C:/Windows/x", "drive letter"),
            ("Project/Alpha.md", "a filename instead of a name"), ("Project/Leak", "symlink to outside"),
        ]:
            check(f"REFUSED read: {why}", refused(call("read_page", {"page_name": bad_name})))
        for bad_date in ("../../outside/secret", "2026-13-45", "2026/01/15", "20260115"):
            check(f"REFUSED journal date: {bad_date!r}", refused(call("read_journal", {"date": bad_date})))

        # --- Logseq: writes ---------------------------------------------------------------
        r = call("create_page", {"page_name": "Project/Gamma", "content": "status:: new\n", "use_template": True})
        check("logseq create_page writes pages/Project___Gamma.md with the template",
              not errored(r) and "## Timeline" in (lg / "pages" / "Project___Gamma.md").read_text())
        check("create_page refuses a page that already exists",
              errored(call("create_page", {"page_name": "Project/Gamma", "content": "again"})))
        check("create_page refuses an unknown namespace",
              errored(call("create_page", {"page_name": "Nowhere/Page", "content": "x"})))
        for name, why in [("Reference/New", "new page in a protected namespace"),
                          ("reference/New", "lower-case spelling of a protected namespace"),
                          ("Reference__New", "'__' alias of '/'"), ("Reference___New", "'___' alias of '/'")]:
            check(f"REFUSED create: {why}", refused(call("create_page", {"page_name": name, "content": "x"})))
        for name, why in [("Reference/Policy", "update of a protected page"),
                          ("REFERENCE/policy", "upper-case spelling"),
                          ("Reference", "the page named exactly as the protected namespace"),
                          ("Reference___Policy", "the filename spelling")]:
            check(f"REFUSED update: {why}", refused(call("update_page", {"page_name": name, "content": "x"})))
        check("REFUSED append: protected page",
              refused(call("append_to_page", {"page_name": "Reference/Policy", "content": "x"})))
        check("protected page is untouched after all refused writes",
              (lg / "pages" / "Reference___Policy.md").read_text() == "kind:: policy\n\nGround truth.\n")
        check("REFUSED update: a page that is a symlink",
              refused(call("update_page", {"page_name": "Project/Leak", "content": "x"})))
        check("the outside file is untouched", "OUTSIDE-SECRET" in (outside / "secret.md").read_text())
        r = call("update_page", {"page_name": "Project/Beta", "content": "status:: resumed\n"})
        check("logseq update_page replaces content",
              not errored(r) and (lg / "pages" / "Project___Beta.md").read_text() == "status:: resumed\n")
        check("update_page on a missing page is not_found",
              body(call("update_page", {"page_name": "Project/Missing", "content": "x"}))["status"] == "not_found")
        r = call("append_to_page", {"page_name": "Loose-Note", "content": "- appended to a page with no namespace"})
        check("append and update work on an existing page with no namespace (only create needs one)",
              not errored(r) and not errored(call("update_page", {"page_name": "Loose-Note", "content": "rewritten\n"}))
              and (lg / "pages" / "Loose-Note.md").read_text() == "rewritten\n")
        r = call("append_to_page", {"page_name": "Project/Alpha", "content": "- 2026-01-20 follow-up"})
        check("logseq append_to_page appends at the end",
              not errored(r) and (lg / "pages" / "Project___Alpha.md").read_text().endswith("- 2026-01-20 follow-up\n"))
        check("create_page refuses content over the payload cap",
              errored(call("create_page", {"page_name": "Project/Big", "content": "x" * (gb.MAX_CONTENT_CHARS + 1)})))
        check("append_to_page refuses content over the payload cap",
              errored(call("append_to_page", {"page_name": "Project/Alpha", "content": "x" * (gb.MAX_APPEND_CHARS + 1)})))
        check("append_to_page refuses when the page would exceed the size cap",
              refused(call("append_to_page", {"page_name": "Project/Huge", "content": "more"})))
        check("create_page refuses empty content", errored(call("create_page", {"page_name": "Project/E", "content": "  "})))
        check("no temp files are left behind by writes",
              not any(p.name.startswith(".") for p in (lg / "pages").iterdir()))

        # --- Obsidian: reads --------------------------------------------------------------
        CTX["backend"] = load_backend(env={"GRAPH_FORMAT": "obsidian", "OBSIDIAN_VAULT_DIR": str(v),
                                           "GRAPH_DAILY_FOLDER": "Daily"})
        r = body(call("read_page", {"page_name": "Project/Alpha"}))
        props = r["properties"]
        check("obsidian frontmatter: scalar, inline list, block list",
              props.get("status") == "active" and props.get("tags") == ["demo", "sample tag"]
              and props.get("owners") == ["Jane Doe", "Sam Roe"])
        check("obsidian frontmatter: unsupported multi-line scalar and nested map are dropped, not mangled",
              "summary" not in props and "nested" not in props and "a" not in props)
        check("obsidian page names may contain spaces",
              body(call("read_page", {"page_name": "Person/Jane Doe"}))["properties"].get("role") == "engineer")
        r = body(call("search", {"query": "alpha"}))
        found = {x["page_name"] for x in r["results"]}
        check("obsidian search skips .obsidian and .trash", "Project/Alpha" in found
              and not any(".obsidian" in n or ".trash" in n for n in found))
        check("obsidian search does not follow a folder symlink out of the vault",
              body(call("search", {"query": "OUTSIDE-SECRET"}))["count"] == 0)
        r = body(call("query_by_property", {"namespace": "Project", "property_name": "owners", "property_value": "sam"}))
        check("obsidian query_by_property matches any element of a list",
              [x["page_name"] for x in r["results"]] == ["Project/Alpha"])
        r = body(call("query_by_property", {"namespace": "Project", "property_name": "tags", "property_value": "sample"}))
        check("obsidian query_by_property on an inline list", r["count"] == 1)
        r = body(call("find_links", {"page_name": "Person/Jane Doe"}))
        check("obsidian backlinks: bare basename with |alias, and path form with .md",
              r["incoming_links"] == ["Concept/Graph", "Inbox", "Project/Alpha"])
        check("obsidian outgoing link strips #heading and |alias", r["outgoing_links"] == ["Project/Alpha"])
        r = body(call("find_links", {"page_name": "Project/Alpha"}))
        check("obsidian backlinks: [[Alpha#Status]] and [[Project/Alpha#Timeline|...]] both count",
              r["incoming_links"] == ["Concept/Graph", "Person/Jane Doe"])
        r = body(call("find_links", {"page_name": "Concept/Graph"}))
        check("obsidian: a bare link to a shared basename is reported as ambiguous, not counted",
              "Inbox" not in r["incoming_links"] and "Inbox" in r["ambiguous_incoming"])
        r = body(call("read_journal", {"date": "2026-01-15"}))
        check("obsidian read_journal reads <daily folder>/<format>.md", r.get("content") == "Daily note.\n")
        s = body(call("graph_stats"))
        check("obsidian graph_stats excludes hidden folders and counts daily notes",
              s["journal_entries"] == 1 and s["namespaces"]["Project"]["count"] == 1 and s["format"] == "obsidian")

        # --- traversal and name validation (obsidian) -------------------------------------
        for bad_name, why in [
            ("../outside/secret", "parent traversal"), ("/etc/passwd", "absolute path"),
            (".obsidian/hidden", "the .obsidian folder"), (".trash/old", "the .trash folder"),
            ("Project/linked/secret", "folder symlink out of the vault"),
            ("Concept/cfg/hidden", "visible symlink into .obsidian"),
            ("Project/A#B", "'#' in a name"), ("Project/A|B", "'|' in a name"), ("Project/[A]", "brackets"),
        ]:
            check(f"REFUSED obsidian read: {why}", refused(call("read_page", {"page_name": bad_name})))

        # --- Obsidian: writes -------------------------------------------------------------
        r = call("create_page", {"page_name": "Meeting/2026-01-20 Kickoff", "content": "---\nkind: kickoff\n---\nNotes.",
                                 "use_template": True})
        p = v / "Meeting" / "2026-01-20 Kickoff.md"
        check("obsidian create_page writes Folder/Name.md with the template",
              not errored(r) and p.is_file() and "## Decisions" in p.read_text())
        r = call("create_page", {"page_name": "Concept/Deep/Nested Note", "content": "x"})
        check("obsidian create_page makes missing subfolders inside a namespace",
              not errored(r) and (v / "Concept" / "Deep" / "Nested Note.md").is_file())
        check("REFUSED obsidian create: protected namespace",
              refused(call("create_page", {"page_name": "Reference/New", "content": "x"})))
        check("REFUSED obsidian update: protected page reached through a symlinked folder",
              refused(call("update_page", {"page_name": "Concept/refalias/Policy", "content": "x"})))
        check("REFUSED obsidian create: into a folder symlink that leaves the vault",
              refused(call("create_page", {"page_name": "Project/linked/new", "content": "x"})))
        check("nothing was written outside the vault", sorted(x.name for x in outside.iterdir()) == ["secret.md"])
        r = call("append_to_page", {"page_name": "Project/Alpha", "content": "- follow-up"})
        check("obsidian append keeps the frontmatter intact",
              not errored(r) and body(call("read_page", {"page_name": "Project/Alpha"}))["properties"]["status"] == "active")

        # --- Obsidian: folder override for a namespace ------------------------------------
        reg2 = td / "reg2.json"
        reg2.write_text(json.dumps({"namespaces": {
            "Contact": {"protected": True, "obsidian_folder": "People"},
            "Project": {"protected": False}}}), encoding="utf-8")
        (v / "People" / "Ann Lee.md").write_text("---\nrole: lead\n---\n", encoding="utf-8")
        CTX["backend"] = load_backend(env={"GRAPH_FORMAT": "obsidian", "OBSIDIAN_VAULT_DIR": str(v),
                                           "GRAPH_NAMESPACES_FILE": str(reg2)})
        check("obsidian_folder maps Contact/Ann Lee to People/Ann Lee.md",
              body(call("read_page", {"page_name": "Contact/Ann Lee"}))["properties"].get("role") == "lead")
        check("listing reports the namespace name, not the folder name",
              [x["page_name"] for x in body(call("list_namespace", {"namespace": "Contact"}))["pages"]]
              == ["Contact/Ann Lee"])
        check("REFUSED: writing the protected namespace through its folder name",
              refused(call("update_page", {"page_name": "People/Ann Lee", "content": "x"})))
        reg2.write_text(json.dumps({"namespaces": {
            "Person": {"protected": False, "obsidian_folder": "People"}}}), encoding="utf-8")
        try:
            load_backend(env={"GRAPH_FORMAT": "obsidian", "OBSIDIAN_VAULT_DIR": str(v),
                              "GRAPH_NAMESPACES_FILE": str(reg2)})
            check("an obsidian_folder that collides with an existing namespace folder fails closed", False)
        except ConfigError as e:
            check("an obsidian_folder that collides with an existing namespace folder fails closed",
                  "also exists" in str(e))

        # --- no shell -----------------------------------------------------------------------
        src_b = (HERE / "graph_backends.py").read_text(encoding="utf-8")
        src_s = Path(__file__).read_text(encoding="utf-8")
        tool_src = src_s.split("# --- selftests")[0]
        shell_markers = ("subprocess", "os.system", "os.popen", "shell=True", "pty.spawn", "os.exec")
        check("no process spawning in the backends or on any tool path",
              not any(m in src_b for m in shell_markers) and not any(m in tool_src for m in shell_markers))

        # --- stdio transport --------------------------------------------------------------
        CTX["backend"] = load_backend(env={"LOGSEQ_GRAPH_DIR": str(lg)})
        out = io.StringIO()
        serve(io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/list"}\nnot json\n'
                          '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'), out)
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
        check("stdio transport: 2 replies for 3 lines (the notification is silent)", len(lines) == 2)
        check("a malformed line is a parse error and does not kill the loop",
              json.loads(lines[1])["error"]["code"] == -32700)
    finally:
        CTX.update(saved)
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    width = max(len(c[0]) for c in checks)
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}", file=sys.stderr)
    print(f"\n{len(checks) - failed}/{len(checks)} passed", file=sys.stderr)
    return 1 if failed else 0


def selftest_sdk() -> int:
    """Spawn `--sdk` on a temp graph and run a real stdio handshake plus one tool call.

    Needs the pinned SDK installed in the running interpreter. Without it this FAILS rather than
    skipping: a check that ran nothing is not a pass.
    """
    import subprocess  # selftest only; no tool path spawns anything
    import tempfile
    try:
        import mcp  # noqa: F401
    except ImportError:
        print(f"FAIL: the MCP SDK is not installed here. pip install -r {HERE / 'requirements.txt'}", file=sys.stderr)
        return 1
    td = Path(tempfile.mkdtemp())
    (td / "pages").mkdir()
    (td / "pages" / "Project___Alpha.md").write_text("status:: active\nhello\n", encoding="utf-8")
    env = {**os.environ, "LOGSEQ_GRAPH_DIR": str(td), "GRAPH_FORMAT": "logseq"}
    env.pop("GRAPH_MCP_WRITES", None)
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": DEFAULT_PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "selftest", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "read_page", "arguments": {"page_name": "Project/Alpha"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "read_page", "arguments": {"page_name": "../../etc/passwd"}}},
    ]
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--sdk"], env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    replies = {}
    try:
        for m in msgs:
            proc.stdin.write(json.dumps(m) + "\n")
            proc.stdin.flush()
            if "id" in m:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    r = json.loads(line)
                    if r.get("id") == m["id"]:
                        replies[m["id"]] = r
                        break
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    ok = []
    ok.append(("sdk initialize returns serverInfo", replies.get(1, {}).get("result", {}).get("serverInfo", {}).get("name") == SERVER_NAME))
    names = {t["name"] for t in replies.get(2, {}).get("result", {}).get("tools", [])}
    ok.append(("sdk tools/list has the 8 read tools, writes off", names == set(HANDLERS) - WRITE_TOOLS))
    res = replies.get(3, {}).get("result", {})
    ok.append(("sdk tools/call read_page works", not res.get("isError")
               and "hello" in (res.get("content") or [{}])[0].get("text", "")))
    res = replies.get(4, {}).get("result", {})
    ok.append(("sdk traversal is refused as an error result", bool(res.get("isError"))
               and "Refused" in (res.get("content") or [{}])[0].get("text", "")))
    for label, good in ok:
        print(f"  [{'PASS' if good else 'FAIL'}] {label}", file=sys.stderr)
    passed = sum(g for _, g in ok)
    print(f"\n{passed}/{len(ok)} passed", file=sys.stderr)
    return 0 if passed == len(ok) else 1


def main(argv) -> int:
    if "--selftest" in argv:
        return selftest()
    if "--selftest-sdk" in argv:
        return selftest_sdk()
    fmt = None
    if "--format" in argv:
        i = argv.index("--format")
        fmt = argv[i + 1] if i + 1 < len(argv) else ""
    try:
        CTX["backend"] = load_backend(fmt)
    except ConfigError as e:
        print(f"graph MCP server: {e}", file=sys.stderr)
        return 2
    CTX["writes"] = writes_enabled()
    if "--sdk" in argv:
        return serve_sdk()
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
