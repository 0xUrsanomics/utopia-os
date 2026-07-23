#!/usr/bin/env python3
"""Egress injection proxy (egress-proxy Phase 1, 2026-07-23).

A local forward proxy that injects real credentials into outbound requests so the
CALLING tool never holds the secret. Phase 1 = a narrow set of RULED hosts (sgai).

For a RULED host it MITM-TLS-terminates (using a leaf cert signed by a local CA the
caller trusts), replaces a PLACEHOLDER in a configured header with the real value
pulled from your broker AT injection time, then re-originates to the real host over
real TLS. Every NON-ruled host BLIND-TUNNELS untouched (we only intercept what we
inject into). The plaintext secret lives ONLY in the broker + this proxy, never in
the tool.

Rules: memory/state/egress_rules.json ::
  {"<host>": {"inject_header": "SGAI-APIKEY", "placeholder": "SGAI_PLACEHOLDER",
              "broker_key": "SGAI_API_KEY", "broker_agent": "web-extract"}}
CA + per-host leaf certs live under a CA dir (default the broker vault/egress-ca, 0700),
generated on first run via openssl. Point a client at the proxy with
  HTTPS_PROXY=http://127.0.0.1:<port>  and trust the CA via REQUESTS_CA_BUNDLE=<ca.pem>.

Subcommands:
  setup                 # gen the CA (idempotent) + print the CA path
  run [--port N]        # run the proxy
  ca-path               # print the CA cert path (for REQUESTS_CA_BUNDLE)
"""
import argparse
import json
import os
import socket
import ssl
import subprocess
import threading

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RULES = os.path.join(ROOT, "memory", "state", "egress_rules.json")
BROKER = os.environ.get("EGRESS_BROKER_CMD", "")  # e.g. "python3 /path/your broker.py get" ; else EGRESS_SECRET_<KEY> env
# NB: NOT under the broker vault (bwrap masks that): the sandboxed caller must be able to
# read ca.pem (public cert) to trust the proxy. ca.key stays 0600 (proxy-only, off-sandbox).
CADIR = os.path.expanduser(os.environ.get("EGRESS_CA_DIR", "~/.config/agent-egress"))
CA_PEM, CA_KEY = os.path.join(CADIR, "ca.pem"), os.path.join(CADIR, "ca.key")


def _sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def ensure_ca():
    os.makedirs(CADIR, exist_ok=True)
    os.chmod(CADIR, 0o700)
    if not (os.path.exists(CA_PEM) and os.path.exists(CA_KEY)):
        _sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", CA_KEY, "-out", CA_PEM,
            "-days", "365", "-nodes", "-subj", "/CN=UrsaEgressCA")
        os.chmod(CA_KEY, 0o600)
    return CA_PEM


def leaf_for(host):
    """Return (cert, key) paths for host, signing a fresh leaf via the CA if missing."""
    ensure_ca()
    cert = os.path.join(CADIR, f"{host}.pem")
    key = os.path.join(CADIR, f"{host}.key")
    if not (os.path.exists(cert) and os.path.exists(key)):
        csr = os.path.join(CADIR, f"{host}.csr")
        ext = os.path.join(CADIR, f"{host}.ext")
        import ipaddress
        try:
            ipaddress.ip_address(host)
            san = f"IP:{host}"
        except ValueError:
            san = f"DNS:{host}"
        open(ext, "w").write(f"subjectAltName={san}\n")
        _sh("openssl", "req", "-newkey", "rsa:2048", "-keyout", key, "-out", csr, "-nodes",
            "-subj", f"/CN={host}")
        _sh("openssl", "x509", "-req", "-in", csr, "-CA", CA_PEM, "-CAkey", CA_KEY,
            "-CAcreateserial", "-out", cert, "-days", "365", "-extfile", ext)
        os.chmod(key, 0o600)
    return cert, key


def load_rules():
    try:
        return json.load(open(RULES))
    except Exception:
        return {}


def broker_value(key, agent):
    # pull the real secret from your broker AT injection time. Configure via
    # EGRESS_BROKER_CMD ("python3 /path/your broker.py get") or, for simple setups,
    # an env var EGRESS_SECRET_<KEY>. The tool never holds the value; the proxy does.
    if BROKER:
        r = _sh(*BROKER.split(), key, "--agent", agent)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    return os.environ.get(f"EGRESS_SECRET_{key}", "")


