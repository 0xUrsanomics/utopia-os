# cron_trace_gotcha_miner.py: cluster recurring tool errors in cron traces into a per-tool gotcha digest.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Cron trace gotcha miner. Read-only scan of daemon cron trace logs -> per-tool gotcha digest.

Port of one step from arXiv 2608.07169 (Agent Memory Distillation): the
"function-memory construction" step, minus the small-model premise. The paper builds a
compact memory of how tools fail so an agent stops re-learning the same gotcha. This does
the construction half only: it reads the per-run cron trace files the daemon writes for
claude_code cron sessions, clusters recurring tool-call ERRORS by
(tool x normalized-error-signature), and emits a ranked per-tool gotcha digest.

Explicitly NOT built: any reactive inject-on-error hook. That was deferred. Miner only.

Trace files (your scheduler daemon writes one pair per cron run) live in TRACE_DIR as:
    <schedule>-<UTCstamp>.out.log   (stdout of the cron claude_code session)
    <schedule>-<UTCstamp>.err.log   (stderr of the cron claude_code session)
On a missing or empty dir the miner exits cleanly with a "no traces yet" notice, and it is
fully testable against a synthetic dir via --trace-dir / AGENT_CRON_TRACE_DIR.

Read-only on traces + one digest file (outputs/raw/reports/cron-gotcha-digest.md) = AUTO-safe.

Usage:
    python3 cron_trace_gotcha_miner.py                       # default dir + default out
    python3 cron_trace_gotcha_miner.py --trace-dir /path     # override trace dir
    python3 cron_trace_gotcha_miner.py --out /path/x.md      # override digest path
    AGENT_CRON_TRACE_DIR=/path python3 cron_trace_gotcha_miner.py
