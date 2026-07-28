#!/usr/bin/env python3
# vector_brain.py — the Tier-3 semantic recall engine (hybrid vector + BM25 search).
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
Vector Brain. hybrid search across ALL knowledge sources.

Indexes:
- Core memory files (memory/*.md)
- Persona memory JSON files (memory/personas/*.json)
- Knowledge-graph pages (e.g. a Logseq/Obsidian export, all namespaces)
- Knowledge files (knowledge/*.md)
- Reviewed outputs (outputs/reviewed/)

Hybrid search:
- Vector: a multilingual embedding model (e.g. BGE-M3, 1024-dim) via LanceDB
- BM25: SQLite FTS5 full-text index
- Fusion: Reciprocal Rank Fusion (RRF) merges both ranked lists
- Chunking: heading-aware splits (markdown ## boundaries + paragraph fallback)

No API calls, no cloud, everything runs locally (GPU if available, else CPU).

Configuration is via environment variables (all optional, sensible defaults):
    AGENT_ROOT              repo root (default: two dirs above this file)
    AGENT_DATA_DIR          where the index + caches live (default: <root>/.data)
    AGENT_GRAPH_DIR         knowledge-graph pages dir (default: <root>/knowledge-graph)
    AGENT_LOG_DIR           recall/latency logs (default: <root>/logs)
    AGENT_AUTO_MEMORY_GLOB  optional external memory glob (default: skipped)
    AGENT_SHARED_CORPUS_GLOB optional multi-agent corpus glob (default: skipped)

Usage:
    vector_brain.py index                          # build/rebuild full + BM25 index
    vector_brain.py index --source memory_core      # index only core memory files
    vector_brain.py search "quarterly planning process"  # hybrid search (default)
    vector_brain.py search "planning process" --mode vector  # vector-only
    vector_brain.py search "api rate limits" --mode bm25     # BM25-only
    vector_brain.py search "who owns the billing integration" --top 10
    vector_brain.py stats                           # show index stats

Output: results ranked by hybrid score (RRF fusion of vector + BM25)
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# Configurable roots. AGENT_ROOT defaults to the repo root (this file lives at
# scripts/memory/vector_brain.py, so parents[2] is the root). Index artifacts,
# knowledge-graph pages, and logs all derive from these so nothing is hardcoded
# to one machine.
ROOT = Path(os.environ.get("AGENT_ROOT", str(Path(__file__).resolve().parents[2])))
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", str(ROOT / ".data")))
GRAPH_DIR = Path(os.environ.get("AGENT_GRAPH_DIR", str(ROOT / "knowledge-graph")))
LOG_DIR = Path(os.environ.get("AGENT_LOG_DIR", str(ROOT / "logs")))
# Optional external agent-memory dir (e.g. a harness-managed memory folder).
# Empty by default = that source is skipped.
AUTO_MEMORY_GLOB = os.environ.get("AGENT_AUTO_MEMORY_GLOB", "")
# Optional shared/multi-agent corpus glob. Empty default = that source is skipped.
SHARED_CORPUS_GLOB = os.environ.get("AGENT_SHARED_CORPUS_GLOB", "")

DB_PATH = DATA_DIR / "vector_brain"
BM25_DB_PATH = DATA_DIR / "vector_brain_fts.db"
RRF_K = 60  # RRF constant. higher = more weight to lower-ranked results

# Project tagging (v2 filesystem-projects layer). Chunks tagged with project
# slug(s) at index time. At search time, if memory/state/active_project.txt is
# non-empty, matching chunks get a soft RRF boost. Boost size tuned to break
# ties without overriding strong matches.
ACTIVE_PROJECT_FILE = ROOT / "memory/state/active_project.txt"
PROJECT_BOOST = 0.003  # ≈ rank-10→rank-7 shuffle in a top-30 RRF list
PROJECT_PATH_RE = re.compile(r"/memory/projects/([^/]+)\.md$")
# Map a persona slug to a default project slug (example; extend as needed).
PERSONA_TO_PROJECT = {
    "coach": "coaching",
}

# Source-path boost (v2.5 layer). Multiplicative weight on RRF score, matched by
# file-path prefix. High-authority curated memory dossiers outrank bulk content
# (mixed-quality graph pages, raw outputs) at equal semantic relevance. Applied
# AFTER project boost so project-tagged items get both bumps.
# Order matters. longest/most-specific prefix wins (first match in list).
# Override via env: AGENT_SOURCE_BOOST="/memory/Context/:1.8,/knowledge-graph/:0.7"
SOURCE_BOOST_PATTERNS: list[tuple[str, float]] = [
    ("/shared-brain/", 1.4),       # Cross-agent findings (shared blackboard, fresh + operational)
    ("/memory/Context/", 1.5),     # Subject dossiers (topics, infra, contacts)
    ("/memory/Infra/", 1.4),       # Component state
    ("/memory/Feedback/", 1.4),    # Behavior rules (durable)
    ("/memory/projects/", 1.4),    # Project files
    ("/memory/personas/", 1.2),    # Persona-specific JSON
    ("/memory/", 1.5),             # Core memory tier (Decisions/Learnings/Preferences/Voice-Profile)
    ("/knowledge/", 1.3),          # Operational knowledge files
    ("/outputs/reviewed/", 1.1),   # Vetted outputs (post-/review)
    ("/knowledge-graph/", 1.0),    # Knowledge-graph baseline (mixed quality)
]
SOURCE_BOOST_DEFAULT = 1.0  # Anything not matched gets neutral weight
# L6 wiring (2026-05-17): confidence / stance as a rank signal.
# Parsed from chunk text at query time (confidence:: lives in the indexed
# body of Learnings/Decisions entries) so NO reindex is needed. Soft + bounded
# so it nudges, never dominates RRF. Chunks with no confidence:: marker (most
# of the corpus: Logseq, Context dossiers, outputs) are untouched (factor 1.0).
CONF_BOOST_K = 0.4          # multiplier slope around the 0.5 neutral midpoint
CONF_FACTOR_MIN = 0.85      # floor for a low-confidence (0.3) entry
CONF_FACTOR_MAX = 1.18      # cap for a high-confidence (0.9) entry
STANCE_SUPERSEDED = 0.60    # demote: entry text says it was superseded
STANCE_REAFFIRMED = 1.06    # small currency boost: reaffirmed / RESOLVED-SHIPPED
# L7 wiring: query-time knowledge-graph expansion.
# DEFAULT-OFF (opt-in --graph-expand). Density was measured before building:
# the indexed corpus (knowledge-graph/pages, ~1.9k pages) was 26% linked,
# 0.77 links/page, tag-hub-dominated. So v1 is the SAFE form: soft-boost
# chunks already in the candidate pool whose page is a 1-hop graph neighbour
# of a retrieved hit (co-citation bump), with tag-hubs excluded + fan-out
# capped so a hub like [[Signal]] (76 inbound) can't flood. v2 (inject
# neighbour chunks NOT in the pool) is intentionally NOT built. it is gated
# on a graph-hygiene densification pass raising real entity-edge density.
GRAPH_BOOST = 1.08          # soft co-citation bump for a graph-neighbour chunk
GRAPH_FANOUT_CAP = 12       # node with > this degree = treated as a hub, skipped
GRAPH_ANCHOR_TOPN = 6       # only the top-N retrieved hits seed graph anchors
BACKLINK_MAP_PATH = DATA_DIR / "backlink_map.json"
# Generic category / structural anchors that are NOT entities. excluded as
# both expansion anchors and pulled neighbours (lowercased compare).
_TAG_HUBS = {
    "signal", "project", "regulation", "macro", "institutional",
    "concept", "network", "person", "intel", "content", "prompt", "daily",
    "routine", "idea", "goal", "learning", "meeting", "prospect", "partner",
}
# L7 source #2: tag/pillar co-citation over a tagged signal/news archive. When
# most pages carry `tags::`/`content-pillar::`, the item-to-item web already
# exists as metadata. ZERO canonical writes. query-time only. default-OFF (same
# --graph-expand gate).
TAG_COCITE_MAP_PATH = DATA_DIR / "tag_cocite_map.json"
TAG_COCITE_MAX_DF = 120   # tag shared by > this many pages = too broad, dropped
                          # (drops macro 460 / regulatory 315 / stablecoin 239;
                          #  keeps discriminating ethereum 105 / governance 94 /
                          #  solana 71). Mirrors GRAPH_FANOUT_CAP hub discipline.
_GENERIC_TAGS = {"signal", "strong", "moderate", "weak", "institutional", ""}
# Model note: MiniLM-L6-v2 (384 dim, CPU) → BGE-M3 (1024 dim, GPU) is a sane
# upgrade path once the corpus crosses ~5K vectors or carries non-English content
# needing proper multilingual handling. BGE-M3: multilingual, 1024-dim, ~2GB
# model, ~30s full reindex on a consumer GPU. Override with EMBEDDING_MODEL env.
# A vector-dimension change forces a full rebuild (384 and 1024 cannot coexist in
# the same LanceDB table).
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")

# Cross-encoder reranker (2026-04-23 upgrade). Opt-in via --rerank flag.
# Runs after RRF fusion, reranks top-20 candidates, keeps top-k.
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
RERANK_CANDIDATES = 20
_rerank_model_cache = None

# Late chunking (2026-04-23 upgrade). Encode full doc once, pool per chunk.
# Docs beyond LATE_CHUNK_MAX_TOKENS fall back to independent chunk encoding.
LATE_CHUNK_ENABLED = False  # 2026-04-23: benchmarked worse than baseline on our corpus (MRR 0.46 vs 0.54). Hurt specific-factual + pronoun categories; helped bilingual + cross-ref. Kept code for future reconsideration. Set True + full reindex to re-enable.
LATE_CHUNK_MAX_TOKENS = 6000
_hf_model_cache = None
_hf_tokenizer_cache = None

# Source directories. All derive from ROOT / GRAPH_DIR so nothing is machine-bound.
SOURCES = {
    "memory_core": {
        "paths": [str(ROOT / "memory/*.md")],
        "type": "markdown",
    },
    "memory_context": {
        "paths": [str(ROOT / "memory/Context/*.md")],
        "type": "markdown",
    },
    "memory_infra": {
        "paths": [str(ROOT / "memory/Infra/*.md")],
        "type": "markdown",
    },
    "memory_feedback": {
        "paths": [str(ROOT / "memory/Feedback/*.md")],
        "type": "markdown",
    },
    "persona_memory": {
        "paths": [str(ROOT / "memory/personas/*.json")],
        "type": "json_entries",
    },
    "knowledge": {
        "paths": [str(ROOT / "knowledge/*.md")],
        "type": "markdown",
    },
    # Knowledge-graph pages (e.g. a Logseq/Obsidian export). Point AGENT_GRAPH_DIR
    # at your graph; the page-name convention (___ / __ encode '/') is Logseq-style.
    "graph": {
        "paths": [str(GRAPH_DIR / "pages/*.md")],
        "type": "logseq_page",
    },
    "outputs": {
        "paths": [str(ROOT / "outputs/reviewed/**/*.md")],
        "type": "markdown",
    },
}
# Optional external agent-memory source (a harness-managed memory folder).
# Enabled only when AGENT_AUTO_MEMORY_GLOB is set.
if AUTO_MEMORY_GLOB:
    SOURCES["auto_memory"] = {"paths": [AUTO_MEMORY_GLOB], "type": "markdown"}
