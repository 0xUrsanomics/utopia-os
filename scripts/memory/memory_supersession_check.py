#!/usr/bin/env python3
# memory_supersession_check.py: read-only supersession report for append-only memory.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""memory_supersession_check.py. Read-only supersession report for append-only memory.

Adapted from PACMI (arXiv 2610.05732, "Provenance-Aware Cascading Memory
Invalidation"). Builds a small provenance graph over memory/Learnings.md and
memory/Decisions.md entries, assigns each entry a validity state, propagates
along dependency edges, and prints what is stale but still unmarked.

It NEVER writes to the memory files. Output goes to stdout only.

Usage:
    python3 scripts/memory/memory_supersession_check.py
    python3 scripts/memory/memory_supersession_check.py --json
    python3 scripts/memory/memory_supersession_check.py --files memory/Learnings.md --limit 50
    python3 scripts/memory/memory_supersession_check.py --selftest

Paths in --files are relative to AGENT_ROOT (default: the repo root). Missing files are skipped.

Convention it reads (write it into Decisions/Learnings entries as Logseq-style properties):
    id::          optional stable id for an entry (else auto id FILE:LINE)
    status::      active | superseded | disputed | retracted   (other values = legacy, read as active)
    supersedes::  ref[, ref]   this entry replaces the referenced one(s)
    depends-on::  ref[, ref]   this entry's claim rests on the referenced one(s)
    A ref is an id, or "YYYY-MM-DD <a few title words>".

It also reads the legacy text markers (heading ~~strike~~, RETRACTED, SUPERSEDED,
DISPROVEN) and infers edges from prose in LATER entries, e.g. 'the earlier
critic-child theory (10-06) ... shown NOT to ...'. Inferred edges are labelled
inferred and should be read as candidates for a human, not as truth.

Checks:
  1. contradicted-unmarked   a later entry supersedes/disproves/retracts an entry
                             that carries no marker, so recall still ranks it as current.
  2. stale-dependents        entries whose depends-on (explicit) or citation (inferred)
                             parent is non-current. PACMI cascade: depends-on parent
                             superseded/retracted -> needs-verification.
  3. contradicted-headings   heading says pending/in progress/open but its own body,
                             or a later entry, says fixed/shipped/done.
  4. aging-open-status       Decisions status:: still "in progress/pending/awaiting"
                             after STATUS_AGE_DAYS.
  5. recall-marker-audit     how vector_brain's _SUPERSEDED_RE (text-marker demotion)
                             lines up with the derived states: false demotions
                             (active entry demoted because it says "supersedes X")
                             and misses (non-current entry not demoted).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DEFAULT_FILES = ["memory/Learnings.md", "memory/Decisions.md"]
STATUS_AGE_DAYS = 7
TODAY = date.today()

# PACMI lattice, ordered weakest to strongest non-current status. "disputed"
# is an addition to the paper's lattice (a later entry argues against it, not yet settled).
LATTICE = ["active", "needs-verification", "disputed", "historical-only",
           "superseded", "retracted"]
RANK = {s: i for i, s in enumerate(LATTICE)}
NON_CURRENT = {"disputed", "historical-only", "superseded", "retracted"}
# Edge type -> state pushed onto the dependent (PACMI transition map).
CASCADE = {"depends-on": "needs-verification", "cites": "needs-verification"}

# Kept identical to _SUPERSEDED_RE in scripts/memory/vector_brain.py so the audit is faithful.
VB_SUPERSEDED_RE = re.compile(
    r"superseded by|\bsupersede[sd]?\b|status::\s*superseded|\bSUPERSEDED\b|~~", re.I)

HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)$")
DATE_IN_HEADING_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
DATED_BULLET_RE = re.compile(r"^- (?:~~)?(\d{4}-\d{2}-\d{2})\b(.*)$")
PROP_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9_-]*)::\s*(.*)$")

