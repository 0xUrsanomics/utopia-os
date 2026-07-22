#!/usr/bin/env python3
# critic_dispatch_hook.py — Stop-hook that dispatches a tool-grounded Critic on high-stake output.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Critic dispatch hook.

Wired into the harness settings.json Stop hook AFTER the stake-emit hook. Reads the
just-emitted stake_classified event from logs/session.jsonl. If stake:high,
dispatches a Critic subagent via `claude --print` with the prompt template from
skills/critic.md. Parses the verdict, appends a critic_verdict event to session.jsonl.

The Critic runs at turn end, not per-tool-use. PostToolUse would fire on every tool
invocation (dozens per turn) which is too granular. Stop is right.

Failure mode: any error -> exit 0, log to errors.jsonl. The hook MUST NOT block the session.

Cooldown: only 1 Critic dispatch per turn (last stake_classified event). Avoids
duplicate dispatch on retry/resume scenarios.

Architecture: ASYNC-ADVISORY. The Stop hook spawns a DETACHED worker and returns in
~1s, so NOTHING blocks the session. The worker runs the tool-grounded critic to
completion (no functional timeout, no retry -> those killed a 60-120s critic hundreds
of times and doubled a deterministic loss). Its verdict is advisory:
  - written to session.jsonl (audit, all verdicts)
  - actionable verdicts (BLOCK / SHIP_WITH_FIXES) -> a per-session state file that
    the next UserPromptSubmit turn surfaces in-context
  - BLOCK only -> an optional operator ping
The verdict lands AFTER the stake:high reply already went out; it is a heads-up /
next-turn correction signal, not a real-time gate.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# AGENT_ROOT defaults to the repo root (this file is scripts/eval/critic_dispatch_hook.py).
REPO_ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

SESSION_LOG = REPO_ROOT / "logs" / "session.jsonl"
ERRORS_LOG = REPO_ROOT / "logs" / "errors.jsonl"
# Phantom-flag ledger. Per a ceiling-accept policy: critic max_turns / timeout /
# parse-failure stays visible across runs instead of being silently absorbed into
# OPERATOR_REVIEW. Self-audit + nightly-system-audit read this ledger to surface
# the failure rate.
CRITIC_PHANTOM_FLAGS = REPO_ROOT / "memory" / "Infra" / "critic-phantom-flags.jsonl"

# Anti-zombie BACKSTOP for the DETACHED worker's claude --print (NOT a latency gate).
# The worker is off the Stop critical path, so a functional timeout is self-sabotage.
# A prior 80s hard timeout + 1 retry killed a genuinely-60-120s tool-grounded critic
# hundreds of times, and the retry doubled a deterministic loss. Both deleted. This
# value now only kills a truly-wedged child (e.g. a network hang): ~3x real critic
# runtime, aligned with WORKER_LOCK_STALE_S so a killed worker's single-flight slot
# frees cleanly.
CRITIC_BACKSTOP_SECONDS = 300

# Tool restriction passed to claude --print
CRITIC_ALLOWED_TOOLS = (
    "Read,Grep,Glob,Bash,WebFetch,"
    "mcp__exa__*,"
    "mcp__plugin_context7_context7__*,"
    "mcp__memory__memory_search,"
    "mcp__memory__memory_list,"
    "mcp__logseq__logseq_read_page,"
    "mcp__logseq__logseq_search,"
    "mcp__logseq__logseq_query_by_property"
)


def _log_error(msg: str, detail: str = "") -> None:
    """Best-effort error logging. Never raises."""
    try:
        ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ERRORS_LOG.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "category": "critic-dispatch-hook",
                "event": "hook_failure",
                "msg": msg,
                "detail": detail[:500],
            }) + "\n")
    except Exception:
        pass


def _emit_phantom_flag(failure_class: str, **fields) -> None:
    """Append a phantom-flag entry to the ledger.

    Critic ceiling-accept policy: each critic dispatch failure (max_turns / timeout /
    envelope parse / exit nonzero / CLI missing / unhandled) writes one JSONL line
    here. Self-audit + nightly system audit read this file to surface the failure rate
    without requiring further architectural fixes. Ledger is append-only JSONL; rotate
    via a separate task when it gets large.

    failure_class: one of max_turns | timeout | envelope_parse | exit_nonzero
                   | claude_cli_missing | unhandled
    """
    try:
        CRITIC_PHANTOM_FLAGS.parent.mkdir(parents=True, exist_ok=True)
        with CRITIC_PHANTOM_FLAGS.open("a") as f:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "failure_class": failure_class,
                **fields,
            }
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass




