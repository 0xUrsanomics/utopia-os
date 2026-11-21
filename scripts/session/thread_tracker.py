#!/usr/bin/env python3
# thread_tracker.py: the store and CLI behind the open-threads tracker (memory/state/threads.json).
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Thread tracker: one entry per open workstream the operator and the agent are talking about.

Operators switch topics often in a chat channel. This store records which workstreams are open,
where each one stands and what comes next, so a bare "ok" or "yes" can be routed to the thread
the agent last asked about. The classifier (thread_classifier.py) and the UserPromptSubmit hook
(thread_classify_hook.py) read this store; the cockpit "Open threads" panel reads it too.

    thread_tracker.py list [--status S] [--area A] [--all] [--json]
    thread_tracker.py touch <id> [--where ..] [--next ..] [--status ..] [--msg N] [--keywords a,b] [--asked]
    thread_tracker.py new --title .. --area .. [--status ..] [--where ..] [--next ..] [--keywords a,b] [--msg N]
    thread_tracker.py done <id>
    thread_tracker.py selftest

Store shape (see memory/state/threads.example.json):
    {"version": 1,
     "state": {"last_asked_thread": id|null, "last_asked_at": iso|null, "current_thread": id|null,
               "updated": iso},
     "threads": [{id, title, area, status, where, next, last_touched, last_msg_id,
                  msg_ids, keywords, created}]}

`msg_ids` holds recent chat message ids (newest last, capped), so a quote-reply to any recent
message in a thread can be matched, not only the very last one.

Write safety: every write takes an exclusive flock on a sibling .lock file, re-reads the store
inside the lock, applies the change, writes a temp file in the same directory, fsyncs it and
os.replace()s it over the store. A corrupt store is never overwritten: load() raises CorruptStore
and every write path refuses (exit 2). Stdlib only. POSIX only (fcntl).

Env:
  AGENT_ROOT              repo root (default: two levels up)
  AGENT_THREADS_FILE      store path (default: $AGENT_ROOT/memory/state/threads.json)
  AGENT_THREAD_AREAS      comma-separated area list (default: work,clients,content,infra,health,personal,other)
  LOCAL_UTC_OFFSET_HOURS  timestamps are written in this offset (default 0, same as the cockpit)
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCAL_TZ = timezone(timedelta(hours=int(os.environ.get("LOCAL_UTC_OFFSET_HOURS", "0") or 0)))
REPO = Path(os.environ.get("AGENT_ROOT") or Path(__file__).resolve().parents[2])
DEFAULT_PATH = REPO / "memory/state/threads.json"

DEFAULT_AREAS = ("work", "clients", "content", "infra", "health", "personal", "other")
AREAS = tuple(a.strip() for a in (os.environ.get("AGENT_THREAD_AREAS") or "").split(",") if a.strip()) \
    or DEFAULT_AREAS
STATUSES = ("waiting_on_operator", "waiting_on_others", "agent_working", "parked", "done")
# Display order: what needs the operator first.
STATUS_ORDER = ("waiting_on_operator", "agent_working", "waiting_on_others", "parked", "done")
STALE_DAYS = 7          # a thread untouched this long is flagged stale (list + cockpit)
MSG_IDS_CAP = 20        # recent message ids kept per thread for reply-to matching
LOCK_TIMEOUT_S = 10.0   # CLI writers wait this long for the lock before giving up


class CorruptStore(Exception):
    """threads.json exists but is not a valid store. Never write over it."""


class LockBusy(Exception):
    """The lock could not be taken within the timeout."""


def store_path() -> Path:
    env = os.environ.get("AGENT_THREADS_FILE")
    return Path(env).expanduser() if env else DEFAULT_PATH


def now_iso() -> str:
    return datetime.now(LOCAL_TZ).replace(microsecond=0).isoformat()


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=LOCAL_TZ)
    except Exception:
        return None


def empty_store() -> dict:
    return {"version": 1,
            "state": {"last_asked_thread": None, "current_thread": None, "updated": now_iso()},
            "threads": []}


