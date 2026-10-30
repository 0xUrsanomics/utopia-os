#!/usr/bin/env python3
# hallucination_sample.py: daily cross-family hallucination sampler over substantive outputs.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Hallucination sampling pipeline (eval-harness metric: sampled factual-error rate).

Samples 5% (1 to 5 files) of substantive outputs written in the last 24h and has a model from a
DIFFERENT family judge them (the same model generating and judging shares its blind spots).
Verdicts go to outputs/raw/hallucination-audit/<YYYY-MM-DD>.md. An alert is written only when the
flag rate is above 2%, any FATAL finding exists, or the judge errored (no verdict is not a pass).

Rules this enforces:
  - Empty or unparseable judge output is ERRORED, never a clean pass.
  - A judge's knowledge is stale, so claims it cannot check are UNVERIFIABLE, not FATAL.
  - Before alerting, an arXiv id / DOI / URL the judge calls fabricated is resolved over HTTP;
    if it returns 200 the finding is downgraded to UNVERIFIABLE.
  - The body is capped at 100 KB (one argv string) and the judge is told when it was cut.

    python3 hallucination_sample.py                     # daily run
    python3 hallucination_sample.py --selftest          # LIVE control pair through the real judge
    python3 hallucination_sample.py --selftest-offline  # parser + resolver checks, no judge needed

Env:
  AGENT_ROOT              repo root (default: two levels up)
  HALLU_JUDGE_CMD         judge command; the prompt is appended as the last argv (e.g. "gemini -p")
  HALLU_DIRS              os.pathsep-separated dirs to sample (default: $AGENT_ROOT/outputs/raw)
  HALLU_JUDGE_TIMEOUT     seconds (default 120)
  AGENT_UTC_OFFSET_HOURS  local offset used for the report date (default 0)
  AGENT_DATA_DIR          alert signal file goes to $AGENT_DATA_DIR/signals/ (default $AGENT_ROOT/.data)
  OPERATOR_CHAT_ID        chat id written into the alert payload (optional)
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import shlex

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
SUBSTANTIVE_DIRS = [Path(p) for p in os.environ.get("HALLU_DIRS", str(ROOT / "outputs/raw")).split(os.pathsep) if p]
AUDIT_DIR = ROOT / "outputs/raw/hallucination-audit"
LOG_PATH = ROOT / "logs/session.jsonl"
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
JUDGE_CMD = shlex.split(os.environ.get("HALLU_JUDGE_CMD", "gemini -p"))
JUDGE_TIMEOUT_SEC = int(os.environ.get("HALLU_JUDGE_TIMEOUT", "120"))  # CLI judges can need the full 120 s
SAMPLE_RATE = 0.05
MIN_SAMPLES = 1
MAX_SAMPLES = 5
FLAG_RATE_THRESHOLD = 0.02
LOCAL_TZ = timezone(timedelta(hours=float(os.environ.get("AGENT_UTC_OFFSET_HOURS", "0"))))

# Substantive type tokens (frontmatter `type:` value). Empty / log-like skipped.
# Read from a single-source registry, knowledge/output-types.json ({"types": {"memo":
# {"substantive": true}}}), so the sampler and the writers share one vocabulary. A hardcoded
# copy drifts: its real coverage can fall to a handful of files without anyone noticing.
# The fallback set keeps sampling alive if the registry is missing or unparseable.
_TYPES_REGISTRY = ROOT / "knowledge/output-types.json"
_FALLBACK_SUBSTANTIVE = {
    "research-memo", "deck-content", "content-draft", "thread-draft",
    "proposal", "long-form", "audit-report", "playbook", "brief",
    "intel-report", "research-synthesis", "regulatory-analysis",
}


def _load_substantive_types() -> set:
    try:
        reg = json.loads(_TYPES_REGISTRY.read_text(encoding="utf-8"))
        s = {t for t, v in reg.get("types", {}).items()
             if isinstance(v, dict) and v.get("substantive")}
        return s or _FALLBACK_SUBSTANTIVE
    except Exception:
        return _FALLBACK_SUBSTANTIVE


SUBSTANTIVE_TYPES = _load_substantive_types()