TITLE_RETRACT_RE = re.compile(r"^~~|\bRETRACTED\b", re.I)
TITLE_SUPERSEDED_RE = re.compile(r"\bSUPERSEDED\b|superseded by", re.I)
TITLE_DISPUTED_RE = re.compile(r"\bDISPROVEN\b|\bDISPUTED\b")
BODY_RETRACT_RE = re.compile(r"^#{3,4}\s+~~|^\*\*RETRACTED|^RETRACTED IN FULL", re.M)

PENDING_RE = re.compile(
    r"pending fix|fix pending|\(pending|pending operator|in progress|\bWIP\b|\bTODO\b|"
    r"awaiting|not yet fixed|unresolved|\(open\)", re.I)
# Strong resolution words only. "done"/"complete" are left out on purpose:
# they mostly describe one finished phase of a still-open item.
RESOLVED_RE = re.compile(
    r"FIX APPLIED|\bfix(?:ed)? (?:landed|held|applied|shipped)\b|\bSHIPPED\b|"
    r"\bRESOLVED\b|\bFIXED\b|\bUPDATE [^\n]{0,40}\b(?:DONE|SHIPPED|LIVE)\b")

# Cues that a sentence passes judgment on an EARLIER entry.
RETRACT_CUE_RE = re.compile(
    r"\bretracted\b|\bretract(?:s|ing)? (?:the|my|that|this|it)\b|\bdisprov(?:ed|en)\b|"
    r"\bshown NOT\b|\bwas (?:wrong|a false alarm)\b|\bwere wrong\b|false alarm|"
    r"probably not the cause|(?:is|was) not the (?:root )?cause|"
    r"earlier [\w -]{0,40}(?:theory|claim|diagnosis|guess|hypothesis)")
SUPERSEDE_CUE_RE = re.compile(
    r"\bsupersedes\b|\bis (?:now )?superseded\b|\bsuperseded by\b|\bis stale\b|"
    r"\bno longer (?:true|holds|applies)\b|\bobsoleted\b", re.I)
OPEN_STATUS_RE = re.compile(
    r"\W{0,3}(?:in progress|pending|awaiting|in build|queued|code patched[^.]*pending|wip)\b", re.I)
HEADING_CUE_RE = re.compile(r"\bheading\b", re.I)

SHORT_DATE_RE = re.compile(r"(?<![\d:-])(?:(20\d\d)-)?(0[1-9]|1[0-2])-([0-3]\d)(?![\d:])")
QUOTE_RE = re.compile(r"[\"“]([^\"”]{6,160})[\"”]")
SENT_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(\"'`*-])|\n")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")
STOP = set("""the a an and or of to in on for is was are be been it its this that
with by as at from not but so if then than into over after before when were has had
have will would can could should entry bullet note earlier later same today dreaming
heading rule fix root cause pending applied agent operator session""".split())


def norm_tokens(text: str) -> set[str]:
    out = set()
    for t in TOKEN_RE.findall(text.lower()):
        if t in STOP or len(t) < 3:
            continue
        out.add(t[:5])
    return out


@dataclass
class Entry:
    file: str
    line: int
    kind: str                       # heading | block | bullet
    title: str
    date: str | None
    text: str = ""
    props: dict = field(default_factory=dict)
    parent_line: int | None = None  # enclosing heading for bullets
    id: str = ""
    state: str = "active"
    state_source: str = "implicit"
    end_line: int = 0

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}"


# ---------------------------------------------------------------- parsing