def _log_debug(stage: str, **extra) -> None:
    """Best-effort debug telemetry. Opt-in via AGENT_CRITIC_DEBUG=1 env var.
    Off by default to prevent session.jsonl flooding (~180 entries/day at stop-hook rate)."""
    if os.environ.get("AGENT_CRITIC_DEBUG", "") != "1":
        return
    try:
        SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SESSION_LOG.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "category": "critic-dispatch-debug",
                "event": "checkpoint",
                "stage": stage,
                **extra,
            }) + "\n")
    except Exception:
        pass


def _detect_invocation_context() -> str:
    """Walk the parent process chain to label how this stop hook was invoked.

    Returns one of: 'cron' (cron-spawned claude --print), 'print' (manual claude
    --print), 'interactive' (normal claude session), or 'unknown' (lookup failed).

    Used to distinguish stop-hook verdicts that fired in a cron --print run (a real
    drift signal) from those that fired in interactive sessions overlapping cron
    windows by coincidence. The daemon name to look for is configurable via
    AGENT_DAEMON_NAME (default "agent-daemon").
    """
    daemon_name = os.environ.get("AGENT_DAEMON_NAME", "agent-daemon")
    try:
        pid = os.getppid()
        chain_cmds: list[str] = []
        for _ in range(20):
            if pid in (0, 1):
                break
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
                chain_cmds.append(cmd)
                with open(f"/proc/{pid}/stat") as f:
                    pid = int(f.read().split()[3])
            except Exception:
                break
        joined = " | ".join(chain_cmds).lower()
        has_print = ("claude" in joined) and ("--print" in joined)
        has_daemon = (daemon_name in joined) or ("scheduler" in joined)
        if has_print and has_daemon:
            return "cron"
        if has_print:
            return "print"
        return "interactive"
    except Exception:
        return "unknown"


def _emit_critic_verdict_event(verdict: dict, draft_text: str) -> None:
    """Append critic_verdict event to session.jsonl."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "category": "critic",
        "event": "critic_verdict",
        "source": "stop-hook",
        "context": _detect_invocation_context(),
        "verdict": verdict.get("verdict", "OPERATOR_REVIEW"),
        "reason": verdict.get("reason", "")[:500],
        "confidence": verdict.get("confidence", 0.0),
        "tool_calls_made": verdict.get("tool_calls_made", 0),
        "fixes_count": len(verdict.get("fixes", [])),
        "ungrounded_claims_count": len(verdict.get("ungrounded_claims", [])),
        "draft_chars": len(draft_text),
    }
    try:
        SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SESSION_LOG.open("a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        _log_error("verdict emit failed", str(e))


def _read_last_classifier_event() -> dict | None:
    """Read the most recent stake_classified event from session.jsonl."""
    if not SESSION_LOG.exists():
        return None
    try:
        with SESSION_LOG.open() as f:
            lines = f.readlines()
        # Walk backwards to find the most recent stake_classified
        for line in reversed(lines[-100:]):  # last 100 events max
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "stake_classified":
                return event
            # If we hit a critic_verdict before a stake_classified, that means
            # this turn's Critic already fired (cooldown).
            if event.get("event") == "critic_verdict":
                return None
        return None
    except Exception as e:
        _log_error("read classifier event failed", str(e))
        return None


def _extract_last_assistant_text(transcript_path: Path) -> str:
    """Read the .jsonl session transcript and return the last assistant message text."""
    if not transcript_path.exists():
        return ""
    last_text = ""
    try:
        with transcript_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, str):
                    last_text = content
                elif isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                    if parts:
                        last_text = "\n".join(parts)
    except Exception as e:
        _log_error("transcript read failed", str(e))
        return ""
    return last_text


def _build_critic_prompt(draft: str, classifier_event: dict) -> str:
    """Construct the Critic subagent prompt.

    HARDCODED -- kept in sync manually with the `## Subagent prompt template`
    section in skills/critic.md. When editing this, also edit that .md (or
    vice versa). Drift between the two = silent regression of Critic behavior.
    """
    stake = classifier_event.get("stake", "unknown")
    matched_rules = ", ".join(classifier_event.get("matched_rules", []))
    doc_type = classifier_event.get("doc_type", "unknown")

    # Trim draft if extremely long (Critic budget ~3K tokens, draft alone shouldn't dominate)
    draft_excerpt = draft if len(draft) <= 4000 else draft[:4000] + "\n[...truncated for Critic budget]"

    return f"""You are the Critic. Verify the draft below against tool-fetched evidence.
