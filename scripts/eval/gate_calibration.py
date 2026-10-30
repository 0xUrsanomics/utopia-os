#!/usr/bin/env python3
# gate_calibration.py: do the scorers still score known answers correctly?
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Do our scorers still score known answers correctly?

A gate that passes everything looks exactly like a gate guarding good work. Pattern from the
elizaOS benchmark calibration agents (perfect / wrong / half answers run through every scorer,
packages/benchmarks/orchestrator/random_baseline_runner.py): before trusting a gate's verdict on
real work, prove it still tells a known-good input from a known-bad one.

Runs every listed gate's own selftest. FAILS if any check fails or any gate ran zero cases (a
check that ran nothing is a FAIL, never green). KNOWN_GAPS are blind spots you have measured and
not yet fixed: list them as (command, why); they are run and reported every time, never counted
as passes, and a gap whose command starts passing is reported so the entry can be removed.

Add your own gates to SELFTESTS as a path under scripts/ plus its selftest arguments. The output
must contain "N/M" or a dict of named True/False checks, so the runner can count what ran.

    python3 gate_calibration.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]

# (script under scripts/, selftest arguments)
SELFTESTS = [
    ("pipeline/external_slop_gate.py", ["--selftest"]),
    ("pipeline/paraphrase_test.py", ["--selftest"]),
    ("eval/hallucination_sample.py", ["--selftest-offline"]),
    ("memory/lib_provenance.py", ["sanitize", "--selftest"]),
    ("eval/lib_case_coverage.py", ["--selftest"]),
    ("security/confirm_ledger.py", ["--selftest"]),
    ("eval/bench_stats.py", ["selftest"]),
    ("eval/label_consensus.py", ["selftest"]),
    ("memory/open_loops.py", ["--selftest"]),
    ("memory/addr.py", ["selftest"]),
]

# (script, args, why). Example shape:
#   ("pipeline/voice_gate.py", ["--draft", "fixtures/anaphora.md"], "ten 'The X is Y.' lines pass")
KNOWN_GAPS: list[tuple[str, list[str], str]] = []


def run(script: str, args: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True,
                       timeout=300, cwd=SCRIPTS.parent)
    return p.returncode, p.stdout + p.stderr


def count(out: str) -> tuple[int, int]:
    """(passed, total) from either 'N/M' or a dict of named True/False checks."""
    checks = re.findall(r"'[\w ?]+': (True|False)", out)
    if checks:
        return sum(v == "True" for v in checks), len(checks)
    # Prefer a summary count ("7/7 pass", "(18/18)", "14/14 passed"); data like "66/90" is not one.
    m = re.findall(r"(\d+)\s*/\s*(\d+)(?=\s*(?:pass|\)))", out)
    if m:
        a, b = m[-1]
        return int(a), int(b)
    if re.search(r"\bselftest PASS\b", out, re.I):
        return 1, 1  # a single pass/fail selftest: count it as one check that ran
    return 0, 0


def main() -> int:
    fails, lines = 0, []
    for script, args in SELFTESTS:
        if not (SCRIPTS / script).exists():
            fails += 1
            lines.append(f"FAIL  {script}: missing")
            continue
        rc, out = run(script, args)
        n_ok, n = count(out)
        ok = rc == 0 and n > 0 and n_ok == n
        fails += not ok
        lines.append(("ok  " if ok else "FAIL") + f"  {script} {' '.join(args)}: {n_ok}/{n}"
                     + ("" if n else " (ran nothing)") + ("" if rc == 0 else f" rc={rc}"))
    for script, args, why in KNOWN_GAPS:
        rc, _ = run(script, args)
        if rc == 0:
            lines.append(f"GAP CLOSED  {script}: now passes. Remove it from KNOWN_GAPS.")
        else:
            lines.append(f"KNOWN GAP   {script}: {why}")
    print("\n".join(lines))
    print(f"\ngate calibration: {len(SELFTESTS) - fails}/{len(SELFTESTS)} pass, {len(KNOWN_GAPS)} known gap(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
