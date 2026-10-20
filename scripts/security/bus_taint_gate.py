#!/usr/bin/env python3
# bus_taint_gate.py: PreToolUse hook that watches for actions derived from untrusted fleet-bus data.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""bus_taint_gate.py: PreToolUse hook that WATCHES for actions derived from untrusted fleet-bus data.

CaMeL-style taint tracking across a multi-agent fleet (bus v2, see scripts/agents/fleet_bus.py).
WARN-ONLY: it never blocks. It logs, so a week of data can show the false-block rate before any rule
is turned into a block (suggested target: under 2% of tool calls per tenant).

Taint state: fleet_bus.py writes <taint dir>/<agent>.json on claim / CLI poll / delivered result
(trust level, bus ids, sha256-hashed tokens of 12+ chars, never payload text). Entries expire after
6h and are cleared on complete/fail. Missing file = untainted.

Rules (name -> when it is logged):
  tmux_other_pane   ALWAYS: tmux send-keys/paste-buffer aimed at a session other than our own
  outbound_send     tainted: chat sends to anyone but the operator DM, mail drafts, social posts,
                    sheet/graph writes,
                    gh writes, curl POST/PUT/-d/-F, git push
  tainted_token     tainted: a tool argument contains a token copied from a recent bus payload
  protected_write   tainted: writes to CLAUDE.md, SOUL.md, MEMORY*, settings*.json, skills/
  bus_publish       tainted: fleet_bus publish (allowed; publish() already forces trust down)

Contract (Claude Code PreToolUse): JSON on stdin, ALWAYS exit 0, prints nothing. FAIL-OPEN: any error
exits 0 and is noted in logs/errors.jsonl. Bypass: FLEET_BUS_TAINT_GATE_DISABLE=1.
Log lines carry ids, tool name, rules, taint level and a short hash. Never payload text or secrets.

Usage:
  bus_taint_gate.py --agent runner [--own-session runner]  # as the hook (reads stdin)
  bus_taint_gate.py --report [--days 7]                     # summary of the last N days

