#!/usr/bin/env python3
# fleet_blocked_probe.py — detect a blocked agent by reading its tmux pane, don't guess.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Detect agent tenants that are WAITING FOR A HUMAN who cannot see them.

WHY THIS EXISTS. Consider a multi-day output outage. Several agents investigate it across
logs, scrapes and cron config and produce competing hypotheses — while the actual cause is
found in one move by opening the tmux pane: an interactive permission request that never
reached the operator. (A separate fleet-wide silence once turned out to be expired
credentials on several tenants.)

THE COMMON SHAPE, and it is why output-derived monitoring cannot see any of it: a process
blocked on INPUT produces nothing while remaining completely healthy. No error, no exit
code, no log line, no failure state. Every artifact the fleet reasons over reports on WORK
PRODUCED. A watchdog restarts on UPTIME, which does not fire either, because the process
is not hung, it is patiently waiting. "Everything looks fine" is literally true.

So this probe reads the one surface that DOES carry the answer: the pane itself.

KEYSTROKE POLICY, and the asymmetry is the whole point:

  UNSENT-COMPOSER    --auto-submit MAY send Alt+Enter. The text is the operator's OWN,
                     already typed, that simply failed to submit. Sending it executes the
                     operator's intent; it does not answer a question. Opt-in only.
  BLOCKED-PERMISSION NEVER auto-answered. There the keystroke IS THE APPROVAL, and these
                     agents also run shell, edit files and add MCP servers, so an auto-yes
                     would approve things the operator never saw. Auto-resolving this would
                     be a security regression wearing a reliability costume.
  BLOCKED-AUTH       Never auto-answered, and pointless anyway: a keystroke does not log
                     anyone in. Needs a human to re-authenticate.

Without --auto-submit the probe sends no keys at all and only reports.

    python3 fleet_blocked_probe.py                # report only, no keys sent
    python3 fleet_blocked_probe.py --json         # machine
    python3 fleet_blocked_probe.py --alert-only   # only states needing a human
    python3 fleet_blocked_probe.py --auto-submit  # + submit stuck composer text
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# Patterns are written against REAL captured pane output, not against imagined prompt text.
# That is deliberate: matchers built from what a document "says" a prompt looks like tend to
# fail on what the tool actually emits.
ACTIVE = re.compile(r"[·✶✻✳*]\s*\w+[.…]{1,3}\s*\(\d+[ms]|esc to interrupt", re.I)
DONE = re.compile(r"^[✻✶·]\s*\w+ for \d+", re.M)

# Composer line. Real form is "❯ " optionally followed by unsent text.
COMPOSER = re.compile(r"^❯\s?(.*)$", re.M)

# VALIDATED against a live instance: a session held "❯ <unsent text>" in its composer.
# The AUTH and PERMISSION patterns below are NOT yet validated against a captured instance.
# They are best-effort and MUST be corrected the first time a real one is seen.
# Recording that honestly so nobody reads a clean run as proof of absence.
AUTH = re.compile(
    r"/login\b|please log ?in|sign ?in to|authentication[_ ]error|invalid api key|"
    r"session (?:has )?expired|credentials? (?:have )?expired|oauth|re-?authenticate|"
    r"token (?:has )?expired|unauthorized", re.I)
PERMISSION = re.compile(
    r"do you want to (?:proceed|allow|continue)|allow this|grant (?:access|permission)|"
    r"\b1\.\s*Yes\b|\by/n\b|\[y/N\]|approve\?|requires? (?:your )?(?:approval|permission)|"
    r"press alt.?enter|waiting for (?:approval|confirmation)", re.I)

# Sessions that are not interactive agents and have no composer. Absent output is normal
# there, so flagging them would train the reader to ignore this probe. Edit to match your
# own non-agent tmux session names (dashboards, gateways, monitors, etc.).
NON_AGENT = {"dashboard", "gateway", "monitor", "cockpit"}


def sessions() -> list[str]:
    r = subprocess.run(["tmux", "ls", "-F", "#{session_name}"],
                       capture_output=True, text=True, timeout=10)
    return [s for s in r.stdout.split() if s]


def pane(name: str, lines: int = 60) -> str:
    r = subprocess.run(["tmux", "capture-pane", "-p", "-S", f"-{lines}", "-t", name],
                       capture_output=True, text=True, timeout=15)
    return r.stdout