def _read_frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    fm_block = text[4:end]
    out: dict = {}
    for line in fm_block.splitlines():
        m = re.match(r"^(\w+):\s*(.+)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def find_candidates(since_utc: datetime) -> list[Path]:
    candidates: list[Path] = []
    mds = [md for d in SUBSTANTIVE_DIRS if d.exists() for md in d.rglob("*.md")]
    for md in mds:
        try:
            mtime = datetime.fromtimestamp(md.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < since_utc:
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) < 400:
            continue
        fm = _read_frontmatter(text)
        # Files with no frontmatter in a substantive dir are candidates, not silently dropped.
        if not fm:
            candidates.append(md)
            continue
        ftype = fm.get("type", "").lower()
        status = fm.get("status", "").lower()
        # Skip already-shipped/approved (it's been reviewed)
        if status in {"shipped", "approved", "approved-ready-to-post"}:
            continue
        if ftype in SUBSTANTIVE_TYPES or "draft" in ftype or "memo" in ftype:
            candidates.append(md)
    return candidates


def sample(candidates: list[Path]) -> list[Path]:
    if not candidates:
        return []
    n = max(MIN_SAMPLES, min(MAX_SAMPLES, int(round(len(candidates) * SAMPLE_RATE))))
    n = min(n, len(candidates))
    random.seed(datetime.now(timezone.utc).strftime("%Y%m%d"))
    return random.sample(candidates, n)


# The no-tool line matters: a headless judge that tries a tool call can be auto-denied and return no text.
JUDGE_PROMPT = """You are a cross-family adversarial fact-checker. Cold-start context. NO knowledge of who wrote this.

Answer from the document text below and your own knowledge ONLY. Do not run commands, read files, browse, search or use any tool. Everything you need is in this prompt.

Document body:
---
{body}
---

Find factual hallucinations. Specifically:
1. Asserted-as-fact claims with no sourcing or hedging.
2. Fabricated numbers, dates, named entities, product names that may not exist.
3. Regulatory or jurisdictional imprecision (citing wrong law, wrong regulator, wrong agency).
4. Invented mechanisms or product surfaces (e.g. claiming a hardware POS exists when product is software-only).
5. Jurisdiction-specific legal or regulatory errors (which regulator covers what, what is legal tender, what a law actually requires).

Your knowledge is stale. It has a cutoff, and this document may be written after it. So do NOT rate a claim FATAL or MAJOR only because you have not heard of it. Label it UNVERIFIABLE instead when it:
- is dated after your knowledge ends, or describes an event, product, filing or figure you cannot check;
- carries an inline source cite (a URL, arXiv id, DOI, ticket or report name, or a named source with a date);
- would need current rates, volumes, prices, counts or identifier ranges to judge (for example an arXiv id that looks too high for its month).
Keep FATAL, MAJOR and MINOR for errors you can show from the document itself (internal contradiction, wrong arithmetic, a list that does not match its count) or from stable facts (what a law or regulator covers, settled history).

For each finding:
- Quote the exact claim.
- Severity: FATAL (invalidates the deliverable) | MAJOR (significant misstatement) | MINOR (improvable) | UNVERIFIABLE (cannot be checked from your knowledge, see above).
- One sentence explanation of what is actually true.

Constraints on YOUR writing:
- Zero em dashes (em-dash or en-dash). Periods and commas only.
- No AI-slop wordlist (leverage, seamless, robust, comprehensive, streamline, dive into, holistic).
- Lead with findings. No preamble.
- If you find no hallucinations, return exactly: NO_FINDINGS

Return a numbered list. After the list, add one line: SEVERITY_COUNTS: FATAL=N MAJOR=N MINOR=N UNVERIFIABLE=N
"""


# A silent character cut makes the judge see half a file and flag a correct headline count.
# The prompt travels as one argv string (Linux caps one arg at
# 128 KiB), so keep the body under 100 KB and tell the judge when anything was cut.
JUDGE_MAX_BYTES = 100_000


def fit_body(body: str, max_bytes: int = JUDGE_MAX_BYTES) -> str:
    raw = body.encode("utf-8")
    if len(raw) <= max_bytes:
        return body
    kept = raw[:max_bytes].decode("utf-8", errors="ignore")
    return (kept + f"\n\n[document truncated at {len(kept)} of {len(body)} chars. The rest was not shown to you. "
            "Do not flag counts, totals or claims that could depend on the missing part.]")


def judge(body: str) -> tuple[str, dict]:
    """Run the cross-family judge on a document body. Returns (raw_output, parsed_counts)."""
    body = fit_body(body)
    prompt = JUDGE_PROMPT.format(body=body)
    try:
        proc = subprocess.run(
            [*JUDGE_CMD, prompt], capture_output=True, text=True, timeout=JUDGE_TIMEOUT_SEC,
        )
        out = (proc.stdout or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return f"[JUDGE_ERROR] {type(e).__name__}: {e}", {"fatal": 0, "major": 0, "minor": 0, "unverifiable": 0, "errored": 1}
    return parse_verdict(out, proc.returncode, proc.stderr or "")


def parse_verdict(out: str, rc: int = 0, stderr: str = "") -> tuple[str, dict]:
    """Parse judge output. Empty or unparseable output is errored, never a clean pass
    (scoring it 0/0/0 would make a broken judge look like a perfect document)."""
    counts = {"fatal": 0, "major": 0, "minor": 0, "unverifiable": 0, "errored": 0}
    out = (out or "").strip()
    if not out:
        counts["errored"] = 1
        return f"[JUDGE_ERROR] empty judge output (rc={rc}) stderr_tail={stderr.strip()[-300:]!r}", counts
    if "NO_FINDINGS" in out:
        return out, counts
    m = re.search(r"SEVERITY_COUNTS:\s*FATAL=(\d+)\s*MAJOR=(\d+)\s*MINOR=(\d+)(?:\s*UNVERIFIABLE=(\d+))?", out, re.IGNORECASE)
    if m:
        counts["fatal"] = int(m.group(1))
        counts["major"] = int(m.group(2))
        counts["minor"] = int(m.group(3))
        counts["unverifiable"] = int(m.group(4) or 0)
        return resolve_cited_ids(out, counts)
    counts["errored"] = 1
    return f"[JUDGE_ERROR] unparseable judge output (rc={rc}, no NO_FINDINGS, no SEVERITY_COUNTS)\n{out}", counts


# A judge can flag a real arXiv id as fabricated from a stale monthly-volume prior.
# Before alerting, resolve any arXiv id, DOI or URL quoted in a FATAL/MAJOR finding that calls the
# identifier fake. If it resolves (HTTP 200), downgrade that finding to UNVERIFIABLE and say so.
_ARXIV_RE = re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b")
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>)\]]+)")
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
_FAKE_ID_RE = re.compile(r"fabricat|mistyped|does not exist|doesn't exist|nonexistent|non-existent|not a real|invalid identifier|no such", re.IGNORECASE)
_SEV_RE = re.compile(r"Severity:\s*\**\s*(FATAL|MAJOR)\b", re.IGNORECASE)


