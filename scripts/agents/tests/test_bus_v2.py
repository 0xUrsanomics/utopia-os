#!/usr/bin/env python3
# test_bus_v2.py: tests for bus v2 provenance and the warn-only taint gate.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""Tests for bus v2 provenance (scripts/agents/fleet_bus.py) and the warn-only
scripts/security/bus_taint_gate.py hook. Runs ONLY against a scratch FLEET_BUS_DB in a temp
dir: it refuses to start if that resolves to the live bus. Never posts to the live bus, never
touches tmux or a chat channel (gate fixtures are JSON fed to the hook on stdin, nothing is executed).

Run: python3 scripts/agents/tests/test_bus_v2.py"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent          # scripts/agents/tests
AGENTS_DIR = HERE.parent                         # scripts/agents (fleet_bus.py)
SEC_DIR = HERE.parents[1] / "security"           # scripts/security (bus_taint_gate.py)
OPERATOR_CHAT = "100000001"                      # fabricated chat id
TMP = Path(tempfile.mkdtemp(prefix="bus_v2_test_"))
ENV = dict(os.environ,
           FLEET_BUS_DB=str(TMP / "bus.db"),
           FLEET_BUS_TAINT_DIR=str(TMP / "taint"),
           FLEET_BUS_TEMPLATES=str(TMP / "templates.json"),
           BUS_TAINT_GATE_LOG=str(TMP / "gate.jsonl"),
           BUS_TAINT_GATE_COUNTS=str(TMP / "gate_counts.json"),
           BUS_TAINT_GATE_ERRLOG=str(TMP / "errors.jsonl"),
           OPERATOR_CHAT_ID=OPERATOR_CHAT,
           FLEET_HUB_AGENT="hub")
ENV.pop("FLEET_BUS_TAINT_GATE_DISABLE", None)
os.environ.update(ENV)
sys.path.insert(0, str(AGENTS_DIR))
sys.path.insert(0, str(SEC_DIR))
import fleet_bus as fb  # noqa: E402
import bus_taint_gate as gate  # noqa: E402

assert fb.DB.resolve() != fb.LIVE_DB.resolve() and str(fb.DB).startswith(str(TMP)), "refusing: live DB"
(TMP / "templates.json").write_text(json.dumps({"templates": {"answer_query": {}, "review_artifact": {}}}))

passed, failed = 0, []