def classify(name: str, text: str) -> dict:
    """-> {state, needs_human, detail}. Order matters: most urgent wins."""
    if not text.strip():
        if name in NON_AGENT:
            return {"state": "not-an-agent", "needs_human": False, "detail": "no composer, expected"}
        # ABSENCE, NOT EVIDENCE. "Announcing ignorance on a deadline is what produces the wrong
        # story." An empty pane is consistent with dead, never-started, cleared, or simply quiet,
        # and this probe cannot tell which.
        # The old detail asserted "session may be dead", which is a cause invented from a null.
        return {"state": "UNKNOWN-NO-OUTPUT", "needs_human": True, "verified": False,
                "detail": "pane is empty. this probe CANNOT distinguish dead, never-started, "
                          "cleared, or idle-and-quiet. no cause is claimed"}

    lines = text.splitlines()
    tail = "\n".join(lines[-40:])

    # A prompt in SCROLLBACK is history, not state. Caught on this probe's first run:
    # a session showed "Login expired . Please run /login" then "/login" then
    # "Login successful" and the probe reported BLOCKED-AUTH on an issue already resolved
    # minutes earlier. Reading history as current state is the same defect class the probe
    # exists to catch, committed by the tool built to detect it.
    #
    # Two guards: only the LIVE PROMPT REGION counts (a real prompt sits at the bottom,
    # waiting), and an explicit resolution marker anywhere after the match clears it.
    live = "\n".join(lines[-10:])
    RESOLVED = re.compile(r"login successful|authenticated|logged in|✓|welcome back", re.I)

    def unresolved(pat):
        m = pat.search(live)
        if not m:
            return None
        after = live[m.end():]
        return None if RESOLVED.search(after) else m

    m = unresolved(AUTH)
    if m:
        return {"state": "BLOCKED-AUTH", "needs_human": True, "verified": True,
                "detail": f"credentials/login prompt: {m.group(0)[:60]!r}. agent cannot proceed until re-auth"}
    m = unresolved(PERMISSION)
    if m:
        return {"state": "BLOCKED-PERMISSION", "needs_human": True, "verified": True,
                "detail": f"approval prompt: {m.group(0)[:60]!r}. DO NOT auto-answer, the keystroke is the approval"}

    # Unsent composer: text sitting in the input box that was never submitted.
    # Only meaningful when the agent is NOT actively working, otherwise it is just typing.
    # The CURRENT composer is the LAST "❯" line, empty or not. Taking the last NON-EMPTY
    # match reaches backwards into scrollback and resurrects old submitted commands:
    # a session showed a historical "❯ /login" above an empty live composer and got
    # flagged as unsent. Second false positive from the same root as the first, reading
    # history as state, so the fix is positional both times.
    matches = list(COMPOSER.finditer(text))
    unsent = matches[-1].group(1).strip() if matches else ""
    if unsent and not ACTIVE.search(tail):
        return {"state": "UNSENT-COMPOSER", "needs_human": True, "verified": True, "text": unsent,
                "detail": f"text sits unsubmitted in the composer: {unsent[:70]!r}. "
                          f"agent is idle and will never act on it"}

    if ACTIVE.search(tail):
        return {"state": "working", "needs_human": False, "detail": "actively processing"}
    if DONE.search(tail):
        return {"state": "idle", "needs_human": False, "detail": "finished, composer empty"}
    return {"state": "idle", "needs_human": False, "detail": "no activity marker, composer empty"}


import datetime
import os
import pathlib

# AGENT_ROOT defaults to the repo root (this file is scripts/agents/fleet_blocked_probe.py).
ROOT = pathlib.Path(os.environ.get("AGENT_ROOT", str(pathlib.Path(__file__).resolve().parents[2])))
AUTOLOG = ROOT / "logs/fleet-autosubmit.jsonl"
# Optional .env fallback for the alert credentials (see _send_tg). Point AGENT_ENV_FILE at it.
ENV_FILE = pathlib.Path(os.environ.get("AGENT_ENV_FILE", str(ROOT / ".env")))


