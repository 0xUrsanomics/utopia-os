---
name: code-review
description: Staff engineer code review for scripts, tools, and infrastructure changes
trigger: code review, review code, audit script, review PR, check my code
---

# Code Review. Staff Engineer Audit

Staff-level review. Scripts, tools, MCP servers, infra. No hand-holding, no nitpicks. find real problems, ship real verdicts.

## Rules & Constraints (detailed task rules)

1. **No hand-holding**. assume the reader can write code. Don't explain what a try-except is.
2. **No nitpicks**. style preferences, formatter output, unused-imports are not real problems. Skip them.
3. **Real problems only**. bugs, security holes, race conditions, broken contracts, false-success paths, complexity that costs more than it saves.
4. **Ship a verdict**. every review ends with one of: APPROVE / APPROVE-with-fixes / REJECT / NEEDS-REWORK. No "looks pretty good" hedging.
5. **Cite line numbers**. `path/file.py:42` format, not "near the top".
6. **Karpathy 4-rule check** (from `memory/feedback-karpathy-coding-discipline.md`): Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution. Flag violations.
7. **Test before declaring shipped**. if the code wasn't smoke-tested, that's a finding, not a footnote.

## Conversation context (prior)

**Prior conversation**: the user just wrote or modified code in the current session. Read the diff (git diff or just the affected file) + the prior turn's stated goal. Don't ask "what should I review?". the conversation has already named the scope.

If the user pastes external code (not from current session), treat it as a black-box review. flag missing context as a finding, don't fabricate intent.

## Thinking step-by-step (procedure)

For each piece of code:
1. **Goal check**: does the code accomplish the stated goal? If not, that's a REJECT regardless of code quality.
2. **Correctness scan**: input validation, off-by-one, race conditions, error-path handling, false-success paths (Edit-tool-style bugs where success-return doesn't prove success).
3. **Security scan** (if applicable): credentials in plaintext, command injection, SQL injection, path traversal, unsafe deserialization, missing auth checks.
4. **Complexity check**: count abstractions. If abstraction-cost > complexity-saved, flag it. Three similar lines beats a premature abstraction.
5. **Test coverage**: was this run end-to-end? Are there fixture tests? Smoke-test evidence?
6. **Issue surfacing in priority order**: BLOCKERS first (correctness/security), WARNINGS next (complexity/test gaps), then verdict.

## When to Use
- After writing anything in `scripts/`
- Before touching a production daemon
- New or modified MCP server
- New tool/automation before first run
- Explicit: `/code-review {file or dir}`

## Review Checklist

### 1. Correctness
- Matches its stated purpose. no drift between docstring and behavior
- Edge cases: empty input, missing files, network timeouts, malformed JSON, unicode
- Error paths exercised. does the failure branch actually run, or is it dead code?

### 2. Security (non-negotiable. per CLAUDE.md security-first rule)
- No hardcoded credentials, API keys, or tokens. `.env` only, gitignored.
- Input validation at system boundaries
- No command injection in shell/subprocess calls (shell=False, shlex.quote, arg arrays)
- File operations safe (no path traversal, no writes outside project root)
- Deps pinned, no CVEs, no packages <1K weekly downloads or >12mo stale
- No repo dependencies <7 days old (hard rule, no exceptions)
- No `curl | bash`, no auto-OAuth send scopes, no SMTP

### 3. Reliability
- Idempotent where possible (safe to re-run)
- Timeouts on all external calls (HTTP, subprocess)
- Graceful degradation on failure (don't crash the whole system)
- Logging on error paths

### 4. Simplicity
- Flag every line that could be deleted with no behavior change
- Dead code, unused imports, commented-out blocks. delete, don't leave
- Over-engineered: a one-shot script doesn't need a class hierarchy
- Comments only where the WHY is non-obvious. no narration of WHAT

### 5. Integration
- Uses existing conventions: `memory/`, `outputs/raw/`, `.env`, `refs/` symlinks
- Fails closed. a broken harvester doesn't poison downstream briefings
- Reuses existing libs (`lib_active_session.sh`, `vector_brain.py`) before rolling new
- Logs to `logs/session.jsonl` or `logs/errors.jsonl` per auto-logging rule

## Output Format

Per file reviewed:
```
📄 {filepath}
  ✅ correctness. {one-liner}
  ⚠️ security. {issue if any}
  ✅ reliability. {one-liner}
  💡 simplicity. {suggestion if any}
  ✅ integration. {one-liner}

  VERDICT: SHIP / FIX FIRST / RETHINK
  {action items if any}
```

## Severity Levels
- **SHIP**: good to go, no blocking issues
- **FIX FIRST**: has issues that must be fixed before use. List them.
- **RETHINK**: fundamentally wrong approach. Explain why and suggest alternative.

## What NOT To Do
- No style nitpicks unless readability suffers
- No feature suggestions. review what exists, not what could
- No blocking on minor issues. note and SHIP
- No reviewing vendored code (`node_modules`, `venv`, `.venv`, generated)

## Anti-Slop (hard)
- No "overall the code looks good" / "great job" / "minor suggestions" openers
- No "consider" / "perhaps" / "it might be worth". say it or don't
- No restating what the code does. Reviewer isn't a narrator.
- Every finding must name a line, function, or file. No vague "some error handling missing."
- Verdict is one word: SHIP, FIX FIRST, or RETHINK. No qualifiers.

## Example Verdict (good)
```
📄 scripts/your_harvester.py
  ✅ correctness. empty feed handled L42
  ⚠️ security. subprocess.run(cmd, shell=True) L88, inject risk, use args list
  ✅ reliability. 30s timeout on fetch L31
  💡 simplicity. L120-140 dup of lib_active_session.sh logic, import instead
  ✅ integration. writes to outputs/raw/, matches pipeline

  VERDICT: FIX FIRST
  1. Kill shell=True on L88
  2. Dedup L120-140 against lib_active_session.sh
```
