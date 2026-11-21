#!/usr/bin/env python3
# orphan_ref_check.py: warn when a summary still mentions something cut from the body.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""orphan_ref_check.py: after a cut, find summary text that still points at what was cut.

A cut removes a section or a named thing from the body, but the TL;DR, the opening
paragraph or the closing section still mention it. The reader is promised something the
piece no longer has.

WHAT IT DOES
  1. Zones of the draft: the TL;DR (its heading plus the bullets under it), the first
     paragraph after the TL;DR, and the last '## ' section. Everything else is the body.
     No TL;DR heading: the zones are the first paragraph and the last section.
  2. From the OLDER copy's body it takes candidates: section headings, and key noun phrases
     (capitalised names and acronyms, figures such as "72%", "US$482 billion", "23.5 million").
  3. A candidate is CUT when it is gone from the draft's body (a heading: no heading in the
     draft carries all its content words).
  4. Each cut candidate still mentioned in a draft zone is a WARN, with the zone line number
     and the older copy's line number.

USAGE
  orphan_ref_check.py <draft.md> [--against <older.md>] [--json]
  Default --against: the newest sibling named <draft-stem>.*.md (draft-full.v12.md,
  draft-full.pre-x.md ...), by modification time.
  exit 0 = no orphan | 1 = WARN, orphan mentions found | 2 = usage error or nothing compared
  (no older copy, or no candidates in it). WARN only: skills/longform does not block on it.