def _resolves(url: str, timeout: int = 10) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "hallucination-audit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _cited_urls(text: str) -> list[str]:
    urls = [f"https://arxiv.org/abs/{i}" for i in _ARXIV_RE.findall(text)]
    urls += [f"https://doi.org/{d.rstrip('.,;')}" for d in _DOI_RE.findall(text)]
    urls += [u.rstrip(".,;") for u in _URL_RE.findall(text) if "arxiv.org" not in u and "doi.org" not in u]
    return urls


def resolve_cited_ids(out: str, counts: dict, resolver=_resolves) -> tuple[str, dict]:
    blocks = re.split(r"(?m)^(?=\d+\.\s)", out)
    notes = []
    for b in blocks:
        sev = _SEV_RE.search(b)
        if not sev or not _FAKE_ID_RE.search(b):
            continue
        hit = next((u for u in _cited_urls(b) if resolver(u)), None)
        if not hit:
            continue
        key = sev.group(1).lower()
        if counts.get(key, 0) > 0:
            counts[key] -= 1
            counts["unverifiable"] = counts.get("unverifiable", 0) + 1
            num = re.match(r"(\d+)\.", b)
            notes.append(f"RESOLVER: finding {num.group(1) if num else '?'} downgraded {sev.group(1).upper()} -> UNVERIFIABLE, {hit} returns 200")
    if notes:
        out = out + "\n" + "\n".join(notes)
    return out, counts


