#!/usr/bin/env python3
# imported_claim_gate.py: flag claim shapes (legal status, counts, existence) that need a primary-source check.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Flag load-bearing IMPORTED factual claims in a draft that need a conflict-check.

WHY THIS EXISTS. A port of the "conflict-activated verification" pattern from
Intent-Guided Decoding (arXiv 2608.16515). The paper's decoding-level branches
do not port (no hosted-logit access), but the PATTERN does: only intervene when
a claim imported from memory / worldview / a harvester could DISAGREE with a
primary source. Verify-on-conflict, not verify-everything.

Typical misses it targets: "the GENIUS Act made stablecoins legal" (wrong),
"a charter made one issuer safe" (count wrong). Those are load-bearing IMPORTED
claims: recalled from worldview, never checked against a primary source before
they went into a draft.

WHAT IT DOES, AND ITS HONEST BOUND. This is a FLAGGER, not a verifier. It scans
for claim SHAPES that are high-risk when imported (legal/regulatory status,
entity-count/superlative, existence). For each hit it says: conflict-check this
against a primary source before ship. It CANNOT auto-verify, by design: there is
no per-claim source map, so which primary source settles a given claim is an
agent decision. Do not read a clean exit as "the claims are true"; read it as
"no high-risk imported shapes were found to flag".

INTENT MODE. Two reading modes, from the paper's faithfulness/factuality split:
  STRICT  (faithfulness): quoting what a specific doc SAYS -> trust the doc.
  TRUTH   (factuality):   asserting a public claim -> distrust worldview memory,
                          prefer the PRIMARY source.
This gate is for TRUTH-mode drafts. On a STRICT-mode draft (you are faithfully
reporting a source's own words) the flags are expected noise; skip it.

Usage:
    imported_claim_gate.py --file draft.md      # scan a file
    cat draft.md | imported_claim_gate.py       # scan stdin
    imported_claim_gate.py --file d.md --json   # machine-readable
    imported_claim_gate.py --selftest           # run built-in fixture

Exit: 0 = no high-risk imported claims found; 3 = claims flagged (advisory,
surfaced for agent-driven conflict-check, NOT an auto-block).
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# Each entry: (risk_class, compiled_regex). A sentence matching any pattern is
# flagged under that class. Patterns are deliberately shape-based, not a
# content wordlist: they catch the GRAMMAR of a load-bearing assertion.
LEGAL_STATUS = [
    re.compile(r"\bmade\b[^.\n]{0,40}\b(?:il)?legal\b", re.I),
    re.compile(r"\b(?:il)?legaliz(?:e|es|ed|ing)\b", re.I),
    re.compile(r"\bis\s+(?:il)?legal\b", re.I),
    re.compile(r"\bban(?:ned|s|ning)?\b", re.I),
    re.compile(r"\bprohibit(?:s|ed|ion)?\b", re.I),
    re.compile(r"\boutlaw(?:s|ed)?\b", re.I),
    re.compile(r"\brequire(?:s|d|ment|ments)?\b", re.I),
    re.compile(r"\bmandat(?:e|es|ed|ory)\b", re.I),
    re.compile(r"\bregulat(?:e|es|ed)\b", re.I),
    re.compile(r"\bauthoriz(?:e|es|ed)\b", re.I),
    re.compile(r"\bsanction(?:s|ed)?\b", re.I),
    # curated named regulatory instruments (case-insensitive). Add your own jurisdiction's.
    re.compile(r"\b(?:MiCA|MiFID|GDPR|Dodd[- ]Frank|Howey|Basel\s+III?|"
               r"GENIUS\s+Act|CLARITY\s+Act)\b", re.I),
    # generic "<Name> Act" (case-sensitive: a capitalized token before "Act")
    re.compile(r"\b[A-Z][A-Za-z]+\s+Act\b"),
]

ENTITY_COUNT = [
    re.compile(r"\bthe\s+first\b", re.I),
    re.compile(r"\bthe\s+only\b", re.I),
    re.compile(r"\bthe\s+(?:largest|biggest|smallest|leading|most|highest|lowest|top)\b", re.I),
    re.compile(r"\bworld'?s\s+(?:first|only|largest|biggest|leading)\b", re.I),
    re.compile(r"\b\d[\d,]*\s+(?:issuers?|companies|company|charters?|firms?|banks?|"
               r"licen[sc]es?|entities|providers?|exchanges?|projects?|protocols?|players?)\b", re.I),
]

EXISTENCE = [
    re.compile(r"\bdoes\s+not\s+exist\b", re.I),
    re.compile(r"\bdo\s+not\s+exist\b", re.I),
    re.compile(r"\bdoesn'?t\s+exist\b", re.I),
    re.compile(r"\bno\s+such\b", re.I),
    re.compile(r"\bthe\s+only\s+way\b", re.I),
    re.compile(r"\bthere\s+(?:is|are|'?s)\s+no\b", re.I),
    re.compile(r"\bno\s+(?:tool|way|method|option|alternative|solution)\b", re.I),
    re.compile(r"\bnever\s+been\s+done\b", re.I),
    re.compile(r"\bnobody\s+(?:has|can)\b", re.I),
]

RISK_CLASSES = [
    ("LEGAL_STATUS", LEGAL_STATUS),
    ("ENTITY_COUNT", ENTITY_COUNT),
    ("EXISTENCE", EXISTENCE),
]

INSTRUCTION = "CONFLICT-CHECK vs primary source before ship; block if the imported claim conflicts."
BOUND = ("FLAGGER not verifier: this flags claim shapes; it does NOT verify them "
         "(no per-claim source map). Verification is agent-driven.")
INTENT_NOTE = ("INTENT-MODE: this gate is for TRUTH-mode drafts (factuality: a public claim -> "
               "distrust worldview/memory, prefer PRIMARY source). In STRICT-mode "
               "(faithfulness: quoting what a specific doc says -> trust the doc) the flags "
               "are expected noise; skip.")

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str):
    for seg in _SENT_SPLIT.split(text):
        seg = seg.strip()
        if seg:
            yield seg