LIMITS. Lexical: a summary that paraphrases the cut thing ("the four tests") is missed, and a
name that survives in the body under another spelling counts as cut.
"""
import argparse
import json
import re
import sys
from pathlib import Path

STOP = set("""a an the and or but of in on at to for from by with as is are was were be been it its
this that these those there here what which who how why when where we i you they he she our my your
not no nor so if then than also only just very more most less few new old one two three four five six
seven eight nine ten first last next back up down out over into about after before under between""".split())
NUMWORD = set("one two three four five six seven eight nine ten twelve hundred".split())
VISUAL = re.compile(r"^\s*\[\[VISUAL:[^\]]*\]\]\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
NOT_FOR_POSTING = re.compile(r"<!--\s*not for posting", re.I)
CAPSEQ = re.compile(r"(?<![\w$])(?:[A-Z][\w&'.-]*[\w]|[A-Z]{2,}|[A-Z])(?:\s+(?:of\s+|de\s+)?(?:[A-Z][\w&'.-]*[\w]|[A-Z]{2,}|[A-Z]\b))*")
FIGURE = re.compile(r"(?:US\$|S\$|Rp\.?\s?|\$)?\d[\d.,]*\d?\s?(?:%|percent\b|per cent\b|million\b|billion\b|trillion\b|bn\b)", re.I)


def read_lines(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    text = NOT_FOR_POSTING.split(text, maxsplit=1)[0]
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                start = j + 1
                break
    return lines, start


def zones(lines, start):
    """{line_index: zone_name} for the TL;DR, the first paragraph after it, the last section."""
    z, n = {}, len(lines)
    heads = [i for i in range(start, n) if HEADING.match(lines[i])]
    tldr = next((i for i in heads if re.match(r"tl;?dr\b", HEADING.match(lines[i]).group(2), re.I)), None)

    def para_from(i):
        while i < n and (not lines[i].strip() or VISUAL.match(lines[i])):
            i += 1
        if i >= n or HEADING.match(lines[i]):
            return i, []
        out = []
        while i < n and lines[i].strip() and not HEADING.match(lines[i]):
            out.append(i)
            i += 1
        return i, out

    if tldr is not None:
        z[tldr] = "TL;DR"
        i = tldr + 1
        bullets = False
        while i < n and not HEADING.match(lines[i]):
            s = lines[i]
            if BULLET.match(s) or (bullets and s.startswith((" ", "\t")) and s.strip()):
                bullets = True
                z[i] = "TL;DR"
            elif s.strip() and not VISUAL.match(s):
                break
            i += 1
        if not bullets:                       # a prose TL;DR: its first paragraph is the TL;DR
            i, para = para_from(tldr + 1)
            for k in para:
                z[k] = "TL;DR"
        _, para = para_from(i)
        for k in para:
            z[k] = "first paragraph"
    else:
        _, para = para_from(start)
        for k in para:
            z[k] = "first paragraph"
    h2 = [i for i in heads if HEADING.match(lines[i]).group(1) == "##" and i != tldr]
    if h2:
        for k in range(h2[-1], n):
            if lines[k].strip() and not VISUAL.match(lines[k]):
                z.setdefault(k, "last section")
    return z, tldr is not None


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[*_`\[\]()]", " ", s)).strip().lower()


def content_words(h):
    return [w for w in re.findall(r"[a-z0-9$%]+", h.lower()) if w not in STOP or w in NUMWORD]


def phrases(line):
    out = set()
    clean = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
    clean = re.sub(r"https?://\S+", " ", clean)
    for m in CAPSEQ.finditer(clean):
        p = m.group(0).strip(" .'-")
        toks = p.split()
        while toks and toks[0].lower() in STOP:
            toks = toks[1:]
        if not toks:
            continue
        p = " ".join(toks)
        if len(toks) == 1:
            t = toks[0]
            sentence_start = re.search(r"(?:^|[.!?:]\s+|^\s*(?:[-*+]|\d+[.)])\s+)" + re.escape(m.group(0)) + r"\b", clean)
            acronym = len(t) >= 2 and t.isupper()
            if not acronym and (sentence_start or len(t) < 3):
                continue
        out.add(p)
    for m in FIGURE.finditer(clean):
        out.add(re.sub(r"\s+", " ", m.group(0).strip()))
    return out


def present(phrase, text_norm):
    return re.search(r"(?<![\w$])" + re.escape(norm(phrase)) + r"(?![\w%])", text_norm) is not None


def check(draft, older):
    dl, ds = read_lines(draft)
    ol, os_ = read_lines(older)
    dz, has_tldr = zones(dl, ds)
    oz, _ = zones(ol, os_)
    d_body = norm(" ".join(dl[i] for i in range(ds, len(dl)) if i not in dz and not VISUAL.match(dl[i])))
    d_heads = [content_words(HEADING.match(l).group(2)) for l in dl[ds:] if HEADING.match(l)]
    cands = {}                                # (kind, text) -> first old line number
    for i in range(os_, len(ol)):
        if i in oz or VISUAL.match(ol[i]):
            continue
        hm = HEADING.match(ol[i])
        if hm and len(hm.group(1)) >= 2 and not re.match(r"tl;?dr\b", hm.group(2), re.I):
            cands.setdefault(("heading", hm.group(2)), i + 1)
        for p in phrases(ol[i]):
            cands.setdefault(("phrase", p), i + 1)
    cut = []
    for (kind, text), oline in cands.items():
        if kind == "heading":
            cw = content_words(text)
            if cw and not any(set(cw) <= set(h) for h in d_heads):
                cut.append((kind, text, oline, cw))
        elif not present(text, d_body):
            cut.append((kind, text, oline, None))
    warns = []
    for kind, text, oline, cw in cut:
        for i in sorted(dz):
            ln = norm(dl[i])
            hit = (set(cw) <= set(re.findall(r"[a-z0-9$%]+", ln))) if kind == "heading" else present(text, ln)
            if hit:
                warns.append({"line": i + 1, "zone": dz[i], "kind": kind, "text": text, "older_line": oline})
    return {"draft": str(draft), "against": str(older), "has_tldr": has_tldr, "candidates": len(cands),
            "cut": len(cut), "cut_items": [f"{k} '{t}' (old L{o})" for k, t, o, _ in cut], "warn": warns}


def default_against(draft):
    d = Path(draft).resolve()
    sib = [p for p in d.parent.glob(f"{d.stem}.*.md") if p.resolve() != d]
    return max(sib, key=lambda p: p.stat().st_mtime) if sib else None


def main():
    ap = argparse.ArgumentParser(description="Warn when the TL;DR, opening or closing still mention something cut from the body.")
    ap.add_argument("draft")
    ap.add_argument("--against", help="older copy (default: newest <draft-stem>.*.md sibling)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-cut", action="store_true", help="also list every candidate cut from the body")
    a = ap.parse_args()
    if not Path(a.draft).is_file():
        print(f"orphan_ref_check: no such draft: {a.draft}", file=sys.stderr)
        return 2
    older = Path(a.against) if a.against else default_against(a.draft)
    if older is None or not older.is_file():
        print(f"orphan_ref_check: NOTHING COMPARED, no older copy found for {a.draft} (pass --against)", file=sys.stderr)
        return 2
    r = check(a.draft, older)
    if r["candidates"] == 0:
        print(f"orphan_ref_check: NOTHING COMPARED, no headings or key phrases found in {older}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"== ORPHAN-REFERENCE CHECK == {a.draft}\n against: {older}")
        if not r["has_tldr"]:
            print(" note: no TL;DR heading; zones = first paragraph + last section")
        print(f" {r['candidates']} headings/phrases in the older body, {r['cut']} gone from the draft body")
        if a.show_cut:
            for c in r["cut_items"]:
                print(f"   cut: {c}")
        for w in r["warn"]:
            print(f" WARN L{w['line']} ({w['zone']}): still mentions {w['kind']} '{w['text']}', cut from the body (old L{w['older_line']})")
        print(f" VERDICT: {'WARN' if r['warn'] else 'CLEAN'} ({len(r['warn'])} orphan mention(s))")
    return 1 if r["warn"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
