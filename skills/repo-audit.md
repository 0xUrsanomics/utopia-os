---
name: repo-audit
trigger: github link drop, "audit this repo", "should we install X", "what about Y" with github URL, "is this safe", "what would change if we adopt"
description: 4-option triage when you drop a GitHub repo URL. doc-mine / clone-audit / install-direct / park. Default to clone-audit for anything that touches credentials, filesystem, or the LLM context layer.
output: chat reply with a verdict line + 4-option breakdown + recommended path
---

# Repo Audit Skill

When you drop a GitHub URL or ask about adopting an external repo, present a 4-option triage and run the recommended path.

## Tone & Voice

Adversarial register. **starting hypothesis: the repo is REJECTED until evidence proves it's safe AND useful.** Don't go soft because "the README looks nice" or "it has stars". The 7-day rule + the standdowns registry + the bundle-RCE gate exist for a reason. Cite specific findings, name specific risks, refuse to blindly adopt anything that touches credentials / filesystem / context layer without a clone-audit first.

**Hard rule**: NEVER install/run any repo less than 7 days old (CLAUDE.md security-first rule). NEVER install repos in the standdowns registry (`memory/standdowns.json`). ALWAYS run `python3 scripts/check_standdown.py <target>` before a recommendation. ALWAYS run `--bundle-scan <dir>` if doing a clone-audit on a bundle that may contain test files (an RCE-in-a-test-file vector).

## Output format

A chat reply with a structured verdict:

```
🔍 repo-audit: <owner>/<repo>

VERDICT: <DOC-MINE | CLONE-AUDIT | INSTALL-DIRECT | PARK | REJECT>

evidence:
- created: <date>, last push: <date>, age: <days>
- stars: N, forks: N, contributors: N
- license: <SPDX>
- standdown check: <clear/warn/block> ({reason if not clear})
- 7-day rule: <pass/fail>
- credentials/fs/context touch: <yes/no + scope>
- bundle-scan (if applicable): N findings, severity X

recommendation:
<paragraph explaining the verdict + specific risks + recommended action>

re-audit triggers (if PARK/REJECT):
- <condition 1>
- <condition 2>
```

If the verdict is INSTALL-DIRECT, run a pre-install standdown check + a dry-run install in a worktree first (per `skills-shared/test-before-bulk.md`).

## Trigger

- A GitHub URL pasted in chat ("github.com/owner/repo", "https://github.com/...")
- "Audit this repo" / "should we install X" / "is this safe to use"
- "What about Y?" / "What would change if we adopt Z?" with repo context
- Repo evaluation following a testimonial / blog post / tweet

## Mandatory pre-checks (security-first rule)

Before ANY option, verify:

1. **7-day age rule**: the repo + each release tag must be ≥7 days old. Hard NO on younger.
2. **Owner provenance**: account age, prior repos, public footprint. An anon owner + 1 repo = a red flag.
3. **Star velocity sanity**: stars/day vs follower count. >100 stars/day with <500 followers = inorganic.
4. **License**: MIT/Apache-2.0 fine; GPL/AGPL = read implications; no license = HARD NO.
5. **Active sprint check**: do NOT install during an active deal sprint (a major delivery window). Defer to the next safe window.

If any check fails → SKIP all 4 options, recommend PARK or REJECT with a reason.

## The 4 options

Present as a table with your pick, ranked by risk × reward for THIS specific repo + your blast-radius profile (a sole operator with .ssh, wallets, and chat sessions on this box).

### Option A. Doc-mine
**What**: lift documentation/skill files only via `curl` pinned to a commit hash. NO runtime install. Pure read.
**When**: the repo has high-quality docs you can crib (skill files, prompt templates, methodology docs) but the runtime is invasive, high-blast-radius, or new.
**Examples**: a browser-automation repo (skill docs lifted, runtime parked); a public skills repo (a few skill files lifted, pinned to a commit hash).
**Cost**: 5-10 min. Zero install. Zero supply-chain surface beyond the curl.
**Output**: docs land in `knowledge/<repo-name>-skills/` with a README capturing provenance + the pinned commit + an adaptation plan.

