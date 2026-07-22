#!/usr/bin/env python3
# file_intake.py — classify, place and INDEX received artifacts so recall can reach them.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Classify, place and INDEX received artifacts so recall can reach them.

WHY THIS EXISTS. Repeated "we don't have that" assertions turned out to be wrong:
the artifacts (a training log, health scans, an invoice) all existed. The root
cause was not carelessness, it was that hundreds of files sat in an inbox
referenced by ZERO scripts and indexed in ZERO recall sources. Artifacts with no
canonical home and no index produce confident false negatives, which is the most
expensive kind of wrong.

THE INDEX IS THE POINT, not the tidy tree. Moving a file to a prettier path fixes
nothing on its own; what failed was RECALL. So every artifact gets an INDEX.jsonl
row even when it cannot be classified, and `archive/unsorted/` is a first-class
destination rather than a failure. An indexed unsorted file is findable. A
perfectly-filed unindexed one is not.

WHAT THE FILENAMES GIVE US. Chat-inbox names often look like
`1775317323451-AgADDRwAAnwoiFY.jpg`: a 13-digit epoch-ms arrival stamp plus an
opaque file id. No semantics, but the timestamp is free and reliable, so every row
gets a real date even when the content is unreadable.

SAFETY, in order of importance:
  - DRY RUN by default. `--apply` is required to touch anything.
  - Nothing is ever deleted. Files are COPIED to the archive and the inbox copy is left
    alone unless `--drain` is passed, which MOVES instead.
  - Every applied operation appends to `archive/OPERATIONS.jsonl`, so a mistaken run is
    undone by replaying it backwards.
  - A destination that already exists is REFUSED, never overwritten.

Config via env:
  AGENT_ROOT            repo root (default: two dirs above this file)
  AGENT_INBOX           source inbox dir (default: ~/.agent/channels/telegram/inbox)
  AGENT_OCR_LANGS       tesseract langs, e.g. "eng" or "eng+deu" (default: eng)
  AGENT_UTC_OFFSET_HOURS  local UTC offset for arrival dates (default: 0 = UTC)

    python3 file_intake.py                      # dry run over the default inbox
    python3 file_intake.py --limit 40 --verbose
    python3 file_intake.py --apply              # copy + index
    python3 file_intake.py --apply --drain      # move + index (inbox becomes staging)
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
INBOX = Path(os.environ.get("AGENT_INBOX", str(Path.home() / ".agent/channels/telegram/inbox")))
ARCHIVE = REPO / "archive"
INDEX = ARCHIVE / "INDEX.jsonl"
OPS = ARCHIVE / "OPERATIONS.jsonl"
# Local timezone as a fixed UTC offset (hours). Default 0 = UTC.
LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=float(os.environ.get("AGENT_UTC_OFFSET_HOURS", "0"))))
OCR_LANGS = os.environ.get("AGENT_OCR_LANGS", "eng")
USE_OCR = True   # flipped off by --no-ocr; images are most of a typical corpus so it matters

TG_NAME = re.compile(r"^(\d{13})-(\S+?)\.([A-Za-z0-9]+)$")

# Media class by extension. Kind is a COARSE bucket; subject is the fine axis.
KIND = {
    "jpg": "image", "jpeg": "image", "png": "image", "webp": "image",
    "pdf": "doc", "docx": "doc", "md": "doc", "txt": "doc", "html": "doc",
    "xlsx": "sheet", "csv": "sheet",
    "oga": "voice", "ogg": "voice", "mp3": "voice", "m4a": "voice",
    "mp4": "video", "mov": "video",
    "py": "code", "sh": "code", "json": "code", "skill": "code",
}

# Content signatures -> subject. Ordered: FIRST match wins, so put specific above generic.
# These are EXAMPLES: extend / replace them with the artifact classes YOU receive.
SIGNATURES: list[tuple[str, str, re.Pattern]] = [
    ("health/body-scans", "evolt",    re.compile(r"EVOLT|SEGMENTAL ANALYSIS|VISCERAL FAT LEVEL", re.I)),
    ("health/body-scans", "inbody",   re.compile(r"InBody|Body Composition Analysis|SMM\b.*PBF", re.I)),
    ("health/bloodwork",  "lab",      re.compile(r"h[ae]matolog|cholesterol|triglyceride|laborator", re.I)),
    ("finance/invoices",  "invoice",  re.compile(r"\binvoice\b|tax invoice|amount due|\bbill\b", re.I)),
    ("finance/receipts",  "receipt",  re.compile(r"\breceipt\b|payment (?:received|successful)|\bpaid\b", re.I)),
    ("deals/contracts",   "contract", re.compile(r"memorandum of understanding|\bMoU\b|this agreement|\bcontract\b", re.I)),
    ("deals/proposals",   "proposal", re.compile(r"\bproposal\b|scope of work|deliverables|sponsorship deck", re.I)),
    # Add your jurisdiction's regulatory vocabulary + regulator names here.
    ("regulatory",        "reg",      re.compile(r"\bregulation\b|\bregulatory\b|\bcircular\b|\bdecree\b|\bstatute\b|compliance notice", re.I)),
    ("training/programs", "program",  re.compile(r"\bRPE\b|\bAMRAP\b|working set|deload|Block\s*\d", re.I)),
]


