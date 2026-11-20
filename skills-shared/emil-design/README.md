# Emil Kowalski design skills (vendored)

## Provenance

- **Source**: [emilkowalski/skills](https://github.com/emilkowalski/skills), pinned to commit `a81dbca07f2217b7103e510c0f13f8d5b017afc9`
- **License**: MIT, see the bundled `LICENSE` (Copyright (c) 2026 Emil Kowalski)
- **Port method**: manual copy of the markdown files at that commit. No scripts, and not the upstream `npx` installer (unpinned, runs code).

Keep the upstream MIT attribution and `LICENSE` intact in any redistribution. The files below are unchanged from upstream; only this README is local.

## What's here

- `emil-design-eng/`: UI polish and motion philosophy
- `break-ui/`: stress a component with worst-case data (long names, empty states, non-Latin text, emoji)
- `pick-ui-library/`: opinionated library picks per task
- `review-animations/`: review motion code against a strict bar
- `ui-cheatsheet.md`, `performance-cheatsheet.md`

## Local rules

Any library named in `pick-ui-library` still goes through the package checks in `CLAUDE.md` (downloads, last publish, CVEs, minimum age) before install. Where this pack conflicts with the repo's own `knowledge/taste-skill-frontend-rules.md` or `skills-shared/anti-ai-slop` rules, the repo rules win. The vendored files keep upstream's em dashes; the repo's no-dash rule covers only what we write. `break-ui` mentions a `prototype` skill that is not included here. To update, read the upstream diff at a new commit, then re-copy.