def parse_file(rel: str) -> list[Entry]:
    path = ROOT / rel
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    entries: list[Entry] = []
    cur: Entry | None = None
    cur_heading: Entry | None = None
    in_comment = False
    in_frontmatter = lines[:1] == ["---"]
    pending_block = False  # after a --- separator, next non-blank starts a block

    def close(n: int):
        nonlocal cur
        if cur is not None:
            cur.end_line = n
            entries.append(cur)
        cur = None

    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        if in_frontmatter:
            if i > 1 and line == "---":
                in_frontmatter = False
            continue
        if "<!--" in line and "-->" not in line:
            in_comment = True
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue

        m = HEADING_RE.match(line)
        if m:
            close(i - 1)
            title = m.group(2).strip()
            dm = DATE_IN_HEADING_RE.search(title)
            cur = Entry(rel, i, "heading", title, dm.group(1) if dm else None)
            cur_heading = cur
            pending_block = False
            continue
        if line == "---":
            close(i - 1)
            cur_heading = None
            pending_block = True
            continue
        bm = DATED_BULLET_RE.match(line)
        if bm:
            # A dated top-level bullet is its own claim (dreaming bullets, updates).
            close(i - 1)
            cur = Entry(rel, i, "bullet", line[2:2 + 160], bm.group(1),
                        parent_line=cur_heading.line if cur_heading else None)
            cur.text = line + "\n"
            continue
        if pending_block and line.strip():
            close(i - 1)
            cur = Entry(rel, i, "block", "", None)
            pending_block = False
        if cur is None:
            if not line.strip():
                continue
            cur = Entry(rel, i, "block", "", None)
        if cur.kind == "bullet" and (not line.strip() or not raw.startswith((" ", "\t"))):
            # bullet ends at blank line or next unindented line; that line
            # belongs back to the enclosing heading (approximation: new block)
            close(i - 1)
            if not line.strip():
                continue
            cur = Entry(rel, i, "block", "", None)
        cur.text += line + "\n"
        # a bullet's own props are indented under it ("  status:: superseded")
        pm = PROP_RE.match(line.strip() if cur.kind == "bullet" else line)
        if pm:
            k = pm.group(1).lower()
            cur.props.setdefault(k, pm.group(2).strip())
    close(len(lines))

    for e in entries:
        if e.kind == "heading":
            e.text = e.title + "\n" + e.text
        if not e.date and e.props.get("date"):
            e.date = e.props["date"][:10]
        if not e.title:
            e.title = (e.props.get("decision") or e.props.get("learning")
                       or e.props.get("context") or e.text.strip().split("\n")[0])[:160]
        e.id = e.props.get("id") or e.key
    return [e for e in entries if e.text.strip()]


def derive_state(e: Entry) -> None:
    st = (e.props.get("status") or "").strip().lower()
    first = st.split()[0].strip(".,;:") if st else ""
    if first in ("superseded", "disputed", "retracted", "active"):
        e.state, e.state_source = first, "status::"
        return
    t = e.title
    if TITLE_RETRACT_RE.search(t) or BODY_RETRACT_RE.search(e.text):
        e.state, e.state_source = "retracted", "text-marker"
    elif TITLE_SUPERSEDED_RE.search(t):
        e.state, e.state_source = "superseded", "text-marker"
    elif TITLE_DISPUTED_RE.search(t):
        e.state, e.state_source = "disputed", "text-marker"


# ---------------------------------------------------------------- refs + edges

def full_date(y: str | None, mo: str, d: str, ctx_date: str | None) -> str:
    year = y or (ctx_date[:4] if ctx_date else str(TODAY.year))
    return f"{year}-{mo}-{d}"


def resolve_ref(ref: str, entries: list[Entry], by_id: dict) -> Entry | None:
    ref = ref.strip()
    if ref in by_id:
        return by_id[ref]
    dm = SHORT_DATE_RE.search(ref)
    toks = norm_tokens(SHORT_DATE_RE.sub(" ", ref))
    cands = [e for e in entries if dm and e.date == full_date(*dm.groups(), None)] if dm else entries
    best, score = None, 0
    for c in cands:
        s = len(toks & norm_tokens(c.title))
        if s > score:
            best, score = c, s
    return best if score >= 2 else None


@dataclass
class Edge:
    src: str        # key of the later / dependent entry
    dst: str        # key of the referenced entry
    etype: str      # supersedes | retracts | depends-on | cites | stale-heading
    origin: str     # explicit | inferred
    evidence: str