# Optional shared/multi-agent corpus (a cross-agent blackboard). Cross-agent
# findings written to a shared corpus dir. Included in the nightly full reindex so
# findings persist; index-append can add new ones incrementally between rebuilds.
# The path should carry /shared-brain/ so the source-boost surfaces fresh findings.
# Enabled only when AGENT_SHARED_CORPUS_GLOB is set.
if SHARED_CORPUS_GLOB:
    SOURCES["shared"] = {"paths": [SHARED_CORPUS_GLOB], "type": "markdown"}

# Skip patterns
SKIP_PATTERNS = [
    "node_modules", "venv", ".git", "__pycache__",
    "Zone.Identifier", ".archive",
]


def extract_project_tags(filepath: str, content: str) -> str:
    """Determine project tags for a chunk (v2 layer, 2026-04-27).

    Returns comma-separated string of project slugs, or "" if none.

    Logic:
    - Files at memory/projects/<slug>.md self-tag with <slug>
    - Files with `projects: [a, b]` (inline) or block-list YAML frontmatter
      multi-tag with those slugs
    - Otherwise empty string
    """
    tags = []

    m = PROJECT_PATH_RE.search(filepath)
    if m:
        tags.append(m.group(1))

    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        inline = re.search(r"^projects:\s*\[([^\]]*)\]", fm, re.MULTILINE)
        if inline:
            for item in inline.group(1).split(","):
                slug = item.strip().strip('"').strip("'")
                if slug and slug not in tags:
                    tags.append(slug)
        else:
            block = re.search(r"^projects:\s*\n((?:\s+-\s+\S+\s*\n?)+)", fm, re.MULTILINE)
            if block:
                for line in block.group(1).splitlines():
                    item = re.match(r"\s*-\s+(.+)", line)
                    if item:
                        slug = item.group(1).strip().strip('"').strip("'")
                        if slug and slug not in tags:
                            tags.append(slug)

    return ",".join(tags)


def get_active_project() -> str:
    """Read active project slug from state file. Empty = no active project."""
    try:
        return ACTIVE_PROJECT_FILE.read_text().strip()
    except Exception:
        return ""


def apply_project_boost(results: list[dict], active: str) -> list[dict]:
    """Soft-boost RRF scores for chunks tagged with the active project.

    Only fires when active_project.txt is non-empty AND chunks have a project
    field that matches. Re-sorts by boosted score. Marks boosted entries with
    `_project_boost=True` for transparent display.
    """
    if not active or not results:
        return results
    boosted = 0
    for r in results:
        proj = r.get("project", "") or ""
        if proj and active in [p.strip() for p in proj.split(",")]:
            r["rrf_score"] = r.get("rrf_score", 0) + PROJECT_BOOST
            r["_project_boost"] = True
            boosted += 1
    if boosted:
        results.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
    return results


def _resolve_source_boost_patterns() -> list[tuple[str, float]]:
    """Merge default SOURCE_BOOST_PATTERNS with AGENT_SOURCE_BOOST env override.

    Env format: comma-separated `prefix:factor` pairs, e.g.
    `/memory/Context/:1.8,/knowledge-graph/:0.7`. Malformed entries skipped
    silently. Env entries override matching defaults; new entries are prepended
    (so they take precedence).
    """
    patterns = list(SOURCE_BOOST_PATTERNS)
    env_value = os.environ.get("AGENT_SOURCE_BOOST", "")
    if not env_value:
        return patterns
    overrides: list[tuple[str, float]] = []
    for pair in env_value.split(","):
        if ":" not in pair:
            continue
        k, v = pair.rsplit(":", 1)
        try:
            factor = float(v.strip())
            if factor < 0:
                continue
            overrides.append((k.strip(), factor))
        except ValueError:
            continue
    # Replace existing same-prefix entries; prepend new ones
    out: list[tuple[str, float]] = []
    override_keys = {k for k, _ in overrides}
    for k, f in patterns:
        if k in override_keys:
            continue
        out.append((k, f))
    return overrides + out


def _path_boost_factor(path: str, patterns: list[tuple[str, float]]) -> float:
    """Return boost factor for the first matching prefix; default if none."""
    if not path:
        return SOURCE_BOOST_DEFAULT
    for prefix, factor in patterns:
        if prefix in path:
            return factor
    return SOURCE_BOOST_DEFAULT


def apply_source_boost(results: list[dict]) -> list[dict]:
    """Multiplicative boost on RRF scores by file-path prefix.

    Adapted from a graph-brain source-boost pattern. High-authority curated
    memory dossiers (memory/Context/, memory/Infra/, memory/) outrank bulk
    content (mixed-quality graph pages, reviewed outputs) at equal semantic
    relevance.

    Marks boosted entries with `_source_factor=<float>` for transparency.
    Applied AFTER project boost so a project-tagged context dossier gets
    both bumps (project additive + source multiplicative).

    Note: matches on `source` (file-path) field, NOT `source_type` (which
    is the chunk content type: markdown / logseq / json_entries). This is
    because the source taxonomy here is path-based, not type-based.
    """
    if not results:
        return results
    patterns = _resolve_source_boost_patterns()
    bumped = 0
    for r in results:
        path = r.get("source", "") or ""
        factor = _path_boost_factor(path, patterns)
        if factor != 1.0:
            r["rrf_score"] = r.get("rrf_score", 0) * factor
            r["_source_factor"] = factor
            bumped += 1
    if bumped:
        results.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
    return results


_CONF_RE = re.compile(r"confidence::\s*([01](?:\.\d+)?)", re.I)
_SUPERSEDED_RE = re.compile(
    r"superseded by|\bsupersede[sd]?\b|status::\s*superseded|\bSUPERSEDED\b|~~", re.I)
_REAFFIRMED_RE = re.compile(
    r"\*\*reaffirmed|\breaffirmed\b|RESOLVED .*\bSHIPPED\b|\*\*UPDATE[^\n]*\bSHIPPED\b", re.I)


def apply_confidence_boost(results: list[dict]) -> list[dict]:
    """Multiplicative confidence + stance boost on RRF scores (L6).

    The substrate already exists: Learnings/Decisions entries carry inline
    `confidence:: 0.3-0.9` + supersede / reaffirm markers, and those lines are
    in the indexed chunk text. This wires them into the ranker so a
    high-confidence, reaffirmed, non-superseded anchor outranks a stale
    low-confidence one at equal semantic relevance. Parsed at query time, so
    no reindex. Soft + bounded. Chunks with no confidence:: marker are
    untouched (the bulk of the corpus). Applied AFTER source boost, BEFORE
    temporal, so temporal recency still has the final pre-rerank say.

    Marks `_confidence_factor=<float>` for transparent display.
    """
    if not results:
        return results
    bumped = 0
    for r in results:
        text = r.get("text", "") or ""
        factor = 1.0
        m = _CONF_RE.search(text)
        if m:
            try:
                conf = float(m.group(1))
                cf = 1.0 + (conf - 0.5) * CONF_BOOST_K
                factor *= max(CONF_FACTOR_MIN, min(CONF_FACTOR_MAX, cf))
            except ValueError:
                pass
        if _SUPERSEDED_RE.search(text):
            factor *= STANCE_SUPERSEDED
        elif _REAFFIRMED_RE.search(text):
            factor *= STANCE_REAFFIRMED
        if factor != 1.0:
            r["rrf_score"] = r.get("rrf_score", 0) * factor
            r["_confidence_factor"] = round(factor, 3)
            bumped += 1
    if bumped:
        results.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
    return results


_DATE_PAGE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _norm_page(name: str) -> str:
    """Logseq filename/link convention: ___ and __ encode '/'. lowercased key."""
    return name.replace("___", "/").replace("__", "/").strip().lower()


def _is_tag_hub(page: str) -> bool:
    """True if this page is a generic category/date anchor, not an entity."""
    p = page.strip().lower()
    if not p:
        return True
    last = p.split("/")[-1]
    if _DATE_PAGE_RE.match(last) or _DATE_PAGE_RE.match(p):
        return True
    if last in _TAG_HUBS or p in _TAG_HUBS:
        return True
    return False


def _page_name_from_source(path: str) -> str:
    """Recover the logseq page key from an indexed chunk's source filepath."""
    return _norm_page(Path(path).stem) if path else ""


def build_backlink_map(force: bool = False) -> dict[str, list[str]]:
    """Build (and cache) an undirected Logseq backlink adjacency map.

    Scans the indexed logseq glob once, parses [[wikilinks]], builds an
    undirected adjacency keyed by normalized page name. Tag-hub endpoints
    (Signal / Project / dates / namespace words) are excluded at build time
    so they never become expansion anchors or neighbours. Cached to
    BACKLINK_MAP_PATH with a built_at stamp; rebuilt when any source file is
    newer than the cache (or force=True, or cache missing/corrupt).

    L7. Default-OFF feature; this map is the reusable infra. Built knowing
    density may be low on a young graph, so the consumer (apply_graph_expansion)
    is the safe boost-in-pool form.
    """
    try:
        glob_pat = SOURCES["graph"]["paths"][0]
    except (KeyError, IndexError):
        return {}
    base = Path(glob_pat).parent
    files = sorted(base.glob(Path(glob_pat).name)) if base.exists() else []
    if not files:
        return {}

    newest = max((f.stat().st_mtime for f in files), default=0.0)
    if not force and BACKLINK_MAP_PATH.exists():
        try:
            cached = json.loads(BACKLINK_MAP_PATH.read_text())
            if cached.get("built_at", 0) >= newest:
                return cached.get("adj", {})
        except (json.JSONDecodeError, OSError):
            pass  # rebuild on corrupt/unreadable cache

    adj: dict[str, set[str]] = {}
    for f in files:
        src = _norm_page(f.stem)
        if _is_tag_hub(src):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _WIKILINK_RE.finditer(content):
            tgt = _norm_page(m.group(1))
            if not tgt or tgt == src or _is_tag_hub(tgt):
                continue
            adj.setdefault(src, set()).add(tgt)
            adj.setdefault(tgt, set()).add(src)

    out = {k: sorted(v) for k, v in adj.items()}
    try:
        BACKLINK_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        BACKLINK_MAP_PATH.write_text(json.dumps(
            {"built_at": newest, "adj": out, "nodes": len(out)}, indent=0))
    except OSError:
        pass  # cache write best-effort; map still returned in-memory
    return out


