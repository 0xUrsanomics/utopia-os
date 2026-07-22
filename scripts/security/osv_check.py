#!/usr/bin/env python3
# osv_check.py — pre-install check of npm/PyPI packages against Google's OSV vulnerability DB.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""OSV malware/vulnerability check for npm/PyPI packages.

Concept ported from NousResearch/hermes-agent (MIT): auto-check `npx`/`uvx`
packages against the OSV malware DB before spawning MCP server processes.
Upstream: https://github.com/NousResearch/hermes-agent

OSV.dev is Google's free Open Source Vulnerabilities database. Public API at
https://api.osv.dev/v1/query. No auth, no rate-limits in normal use.

USAGE:
    # Direct check:
    osv_check.py npm @scope/some-mcp-server
    osv_check.py pypi some-pypi-package

    # Pre-flight wrapper for an npx command:
    osv_check.py --npx-cmd "npx -y @vendor/pkg-name --stdio"
    osv_check.py --uvx-cmd "uvx some-tool"

    # JSON output:
    osv_check.py --json npm @scope/some-mcp-server

EXIT CODES:
    0 = clean (no vulnerabilities or all below severity threshold)
    1 = vulnerabilities found (HIGH/CRITICAL by default)
    2 = network or API error (cannot verify, fail closed)
    3 = bad arguments
"""

import json
import re
import sys
import urllib.request
import urllib.error
from typing import Optional

OSV_API = "https://api.osv.dev/v1/query"
HIGH_OR_CRITICAL = ("HIGH", "CRITICAL")


def query_osv(name: str, ecosystem: str) -> Optional[dict]:
    """POST to OSV API. Returns response dict or None on error."""
    payload = json.dumps({
        "package": {"name": name, "ecosystem": ecosystem}
    }).encode("utf-8")
    req = urllib.request.Request(
        OSV_API,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"osv-check: HTTP error {e.code} from OSV", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"osv-check: network error: {e.reason}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, TimeoutError) as e:
        print(f"osv-check: parse/timeout error: {e}", file=sys.stderr)
        return None


def severity_of(vuln: dict) -> str:
    """Extract a single severity rating from a vuln record. Best-effort across formats."""
    # OSV severity field is a list of {type, score} entries
    severities = vuln.get("severity") or []
    for s in severities:
        score = s.get("score") or ""
        if "/CRITICAL" in score or "AV:N/AC:L" in score:
            return "CRITICAL"
        if "/HIGH" in score or "AV:N/AC:M" in score:
            return "HIGH"
    # Fallback: check database_specific.severity (GHSA format)
    db = vuln.get("database_specific") or {}
    if db.get("severity") in HIGH_OR_CRITICAL:
        return db["severity"]
    # If no clear severity rating, treat as MEDIUM (still concerning)
    return "MEDIUM"


def assess(name: str, ecosystem: str) -> dict:
    """Returns a structured verdict for the package."""
    result = query_osv(name, ecosystem)
    if result is None:
        return {
            "package": name,
            "ecosystem": ecosystem,
            "verdict": "ERROR",
            "vulns_high_or_critical": [],
            "vulns_total": 0,
            "message": "OSV query failed (network/api error): fail closed, do not install",
        }
    vulns = result.get("vulns") or []
    high = []
    for v in vulns:
        sev = severity_of(v)
        if sev in HIGH_OR_CRITICAL:
            high.append({
                "id": v.get("id"),
                "summary": (v.get("summary") or "")[:120],
                "severity": sev,
                "modified": v.get("modified"),
            })
    if high:
        return {
            "package": name,
            "ecosystem": ecosystem,
            "verdict": "BLOCK",
            "vulns_high_or_critical": high,
            "vulns_total": len(vulns),
            "message": f"{len(high)} HIGH/CRITICAL vulnerability(ies) found in OSV. do not install",
        }
    if vulns:
        return {
            "package": name,
            "ecosystem": ecosystem,
            "verdict": "REVIEW",
            "vulns_high_or_critical": [],
            "vulns_total": len(vulns),
            "message": f"{len(vulns)} non-critical vulnerability(ies) found. review before installing",
        }
    return {
        "package": name,
        "ecosystem": ecosystem,
        "verdict": "CLEAN",
        "vulns_high_or_critical": [],
        "vulns_total": 0,
        "message": "No known vulnerabilities in OSV",
    }


def parse_npx_cmd(cmd: str) -> Optional[str]:
    """Extract the package name from an npx command line.

    Examples:
        npx -y @scope/some-mcp-server --stdio  → @scope/some-mcp-server
        npx some-package                       → some-package
        npx --yes foo@1.2.3                    → foo
    """
    tokens = cmd.strip().split()
    if not tokens or tokens[0] != "npx":
        return None
    for t in tokens[1:]:
        if t.startswith("-"):
            continue
        # Strip version specifier if present
        if "@" in t and not t.startswith("@"):
            t = t.split("@", 1)[0]
        return t
    return None


def parse_uvx_cmd(cmd: str) -> Optional[str]:
    """Extract package name from a uvx (uv tool run) command."""
    tokens = cmd.strip().split()
    if not tokens or tokens[0] != "uvx":
        return None
    for t in tokens[1:]:
        if t.startswith("-"):
            continue
        if "==" in t:
            t = t.split("==", 1)[0]
        return t
    return None


def main():
    args = sys.argv[1:]
    json_mode = False
    if "--json" in args:
        json_mode = True
        args.remove("--json")

    if not args:
        print(__doc__, file=sys.stderr)
        sys.exit(3)

    if args[0] == "--npx-cmd":
        if len(args) < 2:
            print("osv-check: --npx-cmd requires a command string", file=sys.stderr)
            sys.exit(3)
        pkg = parse_npx_cmd(args[1])
        if not pkg:
            print(f"osv-check: could not parse npx package from: {args[1]}", file=sys.stderr)
            sys.exit(3)
        result = assess(pkg, "npm")
    elif args[0] == "--uvx-cmd":
        if len(args) < 2:
            print("osv-check: --uvx-cmd requires a command string", file=sys.stderr)
            sys.exit(3)
        pkg = parse_uvx_cmd(args[1])
        if not pkg:
            print(f"osv-check: could not parse uvx package from: {args[1]}", file=sys.stderr)
            sys.exit(3)
        result = assess(pkg, "PyPI")
    elif len(args) >= 2:
        ecosystem_arg = args[0].lower()
        ecosystem = {"npm": "npm", "pypi": "PyPI", "py": "PyPI"}.get(ecosystem_arg)
        if not ecosystem:
            print(f"osv-check: unknown ecosystem '{args[0]}' (expected: npm | pypi)", file=sys.stderr)
            sys.exit(3)
        result = assess(args[1], ecosystem)
    else:
        print("osv-check: missing package name", file=sys.stderr)
        sys.exit(3)

    if json_mode:
        print(json.dumps(result, indent=2))
    else:
        v = result["verdict"]
        emoji = {"CLEAN": "✅", "REVIEW": "⚠️", "BLOCK": "🚩", "ERROR": "❌"}.get(v, "?")
        print(f"{emoji} {v}. {result['package']} ({result['ecosystem']})")
        print(f"   {result['message']}")
        for h in result.get("vulns_high_or_critical", []):
            print(f"   - {h['id']} [{h['severity']}]: {h['summary']}")

    if result["verdict"] == "BLOCK":
        sys.exit(1)
    if result["verdict"] == "ERROR":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
