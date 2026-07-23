#!/usr/bin/env python3
# vendored_deps_check.py — flag manually-installed GitHub deps whose upstream has moved.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Vendored-dependency update checker.

We adopt tools from GitHub via MANUAL install (clone+build, release binary,
git-source global) OUTSIDE a package manager, so nothing tells us when upstream
ships an update. This reads scripts/security/vendored-deps.json, queries each repo's
latest release/tag via `gh api`, compares to our pinned `current`, and flags stale.

Security-aware by design: on a STALE flag it surfaces the new release's AGE (so the
7-day-repo gate is visible) and reminds you to run check_standdown.py <repo> BEFORE
updating. It NEVER updates anything; it only reports. Actual updates stay a human,
gated step (7-day age + standdown + read-the-diff).

managed_by=manual are the real targets; package-manager-managed deps self-update via
their own tooling and are shown for completeness.

Usage:
  vendored_deps_check.py            # human report
  vendored_deps_check.py --json     # machine output
  vendored_deps_check.py --stale    # exit 1 if any manual dep is stale (for cron alerting)
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MANIFEST = os.path.join(ROOT, "scripts/security/vendored-deps.json")


def gh(path):
    try:
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=25)
        return json.loads(r.stdout) if r.returncode == 0 else None
    except Exception:
        return None


def latest(repo, check):
    if check == "release":
        d = gh(f"repos/{repo}/releases/latest")
        if d and d.get("tag_name"):
            return d["tag_name"], d.get("published_at")
    d = gh(f"repos/{repo}/tags")   # fallback for repos with no GitHub releases
    if isinstance(d, list) and d:
        return d[0].get("name"), None
    return None, None


def semver(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


def age_days(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def evaluate():
    m = json.load(open(MANIFEST))
    rows = []
    for d in m["deps"]:
        repo, cur = d.get("repo"), d.get("current")
        if not repo:
            rows.append({**d, "status": "no-repo", "latest": None})
            continue
        lat, pub = latest(repo, d.get("check", "release"))
        if not lat:
            rows.append({**d, "status": "check-failed", "latest": None})
            continue
        stale = semver(lat) > semver(cur)
        rows.append({**d, "latest": lat, "status": "STALE" if stale else "current",
                     "latest_age_days": age_days(pub)})
    return rows


def main():
    rows = evaluate()
    stale = [r for r in rows if r["status"] == "STALE"]
    if "--json" in sys.argv:
        print(json.dumps(rows, indent=2))
    elif "--stale" in sys.argv:
        manual_stale = [r for r in stale if r.get("managed_by") == "manual"]
        print(json.dumps({"stale": [r["name"] for r in stale],
                          "manual_stale": [r["name"] for r in manual_stale]}))
        sys.exit(1 if manual_stale else 0)
    else:
        print(f"\nvendored deps: {len(rows)} tracked, {len(stale)} STALE\n")
        tags = {"STALE": "STALE", "current": " ok  ", "no-repo": "  ?  ", "check-failed": "fail "}
        for r in rows:
            base = f"  [{tags.get(r['status'], '?')}] {r['name']:12} {str(r.get('current','?')):10} [{r.get('managed_by','?')}]"
            if r["status"] == "STALE":
                age = r.get("latest_age_days")
                gate = "  <-- 7-DAY GATE: too new, wait" if (age is not None and age < 7) else ""
                base += f"  ->  {r['latest']}" + (f"  (upstream {age}d old){gate}" if age is not None else "")
            elif r["status"] == "no-repo":
                base += "  (fill repo in the manifest to enable)"
            print(base)
        if stale:
            print("\n  before updating any STALE dep: respect the 7-day age gate + `check_standdown.py <repo>` + read the diff. this tool never auto-updates.")
        print()


if __name__ == "__main__":
    main()
