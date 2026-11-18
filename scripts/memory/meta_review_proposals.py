#!/usr/bin/env python3
# meta_review_proposals.py: proposal-state ledger for the meta-memory-review skill.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Proposal-state ledger for meta-memory-review.

The failure the review exists to catch can happen inside the review itself: a run's
proposals age with zero decisions, because nothing tracks their state and "declined"
is indistinguishable from "not yet looked at" (both are silence). Meanwhile the next
run re-derives the same findings from scratch. This makes each proposal a row with an
explicit state, so a run reports the OPEN set FIRST (with age) and only then hunts for
new findings. "declined" is a valid terminal outcome and it costs one word; the
absence of that word is what is expensive.

Store: memory/state/meta_review_proposals.json
States: open | applied | declined

The DRAIN. A proposal used to close only when the operator answered, so work that
landed through any other path (a dreaming cycle, an unrelated session, a cron fix)
left the ledger asserting `open` forever and the next review re-derived it. Each proposal
may now carry an optional `resolved_when` shell predicate (its machine-checkable
done-condition). `verify` runs every OPEN proposal's predicate and auto-transitions the
passers to `applied` with an `auto-verified` note. A proposal with no predicate stays
manual (decline is still a valid one-word outcome). Register the predicate at `add` time,
so a proposal that cannot state its own done-condition is visibly unfalsifiable when filed.

Usage:
  meta_review_proposals.py                              # list OPEN proposals (default)
  meta_review_proposals.py list [--all]                 # open only, or all
  meta_review_proposals.py add <id> <review_date> "<title>" [--resolved-when "<pred>" --kind K --approved-by "<who>"]
  meta_review_proposals.py set <id> <applied|declined|open> ["note"]   # transition
  meta_review_proposals.py set-predicate <id> "<shell predicate>" --kind K --approved-by "<who>"
  meta_review_proposals.py verify [--dry-run]           # run open predicates, auto-close passers
  meta_review_proposals.py rm <id>                      # remove a proposal (test/cleanup)

resolved_when predicates run via the shell (shell=True) with cwd=REPO, so a predicate is
arbitrary code. The ledger lives in memory/state/, which is gitignored and agent-writable: it
is NOT reviewed like a repo script. Adding or editing a predicate is therefore a CONFIRM
(operator-approved) action. Record the approval with --approved-by "<who, which message>"
on add or set-predicate. `verify` refuses to run any predicate whose entry has no
`approved_by` (it prints why and exits 2), and set-predicate clears an old approval when the
predicate text or kind changes. This is an operator convention, not a security boundary: anything
that can write the ledger can also write the field. Keep predicates cheap and read-only (a
grep/test), exit 0 == resolved.

Exit 2 also when the ledger exists but is corrupt or the wrong shape; nothing is written
over it, so fix or restore the file by hand.

Predicate kinds: `outcome` measures the effect and may auto-close; `impl` only greps the
code, so a pass is flagged for a human read and never auto-closes.

Env (optional): AGENT_ROOT (repo root), AGENT_TZ (IANA timezone for dates and ages, default UTC).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
STORE = REPO / "memory" / "state" / "meta_review_proposals.json"
STATES = ("open", "applied", "declined")
PREDICATE_TIMEOUT_S = 30


def _load() -> dict:
    """Missing ledger = empty. A corrupt or wrong-shape ledger exits 2 here, before any
    caller can write, so the next save never overwrites it with an empty one."""
    if not STORE.exists():
        return {"_schema": "meta-review-proposals-v1", "proposals": []}
    try:
        d = json.loads(STORE.read_text())
    except (OSError, ValueError) as e:
        print(f"ledger unreadable ({STORE}): {type(e).__name__}: {e}. Not touching it; "
              "fix or restore it by hand", file=sys.stderr)
        sys.exit(2)
    if not isinstance(d, dict) or not isinstance(d.get("proposals"), list):
        print(f"ledger has the wrong shape ({STORE}): expected an object with a 'proposals' list. "
              "Not touching it; fix or restore it by hand", file=sys.stderr)
        sys.exit(2)
    return d


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


# Dates use the operator's local timezone. A review that runs early morning local time can still
# be the previous day in UTC, so UTC dates made every age 1 day short and the aging alarm a week late.
TZ = ZoneInfo(os.environ.get("AGENT_TZ", "UTC"))


def _today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def _age_days(review_date: str):
    try:
        d = datetime.strptime(review_date, "%Y-%m-%d").date()
        return (datetime.now(TZ).date() - d).days
    except Exception:
        return None


KINDS = ("outcome", "impl")


