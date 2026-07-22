#!/usr/bin/env python3
# verify_subagent_diff.py — verify a subagent's claimed file changes against actual filesystem state.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
verify_subagent_diff.py — verify a subagent's claimed file changes against actual filesystem state.

Used by the parent (main session) AFTER a subagent returns its structured `subagent_return_v1` JSON.
Confirms claimed `files_changed` actually got modified within the dispatch window, and surfaces
unexpected modifications the child didn't report.

Usage:
    verify_subagent_diff.py \\
        --since "2026-05-04T05:00:00Z" \\
        --claimed file1.md file2.py file3.json \\
        [--scope skills scripts memory outputs]

Exit codes:
    0  = all claimed files verified, no unexpected mods in scope
    1  = mismatch found (claimed-but-not-modified OR unexpected modification)
    2  = invocation error (bad args, missing files, etc)

Output: JSON to stdout for programmatic parsing by the parent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DEFAULT_SCOPE = ["skills", "skills-shared", "scripts", "memory", "outputs/raw", "outputs/reviewed", "knowledge", "logs"]


def parse_ts(s: str) -> datetime:
    if not s:
        raise ValueError("--since is required, ISO 8601 format with Z suffix")
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def file_modified_since(path: Path, since_ts: float) -> tuple[bool, float | None]:
    if not path.exists():
        return False, None
    mtime = path.stat().st_mtime
    return mtime > since_ts, mtime


def scan_scope_for_modifications(scope_dirs: list[str], since_ts: float) -> list[Path]:
    """Find every file modified since timestamp within scope dirs."""
    modified: list[Path] = []
    for d in scope_dirs:
        scope_path = ROOT / d
        if not scope_path.exists():
            continue
        for p in scope_path.rglob("*"):
            if not p.is_file():
                continue
            # Skip caches, lockfiles, transient dirs
            parts = p.parts
            if any(skip in parts for skip in ("__pycache__", ".pytest_cache", ".cache", "node_modules", ".git")):
                continue
            try:
                if p.stat().st_mtime > since_ts:
                    modified.append(p)
            except OSError:
                continue
    return modified


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="Dispatch timestamp (ISO 8601 with Z)")
    ap.add_argument("--claimed", nargs="*", default=[], help="Paths the subagent claimed to modify (relative to project root or absolute)")
    ap.add_argument("--scope", nargs="*", default=DEFAULT_SCOPE, help=f"Directories to scan for unexpected modifications. Default: {DEFAULT_SCOPE}")
    ap.add_argument("--quiet", action="store_true", help="Suppress human-readable preamble; emit only JSON.")

    args = ap.parse_args()

    try:
        since_dt = parse_ts(args.since)
        since_ts = since_dt.timestamp()
    except Exception as e:
        print(json.dumps({"error": f"bad --since value: {e}"}))
        return 2

    # Resolve claimed paths to absolute
    claimed_paths: list[Path] = []
    for c in args.claimed:
        p = Path(c)
        if not p.is_absolute():
            p = ROOT / c
        claimed_paths.append(p)

    # Verify each claimed file
    verified: list[dict] = []
    missing_claimed: list[dict] = []
    for cp in claimed_paths:
        was_modified, mtime = file_modified_since(cp, since_ts)
        rel = str(cp.relative_to(ROOT)) if cp.is_relative_to(ROOT) else str(cp)
        if was_modified:
            verified.append({
                "path": rel,
                "mtime_iso": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "mtime_after_dispatch_seconds": round(mtime - since_ts, 1),
            })
        else:
            missing_claimed.append({
                "path": rel,
                "exists": cp.exists(),
                "mtime_iso": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat() if mtime else None,
                "reason": "not modified since dispatch" if cp.exists() else "file does not exist",
            })

    # Scan scope for unexpected modifications
    all_modified = scan_scope_for_modifications(args.scope, since_ts)
    claimed_set = {p.resolve() for p in claimed_paths if p.exists()}
    unexpected: list[dict] = []
    for m in all_modified:
        if m.resolve() not in claimed_set:
            rel = str(m.relative_to(ROOT))
            unexpected.append({
                "path": rel,
                "mtime_iso": datetime.fromtimestamp(m.stat().st_mtime, tz=timezone.utc).isoformat(),
            })

    verdict = "ok"
    if missing_claimed and unexpected:
        verdict = "both_mismatch"
    elif missing_claimed:
        verdict = "claimed_not_modified"
    elif unexpected:
        verdict = "unexpected_modifications"

    result = {
        "verdict": verdict,
        "since": args.since,
        "scope": args.scope,
        "verified": verified,
        "missing_claimed": missing_claimed,
        "unexpected": unexpected,
        "counts": {
            "verified": len(verified),
            "missing_claimed": len(missing_claimed),
            "unexpected": len(unexpected),
        },
    }

    if not args.quiet:
        print(f"# verify_subagent_diff.py — verdict: {verdict}", file=sys.stderr)
        print(f"# {len(verified)} verified, {len(missing_claimed)} missing-claimed, {len(unexpected)} unexpected", file=sys.stderr)

    print(json.dumps(result, indent=2))
    return 0 if verdict == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