_TAGS_RE = re.compile(r"^tags::\s*(.+)$", re.M)
_PILLAR_RE = re.compile(r"^content-pillar::\s*(.+)$", re.M)


def build_tag_cocitation_map(force: bool = False) -> dict:
    """Build (and cache) a tag/pillar co-citation index over the logseq corpus.

    L7 source #2. Reads existing `tags::` + `content-pillar::` metadata (when
    pages have it). Returns {"page2tags": {page: [tags]}, "tag_df": {tag:
    doc_freq}}. Generic structural tags dropped at build time; over-broad tags
    (df > TAG_COCITE_MAX_DF) are kept in the index but filtered at query time so
    the cap stays tunable without a rebuild. ZERO writes to the corpus. Same
    mtime-staleness caching as build_backlink_map.
    """
    try:
        glob_pat = SOURCES["graph"]["paths"][0]
    except (KeyError, IndexError):
        return {"page2tags": {}, "tag_df": {}}
    base = Path(glob_pat).parent
    files = sorted(base.glob(Path(glob_pat).name)) if base.exists() else []
    if not files:
        return {"page2tags": {}, "tag_df": {}}

    newest = max((f.stat().st_mtime for f in files), default=0.0)
    if not force and TAG_COCITE_MAP_PATH.exists():
        try:
            cached = json.loads(TAG_COCITE_MAP_PATH.read_text())
            if cached.get("built_at", 0) >= newest:
                return {"page2tags": cached.get("page2tags", {}),
                        "tag_df": cached.get("tag_df", {})}
        except (json.JSONDecodeError, OSError):
            pass

    page2tags: dict[str, list[str]] = {}
    tag_df: dict[str, int] = {}
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        toks: set[str] = set()
        tm = _TAGS_RE.search(content)
        if tm:
            for t in re.split(r"[\s,]+", tm.group(1)):
                t = t.strip().lstrip("#").lower()
                if t and t not in _GENERIC_TAGS and len(t) > 2:
                    toks.add(t)
        pm = _PILLAR_RE.search(content)
        if pm:
            p = pm.group(1).strip().lower()
            if p and p not in _GENERIC_TAGS:
                toks.add("pillar:" + p)
        if toks:
            key = _norm_page(f.stem)
            page2tags[key] = sorted(toks)
            for t in toks:
                tag_df[t] = tag_df.get(t, 0) + 1

    try:
        TAG_COCITE_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        TAG_COCITE_MAP_PATH.write_text(json.dumps(
            {"built_at": newest, "page2tags": page2tags, "tag_df": tag_df,
             "pages": len(page2tags)}, indent=0))
    except OSError:
        pass
    return {"page2tags": page2tags, "tag_df": tag_df}


def apply_graph_expansion(query: str, results: list[dict]) -> tuple[list[dict], int, int]:
    """Soft co-citation boost (L7 v1, default-OFF, boost-in-pool only,
    ZERO writes). TWO co-citation sources, unioned:
      #1 entity backlinks  . a pooled chunk whose page is a 1-hop
         [[wikilink]] neighbour of a top hit / query-named entity (the
         entity subgraph). over-degree hubs (>GRAPH_FANOUT_CAP) skipped.
      #2 tag/pillar co-citation  . a pooled chunk sharing a DISCRIMINATING
         tag/pillar (df <= TAG_COCITE_MAX_DF) with a top hit (the tagged
         signal/news archive, whose item-to-item web lives in `tags::`
         metadata). over-broad tags filtered so a tag-hub can't flood.
    Does NOT inject chunks absent from the pool (that is v2, gated on
    densification + the A/B eval). Returns (results, n_boosted, n_anchors).
    """
    if not results:
        return results, 0, 0
    adj = build_backlink_map()
    tagmap = build_tag_cocitation_map()
    page2tags = tagmap.get("page2tags", {})
    tag_df = tagmap.get("tag_df", {})
    if not adj and not page2tags:
        return results, 0, 0

    ql = query.lower()
    hit_pages = [_page_name_from_source(r.get("source", ""))
                 for r in results[:GRAPH_ANCHOR_TOPN]]
    hit_pages = [p for p in hit_pages if p]

    # source #1: entity backlink anchors (the entity subgraph)
    anchors: set[str] = set()
    for pg in hit_pages:
        if pg in adj and not _is_tag_hub(pg) and len(adj[pg]) <= GRAPH_FANOUT_CAP:
            anchors.add(pg)
    for key in adj:
        if "/" in key and not _is_tag_hub(key) and key in ql and len(adj[key]) <= GRAPH_FANOUT_CAP:
            anchors.add(key)
    neighbours: set[str] = set()
    for a in anchors:
        for n in adj.get(a, []):
            if not _is_tag_hub(n):
                neighbours.add(n)
    neighbours -= anchors

    # source #2: tag/pillar co-citation (the signal archive). a pooled chunk
    # sharing a DISCRIMINATING tag (df <= cap) with a top hit is a neighbour.
    tag_anchor_pages = [p for p in hit_pages if p in page2tags]
    anchor_tags: set[str] = set()
    for p in tag_anchor_pages:
        for t in page2tags.get(p, []):
            if tag_df.get(t, 0) <= TAG_COCITE_MAX_DF:
                anchor_tags.add(t)
    tag_neighbours: set[str] = set()
    if anchor_tags:
        anchor_set = set(tag_anchor_pages)
        for pg, tags in page2tags.items():
            if pg in anchor_set:
                continue
            if anchor_tags.intersection(tags):
                tag_neighbours.add(pg)

    boost_set = neighbours | tag_neighbours
    n_anchors = len(anchors) + len(tag_anchor_pages)
    if not boost_set:
        return results, 0, n_anchors

    boosted = 0
    for r in results:
        pg = _page_name_from_source(r.get("source", ""))
        if pg and pg in boost_set and not r.get("_graph_factor"):
            r["rrf_score"] = r.get("rrf_score", 0) * GRAPH_BOOST
            r["_graph_factor"] = GRAPH_BOOST
            r["_graph_src"] = "tag" if pg in tag_neighbours and pg not in neighbours else "entity"
            boosted += 1
    if boosted:
        results.sort(key=lambda x: x.get("rrf_score", 0), reverse=True)
    return results, boosted, n_anchors


def attach_provenance(results: list[dict]) -> list[dict]:
    """Bundle existing rank/source fields into a structured `provenance` dict.

    Adds nothing new, just packages the flat fields into a single object so
    downstream callers (skills, scheduled crons) can treat 'where did this come
    from' as one opaque blob. Backward compatible. flat fields stay intact.
    """
    for r in results:
        r["provenance"] = {
            "source": r.get("source", ""),
            "source_type": r.get("source_type", ""),
            "title": r.get("title", ""),
            "chunk_index": r.get("chunk_index", 0),
            "project": r.get("project", "") or None,
            "vector_rank": r.get("_vector_rank"),
            "bm25_rank": r.get("_bm25_rank"),
            "rrf_score": r.get("rrf_score"),
            "rerank_score": r.get("rerank_score"),
            "source_factor": r.get("_source_factor"),
            "project_boost": bool(r.get("_project_boost")),
            "confidence_factor": r.get("_confidence_factor"),
            "graph_factor": r.get("_graph_factor"),
            "graph_src": r.get("_graph_src"),
        }
    return results


# Append-only CHRONOLOGICAL ledgers. Nucleus expansion is HARMFUL here: these files are diaries
# (entry N and entry N+1 are unrelated events from different days), so the "neighbour" chunk is
# noise, not context. Measured 2026-07-17 on the restored brain: dossier hits (e.g. a
# career-exploration entry) got neighbours that CONTINUE the same subject = useful; Learnings.md /
# session-bootstrap.md hits got neighbours about entirely different days = pure token cost.
# Note the subject-grouped view of this same material already exists as Context/Infra dossiers
# (dreaming + /save promote it there), and recall finds those on their own. so skipping diary
# neighbours loses no real context.
APPEND_LOG_BASENAMES = {"Learnings.md", "Decisions.md", "session-bootstrap.md"}


def _is_append_log(source_path: str) -> bool:
    p = Path(source_path or "")
    return p.name in APPEND_LOG_BASENAMES or "journal" in p.name.lower()


def expand_nucleus_window(results: list[dict], window_size: int) -> list[dict]:
    """Per MemMachine §4.6 (arXiv:2604.04853 Apr 2026). Skips append-only chronological ledgers
    (see APPEND_LOG_BASENAMES): adjacency only means "same subject" in topical dossiers, not diaries.

    For each top-k match, pull adjacent chunks (window_size preceding,
    2*window_size following) from the same source file. Solves the
    "semantically similar but dialogue-fragmented" recall failure where the
    actual answer lives in the chunk next to the matched one. Asymmetric
    (more after than before) per the paper's findings.

    Cluster lives on r['_expanded_context'] as a list of
    {chunk_index, text, position} dicts. Default-off via window_size=0 so
    backward compat is preserved for existing recall consumers.
    """
    if not window_size or not results:
        return results
    if not BM25_DB_PATH.exists():
        return results

    conn = sqlite3.connect(str(BM25_DB_PATH))
    c = conn.cursor()

    for r in results:
        source = r.get("source", "")
        chunk_idx = r.get("chunk_index")
        if not source or chunk_idx is None:
            continue
        if _is_append_log(source):
            continue  # diary file: neighbour = an unrelated day, not context

        before_idx = max(0, chunk_idx - window_size)
        after_idx = chunk_idx + 2 * window_size

        try:
            rows = c.execute("""
                SELECT chunk_index, text
                FROM docs
                WHERE source = ? AND chunk_index >= ? AND chunk_index <= ? AND chunk_index != ?
                ORDER BY chunk_index
            """, (source, before_idx, after_idx, chunk_idx)).fetchall()
        except Exception:
            continue

        cluster = []
        for row in rows:
            cluster.append({
                "chunk_index": row[0],
                "text": row[1],
                "position": "before" if row[0] < chunk_idx else "after",
            })
        if cluster:
            r["_expanded_context"] = cluster

    conn.close()
    return results


