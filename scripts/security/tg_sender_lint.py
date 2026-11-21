#!/usr/bin/env python3
# tg_sender_lint.py: find direct Telegram Bot API sends that can fail silently.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""tg_sender_lint.py: find direct Telegram Bot API sends that can fail silently.

Why: a cron error alert inherited a false-success bug because its sender (the shell
notifier, scripts/scheduler/cron_tg_notify.sh) exited 0 whatever Telegram said. A relay
process failed silently the same way for months. A sender that never looks at Telegram's
answer turns every rejected alert into a silent success.

What counts as a call site: code that builds an api.telegram.org/bot.../sendXxx URL
(sendMessage, sendDocument, sendPhoto, ...), directly or through a base-URL variable such as
API_BASE = f"https://api.telegram.org/bot{TOKEN}", or through a host-only variable such as
API = "https://api.telegram.org" used as f"{API}/bot{token}/{method}" (a method dispatcher,
reported once as "dynamic-method" at the line that builds the URL). Comments, docstrings and
getMe/getUpdates are not call sites.

Rule (one question per site: can a Telegram rejection reach a branch that logs, returns
False or exits nonzero?). The transport matters: curl -s without -f exits 0 on HTTP 4xx and
requests/httpx do not raise on 4xx, while urllib.request.urlopen raises HTTPError on 4xx.
  PASS    the code reads Telegram's "ok" field ("ok":true / .get("ok") / ["ok"]).
  UNSURE  status-only check with the failure surfaced (HTTP_CODE = 200, resp.status == 200,
          raise_for_status, or urllib with an except that logs/returns False). Telegram pairs
          HTTP 200 with ok:true, so these are probably fine, but they do not read "ok".
  FAIL    the response is discarded (>/dev/null, -o /dev/null, no capture), the except is a
          bare pass, or nothing checks the outcome.

Helper callers (lines that run cron_tg_notify.sh) are tallied separately as CHECKED or
UNCHECKED. They never count as FAIL in this version.

Output: VERDICT file:line method reason. Source text is never printed, so a hard-coded token
cannot leak through this tool.

Usage:
  tg_sender_lint.py                 scan this repo's scripts/ (plus any --extra roots, report only)
  tg_sender_lint.py PATH [PATH ...] scan these files or dirs (all treated as repo scope)
  tg_sender_lint.py --extra DIR     also scan DIR (Python only, report only; repeatable), for
                                    example a separately installed MCP daemon
  tg_sender_lint.py --staged        pre-commit mode: block only when a staged file has MORE
                                    FAIL sites than its HEAD version (newly added FAILs)
  tg_sender_lint.py --json          machine-readable output
  tg_sender_lint.py --selftest      fixture tests
Exit: 0 no FAIL in repo scope, 1 any FAIL in repo scope (or zero sites scanned, which is
never green), 2 bad usage. --extra findings never change the exit code.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(os.environ.get("AGENT_ROOT") or Path(__file__).resolve().parents[2])
CODE_ROOT = REPO / "scripts"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "site-packages", "archive"}
SKIP_FILES = {"tg_sender_lint.py"}
HELPER = "cron_tg_notify.sh"

TG_URL = re.compile(r"api\.telegram\.org/bot")
TG_HOST = re.compile(r"^https?://api\.telegram\.org/?$")
SEND_IN_URL = re.compile(r"/(send[A-Z]\w*)")
OK_PARSE = re.compile(
    r"""\.get\(\s*['"]ok['"]|\[\s*['"]ok['"]\s*\]|['"]?"ok"\s*:\s*true|\\"ok\\":\s*true|\.ok\b\s*==\s*true|jq[^\n]*\.ok""")
STATUS_CHECK = re.compile(
    r"""\.status\s*[!=]=\s*200|status_code\s*[!=]=\s*200|raise_for_status|http_code[^\n]*|\bHTTP_CODE\b|=\s*"200"|-w\s+["']?%\{http_code\}""")
SURFACED = re.compile(
    r"""return\s+False|\braise\b|\blog\w*\(|_log_error\(|print\([^\n]*(stderr|fail)|sys\.exit\(|\bexit\s+[1-9]|FAILED|>&2|undelivered""",
    re.I)
