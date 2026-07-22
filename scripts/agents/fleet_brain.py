#!/usr/bin/env python3
# fleet_brain.py — the fleet shared-brain blackboard: per-agent inboxes drained into one shared brain.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""fleet_brain — the fleet shared-brain blackboard.

Agents drop FINDINGS into a per-agent inbox; a drain step moves them to a permanent corpus
dir and indexes them incrementally into the SAME vector_brain every other agent already
recalls from. So one tenant's finding becomes recallable by every other agent once indexed.
This is what makes the fleet COMPOUND instead of running as N blind silos.

Design (integrates with vector_brain.py rather than bolting on):
  inbox/<agent>/<ts>-<slug>.md   write-staging (agent writes here, cheap, no model load)
  corpus/<agent>/<ts>-<slug>.md  permanent store (globbed by the fleet source -> survives
                                 the nightly FULL reindex; never lost)
  drain (index):  move inbox -> corpus, then `vector_brain.py index-append --paths ...`
                  (incremental add + BM25 insert; NO full rebuild).
  recall:         unchanged — every agent's recall already hits the same brain; a
                  fleet-source boost surfaces fresh cross-agent findings.

Single-writer discipline: agents only ever WRITE their own inbox/<self>/ ; the single
drain/indexer is the only writer to the vector store. Avoids the multi-writer corruption class.

CLI (all emit JSON or plain status):
  fleet_brain.py write --agent research --title "..." [--slug x] [--tags a,b] [--content "..."|<stdin>]
  fleet_brain.py index            # drain ALL inboxes -> corpus -> incremental index
  fleet_brain.py list             # pending inbox counts + corpus counts per agent

Config via env: AGENT_ROOT (repo root), AGENT_DATA_DIR (where the brain lives, default <root>/.data),
AGENT_VENV_PY (interpreter that carries the embedding deps; default: this interpreter).
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys
from datetime import datetime
from pathlib import Path

# AGENT_ROOT defaults to the repo root (this file is scripts/agents/fleet_brain.py).
ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
BASE = DATA_DIR / "fleet-brain"
INBOX = BASE / "inbox"
CORPUS = BASE / "corpus"
# Mirrors the fleet_bus roster v1. Rename/extend to match your own tenants.
AGENTS = {"hub", "runner", "research", "marketing", "coach", "assistant"}
VECTOR_BRAIN = ROOT / "scripts" / "memory" / "vector_brain.py"
# The embedding model needs an interpreter with its deps installed. Point AGENT_VENV_PY at that
# venv's python; otherwise fall back to whatever interpreter is running this (fine if deps are global).
VENV_PY = Path(os.environ.get("AGENT_VENV_PY", sys.executable))
LOG = ROOT / "logs" / "session.jsonl"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ts_slug() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return (s[:50] or "finding")


def _log(event: str, **kw) -> None:
    rec = {"ts": _now_iso(), "level": "info", "agent": "fleet-brain", "category": "fleet-brain", "event": event}
    rec.update(kw)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def write(agent: str, title: str, content: str, slug: str | None = None, tags: str | None = None) -> dict:
    if agent not in AGENTS:
        return {"error": f"unknown agent '{agent}' (roster: {sorted(AGENTS)})"}
    slug = _slugify(slug or title)
    d = INBOX / agent
    d.mkdir(parents=True, exist_ok=True)
    fname = f"{_ts_slug()}-{slug}.md"
    fpath = d / fname
    taglist = [t.strip() for t in (tags or "").split(",") if t.strip()]
    fm = (
        "---\n"
        f"title: {title}\n"
        f"agent: {agent}\n"
        "type: fleet-finding\n"
        f"source: fleet/{agent}\n"
        f"tags: {taglist}\n"
        f"created: {_now_iso()}\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{content.strip()}\n\n"
        f"_(fleet finding from {agent}, {_now_iso()})_\n"
    )
    fpath.write_text(fm)
    _log("finding-written", agent=agent, path=str(fpath))
    return {"ok": True, "path": str(fpath), "agent": agent, "title": title}


def index() -> dict:
    """Drain every inbox -> move to corpus -> incrementally index. No-op (fast) if empty."""
    pending: list[Path] = []
    for agent_dir in sorted(INBOX.glob("*")):
        if not agent_dir.is_dir():
            continue
        pending.extend(sorted(agent_dir.glob("*.md")))
    if not pending:
        return {"ok": True, "indexed": 0, "note": "inbox empty, no model load"}

    moved: list[str] = []
    for src in pending:
        agent = src.parent.name
        dst_dir = CORPUS / agent
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        try:
            shutil.move(str(src), str(dst))  # move FIRST so a re-run never double-indexes
            moved.append(str(dst))
        except Exception as e:
            _log("drain-move-failed", path=str(src), err=str(e))

    if not moved:
        return {"ok": False, "indexed": 0, "error": "all moves failed"}

    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    cmd = [py, str(VECTOR_BRAIN), "index-append", "--paths", *moved]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        ok = r.returncode == 0
        tail = (r.stdout or "").strip().splitlines()[-1:] or [(r.stderr or "").strip()[:200]]
        _log("drain-indexed", files=len(moved), rc=r.returncode, detail=tail[0] if tail else "")
        return {"ok": ok, "indexed": len(moved), "rc": r.returncode, "detail": tail[0] if tail else "",
                "note": "files already in corpus; a nightly full reindex will re-find them even if append failed"}
    except subprocess.TimeoutExpired:
        _log("drain-index-timeout", files=len(moved))
        return {"ok": False, "indexed": 0, "error": "index-append timed out (files safe in corpus)"}


def listing() -> dict:
    out = {"inbox": {}, "corpus": {}}
    for a in sorted(AGENTS):
        out["inbox"][a] = len(list((INBOX / a).glob("*.md"))) if (INBOX / a).is_dir() else 0
        out["corpus"][a] = len(list((CORPUS / a).glob("*.md"))) if (CORPUS / a).is_dir() else 0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="agent drops a finding into its inbox")
    w.add_argument("--agent", required=True)
    w.add_argument("--title", required=True)
    w.add_argument("--slug")
    w.add_argument("--tags", help="comma-separated")
    w.add_argument("--content", help="finding body; if omitted, read from stdin")
    sub.add_parser("index", help="drain inboxes -> corpus -> incremental index")
    sub.add_parser("list", help="show pending inbox + corpus counts")
    a = ap.parse_args()

    if a.cmd == "write":
        content = a.content if a.content is not None else sys.stdin.read()
        print(json.dumps(write(a.agent, a.title, content, a.slug, a.tags)))
    elif a.cmd == "index":
        print(json.dumps(index()))
    elif a.cmd == "list":
        print(json.dumps(listing(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