def load_embedding_model():
    """Load sentence-transformers model. Uses CUDA, then Apple Metal (MPS), else CPU."""
    from sentence_transformers import SentenceTransformer
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu")
    except Exception:
        device = "cpu"
    print(f"Loading embedding model: {EMBEDDING_MODEL} on {device}...")
    model = SentenceTransformer(EMBEDDING_MODEL, device=device)
    print(f"Model loaded on {device}.")
    return model


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 80) -> list[str]:
    """Split text into chunks at semantic boundaries.

    Priority: markdown headings > code fences > paragraph breaks > sentence breaks.
    Heading-aware: each ## section becomes its own chunk (merged if tiny).
    Bumped from 500→800 chars to reduce chunk count while keeping retrieval quality.
    """
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    # Step 1: split on markdown headings (##+ lines)
    heading_pattern = re.compile(r"^(#{1,4}\s+.+)$", re.MULTILINE)
    sections: list[str] = []
    last_end = 0
    for m in heading_pattern.finditer(text):
        # Everything before this heading is a section
        before = text[last_end:m.start()].strip()
        if before:
            sections.append(before)
        last_end = m.start()
    # Trailing content after last heading
    trailing = text[last_end:].strip()
    if trailing:
        sections.append(trailing)

    if not sections:
        sections = [text]

    # Step 2: merge tiny adjacent sections, split oversized ones
    chunks: list[str] = []
    buffer = ""
    for section in sections:
        if len(buffer) + len(section) + 1 <= chunk_size:
            buffer = (buffer + "\n\n" + section).strip() if buffer else section
        else:
            # Flush buffer
            if buffer:
                chunks.append(buffer)
            # If section itself is oversized, sub-split on paragraphs/sentences
            if len(section) > chunk_size:
                chunks.extend(_subsplit(section, chunk_size, overlap))
            else:
                buffer = section
                continue
            buffer = ""
    if buffer:
        chunks.append(buffer)

    return [c for c in chunks if c.strip()]


def _extract_breadcrumb(source_path: str, chunk_text: str) -> str:
    """Build a structural-context breadcrumb prefix to inject before chunk embed.

    Pattern lifted from Proxy-Pointer RAG audit 2026-05-22 (TDS article). Prepending
    file-path + first heading at chunk top to embedding input improves retrieval
    relevance for hierarchical-context queries by ~3-5% on hierarchical-style queries.
    Stored text remains unprefixed — only the embed input gets it.

    Example output: "memory/Context/company-profile > # Pricing"
    """
    parts = []
    # File-path component: keep last 3 path segments to balance specificity vs noise
    if source_path:
        path_segs = [s for s in source_path.replace("\\", "/").split("/") if s]
        if path_segs:
            tail = path_segs[-3:]
            stem = tail[-1].rsplit(".", 1)[0]  # strip .md / .json extension
            tail[-1] = stem
            parts.append(" / ".join(tail))
    # Heading component: grab the first markdown heading line in chunk (if any)
    for line in chunk_text.splitlines()[:5]:  # only scan first 5 lines for perf
        stripped = line.strip()
        if stripped.startswith("#"):
            parts.append(stripped)
            break
    if not parts:
        return ""
    return " > ".join(parts) + " :: "


def _subsplit(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Fallback splitter for oversized sections: paragraph > sentence > hard cut."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Try code fence boundary
            fence = text.rfind("\n```", start + chunk_size // 2, end)
            if fence > start:
                end = fence
            else:
                # Try paragraph break
                para = text.rfind("\n\n", start + chunk_size // 2, end)
                if para > start:
                    end = para
                else:
                    # Try sentence break
                    sent = text.rfind(". ", start + chunk_size // 2, end)
                    if sent > start:
                        end = sent + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else len(text)
    return chunks


def load_hf_model():
    """Lazy-load raw transformers model + tokenizer for token-level outputs.

    Used only by late_chunk_embeddings. sentence-transformers doesn't cleanly
    expose per-token embeddings, so we drop to AutoModel directly.
    """
    global _hf_model_cache, _hf_tokenizer_cache
    if _hf_model_cache is not None:
        return _hf_tokenizer_cache, _hf_model_cache
    from transformers import AutoModel, AutoTokenizer
    import torch
    device = "cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu")
    print(f"Loading HF model for late chunking: {EMBEDDING_MODEL} on {device}...")
    tok = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)
    mdl = AutoModel.from_pretrained(EMBEDDING_MODEL).to(device)
    _hf_tokenizer_cache = tok
    _hf_model_cache = mdl
    return tok, mdl


def late_chunk_embeddings(full_text: str, chunk_boundaries):
    """Encode full_text once, pool token embeddings per chunk via char offsets.

    Returns list of 1024-dim numpy arrays (one per chunk), or None if the doc
    exceeds LATE_CHUNK_MAX_TOKENS (caller falls back to independent encoding).
    """
    import torch

    tok, mdl = load_hf_model()

    try:
        encoded = tok(
            full_text,
            return_tensors="pt",
            return_offsets_mapping=True,
            truncation=False,
            add_special_tokens=True,
        )
    except Exception as e:
        print(f"    late-chunk tokenize failed: {e}")
        return None

    n_tokens = encoded["input_ids"].shape[1]
    if n_tokens > LATE_CHUNK_MAX_TOKENS:
        return None

    device = next(mdl.parameters()).device
    input_ids = encoded["input_ids"].to(device)
    attn = encoded["attention_mask"].to(device)
    offsets = encoded["offset_mapping"][0].tolist()

    with torch.no_grad():
        out = mdl(input_ids=input_ids, attention_mask=attn)
    hidden = out.last_hidden_state[0]  # [n_tokens, 1024]

    chunk_vecs = []
    for ch_start, ch_end in chunk_boundaries:
        tok_idxs = [
            i for i, (s, e) in enumerate(offsets)
            if s < ch_end and e > ch_start and (s, e) != (0, 0)
        ]
        if not tok_idxs:
            chunk_vecs.append(None)
            continue
        sel = hidden[tok_idxs]
        pooled = sel.mean(dim=0)
        pooled = pooled / pooled.norm().clamp(min=1e-9)  # L2 normalize
        chunk_vecs.append(pooled.cpu().numpy())

    return chunk_vecs


def _chunk_with_offsets(content_clean):
    """Compute chunks + (char_start, char_end) offsets for late-chunking support."""
    chunks = chunk_text(content_clean)
    cursor = 0
    out = []
    for i, chunk in enumerate(chunks):
        idx = content_clean.find(chunk, cursor)
        if idx < 0:
            idx = cursor  # fallback. offset unreliable, late-chunk may skip this one
        out.append({"text": chunk, "index": i, "start": idx, "end": idx + len(chunk)})
        cursor = idx + len(chunk)
    return out


def extract_markdown(filepath: str) -> list[dict]:
    """Extract chunks from a markdown file. Tracks offsets for late chunking."""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception:
        try:
            with open(filepath, encoding="utf-8-sig") as f:
                content = f.read()
        except Exception:
            return []

    if not content.strip():
        return []

    title = Path(filepath).stem
    title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    name_match = re.search(r"^name:\s*(.+)", content, re.MULTILINE)
    if name_match:
        title = name_match.group(1).strip()

    project = extract_project_tags(filepath, content)

    content_clean = re.sub(r"^---\n.*?---\n", "", content, flags=re.DOTALL)
    chunk_info = _chunk_with_offsets(content_clean)

    return [
        {
            "text": ci["text"],
            "source": filepath,
            "source_type": "markdown",
            "title": title,
            "chunk_index": ci["index"],
            "project": project,
            "_full_text": content_clean,
            "_char_start": ci["start"],
            "_char_end": ci["end"],
        }
        for ci in chunk_info
    ]


def extract_json_entries(filepath: str) -> list[dict]:
    """Extract entries from persona memory JSON files."""
    try:
        with open(filepath) as f:
            data = json.load(f)
    except Exception:
        return []

    entries = data.get("entries", [])
    persona = Path(filepath).stem
    project = PERSONA_TO_PROJECT.get(persona, "")

    return [
        {
            "text": entry.get("content", ""),
            "source": filepath,
            "source_type": "persona_memory",
            "title": f"{persona}. {entry.get('category', 'unknown')}",
            "chunk_index": i,
            "project": project,
        }
        for i, entry in enumerate(entries)
        if entry.get("content", "").strip()
    ]


def extract_logseq_page(filepath: str) -> list[dict]:
    """Extract chunks from a Logseq page. Tracks offsets for late chunking."""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    if not content.strip():
        return []

    fname = Path(filepath).stem
    page_name = fname.replace("___", "/").replace("__", "/")

    project = extract_project_tags(filepath, content)

    chunk_info = _chunk_with_offsets(content)
    return [
        {
            "text": ci["text"],
            "source": filepath,
            "source_type": "logseq",
            "title": page_name,
            "chunk_index": ci["index"],
            "project": project,
            "_full_text": content,
            "_char_start": ci["start"],
            "_char_end": ci["end"],
        }
        for ci in chunk_info
    ]



# ---------------------------------------------------------------- privacy at INDEX time
# Pattern (from an audited search index): exclude sensitive kinds at WRITE, not at query.
# Filtering at recall is one forgotten flag away from a leak, and every consumer of this
# brain (the recall skill, subagents, cron sessions, other agents) would each have to
# remember. Excluding at write means a sensitive chunk cannot be retrieved by anything, ever.
#
# Scope is deliberately CHUNK-level, not file-level: e.g. memory/projects/example-project.md
# can carry both anchors you want recallable AND operator-flagged non-public material. Dropping
# the file would lose the anchors; dropping the chunk keeps them.
_SENSITIVE_DROPPED: list[tuple[str, int]] = []

SENSITIVE_MARKERS = (
    "SENSITIVE / NON-PUBLIC",
    "do NOT publish",
    "do not publish or cite externally",
    "PRIVATE, do NOT publish",
    "CONFIDENTIAL",
)


def _is_sensitive(doc: dict) -> bool:
    body = doc.get("text") or doc.get("content") or ""
    return any(m.lower() in body.lower() for m in SENSITIVE_MARKERS)


def collect_documents(sources: list[str] | None = None) -> list[dict]:
    """Collect all documents from specified sources."""
    all_docs = []
    _SENSITIVE_DROPPED.clear()
    source_filter = sources or list(SOURCES.keys())

    for source_name in source_filter:
        if source_name not in SOURCES:
            print(f"  Unknown source: {source_name}")
            continue

        source = SOURCES[source_name]
        print(f"  Collecting from: {source_name}...")

        for pattern in source["paths"]:
            files = glob.glob(pattern, recursive=True)
            for filepath in files:
                # Skip unwanted files
                if any(skip in filepath for skip in SKIP_PATTERNS):
                    continue

                if source["type"] == "markdown":
                    docs = extract_markdown(filepath)
                elif source["type"] == "json_entries":
                    docs = extract_json_entries(filepath)
                elif source["type"] == "logseq_page":
                    docs = extract_logseq_page(filepath)
                else:
                    continue

                kept = [d for d in docs if not _is_sensitive(d)]
                dropped = len(docs) - len(kept)
                if dropped:
                    _SENSITIVE_DROPPED.append((filepath, dropped))
                all_docs.extend(kept)

        print(f"    {source_name}: {sum(1 for d in all_docs if source_name in SOURCES and any(p in d.get('source', '') for p in ['memory', 'knowledge', 'logseq', 'output'][0:1]))} chunks")

    if _SENSITIVE_DROPPED:
        tot = sum(n for _, n in _SENSITIVE_DROPPED)
        print(f"  EXCLUDED {tot} sensitive chunk(s) at index time from "
              f"{len(_SENSITIVE_DROPPED)} file(s):")
        for fp, n in _SENSITIVE_DROPPED:
            print(f"    {n}x  {fp.split('/')[-1]}")
    print(f"  Total: {len(all_docs)} chunks")
    return all_docs


def build_index(sources: list[str] | None = None):
    """Build or rebuild the vector index.

    With LATE_CHUNK_ENABLED=True, docs that fit in 6000 tokens get late-chunking
    (full-doc encode, per-chunk pool). Oversized docs fall back to independent
    chunk encoding via sentence-transformers.
    """
    import lancedb
    from collections import defaultdict

    st_model = load_embedding_model()
    docs = collect_documents(sources)

    if not docs:
        print("No documents found to index.")
        return

    print(f"\nGenerating embeddings for {len(docs)} chunks...")
    all_embeddings = [None] * len(docs)
    doc_idx_map = {id(d): i for i, d in enumerate(docs)}

    late_hits = 0
    late_misses = 0
    fallback_docs = []

    if LATE_CHUNK_ENABLED:
        # Group by source file so we can encode each file once
        groups = defaultdict(list)
        for d in docs:
            groups[d.get("source", "")].append(d)

        print(f"  Late chunking: {len(groups)} source files to process...")
        processed = 0
        for source, doc_list in groups.items():
            processed += 1
            if processed % 50 == 0:
                print(f"    {processed}/{len(groups)} files... (late_hits={late_hits}, fallbacks={late_misses})")

            if any("_full_text" not in d for d in doc_list):
                fallback_docs.extend(doc_list)
                continue

            full_text = doc_list[0]["_full_text"]
            boundaries = [(d["_char_start"], d["_char_end"]) for d in doc_list]

            vecs = late_chunk_embeddings(full_text, boundaries)
            if vecs is None:
                fallback_docs.extend(doc_list)
                late_misses += 1
                continue

            for d, v in zip(doc_list, vecs):
                if v is None:
                    fallback_docs.append(d)
                    continue
                all_embeddings[doc_idx_map[id(d)]] = v.tolist()
                late_hits += 1
    else:
        fallback_docs = list(docs)

    # Encode fallback docs with sentence-transformers (independent chunk encoding)
    if fallback_docs:
        print(f"  Late-chunk result: {late_hits} chunks pooled, {late_misses} docs fell back.")
        print(f"  Fallback encoding {len(fallback_docs)} chunks independently...")
        # Breadcrumb-prefix injection: prepend file-path + first heading before embed.
        # Storage unchanged (d["text"] retained as-is for display); only embed input prefixed.
        # Pattern from 2026-05-22 Proxy-Pointer RAG audit. Late-chunk path NOT prefixed
        # because it would shift the char offsets the pooler depends on.
        texts = [_extract_breadcrumb(d.get("source", ""), d["text"]) + d["text"] for d in fallback_docs]
        batch_size = 64
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embs = st_model.encode(batch, show_progress_bar=False, normalize_embeddings=True)
            for j, e in enumerate(embs):
                all_embeddings[doc_idx_map[id(fallback_docs[i + j])]] = e.tolist()

    # Safety check
    missing = [i for i, e in enumerate(all_embeddings) if e is None]
    if missing:
        raise RuntimeError(f"Missing embeddings for {len(missing)} chunks. aborting index build")

    # Build records (strip internal _full_text / _char_* fields from stored data)
    records = []
    for doc, embedding in zip(docs, all_embeddings):
        records.append({
            "text": doc["text"][:2000],
            "source": doc["source"],
            "source_type": doc["source_type"],
            "title": doc["title"],
            "chunk_index": doc["chunk_index"],
            "project": doc.get("project", ""),
            "vector": embedding,
            "indexed_at": datetime.now().isoformat(),
        })

    DB_PATH.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(DB_PATH))
    if sources is None:
        try:
            db.drop_table("brain")
        except Exception:
            pass

    table = db.create_table("brain", records, mode="overwrite")
    print(f"\nVector index built: {len(records)} vectors in {DB_PATH}")
    print(f"  Late-chunked: {late_hits} | fallback encoded: {len(fallback_docs)}")
    print(f"Table: brain ({table.count_rows()} rows)")

    # Build BM25 index from the same docs
    print(f"\nBuilding BM25 index...")
    build_bm25_index(docs)


def build_bm25_index(docs: list[dict]):
    """Build SQLite FTS5 full-text index from the same documents."""
    BM25_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(BM25_DB_PATH))
    c = conn.cursor()

    # Drop and recreate
    c.execute("DROP TABLE IF EXISTS docs_fts")
    c.execute("DROP TABLE IF EXISTS docs")

    # Content table (rowid-based for FTS5 content sync)
    c.execute("""
        CREATE TABLE docs (
            id INTEGER PRIMARY KEY,
            text TEXT,
            source TEXT,
            source_type TEXT,
            title TEXT,
            chunk_index INTEGER,
            project TEXT
        )
    """)

    # FTS5 virtual table. tokenizes text + title for full-text search
    c.execute("""
        CREATE VIRTUAL TABLE docs_fts USING fts5(
            text, title,
            content='docs',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
    """)

    # Insert all docs
    for i, doc in enumerate(docs):
        c.execute(
            "INSERT INTO docs (id, text, source, source_type, title, chunk_index, project) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (i, doc["text"][:2000], doc["source"], doc["source_type"], doc["title"], doc["chunk_index"], doc.get("project", "")),
        )
        c.execute(
            "INSERT INTO docs_fts (rowid, text, title) VALUES (?, ?, ?)",
            (i, doc["text"][:2000], doc["title"]),
        )

    conn.commit()
    count = c.execute("SELECT count(*) FROM docs").fetchone()[0]
    conn.close()
    print(f"BM25 index built: {count} docs in {BM25_DB_PATH}")