SILENT_EXCEPT = re.compile(r"except[^\n]*:\s*\n\s*pass\b")
HELPER_MARK = "\n#--followed-helper--\n"  # a helper's own silent except (a logger) is not this site's
RETURNS_BODY = re.compile(r"return\s+data\b|return\s+(resp|r)\.json\(\)|return\s+json\.loads")
SHELL_DISCARD = re.compile(r">\s*/dev/null|-o\s+/dev/null|\|\|\s*true")


def wanted(path):
    p = Path(path)
    if p.name in SKIP_FILES or p.suffix not in (".py", ".sh"):
        return False
    return not any(part in SKIP_DIRS for part in p.parts)


def iter_files(roots, py_only=False):
    for root in roots:
        root = Path(root)
        if root.is_file():
            if wanted(root) and (not py_only or root.suffix == ".py"):
                yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in sorted(filenames):
                f = Path(dirpath) / fn
                if wanted(f) and (not py_only or f.suffix == ".py"):
                    yield f


# ---------------------------------------------------------------- classification

def classify_block(block, transport):
    """Return (verdict, reason) for the text of one call site's block."""
    if OK_PARSE.search(block):
        return "PASS", "reads Telegram ok field"
    if RETURNS_BODY.search(block):
        return "UNSURE", "returns the parsed body; the caller must read ok"
    surfaced = bool(SURFACED.search(block))
    status = bool(STATUS_CHECK.search(block))
    own = block.split(HELPER_MARK, 1)[0]
    if transport == "urllib":
        silent = bool(SILENT_EXCEPT.search(own))
        has_try = "try:" in block
        if status and surfaced:
            return "UNSURE", "urllib status-only check, failure surfaced"
        if has_try and surfaced and not silent:
            return "UNSURE", "urllib raises on 4xx, except surfaces it, ok not read"
        if not has_try:
            return "UNSURE", "urllib without try: a rejection raises into the caller"
        return "FAIL", "urllib error swallowed by bare except/pass"
    if status and surfaced:
        return "UNSURE", "HTTP status-only check, failure surfaced"
    if transport == "shell" and SHELL_DISCARD.search(block):
        return "FAIL", "response discarded (/dev/null or || true), ok not checked"
    if SILENT_EXCEPT.search(own):
        return "FAIL", "response not checked, except is bare pass"
    return "FAIL", "response not checked"


def transport_of(block):
    if "urlopen" in block:
        return "urllib"
    if "curl" in block:
        return "curl"
    return "http-client"


# ---------------------------------------------------------------- python

def _docstring_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _fstring_text(node):
    out = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            out.append(v.value)
        elif isinstance(v, ast.FormattedValue):
            inner = v.value
            out.append("{" + (inner.id if isinstance(inner, ast.Name) else "expr") + "}")
    return "".join(out)