# OCR signatures are DELIBERATELY different from the text ones above. Photos of printouts
# OCR badly: a brand string can score 0 hits on files we KNOW match. What survives the
# noise is domain vocabulary, so these match on vocabulary and require N distinct terms
# rather than one exact hit. The N misses still get indexed, just unclassified.
OCR_SIGNATURES: list[tuple[str, str, re.Pattern, int]] = [
    ("health/body-scans", "inbody",
     re.compile(r"viscera|waist|hip\s*ratio|skeletal|muscle\s*mass|fat\s*mass|"
                r"body\s*compos|/\s*100|segmental|inbod", re.I), 2),
    ("finance/receipts", "receipt",
     re.compile(r"total|subtotal|\btax\b|\bvat\b|receipt|cashier|payment|amount", re.I), 3),
    ("deals/contracts", "contract",
     re.compile(r"agreement|first\s*party|memorandum|signed|witness|hereby", re.I), 2),
]


def ocr(p: Path, cap: int = 4000) -> str:
    """Best-effort OCR. psm 3 (auto page segmentation) measurably beat psm 6 on photos
    of printouts, recovering brand tokens psm 6 lost. Never raises."""
    try:
        r = subprocess.run(["tesseract", str(p), "-", "--psm", "3", "-l", OCR_LANGS],
                           capture_output=True, text=True, timeout=25)
        return r.stdout[:cap]
    except Exception:
        return ""


def arrival(name: str) -> tuple[str, str] | None:
    """(iso-date, ext) from a chat-inbox filename, or None if it is not one."""
    m = TG_NAME.match(name)
    if not m:
        return None
    ms, _, ext = m.groups()
    try:
        dt = datetime.datetime.fromtimestamp(int(ms) / 1000, LOCAL_TZ)
    except (ValueError, OSError, OverflowError):
        return None
    if not (2020 < dt.year < 2100):      # implausible stamp, do not trust it
        return None
    return dt.strftime("%Y-%m-%d"), ext.lower()


def jpeg_dims(p: Path) -> tuple[int, int] | None:
    """Width/height from JPEG SOF markers.

    `file -b` was tried first and returns DPI for many of these, not pixel size, which
    silently broke an earlier filter. Parsing the SOF marker is the only reliable route.
    """
    try:
        with p.open("rb") as f:
            if f.read(2) != b"\xff\xd8":
                return None
            while True:
                b = f.read(1)
                if not b:
                    return None
                if b != b"\xff":
                    continue
                marker = f.read(1)
                while marker == b"\xff":
                    marker = f.read(1)
                if marker in b"\xc0\xc1\xc2\xc3\xc5\xc6\xc7\xc9\xca\xcb\xcd\xce\xcf":
                    f.read(3)
                    h, w = struct.unpack(">HH", f.read(4))
                    return w, h
                ln = f.read(2)
                if len(ln) < 2:
                    return None
                f.seek(struct.unpack(">H", ln)[0] - 2, 1)
    except Exception:
        return None


def text_of(p: Path, ext: str, cap: int = 6000) -> str:
    """Cheap text extraction. Never raises, returns '' when unavailable."""
    try:
        if ext == "pdf":
            r = subprocess.run(["pdftotext", "-layout", "-f", "1", "-l", "2", str(p), "-"],
                               capture_output=True, text=True, timeout=20)
            return r.stdout[:cap]
        if ext in ("md", "txt", "html", "json", "py", "sh", "skill", "csv"):
            return p.read_text(encoding="utf-8", errors="replace")[:cap]
        if ext == "docx":
            r = subprocess.run(["unzip", "-p", str(p), "word/document.xml"],
                               capture_output=True, text=True, timeout=20)
            return re.sub(r"<[^>]+>", " ", r.stdout)[:cap]
    except Exception:
        pass
    return ""


