#!/usr/bin/env python3
# external_slop_gate.py: transcript-free HARD/WARN anti-AI-slop gate for external-facing artifacts.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
external_slop_gate.py . universal, register-agnostic anti-AI-slop gate for ANY
external-facing artifact (CV / cover letter / outreach email / deck copy / memo /
caption / published doc).

WHY THIS EXISTS (the gap it closes). A voice-fidelity gate needs an operator
interview transcript and scores "does this sound like the operator's personal
voice". That fits social posts and thought-leadership. It does NOT fit a formal
client deck, an outreach email, or a CV: those are professional register on
purpose, and most have no transcript to anchor against. Skills that only carry
anti-slop as PROSE advice ("apply the filter") never enforce it. This is the
enforced scan: transcript-free, voice-neutral, and it only flags
machine-generated TELLS, not professional word choice.

WHAT IT IS NOT. Not a voice gate. Not an AI-detector to game (never inject noise
to beat it; fix the actual tell). Not a design gate for visual slop.

PRECISION SPLIT (deliberate, so it does not false-block legit formal docs):
  HARD  = unambiguous AI tells + em/en dash + assistant openers + CV passion-filler
          + retracted claims. A hit exits 1 (block). These are almost never
          legitimate in external output.
  WARN  = words that are context-legit in a formal register (robust, comprehensive,
          leverage...) + structural tells. Printed for review, do NOT change the
          exit code. This is what keeps a real professional deck from tripping.

USAGE
  external_slop_gate.py --file <path>          # scan a file
  external_slop_gate.py --stdin                # scan stdin
  external_slop_gate.py --file X --json        # machine-readable
  external_slop_gate.py --cv                   # add CV/cover-letter filler to HARD
  external_slop_gate.py --selftest             # offline self-check, no file needed
  exit 0 = clean (no HARD hit) | 1 = HARD hit (block, fix before ship) | 2 = usage/error

RETRACTED CLAIMS. A correction recorded only as a prose lesson has to be remembered at copy time,
and stale drafts get copied anyway. So a JSON registry of retracted claims is a HARD block:
  {"claims": [{"id": "...", "pattern": "<regex>", "scope": "all" | "cv", "replacement": "..."}]}