"""

import argparse
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# --- Module constants (overridable for testability) ---------------------------
TRACE_DIR = Path(os.path.expanduser(
    os.environ.get("AGENT_CRON_TRACE_DIR", "~/.agent-daemon/cron-traces")
))
ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DEFAULT_OUT = Path(os.environ.get("AGENT_REPORT_DIR", str(ROOT / "outputs" / "raw" / "reports"))) / "cron-gotcha-digest.md"

# Max signatures shown per tool, and example-string display cap.
TOP_SIGS_PER_TOOL = 10
EXAMPLE_MAXLEN = 220

# --- Tool attribution ---------------------------------------------------------
# Builtin Claude Code tool names that can appear in trace text.
KNOWN_TOOLS = {
    "Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob",
    "Grep", "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite",
}
# mcp__server__tool or mcp__server tokens.
MCP_TOKEN_RE = re.compile(r"mcp__[a-zA-Z0-9]+(?:__[a-zA-Z0-9_]+)?")
# "<tool> failed" / "<tool> errored" / "error calling <tool>" style attributions.
TOOL_BLAME_RE = re.compile(
    r"(?:\b([A-Za-z_][A-Za-z0-9_]{2,})\b\s+(?:tool\s+)?(?:call\s+)?(?:failed|errored)"
    r"|error\s+(?:calling|from|in)\s+\b([A-Za-z_][A-Za-z0-9_]{2,})\b)",
    re.IGNORECASE,
)

# --- Error-line detection -----------------------------------------------------
# A line is a candidate tool-call error if it matches any of these.
ERROR_LINE_RE = re.compile(
    r"("
    r"\berror\b"
    r"|\bexception\b"
    r"|\btraceback\b"
    r"|\bfailed\b"
    r"|\bmcp\s+error\b"
    r"|InputValidationError"
    r"|permission\s+denied"
    r"|timed?\s*out"
    r"|non-?zero\s+exit"
    r"|exit(?:ed\s+with)?\s+code\s+[1-9]"
    r"|process\s+exited\s+with\s+code\s+[1-9]"
    r")",
    re.IGNORECASE,
)
# Lines that mention "error" but are not failures (suppress false positives).
BENIGN_RE = re.compile(
    r"\b(?:no|0|zero)\s+errors?\b|error[-_]?free|without\s+errors?|error\s*:\s*(?:none|null)",
    re.IGNORECASE,
)

# --- Signature normalization --------------------------------------------------
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HEX0X_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
LONGHEX_RE = re.compile(r"\b[0-9a-fA-F]{12,}\b")
ISO_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
CLOCK_RE = re.compile(r"\b\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\b")
WINPATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s\"']+")
UNIXPATH_RE = re.compile(r"(?:~|/)[A-Za-z0-9_.\-/]*/[A-Za-z0-9_.\-/]+")
LINE_RE = re.compile(r"\bline\s+\d+", re.IGNORECASE)
LINECOL_RE = re.compile(r":\d+:\d+\b")
NUM_RE = re.compile(r"\b\d+\b")
WS_RE = re.compile(r"\s+")


def normalize_signature(text: str) -> str:
    """Collapse a raw error line into a stable clustering key.

    Strips the volatile parts (paths, timestamps, hex/uuid ids, line numbers, bare
    integers) so two runs of the same underlying failure map to one signature.
    """
    s = text.strip()
    s = UUID_RE.sub("<UUID>", s)
    s = HEX0X_RE.sub("<HEX>", s)
    s = ISO_TS_RE.sub("<TS>", s)
    s = CLOCK_RE.sub("<TS>", s)
    s = WINPATH_RE.sub("<PATH>", s)
    s = UNIXPATH_RE.sub("<PATH>", s)
    s = LONGHEX_RE.sub("<ID>", s)
    s = LINE_RE.sub("line <N>", s)
    s = LINECOL_RE.sub(":<N>:<N>", s)
    s = NUM_RE.sub("<N>", s)
    s = WS_RE.sub(" ", s).strip().lower()
    return s


def parse_schedule(filename: str) -> str:
    """Recover the schedule name from `<schedule>-<UTCstamp>.out.log`.

    Schedule names can themselves contain hyphens, so we strip a trailing
    timestamp-shaped token rather than naive split-on-first-hyphen.
    """
    stem = filename
    for suf in (".out.log", ".err.log", ".log"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
            break
    # Trailing UTC stamp like -20260813T041500Z or -1723526100 (epoch) or -2026-08-13T04-15-00Z.
    m = re.search(
        r"-(?:\d{8}T\d{6}Z?|\d{4}-\d{2}-\d{2}[T_]\d{2}[-:]\d{2}[-:]\d{2}Z?|\d{10,13})$",
        stem,
    )
    if m:
        stem = stem[: m.start()]
    return stem or filename


def attribute_tool(line: str, last_tool: str) -> str:
    """Best-effort: which tool does this error belong to?"""
    m = MCP_TOKEN_RE.search(line)
    if m:
        return m.group(0)
    # An explicit known-tool token in the line beats the generic blame heuristic,
    # e.g. "Bash command failed" is Bash, not the word "command".
    for kt in KNOWN_TOOLS:
        if re.search(r"\b" + re.escape(kt) + r"\b", line):
            return kt
    m = TOOL_BLAME_RE.search(line)
    if m:
        cand = m.group(1) or m.group(2)
        if cand:
            for kt in KNOWN_TOOLS:
                if kt.lower() == cand.lower():
                    return kt
            return cand
    return last_tool or "unknown"


def scan_tool_mention(line: str) -> str:
    """Return a tool token if this line looks like a tool invocation/mention, else ''.

    Used to carry a 'last seen tool' forward so an error line on the next line can be
    attributed via context.
    """
    m = MCP_TOKEN_RE.search(line)
    if m:
        return m.group(0)
    for kt in KNOWN_TOOLS:
        if re.search(r"\b" + re.escape(kt) + r"\b", line):
            return kt
    return ""


def mine(trace_dir: Path):
    """Scan trace files, cluster errors. Returns (clusters, stats).

    clusters: {tool: {signature: {count, example, schedules(set), streams(set)}}}
    stats:    {"files", "error_lines", "signatures"}
    """
    clusters = defaultdict(lambda: defaultdict(
        lambda: {"count": 0, "example": "", "schedules": set(), "streams": set()}
    ))
    files = sorted(
        p for p in trace_dir.glob("*.log")
        if p.name.endswith(".out.log") or p.name.endswith(".err.log")
    )
    stats = {"files": len(files), "error_lines": 0, "signatures": 0}

    for path in files:
        schedule = parse_schedule(path.name)
        stream = "err" if path.name.endswith(".err.log") else "out"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        last_tool = ""
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            mention = scan_tool_mention(line)
            if mention:
                last_tool = mention
            if not ERROR_LINE_RE.search(line) or BENIGN_RE.search(line):
                continue
            stats["error_lines"] += 1
            tool = attribute_tool(line, last_tool)
            sig = normalize_signature(line)
            if not sig:
                continue
            slot = clusters[tool][sig]
            slot["count"] += 1
            slot["schedules"].add(schedule)
            slot["streams"].add(stream)
            if not slot["example"]:
                slot["example"] = line.strip()[:EXAMPLE_MAXLEN]

    stats["signatures"] = sum(len(sigs) for sigs in clusters.values())
    return clusters, stats


def render_digest(clusters, stats, trace_dir: Path) -> str:
    """Build the markdown digest, tools ranked by total error count desc."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = []
    lines.append("# Cron Trace Gotcha Digest")
    lines.append("")
    lines.append(f"- Generated: {now}")
    lines.append(f"- Trace dir: `{trace_dir}`")
    lines.append(f"- Files scanned: {stats['files']}")
    lines.append(f"- Error lines matched: {stats['error_lines']}")
    lines.append(f"- Distinct (tool x signature) clusters: {stats['signatures']}")
    lines.append("")
    lines.append("Source: read-only scan of daemon cron trace logs. Recurring tool-call "
                 "errors clustered by normalized signature and ranked by count.")
    lines.append("")

    if not clusters:
        lines.append("_No tool-call errors found in the scanned traces._")
        lines.append("")
        return "\n".join(lines)

    tool_totals = {
        tool: sum(s["count"] for s in sigs.values())
        for tool, sigs in clusters.items()
    }
    ranked_tools = sorted(tool_totals.items(), key=lambda kv: (-kv[1], kv[0]))

    for tool, total in ranked_tools:
        lines.append(f"## `{tool}`. {total} error hit(s)")
        lines.append("")
        sigs = clusters[tool]
        ranked_sigs = sorted(
            sigs.items(), key=lambda kv: (-kv[1]["count"], kv[0])
        )[:TOP_SIGS_PER_TOOL]
        for rank, (sig, slot) in enumerate(ranked_sigs, 1):
            scheds = ", ".join(sorted(slot["schedules"])) or "?"
            streams = "/".join(sorted(slot["streams"]))
            lines.append(f"{rank}. **x{slot['count']}**. signature: `{sig}`")
            lines.append(f"   - example: `{slot['example']}`")
            lines.append(f"   - seen in: {scheds} ({streams})")
        extra = len(sigs) - len(ranked_sigs)
        if extra > 0:
            lines.append(f"   - _(+{extra} more signature(s) for this tool)_")
        lines.append("")

    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only cron trace gotcha miner.")
    ap.add_argument("--trace-dir", default=None,
                    help="Override trace dir (else AGENT_CRON_TRACE_DIR or default).")
    ap.add_argument("--out", default=None,
                    help="Override digest output path.")
    ap.add_argument("--quiet", action="store_true", help="Suppress stdout summary.")
    args = ap.parse_args(argv)

    trace_dir = Path(os.path.expanduser(args.trace_dir)) if args.trace_dir else TRACE_DIR
    out_path = Path(os.path.expanduser(args.out)) if args.out else DEFAULT_OUT

    # Clean exit on missing / empty dir (daemon restart pending, dir not created yet).
    if not trace_dir.exists():
        if not args.quiet:
            print(f"[cron-gotcha-miner] no traces yet: {trace_dir} does not exist. "
                  "Nothing to mine.")
        return 0
    trace_files = [
        p for p in trace_dir.glob("*.log")
        if p.name.endswith(".out.log") or p.name.endswith(".err.log")
    ]
    if not trace_files:
        if not args.quiet:
            print(f"[cron-gotcha-miner] no traces yet: {trace_dir} is empty "
                  "(no *.out.log / *.err.log). Nothing to mine.")
        return 0

    clusters, stats = mine(trace_dir)
    digest = render_digest(clusters, stats, trace_dir)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(digest, encoding="utf-8")

    if not args.quiet:
        n_tools = len(clusters)
        print(f"[cron-gotcha-miner] scanned {stats['files']} file(s), "
              f"{stats['error_lines']} error line(s), "
              f"{stats['signatures']} cluster(s) across {n_tools} tool(s).")
        print(f"[cron-gotcha-miner] digest -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
