#!/usr/bin/env python3
# skill_disposition.py: walk the auto-skill candidate queue and propose keep/merge/reject.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Skill-candidate disposition advisor (ADVISORY ONLY, zero mutations).

Inspired by SkillProx (arXiv 2608.07449)
"backward-stage" discipline: instead of forward-generating more skills, walk the
EXISTING queue backward and decide what to keep. SkillProx assumes an accuracy
oracle to rank skills; our ops skills have NO ground truth, so this port drops the
oracle entirely and substitutes CHEAP PROXIES a human can sanity-check in seconds.

Targets a real recurring pain: the auto-skill-candidate queue at
    outputs/raw/skill-candidates/<slug>.md
written by a /save "skill crystallization" step. A nightly consolidation pass can
flag these, but if nobody actions them they rot. This surfaces a per-candidate
disposition so a human can clear the queue in one pass.

WHAT IT DOES (reads only):
  - file age from mtime (days)
  - last-dated signal from frontmatter (max YYYY-MM-DD across reviewed_at / status /
    parent_session / review_notes) and a created-ish min date
  - routing-hit signal: greps the candidate name against memory/Infra/routing.json +
    skills/_index.md + knowledge/skills-routing.md, when present (does anything route to it?)
  - merge signal: slug-token overlap against every installed skill name
    (skills/<name>/SKILL.md or skills/<name>.md, same for skills-shared/)
  - scripts/security/skill_linter.py verdict/score (subprocess, --json), if runnable
  - emits an ADVISORY disposition: KEEP / MERGE / REJECT (+ SKIP for malformed)

WHAT IT NEVER DOES:
  - never deletes, moves, edits, or rewrites ANY skill / candidate / steering file
  - never raises on a bad candidate (skips it gracefully)
  - the ONLY file it writes is its own report under $AGENT_REPORT_DIR
    (default outputs/raw/reports/)

Usage:
    python3 skill_disposition.py                 # scan queue, write + print report
    python3 skill_disposition.py --stdout-only   # print report, do not write a file
    python3 skill_disposition.py --json          # machine-readable rows to stdout
    python3 skill_disposition.py --queue <dir>   # override queue dir (default below)

Exit codes: 0 always on a clean run (including empty queue); 64 on usage error.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DEFAULT_QUEUE = ROOT / "outputs" / "raw" / "skill-candidates"
REPORT_DIR = Path(os.environ.get("AGENT_REPORT_DIR", str(ROOT / "outputs" / "raw" / "reports")))
LINTER = ROOT / "scripts" / "security" / "skill_linter.py"

# Files where a route TO a skill would live. Reading these is how we detect
# whether anything in the system actually points at the candidate.
ROUTING_SOURCES = [
    ROOT / "memory" / "Infra" / "routing.json",
    ROOT / "skills" / "_index.md",
    ROOT / "knowledge" / "skills-routing.md",
]

SKILL_DIRS = [ROOT / "skills", ROOT / "skills-shared"]

# Thresholds (surfaced in the report header so a human can recalibrate).
FRESH_DAYS = 14   # created within this window -> lean KEEP
STALE_DAYS = 30   # older than this + zero routing interest -> eligible for REJECT

# Generic tokens dropped before measuring slug overlap, so a shared "llm" or
# "skill" doesn't fake a merge match. Only DISTINCTIVE tokens count.
STOPWORDS = {
    "llm", "ai", "skill", "skills", "agent", "ops", "tool", "mode", "the", "a",
    "of", "to", "and", "for", "v1", "v2", "v3", "new", "auto", "gen", "engine",
}

DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def today() -> date:
    """Local date. Age is day-granular, so a few hours of TZ skew is immaterial."""
    return datetime.now().date()


