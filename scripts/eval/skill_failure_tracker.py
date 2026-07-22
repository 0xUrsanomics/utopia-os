#!/usr/bin/env python3
# skill_failure_tracker.py — log skill failures, flag rewrite thresholds, recommend model-tier bumps.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
Skill Failure Tracker. Logs failures, checks rewrite thresholds, prunes stale entries.

Usage:
  # Log a failure (optional 4th arg = model tier, enables tier-promotion analysis)
  python skill_failure_tracker.py log <skill_name> "<error_summary>" [model]

  # Check if any skills need rewrite (run by nightly audit)
  python skill_failure_tracker.py check

  # Prune entries older than 30 days
  python skill_failure_tracker.py prune

  # Show current state
  python skill_failure_tracker.py status

  # Register a skill as an accepted structural ceiling (PERMANENT rewrite exemption,
  # no grace expiry). Failures still log + show the count, but never flag REWRITE.
  python skill_failure_tracker.py accept-ceiling <skill_name> "<reason>"

  # Remove an accepted-ceiling exemption
  python skill_failure_tracker.py unaccept-ceiling <skill_name>

Ledger: memory/Infra/skill-failure-ledger.json
Threshold: 3 failures in 14 days -> queued for rewrite
"""

import collections
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
LEDGER_PATH = ROOT / "memory" / "Infra" / "skill-failure-ledger.json"
FAILURE_THRESHOLD = 3
WINDOW_DAYS = 14
EXPIRY_DAYS = 30

# Model-tier promotion on CAPABILITY-limited repeat-fail. The tracker already
# stops+flags on 3x same-shape fail. This adds the missing classifier: is the
# repeat-fail a MODEL-CAPABILITY limit (promote the tier) or a CODE/infra bug (fix
# the code)?
MODEL_LADDER = ["haiku", "sonnet", "opus"]
_CODE_SMELL = (
    "traceback", "timeout", "timed out", "exit code", "exit status", "no such file",
    "not found", "keyerror", "valueerror", "typeerror", "nonetype", "importerror",
    "modulenotfound", "syntaxerror", "connection", "econnrefused", "enoent",
    "permission denied", "auth", "token", "rate limit", "429", "500", "502", "503",
    "refused", "parse error", "jsondecode", "null pointer",
)
_CAP_SMELL = (
    "wrong", "incorrect", "hallucinat", "made up", "fabricat", "missed", "gave up",
    "incoherent", "low quality", "low-quality", "off-topic", "off topic", "misunderstood",
    "misread", "misframe", "overclaim", "ignored the", "failed to follow", "didn't follow",
    "did not follow", "shallow", "generic", "slop", "vague", "inaccurate", "weak take",
)


def load_ledger():
    if LEDGER_PATH.exists():
        ledger = json.loads(LEDGER_PATH.read_text())
    else:
        ledger = {"_schema": "skill-failure-ledger-v1", "failures": [], "rewrite_queue": []}
    # accepted_ceiling: {skill: {reason, since}}. permanent rewrite exemption for
    # known structural limits (e.g. a hook-recovered ~10% miss rate). Distinct from
    # `dismiss` (30d grace that expires + re-queues).
    ledger.setdefault("accepted_ceiling", {})
    return ledger


def save_ledger(ledger):
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, default=str) + "\n")


def classify_failure_kind(error: str) -> str:
    """Heuristic: is a failure model-CAPABILITY-limited or CODE/infra-limited?

    Code/infra smells win ties: a timeout or traceback is an infra problem, not a
    dumb-model problem, so promoting the tier would not fix it.
    """
    e = (error or "").lower()
    if any(k in e for k in _CODE_SMELL):
        return "code"
    if any(k in e for k in _CAP_SMELL):
        return "capability"
    return "unknown"


def _next_tier(model: str):
    m = (model or "").lower()
    for i, t in enumerate(MODEL_LADDER[:-1]):
        if t in m:
            return MODEL_LADDER[i + 1]
    return None  # already top tier, or unrecognized model string


def recommend_tier_bump(recent):
    """Return a promote-tier recommendation string, or None.

    Fires only when capability-smelling failures DOMINATE (cap > code). This answers
    the 'is this a model-capability limit?' question mechanically.
    Detect+recommend ONLY. a human applies the bump.
    """
    kinds = [classify_failure_kind(f.get("error", "")) for f in recent]
    cap, code = kinds.count("capability"), kinds.count("code")
    if cap == 0 or cap <= code:
        return None  # code/infra dominated, or nothing capability-ish -> not a tier problem
    models = [f.get("model") for f in recent if f.get("model")]
    if not models:
        return (f"model-limited smell ({cap}/{len(recent)} capability-kind, not code bugs); "
                f"model not recorded, re-log with a 4th arg <model> to name the exact tier bump")
    top = collections.Counter(m.lower() for m in models).most_common(1)[0][0]
    nt = _next_tier(top)
    if nt is None:
        return (f"model-limited smell ({cap}/{len(recent)}) on '{top}', already top tier; "
                f"root-cause instead of promoting")
    return (f"PROMOTE-TIER candidate: {cap}/{len(recent)} failures are capability-kind on "
            f"'{top}' -> consider {nt} (detect+recommend only, human applies)")


def log_failure(skill_name: str, error_summary: str, model: str = None):
    """Log a skill failure and check if rewrite threshold is hit."""
    ledger = load_ledger()
    now = datetime.now().isoformat()

    rec = {
        "skill": skill_name,
        "ts": now,
        "error": error_summary[:200]  # truncate
    }
    if model:
        rec["model"] = model
    ledger["failures"].append(rec)

    # Accepted-ceiling skills: keep logging the failure (raw count stays visible
    # in `status`) but NEVER queue a rewrite. Permanent, no grace expiry. This is
    # the prose<->state reconciliation: an accepted-ceiling decision is now
    # machine-visible to the nightly audit.
    if skill_name in ledger.get("accepted_ceiling", {}):
        ac = ledger["accepted_ceiling"][skill_name]
        print(f"accepted-ceiling: {skill_name} logged, rewrite suppressed "
              f"(since {str(ac.get('since', ''))[:10]}: {str(ac.get('reason', ''))[:70]})")
        save_ledger(ledger)
        return

    # Check threshold
    cutoff = (datetime.now() - timedelta(days=WINDOW_DAYS)).isoformat()
    recent = [f for f in ledger["failures"]
              if f["skill"] == skill_name and f["ts"] >= cutoff]

    if len(recent) >= FAILURE_THRESHOLD:
        # Most-recent terminal entry. If it's a dismissal within DISMISS_GRACE_DAYS,
        # treat the skill as accepted-ceiling and suppress new re-queueing.
        DISMISS_GRACE_DAYS = 30
        terminal = [q for q in ledger["rewrite_queue"] if q["skill"] == skill_name and q.get("status") in ("completed", "dismissed")]
        terminal_sorted = sorted(terminal, key=lambda q: q.get("dismissed_at") or q.get("completed_at") or q.get("flagged_at") or "", reverse=True)
        latest = terminal_sorted[0] if terminal_sorted else None
        if latest and latest.get("status") == "dismissed":
            ts_str = latest.get("dismissed_at") or latest.get("flagged_at") or ""
            try:
                age_days = (datetime.now() - datetime.fromisoformat(ts_str)).days
            except Exception:
                age_days = 0
            if age_days < DISMISS_GRACE_DAYS:
                print(f"suppressed re-queue: {skill_name} dismissed {age_days}d ago ({DISMISS_GRACE_DAYS}d grace)")
                save_ledger(ledger)
                return

        # Check not already pending
        queued = [q for q in ledger["rewrite_queue"]
                  if q["skill"] == skill_name and q.get("status") == "pending"]
        if not queued:
            tier_rec = recommend_tier_bump(recent)
            ledger["rewrite_queue"].append({
                "skill": skill_name,
                "flagged_at": now,
                "failure_count": len(recent),
                "recent_errors": [f["error"] for f in recent[-3:]],
                "recent_models": [f.get("model") for f in recent[-3:]],
                "tier_recommendation": tier_rec,
                "status": "pending"
            })
            print(f"REWRITE FLAGGED: {skill_name} ({len(recent)} failures in {WINDOW_DAYS} days)")
            if tier_rec:
                print(f"  -> {tier_rec}")
        else:
            print(f"already queued: {skill_name}")
    else:
        remaining = FAILURE_THRESHOLD - len(recent)
        print(f"logged: {skill_name} ({len(recent)}/{FAILURE_THRESHOLD} in window, {remaining} more before rewrite flag)")

    save_ledger(ledger)


def check_rewrite_queue():
    """Return skills that need rewrite attention."""
    ledger = load_ledger()
    pending = [q for q in ledger["rewrite_queue"] if q["status"] == "pending"]

    if not pending:
        print("no skills queued for rewrite")
        return

    print(f"{len(pending)} skill(s) queued for rewrite:\n")
    for q in pending:
        print(f"  {q['skill']}. {q['failure_count']} failures, flagged {q['flagged_at'][:10]}")
        for i, err in enumerate(q.get("recent_errors", []), 1):
            print(f"    error {i}: {err}")
        if q.get("tier_recommendation"):
            print(f"    -> tier: {q['tier_recommendation']}")
        print()


def prune_stale():
    """Remove failure entries older than EXPIRY_DAYS.

    Also clears terminal rewrite-queue entries (completed / dismissed) older
    than EXPIRY_DAYS so the queue stays a working set, not a forever log.
    Pending entries are never pruned by age.
    """
    ledger = load_ledger()
    cutoff = (datetime.now() - timedelta(days=EXPIRY_DAYS)).isoformat()

    before_failures = len(ledger["failures"])
    ledger["failures"] = [f for f in ledger["failures"] if f["ts"] >= cutoff]
    pruned_failures = before_failures - len(ledger["failures"])

    before_queue = len(ledger["rewrite_queue"])
    ledger["rewrite_queue"] = [
        q for q in ledger["rewrite_queue"]
        if q["status"] not in ("completed", "dismissed")
        or q.get("flagged_at", "") >= cutoff
    ]
    pruned_queue = before_queue - len(ledger["rewrite_queue"])

    save_ledger(ledger)
    print(f"pruned {pruned_failures} stale failures + {pruned_queue} terminal queue entries (>{EXPIRY_DAYS}d)")


def dismiss_rewrite(skill_name: str, reason: str):
    """Mark a pending rewrite as dismissed (accepted ceiling, not actually rewritten).

    Use when a flagged skill cannot be improved further (known infrastructure
    limit, third-party flake, accepted noise). Different from `mark_rewrite_done`
    which implies an actual rewrite was performed.
    """
    ledger = load_ledger()
    for q in ledger["rewrite_queue"]:
        if q["skill"] == skill_name and q["status"] == "pending":
            q["status"] = "dismissed"
            q["dismissed_at"] = datetime.now().isoformat()
            q["dismissed_reason"] = reason[:300]
            save_ledger(ledger)
            print(f"dismissed {skill_name} rewrite: {reason[:80]}")
            return
    print(f"no pending rewrite found for {skill_name}")


def accept_ceiling(skill_name: str, reason: str):
    """Register a skill as an accepted structural ceiling.

    PERMANENT rewrite exemption (no 30d grace expiry, unlike `dismiss`). Use when
    a skill's failure rate is a known, decided-against-fixing structural limit
    (infra floor, third-party flake, hook-recovered miss). Failures still LOG
    (count stays visible in status); they just never flag *** REWRITE. Also clears
    any currently-pending rewrite for the skill.
    """
    ledger = load_ledger()
    ledger["accepted_ceiling"][skill_name] = {
        "reason": reason[:300],
        "since": datetime.now().isoformat(),
    }
    cleared = 0
    for q in ledger["rewrite_queue"]:
        if q["skill"] == skill_name and q.get("status") == "pending":
            q["status"] = "dismissed"
            q["dismissed_at"] = datetime.now().isoformat()
            q["dismissed_reason"] = f"accepted-ceiling: {reason[:200]}"
            cleared += 1
    save_ledger(ledger)
    print(f"accepted-ceiling registered: {skill_name} ({reason[:80]})")
    if cleared:
        print(f"  cleared {cleared} pending rewrite(s)")


def unaccept_ceiling(skill_name: str):
    """Remove a skill's accepted-ceiling exemption (rewrites can flag again)."""
    ledger = load_ledger()
    if skill_name in ledger.get("accepted_ceiling", {}):
        del ledger["accepted_ceiling"][skill_name]
        save_ledger(ledger)
        print(f"removed accepted-ceiling exemption: {skill_name}")
    else:
        print(f"no accepted-ceiling exemption for {skill_name}")


