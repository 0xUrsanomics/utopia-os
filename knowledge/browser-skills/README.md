---
name: browser-skills (ported from browser-harness)
description: Site-mechanics knowledge ported from browser-use/browser-harness. CSS selectors, URL patterns, API endpoints, and anti-bot quirks for commonly-automated sites.
type: reference
---

# Browser Skills. Ported Knowledge Pack

Markdown-only port of selected `interaction-skills/` and `domain-skills/` from
[browser-use/browser-harness](https://github.com/browser-use/browser-harness). **No code ported. pure
documentation.** The harness runtime itself is not included here.

## Provenance

- **Source:** `browser-use/browser-harness` (HEAD of `main`, pinned to a commit hash at port time)
- **License:** MIT (Copyright 2026 Browser Use)
- **Port scope:** the `interaction/` + selected `domain/` markdown docs only

Keep the upstream MIT attribution above intact in any redistribution.

## Why only the docs

The interaction and domain docs are pure markdown: zero install risk, immediate research value. The
harness *runtime* is a separate concern:

1. Self-modifying-code designs deserve a community CVE-review window before any install.
2. The runtime attaches to a *real* logged-in Chrome profile, so wallet / mail / banking blast radius
   is real. Pilot only in a dedicated throwaway profile, never your primary session.
3. What's here is the site-mechanics knowledge, decoupled from that runtime.

## What's here

### `interaction/`: site-agnostic web mechanics

The substantive, non-stub interaction docs:

| File | What it covers |
|---|---|
| `connection.md` | CDP daemon startup, tab/page management primitives |
| `dialogs.md` | Native alert/confirm/prompt/beforeunload. JS-thread freeze, accept/dismiss patterns |
| `tabs.md` | Multi-tab orchestration, tab focus model, attach/detach |

Upstream also ships heading-only stubs (cookies, iframes, downloads, uploads, screenshots, etc.). Those
are refresh candidates if upstream fills them in; they were not ported.

**Intentionally excluded:** any doc describing upload of local browser cookies to a third-party cloud.
Not relevant here, and excluded so it doesn't sit in `knowledge/` as latent instruction surface.

### `domain/`: per-site knowledge

Data-extraction and automation recipes for commonly-automated sites. Most are read-only scraping
recipes that prefer a site's public REST/JSON API over the browser; a few cover authenticated UI
automation.

| Domain | File(s) | Kind |
|---|---|---|
| `github/` | repo-actions.md, scraping.md | REST API + repo actions (star/watch via form submit) |
| `coingecko/` | scraping.md | Market data via public API |
| `coinmarketcap/` | scraping.md | Market data via internal JSON API |
| `tradingview/` | scraping.md | Screener/scanner + symbol search APIs |
| `polymarket/` | scraping.md | Prediction-market data via Gamma API + DOM fallback |
| `sec-edgar/` | scraping.md | Filings + XBRL financial data APIs |
| `arxiv/` | scraping.md | Paper search/metadata via Atom API |
| `hackernews/` | scraping.md | Front page + Algolia + Firebase APIs |
| `reddit/` | scraping.md | JSON API + logged-in DOM extraction |
| `substack/` | scraping.md | Publication REST API |
| `producthunt/` | scraping.md | Launch/leaderboard DOM extraction |
| `youtube/` | scraping.md | oEmbed + `ytInitial*` blob extraction |
| `archive-org/`, `wayback-machine/` | scraping.md | Internet Archive CDX + metadata APIs |
| `package-registries/` | npm-pypi.md | npm/PyPI registry + download-stats APIs |
| `linkedin/` | invitation-manager.md | Bulk connection-invitation management (authenticated) |
| `gmail/` | compose.md | Compose-dialog mechanics (authenticated) |
| `tiktok/` | upload.md | TikTok Studio upload flow (authenticated) |
| `expedia/` | automation.md | Hotel-search automation via URL params |
| `loom/` | folder-enumeration.md | Library-folder enumeration (authenticated) |

## Audit notes

All ported files were scanned for API keys, webhooks, exfil URLs, and references to non-public
endpoints. Clean: the only network references are the documented target sites (github.com,
registry.npmjs.org, pypi.org, etc.).

## How to use

These are **reference material**, not runnable skills. Read them when you need to interact with one of
these sites and want to skip the discovery step.

1. **Verify currency**: selectors and URL patterns drift. Spot-check against the live site before
   relying on a multi-step automation.
2. **Prefer APIs**: many docs (e.g. `package-registries/`) explicitly say "never use a browser" because
   the site has a full REST API. Take that path first.
3. **Treat anti-bot notes as starting points, not guarantees**: sites with aggressive bot detection
   (e.g. `tiktok/`) can change behavior at any time.

## Refresh policy

Re-pull from upstream when a selector / URL pattern goes stale in real use, when upstream fills in the
stub interaction docs, or when a new domain you care about appears upstream. Re-pull uses the same
pinned-commit `curl` pattern as the original port.