def infer_edges(entries: list[Entry], by_key: dict) -> list[Edge]:
    edges: list[Edge] = []
    by_date: dict[str, list[Entry]] = {}
    for e in entries:
        if e.date:
            by_date.setdefault(e.date, []).append(e)
    for e in entries:
        for sent in SENT_SPLIT_RE.split(e.text):
            if len(sent) < 12:
                continue
            retract = RETRACT_CUE_RE.search(sent)
            supersede = SUPERSEDE_CUE_RE.search(sent)
            dates = [full_date(*m.groups(), e.date) for m in SHORT_DATE_RE.finditer(sent)]
            dates = [d for d in dates if d in by_date]
            quotes = " ".join(QUOTE_RE.findall(sent))
            stoks = norm_tokens(SHORT_DATE_RE.sub(" ", sent))
            qtoks = norm_tokens(quotes)
            # Judgment edges need an anchor: an explicit date, or a quoted
            # fragment of the target (same-day fallback only with a quote).
            cand_dates = dates or ([e.date] if (retract or supersede) and quotes and e.date in by_date else [])
            best, bscore = None, 0
            for d in cand_dates:
                for c in by_date[d]:
                    if c.key == e.key or (e.parent_line and c.line == e.parent_line and c.file == e.file):
                        continue
                    if c.file == e.file and c.line > e.line:
                        continue  # only judge EARLIER entries
                    ctoks = norm_tokens(c.title + " " + c.text[:400])
                    s = len(stoks & norm_tokens(c.title)) + len(qtoks & ctoks)
                    if s > bscore:
                        best, bscore = c, s
            if not best or bscore < 3:
                continue
            ev = sent.strip()[:220]
            if retract:
                edges.append(Edge(e.key, best.key, "retracts", "inferred", ev))
            elif supersede and HEADING_CUE_RE.search(sent):
                edges.append(Edge(e.key, best.key, "stale-heading", "inferred", ev))
            elif supersede and re.search(r"\bsupersedes\b", sent, re.I) and not re.search(r"is superseded|superseded by", sent, re.I):
                edges.append(Edge(e.key, best.key, "supersedes", "inferred", ev))
            elif supersede:
                edges.append(Edge(e.key, best.key, "supersedes", "inferred", ev))
            elif dates and bscore >= 3:
                edges.append(Edge(e.key, best.key, "cites", "inferred", ev))
    # de-dup, keep strongest per (src,dst)
    prio = {"retracts": 0, "supersedes": 1, "stale-heading": 2, "cites": 3}
    seen: dict[tuple, Edge] = {}
    for ed in edges:
        k = (ed.src, ed.dst)
        if k not in seen or prio[ed.etype] < prio[seen[k].etype]:
            seen[k] = ed
    return list(seen.values())


def explicit_edges(entries: list[Entry], by_id: dict) -> tuple[list[Edge], list[dict]]:
    edges, unresolved = [], []
    for e in entries:
        for prop, etype in (("supersedes", "supersedes"), ("depends-on", "depends-on")):
            v = e.props.get(prop)
            if not v:
                continue
            for ref in [r for r in re.split(r",\s*(?=\S)", v) if r.strip()]:
                t = resolve_ref(ref, entries, by_id)
                if t is None:
                    unresolved.append({"entry": e.key, "prop": prop, "ref": ref})
                else:
                    edges.append(Edge(e.key, t.key, etype, "explicit", f"{prop}:: {ref}"))
    return edges, unresolved


# ---------------------------------------------------------------- checks

