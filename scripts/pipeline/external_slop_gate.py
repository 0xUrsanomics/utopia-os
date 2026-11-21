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
          + retracted claims + rejected phrases. A hit exits 1 (block). These are
          almost never legitimate in external output.
  WARN  = words that are context-legit in a formal register (robust, comprehensive,
          leverage...) + structural tells. Printed for review, do NOT change the
          exit code. This is what keeps a real professional deck from tripping.
  STRUCTURAL. Line-numbered, partly HARD:
    antithesis "X, not Y" family: BLOCK when a slogan-length (<=12 words), digit-free
              hit sits in a headline, TL;DR bullet, first sentence of a paragraph or
              last sentence of a section; WARN elsewhere.
    staccato  3+ consecutive sentences of <=6 words in one paragraph: BLOCK
              (tweets: WARN, via --tweet or '1/ 2/' numbering).
    opinion   "my bet/guess/take/... is", "I read this as": BLOCK when count >
              max(1, prose_words/1500) or 2+ in one section; a single one WARNs.
    Owner-verbatim escape: '>' lines in the text, or sentences found in '>' lines of
    --verbatim FILE (auto: verbatim-approved.md / interview-quotes.md / interview.md beside
    --file). Lines the owner approves in chat go in verbatim-approved.md, not
    interview-quotes.md, so they do not feed a voice gate's anchor score.
  COPY-EDIT. See copyedit():
    aphorism  3+ ## sections ending on a two-sentence kicker: BLOCK (1-2, or tweets: WARN).
    unused    "which I will call X" / "(X from here)", marked X never used again: BLOCK.
    WARN only: forward reference "(same report)" with no source earlier in its section,
              1-3 stray contractions in a 1,500+ word uncontracted text, one word spelled
              two ways (start-up/startup, tokenised/tokenized), hedge drift ("about 72%"
              in one place, "72%" in another).

USAGE
  external_slop_gate.py --file <path>          # scan a file
  external_slop_gate.py --stdin                # scan stdin
  external_slop_gate.py --file X --json        # machine-readable
  external_slop_gate.py --cv                   # add CV/cover-letter filler to HARD
  external_slop_gate.py --tweet                # tweet register (staccato and aphorism only warn)
  external_slop_gate.py --verbatim FILE        # extra owner-verbatim '>' lines (repeatable)
  external_slop_gate.py --structural-warn      # structural and copy-edit hits never block
  external_slop_gate.py --selftest             # offline self-check, no file needed
  exit 0 = clean (no HARD hit) | 1 = HARD hit (block, fix before ship) | 2 = usage/error

RETRACTED CLAIMS. A correction recorded only as a prose lesson has to be remembered at copy time,
and stale drafts get copied anyway. So a JSON registry of retracted claims is a HARD block:
  {"claims": [{"id": "...", "pattern": "<regex>", "scope": "all" | "cv", "replacement": "..."}]}
Path: $AGENT_RETRACTED_CLAIMS, default $AGENT_ROOT/knowledge/retracted-claims.json (start from
knowledge/retracted-claims.example.json). Missing or
broken registry = no retracted-claim checks (it never blocks on its own).

REJECTED PHRASES. Phrases the owner has rejected in their written voice ("needless to say",
...). ANY occurrence is a HARD block with no quota, so this overrides the opinion quota above for
the listed phrases. Exempt only: '>' lines in the text, and sentences found in '>' lines of
verbatim-approved.md (beside --file, or passed as --verbatim). interview.md and
interview-quotes.md do NOT exempt them. --structural-warn does not downgrade them.
  {"phrases": [{"phrase": "...", "source": "...", "added": "YYYY-MM-DD"}]}
Path: $AGENT_REJECTED_PHRASES, default $AGENT_ROOT/knowledge/rejected-phrases.json (start from
knowledge/rejected-phrases.example.json). No file = the check is off (printed as a note). A file
that exists but is unreadable or lists no phrase is a HARD block: a check that ran nothing is
not a pass.
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

# ---------------------------------------------------------------------------
# STRUCTURAL CHECKS:
#   ANTITHESIS  the "X, not Y" family ("tickets, not rides", "not X but Y",
#               "isn't X. It's Y", "less X, more Y").
#   STACCATO    3+ consecutive very short sentences inside one paragraph.
#   OPINION     "my bet is / my guess is / my take is ..." marker overuse.
# Each hit carries a line number. Blocking rules were calibrated on a small
# corpus of published long-form pieces, drafts, tweet drafts, a CV, a cover
# letter and daily briefings (see docs/content-gates.md). Owner-verbatim text is exempt: a
# blockquote line ('>') in the scanned text, or a sentence that appears in a
# '>' line of a verbatim file (interview.md / interview-quotes.md, the same
# convention a voice gate reads). Caller overrides apply unchanged because
# these feed hard_hit like every other HARD check.
# Reuse: the single-sentence "not X, it Y" / "not X but Y" regexes come from
# structure_repetition.py (_R1, _R3). Its two-sentence rule has no contractions
# ("isn't") and nothing catches the ", not Y" tail, so those are added here.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import structure_repetition as _sr  # noqa: E402

STACCATO_MAX_WORDS = 6        # a sentence this short or shorter counts toward a run
STACCATO_MIN_RUN = 3          # run length that blocks (prose); tweets only warn
SLOGAN_MAX_WORDS = 12         # an antithesis this short reads as a slogan
OPINION_WORDS_PER_MARKER = 1500  # allowed markers = max(1, prose_words / 1500)
OPINION_MAX_PER_SECTION = 1
PROMINENT = ("headline", "tldr", "first-sentence", "closing")

_NEG_SKIP = r"(?!only\b|just\b|least\b|yet\b|until\b|because\b|even\b|always\b|necessarily\b|so\b|to\b|that\b|all\b|every\b|enough\b|counting\b|including\b)"
_A_TAIL = re.compile(r",\s+not\s+" + _NEG_SKIP + r"[^,;:!?]{1,60}[.!?]?\s*$", re.I)
_A_LESSMORE = re.compile(r"\b(?:less|fewer|more)\s+[\w$-]+(?:\s+[\w$-]+){0,3},\s+(?:more|less|fewer)\s+\w", re.I)
_NEG_AUX = re.compile(r"\b(?:isn't|aren't|wasn't|weren't|doesn't|don't|didn't|won't|can't|is not|are not|was not|"
                      r"were not|does not|do not|did not|will not|cannot|has not|have not|hasn't|haven't|never)\b", re.I)
