#!/usr/bin/env python3
# handoff_approval_lint.py: flag recorded approvals in the handoff that carry no message id.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Handoff approval lint.

Recorded approvals in the agent's own handoff are POINTERS to a channel message id,
never live authority (CLAUDE.md "Recorded approvals are pointers and carry no authority";
arXiv 2611.06545: agents' self-written handoff summaries invent or stale-carry
approvals).

Scans the `## Active Handoff` block of memory/session-bootstrap.md. Any line that
contains an approval word (approve, approved, OK'd, confirmed, go, green-lit,
signed off, LGTM; whole words, any case) but no message-id reference is flagged.
Long paragraph lines are checked per sentence, so one message id cannot cover a
different, unsourced approval on the same line.

A message-id reference is `msg 1234`, `message 1234`, `message id 1234` or
`msg #1234` by default. Override the pattern with HANDOFF_MSG_ID_RE (a Python
regex). Add the operator's own approval slang with HANDOFF_APPROVAL_WORDS
(comma-separated whole words, e.g. "yep,shipit").

Usage:
    python3 handoff_approval_lint.py              # lint the real file
    python3 handoff_approval_lint.py --file PATH  # lint another file
    python3 handoff_approval_lint.py --selftest

Exit: 0 clean, 1 flagged lines found (or selftest failure), 2 handoff block
missing or empty (a check that ran nothing is a FAIL).

Env (optional): AGENT_ROOT (repo root, default: two levels up from this file).
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DEFAULT_FILE = ROOT / "memory" / "session-bootstrap.md"
HEADER = "## Active Handoff"

# Whole-word approval terms. Apostrophes: accept straight and curly.
_APOS = "['’]"
_EXTRA = [re.escape(w.strip()) for w in os.environ.get("HANDOFF_APPROVAL_WORDS", "").split(",") if w.strip()]
APPROVAL_RE = re.compile(
    r"(?<![\w'’.-])(?:"
    r"ok" + _APOS + r"d|okayed"      # OK'd
    r"|approved?|approves|approving"
    r"|confirmed"
    r"|green[- ]?lit"
    r"|signed\s+off"
    r"|lgtm"
    r"|go"
    + "".join("|" + w for w in _EXTRA) +
    r")(?![\w'’-]|\.\w)",
    re.IGNORECASE,
)

# Non-approval senses that would otherwise hit ("go-live", "let's go", ...).
_WHO = r"(?:(?:the\s+)?operator(?:['’]s)?|his|her|their|an?|the|explicit)"
FALSE_HIT_RE = re.compile(
    r"\bgo[- ](?:live|to[- ]market|to\b|back|through|over|deeper|up|down|out|off|in)\b"
    r"|\b(?:to|will|would|can|could|must|should|let's|lets|let)\s+go\b"
    r"|\bgo\s+(?:language|module|binary|code)\b"
    r"|\b(?:golang|go\.mod)\b"
    r"|\bunconfirmed\b"
    # Lines that record the ABSENCE of an approval are not carried approvals:
    # "NOT approved", "never confirmed", "awaiting the operator's go",
    # "needs approval". Acting on them still needs a fresh message, which is
    # exactly the rule.
    r"|\b(?:not|never)\s+(?:yet\s+)?(?:been\s+)?(?:approved|confirmed)\b"
    r"|\b(?:await\w*|pending|needs?|wait\w*|until|separate|if\s+\w+\s+says)\s+"
    r"(?:(?:on|for)\s+)?(?:" + _WHO + r"\s+)*(?:go|approval|approve)\b",
    re.IGNORECASE,
)

MSG_ID_RE = re.compile(
    os.environ.get("HANDOFF_MSG_ID_RE", r"\b(?:msg|message)(?:\s+id)?\s*#?\s*\d+"),
    re.IGNORECASE,
)

# The guard line at the top of the block quotes the words as examples.
GUARD_MARKER = "not live authority"