def run(files: list[str]) -> dict:
    entries: list[Entry] = []
    for f in files:
        entries.extend(parse_file(f))
    for e in entries:
        derive_state(e)
    by_key = {e.key: e for e in entries}
    by_id = {e.id: e for e in entries}

    exp, unresolved = explicit_edges(entries, by_id)
    inf = infer_edges(entries, by_key)
    edges = exp + inf

    # inferred state: what the graph says the entry SHOULD be
    inferred: dict[str, tuple[str, Edge]] = {}

    def push(key, state, edge):
        if key not in inferred or RANK[state] > RANK[inferred[key][0]]:
            inferred[key] = (state, edge)

    for ed in edges:
        if ed.etype == "supersedes":
            push(ed.dst, "superseded", ed)
        elif ed.etype == "retracts":
            push(ed.dst, "disputed", ed)

    def effective(k: str) -> str:
        s = by_key[k].state
        if k in inferred and RANK[inferred[k][0]] > RANK[s]:
            return inferred[k][0]
        return s

    # 1. contradicted but unmarked
    contradicted = []
    for k, (st, ed) in inferred.items():
        e = by_key[k]
        if e.state == "active":
            contradicted.append({"entry": k, "title": e.title[:140], "should_be": st,
                                 "by": ed.src, "edge": ed.etype, "origin": ed.origin,
                                 "evidence": ed.evidence})

    # 2. stale dependents, BFS cascade over depends-on / cites (PACMI Alg. 1)
    out_dep: dict[str, list[Edge]] = {}
    for ed in edges:
        if ed.etype in CASCADE:
            out_dep.setdefault(ed.dst, []).append(ed)  # parent -> dependents
    cascade_state: dict[str, tuple[str, Edge]] = {}
    queue = [k for k in by_key if effective(k) in NON_CURRENT]
    while queue:
        u = queue.pop(0)
        for ed in out_dep.get(u, []):
            v = ed.src
            s = CASCADE[ed.etype]
            if effective(v) in NON_CURRENT:
                continue
            if v not in cascade_state or RANK[s] > RANK[cascade_state[v][0]]:
                cascade_state[v] = (s, ed)
                queue.append(v)
    stale_deps = [{"entry": v, "title": by_key[v].title[:140], "state": s,
                   "parent": ed.dst, "parent_state": effective(ed.dst),
                   "edge": ed.etype, "origin": ed.origin}
                  for v, (s, ed) in cascade_state.items()]

    # 3. headings that contradict their own body or a later entry
    headings = []
    later_heading_flags = {ed.dst: ed for ed in edges if ed.etype == "stale-heading"}
    for e in entries:
        if e.kind not in ("heading",) and not (e.kind == "block" and e.props.get("status")):
            continue
        label = e.title if e.kind == "heading" else e.props.get("status", "")
        # already hand-marked as no longer true: the stale heading is kept on purpose (history)
        if (e.props.get("status") or "").split()[:1] in (["superseded"], ["disputed"], ["retracted"]):
            continue
        if not PENDING_RE.search(label):
            continue
        body = e.text[len(e.title):] if e.kind == "heading" else e.text
        # never let the status line resolve itself (mixed "X shipped, Y awaiting")
        body = "\n".join(l for l in body.splitlines() if not l.lower().startswith("status::"))
        own = RESOLVED_RE.search(body)
        later = later_heading_flags.get(e.key)
        resolved_later = [ed for ed in edges if ed.dst == e.key and ed.etype in ("supersedes", "retracts")]
        if own or later or resolved_later:
            why = []
            if own:
                why.append(f"own body says '{own.group(0)}'")
            if later:
                why.append(f"later entry {later.src} calls it stale")
            for ed in resolved_later:
                why.append(f"later entry {ed.src} {ed.etype} it")
            headings.append({"entry": e.key, "title": label[:140], "why": "; ".join(why)})

    # 4. aging open status in key:: blocks
    aging = []
    for e in entries:
        st = e.props.get("status", "")
        if (st and e.date and OPEN_STATUS_RE.match(st)
                and not re.search(r"\u2705|\bSHIPPED\b|\bDONE\b|\bLIVE\b|\bcomplete", st, re.I)):
            try:
                age = (TODAY - datetime.strptime(e.date, "%Y-%m-%d").date()).days
            except ValueError:
                continue
            if age > STATUS_AGE_DAYS:
                aging.append({"entry": e.key, "date": e.date, "age_days": age,
                              "status": st[:100], "title": e.title[:100]})

    # 5. recall marker audit: what vector_brain would demote. Uses its live stance_factor()
    # when the recall engine exposes one, else the text regex above.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from vector_brain import stance_factor as _vb_stance
        _demoted = lambda t: _vb_stance(t) < 1.0
        _view = lambda e: ("## " + e.text) if e.kind == "heading" else e.text  # chunks keep the "## "
    except Exception:
        _demoted = lambda t: bool(VB_SUPERSEDED_RE.search(t))
        _view = lambda e: e.text
    false_demote, missed, true_demote = [], [], 0
    for e in entries:
        hit = _demoted(_view(e))
        eff = effective(e.key)
        cur = eff not in NON_CURRENT
        if hit and cur:
            m = VB_SUPERSEDED_RE.search(e.text)
            ctx = e.text[max(0, m.start() - 40):m.end() + 40] if m else e.text[:80]
            false_demote.append({"entry": e.key, "title": e.title[:120],
                                 "matched": ctx.replace("\n", " ")})
        elif hit:
            true_demote += 1
        elif not cur:
            missed.append({"entry": e.key, "title": e.title[:120], "state": eff})

    # inversions: the NEWER entry is demoted (it says "supersedes X") while
    # the OLDER entry it replaces is not. Recall then prefers the stale one.
    inversions = []
    for ed in edges:
        if ed.etype not in ("supersedes", "retracts"):
            continue
        src, dst = by_key[ed.src], by_key[ed.dst]
        if _demoted(_view(src)) and not _demoted(_view(dst)):
            inversions.append({"newer": ed.src, "older": ed.dst, "older_title": dst.title[:100]})

    counts_state = {}
    for e in entries:
        counts_state[effective(e.key)] = counts_state.get(effective(e.key), 0) + 1
    return {
        "files": files,
        "entries": len(entries),
        "by_kind": {k: sum(1 for e in entries if e.kind == k) for k in ("heading", "block", "bullet")},
        "marked_state_counts": {s: sum(1 for e in entries if e.state == s) for s in LATTICE},
        "effective_state_counts": counts_state,
        "convention_usage": {p: sum(1 for e in entries if p in e.props) for p in ("id", "supersedes", "depends-on")},
        "edges": {"explicit": len(exp), "inferred": len(inf),
                  "by_type": {t: sum(1 for ed in edges if ed.etype == t)
                              for t in ("supersedes", "retracts", "stale-heading", "depends-on", "cites")}},
        "unresolved_refs": unresolved,
        "contradicted_unmarked": sorted(contradicted, key=lambda x: x["entry"]),
        "stale_dependents": stale_deps,
        "contradicted_headings": headings,
        "aging_open_status": sorted(aging, key=lambda x: -x["age_days"]),
        "recall_audit": {"true_demotions": true_demote, "false_demotions": len(false_demote),
                         "missed_demotions": len(missed), "inversions": inversions,
                         "false_demotion_examples": false_demote, "missed_examples": missed},
    }


