---
title: SEO + AEO Audit Reference (ported from warpdotdev/oz-skills)
source: https://github.com/warpdotdev/oz-skills/tree/main/.agents/skills/seo-aeo-audit
license: MIT
attribution: Original work © Warp Inc. Ported 2026-05-06.
purpose: Reference docs for auditing/improving search engine visibility (SEO) + AI citation visibility (AEO).
---

# SEO + AEO Audit — Reference Materials

Ported from `warpdotdev/oz-skills` (MIT). Reference material for when a site becomes a real inbound
funnel and needs search-visibility and AI-citation tuning.

Keep the upstream MIT attribution (© Warp Inc.) intact in any redistribution.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Skill spec covering the SEO + AEO audit workflow |
| `references/json-ld-templates.md` | JSON-LD structured-data templates for common page types |
| `scripts/lighthouse.sh` | Local Lighthouse CLI runner (perf + accessibility + SEO) |
| `scripts/pagespeed.sh` | Google PageSpeed Insights API caller (needs `PAGESPEED_API_KEY`) |
| `scripts/search-console-export.mjs` | Google Search Console export (needs `GSC_ACCESS_TOKEN`) |

## When to use

- A site ships and becomes part of an inbound discovery funnel.
- You need to audit a site for SEO opportunity.
- AEO check: whether AI tools (Claude, ChatGPT, Perplexity, Gemini) cite/reference content as expected.
- Reference for JSON-LD structured-data templates when implementing schema.org markup.

## When NOT to use

- Don't run the scripts requiring API keys (`PAGESPEED_API_KEY`, `GSC_ACCESS_TOKEN`) without confirming
  free-tier limits + budget tracking.
- These are reference docs, not an auto-loading skill.
- Don't redistribute externally without preserving the MIT attribution.

## Attribution

Per MIT (see `SKILL.md` frontmatter `license: MIT`):

```
Copyright (c) Warp Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy of this software...
```

Source: https://github.com/warpdotdev/oz-skills/blob/main/.agents/skills/seo-aeo-audit/
