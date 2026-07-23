#!/usr/bin/env python3
"""Fleet root-policy drift verifier.

Reads memory/state/fleet-root-policy.json (the un-overridable fleet floor; seed it
from fleet-root-policy.example.json) and checks a tenant's settings.json against
it. REPORT-ONLY: never edits anything. Exit 1 if any violation (for cron alerting).
The real enforcement is the OS-tenant jail + account-level connector-disable; this
catches config DRIFT that weakens the floor.

Usage:
  fleet_policy_check.py                       # check the local settings.json
  fleet_policy_check.py --settings PATH       # check a specific tenant settings.json
  fleet_policy_check.py --settings PATH --external   # also apply external-tenant rules
  fleet_policy_check.py --json
"""
import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
POLICY = os.path.join(ROOT, "memory/state/fleet-root-policy.json")
LOCAL_SETTINGS = os.path.join(ROOT, ".claude/settings.json")

# allow-rule substrings that would breach a BLOCKED immutable rule
FORBIDDEN_ALLOW = ["gmail_send", "sendmail", "smtp", "curl |", "curl|", "wget |", "wget|"]


def load(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


def check(settings_path, external):
    s = load(settings_path)
    findings = []
    if s is None:
        return [{"rule": "settings_readable", "status": "VIOLATION",
                 "detail": f"cannot read {settings_path}"}]
    perms = s.get("permissions", {}) or {}
    allow = [str(x) for x in perms.get("allow", [])]
    deny = [str(x) for x in perms.get("deny", [])]

    bad = [a for a in allow if any(f in a.lower() for f in FORBIDDEN_ALLOW)]
    findings.append({"rule": "no_blocked_allows", "status": "VIOLATION" if bad else "PASS",
                     "detail": f"allow-rules breaching floor: {bad}" if bad else "no email/curl-pipe allows"})

    hooks = s.get("hooks", {}) or {}
    pre = json.dumps(hooks.get("PreToolUse", []))
    findings.append({"rule": "standdown_hook_wired",
                     "status": "PASS" if "standdown" in pre.lower() else "WARN",
                     "detail": "stand-down check in PreToolUse" if "standdown" in pre.lower()
                               else "stand-down hook not found here (may be enforced elsewhere)"})

    allhooks = json.dumps(hooks)
    findings.append({"rule": "no_skip_perms_in_hooks",
                     "status": "VIOLATION" if "skip-permissions" in allhooks else "PASS",
                     "detail": "skip-permissions found in a hook command" if "skip-permissions" in allhooks
                               else "clean"})

    if external:
        findings.append({"rule": "ext_disable_bundled_mcp",
                         "status": "PASS" if s.get("disableBundledMcpServers") is True else "VIOLATION",
                         "detail": f"disableBundledMcpServers={s.get('disableBundledMcpServers')}"})
        emj = s.get("enabledMcpjsonServers", None)
        findings.append({"rule": "ext_no_mcp_json_servers",
                         "status": "PASS" if emj == [] else "VIOLATION",
                         "detail": f"enabledMcpjsonServers={emj} (must be [])"})
        connectors_denied = any("connector" in d.lower() or "mcp__" in d for d in deny)
        findings.append({"rule": "ext_connectors_denied",
                         "status": "PASS" if connectors_denied else "WARN",
                         "detail": "remote connectors in deny" if connectors_denied
                                   else "connectors not explicitly denied here (verify account-level disable)"})
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", default=LOCAL_SETTINGS)
    ap.add_argument("--external", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    findings = check(a.settings, a.external)
    violations = [f for f in findings if f["status"] == "VIOLATION"]
    if a.json:
        print(json.dumps({"settings": a.settings, "violations": len(violations),
                          "findings": findings}, indent=2))
    else:
        print(f"\nfleet-policy check: {a.settings}")
        print(f"  (external-tenant rules: {'ON' if a.external else 'off'})\n")
        for f in findings:
            tag = {"PASS": " ok  ", "WARN": " warn", "VIOLATION": "VIOL "}.get(f["status"], "?")
            print(f"  [{tag}] {f['rule']:26} {f['detail']}")
        print(f"\n  {len(violations)} violation(s) of the fleet floor.\n"
              if violations else "\n  clean: satisfies the fleet floor.\n")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
