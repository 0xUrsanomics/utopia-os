#!/usr/bin/env python3
# gate_controller.py: adaptive per-gate lambda so multi-gate revise loops stop ping-ponging.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
gate_controller.py - signed-margin constraint controller (CAPO control law port).

Ports the CONTROL LAW from CAPO (arXiv 2608.16068), NOT the optimizer and NOT any
training.

Problem it solves: the voice-vs-data (and any multi-gate) revise ping-pong, where
a fixed weighted score picks weights before seeing the trajectory and "retuning
replaces one violation with another". Instead of a static weighting, each gate
carries an ADAPTIVE lambda that self-tunes across revise rounds by a projected
subgradient step. A violated gate's lambda grows; a slack gate's lambda decays.
The BINDING constraint self-identifies as the largest-lambda violated gate, and
that single fact drives BOTH candidate ranking and the next rewrite instruction.

Primal-dual form (CAPO):
  J(p, lambda) = R(p) - sum_i lambda_i * (C_i - tau_i)
  dual update  lambda_i <- clip(lambda_i + beta * (cost_i - threshold_i), 0, lambda_max)

Here every gate is reduced to a SIGNED normalized margin (not pass/fail):
  floor   gate (measured must be >= threshold):  margin = (measured - threshold) / scale
  ceiling gate (measured must be <= threshold):  margin = (threshold - measured) / scale
A data-target treated as a floor uses direction "floor". Positive margin = slack
(satisfied), negative margin = violation. The dual update is then, per gate:
  lambda_i <- clip(lambda_i + beta * (-margin_i), 0, lambda_max)
which is exactly CAPO's rule normalized by scale (violated -> lambda up, slack -> down).

