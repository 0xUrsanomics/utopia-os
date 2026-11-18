#!/usr/bin/env python3
# lib_claude_call.py: one headless Claude call for a cron script, with its cost logged.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""One headless Claude call for a cron script, with its cost logged.

Pattern from scripts/pipeline/breaking_lane.py: `claude --print --model <m> --no-session-persistence`,
the durable OAuth token via lib_claude_child_env, a NEUTRAL cwd (so the project CLAUDE.md, the
auto-memory index and the project .mcp.json are not loaded: a few thousand tokens of base context
instead of tens of thousands), and --strict-mcp-config with no MCP config (no MCP tools at all).

Tools: default none (--tools ""). Pass tools=["WebSearch", "WebFetch"] for a research call; those
are read-only web tools. The child never gets Bash, file writes, MCP or chat tools, so text it reads
from the web can at worst produce bad text, which the calling script validates.

Cost: --output-format json returns token usage and the CLI's own total cost. Each call appends one
line to $AGENT_LOG_DIR/cron-costs.jsonl (source "direct") with `cli_cost_usd`, the CLI's list-price
figure, plus per-model token counts, so direct calls can be added up next to transcript sessions.

    from lib_claude_call import claude_call
    r = claude_call(prompt, cron="my-cron", model="sonnet", effort="medium",
                    tools=["WebSearch", "WebFetch"], timeout=900)
    r["ok"], r["text"], r["cli_cost_usd"]

Env (optional):
  AGENT_ROOT      repo root (default: two levels up from this file)
  AGENT_LOG_DIR   logs dir (default: $AGENT_ROOT/logs)
  AGENT_DATA_DIR  runtime data dir; the neutral cwd is $AGENT_DATA_DIR/claude-call-cwd
                  (default: $AGENT_ROOT/.data)
  CLAUDE_BIN      claude CLI path (default: `claude` on PATH)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
COST_LOG = Path(os.environ.get("AGENT_LOG_DIR", str(ROOT / "logs"))) / "cron-costs.jsonl"
NEUTRAL_CWD = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data"))) / "claude-call-cwd"

sys.path.insert(0, str(Path(__file__).resolve().parent))


def claude_call(prompt: str, *, cron: str, model: str = "sonnet", effort: str = "medium",
                tools: list[str] | None = None, timeout: int = 600, log: Path | None = COST_LOG,
                label: str = "", max_budget_usd: float | None = None) -> dict:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = {"ok": False, "text": "", "error": "", "cli_cost_usd": 0.0}
    claude = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not claude:
        out["error"] = "claude CLI not found (set CLAUDE_BIN or put claude on PATH)"
        return out
    env = None
    try:
        from lib_claude_child_env import child_env
        env = child_env()
    except Exception:
        pass
    cwd = NEUTRAL_CWD
    try:
        cwd.mkdir(parents=True, exist_ok=True)
    except Exception:
        cwd = Path(tempfile.gettempdir())
    cmd = [claude, "--print", "--model", model, "--effort", effort, "--strict-mcp-config",
           "--no-session-persistence", "--output-format", "json", "--tools", ",".join(tools or [])]
    if tools:
        cmd += ["--allowedTools", ",".join(tools)]
    if max_budget_usd:
        cmd += ["--max-budget-usd", f"{max_budget_usd:.2f}"]  # CLI list-cost basis; a hard stop per call
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
                           cwd=str(cwd), env=env)
        try:
            d = json.loads(r.stdout)
        except json.JSONDecodeError:
            out["error"] = f"exit {r.returncode}, non-JSON output: {(r.stderr or r.stdout)[-300:]}"
            d = {}
        if d:
            out["text"] = d.get("result") or ""
            out["ok"] = not d.get("is_error") and r.returncode == 0
            if not out["ok"]:
                out["error"] = f"exit {r.returncode}, subtype {d.get('subtype')}: {out['text'][:200]}"
            row = {"cron": cron, "label": label, "session_id": None, "run_started": started,
                   "run_ended": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "models": {}, "turns": d.get("num_turns"), "input_tokens": 0, "output_tokens": 0,
                   "cache_read_tokens": 0, "cache_write_tokens": 0,
                   "cli_cost_usd": round(float(d.get("total_cost_usd") or 0), 5),
                   "attributed_by": "caller", "source": "direct"}
            for mdl, u in (d.get("modelUsage") or {}).items():
                uu = {"input_tokens": u.get("inputTokens", 0), "output_tokens": u.get("outputTokens", 0),
                      "cache_read_tokens": u.get("cacheReadInputTokens", 0),
                      "cache_write_tokens": u.get("cacheCreationInputTokens", 0)}
                row["models"][mdl] = uu
                for k, v in uu.items():
                    row[k] += v
            out["cli_cost_usd"] = row["cli_cost_usd"]
            out["usage"] = {k: row[k] for k in ("input_tokens", "output_tokens", "cache_read_tokens",
                                                "cache_write_tokens")}
            if log:
                try:
                    log.parent.mkdir(parents=True, exist_ok=True)
                    with open(log, "a") as fh:
                        fh.write(json.dumps(row) + "\n")
                except Exception:
                    pass
    except subprocess.TimeoutExpired:
        out["error"] = f"timeout after {timeout}s"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="smoke test: one tiny call, cost logged to --log")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--log", type=Path, required=True)
    a = ap.parse_args()
    r = claude_call("Reply with the single word OK.", cron="smoke-test", model=a.model, effort="low", log=a.log)
    print(json.dumps({k: r[k] for k in ("ok", "text", "error", "cli_cost_usd")}))
