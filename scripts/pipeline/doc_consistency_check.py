#!/usr/bin/env python3
# doc_consistency_check.py: check a multi-doc pack says the same facts, versions and contacts everywhere.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
doc_consistency_check.py . cross-doc fact check for multi-document packs.

WHY. A pack that leaves together (a proposal pack, CV + cover letter + form answers, a memo +
annex) must say the SAME thing everywhere. A typical failure: every doc is carefully written,
yet one feature is "P1" in three docs and "parked" in three others, the spec is called V1.1 or
V1.2 depending on the doc, and a company rename is half done. Each doc passes on its own; the
SET disagrees. A single-file slop gate checks one file at a time, so it cannot see this class.

TWO MODES (combinable)
  1. --facts FACTS.json : declared key facts, checked against every doc.
     {"facts": [
       {"id": "fee",     "expect": ["EUR 900"], "forbid": ["EUR 750"], "require": "all"},
       {"id": "export",  "forbid": ["widget export .{0,40}P1"], "regex": true},
       {"id": "rename",  "forbid": ["\\bOLDCO\\b"], "regex": true, "why": "renamed to Acme"}
     ]}
     expect  : at least one variant must appear (in every doc if require=all, in at least one
               doc if require=any, default any). Missing where required = FAIL.
     forbid  : any hit in any doc = FAIL (stale value, old name, retired claim).
     regex   : treat expect/forbid as regular expressions (case-insensitive) instead of text.
  2. --auto : no facts file needed. Collects VERSION labels (V0.5, v5.1, Draft V0.2) and
     contact handles (emails, phone numbers, URLs) per doc and WARNs where docs disagree. Heuristic:
     a WARN is a prompt to look, not a verdict.

INPUTS: .md .txt .html .docx (stdlib zip/XML, no python-docx needed) .pdf (pdftotext).
USAGE
  doc_consistency_check.py DOC [DOC...] [--facts F.json] [--auto] [--json]
  doc_consistency_check.py --selftest
