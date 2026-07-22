#!/usr/bin/env python3
# audit_repo_hooks.py — scan .git/hooks/ for planted executables (zip-hook attack defense).
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Audit .git/hooks/* for non-.sample executable files.

Defends against the "Contagious Interview" zip-hook attack vector: a downloaded zip
can ship an executable .git/hooks/* file that git auto-fires on the next checkout or
commit. Standard `unzip` preserves the executable bit, so the payload runs silently.

Scans either a single repo path (passed as arg) or the default scan roots if no arg.
Flags any executable (u+x) file under .git/hooks/ that does NOT end in .sample. An
optional allowlist (sha256-pinned) suppresses known-good hooks and detects drift.

Usage:
    python3 audit_repo_hooks.py                   # scan default roots
    python3 audit_repo_hooks.py /path/to/repo     # scan one repo
    python3 audit_repo_hooks.py --quiet           # silent unless findings
    python3 audit_repo_hooks.py --tg              # send an alert on findings

Exit codes:
    0 = no findings (all clean; findings are still printed/logged when present)
    2 = invocation error (e.g. bad path)
    3 = drift detected (a known allowlisted hook was modified — elevated severity)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
LOG_PATH = ROOT / "logs" / "session.jsonl"
ALLOWLIST_PATH = ROOT / "memory" / "git-hooks-allowlist.json"
# Operator chat id for optional alerts. Empty by default; set OPERATOR_CHAT_ID to enable.
TG_CHAT_ID = os.environ.get("OPERATOR_CHAT_ID", "")
# Env file that may hold TG_BOT_TOKEN=... for the optional alert path.
AGENT_ENV_FILE = os.environ.get("AGENT_ENV_FILE", str(Path.home() / ".config" / "utopia-os" / ".env"))

# Default: scan the workspace root. Override with a colon-separated SCAN_ROOTS env
# (e.g. to sweep every repo under a projects directory).
DEFAULT_SCAN_ROOTS = [Path(p) for p in os.environ.get("SCAN_ROOTS", str(ROOT)).split(os.pathsep) if p]
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".cache"}


def log_event(level: str, event: str, **extra) -> None:
    """Append one-line JSONL to the session log."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "persona": "agent",
            "category": "audit-repo-hooks",
            "event": event,
            **extra,
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def find_git_hook_dirs(scan_root: Path) -> list[Path]:
    """Find all .git/hooks/ directories under a root, respecting SKIP_DIRS."""
    hits = []
    for dirpath, dirnames, filenames in os.walk(scan_root):
        # Prune
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        # Only care about .git/hooks
        if Path(dirpath).name == "hooks" and Path(dirpath).parent.name == ".git":
            hits.append(Path(dirpath))
            # Don't descend into .git
            dirnames[:] = []
    return hits


def load_allowlist() -> dict[str, str]:
    """Return {path: expected_sha256} from allowlist file. Empty dict on failure."""
    try:
        data = json.loads(ALLOWLIST_PATH.read_text())
        return {e["path"]: e["sha256"] for e in data.get("entries", []) if "path" in e and "sha256" in e}
    except Exception:
        return {}


def sha256_file(path: Path) -> str:
    """Compute hex sha256 of a file's contents."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def audit_hooks_dir(hooks_dir: Path, allowlist: dict[str, str]) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (findings, allowlisted_clean, drift) tuples.

    findings: non-allowlisted suspicious hooks (original behavior).
    allowlisted_clean: hooks in allowlist with matching sha256 — info only.
    drift: hooks in allowlist but sha256 MISMATCH — elevated severity.
    """
    findings: list[dict] = []
    allowlisted_clean: list[dict] = []
    drift: list[dict] = []
    if not hooks_dir.exists():
        return findings, allowlisted_clean, drift
    for entry in hooks_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.name.endswith(".sample"):
            continue
        try:
            st = entry.stat()
            if not (st.st_mode & stat.S_IXUSR):
                continue
            path_str = str(entry)
            info = {
                "path": path_str,
                "mode": oct(st.st_mode & 0o777),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            }
            expected_hash = allowlist.get(path_str)
            if expected_hash is not None:
                actual_hash = sha256_file(entry)
                info["sha256"] = actual_hash
                if actual_hash == expected_hash:
                    allowlisted_clean.append(info)
                else:
                    info["expected_sha256"] = expected_hash
                    drift.append(info)
            else:
                findings.append(info)
        except OSError:
            continue
    return findings, allowlisted_clean, drift


def send_tg_alert(findings_by_repo: dict[str, list[dict]]) -> None:
    """Best-effort Telegram alert. Fails silently if unconfigured."""
    try:
        total = sum(len(v) for v in findings_by_repo.values())
        lines = [f"🚨 audit-repo-hooks: {total} executable hooks found across {len(findings_by_repo)} repos"]
        for repo, items in findings_by_repo.items():
            lines.append(f"\n{repo}:")
            for item in items[:5]:
                lines.append(f"  - {Path(item['path']).name} ({item['mode']}, {item['size']}b)")
        text = "\n".join(lines)[:3500]
        # Read the bot token from AGENT_ENV_FILE (TG_BOT_TOKEN=...). Log-only if absent.
        token_path = Path(AGENT_ENV_FILE)
        if token_path.exists() and TG_CHAT_ID:
            token = ""
            for line in token_path.read_text().splitlines():
                if line.startswith("TG_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
            if token:
                subprocess.run([
                    "curl", "-s", "-X", "POST",
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    "-d", f"chat_id={TG_CHAT_ID}",
                    "--data-urlencode", f"text={text}",
                ], capture_output=True, timeout=10)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="Specific repo or dir to scan (defaults to scan roots)")
    ap.add_argument("--quiet", action="store_true", help="Suppress stdout unless findings")
    ap.add_argument("--tg", action="store_true", help="Send an alert on findings")
    args = ap.parse_args()

    if args.path:
        scan_paths = [Path(args.path)]
        if not scan_paths[0].exists():
            print(f"error: path not found: {args.path}", file=sys.stderr)
            return 2
    else:
        scan_paths = DEFAULT_SCAN_ROOTS

    allowlist = load_allowlist()
    findings_by_repo: dict[str, list[dict]] = {}
    drift_by_repo: dict[str, list[dict]] = {}
    allowlisted_count = 0
    hooks_dirs_scanned = 0

    for root in scan_paths:
        if not root.exists():
            continue
        for hooks_dir in find_git_hook_dirs(root):
            hooks_dirs_scanned += 1
            findings, allowlisted_clean, drift = audit_hooks_dir(hooks_dir, allowlist)
            allowlisted_count += len(allowlisted_clean)
            repo_path = str(hooks_dir.parent.parent)
            if findings:
                findings_by_repo[repo_path] = findings
            if drift:
                drift_by_repo[repo_path] = drift

    has_drift = bool(drift_by_repo)
    has_findings = bool(findings_by_repo)

    if has_drift:
        drift_total = sum(len(v) for v in drift_by_repo.values())
        print(f"🚨 DRIFT: {drift_total} allowlisted hook(s) modified — sha256 mismatch")
        for repo, items in drift_by_repo.items():
            print(f"\n{repo}:")
            for item in items:
                print(f"  {Path(item['path']).name}  expected_sha={item['expected_sha256'][:16]}...  actual_sha={item['sha256'][:16]}...  mtime={item['mtime']}")
        log_event("alert", "allowlist_drift", count=drift_total, repos=list(drift_by_repo.keys()), dirs_scanned=hooks_dirs_scanned, details=drift_by_repo)
        if args.tg:
            send_tg_alert(drift_by_repo)

    if has_findings:
        total = sum(len(v) for v in findings_by_repo.values())
        print(f"⚠️  FINDINGS: {total} suspicious hook executables across {len(findings_by_repo)} repos")
        for repo, items in findings_by_repo.items():
            print(f"\n{repo}:")
            for item in items:
                print(f"  {Path(item['path']).name}  mode={item['mode']}  size={item['size']}b  mtime={item['mtime']}")
        log_event("warn", "findings", count=total, repos=list(findings_by_repo.keys()), dirs_scanned=hooks_dirs_scanned, allowlisted_skipped=allowlisted_count)
        if args.tg:
            send_tg_alert(findings_by_repo)

    if not has_findings and not has_drift:
        if not args.quiet:
            print(f"✅ clean ({hooks_dirs_scanned} .git/hooks/ dirs scanned, {allowlisted_count} allowlisted hook(s) verified, 0 non-allowlisted executables)")
        log_event("info", "clean", dirs_scanned=hooks_dirs_scanned, allowlisted_count=allowlisted_count)

    # Exit code semantics:
    # exit 0 = script ran cleanly (findings printed to stdout + logged; not a runtime failure)
    # exit 2 = invocation error (bad path)
    # exit 3 = drift detected (elevated severity — a known hook was tampered with)
    if has_drift:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
