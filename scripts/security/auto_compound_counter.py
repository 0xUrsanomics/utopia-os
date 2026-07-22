# auto_compound_counter.py — detects "just do it" AUTO-op cascades and forces a /scope re-check.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Auto-compound action counter. Forces a /scope check-in when AUTO ops chain in same domain.

Privilege-escalation cascades happen because each step inherits prior authorization without
re-verification. This counter detects the cascade shape and forces an explicit /scope restate
when 3+ AUTO operations happen in the same domain without an intervening user message.

Domains tracked:
    install         — npm/bun/pip/cargo/pipx install, mcp add
    settings_edit   — harness settings.json modifications
    scheduler       — schedule_create, schedule_update, schedule_delete
    skill_edit      — writes to skills/ or skills-shared/
    cron_fire       — manual non-interactive invocations / daemon-spawn

State at memory/state/auto_compound_counter.json. Reset on user message (a Stop hook can
clear it). Threshold = 3 in same domain → forces the agent to invoke /scope before the next AUTO op.

Usage:
    python3 auto_compound_counter.py --bump <domain> [<details>]   # +1 in domain
    python3 auto_compound_counter.py --check                        # exit 0 ok / 1 threshold
    python3 auto_compound_counter.py --reset                        # clear all (call on user msg)
    python3 auto_compound_counter.py --status                       # show counters
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
STATE_FILE = ROOT / "memory" / "state" / "auto_compound_counter.json"
THRESHOLD = 3
DOMAINS = ["install", "settings_edit", "scheduler", "skill_edit", "cron_fire"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"reset_at": now_iso(), "counters": {d: [] for d in DOMAINS}}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"reset_at": now_iso(), "counters": {d: [] for d in DOMAINS}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # STATE_FILE is this tool's own source of truth (load_state reads it back).
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    # Additionally record the change to the canonical SSOT store (scripts/memory/ssot.py)
    # so every AUTO-op mutation lands in one unified change log. Best-effort: if the SSOT
    # module isn't importable, the direct write above still keeps the counter correct.
    try:
        _mem = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
        sys.path.insert(0, _mem)
        import ssot as _SSOT
        _SSOT.set_("counter.auto_compound", state, by="auto-compound-counter", reason="counter bump/reset")
    except Exception:
        pass


def cmd_bump(domain: str, details: str = "") -> int:
    if domain not in DOMAINS:
        print(f"unknown domain: {domain}. valid: {DOMAINS}", file=sys.stderr)
        return 64
    state = load_state()
    state.setdefault("counters", {}).setdefault(domain, []).append({
        "at": now_iso(),
        "details": details,
    })
    save_state(state)
    count = len(state["counters"][domain])
    print(json.dumps({"domain": domain, "count": count, "threshold": THRESHOLD, "exceeded": count >= THRESHOLD}))
    return 0


def cmd_check() -> int:
    state = load_state()
    exceeded = []
    for domain, events in state.get("counters", {}).items():
        if len(events) >= THRESHOLD:
            exceeded.append({
                "domain": domain,
                "count": len(events),
                "events": events,
            })
    if exceeded:
        print(json.dumps({"verdict": "threshold_exceeded", "domains": exceeded, "since_reset": state.get("reset_at")}, indent=2))
        return 1
    print(json.dumps({"verdict": "ok", "counters": {d: len(state.get("counters", {}).get(d, [])) for d in DOMAINS}}))
    return 0


def cmd_reset() -> int:
    state = {"reset_at": now_iso(), "counters": {d: [] for d in DOMAINS}}
    save_state(state)
    print("reset")
    return 0


def cmd_status() -> int:
    state = load_state()
    print(f"reset_at: {state.get('reset_at')}")
    print(f"threshold: {THRESHOLD}")
    print(f"{'domain':<15} count")
    print("-" * 30)
    for d in DOMAINS:
        events = state.get("counters", {}).get(d, [])
        marker = " ⚠️" if len(events) >= THRESHOLD else ""
        print(f"  {d:<13} {len(events)}{marker}")
        for e in events[-3:]:
            print(f"    - {e['at']}: {e.get('details', '')}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        return cmd_status()
    cmd = sys.argv[1]
    if cmd == "--bump":
        if len(sys.argv) < 3:
            print("usage: --bump <domain> [<details>]", file=sys.stderr)
            return 64
        details = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
        return cmd_bump(sys.argv[2], details)
    if cmd == "--check":
        return cmd_check()
    if cmd == "--reset":
        return cmd_reset()
    if cmd == "--status":
        return cmd_status()
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
