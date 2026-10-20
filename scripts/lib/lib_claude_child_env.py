#!/usr/bin/env python3
# lib_claude_child_env.py: build a child env that carries the durable Claude setup credential.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Shared helper: build a child env carrying the long-lived `claude setup-token` credential.

Every headless `claude --print` / `claude -p` subprocess should authenticate off the long-lived
setup credential in ~/.claude/oauth-token.env, NOT the mutable interactive OAuth block in
~/.claude/.credentials.json. That block expires, and same-account logins clobber it (refresh
race). A VALID credential in the env wins over a dead credentials block.

This is the Python sibling of scripts/lib/lib_claude_setup_auth.sh. It exists so callers stop
hand-rolling the same load block (a scheduler re-fire, the critic dispatcher and a daemon each had
an inline copy before this). Import + use:

    from lib_claude_child_env import child_env
    subprocess.run([claude, "--print", ...], env=child_env(), ...)

FAIL-OPEN: if the credential file is absent, empty or unreadable, returns os.environ unchanged so
the caller still launches on whatever credentials exist. A missing credential must never take a
caller down.

Resolution order mirrors lib_claude_setup_auth.sh (per-agent override, then shared):
    ~/.claude/oauth-token.<agent>.env   (agent arg or CLAUDE_TOKEN_AGENT, optional)
    ~/.claude/oauth-token.env           (fleet-shared)

Never prints the credential value. Handles both `export VAR=...` (the install_setup_auth.sh %q
format) and bare `VAR=...` lines.

Self-test: python3 lib_claude_child_env.py --selftest   (uses a temp HOME, touches nothing real)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_LINE = re.compile(r"\s*(?:export\s+)?CLAUDE_CODE_OAUTH_TOKEN=(.*)")


def child_env(agent: str | None = None) -> dict:
    """Return os.environ augmented with CLAUDE_CODE_OAUTH_TOKEN. Fail-open."""
    env = os.environ.copy()
    base = Path.home() / ".claude"
    agent = agent or os.environ.get("CLAUDE_TOKEN_AGENT") or ""
    candidates = []
    if agent:
        candidates.append(base / f"oauth-token.{agent}.env")
    candidates.append(base / "oauth-token.env")
    for f in candidates:
        try:
            if not f.is_file():
                continue
            for line in f.read_text().splitlines():
                m = _LINE.match(line)
                if m:
                    val = m.group(1).strip().strip("'\"")
                    if val:
                        env["CLAUDE_CODE_OAUTH_TOKEN"] = val
                        return env
        except Exception:
            continue
    return env


def _selftest() -> int:
    import tempfile
    old_home = os.environ.get("HOME")
    old_val = os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    bad = 0
    try:
        with tempfile.TemporaryDirectory() as td:
            os.environ["HOME"] = td
            bad += "CLAUDE_CODE_OAUTH_TOKEN" in child_env()  # no file: fail-open, nothing added
            cdir = Path(td) / ".claude"
            cdir.mkdir()
            (cdir / "oauth-token.env").write_text("export CLAUDE_CODE_OAUTH_TOKEN='shared-fake-value'\n")
            bad += child_env().get("CLAUDE_CODE_OAUTH_TOKEN") != "shared-fake-value"
            (cdir / "oauth-token.worker.env").write_text("CLAUDE_CODE_OAUTH_TOKEN=agent-fake-value\n")
            bad += child_env("worker").get("CLAUDE_CODE_OAUTH_TOKEN") != "agent-fake-value"
            bad += child_env("other").get("CLAUDE_CODE_OAUTH_TOKEN") != "shared-fake-value"
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
        if old_val is not None:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = old_val
    print("selftest: PASS" if not bad else f"selftest: {bad} FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
