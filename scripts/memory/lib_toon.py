#!/usr/bin/env python3
# lib_toon.py — encode Python objects to TOON (Token-Oriented Object Notation) for LLM prompts.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
TOON (Token-Oriented Object Notation) encoder for LLM prompt construction.

Per https://github.com/toon-format/toon — TOON combines YAML-style indentation
with CSV-style tabular layout for uniform arrays of objects. ~30-60% token
savings on structured data when fed to an LLM as input.

USAGE BOUNDARY (NON-NEGOTIABLE):
TOON encoding happens ONLY at the prompt-build step. Storage files / MCP tool
inputs / runtime scratch files / settings files / config files STAY JSON.
TOON is for "convert-immediately-before-passing-to-the-model" not "rewrite our
schemas."

Stats on a representative 29-object array:
- JSON pretty-printed: ~11KB
- TOON encoded: ~4-5KB
- Token saving: ~55-60% on the structured array section

Spec implemented (subset, sufficient for common use cases):
- Scalar key:value (top-level)
- Uniform array of objects → `name[N]{f1,f2,f3}:\n  v1,v2,v3\n  v1,v2,v3`
- Nested objects → indented key:value tree (YAML-style)
- Falls back to JSON if structure is non-uniform OR encoder hits an edge case

Reference: https://github.com/toon-format/toon (Spec + benchmarks).
"""
from __future__ import annotations
import json
from typing import Any


def _is_uniform_array_of_dicts(arr: list) -> bool:
    """Check if a list is a uniform array of dicts with same key set."""
    if not arr or not isinstance(arr[0], dict):
        return False
    keys = set(arr[0].keys())
    if not keys:
        return False
    for item in arr:
        if not isinstance(item, dict):
            return False
        if set(item.keys()) != keys:
            return False
    return True


def _normalize_array_of_dicts(arr: list) -> list:
    """If arr is an ALMOST-uniform array of dicts (some entries missing some
    keys, but all entries are dicts), fill missing keys with empty string so
    the array becomes uniform for TOON encoding.

    Returns the original arr unchanged if it's not array-of-dicts.
    """
    if not arr or not isinstance(arr[0], dict):
        return arr
    if not all(isinstance(item, dict) for item in arr):
        return arr
    # Compute union of all keys, preserving first-seen order
    seen = []
    seen_set = set()
    for item in arr:
        for k in item.keys():
            if k not in seen_set:
                seen.append(k)
                seen_set.add(k)
    normalized = []
    for item in arr:
        nrow = {k: item.get(k, "") for k in seen}
        normalized.append(nrow)
    return normalized


def _toon_escape(val: Any) -> str:
    """Escape a value for TOON CSV row.

    Rules:
    - None → empty
    - Strings with comma/newline/quote → wrapped in double quotes, internal " doubled
    - Numbers/bools → str(val)
    - Multi-line strings → escape \n as \\n
    """
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val)
    # Replace internal newlines with literal \n for single-line CSV row
    s = s.replace("\n", "\\n").replace("\r", "")
    # Quote if contains comma or quote
    if "," in s or '"' in s or s.startswith(" ") or s.endswith(" "):
        s = '"' + s.replace('"', '""') + '"'
    return s


def to_toon(data: Any, indent: int = 0) -> str:
    """Encode a Python object to TOON.

    Falls back to JSON for shapes TOON doesn't handle well (non-uniform arrays,
    deeply nested heterogeneous structures).
    """
    try:
        return _encode(data, indent)
    except Exception:
        # Safety fallback: any encoder edge case → JSON
        return json.dumps(data, indent=2, default=str)


def _encode(data: Any, indent: int) -> str:
    pad = "  " * indent
    if isinstance(data, dict):
        lines = []
        for key, val in data.items():
            # Try to normalize almost-uniform arrays into uniform shape
            if isinstance(val, list) and val and isinstance(val[0], dict):
                val = _normalize_array_of_dicts(val)
            if isinstance(val, list) and _is_uniform_array_of_dicts(val):
                # CSV-style tabular layout for uniform array
                fields = list(val[0].keys())
                lines.append(f"{pad}{key}[{len(val)}]{{{','.join(fields)}}}:")
                for row in val:
                    cells = [_toon_escape(row.get(f)) for f in fields]
                    lines.append(f"{pad}  {','.join(cells)}")
            elif isinstance(val, list):
                # Non-uniform array → fall back to JSON inline
                lines.append(f"{pad}{key}: {json.dumps(val, default=str)}")
            elif isinstance(val, dict):
                # Nested dict → recurse with indent
                lines.append(f"{pad}{key}:")
                lines.append(_encode(val, indent + 1))
            else:
                lines.append(f"{pad}{key}: {_toon_escape(val)}")
        return "\n".join(lines)
    if isinstance(data, list):
        if _is_uniform_array_of_dicts(data):
            fields = list(data[0].keys())
            out = [f"{pad}[{len(data)}]{{{','.join(fields)}}}:"]
            for row in data:
                cells = [_toon_escape(row.get(f)) for f in fields]
                out.append(f"{pad}  {','.join(cells)}")
            return "\n".join(out)
        return json.dumps(data, indent=2, default=str)
    return _toon_escape(data)


def measure_savings(data: Any) -> dict:
    """Return JSON-vs-TOON size comparison for a given data structure."""
    json_str = json.dumps(data, indent=2, default=str)
    toon_str = to_toon(data)
    json_bytes = len(json_str.encode("utf-8"))
    toon_bytes = len(toon_str.encode("utf-8"))
    saving_pct = (1 - toon_bytes / json_bytes) * 100 if json_bytes > 0 else 0
    # Rough token estimate (1 token ~= 4 chars for English)
    return {
        "json_bytes": json_bytes,
        "toon_bytes": toon_bytes,
        "saving_bytes": json_bytes - toon_bytes,
        "saving_pct": round(saving_pct, 1),
        "json_tokens_est": json_bytes // 4,
        "toon_tokens_est": toon_bytes // 4,
        "tokens_saved_est": (json_bytes - toon_bytes) // 4,
    }


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="JSON → TOON encoder")
    parser.add_argument("input", nargs="?", help="JSON file (or stdin)")
    parser.add_argument("--measure", action="store_true",
                        help="Print JSON-vs-TOON byte/token comparison")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    if args.measure:
        m = measure_savings(data)
        print(json.dumps(m, indent=2))
    else:
        print(to_toon(data))