Path: $AGENT_RETRACTED_CLAIMS, default $AGENT_ROOT/knowledge/retracted-claims.json (start from
knowledge/retracted-claims.example.json). Missing or
broken registry = no retracted-claim checks (it never blocks on its own).
"""
import sys, os, re, argparse, json

# -- HARD: unambiguous machine tells. A hit blocks. High precision on purpose. --
HARD_WORDS = [
    "delve", "tapestry", "treasure trove", "ever-evolving", "ever evolving",
    "underscores", "underscore the", "a testament to", "testament to",
    "it is important to note", "it's worth noting", "at the end of the day",
    "let's dive in", "let's dive into", "let me unpack", "let's unpack",
    "without further ado", "buckle up", "here's the thing", "here's the kicker",
    "let that sink in", "make no mistake", "needle in a haystack",
    "in today's fast-paced", "in today's ever", "in the world of",
    "speaks volumes", "at the heart of", "when it comes to",
    "navigating the", "the realm of", "in this article", "in conclusion,",
]
# -- HARD: assistant / AI-cliche OPENERS (only flagged at the very start). --
HARD_OPENERS = [
    "sure!", "sure,", "of course!", "of course,", "i'd be happy to",
    "i would be happy to", "absolutely!", "great question", "let me help",
    "certainly!", "here's a", "here is a", "as an ai", "in today's",
]
# -- HARD: CV / cover-letter passion-filler (only added under --cv). --
CV_FILLER = [
    "i am excited to", "i'm excited to", "i am thrilled", "i'm thrilled",
    "i am passionate about", "i'm passionate about", "excited about the opportunity",
    "proven track record", "results-driven", "results driven", "detail-oriented",
    "detail oriented", "team player", "go-getter", "hit the ground running",
    "wearing many hats", "wear many hats", "think outside the box",
    "outside the box", "hard-working", "self-starter", "fast-paced environment",
    "dynamic environment", "value add", "value-add", "i believe my", "my passion for",
]
# -- WARN: context-legit in a formal register. Printed, never blocks. --
WARN_WORDS = [
    "leverage", "streamline", "unlock", "comprehensive", "holistic", "seamless",
    "robust", "crucial", "pivotal", "foster", "elevate", "unleash", "synergy",
    "spearheaded", "landscape", "cutting-edge", "state-of-the-art", "game-changer",
    "game changer", "revolutionize", "empower", "bandwidth", "circle back",
    "boasts", "nestled", "realm", "stark contrast", "genuinely",
]

def _read(args):
    if args.stdin:
        return sys.stdin.read()
    if args.file:
        with open(args.file, encoding="utf-8", errors="replace") as f:
            return f.read()
    return None

def _strip_md(md):
    md = re.sub(r"^---\n.*?\n---\n", "", md, flags=re.S)   # frontmatter
    md = re.sub(r"`{1,3}[^`]*`{1,3}", " ", md)             # code spans
    return md

def _first_sentence(text):
    t = re.sub(r"\s+", " ", _strip_md(text)).strip().lower()
    m = re.split(r"(?<=[.?!])\s+", t)
    return m[0] if m else ""

def _find(text, phrases):
    """Case-insensitive hits. Single tokens are word-boundaried; multiword
    phrases match as substrings (already specific enough to not false-fire)."""
    low = text.lower()
    hits = []
    for p in phrases:
        if " " in p or "-" in p or "," in p:
            if p in low:
                hits.append(p)
        else:
            if re.search(r"\b" + re.escape(p) + r"\b", low):
                hits.append(p)
    return hits

DASH = re.compile("[\u2014\u2013]")  # em dash, en dash

# Claims a correction retracted. A match in scope is a HARD block (see the docstring).
_ROOT = os.environ.get("AGENT_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
RETRACTED = os.environ.get("AGENT_RETRACTED_CLAIMS") or os.path.join(_ROOT, "knowledge", "retracted-claims.json")

def _retracted(body, cv):
    try:
        rows = json.load(open(RETRACTED, encoding="utf-8")).get("claims", [])
    except Exception:
        return []  # a missing or broken registry never blocks a ship on its own
    flat = re.sub(r"\s+", " ", body)
    # Paraphrase net: a row may also carry "concept", a list of regex groups. It matches when
    # every group appears in ONE sentence, so a reworded copy of a retracted claim is caught,
    # not only the exact old wording.
    sentences = re.split(r"(?<=[.!?])\s+|\n+", body)
    def _concept(r):
        groups = r.get("concept") or []
        return bool(groups) and any(all(re.search(g, sen, re.I) for g in groups) for sen in sentences)
    return [r for r in rows if (r.get("scope") == "all" or (cv and r.get("scope") == "cv"))
            and (re.search(r["pattern"], flat, re.I) or _concept(r))]

def scan(text, cv=False):
    body = _strip_md(text)
    hard_words = list(HARD_WORDS) + (CV_FILLER if cv else [])
    res = {
        "em_en_dash": bool(DASH.search(text)),
        "hard_slop": _find(body, hard_words),
        "hard_opener": [o for o in HARD_OPENERS if _first_sentence(text).startswith(o)],
        "warn_slop": _find(body, WARN_WORDS),
        "warn_structural": _structural(body),
        "retracted": [{"id": r["id"], "replacement": r.get("replacement", "")} for r in _retracted(body, cv)],
    }
    res["hard_hit"] = bool(res["em_en_dash"] or res["hard_slop"] or res["hard_opener"] or res["retracted"])
    return res

def _structural(body):
    warns = []
    if len(re.findall(r",\s+(creating|making|allowing|ensuring|driving|helping|enabling)\s+\w+ing\b", body.lower())) >= 2:
        warns.append("participial-tail x2+ (', creating/ensuring ...ing')")
    if len(re.findall(r"\bfrom\s+\w+\s+to\s+\w+", body.lower())) >= 2:
        warns.append("'from X to Y' framing x2+")
    if len(re.findall(r"\bnot just\b[^.]{0,60}\bbut\b", body.lower())) >= 1:
        warns.append("'not just X but Y' construction")
    if len(re.findall(r"\?\s+(Because|The|That's|It's|This)\b", body)) >= 2:
        warns.append("rhetorical-Q-then-answer x2+")
    # Rules adapted from the pstack "unslop" checklist. WARN only, all three
    # have legit uses in formal docs (CV section labels, title-case deck titles).
    if len(_colon_connectors(body)) >= 3:
        warns.append("colon-as-connector x3+ (mid-sentence ':' joining two clauses; end the sentence instead)")
    restated = _restated_labels(body)
    if restated:
        warns.append(f"inline-header list restates its label: {', '.join(restated[:3])}")
    titled = _title_case_headings(body)
    if titled:
        warns.append(f"title-case heading(s), use sentence case: {', '.join(titled[:3])}")
    return warns

_SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}

def _colon_connectors(body):
    """Prose lines where a colon joins two clauses mid-sentence. Skips list
    items, headings, table rows, lead-ins that end in ':', times and URLs."""
    hits = []
    for line in body.splitlines():
        ls = line.strip()
        if not ls or ls[0] in "-*#|>" or re.match(r"\d+[.)]\s", ls) or ls.endswith(":"):
            continue
        ls = re.sub(r"https?://\S+|\b\d{1,2}:\d{2}\b|\*\*[^*]+:\*\*", " ", ls)
        for m in re.finditer(r"\b[a-z]\w*:\s+[a-z]\w+\s+\w+\s+\w+", ls):
            hits.append(m.group(0))
    return hits

def _restated_labels(body):
    """'**Performance:** Performance improved...' style: the line repeats the label."""
    out = []
    for m in re.finditer(r"\*\*([A-Za-z][\w ]{1,40}?):?\*\*:?\s+(\w+)", body):
        label, nxt = m.group(1).split()[0].lower(), m.group(2).lower()
        if len(label) > 3 and nxt[:5] == label[:5]:
            out.append(m.group(1))
    return out

def _title_case_headings(body):
    out = []
    for m in re.finditer(r"^#{2,6}\s+(.+)$", body, flags=re.M):
        words = [w for w in re.findall(r"[A-Za-z][\w'-]*", m.group(1))]
        content = [w for w in words[1:] if w.lower() not in _SMALL]
        if len(content) >= 3 and all(w[0].isupper() for w in content) and not all(w.isupper() for w in content):
            out.append(m.group(1).strip()[:50])
    return out

def _p(res, label):
    hardn = len(res["hard_slop"]) + len(res["hard_opener"]) + (1 if res["em_en_dash"] else 0)
    verdict = "BLOCK" if res["hard_hit"] else "CLEAN"
    print(f"== EXTERNAL-SLOP GATE . {verdict} =={(' '+label) if label else ''}")
    if res["em_en_dash"]:
        print(" XX em/en dash present (zero tolerance) . replace with . , ( ) or ->")
    if res["hard_slop"]:
        print(f" XX hard slop: {', '.join(res['hard_slop'])}")
    if res["hard_opener"]:
        print(f" XX AI opener: {', '.join(res['hard_opener'])}")
    for r in res["retracted"]:
        print(f" XX retracted claim ({r['id']}). Use instead: {r['replacement']}")
    if not res["hard_hit"]:
        print(" OK no hard tells")
    if res["warn_slop"]:
        print(f" .. WARN context-legit words (review, not a block): {', '.join(res['warn_slop'])}")
    if res["warn_structural"]:
        for w in res["warn_structural"]:
            print(f" .. WARN structural tell: {w}")
    if res["hard_hit"]:
        print(" FIX: rewrite the flagged spans in plain, specific language. Do NOT")
        print("      inject noise to beat the scan; cut the tell and say the thing.")

def _selftest():
    checks = []
    clean = "We shipped the pipeline in three weeks. It cut manual review by half. The client signed."
    r = scan(clean); checks.append(("clean_passes", not r["hard_hit"]))
    r = scan("Let me help you delve into this tapestry of solutions."); checks.append(("hard_slop_blocks", r["hard_hit"]))
    r = scan("This is a report about revenue - and growth."); checks.append(("hyphen_ok", not r["em_en_dash"]))
    r = scan("This is a report \u2014 about revenue."); checks.append(("emdash_blocks", r["em_en_dash"]))
    r = scan("I am a robust, comprehensive candidate."); checks.append(("warn_no_block", not r["hard_hit"] and len(r["warn_slop"]) >= 2))
    r = scan("I am excited to apply for this role.", cv=True); checks.append(("cv_filler_blocks", r["hard_hit"]))
    r = scan("I am excited to apply for this role.", cv=False); checks.append(("cv_filler_off_by_default", not r["hard_hit"]))
    r = scan("Sure! Here is your answer."); checks.append(("opener_blocks", r["hard_hit"]))
    r = scan("## Why The Global Playbook Fails Locally\nText."); checks.append(("title_case_warns", any("title-case" in w for w in r["warn_structural"]) and not r["hard_hit"]))
    r = scan("## Why the global playbook fails locally\nText."); checks.append(("sentence_case_ok", not any("title-case" in w for w in r["warn_structural"])))
    r = scan("- **Performance:** Performance improved a lot.\n- **Cost:** down 20%."); checks.append(("restated_label_warns", any("restates" in w for w in r["warn_structural"])))
    r = scan("- **Cost:** down 20% after the switch."); checks.append(("plain_label_ok", not any("restates" in w for w in r["warn_structural"])))
    colon = "The answer is simple: you describe the conditions first. The fix was obvious: we cut the step entirely. The pattern holds: every team pays the same tax."
    r = scan(colon); checks.append(("colon_connector_warns", any("colon" in w for w in r["warn_structural"])))
    r = scan("Meeting at 15:00 today. See https://x.com/a:b for details.\nItems:\n- one"); checks.append(("colon_times_urls_ok", not any("colon" in w for w in r["warn_structural"])))
    global RETRACTED
    import tempfile
    saved = RETRACTED
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump({"claims": [{"id": "example-led-acme-deal", "pattern": "led\\s+the\\s+acme\\s+deal",
                               "scope": "cv", "replacement": "supported the Acme deal team",
                               "concept": ["\\b(led|ran|headed|drove)\\b", "\\bacme\\b", "\\b(deal|partnership|contract)\\b"]}]}, tf)
    RETRACTED = tf.name
    try:
        r = scan("Led the Acme deal in 2024", cv=True); checks.append(("retracted_claim_blocks_cv", bool(r["retracted"]) and r["hard_hit"]))
        r = scan("Led the Acme deal in 2024"); checks.append(("retracted_scoped_to_cv", not r["retracted"]))
        r = scan("Headed the partnership with Acme from day one.", cv=True); checks.append(("retracted_paraphrase_blocks", bool(r["retracted"]) and r["hard_hit"]))
        r = scan("Supported the Acme deal team on pricing.", cv=True); checks.append(("canonical_line_passes", not r["retracted"]))
    finally:
        RETRACTED = saved
        os.unlink(tf.name)
    ok = all(v for _, v in checks)
    for n, v in checks:
        print(f" {'PASS' if v else 'FAIL'}  {n}")
    print(f"== SELFTEST {'PASS' if ok else 'FAIL'} ({sum(v for _,v in checks)}/{len(checks)}) ==")
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--cv", action="store_true", help="also HARD-block CV/cover-letter passion-filler")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if _selftest() else 1)
    text = _read(a)
    if text is None:
        print("usage: external_slop_gate.py --file <path> | --stdin  [--cv] [--json]", file=sys.stderr)
        sys.exit(2)
    res = scan(text, cv=a.cv)
    if a.json:
        out = dict(res); out["verdict"] = "BLOCK" if res["hard_hit"] else "CLEAN"; out["label"] = a.label
        print(json.dumps(out, indent=2))
    else:
        _p(res, a.label)
    sys.exit(1 if res["hard_hit"] else 0)

if __name__ == "__main__":
    main()