def auto_submit(name: str, expected: str) -> dict:
    """Send Alt+Enter to a session stuck with UNSENT text. UNSENT-COMPOSER ONLY.

    Opt-in, and for THIS STATE ONLY. The reasoning: the meaningful approval happens
    upstream, the operator confirms before anything reaches this point, so submitting
    already-typed text executes the operator's intent rather than approving a new decision.

    NEVER extended to BLOCKED-PERMISSION: there the keystroke IS the approval, and these
    agents also run shell, edit files and add MCPs, so an auto-yes there approves things the
    operator never saw. Pointless for BLOCKED-AUTH: a keystroke does not log anyone in.

    Re-verifies state immediately before sending, because the agent may have started
    working in the seconds since the scan and submitting into a live session would inject
    a stray keystroke mid-work.
    """
    fresh = classify(name, pane(name))
    if fresh["state"] != "UNSENT-COMPOSER":
        return {"session": name, "submitted": False,
                "reason": f"state changed to {fresh['state']} before send, skipped"}
    if expected and fresh.get("text") != expected:
        return {"session": name, "submitted": False,
                "reason": "composer text changed between scan and send, skipped"}
    try:
        # M-Enter (Alt+Enter) is what actually submits in these panes.
        subprocess.run(["tmux", "send-keys", "-t", name, "M-Enter"],
                       capture_output=True, timeout=10, check=True)
    except Exception as e:
        return {"session": name, "submitted": False, "reason": f"send failed: {str(e)[:60]}"}
    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "session": name, "submitted": True, "text": expected[:120]}
    try:
        AUTOLOG.parent.mkdir(parents=True, exist_ok=True)
        with AUTOLOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    return rec



