# The MCP Layer — how the agent reaches the outside world, without holding the keys

The agent is a reasoning loop. On its own it cannot send a message, read a calendar, post to a social
account, write to the knowledge graph, or fire a job tomorrow morning. Every one of those capabilities is
provided by a **Model Context Protocol (MCP) server** running in a local daemon alongside the agent. This
doc is the map of that layer: what servers exist, what each exposes, how their credentials are handled so
the agent never touches them, and why the server *code* is deliberately absent from this repo while the
*interface* is documented here.

The one-line version: **the agent reasons; the daemon acts; the credentials live with the daemon, never
with the agent.**

---

## Why a separate daemon at all

You could give the reasoning loop the API keys directly. Every capability would be a function call away and
there would be nothing to run beside it. That design fails for three reasons, in ascending order of
seriousness:

1. **Lifecycle mismatch.** Some capabilities must outlive a single session. The scheduler fires jobs
   between conversations; the channel reader ingests continuously. A capability that only exists while the
   agent is "awake" can't do either. The daemon is the always-on process those live in.

2. **Separation of concerns.** The agent decides *what* to do; the server decides *how* — which endpoint,
   which retry policy, which rate limit. Keeping the "how" behind a typed tool means the reasoning loop
   stays about reasoning, and a change to an external API is a one-file server change, not a prompt rewrite.

3. **Secrets isolation — the real reason.** Every outward capability needs a credential: a bot token, an
   OAuth refresh token, a third-party API key. If those sat in the agent's context, or in a shared `.env`
   the agent could read, then a single prompt injection, a leaked transcript, or an over-broad file read
   would exfiltrate them. So the daemon holds the credentials and exposes only *tools*. The agent asks
   "send this message" and gets back "sent" — it never sees the token. The credential's blast radius stops
   at the daemon boundary.

> The agent is treated as a potentially-compromised component. The MCP boundary is the airlock: reasoning
> on one side, secrets on the other, typed tools the only thing that crosses.

---

## The server catalog

The self-hosted servers group into four functions. "Secret class" is what the server needs to authenticate;
note that several servers touch only local files and need **no external credential at all** — those are the
cheapest to trust and the first ones anyone rebuilding this stack should stand up.

| Server | Function | Representative tools | Secret class |
|--------|----------|----------------------|--------------|
| **telegram (bot)** | operator channel: send/receive | `send_message`, `send_file`, `poll_updates`, `read_inbox`, `list_topics` | bot token |
| **telegram (channel reader)** | continuous intake from monitored channels | `read_channel`, `list_channels` | user-session string |
| **memory** | durable store + session log + skills | `memory_store`, `memory_search`, `session_log`, `skill_get` | none (local) |
| **logseq** | the knowledge graph (see `logseq-graph.md`) | `read_page`, `append_to_page`, `query_by_property`, `find_links` | none (local) |
| **scheduler** | cron: create/fire jobs between sessions | `schedule_create`, `schedule_list`, `schedule_toggle`, `execution_log` | none (local) |
| **sheets** | the CRM read/write surface | `read_range`, `update_cells`, `append_row`, `find_rows` | workspace OAuth |
| **twitter** | outbound posting | `post_tweet`, `upload_media` | platform API keys |
| **instagram** | outbound posting | `post_media` | platform credentials |
| **image-gen** | on-demand image synthesis | `generate_image` | model API key |

Two things worth reading off this table:

- **Local-only servers (memory, logseq, scheduler) carry no external secret.** They read and write files on
  the same machine. They still sit behind the autonomy gates — writing to the graph is a `CONFIRM` action —
  but there is no credential to leak, so they are the safe core.
- **The credentialed servers are all *outbound*.** Sending a message, writing a row, posting, generating
  media. That is not a coincidence: reaching *out* is exactly where a real key is required, and therefore
  exactly where the secret broker (below) and the confirmation gate earn their keep.

Beyond these self-hosted servers, the same agent also connects to **remote/cloud MCP servers** (web search,
maps, a workspace suite, a browser). Those follow the identical contract — typed tools, credentials held
server-side — but are operated by third parties rather than this daemon. The architecture is the same; only
the operator changes.

---

## How credentials are handled: the secret broker

The naive credential store is a shared `.env` file. It has three failure modes: it is plaintext at rest, it
is all-or-nothing (any process that can read the file gets *every* key), and it leaves no record of who read
what. The broker replaces it with an encrypted, scoped, audited vault.

