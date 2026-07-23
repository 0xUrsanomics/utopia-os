#!/usr/bin/env python3
# ab_eval.py — deterministic A/B eval harness for full-agent config changes.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""A/B eval harness: hold the model constant, make a CONFIG change the ONLY
variable, run a behavioral capability-axis corpus through both arms, score
DETERMINISTICALLY off the run transcript + resulting filesystem (NO LLM in the
scoring path), and report a 4-way head-to-head matrix
(both-pass / A-only / B-only / both-fail).

The pattern is "same model, only the loop varies": component-level A/Bs (rerank,
graph) miss whole-agent regressions, so this drives `claude -p` to A/B two full
agent configs against each other.

A "config" is a text file appended to the system prompt (an empty file = baseline).
The corpus, model, allowed-tools and per-case setup are held IDENTICAL across arms,
so the config addendum is the only variable. Each case runs in an isolated temp cwd.

Usage:
  ab_eval.py run --config-a A.txt [--config-b B.txt] [--corpus F] [--model M]
                 [--case ID] [--timeout SEC] [--json]
      config-a alone  -> single-arm behavioral pass/fail report.
      config-a + config-b -> A/B 4-way head-to-head matrix.
  ab_eval.py list-cases [--corpus F]

Model defaults to 'sonnet' (fast/cheap for eval); the point is it is CONSTANT
across arms, not which one it is.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

CLAUDE = os.environ.get("CLAUDE_BIN") or "claude"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORPUS = os.path.join(HERE, "behavioral_corpus.json")
DEFAULT_TOOLS = "Read Edit Write Bash Grep Glob"


def parse_stream(stdout: str):
    """Parse claude -p stream-json: collect tool_use names, final step count, reply."""
    tools, steps, reply, usage = [], 0, "", None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t = ev.get("type")
        if t == "assistant":
            for b in (ev.get("message", {}).get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools.append(b.get("name", ""))
        elif t == "result":
            reply = ev.get("result") or reply
            steps = ev.get("num_turns", steps)
            usage = ev.get("usage")
    return tools, steps, reply, usage


def score(assert_, tools, steps, reply, cwd) -> dict:
    """Deterministic assertion evaluation. Returns {check_name: bool}."""
    checks = {}
    rl = (reply or "").lower()
    a = assert_
    if "max_steps" in a:
        checks["max_steps"] = steps <= a["max_steps"]
    if "tool_invoked" in a:
        checks["tool_invoked"] = all(t in tools for t in a["tool_invoked"])
    if "tool_not_invoked" in a:
        checks["tool_not_invoked"] = all(t not in tools for t in a["tool_not_invoked"])
    if "reply_contains" in a:
        checks["reply_contains"] = all(s.lower() in rl for s in a["reply_contains"])
    if "reply_contains_any" in a:
        checks["reply_contains_any"] = any(s.lower() in rl for s in a["reply_contains_any"])
    if "reply_not_contains" in a:
        checks["reply_not_contains"] = all(s.lower() not in rl for s in a["reply_not_contains"])
    if "file_exists" in a:
        checks["file_exists"] = all(os.path.exists(os.path.join(cwd, f)) for f in a["file_exists"])
    if "file_absent" in a:
        checks["file_absent"] = all(not os.path.exists(os.path.join(cwd, f)) for f in a["file_absent"])
    if "file_contains" in a:
        ok = True
        for f, sub in a["file_contains"].items():
            p = os.path.join(cwd, f)
            ok = ok and os.path.exists(p) and sub.lower() in open(p, errors="replace").read().lower()
        checks["file_contains"] = ok
    return checks


def run_case(case, config_text, model, timeout=180) -> dict:
    cwd = tempfile.mkdtemp(prefix="abeval_")
    try:
        for name, content in (case.get("setup", {}).get("files") or {}).items():
            with open(os.path.join(cwd, name), "w") as f:
                f.write(content)
        tools_arg = (case.get("allowed_tools") or DEFAULT_TOOLS).split()
        cmd = [CLAUDE, "-p", case["prompt"], "--model", model,
               "--output-format", "stream-json", "--verbose",
               "--dangerously-skip-permissions", "--add-dir", cwd]
        if config_text:
            cmd += ["--append-system-prompt", config_text]
        cmd += ["--allowed-tools"] + tools_arg  # variadic LAST so nothing else is consumed
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"id": case["id"], "axis": case.get("axis"), "passed": False,
                    "error": "timeout", "checks": {}, "steps": None, "tools": []}
        tools, steps, reply, usage = parse_stream(p.stdout)
        checks = score(case.get("assert", {}), tools, steps, reply, cwd)
        passed = bool(checks) and all(checks.values())
        return {"id": case["id"], "axis": case.get("axis"), "passed": passed,
                "checks": checks, "steps": steps, "tools": tools,
                "reply_excerpt": (reply or "")[:200],
                "stderr": (p.stderr or "")[:200] if not checks else ""}
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def _read_cfg(path):
    if not path:
        return ""
    with open(path) as f:
        return f.read().strip()