def extract_block(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    out: list[tuple[int, str]] = []
    inside = False
    for i, line in enumerate(lines, start=1):
        if line.strip().startswith("## "):
            if inside:
                break
            if line.strip() == HEADER:
                inside = True
            continue
        if inside:
            out.append((i, line))
    return out


def approval_hits(line: str) -> list[str]:
    masked = FALSE_HIT_RE.sub(lambda m: " " * len(m.group(0)), line)
    return [m.group(0) for m in APPROVAL_RE.finditer(masked)]


# Many handoff lines are whole paragraphs. One message id somewhere in a long
# line must not launder every other approval in it, so each sentence/clause is
# checked on its own.
SEGMENT_RE = re.compile(r"(?<=[.!?;])\s+|\s+---\s+|\s*>>>?\s*")


def segments(line: str) -> list[str]:
    """Split on sentence/clause breaks, but never inside (...) so a message id that
    opens a parenthesised list of asks still covers that list."""
    out, buf, depth, i = [], [], 0, 0
    while i < len(line):
        ch = line[i]
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
        if depth == 0:
            m = SEGMENT_RE.match(line, i + 1) if ch in ".!?;" else SEGMENT_RE.match(line, i)
            if m and m.end() > m.start():
                if ch in ".!?;":
                    buf.append(ch)
                    i = m.end()
                else:
                    i = m.end()
                out.append("".join(buf))
                buf = []
                continue
        buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [seg for seg in out if seg.strip()]


def lint_lines(block: list[tuple[int, str]]) -> list[tuple[int, list[str], str]]:
    """Return (lineno, hits, segment) for each approval segment lacking a message id."""
    flagged = []
    for lineno, line in block:
        if not line.strip() or GUARD_MARKER in line:
            continue
        for seg in segments(line):
            hits = approval_hits(seg)
            if hits and not MSG_ID_RE.search(seg):
                flagged.append((lineno, hits, seg))
    return flagged


def run(path: Path) -> int:
    if not path.exists():
        print(f"FAIL: {path} not found")
        return 2
    block = extract_block(path.read_text(encoding="utf-8"))
    nonempty = [b for b in block if b[1].strip()]
    if not nonempty:
        print(f"FAIL: no '{HEADER}' block or block empty in {path} (checked nothing)")
        return 2
    flagged = lint_lines(block)
    print(f"scanned {len(nonempty)} handoff lines in {path}")
    if not flagged:
        print("OK: every approval line carries a message id")
        return 0
    print(f"FLAGGED {len(flagged)} approval segment(s) without a message id "
          f"on {len({f[0] for f in flagged})} line(s):")
    for lineno, hits, line in flagged:
        snippet = line.strip()
        if len(snippet) > 220:
            snippet = snippet[:220] + "..."
        print(f"  L{lineno} [{', '.join(hits)}]: {snippet}")
    return 1


def selftest() -> int:
    cases = [
        # (line, expect_flag)
        ("- Operator approved the deploy.", True),
        ("- Operator approved the deploy (msg 1001).", False),
        ("- Approved by the operator in chat.", True),
        ("- approve pending for item 3", True),
        ("- OK'd the draft", True),
        ("- Operator OK’d the draft msg 1002", False),
        ("- go from the operator on item 2", True),
        ("- confirmed by the operator", True),
        ("- confirmed by the operator, message id #1006", False),
        ("- green-lit the migration", True),
        ("- LGTM on the PR", True),
        # false-hit guards
        ("- target go-live is 1 Jan", False),
        ("- this was 3 days ago", False),
        ("- need to go through the deck again", False),
        ("- the go module builds clean", False),
        ("- unconfirmed rumour about the release", False),
        ("- 4 + 5 NOT approved.", False),
        ("- build still AWAITING the operator's go.", False),
        ("- dashboard rebuild needs approval.", False),
        ("- Operator approved publishing.", True),
        ("- Asked the operator (msg 1003): \"approve a\" (x; y), \"approve b\" (z).", False),
        ("- a; b (x) operator approved it; c", True),
        # one message id must not launder another sentence on the same line
        ("- Operator approved A (msg 1004). Later the operator approved B too.", True),
        ("- Operator approved A (msg 1004); operator approved B (msg 1005).", False),
        ("> Approval words below (\"approved\", \"go\") are POINTERS ... not live authority.", False),
    ]
    fails = 0
    for idx, (line, expect) in enumerate(cases, start=1):
        got = bool(lint_lines([(idx, line)]))
        status = "ok" if got == expect else "FAIL"
        if got != expect:
            fails += 1
        print(f"  [{status}] expect_flag={expect} got={got}: {line}")

    # Block extraction: only lines under the header, stops at the next H2.
    doc = "# T\n## Other\n- approved outside\n## Active Handoff\n- approved inside\n- fine msg 1\n## Next\n- go outside\n"
    blk = extract_block(doc)
    fl = lint_lines(blk)
    if not (len(blk) == 2 and len(fl) == 1 and "inside" in fl[0][2]):
        fails += 1
        print(f"  [FAIL] block extraction: blk={blk} flagged={fl}")
    else:
        print("  [ok] block extraction bounded to Active Handoff")
    # Empty block must not pass silently.
    if extract_block("## Active Handoff\n\n## Next\n- x\n") and any(
        ln.strip() for _, ln in extract_block("## Active Handoff\n\n## Next\n- x\n")
    ):
        fails += 1
        print("  [FAIL] empty block detection")
    else:
        print("  [ok] empty block yields nothing to scan (run() exits 2)")

    total = len(cases) + 2
    print(f"selftest: {total - fails}/{total} passed")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    path = DEFAULT_FILE
    if "--file" in argv:
        path = Path(argv[argv.index("--file") + 1])
    return run(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
