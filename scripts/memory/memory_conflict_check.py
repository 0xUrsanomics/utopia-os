#!/usr/bin/env python3
# memory_conflict_check.py: write-time contradiction flags for a new memory entry.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Write-time contradiction check for memory entries.

Before a new fact is appended to memory, find the existing entries about the same subject and flag
the ones that likely disagree with it, so the writer reconciles NOW (supersede the old line, or
merge) instead of leaving two live versions for a future session to trip on.

How it works (stdlib only, reads the live files, so it is never staler than the disk):
  1. Split memory/*.md, memory/Context, memory/Infra, memory/Feedback, memory/projects into blocks
     (a heading, a bullet, or a paragraph).
  2. Score each block by shared SALIENT tokens with the candidate: tickers and acronyms, capitalised
     names, numbers with their unit, dates. Ordinary words do not count.
  3. For the top neighbours, raise flags:
       - status-flip: one side says live/shipped/active/approved/signed, the other dead/paused/
         reverted/rejected/walked/cancelled/postponed
       - number-drift: same unit or keyword, different number (e.g. "40 feeds" vs "38 feeds")
       - date-drift: same subject keyword, different ISO date for what reads like the same event
       - negation: one side carries NOT / never / no longer around the shared subject
  4. Exit 1 when any neighbour is flagged, 0 when clean, so a caller can gate on it.

It flags, it does not decide. A flagged neighbour is often just an older state that the new entry
correctly supersedes. The writer then marks the old block with `superseded_by:: YYYY-MM-DD <where>`
(or edits it), which is the whole point: one live version per fact.

Usage:
  memory_conflict_check.py --text "Acme export job moved to 02:00 on 2026-10-16, 40 feeds live"
  memory_conflict_check.py --file /path/to/candidate.md
  memory_conflict_check.py --text "..." --top 8 --json
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
MEM = ROOT / "memory"
SCAN = [MEM / "Decisions.md", MEM / "Learnings.md", MEM / "Preferences.md", MEM / "USER.md"]
SCAN_DIRS = [MEM / "Context", MEM / "Infra", MEM / "Feedback", MEM / "projects"]

POS = r"live|shipped|active|approved|signed|confirmed|enabled|installed|open|accepted|closed[- ]won|submitted|pushed|public"
NEG = r"dead|paused|reverted|rejected|walked|cancell?ed|postponed|disabled|uninstalled|retired|scrapped|blocked|banned|closed[- ]lost|declined|private|deprecated"
NEGATION = r"\b(not|never|no longer|isn't|wasn't|don't|doesn't)\b"
# Capitalised words that carry no subject. Add your agent's and operator's own names here, since
# they appear in almost every entry and would otherwise make everything look related.
STOP = {"The", "This", "That", "When", "What", "Why", "How", "And", "But", "For", "With", "From",
        "TG", "OK", "NEW", "NOTE", "UTC", "USD", "EUR", "MD", "JSON", "CLI", "API"}
STOP |= {w.strip() for w in os.environ.get("MEMORY_CONFLICT_STOPWORDS", "").split(",") if w.strip()}


def salient(text):
    """Salient tokens: acronyms/tickers, Capitalised names, number+unit pairs, ISO dates."""
    toks = set()
    for m in re.finditer(r"\b[A-Z][A-Za-z0-9]{1,}(?:[-/][A-Za-z0-9]+)*\b", text):
        t = m.group(0)
        if t not in STOP and not t.isdigit():
            toks.add(t.lower())
    for m in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", text):
        toks.add(m.group(0))
    return toks


def numbers(text):
    """(number, following word) pairs, e.g. ('40', 'feeds'), ('3.5k', 'rows')."""
    out = set()
    for m in re.finditer(r"\b(\d[\d.,]*\s?[kmbt%]?)\s*([A-Za-z]{3,})", text, re.I):
        n = m.group(1).replace(",", "").replace(" ", "").lower()
        if re.fullmatch(r"\d{4}", n):  # a bare year is a date, not a quantity
            continue
        out.add((n, m.group(2).lower()))
    return out


def blocks():
    files = [p for p in SCAN if p.exists()]
    for d in SCAN_DIRS:
        if d.exists():
            files += sorted(d.rglob("*.md"))
    for f in files:
        try:
            lines = f.read_text(errors="ignore").splitlines()
        except Exception:
            continue
        buf, start = [], 0
        for i, ln in enumerate(lines + [""]):
            boundary = not ln.strip() or ln.lstrip().startswith(("- ", "* ", "#"))
            if boundary and buf:
                yield f, start + 1, "\n".join(buf)
                buf = []
            if ln.strip():
                if not buf:
                    start = i
                buf.append(ln)


def focus(block, shared):
    """Only the sentences of a block that mention a shared token. Long blocks otherwise flag on noise."""
    sents = re.split(r"(?<=[.;!?])\s+|\n", block)
    keep = [x for x in sents if salient(x) & shared]
    return " ".join(keep) if keep else ""


def flags_for(cand, block, shared):
    if "superseded_by::" in block:
        return []  # already reconciled
    block = focus(block, shared)
    if not block:
        return []
    fl = []
    cpos, cneg = set(re.findall(POS, cand, re.I)), set(re.findall(NEG, cand, re.I))
    bpos, bneg = set(re.findall(POS, block, re.I)), set(re.findall(NEG, block, re.I))
    if (cpos and bneg and not cneg) or (cneg and bpos and not cpos):
        fl.append(f"status-flip ({', '.join(sorted(cpos | cneg))} vs {', '.join(sorted(bpos | bneg))})")
    cn, bn = numbers(cand), numbers(block)
    for n, unit in cn:
        others = {m for m, u in bn if u == unit and m != n}
        if others:
            fl.append(f"number-drift ({n} {unit} vs {', '.join(sorted(others))} {unit})")
    cd, bd = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", cand)), set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", block))
    if cd and bd and not (cd & bd) and re.search(r"\b(on|by|deadline|due|launch|signed|closed|expires?)\b", block, re.I):
        fl.append(f"date-drift ({', '.join(sorted(cd))} vs {', '.join(sorted(bd))})")
    if bool(re.search(NEGATION, cand, re.I)) != bool(re.search(NEGATION, block, re.I)):
        fl.append("negation-mismatch")
    return fl


def check(cand, top=6, min_shared=2):
    """Rank blocks by the rarity-weighted overlap of salient tokens (a rare name counts more than a
    common acronym). One shared token is enough if it is rare (in 150 blocks or fewer) or the candidate has only one."""
    import math
    cs = salient(cand)
    if not cs:
        return cs, []
    allb = [(f, line, text, salient(text)) for f, line, text in blocks()]
    df = {t: sum(1 for *_, st in allb if t in st) for t in cs}
    n = max(len(allb), 1)
    scored = []
    for f, line, text, st in allb:
        shared = cs & st
        if not shared or text.strip() == cand.strip():
            continue
        rare = len(cs) == 1 or any(df[t] <= 150 for t in shared)
        if len(shared) < min_shared and not rare:
            continue
        score = sum(math.log(n / (1 + df[t])) for t in shared)
        scored.append((score, f, line, text, shared))
    scored.sort(key=lambda x: -x[0])
    out = []
    for sc, f, line, text, shared in scored[:top]:
        out.append({"file": str(f.relative_to(ROOT)), "line": line, "shared": sorted(shared), "score": round(sc, 1),
                    "flags": flags_for(cand, text, shared), "text": focus(text, shared)[:400] or text[:400]})
    return cs, out


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--file")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--min-shared", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cand = a.text if a.text is not None else Path(a.file).read_text()
    cs, res = check(cand, a.top, a.min_shared)
    flagged = [r for r in res if r["flags"]]
    if a.json:
        print(json.dumps({"salient": sorted(cs), "neighbours": res, "flagged": len(flagged)}, ensure_ascii=False, indent=1))
    else:
        print(f"salient tokens: {', '.join(sorted(cs)) or '(none)'}")
        if not res:
            print("no related entries found")
        for r in res:
            mark = "FLAG" if r["flags"] else "ok  "
            print(f"\n[{mark}] {r['file']}:{r['line']}  shared: {', '.join(r['shared'])}")
            for fl in r["flags"]:
                print(f"       ! {fl}")
            print("       " + r["text"].replace("\n", " ")[:220])
        print(f"\n{len(flagged)} flagged of {len(res)} related. Reconcile flagged ones: edit, or mark `superseded_by:: <date> <where>`.")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
