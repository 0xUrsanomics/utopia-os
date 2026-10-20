#!/usr/bin/env python3
# verify_claims.py: keep only extracted claims whose quote is verbatim in the source and holds the number.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Verify a reader model's extracted claims against the archived source text.

Pattern: delegate a long read to a cheaper "reader" model, then trust nothing it returns
unless the quote is a VERBATIM substring of the archived text AND the claimed number appears
inside that quote. Cheaper models fabricate citations; a substring check costs nothing and
catches every invented quote.

  verify_claims.py SOURCE.txt CLAIMS.json   (CLAIMS = reader output; JSON array of {claim, number, quote})
  verify_claims.py --selftest
prints a JSON report {verified: [...], rejected: [...]} and exits 1 if more than half are rejected.
"""
import json
import os
import re
import sys
import tempfile


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def load_claims(raw):
    m = re.search(r"\[.*\]", raw, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return [json.loads(x) for x in re.findall(r"\{[^{}]*\}", raw)]


def check(src_text, claims):
    src = norm(src_text)
    ok, bad = [], []
    for c in claims:
        q, n = norm(c.get("quote", "")), str(c.get("number", "")).strip()
        (ok if q and q in src and n in q else bad).append(c)
    return ok, bad


def main(src_path, claims_path):
    src = open(src_path, encoding="utf-8", errors="ignore").read()
    claims = load_claims(open(claims_path, encoding="utf-8", errors="ignore").read())
    ok, bad = check(src, claims)
    print(json.dumps({"total": len(claims), "verified": ok, "rejected": bad}, indent=1, ensure_ascii=False))
    return 1 if claims and len(bad) > len(claims) / 2 else 0


def _selftest():
    src = "Acme shipped 3 releases in Q2.\nRevenue grew 14 percent year on year, the report says."
    raw = ("Here are the claims:\n"
           '[{"claim": "growth", "number": "14", "quote": "Revenue grew 14 percent year on year"},'
           ' {"claim": "releases", "number": "4", "quote": "Acme shipped 3 releases"},'
           ' {"claim": "invented", "number": "9", "quote": "Acme hired 9 engineers"}]')
    ok, bad = check(src, load_claims(raw))
    passed = [c["claim"] for c in ok] == ["growth"] and len(bad) == 2
    with tempfile.TemporaryDirectory() as td:
        sp, cp = os.path.join(td, "s.txt"), os.path.join(td, "c.json")
        open(sp, "w").write(src)
        open(cp, "w").write(raw)
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(sp, cp)
    passed = passed and rc == 1  # 2 of 3 rejected -> exit 1
    print(f"selftest {'PASS' if passed else 'FAIL'}: verified={[c['claim'] for c in ok]} rejected={len(bad)} rc={rc}")
    return 0 if passed else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        raise SystemExit(_selftest())
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
