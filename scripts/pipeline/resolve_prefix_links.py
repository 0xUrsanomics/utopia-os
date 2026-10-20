#!/usr/bin/env python3
# resolve_prefix_links.py: repair truncated wikilinks only when exactly one page matches the prefix.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Repair namespaced cross-links that a harvester wrote with the page name cut short.

Why: harvesters that write graph pages often have the model compose [[Signal/<slug>]] links from
memory. On long slugs (100+ characters is common for dated news slugs) it sometimes drops the tail,
e.g. [[Signal/2026-10-14-acme-launches-widget-vaults-for-small-al]] for a page whose real name
continues "...-allocators-in-three-regions". The link is then dead.

Rule, deliberately narrow: a [[<NS>/X]] link is rewritten only when
  - no page named <NS>/X exists,
  - X is at least MIN_PREFIX characters (short stems like a first name are ambiguous, never touched),
  - exactly ONE existing <NS> page name starts with X (case-insensitive).
Anything else is left alone and reported. Idempotent.

Pages dir: --pages, default $AGENT_GRAPH_DIR/pages (AGENT_GRAPH_DIR default: <root>/knowledge-graph).
Namespace: --namespace, default "Signal". Logseq stores "NS/page" as the file "NS___page.md".

  resolve_prefix_links.py                 fix pages modified in the last 3 days (the harvester hook)
  resolve_prefix_links.py --all           scan every page in the namespace
  resolve_prefix_links.py --dry-run ...   report only
  resolve_prefix_links.py --selftest      fabricated pages in a temp dir
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

_ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
PAGES = Path(os.environ.get("AGENT_GRAPH_DIR", str(_ROOT / "knowledge-graph"))) / "pages"
MIN_PREFIX = 25


def run(pages, ns="Signal", all_pages=False, days=3.0, dry_run=False):
    """Returns (fixed, unresolved)."""
    link = re.compile(r"\[\[(" + re.escape(ns) + r"/[^\]|]+)\]\]")
    pre = f"{ns}___"
    names = [f[:-3] for f in os.listdir(pages) if f.endswith(".md")]
    signal = {n.replace("___", "/").lower(): n.replace("___", "/") for n in names if n.startswith(pre)}
    cutoff = time.time() - days * 86400
    fixed = unresolved = 0
    for n in names:
        if not n.startswith(pre):
            continue
        p = pages / f"{n}.md"
        if not all_pages and p.stat().st_mtime < cutoff:
            continue
        text = p.read_text(errors="ignore")
        if f"[[{ns}/" not in text:
            continue

        def repl(m):
            nonlocal fixed, unresolved
            target = m.group(1).strip()
            low = target.lower()
            if low in signal:
                return m.group(0)
            hits = [v for k, v in signal.items() if k.startswith(low)] if len(target) >= MIN_PREFIX else []
            if len(hits) == 1:
                fixed += 1
                print(f"fix  {n}: {target} -> {hits[0]}")
                return f"[[{hits[0]}]]"
            unresolved += 1
            print(f"skip {n}: {target} ({len(hits)} prefix matches)")
            return m.group(0)

        new = link.sub(repl, text)
        if new != text and not dry_run:
            p.write_text(new)
    return fixed, unresolved


def _selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pages = Path(td)
        full = "2026-10-14-acme-launches-widget-vaults-for-small-allocators-in-three-regions"
        (pages / f"Signal___{full}.md").write_text("body\n")
        (pages / "Signal___2026-10-14-acme-launches-widget-vaults-for-large-funds.md").write_text("body\n")
        (pages / "Signal___2026-10-15-roundup.md").write_text(
            "see [[Signal/2026-10-14-acme-launches-widget-vaults-for-small-al]]\n"   # unique prefix: fix
            "and [[Signal/2026-10-14-acme-launches-widget-vaults-for]]\n"            # two matches: skip
            "and [[Signal/Alice]]\n")                                                # short: skip
        fixed, unresolved = run(pages, all_pages=True)
        text = (pages / "Signal___2026-10-15-roundup.md").read_text()
        ok = fixed == 1 and unresolved == 2 and f"[[Signal/{full}]]" in text
        again = run(pages, all_pages=True)
        ok = ok and again == (0, 2)  # idempotent
    print(f"selftest {'PASS' if ok else 'FAIL'}: fixed={fixed} unresolved={unresolved}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--days", type=float, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pages", default=str(PAGES))
    ap.add_argument("--namespace", default="Signal")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    pages = Path(a.pages)
    if not pages.is_dir():
        print(f"resolve_prefix_links: no pages dir at {pages} (set --pages or AGENT_GRAPH_DIR)", file=sys.stderr)
        return 2
    fixed, unresolved = run(pages, a.namespace, a.all, a.days, a.dry_run)
    print(f"resolve_prefix_links: {fixed} fixed, {unresolved} dead links left alone{' (dry run)' if a.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