Pure stdlib. No third-party deps. ASCII only.
"""

import argparse
import json
import sys

# --- defaults (all configurable) -------------------------------------------
DEFAULT_BETA = 1.0
DEFAULT_LAMBDA_MAX = 10.0
DEFAULT_LAMBDA_INIT = 1.0
_EPS = 1e-12  # margins within +/- EPS of zero are treated as exactly satisfied


# --- core control law -------------------------------------------------------
def compute_margin(gate):
    """Signed normalized margin for one gate.

    gate: dict with keys name, measured, threshold, scale, direction.
      direction "floor"   -> satisfied when measured >= threshold.
      direction "ceiling" -> satisfied when measured <= threshold.
    Returns a float. Positive = slack (satisfied), negative = violated.
    """
    measured = float(gate["measured"])
    threshold = float(gate["threshold"])
    scale = float(gate.get("scale", 1.0))
    if scale == 0.0:
        raise ValueError("gate %r has scale 0; scale must be non-zero" % gate.get("name"))
    scale = abs(scale)
    direction = str(gate.get("direction", "floor")).lower()
    if direction == "floor":
        return (measured - threshold) / scale
    if direction == "ceiling":
        return (threshold - measured) / scale
    raise ValueError("gate %r has unknown direction %r (want floor|ceiling)"
                     % (gate.get("name"), direction))


def signed_margins(gates):
    """Return an ordered dict {name: margin} for a list of gate dicts."""
    out = {}
    for g in gates:
        out[g["name"]] = compute_margin(g)
    return out


def is_violated(margin):
    """A gate is violated only when its margin is meaningfully below zero."""
    return margin < -_EPS


def update_lambdas(gates, lambdas=None, beta=DEFAULT_BETA,
                   lambda_max=DEFAULT_LAMBDA_MAX, init=DEFAULT_LAMBDA_INIT):
    """Projected-subgradient dual update, one step (CAPO Eq.4).

    lambda_i <- clip(lambda_i + beta * (-margin_i), 0, lambda_max)

    lambdas: dict {name: lambda} carried ACROSS revise rounds. Missing gates
             start at `init`. The caller persists the returned dict.
    Returns a NEW dict; the input is not mutated.
    """
    lambdas = dict(lambdas or {})
    out = dict(lambdas)
    for g in gates:
        name = g["name"]
        cur = lambdas.get(name, init)
        margin = compute_margin(g)
        nxt = cur + beta * (-margin)
        if nxt < 0.0:
            nxt = 0.0
        elif nxt > lambda_max:
            nxt = lambda_max
        out[name] = nxt
    return out


def binding_constraint(gates, lambdas, init=DEFAULT_LAMBDA_INIT):
    """The binding constraint = largest-lambda gate among currently violated ones.

    Returns (name, margin, lam) or (None, None, None) when feasible (nothing
    violated). Ties on lambda break by most-negative margin, then gate order.
    """
    best = None
    for g in gates:
        margin = compute_margin(g)
        if not is_violated(margin):
            continue
        lam = lambdas.get(g["name"], init)
        key = (lam, -margin)  # higher lambda wins, then more-negative margin
        if best is None or key > best[0]:
            best = (key, g["name"], margin, lam)
    if best is None:
        return (None, None, None)
    return (best[1], best[2], best[3])


def rewrite_instruction(gates, lambdas, init=DEFAULT_LAMBDA_INIT):
    """One-line instruction naming the binding constraint to protect next revise."""
    name, margin, _lam = binding_constraint(gates, lambdas, init=init)
    if name is None:
        return "feasible: no binding constraint, all gates satisfied"
    return ("binding constraint: %s (margin %.3f), protect it in the next revise"
            % (name, margin))


def candidate_score(candidate, lambdas, init=DEFAULT_LAMBDA_INIT):
    """J = quality - sum_i lambda_i * max(0, -margin_i).

    Only violations are penalized (slack gates do not add reward here). `quality`
    is an optional caller-supplied scalar, default 0.
    candidate: dict with keys `gates` (list) and optional `quality`, `name`.
    """
    quality = float(candidate.get("quality", 0.0))
    penalty = 0.0
    for g in candidate.get("gates", []):
        margin = compute_margin(g)
        if margin < 0.0:
            lam = lambdas.get(g["name"], init)
            penalty += lam * (-margin)
    return quality - penalty


def rank_candidates(candidates, lambdas, init=DEFAULT_LAMBDA_INIT):
    """Rank candidate drafts by J (highest first). Returns (best, ranked).

    `ranked` is a list of dicts {name, J, quality} in descending J order.
    `best` is the full best candidate dict (feasible-closest / highest reward).
    Original candidate order breaks ties (stable sort).
    """
    scored = []
    for i, c in enumerate(candidates):
        j = candidate_score(c, lambdas, init=init)
        scored.append((j, i, c))
    ranked_sorted = sorted(scored, key=lambda t: (-t[0], t[1]))
    ranked = [{"name": t[2].get("name", "cand%d" % t[1]),
               "J": t[0],
               "quality": float(t[2].get("quality", 0.0))}
              for t in ranked_sorted]
    best = ranked_sorted[0][2] if ranked_sorted else None
    return best, ranked


def step(gates, lambdas=None, beta=DEFAULT_BETA, lambda_max=DEFAULT_LAMBDA_MAX,
         init=DEFAULT_LAMBDA_INIT):
    """One full controller round: margins -> lambda update -> binding -> instruction.

    Binding constraint and rewrite instruction are read from the UPDATED lambdas,
    so the round's own signal is reflected. Returns a dict the caller persists:
      { margins, lambdas (updated), binding{name,margin,lambda}, instruction, feasible }
    """
    margins = signed_margins(gates)
    new_lambdas = update_lambdas(gates, lambdas, beta=beta,
                                 lambda_max=lambda_max, init=init)
    name, margin, lam = binding_constraint(gates, new_lambdas, init=init)
    return {
        "margins": margins,
        "lambdas": new_lambdas,
        "binding": {"name": name, "margin": margin, "lambda": lam},
        "instruction": rewrite_instruction(gates, new_lambdas, init=init),
        "feasible": name is None,
    }


# --- self test --------------------------------------------------------------
def _selftest():
    """Voice-vs-data scenario. Asserts the binding constraint flips across rounds."""
    print("gate_controller --selftest : voice-vs-data arbitration")
    print("-" * 60)
    ok = True

    # Round 1: voice violated (below floor), data satisfied (above target-floor).
    r1_gates = [
        {"name": "voice_overlap", "measured": 0.004, "threshold": 0.005,
         "scale": 0.001, "direction": "floor"},
        {"name": "data_density", "measured": 6.0, "threshold": 4.0,
         "scale": 1.0, "direction": "floor"},
    ]
    lambdas = {}  # fresh, everything starts at init=1.0
    r1 = step(r1_gates, lambdas)
    lambdas = r1["lambdas"]  # caller persists
    print("ROUND 1  (voice 0.004 < floor 0.005; data 6 >= target 4)")
    print("  margins   : voice=%.3f  data=%.3f"
          % (r1["margins"]["voice_overlap"], r1["margins"]["data_density"]))
    print("  lambdas   : voice=%.3f  data=%.3f"
          % (lambdas["voice_overlap"], lambdas["data_density"]))
    print("  binding   : %s (margin %s)"
          % (r1["binding"]["name"], r1["binding"]["margin"]))
    print("  rewrite   : %s" % r1["instruction"])

    # Assertions for round 1.
    if r1["binding"]["name"] != "voice_overlap":
        print("  FAIL: round-1 binding should be voice_overlap, got %r"
              % r1["binding"]["name"]); ok = False
    if not (lambdas["voice_overlap"] > DEFAULT_LAMBDA_INIT):
        print("  FAIL: lambda_voice should rise above init, got %.3f"
              % lambdas["voice_overlap"]); ok = False
    if not (lambdas["data_density"] < DEFAULT_LAMBDA_INIT):
        print("  FAIL: lambda_data should decay below init, got %.3f"
              % lambdas["data_density"]); ok = False
    if r1["feasible"]:
        print("  FAIL: round 1 should be infeasible"); ok = False

    voice_lambda_after_r1 = lambdas["voice_overlap"]

    # Round 2: the fix landed, voice now satisfied; data still satisfied.
    r2_gates = [
        {"name": "voice_overlap", "measured": 0.0052, "threshold": 0.005,
         "scale": 0.001, "direction": "floor"},
        {"name": "data_density", "measured": 6.0, "threshold": 4.0,
         "scale": 1.0, "direction": "floor"},
    ]
    r2 = step(r2_gates, lambdas)  # carries lambdas from round 1
    lambdas = r2["lambdas"]
    print("")
    print("ROUND 2  (voice 0.0052 >= floor 0.005; data 6 >= target 4)")
    print("  margins   : voice=%.3f  data=%.3f"
          % (r2["margins"]["voice_overlap"], r2["margins"]["data_density"]))
    print("  lambdas   : voice=%.3f  data=%.3f"
          % (lambdas["voice_overlap"], lambdas["data_density"]))
    print("  binding   : %s" % r2["binding"]["name"])
    print("  rewrite   : %s" % r2["instruction"])

    # Assertions for round 2.
    if r2["binding"]["name"] is not None:
        print("  FAIL: round-2 binding should be None (feasible), got %r"
              % r2["binding"]["name"]); ok = False
    if not r2["feasible"]:
        print("  FAIL: round 2 should be feasible"); ok = False
    if not (lambdas["voice_overlap"] < voice_lambda_after_r1):
        print("  FAIL: lambda_voice should decay in round 2 (%.3f -> %.3f)"
              % (voice_lambda_after_r1, lambdas["voice_overlap"])); ok = False

    # Candidate ranking check: two drafts under round-1 lambdas, the voice-fixed
    # one must win because voice carries the higher lambda / bigger penalty.
    r1_lambdas = r1["lambdas"]
    cand_voice_fixed = {"name": "fix_voice", "quality": 0.0, "gates": [
        {"name": "voice_overlap", "measured": 0.0052, "threshold": 0.005,
         "scale": 0.001, "direction": "floor"},
        {"name": "data_density", "measured": 3.0, "threshold": 4.0,
         "scale": 1.0, "direction": "floor"},
    ]}
    cand_data_fixed = {"name": "fix_data", "quality": 0.0, "gates": [
        {"name": "voice_overlap", "measured": 0.004, "threshold": 0.005,
         "scale": 0.001, "direction": "floor"},
        {"name": "data_density", "measured": 6.0, "threshold": 4.0,
         "scale": 1.0, "direction": "floor"},
    ]}
    best, ranked = rank_candidates([cand_data_fixed, cand_voice_fixed], r1_lambdas)
    print("")
    print("CANDIDATE RANKING (under round-1 lambdas; protect the binding gate)")
    for r in ranked:
        print("  %-10s J=%.3f" % (r["name"], r["J"]))
    print("  best      : %s" % best.get("name"))
    if best.get("name") != "fix_voice":
        print("  FAIL: ranking should prefer the voice-fixed draft, got %r"
              % best.get("name")); ok = False

    print("-" * 60)
    if ok:
        print("SELFTEST PASS: binding flips voice_overlap -> None; lambda rises then decays; ranking protects binding")
        return 0
    print("SELFTEST FAIL")
    return 1


# --- CLI --------------------------------------------------------------------
def _run_from_payload(payload):
    """Run one step or a ranking from a JSON payload; return a result dict."""
    beta = float(payload.get("beta", DEFAULT_BETA))
    lambda_max = float(payload.get("lambda_max", DEFAULT_LAMBDA_MAX))
    init = float(payload.get("init", DEFAULT_LAMBDA_INIT))
    lambdas = payload.get("lambdas", {})
    if "candidates" in payload:
        best, ranked = rank_candidates(payload["candidates"], lambdas, init=init)
        return {"mode": "rank",
                "best": (best or {}).get("name"),
                "ranked": ranked}
    gates = payload.get("gates", [])
    return {"mode": "step",
            **step(gates, lambdas, beta=beta, lambda_max=lambda_max, init=init)}


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Signed-margin constraint controller (CAPO control law).")
    p.add_argument("--selftest", action="store_true",
                   help="run the voice-vs-data scenario and assert binding flips")
    p.add_argument("--input", metavar="FILE",
                   help="JSON payload file; if omitted, read stdin")
    p.add_argument("--json", dest="inline_json", metavar="STR",
                   help="JSON payload as an inline string")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    raw = None
    if args.inline_json:
        raw = args.inline_json
    elif args.input:
        with open(args.input, "r") as fh:
            raw = fh.read()
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()

    if not raw or not raw.strip():
        p.print_help()
        print("\nExpected JSON payload with `gates` (control step) or `candidates` (ranking).")
        return 2

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print("ERROR: invalid JSON payload: %s" % e, file=sys.stderr)
        return 2

    try:
        result = _run_from_payload(payload)
    except (KeyError, ValueError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
