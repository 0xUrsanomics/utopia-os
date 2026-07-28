#!/usr/bin/env python3
# lib_signal_store.py — crash- and concurrency-safe JSON list/envelope append for shared harvest files.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""lib_signal_store.py — crash- and concurrency-safe JSON list append.

Multiple harvesters (e.g. a telegram / email / rss / job / social harvester) read-modify-write
the SAME shared today-signals.json. The naive hand-rolled pattern everywhere is:

    existing = json.load(open(p))      # read
    existing.extend(items)             # modify
    json.dump(existing, open(p, "w"))  # write  <-- truncates THEN writes

Two failure modes:
  1. Corruption: `open(p,"w")` truncates immediately. A crash / kill / OOM
     between truncate and dump leaves a 0-byte or half-written file. The
     next reader's json.load throws, the harvester swallows it to `[]`, and
     the whole day's accumulated signals are silently gone.
  2. Lost update: two harvesters overlapping (cron drift) each read the old
     list, each append only their own items, last writer's os-level write
     wins. The other harvester's signals vanish with no error.

Fix = serialize the whole read-modify-write across processes with an
exclusive file lock, and make the write atomic (temp file in the same dir
+ fsync + os.replace, which is atomic on POSIX same-filesystem). Atomicity
alone stops corruption; the lock is what stops lost-update.

Pure stdlib. Any writer: `from lib_signal_store import append_signals`.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl  # POSIX only
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - non-POSIX (native Windows) only
    _HAVE_FCNTL = False
    # SAY SO. Without fcntl the "exclusive lock" below degrades to a no-op, so two
    # processes can interleave writes and the guarantee in _exclusive_lock's docstring
    # quietly stops being true. A silent downgrade of a concurrency control is worse
    # than a missing feature, because nothing distinguishes it from a working lock
    # until data is already lost. Run under WSL2 on Windows; see QUICKSTART.md.
    import warnings
    warnings.warn(
        "fcntl is unavailable on this platform, so lib_signal_store's cross-process "
        "lock is a NO-OP and concurrent writers are not serialised. Run under WSL2 on "
        "Windows, or ensure only one process writes the signal store.",
        RuntimeWarning, stacklevel=2,
    )


@contextmanager
def _exclusive_lock(lock_path: Path):
    """Cross-process exclusive lock. Blocks until acquired, always released.

    Lock lives in a sidecar `<file>.lock` so it never collides with the
    atomic os.replace of the data file itself.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        if _HAVE_FCNTL:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if _HAVE_FCNTL:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def read_signals(path: str | os.PathLike) -> list:
    """Tolerant reader: missing / empty / corrupt file -> []. Never raises."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError, ValueError):
        return []


