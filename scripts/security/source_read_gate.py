#!/usr/bin/env python3
# source_read_gate.py: PreToolUse gate, a draft with a data claim must record the primary source it read.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Fail-open SOURCE-READ gate (PreToolUse on Write/Edit).

MECHANICAL enforcement of read-the-primary-source-before-drafting. Banked as a prose lesson, this
rule gets skipped exactly when it matters: a draft written off a headline number instead of the
report behind it, killed in review once someone reads the actual breakdown. Prose lessons do not
gate anything; a check the agent must remember to consult is a wish. So this is a hook that BLOCKS
at draft time.

Rule: when a WRITE (or content-bearing EDIT) targets a DRAFT file and the written content contains
a draft body (a body heading, see DRAFT_BODY below), the content MUST carry a non-empty
`source_read::` line that contains EITHER a primary-source http(s) URL AND some extracted figures,
OR an explicit n/a justification for a pure-opinion piece with no data claim. Otherwise: exit 2 +
stderr reason -> the agent reads the source, records it, and re-writes.

Fail-open by design: ANY error (unreadable stdin, unexpected shape, exception) exits 0 (allow). A
gate bug must never brick file writes. Scoped tightly to draft paths, and only fires when the write
actually carries a draft body, so status-only edits and non-draft writes pass.

Env (both are Python regexes):
  SOURCE_READ_GATE_PATHS  which file paths are drafts
                          default: outputs/raw/<any>/drafts/<file>.md or outputs/raw/<any>/runs/<any>/draft*.md
  SOURCE_READ_GATE_BODY   what marks a draft body in the content
                          default: a markdown heading "T1", "Draft" or "Body" (levels 1 to 3)
Self-test: source_read_gate.py --selftest
"""
import json
import os
import re
import sys

DRAFT_PATH_RX = re.compile(os.environ.get(
    "SOURCE_READ_GATE_PATHS",
    r"outputs/raw/(?:[^/]+/)*(?:drafts/[^/]+\.md$|runs/.+/draft[^/]*\.md$)"))
DRAFT_BODY_RX = re.compile(os.environ.get(
    "SOURCE_READ_GATE_BODY", r"^\s{0,3}#{1,3}\s*(?:T1|Draft|Body)\b"), re.MULTILINE)
URL_RX = re.compile(r"https?://\S{4,}")
SOURCE_LINE_RX = re.compile(r"^\s*source_read\s*::?\s*(.+)$", re.IGNORECASE | re.MULTILINE)
NA_RX = re.compile(r"\b(n/?a|no[- ]?data|no[- ]?source|opinion|pure[- ]?take|no[- ]?stat)\b", re.IGNORECASE)


def verdict(tool, ti):
    """None = allow, else the block reason. Pure, so the self-test can call it."""
    if tool not in ("Write", "Edit"):
        return None
    path = str(ti.get("file_path", ""))
    if not DRAFT_PATH_RX.search(path):
        return None  # not a draft file
    # Write carries full content; Edit carries new_string (a fragment).
    content = ti.get("content")
    if content is None:
        content = ti.get("new_string", "") or ""
    content = str(content)
    if not DRAFT_BODY_RX.search(content):
        return None  # no draft body in this write (status edit) -> allow
    for m in SOURCE_LINE_RX.finditer(content):
        val = (m.group(1) or "").strip()
        if NA_RX.search(val):
            return None
        if URL_RX.search(val) and len(val) >= 30:  # URL + some extracted figures
            return None
    return "missing-source-read"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail-open: unreadable payload never blocks
    try:
        if verdict(data.get("tool_name", ""), data.get("tool_input", {}) or {}):
            sys.stderr.write(
                "BLOCKED (source_read_gate): this draft has a body but no valid `source_read::` line.\n"
                "READ THE PRIMARY SOURCE FIRST, then add a frontmatter line:\n"
                "  source_read:: <primary-source URL> | <the key figures you actually read>\n"
                "For a pure-opinion piece with NO data claim, write:\n"
                "  source_read:: n/a (opinion, no data claim)\n"
                "This gate is mechanical, not a reminder: drafting off a headline number instead of the\n"
                "source behind it is the failure it exists to stop.\n"
            )
            sys.exit(2)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-open


def _selftest() -> int:
    p = "outputs/raw/social/drafts/2026-10-01-widget-prices.md"
    body = "---\ntitle: x\n---\n## T1\nWidget prices fell 12 percent.\n"
    cases = [
        ("Write", {"file_path": p, "content": body}, True),
        ("Write", {"file_path": p, "content": "source_read:: https://example.org/report | prices -12% y/y, n=400\n" + body}, False),
        ("Write", {"file_path": p, "content": "source_read:: n/a (opinion, no data claim)\n" + body}, False),
        ("Write", {"file_path": p, "content": "status: parked\n"}, False),           # no body
        ("Write", {"file_path": "notes/todo.md", "content": body}, False),          # not a draft path
        ("Edit", {"file_path": p, "new_string": body}, True),
        ("Read", {"file_path": p}, False),
    ]
    bad = 0
    for tool, ti, want in cases:
        got = verdict(tool, ti) is not None
        bad += got != want
        print(f" {'PASS' if got == want else 'FAIL'}  {tool:5} block={got}")
    print("selftest: PASS" if not bad else f"selftest: {bad} FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    main()
