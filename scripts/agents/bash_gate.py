#!/usr/bin/env python3
# bash_gate.py — PreToolUse Bash danger-pattern gate for the fleet WORKER tenants.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Block the high-damage command patterns a prompt-injected worker would run.

Wire this into the broad-Bash worker tenants' settings as a PreToolUse hook on the Bash tool.
Defense-in-depth for the fleet_bus prompt-injection residual: a broad-Bash worker that gets
prompt-injected could run arbitrary commands. This gate BLOCKS the high-damage command patterns
a successful injection would use (credential exfil, curl-pipe-bash, root/home wipe,
sudo/privileged/system ops) while ALLOWING normal worker bash (reading the graph, writing its own
outbox, python, grep, git, fleet_bus.py, curl-for-research).

HONEST LIMIT: this is NOT a hard guarantee. A determined injection can phrase around any finite
pattern set. It removes the easy, high-value wins (exfil/destroy/RCE), layered under the existing
skill-linter + repo-hook-audit hooks. Documented as such in bus_dispatcher.py THREAT MODEL.

Contract (PreToolUse hook): reads JSON payload from stdin; exit 2 + stderr "BLOCKED: ..." blocks the
call; exit 0 allows. FAIL-OPEN: any error exits 0 (a gate bug must never freeze a worker).
Bypass: env FLEET_BASH_GATE_DISABLE=1 -> always allow.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# AGENT_ROOT defaults to the repo root (this file is scripts/agents/bash_gate.py).
ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
SESSION_LOG = ROOT / "logs" / "session.jsonl"

# (pattern, label) high-signal danger set. Kept deliberately narrow to avoid false-positives that
# would break legitimate worker bash. Each is a substring/regex on the raw command.
DANGER = [
    # credential / secret exfil (workers have no legitimate reason to touch these)
    (re.compile(r"/\.ssh(/|\b)"), "ssh-dir access"),
    (re.compile(r"(^|[\s/=])\.env(\b|\.|/|$)"), ".env access"),
    (re.compile(r"id_rsa|id_ed25519|\.pem\b|private[_-]?key"), "private-key access"),
    (re.compile(r"\.credentials\.json|/\.aws/|/\.gnupg/"), "credential-store access"),
    (re.compile(r"wallet\.(json|dat|key)|mnemonic|seed[_-]?phrase"), "wallet/seed access"),
    # remote code execution (curl/wget piped into a shell)
    (re.compile(r"(curl|wget|fetch)\b[^\n|]*\|[^\n|]*\b(bash|sh|zsh|sudo|python3?|node)\b"),
     "curl-pipe-to-shell"),
    (re.compile(r"\b(bash|sh|zsh)\b[^\n]*<\(\s*(curl|wget)"), "shell-from-remote"),
    # destructive: root / system / home wipe (but ALLOW /tmp, relative, and deep own-tenant rm)
    (re.compile(r"\brm\s+-[rf]{1,2}\s+/(\s|$|\*)"), "rm-rf-root"),
    (re.compile(r"\brm\s+-[rf]{1,2}\s+/(etc|usr|bin|boot|lib|lib64|sys|proc|var|root|dev|sbin|opt)(\s|/|$)"),
     "rm-rf-system-dir"),
    (re.compile(r"\brm\s+-[rf]{1,2}\s+(~|\$HOME|/home)(\s|/|$)"), "rm-rf-home"),
    (re.compile(r"\bmkfs\b|\bdd\s+if=|>\s*/dev/sd|:\(\)\s*\{\s*:\|:&\s*\}"), "disk-destroy/forkbomb"),
    # privilege / system mutation (workers should never do these)
    (re.compile(r"(^|[\s;&|])sudo\s"), "sudo"),
    (re.compile(r"\b(systemctl|service)\s|\bchattr\b|\bcrontab\s+-|\bchown\s+-R\s+/|\bchmod\s+-R?\s*777\s+/"),
     "privileged/system-mutation"),
    # redirect-writes into system config (a broad class of cross-tenant / system tamper)
    (re.compile(r">\s*/etc/|>\s*/(usr|bin|boot|lib|lib64|sbin)/"), "system-config write"),
]


def _emit(decision: str, reason: str, cmd: str) -> None:
    try:
        SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SESSION_LOG.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "category": "fleet-bash-gate", "event": "gate_decision",
                "decision": decision, "reason": reason[:120], "cmd": cmd[:200],
            }) + "\n")
    except Exception:
        pass


def main() -> int:
    if os.environ.get("FLEET_BASH_GATE_DISABLE", "") == "1":
        return 0
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)
    except Exception:
        return 0  # fail-open

    if payload.get("tool_name", "") != "Bash":
        return 0
    cmd = (payload.get("tool_input", {}) or {}).get("command", "") or ""
    if not cmd:
        return 0

    for pat, label in DANGER:
        if pat.search(cmd):
            reason = (f"fleet bash gate: matched high-damage pattern [{label}]. If this is a "
                      f"legitimate op, an operator can re-run with FLEET_BASH_GATE_DISABLE=1.")
            _emit("block", label, cmd)
            print(f"BLOCKED: {reason}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