def append_documents(filepaths: list[str]) -> int:
    """Incrementally APPEND markdown files to the existing brain + BM25 index.

    The shared-corpus append path. Unlike build_index (full overwrite), this
    opens the live "brain" table and table.add()s new rows, and INSERTs into the
    BM25 docs/docs_fts tables with continuing rowids. Cheap enough for a */30 pass.
    Idempotency is the CALLER's job (drain inbox -> append -> move file out), so a
    given file is only appended once; the nightly full reindex rebuilds from the
    corpus glob and naturally subsumes these rows (no duplication).

    Falls back to a full build_index() if the table doesn't exist yet (cold DB).
    Returns the number of chunks appended.
    """
    import lancedb

    paths = [p for p in filepaths if Path(p).is_file()]
    if not paths:
        print("append: no input files")
        return 0

    docs = []
    _dropped = 0
    for p in paths:
        chunks = extract_markdown(p)
        # Same index-time privacy guard as collect_documents(). This path MUST enforce it too:
        # index-append is the hot path (a shared-corpus indexer can run it every 30 min, and it is
        # what a live session reaches for), so a guard installed only on the full rebuild would be bypassed by
        # exactly the traffic most likely to carry fresh operator-flagged material.
        _before = len(chunks)
        chunks = [d for d in chunks if not _is_sensitive(d)]
        _dropped += _before - len(chunks)
        try:
            content = Path(p).read_text(errors="ignore")
            proj = extract_project_tags(p, content)
        except Exception:
            proj = ""
        for d in chunks:
            d.setdefault("project", proj)
        docs.extend(chunks)
    if not docs:
        print("append: no chunks extracted")
        return 0

    # Cold DB: no table yet -> a full build is correct (and includes the corpus).
    if not DB_PATH.exists():
        print("append: brain table missing -> running full build_index()")
        build_index()
        return len(docs)

    st_model = load_embedding_model()
    # Same breadcrumb-prefix + normalized encode as build_index's fallback path.
    texts = [_extract_breadcrumb(d.get("source", ""), d["text"]) + d["text"] for d in docs]
    embs = st_model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

    records = []
    for d, e in zip(docs, embs):
        records.append({
            "text": d["text"][:2000],
            "source": d["source"],
            "source_type": d["source_type"],
            "title": d["title"],
            "chunk_index": d["chunk_index"],
            "project": d.get("project", ""),
            "vector": e.tolist(),
            "indexed_at": datetime.now().isoformat(),
        })

    db = lancedb.connect(str(DB_PATH))
    table = db.open_table("brain")
    table.add(records)

    # Mirror into BM25 with continuing rowids (FTS5 content table is rowid-synced).
    if BM25_DB_PATH.exists():
        conn = sqlite3.connect(str(BM25_DB_PATH))
        c = conn.cursor()
        base = (c.execute("SELECT COALESCE(MAX(id), -1) FROM docs").fetchone()[0]) + 1
        for i, d in enumerate(docs):
            rid = base + i
            c.execute(
                "INSERT INTO docs (id, text, source, source_type, title, chunk_index, project) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rid, d["text"][:2000], d["source"], d["source_type"], d["title"], d["chunk_index"], d.get("project", "")),
            )
            c.execute(
                "INSERT INTO docs_fts (rowid, text, title) VALUES (?, ?, ?)",
                (rid, d["text"][:2000], d["title"]),
            )
        conn.commit()
        conn.close()

    print(f"append: +{len(records)} chunks from {len(paths)} file(s); brain now {table.count_rows()} rows")
    if _dropped:
        print(f"append: EXCLUDED {_dropped} sensitive chunk(s) at index time")
    return len(records)