def parse_frontmatter(text: str) -> dict:
    """Best-effort YAML-ish frontmatter parse (key: value, first block only).

    Deliberately not a full YAML parser: candidates are flat key/value blocks and
    we only need string scalars. Returns {} if no frontmatter fence is present.
    """
    fm = {}
    if not text.startswith("---"):
        return fm
    end = text.find("\n---", 3)
    if end == -1:
        return fm
    block = text[3:end]
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if m:
            fm[m.group(1).strip()] = m.group(2).strip()
    return fm


def slug_tokens(name: str) -> set:
    toks = re.split(r"[^A-Za-z0-9]+", name.lower())
    return {t for t in toks if t and t not in STOPWORDS and len(t) > 1}


def installed_skill_slugs() -> dict:
    """Map existing skill name -> distinctive token set. Handles both layouts:
    skills/<name>.md and skills/<name>/SKILL.md."""
    out = {}
    for d in SKILL_DIRS:
        if not d.is_dir():
            continue
        for f in d.glob("*.md"):
            if f.stem == "_index":
                continue
            out[f.stem] = slug_tokens(f.stem)
        for f in d.glob("*/SKILL.md"):
            out[f.parent.name] = slug_tokens(f.parent.name)
    return out


def count_routing_hits(name: str, stem: str) -> tuple:
    """Count literal references to the candidate across routing sources.

    Cheap + precise: a route that points at this candidate names it by its slug.
    Returns (total_hits, [source_basenames_with_hits]).
    """
    needles = {n for n in (name.lower(), stem.lower()) if n}
    # Word-boundary match on the slug so a short stem ("fresh") does not
    # false-match a longer token ("refresh", "fresh-start"). Slugs contain
    # hyphens, so the boundary excludes [\w-] on both sides.
    patterns = [re.compile(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])")
                for n in needles]
    total = 0
    where = []
    for src in ROUTING_SOURCES:
        try:
            body = src.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        hits = sum(len(p.findall(body)) for p in patterns)
        if hits:
            total += hits
            where.append(src.name)
    return total, where


def best_merge_target(cand_tokens: set, installed: dict, cand_stem: str) -> dict:
    """Find the installed skill with the strongest distinctive-token overlap.

    Advisory heuristic only (token overlap, NOT semantic). Reported so a human can
    judge; only drives a MERGE disposition when overlap is strong.
    """
    best = {"target": None, "shared": [], "exact_name": False}
    if cand_stem in installed:
        best["target"] = cand_stem
        best["shared"] = sorted(cand_tokens & installed[cand_stem])
        best["exact_name"] = True
        return best
    best_n = 0
    for stem, toks in installed.items():
        shared = cand_tokens & toks
        if len(shared) > best_n:
            best_n = len(shared)
            best = {"target": stem, "shared": sorted(shared), "exact_name": False}
    return best


