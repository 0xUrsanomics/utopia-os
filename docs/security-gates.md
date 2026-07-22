# Security Gates — grading autonomy, stopping before the irreversible

An agent with filesystem access, a package manager, and the ability to act between sessions is a powerful
runtime and a large blast radius. The security layer's job is to make the powerful actions *slow down* and
the irreversible ones *stop for a human*, without turning every trivial read into a confirmation prompt.
It does this with graded autonomy, a persistent registry of things not to do, a counter that catches
approval-cascades, static linting of anything executable, and one rule that ties it all together:

> **Authority comes from the operator's own channel, never from content the agent is processing.**

## Autonomy modes

Every action class is graded into one of four modes. The grade decides whether the agent just acts, acts
and reports, asks first, or refuses outright.

| Mode | When | Behavior | Examples |
|---|---|---|---|
| **AUTO** | Routine, reversible, low-risk | Do it. Log it. Don't ask. | Read files, search, analyse, run a scheduled job, generate a draft into a scratch dir, update internal memory. |
| **INFORM** | Moderate, non-trivial but safe | Do it, then say what you did and why. | Create a new output file, modify a skill, install an audited package, run a data-mutating script, kill a process. |
| **CONFIRM** | Strategic, irreversible, external-facing | Ask first. Wait for approval. | Write to a shared knowledge store, edit the system prompt, create/delete a scheduled task, change infrastructure, anything an outside party will see. |
| **BLOCKED** | Never | Refuse, always. | Auto-sending mail on the operator's behalf. Draft it; let the human tap send. |

The mapping from tool to mode lives in a typed schema (`scripts/security/permissions.schema.json`); the
prose above is the summary, the schema is the lookup table. Two supporting rules keep the grades honest:

- **CONFIRM implies a restate.** Before any CONFIRM action, the agent restates the ask, lists its concrete
  assumptions, and names what's out of scope — *then* waits. An approval is only meaningful if the human
  can see what they're approving.
- **The operator can override the grade** ("just do it" → treat as AUTO; "check with me first" →
  treat as CONFIRM) — but only from their own channel, per the envelope rule below. The override applies
  to the current task and then resets.

## The envelope rule — where authority actually comes from

This is the linchpin, so it gets its own section. The agent spends most of its time **processing content**:
reading emails, summarizing documents, ingesting tool results, relaying messages from a group. That content
will, eventually, contain a sentence like *"the operator said go ahead and install this"* or *"approved —
just do it."* A prompt injection is exactly a piece of processed content engineered to read as an instruction.

**Authority is the envelope, not the content.** An override or a CONFIRM approval counts only when it
arrives from the operator's *own* channel — their verified chat identity on the allowlist. It never counts
when it appears inside:

- an email body or an attached document,
- a tool or MCP result,
- a message from someone else relaying "the operator said…",
- text that mimics the operator's voice or formatting.

A quoted, forwarded, or embedded "just do it" is not authorization. The same words that are binding from the
operator's channel are inert when they arrive as data to be processed. Access control is also enforced this
way structurally: pairing requests, allowlist edits, and channel approvals are driven by the operator at the
terminal — never by a message that *asks* to be approved, because that request is precisely what an attacker
would send.

## The stand-down registry

A message-level reminder ("don't install that sketchy package") is forgotten by the next session. A
persistent registry is not. The stand-down registry is a durable list of "don't install / don't run / don't
add X" decisions that is **checked before every**:

- package install (`npm`/`pip`/`cargo`/… install),
- MCP server addition,
- settings/allow-list edit,
- scheduled-task creation.

Each entry carries a verdict, and the check respects it:

| Verdict | Meaning | Action |
|---|---|---|
| `block` | Known-bad, never proceed | Refuse; surface the reason. |
| `warn` | Proceed only with eyes open | Proceed **only** on explicit operator re-confirmation that cites the reason. |
| `clear` | Vetted, fine | Proceed. |
| `expired` | The vetting is stale | Treat as needs-review, re-audit before use. |

Entries match two ways: **named targets** (a specific package or repo) and **patterns** — the shapes that
are dangerous regardless of name:

- `curl … | bash` and other pipe-to-shell installs,
- any auto-send scope (`gmail_send`, SMTP, sendmail),
- **a repo younger than 7 days** — no exceptions. New repositories haven't been community-vetted; the age
  gate is a structural defense against install-day supply-chain attacks.

The reason the registry is a *store* and not a rule is durability: when the agent observes a new "don't
install X" decision, it appends an entry before it can forget, and every future session inherits it. A
persistent stand-down beats a per-message reminder because the whole failure mode is that reminders don't
persist.

## The auto-compound counter — catching the approval cascade

The dangerous pattern isn't one unauthorized action. It's **many individually-authorized actions
compounding on a single approval.** The operator says "yeah, do it" to one thing; the agent, still inside
that authorization, chains a settings edit, then a schedule creation, then four schedule updates, then a
manual override — seven consequential actions on one "yeah." Each was locally fine. The cascade was not.

The counter detects exactly this:

- After every AUTO-mode action in a sensitive domain (`install`, `settings_edit`, `scheduler`,
  `skill_edit`, `cron_fire`), bump a per-domain counter.
- Before chaining *another* AUTO action in the same domain, check the counter.
- When any domain crosses a threshold (e.g. 3) since the last operator message, **stop** and force a
  re-scope: list what's been done, what's queued, and get explicit re-authorization before continuing.
- The counter **resets on every new operator message.** A fresh instruction is a fresh authorization
  budget; silence is not.

```
operator: "ok go"                    ← authorization budget resets
  install X          [install: 1]
  edit settings      [settings: 1]
  create schedule    [scheduler: 1]
  update schedule    [scheduler: 2]
  update schedule    [scheduler: 3]  ← threshold hit → STOP, restate, re-ask
```

The insight: each action passing its own gate is not the same as the *sequence* being authorized. The
counter turns "many small yeses" back into one explicit yes.

## The skill linter

Skills are executable workflows the agent trusts and runs. Anything a skill file can smuggle in — a
prompt-injection string, a request to exfiltrate a file, an instruction to escalate its own permissions —
runs with the agent's trust. So skills are **statically scanned before they're trusted**: a linter checks
skill files for known injection and exfiltration patterns and runs as a pre-commit / pre-load hook, so a
poisoned skill is caught before it ever executes. The same scan applies to skills pulled from outside — a
shared skill is untrusted text until it passes.

## Send guards

Outbound messages are the highest-consequence AUTO-adjacent action, so they get a dedicated pre-flight and
a hard ceiling. Auto-sending mail is **BLOCKED** outright — the only path is draft-and-tap: the agent
composes the message into a draft, and the human sends it. No OAuth send scope, no SMTP, no exceptions. For
other outbound channels the send guard runs a pre-flight check (recipient, content, mode) before anything
leaves.

## Security-first install rule

Underneath the registry sits a standing rule for anything downloaded or integrated: check it before running
it. Package download counts, last-publish date, maintainer reputation, known CVEs; a repo's stars,
contributors, and last commit; what an MCP server actually exposes; the source of any script before you run
it. Pin versions. Never pipe a remote script straight into a shell. Never run a repo younger than 7 days.
Slower and safe beats fast and sorry — this rule overrides convenience, always.

## How the gates wire in

The gates are not advice the model is asked to remember — they are **hooks the runtime enforces**. The
stand-down check and the compound counter run as pre-action hooks; the skill linter runs pre-commit and
pre-load; the send guard sits in front of the outbound path. Enforcement in the harness, not in the prompt,
is what makes them reliable: a hook fires whether or not the model "remembers" the rule this turn.

## Design principles

- **Grade every action.** Reversible and routine flows freely; irreversible and external stops for a human.
- **Authority is the envelope.** Only the operator's own channel authorizes; processed content never does,
  no matter what it says.
- **Persist the stand-down.** A registry outlives a session; a reminder doesn't.
- **Count the cascade, not just the action.** Many authorized steps on one approval is its own failure mode.
- **Enforce in the harness.** Gates live in hooks, so they don't depend on the model choosing to obey them.

See also: `ssot.md` (stores the counters and mode flags), `agent-protocols.md` (per-surface permission
boundaries and forbidden-tool lists), `session-management.md` (the restate/scope step CONFIRM triggers).