def print_report(r: dict, limit: int) -> None:
    p = print
    p(f"memory_supersession_check  ({TODAY.isoformat()})  read-only")
    p(f"files: {', '.join(r['files'])}")
    p(f"entries parsed: {r['entries']}  {r['by_kind']}")
    p(f"marked states: {r['marked_state_counts']}")
    p(f"effective states (marks + inferred edges): {r['effective_state_counts']}")
    p(f"convention usage: {r['convention_usage']}")
    p(f"edges: {r['edges']}")
    if r["unresolved_refs"]:
        p(f"unresolved explicit refs: {len(r['unresolved_refs'])}")

    def section(name, rows, fmt):
        p(f"\n== {name}: {len(rows)}")
        for row in rows[:limit]:
            p("  " + fmt(row))
        if len(rows) > limit:
            p(f"  ... {len(rows) - limit} more (use --limit or --json)")

    section("1. contradicted but unmarked (recall still treats as current)",
            r["contradicted_unmarked"],
            lambda x: f"{x['entry']}  should be {x['should_be']} ({x['origin']} {x['edge']} by {x['by']})\n"
                      f"      title: {x['title']}\n      evidence: {x['evidence'][:200]}")
    section("2. stale dependents (cascade)", r["stale_dependents"],
            lambda x: f"{x['entry']}  -> {x['state']} via {x['origin']} {x['edge']} on {x['parent']} ({x['parent_state']})\n"
                      f"      title: {x['title']}")
    section("3. contradicted headings", r["contradicted_headings"],
            lambda x: f"{x['entry']}  {x['title']}\n      why: {x['why']}")
    section(f"4. open status older than {STATUS_AGE_DAYS} days", r["aging_open_status"],
            lambda x: f"{x['entry']}  {x['date']} ({x['age_days']}d)  status: {x['status']}")
    a = r["recall_audit"]
    p(f"\n== 5. vector_brain text-marker audit")
    p(f"  true demotions: {a['true_demotions']}  false demotions (current entry demoted): "
      f"{a['false_demotions']}  missed (non-current, not demoted): {a['missed_demotions']}")
    p(f"  inversions (newer entry demoted, older entry it replaces NOT demoted): {len(a['inversions'])}")
    for x in a["inversions"][:limit]:
        p(f"  INV   newer {x['newer']} demoted, older {x['older']} full weight: {x['older_title'][:80]}")
    for x in a["false_demotion_examples"][:min(limit, 8)]:
        p(f"  FALSE {x['entry']}  ...{x['matched'][:120]}...")
    for x in a["missed_examples"][:min(limit, 8)]:
        p(f"  MISS  {x['entry']}  [{x['state']}] {x['title'][:100]}")


