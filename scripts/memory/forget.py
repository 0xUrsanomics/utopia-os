#!/usr/bin/env python3
# forget.py: find every copy of a fact before forgetting it, then prove it cannot be recovered.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Find every copy of a fact before forgetting it, and check afterwards that it cannot be recovered.

Why: in agent memory, what fails is missing the related records, not the delete itself
(MemCut, arXiv 2610.21405). A fact lives in tier-1 memory, the vector index, its backups, derived
maps, transcripts, logs, SQLite stores and git history. Deleting the one copy you know about leaves
the rest answerable by recall.

READ-ONLY. This script never edits, moves or deletes anything. The runbook is:
  1. `plan`   lists every location that holds the fact.
  2. The operator approves the removal list.
  3. The edits are made by hand (or by a reviewed script), backups included.
  4. `verify` re-runs the scan plus a semantic recall test, exit 1 if anything is still recoverable.

  forget.py plan   --strings "4,200" "Acme" [--questions "what fee did Acme refuse?"] [--json OUT]
  forget.py verify --strings ... --questions ...     same scan + recall recovery test, exit 1 if recoverable
  forget.py selftest                                 control pair: plant a fake fact, find it, remove, miss it

Strings match case-insensitively as plain substrings. Pass paraphrases and numbers too.
Questions go through scripts/memory/vector_brain.py search (semantic), which catches wording the
strings miss.

Env (all optional):
  AGENT_ROOT        repo root (default: two levels up from this file)
  AGENT_DATA_DIR    runtime data dir holding vector_brain/ and *.db stores (default: $AGENT_ROOT/.data)
  AGENT_LOG_DIR     logs dir (default: $AGENT_ROOT/logs)
  AGENT_GRAPH_DIR   knowledge-graph pages dir (default: $AGENT_ROOT/knowledge-graph)
  AGENT_VENV_PY     interpreter that carries the embedding deps for the recall test
  FORGET_EXTRA_DIRS extra stores to scan, "label=/path" entries separated by os.pathsep
  FORGET_SQLITE     comma-separated *.db names under AGENT_DATA_DIR to scan
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA = Path(os.environ.get("AGENT_DATA_DIR", str(REPO / ".data")))
LOGS = Path(os.environ.get("AGENT_LOG_DIR", str(REPO / "logs")))
GRAPH = Path(os.environ.get("AGENT_GRAPH_DIR", str(REPO / "knowledge-graph")))
VENV_PY = Path(os.environ.get("AGENT_VENV_PY", sys.executable))

# (store label, path, binary?) binary=True greps inside binary files too (LanceDB data files)
TREES = [
    ("tier1-memory", REPO / "memory", False),
    ("knowledge", REPO / "knowledge", False),
    ("skills", REPO / "skills", False),
    ("outputs", REPO / "outputs", False),
    ("archive-backups", REPO / "sandbox/archive", False),
    ("logs", LOGS, False),
    ("transcripts", HOME / ".claude/projects", False),
    ("knowledge-graph", GRAPH, False),
    ("vector-brain-live", DATA / "vector_brain", True),
    ("vector-brain-backups", DATA, True),  # filtered to the backup dirs below
    ("derived-maps", DATA, False),          # filtered to the json maps below
]
for _entry in filter(None, os.environ.get("FORGET_EXTRA_DIRS", "").split(os.pathsep)):
    _label, _, _path = _entry.partition("=")
    if _path:
        TREES.append((_label.strip() or "extra", Path(_path).expanduser(), False))

BACKUP_DIRS = ("vector_brain.bak", "backup-pre-reindex", "pre-consolidation-backup")
DERIVED = ("backlink_map.json", "tag_cocite_map.json")
SQLITE = [s.strip() for s in os.environ.get(
    "FORGET_SQLITE", "memory.db,telegram.db,session_search.db,vector_brain_fts.db,fleet_bus.db,addr.db").split(",")
    if s.strip()]
SELF = {str(Path(__file__).resolve())}


def grep_tree(root, strings, binary, only=None):
    if not root.exists():
        return None
    targets = [root]
    if only == "backups":
        targets = [p for p in root.iterdir() if p.name.startswith(BACKUP_DIRS)]
    elif only == "derived":
        targets = [root / n for n in DERIVED if (root / n).exists()]
    if not targets:
        return []
    cmd = ["grep", "-rlFi", "-a" if binary else "-I"]
    for s in strings:
        cmd += ["-e", s]
    out = subprocess.run(cmd + [str(t) for t in targets], capture_output=True, text=True, timeout=1800)
    return [ln for ln in out.stdout.splitlines() if ln and ln not in SELF]


