---
name: redact
description: Per-entry redaction primitive for memory/ + outputs/ files. Strips matching content, replaces with [REDACTED YYYY-MM-DD reason] marker, logs to logs/redact-log.jsonl. Use when a credential, PII, or other sensitive content slipped into a tracked file.
trigger: redact, strip, sanitize, scrub, /redact, remove sensitive
---

# /redact. Memory audit primitive

Strip sensitive content from any tracked file with an audit trail. Pattern modeled on the managed-agent memory feature (filesystem audit + per-entry redaction), adapted to a solo-operator stack.

## When to use

- A credential, API key, or token slipped into a memory file or output
- A name, phone number, or address you didn't mean to log durably
- A quote from a private conversation that shouldn't sit in a corpus that may go public (e.g. for a public review or backups)
- Any case where you want a clean strip + audit trail (NOT silent deletion)

## When NOT to use

- Removing entire memory files → use `git rm` + commit
- Bulk cleanup → use the `dreaming` skill's pruning pass instead
- Nothing got tracked yet → just don't write it

## Workflow

### Invocation

```
/redact <file-path> "<search-pattern>" "<reason>"
```

Examples:
```
/redact memory/Context/partner-event.md "sk-XXXX..." "leaked API key"
/redact outputs/raw/agent/2026-04-25-self-audit.md "<counterparty name>" "PII. anonymize counterparty"
/redact memory/Decisions.md "+1555..." "phone number leaked"
```

### Steps the skill executes

1. **Read the target file.** Verify it exists and is in `memory/` or `outputs/` (refuse on `.env`, `.ssh/`, anything outside the workspace).
2. **Find matches.** Show every line containing the pattern (with line numbers). User confirms before any change.
3. **Replace each match in place** with `[REDACTED YYYY-MM-DD reason="<reason>"]` (pattern length collapsed to the marker).
4. **Append audit log** to `logs/redact-log.jsonl`:
   ```json
   {"ts":"<ISO>","file":"<path>","pattern_hash":"<sha256>","occurrences":<count>,"reason":"<reason>","actor":"agent"}
   ```
   Hash the pattern (don't log the secret itself).
5. **If file is in git:** suggest `git commit -m "redact: <reason>"` so the strip is preserved in history (the unredacted version still lives in older commits. that's a separate cleanup if needed).

### Hard rules

- **Never silently strip.** Always show matches first + ask.
- **Never log the secret itself** in `redact-log.jsonl`: only the hash + count + reason.
- **Refuse on disallowed paths**: `.env`, `.ssh`, anything ending in `.key/.pem`, `.gitignore`d files (per `git check-ignore`). Those need different handling.
- **Pattern is literal substring** by default. For regex, use `--regex` flag.
- **One file per invocation.** Bulk redaction = run multiple times. Audit clarity > batch convenience.

### What about git history?

This skill only redacts the working copy. The pre-redaction version still exists in git commits. If the leaked content needs to be purged from history too:

1. Run `/redact` first (working copy clean)
2. THEN run `git filter-repo --replace-text <patterns-file>` (manual, careful, force-push needed): separate workflow, NOT in this skill
3. Sync the redaction with backups: old copies will eventually rotate out

The default flow is "redact + commit + move on." Filter-repo only when truly catastrophic (key in a public repo, etc.).

## Audit log format

`logs/redact-log.jsonl`:

```json
{"ts":"2026-04-25T19:00:00Z","file":"memory/Context/example.md","pattern_hash":"a3f5...","occurrences":2,"reason":"phone number leaked","actor":"agent","session_id":"<if available>"}
```

The hash is `sha256(pattern)`. Reason field is free-form but should be short + truthful.

## Composition with other skills

- **Before:** `/save` (don't extract sensitive content into memory in the first place. leak is the failure mode this catches)
- **After:** `git commit` (preserve the strip in source control)
- **Periodic:** the `dreaming` skill could optionally surface "files containing `[REDACTED ...]` clusters" for review (concentrated redactions = signal of a leaky source)

## Why this exists

Three reasons:

1. **Solo-operator hygiene.** Most memory leaks are accidental (a paste, a forgotten PII strip). Cheap fix when you spot it; expensive fix when it sits.
2. **Audit-clean replacement for `sed -i` deletions.** `sed -i 's/secret//'` is a black hole. no record. `/redact` leaves a marker + log. Future-you (or an audit) can see what was removed and why.
3. **Feature parity with managed-agent memory hygiene.** The same primitive built into enterprise agent platforms, at a smaller-blast-radius operator scale, so you can reason about memory hygiene with the same vocabulary.

## Implementation notes

For now this skill is a behavior contract. when triggered, follow the workflow above using Read/Edit/Bash tools. A scripted implementation at `scripts/redact.py` is a future move if the skill gets invoked >5x and the manual flow gets repetitive.