def add(pid: str, review_date: str, title: str, resolved_when: str = "", kind: str = "",
        approved_by: str = "") -> None:
    d = _load()
    if any(p["id"] == pid for p in d["proposals"]):
        print(f"exists: {pid} (use set to transition)")
        return
    review_date = review_date or _today()
    if review_date > _today():
        # review_date is the FILING date; a future date made ages negative and hid the item
        print(f"refused: review_date {review_date} is after today {_today()} ({TZ}); pass the filing date")
        return
    if resolved_when.strip() and kind not in KINDS:
        print(f"refused: a predicate needs --kind {'|'.join(KINDS)}")
        return
    d["proposals"].append({
        "id": pid, "review_date": review_date, "title": title[:200],
        "state": "open", "decided_at": None, "note": "",
        "resolved_when": (resolved_when or "")[:500],
        "predicate_kind": kind if resolved_when.strip() else "",
        "approved_by": approved_by.strip() if resolved_when.strip() else "",
    })
    _save(d)
    pred = " +predicate" if resolved_when.strip() else " (no predicate, manual-close only)"
    if resolved_when.strip() and not approved_by.strip():
        pred += ", NOT approved (verify will refuse it until set-predicate --approved-by)"
    print(f"added {pid} (open, {review_date}){pred}")


def set_predicate(pid: str, predicate: str, kind: str = "", approved_by: str = "") -> None:
    if predicate.strip() and kind not in KINDS:
        print(f"refused: a predicate needs --kind {'|'.join(KINDS)}")
        return
    if len(predicate or "") > 500:  # was silently cut at 500 chars, storing a broken predicate
        print(f"refused: predicate is {len(predicate)} chars, max 500. Put the check in a script and call it")
        sys.exit(2)
    d = _load()
    for p in d["proposals"]:
        if p["id"] == pid:
            changed = ((p.get("resolved_when") or "") != (predicate or "")
                       or (p.get("predicate_kind") or "") != (kind if predicate.strip() else ""))
            p["resolved_when"] = (predicate or "")[:500]
            p["predicate_kind"] = kind if predicate.strip() else ""
            if approved_by.strip():
                p["approved_by"] = approved_by.strip()
            elif changed or not predicate.strip():
                p["approved_by"] = ""  # an approval covers the text it was given for, not an edit
            _save(d)
            print(f"{pid} resolved_when {'set' if predicate.strip() else 'cleared'}"
                  + ("" if p.get("approved_by") or not predicate.strip()
                     else ", NOT approved (verify will refuse it until --approved-by)"))
            return
    print(f"not found: {pid} (add it first)")


def rm(pid: str) -> None:
    d = _load()
    before = len(d["proposals"])
    d["proposals"] = [p for p in d["proposals"] if p["id"] != pid]
    if len(d["proposals"]) == before:
        print(f"not found: {pid}")
        return
    _save(d)
    print(f"removed {pid}")


def _run_predicate(pred: str):
    """Run a stored shell predicate. Returns (passed, detail). Exit 0 == resolved."""
    try:
        r = subprocess.run(pred, shell=True, cwd=str(REPO),
                           capture_output=True, text=True, timeout=PREDICATE_TIMEOUT_S)
        detail = (r.stderr or r.stdout or "").strip().replace("\n", " ")[:160]
        return r.returncode == 0, detail
    except subprocess.TimeoutExpired:
        return False, f"predicate timed out (>{PREDICATE_TIMEOUT_S}s)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _approved(p: dict, refused: list) -> bool:
    if (p.get("approved_by") or "").strip():
        return True
    refused.append(p["id"])
    print(f"[refused]     {p['id']}: predicate has no approved_by, not run. A predicate runs as "
          "shell code, so adding or editing one is a CONFIRM action: get operator approval, then "
          f"`set-predicate {p['id']} \"<pred>\" --kind K --approved-by \"<who>\"`")
    return False


def verify(dry_run: bool = False) -> int:
    """Step 0 drain: run every OPEN proposal's resolved_when predicate; auto-close passers.
    Returns 2 if any predicate was refused for lacking approved_by, else 0."""
    d = _load()
    checked = closed = 0
    refused: list = []
    # Applied OUTCOME predicates are re-run too, so a fix that broke again shows up at the top of
    # Step 0. Report only, never reopen: a person reads the cause first (a red can come from an
    # outage, such as DNS being down, rather than from the code).
    regressed = []
    for p in d["proposals"]:
        if p.get("state") != "applied" or p.get("predicate_kind") != "outcome":
            continue
        pred = (p.get("resolved_when") or "").strip()
        if not pred or not _approved(p, refused):
            continue
        ok, detail = _run_predicate(pred)
        if not ok:
            regressed.append((p["id"], detail, p.get("note", "")))
    for pid, detail, note in regressed:
        print(f"[regressed]   {pid}: applied outcome predicate now FAILS ({detail or 'nonzero exit'})"
              f" | last note: {note[:120]}")
    if regressed:
        print(f"verify: {len(regressed)} applied proposal(s) regressed; read the cause before reopening\n")
    for p in d["proposals"]:
        if p.get("state") != "open":
            continue
        pred = (p.get("resolved_when") or "").strip()
        if not pred or not _approved(p, refused):
            continue
        checked += 1
        passed, detail = _run_predicate(pred)
        kind = p.get("predicate_kind") or ""
        if passed and kind != "outcome":
            # An impl predicate (or a legacy one with no kind) only proves the code changed,
            # not that the effect happened. Flag it for a human read; never auto-close.
            print(f"[would-close] {p['id']}: {kind or 'unkinded'} predicate passed, read the change, "
                  f"then `set {p['id']} applied` or re-predicate with --kind outcome")
            continue
        if passed:
            closed += 1
            if dry_run:
                print(f"[would-close] {p['id']}: predicate passed")
            else:
                p["state"] = "applied"
                p["decided_at"] = _today()
                p["note"] = f"auto-verified {_today()} (Step 0 resolved_when passed)"
                print(f"[auto-close]  {p['id']}: predicate passed -> applied")
        else:
            print(f"[still-open]  {p['id']}: predicate failed ({detail or 'nonzero exit'})")
    if closed and not dry_run:
        _save(d)
    print(f"\nverify: {checked} open proposal(s) with a predicate, {closed} auto-closed"
          + (" (dry-run, no writes)" if dry_run else ""))
    if refused:
        print(f"verify: FAIL, {len(refused)} predicate(s) refused for missing approved_by: "
              + ", ".join(refused), file=sys.stderr)
        return 2
    return 0