Env: AGENT_ROOT (logs under $AGENT_ROOT/logs), AGENT_DATA_DIR, FLEET_BUS_DB, FLEET_BUS_TAINT_DIR,
OPERATOR_CHAT_ID (the one chat a tainted agent may still reply to), FLEET_BUS_AGENT,
FLEET_HUB_AGENT / FLEET_HUB_SESSION (the hub's own tmux session name),
BUS_TAINT_GATE_LOG / _COUNTS / _ERRLOG (override log paths, used by the tests).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
LOG = Path(os.environ.get("BUS_TAINT_GATE_LOG") or ROOT / "logs/bus_taint_gate.jsonl")
COUNTS = Path(os.environ.get("BUS_TAINT_GATE_COUNTS") or ROOT / "logs/bus_taint_gate_counts.json")
ERRLOG = Path(os.environ.get("BUS_TAINT_GATE_ERRLOG") or ROOT / "logs/errors.jsonl")
LIVE_DB = DATA_DIR / "fleet_bus.db"
TAINT_TTL_HRS = 6  # keep in step with fleet_bus.TAINT_TTL_HRS
OPERATOR_DM = os.environ.get("OPERATOR_CHAT_ID", "")  # unset = every chat reply counts as outbound
TRUST_LEVELS = {"external": 0, "fleet": 1, "operator": 2}

# ---- token hashing (shared with fleet_bus.taint_add, which imports this function) ----
_TOKEN = re.compile(r"[A-Za-z0-9_./:@~%+=?&#-]{12,}")
_HEXISH = re.compile(r"^[0-9a-f]{8,64}$")  # bus ids and hashes: they appear in every bus command


def taint_tokens(text: str) -> list:
    """sha256[:16] of each 12+ char URL/path/address/handle-like token. Hashes only, so the taint
    file and the gate never hold the token text itself."""
    out, seen = [], set()
    for m in _TOKEN.finditer(str(text or "")):
        t = m.group(0).strip(".,;:)'\"]}")
        if len(t) < 12 or _HEXISH.match(t.lower()) or "fleet_bus" in t or t.startswith("BUS-DATA"):
            continue
        h = hashlib.sha256(t.encode()).hexdigest()[:16]
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _taint_dir() -> Path:
    if os.environ.get("FLEET_BUS_TAINT_DIR"):
        return Path(os.environ["FLEET_BUS_TAINT_DIR"])
    return Path(os.environ.get("FLEET_BUS_DB") or LIVE_DB).parent / "bus_taint"


def _taint(agent: str):
    """(level or None, ids, token-hash set) from the agent's live taint entries."""
    try:
        d = json.loads((_taint_dir() / f"{agent}.json").read_text())
        ents = d.get("entries", {}) if isinstance(d, dict) else {}
    except Exception:
        return None, [], set()
    cut = (datetime.now(timezone.utc) - timedelta(hours=TAINT_TTL_HRS)).isoformat()
    lvls, ids, toks = [], [], set()
    for mid, e in ents.items():
        if not isinstance(e, dict) or str(e.get("ts", "")) < cut or e.get("trust") == "operator":
            continue
        lvls.append(e.get("trust") if e.get("trust") in TRUST_LEVELS else "external")
        ids.append(mid)
        toks.update(x for x in e.get("tok", []) if isinstance(x, str))
    if not lvls:
        return None, [], set()
    return min(lvls, key=TRUST_LEVELS.get), ids, toks


# ---- rule matchers ----
_TMUX = re.compile(r"\btmux\b[^\n;|&]*\b(send-keys|send|paste-buffer|pasteb)\b([^\n;|&]*)")
_TMUX_T = re.compile(r"-t\s*['\"]?([^\s'\"]+)")
_CURL_W = re.compile(r"\bcurl\b[^\n|;]*(\s-d\b|\s-d['\"\S]|--data|\s-F\b|--form|--upload-file|\s-T\s|"
                     r"-X\s*['\"]?(POST|PUT|PATCH|DELETE))")
_GH_W = re.compile(r"\bgh\s+(pr|issue|release|repo|gist|label)\s+(create|comment|edit|merge|close|delete|"
                   r"review|reopen|upload)\b|\bgh\s+api\b[^\n;|]*(-X\s*(POST|PUT|PATCH|DELETE)|\s-[fF]\s)")
_GIT_PUSH = re.compile(r"\bgit\s+push\b")
_PROT_NAME = re.compile(r"(^|/)(CLAUDE\.md|SOUL\.md|MEMORY[\w.-]*|settings[\w.-]*\.json)$")
_PROT_BASH = re.compile(r"(>>?|\btee\b|\bsed\s+-i|\bcp\b|\bmv\b|\bln\b|\btruncate\b)[^\n;|&]*"
                        r"(CLAUDE\.md|SOUL\.md|MEMORY[\w.-]*\.md|settings[\w.-]*\.json|/skills/)")
_BUS_PUB = re.compile(r"(fleet_bus\.py|\bbin/bus)\b[^\n;|&]*\bpublish\b")
_SEND_TOOLS = re.compile(r"(gmail_(send|createDraft)|drive_shareFile|calendar_(create|update)Event|"
                         r"sheets_(append_row|update_cells)|logseq_(create|update|append)|"
                         r"(twitter|instagram)\w*__\w*(post|tweet|reply|send|publish|create|upload|quote)|"
                         r"docs_(create|writeText|replaceText))", re.I)
_TG_TOOLS = re.compile(r"telegram\w*__(reply|edit_message|react|telegram_send_message|telegram_send_file)")


def _tmux_other(cmd: str, own: str) -> bool:
    for m in _TMUX.finditer(cmd):
        t = _TMUX_T.search(m.group(2) or "")
        if t and re.split(r"[:.]", t.group(1))[0] not in (own, ""):
            return True
    return False


def _outbound(tool: str, ti: dict, cmd: str) -> bool:
    if tool == "Bash":
        return bool(_CURL_W.search(cmd) or _GH_W.search(cmd) or _GIT_PUSH.search(cmd))
    if _TG_TOOLS.search(tool):
        if "telegram_send" in tool:
            return str(ti.get("destination", "personal")) != "personal"
        return not OPERATOR_DM or str(ti.get("chat_id", "")) != OPERATOR_DM
    return bool(_SEND_TOOLS.search(tool))


def _protected(tool: str, ti: dict, cmd: str) -> bool:
    if tool == "Bash":
        return bool(_PROT_BASH.search(cmd))
    fp = str(ti.get("file_path") or ti.get("notebook_path") or "")
    return bool(fp) and tool in ("Write", "Edit", "MultiEdit", "NotebookEdit") and (
        bool(_PROT_NAME.search(fp)) or "/skills/" in fp)


def _strings(v) -> list:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def evaluate(payload: dict, agent: str, own: str) -> dict | None:
    """The log record for this tool call, or None when no rule fires. Pure apart from reading the
    taint file, so tests can call it directly."""
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {}
    cmd = str(ti.get("command") or "") if tool == "Bash" else ""
    level, ids, toks = _taint(agent)
    rules = []
    if tool == "Bash" and _tmux_other(cmd, own):
        rules.append("tmux_other_pane")
    hits = 0
    if level is not None:
        if _outbound(tool, ti, cmd):
            rules.append("outbound_send")
        if toks and not (tool == "Bash" and _BUS_PUB.search(cmd)):
            hits = len(set(taint_tokens(" ".join(_strings(ti)))) & toks)
            if hits:
                rules.append("tainted_token")
        if _protected(tool, ti, cmd):
            rules.append("protected_write")
        if tool == "Bash" and _BUS_PUB.search(cmd):
            rules.append("bus_publish")
    if not rules:
        return None
    blob = json.dumps(ti, sort_keys=True, default=str)
    return {"ts": datetime.now(timezone.utc).isoformat(), "agent": agent,
            "session": str(payload.get("session_id") or "")[:12], "tool": tool[:80], "rules": rules,
            "taint": level, "bus_ids": ids[:10], "tok_hits": hits,
            "h": hashlib.sha256(blob.encode()).hexdigest()[:12]}


def _append(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _count(agent: str) -> None:
    """Per-day, per-agent tool-call count: the denominator for the false-block rate."""
    import fcntl
    COUNTS.parent.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).date().isoformat()
    with COUNTS.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        try:
            d = json.loads(f.read() or "{}")
        except Exception:
            d = {}
        d.setdefault(day, {})[agent] = d.get(day, {}).get(agent, 0) + 1
        for k in sorted(d)[:-30]:  # keep 30 days
            d.pop(k, None)
        f.seek(0); f.truncate(); f.write(json.dumps(d))


def report(days: int) -> dict:
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    by_rule, by_agent, by_tool, by_day, flagged = {}, {}, {}, {}, 0
    try:
        lines = LOG.read_text().splitlines()
    except Exception:
        lines = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if str(r.get("ts", "")) < cut:
            continue
        flagged += 1
        a = r.get("agent", "?")
        by_agent[a] = by_agent.get(a, 0) + 1
        by_tool[r.get("tool", "?")] = by_tool.get(r.get("tool", "?"), 0) + 1
        by_day[r["ts"][:10]] = by_day.get(r["ts"][:10], 0) + 1
        for ru in r.get("rules", []):
            by_rule[ru] = by_rule.get(ru, 0) + 1
    try:
        counts = json.loads(COUNTS.read_text())
    except Exception:
        counts = {}
    calls = {}
    for day, per in counts.items():
        if day >= cut[:10]:
            for a, n in per.items():
                calls[a] = calls.get(a, 0) + n
    rate = {a: round(100.0 * by_agent.get(a, 0) / n, 2) for a, n in calls.items() if n}
    return {"days": days, "flagged_calls": flagged, "by_rule": by_rule, "by_agent": by_agent,
            "by_tool": dict(sorted(by_tool.items(), key=lambda kv: -kv[1])[:15]), "by_day": by_day,
            "tool_calls_seen": calls, "flag_rate_pct": rate,
            "note": "warn-only; flag_rate_pct is the would-block rate the go/no-go for blocking reads"}


def _arg(name: str, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main() -> int:
    if "--report" in sys.argv:
        try:
            print(json.dumps(report(int(_arg("--days", "7"))), indent=1))
        except Exception as e:
            print(json.dumps({"error": type(e).__name__}))
        return 0
    if os.environ.get("FLEET_BUS_TAINT_GATE_DISABLE", "") == "1":
        return 0
    hub = os.environ.get("FLEET_HUB_AGENT", "hub")
    agent = _arg("--agent") or os.environ.get("FLEET_BUS_AGENT") or hub
    own = _arg("--own-session") or (os.environ.get("FLEET_HUB_SESSION", hub) if agent == hub
                                    else f"fleet-{agent}")
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
        _count(agent)
        rec = evaluate(payload, agent, own)
        if rec:
            _append(LOG, rec)
    except Exception as e:
        try:
            _append(ERRLOG, {"ts": datetime.now(timezone.utc).isoformat(), "category": "bus_taint_gate",
                             "event": "gate_error", "detail": type(e).__name__,
                             "line": getattr(e.__traceback__, "tb_lineno", None)})
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