_SELFTEST_LEARNINGS = """# Learnings

## 2026-09-01 Export job fails because the disk is full
The nightly export job for Acme fails. Root cause: the disk is full.

## 2026-09-03 Export job disk theory was wrong
The earlier disk-full theory (09-01) for the Acme export job was wrong, the export job fails on an
expired credential. "nightly export job for Acme fails" is shown NOT to be disk related.

## 2026-09-04 Retry wrapper for the export job
depends-on:: 2026-09-01 export job disk full
Adds a retry wrapper sized for the disk-full failure of the export job.

- 2026-08-01 Old rule for widget naming
  status:: superseded
"""


def _selftest() -> int:
    """Fabricated memory: a later entry disproves an earlier one, a third depends on it."""
    import tempfile
    global ROOT
    old = ROOT
    with tempfile.TemporaryDirectory() as td:
        ROOT = Path(td)
        (ROOT / "memory").mkdir()
        (ROOT / "memory" / "Learnings.md").write_text(_SELFTEST_LEARNINGS)
        try:
            r = run(["memory/Learnings.md", "memory/missing.md"])
        finally:
            ROOT = old
    checks = {
        "parsed": r["entries"] >= 4,
        "contradicted_unmarked": any(x["entry"].endswith(":3") for x in r["contradicted_unmarked"]),
        "explicit_depends_on": r["convention_usage"]["depends-on"] == 1,
        "stale_dependent": any(x["entry"].endswith(":10") for x in r["stale_dependents"]),
        "marked_superseded": r["marked_state_counts"]["superseded"] == 1,
    }
    for k, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {k}")
    bad = sum(not v for v in checks.values())
    print("selftest: PASS" if not bad else f"selftest: {bad} FAIL")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--files", nargs="*", default=DEFAULT_FILES)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--selftest", action="store_true", help="run on fabricated memory in a temp dir")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    r = run(args.files)
    if args.json:
        json.dump(r, sys.stdout, indent=1, ensure_ascii=False)
        print()
    else:
        print_report(r, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
