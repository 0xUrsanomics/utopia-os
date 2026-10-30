#!/usr/bin/env python3
# instruction_stack_diff.py: what changed in the agent CLI's instruction stack between two versions.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""What changed in Claude Code's instruction stack (system prompt + tool definitions) between two versions.
Idea from arXiv 2610.37332 (instruction stacks change in bursts, mostly unexplained). Read-only, run by hand
after an upgrade. Output stays local: the stack includes CLAUDE.md and memory text, so never post it to a chat.

  python3 instruction_stack_diff.py                    -> last two versions seen
  python3 instruction_stack_diff.py --from 2.1.100 --to 2.1.101 [--days 30]

Per version it takes the main-thread request shape used most often (api-request rows, querySource
repl_main_thread) and its api-request-shape text. A shape change can come from Claude Code OR from your own
CLAUDE.md/MCP/settings; lines that look like yours are marked [ours?] so the two can be told apart.
Writes memory/state/instruction-stack/<from>__<to>.md and prints a short summary.

Env:
  AGENT_ROOT            repo root (default: two levels up)
  CC_PROJECT_DIR        transcript dir (default: ~/.claude/projects/<slug of AGENT_ROOT>)
  INSTR_OURS_PATTERN    extra regex alternatives that mark a line as yours (e.g. your agent's name)
"""
import argparse
import difflib
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
PROJ = Path(os.environ.get(
    "CC_PROJECT_DIR", str(Path.home() / ".claude/projects" / ("-" + str(REPO).replace("/", "-")))))
OUT = REPO / "memory/state/instruction-stack"
_EXTRA = os.environ.get("INSTR_OURS_PATTERN", "").strip()
OURS = re.compile(r"(?i)" + re.escape(str(REPO)) + r"|memory/|CLAUDE\.md|mcp__(?!plugin_)"
                  + (("|" + _EXTRA) if _EXTRA else ""))
MAX_DIFF_LINES = 400


def vkey(v):
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"[.-]", v))


def scan(days):
    cutoff = time.time() - days * 86400
    use, shapes = Counter(), {}
    for f in PROJ.glob("*.jsonl"):
        if f.stat().st_mtime < cutoff:
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                if '"api-request' not in ln or '"api-request-blob"' in ln:
                    continue
                try:
                    d = json.loads(ln)
                except Exception:
                    continue
                if d.get("type") == "api-request-shape":
                    shapes.setdefault(d["shapeHash"], (d.get("version"), d.get("shape", "")))
                elif d.get("type") == "api-request" and d.get("querySource") == "repl_main_thread":
                    use[(d.get("version"), d.get("shapeHash"))] += 1
    main = {}
    for (ver, h), n in use.most_common():
        if ver and h in shapes and ver not in main:
            main[ver] = (h, n)
    return main, shapes


def system_lines(shape):
    return "\n".join(b.get("text", "") for b in shape.get("system") or [] if isinstance(b, dict)).split("\n")


def tool_map(shape):
    return {t.get("name"): t for t in shape.get("tools") or [] if isinstance(t, dict) and t.get("name")}


def tool_text(t):
    return (t.get("description") or "").split("\n") + json.dumps(t.get("input_schema"), indent=1, sort_keys=True).split("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="a")
    ap.add_argument("--to", dest="b")
    ap.add_argument("--days", type=int, default=21)
    args = ap.parse_args()
    main_shapes, shapes = scan(args.days)
    vers = sorted(main_shapes, key=vkey)
    if len(vers) < 2 and not (args.a and args.b):
        print(f"FAIL: fewer than 2 versions with a main-thread shape in the last {args.days} days: {vers}")
        return 1
    a, b = args.a or vers[-2], args.b or vers[-1]
    for v in (a, b):
        if v not in main_shapes:
            print(f"FAIL: no main-thread shape for {v}; seen: {vers}")
            return 1
    (ha, na), (hb, nb) = main_shapes[a], main_shapes[b]
    sa, sb = shapes[ha][1], shapes[hb][1]
    ta, tb = tool_map(sa), tool_map(sb)
    diff = list(difflib.unified_diff(system_lines(sa), system_lines(sb), f"{a} system", f"{b} system", n=1, lineterm=""))
    for name in sorted(set(ta) & set(tb)):
        if ta[name] != tb[name]:
            diff += list(difflib.unified_diff(tool_text(ta[name]), tool_text(tb[name]), f"{a} tool {name}",
                                              f"{b} tool {name}", n=1, lineterm=""))
    changed = [d for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---"))]
    ours = sum(bool(OURS.search(d)) for d in changed)
    changed_tools = sorted(n for n in set(ta) & set(tb) if ta[n] != tb[n])
    rep = [f"# Instruction stack {a} -> {b} ({time.strftime('%Y-%m-%d %H:%M')})",
           f"- shape {a}: {ha[:12]} ({na} main-thread requests), {len(ta)} tools",
           f"- shape {b}: {hb[:12]} ({nb} main-thread requests), {len(tb)} tools",
           f"- tools added: {sorted(set(tb) - set(ta)) or 'none'}",
           f"- tools removed: {sorted(set(ta) - set(tb)) or 'none'}",
           f"- tools changed: {changed_tools or 'none'}",
           f"- changed lines: {len(changed)}, of which look like ours [ours?]: {ours}",
           "", "## Diff (system prompt, then changed tools; 1 line context)", "```"]
    for d in diff[:MAX_DIFF_LINES]:
        tag = " [ours?]" if d[:1] in "+-" and not d.startswith(("+++", "---")) and OURS.search(d) else ""
        rep.append(d[:400] + tag)
    if len(diff) > MAX_DIFF_LINES:
        rep.append(f"... {len(diff) - MAX_DIFF_LINES} more diff lines cut")
    rep.append("```")
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{a}__{b}.md"
    out.write_text("\n".join(rep) + "\n")
    print("\n".join(rep[:7]))
    print("written:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
