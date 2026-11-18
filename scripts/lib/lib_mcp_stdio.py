#!/usr/bin/env python3
# lib_mcp_stdio.py: minimal stdio MCP client so a cron pre-step can call a tool without a model turn.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Minimal stdio MCP client for cron pre-steps.

Why: a cron that runs as a model session often spends most of its tokens calling MCP tools and
then re-reading the raw results on every later turn. A script can make the same calls, trim the
results, and hand the model one compact packet. This module launches an MCP server exactly as the
cron config launches it and calls tools over JSON-RPC.

READ-ONLY BY DEFAULT: call() refuses any tool not on the read allowlist, and call_write() refuses
any tool not on the write allowlist. Both lists start EMPTY, so nothing runs until the operator
names each tool. Adding a tool to either list is a gate change and goes to the operator.

Allowlist file (JSON), default $AGENT_ROOT/memory/state/mcp-stdio-allowlist.json:
    {"read":  {"memory": ["memory_search", "memory_list"]},
     "write": {"memory": ["memory_store"]}}
Tool names are as the SERVER exposes them (Claude Code prefixes them with mcp__<server>__).

Server definitions are read from the first file that defines the server under "mcpServers":
$AGENT_MCP_CONFIG (if set), then $AGENT_ROOT/.mcp.json, then ~/.claude.json.

    from lib_mcp_stdio import MCPServer
    with MCPServer("memory") as s:
        text = s.call("memory_search", {"query": "release checklist"})

Env (optional): AGENT_ROOT, AGENT_MCP_CONFIG, AGENT_MCP_ALLOWLIST (path to the allowlist file).
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import time
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
ALLOWLIST = Path(os.environ.get("AGENT_MCP_ALLOWLIST", str(ROOT / "memory" / "state" / "mcp-stdio-allowlist.json")))
CONFIG_SOURCES = [Path(p) for p in (os.environ.get("AGENT_MCP_CONFIG"),) if p] + [
    ROOT / ".mcp.json", Path.home() / ".claude.json"]


class MCPError(RuntimeError):
    pass


def _allowlist(kind: str) -> dict[str, set[str]]:
    """kind = "read" | "write". A missing or unreadable file means an empty list (fail closed)."""
    try:
        data = json.loads(ALLOWLIST.read_text()).get(kind) or {}
        return {srv: set(tools or []) for srv, tools in data.items()}
    except Exception:
        return {}


def _server_def(name: str) -> dict:
    cfg = None
    for src in CONFIG_SOURCES:
        try:
            cfg = json.loads(src.read_text()).get("mcpServers", {}).get(name)
        except Exception:
            cfg = None
        if cfg:
            break
    if not cfg or not cfg.get("command"):
        raise MCPError(f"no stdio definition for MCP server '{name}'")
    return {"command": cfg["command"], "args": cfg.get("args") or [], "env": dict(cfg.get("env") or {})}


class MCPServer:
    def __init__(self, name: str, timeout: float = 60.0):
        self.name = name
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self._id = 0
        self._buf = b""

    def __enter__(self):
        d = _server_def(self.name)
        env = os.environ.copy()
        env.update(d["env"])
        self.proc = subprocess.Popen([d["command"], *d["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, env=env, cwd=str(ROOT))
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "cron-prestep", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *a):
        if self.proc:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()

    def _send(self, obj):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        self.proc.stdin.flush()

    def _readline(self, deadline):
        while b"\n" not in self._buf:
            left = deadline - time.time()
            if left <= 0:
                raise MCPError(f"{self.name}: timeout after {self.timeout}s")
            r, _, _ = select.select([self.proc.stdout], [], [], left)
            if not r:
                continue
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            if not chunk:
                raise MCPError(f"{self.name}: server closed stdout")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line

    def _rpc(self, method, params):
        self._id += 1
        my = self._id
        self._send({"jsonrpc": "2.0", "id": my, "method": method, "params": params})
        deadline = time.time() + self.timeout
        while True:
            line = self._readline(deadline).strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # a server that logs to stdout; skip
            if msg.get("id") == my:
                if "error" in msg:
                    raise MCPError(f"{self.name}.{method}: {msg['error']}")
                return msg.get("result")

    def _call(self, tool: str, args: dict) -> str:
        res = self._rpc("tools/call", {"name": tool, "arguments": args}) or {}
        text = "\n".join(c.get("text", "") for c in res.get("content") or [] if c.get("type") == "text")
        if res.get("isError"):
            raise MCPError(f"{self.name}.{tool}: {text[:300]}")
        return text

    def call(self, tool: str, args: dict) -> str:
        if tool not in _allowlist("read").get(self.name, set()):
            raise MCPError(f"refused: {self.name}.{tool} is not on the read-only allowlist")
        return self._call(tool, args)

    def call_write(self, tool: str, args: dict) -> str:
        if tool not in _allowlist("write").get(self.name, set()):
            raise MCPError(f"refused: {self.name}.{tool} is not on the write allowlist")
        return self._call(tool, args)

    def list_tools(self) -> list[str]:
        return [t["name"] for t in (self._rpc("tools/list", {}) or {}).get("tools", [])]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: lib_mcp_stdio.py <server-name>   (lists the server's tools)", file=sys.stderr)
        sys.exit(64)
    with MCPServer(sys.argv[1]) as s:
        print("\n".join(s.list_tools()))
