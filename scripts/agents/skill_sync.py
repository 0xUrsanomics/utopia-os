#!/usr/bin/env python3
# skill_sync.py — fleet skill-sync / drift monitor: propagate canonical skills across tenants.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Fleet skill-sync / drift monitor.

Fleet tenants hold COPIES of skills, not symlinks (a headless tenant can't symlink into the
shared tree). When `skills-shared/` or `skills/` updates, tenant copies silently drift. This
tool detects that drift and, for skills explicitly marked canonical-tracking, syncs the
canonical version back.

SAFE BY DEFAULT: dry-run unless `--apply`. A DRIFTED skill is NEVER overwritten unless it is
classed `canonical` — because drift is often an INTENTIONAL tenant adaptation (e.g. a
sycophancy-guard adapted to the fleet-bus escalation flow, hundreds of lines different on
purpose). Unexplained drift defaults to REPORT-ONLY.

Classification per tenant skill:
  in-sync     : byte-identical to canonical  -> tracks canonical, nothing to do
  drift       : differs from canonical        -> stale OR intentional adaptation
  tenant-only : no canonical counterpart      -> tenant owns it, leave alone

Manifest override (memory/state/fleet-skill-sync-manifest.json):
  {"<tenant>/<skill.md>": "canonical" | "adapted" | "tenant-only"}
  canonical   -> on --apply, sync canonical -> tenant when drifted (backup first)
  adapted     -> tenant-owned intentional divergence, NEVER auto-sync (report only)
  tenant-only -> ignore
  Absent key  -> SAFE DEFAULT: in-sync->canonical, drift->adapted, no-canon->tenant-only.

Tenant discovery: tenants keep skill copies under <tenant>/.claude/skills inside the fleet
home (AGENT_FLEET_HOME, default <root>/.data/fleet). Extra tenants outside that tree can be
added via FLEET_EXTRA_TENANTS="name=/abs/skills/dir,other=/abs/dir".

Usage:
  python3 scripts/agents/skill_sync.py           # dry-run report
  python3 scripts/agents/skill_sync.py --apply    # sync canonical+drifted only
  python3 scripts/agents/skill_sync.py --json      # machine-readable (cron)
Exit: 0 = nothing actionable; 1 = adapted-drift (info); 2 = canonical-drift needs sync.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, sys, tempfile
from pathlib import Path

# AGENT_ROOT / REPO defaults to the repo root (this file is scripts/agents/skill_sync.py).
REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
CANON_DIRS = [REPO / "skills-shared", REPO / "skills"]  # search order
MANIFEST = REPO / "memory" / "state" / "fleet-skill-sync-manifest.json"
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(REPO / ".data")))
FLEET_ROOT = Path(os.environ.get("AGENT_FLEET_HOME", str(DATA_DIR / "fleet")))


def _extra_tenants() -> dict[str, Path]:
    """Parse FLEET_EXTRA_TENANTS='name=/abs/dir,other=/abs/dir' for tenants outside the fleet home."""
    out: dict[str, Path] = {}
    raw = os.environ.get("FLEET_EXTRA_TENANTS", "").strip()
    for pair in [p for p in raw.split(",") if p.strip()]:
        if "=" in pair:
            name, path = pair.split("=", 1)
            out[name.strip()] = Path(path.strip()).expanduser()
    return out


def discover_tenants() -> dict[str, Path]:
    t: dict[str, Path] = {}
    if FLEET_ROOT.is_dir():
        for d in sorted(FLEET_ROOT.glob("*/.claude/skills")):
            t[d.parts[-3]] = d  # <tenant>/.claude/skills -> tenant name
    for name, d in _extra_tenants().items():
        if d.is_dir():
            t[name] = d
    return t


def canonical_for(skill_name: str) -> Path | None:
    for base in CANON_DIRS:
        p = base / skill_name
        if p.is_file():
            return p
    return None


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def classify(tenant_skill: Path, canon: Path | None, override: str | None) -> tuple[str, str]:
    """Return (status, effective_class)."""
    if canon is None:
        return "tenant-only", override or "tenant-only"
    status = "in-sync" if _sha(tenant_skill) == _sha(canon) else "drift"
    if override:
        return status, override
    # safe defaults
    return status, ("canonical" if status == "in-sync" else "adapted")


def sync_one(canon: Path, dest: Path) -> None:
    """Atomic copy canon -> dest, backing up the existing dest first."""
    bak = dest.with_suffix(dest.suffix + ".bak-presync")
    shutil.copy2(dest, bak)
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(canon.read_bytes())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="sync canonical-marked drifted skills")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    manifest = {}
    if MANIFEST.is_file():
        try:
            manifest = {k: v for k, v in json.loads(MANIFEST.read_text()).items() if not k.startswith("_")}
        except (json.JSONDecodeError, OSError):
            manifest = {}

    tenants = discover_tenants()
    rows, synced, needs_sync, review = [], [], 0, 0
    for tname, sdir in tenants.items():
        for sk in sorted(sdir.glob("*.md")):
            key = f"{tname}/{sk.name}"
            canon = canonical_for(sk.name)
            status, cls = classify(sk, canon, manifest.get(key))
            action = "-"
            if status == "drift" and cls == "canonical":
                needs_sync += 1
                if args.apply:
                    sync_one(canon, sk)
                    action = "SYNCED"
                    synced.append(key)
                    needs_sync -= 1
                else:
                    action = "would-sync"
            elif status == "drift" and cls == "adapted":
                action = "review (adapted?)"
                review += 1
            rows.append({"tenant": tname, "skill": sk.name,
                         "canonical": str(canon.relative_to(REPO)) if canon else None,
                         "status": status, "class": cls, "action": action})

    if args.json:
        print(json.dumps({"rows": rows, "synced": synced, "needs_sync": needs_sync,
                          "review": review, "tenants": list(tenants)}, indent=2))
    else:
        print(f"fleet skill-sync: {len(tenants)} tenants, {len(rows)} tenant skills")
        for r in rows:
            print(f"  [{r['status']:9s}] {r['tenant']}/{r['skill']:22s} class={r['class']:11s} {r['action']}")
        if synced:
            print(f"  SYNCED {len(synced)}: {', '.join(synced)}")
        note = []
        if needs_sync:
            note.append(f"{needs_sync} canonical-drift (need --apply)")
        if review:
            note.append(f"{review} adapted-drift (manual review, expected)")
        print("  " + ("; ".join(note) if note else "clean, nothing actionable."))
    # exit: 2 = canonical-drift needs sync (alert-worthy); 1 = only adapted-drift (info); 0 = clean
    return 2 if needs_sync else (1 if review else 0)


if __name__ == "__main__":
    raise SystemExit(main())
