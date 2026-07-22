# LLM Supply Chain Security. "Your Agent Is Mine" Paper

**Source:** https://arxiv.org/abs/2604.08407
**Title:** Your Agent Is Mine: Measuring Malicious Intermediary Attacks on the LLM Supply Chain
**Authors:** Hanzhi Liu, Chaofan Shou, Hongbo Wen, Yanju Chen, Ryan Jingyang Fang, Yu Feng
**Relevance:** Affects any LLM stack that uses third-party API routers/proxies.

---

## Threat Model

Third-party LLM API routers (OpenRouter-class proxies, "cheap" multi-model gateways) operate as
unencrypted intermediaries between client and upstream LLM provider. They can:

1. **Inject payloads**: modify LLM responses to insert malicious code/instructions before forwarding
2. **Exfiltrate secrets**: scan prompts for credentials, API keys, wallet addresses
3. **Steal tokens**: capture leaked API keys for unauthorized usage
4. **Evade detection**: multiple variants bypass naive client-side checks

## Empirical Findings (the paper's measurements)

- **9 malicious routers identified** (1 paid + 8 free) actively injecting harmful code into responses
- **17 routers** accessed AWS credentials submitted by researchers as test inputs
- **1 router drained an Ethereum wallet** (likely scanned for seed phrases or private keys in prompts)
- **100M GPT-5.4 tokens** generated from a single leaked OpenAI key across multiple sessions
- **2 billion billed tokens stolen** + **99 credentials harvested** from 440 Codex sessions in the study
- The research proxy implemented all four attack patterns against public agent frameworks

## Defenses Evaluated

### Client-side mitigations
1. **Fail-closed policy gates**: when verification fails, block the response rather than pass it through
2. **Response anomaly detection**: statistical/structural checks on returned content
3. **Append-only transparency logging**: every request/response logged immutably for forensic review

### Effectiveness
The paper notes these defenses help but are not sufficient against sophisticated adversaries. The
fundamental fix is to avoid untrusted intermediaries.

## Implications for a subscription-first agent stack

### What "good" looks like
- Direct connection to the model provider (a first-party subscription/API), no proxy in between
- Any CLI/tool talks to its official first-party developer platform, not a router
- MCP servers talk to first-party services (calendar, sheets, etc.)
- No third-party LLM aggregators, no "cheap inference" gateways

### Where exposure creeps in
- Every additional cloud-hosted service = additional attack surface; trust depends on that provider's
  security posture
- Any future wallet/payment integration multiplies the blast radius of a compromised intermediary
- A third-party LLM router, if ever added, would be a major risk

## Defense Plan

### Baseline (get these in place)
- No third-party LLM routers; direct provider connections only
- File-integrity monitoring on `.env` and credential files (alert on unauthorized change)
- A security-first rule that blocks installing untrusted MCP servers

### Short-term additions
1. **Audit all API calls in scheduled tasks**: verify every endpoint is first-party, no aggregators
2. **Endpoint allowlist**: alert if an agent process makes calls to unknown domains
3. **Centralized credential audit**: one script that lists every API key in use, where it lives, what
   it can do
4. **Append-only request log**: log every outbound LLM/API call to a tamper-evident file

### Medium-term
1. **Pre-flight check on new MCP servers**: test against a canary credential before granting real access
2. **Response anomaly detection**: statistical checks on scheduled-task output to flag anomalies
3. **Token rotation schedule**: periodic rotation of API keys to limit exposure window

### Hard rules
1. **NEVER use a third-party LLM router**: always direct to provider
2. **NEVER hardcode credentials in prompts**: they're fingerprints for routers to exfiltrate
3. **Audit any new LLM-adjacent service before adding**: check who runs it, where credentials go
4. **Treat "cheaper" inference services as adversarial by default**: the price gap usually has a hidden
   cost
5. **DCI spot-check before adding any third-party MCP** (arXiv:2606.04769): before adding a non-first-
   party MCP server, cross-check each tool's DESCRIPTION against its CODE. Does a tool described
   "read-only"/"safe"/"no side effects" actually write, delete, send, or do undisclosed side effects?
   The paper found ~9.93% of 19,200 real MCP tool pairs mismatch, and the agent blindly trusts the
   description. A one-shot static read is enough; quote the mismatch if found, refuse adoption on a
   security-boundary lie.

## Recommended actions

- If your stack is already direct-to-provider, no immediate action beyond codifying the "no LLM routers"
  rule.
- If any agent in your fleet routes through a proxy (OpenRouter-class), audit which endpoints it uses,
  rotate any keys that passed through it, and evaluate switching to direct provider APIs, prioritizing
  the highest-stakes agents (trading, intelligence).
- Long-term: track follow-up research and any published IOC list of flagged routers. If multi-model
  routing is genuinely needed, run a self-hosted gateway rather than trusting a third party.

---

## Key Takeaway

The cheaper the service, the more likely it's monetizing your data + secrets. Free LLM routers are
particularly risky. Direct provider connections cost more but eliminate the supply-chain attack surface
entirely.