def search_bm25(query: str, top_k: int = 30) -> list[dict]:
    """BM25 full-text search via SQLite FTS5."""
    if not BM25_DB_PATH.exists():
        return []

    conn = sqlite3.connect(str(BM25_DB_PATH))
    c = conn.cursor()

    # FTS5 match query. escape special chars, use implicit AND
    # Split query into tokens, wrap each in quotes for exact matching
    tokens = query.split()
    fts_query = " OR ".join(f'"{t}"' for t in tokens if t.strip())

    # Defensive: project column may not exist on legacy indexes (pre-v2).
    has_project = False
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(docs)").fetchall()]
        has_project = "project" in cols
    except Exception:
        pass

    project_col = ", d.project" if has_project else ""
    try:
        rows = c.execute(f"""
            SELECT d.id, d.text, d.source, d.source_type, d.title, d.chunk_index{project_col},
                   bm25(docs_fts, 1.0, 0.5) as rank
            FROM docs_fts
            JOIN docs d ON d.id = docs_fts.rowid
            WHERE docs_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, top_k)).fetchall()
    except Exception:
        conn.close()
        return []

    conn.close()

    results = []
    for row in rows:
        rec = {
            "id": row[0],
            "text": row[1],
            "source": row[2],
            "source_type": row[3],
            "title": row[4],
            "chunk_index": row[5],
        }
        if has_project:
            rec["project"] = row[6] or ""
            rec["bm25_rank"] = -row[7]
        else:
            rec["project"] = ""
            rec["bm25_rank"] = -row[6]
        results.append(rec)
    return results


def search_vector(query: str, model, top_k: int = 30) -> list[dict]:
    """Vector similarity search via LanceDB."""
    import lancedb

    query_embedding = model.encode([query])[0].tolist()

    db = lancedb.connect(str(DB_PATH))
    try:
        table = db.open_table("brain")
    except Exception:
        return []

    results = table.search(query_embedding).limit(top_k).to_list()

    out = []
    for r in results:
        out.append({
            "text": r["text"],
            "source": r["source"],
            "source_type": r["source_type"],
            "title": r["title"],
            "chunk_index": r["chunk_index"],
            "project": r.get("project", "") or "",
            "vector_score": 1 - r.get("_distance", 1),
        })
    return out


def rrf_fuse(vector_results: list[dict], bm25_results: list[dict], top_k: int = 10) -> list[dict]:
    """Reciprocal Rank Fusion. merge two ranked lists into one.

    RRF score = sum over lists of 1/(k + rank), where k=RRF_K (default 60).
    Higher k = more uniform weighting across ranks.
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}

    # Score vector results
    for rank, r in enumerate(vector_results):
        key = f"{r['source']}:{r['chunk_index']}"
        scores[key] = scores.get(key, 0) + 1.0 / (RRF_K + rank + 1)
        if key not in docs:
            docs[key] = r
            docs[key]["_vector_rank"] = rank + 1
            docs[key]["_bm25_rank"] = None

    # Score BM25 results
    for rank, r in enumerate(bm25_results):
        key = f"{r['source']}:{r['chunk_index']}"
        scores[key] = scores.get(key, 0) + 1.0 / (RRF_K + rank + 1)
        if key not in docs:
            docs[key] = r
            docs[key]["_bm25_rank"] = rank + 1
            docs[key]["_vector_rank"] = None
        else:
            docs[key]["_bm25_rank"] = rank + 1

    # Sort by fused score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    results = []
    for key, score in ranked:
        doc = docs[key]
        doc["rrf_score"] = score
        results.append(doc)

    return results


def load_reranker():
    """Lazy-load cross-encoder reranker. Cached as singleton. Fails silently."""
    global _rerank_model_cache
    if _rerank_model_cache is not None:
        return _rerank_model_cache
    try:
        from sentence_transformers import CrossEncoder
        import torch
        device = "cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu")
        print(f"Loading reranker: {RERANKER_MODEL} on {device}...")
        _rerank_model_cache = CrossEncoder(RERANKER_MODEL, device=device, max_length=512)
        print("Reranker loaded.")
        return _rerank_model_cache
    except Exception as e:
        print(f"  ! reranker load failed: {e}. rerank will no-op")
        return None


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Cross-encoder rerank: score (query, doc.text) pairs, return top_k.

    Fails gracefully. if model can't load or scoring errors, returns input
    unchanged so the recall pipeline keeps working.
    """
    if not candidates:
        return candidates
    model = load_reranker()
    if model is None:
        return candidates[:top_k]

    pairs = [(query, c["text"][:1500]) for c in candidates]
    try:
        scores = model.predict(pairs, batch_size=16, show_progress_bar=False)
    except Exception as e:
        print(f"  ! rerank scoring failed: {e}. falling back to RRF order")
        return candidates[:top_k]

    scored = list(zip(candidates, scores))
    scored.sort(key=lambda x: x[1], reverse=True)
    out = []
    for doc, score in scored[:top_k]:
        doc["rerank_score"] = float(score)
        out.append(doc)
    return out


# L4 wiring (2026-05-17): query expansion + intent routing.
# Heuristic only. NO LLM in the recall hot path (keeps recall fast + offline).
# Original query is ALWAYS variant[0]; variants are additive recall, never replace.
_QSTOP = {
    "what", "whats", "what's", "who", "whos", "who's", "when", "where", "why",
    "how", "is", "are", "was", "were", "do", "does", "did", "the", "a", "an",
    "of", "on", "in", "for", "to", "we", "i", "have", "has", "any", "about",
    "me", "find", "show", "tell", "give", "get", "recall", "remember", "know",
    "status", "update",  # generic recall filler, not entity signal
}


def expand_query(query: str) -> list[str]:
    """1 query -> up to 4 deduped variants (original first). Heuristic, no LLM.

    v1: original + keyword-core (stripped of question/stop words, lifts BM25
    recall) + conjunction decomposition (split on and / & / vs / , into
    sub-queries so multi-entity asks hit each entity's chunks). Cap 4.
    """
    variants = [query.strip()]
    seen = {query.strip().lower()}

    def _add(v: str):
        v = " ".join(v.split()).strip()
        if len(v.split()) >= 2 and v.lower() not in seen:
            variants.append(v)
            seen.add(v.lower())

    toks = re.findall(r"[\w'+-]+", query.lower())
    core = [t for t in toks if t not in _QSTOP and len(t) > 1]
    if 2 <= len(core) < len(toks):
        _add(" ".join(core))

    parts = re.split(r"\s+(?:and|&|vs\.?|versus)\s+|\s*[,/]\s*", query, flags=re.I)
    if len(parts) > 1:
        for p in parts:
            _add(p)

    return variants[:4]


def classify_intent(query: str) -> str:
    """Lightweight regex intent. v1 tilts ONLY temporal (reuses existing
    temporal-rerank machinery, no new boost tables = low blast radius).
    person | timeline | howto | concept | default.
    """
    q = query.lower()
    if re.search(r"\b(when|timeline|history|latest|recent|last (time|week|month)|status of|progress|so far|update on)\b", q):
        return "timeline"
    if re.search(r"\b(who|whose|contact|handling|owner|lead on|reach out|intro to)\b", q):
        return "person"
    if re.search(r"\b(how (do|to|can)|steps|procedure|workflow|set up|configure|fix|debug)\b", q):
        return "howto"
    return "concept" if len(query.split()) <= 4 else "default"


def rrf_merge(ranked_lists: list[list[dict]], top_k: int = 20) -> list[dict]:
    """Generic Reciprocal Rank Fusion across N pre-fused per-variant lists.
    Keyed by source:chunk_index. Union recall: a chunk surfacing for several
    query variants accumulates score. Preserves the doc dict (incl
    _vector_rank/_bm25_rank from its first-seen variant fusion).
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}
    for rlist in ranked_lists:
        for rank, r in enumerate(rlist):
            key = f"{r['source']}:{r['chunk_index']}"
            scores[key] = scores.get(key, 0) + 1.0 / (RRF_K + rank + 1)
            if key not in docs:
                docs[key] = r
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    out = []
    for key, score in ranked:
        doc = docs[key]
        doc["rrf_score"] = score
        out.append(doc)
    return out


