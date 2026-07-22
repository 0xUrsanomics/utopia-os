#!/usr/bin/env python3
# lib_provenance.py — provenance + corroboration stamps for durable memory entries.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Provenance and corroboration stamps for durable memory entries.

WHY THIS EXISTS. Three unrelated agent-memory papers (GovMem 2607.02579,
A-TMA 2607.01935, FARMA 2607.05029) independently identified the same missing
primitive in systems shaped like this one: nothing records where a memory came
from, so at retrieval time a belief formed once is indistinguishable from a
belief confirmed many times independently.

The live failure mode: a single conversation produces N memory entries. They
share one session and one reasoning chain, so they are correlated by
construction, yet each is written as though independently established. A later
session reading all N sees N agreeing records and has no way to know they are
one record restated.

DESIGN, and why it is inline rather than a sidecar index:
  - a semantic-recall indexer that chunks markdown on `##` heading boundaries
    will carry a line placed directly under an entry heading INSIDE that chunk.
    Retrieval surfacing is therefore free: no indexer change, no reindex
    coupling, no schema migration. This is the whole reason for the inline choice.
  - A sidecar keyed by file+heading would need stable anchors into append-only
    prose and would silently desync the first time a heading is edited.
  - It stays human-readable and greppable, and matches the `key:: value`
    convention already used throughout memory/.

FIELDS, kept to what answers "what does this claim actually rest on?":
  agent    which agent wrote it (multiple agents write to shared surfaces)
  session  session id. Two entries sharing this are NOT independent evidence.
  support  once | Nx  where N counts INDEPENDENT incidents, not restatements
  ingest   clean | untrusted. Whether the producing session processed external
           content. This is the belief-path flag: an "authority is the envelope"
           rule blocks the instruction path, but untrusted content can still shift
           what an agent CONCLUDES, and that conclusion is then written with
           genuinely legitimate agent provenance which no provenance check catches.

Deliberately NOT a forgery detector. Content pattern-matching (phrase/format
scoring) is defeated by a paraphrase and would flag deliberately-schematised
entries as forged. Metadata about origin is durable in a way that
pattern-matching on content is not.

    python3 lib_provenance.py stamp --support once
    python3 lib_provenance.py audit           # corpus coverage + session clusters
    python3 lib_provenance.py audit --file memory/Learnings.md
