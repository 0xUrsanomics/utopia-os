# Agent skill-authoring principles

Five rules for writing skills that the agent actually loads and follows. Ideas taken from the `effective-agent-skills` guidance in davidondrej/skills (read as reference, not installed or copied). Only the points not already covered by `skills-shared/skill-creator/SKILL.md` and `scripts/security/skill_linter.py` are kept here.

## 1. The description says WHAT and WHEN, never HOW

The description is the only text the agent sees before it decides to load a skill. If the description summarizes the workflow steps, the agent tends to follow that summary and skip the body. Write three things: what the skill does, when to fire it, and how it differs from sibling skills. Keep the procedure out of the description. The `trigger:` frontmatter already handles routing; this rule is about not putting the "how" where it replaces the body. It explains a common failure: a skill that fires and then under-executes.

## 2. Capability primitive or process primitive

There are two valid skill shapes. Name which one you are building.

- **Capability primitive.** A thin wrapper over a deterministic script or CLI. The logic lives in code; SKILL.md teaches the invocation (30 to 80 lines of command examples). Use it when the bottleneck is "the agent cannot do X".
- **Process primitive.** A method the agent follows. Pure prompt, no scripts. Reliability comes from an explicit checklist and a validation loop. Use it when the bottleneck is "the agent's output or process quality is poor".

## 3. Match strictness to how fragile the task is

Scale how rigid the instructions are to the cost of a wrong move:

- loose heuristics when many approaches are valid (code review);
- pseudocode or a template when there is a preferred pattern but variation is fine (a report format);
- exact scripts and strict step lists when the workflow is fragile or must be consistent (migrations, patching a document, any verify loop that gates a send).

## 4. References one level deep, never chains

Link reference files directly from SKILL.md. Never SKILL.md to a.md to b.md to c.md: the agent previews nested files only partly and misses instructions. Add a table of contents to any reference file over about 100 lines.

## 5. The colon-in-description YAML trap

Strict YAML parsers read `: ` (colon then space) inside an UNQUOTED description as a nested mapping, even though Claude Code's parser accepts it. If a description needs a colon mid-sentence, single-quote the whole value and double any inner apostrophes. Also keep `<` and `>` out of frontmatter, since they can inject into the system prompt. Skills used only by Claude Code are unaffected; this bites any skill you share to an agent runtime with a strict parser.

## Lesson: a shared command denylist (not built as code)

The same source runs ONE denylist file enforced across every agent CLI through a PreToolUse hook. The transferable lessons:

- One source-of-truth denylist beats per-agent config that drifts apart. If you run several agents, consider a fleet-shared list.
- Block only the irreversible or catastrophic: `rm -rf` on `/` or home, `dd`, `mkfs`, curl piped to a shell, `git push --force`, repo deletion, token exfiltration. Leave locally recoverable commands allowed (`rm -rf node_modules`, `git clean`), or over-blocking makes the agent useless.
- Known false positive: a harmless command whose ARGUMENT text contains a dangerous-looking string (a prompt that mentions `git push --force`) gets regex-blocked. Workaround: put the text in a file.
- It is a seatbelt against accidents, not a sandbox against a hostile agent. Obfuscation such as `python -c "shutil.rmtree(...)"` slips past any regex. For containment use `scripts/security/bwrap_run.sh`.

## Skipped

An ADR loop (read all decisions, propose the next one) overlaps a `Decisions.md` log plus the critic. The one new bit is a retrospective self-check prompt: "list the decisions I made that I am NOT confident about, plus the alternatives I skipped". Worth asking at the end of a long build; not worth its own file.
