#!/usr/bin/env python3
# cockpit.py — read-only localhost dashboard for the whole system: one file, stdlib-only, GET-only.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Cockpit — read-only localhost command center.

Single stdlib file. 127.0.0.1:8787, GET-only, no deps, no writes, no controls. Manual start:

    python3 scripts/cockpit/cockpit.py            # serve
    python3 scripts/cockpit/cockpit.py --once     # print /api JSON and exit (smoke)
    python3 scripts/cockpit/cockpit.py --port N   # alternate port

Architecture: a PANELS registry of (key, title, column, collector) entries.
Each collector reads ONE source and returns a normalized dict; it is fail
isolated (any exception becomes {"error": ...} and that card shows
unavailable, never killing the page). Add a monitor = write one collector +
append one PANELS row. Zero changes to the server or other panels.

Safety: read-only everywhere, binds loopback only, do_POST/PUT -> 405, the
client renders via createElement/textContent (no raw HTML injection).
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
# The coding-agent CLI's per-project transcript dir. Override with CC_PROJECT_DIR.
CC_PROJ = Path(os.environ.get(
    "CC_PROJECT_DIR",
    str(HOME / ".claude/projects" / ("-" + str(REPO).replace("/", "-"))),
))
# The agent daemon's runtime sqlite (schedules + execution_log). Override via env.
DAEMON_DB = Path(os.environ.get("AGENT_DAEMON_DB", str(HOME / ".agent-daemon/data/agent.db")))
DAEMON_SERVICE = os.environ.get("AGENT_DAEMON_SERVICE", "agent-daemon")
VECTOR_STORE = Path(os.environ.get("AGENT_VECTOR_STORE", str(HOME / ".agent-daemon/data/vector_store")))
SESSION_LOG = REPO / "logs/session.jsonl"
ERROR_LOG = REPO / "logs/errors.jsonl"
SSOT_DB = REPO / "memory/state/ssot.sqlite"
GOALS = REPO / "memory/state/active_goals.json"
PIPELINE_MD = REPO / "memory/pipeline.md"
LOCAL_OFFSET = int(os.environ.get("LOCAL_UTC_OFFSET_HOURS", "0"))
LOCAL_TZ = timezone(timedelta(hours=LOCAL_OFFSET))
START = time.time()


def _now() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _ago(iso: str) -> str:
    try:
        secs = (datetime.now(LOCAL_TZ) - datetime.fromisoformat(iso)).total_seconds()
        if secs < 90:
            return "just now"
        if secs < 5400:
            return f"{int(secs // 60)}m ago"
        if secs < 129600:
            return f"{int(secs // 3600)}h ago"
        return f"{int(secs // 86400)}d ago"
    except Exception:
        return str(iso)[:16]