_A_NEXT = re.compile(r"^(?:It|It's|It is|They|They're|They are)\b", re.I)
# "not a barrier but a moat" counts; a comma before "but" is a concession ("not signed yet, but the
# draft is public") and does not. structure_repetition._R1 counts both, so only its _R3 is reused.
_A_NOTBUT = re.compile(r"\bnot\b(?!\s+only\b)[^.!?,;:]{1,40}?\s+but\b(?!\s+also\b)", re.I)
_A_NOTSTART = re.compile(r"^Not\b", re.I)
_OPINION = re.compile(
    r"\bmy\s+(?:own\s+|honest\s+|working\s+)?(?:reading|read|view|opinion|bet|guess|take|pick)\b"
    r"(?:\s+(?:here|now|today|of\s+\w+(?:\s+\w+)?))?\s*(?:is|was|:)"
    r"|\bI\s+read\s+(?:this|that|it|these|those|them)\s+as\b", re.I)
_WORDRX = re.compile(r"[A-Za-z0-9$%][\w$%.,'/-]*")
_QUOTED = re.compile(r"\"[^\"\n]{1,300}\"|“[^”\n]{1,300}”")
_NOT_FOR_POSTING = re.compile(r"<!--\s*not for posting", re.I)
_TWEET_NUM = re.compile(r"^\s*\d{1,2}/\s", re.M)


def _nwords(s):
    return len(_WORDRX.findall(s))