Self-reflection without a tool call FAILS this gate. Be tight: target 3-5 tool calls, ceiling 8.

Draft:
---
{draft_excerpt}
---

Stake context (from classifier):
- stake: {stake}
- matched_rules: {matched_rules}
- doc_type: {doc_type}

Run 2 grounding checks. Use the FASTEST tool that can verify (priority order:
memory_search > logseq_search > Read > Grep > Glob > Exa > WebFetch). Prefer one
targeted call over many; Glob+single-Read beats multi-Grep.

1. Top-3 source check: identify the 3 STRONGEST load-bearing claims (highest stakes
   / most specific / most cited). For each, fetch a source via the fastest tool that
   can verify it. Flag any of the 3 that cannot be grounded. Do NOT source every claim
   in the draft -- sampling the top 3 is the contract.

2. Blind-spot probe: run ONE tool query against what the draft most likely missed
   (search-truncation OR strongest counter-thesis, whichever fits the doc_type).
   If you find substantive evidence the draft ignores, flag it.

Return ONLY a JSON verdict in this shape (no surrounding markdown, no preamble):

{{"verdict": "SHIP" | "SHIP_WITH_FIXES" | "BLOCK", "fixes": [{{"issue": "...", "fix": "...", "auto_applicable": true | false}}], "reason": "1-3 sentence summary", "confidence": 0.0-1.0, "tool_calls_made": <int>, "ungrounded_claims": []}}

Hard rules:
- BLOCK requires a specific BLOCKER-class issue (factual error, contradicts sourced
  evidence, top-3 claim cannot be grounded).
- SHIP_WITH_FIXES is for in-place fixable issues (citation add, wording refine).
- SHIP requires >=1 tool call backing the strongest claim. SHIP with zero tool calls
  is forbidden.
- Zero tool calls -> BLOCK with reason "self-reflection only, no tool grounding".
- Graceful degradation: if you hit the 8-turn ceiling with checks incomplete, return
  SHIP_WITH_FIXES + fixes=[{{"issue":"incomplete grounding","fix":"re-run with narrower scope","auto_applicable":false}}]
  rather than burning more turns.