def run_corpus(corpus, config_text, model, case_filter, timeout):
    cases = [c for c in corpus["cases"] if not case_filter or c["id"] == case_filter]
    rows = [run_case(c, config_text, model, timeout) for c in cases]
    npass = sum(1 for r in rows if r["passed"])
    return {"mode": "single", "model": model, "n": len(rows), "passed": npass,
            "failed": len(rows) - npass, "rows": rows}


def run_ab(corpus, cfg_a, cfg_b, model, case_filter, timeout):
    cases = [c for c in corpus["cases"] if not case_filter or c["id"] == case_filter]
    matrix = {"both_pass": [], "a_only": [], "b_only": [], "both_fail": []}
    rows = []
    for c in cases:
        ra = run_case(c, cfg_a, model, timeout)
        rb = run_case(c, cfg_b, model, timeout)
        ap, bp = ra["passed"], rb["passed"]
        bucket = ("both_pass" if ap and bp else "a_only" if ap else
                  "b_only" if bp else "both_fail")
        matrix[bucket].append(c["id"])
        rows.append({"id": c["id"], "axis": c.get("axis"), "a_pass": ap, "b_pass": bp,
                     "bucket": bucket, "a_checks": ra["checks"], "b_checks": rb["checks"]})
    return {"mode": "ab", "model": model, "n": len(cases),
            "summary": {k: len(v) for k, v in matrix.items()}, "matrix": matrix, "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config-a", default=None, help="system-prompt addendum file for arm A (empty/omitted = baseline)")
    r.add_argument("--config-b", default=None, help="arm B file; if given, produce an A/B matrix")
    r.add_argument("--corpus", default=DEFAULT_CORPUS)
    r.add_argument("--model", default="sonnet")
    r.add_argument("--case", default=None, help="run only this case id")
    r.add_argument("--timeout", type=int, default=180)
    r.add_argument("--json", action="store_true")
    lc = sub.add_parser("list-cases")
    lc.add_argument("--corpus", default=DEFAULT_CORPUS)
    a = ap.parse_args()

    corpus = json.load(open(a.corpus))

    if a.cmd == "list-cases":
        for c in corpus["cases"]:
            print(f"{c['id']:32} [{c.get('axis','')}]  {c['prompt'][:60]}")
        return 0

    cfg_a = _read_cfg(a.config_a)
    if a.config_b is not None:
        cfg_b = _read_cfg(a.config_b)
        out = run_ab(corpus, cfg_a, cfg_b, a.model, a.case, a.timeout)
    else:
        out = run_corpus(corpus, cfg_a, a.model, a.case, a.timeout)

    if a.json:
        print(json.dumps(out, indent=2))
    else:
        _render(out)
    return 0


def _render(out):
    if out["mode"] == "single":
        print(f"\nbehavioral corpus: {out['passed']}/{out['n']} passed  (model={out['model']})\n")
        for r in out["rows"]:
            mark = "PASS" if r["passed"] else "FAIL"
            fails = [k for k, v in (r["checks"] or {}).items() if not v] or ([r.get("error")] if r.get("error") else [])
            print(f"  [{mark}] {r['id']:30} steps={r['steps']} {'' if r['passed'] else 'x:' + ','.join(str(f) for f in fails)}")
    else:
        s = out["summary"]
        print(f"\nA/B head-to-head ({out['n']} cases, model={out['model']}):")
        print(f"  both pass : {s['both_pass']}")
        print(f"  A only    : {s['a_only']}   {out['matrix']['a_only']}")
        print(f"  B only    : {s['b_only']}   {out['matrix']['b_only']}")
        print(f"  both fail : {s['both_fail']}   {out['matrix']['both_fail']}")
        delta = s["b_only"] - s["a_only"]
        print(f"  net B-vs-A : {'+' if delta >= 0 else ''}{delta}  (positive = B helped)\n")


if __name__ == "__main__":
    sys.exit(main())