def _read_http_request(sock):
    """Read one HTTP request (headers + body per Content-Length) from a TLS-wrapped sock."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    if b"\r\n\r\n" not in buf:
        return buf, b""
    head, rest = buf.split(b"\r\n\r\n", 1)
    clen = 0
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            try:
                clen = int(line.split(b":", 1)[1].strip())
            except Exception:
                clen = 0
    body = rest
    while len(body) < clen:
        chunk = sock.recv(4096)
        if not chunk:
            break
        body += chunk
    return head, body


def _inject(head, rule):
    """Inject the real broker value into the outbound request per the rule.

    inject_location: "header" (overwrite the named header's value) | "query" | "path"
    (replace the placeholder substring in the request line). Optional header_allowlist
    strips every outbound header except the allowed + essential ones (wire-level exfil
    defense). The real value is pulled from the broker HERE, never held by the tool.
    """
    real = broker_value(rule["broker_key"], rule["broker_agent"])
    if not real:
        return head, False
    # value_template lets an auth scheme prefix the secret, e.g. "Bearer {value}".
    val = rule.get("value_template", "{value}").format(value=real)
    lines = head.split(b"\r\n")
    reqline, hdrs = lines[0], lines[1:]
    loc = rule.get("inject_location", "header")
    name = rule.get("name") or rule.get("inject_header", "")
    ph = rule.get("placeholder", "")
    done = False

    if loc == "header" and name:
        out = []
        for line in hdrs:
            if line.lower().startswith((name.lower() + ":").encode()):
                out.append(f"{name}: {val}".encode()); done = True
            else:
                out.append(line)
        if not done:                       # header absent -> add it
            out.append(f"{name}: {val}".encode()); done = True
        hdrs = out
    elif loc in ("query", "path") and ph:
        rl = reqline.decode("latin1")
        if ph in rl:
            reqline = rl.replace(ph, val).encode("latin1"); done = True

    allow = rule.get("header_allowlist")
    if allow:
        keep = {h.lower() for h in allow} | {"host", "content-length", "content-type"}
        if loc == "header":
            keep.add(name.lower())
        hdrs = [h for h in hdrs
                if h.split(b":", 1)[0].strip().lower().decode("latin1", "replace") in keep]

    return b"\r\n".join([reqline] + hdrs), done


def _upstream_ctx():
    # re-originate to the real host over real TLS, verified against system CAs.
    # (patchable in tests to trust a local mock.)
    return ssl.create_default_context()


def mitm(client, host, port, rule):
    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    cert, key = leaf_for(host)
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(cert, key)
    tls_client = sctx.wrap_socket(client, server_side=True)
    head, body = _read_http_request(tls_client)
    head, injected = _inject(head, rule)
    up = _upstream_ctx().wrap_socket(
        socket.create_connection((host, port), timeout=30), server_hostname=host)
    up.sendall(head + b"\r\n\r\n" + body)
    while True:
        data = up.recv(8192)
        if not data:
            break
        tls_client.sendall(data)
    up.close()
    tls_client.close()


def tunnel(client, host, port):
    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    try:
        upstream = socket.create_connection((host, port), timeout=30)
    except Exception:
        client.close()
        return
    def relay(a, b):
        try:
            while True:
                d = a.recv(8192)
                if not d:
                    break
                b.sendall(d)
        except Exception:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
    t = threading.Thread(target=relay, args=(client, upstream), daemon=True)
    t.start()
    relay(upstream, client)


def handle(client, rules):
    try:
        line = b""
        while b"\r\n" not in line:
            c = client.recv(1)
            if not c:
                client.close(); return
            line += c
        # consume the rest of the CONNECT headers
        rest = b""
        while b"\r\n\r\n" not in (line + rest):
            c = client.recv(1)
            if not c:
                break
            rest += c
        parts = line.decode("latin1").split()
        if len(parts) >= 2 and parts[0].upper() == "CONNECT":
            host, _, p = parts[1].partition(":")
            port = int(p or 443)
            if host in rules:
                mitm(client, host, port, rules[host])
            else:
                tunnel(client, host, port)
        else:
            client.close()
    except Exception:
        try:
            client.close()
        except Exception:
            pass


def cmd_run(a):
    rules = load_rules()
    ensure_ca()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", a.port))
    srv.listen(64)
    print(json.dumps({"listening": f"127.0.0.1:{srv.getsockname()[1]}", "ca": CA_PEM,
                      "ruled_hosts": list(rules)}))
    while True:
        client, _ = srv.accept()
        threading.Thread(target=handle, args=(client, rules), daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run"); p.add_argument("--port", type=int, default=8888); p.set_defaults(fn=cmd_run)
    sub.add_parser("setup").set_defaults(fn=lambda a: print(json.dumps({"ca": ensure_ca()})))
    sub.add_parser("ca-path").set_defaults(fn=lambda a: print(ensure_ca()))
    sub.add_parser("rules").set_defaults(fn=lambda a: print(json.dumps(load_rules(), indent=2)))
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