def write_audit(today_local: str, samples: list[tuple[Path, str, dict]], n_candidates: int) -> Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out = AUDIT_DIR / f"{today_local}.md"
    flagged = sum(1 for _, _, c in samples if c["fatal"] + c["major"] > 0)
    rate = flagged / len(samples) if samples else 0.0
    n_errored = sum(c.get("errored", 0) for _, _, c in samples)
    body = [
        "---",
        f"date: {today_local}",
        f"type: hallucination-audit",
        f"candidates_in_window: {n_candidates}",
        f"sampled: {len(samples)}",
        f"flagged: {flagged}",
        f"errored: {n_errored}",
        f"flag_rate: {rate:.3f}",
        f"threshold: {FLAG_RATE_THRESHOLD}",
        "---",
        "",
        f"# Hallucination audit. {today_local}",
        "",
        f"Substantive outputs in last 24h: **{n_candidates}**. Sampled: **{len(samples)}** ({SAMPLE_RATE:.0%}). Flagged: **{flagged}** (rate {rate:.1%}). Errored (judge gave no usable verdict, NOT a clean pass): **{n_errored}**.",
        "",
    ]
    for path, verdict, counts in samples:
        rel = path.relative_to(ROOT)
        body.append(f"## {rel}")
        body.append("")
        body.append(f"counts: FATAL={counts['fatal']} MAJOR={counts['major']} MINOR={counts['minor']} UNVERIFIABLE={counts.get('unverifiable', 0)} errored={counts.get('errored', 0)}")
        body.append("")
        body.append("```")
        body.append(verdict)
        body.append("```")
        body.append("")
    out.write_text("\n".join(body), encoding="utf-8")
    return out


def alert(out_path: Path, flagged: int, sampled: int, fatal_count: int, errored: int = 0) -> None:
    """Write an alert signal file for your notifier to pick up. Best-effort. Silent on failure."""
    if sampled == 0:
        return
    rate = flagged / sampled
    if rate < FLAG_RATE_THRESHOLD and fatal_count == 0 and errored == 0:
        return
    msg = (
        f"hallucination audit: {flagged}/{sampled} flagged "
        f"({rate:.1%} vs threshold {FLAG_RATE_THRESHOLD:.0%})"
        f"{' + FATAL=' + str(fatal_count) if fatal_count else ''}"
        f"{' + judge errored=' + str(errored) + ' (no verdict, not clean)' if errored else ''}\n"
        f"report: {out_path.relative_to(ROOT)}"
    )
    # A signal file the notifier daemon polls, so this script needs no chat credentials.
    signal = DATA_DIR / "signals/hallucination-audit-alert"
    signal.parent.mkdir(parents=True, exist_ok=True)
    payload = {"chat_id": os.environ.get("OPERATOR_CHAT_ID", ""), "text": msg}
    try:
        signal.write_text(json.dumps(payload))
    except OSError:
        pass


def log_run(extras: dict) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level": "info",
        "persona": "agent",
        "category": "hallucination-audit",
        "event": "completed",
    }
    entry.update(extras)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


# Control pair: a judge that never flags anything also returns NO_FINDINGS, so a clean audit
# only means something if the judge is shown to catch errors it can check. Each planted error is
# checkable from the document itself or from stable facts, per the judge prompt. Fabricated doc.
_SELFTEST_CLEAN = """---
type: research-memo
---
# Vendor onboarding note

In the United States, the SEC regulates securities offerings.
The euro is the official currency of Germany.
We reviewed three vendors: Northwind, Contoso and Fabrikam.
Onboarding took 4, 6 and 5 days, a total of 15 days and an average of 5 days.
The pilot ran from 3 March to 28 March, so it lasted under one month.
"""
_SELFTEST_PLANTED = {
    "Federal Reserve regulates securities": "In the United States, the Federal Reserve regulates securities offerings.",
    "Swiss franc": "The Swiss franc is the official currency of Germany.",
    "five vendors": "We reviewed five vendors: Northwind, Contoso and Fabrikam.",
    "total of 19 days": "Onboarding took 4, 6 and 5 days, a total of 19 days and an average of 5 days.",
}


def _planted_doc() -> str:
    lines = _SELFTEST_CLEAN.splitlines()
    swaps = [("In the United States", "Federal Reserve regulates securities"), ("The euro is", "Swiss franc"),
             ("We reviewed three", "five vendors"), ("Onboarding took", "total of 19 days")]
    for prefix, key in swaps:
        lines = [_SELFTEST_PLANTED[key] if ln.startswith(prefix) else ln for ln in lines]
    return "\n".join(lines) + "\n"