def _norm(s):
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def load_verbatim(path):
    """Operator-verbatim lines = markdown blockquote lines ('>') of an interview
    file."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [_norm(l.lstrip()[1:]) for l in f if l.lstrip().startswith(">") and l.strip() != ">"]
    except OSError:
        return []


def _is_verbatim(s, verbatim):
    n = _norm(s)
    return len(n.split()) >= 3 and any(f" {n} " in f" {v} " for v in verbatim)


def _mask(s):
    """Hide what is not the writer's own claim: tweet numbering, inline html,
    quoted spans and parentheticals (a "(accounts, not people)" gloss)."""
    s = re.sub(r"^\d+/\s*", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = _QUOTED.sub(lambda m: "Q" * len(m.group(0)), s)
    return re.sub(r"\([^()]*\)", lambda m: "Q" * len(m.group(0)), s)


def _clean_inline(s):
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"`[^`]*`", " ", s)
    return re.sub(r"[*_]{1,3}", "", s)


def _units(text):
    """Split into (kind, section, [(line, text)]) units with ORIGINAL 1-based line
    numbers. kind = heading | item | para | quote. Drops frontmatter, fences,
    tables, html comments and anything below a 'not for posting' marker."""
    text = re.sub(r"<!--(?!\s*not for posting)(.*?)-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S | re.I)
    lines = text.split("\n")
    i0 = 0
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                i0 = j + 1
                break
    units, cur, section, fence = [], [], 0, False

    def flush():
        nonlocal cur
        if cur:
            units.append(("para", section, cur))
            cur = []

    for idx in range(i0, len(lines)):
        ln, st = idx + 1, lines[idx].strip()
        if _NOT_FOR_POSTING.search(st):
            break
        if st.startswith("```"):
            fence = not fence
            flush()
            continue
        if fence:
            continue
        if not st or st.startswith("|"):
            flush()
            continue
        if st.startswith("#"):
            flush()
            section += 1
            units.append(("heading", section, [(ln, st.lstrip("#").strip())]))
            continue
        if st.startswith(">"):
            flush()
            units.append(("quote", section, [(ln, st.lstrip("> ").strip())]))
            continue
        mi = re.match(r"^(?:[-*+•]|\d+[.)])\s+(.*)$", st)
        if mi:
            flush()
            units.append(("item", section, [(ln, mi.group(1))]))
            continue
        cur.append((ln, st))
    flush()
    return units


def _sentences(unit_lines):
    out = []
    for ln, t in unit_lines:
        t = re.sub(r"\b(e\.g|i\.e|vs|etc|Mr|Ms|Dr|U\.S|No|approx)\.", lambda m: m.group(0).replace(".", "․"), _clean_inline(t))
        for p in re.split(r"(?<=[.!?])[\"”')\]]?\s+(?=[\"“(\[]?[A-Za-z0-9$])", t):
            p = p.replace("․", ".").strip()
            if not p:
                continue
            if out and not re.search(r"[.!?:][\"”')\]]?$", out[-1][1]):
                out[-1][1] += " " + p      # soft-wrapped sentence continues on the next line
            else:
                out.append([ln, p])
    return [(ln, p) for ln, p in out]


def _antithesis_form(s, nxt):
    m = _mask(s)
    if _A_TAIL.search(m):
        return "X, not Y"
    if _sr._R3.search(m):
        return "not X, it's Y"
    if _A_NOTBUT.search(m):
        return "not X but Y"
    if _A_LESSMORE.search(m):
        return "less X, more Y"
    if nxt is not None and _nwords(m) <= 10 and _nwords(nxt) <= 10:
        if _NEG_AUX.search(m) and _A_NEXT.match(_mask(nxt)):
            return "isn't X. It's Y (2 sentences)"
        if _A_NOTSTART.match(m) and _nwords(m) <= 8:
            return "Not X. Y (2 sentences)"
    return None


def structural(text, verbatim=(), tweet=None):
    """ANTITHESIS / STACCATO / OPINION hits with line numbers and a block list.
    tweet=None autodetects a numbered thread ('1/ ... 2/ ...')."""
    if tweet is None:
        tweet = len(_TWEET_NUM.findall(text)) >= 2
    units = _units(text)
    tldr_secs = {sec for k, sec, ul in units if k == "heading" and re.match(r"tl;?dr\b", ul[0][1], re.I)}
    split, last_in_sec = [], {}
    for kind, sec, ul in units:
        sents = [(ul[0][0], _clean_inline(ul[0][1]))] if kind == "heading" else _sentences(ul)
        split.append((kind, sec, sents))
        if kind in ("para", "item") and sents:
            last_in_sec[sec] = sents[-1]
    words, anti, stacc, opin, exempt = 0, [], [], [], []
    for kind, sec, sents in split:
        if kind == "quote":
            continue                      # blockquote = quoted or operator-verbatim text
        words += sum(_nwords(s) for _, s in sents)
        for k, (ln, s) in enumerate(sents):
            if _is_verbatim(s, verbatim):
                exempt.append({"line": ln, "sentence": s})
                continue
            form = _antithesis_form(s, sents[k + 1][1] if k + 1 < len(sents) else None)
            if form:
                if kind == "heading":
                    pos = "headline"
                elif kind == "item" and (sec in tldr_secs or re.match(r"tl;?dr", s, re.I)):
                    pos = "tldr"
                elif last_in_sec.get(sec) == (ln, s):
                    pos = "closing"
                elif k == 0:
                    pos = "first-sentence"
                else:
                    pos = "body"
                ms = _mask(s)
                factual = bool(re.search(r"\d", ms))
                slogan = _nwords(ms) <= SLOGAN_MAX_WORDS
                blocks = (pos in PROMINENT and slogan and not factual and not form.startswith("Not X")
                          and not (tweet and "2 sentences" in form))
                anti.append({"line": ln, "form": form, "position": pos, "sentence": s, "block": blocks})
            for mo in _OPINION.finditer(_mask(s)):
                opin.append({"line": ln, "section": sec, "marker": mo.group(0), "sentence": s})
        if kind in ("para", "item"):
            # a short sentence is owner-verbatim when it sits inside a window of up to 4
            # neighbouring sentences that appears in a '>' line; verbatim sentences break a run
            vb = set()
            if verbatim:
                for i in range(len(sents)):
                    for j in range(max(0, i - 3), i + 1):
                        for k in range(i, min(len(sents), j + 4)):
                            if _is_verbatim(" ".join(x[1] for x in sents[j:k + 1]), verbatim):
                                vb.add(i)
            run, vrun = [], []
            for i, (ln, s) in enumerate(sents + [(None, None)]):
                if s is not None and i in vb and _nwords(s) <= STACCATO_MAX_WORDS:
                    vrun.append(s)
                if s is not None and i not in vb and _nwords(s) <= STACCATO_MAX_WORDS and not re.search(r"\d", _mask(s)):
                    run.append((ln, s))
                    continue
                if len(run) >= STACCATO_MIN_RUN:
                    stacc.append({"line": run[0][0], "length": len(run), "sentences": [x[1] for x in run],
                                  "block": not tweet})
                run = []
            if len(vrun) >= STACCATO_MIN_RUN:
                exempt.append({"line": sents[0][0], "sentence": " ".join(vrun)})
    allowed = round(max(1.0, words / OPINION_WORDS_PER_MARKER), 1)   # "more than once per ~1,500 words" blocks
    per_sec = {}
    for o in opin:
        per_sec[o["section"]] = per_sec.get(o["section"], 0) + 1
    crowded = sorted(s for s, n in per_sec.items() if n > OPINION_MAX_PER_SECTION)
    opin_block = len(opin) > allowed or bool(crowded)
    block = [f"antithesis L{a['line']} {a['position']}: {a['sentence'][:70]}" for a in anti if a["block"]]
    block += [f"staccato L{s['line']} x{s['length']}: {' '.join(s['sentences'])[:70]}" for s in stacc if s["block"]]
    if opin_block:
        block.append(f"opinion markers x{len(opin)} (allowed {allowed} for {words} prose words"
                     + (f"; 2+ in one section at L{', L'.join(str(o['line']) for o in opin if o['section'] in crowded)}" if crowded else "")
                     + ")")
    return {"words": words, "tweet": tweet, "antithesis": anti, "staccato": stacc, "opinion": opin,
            "opinion_allowed": allowed, "opinion_block": opin_block, "verbatim_exempt": exempt, "block": block}


# ---------------------------------------------------------------------------
# COPY-EDIT CHECKS, added after a second-model copy-edit review of a long-form
# draft caught these after the gate had passed it.
#   APHORISM     a ## section whose last paragraph is two short sentences with a turn
#                (negation, pivot word, comparative, or equal-length pair). BLOCK at
#                3+ sections in one piece (prose); WARN for 1-2, or in tweet register.
#   FORWARD REF  "(same report)" / "same source" / "the report above" with no named
#                source (parenthetical citation, link, "according to", "via X")
#                earlier in its section ("above": earlier in the text). WARN.
#   UNUSED TERM  "which I will call X" / "I will call it X" / "(X from here)" where a
#                capitalised, quoted or emphasised X never appears again. BLOCK.
#   CONSISTENCY  1 to 3 contractions in an otherwise uncontracted text of 1,500+
#                words; the same word spelled two ways (start-up/startup,
#                on-chain/onchain, tokenised/tokenized). Both WARN.
#   HEDGE DRIFT  the same percentage with "about/around/roughly..." in one place
#                and bare in another. Ranges ("3% to 5%") are skipped. WARN.
# Spelling and hedge drift stay WARN because a wider run over cover letters, CVs,
# tweets and briefings found legit pairs (presale vs pre-sales) and the same
# figure used for two different quantities.
# ---------------------------------------------------------------------------
APHORISM_MAX_WORDS = 8         # both closing sentences this short or shorter
APHORISM_BLOCK_SECTIONS = 3    # this many sections ending in one blocks (prose)
CONTRACTION_LONG_WORDS = 1500  # contraction drift only checked on texts this long
CONTRACTION_MAX_STRAY = 3      # 1..this many contractions = stray, warn
_CE_NEG = re.compile(r"\b(?:not|no|never|nothing|nobody|none|without|missing)\b|n['’]t\b", re.I)
_CE_PIVOT = re.compile(r"\b(?:but|yet|still|instead|only|later|first|then|now|today|tomorrow|again|until)\b", re.I)
_CE_COMPAR = re.compile(r"\b(?:more|less|fewer|bigger|smaller|better|worse|larger|cheaper|harder|easier)\b", re.I)
_CE_CONTRACTION = re.compile(r"\b[A-Za-z]+(?:n['’]t|['’]re|['’]ve|['’]ll|['’]d|['’]m)\b"
                             r"|\b(?:it|that|there|what|here|who|where|let|he|she)['’]s\b", re.I)
_CE_SAMEREF = re.compile(r"\((?:same|ditto)\s+(?:report|source|study|survey|data|dataset|filing|paper|article|count)\)"
                         r"|\b(?:the\s+)?same\s+(?:source|report|study|survey|dataset|filing|paper)\b"
                         r"|\bthe\s+(?:report|source|study|survey|paper|article|data)\s+(?:cited\s+|quoted\s+)?above\b|\bibid\b", re.I)
_CE_CITE_PAREN = re.compile(r"\((?!\s*(?:same|ditto)\b)[^()]*(?:[A-Z][a-z]|[A-Z]{2,}|\b(?:19|20)\d\d\b)[^()]*\)")
_CE_CITE_OTHER = re.compile(r"\[[^\]]+\]\([^)]+\)|\b[Aa]ccording to\b|\bvia\s+[A-Z]")
_CE_TERM = r"[\"“*_]{0,2}[A-Za-z][\w-]*(?:\s+[A-Z][\w-]*){0,2}[\"”*_]{0,2}"
_CE_HERE = r"(?i:from\s+here(?:\s+on)?|for\s+short|hereafter|below)"
# a definitional cue is required: "which/what I call X", "I call it/them/this X", or a trailing "from here"
_CE_CALL = r"\bI(?:\s+(?i:will|shall)|['’]ll)?\s+(?i:call)\s+"
_CE_DEFINE = re.compile(r"\b(?i:which|what)\s+" + _CE_CALL + r"(?:(?i:it|them|this)\s+)?(?:(?i:the|a|an)\s+)?(?P<t1>" + _CE_TERM + r")"
                        r"|" + _CE_CALL + r"(?i:it|them|this)\s+(?:(?i:the|a|an)\s+)?(?P<t3>" + _CE_TERM + r")"
                        r"|" + _CE_CALL + r"(?P<t4>" + _CE_TERM + r")\s+" + _CE_HERE +
                        r"|\((?:(?i:the|a|an)\s+)?(?P<t2>" + _CE_TERM + r")\s+" + _CE_HERE + r"\)")
_CE_PCT = re.compile(r"(?:(?P<h>\b(?:about|around|roughly|approximately|nearly|almost|some|circa|close\s+to)|~)\s*)?"
                     r"(?<![\d.])(?P<v>\d+(?:\.\d+)?)\s?(?:%|percent\b|per\s+cent\b)", re.I)
_CE_RANGE = re.compile(r"^\s*(?:to|-|and)\s*\d")
_CE_SKIP_SPELL = {"resign", "recover", "recreate", "recreation", "reform", "release", "repress", "coop",
                  "relay", "reserve", "resort", "resent", "recount", "redress"}


def _ce_turn(a, b):
    """What makes two short closing sentences read as a kicker. None = plain pair."""
    if _CE_NEG.search(a) or _CE_NEG.search(b):
        return "negation"
    if _CE_PIVOT.search(a) or _CE_PIVOT.search(b):
        return "pivot"
    if _CE_COMPAR.search(b):
        return "comparative"
    na, nb = _nwords(a), _nwords(b)
    if abs(na - nb) <= 1 and max(na, nb) <= 6:
        return "parallel"
    return None


def copyedit(text, verbatim=(), tweet=None):
    """Copy-edit tells a copy-edit review caught that the slop lists miss. Same unit
    split as structural(): quotes ('>'), tables, code and frontmatter are out."""
    if tweet is None:
        tweet = len(_TWEET_NUM.findall(text)) >= 2
    units = _units(text)
    headed = {sec for k, sec, ul in units if k == "heading"}
    prose, last = [], {}
    for kind, sec, ul in units:
        if kind == "quote":
            continue
        if sec in headed and kind in ("para", "item"):
            last[sec] = (kind, ul)
        sents = [(ul[0][0], _clean_inline(ul[0][1]))] if kind == "heading" else _sentences(ul)
        prose += [(kind, sec, ln, s) for ln, s in sents]
    # 1. section-closing aphorism
    aph = []
    for sec, (kind, ul) in sorted(last.items()):
        s = _sentences(ul) if kind == "para" else []
        if len(s) != 2:
            continue
        (ln, a), (_, b) = s
        if max(_nwords(a), _nwords(b)) > APHORISM_MAX_WORDS or re.search(r"\d", a + b):
            continue
        turn = _ce_turn(_mask(a), _mask(b))
        if turn:
            ex = _is_verbatim(a + " " + b, verbatim) or (_is_verbatim(a, verbatim) and _is_verbatim(b, verbatim))
            aph.append({"line": ln, "turn": turn, "text": f"{a} {b}", "exempt": ex})
    n_aph = sum(1 for a in aph if not a["exempt"])
    aph_block = n_aph >= APHORISM_BLOCK_SECTIONS and not tweet
    # 2. back-pointer to a source with nothing named before it
    lines = text.split("\n")
    fwd, cited_secs, cited_any = [], set(), False
    for kind, sec, ln, s in prose:
        for m in _CE_SAMEREF.finditer(s):
            before = s[:m.start()]
            if _CE_CITE_PAREN.search(before) or _CE_CITE_OTHER.search(before):
                continue
            if (cited_any if "above" in m.group(0).lower() else sec in cited_secs):
                continue
            fwd.append({"line": ln, "phrase": m.group(0), "sentence": s})
        raw = lines[ln - 1] if 0 < ln <= len(lines) else s
        if _CE_CITE_PAREN.search(_CE_SAMEREF.sub(" ", s)) or _CE_CITE_OTHER.search(raw):
            cited_secs.add(sec)
            cited_any = True
    # 3. defined but never used (read on raw lines, so *emphasis* and quotes still mark the term)
    raw_prose = [(ln, t) for kind, sec, ul in units if kind != "quote" for ln, t in ul]
    unused = []
    for i, (ln, t) in enumerate(raw_prose):
        for m in _CE_DEFINE.finditer(t):
            raw_term = (m.group("t1") or m.group("t2") or m.group("t3") or m.group("t4") or "").strip()
            term = raw_term.strip("\"“”*_ ")
            if not term or not (raw_term != term or term[0].isupper()):
                continue                  # an unmarked lowercase capture is usually "I'll call you"
            rest = _clean_inline(t[m.end():] + " " + " ".join(x for _, x in raw_prose[i + 1:]))
            if not re.search(r"(?<![\w-])" + re.escape(term) + r"(?:['’]?s)?(?![\w-])", rest):
                unused.append({"line": ln, "term": term, "block": True})
    # 4. consistency: stray contractions, one word spelled two ways
    words = sum(_nwords(s) for *_, s in prose)
    clean = [(ln, _QUOTED.sub(" ", re.sub(r"https?://\S+", " ", s))) for *_, ln, s in prose]
    contr = [{"line": ln, "word": m.group(0)} for ln, s in clean for m in _CE_CONTRACTION.finditer(s)]
    contr_warn = words >= CONTRACTION_LONG_WORDS and 1 <= len(contr) <= CONTRACTION_MAX_STRAY
    forms = {}
    for ln, s in clean:
        for w in re.findall(r"\b[A-Za-z]+(?:-[A-Za-z]+)*\b", s):
            lw = w.lower()
            k = lw.replace("-", "")
            if len(k) > 6:
                k = re.sub(r"is(e|ed|es|ing|ation|ations|er|ers)$", r"iz\1", k)
            k = k[:-1] if k.endswith("s") and len(k) > 4 else k
            if k not in _CE_SKIP_SPELL:
                forms.setdefault(k, {}).setdefault(lw, []).append(ln)
    spell = []
    for k, f in forms.items():
        if len(f) < 2:
            continue
        hy = {w for w in f if "-" in w}
        sz = {("s" if re.search(r"is(?:e|ed|es|ing|ation|ations|er|ers)s?$", w) else "z")
              for w in f if "-" not in w and re.search(r"i[sz](?:e|ed|es|ing|ation|ations|er|ers)s?$", w)}
        if (hy and set(f) - hy) or len(sz) > 1:
            spell.append({"forms": {w: l[:3] for w, l in f.items()}})
    # 5. hedge drift on percentages
    pct = {}
    for ln, s in clean:
        for m in _CE_PCT.finditer(s):
            if _CE_RANGE.match(s[m.end():]) or re.search(r"\d\s*%?\s*(?:to|-|and)\s*$", s[:m.start("v")]):
                continue                  # one end of a range is approximate by construction
            d = pct.setdefault(m.group("v"), {"hedged": [], "bare": []})
            d["hedged" if m.group("h") else "bare"].append(ln)
    drift = [{"value": v + "%", **d} for v, d in pct.items() if d["hedged"] and d["bare"]]
    block = []
    if aph_block:
        block.append(f"aphorism closers x{n_aph} (sections end on a two-sentence kicker at L"
                     + ", L".join(str(a["line"]) for a in aph if not a["exempt"]) + ")")
    block += [f"unused term L{u['line']}: '{u['term']}' is defined and never used" for u in unused if u["block"]]
    return {"aphorism": aph, "aphorism_count": n_aph, "aphorism_block": aph_block, "forward_ref": fwd,
            "unused_term": unused, "contractions": contr, "contraction_warn": contr_warn, "words": words,
            "spelling": spell, "hedge_drift": drift, "block": block}


# Selftest fixture list: invented generic phrases, not anyone's real list. None of them is in
# HARD_WORDS, so a selftest block can only come from the rejected-phrases check.
_SELFTEST_REJECTED = ("it goes without saying", "needless to say", "my guess is", "all things considered",
                      "when all is said and done", "let's be clear", "the bottom line is", "it is worth noting that")

REJECTED_PHRASES = os.environ.get("AGENT_REJECTED_PHRASES") or os.path.join(_ROOT, "knowledge", "rejected-phrases.json")


def load_rejected(path=None):
    """(phrases, state). state: "ok", "off" (no file: check not configured) or "error"
    (file exists but is unreadable or lists no phrase)."""
    p = path or REJECTED_PHRASES
    if not os.path.exists(p):
        return [], "off"
    try:
        rows = json.load(open(p, encoding="utf-8")).get("phrases", [])
        out = [str(r["phrase"]).strip() for r in rows if str(r.get("phrase", "")).strip()]
        return (out, "ok") if out else ([], "error")
    except Exception:
        return [], "error"



def _phrase_rx(p):
    parts = [re.escape(w).replace("'", "['’]") for w in p.lower().replace("’", "'").split()]
    return re.compile(r"(?<![\w'’])" + r"\s+".join(parts) + r"(?![\w'’])", re.I)


def rejected_phrases(text, approved=(), phrases=None):
    """(hits, error). Every listed phrase outside '>' lines and outside sentences found in
    '>' lines of verbatim-approved.md. No quota: each occurrence is a hit.
    No list configured: no hits and no error."""
    if phrases is None:
        phrases, state = load_rejected()
        if state == "off":
            return [], ""
        if state == "error":
            return [], "rejected-phrases list unreadable or empty"
    if not phrases:
        return [], "rejected-phrases list unreadable or empty"
    rxs = [(p, _phrase_rx(p)) for p in phrases]
    hits = []
    for kind, sec, ul in _units(text):
        if kind == "quote":
            continue
        sents = [(ul[0][0], ul[0][1])] if kind == "heading" else _sentences(ul)
        for ln, s in sents:
            for p, rx in rxs:
                if rx.search(s):
                    if _is_verbatim(s, approved):
                        continue
                    hits.append({"line": ln, "phrase": p, "sentence": s})
    return hits, ""


def hard_reasons(res):
    """Every HARD reason as short strings. Callers that list hits use this, so a
    new check shows up in their messages and override logs without another edit."""
    return ((["em/en dash"] if res["em_en_dash"] else []) + res["hard_slop"] + res["hard_opener"]
            + [f"retracted:{r['id']}" for r in res["retracted"]]
            + [f"rejected phrase L{h['line']}: '{h['phrase']}'" for h in res.get("rejected_phrase", [])]
            + ([res["rejected_registry_error"]] if res.get("rejected_registry_error") else [])
            + res.get("structural_block", []))


def scan(text, cv=False, verbatim=(), tweet=None, approved=()):
    """approved = normalised '>' lines of verbatim-approved.md (load_verbatim); only these
    exempt a rejected phrase. verbatim (any interview file) still feeds the structural checks."""
    body = _strip_md(text)
    hard_words = list(HARD_WORDS) + (CV_FILLER if cv else [])
    st = structural(text, verbatim=verbatim, tweet=tweet)
    ce = copyedit(text, verbatim=verbatim, tweet=st["tweet"])
    rj, rj_err = rejected_phrases(text, approved=approved)
    res = {
        "em_en_dash": bool(DASH.search(text)),
        "hard_slop": _find(body, hard_words),
        "hard_opener": [o for o in HARD_OPENERS if _first_sentence(text).startswith(o)],
        "warn_slop": _find(body, WARN_WORDS),
        "warn_structural": _structural(body),
        "retracted": [{"id": r["id"], "replacement": r.get("replacement", "")} for r in _retracted(body, cv)],
        "structural": st,
        "copyedit": ce,
        "structural_block": st["block"] + ce["block"],   # copy-edit blocks ride the same list (hard_reasons, --structural-warn)
        "rejected_phrase": rj,
        "rejected_registry_error": rj_err,
        "rejected_list": load_rejected()[1],
    }
    res["hard_hit"] = bool(res["em_en_dash"] or res["hard_slop"] or res["hard_opener"] or res["retracted"]
                           or res["structural_block"] or res["rejected_phrase"] or res["rejected_registry_error"])
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
    if res.get("rejected_registry_error"):
        print(f" XX {res['rejected_registry_error']}")
    elif res.get("rejected_list") == "off":
        print(" -- note: no rejected-phrases list configured, that check is off")
    for h in res.get("rejected_phrase", []):
        print(f" XX rejected phrase L{h['line']} '{h['phrase']}' (the owner rejected it; say the claim plainly): {h['sentence'][:90]}")
    st = res["structural"]
    for a in st["antithesis"]:
        print(f" {'XX' if a['block'] else '..'} {'' if a['block'] else 'WARN '}antithesis L{a['line']} [{a['position']}, {a['form']}]: {a['sentence']}")
    for s in st["staccato"]:
        why = "" if s["block"] else "WARN "
        print(f" {'XX' if s['block'] else '..'} {why}staccato L{s['line']} x{s['length']}: {' | '.join(s['sentences'])}")
    if st["opinion"]:
        mark = "XX" if st["opinion_block"] else ".."
        print(f" {mark} {'' if st['opinion_block'] else 'WARN '}opinion markers x{len(st['opinion'])} "
              f"(allowed {st['opinion_allowed']} for {st['words']} prose words, max {OPINION_MAX_PER_SECTION} per section):")
        for o in st["opinion"]:
            print(f"      L{o['line']} (section {o['section']}): \"{o['marker']}\"")
    for e in st["verbatim_exempt"]:
        print(f" -- verbatim-exempt L{e['line']}: {e['sentence'][:100]}")
    ce = res["copyedit"]
    if ce["aphorism"]:
        mark = "XX" if ce["aphorism_block"] else ".."
        print(f" {mark} {'' if ce['aphorism_block'] else 'WARN '}aphorism closers x{ce['aphorism_count']} "
              f"(blocks at {APHORISM_BLOCK_SECTIONS}+ sections; section ends on two short sentences with a turn):")
        for a in ce["aphorism"]:
            print(f"      L{a['line']} [{a['turn']}]{' verbatim-exempt' if a['exempt'] else ''}: {a['text']}")
    for u in ce["unused_term"]:
        print(f" {'XX' if u['block'] else '..'} {'' if u['block'] else 'WARN '}unused term L{u['line']}: "
              f"'{u['term']}' is defined and never appears again (use it or cut the definition)")
    for f in ce["forward_ref"]:
        print(f" .. WARN forward reference L{f['line']}: '{f['phrase']}' with no named source earlier in its section")
    if ce["contraction_warn"]:
        print(f" .. WARN stray contractions x{len(ce['contractions'])} in {ce['words']} uncontracted words: "
              + ", ".join(f"L{c['line']} {c['word']}" for c in ce["contractions"]))
    for s in ce["spelling"]:
        print(" .. WARN one word, two spellings: " + " vs ".join(f"{w} (L{', L'.join(map(str, l))})" for w, l in s["forms"].items()))
    for d in ce["hedge_drift"]:
        print(f" .. WARN hedge drift {d['value']}: hedged at L{', L'.join(map(str, d['hedged']))}, "
              f"bare at L{', L'.join(map(str, d['bare']))} (pick one form)")
    if not res["hard_hit"]:
        print(" OK no hard tells")
    if res["warn_slop"]:
        print(f" .. WARN context-legit words (review, not a block): {', '.join(res['warn_slop'])}")
    if res["warn_structural"]:
        for w in res["warn_structural"]:
            print(f" .. WARN structural tell: {w}")
    if res["structural_block"]:
        print(" FIX (structure): say what it IS without the foil; join or vary short runs; keep one")
        print("      section kicker at most two; use a defined term or cut its definition;")
        print("      opinion marker where a claim could read as fact. Owner-verbatim lines go in")
        print("      verbatim-approved.md beside the draft as '>' lines (with the approving message id).")
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
    # -- structural checks --
    sb = lambda r, kind: [b for b in r["structural_block"] if b.startswith(kind)]
    r = scan("## The scoreboard: tickets, not rides\n\nText follows here."); checks.append(("antithesis_headline_blocks", bool(sb(r, "antithesis")) and r["hard_hit"]))
    r = scan("## TL;DR\n\n- The town sells tickets, not rides.\n- More detail in the essay below this list."); checks.append(("antithesis_tldr_blocks", bool(sb(r, "antithesis"))))
    r = scan("This is a toll, not a tax. The rest of this paragraph explains the toll in plain words."); checks.append(("antithesis_first_sentence_blocks", bool(sb(r, "antithesis"))))
    r = scan("It's not about the money, it's about the rules. We checked the rules twice over the year."); checks.append(("antithesis_not_about_it_blocks", bool(sb(r, "antithesis"))))
    r = scan("Less talk, more building. The team shipped two releases this month."); checks.append(("antithesis_less_more_blocks", bool(sb(r, "antithesis"))))
    r = scan("The demand isn't gone. It moved offshore. Volumes show where it went last year in detail."); checks.append(("antithesis_isnt_its_blocks", bool(sb(r, "antithesis"))))
    r = scan("Pool flows were large this week. Per the dashboard, the $1.5B is USDC leaving the pool, not reserves. We checked it twice."); checks.append(("factual_negation_warns_only", r["structural"]["antithesis"] and not sb(r, "antithesis")))
    r = scan("The regulator counted 23.5 million accounts (accounts, not people) in September."); checks.append(("parenthetical_negation_ignored", not r["structural"]["antithesis"]))
    r = scan('He said "this is a toll, not a tax" at the hearing, and the room went quiet for a while.'); checks.append(("quoted_negation_ignored", not r["structural"]["antithesis"]))
    r = scan("The rule is not signed yet, but the draft is public. Comments close in March."); checks.append(("concessive_comma_but_ok", not sb(r, "antithesis")))
    r = scan("I do not hold the token. That is disclosed above in the note."); checks.append(("disclosure_pair_ok", not sb(r, "antithesis")))
    r = scan("- Partner mini apps: signed. Not delivered. Closed in July."); checks.append(("status_not_delivered_ok", not sb(r, "antithesis")))
    r = scan("This is not a barrier but a moat. The rest explains why in plain terms."); checks.append(("not_but_np_blocks", bool(sb(r, "antithesis"))))
    r = scan("The market grew last year and volume climbed steadily through the quarter."); checks.append(("antithesis_clean_zero", not r["structural"]["antithesis"]))
    r = scan("I looked for one. I found none. Vietnam has one. The rest of the region has more."); checks.append(("staccato_blocks", bool(sb(r, "staccato")) and r["hard_hit"]))
    r = scan("I looked for one in every registry I could reach. I found none at any real scale. Vietnam has one."); checks.append(("staccato_two_short_ok", not r["structural"]["staccato"]))
    r = scan("Unread: 69. Outside Promotions: 47. Promotions: 22."); checks.append(("staccato_numeric_readout_ok", not r["structural"]["staccato"]))
    r = scan("1/ same banks. same rails. new ledger.\n\n2/ the rest of the thread says why it matters for the local currency."); checks.append(("staccato_tweet_warns_only", r["structural"]["staccato"] and not sb(r, "staccato")))
    v = [_norm("Rain is coming. It is not quite here yet. But it will.")]
    r = scan("Prices fell. Rain is coming. It is not quite here yet. But it will.", verbatim=v); checks.append(("staccato_verbatim_exempt", not sb(r, "staccato") and r["structural"]["verbatim_exempt"]))
    r = scan("> Rain is coming. It is not quite here yet. But it will.\n\nThe piece goes on in full sentences here."); checks.append(("blockquote_verbatim_exempt", not r["structural"]["staccato"]))
    r = scan("## TL;DR\n\n- The town sells tickets, not rides.", verbatim=[_norm("the town sells tickets, not rides")]); checks.append(("antithesis_verbatim_exempt", not sb(r, "antithesis")))
    r = scan("I looked for one. I found none. Vietnam has one. The region has more.", verbatim=[_norm("thailand has two exchanges and a regulator")]); checks.append(("verbatim_loaded_nonmatch_still_blocks", bool(sb(r, "staccato"))))
    r = scan("Prices went up. It was. Not here. Then more.", verbatim=[_norm("prices went upward it wasnt")]); checks.append(("verbatim_word_boundary", not r["structural"]["verbatim_exempt"]))
    one = "My guess is that the buyers left. " + "Plain words carry the rest of the argument here. " * 60
    r = scan(one); checks.append(("opinion_single_warns_only", len(r["structural"]["opinion"]) == 1 and not r["structural"]["opinion_block"]))
    r = scan("## A\n\nMy take is that it grows. Then my bet is it stalls.\n\n## B\n\n" + "Plain words. " * 40); checks.append(("opinion_two_in_section_blocks", r["structural"]["opinion_block"] and r["hard_hit"]))
    sec = lambda n: f"## S{n}\n\nMy bet is that point {n} holds. " + "Plain words carry the rest of this part. " * 60 + "\n\n"
    r = scan(sec(1) + sec(2) + sec(3)); checks.append(("opinion_density_blocks", r["structural"]["opinion_block"] and r["structural"]["opinion_allowed"] == 1))
    r = scan(sec(1) + sec(2) + "## S3\n\n" + "Plain words carry the rest of this part. " * 300); checks.append(("opinion_under_density_ok", not r["structural"]["opinion_block"]))
    r = scan("This is a toll, not a tax. Then more words follow in this paragraph.")
    checks.append(("hard_reasons_lists_structural", any(x.startswith("antithesis") for x in hard_reasons(r))))
    # -- copy-edit checks --
    ce = lambda r: r["copyedit"]
    body = "The longer paragraph sets out the argument in plain and complete sentences for the reader.\n\n"
    kick = ["Fast tools remove the delay. They do not fix the plan.",
            "Sharing splits the cake. Baking makes a bigger one.", "Ship small first. Polish can come later.",
            "The parts exist. The budget did not cover them."]
    piece = lambda ends: "".join(f"## Part {i}\n\n{body}{e}\n\n" for i, e in enumerate(ends))
    r = scan(piece(kick[:3])); checks.append(("aphorism_3_sections_blocks", ce(r)["aphorism_block"] and ce(r)["aphorism_count"] == 3 and any(b.startswith("aphorism") for b in hard_reasons(r))))
    r = scan(piece(kick[:2])); checks.append(("aphorism_2_sections_warns", ce(r)["aphorism_count"] == 2 and not ce(r)["aphorism_block"] and not r["hard_hit"]))
    r = scan(piece(kick[:2] + ["Check the forecast. It changes before the weekend does."])); checks.append(("aphorism_plain_pair_not_counted", ce(r)["aphorism_count"] == 2))
    r = scan(piece(kick[:2] + ["We checked this against every registry we could reach, twice, and the count held."])); checks.append(("aphorism_long_closer_ok", ce(r)["aphorism_count"] == 2))
    r = scan(piece(kick[:3]), verbatim=[_norm(kick[2])]); checks.append(("aphorism_verbatim_exempt", ce(r)["aphorism_count"] == 2 and not ce(r)["aphorism_block"]))
    r = scan(piece(kick[:3]), tweet=True); checks.append(("aphorism_tweet_warns_only", ce(r)["aphorism_count"] == 3 and not ce(r)["aphorism_block"]))
    r = scan(body + kick[0] + "\n\n" + body + kick[1] + "\n\n" + body + kick[2]); checks.append(("aphorism_needs_sections", not ce(r)["aphorism"]))
    fw = "## Money\n\nTotal funding does not sort it either: Region A raised US$366 million, close to Region B's US$355.7 million (same report). In 2025 they raised US$355.7 million (Example Research, via Daily Ledger)."
    r = scan(fw); checks.append(("forward_ref_warns", len(ce(r)["forward_ref"]) == 1 and not r["hard_hit"]))
    r = scan("## Money\n\nIn 2025 they raised US$355.7 million (Example Research, via Daily Ledger). Region A raised US$366 million (same report)."); checks.append(("backward_ref_ok", not ce(r)["forward_ref"]))
    r = scan("## A\n\nPrices fell 20% (OpenRouter, November 2026).\n\n## B\n\nVolumes held (same report)."); checks.append(("same_ref_other_section_warns", len(ce(r)["forward_ref"]) == 1))
    r = scan("## A\n\nPrices fell (OpenRouter, November 2026).\n\n## B\n\nThe report above covers volume too."); checks.append(("report_above_after_source_ok", not ce(r)["forward_ref"]))
    ut = "It is known for *copy, adapt, ship*, which I will call CAS from here. Copying is the rational bet in a big home market."
    r = scan(ut); checks.append(("unused_term_blocks", [u["term"] for u in ce(r)["unused_term"]] == ["CAS"] and r["hard_hit"]))
    r = scan(ut + " The region's row is CAS under licence."); checks.append(("used_term_ok", not ce(r)["unused_term"]))
    r = scan("The licensing route (the toll from here) costs time. Nothing else follows."); checks.append(("unused_paren_lowercase_unmarked_ignored", not ce(r)["unused_term"]))
    r = scan("The licensing route (the \"toll\" from here) costs time. Nothing else follows."); checks.append(("unused_paren_quoted_blocks", [u["term"] for u in ce(r)["unused_term"]] == ["toll"]))
    r = scan("The licensing route (the *toll* from here) costs time. The toll is paid once a year."); checks.append(("used_paren_term_ok", not ce(r)["unused_term"]))
    r = scan("I'll call you tomorrow about the contract and the terms."); checks.append(("call_you_ignored", not ce(r)["unused_term"]))
    r = scan("I'll call Sarah on Monday about the contract and the terms."); checks.append(("call_named_person_ignored", not ce(r)["unused_term"]))
    r = scan("The licensing route costs time, and I will call it the Toll. Nothing else follows."); checks.append(("call_it_term_blocks", [u["term"] for u in ce(r)["unused_term"]] == ["Toll"]))
    long_plain = "The team builds the product for users abroad and ships it every week. " * 120
    r = scan("I couldn't find one. " + long_plain); checks.append(("stray_contraction_warns", ce(r)["contraction_warn"] and not r["hard_hit"]))
    r = scan("I couldn't find one. We didn't look hard. It isn't there. They're not sure. " + long_plain); checks.append(("contracted_voice_ok", not ce(r)["contraction_warn"]))
    r = scan("I couldn't find one. Short note."); checks.append(("contraction_short_text_ok", not ce(r)["contraction_warn"]))
    r = scan("Regional startups raised less money last year than in any year since the boom, and one start-up founder moved abroad. Organised clubs and organized leagues both grew over the same period."); checks.append(("spelling_variants_warn", len(ce(r)["spelling"]) == 2 and not r["hard_hit"]))
    r = scan("Start-ups raised less. One start-up moved abroad. Organised clubs grew."); checks.append(("spelling_consistent_ok", not ce(r)["spelling"]))
    r = scan("About 72% of shops closed early that year. Later, 72% of them still closed early."); checks.append(("hedge_drift_warns", [d["value"] for d in ce(r)["hedge_drift"]] == ["72%"] and not r["hard_hit"]))
    r = scan("About 72% of shops closed early. Later, about 72% of them still did."); checks.append(("hedge_consistent_ok", not ce(r)["hedge_drift"]))
    r = scan("It adds about 5% today and 3% to 5% after the change."); checks.append(("hedge_range_ok", not ce(r)["hedge_drift"]))
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
    # -- rejected phrases (the invented _SELFTEST_REJECTED list in a temp file, so the test never reads a real list) --
    global REJECTED_PHRASES
    saved_rj = REJECTED_PHRASES
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump({"phrases": [{"phrase": p} for p in _SELFTEST_REJECTED]}, tf)
    REJECTED_PHRASES = tf.name
    try:
        rp = lambda r: [h["phrase"] for h in r["rejected_phrase"]]
        checks.append(("rejected_list_loads", load_rejected()[1] == "ok" and len(load_rejected()[0]) == len(_SELFTEST_REJECTED)))
        r = scan(one); checks.append(("rejected_single_blocks_no_quota", rp(r) == ["my guess is"] and r["hard_hit"]
                                      and any(x.startswith("rejected phrase") for x in hard_reasons(r))))
        r = scan("Rates fell in March. Let\u2019s be clear, the data may move."); checks.append(("rejected_curly_apostrophe_blocks", rp(r) == ["let's be clear"]))
        r = scan("## Needless to say\n\nRates fell. Needless to say, nobody knows yet."); checks.append(("rejected_heading_and_body_each_count", len(rp(r)) == 2))
        r = scan("My guess isn't settled on the rates question this quarter."); checks.append(("rejected_word_boundary", not rp(r)))
        r = scan("> my guess is that the buyers left\n\nThe piece goes on in plain words here."); checks.append(("rejected_blockquote_exempt", not rp(r)))
        ap_line = [_norm("My guess is that the buyers left for the coast.")]
        r = scan("My guess is that the buyers left for the coast. More words here.", approved=ap_line); checks.append(("rejected_verbatim_approved_exempt", not rp(r)))
        r = scan("My guess is that the buyers left for the coast. More words here.", verbatim=ap_line); checks.append(("rejected_interview_verbatim_not_exempt", rp(r) == ["my guess is"]))
        hits, err = rejected_phrases("my guess is plain", phrases=[]); checks.append(("rejected_empty_list_is_error", not hits and bool(err)))
        r = scan("It is worth\nnoting that the numbers show growth in the second half."); checks.append(("rejected_multiword_any_whitespace_blocks", rp(r) == ["it is worth noting that"]))
        with open(tf.name, "w") as f:
            f.write("{not json")
        r = scan("Plain words only."); checks.append(("rejected_broken_list_blocks", r["hard_hit"] and bool(r["rejected_registry_error"])))
        REJECTED_PHRASES = tf.name + ".missing"
        r = scan("My guess is that plain words carry it."); checks.append(("rejected_no_list_is_off", not r["rejected_phrase"] and not r["rejected_registry_error"]))
    finally:
        REJECTED_PHRASES = saved_rj
        os.unlink(tf.name)
    ok = all(v for _, v in checks)
    for n, v in checks:
        print(f" {'PASS' if v else 'FAIL'}  {n}")
    print(f"== SELFTEST {'PASS' if ok else 'FAIL'} ({sum(bool(v) for _,v in checks)}/{len(checks)}) ==")
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--cv", action="store_true", help="also HARD-block CV/cover-letter passion-filler")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--verbatim", action="append", default=[],
                    help="file whose '>' lines are owner-verbatim (repeatable). With --file, verbatim-approved.md, "
                         "interview-quotes.md and interview.md next to the file load automatically")
    ap.add_argument("--structural-warn", action="store_true",
                    help="print antithesis/staccato/opinion hits but never block on them (internal digests "
                         "sent only to the operator, such as a daily briefing)")
    ap.add_argument("--tweet", action="store_true", help="tweet register: staccato warns instead of blocking "
                    "(also autodetected from '1/ 2/' thread numbering)")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if _selftest() else 1)
    text = _read(a)
    if text is None:
        print("usage: external_slop_gate.py --file <path> | --stdin  [--cv] [--json] [--verbatim F] [--tweet]", file=sys.stderr)
        sys.exit(2)
    vfiles = list(a.verbatim)
    if a.file:
        here = os.path.dirname(os.path.abspath(a.file))
        vfiles += [p for p in (os.path.join(here, n) for n in ("verbatim-approved.md", "interview-quotes.md", "interview.md"))
                   if os.path.isfile(p) and p not in vfiles]
    verbatim = [v for p in vfiles for v in load_verbatim(p)]
    approved = [v for p in vfiles if os.path.basename(p) == "verbatim-approved.md" for v in load_verbatim(p)]
    if vfiles and not a.json:
        print(f" (verbatim source: {', '.join(os.path.relpath(p) for p in vfiles)}, {len(verbatim)} '>' lines)")
    res = scan(text, cv=a.cv, verbatim=verbatim, tweet=True if a.tweet else None, approved=approved)
    if a.structural_warn and res["structural_block"]:
        res["structural_block"] = []
        res["hard_hit"] = bool(res["em_en_dash"] or res["hard_slop"] or res["hard_opener"] or res["retracted"]
                               or res["rejected_phrase"] or res["rejected_registry_error"])
        for x in res["structural"]["antithesis"] + res["structural"]["staccato"]:
            x["block"] = False
        res["structural"]["opinion_block"] = False
        res["copyedit"]["aphorism_block"] = False
        for u in res["copyedit"]["unused_term"]:
            u["block"] = False
    if a.json:
        out = dict(res); out["verdict"] = "BLOCK" if res["hard_hit"] else "CLEAN"; out["label"] = a.label
        print(json.dumps(out, indent=2))
    else:
        _p(res, a.label)
    sys.exit(1 if res["hard_hit"] else 0)

if __name__ == "__main__":
    main()