def _clip(s: str, n: int = 160) -> str:
    return s if len(s) <= n else s[: n - 3].rstrip() + "..."


def scan(text: str):
    """Return a list of per-sentence hits: {phrase, classes, triggers}."""
    hits = []
    for sent in _sentences(text):
        classes, triggers = [], []
        for risk_class, patterns in RISK_CLASSES:
            for rx in patterns:
                m = rx.search(sent)
                if m:
                    if risk_class not in classes:
                        classes.append(risk_class)
                    trig = m.group(0).strip()
                    if trig not in triggers:
                        triggers.append(trig)
        if classes:
            hits.append({"phrase": _clip(sent), "classes": classes, "triggers": triggers})
    return hits


def _selftest() -> int:
    fixture = (
        "The GENIUS Act made stablecoins legal in the United States.\n"
        "It was the first layer 1 to do it.\n"
        "We grabbed coffee and talked about the roadmap over the weekend.\n"
    )
    hits = scan(fixture)
    flagged_phrases = [h["phrase"] for h in hits]
    problems = []

    genius = [h for h in hits if "GENIUS Act" in " ".join(h["triggers"])
              or "made stablecoins legal" in h["phrase"]]
    if not genius:
        problems.append("MISS: 'the GENIUS Act made stablecoins legal' was not flagged")
    elif "LEGAL_STATUS" not in genius[0]["classes"]:
        problems.append("WRONGCLASS: GENIUS-Act claim not tagged LEGAL_STATUS")

    first = [h for h in hits if "the first" in h["phrase"].lower()]
    if not first:
        problems.append("MISS: 'the first layer 1' was not flagged")
    elif "ENTITY_COUNT" not in first[0]["classes"]:
        problems.append("WRONGCLASS: 'the first' claim not tagged ENTITY_COUNT")

    benign = [p for p in flagged_phrases if "coffee" in p.lower()]
    if benign:
        problems.append("FALSE-POSITIVE: benign sentence was flagged")

    if len(hits) != 2:
        problems.append(f"COUNT: expected 2 flagged sentences, got {len(hits)}")

    print("selftest fixture:")
    for h in hits:
        print(f"  FLAG [{','.join(h['classes'])}] {h['phrase']}  <- {h['triggers']}")
    print(f"  flagged sentences: {len(hits)} (expected 2)")
    if problems:
        print("SELFTEST FAIL:")
        for p in problems:
            print("  - " + p)
        return 1
    print("SELFTEST PASS: 2 risky claims flagged, benign not flagged.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Flag load-bearing imported claims needing a conflict-check.")
    ap.add_argument("--file", help="draft file to scan (default: stdin)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--selftest", action="store_true", help="run built-in fixture and exit")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()

    if a.file:
        with open(a.file, encoding="utf-8") as f:
            text = f.read()
    else:
        if sys.stdin.isatty():
            ap.error("no input: pass --file PATH or pipe text on stdin")
        text = sys.stdin.read()

    hits = scan(text)

    if a.json:
        print(json.dumps({
            "mode": "TRUTH-gate",
            "intent_note": INTENT_NOTE,
            "flagged": len(hits),
            "hits": [{**h, "instruction": INSTRUCTION} for h in hits],
            "bound": BOUND,
        }, indent=2))
    else:
        print(INTENT_NOTE)
        print(BOUND)
        print()
        if not hits:
            print("clear: no high-risk imported claim shapes found.")
        else:
            for h in hits:
                print(f"FLAG [{', '.join(h['classes'])}]")
                print(f'  "{h["phrase"]}"')
                print(f"  triggers: {', '.join(h['triggers'])}")
                print(f"  {INSTRUCTION}")
                print()
            print(f"{len(hits)} claim(s) flagged for conflict-check (advisory, not an auto-block).")

    return 3 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