"""
from __future__ import annotations

import argparse
import json
import datetime
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# AGENT_ROOT defaults to the repo root (this file is scripts/memory/lib_provenance.py).
REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
# Local timezone as a fixed UTC offset (hours). Default 0 = UTC. Override with
# AGENT_UTC_OFFSET_HOURS (e.g. "7", "-5", "5.5").
LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=float(os.environ.get("AGENT_UTC_OFFSET_HOURS", "0"))))

# Files that carry durable, retrievable claims. Deliberately excludes memory/state/
# (runtime cursors, not claims) and personas (sidecar JSON, different shape).
CORPUS = ["memory/Learnings.md", "memory/Decisions.md",
          "memory/Context/*.md", "memory/Infra/*.md", "memory/Feedback/*.md"]

LINE = re.compile(
    r"^provenance::\s*"
    r"agent=(?P<agent>\S+)\s+"
    r"session=(?P<session>\S+)\s+"
    r"support=(?P<support>\S+)\s+"
    r"ingest=(?P<ingest>\S+)\s*$", re.M)

VALID_INGEST = {"clean", "untrusted"}
SUPPORT = re.compile(r"^(once|\d+x)$")


STATE = REPO / "memory/state/provenance-session.json"
IDLE_HOURS = 6.0


def session_id(now: datetime.datetime | None = None, agent: str = "agent") -> str:
    """Stable id for the current session, stable ACROSS MIDNIGHT.

    Prefers the harness session identifier when present, so two /save runs in one
    conversation collapse to one id, which is the entire point.

    A bare date-stamp fallback is wrong: one continuous conversation that crosses
    midnight would produce two different session ids, so the cluster detector would
    report sibling entries as INDEPENDENT. That is the exact false-independence this
    module exists to prevent, produced by the module itself.

    Fixed by caching the id with an idle timeout: reuse while activity continues,
    mint a new one only after IDLE_HOURS of silence. Errs toward over-grouping
    (treating a genuinely new session as a continuation) because over-grouping
    understates independence, and understating it is the safe direction.
    """
    sid = os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("AGENT_SESSION_ID")
    if sid:
        return sid[:12]

    now = now or datetime.datetime.now(LOCAL_TZ)
    cache = {}
    if STATE.exists():
        try:
            cache = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}          # unreadable cache must not break a write path

    prev = cache.get(agent) or {}
    cur = prev.get("id")
    try:
        last = datetime.datetime.fromisoformat(prev["last_used"])
        idle = (now - last).total_seconds() / 3600.0
    except Exception:
        idle = float("inf")

    if not cur or idle > IDLE_HOURS:
        day = now.strftime("%Y-%m-%d")
        # Suffix distinguishes multiple sessions in one day without colliding.
        used = {v.get("id", "") for v in cache.values() if isinstance(v, dict)}
        suffix, i = "a", 0
        while f"{day}{suffix}" in used and i < 25:
            i += 1
            suffix = chr(ord("a") + i)
        cur = f"{day}{suffix}"

    cache[agent] = {"id": cur, "last_used": now.isoformat()}
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".json.tmp")      # atomic, per atomic-state-file-writes
        # SSOT-canonical write. Fallback to direct write if the ssot helper is absent.
        try:
            import sys as _S, os as _O; _S.path.insert(0, _O.path.dirname(_O.path.abspath(__file__)))
            import ssot as _SSOT; _SSOT.set_("session.provenance", cache, by="lib-provenance", reason="provenance session assign")
        except Exception:
            tmp.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
            tmp.replace(STATE)

    except Exception:
        pass                    # a read-only FS must degrade, never block the write
    return cur


def stamp(agent: str = "agent", support: str = "once", ingest: str = "clean",
          session: str | None = None) -> str:
    """Render a provenance line. Refuses malformed values rather than emitting them."""
    if not SUPPORT.match(support):
        raise ValueError(f"support must be 'once' or 'Nx' (e.g. 3x), got {support!r}")
    if ingest not in VALID_INGEST:
        raise ValueError(f"ingest must be one of {sorted(VALID_INGEST)}, got {ingest!r}")
    # agent MUST be threaded through: the cache is keyed per agent, and calling
    # session_id() bare would hand a sibling tenant's session id, silently merging
    # two independent conversations into one "cluster".
    return (f"provenance:: agent={agent} session={session or session_id(agent=agent)} "
            f"support={support} ingest={ingest}")


def parse(text: str) -> dict | None:
    m = LINE.search(text)
    return m.groupdict() if m else None


def entries(path: Path) -> list[tuple[str, str]]:
    """Split a memory file into (heading, body) on `##` boundaries.

    Matches the recall indexer's chunking boundary on purpose: if the two
    disagreed, a stamp could sit in a different chunk than the claim it describes,
    which would be worse than no stamp at all.
    """
    parts = re.split(r"\n(?=##\s)", path.read_text(encoding="utf-8"))
    out = []
    for p in parts:
        if not p.startswith("##"):
            continue
        head = p.split("\n", 1)[0].strip()
        out.append((head, p))
    return out


def _files() -> list[Path]:
    seen = []
    for pat in CORPUS:
        if "*" in pat:
            seen.extend(sorted((REPO / pat.rsplit("/", 1)[0]).glob(pat.rsplit("/", 1)[1])))
        else:
            p = REPO / pat
            if p.exists():
                seen.append(p)
    return seen


def audit(only: Path | None = None) -> dict:
    """Report stamp coverage and, more importantly, same-session clusters.

    A cluster of k entries sharing one session is k restatements of one origin
    presenting as k independent records. That is the failure this whole primitive
    exists to make visible, so it is the headline of the report rather than a detail.
    """
    stamped, unstamped = [], []
    by_session = defaultdict(list)
    for f in ([only] if only else _files()):
        for head, body in entries(f):
            rel = str(f.relative_to(REPO))
            p = parse(body)
            if p:
                stamped.append((rel, head, p))
                by_session[p["session"]].append((rel, head))
            else:
                unstamped.append((rel, head))
    clusters = {s: v for s, v in by_session.items() if len(v) > 1}
    untrusted = [(r, h) for r, h, p in stamped if p["ingest"] == "untrusted"]
    return {"stamped": stamped, "unstamped": unstamped,
            "clusters": clusters, "untrusted": untrusted}


CONF = re.compile(r"^confidence::\s*([0-9.]+)\s*$", re.M)
EVID = re.compile(r"^evidence::\s*\[([^\]]*)\]\s*$", re.M)

# Phrases in an evidence:: note that betray a SINGLE origin behind a multi-count claim.
# The convention is that confidence rises on "each independent re-confirmation in a LATER
# session" — these phrases say the opposite out loud.
SAME_ORIGIN = re.compile(
    r"same-day|same day|one-audit|one audit|single-session|co-occurring|in-one-|"
    r"same-session|one-session|same-run|one-run", re.I)


def confidence_audit(only: Path | None = None) -> dict:
    """Flag confidence:: values that were raised on CORRELATED observations.

    A confidence bump is granted per "independent re-confirmation in a later
    session". If independence is enforced by convention but never checked, a claim
    seen three times inside one audit can be scored as though seen three times across
    three sessions. The GovMem paper names exactly this: "observations that share
    prompts, tools, intermediate context, or parent events should not count as
    independent votes."

    Two detectable shapes, both conservative (they only fire on self-reported evidence):
      1. the evidence note SAYS single-origin ("same-day", "in-one-audit", "co-occurring")
      2. count > 1 while only ONE date is recorded, so nothing attests to spread over time
    Entries with no evidence:: at all are reported separately as unverifiable, not as
    violations, because absence of a record is not proof of correlation.
    """
    flagged, unverifiable, ok = [], [], []
    for f in ([only] if only else _files()):
        for head, body in entries(f):
            c = CONF.search(body)
            if not c:
                continue
            rel, conf = str(f.relative_to(REPO)), float(c.group(1))
            e = EVID.search(body)
            if not e:
                unverifiable.append((rel, head, conf))
                continue
            raw = e.group(1)
            parts = [x.strip() for x in raw.split(",")]
            note = " ".join(parts[2:]) if len(parts) > 2 else ""
            try:
                count = int(parts[0])
            except (ValueError, IndexError):
                count = 1
            dates = re.findall(r"\d{4}-\d{2}-\d{2}", raw)
            reason = None
            if SAME_ORIGIN.search(note):
                reason = f"note declares single origin: {note[:48]}"
            elif count > 1 and len(set(dates)) <= 1:
                reason = f"count={count} but only {len(set(dates))} distinct date recorded"
            (flagged if reason else ok).append((rel, head, conf, reason or ""))
    return {"flagged": flagged, "unverifiable": unverifiable, "ok": ok}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("confidence", help="flag confidence:: raised on correlated observations")
    c.add_argument("--file", default=None)
    c.add_argument("--show", type=int, default=10)

    s = sub.add_parser("stamp", help="print a provenance line for a new entry")
    s.add_argument("--agent", default="agent")
    s.add_argument("--support", default="once", help="'once' or 'Nx' for N independent incidents")
    s.add_argument("--ingest", default="clean", choices=sorted(VALID_INGEST))
    s.add_argument("--session", default=None)

    a = sub.add_parser("audit", help="stamp coverage + same-session clusters")
    a.add_argument("--file", default=None)
    a.add_argument("--show", type=int, default=6, help="max rows per section")

    args = ap.parse_args()

    if args.cmd == "stamp":
        try:
            print(stamp(args.agent, args.support, args.ingest, args.session))
        except ValueError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 2
        return 0

    if args.cmd == "confidence":
        r = confidence_audit(Path(args.file).resolve() if args.file else None)
        tot = len(r["flagged"]) + len(r["unverifiable"]) + len(r["ok"])
        print(f"entries with confidence:: {tot}   "
              f"flagged: {len(r['flagged'])}   "
              f"no evidence:: to check: {len(r['unverifiable'])}   "
              f"looks independent: {len(r['ok'])}")
        if r["flagged"]:
            print("\nconfidence raised on CORRELATED observations "
                  "(these are one origin counted as many):")
            for rel, head, conf, why in r["flagged"][:args.show]:
                print(f"  {conf:>4}  {head[:56]}")
                print(f"        {rel}  ::  {why}")
        if r["unverifiable"]:
            print(f"\nno evidence:: array, so independence is unverifiable "
                  f"({len(r['unverifiable'])}). Not violations, just unprovable:")
            for rel, head, conf in r["unverifiable"][:args.show]:
                print(f"  {conf:>4}  {head[:60]}")
        return 0

    r = audit(Path(args.file).resolve() if args.file else None)
    tot = len(r["stamped"]) + len(r["unstamped"])
    pct = (len(r["stamped"]) / tot * 100) if tot else 0.0
    print(f"entries: {tot}   stamped: {len(r['stamped'])} ({pct:.1f}%)   "
          f"unstamped: {len(r['unstamped'])}")
    print("  unstamped entries predate the primitive. That is honest missing data, "
          "not a defect to backfill: their real origin is unrecoverable and inventing\n"
          "  one would manufacture exactly the false confidence this is meant to prevent.")

    if r["clusters"]:
        print(f"\nsame-session clusters ({len(r['clusters'])}). "
              f"Entries here are NOT independent evidence of each other:")
        for sess, items in sorted(r["clusters"].items(), key=lambda kv: -len(kv[1])):
            print(f"  session {sess}: {len(items)} entries")
            for rel, head in items[:args.show]:
                print(f"      {rel}  {head[:64]}")
    else:
        print("\nsame-session clusters: none")

    if r["untrusted"]:
        print(f"\nformed in sessions that ingested untrusted content ({len(r['untrusted'])}):")
        for rel, head in r["untrusted"][:args.show]:
            print(f"      {rel}  {head[:64]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
