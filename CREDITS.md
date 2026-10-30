# Credits & Acknowledgments

Utopia OS stands on a lot of other people's work. Many of its skills, patterns, and reference packs
were adapted or doc-mined from open-source projects and public research. This file credits them. If
you believe your work is used here and isn't credited (or is credited wrong), please open an issue and
it will be fixed.

## Runtime & foundation
- **Anthropic**, Claude Code (the coding-agent runtime this framework sits on) and Claude itself,
  which co-authored much of this repo. Several skills adapt patterns from Anthropic's public skills and
  cookbook (document handling, artifact building, MCP server construction).
- **Letta / MemGPT**, the tiered-memory framing (always-loaded core vs on-demand recall vs archival)
  that the memory system is modeled on.

## Skills & workflows
- **[garrytan/gstack](https://github.com/garrytan/gstack)** (MIT), the office-hours, CEO-review, and
  design-review planning skills, plus cross-cutting workflow patterns.
- **[gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done)**, the assumption-first
  scoping pattern behind the `scope` skill.
- **wwwazzz / senior-pm-prompt**, the PRD/spec generation skill.
- **199-biotechnologies / Boris Djordjevic**, the deep-research fan-out + adversarial-verify harness.
- **Andrej Karpathy**, the agent-loop and "LLM council" patterns behind the autoresearch skills.
- **Alireza Rezvani**, the AI-SEO, marketing-psychology, and content-humanizer skills.
- **[VectifyAI/OpenKB](https://github.com/VectifyAI)**, AGENTS.md structure and path-guard patterns.
- **[petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop)** (MIT, Peter Yang), the synonym-cycling / elegant-variation rule, the fake-profound-kicker "delete, don't rewrite" rule, and the detect-mode + minimum-effective-edit stances in the `anti-ai-slop` skill.

## Knowledge packs
- **[tw93/Waza](https://github.com/tw93/Waza)** (MIT), the `waza-skills/` pack.
- **[browser-use/browser-harness](https://github.com/browser-use)**, the `browser-skills/` pack.
- **[warpdotdev/oz-skills](https://github.com/warpdotdev/oz-skills)**, the `seo-aeo-audit/` and
  `mcp-builder-reference/` packs (see their bundled LICENSE files).
- **[Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill)** (MIT), the frontend taste rules.
- **[mzlogin/chinese-copywriting-guidelines](https://github.com/mzlogin/chinese-copywriting-guidelines)**
, typographic/copywriting structure references.

## Research the design draws on
- **UniCR** (arXiv 2509.01455), the conformal / abstention approach behind the confidence wrapper.
- **"Remember When It Matters" (Meta AI, arXiv 2607.08716)**, names *behavioral state decay*, which
  independently validates the session-survival + handoff design.
- **Google OSV**, the vulnerability data behind the dependency-check gate.
- Supply-chain-security research (the "contagious interview" / zip-hook attack literature) informs the
  `safe_unzip` and repo-hook audit defenses.

## Token efficiency
Running an operator agent all day is expensive; these tools keep the token spend down.
- **[TOON, Token-Oriented Object Notation](https://github.com/toon-format/toon)**, the compact
  serialization format that `scripts/memory/lib_toon.py` implements (YAML-style indentation + CSV-style
  tabular rows), roughly 30-60% fewer tokens than JSON for uniform arrays of objects. Shipped in this repo.
- **RTK (Rust Token Killer)**, a token-optimizing CLI proxy that rewrites verbose dev-tool output,
  cutting 60-90% of the tokens on routine operations. Used in the development workflow (not bundled).
- **[caveman](https://github.com/JuliusBrussee/caveman)**, prompt/token minimization discipline.

## Infrastructure
- **[LanceDB](https://github.com/lancedb/lancedb)**, the local vector store for archival memory.
- **[BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)**, the multilingual embedding model.

## Adapter-era security lifts (2026-07)
- **confirm_gate.py** (per-request approval IDs + hash-bound approvals) adapts patterns from OpenClaw and OpenAI Codex CLI.
- **fleet-root-policy.json + fleet_policy_check.py** (admin-immutable fleet floor) adapts the Codex `requirements.toml` managed-config layer.
- **evidence_ledger.py + evidence_completion_check.sh** (verification-evidence before "done") adapts hermes-agent's evidence-based completion gate.
- **bwrap_run.sh** sandboxes untrusted-content subprocesses so they cannot read credential paths; bubblewrap is by the containers/bubblewrap project.
- **fleet_board.py** (shared-editable-state agent coordination: board + event feed + optimistic CAS + capability tiers + suggest/accept) adapts the coordination model of workbench.md.
- **egress_proxy.py** (an egress MITM proxy that injects credentials on the wire so a tool never holds the secret) + **principal_floor.sh** (a bubblewrap secret-masking session floor) adapt the credential-injection + sandboxing model of paradigmxyz/centaur (iron-proxy).

## v2 additions (2026-10)
- **[elvisun/newsjack](https://github.com/elvisun/newsjack)** (MIT, Copyright (c) 2026 Elvis Sun). Four skills and two doctrine files vendored unchanged at commit 3b7fb82 in `skills-shared/newsjack/`, wired into the breaking-news lane.
- **[davidondrej/skills](https://github.com/davidondrej/skills)** (MIT). The skill-authoring principles in `knowledge/agent-skill-authoring-principles.md` (patterns, no code copied).
- **[herdrdev/herdr](https://github.com/herdrdev/herdr)** (Apache-2.0). Agent lifecycle states and the identity-pinned claim in the bus (`knowledge/herdr-runtime-lifts.md`; patterns, no code copied).
- **CaMeL** (Google DeepMind, "Defeating Prompt Injections by Design"). The taint-tracking idea behind `bus_taint_gate.py`.
- **MemCut** (arXiv 2610.21405). The finding that deletion fails on missed related records, which shaped `forget.py`.
- Rules 42 to 46 of `anti-ai-slop` restate an a16z article on empty-weight sentences in our own words; credit is in the skill.

## v3 additions (2026-10)
- **[elizaOS](https://github.com/elizaOS/eliza)** (MIT). Three patterns, no code copied: a confirmation counts only from a newer user message (`confirm_ledger.py`), forged security stamps are stripped from incoming text (`lib_provenance.py sanitize`), and benchmark results must cover exactly the selected cases, with scorers calibrated on known answers (`lib_case_coverage.py`, `gate_calibration.py`).
- **[Mainplane](https://github.com/mainplane-ai/mainplane)**. The idea of pointing a continuing session at a searchable log of the prior one instead of trusting the summary (`session_slimlog.py`), and the context meter (`context_meter_hook.sh`). Pattern only.
- **[plurnk-bench](https://github.com/plurnk/plurnk-bench)**. The reporting format in `bench_stats.py` (Wilson intervals, paired tests, "not separated") and the addressable-memory idea behind `addr.py`. Pattern only.
- **gbrain** (docs/guides/open-loops.md and memory-trust.md). The open-loop rules in `open_loops.py` and the `origin` field on provenance stamps. Pattern only.
- **Compact-Bench** (arXiv 2610.31710). The finding that a regex extractor keeps far more recurring details than an LLM summary, which shaped `compact_anchor_extract.py`.
- **ClawMMU** (arXiv 2610.28093). The authority cap in recall: a curated path does not lend its boost to an entry formed from untrusted content.
- **arXiv 2610.37332** on instruction stacks changing in bursts, behind `instruction_stack_diff.py`.

---

Where an upstream project ships a LICENSE, that license is preserved in the relevant subdirectory
(e.g. `knowledge/mcp-builder-reference/LICENSE.txt`). This project as a whole is MIT-licensed; the
upstream licenses govern their respective files.
