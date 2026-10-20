#!/usr/bin/env python3
# inputs_manifest_check.py: validate declared skill inputs:/stages: manifests, catch dead pointers.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""inputs_manifest_check.py - validate skill inputs: + stages: manifests (ICM lifts 1-3).

Adapted from the Interpretable Context Methodology (arXiv 2603.16021v2):

  inputs:  (Lift 1) the exact context files a skill loads, split
             reference: (ICM Layer 3, stable rules internalized as constraints)
             working:   (ICM Layer 4, per-run material processed as input)
           so loading is a declared, auditable contract, not per-run agent judgment.

  stages:  (Lift 2) the pipeline's execution order as a declared list, each stage with
             id / does / optional out: (the artifact it emits) / budget: (Lift 3, a soft
             per-stage token target, ICM range 2000-8000).

Checks (dependency-free, no PyYAML, so it runs under any python):
  - every inputs reference/working path resolves (templated {var}/YYYY-MM-DD -> static prefix dir)
  - every stage `out:` path resolves
  These are DRIFT (exit 1): they catch the dead-pointer failure class (an index or skill that
  points at a file that was renamed or never written, which silently loads nothing).
  - budget missing / out of the 2000-8000 band, or a stage missing id/does: ADVISORY only
    (Lift 3 is a hygiene target, not a proven quality lever), printed but exit stays 0.

Skill files scanned: skills/*.md, skills/*/SKILL.md, skills-shared/*.md, skills-shared/*/SKILL.md.
Paths in a manifest resolve relative to AGENT_ROOT (default: the repo root).

Exit 0 = clean (advisories allowed). Exit 1 = dead refs or malformed block.
Usage: inputs_manifest_check.py [--json]

Example frontmatter:
  inputs:
    reference:
      - memory/SOUL.md
    working:
      - outputs/raw/{persona}/
  stages:
    - id: draft
      does: write the first draft
      out: outputs/raw/
      budget: 4000
"""
import sys
import os
import re
import glob

FM_RE = re.compile(r'^---\n(.*?)\n---', re.DOTALL)
SECTION_RE = re.compile(r'^(reference|working):\s*(#.*)?$')
ITEM_RE = re.compile(r'^-\s+(.+?)\s*(?:#.*)?$')
KV_RE = re.compile(r'^(\w+):\s*(.*)$')
BUDGET_MIN, BUDGET_MAX = 2000, 8000


def repo_root():
    if os.environ.get("AGENT_ROOT"):
        return os.environ["AGENT_ROOT"]
    d = os.path.dirname(os.path.abspath(__file__))   # .../scripts/pipeline
    return os.path.dirname(os.path.dirname(d))        # repo root


def extract_block(fm, key):
    """Isolate a top-level `<key>:` sub-block from frontmatter so an unrelated
    field (e.g. a description containing a colon) can't affect parsing."""
    hdr = re.compile(r'^' + re.escape(key) + r':\s*(#.*)?$')
    out = []
    capturing = False
    for ln in fm.split('\n'):
        if not capturing and hdr.match(ln):
            capturing = True
            continue
        if capturing:
            if ln and not ln[0].isspace():   # next top-level key ends the block
                break
            out.append(ln)
    return out if capturing else None


def parse_inputs_block(lines):
    """Parse the fixed 2-level inputs shape into {section: [paths]}."""
    result = {}
    section = None
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        m = SECTION_RE.match(s)
        if m:
            section = m.group(1)
            result.setdefault(section, [])
            continue
        m = ITEM_RE.match(s)
        if m and section is not None:
            result[section].append(m.group(1).strip().strip('"\''))
    return result


def parse_stages_block(lines):
    """Parse a block-style list of stage dicts into [{id,does,out,budget}, ...]."""
    stages = []
    cur = None
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        m = re.match(r'^-\s+(.*)$', s)
        if m:                       # new stage item
            if cur is not None:
                stages.append(cur)
            cur = {}
            kv = KV_RE.match(m.group(1))
            if kv:
                cur[kv.group(1)] = kv.group(2).strip().strip('"\'')
            continue
        kv = KV_RE.match(s)
        if kv and cur is not None:
            cur[kv.group(1)] = kv.group(2).strip().strip('"\'')
    if cur is not None:
        stages.append(cur)
    return stages