EXIT 0 = no FAIL (WARN allowed) | 1 = at least one FAIL | 2 = usage error
"""
import argparse, json, os, re, subprocess, sys, tempfile, zipfile
from collections import defaultdict

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_doc(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        # stdlib ET is safe enough here: it never fetches external entities, and expat >= 2.4.1
        # blocks billion-laughs expansion. defusedxml would be a new dep for no extra coverage.
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        paras = []
        for p in root.iter(W_NS + "p"):
            t = "".join(x.text or "" for x in p.iter(W_NS + "t"))
            if t.strip():
                paras.append(t)
        return "\n".join(paras)
    if ext == ".pdf":
        out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True)
        return out.stdout
    with open(path, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    if ext in (".html", ".htm"):
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", txt, flags=re.S | re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
    return txt


def norm(s):
    s = s.replace(" ", " ").replace("’", "'")
    return re.sub(r"\s+", " ", s).lower()


def _hits(text, pats, regex):
    found = []
    for p in pats:
        if regex:
            m = re.search(p, text, flags=re.I | re.S)
            if m:
                found.append((p, m.group(0)[:80]))
        elif norm(p) in text:
            found.append((p, p))
    return found


def check_facts(docs, facts):
    """docs: {name: normalized_text_or_raw}. Returns list of result dicts."""
    out = []
    for f in facts:
        fid, regex = f.get("id", "?"), bool(f.get("regex"))
        req = f.get("require", "any")
        texts = {n: (t if regex else norm(t)) for n, t in docs.items()}
        res = {"id": fid, "status": "PASS", "detail": []}
        for n, t in texts.items():
            for pat, snip in _hits(t, f.get("forbid", []), regex):
                res["status"] = "FAIL"
                res["detail"].append(f"FORBIDDEN in {n}: '{snip}'" + (f" ({f['why']})" if f.get("why") else ""))
        if f.get("expect"):
            have = [n for n, t in texts.items() if _hits(t, f["expect"], regex)]
            missing = [n for n in texts if n not in have]
            if req == "all" and missing:
                res["status"] = "FAIL"
                res["detail"].append(f"expected {f['expect']} missing in: {', '.join(missing)}")
            elif req == "any" and not have:
                res["status"] = "FAIL"
                res["detail"].append(f"expected {f['expect']} in no doc")
            else:
                res["detail"].append(f"expected value present in {len(have)}/{len(texts)} docs")
        out.append(res)
    return out


VERSION = re.compile(r"\b(?:draft\s+)?v\d+(?:\.\d+){1,2}\b", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE = re.compile(r"\+\d[\d -]{7,16}\d")   # space, not \s: \s crossed a newline into the next line's digits
URL = re.compile(r"\b(?:https?://)?(?:www\.)?(?:linkedin\.com/in|github\.com|x\.com|t\.me)/[\w.-]+", re.I)


def check_auto(docs):
    out = []
    # versions: a doc citing several labels for the same thing is common; flag when the SET of labels differs
    vers = {n: sorted({v.lower().replace("draft ", "") for v in VERSION.findall(t)}) for n, t in docs.items()}
    vers = {n: v for n, v in vers.items() if v}
    if len({tuple(v) for v in vers.values()}) > 1:
        out.append({"id": "auto:version-labels", "status": "WARN",
                    "detail": [f"{n}: {', '.join(v)}" for n, v in vers.items()] +
                              ["docs cite different version labels; confirm they refer to different documents"]})
    for label, rx in (("emails", EMAIL), ("phones", PHONE), ("profile-urls", URL)):
        per = {n: sorted({re.sub(r"[\s-]", "", m.lower()) for m in rx.findall(t)}) for n, t in docs.items()}
        per = {n: v for n, v in per.items() if v}
        if len(per) >= 2 and len({tuple(v) for v in per.values()}) > 1:
            out.append({"id": f"auto:{label}", "status": "WARN",
                        "detail": [f"{n}: {', '.join(v)}" for n, v in per.items()] +
                                  [f"{label} differ across docs; a contact detail should match everywhere"]})
    return out


def _selftest():
    # Fabricated pack: Acme (formerly OLDCO) proposal in three docs.
    d = {"a.md": "Fee EUR 900 flat. Widget export is parked. Spec V1.2.",
         "b.md": "Fee EUR 900 flat. Widget export P1 priority. Spec V1.1. Contact oc@example.com",
         "c.md": "Fee EUR 750. OC keen to join."}
    facts = [{"id": "ask", "expect": ["EUR 900"], "forbid": ["EUR 750"], "require": "all"},
             {"id": "export", "forbid": [r"widget export.{0,20}P1"], "regex": True},
             {"id": "rename", "forbid": [r"\bOC\b"], "regex": True}]
    r = {x["id"]: x for x in check_facts(d, facts)}
    a = {x["id"]: x for x in check_auto(d)}
    clean = {x["id"]: x for x in check_facts({"a.md": "Fee EUR 900.", "b.md": "Fee EUR 900 net."},
                                              [{"id": "ask", "expect": ["EUR 900"], "require": "all"}])}
    checks = [
        ("forbid_catches_stale_value", r["ask"]["status"] == "FAIL" and any("750" in x for x in r["ask"]["detail"])),
        ("require_all_flags_missing_doc", any("missing in: c.md" in x for x in r["ask"]["detail"])),
        ("regex_forbid_catches_contradiction", r["export"]["status"] == "FAIL"),
        ("rename_residue_caught_word_boundary", r["rename"]["status"] == "FAIL" and "oc@example.com" not in str(r["rename"]["detail"])),
        ("auto_version_mismatch_warns", "auto:version-labels" in a),
        ("clean_set_passes", clean["ask"]["status"] == "PASS"),
        ("phone_does_not_cross_newline", "auto:phones" not in {x["id"] for x in check_auto(
            {"cv.pdf": "call +1 555-0100-0199 now", "cover.pdf": "+1 555-0100-0199\n13 October 2026"})}),
    ]
    for n, v in checks:
        print(f" {'PASS' if v else 'FAIL'}  {n}")
    ok = all(v for _, v in checks)
    print(f"== SELFTEST {'PASS' if ok else 'FAIL'} ({sum(v for _, v in checks)}/{len(checks)}) ==")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="*")
    ap.add_argument("--facts")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if _selftest() else 1)
    if len(a.docs) < 2 or not (a.facts or a.auto):
        print("usage: doc_consistency_check.py DOC DOC [...] (--facts F.json | --auto) [--json]", file=sys.stderr)
        sys.exit(2)
    docs = {os.path.basename(p): read_doc(p) for p in a.docs}
    results = []
    if a.facts:
        with open(a.facts) as f:
            results += check_facts(docs, json.load(f)["facts"])
    if a.auto:
        results += check_auto(docs)
    fail = any(r["status"] == "FAIL" for r in results)
    if a.json:
        print(json.dumps({"verdict": "FAIL" if fail else "PASS", "docs": list(docs), "results": results}, indent=2))
    else:
        print(f"== DOC CONSISTENCY . {'FAIL' if fail else 'PASS'} . {len(docs)} docs ==")
        for r in results:
            print(f"[{r['status']:4}] {r['id']}")
            for d in r["detail"]:
                print(f"         {d}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