def _atomic_write_json(path: Path, obj) -> None:
    """Write obj as JSON to a temp file in the SAME dir, fsync, os.replace.

    Same-dir temp guarantees os.replace is a same-filesystem atomic rename.
    fsync before replace so a power loss can't surface an empty file under
    the real name.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic on POSIX same-fs
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_signals(items: list, path: str | os.PathLike) -> int:
    """Atomically append `items` to the JSON list at `path`, concurrency-safe.

    The lock spans the ENTIRE read-modify-write so two overlapping
    harvesters cannot lose each other's updates. Returns the new total
    length. A corrupt/missing existing file is treated as [] (the items
    being appended are still preserved, not lost to the corruption).
    """
    if not items:
        p = Path(path)
        return len(read_signals(p))
    p = Path(path)
    with _exclusive_lock(p.with_suffix(p.suffix + ".lock")):
        existing = read_signals(p)
        existing.extend(items)
        _atomic_write_json(p, existing)
        return len(existing)


def _today_local() -> str:
    # Local date without pulling a tz lib. Set LOCAL_UTC_OFFSET_HOURS to your offset.
    import datetime as _dt
    offset = int(os.environ.get("LOCAL_UTC_OFFSET_HOURS", "0"))
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=offset)).strftime("%Y-%m-%d")


# Schema-guard: the today-signals.json ENVELOPE feeds a downstream content pipeline. Consumers read
# enriched fields (e.g. a signal's content angle / pillar). Harvesters have repeatedly shipped signals
# MISSING these enriched fields, and the downstream step then produced nothing. This guard NORMALIZES
# rather than rejects: rejecting a write would drop signals, the exact data-loss failure this whole
# module exists to prevent. Every stored signal is guaranteed to carry the enriched keys (defaulted to
# None when absent); existing values are never overwritten. Consumers can therefore rely on the keys
# existing instead of KeyError-ing or silently skipping. normalize_signal is public so a
# producer/consumer can validate before use if it wants.
ENRICHED_FIELDS = ("content_angle", "content_pillar")


def normalize_signal(sig):
    """Guarantee a signal dict carries every ENRICHED_FIELDS key. Non-destructive: present values
    are preserved, only absent keys are added with a None default. Returns (sig, missing_fields)
    where missing_fields lists the keys that had to be defaulted."""
    if not isinstance(sig, dict):
        return sig, []  # leave non-dict entries untouched (defensive)
    missing = [k for k in ENRICHED_FIELDS if k not in sig]
    for k in missing:
        sig[k] = None
    return sig, missing


def _normalize_envelope_signals(env, source) -> int:
    """Normalize the whole env['signals'] array in place. Emit one stderr line if any signal was
    missing an enriched field, so a silent strip is visible in cron logs rather than swallowed.
    Returns the count of signals that had to be defaulted."""
    import sys as _sys
    sigs = env.get("signals") or []
    missing_n = 0
    for i, s in enumerate(sigs):
        sigs[i], miss = normalize_signal(s)
        if miss:
            missing_n += 1
    if missing_n:
        print(
            f"[lib_signal_store] schema-guard normalized {missing_n}/{len(sigs)} signal(s) "
            f"missing {list(ENRICHED_FIELDS)} (defaulted to None); writer source={source}",
            file=_sys.stderr,
        )
    return missing_n


def append_envelope_signals(items: list, path: str | os.PathLike,
                            source: str = "unknown") -> int:
    """Concurrency-safe append into the today-signals.json ENVELOPE shape.

    today-signals.json is NOT a flat list. The real on-disk + consumer
    contract (a downstream reader does `data.get("signals", [])`) is:

        {"date","generated_at","source","signals":[...], ...extra preserved}

    A flat-list append (append_signals) would discard the envelope and
    break every reader. This locks the whole RMW, tolerates a
    missing/corrupt/legacy-list file (rebuilds a fresh envelope, or lifts
    a bare list into .signals so nothing is lost), appends to `signals`,
    refreshes date/generated_at, records last writer in `source`, and
    preserves any extra keys already on the envelope (e.g. `_recovered`).
    Date rolls daily: if the stored `date` is not today (local), the signals
    array resets (a fresh day) instead of growing unbounded.
    """
    import datetime as _dt
    if not items:
        items = []
    p = Path(path)
    with _exclusive_lock(p.with_suffix(p.suffix + ".lock")):
        raw = None
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, OSError, ValueError):
                raw = None
        if isinstance(raw, dict):
            env = dict(raw)                       # preserve extra keys
            sigs = env.get("signals")
            env["signals"] = sigs if isinstance(sigs, list) else []
        elif isinstance(raw, list):
            env = {"signals": list(raw)}          # legacy flat list -> lift
        else:
            env = {"signals": []}                 # missing/corrupt -> fresh
        today = _today_local()
        stored = env.get("date")
        # Reset ONLY on a genuine stale date (a real prior day). An ABSENT
        # date (corrupt-recovery / legacy-list lift / fresh file) must NOT
        # wipe: there's no prior day to drop, and wiping would lose the
        # lifted signals. Just stamp today.
        if stored is not None and stored != today:
            env["signals"] = []
        env["date"] = today
        env["signals"].extend(items)
        offset = int(os.environ.get("LOCAL_UTC_OFFSET_HOURS", "0"))
        env["generated_at"] = _dt.datetime.now(
            _dt.timezone(_dt.timedelta(hours=offset))).isoformat()
        env["source"] = source
        env.setdefault("date", today)
        _normalize_envelope_signals(env, source)  # schema-guard: enriched fields always present
        _atomic_write_json(p, env)
        return len(env["signals"])


def atomic_write_json(obj, path: str | os.PathLike) -> None:
    """Crash-safe FULL REPLACE of a JSON file (temp + fsync + os.replace).

    For single-writer full-overwrite producers (e.g. a telethon harvester or
    an rss poller) where the failure mode is a kill mid-`open(w)+json.dump`
    leaving a truncated/empty file, NOT lost-update. Held under the same
    sidecar lock so it is also safe if a reader/another writer races.
    """
    p = Path(path)
    with _exclusive_lock(p.with_suffix(p.suffix + ".lock")):
        _atomic_write_json(p, obj)


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="atomic signal-store helper")
    ap.add_argument("path")
    ap.add_argument("--read", action="store_true",
                    help="print current item count and exit")
    ap.add_argument("--append-stdin", action="store_true",
                    help="read a JSON list from stdin and atomically append "
                         "it to <path> (concurrency-safe). prints new total")
    ap.add_argument("--replace-stdin", action="store_true",
                    help="read JSON from stdin and atomically REPLACE <path>")
    ap.add_argument("--append-envelope-stdin", action="store_true",
                    help="read a JSON list of signals from stdin and append "
                         "into the today-signals.json ENVELOPE "
                         "({date,generated_at,source,signals:[]}), "
                         "concurrency-safe. Use this for today-signals.json, "
                         "NOT --append-stdin. prints new signals count")
    ap.add_argument("--source", default="unknown",
                    help="writer name recorded in the envelope (with "
                         "--append-envelope-stdin), e.g. signal-harvester-rss")
    a = ap.parse_args()
    if a.read:
        print(len(read_signals(a.path)))
    elif a.append_stdin:
        payload = json.load(sys.stdin)
        if not isinstance(payload, list):
            print("error: stdin must be a JSON list", file=sys.stderr)
            sys.exit(2)
        print(append_signals(payload, a.path))
    elif a.append_envelope_stdin:
        payload = json.load(sys.stdin)
        if not isinstance(payload, list):
            print("error: stdin must be a JSON list of signals",
                  file=sys.stderr)
            sys.exit(2)
        print(append_envelope_signals(payload, a.path, source=a.source))
    elif a.replace_stdin:
        atomic_write_json(json.load(sys.stdin), a.path)
        print("ok")
    else:
        ap.error("one of --read / --append-stdin / "
                 "--append-envelope-stdin / --replace-stdin required")
