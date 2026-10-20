#!/usr/bin/env python3
# paraphrase_test.py: lexical gate for insight-shaped filler and transplantable sentences.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
paraphrase_test.py . the "insight-shaped writing" gate. Idea source: a16z crypto, Steph Zinn,
"The habits of AI writing" (2026-08-25).

WHY THIS EXISTS (the gap it closes). external_slop_gate.py catches WORD/phrase tells
(delve, tapestry, em dash). A voice-density check catches SMOOTHING statistically. NEITHER catches
INSIGHT-SHAPED writing: a sentence that sounds profound but is semantically vacant, that
does not survive paraphrase ("something real is happening", "the stakes couldn't be
higher"). Zinn's frame: stop asking "is it AI", ask "is it doing its job". A sentence that
paraphrases down to "stuff exists / things are changing" is filler regardless of provenance.

TWO TESTS (from the article):
  1. PARAPHRASE: restate the sentence plainly. If it collapses to "stuff exists" or
     "things are changing", it never meant anything. Cut it.
  2. TRANSPLANT: could a stranger drop this sentence, word for word, into an unrelated
     essay on a different topic with nobody noticing? If yes it is fungible (no voice,
     no specificity). Rework it.

TWO LAYERS:
  LEXICAL (default, deterministic, $0, no network): flags the article's named tells that
    ARE pattern-detectable . insight-shaped phrases, recyclable phrasing, abstract-noun
    density, vague intensifiers, empty contrasts, gestures-vaguely nouns. Advisory (WARN):
    insight-shaped detection is fuzzier than a wordlist, so it SURFACES, does not block,
    unless --enforce. This is deliberately NOT in external_slop_gate (different axis).
  --llm (optional, a second "reader" model): the real judgment. Runs the paraphrase +
    transplant tests sentence by sentence via an LLM and returns the sentences that fail.
    Fail-open: if no engine is reachable, it says so and the lexical result still stands.

WHAT IT IS NOT. Not a voice gate. Not an AI-detector to game (never inject noise; cut the
tell, say the thing). Not a word-tell gate (that stays external_slop_gate). Advisory by default.

READER MODEL for --llm: $PARAPHRASE_LLM_CMD if set (a command line; the prompt is appended as
its last argument, e.g. "my-model-cli -p"), else `claude --print` if on PATH. The child gets the
long-lived setup credential via scripts/lib/lib_claude_child_env.py (fail-open).

USAGE
  paraphrase_test.py --file <path>            # lexical scan (advisory)
  paraphrase_test.py --stdin                  # scan stdin
  paraphrase_test.py --file X --llm           # add the LLM paraphrase/transplant pass
  paraphrase_test.py --file X --enforce       # make lexical findings exit 1 (block)
  paraphrase_test.py --file X --json          # machine-readable
  paraphrase_test.py --selftest               # offline self-check, no file needed
  exit 0 = clean or advisory-only | 1 = findings under --enforce | 2 = usage/error
"""
import sys, re, argparse, json, subprocess, shutil, os, tempfile

# -- INSIGHT-SHAPED: sounds profound, means nothing. "naturally essenced profundity". --
INSIGHT_SHAPED = [
    "something real is happening", "something profound is happening",
    "something important is happening", "something big is happening",
    "the stakes couldn't be higher", "the stakes could not be higher",
    "the stakes have never been higher", "the implications are significant",
    "the implications are profound", "the implications are staggering",
    "this changes everything", "this is bigger than", "this matters for",
    "we're at an inflection point", "at an inflection point",
    "we are at an inflection point", "we're at a turning point",
    "the next chapter", "a new chapter", "the next frontier", "a new era",
    "a paradigm shift", "a fundamental shift", "a seismic shift",
    "now more than ever", "the future is here", "this is the future",
    "the world is changing", "the world has changed", "change is coming",
]
# -- RECYCLABLE PHRASING: transplant-test failures, fungible connective tissue. --
RECYCLABLE = [
    "a useful way to think about it is", "a useful way to think about this is",
    "the key idea is", "the key insight is", "the key takeaway is",
    "this can be understood as", "this is best understood as",
    "at its core", "at a fundamental level", "when you really think about it",
    "it's important to understand", "the reality is that", "the fact of the matter is",
    "one way to think about", "it all comes down to",
]
# -- VAGUE INTENSIFIERS: signal weight, carry none (esp. with nothing concrete behind). --
VAGUE_INTENSIFIER = [
    "very important", "highly significant", "significant impact", "major role",
    "critically important", "increasingly important", "hugely important",
    "plays a key role", "plays a vital role", "plays a crucial role",
    "a significant amount", "a wide range of", "a variety of",
]
# -- GESTURES VAGUELY: point to the vicinity of a thing, not the thing (Zinn). --
#    "space"/"arena"/"sphere" only in the "the X space" shape, checked by regex below.
GESTURE_NOUNS = ["landscape", "journey", "tapestry", "realm", "ecosystem"]
# -- ABSTRACT NOUNS: saying nothing in 3+ syllables. Density-checked, not per-hit. --
ABSTRACT_NOUNS = [
    "efficiency", "complexity", "society", "communication", "innovation",
    "scalability", "optimization", "transformation", "disruption", "connectivity",
    "functionality", "capability", "methodology", "synergy", "momentum",
    "paradigm", "framework", "granularity", "modularity", "interoperability",
]

DASH = re.compile("[\u2014\u2013]")  # em dash, en dash

def _strip_md(md):
    md = re.sub(r"^---\n.*?\n---\n", "", md, flags=re.S)   # frontmatter
    md = re.sub(r"`{1,3}[^`]*`{1,3}", " ", md)             # code spans
    md = re.sub(r"^#{1,6}\s+", "", md, flags=re.M)         # header marks
    return md

def _phrase_hits(low, phrases):
    return [p for p in phrases if p in low]

def _word_count(body):
    return max(1, len(re.findall(r"\b\w+\b", body)))

def scan(text):
    body = _strip_md(text)
    low = body.lower()
    wc = _word_count(body)
    # gestures: plain gesture nouns + the "the X space/arena/sphere" shape
    gestures = _phrase_hits(low, GESTURE_NOUNS)
    for m in re.findall(r"\bthe\s+([a-z]+)\s+(space|arena|sphere)\b", low):
        gestures.append(f"the {m[0]} {m[1]}")
    # abstract-noun density (per 100 words); list the offenders
    abs_hits = [w for w in ABSTRACT_NOUNS if re.search(r"\b" + w + r"\b", low)]
    abs_count = sum(len(re.findall(r"\b" + w + r"\b", low)) for w in ABSTRACT_NOUNS)
    abs_density = round(abs_count / wc * 100, 2)
    # empty contrast: "not just X ... but Y" / "isn't about ... it's about"
    empty_contrast = []
    if re.search(r"\bnot just\b[^.]{0,70}\bbut\b", low):
        empty_contrast.append("not just X ... but Y (check Y is not fuzzier than X)")
    if re.search(r"\bisn't (just )?about\b[^.]{0,60}\bit'?s about\b", low):
        empty_contrast.append("isn't about X, it's about Y")
    res = {
        "insight_shaped": _phrase_hits(low, INSIGHT_SHAPED),
        "recyclable": _phrase_hits(low, RECYCLABLE),
        "vague_intensifier": _phrase_hits(low, VAGUE_INTENSIFIER),
        "gestures_vaguely": sorted(set(gestures)),
        "empty_contrast": empty_contrast,
        "abstract_noun_density": abs_density,
        "abstract_nouns": abs_hits,
        "word_count": wc,
    }
    # a "finding" = any surfaced tell. abstract-noun density flags only above a floor.
    n = (len(res["insight_shaped"]) + len(res["recyclable"]) +
         len(res["vague_intensifier"]) + len(res["gestures_vaguely"]) +
         len(res["empty_contrast"]) + (1 if abs_density >= 2.5 else 0))
    res["findings"] = n
    res["abstract_density_flag"] = abs_density >= 2.5
    return res

# ---------- optional LLM paraphrase/transplant pass (reader model) ----------
LLM_PROMPT = """You are a prose editor running the paraphrase and transplant tests on a draft. For EACH sentence apply two tests.
1. PARAPHRASE: restate it plainly. If the restatement collapses to "stuff exists" or "things are changing" (it survives paraphrase into vacancy), it is INSIGHT-SHAPED filler.
2. TRANSPLANT: could a stranger drop this exact sentence into an unrelated essay on a different topic with nobody noticing? If yes it is FUNGIBLE (no voice, no specificity).
Return ONLY the sentences that FAIL a test. For each: the sentence (quoted), which test failed (PARAPHRASE or TRANSPLANT), and a one-line concrete rewrite or the word cut. No preamble. No em dashes (use periods, commas, parentheses). If every sentence passes, return exactly the token CLEAN on its own line.

DRAFT:
---
%s
---"""

def _llm_pass(body, timeout=180):
    """Run the semantic paraphrase/transplant test. Fail-open: returns (ok, text)."""
    import shlex
    prompt = LLM_PROMPT % body.strip()
    engines = []
    custom = os.environ.get("PARAPHRASE_LLM_CMD", "").strip()
    if custom:
        parts = shlex.split(custom)
        exe = shutil.which(parts[0]) or parts[0]
        engines.append((os.path.basename(parts[0]), [exe] + parts[1:] + [prompt]))
    claude = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    # untrusted text goes into this prompt: no tools, no MCP, no saved session, run from a neutral cwd
    engines.append(("claude", [claude, "--print", "--tools", "", "--strict-mcp-config", "--no-session-persistence", prompt]))
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
        from lib_claude_child_env import child_env
        env = child_env()
    except Exception:
        env = dict(os.environ)
    for engine, cmd in engines:
        if not (cmd[0] and os.path.exists(cmd[0])):
            continue
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=tempfile.gettempdir(), env=env)
            txt = (out.stdout or "").strip()
            low = txt.lower()
            if txt and not any(s in low for s in
                    ("no output produced", "auto-denied", "headless mode cannot prompt")):
                txt = DASH.sub("-", txt)   # engines can emit dashes; rule forbids them
                return True, f"[{engine}] " + txt
        except Exception:
            continue
    return False, "(no LLM engine reachable . lexical result stands; run --llm later)"

def _p(res, label, llm_text=None):
    verdict = "FINDINGS" if res["findings"] else "CLEAN"
    print(f"== PARAPHRASE / INSIGHT-SHAPED GATE . {verdict} =={(' '+label) if label else ''}")
    if res["insight_shaped"]:
        print(f" .. insight-shaped (sounds deep, empty): {', '.join(res['insight_shaped'])}")
    if res["recyclable"]:
        print(f" .. recyclable phrasing (transplant-fail): {', '.join(res['recyclable'])}")
    if res["vague_intensifier"]:
        print(f" .. vague intensifier (weight, no concrete): {', '.join(res['vague_intensifier'])}")
    if res["gestures_vaguely"]:
        print(f" .. gestures vaguely (vicinity, not the thing): {', '.join(res['gestures_vaguely'])}")
    if res["empty_contrast"]:
        for c in res["empty_contrast"]:
            print(f" .. empty contrast: {c}")
    if res["abstract_density_flag"]:
        print(f" .. abstract-noun density {res['abstract_noun_density']}/100w (>=2.5): {', '.join(res['abstract_nouns'])}")
    if not res["findings"]:
        print(" OK no lexical insight-shaped tells")
    print(" TEST: paraphrase each flagged span. if it restates to 'stuff exists /")
    print("       things change', cut it. if a stranger could claim it, rework it.")
    if llm_text is not None:
        print("-- LLM paraphrase/transplant pass --")
        print(llm_text)

def _selftest():
    checks = []
    clean = ("We shipped the pipeline in three weeks. It cut manual review by half. "
             "The client signed on a Tuesday. The export moved 1.25 million rows that week.")
    r = scan(clean); checks.append(("clean_passes", r["findings"] == 0))
    r = scan("Something real is happening in this market right now.")
    checks.append(("insight_shaped_flags", "something real is happening" in r["insight_shaped"]))
    r = scan("A useful way to think about it is that the key idea is scale.")
    checks.append(("recyclable_flags", len(r["recyclable"]) >= 2))
    r = scan("This has a very important, significant impact on the sector.")
    checks.append(("vague_intensifier_flags", len(r["vague_intensifier"]) >= 2))
    r = scan("The fintech space is a fast-moving landscape on a journey.")
    checks.append(("gestures_flag", len(r["gestures_vaguely"]) >= 2))
    r = scan("Innovation drives efficiency, complexity, and transformation across the paradigm.")
    checks.append(("abstract_density_flags", r["abstract_density_flag"]))
    r = scan("It's not just about the tech, but about the vision.")
    checks.append(("empty_contrast_flags", len(r["empty_contrast"]) >= 1))
    ok = all(v for _, v in checks)
    for n, v in checks:
        print(f" {'PASS' if v else 'FAIL'}  {n}")
    print(f"== SELFTEST {'PASS' if ok else 'FAIL'} ({sum(v for _,v in checks)}/{len(checks)}) ==")
    return ok

def _read(a):
    if a.stdin:
        return sys.stdin.read()
    if a.file:
        with open(a.file, encoding="utf-8", errors="replace") as f:
            return f.read()
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--llm", action="store_true", help="add the reader-model paraphrase/transplant pass")
    ap.add_argument("--enforce", action="store_true", help="make lexical findings exit 1 (default: advisory, exit 0)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if _selftest() else 1)
    text = _read(a)
    if text is None:
        print("usage: paraphrase_test.py --file <path> | --stdin  [--llm] [--enforce] [--json]", file=sys.stderr)
        sys.exit(2)
    res = scan(text)
    llm_text = None
    if a.llm:
        _, llm_text = _llm_pass(_strip_md(text))
    if a.json:
        out = dict(res)
        out["verdict"] = "FINDINGS" if res["findings"] else "CLEAN"
        out["label"] = a.label
        if llm_text is not None:
            out["llm_pass"] = llm_text
        print(json.dumps(out, indent=2))
    else:
        _p(res, a.label, llm_text)
    sys.exit(1 if (res["findings"] and a.enforce) else 0)

if __name__ == "__main__":
    main()
