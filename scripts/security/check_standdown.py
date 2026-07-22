# check_standdown.py — stand-down registry checker: gates installs / mcp-adds / settings-edits.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Stand-down registry checker. Run before any install / mcp-add / settings-edit.

Returns:
    exit 0  : clear (no stand-down match) — proceed
    exit 1  : warn (warn-severity match) — needs explicit user re-confirmation
    exit 2  : block (block-severity match) — refuse to proceed
    exit 3  : expired (entry exists but expired) — surface as needs-review
    exit 64 : usage error

Usage:
    python3 check_standdown.py <target>            # exact-target check (package/repo/url)
    python3 check_standdown.py --pattern <cmd>     # pattern check (full command line)
    python3 check_standdown.py --bundle-scan <dir> # walk dir, flag files matching pattern entries with bundle_scan block
    python3 check_standdown.py --list              # list all entries

Exit codes are designed for shell-script piping. Stdout has a single JSON line with
{verdict, reason, entry_id, expires_at} on every run.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
REGISTRY = ROOT / "memory" / "standdowns.json"


def load_registry() -> dict:
    if not REGISTRY.exists():
        return {"entries": []}
    return json.loads(REGISTRY.read_text())


def is_expired(entry: dict) -> bool:
    exp = entry.get("expires_at")
    if not exp:
        return False
    try:
        expires = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires
    except Exception:
        return False


def find_match(target: str, kind_filter: str | None, registry: dict) -> dict | None:
    target_lower = target.lower()
    for entry in registry.get("entries", []):
        if kind_filter and entry.get("kind") != kind_filter:
            continue
        entry_target = (entry.get("target") or "").lower()
        if not entry_target:
            # Defensive: an empty target would match EVERY check (substring branch
            # does `"" in x` == True; pattern branch does `re.search("", x)` == match).
            # A malformed entry must match NOTHING, not everything. Surface it so the
            # registry gets fixed rather than silently crying wolf on all actions.
            print(f"warning: standdown entry {entry.get('id','?')!r} has no 'target'; skipped", file=sys.stderr)
            continue
        if entry.get("kind") == "pattern":
            try:
                if re.search(entry_target, target_lower):
                    return entry
            except re.error:
                continue
        else:
            if entry_target == target_lower or entry_target in target_lower:
                return entry
    return None


def emit(verdict: str, entry: dict | None = None, message: str = "") -> int:
    out = {
        "verdict": verdict,
        "reason": entry.get("reason") if entry else message,
        "entry_id": entry.get("id") if entry else None,
        "expires_at": entry.get("expires_at") if entry else None,
        "re_audit_triggers": entry.get("re_audit_triggers", []) if entry else [],
        "source_decision": entry.get("source_decision") if entry else None,
    }
    print(json.dumps(out, ensure_ascii=False))
    if verdict == "clear":
        return 0
    if verdict == "warn":
        return 1
    if verdict == "block":
        return 2
    if verdict == "expired":
        return 3
    return 64


def bundle_scan(bundle_dir: str, registry: dict) -> int:
    """Walk bundle_dir and check every file path against pattern entries that have bundle_scan block."""
    root = Path(bundle_dir).resolve()
    if not root.exists() or not root.is_dir():
        print(json.dumps({"verdict": "error", "reason": f"not a directory: {bundle_dir}"}))
        return 64

    scan_entries = [
        e for e in registry.get("entries", [])
        if e.get("kind") == "pattern" and e.get("bundle_scan")
    ]
    if not scan_entries:
        print(json.dumps({"verdict": "clear", "reason": "no bundle_scan-enabled entries in registry"}))
        return 0

    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        for fname in filenames:
            full = Path(dirpath) / fname
            rel = str(full.relative_to(root))
            rel_for_match = "/" + rel.replace(os.sep, "/").lower()
            for entry in scan_entries:
                if is_expired(entry):
                    continue
                pat = (entry.get("target") or "").lower()
                try:
                    if re.search(pat, rel_for_match):
                        findings.append({"file": rel, "entry_id": entry["id"], "severity": entry.get("severity", "warn")})
                except re.error:
                    continue

    if not findings:
        print(json.dumps({"verdict": "clear", "reason": f"bundle-scan: 0 matches in {bundle_dir}", "scanned": str(root)}))
        return 0

    # Aggregate severity: block beats warn
    has_block = any(f["severity"] == "block" for f in findings)
    verdict = "block" if has_block else "warn"
    out = {
        "verdict": verdict,
        "reason": f"bundle-scan: {len(findings)} matching file(s) require manual audit before import",
        "scanned": str(root),
        "findings": findings,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 2 if has_block else 1


def list_entries(registry: dict) -> int:
    print(f"{'id':<35} {'kind':<10} {'sev':<6} {'target':<40} expires")
    print("-" * 110)
    for e in registry.get("entries", []):
        exp = e.get("expires_at") or "permanent"
        print(f"{e['id']:<35} {e.get('kind',''):<10} {e.get('severity',''):<6} {e.get('target','')[:38]:<40} {exp}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_standdown.py <target> | --pattern <cmd> | --list", file=sys.stderr)
        return 64

    registry = load_registry()

    if sys.argv[1] == "--list":
        return list_entries(registry)

    if sys.argv[1] == "--bundle-scan":
        if len(sys.argv) < 3:
            print("usage: check_standdown.py --bundle-scan <dir>", file=sys.stderr)
            return 64
        return bundle_scan(sys.argv[2], registry)

    if sys.argv[1] == "--pattern":
        if len(sys.argv) < 3:
            return 64
        target = sys.argv[2]
        kind_filter = "pattern"
    else:
        target = sys.argv[1]
        kind_filter = None

    match = find_match(target, kind_filter, registry)
    if match is None:
        return emit("clear", message=f"no stand-down for {target}")

    if is_expired(match):
        return emit("expired", entry=match)

    return emit(match.get("severity", "warn"), entry=match)


if __name__ == "__main__":
    sys.exit(main())