def search(query: str, top_k: int = 5, mode: str = "hybrid", rerank_enable: bool = False,
           expand_window: int = 0, temporal_enable: bool = False,
           expand_enable: bool = False, confidence_boost_enable: bool = False,
           graph_expand_enable: bool = False):
    """Search across the vector brain.

    Modes:
      hybrid (default): RRF fusion of vector + BM25
      vector. vector similarity only
      bm25. BM25 keyword only

    rerank_enable: when True and mode=="hybrid", runs cross-encoder rerank
    over top-20 RRF candidates before cutting to top_k.

    expand_window: when >0, fetches N preceding + 2N following chunks per match
    from the same source file (MemMachine §4.6 nucleus-cluster pattern).
    Hybrid mode only. Default 0 = no expansion = backward compat preserved.
    """
    import time as _time
    _t0 = _time.perf_counter()
    if mode == "bm25":
        results = search_bm25(query, top_k)
        print(f"\nBM25 Search: \"{query}\"")
        print(f"Results: {len(results)}")
        print("=" * 60)
        for i, r in enumerate(results):
            print(f"\n[{i+1}] BM25 rank: {r['bm25_rank']:.1f} | {r['source_type']} | {r['title']}")
            print(f"    Source: {r['source']}")
            print(f"    {r['text'][:200]}...")
        _log_latency(query, mode, top_k, _t0, results, rerank_enable=False)
        return results

    # Load model for vector search
    model = load_embedding_model()

    if mode == "vector":
        results = search_vector(query, model, top_k)
        print(f"\nVector Search: \"{query}\"")
        print(f"Results: {len(results)}")
        print("=" * 60)
        for i, r in enumerate(results):
            print(f"\n[{i+1}] Score: {r['vector_score']:.3f} | {r['source_type']} | {r['title']}")
            print(f"    Source: {r['source']}")
            print(f"    {r['text'][:200]}...")
        _log_latency(query, mode, top_k, _t0, results, rerank_enable=False)
        return results

    # Intent routing (L4): timeline intent auto-enables temporal-rerank
    # (reuses existing machinery, no new boost tables). Explicit --temporal wins.
    intent = classify_intent(query)
    intent_auto_temporal = False
    if intent == "timeline" and not temporal_enable:
        temporal_enable = True
        intent_auto_temporal = True

    # Candidate pool size: same two values as pre-L4 (zero regression when
    # expand_enable=False, the default + programmatic path).
    pool_k = RERANK_CANDIDATES if rerank_enable else max(top_k * 3, 15)

    if not expand_enable:
        # Hybrid: fetch top-30 from each, fuse with RRF (original path, unchanged)
        vec_results = search_vector(query, model, top_k=30)
        bm25_results = search_bm25(query, top_k=30)
        fused = rrf_fuse(vec_results, bm25_results, top_k=pool_k)
    else:
        # L4: expand to <=4 variants, per-variant hybrid+RRF, then
        # RRF-merge the per-variant pools. Union recall; original is variant[0].
        variants = expand_query(query)
        per_variant = []
        vec_results = bm25_results = []
        for vi, qv in enumerate(variants):
            vr = search_vector(qv, model, top_k=30)
            br = search_bm25(qv, top_k=30)
            if vi == 0:  # original query drives the print counts
                vec_results, bm25_results = vr, br
            per_variant.append(rrf_fuse(vr, br, top_k=pool_k))
        fused = rrf_merge(per_variant, top_k=pool_k)

    active = get_active_project()

    fused = apply_project_boost(fused, active)
    fused = apply_source_boost(fused)
    if confidence_boost_enable:
        fused = apply_confidence_boost(fused)
    graph_boosted = graph_anchors = 0
    if graph_expand_enable:
        fused, graph_boosted, graph_anchors = apply_graph_expansion(query, fused)
    if temporal_enable:
        # Optional sibling module: temporal decay rerank (STATIC/VERSIONED/EVENT
        # doc-kinds). If it isn't present, skip gracefully rather than error, so
        # the recall pipeline keeps working without it.
        try:
            from lib_temporal_rerank import apply_temporal_rerank
            fused = apply_temporal_rerank(fused, score_field="rrf_score")
        except ImportError:
            temporal_enable = intent_auto_temporal = False
    if rerank_enable:
        final = rerank(query, fused, top_k=top_k)
    else:
        final = fused[:top_k]

    final = expand_nucleus_window(final, expand_window)
    final = attach_provenance(final)

    boosted_n = sum(1 for r in final if r.get("_project_boost"))
    src_up = sum(1 for r in final if (r.get("_source_factor") or 1.0) > 1.0)
    src_dn = sum(1 for r in final if 0 < (r.get("_source_factor") or 1.0) < 1.0)
    proj_sfx = f" [📂{active}: {boosted_n} boosted]" if active and boosted_n else (f" [📂{active}: 0 hits]" if active else "")
    src_sfx = ""
    if src_up or src_dn:
        parts = []
        if src_up:
            parts.append(f"⬆ {src_up}")
        if src_dn:
            parts.append(f"⬇ {src_dn}")
        src_sfx = f" [{' / '.join(parts)} src]"
    temporal_sfx = ""
    if temporal_enable:
        kinds = {"STATIC": 0, "VERSIONED": 0, "EVENT": 0}
        for r in final:
            k = r.get("_doc_kind")
            if k in kinds:
                kinds[k] += 1
        temporal_sfx = f" [⏱ S{kinds['STATIC']}/V{kinds['VERSIONED']}/E{kinds['EVENT']}]"
    exp_sfx = f" [⊕expand {len(variants)}q]" if expand_enable else ""
    intent_sfx = f" [🎯{intent}{'+temporal' if intent_auto_temporal else ''}]"
    conf_n = sum(1 for r in final if r.get("_confidence_factor"))
    conf_sfx = f" [★conf {conf_n}]" if conf_n else ""
    graph_sfx = f" [🕸{graph_boosted}/{graph_anchors}a]" if graph_expand_enable and graph_anchors else ""
    print(f"\nHybrid Search: \"{query}\"" + (" [+rerank]" if rerank_enable else "") + exp_sfx + intent_sfx + proj_sfx + src_sfx + conf_sfx + graph_sfx + temporal_sfx)
    print(f"Results: {len(final)} (from {len(vec_results)} vector + {len(bm25_results)} BM25)")
    print("=" * 60)

    for i, r in enumerate(final):
        vr = r.get("_vector_rank", "-")
        br = r.get("_bm25_rank", "-")
        rr_sfx = f" | rerank: {r['rerank_score']:.3f}" if "rerank_score" in r else ""
        rrf_prefix = f"RRF: {r.get('rrf_score', 0):.4f} | " if "rrf_score" in r else ""
        proj_marker = " 📂" if r.get("_project_boost") else ""
        sf = r.get("_source_factor")
        src_marker = f" ×{sf:g}" if sf and sf != 1.0 else ""
        cf = r.get("_confidence_factor")
        conf_marker = f" ★{cf:g}" if cf and cf != 1.0 else ""
        gf = r.get("_graph_factor")
        graph_marker = " 🕸" if gf else ""
        print(f"\n[{i+1}] {rrf_prefix}vec#{vr} bm25#{br}{rr_sfx} | {r['source_type']} | {r['title']}{proj_marker}{src_marker}{conf_marker}{graph_marker}")
        print(f"    Source: {r['source']}")
        print(f"    {r['text'][:200]}...")
        if r.get("_expanded_context"):
            for ctx in r["_expanded_context"]:
                marker = "↑" if ctx["position"] == "before" else "↓"
                print(f"    {marker} chunk#{ctx['chunk_index']}: {ctx['text'][:120]}...")

    _log_recall(query, final, mode)
    _log_latency(query, mode, top_k, _t0, final, rerank_enable=rerank_enable)
    return final


def _log_recall(query: str, results: list[dict], mode: str) -> None:
    """Append one JSONL line per recall call. Feeds downstream usage-signal tooling.

    Best-effort: failures don't block the search. Log path lives under AGENT_LOG_DIR.
    """
    try:
        import json as _json
        from datetime import datetime as _dt
        log_path = LOG_DIR / "vector_brain_recall.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": _dt.utcnow().isoformat() + "Z",
            "query": query,
            "mode": mode,
            "top_sources": [
                {"source": r.get("source", ""), "source_type": r.get("source_type", ""),
                 "title": r.get("title", "")}
                for r in (results or [])[:10]
            ],
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass


def _log_latency(query: str, mode: str, top_k: int, t0: float,
                 results: list[dict], rerank_enable: bool = False) -> None:
    """Append one JSONL line per recall call with timing (retrieval-latency metric).

    Consumed by a latency-digest roll-up (weekly p50/p95/p99). Best-effort:
    failures don't block search.
    """
    try:
        import json as _json
        import time as _time
        from datetime import datetime as _dt
        elapsed_ms = (_time.perf_counter() - t0) * 1000.0
        log_path = LOG_DIR / "vector_brain_latency.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": _dt.utcnow().isoformat() + "Z",
            "mode": mode,
            "top_k": top_k,
            "rerank": rerank_enable,
            "query_chars": len(query or ""),
            "retrieval_ms": round(elapsed_ms, 2),
            "n_results": len(results or []),
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass


def stats():
    """Show index statistics."""
    import lancedb

    if not DB_PATH.exists():
        print("No index found. Run: vector_brain.py index")
        return

    db = lancedb.connect(str(DB_PATH))
    try:
        table = db.open_table("brain")
    except Exception:
        print("Table 'brain' not found.")
        return

    total = table.count_rows()

    # Get source type breakdown
    all_data = table.to_pandas()
    by_type = all_data["source_type"].value_counts().to_dict()

    print(f"\nVector Brain Stats:")
    print(f"  Total vectors: {total}")
    print(f"  DB path: {DB_PATH}")
    print(f"\n  By source type:")
    for stype, count in by_type.items():
        print(f"    {stype}: {count}")

    # Unique sources
    unique_sources = all_data["source"].nunique()
    print(f"\n  Unique source files: {unique_sources}")

    # BM25 stats
    if BM25_DB_PATH.exists():
        conn = sqlite3.connect(str(BM25_DB_PATH))
        bm25_count = conn.execute("SELECT count(*) FROM docs").fetchone()[0]
        conn.close()
        print(f"\n  BM25 index: {bm25_count} docs in {BM25_DB_PATH}")
    else:
        print(f"\n  BM25 index: not built (run index to create)")


_addhoc_model_cache = None


def add_document(text: str, source: str, doc_id: str | None = None,
                 metadata: dict | None = None, update_bm25: bool = True) -> dict:
    """Append a single document to the brain table out-of-band.

    Used by external benchmark scripts (e.g. vector_brain_longmemeval.py) to
    push synthetic / dataset entries without going through the full
    filesystem-walking index path. Loads the embedding model lazily and
    caches it across calls in the same process.

    Returns dict with {"vectors_added": 1, "bm25_added": 0|1, "table_rows": N}.

    Note: this writes directly to the existing "brain" table. Repeated calls
    with the same doc_id will create duplicate rows — caller manages dedup.
    """
    import lancedb

    global _addhoc_model_cache
    if _addhoc_model_cache is None:
        _addhoc_model_cache = load_embedding_model()
    model = _addhoc_model_cache

    if not text or not text.strip():
        raise ValueError("add_document: empty text")

    metadata = metadata or {}
    title = metadata.get("title") or (doc_id or source)
    project = metadata.get("project", "")
    source_type = metadata.get("source_type") or "external"
    chunk_index = int(metadata.get("chunk_index", 0))

    # Embed
    emb = model.encode([text[:8000]], show_progress_bar=False, normalize_embeddings=True)
    vector = emb[0].tolist() if hasattr(emb[0], "tolist") else list(emb[0])

    record = {
        "text": text[:2000],
        "source": source,
        "source_type": source_type,
        "title": title,
        "chunk_index": chunk_index,
        "project": project,
        "vector": vector,
        "indexed_at": datetime.now().isoformat(),
    }

    DB_PATH.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(DB_PATH))
    if "brain" not in db.table_names():
        table = db.create_table("brain", [record])
    else:
        table = db.open_table("brain")
        table.add([record])

    bm25_added = 0
    if update_bm25 and BM25_DB_PATH.exists():
        conn = sqlite3.connect(str(BM25_DB_PATH))
        try:
            cur = conn.execute("SELECT MAX(id) FROM docs")
            next_id = (cur.fetchone()[0] or 0) + 1
            conn.execute(
                "INSERT INTO docs (id, text, source, source_type, title, chunk_index, project) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (next_id, text[:2000], source, source_type, title, chunk_index, project),
            )
            try:
                conn.execute(
                    "INSERT INTO docs_fts (rowid, text, title) VALUES (?, ?, ?)",
                    (next_id, text[:2000], title),
                )
            except sqlite3.OperationalError:
                pass
            conn.commit()
            bm25_added = 1
        finally:
            conn.close()

    return {
        "vectors_added": 1,
        "bm25_added": bm25_added,
        "table_rows": table.count_rows(),
    }


# ---------------------------------------------------------------- MCP server (`serve`)
# The adapter templates advertised a `recall` MCP server and pointed at a `--serve` flag that
# did not exist, so every harness config shipped with a server that fails at launch. This is
# that flag, made real.
#
# TWO THINGS MAKE THIS SAFE TO BOLT ON HERE RATHER THAN IN A SEPARATE FILE. The heavy imports
# (torch, lancedb, sentence_transformers) are already lazy, inside the functions that need
# them, so this module still imports on a bare Python and the server starts and can report a
# missing dependency instead of dying on import. And `search()` already RETURNS its result
# list; it just also prints a human view. Printing is the hazard: stdout is the JSON-RPC
# channel, so a stray print corrupts the stream. Every call below runs inside
# redirect_stdout(stderr), which keeps the human output visible in the server log where it is
# useful and out of the protocol where it is fatal.