def run_linter(path: Path) -> dict:
    """Invoke skill_linter.py --json on the candidate. Never raises."""
    if not LINTER.exists():
        return {"verdict": "unavailable", "score": None, "note": "linter not found"}
    try:
        proc = subprocess.run(
            [sys.executable, str(LINTER), str(path), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(proc.stdout)
        results = data.get("results") or []
        if results:
            r = results[0]
            return {"verdict": r.get("verdict", "unknown"),
                    "score": r.get("score"),
                    "findings": len(r.get("findings") or [])}
        return {"verdict": data.get("worst_verdict", "unknown"), "score": None}
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError, ValueError) as e:
        return {"verdict": "unavailable", "score": None, "note": type(e).__name__}


def assess(path: Path, installed: dict) -> dict:
    """Compute proxies + disposition for one candidate. Never raises."""
    row = {"file": path.name, "path": str(path)}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        row.update(disposition="SKIP", reason=f"unreadable ({type(e).__name__})")
        return row

    fm = parse_frontmatter(text)
    name = fm.get("name", path.stem)
    stem = path.stem
    status = (fm.get("status") or "unknown").strip()

    # --- age proxies ---
    try:
        mtime_age = (today() - date.fromtimestamp(path.stat().st_mtime)).days
    except OSError:
        mtime_age = None

    # dates embedded anywhere in the frontmatter block (reviewed_at, status,
    # parent_session, review_notes, created, date, ...)
    fm_text = "\n".join(f"{k}: {v}" for k, v in fm.items())
    found_dates = sorted(set(DATE_RE.findall(fm_text)))
    last_dated = found_dates[-1] if found_dates else None
    created_dated = found_dates[0] if found_dates else None
    dated_age = None
    if last_dated:
        try:
            dated_age = (today() - date.fromisoformat(last_dated)).days
        except ValueError:
            dated_age = None

    ages = [a for a in (mtime_age, dated_age) if a is not None]
    effective_age = min(ages) if ages else None  # most-recent human/file touch

    # --- routing interest ---
    routing_hits, routing_where = count_routing_hits(name, stem)

    # --- merge overlap ---
    cand_tokens = slug_tokens(name) | slug_tokens(stem)
    merge = best_merge_target(cand_tokens, installed, stem)
    strong_merge = merge["exact_name"] or len(merge["shared"]) >= 2

    # --- linter ---
    lint = run_linter(path)

    on_hold = "hold" in status.lower()

    # --- disposition precedence (advisory) ---
    # 1. exact-name collision with an installed skill = redundant -> MERGE (dedupe)
    # 2. explicit human hold with a review date -> KEEP (never auto-reject a hold)
    # 3. anything routes to it -> KEEP (wire/promote it)
    # 4. strong slug overlap with an installed skill -> MERGE
    # 5. stale + zero routing + not held -> REJECT
    # 6. fresh -> KEEP
    # 7. aging, ambiguous -> KEEP (revisit); conservative, advisory never auto-rejects
    if merge["exact_name"]:
        disp = "MERGE"
        reason = f"name collides with installed skill '{merge['target']}' (redundant)"
    elif on_hold and last_dated:
        disp = "KEEP"
        reason = f"explicit human hold (status={status}, reviewed {last_dated}); respect it"
    elif routing_hits > 0:
        disp = "KEEP"
        reason = f"{routing_hits} routing reference(s) in {', '.join(routing_where)}"
    elif strong_merge:
        disp = "MERGE"
        reason = (f"overlaps installed '{merge['target']}' on "
                  f"{{{', '.join(merge['shared'])}}}")
    elif effective_age is not None and effective_age > STALE_DAYS and routing_hits == 0:
        disp = "REJECT"
        reason = f"stale ({effective_age}d > {STALE_DAYS}d) + zero routing interest"
    elif effective_age is not None and effective_age <= FRESH_DAYS:
        disp = "KEEP"
        reason = f"recently touched ({effective_age}d <= {FRESH_DAYS}d)"
    else:
        age_s = f"{effective_age}d" if effective_age is not None else "unknown age"
        disp = "KEEP"
        reason = f"aging ({age_s}), no routing/merge signal; revisit (conservative default)"

    row.update(
        name=name, status=status,
        mtime_age_days=mtime_age, effective_age_days=effective_age,
        created_dated=created_dated, last_dated=last_dated,
        routing_hits=routing_hits, routing_where=routing_where,
        merge_target=merge["target"], merge_shared=merge["shared"],
        linter_verdict=lint.get("verdict"), linter_score=lint.get("score"),
        disposition=disp, reason=reason,
    )
    return row


def build_report(rows: list, queue: Path) -> str:
    stamp = today().isoformat()
    counts = {}
    for r in rows:
        counts[r["disposition"]] = counts.get(r["disposition"], 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"

    L = []
    L.append(f"# Skill-Candidate Disposition Report, {stamp}")
    L.append("")
    L.append("> **ADVISORY ONLY. This report mutates NOTHING.** The generating "
             "script (`scripts/pipeline/skill_disposition.py`) does not delete, move, "
             "or edit any skill, candidate, or steering file. It only reads the queue "
             "and writes this report. A human reviews the dispositions below and "
             "acts (or not).")
    L.append("")
    L.append(f"- Queue scanned: `{queue}`")
    L.append(f"- Candidates: **{len(rows)}**")
    L.append(f"- Disposition tally: {summary}")
    L.append(f"- Proxy thresholds: fresh <= {FRESH_DAYS}d, stale > {STALE_DAYS}d "
             f"(no accuracy oracle, cheap proxies only)")
    L.append("")
    L.append("Disposition legend: **KEEP** (recent / routed / explicit hold), "
             "**MERGE** (overlaps an installed skill), **REJECT** (stale + zero "
             "routing + old), **SKIP** (malformed, could not assess).")
    L.append("")

    if not rows:
        L.append("_Queue is empty. Nothing to disposition._")
        return "\n".join(L) + "\n"

    for r in rows:
        L.append(f"## {r['disposition']}: `{r['file']}`")
        if r["disposition"] == "SKIP":
            L.append(f"- **Reason:** {r.get('reason')}")
            L.append("")
            continue
        L.append(f"- **Advisory:** {r['disposition']}. {r['reason']}")
        L.append(f"- Name / status: `{r.get('name')}` / `{r.get('status')}`")
        L.append(f"- Age: mtime {r.get('mtime_age_days')}d, "
                 f"effective {r.get('effective_age_days')}d "
                 f"(frontmatter dates {r.get('created_dated')} .. {r.get('last_dated')})")
        rw = r.get("routing_where") or []
        L.append(f"- Routing hits: {r.get('routing_hits')}"
                 + (f" (in {', '.join(rw)})" if rw else " (nothing routes to it)"))
        mt = r.get("merge_target")
        ms = r.get("merge_shared") or []
        L.append(f"- Nearest installed skill: "
                 + (f"`{mt}` sharing {{{', '.join(ms)}}}" if mt and ms
                    else f"`{mt}` (no distinctive token overlap)" if mt else "none"))
        L.append(f"- Linter: {r.get('linter_verdict')} "
                 f"(score {r.get('linter_score')})")
        L.append("")

    L.append("---")
    L.append("_Next step is human: for each REJECT, confirm before `git rm`; for each "
             "MERGE, fold into the named skill; KEEP rows stay queued. The script will "
             "not do any of this for you._")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Advisory skill-candidate disposition.")
    ap.add_argument("--queue", default=str(DEFAULT_QUEUE),
                    help="candidate queue dir (default: outputs/raw/skill-candidates)")
    ap.add_argument("--stdout-only", action="store_true",
                    help="print report but do not write a file")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable rows to stdout instead of markdown")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 64

    queue = Path(args.queue)
    if not queue.is_dir():
        msg = f"Queue directory not found: {queue}. Nothing to disposition."
        if args.json:
            print(json.dumps({"queue": str(queue), "candidates": 0,
                              "note": "queue missing", "rows": []}))
        else:
            print(msg)
        return 0

    candidates = sorted(queue.glob("*.md"))
    installed = installed_skill_slugs()
    rows = []
    for c in candidates:
        try:
            rows.append(assess(c, installed))
        except Exception as e:  # belt-and-suspenders: a candidate never breaks the run
            rows.append({"file": c.name, "path": str(c), "disposition": "SKIP",
                         "reason": f"unexpected error ({type(e).__name__})"})

    if args.json:
        print(json.dumps({"queue": str(queue), "candidates": len(rows),
                          "rows": rows}, indent=2))
        return 0

    report = build_report(rows, queue)
    if not args.stdout_only:
        try:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            out = REPORT_DIR / f"skill-disposition-{today().isoformat()}.md"
            out.write_text(report, encoding="utf-8")
            print(f"[report written] {out}\n")
        except OSError as e:
            print(f"[report NOT written: {type(e).__name__}] printing to stdout only\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
