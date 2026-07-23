# Credits & Acknowledgments

Utopia OS stands on a lot of other people's work. Many of its skills, patterns, and reference packs
were adapted or doc-mined from open-source projects and public research. This file credits them. If
you believe your work is used here and isn't credited (or is credited wrong), please open an issue and
it will be fixed.

## Runtime & foundation
- **Anthropic** — Claude Code (the coding-agent runtime this framework sits on) and Claude itself,
  which co-authored much of this repo. Several skills adapt patterns from Anthropic's public skills and
  cookbook (document handling, artifact building, MCP server construction).
- **Letta / MemGPT** — the tiered-memory framing (always-loaded core vs on-demand recall vs archival)
  that the memory system is modeled on.

## Skills & workflows
- **[garrytan/gstack](https://github.com/garrytan/gstack)** (MIT) — the office-hours, CEO-review, and
  design-review planning skills, plus cross-cutting workflow patterns.
- **[gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done)** — the assumption-first
  scoping pattern behind the `scope` skill.
- **wwwazzz / senior-pm-prompt** — the PRD/spec generation skill.
- **199-biotechnologies / Boris Djordjevic** — the deep-research fan-out + adversarial-verify harness.
- **Andrej Karpathy** — the agent-loop and "LLM council" patterns behind the autoresearch skills.
- **Alireza Rezvani** — the AI-SEO, marketing-psychology, and content-humanizer skills.
- **[VectifyAI/OpenKB](https://github.com/VectifyAI)** — AGENTS.md structure and path-guard patterns.
- **[petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop)** (MIT, Peter Yang) — the synonym-cycling / elegant-variation rule, the fake-profound-kicker "delete, don't rewrite" rule, and the detect-mode + minimum-effective-edit stances in the `anti-ai-slop` skill.

## Knowledge packs
- **[tw93/Waza](https://github.com/tw93/Waza)** (MIT) — the `waza-skills/` pack.
- **[browser-use/browser-harness](https://github.com/browser-use)** — the `browser-skills/` pack.
- **[warpdotdev/oz-skills](https://github.com/warpdotdev/oz-skills)** — the `seo-aeo-audit/` and
  `mcp-builder-reference/` packs (see their bundled LICENSE files).
- **[Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill)** (MIT) — the frontend taste rules.
- **[mzlogin/chinese-copywriting-guidelines](https://github.com/mzlogin/chinese-copywriting-guidelines)**
  — typographic/copywriting structure references.

## Research the design draws on
- **UniCR** (arXiv 2509.01455) — the conformal / abstention approach behind the confidence wrapper.
- **"Remember When It Matters" (Meta AI, arXiv 2607.08716)** — names *behavioral state decay*, which
  independently validates the session-survival + handoff design.
- **Google OSV** — the vulnerability data behind the dependency-check gate.
- Supply-chain-security research (the "contagious interview" / zip-hook attack literature) informs the
  `safe_unzip` and repo-hook audit defenses.

## Token efficiency
Running an operator agent all day is expensive; these tools keep the token spend down.
- **[TOON — Token-Oriented Object Notation](https://github.com/toon-format/toon)** — the compact
  serialization format that `scripts/memory/lib_toon.py` implements (YAML-style indentation + CSV-style
  tabular rows), roughly 30-60% fewer tokens than JSON for uniform arrays of objects. Shipped in this repo.
- **RTK (Rust Token Killer)** — a token-optimizing CLI proxy that rewrites verbose dev-tool output,
  cutting 60-90% of the tokens on routine operations. Used in the development workflow (not bundled).
- **[caveman](https://github.com/JuliusBrussee/caveman)** — prompt/token minimization discipline.

## Infrastructure
- **[LanceDB](https://github.com/lancedb/lancedb)** — the local vector store for archival memory.
- **[BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)** — the multilingual embedding model.

## Adapter-era security lifts (2026-07)
- **confirm_gate.py** (per-request approval IDs + hash-bound approvals) adapts patterns from OpenClaw and OpenAI Codex CLI.
- **fleet-root-policy.json + fleet_policy_check.py** (admin-immutable fleet floor) adapts the Codex `requirements.toml` managed-config layer.
- **evidence_ledger.py + evidence_completion_check.sh** (verification-evidence before "done") adapts hermes-agent's evidence-based completion gate.

---

Where an upstream project ships a LICENSE, that license is preserved in the relevant subdirectory
(e.g. `knowledge/mcp-builder-reference/LICENSE.txt`). This project as a whole is MIT-licensed; the
upstream licenses govern their respective files.