def grep_sqlite(db, strings):
    path = DATA / db
    if not path.exists():
        return None
    hits = []
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for (table,) in con.execute("select name from sqlite_master where type='table'"):
            if table.endswith(("_data", "_idx", "_docsize", "_config")):
                continue
            cols = [r[1] for r in con.execute(f'pragma table_info("{table}")') if (r[2] or "").upper() in ("TEXT", "")]
            for col in cols:
                for s in strings:
                    try:
                        n = con.execute(f'select count(*) from "{table}" where "{col}" like ?', (f"%{s}%",)).fetchone()[0]
                    except sqlite3.Error:
                        continue
                    if n:
                        hits.append(f"{db}:{table}.{col} ({n} rows match '{s}')")
    finally:
        con.close()
    return hits


def git_history(strings):
    hits = []
    if not (REPO / ".git").exists():
        return None
    for s in strings:
        out = subprocess.run(["git", "-C", str(REPO), "log", "--all", "--oneline", "-i", "-S", s],
                             capture_output=True, text=True, timeout=600)
        n = len([ln for ln in out.stdout.splitlines() if ln])
        if n:
            hits.append(f"{n} commits add or remove '{s}' (pushed history lives on any remote too)")
    return hits


def scan(strings):
    report = {}
    for label, root, binary in TREES:
        only = "backups" if label == "vector-brain-backups" else "derived" if label == "derived-maps" else None
        report[label] = grep_tree(root, strings, binary, only)
    for db in SQLITE:
        report[f"sqlite:{db}"] = grep_sqlite(db, strings)
    report["git-history"] = git_history(strings)
    return report


def recall(questions, strings):
    """Ask vector_brain each question; recoverable if a top hit still contains one of the strings."""
    code = (
        "import json,sys\n"
        f"sys.path.insert(0,{str(Path(__file__).resolve().parent)!r})\n"
        "import io,contextlib, vector_brain as vb\n"
        "qs=json.loads(sys.argv[1]); out=[]\n"
        "for q in qs:\n"
        "    with contextlib.redirect_stdout(io.StringIO()):\n"
        "        r=vb.search(q, top_k=5, rerank_enable=True)\n"
        "    out.append({'q':q,'hits':[{'source':x.get('source'),'text':(x.get('text') or '')[:2000]} for x in r]})\n"
        "print('@@'+json.dumps(out))\n"
    )
    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    r = subprocess.run([py, "-c", code, json.dumps(questions)], capture_output=True, text=True, timeout=900)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("@@")), None)
    if not line:
        return None, f"recall failed: {(r.stderr or '')[-300:]}"
    rows = []
    for item in json.loads(line[2:]):
        leaked = [h["source"] for h in item["hits"] if any(s.lower() in h["text"].lower() for s in strings)]
        rows.append({"question": item["q"], "recoverable": bool(leaked), "leaking_sources": leaked,
                     "top_source": item["hits"][0]["source"] if item["hits"] else None})
    return rows, None


def show(report, rows=None, err=None):
    total = 0
    print("store                     hits  sample")
    for label, hits in report.items():
        if hits is None:
            print(f"{label:25} n/a   (not present)")
            continue
        total += len(hits)
        sample = hits[0][:110] if hits else ""
        print(f"{label:25} {len(hits):4}  {sample}")
    print(f"\n{total} locations hold at least one string. Read-only scan, nothing changed.")
    if err:
        print(f"RECALL CHECK NOT RUN: {err}")
    for r in rows or []:
        flag = "RECOVERABLE" if r["recoverable"] else "not recovered (read top source to be sure)"
        print(f"  Q: {r['question']}\n     {flag}; top source: {r['top_source']}")
        for s in r["leaking_sources"]:
            print(f"     leaks via {s}")
    print("Not scannable here (remove by hand, operator only): chat-app history, cloud-drive version "
          "history, remote git history after a force-push, shared sheets/docs/mail, anything already sent.")
    return total


def selftest():
    """Control pair: the scan must go red on a planted fact, then green once it is removed."""
    fact = "zz-forget-selftest-7f3a9c"
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "note.md").write_text(f"planted fact: {fact}\n")
        found = grep_tree(tmp, [fact.upper()], False)
        (tmp / "note.md").write_text("clean\n")
        gone = grep_tree(tmp, [fact], False)
        ok = found == [str(tmp / "note.md")] and gone == []
        print(f"selftest {'PASS' if ok else 'FAIL'}: planted found={bool(found)} (case-insensitive), after removal found={bool(gone)}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=["plan", "verify", "selftest"])
    ap.add_argument("--strings", nargs="+", default=[])
    ap.add_argument("--questions", nargs="+", default=[])
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.mode == "selftest":
        return selftest()
    strings = [s for s in a.strings if len(s.strip()) >= 3]
    if not strings:
        ap.error("--strings needs at least one string of 3+ characters")
    report = scan(strings)
    rows = err = None
    if a.questions:
        rows, err = recall(a.questions, strings)
    total = show(report, rows, err)
    if a.json:
        Path(a.json).write_text(json.dumps({"strings": strings, "report": report, "recall": rows}, indent=1))
    if a.mode == "verify":
        if err:
            return 2
        return 1 if total or any(r["recoverable"] for r in rows or []) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