MCP_SERVER_NAME = "utopia-recall"
MCP_SERVER_VERSION = "1.0.0"
MCP_DEFAULT_PROTOCOL = "2025-06-18"

MCP_TOOLS = [
    {
        "name": "recall",
        "description": ("Semantic search over the indexed memory corpus. Hybrid vector + BM25 "
                        "by default. Returns the matching chunks with their source paths."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."},
                "top_k": {"type": "integer", "description": "How many results. Default 5."},
                "mode": {"type": "string", "enum": ["hybrid", "vector", "bm25"],
                         "description": "Retrieval mode. Default hybrid."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "recall_stats",
        "description": ("Index statistics: row count and sources. Use it to tell 'the index is "
                        "empty' apart from 'the query matched nothing', which look identical "
                        "from a caller's side."),
        "inputSchema": {"type": "object", "properties": {}},
    },
]

_MCP_DEPS_HINT = ("The recall tier is not installed. It is the one optional dependency group "
                  "in this repo: pip install -r requirements-memory.txt. Everything else in "
                  "Utopia OS runs without it.")


def _mcp_recall(args: dict) -> str:
    import contextlib
    q = (args.get("query") or "").strip()
    if not q:
        raise ValueError("query is empty")
    top_k = int(args.get("top_k") or 5)
    mode = args.get("mode") or "hybrid"
    with contextlib.redirect_stdout(sys.stderr):
        rows = search(q, top_k, mode) or []
    return json.dumps({
        "query": q, "mode": mode, "count": len(rows),
        "results": [{
            "title": r.get("title"),
            "source": r.get("source"),
            "source_type": r.get("source_type"),
            "text": r.get("text", ""),
        } for r in rows],
    }, indent=2, ensure_ascii=False)


def _mcp_stats(_args: dict) -> str:
    import contextlib
    with contextlib.redirect_stdout(sys.stderr):
        s = stats()
    return json.dumps(s if isinstance(s, dict) else {"stats": str(s)},
                      indent=2, ensure_ascii=False, default=str)


_MCP_HANDLERS = {"recall": _mcp_recall, "recall_stats": _mcp_stats}


def mcp_handle(req: dict):
    """Return a response dict, or None for notifications (which must not be answered)."""
    method, req_id = req.get("method"), req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": params.get("protocolVersion") or MCP_DEFAULT_PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION}}}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}
    if method == "tools/call":
        fn = _MCP_HANDLERS.get(params.get("name"))
        if fn is None:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32602, "message": f"unknown tool: {params.get('name')}"}}
        try:
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": fn(params.get("arguments") or {})}]}}
        except ImportError as e:
            # The expected failure, and it must be legible: an agent that gets "No module named
            # lancedb" cannot act, whereas one told which requirements file to install can.
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": f"{_MCP_DEPS_HINT} (underlying: {e})"}],
                "isError": True}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}}
    if req_id is None:
        return None
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def mcp_serve(stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700, "message": "parse error"}}) + "\n")
            stdout.flush()
            continue
        resp = mcp_handle(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


def mcp_selftest() -> int:
    """Protocol-level, and deliberately runs WITHOUT the recall tier installed.

    The point is to prove the server starts and degrades legibly on a bare Python, because
    that is the state every first-time reader is in.
    """
    import io
    checks, failed = [], 0

    def check(label, cond):
        nonlocal failed
        checks.append((label, bool(cond)))
        if not cond:
            failed += 1

    r = mcp_handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2099-01-01"}})
    check("initialize echoes the client protocol version",
          r["result"]["protocolVersion"] == "2099-01-01")
    check("serverInfo names this server",
          r["result"]["serverInfo"]["name"] == MCP_SERVER_NAME)
    check("initialized notification gets no reply",
          mcp_handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)

    r = mcp_handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    check("tools/list returns recall + recall_stats",
          {t["name"] for t in r["result"]["tools"]} == {"recall", "recall_stats"})
    check("every tool has an inputSchema",
          all("inputSchema" in t for t in r["result"]["tools"]))

    r = mcp_handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "nope", "arguments": {}}})
    check("unknown tool is a JSON-RPC error", "error" in r)
    check("unknown method is -32601",
          mcp_handle({"jsonrpc": "2.0", "id": 4, "method": "zzz"})["error"]["code"] == -32601)

    r = mcp_handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                    "params": {"name": "recall", "arguments": {"query": "  "}}})
    check("empty query is rejected before any model load", r["result"].get("isError"))

    r = mcp_handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                    "params": {"name": "recall", "arguments": {"query": "anything"}}})
    txt = r["result"]["content"][0]["text"]
    check("a real call either works or names the requirements file, never a bare traceback",
          (not r["result"].get("isError")) or "requirements-memory.txt" in txt
          or "Error" in txt or "error" in txt)

    out = io.StringIO()
    mcp_serve(io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
                          'not json\n'
                          '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'), out)
    lines = [l for l in out.getvalue().splitlines() if l.strip()]
    check("stdio transport: 2 replies for 3 lines (notification is silent)", len(lines) == 2)
    check("malformed line is a parse error and does not kill the loop",
          json.loads(lines[1])["error"]["code"] == -32700)

    width = max(len(c[0]) for c in checks)
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}", file=sys.stderr)
    print(f"\n{len(checks) - failed}/{len(checks)} passed", file=sys.stderr)
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description="Vector Brain. Semantic Search")
    sub = parser.add_subparsers(dest="command")

    idx = sub.add_parser("index", help="Build/rebuild the vector index")
    idx.add_argument("--source", help="DESTRUCTIVE: rebuild the WHOLE table containing ONLY this source "
                                      "(build_index uses mode='overwrite'). NOT an incremental append. "
                                      "Requires --force. For a normal refresh run plain `index` (all sources).")
    idx.add_argument("--force", action="store_true",
                     help="Required with --source. Acknowledges that --source WIPES every other source "
                          "from the brain (see the 2026-07-13 and 2026-07-17 self-inflicted wipes).")

    sub.add_parser("serve", help="Run as an MCP server over stdio (JSON-RPC). This is the `recall` server the adapter templates point at.")
    sub.add_parser("selftest", help="Protocol selftest for `serve`. No model load, no index needed.")

    srch = sub.add_parser("search", help="Hybrid search (vector + BM25)")
    srch.add_argument("query", help="Search query")
    srch.add_argument("--top", type=int, default=5, help="Number of results")
    srch.add_argument("--mode", choices=["hybrid", "vector", "bm25"], default="hybrid",
                       help="Search mode: hybrid (default), vector, bm25")
    srch.add_argument("--no-rerank", dest="rerank", action="store_false",
                       help="DISABLE cross-encoder rerank. Rerank is default-ON for the recall/CLI "
                            "path (L5 wiring 2026-05-17). Use this to opt out for speed.")
    srch.set_defaults(rerank=True)
    srch.add_argument("--expand-window", type=int, default=0,
                       help="Fetch N preceding + 2N following chunks per match (MemMachine §4.6 nucleus expansion). Hybrid mode only. Default 0 = off.")
    srch.add_argument("--temporal", action="store_true",
                       help="Apply temporal decay rerank (temporal-RAG patterns; requires the optional lib_temporal_rerank module). STATIC files no decay, VERSIONED 90d half-life clamped at 0.5 floor, EVENT 30d half-life full decay. Hybrid mode only.")
    srch.add_argument("--no-expand", dest="expand", action="store_false",
                       help="DISABLE query expansion. Expansion is default-ON for the recall/CLI "
                            "path (L4 wiring 2026-05-17): 1 query -> up to 4 heuristic "
                            "variants, per-variant hybrid+RRF, RRF-merged. Use this for a raw "
                            "single-query search.")
    srch.set_defaults(expand=True)
    srch.add_argument("--no-confidence-boost", dest="confidence_boost", action="store_false",
                       help="DISABLE confidence/stance rank signal. Default-ON for the recall/CLI "
                            "path (L6 wiring 2026-05-17): parses inline confidence:: + "
                            "supersede/reaffirm markers from chunk text, soft-boosts high-confidence "
                            "non-superseded anchors. No reindex. Use this for raw RRF.")
    srch.set_defaults(confidence_boost=True)
    srch.add_argument("--graph-expand", dest="graph_expand", action="store_true",
                       help="ENABLE Logseq backlink co-citation boost (L7, "
                            "DEFAULT-OFF). Soft-boosts pooled chunks whose page is a "
                            "1-hop graph neighbour of a top hit. tag-hubs excluded, "
                            "fan-out capped. opt-in: graph link density is currently "
                            "low (26%%, measured 2026-05-17), so off until densified.")  # %% is REQUIRED: argparse %-formats help text, so a bare % here made `search --help` raise ValueError instead of printing help.
    srch.set_defaults(graph_expand=False)

    sub.add_parser("stats", help="Show index statistics")

    app = sub.add_parser("index-append", help="Incrementally append md files to the live index (shared-corpus path)")
    app.add_argument("--paths", nargs="+", required=True, help="Markdown file paths to append")

    args = parser.parse_args()

    if args.command == "index":
        # GUARD (added 2026-07-17 after the SECOND self-inflicted wipe; first was 2026-07-13).
        # build_index() does create_table(mode="overwrite"): --source rebuilds the WHOLE brain
        # containing ONLY that source, silently destroying every other source. It is NOT an
        # incremental refresh. Fail loud instead of wiping. Use plain `index` (all sources) to
        # refresh, or `index-append --paths ...` to add new docs without a rebuild.
        if args.source and not args.force:
            print("REFUSED: `index --source <x>` is DESTRUCTIVE. It rebuilds the whole brain with ONLY\n"
                  f"         '{args.source}', wiping every other source (this wiped the brain on\n"
                  "         2026-07-13 27133->5373 and again 2026-07-17 18.5k->552).\n"
                  "  To refresh everything:      vector_brain.py index\n"
                  "  To add new docs (safe):     vector_brain.py index-append --paths <file> ...\n"
                  "  If you REALLY want a scoped single-source rebuild: re-run with --force")
            return
        sources = [args.source] if args.source else None
        build_index(sources)
    elif args.command == "index-append":
        append_documents(args.paths)
    elif args.command == "search":
        search(args.query, args.top, args.mode,
               rerank_enable=getattr(args, "rerank", True),
               expand_window=getattr(args, "expand_window", 0),
               temporal_enable=getattr(args, "temporal", False),
               expand_enable=getattr(args, "expand", True),
               confidence_boost_enable=getattr(args, "confidence_boost", True),
               graph_expand_enable=getattr(args, "graph_expand", False))
    elif args.command == "serve":
        mcp_serve()
    elif args.command == "selftest":
        sys.exit(mcp_selftest())
    elif args.command == "stats":
        stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