def selftest_offline() -> int:
    """Checks that need no judge: parsing, errored-not-clean, truncation notice, resolver downgrade."""
    _, empty = parse_verdict("")
    _, clean = parse_verdict("NO_FINDINGS")
    _, junk = parse_verdict("looks fine to me")
    _, counted = parse_verdict("1. x\nSeverity: MAJOR\nSEVERITY_COUNTS: FATAL=1 MAJOR=2 MINOR=0 UNVERIFIABLE=1")
    fake = ("1. \"arXiv 2601.01234\" Severity: MAJOR. This id does not exist.\n"
            "SEVERITY_COUNTS: FATAL=0 MAJOR=1 MINOR=0 UNVERIFIABLE=0")
    _, resolved = resolve_cited_ids(fake, {"fatal": 0, "major": 1, "minor": 0, "unverifiable": 0, "errored": 0},
                                    resolver=lambda u: True)
    cut = fit_body("x" * 50, max_bytes=10)
    checks = {
        "empty_is_errored": empty["errored"] == 1,
        "no_findings_is_clean": clean["errored"] == 0 and clean["fatal"] + clean["major"] == 0,
        "unparseable_is_errored": junk["errored"] == 1,
        "counts_parsed": (counted["fatal"], counted["major"], counted["unverifiable"]) == (1, 2, 1),
        "resolver_downgrades": resolved["major"] == 0 and resolved["unverifiable"] == 1,
        "truncation_announced": "truncated" in cut,
        "planted_doc_differs": _planted_doc() != _SELFTEST_CLEAN,
    }
    ok = all(checks.values())
    print(f"selftest-offline {'PASS' if ok else 'FAIL'}: {checks}")
    return 0 if ok else 1


def selftest(judge_fn=None) -> int:
    """Control pair: the judge must flag at least 3 of 4 planted errors as FATAL/MAJOR,
    and raise no FATAL/MAJOR on the clean twin. Errored or unparseable output is a FAIL."""
    judge_fn = judge_fn or judge
    clean_out, clean = judge_fn(_SELFTEST_CLEAN)
    planted_out, planted = judge_fn(_planted_doc())
    low = planted_out.lower()
    caught = [k for k in _SELFTEST_PLANTED if k.lower() in low]
    checks = {
        "clean_parsed": clean["errored"] == 0,
        "planted_parsed": planted["errored"] == 0,
        "clean_no_fatal_major": clean["fatal"] + clean["major"] == 0,
        "planted_fatal_major_ge_3": planted["fatal"] + planted["major"] >= 3,
        "planted_quoted_ge_3": len(caught) >= 3,
    }
    ok = all(checks.values())
    print(f"selftest {'PASS' if ok else 'FAIL'}: {checks}")
    print(f"  planted quoted: {caught} | planted counts {planted} | clean counts {clean}")
    if not ok:
        print("--- clean judge output ---\n" + clean_out + "\n--- planted judge output ---\n" + planted_out)
    log_run({"event": "selftest", "result": "pass" if ok else "fail", "caught": len(caught),
             "planted_counts": planted, "clean_counts": clean})
    return 0 if ok else 1


def main() -> int:
    if "--selftest-offline" in sys.argv:
        return selftest_offline()
    if "--selftest" in sys.argv:
        return selftest()
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(hours=24)
    today_local = now_utc.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")

    candidates = find_candidates(since)
    if not candidates:
        log_run({"event": "no-candidates", "candidates": 0, "sampled": 0})
        print("no substantive candidates in last 24h. wrote nothing.")
        return 0

    samples = sample(candidates)
    results: list[tuple[Path, str, dict]] = []
    fatal_total = 0
    major_total = 0
    minor_total = 0
    unverifiable_total = 0
    errored = 0
    for path in samples:
        body = path.read_text(encoding="utf-8", errors="replace")
        verdict, counts = judge(body)
        results.append((path, verdict, counts))
        fatal_total += counts["fatal"]
        major_total += counts["major"]
        minor_total += counts["minor"]
        unverifiable_total += counts.get("unverifiable", 0)
        errored += counts.get("errored", 0)

    out_path = write_audit(today_local, results, len(candidates))
    flagged = sum(1 for _, _, c in results if c["fatal"] + c["major"] > 0)
    alert(out_path, flagged, len(results), fatal_total, errored)
    log_run({
        "candidates": len(candidates),
        "sampled": len(results),
        "flagged": flagged,
        "fatal_total": fatal_total,
        "major_total": major_total,
        "minor_total": minor_total,
        "unverifiable_total": unverifiable_total,
        "errored": errored,
        "report": str(out_path.relative_to(ROOT)),
    })
    print(f"audit: {flagged}/{len(results)} flagged. report: {out_path}")
    return 1 if flagged > 0 or fatal_total > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
