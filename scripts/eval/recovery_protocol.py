#!/usr/bin/env python3
# recovery_protocol.py: escalation ladder, context partition and plan versioning for agent runs.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
recovery_protocol.py. Reference implementation of 3 patterns from
Graph Harness (arXiv 2604.11378).

Ships 3 additive primitives. Nothing live depends on this until you wire it in.

  1. EscalationLadder. ordered bounded recovery (L1 retry -> L2 patch -> L3 replan).
     enforces the level-ordering invariant (never skip a level) + a hard replan cap
     (anti unbounded-replan, the paper's core safety property).
  2. ContextPartition. keeps failure/diagnostic history OUT of the retry's
     execution-reasoning premise (the formal fix for a common root cause: a flawed
     premise from an earlier failure corrupting the answer reasoned on top of it).
  3. PlanVersion. immutable plan-version stamp + audit trail of which version
     governed which actions (debuggability for autonomous multi-step runs).

Stdlib only. No new deps (security-first). Run: python3 recovery_protocol.py --selftest
"""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


# ---- Pattern 1: Escalation ladder ------------------------------------------

class Level(int, Enum):
    RETRY = 1     # mechanical, no LLM, transient failures (timeouts, rate limits)
    PATCH = 2     # LLM local fix, node-scoped, does NOT change plan structure
    REPLAN = 3    # full replan, only after L1+L2 exhausted, new plan version


@dataclass
class LadderConfig:
    retry_budget: int = 2      # L1 attempts before escalate
    patch_budget: int = 3      # L2 attempts before escalate (paper: ~3)
    replan_cap: int = 2        # max full replans before a hard ABORT (anti unbounded)


@dataclass
class RecoveryOutcome:
    resolved: bool
    level_reached: Optional[int]
    aborted: bool
    trace: list                # ordered [(level, attempt, ok), ...]
    reason: str


class EscalationLadder:
    """Ordered, bounded recovery. Invariants enforced by construction:
    never skip a level, never replan until retry+patch are exhausted,
    never exceed replan_cap (=> ABORT + escalate to operator)."""

    def __init__(self, cfg: Optional[LadderConfig] = None):
        self.cfg = cfg or LadderConfig()

    def run(self, *, retry: Callable[[], bool], patch: Callable[[], bool],
            replan: Callable[[], bool]) -> RecoveryOutcome:
        trace = []
        # L1 mechanical retry
        for a in range(1, self.cfg.retry_budget + 1):
            ok = bool(retry())
            trace.append((Level.RETRY.value, a, ok))
            if ok:
                return RecoveryOutcome(True, 1, False, trace, "resolved at L1 retry")
        # L2 local patch (only reached after L1 exhausted)
        for a in range(1, self.cfg.patch_budget + 1):
            ok = bool(patch())
            trace.append((Level.PATCH.value, a, ok))
            if ok:
                return RecoveryOutcome(True, 2, False, trace, "resolved at L2 patch")
        # L3 full replan (only reached after L1+L2 exhausted), capped
        for v in range(1, self.cfg.replan_cap + 1):
            ok = bool(replan())
            trace.append((Level.REPLAN.value, v, ok))
            if ok:
                return RecoveryOutcome(True, 3, False, trace, f"resolved at L3 replan v{v}")
        return RecoveryOutcome(
            False, 3, True, trace,
            f"ABORT: replan_cap={self.cfg.replan_cap} exhausted, escalate to operator")


# ---- Pattern 2: Context partition ------------------------------------------

@dataclass
class PartitionedContext:
    """C_exec vs C_diag. The retry reasons over exec_ctx ONLY. diag_ctx is a
    separate labeled block it may READ as evidence but never inherits as premise.
    Prevents failure history from silently becoming the next attempt's assumption."""
    exec_ctx: dict = field(default_factory=dict)   # clean task inputs/outputs
    diag_ctx: list = field(default_factory=list)   # failure history, kill reasons

    def record_failure(self, level: int, reason: str, artifact: str = "") -> None:
        self.diag_ctx.append({"level": level, "reason": reason, "artifact": artifact})

    def retry_view(self) -> dict:
        """What the next attempt SEES: clean execution context + diagnostics
        fenced as external evidence, NOT merged into the working premise."""
        return {
            "execution_context": dict(self.exec_ctx),
            "diagnostic_evidence": list(self.diag_ctx),   # fenced, labeled, not premise
            "_rule": ("diagnostic_evidence is prior-failure history. do NOT adopt it as "
                      "premise. reason from execution_context. use diagnostics only to "
                      "avoid repeating a mistake."),
        }


# ---- Pattern 3: Plan-version audit trail -----------------------------------

@dataclass
class PlanVersion:
    """Immutable plan-version stamp + audit trail. A structural change is a NEW
    version (prior actions retained). Lets an autonomous run answer 'which plan
    version governed which action' after the fact."""
    plan_id: str
    version: int = 1
    actions: list = field(default_factory=list)

    def stamp(self, action: str) -> None:
        self.actions.append({"v": self.version, "action": action})

    def bump(self, reason: str) -> "PlanVersion":
        self.actions.append({"v": self.version, "action": f"__REPLAN__: {reason}"})
        self.version += 1
        return self

    def audit(self) -> dict:
        return {"plan_id": self.plan_id, "current_version": self.version,
                "trail": list(self.actions)}


# ---- self-test -----------------------------------------------------------

def _selftest() -> int:
    fails = []

    # 1. resolves at L1 when first retry works
    got = EscalationLadder().run(retry=lambda: True, patch=lambda: False, replan=lambda: False)
    if not (got.resolved and got.level_reached == 1):
        fails.append(f"L1-resolve: {got}")

    # 2. escalates L1->L2->L3 in order, resolves at L3
    got = EscalationLadder(LadderConfig(retry_budget=2, patch_budget=2, replan_cap=2)).run(
        retry=lambda: False, patch=lambda: False, replan=lambda: True)
    levels = [t[0] for t in got.trace]
    if levels != [1, 1, 2, 2, 3]:
        fails.append(f"ordering: {levels}")
    if not got.resolved or got.level_reached != 3:
        fails.append(f"L3-resolve: {got}")

    # 3. invariant: replan never fires before retry+patch exhausted
    calls = []
    EscalationLadder(LadderConfig(2, 2, 1)).run(
        retry=lambda: (calls.append("r"), False)[1],
        patch=lambda: (calls.append("p"), False)[1],
        replan=lambda: (calls.append("R"), False)[1])
    if calls != ["r", "r", "p", "p", "R"]:
        fails.append(f"invariant: {calls}")

    # 4. abort after replan_cap exhausted
    got = EscalationLadder(LadderConfig(1, 1, 2)).run(
        retry=lambda: False, patch=lambda: False, replan=lambda: False)
    if not got.aborted:
        fails.append(f"abort: {got}")

    # 5. context partition: diag never leaks into exec premise
    pc = PartitionedContext(exec_ctx={"task": "draft tweet", "premise": "X is true"})
    pc.record_failure(2, "premise Y was false", "killed draft")
    view = pc.retry_view()
    if "premise Y was false" in json.dumps(view["execution_context"]):
        fails.append("partition-leak")
    if not view["diagnostic_evidence"]:
        fails.append("partition-lost-diag")

    # 6. plan version bump keeps immutable trail
    pv = PlanVersion("run-abc")
    pv.stamp("did A")
    pv.bump("structure changed")
    pv.stamp("did B")
    au = pv.audit()
    if au["current_version"] != 2:
        fails.append(f"version: {au}")
    if len(au["trail"]) != 3:
        fails.append(f"trail: {au}")

    if fails:
        print("SELFTEST FAIL:")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST PASS 6/6: escalation ladder (ordering + invariant + abort), "
          "context partition (no leak, diag kept), plan-version audit (immutable trail).")
    return 0


def _cli_stamp(argv) -> int:
    """Emit a plan_version-tagged log line. For autonomous multi-step runs
    (harvesters, daily-forest, run-folders) to record which plan version
    governed the run. Additive: appends one JSONL line, touches nothing else."""
    import datetime

    def _arg(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default

    plan = _arg("--plan")
    if not plan:
        print("usage: recovery_protocol.py --stamp --plan <id> [--action <text>] [--version N] [--log <path>]")
        return 2
    rec = {
        "ts": datetime.datetime.now().astimezone().isoformat(),
        "level": "info", "category": "system", "event": "plan_version_stamp",
        "plan_version": {"plan_id": plan, "version": int(_arg("--version", "1")),
                         "action": _arg("--action", "")},
    }
    log = _arg("--log", "logs/session.jsonl")
    with open(log, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(f"stamped plan_version: {plan} v{rec['plan_version']['version']} -> {log}")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--stamp" in sys.argv:
        sys.exit(_cli_stamp(sys.argv))
    print(__doc__)
