#!/usr/bin/env python3
# md_to_pdf.py: markdown to PDF via pandoc + weasyprint, with a stale-output guard.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
Convert a markdown file to a styled PDF via pandoc + weasyprint.

Uses pandoc (md → html) then weasyprint (html → pdf) under the hood.
Chain: `pandoc input.md --pdf-engine=weasyprint -o output.pdf`

Useful for: briefings, proposals, board docs, research summaries.

Usage:
    md_to_pdf.py input.md [--out output.pdf] [--css style.css]
                          [--title "Doc Title"] [--margin 20mm]

Stale-output guard: the output file is deleted before
rendering, and the run exits 1 if afterwards it is missing, empty, or not newer than the
start time. A failed render can no longer leave last version's PDF in place looking fresh.
Lines that are only a `[[VISUAL: ...]]` placeholder are removed before rendering (they used
to print as text). The markdown goes to pandoc on stdin, so `pagetitle` is set to the input
file's stem unless --title is given.
"""
from __future__ import annotations
import argparse
import math
import re
import subprocess
import sys
import time
from pathlib import Path

VISUAL_LINE = re.compile(r"^[ \t]*\[\[VISUAL:[^\]]*\]\][ \t]*$", re.MULTILINE)


def strip_visual_markers(md: str) -> str:
    """Drop lines that hold only a [[VISUAL: ...]] placeholder."""
    return VISUAL_LINE.sub("", md)


def output_problem(out_path: Path, start: float) -> str:
    """'' when out_path is a fresh, non-empty file written after `start`, else why not."""
    if not out_path.is_file():
        return f"output missing after render: {out_path}"
    st = out_path.stat()
    if st.st_size == 0:
        return f"output is empty: {out_path}"
    if st.st_mtime < math.floor(start):
        return f"output not newer than the start of this run: {out_path}"
    return ""


def convert(md_path: Path, out_path: Path, css: Path | None = None,
            title: str | None = None, margin: str = "20mm") -> int:
    # weasyprint supports CSS Paged Media. margins set via CSS @page
    # instead of engine flags. Write a tiny @page CSS to a temp file.
    import tempfile, os
    css_tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".css", delete=False, encoding="utf-8"
    )
    css_tmp.write(f"@page {{ margin: {margin}; }}\n"
                  "body { font-family: sans-serif; line-height: 1.45; }\n"
                  "code, pre { font-family: 'DejaVu Sans Mono', monospace; }\n"
                  "pre { background: #f4f4f4; padding: 8px; border-radius: 4px; "
                  "font-size: 0.85em; overflow-wrap: break-word; }\n"
                  "h1,h2,h3 { color: #222; }\n"
                  "table { border-collapse: collapse; width: 100%; }\n"
                  "th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }\n"
                  "th { background: #f0f0f0; }\n")
    css_tmp.close()

    md_text = strip_visual_markers(md_path.read_text(encoding="utf-8"))
    cmd = [
        "pandoc", "-f", "markdown",
        "--pdf-engine=weasyprint",
        "--css", css_tmp.name,
        "-o", str(out_path),
    ]
    if css:
        cmd.extend(["--css", str(css)])
    if title:
        cmd.extend(["--metadata", f"title={title}"])
    else:
        cmd.extend(["--metadata", f"pagetitle={md_path.stem}"])

    try:
        result = subprocess.run(cmd, input=md_text, capture_output=True, text=True)
    except FileNotFoundError:
        os.unlink(css_tmp.name)
        print("error: pandoc not found on PATH (install pandoc and weasyprint)", file=sys.stderr)
        return 1
    try:
        os.unlink(css_tmp.name)
    except OSError:
        pass
    if result.returncode != 0:
        print(f"pandoc failed:\n{result.stderr}", file=sys.stderr)
        return result.returncode
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Convert markdown to PDF")
    p.add_argument("md", type=Path, help="Input markdown file")
    p.add_argument("--out", type=Path, default=None,
                   help="Output PDF path (default: <input>.pdf)")
    p.add_argument("--css", type=Path, default=None,
                   help="Optional CSS stylesheet")
    p.add_argument("--title", default=None, help="Document title")
    p.add_argument("--margin", default="20mm", help="Page margin (default 20mm)")
    args = p.parse_args()

    if not args.md.is_file():
        print(f"error: file not found: {args.md}", file=sys.stderr)
        return 1

    out = args.out or args.md.with_suffix(".pdf")
    start = time.time()
    try:
        out.unlink(missing_ok=True)
    except OSError as e:
        print(f"error: cannot remove the old output before rendering: {e}", file=sys.stderr)
        return 1
    rc = convert(args.md, out, args.css, args.title, args.margin)
    problem = output_problem(out, start)
    if rc == 0 and problem:
        rc = 1
    if problem:
        print(f"error: {problem}", file=sys.stderr)
    if rc == 0:
        print(f"wrote {out}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
