---
name: verify-stack
description: "Drive-and-prove check for a long-running agent stack. Proves that features actually reach the person who uses them (evidence level L5), not just that processes exist. Covers the chat send path, cron fire and delivery, the cockpit serving current code, and MCP servers. Use for /verify-stack, 'is it actually live', 'prove it works', after any daemon, cockpit, cron or MCP change, and before telling the operator something is LIVE."
trigger: /verify-stack, verify the stack, is it actually live, prove it works, prove it's live, end to end check
provenance: "Adapted from pstack create-verification-skill and maintain-verification-skill (github.com/cursor/plugins, MIT, Lauren Tan). Changed from 'launch an app' to a long-running stack that this skill never launches or kills."
---

# verify-stack

Health checks and watchdogs answer "is it there, is it up" (L2 to L4). This skill answers "does the feature reach the person who uses it" (L5, `knowledge/evidence-ladder.md`). It exists because of two common misses: a dashboard called LIVE while the running process still held old code, and crons that exist but never deliver.

Helper: `scripts/eval/verify_stack.py` (read-only). Evidence: `outputs/verify/<YYYY-MM-DD-HHMMSS>/<feature>.json`.

## Launch

Nothing to launch. The stack is long-running (scheduler daemon, cockpit, MCP servers spawned by the agent runtime). This skill NEVER starts, restarts or kills anything. A fix that needs a restart is reported, then done as a separate step (INFORM; CONFIRM if it touches the scheduler or settings).

## Doctor (run first, and again after any surprising result)

```bash
python3 scripts/eval/verify_stack.py doctor
```

PASS = the stack's own health checks pass, the scheduler daemon PID is alive, and an outgoing chat message was logged in the last 26 hours. On FAIL, stop: driving a broken stack proves nothing.

## Feature map (v1)

| # | Feature (user's point of view) | Drive | Proof (end state) | Level |
|---|---|---|---|---|
| 1 | The agent's chat messages reach the operator | the agent sends ONE message to a dedicated log topic with a nonce `VS-<6 digits>`; then `verify_stack.py tg-check --nonce VS-xxxxxx` | the nonce is in the live outgoing-message log with a platform message id | L5 |
| 2 | Scheduled jobs fire AND deliver | `verify_stack.py cron [--name <schedule>]` | last run `completed`, under 26 hours old, and at least 1 outgoing message between start and completion + 120 s | L5 |
| 3 | The cockpit shows current data and code | `verify_stack.py cockpit` | the cockpit port answers 200, is bound to 127.0.0.1, AND the serving process started after the newest edit to `scripts/cockpit/cockpit.py` | L5 |
| 4 | MCP tools are callable | `verify_stack.py mcp` (wraps the MCP smoke test) | every stdio server handshakes and lists tools; HTTP servers answer; single-consumer servers (the chat bridge) are skipped by design | L4 |

All at once: `python3 scripts/eval/verify_stack.py all --nonce VS-xxxxxx` (send the feature 1 message first).

If you publish something else people use (a public dashboard, a site), add it as a feature row: the public URL answering 200 is the proof, and a local copy bound to `0.0.0.0` is a WARN.

### Gotchas

- **Check the LIVE log, not a frozen one.** If your stack ever moved its message log to a new database, a check against the old file passes on stale data. Name the live store in the helper and nowhere else.
- **Feature 1 proves the daemon send path, not the plugin reply path.** A chat plugin's `reply` tool returns its own message id; that return value is its proof, and it may not write to the daemon's log.
- **The one outbound drive goes to the log topic only.** Never drive to the operator's personal chat or another topic. One message per run.
- **Cron proof is correlation by time window**, not by job id. Another job sending in the same window can mask a silent cron. For a suspicious cron, read its `execution_log.output` too.
- **A smoke test's "failed" may be a count, not a list.** `ok: null` means spawn-skipped, not failed.

## Evidence

Every run writes one JSON per feature under `outputs/verify/<ts>/`: status, evidence level, the facts checked, the fix. The files hold ids and timestamps only, never message text or secrets. When reporting, cite the status, the level and the one fact that decided it (for example "cockpit FAIL L5: process started 10-03, cockpit.py edited 10-05").

## Cleanup

Nothing to tear down (this skill starts nothing). The log-topic test message stays; it is the proof. Evidence folders older than 30 days can be pruned (INFORM): `find outputs/verify -maxdepth 1 -type d -mtime +30 -exec rm -r {} +`.

## Maintenance

The feature map rots when the stack changes. When a feature is ADDED or moves (new port, new database, new delivery path), in the same change:

1. Update the table above and `verify_stack.py`.
2. Run the new check once live and paste the result into the change note.
3. A behaviour the map describes that the stack no longer has is either map drift (fix the map) or a real regression (report it, never paper over it in the map).

Never weaken a check to make it pass. Run the negative controls once after any change to the helper: a bogus nonce and a bogus cron name must both FAIL.