def _tail(path: Path, n: int) -> list[str]:
    if not path.exists():
        return []
    dq: collections.deque[str] = collections.deque(maxlen=n)
    with path.open(errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                dq.append(line)
    return list(dq)


def _tasks_dir() -> Path | None:
    dirs = sorted(glob.glob(str(HOME / ".claude/tasks/*/")), key=os.path.getmtime)
    return Path(dirs[-1]) if dirs else None


def _load_tasks() -> list[dict]:
    d = _tasks_dir()
    if not d:
        return []
    out = []
    for f in glob.glob(str(d / "*.json")):
        try:
            t = json.load(open(f))
            t["_mtime"] = os.path.getmtime(f)
            out.append(t)
        except Exception:
            pass
    return out


# ── collectors ──────────────────────────────────────────────────────

def c_heartbeat() -> dict:
    cells = []
    # daemon
    try:
        r = subprocess.run(["systemctl", "is-active", DAEMON_SERVICE],
                            capture_output=True, text=True, timeout=4)
        up = r.stdout.strip() == "active"
        cells.append({"label": "daemon",
                       "b": "up" if up else "DOWN", "cls": "ok" if up else "bad",
                       "span": f"{DAEMON_SERVICE}.service"})
    except Exception:
        cells.append({"label": "daemon", "b": "unknown", "cls": "warn", "span": ""})
    # last cron fire
    try:
        con = sqlite3.connect(f"file:{DAEMON_DB}?mode=ro", uri=True, timeout=4)
        row = con.execute("select schedule_name, started_at, status from "
                           "execution_log order by started_at desc limit 1").fetchone()
        con.close()
        if row:
            cells.append({"label": "last cron", "b": row[0][:22],
                          "cls": "ok" if (row[2] or "").startswith(("succ", "comp", "ok"))
                          else "warn", "span": (row[1] or "")[:19]})
        else:
            cells.append({"label": "last cron", "b": "none", "cls": "mut", "span": ""})
    except Exception:
        cells.append({"label": "last cron", "b": "db err", "cls": "warn", "span": ""})
    # watchdog (orphan-cleanup events in session.jsonl)
    wd = "no signal"
    for ln in reversed(_tail(SESSION_LOG, 400)):
        if "orphan" in ln:
            try:
                j = json.loads(ln)
                wd = (j.get("detail") or j.get("event") or "seen")[:26]
            except Exception:
                wd = "seen"
            break
    cells.append({"label": "watchdog", "b": "🟢 seen", "cls": "ok", "span": wd})
    # chat plugin (recent disconnect in errors)
    tg = "ok"
    tgc = "ok"
    for ln in reversed(_tail(ERROR_LOG, 120)):
        if "telegram" in ln.lower() and ("disconnect" in ln.lower() or "plugin" in ln.lower()):
            tg = "recent reconnect"
            tgc = "warn"
            break
    cells.append({"label": "chat plugin", "b": tg, "cls": tgc, "span": ""})
    # vector store
    cells.append({"label": "vector store",
                   "b": "🟢 indexed" if VECTOR_STORE.exists() else "missing",
                   "cls": "ok" if VECTOR_STORE.exists() else "bad",
                   "span": "semantic recall" if VECTOR_STORE.exists() else ""})
    return {"heartbeat": cells}


def _pct_from_blockers(task: dict, by_id: dict) -> int | None:
    bb = task.get("blockedBy") or []
    if not bb:
        return None
    done = sum(1 for tid in bb
               if (by_id.get(str(tid)) or {}).get("status") == "completed")
    return round(done / len(bb) * 100)


def c_blocked() -> dict:
    tasks = _load_tasks()
    by_id = {str(t.get("id")): t for t in tasks}
    marks = (("USER-ACTION", "p-action"), ("CONFIRM", "p-confirm"),
             ("DECISION", "p-confirm"), ("RELAY", "p-action"),
             ("REDLINE", "p-redline"))
    items = []
    for t in tasks:
        if t.get("status") not in ("pending", "in_progress"):
            continue
        blob = f"{t.get('subject','')} {t.get('description','')}".upper()
        tag = next((m for m, _ in marks if m in blob), None)
        if not tag:
            continue
        cls = dict(marks)[tag]
        items.append({"tag": tag, "tagcls": cls,
                      "text": f"#{t.get('id')} {t.get('subject','')}"[:90]})
    return {"badge": str(len(items)), "kind": "you",
            "items": items[:10] or [{"tag": "", "tagcls": "",
                                     "text": "nothing waiting on you"}]}


def c_tasks() -> dict:
    tasks = _load_tasks()
    by_id = {str(t.get("id")): t for t in tasks}
    n = collections.Counter(t.get("status") for t in tasks)

    def _id_key(t: dict) -> int:
        try:
            return int(t.get("id") or 0)
        except Exception:
            return 0

    active_sorted = sorted(
        (t for t in tasks if t.get("status") == "in_progress"),
        key=_id_key,
    )
    active_items = []
    for t in active_sorted:
        pct = _pct_from_blockers(t, by_id)
        active_items.append({
            "text": f"#{t.get('id')} {t.get('subject','')}"[:80],
            "bar": pct if pct is not None else 50,
            "barcls": "hot",
            "sub": (f"~{pct}% · {sum(1 for b in (t.get('blockedBy') or []) if (by_id.get(str(b)) or {}).get('status')=='completed')}/{len(t.get('blockedBy') or [])} dep tasks done"
                    if pct is not None else "in progress"),
        })

    pending_sorted = sorted(
        (t for t in tasks if t.get("status") == "pending"),
        key=_id_key,
    )
    pending_items = [
        {"text": f"#{t.get('id')} {t.get('subject','')}"[:80]}
        for t in pending_sorted
    ]

    completed_sorted = sorted(
        (t for t in tasks if t.get("status") == "completed"),
        key=_id_key,
    )
    completed_items = [
        {"text": f"#{t.get('id')} {t.get('subject','')}"[:80]}
        for t in completed_sorted
    ]

    groups = [
        {"label": f"active ({len(active_items)})",
         "items": active_items or [{"text": "no active tasks"}],
         "expanded": True},
        {"label": f"pending ({len(pending_items)})",
         "items": pending_items or [{"text": "no pending tasks"}],
         "expanded": False},
        {"label": f"completed ({len(completed_items)})",
         "items": completed_items or [{"text": "no completed tasks"}],
         "expanded": False},
    ]

    return {
        "badge": f"{n.get('in_progress',0)} active · {n.get('pending',0)} pend · {n.get('completed',0)} done",
        "groups": groups,
        "note": "bar = done-deps / total-deps (blockedBy graph) · click headers to expand",
    }


def c_goals() -> dict:
    try:
        g = json.load(open(GOALS)).get("goals") or []
    except Exception:
        g = []
    if not g:
        return {"badge": "/goal", "items": [{"text": "no active goals · /goal new"}]}
    items = []
    for x in g[:6]:
        pct = x.get("progress") or x.get("pct") or 0
        items.append({"text": x.get("title") or x.get("name") or "goal",
                       "bar": pct, "barcls": "pur",
                       "sub": f"{pct}% · {x.get('note','')}"[:80]})
    return {"badge": "/goal", "items": items}


def c_pipeline() -> dict:
    """Generic pipeline panel: extract the first bullets from a markdown notes file."""
    items = []
    try:
        txt = PIPELINE_MD.read_text(errors="replace")
        for ln in txt.splitlines():
            ls = ln.strip()
            if ls.startswith(("- ", "* ")) and len(ls) > 4:
                items.append({"text": ls[2:][:96]})
            if len(items) >= 8:
                break
        if not items:
            for ln in txt.splitlines():
                if ln.startswith("description:"):
                    items.append({"text": ln.split(":", 1)[1].strip()[:240]})
                    break
    except Exception as e:
        return {"badge": "pipeline", "error": str(e)[:80]}
    return {"badge": "pipeline", "items": items or [{"text": "no data (create memory/pipeline.md)"}]}


def c_scheduler() -> dict:
    try:
        con = sqlite3.connect(f"file:{DAEMON_DB}?mode=ro", uri=True, timeout=4)
        total = con.execute("select count(*) from schedules").fetchone()[0]
        en = con.execute("select count(*) from schedules where enabled=1").fetchone()[0]
        rows = con.execute("select schedule_name, started_at, status, error "
                           "from execution_log order by started_at desc limit 7").fetchall()
        # 12h fire-frequency spark: bucket fires into 12 one-hour bins
        now_utc = datetime.now(timezone.utc)
        cutoff = (now_utc - timedelta(hours=12)).isoformat()
        fire_rows = con.execute(
            "select started_at, status from execution_log "
            "where started_at >= ? order by started_at asc",
            (cutoff,)).fetchall()
        con.close()
    except Exception as e:
        return {"badge": "scheduler", "error": str(e)[:80]}

    # Build 12 hourly buckets; ignore parse failures silently
    buckets = [0] * 12
    err_buckets = [0] * 12
    for st, status in fire_rows:
        try:
            ts = datetime.fromisoformat(st.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            hours_ago = int((now_utc - ts).total_seconds() // 3600)
            if 0 <= hours_ago < 12:
                idx = 11 - hours_ago  # oldest left, newest right
                buckets[idx] += 1
                if not (status or "").startswith(("succ", "comp", "ok")):
                    err_buckets[idx] += 1
        except Exception:
            continue
    spark = _spark(buckets) if any(buckets) else ""
    total_fires = sum(buckets)
    total_errs = sum(err_buckets)

    items = []
    if spark:
        err_tag = f" · {total_errs} err" if total_errs else ""
        items.append({"text": "12h fire-freq",
                      "sub": f"{total_fires} fires{err_tag}",
                      "right": "1h buckets",
                      "spark": spark})
    for nm, st, status, err in rows:
        ok = (status or "").startswith(("succ", "comp", "ok"))
        items.append({"text": nm[:34], "right": (st or "")[11:19],
                       "tag": "ok" if ok else "err",
                       "tagcls": "ok" if ok else "bad"})
    return {"badge": f"{en}/{total} enabled", "items": items,
            "note": "recent fires (execution_log) · sparkline = fires/hr"}


_DU_CACHE: dict[str, tuple[float, int]] = {}
_DU_TTL = 300  # 5min — du is expensive, refresh inline at most every 5min


def _du_mb(path: str) -> int | None:
    """Cached `du -sm` for a path. Returns size in MB, or None on error."""
    now = time.time()
    hit = _DU_CACHE.get(path)
    if hit and now - hit[0] < _DU_TTL:
        return hit[1]
    try:
        out = subprocess.run(["du", "-sm", path],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            mb = int(out.stdout.split()[0])
            _DU_CACHE[path] = (now, mb)
            return mb
    except Exception:
        return None
    return None


def _df_gb(mount: str) -> tuple[int, int] | None:
    """Returns (used_gb, total_gb) for the mountpoint, or None."""
    try:
        out = subprocess.run(["df", "-BG", mount],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            lines = out.stdout.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    total = int(parts[1].rstrip("G"))
                    used = int(parts[2].rstrip("G"))
                    return (used, total)
    except Exception:
        return None
    return None


def _nvidia_smi() -> dict | None:
    """Query nvidia-smi if present. Returns vram+util dict, or None (no GPU / not installed)."""
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            line = out.stdout.strip().splitlines()[0]
            parts = [s.strip() for s in line.split(",")]
            if len(parts) >= 4:
                return {
                    "name": parts[0].replace("NVIDIA GeForce ", "").replace(" Laptop GPU", " L"),
                    "vram_used_mb": int(parts[1]),
                    "vram_total_mb": int(parts[2]),
                    "gpu_util_pct": int(parts[3]),
                }
    except Exception:
        return None
    return None


_CPU_PREV: dict = {}  # cached last /proc/stat snapshot for delta calc

# ── sparkline helpers ─────────────────────────────────────────────────────
# Pure unicode block sparklines, no HTML injection (rendered via textContent
# downstream, same as all other cockpit text). 8 levels of resolution.
_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"
_SAMPLES: dict[str, "deque"] = {}


def _push_sample(name: str, val: float, maxlen: int = 60):
    """Push a value into the named circular buffer. Returns the buffer."""
    from collections import deque
    buf = _SAMPLES.get(name)
    if buf is None or buf.maxlen != maxlen:
        buf = deque(maxlen=maxlen)
        _SAMPLES[name] = buf
    buf.append(val)
    return buf


def _spark(values, levels: int = 8) -> str:
    """Render a unicode sparkline from a sequence of numbers."""
    if not values:
        return ""
    vs = list(values)
    lo, hi = min(vs), max(vs)
    if hi == lo:
        return _SPARK_BLOCKS[3] * len(vs)
    rng = hi - lo
    return "".join(
        _SPARK_BLOCKS[min(levels - 1, int((v - lo) / rng * levels))]
        for v in vs
    )


def _cpu_pct() -> tuple[int, int] | None:
    """Returns (cpu_pct, n_cores) using /proc/stat delta vs last call.
    First call after process start returns (0, n_cores) (no baseline yet)."""
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        # parts[0]="cpu", then user,nice,system,idle,iowait,irq,softirq,steal,...
        vals = [int(x) for x in parts[1:9]]
        idle = vals[3] + vals[4]  # idle + iowait
        total = sum(vals)
        cores = os.cpu_count() or 1
        if not _CPU_PREV:
            _CPU_PREV.update({"idle": idle, "total": total})
            return (0, cores)
        d_idle = idle - _CPU_PREV["idle"]
        d_total = total - _CPU_PREV["total"]
        _CPU_PREV["idle"] = idle
        _CPU_PREV["total"] = total
        if d_total <= 0:
            return (0, cores)
        pct = round((d_total - d_idle) * 100 / d_total)
        return (max(0, min(100, pct)), cores)
    except Exception:
        return None


def c_system() -> dict:
    def _bcls(p: int) -> str:
        return "danger" if p >= 90 else ("warn" if p >= 75 else "ok")

    items = []

    # CPU usage (delta of /proc/stat between calls)
    cpu = _cpu_pct()
    if cpu is not None:
        pct, cores = cpu
        buf = _push_sample("cpu", pct, maxlen=30)
        items.append({"text": "CPU", "right": f"{cores} cores",
                      "sub": f"{pct}% load",
                      "bar": pct, "barcls": _bcls(pct),
                      "spark": _spark(buf)})

    # RAM
    try:
        mi = {}
        for ln in open("/proc/meminfo"):
            k, v = ln.split(":")
            mi[k] = int(v.strip().split()[0])
        tot = mi["MemTotal"] / 1048576
        avail = mi["MemAvailable"] / 1048576
        used = tot - avail
        pct = round(used / tot * 100)
        buf = _push_sample("ram", pct, maxlen=30)
        items.append({"text": "RAM", "right": f"{used:.1f} / {tot:.0f} GB",
                      "sub": f"{pct}% used",
                      "bar": pct, "barcls": _bcls(pct),
                      "spark": _spark(buf)})
    except Exception:
        pass

    # Root filesystem
    df_root = _df_gb("/")
    if df_root:
        u, t = df_root
        p = u * 100 // t
        items.append({"text": "disk (/)", "right": f"{u} / {t} GB",
                      "sub": f"{p}% used", "bar": p, "barcls": _bcls(p)})

    # GPU VRAM (if an NVIDIA GPU is present)
    gpu = _nvidia_smi()
    if gpu:
        vu = gpu["vram_used_mb"] / 1024
        vt = gpu["vram_total_mb"] / 1024
        vram_pct = round(gpu["vram_used_mb"] * 100 / max(gpu["vram_total_mb"], 1))
        buf = _push_sample("vram", vram_pct, maxlen=30)
        items.append({
            "text": "VRAM",
            "right": f"{vu:.1f} / {vt:.0f} GB",
            "sub": f"{gpu['name']} · {gpu['gpu_util_pct']}% gpu · {vram_pct}% vram",
            "bar": vram_pct, "barcls": _bcls(vram_pct),
            "spark": _spark(buf),
        })

    # workspace repo size (du -sm, cached 5min)
    repo_mb = _du_mb(str(REPO))
    if repo_mb is not None:
        size_s = f"{repo_mb/1024:.1f} GB" if repo_mb >= 1024 else f"{repo_mb} MB"
        items.append({"text": "workspace", "right": size_s, "sub": ""})

    # Top 5 processes by RSS — collapsible group
    proc_items = []
    try:
        ps = subprocess.run(["ps", "-eo", "rss,comm,args", "--sort=-rss"],
                            capture_output=True, text=True, timeout=5)
        for ln in ps.stdout.splitlines()[1:6]:
            p = ln.split(None, 2)
            if len(p) >= 2:
                rss = int(p[0]) // 1024
                proc_items.append({"text": p[1][:18], "right": f"{rss} MB",
                                   "sub": (p[2][:40] if len(p) > 2 else "")})
    except Exception:
        pass

    tsize = 0
    try:
        js = glob.glob(str(CC_PROJ / "*.jsonl"))
        if js:
            tsize = max(os.path.getsize(f) for f in js) // 1048576
    except Exception:
        pass
    out = {"badge": "host",
           "note": f"transcript ~{tsize} MB · cockpit up {int(time.time()-START)}s",
           "items": items}
    if proc_items:
        out["groups"] = [{"label": f"top procs ({len(proc_items)})",
                          "items": proc_items, "expanded": False}]
    return out


_NOISE = ("turn_boundary", "stake-classifier", "dir-watchdog")


def c_activity() -> dict:
    items = []
    for ln in reversed(_tail(SESSION_LOG, 250)):
        try:
            j = json.loads(ln)
        except Exception:
            continue
        cat = j.get("category") or j.get("type") or ""
        if cat in _NOISE:
            continue
        txt = (j.get("detail") or j.get("event") or j.get("summary") or cat)
        ts = (j.get("ts") or "")[11:19]
        items.append({"tag": cat[:12], "tagcls": "hot", "text": str(txt)[:80],
                       "right": ts})
        if len(items) >= 9:
            break
    return {"badge": "session.jsonl", "items": items or [{"text": "no events"}]}


def c_errors() -> dict:
    items = []
    for ln in reversed(_tail(ERROR_LOG, 60)):
        try:
            j = json.loads(ln)
            txt = j.get("error") or j.get("detail") or j.get("event") or ln
            ts = (j.get("ts") or "")[5:16]
        except Exception:
            txt, ts = ln, ""
        items.append({"tag": "✕", "tagcls": "bad", "text": str(txt)[:80],
                       "right": ts})
        if len(items) >= 5:
            break
    return {"badge": "errors.jsonl", "items": items or
            [{"tag": "·", "tagcls": "mut", "text": "no errors logged"}]}


_CCU_CACHE: dict = {"t": 0.0, "v": None, "busy": False}
_CCU_LOCK = threading.Lock()


def _ccusage_bin() -> str:
    for p in (HOME / ".bun/bin/ccusage", Path("/usr/local/bin/ccusage")):
        if p.exists():
            return str(p)
    return "ccusage"


def _fmt_tok(n) -> str:
    n = n or 0
    if n >= 1_000_000:
        return f"{n/1e6:.1f}M"
    if n >= 1_000:
        return f"{n/1e3:.0f}K"
    return str(int(n))


def _tok_io(inp, outp, cache) -> str:
    # split view: input vs output vs cache (cache usually dwarfs both on a subscription plan).
    return f"in {_fmt_tok(inp)} · out {_fmt_tok(outp)} · cache {_fmt_tok(cache)}"


def _model_fam(name: str) -> str:
    n = name or ""
    if "opus" in n:
        return "opus"
    if "sonnet" in n:
        return "sonnet"
    if "haiku" in n:
        return "haiku"
    return n.split("-")[1] if n.count("-") >= 1 else (n or "?")


def _per_model(rows: list[dict]) -> str:
    # sum modelBreakdowns cost by family across a window's day-rows
    acc: dict[str, float] = {}
    for r in rows:
        for mb in (r.get("modelBreakdowns") or []):
            acc[_model_fam(mb.get("modelName"))] = (
                acc.get(_model_fam(mb.get("modelName")), 0.0)
                + (mb.get("cost") or 0.0))
    if not acc:
        return "no model breakdown"
    order = ["opus", "sonnet", "haiku"]
    parts = [f"{k} ${acc[k]:,.0f}" for k in order if k in acc]
    parts += [f"{k} ${v:,.0f}" for k, v in acc.items() if k not in order]
    return " · ".join(parts)


def _ccusage_compute() -> dict:
    # the heavy bit: two ccusage subprocesses (slow, 5-30s) + parse.
    # Runs ONLY in a background thread, never the request path.
    cc = _ccusage_bin()
    try:
        rb = subprocess.run([cc, "blocks", "--active", "--json"],
                            capture_output=True, text=True, timeout=20)
        blocks = (json.loads(rb.stdout) or {}).get("blocks") or []
        rd = subprocess.run([cc, "daily", "--json", "--breakdown"],
                            capture_output=True, text=True, timeout=30)
        days = (json.loads(rd.stdout) or {}).get("daily") or []
        days = sorted(days, key=lambda x: x.get("date") or "")

        items, big, bar, barcls, note_bits = [], "no data", None, "ok", []

        if blocks:
            b = blocks[0]
            cost = b.get("costUSD") or 0.0
            pj = b.get("projection") or {}
            br = b.get("burnRate") or {}
            pcost = pj.get("totalCost") or 0.0
            rem = pj.get("remainingMinutes")
            barpct = round(cost / pcost * 100) if pcost else 0
            big = f"${cost:.2f} now / 5h block"
            bar = min(barpct, 100)
            barcls = "bad" if barpct >= 90 else ("warn" if barpct >= 70 else "ok")
            mdl = ", ".join(_model_fam(m) for m in (b.get("models") or [])) or "?"
            tcb = b.get("tokenCounts") or {}
            io = _tok_io(tcb.get("inputTokens"), tcb.get("outputTokens"),
                         (tcb.get("cacheCreationInputTokens") or 0)
                         + (tcb.get("cacheReadInputTokens") or 0))
            items.append({"text": "5h block (live)", "right": f"${cost:.2f}",
                          "sub": f"{_fmt_tok(b.get('totalTokens'))} tok · {io} · "
                                 f"burn ${br.get('costPerHour',0):.0f}/hr · "
                                 f"proj ${pcost:.0f} · {mdl}"})
            note_bits.append(f"block {(b.get('startTime') or '')[11:16]}–"
                             f"{(b.get('endTime') or '')[11:16]}UTC ~{rem}min left")

        def win(label, rs):
            tot = sum(r.get("totalCost") or 0.0 for r in rs)
            tok = sum(r.get("totalTokens") or 0 for r in rs)
            inp = sum(r.get("inputTokens") or 0 for r in rs)
            outp = sum(r.get("outputTokens") or 0 for r in rs)
            cache = sum((r.get("cacheCreationTokens") or 0)
                        + (r.get("cacheReadTokens") or 0) for r in rs)
            items.append({"text": label, "right": f"${tot:,.0f}",
                          "sub": f"{_fmt_tok(tok)} tok · {_tok_io(inp, outp, cache)}"
                                 f" · {_per_model(rs)}"})

        if days:
            # 14-day daily cost sparkline (range-frame, no axes, direct value)
            last14 = days[-14:] if len(days) >= 14 else days
            costs = [r.get("totalCost") or 0.0 for r in last14]
            if costs and any(c > 0 for c in costs):
                spark = _spark(costs)
                lo, hi = min(costs), max(costs)
                items.append({"text": f"{len(last14)}d cost trend",
                              "sub": f"${lo:.0f}–${hi:.0f}/day range",
                              "right": "→ today",
                              "spark": spark})
            win("today", days[-1:])
            win("last 7 days", days[-7:])
            win("last 30 days", days[-30:])
            win(f"from inception ({len(days)}d tracked)", days)
        else:
            items.append({"text": "daily breakdown unavailable"})

        return {"badge": "ccusage · API-rate equiv",
                "big": big, "bar": bar, "barcls": barcls, "items": items,
                "note": (" · ".join(note_bits) + " · " if note_bits else "")
                + "$ = notional API price (a flat subscription may make real spend $0) · cache≤45s"}
    except Exception as e:
        return {"badge": "ccusage", "error": str(e)[:90]}


def _ccusage_refresh() -> None:
    v = _ccusage_compute()
    with _CCU_LOCK:
        _CCU_CACHE.update(t=time.time(), v=v, busy=False)


def c_ccusage() -> dict:
    # NON-BLOCKING. The ccusage subprocesses are slow; running them in the
    # /api request path would hang the page and, with the 5s auto-refresh + cold
    # cache, spawn a thundering herd of ccusage procs. So: serve cached/placeholder
    # INSTANTLY, refresh in a single daemon thread when stale. First paint shows
    # "warming", a later 5s tick fills it from cache. Lock guards the in-flight flag
    # so only one refresh runs no matter how many concurrent /api requests hit.
    now = time.time()
    with _CCU_LOCK:
        if _CCU_CACHE["v"] is not None and now - _CCU_CACHE["t"] < 45:
            return _CCU_CACHE["v"]
        start = not _CCU_CACHE["busy"]
        if start:
            _CCU_CACHE["busy"] = True
        stale = _CCU_CACHE["v"]
    if start:
        threading.Thread(target=_ccusage_refresh, daemon=True).start()
    if stale is not None:
        return stale
    return {"badge": "ccusage · warming",
            "items": [{"text": "sampling ccusage… first result in ≤30s, "
                       "auto-fills (page is not blocked)"}]}


def c_ssot() -> dict:
    """SSOT operational-state store: canonical keys by namespace + most-recent changes.
    Read-only, excludes the internal migration.* bookkeeping keys."""
    if not SSOT_DB.exists():
        return {"badge": "SSOT", "items": [{"text": "ssot.sqlite not found"}]}
    try:
        con = sqlite3.connect(f"file:{SSOT_DB}?mode=ro", uri=True, timeout=2)
        keys = [r[0] for r in con.execute("SELECT key FROM state")]
        recent = con.execute("SELECT key, by, ts FROM state_log "
                             "WHERE key NOT LIKE 'migration.%' "
                             "ORDER BY id DESC LIMIT 4").fetchall()
        con.close()
    except Exception as e:
        return {"badge": "SSOT", "error": str(e)[:90]}
    canon = [k for k in keys if not k.startswith("migration.")]
    ns = collections.Counter(k.split(".")[0] for k in canon)
    items = [{"text": name, "sub": f"{cnt} key{'s' if cnt != 1 else ''}"}
             for name, cnt in sorted(ns.items(), key=lambda x: (-x[1], x[0]))]
    for key, by, ts in recent:
        items.append({"text": f"↻ {key}", "sub": f"by {by} · {_ago(ts)}"})
    return {"badge": f"SSOT · {len(canon)} keys", "items": items}


# key, title, column (0/1/2), collector
PANELS = [
    ("blocked", "⚠ Blocked on YOU", 0, c_blocked),
    ("ccusage", "Token usage · 5h block", 0, c_ccusage),
    ("system", "System", 0, c_system),
    ("tasks", "Tasks", 1, c_tasks),
    ("pipeline", "Pipeline", 1, c_pipeline),
    ("errors", "Errors", 1, c_errors),
    ("goals", "Goals", 2, c_goals),
    ("scheduler", "Scheduler", 2, c_scheduler),
    ("ssot", "SSOT · state", 2, c_ssot),
    ("activity", "Activity / Delegation", 2, c_activity),
]


def build_api() -> dict:
    out = {"generated": _now(), "panels": {}}
    try:
        out["heartbeat"] = c_heartbeat().get("heartbeat", [])
    except Exception as e:
        out["heartbeat"] = [{"label": "heartbeat", "b": "error",
                             "cls": "bad", "span": str(e)[:40]}]
    for key, title, col, fn in PANELS:
        try:
            d = fn()
        except Exception as e:
            d = {"error": str(e)[:120]}
        d["title"] = title
        d["col"] = col
        out["panels"][key] = d
    return out


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Cockpit</title><style>
:root{--bg:#0d1117;--card:#161b22;--bd:#30363d;--fg:#c9d1d9;--mut:#8b949e;
--ok:#3fb950;--warn:#d29922;--bad:#f85149;--hot:#58a6ff;--pur:#bc8cff}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--fg);
font:13px/1.5 ui-monospace,Menlo,monospace}
.wrap{max-width:1500px;margin:0 auto;padding:0 14px 18px}
header{display:flex;justify-content:space-between;align-items:center;padding:12px 2px}
h1{font-size:14px;margin:0;letter-spacing:.5px}
.dot{height:8px;width:8px;border-radius:50%;background:var(--ok);
display:inline-block;margin-right:6px}
.beat{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--bd);
border-radius:8px;background:#10151c;font-size:11px;overflow:hidden;margin-bottom:12px}
.beat>div{padding:8px 12px;border-right:1px solid var(--bd);display:flex;
flex-direction:column;gap:1px}.beat>div:last-child{border-right:0}
.beat b{font-size:12px}.beat span{color:var(--mut)}
.cols{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;align-items:start}
.col{display:flex;flex-direction:column;gap:12px;min-width:0}
.card{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:12px}
.card h2{font-size:12px;margin:0 0 9px;color:var(--mut);text-transform:uppercase;
letter-spacing:1px;display:flex;justify-content:space-between;gap:8px}
.row{padding:5px 0;border-bottom:1px solid #21262d;display:flex;gap:8px;
align-items:flex-start}.row:last-child{border:0}
.tag{font-size:10px;padding:1px 6px;border-radius:10px;background:#21262d;
color:var(--mut);white-space:nowrap}
.sub{flex:1;min-width:0}.ok{color:var(--ok)}.warn{color:var(--warn)}
.bad{color:var(--bad)}.hot{color:var(--hot)}.mut{color:var(--mut)}.pur{color:var(--pur)}
.bar{height:6px;background:#21262d;border-radius:3px;overflow:hidden;
margin:5px 0 2px;width:100%}.bar>i{display:block;height:100%}
.big{font-size:21px;font-weight:600}.err{color:var(--mut);font-size:11px;margin-top:7px}
small{color:var(--mut)}.when{color:var(--mut);white-space:nowrap;font-size:11px}
.you{border-color:#7d4b00;background:#1a1206}.you h2{color:var(--warn)}
.pill{font-size:10px;padding:1px 7px;border-radius:10px;font-weight:600;white-space:nowrap}
.p-confirm{background:#7d2b2b;color:#ffd7d7}.p-action{background:#6b4e00;color:#ffe9b0}
.p-redline{background:#1f4f6b;color:#bfe6ff}
.ghdr{margin:8px 0 4px;padding:4px 6px;background:#0e131a;border-radius:4px;
color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.8px;
user-select:none}.ghdr:hover{background:#161c25;color:#e6edf3}
.gcaret{display:inline-block;width:10px}.gbody{padding-left:2px}
/* Responsive: the grid collapses on narrow viewports so the page never scrolls sideways. */
@media(max-width:1100px){.cols{grid-template-columns:1fr 1fr}}
@media(max-width:760px){.cols{grid-template-columns:1fr}
.beat{grid-template-columns:repeat(2,1fr)}}
.spk{display:block;font-family:'Cascadia Mono','Consolas','Courier New',monospace;
letter-spacing:-1.5px;font-size:11px;color:var(--hot);line-height:1;margin-top:3px;
white-space:nowrap;overflow:hidden;text-overflow:clip;max-width:100%}
</style></head><body><div class="wrap">
<header><h1><span class="dot"></span>COCKPIT
<small>&nbsp;read-only · auto-refresh 5s</small></h1>
<small id="ts">loading…</small></header>
<div class="beat" id="beat"></div>
<div class="cols"><div class="col" id="c0"></div>
<div class="col" id="c1"></div><div class="col" id="c2"></div></div>
</div><script>
function E(t,c,x){var e=document.createElement(t);if(c)e.className=c;
if(x!=null)e.textContent=x;return e;}
function bar(p,cls){var b=E("div","bar"),i=E("i");
i.style.width=Math.max(0,Math.min(100,p))+"%";
i.style.background="var(--"+(cls||"hot")+")";b.appendChild(i);return b;}
var GROUP_STATE=(function(){try{return JSON.parse(localStorage.getItem("cockpit.groupState")||"{}");}catch(e){return {};}})();
function saveGroupState(){try{localStorage.setItem("cockpit.groupState",JSON.stringify(GROUP_STATE));}catch(e){}}
function renderItem(it){var r=E("div","row");
if(it.tag)r.appendChild(E("span",it.tagcls?("tag "+it.tagcls):"tag",it.tag));
if(it.pillcls)r.appendChild(E("span","pill "+it.pillcls,it.tag));
var s=E("div","sub");s.appendChild(E("div",null,it.text||""));
if(it.bar!=null)s.appendChild(bar(it.bar,it.barcls));
if(it.sub)s.appendChild(E("small",null,it.sub));
if(it.spark)s.appendChild(E("span","spk",it.spark));
r.appendChild(s);
if(it.right)r.appendChild(E("span","when",it.right));
return r;}
function card(p){var c=E("div","card"+(p.kind==="you"?" you":""));
var h=E("h2");h.appendChild(E("span",null,p.title));
h.appendChild(E("span",null,p.badge||""));c.appendChild(h);
if(p.error){c.appendChild(E("div","err","·· unavailable: "+p.error));return c;}
if(p.big){var bg=E("div","big",p.big);c.appendChild(bg);
if(p.bar!=null)c.appendChild(bar(p.bar,p.barcls));}
(p.items||[]).forEach(function(it){c.appendChild(renderItem(it));});
(p.groups||[]).forEach(function(g,gi){
var stateKey=(p.key||p.title)+"/"+gi;
var expanded=GROUP_STATE.hasOwnProperty(stateKey)?GROUP_STATE[stateKey]:!!g.expanded;
var gh=E("div","ghdr");
gh.appendChild(E("span","gcaret",expanded?"▾":"▸"));
gh.appendChild(E("span",null," "+g.label));
var body=E("div","gbody");
(g.items||[]).forEach(function(it){body.appendChild(renderItem(it));});
if(!expanded)body.style.display="none";
gh.style.cursor="pointer";
gh.addEventListener("click",function(){
var hidden=body.style.display==="none";
body.style.display=hidden?"":"none";
gh.firstChild.textContent=hidden?"▾":"▸";
GROUP_STATE[stateKey]=hidden;saveGroupState();});
c.appendChild(gh);c.appendChild(body);});
if(p.note)c.appendChild(E("div","err",p.note));
return c;}
function beatCell(x){var d=E("div");d.appendChild(E("span",null,x.label));
d.appendChild(E("b",x.cls,x.b));d.appendChild(E("span",null,x.span||""));return d;}
function tick(){fetch("/api").then(function(r){return r.json();}).then(function(d){
document.getElementById("ts").textContent=d.generated;
var bt=document.getElementById("beat");bt.replaceChildren();
(d.heartbeat||[]).forEach(function(x){bt.appendChild(beatCell(x));});
var col=[[],[],[]];
Object.keys(d.panels).forEach(function(k){var p=d.panels[k];
p.key=k;col[p.col||0].push(p);});
[0,1,2].forEach(function(i){var el=document.getElementById("c"+i);
el.replaceChildren();col[i].forEach(function(p){el.appendChild(card(p));});});
}).catch(function(e){document.getElementById("ts").textContent="api error";});}
tick();setInterval(tick,5000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api"):
            b = json.dumps(build_api()).encode()
            self._send(200, b, "application/json")
        elif self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def _deny(self):
        self._send(405, b"read-only cockpit: GET only", "text/plain")

    do_POST = do_PUT = do_DELETE = do_PATCH = _deny


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--once", action="store_true",
                    help="print /api JSON once and exit (smoke test)")
    a = ap.parse_args()
    if a.once:
        print(json.dumps(build_api(), indent=2))
        return
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"cockpit → http://127.0.0.1:{a.port}  (read-only, Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
