#!/usr/bin/env python3
# bench_stats.py: honest A-vs-B benchmark statistics.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Honest A-vs-B benchmark statistics: intervals, a paired test, cost per solve, and a verdict.

Why: a bench that reports single accuracies invites calling 85.8 vs 84.9 a "tie" (or a "win") by
eye. Reporting pattern from plurnk-bench (github.com/plurnk/plurnk-bench): Wilson intervals per arm,
a paired test on the same cells, discordant counts, cost per solve, and "not separated" stated
plainly when the test cannot tell the arms apart.

  bench_stats.py paired results.jsonl [--a NAME --b NAME]
      rows: {"item": "...", "arm": "...", "pass": true|false|0|1, "attempt": 1 (optional), "cost": 0.01 (optional)}
      Pairs cells by (item, attempt). Exact McNemar on discordant cells; with repeated attempts also a
      per-item sign-flip permutation test (the plurnk-bench test). Exit 0 always; read the verdict line.
  bench_stats.py quick --a NAME:PASSES/N --b NAME:PASSES/N
      Aggregate-only fallback (no per-item data): Wilson intervals + two-proportion z test.
      Weaker than paired; say so when you use it.
  bench_stats.py selftest
"""
import argparse
import json
import math
import random
import sys
from collections import defaultdict

Z95 = 1.959963984540054


def wilson(k, n, z=Z95):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def mcnemar_exact(b, c):
    """Two-sided exact binomial test on discordant counts b (only A) and c (only B)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def signflip(diffs, resamples=20000, seed=7):
    """Two-sided sign-flip permutation test on per-item differences (plurnk-bench's paired test)."""
    obs = abs(sum(diffs))
    if obs == 0:
        return 1.0
    rng = random.Random(seed)
    hit = 0
    for _ in range(resamples):
        if abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= obs:
            hit += 1
    return (hit + 1) / (resamples + 1)


def two_prop_z(k1, n1, k2, n2):
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (k1 / n1 - k2 / n2) / se
    return math.erfc(abs(z) / math.sqrt(2))


def pct(x):
    return f"{100 * x:.1f}%"


def verdict(p, a, b, ka, kb):
    lead = a if ka > kb else b
    if ka == kb:
        return f"VERDICT: equal counts, nothing to separate (p = {p:.3g})."
    if p < 0.05:
        return f"VERDICT: SEPARATED, {lead} ahead (p = {p:.3g} < 0.05)."
    return (f"VERDICT: NOT SEPARATED (p = {p:.3g}). {lead} is ahead in this sample; report the direction "
            f"as observed, not as a difference. Do not call it a win, and do not call it a tie either.")


def paired(path, a=None, b=None):
    cells = defaultdict(dict)
    cost = defaultdict(float)
    has_cost = False
    attempts = set()
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        key = (str(r["item"]), r.get("attempt", 1))
        attempts.add(key[1])
        cells[key][r["arm"]] = bool(r["pass"])
        if "cost" in r:
            has_cost = True
            cost[r["arm"]] += float(r["cost"])
    arms = sorted({arm for c in cells.values() for arm in c})
    a = a or arms[0]
    b = b or arms[1]
    shared = {k: v for k, v in cells.items() if a in v and b in v}
    dropped = len(cells) - len(shared)
    n = len(shared)
    ka = sum(v[a] for v in shared.values())
    kb = sum(v[b] for v in shared.values())
    both = sum(v[a] and v[b] for v in shared.values())
    only_a = sum(v[a] and not v[b] for v in shared.values())
    only_b = sum(v[b] and not v[a] for v in shared.values())
    neither = n - both - only_a - only_b
    print(f"{'arm':14} {'passes':>12} {'95% Wilson':>16}" + (f" {'spend':>9} {'per solve':>10}" if has_cost else ""))
    for arm, k in ((a, ka), (b, kb)):
        lo, hi = wilson(k, n)
        row = f"{arm:14} {k:>4}/{n:<4} {pct(k / n):>6} {pct(lo):>7}-{pct(hi):<7}"
        if has_cost:
            row += f" {cost[arm]:>9.3f} {(cost[arm] / k if k else float('nan')):>10.4f}"
        print(row)
    print(f"cells: both {both} · only {a} {only_a} · only {b} {only_b} · neither {neither}"
          + (f" · {dropped} cells missing an arm, excluded" if dropped else ""))
    p_mc = mcnemar_exact(only_a, only_b)
    print(f"exact McNemar on discordant cells: p = {p_mc:.3g}")
    p = p_mc
    if len(attempts) > 1:
        per_item = defaultdict(int)
        for (item, _), v in shared.items():
            per_item[item] += int(v[a]) - int(v[b])
        p = signflip(list(per_item.values()))
        print(f"per-item sign-flip permutation ({len(per_item)} items x {len(attempts)} attempts, 20,000 resamples): p = {p:.3g}")
    print(verdict(p, a, b, ka, kb))


def quick(a, b):
    def parse(s):
        name, frac = s.rsplit(":", 1)
        k, n = frac.split("/")
        return name, int(k), int(n)
    (na, ka, nna), (nb, kb, nnb) = parse(a), parse(b)
    for name, k, n in ((na, ka, nna), (nb, kb, nnb)):
        lo, hi = wilson(k, n)
        print(f"{name:14} {k:>4}/{n:<4} {pct(k / n):>6}  95% Wilson {pct(lo)}-{pct(hi)}")
    p = two_prop_z(ka, nna, kb, nnb)
    print(f"two-proportion z test (UNPAIRED, aggregate only; a paired run on the same items is stronger): p = {p:.3g}")
    print(verdict(p, na, nb, ka / nna, kb / nnb))


def selftest():
    ok = True
    # plurnk-bench evidence-2026-10-11 publishes 66/90 -> 63.4-81.4% and 59/90 -> 55.3-74.6% (Wilson).
    for k, n, want in ((66, 90, (63.4, 81.4)), (59, 90, (55.3, 74.6))):
        lo, hi = wilson(k, n)
        got = (round(100 * lo, 1), round(100 * hi, 1))
        ok &= got == want
        print(f"wilson {k}/{n}: {got} want {want} {'ok' if got == want else 'FAIL'}")
    # Exact McNemar: 9 vs 2 discordant -> two-sided binomial p = 0.0654.
    p = mcnemar_exact(9, 2)
    ok &= abs(p - 0.0654) < 0.001
    print(f"mcnemar 9 vs 2: {p:.4f} want 0.0654 {'ok' if abs(p - 0.0654) < 0.001 else 'FAIL'}")
    # Control pair: identical arms must not separate; a large real gap must.
    same = signflip([1, -1] * 15)
    big = signflip([1] * 25 + [0] * 5)
    ok &= same > 0.5 and big < 0.001
    print(f"signflip null {same:.3f} (want > 0.5), signflip strong {big:.5f} (want < 0.001)")
    print(f"selftest {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["paired", "quick", "selftest"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--a")
    ap.add_argument("--b")
    x = ap.parse_args()
    if x.mode == "selftest":
        return selftest()
    if x.mode == "paired":
        if not x.path:
            ap.error("paired needs a results.jsonl path")
        paired(x.path, x.a, x.b)
    else:
        if not (x.a and x.b):
            ap.error("quick needs --a NAME:K/N --b NAME:K/N")
        quick(x.a, x.b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
