# newsjack skills (vendored, unchanged)

Copied unchanged from github.com/elvisun/newsjack at commit 3b7fb82, MIT license (see `LICENSE`, Copyright (c) 2026 Elvis Sun). Only four skills plus the two doctrine files they reference are included:

| File | Upstream role |
|---|---|
| `newsjack-triage.md` | routes fresh stories by brand standing (pitch_ready, big_story, watch) |
| `newsworthiness-check.md` | is this story worth acting on at all |
| `story-origin-check.md` | is this a new story or a re-run of an old one |
| `angle-generator.md` | writes angles for stories that passed triage |
| `ETHICS.md`, `WHY-NOT-SPAM.md` | the ethical floor the four skills inherit |

## Why the files are not edited

License fidelity and easy updates. The upstream files keep their own style, including em dashes, and reference paths such as `skills/ETHICS.md` from the upstream layout. Read those as the files in this folder. This repo's dash rule does not apply to vendored files.

## What is not included

No upstream CLI and no Medialyst MCP. The upstream skills call a `news-search` skill that this repo does not ship. Upstream already allows a fallback to ordinary web search; with no search at all, a caller should pass the clustered sources it already has and accept `unclear` when they are not enough.

## How they are used here

- A brand standing profile is required input. Example (fabricated company): `knowledge/newsjack-profile.example.md`.
- `scripts/pipeline/breaking_lane.py` (angle step) shows one way to wire them into a news lane that runs in shadow mode first.
- Local deviation in that wiring: `story-origin-check` assumes a news search. A caller with no tools has the model judge origin from the clustered sources the lane passes in, and it must answer `unclear` when that is not enough.

## Updating

Fetch the same paths at a newer commit, diff, read every change (these files are instructions the model will follow, so treat them as untrusted until read), run `python3 scripts/security/skill_linter.py skills-shared/newsjack`, then bump the commit hash here.