def show_status():
    """Show current ledger state."""
    ledger = load_ledger()
    cutoff = (datetime.now() - timedelta(days=WINDOW_DAYS)).isoformat()

    # Count recent failures per skill
    recent_by_skill = {}
    for f in ledger["failures"]:
        if f["ts"] >= cutoff:
            recent_by_skill.setdefault(f["skill"], []).append(f)

    print("=== Skill Failure Tracker ===")
    print(f"Total failures (all time): {len(ledger['failures'])}")
    print(f"Skills with recent failures ({WINDOW_DAYS}d window):")

    accepted = ledger.get("accepted_ceiling", {})
    if recent_by_skill:
        for skill, failures in sorted(recent_by_skill.items(), key=lambda x: -len(x[1])):
            if skill in accepted:
                flag = " [accepted-ceiling]"
            elif len(failures) >= FAILURE_THRESHOLD:
                flag = " *** REWRITE"
            else:
                flag = ""
            print(f"  {skill}: {len(failures)}/{FAILURE_THRESHOLD}{flag}")
    else:
        print("  (none)")

    pending = [q for q in ledger["rewrite_queue"]
               if q["status"] == "pending" and q["skill"] not in accepted]
    if pending:
        print(f"\nRewrite queue ({len(pending)} pending):")
        for q in pending:
            print(f"  {q['skill']}. flagged {q['flagged_at'][:10]}")

    if accepted:
        print("\nAccepted-ceiling (permanent rewrite exemption):")
        for skill, meta in accepted.items():
            print(f"  {skill}: since {str(meta.get('since', ''))[:10]} - {str(meta.get('reason', ''))[:70]}")


