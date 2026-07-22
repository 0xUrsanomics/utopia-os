#!/usr/bin/env python3
# bus_turn_poll.py — UserPromptSubmit hook: surface new fleet-bus messages at turn start.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Surface NEW fleet-bus messages addressed to the hub at the START of every turn.

The hub agent is the operator-facing session. The bus (fleet_bus.py) is pull-based and the
dispatcher deliberately never send-keys into the operator chat, so without this hook an
inter-agent ping addressed to the hub just sits pending until someone manually says "check
the bus". This is the real-time path: on every operator turn it reads the hub's inbox and
prints anything not seen before, so the operator never has to poll by hand.

Design:
- READ-ONLY poll of fleet_bus (`poll --agent hub` is non-mutating; never claims/completes).
- Seen-cursor (memory/state/bus_seen.json) so each message surfaces EXACTLY ONCE, not
  re-injected every turn until it is completed.
- FAIL-SAFE: every path swallows errors and exits 0. A bus hiccup must never block a turn.
- Quiet when nothing new (no output = no context noise).
- `--seed` marks all current pending as seen without surfacing (clean-slate install).

Wire it as a UserPromptSubmit hook (see settings.example.json).
"""
import os
import sys
import json
import subprocess
from pathlib import Path

# AGENT_ROOT defaults to the repo root (this file is scripts/agents/bus_turn_poll.py).
ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
SEEN = ROOT / "memory" / "state" / "bus_seen.json"
FLEET_BUS = str(Path(__file__).resolve().parent / "fleet_bus.py")
# The hub is the operator-facing agent in the roster (see fleet_bus.py AGENTS).
HUB = os.environ.get("FLEET_HUB_AGENT", "hub")


def _load_seen() -> set:
    try:
        return set(json.loads(SEEN.read_text()).get("seen", []))
    except Exception:
        return set()


def _save_seen(seen: set) -> None:
    try:
        SEEN.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seen": sorted(x for x in seen if x)}
        # Prefer the canonical SSOT store (scripts/memory/ssot.py) so the cursor lands in the
        # unified change log; fall back to a direct write if that module isn't importable.
        try:
            _mem = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
            sys.path.insert(0, _mem)
            import ssot as _SSOT  # noqa: E402
            _SSOT.set_("bus.seen", payload, by="bus-poll", reason="bus seen dedup")
        except Exception:
            SEEN.write_text(json.dumps(payload))
    except Exception:
        pass


def _poll_hub() -> list:
    try:
        out = subprocess.run(["python3", FLEET_BUS, "poll", "--agent", HUB],
                             capture_output=True, text=True, timeout=8)
        data = json.loads(out.stdout or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def main() -> None:
    seed = "--seed" in sys.argv
    msgs = _poll_hub()
    seen = _load_seen()
    new = [m for m in msgs if m.get("id") and m.get("id") not in seen]
    if seed:
        for m in msgs:
            if m.get("id"):
                seen.add(m["id"])
        _save_seen(seen)
        print(f"seeded {len(msgs)} pending-to-{HUB} as seen")
        return
    if not new:
        return
    lines = [f"🔔 Fleet bus: {len(new)} new message(s) addressed to you (the {HUB} agent). "
             f"Act on them, then `python3 scripts/agents/fleet_bus.py complete --id <id>`:"]
    for m in new:
        payload = m.get("payload", "")
        try:
            txt = json.loads(payload).get("text", payload)
        except Exception:
            txt = payload
        lines.append(f"  - [{m.get('id','')[:8]}] {m.get('from_agent','?')} "
                     f"({m.get('msg_type','')}): {str(txt)[:240]}")
    print("\n".join(lines))
    for m in new:
        seen.add(m["id"])
    _save_seen(seen)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