def _str_text(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return _fstring_text(node)
    return None


def _clean_py_lines(src, tree, doc_ids):
    """Source lines with comments cut and docstring lines blanked, so text such as a
    comment saying "ok":true can never make a site PASS. Line numbers are preserved."""
    import io as _io
    import tokenize
    lines = src.splitlines()
    for node in ast.walk(tree):
        if id(node) in doc_ids:
            for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                if 0 < ln <= len(lines):
                    lines[ln - 1] = ""
    try:
        for tok in tokenize.generate_tokens(_io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                if 0 < row <= len(lines):
                    lines[row - 1] = lines[row - 1][:col]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return lines


def py_sites(src):
    """Yield (lineno, method, block_text) for each Telegram send site in Python source."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    docs = _docstring_ids(tree)
    lines = _clean_py_lines(src, tree, docs)
    inner_consts = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                inner_consts.add(id(v))
    # base-URL variables: NAME = f"https://api.telegram.org/bot{TOKEN}" (no method in it)
    bases, hosts = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            vals = [node.value] + ([node.value.body, node.value.orelse] if isinstance(node.value, ast.IfExp) else [])
            for v in vals:
                t = _str_text(v)
                if t and TG_URL.search(t) and not SEND_IN_URL.search(t):
                    bases.add(node.targets[0].id)
                elif t and TG_HOST.match(t):
                    hosts.add(node.targets[0].id)
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    by_name = {f.name: f for f in funcs}

    def src_of(f):
        return "\n".join(lines[f.lineno - 1:f.end_lineno])

    def block_for(lineno):
        best = None
        for f in funcs:
            if f.lineno <= lineno <= (f.end_lineno or f.lineno):
                if best is None or f.lineno > best.lineno:
                    best = f
        if best is None:
            return "\n".join(lines[max(0, lineno - 15):lineno + 15])
        text = src_of(best)
        # follow one level into same-module helpers that receive the request
        # (send() builds the URL, _post(req) checks the answer)
        for node in ast.walk(best):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in by_name and node.func.id != best.name:
                text += HELPER_MARK + src_of(by_name[node.func.id])
        return text

    seen = set()
    for node in ast.walk(tree):
        if id(node) in docs or id(node) in inner_consts:
            continue
        t = _str_text(node)
        if not t:
            continue
        method = None
        if TG_URL.search(t):
            m = SEND_IN_URL.search(t.split("api.telegram.org", 1)[1])
            if m:
                method = m.group(1)
        elif isinstance(node, ast.JoinedStr):
            m = re.match(r"\{(\w+)\}/(send[A-Z]\w*|\{\w+\})", t)
            mh = re.match(r"\{(\w+)\}/bot\{\w+\}/(send[A-Z]\w*|\{\w+\})", t)
            if m and m.group(1) in bases:
                method = m.group(2) if m.group(2).startswith("send") else "dynamic-method"
            elif mh and mh.group(1) in hosts:
                method = mh.group(2) if mh.group(2).startswith("send") else "dynamic-method"
        if method and (node.lineno, method) not in seen:
            seen.add((node.lineno, method))
            yield node.lineno, method, block_for(node.lineno)


# ---------------------------------------------------------------- shell

def sh_functions(lines):
    """{name: body} for shell functions defined as `name() {` ... `}` at the same indent."""
    funcs, i = {}, 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:function\s+)?([A-Za-z_]\w*)\s*\(\)\s*\{\s*$", lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not re.match("^" + m.group(1) + r"\}\s*$", lines[j]):
                j += 1
            funcs[m.group(2)] = "\n".join(lines[i:j + 1])
            i = j
        i += 1
    return funcs


def _clean_sh_lines(src):
    """Shell lines with whole-line and trailing comments removed (a trailing ' #' counts
    only when the quotes before it are balanced). Line numbers are preserved."""
    out = []
    for line in src.splitlines():
        if line.lstrip().startswith("#"):
            out.append("")
            continue
        cut = line
        for m in re.finditer(r"\s#", line):
            pre = line[:m.start()]
            if pre.count('"') % 2 == 0 and pre.count("'") % 2 == 0:
                cut = pre
                break
        out.append(cut)
    return out


def sh_sites(src):
    lines = _clean_sh_lines(src)
    funcs = sh_functions(lines)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") or not TG_URL.search(line):
            continue
        m = SEND_IN_URL.search(line.split("api.telegram.org", 1)[1])
        if not m:
            continue
        start = i
        while start > 0 and lines[start - 1].rstrip().endswith("\\"):
            start -= 1
        end = i
        while end < len(lines) - 1 and lines[end].rstrip().endswith("\\"):
            end += 1
        # follow-up window: up to 10 lines or the end of the enclosing function
        stop = end + 1
        while stop < len(lines) and stop <= end + 10 and lines[stop].rstrip() != "}":
            stop += 1
        cmd = "\n".join(lines[start:end + 1])
        block = "\n".join(lines[start:stop])
        # follow same-file helper functions the block calls (e.g. tg_result checking "ok")
        for name, body in funcs.items():
            if re.search(r"(^|[\s;&|(])" + name + r"(\s|;|$)", block, re.M) and name + "()" not in block:
                block += "\n" + body
        yield i + 1, m.group(1), cmd, block


def classify_shell(cmd, block):
    if OK_PARSE.search(block):
        return "PASS", "reads Telegram ok field"
    captured = bool(re.search(r"\w+=\$\(\s*curl", cmd)) or "-w" in cmd
    if STATUS_CHECK.search(block) and captured:
        if SURFACED.search(block):
            return "UNSURE", "HTTP status-only check, failure surfaced"
        return "UNSURE", "HTTP status-only check, failure not logged"
    if SHELL_DISCARD.search(cmd) or not captured:
        return "FAIL", "response discarded (/dev/null, || true or no capture), ok not checked"
    return "FAIL", "response captured but ok not checked"


# ---------------------------------------------------------------- helper callers

def helper_calls(path, src):
    """(lineno, CHECKED|UNCHECKED) for each line that runs cron_tg_notify.sh."""
    out = []
    lines = src.splitlines()
    if path.suffix == ".sh":
        vars_ = set(re.findall(r"^\s*(\w+)=[\"']?[^\n]*" + re.escape(HELPER), src, re.M))
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("#") or not s:
                continue
            if re.match(r"^\w+=", s) and HELPER in s:
                continue  # path assignment, not a call
            hit = HELPER in s or any(re.search(r"\"?\$\{?" + v + r"\}?\"?\s+\"", s) for v in vars_)
            if not hit:
                continue
            checked = bool(re.search(r"^\s*(if|elif|until|while)\b|\|\|\s*(?!true\b)\S|;\s*rc=\$\?|\brc=\$\?", s)) \
                or (i + 1 < len(lines) and re.search(r"\$\?", lines[i + 1]))
            out.append((i + 1, "CHECKED" if checked else "UNCHECKED"))
    else:
        # python: names bound to the helper path, then subprocess calls that use one of them
        names = set(re.findall(r"""^\s*([\w"'\[\]]+?)\s*[=:]\s*[^\n]*""" + re.escape(HELPER), src, re.M))
        names = {n.strip("\"'[]") for n in names} | {HELPER}
        for i, line in enumerate(lines):
            if line.lstrip().startswith("#") or not re.search(r"subprocess\.(run|call|Popen|check_call|check_output)", line):
                continue
            stmt = "\n".join(lines[i:i + 4])
            if not any(n and n in stmt for n in names):
                continue
            after = "\n".join(lines[i:i + 12])
            checked = bool(re.search(r"returncode|check_call|check=True|check_output", after))
            out.append((i + 1, "CHECKED" if checked else "UNCHECKED"))
    return out


# ---------------------------------------------------------------- scan

def scan_text(path, src):
    """Return (sites, helpers). sites = list of dicts."""
    sites = []
    path = Path(path)
    if path.suffix == ".py":
        res = py_sites(src)
        if res is None:
            sites.append({"line": 1, "method": "?", "verdict": "UNSURE", "reason": "python parse error, not analysed"})
        else:
            for ln, method, block in res:
                v, r = classify_block(block, transport_of(block))
                sites.append({"line": ln, "method": method, "verdict": v, "reason": r})
    elif path.suffix == ".sh":
        for ln, method, cmd, block in sh_sites(src):
            v, r = classify_shell(cmd, block)
            sites.append({"line": ln, "method": method, "verdict": v, "reason": r})
    helpers = [{"line": ln, "state": st} for ln, st in helper_calls(path, src)]
    return sites, helpers


def scan(roots, scope, py_only=False):
    rows, helpers, files = [], [], 0
    for f in iter_files(roots, py_only=py_only):
        try:
            src = f.read_text(errors="replace")
        except OSError:
            continue
        files += 1
        s, h = scan_text(f, src)
        for x in s:
            rows.append({"scope": scope, "file": str(f), **x})
        for x in h:
            helpers.append({"scope": scope, "file": str(f), **x})
    return rows, helpers, files


def rel(p):
    try:
        return str(Path(p).relative_to(REPO))
    except ValueError:
        return str(p)


def print_report(rows, helpers):
    for scope in ("repo", "extra"):
        sr = [r for r in rows if r["scope"] == scope]
        if not sr and scope == "extra":
            continue
        counts = {k: sum(1 for r in sr if r["verdict"] == k) for k in ("PASS", "FAIL", "UNSURE")}
        tag = "" if scope == "repo" else " (report only)"
        print(f"== {scope}{tag}: {len(sr)} call sites, PASS {counts['PASS']} / FAIL {counts['FAIL']} / UNSURE {counts['UNSURE']}")
        for v in ("FAIL", "UNSURE", "PASS"):
            for r in sorted((r for r in sr if r["verdict"] == v), key=lambda r: (r["file"], r["line"])):
                print(f"{v:6} {rel(r['file'])}:{r['line']} {r['method']}: {r['reason']}")
    hc = [h for h in helpers if h["scope"] == "repo"]
    if hc:
        unchecked = [h for h in hc if h["state"] == "UNCHECKED"]
        print(f"== helper callers ({HELPER}, informational): {len(hc)}, CHECKED {len(hc) - len(unchecked)} / UNCHECKED {len(unchecked)}")
        for h in sorted(unchecked, key=lambda h: (h["file"], h["line"])):
            print(f"UNCHECKED {rel(h['file'])}:{h['line']}")


# ---------------------------------------------------------------- staged (pre-commit)

def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=20)


def scan_staged(repo=REPO):
    """Compare FAIL counts per staged file: staged blob vs HEAD blob. Returns (new_fail_rows, n_files)."""
    r = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"], repo)
    files = [f for f in r.stdout.splitlines() if f.startswith("scripts/") and wanted(f)]
    new_rows = []
    for f in files:
        staged = _git(["show", f":{f}"], repo)
        if staged.returncode != 0:
            continue
        head = _git(["show", f"HEAD:{f}"], repo)
        s_sites, _ = scan_text(f, staged.stdout)
        h_sites, _ = scan_text(f, head.stdout) if head.returncode == 0 else ([], [])
        s_fail = [x for x in s_sites if x["verdict"] == "FAIL"]
        h_fail = [x for x in h_sites if x["verdict"] == "FAIL"]
        if len(s_fail) > len(h_fail):
            new_rows += [{"file": f, **x} for x in s_fail]
    return new_rows, len(files)


# ---------------------------------------------------------------- selftest

CANARY = "123456:CANARY-TOKEN-do-not-print"

FIXTURES = {
    "good_curl.sh": ('#!/bin/bash\n'
                     'send() {\n'
                     '  resp=$(curl -s "https://api.telegram.org/bot${TOK}/sendMessage" \\\n'
                     '    --data-urlencode "text=$1" 2>/dev/null) || true\n'
                     '  case "$resp" in *\'"ok":true\'*) return 0 ;; esac\n'
                     '  echo "undelivered" >&2; return 1\n'
                     '}\n', ["PASS"]),
    "bad_curl.sh": ('#!/bin/bash\n'
                    '# curl https://api.telegram.org/bot/sendMessage in a comment is not a site\n'
                    'curl -s -X POST "https://api.telegram.org/bot' + CANARY + '/sendMessage" \\\n'
                    '  -d chat_id=1 -d text=hi > /dev/null 2>&1 || true\n'
                    'echo "ALERT_SENT" >> log\n'
                    'exit 0\n', ["FAIL"]),
    "status_curl.sh": ('#!/bin/bash\n'
                       'CODE=$(curl -s -o /dev/null -w "%{http_code}" \\\n'
                       '  -X POST "https://api.telegram.org/bot${T}/sendMessage" -d text=x || echo 000)\n'
                       'if [ "$CODE" = "200" ]; then echo sent; else echo "FAILED to send"; fi\n', ["UNSURE"]),
    "requests_no_ok.py": ('import requests\n'
                          'def send(tok, text):\n'
                          '    """Posts to https://api.telegram.org/bot<tok>/sendMessage (docstring, not a site)."""\n'
                          '    try:\n'
                          '        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", data={"text": text})\n'
                          '    except Exception:\n'
                          '        pass\n', ["FAIL"]),
    "requests_ok.py": ('import requests\n'
                       'def send(tok, text):\n'
                       '    r = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument", data={"text": text})\n'
                       '    body = r.json()\n'
                       '    if not body.get("ok"):\n'
                       '        log("send failed")\n'
                       '        return False\n'
                       '    return True\n', ["PASS"]),
    "curl_subprocess_no_ok.py": ('import subprocess\n'
                                 'def send(tok, text):\n'
                                 '    try:\n'
                                 '        subprocess.run(["curl", "-s", f"https://api.telegram.org/bot{tok}/sendPhoto",\n'
                                 '                        "-d", "x"], capture_output=True, timeout=10)\n'
                                 '    except Exception:\n'
                                 '        pass\n', ["FAIL"]),
    "urllib_status.py": ('import urllib.request\n'
                         'def send(tok, data):\n'
                         '    try:\n'
                         '        with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data) as r:\n'
                         '            return r.status == 200\n'
                         '    except Exception as e:\n'
                         '        print("tg send failed", type(e).__name__)\n'
                         '        return False\n', ["UNSURE"]),
    "urllib_pass.py": ('import urllib.request\n'
                       'def send(tok, data):\n'
                       '    try:\n'
                       '        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data).read()\n'
                       '    except Exception:\n'
                       '        pass\n', ["FAIL"]),
    "indirect_base.py": ('import httpx\n'
                         'TOKEN = "x"\n'
                         'API_BASE = f"https://api.telegram.org/bot{TOKEN}"\n'
                         'async def alert(text):\n'
                         '    try:\n'
                         '        async with httpx.AsyncClient() as c:\n'
                         '            await c.post(f"{API_BASE}/sendMessage", json={"text": text})\n'
                         '    except Exception:\n'
                         '        pass\n'
                         'async def getme():\n'
                         '    async with httpx.AsyncClient() as c:\n'
                         '        await c.post(f"{API_BASE}/getMe")\n', ["FAIL"]),
    "host_base_dispatch_ok.py": ('import json, urllib.request\n'
                                 'API = "https://api.telegram.org"\n'
                                 'def _call(method, params):\n'
                                 '    url = f"{API}/bot{_token()}/{method}"\n'
                                 '    try:\n'
                                 '        with urllib.request.urlopen(url, data=params) as r:\n'
                                 '            body = json.loads(r.read())\n'
                                 '    except Exception as e:\n'
                                 '        raise RuntimeError("send failed") from None\n'
                                 '    if not body.get("ok"):\n'
                                 '        raise RuntimeError("rejected")\n'
                                 '    return body.get("result")\n', ["PASS"]),
    "host_base_dispatch_silent.py": ('import urllib.request\n'
                                     'API = "https://api.telegram.org"\n'
                                     'def call(tok, method, data):\n'
                                     '    try:\n'
                                     '        urllib.request.urlopen(f"{API}/bot{tok}/{method}", data=data).read()\n'
                                     '    except Exception:\n'
                                     '        pass\n'
                                     'def hello():\n'
                                     '    return f"{API} is the host"\n', ["FAIL"]),
    "sh_helper_fn.sh": ('#!/bin/bash\n'
                        'tg_result() {\n'
                        '    case "${_tg:-}" in *\'"ok":true\'*) _d=SENT ;; *) _d=UNDELIVERED ;; esac\n'
                        '}\n'
                        '_tg="$(curl -s "https://api.telegram.org/bot${T}/sendMessage" \\\n'
                        '    --data-urlencode "text=x" 2>/dev/null)" || true\n'
                        'tg_result\n'
                        'echo "$_d" >> log\n', ["PASS"]),
    "py_helper_fn.py": ('import urllib.request\n'
                        'def _post(req):\n'
                        '    try:\n'
                        '        with urllib.request.urlopen(req) as r:\n'
                        '            return json.loads(r.read()).get("ok", False)\n'
                        '    except Exception as e:\n'
                        '        return False\n'
                        'def send(tok, data):\n'
                        '    return _post(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data))\n',
                        ["PASS"]),
    "comment_says_ok.sh": ('#!/bin/bash\n'
                           '# this send reads "ok":true and logs undelivered (it does not)\n'
                           'curl -s "https://api.telegram.org/bot${T}/sendMessage" -d text=x >/dev/null 2>&1 || true  # "ok":true\n',
                           ["FAIL"]),
    "docstring_says_ok.py": ('import subprocess\n'
                             'def send(tok):\n'
                             '    """True only when Telegram answered "ok":true; logs undelivered otherwise."""\n'
                             '    subprocess.run(["curl", f"https://api.telegram.org/bot{tok}/sendMessage"])  # "ok":true\n',
                             ["FAIL"]),
    "no_sites.py": ('def f():\n    return "api.telegram.org/bot is mentioned, no method"\n', []),
}


def selftest():
    cases = []

    def check(name, cond):
        cases.append((name, bool(cond)))

    with tempfile.TemporaryDirectory() as td:
        for name, (src, want) in FIXTURES.items():
            p = Path(td) / name
            p.write_text(src)
            sites, _ = scan_text(p, src)
            got = [s["verdict"] for s in sites]
            check(f"{name}: verdicts {want}", got == want)
        rows, _, nfiles = scan([td], "repo")
        check("scan walked all fixtures", nfiles == len(FIXTURES))
        check("scan found the expected number of sites",
              len(rows) == sum(len(w) for _, w in FIXTURES.values()))

        # report and exit code: FAIL present -> 1, and the canary token never printed
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main_with([td])
        out = buf.getvalue()
        check("exit 1 when a FAIL exists", rc == 1)
        check("report never prints source text or the token", CANARY not in out and "ALERT_SENT" not in out
              and "data={" not in out)

        # zero sites scanned is never green
        empty = Path(td) / "empty"
        empty.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main_with([str(empty)])
        check("zero sites scanned exits 1", rc == 1)

        # only PASS/UNSURE -> exit 0
        clean = Path(td) / "clean"
        clean.mkdir()
        for n in ("good_curl.sh", "requests_ok.py", "urllib_status.py"):
            (clean / n).write_text(FIXTURES[n][0])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main_with([str(clean)])
        check("PASS and UNSURE only exits 0", rc == 0)

        # helper callers: unchecked vs checked
        hsrc = ('N=/x/cron_tg_notify.sh\n'
                '"$N" "msg" >/dev/null 2>&1 || true\n'
                'if "$N" "msg"; then :; else echo undelivered >> log; fi\n')
        h = helper_calls(Path("h.sh"), hsrc)
        check("helper callers: one unchecked, one checked", [s for _, s in h] == ["UNCHECKED", "CHECKED"])

        # staged mode: a new FAIL in a commit is caught; an unchanged FAIL is not
        repo = Path(td) / "repo"
        (repo / "scripts").mkdir(parents=True)
        g = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
        g("init", "-q")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        old = repo / "scripts" / "old.py"
        old.write_text(FIXTURES["urllib_pass.py"][0])
        g("add", ".")
        g("commit", "-qm", "base")
        old.write_text(FIXTURES["urllib_pass.py"][0] + "\n# touched\n")
        g("add", ".")
        new_rows, n = scan_staged(repo)
        check("staged: touching a file with an old FAIL does not block", n == 1 and not new_rows)
        (repo / "scripts" / "new.sh").write_text(FIXTURES["bad_curl.sh"][0])
        g("add", ".")
        new_rows, n = scan_staged(repo)
        check("staged: a newly added FAIL blocks", n == 2 and len(new_rows) == 1 and new_rows[0]["file"].endswith("new.sh"))

    if not cases:
        print("FAIL: zero cases ran")
        return 1
    failed = [n for n, ok in cases if not ok]
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


# ---------------------------------------------------------------- main

def main_with(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--extra", action="append", default=[], help="extra root, Python only, report only")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.staged:
        try:
            new_rows, n = scan_staged()
        except Exception as e:  # a crash or git timeout is not a FAIL: exit 2, the hook warns
            print(f"tg_sender_lint: staged scan error ({type(e).__name__}), not checked", file=sys.stderr)
            return 2
        if n == 0:
            return 0  # nothing relevant staged: no work, not a failed check
        for r in new_rows:
            print(f"FAIL   {r['file']}:{r['line']} {r['method']}: {r['reason']}")
        if new_rows:
            print("tg_sender_lint: this commit adds a Telegram send whose result is not checked. "
                  "Read the ok field (or call cron_tg_notify.sh and check its exit code), and log a failed send.",
                  file=sys.stderr)
            return 1
        return 0
    roots = a.paths or [str(CODE_ROOT)]
    rows, helpers, nfiles = scan(roots, "repo")
    for extra in a.extra:
        if Path(extra).is_dir():
            drows, _, _ = scan([extra], "extra", py_only=True)
            rows += drows
    code_rows = [r for r in rows if r["scope"] == "repo"]
    if a.json:
        print(json.dumps({"files": nfiles, "sites": rows, "helpers": helpers}, indent=1))
    else:
        print_report(rows, helpers)
    if not code_rows:
        print(f"FAIL: zero Telegram send sites found in {nfiles} files; a lint that checked nothing is not green")
        return 1
    return 1 if any(r["verdict"] == "FAIL" for r in code_rows) else 0


if __name__ == "__main__":
    sys.exit(main_with(sys.argv[1:]))
