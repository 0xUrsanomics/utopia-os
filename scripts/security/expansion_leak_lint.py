#!/usr/bin/env python3
# expansion_leak_lint.py: static check for a default-value expansion of a secret on an output line.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""expansion_leak_lint.py: static check for the shell idiom that prints a secret while looking
like a presence check.

(Named without the word "secret" because the repo .gitignore excludes any *secret* path.)

The trap: `${VAR:-default}` expands to the VALUE whenever VAR is set, so
`echo "tok=${VAR:+SET}${VAR:-UNSET}"` prints `SET<the secret>`. It looks safe in every rehearsal
where VAR is empty. Safe forms: `[ -n "$VAR" ] && echo SET || echo UNSET`, or `echo "${VAR:+SET}"`.

Rule: flag `${NAME:-x}`, `${NAME-x}`, `${NAME:=x}`, `${NAME=x}` when NAME looks like a secret
(an underscore-separated segment is TOKEN / SECRET / KEY / PASSWORD / PASSWD / PASSPHRASE /
APIKEY / CREDENTIAL(S), or a segment ends in TOKEN / SECRET / PASSWORD / APIKEY). Segment
matching keeps KEYWORD, MONKEY, TOKENIZER out.

Pattern names (the only thing printed besides file:line and the variable NAME; line text and
default values are NEVER printed, so a hard-coded secret cannot leak through this tool):
  secret-default-expansion-on-output-line  the expansion sits on an echo/printf/print/logger/tee
                                           or stderr line. This is the leak shape. Blocks commits.
  secret-default-expansion                 any other default expansion of a secret-named var.
                                           Often legitimate (passing the value to curl). Warn only.

Usage:
  expansion_leak_lint.py PATH [PATH ...]   scan files / dirs (recursive)
  expansion_leak_lint.py --staged          scan only ADDED lines of staged files (pre-commit)
Exit: 0 clean, 1 output-line hit found (or any hit with --strict), 2 nothing scanned or bad usage.
A run that scanned zero files exits 2, never 0.
"""
import argparse
import os
import re
import subprocess
import sys

EXPANSION = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?P<op>:?[-=])[^}]*\}")
SECRET_SEGMENTS = {"TOKEN", "SECRET", "KEY", "PASSWORD", "PASSWD", "PASSPHRASE", "APIKEY",
                   "CREDENTIAL", "CREDENTIALS"}
SECRET_SUFFIXES = ("TOKEN", "SECRET", "PASSWORD", "APIKEY")
OUTPUT_LINE = re.compile(r"\b(echo|printf|print|logger|tee)\b|>&2|\bcat\s*<<")
SCAN_EXT = {".sh", ".bash", ".zsh", ".py", ".md", ".yml", ".yaml", ".toml", ".service", ".env.example"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}

OUT_NAME = "secret-default-expansion-on-output-line"
GEN_NAME = "secret-default-expansion"


def is_secret_name(name):
    segs = [s for s in name.upper().split("_") if s]
    return any(s in SECRET_SEGMENTS or s.endswith(SECRET_SUFFIXES) for s in segs)


def scan_line(line):
    """Return list of (pattern_name, var_name) for one line."""
    found = []
    for m in EXPANSION.finditer(line):
        if is_secret_name(m.group("name")):
            found.append((OUT_NAME if OUTPUT_LINE.search(line) else GEN_NAME, m.group("name")))
    return found


def wanted(path):
    if os.path.basename(path).startswith(".env") and not path.endswith(".example"):
        return False  # never open real env files
    ext = os.path.splitext(path)[1]
    # splitext(".env.example") gives ".example", so multi-dot names match on the basename.
    if ext in SCAN_EXT or os.path.basename(path).endswith(".env.example"):
        return True
    if ext == "":
        try:
            with open(path, "rb") as fh:
                return fh.read(2) == b"#!"
        except OSError:
            return False
    return False


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in sorted(files):
                    fp = os.path.join(root, f)
                    if wanted(fp):
                        yield fp
        elif os.path.isfile(p) and wanted(p):
            yield p


def scan_paths(paths):
    hits, scanned = [], 0
    for fp in iter_files(paths):
        scanned += 1
        try:
            with open(fp, errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    for pat, name in scan_line(line):
                        hits.append((fp, i, pat, name))
        except OSError:
            continue
    return hits, scanned


def scan_staged():
    """Added lines only, so legacy hits elsewhere in a touched file do not block a commit."""
    names = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                           capture_output=True, text=True, check=True, timeout=20).stdout.split()
    files = [f for f in names if wanted(f)]
    hits = []
    for f in files:
        diff = subprocess.run(["git", "diff", "--cached", "-U0", "--", f],
                              capture_output=True, text=True, timeout=20).stdout
        lineno = 0
        for dl in diff.splitlines():
            h = re.match(r"@@ -\S+ \+(\d+)", dl)
            if h:
                lineno = int(h.group(1)) - 1
                continue
            if dl.startswith("+") and not dl.startswith("+++"):
                lineno += 1
                for pat, name in scan_line(dl[1:]):
                    hits.append((f, lineno, pat, name))
    return hits, len(files), len(names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 on ANY hit, not only output-line hits")
    a = ap.parse_args()
    if a.staged:
        hits, scanned, staged_total = scan_staged()
        if staged_total == 0:
            return 0  # nothing staged: the hook has no work, not a failed check
    elif a.paths:
        hits, scanned = scan_paths(a.paths)
    else:
        ap.print_usage(sys.stderr)
        return 2
    for fp, ln, pat, name in hits:
        print(f"{fp}:{ln}: {pat} (var {name})")
    n_out = sum(1 for h in hits if h[2] == OUT_NAME)
    print(f"expansion_leak_lint: scanned {scanned} file(s), {len(hits)} hit(s), "
          f"{n_out} on an output line", file=sys.stderr)
    if scanned == 0 and not a.staged:
        print("expansion_leak_lint: FAIL, zero files scanned", file=sys.stderr)
        return 2
    if n_out or (a.strict and hits):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