"""


# claude binary: env override, then PATH lookup, then bare name.
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"

# --- Async decouple ---
# The Stop-hook critic used to block up to 160s (80s x 1 retry) waiting on a
# `claude --print` child. Under interactive-session contention that child's
# boot+work routinely blew the budget: 52% of dispatches returned OPERATOR_REVIEW
# from timeout (zero diagnostic value, pure latency). Fix: spawn the dispatch
# DETACHED so the hook returns in ~1s. The critic still runs and emits its verdict,
# just off the critical path. A single-flight lock stops detached critics from
# piling up (concurrent claude children would re-create the contention).
RUN_DIR = Path(os.environ.get("AGENT_RUN_DIR", str(Path.home() / ".agent-daemon" / "run")))
WORKER_LOCK = RUN_DIR / "critic-worker.lock"
WORKER_LOCK_STALE_S = 300

# --- Async-advisory surfacing ---
# Actionable verdicts (BLOCK / SHIP_WITH_FIXES) drop a per-session state file that
# the next UserPromptSubmit turn surfaces in-context, then deletes. SHIP /
# OPERATOR_REVIEW are audit-only (session.jsonl), never surfaced.
VERDICT_DIR = Path(os.environ.get("AGENT_VERDICT_DIR", str(Path.home() / ".agent-daemon" / "state" / "critic_verdicts")))
# BLOCK-only operator ping. Relay bot (separate from the polling bot to avoid
# contention), matches the established cron-notify pattern used elsewhere.
RELAY_BOT_TOKEN = os.environ.get("AGENT_RELAY_BOT_TOKEN", "")
RELAY_CHAT_ID = os.environ.get("AGENT_RELAY_CHAT_ID", "")


def _safe_unlink(p: Path) -> None:
    try:
        p.unlink(missing_ok=True)
    except Exception:
        pass


def _worker_lock_held() -> bool:
    """True if a critic worker is already running (fresh lock + live PID)."""
    try:
        if not WORKER_LOCK.exists():
            return False
        if (time.time() - WORKER_LOCK.stat().st_mtime) > WORKER_LOCK_STALE_S:
            return False  # stale lock, treat as free
        pid = int((WORKER_LOCK.read_text().strip() or "0"))
        if pid <= 0:
            return False
        os.kill(pid, 0)  # raises ProcessLookupError if dead
        return True
    except (ProcessLookupError, ValueError, OSError):
        return False


def _spawn_detached_worker(prompt: str, draft_text: str, classifier_event: dict,
                           session_id: str = "") -> bool:
    """Write the critic job to a tmpfile and spawn a detached worker process.

    start_new_session=True detaches the child into its own session so it survives
    THIS Stop-hook process exiting. Returns True if the worker was spawned.
    """
    import tempfile
    try:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        fd, job_path = tempfile.mkstemp(prefix="critic-job-", suffix=".json", dir=str(RUN_DIR))
        with os.fdopen(fd, "w") as f:
            json.dump({"prompt": prompt, "draft_text": draft_text,
                       "classifier_event": classifier_event,
                       "session_id": session_id}, f)
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--worker", job_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception as e:
        _log_error("worker spawn failed", str(e))
        return False


def _write_verdict_statefile(verdict: dict, session_id: str, draft_text: str) -> None:
    """Persist an ACTIONABLE verdict (BLOCK / SHIP_WITH_FIXES) to a per-session state
    file for next-turn in-context surfacing. SHIP / OPERATOR_REVIEW are audit-only
    (session.jsonl) and never surfaced. Best-effort, never raises."""
    v = verdict.get("verdict", "")
    if v not in ("BLOCK", "SHIP_WITH_FIXES"):
        return
    try:
        VERDICT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        sid = (session_id or "unknown").replace("/", "_")
        path = VERDICT_DIR / f"{sid}-{stamp}.json"
        path.write_text(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "verdict": v,
            "reason": verdict.get("reason", "")[:400],
            "fixes": verdict.get("fixes", [])[:5],
            "confidence": verdict.get("confidence", 0.0),
            "draft_excerpt": (draft_text or "").strip().replace("\n", " ")[:200],
        }) + "\n")
    except Exception as e:
        _log_error("verdict statefile write failed", str(e))


def _send_block_ping(verdict: dict, draft_text: str) -> None:
    """Operator ping on BLOCK ONLY. No ping for any other verdict. Relay bot,
    best-effort, never raises. Kept em-dash-free for a send guard."""
    if verdict.get("verdict") != "BLOCK":
        return
    if not RELAY_BOT_TOKEN or not RELAY_CHAT_ID:
        _log_error("relay ping skipped", "AGENT_RELAY_BOT_TOKEN/AGENT_RELAY_CHAT_ID not set")
        return
    reason = verdict.get("reason", "")[:300]
    excerpt = (draft_text or "").strip().replace("\n", " ")[:120]
    text = ("Critic BLOCK (off-path, on your prior stake:high reply)\n"
            f"reason: {reason}\n"
            f"draft: {excerpt}")
    try:
        data = json.dumps({"chat_id": RELAY_CHAT_ID, "text": text}).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{RELAY_BOT_TOKEN}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            _ = resp.status
    except Exception as e:
        _log_error("block ping failed", str(e))


def _run_worker(job_path: str) -> int:
    """Detached worker: load job, dispatch the critic OFF the Stop-hook critical
    path, emit the verdict. Owns the single-flight lock for its lifetime."""
    try:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        WORKER_LOCK.write_text(str(os.getpid()))
    except Exception:
        pass
    try:
        with open(job_path) as f:
            job = json.load(f)
        verdict = _dispatch_critic_via_claude_print(job.get("prompt", ""))
        draft_text = job.get("draft_text", "")
        session_id = job.get("session_id", "")
        _emit_critic_verdict_event(verdict, draft_text)        # audit (all verdicts)
        _write_verdict_statefile(verdict, session_id, draft_text)  # surface next turn
        _send_block_ping(verdict, draft_text)                  # operator ping on BLOCK only
    except Exception as e:
        _log_error("worker run failed", str(e))
    finally:
        _safe_unlink(Path(job_path))
        _safe_unlink(WORKER_LOCK)
    return 0


def _dispatch_critic_via_claude_print(prompt: str) -> dict:
    """Spawn `claude --print` with the Critic prompt + restricted tools, inside the
    DETACHED worker.

    The worker is already off the Stop-hook critical path (detach), so NOTHING waits
    on this call. A prior 80s hard timeout + 1 retry killed a genuinely-60-120s
    tool-grounded critic hundreds of times and doubled a deterministic loss; BOTH are
    deleted. subprocess.run keeps only CRITIC_BACKSTOP_SECONDS as an anti-zombie
    backstop (a network-wedged claude child), not a latency gate.
    """
    cmd = [
        CLAUDE_BIN,
        "--print",
        "--output-format", "json",
        "--allowed-tools", CRITIC_ALLOWED_TOOLS,
        "--max-turns", "8",
        "--permission-mode", "default",
        prompt,
    ]
    # Recursion guard. Pass AGENT_CRITIC_DISABLE=1 in child env so the child's own
    # critic_dispatch_hook short-circuits. Prevents the infinite chain that burned
    # extra-usage + RAM overnight once (Critic output mentioning regulators/partners/
    # money re-classified stake=high -> recursion).
    child_env = {**os.environ, "AGENT_CRITIC_DISABLE": "1"}
    try:
        start = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CRITIC_BACKSTOP_SECONDS,
            env=child_env,
        )
        elapsed = time.time() - start
        if result.returncode != 0:
            # rc=1 with partial stdout often = max-turns exhausted. stdout may hold
            # partial JSON or an error message.
            stdout_snip = result.stdout[:150] if result.stdout else ""
            _log_error(
                "claude --print exit nonzero",
                f"rc={result.returncode} stderr={result.stderr[:150]} stdout={stdout_snip} elapsed={elapsed:.1f}s",
            )
            failure_cls = "max_turns" if (result.returncode == 1 and stdout_snip) else "exit_nonzero"
            _emit_phantom_flag(
                failure_cls,
                rc=result.returncode,
                elapsed_s=round(elapsed, 2),
                stdout_snip=stdout_snip[:100],
            )
            return {
                "verdict": "OPERATOR_REVIEW",
                "reason": f"claude --print exit {result.returncode}",
                "confidence": 0.0,
                "tool_calls_made": 0,
                "fixes": [],
                "ungrounded_claims": [],
            }
        # claude --print --output-format json wraps the subagent stdout in a result
        # envelope; extract the inner verdict.
        try:
            envelope = json.loads(result.stdout)
            inner_text = envelope.get("result", "") if isinstance(envelope, dict) else ""
            verdict = _parse_verdict_from_text(inner_text)
            verdict["_dispatch_elapsed_s"] = round(elapsed, 2)
            return verdict
        except json.JSONDecodeError as e:
            _log_error("envelope parse failed", str(e) + " stdout=" + result.stdout[:300])
            _emit_phantom_flag(
                "envelope_parse",
                elapsed_s=round(elapsed, 2),
                stdout_snip=result.stdout[:100],
            )
            return {
                "verdict": "OPERATOR_REVIEW",
                "reason": "envelope parse failed",
                "confidence": 0.0,
                "tool_calls_made": 0,
                "fixes": [],
                "ungrounded_claims": [],
            }
    except subprocess.TimeoutExpired:
        # NOT a latency failure. Only fires on a truly-wedged child past ~3x real
        # runtime. No retry by design (retry doubled a deterministic loss).
        _log_error(
            "Critic dispatch backstop kill",
            f"backstop={CRITIC_BACKSTOP_SECONDS}s (wedged child, no retry by design)",
        )
        _emit_phantom_flag("backstop_kill", backstop_s=CRITIC_BACKSTOP_SECONDS)
        return {
            "verdict": "OPERATOR_REVIEW",
            "reason": f"Critic backstop kill (>{CRITIC_BACKSTOP_SECONDS}s, wedged)",
            "confidence": 0.0,
            "tool_calls_made": 0,
            "fixes": [],
            "ungrounded_claims": [],
        }
    except FileNotFoundError:
        _log_error("claude CLI not on PATH", "")
        _emit_phantom_flag("claude_cli_missing")
        return {
            "verdict": "OPERATOR_REVIEW",
            "reason": "claude CLI not found",
            "confidence": 0.0,
            "tool_calls_made": 0,
            "fixes": [],
            "ungrounded_claims": [],
        }
    except Exception as e:
        _log_error("Critic dispatch unhandled", str(e))
        _emit_phantom_flag(
            "unhandled",
            exc_type=type(e).__name__,
            exc_msg=str(e)[:100],
        )
        return {
            "verdict": "OPERATOR_REVIEW",
            "reason": f"dispatch error: {type(e).__name__}",
            "confidence": 0.0,
            "tool_calls_made": 0,
            "fixes": [],
            "ungrounded_claims": [],
        }


def _parse_verdict_from_text(text: str) -> dict:
    """Extract the JSON verdict from subagent output. Best-effort parse."""
    # Strip code fences if present
    text = text.strip()
    if text.startswith("```"):
        # Remove leading ```json or ``` line
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3].strip()
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    # Failed parse -> OPERATOR_REVIEW
    return {
        "verdict": "OPERATOR_REVIEW",
        "reason": "verdict JSON parse failed",
        "confidence": 0.0,
        "tool_calls_made": 0,
        "fixes": [],
        "ungrounded_claims": [],
    }


def main() -> int:
    try:
        _log_debug("entry")
        # Race-condition guard. Stop hooks aren't strictly sequential: the stake-emit
        # hook can still be writing session.jsonl when critic_dispatch starts. A short
        # sleep lets stake_emit complete + flush before we read.
        time.sleep(0.6)
        payload_raw = sys.stdin.read()
        if not payload_raw.strip():
            _log_debug("exit", reason="empty_payload")
            return 0
        payload = json.loads(payload_raw)
    except Exception as e:
        _log_error("payload parse failed", str(e))
        return 0

    transcript_path_str = payload.get("transcript_path", "")
    session_id = payload.get("session_id", "")
    if not transcript_path_str:
        _log_debug("exit", reason="no_transcript_path")
        return 0

    # Cooldown check: read last classifier event AND check if Critic already fired
    classifier_event = _read_last_classifier_event()
    if classifier_event is None:
        _log_debug("exit", reason="no_classifier_or_cooldown")
        return 0

    if classifier_event.get("stake") != "high":
        _log_debug("exit", reason="not_high", stake=classifier_event.get("stake"))
        return 0

    transcript_path = Path(transcript_path_str)
    text = _extract_last_assistant_text(transcript_path)
    if not text or len(text.strip()) < 50:
        _log_debug("exit", reason="text_too_short", text_len=len(text or ""))
        return 0

    # Cooldown env-var override: skip dispatch if AGENT_CRITIC_DISABLE=1 in environment
    if os.environ.get("AGENT_CRITIC_DISABLE", "") == "1":
        _log_debug("exit", reason="disabled_env")
        return 0

    # Single-flight: if a critic worker is already running, skip this dispatch.
    # Avoids stacking concurrent `claude --print` children (the contention that
    # caused the timeouts). Dispatches are >180s apart in practice, so genuine
    # skips are rare; a skipped turn just gets no verdict (acceptable, the verdict
    # is a passive ledger entry in interactive mode, not a real-time gate).
    if _worker_lock_held():
        _log_debug("exit", reason="worker_already_running")
        return 0

    _log_debug("dispatching", text_chars=len(text), stake=classifier_event.get("stake"), rules=classifier_event.get("matched_rules", []))
    prompt = _build_critic_prompt(text, classifier_event)
    # ASYNC DECOUPLE: spawn detached so this hook returns immediately. The critic
    # runs + emits its verdict off the critical path. See header note.
    spawned = _spawn_detached_worker(prompt, text, classifier_event, session_id)
    _log_debug("worker_spawned", spawned=spawned)
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        sys.exit(_run_worker(sys.argv[2]))
    sys.exit(main())