def _send_tg(alerts: list) -> None:
    """Deliver the alert to the operator's personal chat. VERIFIED vs UNKNOWN kept separate in the
    message, so an inference never reads as a confirmation. Silent no-op (logged) if creds are absent,
    since a crash here would itself be a silent monitoring failure."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (tok and chat):
        # Fall back to a local .env file (AGENT_ENV_FILE). A cron shell task may not inherit these
        # as env vars, and when the exit code is decoupled from findings this alert is the ONLY
        # notification path for a real block, so delivery must NOT depend on env inheritance.
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text().splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN=") and not tok:
                    tok = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID=") and not chat:
                    chat = line.split("=", 1)[1].strip()
    if not (tok and chat):
        print("--tg: TELEGRAM_BOT_TOKEN/CHAT_ID not in env or .env, alert NOT delivered", file=sys.stderr)
        return
    confirmed = [a for a in alerts if a.get("verified")]
    unknown = [a for a in alerts if not a.get("verified")]
    lines = ["\U0001F6A8 fleet blocked-probe"]
    if confirmed:
        lines.append(f"\n{len(confirmed)} VERIFIED, needs a human:")
        for a in confirmed:
            lines.append(f"  {a['session']}: {a['state']}")
    if unknown:
        lines.append(f"\n{len(unknown)} UNKNOWN (empty pane, cause not established):")
        for a in unknown:
            lines.append(f"  {a['session']}")
    lines.append("\n(auto-submit NOT run by this cron. a permission prompt needs your keystroke.)")
    body = "\n".join(lines)
    try:
        import urllib.request, urllib.parse
        data = urllib.parse.urlencode({"chat_id": chat, "text": body}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:
        print(f"--tg: send failed: {str(e)[:80]}", file=sys.stderr)


SEEN_FILE = ROOT / "memory/state/blocked_probe_seen.json"


def _sig(row: dict) -> str:
    """Signature of what a session is blocked ON. Changes when the session makes progress; stays
    identical when it is genuinely stuck at the same prompt/composer text."""
    import hashlib
    basis = f"{row.get('state','')}|{row.get('text') or row.get('detail','')}"
    return hashlib.md5(basis.encode("utf-8", "replace")).hexdigest()[:16]


def _staleness_gate(alerts: list) -> list:
    """Only surface blocks that PERSIST across >=2 probe cycles (~30 min). A session that is actively
    working (esp. the orchestrator) changes its composer every cycle, so its signature differs
    run-to-run and it never alerts. A real stuck prompt is frozen, same signature, and alerts on the
    second consecutive sighting. Fixes the false positive where the orchestrator session flagged its
    own UNSENT-COMPOSER while mid-work. Maintains state in SEEN_FILE; call only on the cron (--tg)
    path so manual runs don't perturb the cadence."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        seen = json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else {}
    except Exception:
        seen = {}
    persistent, new_seen = [], {}
    for r in alerts:
        s = r["session"]
        sig = _sig(r)
        prev = seen.get(s)
        if prev and prev.get("sig") == sig:
            r["_since"] = prev.get("since", now)   # unchanged since a prior cycle => real, persistent
            persistent.append(r)
            new_seen[s] = prev
        else:
            new_seen[s] = {"sig": sig, "since": now}   # new/changed => transient, record but don't alert
    # sessions no longer flagged simply drop out of new_seen (auto-cleared)
    try:
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SEEN_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(new_seen, indent=2))
        tmp.replace(SEEN_FILE)
    except Exception:
        pass                # a read-only FS degrades to "alert every cycle", never crashes the probe
    return persistent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--alert-only", action="store_true")
    ap.add_argument("--tg", action="store_true",
                    help="send alerts to the operator's personal chat. fires ONLY when an agent needs "
                         "a human, never on a clean run. a detector whose alert stays in a cron log is "
                         "the silent failure it exists to catch.")
    ap.add_argument("--auto-submit", action="store_true",
                    help="submit stuck composer text. UNSENT-COMPOSER only, never a permission prompt")
    args = ap.parse_args()

    try:
        names = sessions()
    except Exception as e:
        print(f"tmux unavailable: {e}", file=sys.stderr)
        return 2

    rows = []
    for n in names:
        try:
            rows.append({"session": n, **classify(n, pane(n))})
        except Exception as e:
            rows.append({"session": n, "state": "probe-error", "needs_human": True, "verified": False,
                         "detail": str(e)[:80]})

    submitted = []
    if args.auto_submit:
        for r in rows:
            if r["state"] == "UNSENT-COMPOSER":
                res = auto_submit(r["session"], r.get("text", ""))
                submitted.append(res)
                if res.get("submitted"):
                    r["state"] = "auto-submitted"
                    r["needs_human"] = False
                    r["detail"] = f"stuck text submitted: {res['text']!r}"
                else:
                    r["detail"] += f" | auto-submit skipped: {res['reason']}"

    alerts = [r for r in rows if r["needs_human"]]
    # Staleness gate on the cron (--tg) path: only TG a block that has PERSISTED across >=2 probe
    # cycles. A working session (esp. the orchestrator) changes its composer each cycle and never
    # reaches TG; a real stuck prompt is frozen and alerts on the 2nd sighting. stdout still shows all.
    if args.tg:
        persistent = _staleness_gate(alerts)
        if persistent:
            _send_tg(persistent)
    if args.json:
        print(json.dumps({"rows": rows, "alerts": len(alerts)}, indent=2))
        return 0  # findings are in the JSON "alerts" field, not the exit code (see note below)

    show = alerts if args.alert_only else rows
    for r in show:
        mark = "!!" if r["needs_human"] else "  "
        print(f"{mark} {r['session']:<18} {r['state']:<20} {r['detail']}")
    if alerts:
        # Report the two classes SEPARATELY. Collapsing them is how an unknown becomes a claim.
        confirmed = [r for r in alerts if r.get("verified")]
        unknown = [r for r in alerts if not r.get("verified")]
        if confirmed:
            print(f"\n{len(confirmed)} VERIFIED_BLOCKED: probe matched a live prompt or unsent text. "
                  f"Nothing was auto-resolved by design: for a permission prompt the unblocking "
                  f"keystroke IS the approval.")
        if unknown:
            print(f"\n{len(unknown)} UNKNOWN_NO_OUTPUT: produced nothing and the probe cannot say "
                  f"why. This is an absence, NOT a diagnosis. Open the pane before concluding "
                  f"anything about it.")
    elif not args.alert_only:
        print("\nno agent is blocked on a human.")
    # Exit code reflects whether the PROBE RAN, not what it found. Findings are delivered via the
    # --tg alert + stdout, not the exit code. Returning 1-on-findings (fixed 2026-07-22) collided
    # with the daemon's shell-task semantics (rc!=0 => "Task failed"), so a SUCCESSFUL detection of
    # a blocked agent got misreported as the probe failing. Real probe errors still return 2 (tmux
    # unavailable). No consumer branches on exit 1 (verified: grep found none).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