### Option B. Clone + source audit
**What**: clone the repo locally to `sandbox/audit-<repo>/` (read-only, NO build, NO install). Spawn a subagent or audit inline. Read the priority files (install scripts, telemetry, network code, credential surfaces, hooks). Cross-reference public security issues. Produce a verdict + concrete file:line citations.
**When**: the repo touches credentials, the filesystem at scale, the LLM context layer, the dev workflow (MITM risk), or the source recommends without source-level due diligence.
**Examples**: a CLI proxy tool (subagent audit on a tagged version, verdict GREEN-CAUTIOUS-INSTALL with specific risks + mitigations).
**Cost**: 30-60 min if delegated to a subagent (preferred. reads 5-10 source files, writes a structured report). Zero install during the audit phase.
**Output**: `outputs/raw/agent/YYYY-MM-DD-<repo>-source-audit-<version>.md` with a verdict line / executive summary / file:line findings table / top-5 risks / top-5 mitigations / decision recommendation.

### Option C. Install direct
**What**: install per the docs without a source review. Trust the README + ecosystem coverage.
**When**: ONLY for established tools with broad community vetting (10K+ users, multi-year history, an official package channel) AND low blast radius (read-only, no credential access, no filesystem MITM, no LLM-layer interception).
**Cost**: 5-15 min install + smoke test.
**Risk**: the highest of the 4. Don't pick this for AI-context tools, shell hooks, credential-adjacent infra, or anything publishing >50 releases/quarter.
**Examples**: standard apt/npm packages with strong provenance.

### Option D. Park
**What**: defer evaluation. Document the parked state in `memory/reference-<repo>-parked.md` with a re-audit date + checklist.
**When**: it fails the security pre-check OR an active sprint conflict OR there's insufficient external coverage to evaluate yet OR the repo is too young (<7 days, <14 days for high-blast-radius).
**Cost**: 2-5 min documentation.
**Output**: a parked dossier with explicit re-audit triggers + checklist.

## Decision matrix