def classify(p: Path, ext: str) -> tuple[str, str, float, str]:
    """-> (subject, label, confidence, basis). Confidence is recorded, never hidden.

    Low confidence routes to unsorted/ but is STILL indexed, so a wrong guess degrades to
    'findable but provisional' instead of 'silently misfiled and now harder to find'.
    """
    kind = KIND.get(ext, "other")
    body = text_of(p, ext)
    if body.strip():
        for subject, label, pat in SIGNATURES:
            if pat.search(body):
                return subject, label, 0.9, f"content matched {label}"
        # Text extracted but nothing matched: real signal that it is simply another doc.
        return "unsorted", kind, 0.35, "text extracted, no signature matched"

    if kind == "image":
        if USE_OCR:
            txt = ocr(p)
            if txt.strip():
                best = None
                for subject, label, pat, need in OCR_SIGNATURES:
                    distinct = {m.group(0).lower().replace(" ", "") for m in pat.finditer(txt)}
                    if len(distinct) >= need and (best is None or len(distinct) > best[0]):
                        best = (len(distinct), subject, label)
                if best:
                    n_hits, subject, label = best
                    # Cap below the text-signature tier: OCR is noisier, so an OCR-derived
                    # subject should never claim the same certainty as extracted text.
                    conf = min(0.8, 0.5 + 0.1 * n_hits)
                    return subject, label, conf, f"OCR matched {n_hits} {label} terms"
        d = jpeg_dims(p) if ext in ("jpg", "jpeg") else None
        if d:
            w, h = d
            ratio = h / w if w else 0
            if ratio > 1.7:
                return "unsorted", "screenshot", 0.4, f"tall aspect {w}x{h}, likely a phone screenshot"
            return "unsorted", "photo", 0.3, f"aspect {w}x{h}"
        return "unsorted", "image", 0.2, "image, no dimensions readable"

    if kind in ("voice", "video"):
        # Deliberately NOT transcribed here. Filing places and indexes; extraction is a
        # separate per-domain concern (the same boundary as a separate per-domain extractor).
        return "unsorted", kind, 0.3, f"{kind}, not transcribed at intake"

    return "unsorted", kind, 0.2, "no cheap discriminator applied"


def slug(label: str, digest: str) -> str:
    return f"{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-') or 'item'}-{digest[:8]}"


def plan(src: Path) -> dict | None:
    a = arrival(src.name)
    if not a:
        return None
    date, ext = a
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    subject, label, conf, basis = classify(src, ext)
    dest = ARCHIVE / subject / f"{date}-{slug(label, digest)}.{ext}"
    return {
        "sha256": digest, "source": str(src), "dest": str(dest.relative_to(REPO)),
        "subject": subject, "label": label, "kind": KIND.get(ext, "other"),
        "ext": ext, "arrived": date, "confidence": conf, "basis": basis,
        "bytes": src.stat().st_size,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default=str(INBOX))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--drain", action="store_true", help="MOVE instead of copy. requires --apply")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-ocr", action="store_true",
                    help="skip OCR on images. ~0.3s/image, and images are most of the corpus")
    args = ap.parse_args()

    global USE_OCR
    USE_OCR = not args.no_ocr

    if args.drain and not args.apply:
        print("refused: --drain without --apply would imply a move in a dry run", file=sys.stderr)
        return 2

    src_dir = Path(args.source).expanduser()
    if not src_dir.exists():
        print(f"no such source: {src_dir}", file=sys.stderr)
        return 2

    files = sorted(f for f in src_dir.iterdir() if f.is_file())
    if args.limit:
        files = files[:args.limit]

    seen: set[str] = set()
    if INDEX.exists():
        for line in INDEX.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["sha256"])
            except Exception:
                pass

    plans, skipped, dupes = [], 0, 0
    for f in files:
        try:
            pl = plan(f)
        except Exception as e:
            print(f"  ! {f.name}: {str(e)[:60]}")
            skipped += 1
            continue
        if not pl:
            skipped += 1
            continue
        if pl["sha256"] in seen:
            dupes += 1
            continue
        seen.add(pl["sha256"])
        plans.append(pl)

    by_subject = Counter(p["subject"] for p in plans)
    by_label = Counter(p["label"] for p in plans)
    print(f"scanned {len(files)} file(s)  planned {len(plans)}  "
          f"already-indexed {dupes}  unparseable-name {skipped}")
    print("\nby subject:")
    for s, c in by_subject.most_common():
        print(f"  {c:>4}  {s}")
    print("\nby label:")
    for l, c in by_label.most_common(10):
        print(f"  {c:>4}  {l}")
    ident = sum(1 for p in plans if p["confidence"] >= 0.8)
    print(f"\nconfidently identified: {ident}/{len(plans)}. "
          f"The rest land in unsorted/ but are STILL indexed and therefore findable.")

    if args.verbose:
        print("\nfirst 12 planned placements:")
        for p in plans[:12]:
            print(f"  {p['confidence']:.2f}  {p['dest']}")
            print(f"        {p['basis']}")

    if not args.apply:
        print("\nDRY RUN. nothing written. re-run with --apply to place + index.")
        return 0

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    placed, refused = 0, 0
    now = datetime.datetime.now(LOCAL_TZ).isoformat()
    with INDEX.open("a", encoding="utf-8") as idx, OPS.open("a", encoding="utf-8") as ops:
        for p in plans:
            dest = REPO / p["dest"]
            if dest.exists():
                refused += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = Path(p["source"])
            if args.drain:
                shutil.move(str(src), dest)
            else:
                shutil.copy2(src, dest)
            idx.write(json.dumps({**p, "indexed_at": now}) + "\n")
            ops.write(json.dumps({"ts": now, "op": "move" if args.drain else "copy",
                                  "from": p["source"], "to": p["dest"],
                                  "sha256": p["sha256"]}) + "\n")
            placed += 1
    print(f"\nplaced {placed}   refused (destination existed) {refused}")
    print(f"index: {INDEX.relative_to(REPO)}   reversal log: {OPS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
