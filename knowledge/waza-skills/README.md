# Waza Skills. Doc-Mined for Adaptation

## Provenance

- **Source**: [tw93/Waza](https://github.com/tw93/Waza) (pinned to a commit hash at port time)
- **License**: MIT
- **Port method**: direct fetch from `raw.githubusercontent.com` pinned to the commit. No third-party
  package-manager install.

Keep the upstream MIT attribution above intact in any redistribution.

## What's here

Three of Waza's skills, ported as reference docs (not directly-invocable skills):

| File | What it is |
|---|---|
| `think/SKILL.md` | Pre-code skeptic primitive: turn a rough idea into a validated, approved plan before writing code. |
| `hunt/SKILL.md` | Systematic debugging with root-cause-first discipline: no fix until you can state the cause in one sentence. |
| `write/SKILL.md` | Prose rewriter that strips AI writing patterns; bilingual (English + Chinese) dispatch. |
| `write/references/write-en.md` | The English-side anti-AI-slop rewriter rules. Useful as-is. |

Not ported: Waza's `design`, `check`, `health`, `read`, and `learn` skills (each overlaps a workflow
better served by a dedicated tool), and `write/references/write-zh.md` (Chinese-only).

## Adapting these

These are reference docs for inspiration, not drop-in skills. Before turning one into a real skill:

1. **think** → adapt as a planning skill, or fold it into an existing scope/plan step. Strip the
   original's voice and match your own register.
2. **hunt** → adapt as a debugging skill. Wire it to your own error log + failure-history source so the
   root-cause discipline is grounded in real prior failures.
3. **write** → the reusable asset is the *bilingual structure* and the anti-slop rule set, not the
   verbatim prose. Merge the rules into your own anti-slop / humanizer skill rather than shipping it
   standalone.

Adaptation means re-authoring against your own voice and tooling, not copy-paste.
