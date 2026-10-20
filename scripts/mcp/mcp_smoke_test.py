#!/usr/bin/env python3
# mcp_smoke_test.py: real JSON-RPC handshake + tools/list per configured MCP server.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""mcp_smoke_test.py - verified read-only call per MCP server.

Deeper than a PID-liveness check: this actually spawns
each configured stdio MCP server, runs the JSON-RPC handshake (initialize ->
notifications/initialized -> tools/list), and confirms it returns a real tool list.
Answers "does this MCP actually work" not just "is a process alive".

Source of truth: ~/.claude.json mcpServers (global), plus with --project the entry for this
repo in its "projects" map and the repo's own .mcp.json. Override the config path with
MCP_CONFIG_FILE and the project path with AGENT_ROOT.
- stdio servers: full handshake, reports tool count.
- http servers: reachability probe only (deep MCP-over-HTTP handshake not attempted).
- telegram (and any KNOWN_SINGLE_CONSUMER): spawn-SKIPPED, a second getUpdates consumer
  would 409 the live daemon poller. Reported config-present, not spawned. Add names with
  MCP_SMOKE_SKIP=name1,name2.

Read-only: initialize + tools/list only, never calls a tool. Ephemeral: each server
is spawned then killed. Run on-demand, not on a cron.

Exit 0 = all probed servers healthy. Exit 1 = one or more failed. Usage: [--json] [--project]
"""
import sys
import os
import json
import subprocess
import select
import time
import urllib.request

KNOWN_SINGLE_CONSUMER = {"telegram"} | {s.strip() for s in os.environ.get("MCP_SMOKE_SKIP", "").split(",") if s.strip()}
ROOT = os.path.realpath(os.environ.get("AGENT_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HANDSHAKE_TIMEOUT = 12.0               # seconds per server


def load_servers(include_project):
    p = os.path.expanduser(os.environ.get("MCP_CONFIG_FILE", "~/.claude.json"))
    try:
        d = json.load(open(p))
    except (OSError, ValueError):
        d = {}
    servers = dict(d.get("mcpServers", {}))
    if include_project:
        for proj, pcfg in (d.get("projects", {}) or {}).items():
            if os.path.realpath(proj) == ROOT:
                for name, cfg in (pcfg.get("mcpServers", {}) or {}).items():
                    servers.setdefault(name, cfg)
        try:
            local = json.load(open(os.path.join(ROOT, ".mcp.json")))
            for name, cfg in (local.get("mcpServers", {}) or {}).items():
                servers.setdefault(name, cfg)
        except (OSError, ValueError):
            pass
    return servers


def _read_json_line(proc, want_id, deadline):
    """Read newline-delimited JSON from proc.stdout until a message with id==want_id
    arrives or the deadline passes. Returns the parsed message or None."""
    buf = ""
    while time.time() < deadline:
        r, _, _ = select.select([proc.stdout], [], [], max(0.0, deadline - time.time()))
        if not r:
            break
        chunk = os.read(proc.stdout.fileno(), 65536)
        if not chunk:
            break
        buf += chunk.decode("utf-8", "replace")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == want_id:
                return msg
    return None


def probe_stdio(name, cfg):
    cmd = [cfg["command"]] + list(cfg.get("args", []))
    env = dict(os.environ)
    env.update(cfg.get("env", {}) or {})
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env)
    except Exception as e:
        return {"server": name, "transport": "stdio", "ok": False,
                "detail": "spawn failed: %s" % e}
    deadline = time.time() + HANDSHAKE_TIMEOUT
    try:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "mcp-smoke-test", "version": "1.0"}}}
        proc.stdin.write((json.dumps(init) + "\n").encode()); proc.stdin.flush()
        ir = _read_json_line(proc, 1, deadline)
        if ir is None or "result" not in ir:
            return {"server": name, "transport": "stdio", "ok": False,
                    "detail": "no/invalid initialize response"}
        srv = (ir["result"].get("serverInfo") or {}).get("name", "?")
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n").encode())
        proc.stdin.flush()
        tr = _read_json_line(proc, 2, deadline)
        if tr is None or "result" not in tr:
            return {"server": name, "transport": "stdio", "ok": False,
                    "detail": "initialized but tools/list failed", "serverInfo": srv}
        tools = tr["result"].get("tools", [])
        return {"server": name, "transport": "stdio", "ok": True,
                "detail": "%d tools" % len(tools), "serverInfo": srv}
    except Exception as e:
        return {"server": name, "transport": "stdio", "ok": False, "detail": "error: %s" % e}
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def probe_http(name, cfg):
    url = cfg.get("url") or cfg.get("httpUrl") or ""
    if not url:
        return {"server": name, "transport": "http", "ok": False, "detail": "no url in config"}
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return {"server": name, "transport": "http", "ok": True,
                    "detail": "reachable (HTTP %s), handshake not deep-probed" % resp.status}
    except Exception as e:
        # a 4xx/405 still proves the host answers; only a connection error is a real fail
        code = getattr(e, "code", None)
        if code:
            return {"server": name, "transport": "http", "ok": True,
                    "detail": "host answers (HTTP %s), handshake not deep-probed" % code}
        return {"server": name, "transport": "http", "ok": False, "detail": "unreachable: %s" % e}


def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return 0
    include_project = "--project" in sys.argv
    servers = load_servers(include_project)
    results = []
    for name, cfg in sorted(servers.items()):
        if name in KNOWN_SINGLE_CONSUMER:
            results.append({"server": name, "transport": cfg.get("type", "stdio"),
                            "ok": None, "detail": "spawn-skipped (single-consumer, would 409 live poller); config present"})
            continue
        if cfg.get("type") == "http":
            results.append(probe_http(name, cfg))
        else:
            results.append(probe_stdio(name, cfg))

    failed = [r for r in results if r["ok"] is False]
    rc = 1 if failed else 0

    if "--json" in sys.argv:
        print(json.dumps({"results": results, "failed": len(failed)}))
        return rc

    for r in results:
        mark = "OK  " if r["ok"] else ("SKIP" if r["ok"] is None else "FAIL")
        print("%s %-16s [%s] %s" % (mark, r["server"], r.get("transport", "?"), r["detail"]))
    print("---")
    print("%d probed, %d failed, %d skipped" %
          (sum(1 for r in results if r["ok"] is not None), len(failed),
           sum(1 for r in results if r["ok"] is None)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