def static_prefix(p):
    """For a templated/glob path return the static dir prefix before the first
    {var}, * or date-placeholder segment; None if the path is fully literal."""
    keep = []
    for seg in p.split('/'):
        if '{' in seg or '*' in seg or re.search(r'YYYY|MM|DD', seg):
            break
        keep.append(seg)
    sp = '/'.join(keep)
    return sp if sp and sp != p else None


def resolves(root, p):
    if os.path.exists(os.path.join(root, p)):
        return True
    sp = static_prefix(p)
    return bool(sp) and os.path.isdir(os.path.join(root, sp))


def main():
    root = repo_root()
    files = sorted(set(
        glob.glob(os.path.join(root, 'skills', '*.md')) +
        glob.glob(os.path.join(root, 'skills', '*', 'SKILL.md')) +
        glob.glob(os.path.join(root, 'skills-shared', '*.md')) +
        glob.glob(os.path.join(root, 'skills-shared', '*', 'SKILL.md'))))
    manifests = 0
    dead = []        # (skill, section, path) -> exit 1
    malformed = []   # (skill, error)         -> exit 1
    warns = []       # (skill, warning)       -> advisory, exit 0

    for sf in files:
        text = open(sf, encoding='utf-8', errors='replace').read()
        m = FM_RE.match(text)
        if not m:
            continue
        fm = m.group(1)
        has_inputs = 'inputs:' in fm
        has_stages = 'stages:' in fm
        if not (has_inputs or has_stages):
            continue
        rel = os.path.relpath(sf, root)
        counted = False

        if has_inputs:
            block = extract_block(fm, 'inputs')
            if block is not None:
                inp = parse_inputs_block(block)
                if not inp or not any(inp.get(s) for s in ('reference', 'working')):
                    malformed.append((rel, "inputs: declared but no reference/working paths parsed"))
                else:
                    counted = True
                    for section in ('reference', 'working'):
                        for p in inp.get(section, []):
                            if not resolves(root, str(p)):
                                dead.append((rel, section, p))

        if has_stages:
            sblock = extract_block(fm, 'stages')
            if sblock is not None:
                stages = parse_stages_block(sblock)
                if not stages:
                    malformed.append((rel, "stages: declared but no stages parsed"))
                else:
                    counted = True
                    for i, st in enumerate(stages):
                        sid = st.get('id', "#%d" % i)
                        if 'id' not in st or 'does' not in st:
                            warns.append((rel, "stage %s: missing id/does" % sid))
                        outp = st.get('out')
                        if outp and not resolves(root, outp):
                            dead.append((rel, "stage:%s" % sid, outp))
                        b = st.get('budget')
                        if b is None:
                            warns.append((rel, "stage %s: no budget (Lift 3 advisory)" % sid))
                        else:
                            try:
                                bi = int(b)
                                if bi > BUDGET_MAX:
                                    warns.append((rel, "stage %s: budget %d > %d (ICM degradation line)" % (sid, bi, BUDGET_MAX)))
                                elif bi < BUDGET_MIN:
                                    warns.append((rel, "stage %s: budget %d < %d (unusually small)" % (sid, bi, BUDGET_MIN)))
                            except (ValueError, TypeError):
                                warns.append((rel, "stage %s: budget %r not an int" % (sid, b)))

        if counted:
            manifests += 1

    rc = 1 if (dead or malformed) else 0

    if '--json' in sys.argv:
        import json
        print(json.dumps({
            "manifests": manifests,
            "dead": [{"skill": s, "section": sec, "path": p} for s, sec, p in dead],
            "parse_errors": [{"skill": s, "error": e} for s, e in malformed],
            "warnings": [{"skill": s, "warning": w} for s, w in warns],
        }))
        return rc

    if warns:
        print("ADVISORY: %d warning(s):" % len(warns))
        for rel, w in warns:
            print("  %s: %s" % (rel, w))
    if malformed:
        print("MALFORMED: %d block(s):" % len(malformed))
        for rel, e in malformed:
            print("  %s: %s" % (rel, e))
    if dead:
        print("FAIL: %d dead reference(s) across %d manifest(s):" % (len(dead), manifests))
        for rel, section, p in dead:
            print("  %s [%s] -> %s" % (rel, section, p))
    if rc == 0:
        print("OK: %d skill manifest(s) checked, all inputs + stage-outs resolve." % manifests)
    return rc


if __name__ == '__main__':
    sys.exit(main())
