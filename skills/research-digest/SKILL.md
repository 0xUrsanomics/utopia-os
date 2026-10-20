---
name: research-digest
description: Weekly full-read digest of the week's research reports (research firms, banks, central banks, regulators, multilaterals). Daily harvesters flatten a report to one line under a per-run cap; this lane gives the 4 to 6 most relevant reports a full read with numbers and their basis, a read on what it means for the operator's work, and trust caveats. A cheaper reader model extracts quotes, a script verifies them, the main model judges.
trigger: research digest, weekly research, report digest, research roundup
---

# Research Digest: weekly full read of reports

## Why this exists

Long research reports must not get lost in a fast signal flow. Daily harvesters (RSS, email, chat channels) catch these items but flatten each one to a single signal and cap items per run, so a 30-page report competes with breaking news and loses. This lane reads the week's best reports in full, once a week (for example Saturday morning).

## Inputs

1. **Feeds:** the last 7 days of items from feeds you have tagged as research in your feed reader (ignore its seen-database for this pass, so items already surfaced as one-liners still qualify). The feed harvester itself is not shipped in this repo.
2. **Email:** `python3 scripts/pipeline/email_research_senders.py query --days 7` prints a Gmail search query built from your sender allowlist (example list shipped next to it). Run it through your Gmail MCP search (about 60 results), then fetch metadata for subject and sender. Senders marked `sponsored` are never picked as research.
3. **Already digested:** list `memory/Context/` and `outputs/raw/research-digest/` and skip anything already ingested.

## Procedure

1. Post a start heartbeat to the operator channel.
2. Build the candidate list (feeds plus email). Drop product promos, event invites, job posts, sponsored content, and press items with no research content (a routine speech unrelated to your domain).
3. **Pick 4 to 6** by: (a) relevance to the operator's actual work and service line; (b) substance (a report with data beats an opinion newsletter); (c) source weight (central bank, regulator, multilateral or tier-1 research beats a blog). Prefer at least one source from outside your own industry's echo chamber (a bank, a regulator, a multilateral) when the week has one.
4. **Full read of each pick: a reader model extracts, a script verifies, the main model judges.**
   a. **Archive first:** `sandbox/archive/reports/<YYYY-MM-DD>-<slug>/`. PDF via curl, then `pdftotext -layout file.pdf source.txt`. A web page via the publisher's JSON or API, or a fetch, saved as `source.txt`. An email body saved as `source.txt`. If paywalled, say so and digest only the public part.
   b. **Gate the reader model (security).** If the reader is an external CLI, check its version first and use it only if that version is marked reviewed in your stand-down registry (`scripts/security/check_standdown.py <cli-name>`) AND that release is at least 7 days old. CLIs that auto-update can change under you between runs. Otherwise skip to step e and read inline. Log every reader outcome (`reader_ok` or `reader_fallback`).
   c. **Reader extraction.** Give a cheaper, long-context model the archived file and this instruction: "Read the file <abs path>/source.txt (a research report). Return ONLY a JSON array of the 15 to 25 most important claims, each {\"claim\": short sentence, \"number\": the exact number string as written (or \"\" if none), \"quote\": an exact verbatim substring of the file, max 200 chars}. Include the report's stated method, sample, period and any caveat as claims too. No commentary." Run it with a timeout (about 150 s) and save the output as `claims.json`. Run it without permission-bypass flags.
   d. **Verify mechanically:** `python3 scripts/eval/verify_claims.py source.txt claims.json > verified.json`. Use only `verified` claims. A claim is verified only if its quote is a verbatim substring of the source AND its number sits inside that quote. Reader models can fabricate quotes, so rejected claims are DROPPED, never paraphrased back in.
   e. **Fallback:** if the reader times out, returns no JSON, or verify exits 1 (more than half rejected), the main model reads that report itself, and the run log says `reader_fallback`.
   f. **The main model judges.** Using the verified claims plus a skim of the source's headings, summary and conclusion, write the section in step 5. The judgment (what it means, how much to trust it) is always the main model's, never the reader's. Read the charts that carry numbers yourself when the text does not state them.
5. **Write one section per report** in `outputs/raw/research-digest/<YYYY-MM-DD>.md`:
   - title, publisher, date, URL, archive path
   - **Read straight for us** (2 to 4 bullets, verdict first: good, bad or neutral for the operator's work, and why)
   - **Numbers with basis** (every number carries its basis: disclosed-only, sample size, period, source dataset). A caveat that changes how a number reads travels WITH the number.
   - **How much to trust it** (method gaps, sponsor or conflict of interest, small-base percentages, pending deals)
   - **Coverage of your region or niche** (what it says, or "none")
6. If a report will be referenced again (a recurring quarterly series, a regulator framework, a multilateral report), also write or update a `memory/Context/<slug>.md` dossier, and cross-link any existing dossier it confirms or contradicts.
7. **Index:** `python3 scripts/memory/vector_brain.py index-append --paths <digest file>`. Never a full `index` rebuild for this.
8. **Chat summary** to the operator, at most about 15 lines: one line per report (publisher, title, verdict), then the single most useful number with its basis, then the digest path. Attach the digest file.
9. Log one line to `logs/session.jsonl` (`category=research-digest`, picks, candidates_seen, feeds_failed).

## Hard rules

- No em or en dashes. Anti-slop rules apply (`skills-shared/anti-ai-slop/SKILL.md`). Never narrow a claim beyond what the source says.
- Never present a global total as regional demand. Many reports have no data at all for a given region; say "none" instead of inferring.
- Stay inside the operator's service line. A regulatory report is read as "what it means for the work", never as legal advice.
- Empty week (no candidate clears step 2): send one short line saying so; do not pad.
- Budget: stop at about 60K tokens or 30 tool calls. A partial digest with 2 full reads beats a timeout.
