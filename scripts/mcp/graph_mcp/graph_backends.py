#!/usr/bin/env python3
# graph_backends.py: page-format backends for the graph MCP server (Logseq graph, Obsidian vault).
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Format backends for scripts/mcp/graph_mcp/server.py.

ONE CORE, TWO FORMATS. The server's tools (read, search, list, query, links, writes, stats,
journal) are format-free. What differs between a Logseq graph and an Obsidian vault is narrow,
and it all lives here:

  question                    Logseq graph                     Obsidian vault
  --------------------------  -------------------------------  ---------------------------------
  where is page "Project/X"?  pages/Project___X.md (flat)      Project/X.md (a real folder)
  what are its properties?    `key:: value` lines              YAML frontmatter between --- lines
  what does it link to?       [[Page]]                         [[Page]], [[Page|alias]],
                                                               [[Page#Heading]], bare basenames
  where is today's note?      journals/YYYY_MM_DD.md           <daily folder>/<daily format>.md

Keeping the differences in one class per format means every safety rule (name validation, the
path jail, size caps, protected namespaces) is written once, in the base class, and both formats
inherit it. A separate Obsidian server would have been a second copy of the jail, which is the
one piece of code that must never drift.

STDLIB ONLY. No YAML library: the frontmatter reader handles the subset vaults actually use
(scalars, inline lists, block lists) and skips the rest. See docs/obsidian.md for the limits.
"""
from __future__ import annotations

import csv
import os
import re
from datetime import date, datetime
from pathlib import Path

MAX_NAME_LEN = 300
MAX_PAGE_BYTES = 1_000_000      # read cap, and the cap on a page's size after a write
MAX_CONTENT_CHARS = 100_000     # create / update payload
MAX_APPEND_CHARS = 50_000       # append payload
MAX_SCAN_FILES = 50_000         # a scan that would read more files than this stops and says so

LINK_RE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
# Never valid in a page name on either backend: path separators other than '/', Windows-reserved
# characters, and NUL. ':' also blocks drive letters.
_BAD_CHARS = set('\\:*?"<>|')
_DATE_RE = re.compile(r"^\d{4}[-_]\d{2}[-_]\d{2}$")


class Refused(PermissionError):
    """A request the safety rules declined. Distinct from 'not found' on purpose."""


def _inside(p: Path, base: Path) -> bool:
    try:
        return p.is_relative_to(base)
    except AttributeError:  # Python 3.8
        return p == base or str(p).startswith(str(base) + os.sep)


def parse_date(raw: str) -> date:
    """Strict YYYY-MM-DD or YYYY_MM_DD. Anything else is refused before it reaches a path."""
    s = (raw or "").strip()
    if not _DATE_RE.match(s):
        raise Refused(f"date must be YYYY-MM-DD or YYYY_MM_DD, got {raw!r}")
    try:
        return datetime.strptime(s.replace("_", "-"), "%Y-%m-%d").date()
    except ValueError as e:
        raise Refused(f"not a real date: {raw!r} ({e})")


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def parse_frontmatter(text: str) -> dict:
    """Read YAML frontmatter, the subset vaults use. Stdlib only.

    Supported: `key: value`, `key: [a, b]`, and block lists (`key:` then `  - a` lines).
    Not supported, and skipped rather than guessed: nested maps, multi-line scalars (| and >),
    anchors. A key whose value is unsupported is left out instead of holding half a value.
    """
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    body = []
    for line in lines[1:]:
        if line.strip() in ("---", "..."):
            break
        body.append(line)
    else:
        return {}  # no closing fence: not frontmatter

    props: dict = {}
    key = None
    block_keys: set = set()
    for line in body:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s*-\s+(.*)$", line) or re.match(r"^\s*-$", line)
        if item and key in block_keys:
            val = _unquote(item.group(1)) if item.groups() else ""
            if val:
                props[key].append(val)
            continue
        km = re.match(r"^([A-Za-z0-9_][\w\- .]*?)\s*:(?:\s+(.*))?$", line)
        if km and not line[0].isspace():
            key = km.group(1).strip()
            val = (km.group(2) or "").strip()
            if val == "":
                props[key] = []
                block_keys.add(key)
            elif val in ("|", ">", "|-", ">-", "|+", ">+") or val.startswith("&"):
                props.pop(key, None)
                key = None
            elif val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                row = next(csv.reader([inner], skipinitialspace=True)) if inner else []
                props[key] = [_unquote(x) for x in row if x.strip()]
                key = None
            else:
                props[key] = _unquote(val)
                key = None
            continue
        # Indented non-list line: a nested map or a continuation. Unsupported, drop the key.
        if key in block_keys and not props.get(key):
            props.pop(key, None)
            block_keys.discard(key)
        key = None
    for k in list(block_keys):
        if k in props and props[k] == []:
            props[k] = ""  # `key:` with nothing under it is an empty value, not an empty list
    return props


def parse_logseq_properties(text: str) -> dict:
    """Logseq `key:: value` lines, anywhere on the page (a bullet prefix is allowed)."""
    props = {}
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        m = re.match(r"^([a-zA-Z0-9_-]+)::\s*(.*)$", line)
        if m and m.group(1) not in ("template", "template-including-parent"):
            props[m.group(1)] = m.group(2).strip()
    return props


class Backend:
    """Shared rules. Subclasses map names to files and parse their format."""

    fmt = "base"
    extra_bad_chars: set = set()

    def __init__(self, root: Path, registry: dict):
        self.root = Path(root).resolve()
        self.registry = registry  # {"namespaces": {...}, "domains": {...}}
        self.namespaces = registry.get("namespaces", {})
        self._ns_fold = {k.casefold(): k for k in self.namespaces}

    # --- names -----------------------------------------------------------------------------
    def validate_name(self, name) -> str:
        if not isinstance(name, str):
            raise ValueError("page_name must be a string")
        n = name.strip()
        if not n:
            raise ValueError("page_name is empty")
        if len(n) > MAX_NAME_LEN:
            raise ValueError(f"page_name is {len(n)} characters, over the {MAX_NAME_LEN} limit")
        if _CTRL_RE.search(n):
            raise Refused("page_name contains control characters")
        bad = (_BAD_CHARS | self.extra_bad_chars) & set(n)
        if bad:
            raise Refused(f"characters not allowed in a {self.fmt} page name: {''.join(sorted(bad))}")
        if n.startswith("/") or n.endswith("/"):
            raise Refused("page_name may not start or end with '/' (absolute paths are refused)")
        for seg in n.split("/"):
            if not seg.strip():
                raise Refused("page_name has an empty segment ('//')")
            if seg.strip() in (".", ".."):
                raise Refused("page_name may not contain '.' or '..' segments")
            if seg.startswith("."):
                raise Refused("page_name segments may not start with '.' (hidden files and folders)")
            if seg != seg.strip():
                raise Refused("page_name segments may not start or end with a space")
        if n.lower().endswith(".md"):
            raise Refused("page_name is a name, not a filename: drop the .md")
        return n

    def namespace_of(self, name: str):
        """Longest registry namespace that prefixes the name, compared case-folded."""
        f = name.casefold()
        for k in sorted(self._ns_fold, key=len, reverse=True):
            if f.startswith(k + "/"):
                return self._ns_fold[k]
        return None

    def canonical_namespace(self, ns: str):
        return self._ns_fold.get((ns or "").strip().strip("/").casefold())

    def is_protected(self, name: str) -> bool:
        """A page is protected if it sits in a protected namespace OR is named exactly as one."""
        ns = self.namespace_of(name)
        if ns and self.namespaces[ns].get("protected"):
            return True
        exact = self._ns_fold.get(name.casefold())
        return bool(exact and self.namespaces[exact].get("protected"))

    # --- paths -----------------------------------------------------------------------------
    def jail(self, p: Path, base: Path = None) -> Path:
        """Resolve first, judge second: symlinks and '..' are decided by where the path lands."""
        base = (base or self.root).resolve()
        rp = p.resolve()
        if not _inside(rp, base):
            raise Refused(f"path escapes the {self.fmt} root")
        rel = rp.relative_to(base).parts
        if any(part.startswith(".") for part in rel):
            raise Refused("hidden files and folders (.obsidian, .trash, .git, ...) are off limits")
        return rp

    def raw_path(self, name: str) -> Path:
        """Where the page file sits before symlinks are resolved."""
        raise NotImplementedError

    def page_path(self, name: str) -> Path:
        """The resolved, jailed path. Every read and write goes through this."""
        return self.jail(self.raw_path(name), self._jail_base())

    def _jail_base(self) -> Path:
        return self.root

    def name_for_path(self, rp: Path) -> str:
        """The page name a resolved file answers to. Protection is checked on this too, so a
        symlinked folder or an alias spelling cannot reach a protected page by another name."""
        raise NotImplementedError

    def iter_pages(self):
        """Yield (page_name, Path). Never yields a file that resolves outside the root."""
        raise NotImplementedError

    def properties(self, text: str) -> dict:
        raise NotImplementedError

    def link_target(self, raw: str) -> str:
        return raw.strip()

    def links(self, text: str) -> list:
        out = []
        for m in LINK_RE.finditer(text):
            t = self.link_target(m.group(1))
            if t and t not in out:
                out.append(t)
        return out

    def link_points_to(self, target: str, page_name: str, unique_basenames: set) -> bool:
        return target.casefold() == page_name.casefold()

    def journal_path(self, d: date) -> Path:
        raise NotImplementedError

    def naming_rules(self) -> dict:
        raise NotImplementedError

    def journal_count(self) -> int:
        return 0


class LogseqBackend(Backend):
    """Logseq graph: <root>/pages/Namespace___Page.md and <root>/journals/YYYY_MM_DD.md."""

    fmt = "logseq"
    NS_SEP = "___"

    def __init__(self, root: Path, registry: dict):
        super().__init__(root, registry)
        self.pages_dir = self.root / "pages"
        self.journals_dir = self.root / "journals"

    def validate_name(self, name) -> str:
        n = super().validate_name(name)
        # The filename encodes '/' as '___', and older graphs (and the recall indexer) also read
        # '__' as '/'. A name carrying either would alias another namespace's file, which is how
        # 'Reference___Policy' could slip past a check that looked for 'Reference/'.
        if "__" in n:
            raise Refused("page_name may not contain '__' (it encodes '/' in Logseq filenames)")
        return n

    def raw_path(self, name: str) -> Path:
        fname = name.replace("/", self.NS_SEP) + ".md"
        if len(fname.encode("utf-8")) > 255:
            raise Refused("page_name is too long for a single filename")
        return self.pages_dir / fname

    def _jail_base(self) -> Path:
        return self.pages_dir

    def name_for_path(self, rp: Path) -> str:
        return rp.stem.replace(self.NS_SEP, "/")

    def iter_pages(self):
        if not self.pages_dir.is_dir():
            return
        n = 0
        for f in sorted(self.pages_dir.iterdir()):
            if f.suffix != ".md" or f.name.startswith("."):
                continue
            try:
                rp = self.jail(f, self.pages_dir)
            except Refused:
                continue
            if not rp.is_file():
                continue
            n += 1
            if n > MAX_SCAN_FILES:
                raise RuntimeError(f"graph has more than {MAX_SCAN_FILES} pages; raise MAX_SCAN_FILES deliberately")
            yield f.stem.replace(self.NS_SEP, "/"), rp

    def properties(self, text: str) -> dict:
        return parse_logseq_properties(text)

    def journal_path(self, d: date) -> Path:
        return self.jail(self.journals_dir / f"{d.strftime('%Y_%m_%d')}.md", self.journals_dir)

    def journal_count(self) -> int:
        return len(list(self.journals_dir.glob("*.md"))) if self.journals_dir.is_dir() else 0

    def naming_rules(self) -> dict:
        return {
            "separator": "'/' builds the namespace: Project/Example-Name -> pages/Project___Example-Name.md",
            "word_separator": "hyphens, not spaces (spaces work but fragment links)",
            "dates": "ISO in the instance name, e.g. Meeting/2026-01-15-Kickoff",
            "refused": "'..', leading '/', '__', '\\', ':', '*', '?', '\"', '<', '>', '|', control characters",
        }


class ObsidianBackend(Backend):
    """Obsidian vault: '/' in a page name is a real folder; properties are YAML frontmatter."""

    fmt = "obsidian"
    # Obsidian itself refuses these in a note name; '[' and ']' would also break a wikilink.
    extra_bad_chars = set("#^[]")

    def __init__(self, root: Path, registry: dict, daily_folder: str = "", daily_format: str = "%Y-%m-%d"):
        super().__init__(root, registry)
        self.daily_folder = (daily_folder or "").strip().strip("/")
        self.daily_format = daily_format or "%Y-%m-%d"
        if self.daily_folder:
            self.validate_name(self.daily_folder)  # same rules: no '..', no hidden, no absolute
        if "/" in self.daily_format or ".." in self.daily_format:
            raise Refused("daily note format may not contain '/' or '..'")
        # Optional per-namespace folder override: {"Person": {"obsidian_folder": "People"}}.
        self._ns_to_folder = {}
        for ns, info in self.namespaces.items():
            folder = (info.get("obsidian_folder") or "").strip().strip("/")
            if folder:
                self.validate_name(folder)
                if folder.casefold() != ns.casefold() and self._dir_exists_casefold(ns):
                    # Both folders would answer to "<ns>/Name". Refuse to guess which one wins.
                    raise Refused(f"namespace {ns!r} maps to folder {folder!r}, but a folder named "
                                  f"{ns!r} also exists in the vault. Rename one of them.")
                self._ns_to_folder[ns] = folder

    def _dir_exists_casefold(self, rel: str) -> bool:
        cur = self.root
        for seg in rel.split("/"):
            try:
                hit = [d for d in cur.iterdir() if d.is_dir() and d.name.casefold() == seg.casefold()]
            except OSError:
                return False
            if not hit:
                return False
            cur = hit[0]
        return True

    def namespace_of(self, name: str):
        # A folder alias ("People/Jane") is the same page as its namespace form ("Person/Jane"),
        # so it must get the same namespace, and the same protection.
        return super().namespace_of(self._name(name))

    def is_protected(self, name: str) -> bool:
        return super().is_protected(self._name(name))

    def _rel(self, name: str) -> str:
        name = self._name(name)
        ns = super().namespace_of(name)
        if ns and ns in self._ns_to_folder:
            return self._ns_to_folder[ns] + name[len(ns):]
        return name

    def _name(self, rel: str) -> str:
        f = rel.casefold()
        for ns, folder in sorted(self._ns_to_folder.items(), key=lambda kv: len(kv[1]), reverse=True):
            if f.startswith(folder.casefold() + "/"):
                return ns + rel[len(folder):]
        return rel

    def raw_path(self, name: str) -> Path:
        rel = self._rel(name)
        if any(len(seg.encode("utf-8")) > 250 for seg in rel.split("/")):
            raise Refused("a page_name segment is too long for a filename")
        return self.root / (rel + ".md")

    def name_for_path(self, rp: Path) -> str:
        return self._name(rp.relative_to(self.root).as_posix()[:-3])

    def iter_pages(self):
        n = 0
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fn in sorted(filenames):
                if not fn.endswith(".md") or fn.startswith("."):
                    continue
                f = Path(dirpath) / fn
                try:
                    rp = self.jail(f)
                except Refused:
                    continue
                if not rp.is_file():
                    continue
                n += 1
                if n > MAX_SCAN_FILES:
                    raise RuntimeError(f"vault has more than {MAX_SCAN_FILES} notes; raise MAX_SCAN_FILES deliberately")
                rel = f.relative_to(self.root).as_posix()[:-3]
                yield self._name(rel), rp

    def properties(self, text: str) -> dict:
        return parse_frontmatter(text)

    def link_target(self, raw: str) -> str:
        t = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if t.lower().endswith(".md"):
            t = t[:-3]
        return t

    def link_points_to(self, target: str, page_name: str, unique_basenames: set) -> bool:
        t = target.casefold()
        if t == page_name.casefold() or t == self._rel(page_name).casefold():
            return True
        base = page_name.rsplit("/", 1)[-1].casefold()
        # A bare [[Name]] resolves by basename, the way Obsidian does, but only when exactly one
        # note in the vault has that basename. Ambiguous bare links are reported, not guessed.
        return "/" not in t and t == base and base in unique_basenames

    def journal_path(self, d: date) -> Path:
        fname = d.strftime(self.daily_format) + ".md"
        folder = self.root / self.daily_folder if self.daily_folder else self.root
        return self.jail(folder / fname)

    def journal_count(self) -> int:
        folder = self.root / self.daily_folder if self.daily_folder else self.root
        if not folder.is_dir():
            return 0
        n = 0
        for f in folder.glob("*.md"):
            try:
                datetime.strptime(f.stem, self.daily_format)
                n += 1
            except ValueError:
                continue
        return n

    def naming_rules(self) -> dict:
        return {
            "separator": "'/' is a folder: Project/Example Name -> Project/Example Name.md",
            "word_separator": "spaces are fine, Obsidian titles are file names",
            "links": "[[Name]], [[Folder/Name]], [[Name|alias]] and [[Name#Heading]] all count as links to Name",
            "daily_notes": f"{self.daily_folder or '<vault root>'}/{self.daily_format}.md",
            "refused": "'..', leading '/', hidden segments (.obsidian), '#', '^', '[', ']', '|', '\\', ':', '*', '?', '\"', '<', '>'",
        }