def validate(data) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("threads"), list):
        raise CorruptStore("top level must be an object with a threads list")
    if not isinstance(data.get("state", {}), dict):
        raise CorruptStore("state must be an object")
    seen = set()
    for t in data["threads"]:
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t["id"]:
            raise CorruptStore("every thread needs a string id")
        if t["id"] in seen:
            raise CorruptStore(f"duplicate thread id {t['id']}")
        seen.add(t["id"])
    data.setdefault("state", {})
    data["state"].setdefault("last_asked_thread", None)
    data["state"].setdefault("current_thread", None)
    return data


def load(path: Path | None = None) -> dict:
    """Read the store. Missing file -> empty store. Unreadable/invalid -> CorruptStore."""
    p = path or store_path()
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty_store()
    except OSError as e:
        raise CorruptStore(f"cannot read: {type(e).__name__}") from e
    try:
        return validate(json.loads(raw))
    except CorruptStore:
        raise
    except Exception as e:
        raise CorruptStore(f"invalid JSON: {type(e).__name__}") from e


@contextlib.contextmanager
def locked(path: Path | None = None, timeout: float = LOCK_TIMEOUT_S):
    """Exclusive flock on <store>.lock. timeout=0 means try once (non-blocking)."""
    p = path or store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p) + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockBusy(str(p))
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)   # closing the fd releases the flock