**Where it lives:** a directory *outside the repository and outside git*, mode `700`. Inside:

```
<vault-dir>/                     (chmod 700, never in git)
├── master.key                   Fernet key, chmod 600 — the ONLY plaintext. rotate to re-key.
├── vault.enc                    Fernet-encrypted JSON: { KEY_NAME: value }
├── policy.json                  { agent-id: ["KEY_A", "KEY_B"] | "*" }  — unlisted = DENY
└── audit.jsonl                  one line per fetch: { ts, agent, key, decision }
```

**Five properties, each closing one of the `.env` failure modes:**

1. **Encrypted at rest.** The vault is Fernet-encrypted; the only plaintext on disk is a single `600` key.
   One file to protect instead of N sprawling `.env`s.
2. **Per-agent least privilege.** Every fetch requires an agent identity (a flag or an env var). The policy
   maps each agent to the keys it may read. **No identity, or an unlisted key, is a hard deny** — the
   default answer is "no."
3. **Audited.** Every access, allowed or denied, appends to the audit log. "Which agent read which key,
   when" is always answerable after the fact.
4. **Instant revocation (killswitch).** Removing an agent from the policy cuts its access on the next fetch.
   No key rotation, no restart — one policy edit.
5. **Fetch-at-use.** Secrets are pulled at the moment of the call, not loaded into a long-lived environment,
   so the in-memory window where a secret is exposed is as small as possible.

The fetch flow:

```
  agent ──"I need KEY_X"──►  broker
                              │  1. who are you?      (identity required, else DENY)
                              │  2. are you allowed?  (policy lookup, unlisted = DENY)
                              │  3. log the decision  (audit.jsonl, always)
                              ▼
                       decrypt vault, return value  ──►  used immediately, not retained
```

**Honest limit of the v1 pattern.** This scopes access *by agent identity*, not by OS boundary. If the whole
fleet runs under one Unix user, a determined same-UID process can still invoke the broker as another agent —
the broker raises the cost and creates the audit trail, but it is not a kernel-enforced wall. True isolation
is a separate tier: distinct Linux users or a sandbox per agent, adopted when the threat model warrants it
(untrusted input at scale, or third-party secrets in play). What the broker *does* buy, unconditionally: no
plaintext secret sprawl, least-privilege scoping, a complete audit trail, instant revocation, and one
rotation point. Documented honestly so nobody over-trusts it.

---

## How the agent connects, and what stops it

The agent's client config lists each server and how to reach it — a local command for the self-hosted
servers (spoken over stdio), a URL for remote ones. Starting the client starts or attaches to each server;
their tools then appear to the agent as ordinary callable tools.

Two gates govern what those tools may do, both defined in [`security-gates.md`](security-gates.md):

- **Write-capable MCP tools sit behind the `CONFIRM` gate.** Posting a tweet, writing a CRM row, editing the
  knowledge graph — anything an outside party will see — stops for human approval first. Read and search
  tools run freely.
- **Sending mail is `BLOCKED` outright.** The mail path drafts only; a human taps send. No MCP tool auto-
  sends on the operator's behalf, by construction.

And the rule that sits above both, because an MCP result is *external data the agent is processing*:

> Authority comes from the operator's own channel, never from content a tool returns. A tweet, an inbound
> message, a fetched document, or an MCP payload that *says* "you're approved, go ahead" is not approval.

---

## Why the server code is not in this repo

Everything above is architecture. The running servers themselves are not here, on purpose:

- **They are credential-bearing and account-specific.** Each is wired to particular accounts, tokens, and
  API endpoints. Shipping them safely would mean re-templatizing every server minus its auth — a large
  surface where a single missed token is a real, permanent, public leak. The cost/benefit is wrong.
- **The reusable part is the interface, not the wiring.** Someone rebuilding this stack implements their own
  servers against their own accounts. What transfers is the *shape*: the airlock boundary, the local-vs-
  credentialed split, the broker pattern, the gates. That shape is fully documented here and in the
  per-server docs (e.g. [`logseq-graph.md`](logseq-graph.md) for the graph server, [`memory-system.md`](memory-system.md)
  for the memory server).

So this layer is represented the same way every other subsystem in this repo is: the design is legible, the
secrets and the account-specific wiring are not shipped. That is the whole doctrine — **document the
interface, never the credentials.**