def set_state(pid: str, state: str, note: str = "") -> None:
    if state not in STATES:
        print(f"state must be one of {STATES}")
        return
    d = _load()
    for p in d["proposals"]:
        if p["id"] == pid:
            p["state"] = state
            p["decided_at"] = None if state == "open" else _today()
            if note:
                p["note"] = note[:300]
            _save(d)
            print(f"{pid} -> {state}")
            return
    print(f"not found: {pid} (add it first)")


def list_(show_all: bool = False) -> None:
    d = _load()
    ps = [p for p in d["proposals"] if show_all or p["state"] == "open"]
    if not ps:
        print("(no proposals tracked)" if show_all else "(no OPEN proposals, all decided)")
        return
    # open first, then by review_date (oldest first, so aging items surface at top)
    ps.sort(key=lambda p: (p["state"] != "open", p["review_date"]))
    aging = 0
    for p in ps:
        age = _age_days(p["review_date"])
        agestr = f"{age}d" if isinstance(age, int) else "?"
        alarm = ""
        if p["state"] == "open" and isinstance(age, int) and age >= 14:
            alarm = "  <- AGING >2 cycles, decide or decline"
            aging += 1
        tag = ""
        if p["state"] == "open":
            tag = " [auto]" if (p.get("resolved_when") or "").strip() else " [manual]"
        print(f"[{p['state']:8}] {p['id']:16} {p['review_date']} (age {agestr}){tag}{alarm}")
        print(f"                   {p['title'][:88]}")
        if p.get("note"):
            print(f"                   note: {p['note'][:100]}")
    if aging:
        print(f"\n{aging} open proposal(s) past 2 review cycles. Decline is a valid one-word outcome.")


def main() -> int:
    ap = argparse.ArgumentParser(description="meta-memory-review proposal-state ledger")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list").add_argument("--all", action="store_true")
    a = sub.add_parser("add")
    a.add_argument("id"); a.add_argument("review_date"); a.add_argument("title")
    a.add_argument("--resolved-when", default="", dest="resolved_when",
                   help="shell predicate storing the done-condition; exit 0 == resolved")
    a.add_argument("--kind", default="", choices=("",) + KINDS,
                   help="outcome = measures the effect (auto-closes); impl = greps the code (never auto-closes)")
    a.add_argument("--approved-by", default="", dest="approved_by",
                   help="who approved this predicate and where (CONFIRM action); verify refuses it without one")
    s = sub.add_parser("set")
    s.add_argument("id"); s.add_argument("state"); s.add_argument("note", nargs="?", default="")
    sp = sub.add_parser("set-predicate")
    sp.add_argument("id"); sp.add_argument("predicate")
    sp.add_argument("--kind", default="", choices=("",) + KINDS)
    sp.add_argument("--approved-by", default="", dest="approved_by")
    v = sub.add_parser("verify")
    v.add_argument("--dry-run", action="store_true")
    r = sub.add_parser("rm")
    r.add_argument("id")
    args = ap.parse_args()

    if args.cmd == "add":
        add(args.id, args.review_date, args.title, args.resolved_when, args.kind, args.approved_by)
    elif args.cmd == "set":
        set_state(args.id, args.state, args.note)
    elif args.cmd == "set-predicate":
        set_predicate(args.id, args.predicate, args.kind, args.approved_by)
    elif args.cmd == "verify":
        return verify(dry_run=args.dry_run)
    elif args.cmd == "rm":
        rm(args.id)
    elif args.cmd == "list":
        list_(show_all=args.all)
    else:
        list_(show_all=False)  # default: open set
    return 0


if __name__ == "__main__":
    sys.exit(main())