def mark_rewrite_done(skill_name: str):
    """Mark a rewrite as completed."""
    ledger = load_ledger()
    for q in ledger["rewrite_queue"]:
        if q["skill"] == skill_name and q["status"] == "pending":
            q["status"] = "completed"
            q["completed_at"] = datetime.now().isoformat()
            print(f"marked {skill_name} rewrite as completed")
            save_ledger(ledger)
            return
    print(f"no pending rewrite found for {skill_name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "log" and len(sys.argv) >= 4:
        model = sys.argv[4] if len(sys.argv) >= 5 else None
        log_failure(sys.argv[2], sys.argv[3], model)
    elif cmd == "check":
        check_rewrite_queue()
    elif cmd == "prune":
        prune_stale()
    elif cmd == "status":
        show_status()
    elif cmd == "done" and len(sys.argv) >= 3:
        mark_rewrite_done(sys.argv[2])
    elif cmd == "dismiss" and len(sys.argv) >= 4:
        dismiss_rewrite(sys.argv[2], sys.argv[3])
    elif cmd == "accept-ceiling" and len(sys.argv) >= 4:
        accept_ceiling(sys.argv[2], sys.argv[3])
    elif cmd == "unaccept-ceiling" and len(sys.argv) >= 3:
        unaccept_ceiling(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)