def save(data: dict, path: Path | None = None) -> None:
    """Atomic replace. Caller must hold the lock."""
    p = path or store_path()
    validate(data)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    with contextlib.suppress(OSError):
        dfd = os.open(str(p.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def mutate(fn, path: Path | None = None, timeout: float = LOCK_TIMEOUT_S):
    """Lock, re-read, apply fn(data) -> result, stamp, write. Returns fn's result."""
    p = path or store_path()
    with locked(p, timeout):
        data = load(p)          # raises CorruptStore: nothing is written
        result = fn(data)
        data["state"]["updated"] = now_iso()
        save(data, p)
        return result


def find(data: dict, tid: str) -> dict | None:
    return next((t for t in data["threads"] if t["id"] == tid), None)


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return (s[:40].rstrip("-")) or "thread"


def split_keywords(s: str | None) -> list[str]:
    return [k.strip().lower() for k in (s or "").split(",") if k.strip()]


def add_msg(t: dict, msg) -> None:
    if msg is None:
        return
    msg = int(msg)
    t["last_msg_id"] = msg
    ids = [i for i in (t.get("msg_ids") or []) if i != msg]
    ids.append(msg)
    t["msg_ids"] = ids[-MSG_IDS_CAP:]


def touch_thread(data: dict, tid: str, *, where=None, nxt=None, status=None, msg=None,
                 keywords=None, asked=False, when: str | None = None) -> dict:
    t = find(data, tid)
    if t is None:
        raise KeyError(tid)
    if status is not None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        t["status"] = status
    if where is not None:
        t["where"] = where
    if nxt is not None:
        t["next"] = nxt
    if keywords:
        t["keywords"] = list(dict.fromkeys((t.get("keywords") or []) + keywords))
    add_msg(t, msg)
    t["last_touched"] = when or now_iso()
    st = data["state"]
    if t["status"] != "done":
        st["current_thread"] = tid
    # Waiting on the operator means the agent just asked something: a bare "ok" next refers here.
    if asked or status == "waiting_on_operator":
        st["last_asked_thread"] = tid
        st["last_asked_at"] = t["last_touched"]
    return t


def new_thread(data: dict, *, title: str, area: str, status: str = "agent_working", where: str = "",
               nxt: str = "", keywords=None, msg=None, tid: str | None = None) -> dict:
    if area not in AREAS:
        raise ValueError(f"area must be one of {AREAS}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    base = slugify(tid or title)
    cand, n = base, 2
    while find(data, cand):
        cand, n = f"{base}-{n}", n + 1
    ts = now_iso()
    t = {"id": cand, "title": title, "area": area, "status": status, "where": where,
         "next": nxt, "last_touched": ts, "last_msg_id": None, "msg_ids": [],
         "keywords": keywords or [], "created": ts}
    add_msg(t, msg)
    data["threads"].append(t)
    if status != "done":
        data["state"]["current_thread"] = cand
    if status == "waiting_on_operator":
        data["state"]["last_asked_thread"] = cand
        data["state"]["last_asked_at"] = ts
    return t


def done_thread(data: dict, tid: str) -> dict:
    t = find(data, tid)
    if t is None:
        raise KeyError(tid)
    t["status"] = "done"
    t["last_touched"] = now_iso()
    st = data["state"]
    for k in ("current_thread", "last_asked_thread"):
        if st.get(k) == tid:
            st[k] = None
    return t


def age_days(t: dict, now: datetime | None = None) -> float | None:
    d = parse_iso(t.get("last_touched"))
    if d is None:
        return None
    return ((now or datetime.now(LOCAL_TZ)) - d).total_seconds() / 86400


def ago(t: dict) -> str:
    a = age_days(t)
    if a is None:
        return "?"
    s = a * 86400
    if s < 3600:
        return f"{int(s // 60)}m ago"
    if s < 86400:
        return f"{int(s // 3600)}h ago"
    return f"{int(a)}d ago"


def sorted_threads(threads: list[dict]) -> list[dict]:
    """Status order first, then most recently touched first."""
    def key(t):
        d = parse_iso(t.get("last_touched"))
        rank = STATUS_ORDER.index(t["status"]) if t.get("status") in STATUS_ORDER else 99
        return (rank, -(d.timestamp() if d else 0))
    return sorted(threads, key=key)


# ---------------------------------------------------------------- CLI

def _die(msg: str, code: int = 2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def cmd_list(a) -> int:
    data = load()
    ts = data["threads"]
    if a.status:
        ts = [t for t in ts if t.get("status") == a.status]
    elif not a.all:
        ts = [t for t in ts if t.get("status") != "done"]
    if a.area:
        ts = [t for t in ts if t.get("area") == a.area]
    ts = sorted_threads(ts)
    if a.json:
        out = []
        for t in ts:
            age = age_days(t)
            out.append({**t, "stale": bool(age is not None and age > STALE_DAYS and t["status"] != "done"),
                        "ago": ago(t)})
        print(json.dumps({"state": data["state"], "threads": out}, indent=2, ensure_ascii=False))
        return 0
    if not ts:
        print("no threads match")
        return 0
    cur = None
    for t in ts:
        if t["status"] != cur:
            cur = t["status"]
            n = sum(1 for x in ts if x["status"] == cur)
            print(f"\n[{cur}] ({n})")
        age = age_days(t)
        stale = " STALE" if age is not None and age > STALE_DAYS and t["status"] != "done" else ""
        print(f"- {t['id']}: {t['title']} ({t['area']}, {ago(t)}{stale})")
        if t.get("where"):
            print(f"    where: {t['where']}")
        if t.get("next"):
            print(f"    next:  {t['next']}")
    st = data["state"]
    print(f"\ncurrent: {st.get('current_thread')} | last asked: {st.get('last_asked_thread')}")
    return 0


def cmd_touch(a) -> int:
    def fn(data):
        return touch_thread(data, a.id, where=a.where, nxt=a.next, status=a.status, msg=a.msg,
                            keywords=split_keywords(a.keywords), asked=a.asked)
    try:
        t = mutate(fn)
    except KeyError:
        _die(f"no thread with id {a.id}")
    print(f"touched {t['id']} [{t['status']}]")
    return 0


def cmd_new(a) -> int:
    def fn(data):
        return new_thread(data, title=a.title, area=a.area, status=a.status, where=a.where or "",
                          nxt=a.next or "", keywords=split_keywords(a.keywords), msg=a.msg, tid=a.id)
    t = mutate(fn)
    print(f"created {t['id']}")
    return 0


def cmd_done(a) -> int:
    try:
        t = mutate(lambda d: done_thread(d, a.id))
    except KeyError:
        _die(f"no thread with id {a.id}")
    print(f"done {t['id']}")
    return 0


def cmd_selftest(_a) -> int:
    """Store-level checks on a temp store. Exits 1 on any failure, and on zero checks run."""
    import subprocess
    results: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "threads.json"
        env = {**os.environ, "AGENT_THREADS_FILE": str(p)}
        env.pop("AGENT_THREAD_AREAS", None)
        me = [sys.executable, str(Path(__file__).resolve())]

        # 1. missing file -> empty store, new creates it
        r = subprocess.run(me + ["new", "--title", "Alpha thread", "--area", "infra"], env=env,
                           capture_output=True, text=True)
        results.append(("new on missing file creates store", r.returncode == 0 and p.exists()))

        # 2. 20 concurrent writers, no lost update
        procs = [subprocess.Popen(me + ["new", "--title", f"Par {i}", "--area", "other"], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for i in range(20)]
        rcs = [pp.wait() for pp in procs]
        d = load(p)
        results.append(("20 parallel new -> 21 threads, all rc 0",
                        all(rc == 0 for rc in rcs) and len(d["threads"]) == 21))

        # 3. 20 concurrent touches of one thread with distinct message ids -> all 20 ids kept
        procs = [subprocess.Popen(me + ["touch", "alpha-thread", "--msg", str(1000 + i)], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for i in range(20)]
        rcs = [pp.wait() for pp in procs]
        t = find(load(p), "alpha-thread")
        results.append(("20 parallel touch keep all 20 message ids",
                        all(rc == 0 for rc in rcs) and sorted(t["msg_ids"]) == list(range(1000, 1020))))

        # 4. waiting_on_operator sets last_asked_thread; done clears it
        subprocess.run(me + ["touch", "alpha-thread", "--status", "waiting_on_operator"], env=env,
                       capture_output=True)
        ok1 = load(p)["state"]["last_asked_thread"] == "alpha-thread"
        subprocess.run(me + ["done", "alpha-thread"], env=env, capture_output=True)
        st = load(p)["state"]
        results.append(("asked pointer set by waiting_on_operator, cleared by done",
                        ok1 and st["last_asked_thread"] is None and st["current_thread"] is None))

        # 5. bad area rejected, store unchanged
        before = p.read_bytes()
        r = subprocess.run(me + ["new", "--title", "x", "--area", "nope"], env=env, capture_output=True)
        results.append(("invalid area rejected, store unchanged", r.returncode != 0 and p.read_bytes() == before))

        # 6. AGENT_THREAD_AREAS replaces the default area list
        r = subprocess.run(me + ["new", "--title", "Custom area", "--area", "garden"],
                           env={**env, "AGENT_THREAD_AREAS": "garden,other"}, capture_output=True)
        results.append(("AGENT_THREAD_AREAS accepts a custom area",
                        r.returncode == 0 and find(load(p), "custom-area") is not None))

        # 7. corrupt store: writes refused, file untouched
        p.write_text("{not json", encoding="utf-8")
        r = subprocess.run(me + ["new", "--title", "y", "--area", "other"], env=env, capture_output=True)
        results.append(("corrupt store: write refused, exit 2, bytes untouched",
                        r.returncode == 2 and p.read_text() == "{not json"))

        # 8. no temp files left behind
        left = [x.name for x in Path(td).iterdir() if x.name.endswith(".tmp")]
        results.append(("no temp files left", not left))

    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    passed = sum(ok for _, ok in results)
    print(f"{passed}/{len(results)} passed")
    if not results:
        print("FAIL: zero checks ran")
        return 1
    return 0 if passed == len(results) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Open-threads tracker (memory/state/threads.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--area", choices=AREAS)
    p.add_argument("--all", action="store_true", help="include done threads")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("touch")
    p.add_argument("id")
    p.add_argument("--where")
    p.add_argument("--next")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--msg", type=int, help="chat message id that belongs to this thread")
    p.add_argument("--keywords", help="comma-separated, appended")
    p.add_argument("--asked", action="store_true", help="the agent just asked the operator something here")
    p.set_defaults(fn=cmd_touch)

    p = sub.add_parser("new")
    p.add_argument("--title", required=True)
    p.add_argument("--area", required=True, choices=AREAS)
    p.add_argument("--status", default="agent_working", choices=STATUSES)
    p.add_argument("--where")
    p.add_argument("--next")
    p.add_argument("--keywords", help="comma-separated")
    p.add_argument("--msg", type=int)
    p.add_argument("--id", help="explicit slug (default: from title)")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("done")
    p.add_argument("id")
    p.set_defaults(fn=cmd_done)

    p = sub.add_parser("selftest")
    p.set_defaults(fn=cmd_selftest)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except CorruptStore as e:
        _die(f"threads.json is unreadable ({e}); refusing to write. Restore it from a backup "
             f"or fix the JSON by hand.")
    except LockBusy:
        _die("threads.json is locked by another writer; try again", 3)
    except ValueError as e:
        _die(str(e))
    return 1


if __name__ == "__main__":
    sys.exit(main())