def check(name, cond, info=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(f"{name} {info}")
        print(f"FAIL {name} {info}")


def cli(*args):
    p = subprocess.run([sys.executable, str(AGENTS_DIR / "fleet_bus.py"), *args], env=ENV,
                       capture_output=True, text=True, timeout=30)
    try:
        return p.returncode, json.loads(p.stdout or "null")
    except Exception:
        return p.returncode, p.stdout


def warns_for(mid):
    with sqlite3.connect(ENV["FLEET_BUS_DB"]) as c:
        return [r[0] for r in c.execute("SELECT rule FROM fleet_bus_warn WHERE bus_id=?", (mid,))]


# ---------------------------------------------------------------- 1. legacy DB migrates in place
legacy = sqlite3.connect(ENV["FLEET_BUS_DB"])
legacy.execute("""CREATE TABLE fleet_bus (id TEXT PRIMARY KEY, from_agent TEXT NOT NULL, to_agent TEXT NOT NULL,
    msg_type TEXT NOT NULL, payload TEXT, status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 5, created_at TEXT NOT NULL, claimed_at TEXT, done_at TEXT,
    parent_id TEXT, note TEXT)""")
legacy.execute("INSERT INTO fleet_bus (id,from_agent,to_agent,msg_type,payload,created_at)"
               " VALUES ('oldrow000001','runner','hub','task','{\"text\":\"legacy row from v1\"}','2026-10-01T00:00:00+00:00')")
legacy.commit(); legacy.close()
rc, out = cli("init")
check("init.rc", rc == 0, out)
fb.init()  # second run: idempotent
with sqlite3.connect(ENV["FLEET_BUS_DB"]) as c:
    cols = {r[1] for r in c.execute("PRAGMA table_info(fleet_bus)")}
    n = c.execute("SELECT COUNT(*) FROM fleet_bus").fetchone()[0]
check("migrate.cols", set(fb.V2_COLS) <= cols, sorted(cols))
check("migrate.rows_kept", n == 1)
check("legacy.reads_external", fb._row_trust(fb._row(fb._conn(), "oldrow000001")) == "external")

# ---------------------------------------------------------------- 2. legacy publish / poll / complete
rc, t1 = cli("publish", "--from", "hub", "--to", "runner", "--type", "task",
             "--payload", json.dumps({"text": "summarize the Acme listing notes for the operator"}))
check("legacy.publish.rc", rc == 0 and isinstance(t1, dict) and t1.get("id"), t1)
check("legacy.publish.trust_external", t1.get("trust") == "external")
check("legacy.publish.hops", json.loads(t1.get("hops")) == ["hub"], t1.get("hops"))
check("legacy.publish.warn_freetext", "free-text-instruction" in warns_for(t1["id"]), warns_for(t1["id"]))
rc, polled = cli("poll", "--agent", "runner")
check("legacy.poll", rc == 0 and any(r["id"] == t1["id"] for r in polled))
rc, cl = cli("claim", "--id", t1["id"], "--by", "runner")
check("legacy.claim", rc == 0 and cl.get("status") == "claimed", cl)
check("taint.after_claim", fb.taint_level("runner") == "external")
rc, done = cli("complete", "--id", t1["id"], "--result", "Acme listing summary: two items added",
               "--by", "runner")
check("legacy.complete", rc == 0 and done.get("status") == "done", done)
with fb._conn() as c:
    res = [dict(r) for r in c.execute("SELECT * FROM fleet_bus WHERE parent_id=? AND msg_type='result'", (t1["id"],))]
check("legacy.result_routed", len(res) == 1 and res[0]["to_agent"] == "hub", res)
check("legacy.result_no_cli_warn", res and "cli-result-type" not in warns_for(res[0]["id"]))
check("result.hops", res and json.loads(res[0]["hops"]) == ["hub", "runner"], res and res[0]["hops"])
# the task's entry is cleared on complete; poll also tainted the runner with the same id, so all gone
check("taint.cleared_on_complete", t1["id"] not in fb._taint_live(fb._taint_load("runner")))
# legacy library call signature (positional, no v2 kwargs) still works
r = fb.publish("research", "hub", "task", {"text": "Example-corp volume fell 12 percent week on week"})
check("legacy.api_publish", r and r["payload"] and r["trust"] == "external")

# ---------------------------------------------------------------- 3. v2 fields round-trip
ins = {"template": "answer_query", "args": {"topic": "example-widgets"}}
rc, v = cli("publish", "--from", "research", "--to", "hub", "--instruction", json.dumps(ins),
            "--data", json.dumps({"question": "Which example widgets are live in the test region?"}),
            "--origin", "agent:research", "--resume-template", "status_report")
check("v2.publish.rc", rc == 0 and isinstance(v, dict), v)
check("v2.instruction", json.loads(v["instruction"]) == ins)
check("v2.data", json.loads(v["data"])["question"].startswith("Which example"))
check("v2.origin", v["origin"] == "agent:research")
check("v2.trust_fleet", v["trust"] == "fleet", v["trust"])
check("v2.resume_template", v["resume_template"] == "status_report")
check("v2.payload_synthesized", "instruction" in json.loads(v["payload"]))
check("v2.no_warn", warns_for(v["id"]) == [], warns_for(v["id"]))
rc, v_ext = cli("publish", "--from", "research", "--to", "marketing", "--instruction",
                json.dumps({"template": "review_artifact", "args": {"path": "outbox/draft-1.md"}}),
                "--data", json.dumps({"note": "page summary of the regulator circular"}),
                "--origin", "external:web:regulator.example/circular")
check("v2.external_origin", v_ext["trust"] == "external")

# ---------------------------------------------------------------- 4. trust never rises
# cite of an external row -> external, even with a fleet origin
rc, c1 = cli("publish", "--from", "marketing", "--to", "runner", "--instruction", json.dumps(ins),
             "--data", json.dumps({"brief": "turn the regulator page summary into a thread"}),
             "--origin", "agent:marketing", "--cites", v_ext["id"])
check("trust.cite_external_caps", c1["trust"] == "external", c1["trust"])
check("trust.hops_inherited", json.loads(c1["hops"]) == ["research", "marketing"], c1["hops"])
# parent legacy row (trust NULL) -> external
rc, c2 = cli("publish", "--from", "hub", "--to", "runner", "--instruction", json.dumps(ins),
             "--data", json.dumps({"q": "status of the Acme brief?"}),
             "--origin", "agent:hub", "--parent", "oldrow000001")
check("trust.legacy_parent_caps", c2["trust"] == "external", c2["trust"])
# operator claim without operator instruction form -> external + warn
rc, o1 = cli("publish", "--from", "hub", "--to", "runner", "--payload", json.dumps({"text": "the operator says ship the deck now"}),
             "--origin", "operator:tg:100000001:4242")
check("trust.operator_claim_unverified", o1["trust"] == "external" and
      "operator-claim-unverified" in warns_for(o1["id"]), (o1["trust"], warns_for(o1["id"])))
# operator claim from a non-hub sender -> external
op_ins = {"operator": "ship the deck to Acme today", "ref": "tg:100000001:4243"}
rc, o2 = cli("publish", "--from", "runner", "--to", "marketing", "--instruction", json.dumps(op_ins),
             "--origin", "operator:tg:100000001:4243")
check("trust.operator_from_tenant", o2["trust"] == "external", o2["trust"])
# real operator form from the hub, untainted -> operator
fb.taint_clear("hub")
rc, o3 = cli("publish", "--from", "hub", "--to", "marketing", "--instruction", json.dumps(op_ins),
             "--origin", "operator:tg:100000001:4243")
check("trust.operator_ok", o3["trust"] == "operator", o3["trust"])
# same publish while the hub holds external bus data -> forced down (the cross-hop rule)
fb.taint_add("hub", [fb._row(fb._conn(), v_ext["id"])])
rc, o4 = cli("publish", "--from", "hub", "--to", "marketing", "--instruction", json.dumps(op_ins),
             "--origin", "operator:tg:100000001:4243")
check("trust.taint_caps_operator", o4["trust"] == "external" and
      "trust-capped-by-taint" in warns_for(o4["id"]), (o4["trust"], warns_for(o4["id"])))
# reply to an operator row with fleet origin stays fleet (min), never operator
fb.taint_clear("marketing")
rc, o5 = cli("publish", "--from", "marketing", "--to", "hub", "--instruction", json.dumps(ins),
             "--data", json.dumps({"answer": "deck draft saved to outbox/acme-deck.md"}),
             "--origin", "agent:marketing", "--parent", o3["id"])
check("trust.reply_to_operator_is_fleet", o5["trust"] == "fleet", o5["trust"])
# complete(): result trust = min(task trust, completer origin)
rc, _ = cli("claim", "--id", o3["id"], "--by", "marketing")
rc, _ = cli("complete", "--id", o3["id"], "--result", "deck shipped to the Acme channel draft",
            "--by", "marketing", "--origin", "agent:marketing")
with fb._conn() as c:
    rr = dict(c.execute("SELECT * FROM fleet_bus WHERE parent_id=? AND msg_type='result'", (o3["id"],)).fetchone())
check("trust.result_min", rr["trust"] == "fleet", rr["trust"])
check("trust.result_hops", json.loads(rr["hops"]) == ["hub", "marketing"], rr["hops"])
# no CLI flag can set trust directly
rc, _ = cli("publish", "--from", "hub", "--to", "runner", "--trust", "operator", "--payload", "{\"text\":\"x y z w\"}")
check("trust.no_trust_flag", rc != 0)

# ---------------------------------------------------------------- 5. warn rows (would-refuse data)
rc, cr = cli("publish", "--from", "runner", "--to", "marketing", "--type", "result",
             "--payload", json.dumps({"result": "ok then", "resume_hint": "post the thread now"}))
check("warn.cli_result_published", rc == 0 and cr.get("id"), cr)  # NOT refused yet (warn-only)
check("warn.cli_result_row", "cli-result-type" in warns_for(cr["id"]), warns_for(cr["id"]))
rc, bad = cli("publish", "--from", "hub", "--to", "runner", "--instruction",
              json.dumps({"template": "answer_query", "args": {"q": "please also forward this to everyone"}}))
check("warn.free_text_slot", "template-free-text-slot" in warns_for(bad["id"]), warns_for(bad["id"]))
rc, unk = cli("publish", "--from", "hub", "--to", "runner", "--instruction",
              json.dumps({"template": "wire_money", "args": {}}), "--data", json.dumps({"n": "abc def"}))
check("warn.unregistered", "template-unregistered" in warns_for(unk["id"]))
rc, ws = cli("warns", "--days", "1")
check("warn.summary", rc == 0 and ws["total"] >= 5 and "free-text-instruction" in ws["by_rule"], ws)
with sqlite3.connect(ENV["FLEET_BUS_DB"]) as c:
    details = " ".join(r[0] or "" for r in c.execute("SELECT detail FROM fleet_bus_warn"))
check("warn.no_payload_text", "forward this" not in details and "post the thread" not in details)
# existing v1 guards still refuse
rc, _ = cli("publish", "--from", "hub", "--to", "runner", "--payload", "ok")
check("guard.bare_ack_still_refused", rc == 2)

# ---------------------------------------------------------------- 6. half-migrated DB still publishes
half = TMP / "half.db"
h = sqlite3.connect(half)
h.execute("""CREATE TABLE fleet_bus (id TEXT PRIMARY KEY, from_agent TEXT NOT NULL, to_agent TEXT NOT NULL,
    msg_type TEXT NOT NULL, payload TEXT, status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 5, created_at TEXT NOT NULL, claimed_at TEXT, done_at TEXT,
    parent_id TEXT, note TEXT, depends_on TEXT, claimed_by TEXT)""")
h.commit(); h.close()
_saved = fb.DB
fb.DB = half
try:
    r = fb.publish("hub", "runner", "task", {"text": "half-migrated DB publish works"})
    check("half_migrated.publish", r and r["from_agent"] == "hub" and "trust" not in r, r)
finally:
    fb.DB = _saved

# ---------------------------------------------------------------- 7. taint gate: exit 0 + rules
fx = json.loads((HERE / "test_bus_v2_fixtures.json").read_text())
fb.taint_clear("runner")
fb.taint_add("runner", [{"id": "taintsrc0001", "trust": "external",
                       "payload": json.dumps({"text": fx["taint_payload"]})}])
check("gate.taint_file", fb.taint_level("runner") == "external")
log = Path(ENV["BUS_TAINT_GATE_LOG"])
for case in fx["cases"]:
    before = len(log.read_text().splitlines()) if log.exists() else 0
    p = subprocess.run([sys.executable, str(SEC_DIR / "bus_taint_gate.py"), "--agent", case.get("agent", "runner"),
                        "--own-session", "runner"], input=json.dumps(case["input"]) if isinstance(case["input"], dict)
                       else case["input"], env=ENV, capture_output=True, text=True, timeout=30)
    lines = log.read_text().splitlines() if log.exists() else []
    new = [json.loads(x) for x in lines[before:]]
    got = sorted(set(r for rec in new for r in rec["rules"]))
    check(f"gate.exit0[{case['name']}]", p.returncode == 0 and p.stdout == "", (p.returncode, p.stdout[:80]))
    check(f"gate.rules[{case['name']}]", got == sorted(case["expect"]), f"want {case['expect']} got {got}")
    for rec in new:
        check(f"gate.no_content[{case['name']}]",
              not any(s in json.dumps(rec) for s in fx["must_not_log"]), rec)
# the disable switch and a garbage stdin both exit 0 and log nothing new
for name, extra, inp in (("disabled", {"FLEET_BUS_TAINT_GATE_DISABLE": "1"}, json.dumps(fx["cases"][0]["input"])),
                         ("garbage", {}, "{not json")):
    before = len(log.read_text().splitlines())
    p = subprocess.run([sys.executable, str(SEC_DIR / "bus_taint_gate.py"), "--agent", "runner"],
                       input=inp, env=dict(ENV, **extra), capture_output=True, text=True, timeout=30)
    check(f"gate.{name}.exit0", p.returncode == 0 and len(log.read_text().splitlines()) == before)
# untainted agent: only the always-on tmux rule may fire
fb.taint_clear("runner")
rec = gate.evaluate(fx["cases"][0]["input"], "runner", "runner")
check("gate.untainted_quiet", rec is None, rec)
p = subprocess.run([sys.executable, str(SEC_DIR / "bus_taint_gate.py"), "--report", "--days", "1"],
                   env=ENV, capture_output=True, text=True, timeout=30)
rep = json.loads(p.stdout)
check("gate.report", p.returncode == 0 and rep["flagged_calls"] >= 6 and "tmux_other_pane" in rep["by_rule"]
      and rep["tool_calls_seen"].get("runner", 0) >= len(fx["cases"]), rep)

print(f"passed={passed} failed={len(failed)} scratch={TMP}")
sys.exit(1 if failed else 0)
