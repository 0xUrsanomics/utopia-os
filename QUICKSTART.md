# Quickstart

A human first-run path. Fifteen minutes to a working core, longer if you want the chat bridge.

If you would rather have your coding agent do the whole thing, use [`SETUP.md`](SETUP.md)
instead. That file is written **for the agent** and covers all eight harnesses. This one is
written for you, and assumes nothing.

---

## 0. What you actually need

**Python 3.9 or newer. That is the whole list.**

The core of Utopia OS has no third-party dependencies. Memory is Markdown files, the state
store is stdlib `sqlite3`, the security gates are stdlib, and the cockpit is stdlib
`http.server`. All 49 Python modules under `scripts/` import with nothing installed.

```bash
python3 --version     # need 3.9+
git clone https://github.com/0xUrsanomics/utopia-os.git
cd utopia-os
pip install -r requirements.txt     # installs nothing, by design. see the file's header
```

Two things are genuinely optional and both are opt-in:

| You want | Install | Cost |
|---|---|---|
| Semantic recall over your notes | `pip install -r requirements-memory.txt` | ~2.5-6 GB, plus ~2 GB model on first run |
| A Telegram or Discord bot as the interface | no packages; see [`docs/bot-setup.md`](docs/bot-setup.md) | ~10 minutes of clicking |

Skip both on your first pass. The system is useful without either.

---

## 1. Platform

| Platform | State | Notes |
|---|---|---|
| **Linux** | Supported | The reference platform. |
| **macOS, Apple Silicon** | Supported | Runs near-unchanged. `vector_brain.py` detects Metal/MPS and uses it; falls back to CPU. |
| **macOS, Intel** | Supported | Same as Linux, CPU-only for the recall tier. |
| **Windows via WSL2** | Supported | This is how the reference system runs. **Use this on Windows.** |
| **Windows, native** | Partial, see below | Not recommended. |

**Native Windows, honestly.** Most of the repo is pure stdlib and will run. The one real
problem is `scripts/memory/lib_signal_store.py`, which uses `fcntl` for its cross-process
file lock. `fcntl` is POSIX-only. The import is already guarded, so nothing crashes: the
lock quietly becomes a no-op, and two processes writing the signal store at once are no
longer serialised. Since the scheduler and the chat bridge are exactly the kind of thing you
run concurrently, that matters. The module now emits a warning when this happens so it fails
loudly rather than silently.

Install WSL2 and clone inside it:

```powershell
wsl --install -d Ubuntu        # then open Ubuntu and follow the Linux path
```

---

## 2. First run: memory and the state store

Copy the scaffolds, dropping the `.template` from each name:

```bash
for f in memory/templates/*.template.md; do
  b=$(basename "$f" .template.md)
  cp -n "$f" "memory/$b.md"
done
ls memory/*.md          # SOUL.md USER.md MEMORY.md Preferences.md Decisions.md ...
```

The state store needs no init step: it creates its schema on first use. Prove it works:

```bash
python3 scripts/memory/ssot.py self-test
```

That runs the real controls (anonymous writes refused, non-namespaced keys refused,
round-trip, audit log, no-op de-duplication) and prints a `[PASS]` per control. The database
lands at `memory/state/ssot.sqlite` and is gitignored.

Now fill in two files by hand. They are the ones everything else reads:

- `memory/SOUL.md` — your voice constitution. How the agent writes, what it never does.
- `memory/USER.md` — who you are. Role, timezone, what you are working on.

Both ship as templates with the section headings already in place. Write a paragraph in
each; you will refine them for months. **Nothing works well until these two are real** —
an agent with an empty voice file sounds like every other agent.

---

## 3. Wire the system prompt

Copy `CLAUDE.md` to wherever your harness reads its instruction file from. On Claude Code
that is the project root or `~/.claude/CLAUDE.md`; on Codex, grok, opencode and pi it is
`AGENTS.md`. See [`AGENTS.md`](AGENTS.md) for the per-harness mapping and
[`adapters/`](adapters/) for a config template per harness.

Read it before you use it. It encodes opinions (autonomy tiers, a CONFIRM gate, an
anti-slop stance) that you may want to change.

---

## 4. Turn on the safety gates

This is the part worth not skipping. The gates are what stop an agent from installing a
malicious package or overwriting something irreversible.

```bash
cp settings.example.json ~/.claude/settings.json    # or your harness's equivalent
```

`settings.example.json` wires the hooks in [`scripts/security/`](scripts/security/): the
stand-down registry, the auto-compound counter, the skill linter, the send guards, and the
CONFIRM gate. [`docs/security-gates.md`](docs/security-gates.md) explains what each one
blocks and why. For a non-Claude-Code harness, your adapter's README maps these onto its
own hook system.

Check the CONFIRM gate responds before you trust it:

```bash
python3 scripts/security/confirm_gate.py list      # empty on a fresh install, and that is correct
python3 scripts/security/confirm_gate.py --help    # register / validate / list
```

The gate works by `register`ing a pending action and `validate`ing the approval against a
hash of that exact action, so a stale approval cannot authorise a mutated one.

---

## 5. See it

```bash
python3 scripts/cockpit/cockpit.py       # then open http://localhost:8787
```

Read-only, localhost-only, no dependencies. It shows memory state, session activity, and
gate status. If this renders, your core install is good.

---

## 6. Optional: a chat interface

Most of the value of an ops system is being able to talk to it from your phone. For Telegram
a working MCP server ships, so this is wiring rather than building:

```bash
python3 scripts/mcp/telegram_bridge.py --selftest    # 16 checks, no token or network needed
```

Then get a token and your chat id, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS`,
and point your adapter's MCP block at the bridge. Full walkthrough with the exact click
paths: **[`docs/bot-setup.md`](docs/bot-setup.md)**. Discord gets you as far as credentials;
the server for it is yours to write, and the Telegram bridge is the shape to copy.

Never put a token in a file you commit. The gates include a secret scanner, but do not make
it do work it should not have to.

---

## Where to go next

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the whole-system picture.
- [`docs/memory-system.md`](docs/memory-system.md) — how the tiers actually work.
- [`skills/`](skills/) — adopt one at a time. `save` and `scope` are the two that pay off
  first.
- [`docs/security-gates.md`](docs/security-gates.md) — read before granting any autonomy.

## If it does not work

- **`ModuleNotFoundError` on a core script.** Should not happen; the core is stdlib-only.
  Check you are on Python 3.9+ and not accidentally running Python 2.
- **Recall returns nothing.** You have not installed `requirements-memory.txt`, or you have
  not indexed yet: `python3 scripts/memory/vector_brain.py index`.
- **A hook does not fire.** Harness hook config is the usual culprit. Check your adapter
  README, and confirm the script is executable (`chmod +x`).
- **A gate blocks something you wanted.** That is the gate working. Read the reason it
  printed; override deliberately rather than by disabling the hook.