| Tool class | Default option |
|---|---|
| Skill/prompt/methodology docs | A. doc-mine |
| Shell/PreToolUse hooks (proxies, compressors, wrappers) | B. clone-audit |
| MCP servers handling tokens or files | B. clone-audit |
| Standard apt/npm packages (jq, ripgrep, etc.) | C. install direct |
| Anything <7 days old | D. park (security pre-check fail) |
| AI/LLM-context-layer tools (compressors, hooks, proxies) | B. clone-audit |
| Dev workflow MITM (rebase tools, git wrappers) | B. clone-audit |
| Anything recommended without source reading | B. clone-audit (don't trust a testimonial alone) |
| Repo touching .ssh / wallets / credentials | B. clone-audit |

## Clone+audit workflow (Option B detailed)

When B is the chosen path:

1. **Clone shallow** to `sandbox/audit-<repo>/<repo>/` with `git clone --depth 50` (full history not needed for the audit).
2. **Pin to a release tag**: checkout the latest stable tag, NOT main. Note the commit hash for the audit report.
3. **Map the audit surface**: list:
   - `install.sh` / `Makefile` / `setup.py` / `package.json` postinstall. the install vector
   - `src/**/telemetry*` / `src/**/network*` / anything touching an HTTP client. the exfil surface
   - `hooks/` / any shell-MITM scripts. the blast radius
   - Credential reads (env vars: AWS_*, GITHUB_TOKEN, *_API_KEY, paths: ~/.ssh, ~/.aws, wallets)
   - `Cargo.toml` / `package.json` deps. the supply chain
4. **Spawn a subagent** if the surface is >5 files OR Rust/Go/multi-language. Brief it with: target paths, pre-existing security-issue links (cross-reference, don't substitute), deliverable format. Read-only. DO NOT install/build/run.
5. **Cross-reference open issues**: search `github.com/<owner>/<repo>/issues?q=security+OR+vulnerability+OR+injection`. Note any open + unfixed.
6. **Write the report** to `outputs/raw/agent/YYYY-MM-DD-<repo>-source-audit-<version>.md`:
   - Verdict line (top): GREEN-INSTALL-OK / GREEN-CAUTIOUS-INSTALL / RED-DO-NOT-INSTALL / NEEDS-MORE-INFO
   - Executive summary (5-8 sentences, concrete numbers/findings)
   - Section findings table (file:line citations + PASS/FAIL/CONCERN)
   - Top-5 risks (ordered by blast radius × likelihood)
   - Top-5 mitigations (concrete, testable)
   - Install recommendation (flags, env vars, source-build vs pre-built)

7. **Chat reply** with the verdict + a 5-line summary + a decision question.

## Install execution (post-GREEN verdict)

If the verdict allows install:

- **Source-build preferred** over a pre-built binary (compile-time gates like `option_env!()` close telemetry/exfil surfaces that pre-builts leave open).
- **Pin to the audited commit hash**, not `main` or `latest`.
- **Backup any config the install touches** (e.g. `~/.claude/settings.json`) to `sandbox/backups/YYYY-MM-DD-<file>-pre-<repo>.json` before modification.
- **Disable telemetry via an env var** even if compiled out (defense-in-depth).
- **Smoke test** before declaring done. For session-cached configs (settings.json hooks), note that activation requires a /restart.
- **Document re-audit triggers** in the reference dossier (specific file:line regressions, version bumps, behavior changes).

## Memory hooks

After every clone+audit run, regardless of verdict:
- Update or create `memory/reference-<repo>-<state>.md`
- States: `-parked.md`, `-installed.md`, `-rejected.md`, `-doc-mined.md`, `-adopted.md`
- Update the MEMORY.md index pointer with the current state + a 1-line description
- Append a 1-line entry to `memory/Decisions.md` linking to the dossier (only for adopt/install/reject. not for park)
- Add a Learnings.md entry ONLY if a non-obvious finding emerged (a toolchain quirk, an install footgun, an audit-methodology insight)

## Adversarial Stance (from a GSD audit)

**Starting hypothesis: the repo is REJECTED until a source review proves otherwise.** Stars, momentum, testimonials, viral GitHub trends. none of these flip the default. Only the source review does.

**Common ways repo-audit goes soft (catch yourself here):**
1. Downgrading a 7-day-rule violation to a WARNING because the repo "looks legitimate" (a known founder / known org / high stars). The rule is a hard NO. owner reputation doesn't waive it.
2. Treating "MIT license + active development" as proof of safety. A license says nothing about postinstall hooks, telemetry, or settings.json mutation.
3. Skipping the install.js / postinstall script read because "it's just npm install." That's exactly where the binary fetches + settings mutations live.
4. Anchoring on the FIRST audit finding and missing the second/third. Multiple sketchy items often co-exist (e.g. a binary fetch AND a settings.json mutation AND telemetry).
5. Skipping the "what does v2 cost" question. Some repos rope in a CLI replacement that quietly competes with your coding agent itself, or a paid SaaS dependency.

**Severity classification (mandatory on every finding):**
- **BLOCKER**: must fix before any install / adoption: a 7-day rule fail, a missing license, a postinstall hook with network egress + no opt-out, a settings.json mutation, credential handling, a telemetry server with no local-only mode, an owner-provenance fail (anon, <3mo account, <100 followers + zero prior repos).
- **WARNING**: note + proceed with mitigation: a postinstall with opt-out env vars, telemetry that's opt-in (not server-side), high-blast-radius tools (LLM context layer, dev workflow MITM) where doc-mine is the safer default than install.

## Anti-patterns

- ❌ Don't curl-pipe-bash an installer without reading it (per security-first)
- ❌ Don't trust a testimonial as a substitute for a source review (workflow shape differs, threat models differ)
- ❌ Don't install during an active deal sprint (a major delivery window)
- ❌ Don't auto-update. pin to the audited commit, manually re-audit before bumps
- ❌ Don't skip the backup of settings.json or any other config before the install touches it
- ❌ Don't substitute external coverage (HN/blog/social) for a source review on high-blast-radius tools

## Provenance

Created after a clone+audit pattern earned its stripes (PARKED → re-audit → GREEN-CAUTIOUS-INSTALL → installed). Codifying the workflow so future GitHub link drops get the structured 4-option triage by default instead of ad-hoc evaluation.

Related skills: `skills/self-audit.md` (internal repo audit), `skills/recall.md` (find prior audit verdicts before re-evaluating).
