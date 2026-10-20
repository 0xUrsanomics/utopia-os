#!/usr/bin/env python3
# structure_repetition.py: advisory detector for one sentence skeleton dominating a draft.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""structure_repetition.py . syntactic-monotony detector (ADVISORY).

WHY THIS EXISTS
  A reviewer caught a long-form draft that reused ONE sentence structure all over: an
  antithesis "not X, it Y" reversal fired 10+ times ("The rules did not stop the
  demand. They moved it." / "The shop is not empty, it is mis-stocked." ...).
  Voice gates that measure 2-word-opener diversity and sentence-LENGTH variation
  missed it: they do not look at repeated
  syntactic TEMPLATES. A draft can vary its openers and its lengths and still
  hammer the same skeleton. This closes that blind spot.

TWO METRICS
  1. antithesis_ratio . fraction of sentences using a negation-contrast /
     reversal template ("not X, it Y" / "not X but Y" / "X did not Y. It Z'd").
  2. top_skeleton_share . the single most-repeated sentence "skeleton" (first 6
     tokens, function words kept verbatim, content words blanked to '#') as a
     share of the sentences considered. High = one structural template dominates.

GUARDRAIL (NON-NEGOTIABLE)
  This measures structural MONOTONY to prompt a HUMAN revision. It is NOT a
  detector to game by mechanically shuffling syntax or sprinkling throwaway
  clauses to defeat the skeleton hash. The fix is VARIED WRITING . real
  sentences built different ways . never noise. A draft that games the metric
  while staying monotone to a reader has failed the point, not passed it.

STATUS: ADVISORY ONLY. main() always exits 0 when it runs (exit 2 = usage
error). Other gates can import structure_metrics()/format_block() and print the
output as an advisory block; it does NOT touch their exit codes or verdicts. The thresholds below are
PROVISIONAL advisory flags; they promote to hard-floors after more calibration
data.

USAGE
  structure_repetition.py --file <path> [--json]
  structure_repetition.py --stdin [--json]
  structure_repetition.py --selftest
"""
import argparse
import json
import re
import sys

# -- PROVISIONAL ADVISORY THRESHOLDS ---------------------------------------
# Calibrated on a POSITIVE control (antithesis crutch, every sentence a
# reversal) vs a NEGATIVE control (a shipped long-form draft). Measured split:
#     antithesis_ratio     positive 0.600  vs  negative 0.060
#     top_skeleton_share   positive 0.154  vs  negative 0.030
# Thresholds set to flag the positive and pass the negative, both with margin.
# antithesis stays at the provisional 0.08 (positive +0.52, negative -0.02).
# top_skeleton lowered from the provisional 0.15 to 0.12: at 0.15 the positive
# cleared by only 0.004 (on the line), so 0.12 gives the positive +0.034 while
# the negative (real shipped prose) still sits ~4x under it at 0.030 (-0.090).
# ADVISORY today; both promote to HARD-FLOORS after more flagged-draft data
# accumulates. Recalibrate on your own corpus before promoting.
ANTITHESIS_RATIO_FLAG = 0.08     # flag if fraction of reversal sentences exceeds
TOP_SKELETON_SHARE_FLAG = 0.12   # flag if one skeleton dominates beyond this

MIN_SKELETON_TOKENS = 5          # sentences shorter than this are ignored for skeletons
SKELETON_PREFIX = 6              # first N tokens form the skeleton

# Hardcoded function/stopword set (per spec). Kept verbatim in a skeleton;
# every other (content) word is blanked to '#'.
FUNCTION_WORDS = {
    "the", "a", "an", "it", "they", "that", "this", "is", "are", "was", "were",
    "not", "but", "and", "or", "of", "to", "in", "on", "for", "with", "as",
    "at", "by", "its", "their", "do", "did", "does", "has", "have", "had",
    "no", "then", "so", "when", "while", "if",
}

# Auxiliaries for the two-sentence reversal ("X did not Y. It Z'd").
_AUX = r"(?:did|does|do|is|are|was|were|has|have|had|will|would|can|could)"

# Bullet 1: "not" followed (within the sentence) by ", it/they/its" OR by "but".
#   e.g. "not empty, it is mis-stocked" / "not a barrier but a moat"
# A 40-char window keeps a stray far-off "but" from false-firing; it matches the
# spirit of bullet 3's {1,40} window and the given examples both sit well inside.
_R1 = re.compile(r"\bnot\b[^.!?]{0,40}?(?:,\s*(?:it|they|its)\b|\bbut\b)", re.I)
# Bullet 2 (first half): an aux + "not" somewhere in THIS sentence...
_R2_AUX = re.compile(r"\b" + _AUX + r"\s+not\b", re.I)
# Bullet 2 (second half): ...and the NEXT sentence opens with It/They/That/Those
# (capitalized, as written in the spec).
_R2_NEXT = re.compile(r"^\s*(?:It|They|That|Those)\b")
# Bullet 3: "not <1-40 non-comma/period chars>, (it|they)" (literal per spec).
_R3 = re.compile(r"\bnot\b [^,.]{1,40}, (?:it|they)\b", re.I)

# frontmatter / fenced code / figure directions / headers stripped before split
_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.S)
_FENCE = re.compile(r"```.*?```", re.S)
_FIGURE = re.compile(r"\[FIGURE:.*?\]", re.S | re.I)
_WORD = re.compile(r"[A-Za-z0-9']+(?:-[A-Za-z0-9']+)*")


def _strip_md(text):
    """Drop frontmatter, fenced code, [FIGURE: ...] directions, headers, and
    inline markdown emphasis so sentence splitting sees prose, not scaffolding.
    Sentence-ending punctuation is preserved (needed by the antithesis rules)."""
    text = _FRONTMATTER.sub(" ", text)
    text = _FENCE.sub(" ", text)
    text = _FIGURE.sub(" ", text)
    kept = []
    for line in text.splitlines():
        if line.strip().startswith("#"):   # markdown headers / subtitles
            continue
        kept.append(line)
    text = "\n".join(kept)
    text = re.sub(r"[*_`>]", "", text)     # emphasis / blockquote markers
    return text


def split_sentences(text):
    """Return a list of sentence STRINGS (punctuation intact). Splits on
    ./!/? boundaries after markdown scaffolding is removed."""
    text = _strip_md(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _tokens(sentence):
    """Word tokens of a sentence (keeps internal apostrophes/hyphens whole:
    don't, out-compete, capital-gains)."""
    return _WORD.findall(sentence)


def antithesis(sents):
    """Count sentences that use a negation-contrast / reversal template.

    A sentence counts AT MOST ONCE. Three templates (bullets in the spec):
      R1  "not ... , it/they/its"  OR  "not ... but"   (within one sentence)
      R2  aux + "not" in this sentence AND next sentence opens It/They/That/Those
      R3  "not <=40 chars, (it|they)"                  (literal window form)
    """
    matched_idx = []
    matched_sentences = []
    n = len(sents)
    for i, s in enumerate(sents):
        hit = False
        if _R1.search(s) or _R3.search(s):
            hit = True
        elif _R2_AUX.search(s) and i + 1 < n and _R2_NEXT.match(sents[i + 1]):
            hit = True
        if hit:
            matched_idx.append(i)
            matched_sentences.append(s)
    count = len(matched_idx)
    ratio = count / n if n else 0.0
    return count, ratio, matched_sentences


def skeleton(sentence):
    """Structural skeleton of a sentence: lowercase the first 6 tokens, keep
    FUNCTION words verbatim, replace every content word with '#'.

    "The rules did not stop the demand" -> "the # did not # the"
    "The market did not die"            -> "the # did not #"
    """
    toks = [t.lower() for t in _tokens(sentence)][:SKELETON_PREFIX]
    return " ".join(t if t in FUNCTION_WORDS else "#" for t in toks)


def top_skeleton(sents):
    """Most-repeated skeleton among sentences with >= MIN_SKELETON_TOKENS
    tokens. Returns (share, top_skeleton_string, top_count, n_considered)."""
    counts = {}
    considered = 0
    for s in sents:
        if len(_tokens(s)) < MIN_SKELETON_TOKENS:
            continue
        considered += 1
        sk = skeleton(s)
        counts[sk] = counts.get(sk, 0) + 1
    if considered == 0:
        return 0.0, "", 0, 0
    top_sk, top_ct = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return top_ct / considered, top_sk, top_ct, considered


def structure_metrics(text):
    """Compute both metrics + supporting detail over `text`. Importable entry."""
    sents = split_sentences(text)
    total = len(sents)
    a_count, a_ratio, a_sents = antithesis(sents)
    sk_share, sk_top, sk_count, sk_considered = top_skeleton(sents)
    return {
        "total_sentences": total,
        "antithesis_ratio": round(a_ratio, 4),
        "antithesis_count": a_count,
        "antithesis_flag": a_ratio > ANTITHESIS_RATIO_FLAG,
        "antithesis_threshold": ANTITHESIS_RATIO_FLAG,
        "antithesis_sentences": a_sents,
        "top_skeleton_share": round(sk_share, 4),
        "top_skeleton": sk_top,
        "top_skeleton_count": sk_count,
        "skeleton_considered": sk_considered,
        "top_skeleton_flag": sk_share > TOP_SKELETON_SHARE_FLAG,
        "top_skeleton_threshold": TOP_SKELETON_SHARE_FLAG,
    }


def format_block(m, indent=" "):
    """Human-readable advisory block. Used standalone AND by importing gates."""
    a_mark = "high" if m["antithesis_flag"] else "OK "
    s_mark = "high" if m["top_skeleton_flag"] else "OK "
    lines = [
        f"{indent}-- structure repetition (advisory, not gating) --",
        f"{indent}{a_mark} antithesis_ratio: {m['antithesis_ratio']:.3f}  "
        f"({m['antithesis_count']}/{m['total_sentences']} sentences, "
        f"flag >{m['antithesis_threshold']})",
        f"{indent}{s_mark} top_skeleton_share: {m['top_skeleton_share']:.3f}  "
        f"(x{m['top_skeleton_count']}/{m['skeleton_considered']}, "
        f"flag >{m['top_skeleton_threshold']})",
    ]
    if m["top_skeleton"]:
        lines.append(f"{indent}    top skeleton: \"{m['top_skeleton']}\"")
    if m["antithesis_flag"] or m["top_skeleton_flag"]:
        lines.append(f"{indent}    FIX = vary the sentence structure by hand "
                     f"(real varied sentences), NOT syntax-shuffling to game it.")
    return "\n".join(lines)


def _selftest():
    """Offline verification on tiny inputs. No files."""
    checks = []

    def chk(name, cond):
        checks.append((name, bool(cond)))

    # skeleton examples from the spec
    chk("skeleton_ex1",
        skeleton("The rules did not stop the demand") == "the # did not # the")
    chk("skeleton_ex2",
        skeleton("The market did not die") == "the # did not #")

    # antithesis: comma-it reversal fires
    _, r, _ = antithesis(split_sentences("The shop is not empty, it is mis-stocked."))
    chk("antithesis_comma_it", r > 0)

    # antithesis: "not X but Y" fires
    _, r, _ = antithesis(split_sentences("This is not a barrier but a moat."))
    chk("antithesis_not_but", r > 0)

    # antithesis: two-sentence "did not ... It ..." reversal fires
    _, r, _ = antithesis(split_sentences("The rules did not stop the demand. They moved it."))
    chk("antithesis_two_sentence", r > 0)

    # antithesis: next sentence NOT opening It/They/That/Those does not fire R2
    c, _, _ = antithesis(split_sentences("It did not solve anything. Speed got mistaken for direction."))
    chk("antithesis_r2_needs_pronoun_start", c == 0)

    # a plain declarative with no reversal scores zero
    c, _, _ = antithesis(split_sentences("The market grew last year. Volume climbed steadily."))
    chk("antithesis_clean_is_zero", c == 0)

    # skeleton dedup: two identical-shape sentences share one skeleton
    share, top, cnt, considered = top_skeleton(split_sentences(
        "The market did not die. The signal did not fade."))
    chk("skeleton_share_repeat", cnt == 2 and considered == 2 and abs(share - 1.0) < 1e-9)

    # short sentences (< 5 tokens) are excluded from skeletons
    _, _, _, considered = top_skeleton(split_sentences("They moved it. Go now."))
    chk("skeleton_excludes_short", considered == 0)

    # full metrics dict is well-formed
    m = structure_metrics("The market did not die. It is only waiting to be served right.")
    chk("metrics_keys", "antithesis_ratio" in m and "top_skeleton_share" in m)

    passed = sum(1 for _, ok in checks if ok)
    for name, ok in checks:
        print(f" {'PASS' if ok else 'FAIL'}  {name}")
    allok = passed == len(checks)
    print(f"== SELFTEST {'PASS' if allok else 'FAIL'} ({passed}/{len(checks)}) ==")
    return allok


def main():
    ap = argparse.ArgumentParser(description="Advisory syntactic-monotony detector.")
    ap.add_argument("--file", help="path to a text/markdown file to analyze")
    ap.add_argument("--stdin", action="store_true", help="read text from stdin")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--selftest", action="store_true", help="offline self-check; no files")
    a = ap.parse_args()

    if a.selftest:
        # selftest reports its own pass/fail via exit code (1 on failure) so it
        # is usable in CI; the normal analysis path is advisory and exits 0.
        sys.exit(0 if _selftest() else 1)

    if a.file and a.stdin:
        print("structure_repetition: use --file OR --stdin, not both", file=sys.stderr)
        sys.exit(2)
    if not a.file and not a.stdin:
        print("structure_repetition: need --file <path> or --stdin (or --selftest)",
              file=sys.stderr)
        sys.exit(2)

    if a.stdin:
        text = sys.stdin.read()
    else:
        try:
            text = open(a.file, encoding="utf-8").read()
        except OSError as e:
            print(f"structure_repetition: {e}", file=sys.stderr)
            sys.exit(2)

    m = structure_metrics(text)

    if a.json:
        print(json.dumps(m, indent=2))
    else:
        src = a.file if a.file else "<stdin>"
        print(f"== STRUCTURE REPETITION (advisory) ==")
        print(f" source: {src}  ({m['total_sentences']} sentences)")
        print(format_block(m, indent=" "))

    # ADVISORY: always exit 0 when it ran. This is a prompt-a-human signal, not
    # a gate. (Usage errors above exit 2.)
    sys.exit(0)


if __name__ == "__main__":
    main()
