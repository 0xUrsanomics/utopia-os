#!/usr/bin/env python3
# label_consensus.py: second-teacher agreement check for training labels.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Second-teacher agreement check for classifier training labels, and the agreed subset to train on.

Why: labels from ONE teacher model carry that teacher's mistakes twice, once into training and once
into scoring, where they count as right. Pattern from two-teacher pseudo-labelling (label with two
teachers from different model families, train only on rows where both agree): disagreement is where
the label is least trustworthy, so it is the first thing to look at and the last thing to train on.

Input: two JSONL label files over the same rows, one per teacher.
    {"id": "row-001", "label": "keep", "text": "optional, kept for the disagreements file"}
A teacher that answered something outside the label set writes "label": null (an abstain).

  label_consensus.py report --a teacher_a.jsonl --b teacher_b.jsonl [--out DIR]
      agreement, Cohen's kappa, confusion table, disagreements.jsonl, agreement.md
  label_consensus.py agreed --a teacher_a.jsonl --b teacher_b.jsonl --out agreed.jsonl
      write only the rows both teachers labelled the same (teacher A's row, unchanged)
  label_consensus.py selftest

Then retrain on agreed.jsonl, score the old and new model on the SAME held-out rows, and compare
them with bench_stats.py paired (a single accuracy number per model is not a comparison).
Exit 1 if the two files share no ids: a report over nothing is not a clean result.
"""
import argparse
import collections
import json
import sys
from pathlib import Path


def load(path):
    rows = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            rows[str(r["id"])] = r
    return rows


def kappa(pairs, labels):
    """Cohen's kappa: agreement corrected for chance (0 = chance, 1 = perfect)."""
    n = len(pairs)
    if not n:
        return 0.0
    po = sum(a == b for a, b in pairs) / n
    ca = collections.Counter(a for a, _ in pairs)
    cb = collections.Counter(b for _, b in pairs)
    pe = sum(ca[lab] * cb[lab] for lab in labels) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def join(a_path, b_path):
    a, b = load(a_path), load(b_path)
    shared = sorted(set(a) & set(b))
    return a, b, shared, sorted(set(a) ^ set(b))


def cmd_report(a_path, b_path, out):
    a, b, ids, unmatched = join(a_path, b_path)
    if not ids:
        print("FAIL: the two label files share no ids; nothing was compared.", file=sys.stderr)
        return 1
    answered = [i for i in ids if a[i].get("label") is not None and b[i].get("label") is not None]
    pairs = [(a[i]["label"], b[i]["label"]) for i in answered]
    labels = sorted({x for p in pairs for x in p})
    agree = sum(x == y for x, y in pairs)
    conf = collections.Counter(pairs)
    lines = [f"# Teacher agreement: {Path(a_path).name} (A) vs {Path(b_path).name} (B)", "",
             f"- shared rows {len(ids)}, abstained (either teacher) {len(ids) - len(answered)}"
             + (f", ids in only one file {len(unmatched)} (excluded)" if unmatched else ""),
             f"- agreement {agree}/{len(answered)} = {100 * agree / max(1, len(answered)):.1f}%",
             f"- Cohen's kappa {kappa(pairs, labels):.3f} (chance-corrected; 0 = chance, 1 = perfect)", "",
             "| A \\ B | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for x in labels:
        lines.append(f"| {x} | " + " | ".join(str(conf[(x, y)]) for y in labels) + " |")
    out.mkdir(parents=True, exist_ok=True)
    dis = [i for i in ids if a[i].get("label") != b[i].get("label")]
    with open(out / "disagreements.jsonl", "w", encoding="utf-8") as f:
        for i in dis:
            f.write(json.dumps({"id": i, "a": a[i].get("label"), "b": b[i].get("label"),
                                "text": str(a[i].get("text", ""))[:500]}, ensure_ascii=False) + "\n")
    lines.append(f"\n- disagreements written: {out / 'disagreements.jsonl'} ({len(dis)}, abstains count as disagree)")
    text = "\n".join(lines)
    (out / "agreement.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def cmd_agreed(a_path, b_path, out):
    a, b, ids, _ = join(a_path, b_path)
    keep = [i for i in ids if a[i].get("label") is not None and a[i].get("label") == b[i].get("label")]
    if not ids:
        print("FAIL: the two label files share no ids; nothing was compared.", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for i in keep:
            f.write(json.dumps(a[i], ensure_ascii=False) + "\n")
    print(f"agreed rows: {len(keep)} of {len(ids)} shared, written to {out}")
    return 0


def selftest():
    ok = True
    k_same = kappa([("a", "a"), ("b", "b")] * 10, ["a", "b"])
    k_rand = kappa([("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")] * 10, ["a", "b"])
    ok &= abs(k_same - 1) < 1e-9 and abs(k_rand) < 1e-9
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "a.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"id": 1, "label": "keep"}, {"id": 2, "label": "skip"}, {"id": 3, "label": "keep"}]) + "\n")
    (d / "b.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"id": 1, "label": "keep"}, {"id": 2, "label": "keep"}, {"id": 3, "label": None}]) + "\n")
    cmd_agreed(d / "a.jsonl", d / "b.jsonl", d / "agreed.jsonl")
    got = [json.loads(x)["id"] for x in (d / "agreed.jsonl").read_text().splitlines()]
    ok &= got == [1]
    (d / "c.jsonl").write_text(json.dumps({"id": 9, "label": "keep"}) + "\n")
    ok &= cmd_report(d / "a.jsonl", d / "c.jsonl", d) == 1  # no shared ids is a FAIL
    print(f"kappa identical {k_same:.2f} (want 1), kappa chance {k_rand:.2f} (want 0), agreed ids {got} (want [1])")
    print(f"selftest {'PASS' if ok else 'FAIL'} ({'3/3' if ok else 'fail'})")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["report", "agreed", "selftest"])
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--out")
    x = ap.parse_args()
    if x.cmd == "selftest":
        return selftest()
    if not (x.a and x.b):
        ap.error("--a and --b label files are required")
    if x.cmd == "report":
        return cmd_report(x.a, x.b, Path(x.out or "label-consensus"))
    if not x.out:
        ap.error("agreed needs --out")
    return cmd_agreed(x.a, x.b, Path(x.out))


if __name__ == "__main__":
    sys.exit(main())
