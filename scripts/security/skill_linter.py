# skill_linter.py — static security scan of skill markdown files before they are trusted/registered.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Local pre-deploy skill linter. Static security scan of skill markdown files.

Design pattern: scan a third-party / newly-generated "skill" before it is registered,
score it, and emit a pass/warn/fail verdict with findings grouped by severity. Skills here
are markdown workflow files (skills/*.md, skills-shared/*.md) that the model executes as
instructions. The risk surface is therefore both the SHELL it tells the model to run AND the
INSTRUCTIONS themselves (prompt-injection class).

Complements, does not replace:
  - check_standdown.py   : gates package installs / mcp-add / settings edits
  - audit_repo_hooks.py  : audits git hooks for the zip-hook attack vector
This one gates the skill corpus itself.

Verdict:
    PASS  (exit 0) : no high/critical findings, score >= 70
    WARN  (exit 1) : any high finding OR score in [50, 70)
    FAIL  (exit 2) : any critical finding OR score < 50
    usage (exit 64)

Score: starts at 100, subtract per-finding penalty (critical 40 / high 20 /
medium 8 / low 2), floored at 0. Informational; the verdict is severity-driven.

Usage:
    python3 skill_linter.py <file.md>           # detailed findings for one skill
    python3 skill_linter.py <dir>               # scan every *.md under dir
    python3 skill_linter.py --all               # scan skills/ + skills-shared/
    python3 skill_linter.py <target> --json     # machine-readable output

Suppression (precision escape hatch): a skill may acknowledge a known-safe match
in its frontmatter, eslint-disable style:
    linter_ack: ["curl-pipe-bash: documents the anti-pattern, not executing it"]
Each ack entry starts with "<rule-id>:" and suppresses that rule for that file.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
SKILL_DIRS = [ROOT / "skills", ROOT / "skills-shared"]
MANIFEST = ROOT / "memory" / "state" / "skill-lint-manifest.json"

PENALTY = {"critical": 40, "high": 20, "medium": 8, "low": 2}

# Each rule: (id, severity, regex, description, anchored)
#   anchored=True  -> the token only counts when joined to a command/IO verb on the
#                     same line (cuts prose false positives like "never expose .env").
#   anchored=False -> match anywhere (dangerous in prose too, e.g. prompt injection).
VERB = r"(?:cat|less|head|tail|read|cp|scp|mv|curl|wget|source|echo|printf|export|tar|zip|base64|xxd|grep|awk|sed)"

RULES = [
    # ---- CRITICAL ----
    ("curl-pipe-bash", "critical",
     r"(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh|python3?)\b",
     "curl|bash style remote-exec install (security-first hard ban)", False),
    ("auto-send-email", "critical",
     r"\b(?:gmail_send|sendmail|smtplib|/usr/sbin/sendmail|msmtp)\b|smtp\.send_message",
     "outbound email send (draft-only policy; auto-send is blocked)", False),
    ("prompt-injection-selfapprove", "critical",
     r"(?:ignore (?:all |the )?previous instructions|disregard (?:the |all )?(?:above|prior)|"
     r"approve (?:the )?(?:pending )?pairing|add (?:me|them) to the allowlist|"
     r"disable the (?:gate|guard|standdown|security)|skip the (?:standdown|security) check|"
     r"bypass the confirm gate)",
     "prompt-injection / self-approval phrasing inside skill instructions", False),
    ("destructive-root", "critical",
     r"\brm\s+-rf\s+(?:/|~|\$HOME|/\*)\s*(?:$|\s)|\bmkfs\b|\bdd\s+[^\n]*of=/dev/|:\(\)\s*\{\s*:\|:",
     "filesystem-destroying command (rm -rf /, mkfs, dd to device, fork bomb)", False),

    # ---- HIGH ----
    ("secret-file-access", "high",
     rf"{VERB}\b[^\n]*(?:\.env\b|\.ssh/|id_rsa|id_ed25519|\.pem\b|wallet|credentials\.json|\.aws/cred|private[_-]?key)",
     "command reads/moves a secret or credential file", True),
    ("skip-permissions", "high",
     r"--dangerously-skip-permissions",
     "permission-bypass flag (acceptable only in known callsites; review)", False),
    ("privilege-escalation", "high",
     r"(?:^|\s|`)(?:sudo|su)\s+\S|\bchmod\s+(?:-R\s+)?0?777\b|\bchattr\s+[+-]i",
     "privilege escalation or world-writable / immutable chmod", False),
    ("network-exfil", "high",
     r"(?:curl|wget)\b[^\n]*(?:-X\s*POST|--data|-d\s|-F\s|--upload-file)\b",
     "outbound POST/upload to a network endpoint (possible exfil)", False),
    ("settings-allowlist-edit", "high",
     r"settings\.json[^\n]*(?:allow|deny|permissions)|(?:allow|deny)[^\n]*settings\.json",
     "edits the harness settings.json allow/deny list", False),
    ("dynamic-exec", "high",
     r"\b(?:eval|exec)\s*\(|python3?\s+-c\s+[\"']|\bnode\s+-e\b",
     "evaluates dynamic/fetched code", False),

    # ---- MEDIUM ----
    ("pkg-install", "medium",
     r"\b(?:npm|pnpm|yarn|bun)\s+(?:install|add|i)\b|\b(?:pip3?|pipx)\s+install\b|\bcargo\s+install\b|\bgo\s+install\b",
     "package install (must pass check_standdown.py first)", False),
    ("hardcoded-secret", "medium",
     r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{20,}\.)",
     "literal that looks like an API key / token / JWT", False),
    ("destructive-fs", "medium",
     r"\brm\s+-rf\s+(?!/|~|\$HOME|/\*)\S|\btruncate\b|\bshred\b",
     "destructive filesystem op on a non-root path", False),
    ("secret-file-ref", "medium",
     r"(?<![A-Za-z0-9_./-])(?:\.env|id_rsa|wallet\.dat|credentials\.json|\.aws/credentials)(?![A-Za-z0-9_])",
     "references a secret/credential file (prose; verify intent)", False),

    # ---- LOW (hygiene, not security) ----
    ("placeholder-token", "low",
     r"\{\{[A-Z0-9_]+\}\}|<INSERT|TODO:|FIXME:|XXX:",
     "unfilled placeholder / TODO left in skill", False),
]

# Negation/guard context: a line that PROHIBITS or guards against a command pattern
# (a security/ops skill documenting "never curl|bash" or "refuse on .env") is not a
# threat. Suppress command-class rules when such context is on the same line. NOT
# applied to prompt-injection or hardcoded-secret: a malicious injection may itself
# contain "do not tell the user", and a real key is a key regardless of surrounding
# prose. Blunt heuristic by design; the linter_ack escape hatch is the precise tool.
NEG_SUPPRESSIBLE = {
    "curl-pipe-bash", "auto-send-email", "secret-file-access", "secret-file-ref",
    "privilege-escalation", "network-exfil", "destructive-root", "destructive-fs",
    "pkg-install", "settings-allowlist-edit", "skip-permissions", "dynamic-exec",
}
NEG_CTX = re.compile(
    r"\b(?:no|not|never|don'?t|do not|avoid|refuses?|refused|reject|forbid(?:den)?|"
    r"disallow|prohibit(?:ed)?|without|gitignored?|forbidden)\b", re.I)


def parse_frontmatter_acks(text: str) -> set:
    """Pull rule-ids the skill has acknowledged as known-safe in its frontmatter."""
    acks = set()
    m = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return acks
    fm = m.group(1)
    am = re.search(r"linter_ack:\s*\[(.*?)\]", fm, re.S)
    if not am:
        return acks
    for item in re.findall(r"[\"']([^\"']+)[\"']", am.group(1)):
        rule_id = item.split(":", 1)[0].strip()
        if rule_id:
            acks.add(rule_id)
    return acks


def lint_file(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"file": str(path), "error": str(e), "verdict": "error", "score": 0, "findings": []}

    acks = parse_frontmatter_acks(text)
    lines = text.splitlines()
    findings = []
    for rid, sev, pat, desc, anchored in RULES:
        if rid in acks:
            continue
        rx = re.compile(pat, re.I)
        suppressible = rid in NEG_SUPPRESSIBLE
        for i, line in enumerate(lines, 1):
            mm = rx.search(line)
            if not mm:
                continue
            if suppressible and NEG_CTX.search(line):
                continue  # prohibition / guard phrasing, not a live command
            snippet = line.strip()
            findings.append({
                "rule": rid, "severity": sev, "line": i,
                "match": snippet[:120], "description": desc,
            })

    score = 100
    for f in findings:
        score -= PENALTY[f["severity"]]
    score = max(0, score)

    has_crit = any(f["severity"] == "critical" for f in findings)
    has_high = any(f["severity"] == "high" for f in findings)
    if has_crit or score < 50:
        verdict = "fail"
    elif has_high or score < 70:
        verdict = "warn"
    else:
        verdict = "pass"

    return {"file": str(path.relative_to(ROOT)) if str(path).startswith(str(ROOT)) else str(path),
            "verdict": verdict, "score": score,
            "acks": sorted(acks), "findings": findings}


def collect_targets(arg: str) -> list:
    if arg == "--all":
        out = []
        for d in SKILL_DIRS:
            out += sorted(d.glob("*.md"))
        return out
    p = Path(arg)
    if p.is_dir():
        return sorted(p.glob("*.md"))
    if p.is_file():
        return [p]
    return []


def verdict_exit(worst: str) -> int:
    return {"fail": 2, "warn": 1, "pass": 0, "error": 2}.get(worst, 0)


def worst_of(verdicts: list) -> str:
    for v in ("fail", "error", "warn", "pass"):
        if v in verdicts:
            return v
    return "pass"


def sha256_text(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return ""


def delta_scan(as_json: bool) -> int:
    """Lint ONLY skills new-or-changed since the last manifest (content hash).
    First run seeds the manifest silently (the existing corpus is the trusted
    baseline, never alarm on it). Thereafter: exit 2 if any new/changed skill is
    warn/fail (so the cron wrapper can alert), else exit 0. The manifest stores
    {path: {sha256, verdict}} at MANIFEST so a flagged-but-unchanged skill does not
    re-alert until its content changes again."""
    try:
        manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    except Exception:
        manifest = {}
    prev = manifest.get("skills", {})
    first_run = not prev

    current = []
    for d in SKILL_DIRS:
        current += sorted(d.glob("*.md"))
    cur_hash = {str(p.relative_to(ROOT)): sha256_text(p) for p in current}

    changed = [p for p in current
               if prev.get(str(p.relative_to(ROOT)), {}).get("sha256") != cur_hash[str(p.relative_to(ROOT))]]

    lint_results = {}
    for p in changed:
        r = lint_file(p)
        lint_results[r["file"]] = r

    new_skills = {}
    for p in current:
        rel = str(p.relative_to(ROOT))
        verdict = lint_results[rel]["verdict"] if rel in lint_results else prev.get(rel, {}).get("verdict", "pass")
        new_skills[rel] = {"sha256": cur_hash[rel], "verdict": verdict}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({"version": 1, "skills": new_skills}, ensure_ascii=False))

    flagged = [r for r in lint_results.values() if r["verdict"] in ("warn", "fail", "error")]
    if as_json:
        print(json.dumps({"mode": "delta", "first_run": first_run, "scanned": len(changed),
                          "flagged": len(flagged), "flagged_files": flagged,
                          "changed_files": list(lint_results.keys())}, ensure_ascii=False))
    elif first_run:
        print(f"skill-lint delta: seeded manifest with {len(current)} skills (first run, no alerts).")
    elif not changed:
        print("skill-lint delta: no new or changed skills.")
    else:
        print(f"skill-lint delta: {len(changed)} new/changed, {len(flagged)} flagged.")
        for r in flagged:
            print(f"[{r['verdict'].upper()}] score {r['score']}  {r['file']}")
            for f in sorted(r["findings"], key=lambda f: {'critical':0,'high':1,'medium':2,'low':3}[f['severity']]):
                print(f"        {f['severity']:<8} L{f['line']:<4} {f['rule']}: {f['match']}")

    return 0 if first_run else (2 if flagged else 0)


def main() -> int:
    args = [a for a in sys.argv[1:]]
    if not args:
        print("usage: skill_linter.py <file|dir|--all|--delta> [--json]", file=sys.stderr)
        return 64
    as_json = "--json" in args
    if "--delta" in args:
        return delta_scan(as_json)
    targets_arg = next((a for a in args if a != "--json"), "--all")

    targets = collect_targets(targets_arg)
    if not targets:
        print(f"no skill files for target: {targets_arg}", file=sys.stderr)
        return 64

    results = [lint_file(t) for t in targets]
    worst = worst_of([r["verdict"] for r in results])

    if as_json:
        print(json.dumps({"target": targets_arg, "worst_verdict": worst,
                          "scanned": len(results), "results": results}, ensure_ascii=False))
        return verdict_exit(worst)

    # Human report
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    flagged = [r for r in results if r["verdict"] in ("warn", "fail", "error")]
    icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "error": "ERR "}

    if len(targets) > 1:
        n_pass = sum(1 for r in results if r["verdict"] == "pass")
        print(f"skill-lint: {len(results)} scanned | "
              f"{n_pass} pass / {sum(1 for r in results if r['verdict']=='warn')} warn / "
              f"{sum(1 for r in results if r['verdict']=='fail')} fail")
        print("-" * 72)
    for r in sorted(flagged, key=lambda r: (verdict_exit(r["verdict"]) * -1, -r.get("score", 0))):
        print(f"[{icon[r['verdict']]}] score {r['score']:>3}  {r['file']}")
        for f in sorted(r["findings"], key=lambda f: sev_rank[f["severity"]]):
            print(f"        {f['severity']:<8} L{f['line']:<4} {f['rule']}: {f['match']}")
    if len(targets) == 1 and not flagged:
        print(f"[PASS] score {results[0]['score']}  {results[0]['file']} — clean")
    if len(targets) > 1 and not flagged:
        print("all clean.")
    return verdict_exit(worst)


if __name__ == "__main__":
    sys.exit(main())
