---
source: caldoai/skills, skills/untangle-codebase/SKILL.md, MIT, pinned commit 442c299, github.com/caldoai/skills
read: via the GitHub API only. Nothing installed or run; the upstream `npx skills add` route was not used.
status: lifted as working rules for refactors and code reviews
---

# Untangle rules (refactor and review lens)

## The one question
For any two pieces of code: **should these change together?** Every structural problem is the code answering that wrong, in one of three ways.

## Three buckets
1. **Hidden links.** These pieces must change together, but nothing in the code shows it.
   - Copied logic or values. Example: the same per-source dedup loop pasted once per data source in one pipeline script.
   - A module that reads a global or file another module writes.
   - One feature split across folders by layer.
   - A call order or convention that callers just have to know.
2. **Needless links.** These pieces are tied together but change for different reasons.
   - Callers that depend on internals.
   - Stable code that imports more volatile code.
   - A general function with a parameter only one workflow understands.
   - A shallow module whose interface moves whenever its internals do.
3. **Surplus.** These pieces have no reason of their own to change.
   - Pass-through wrappers.
   - Config or extension points for things that never vary.
   - Dead code.

## Special cases are clues
These are clues, not chores:
- an `if` for one value;
- a parameter for one caller;
- a swallowed exception;
- a retry or sleep;
- a disabled test.

Each one is a requirement the design never accounted for. Collect them and redesign so they become unnecessary. Do not patch them one by one. This is the same idea as a root-cause-over-bandaid rule: a fix of the same shape needed N times means the design is the bug.

## Method
1. **List every problem before changing anything.** Use file:line, written as plain sentences.
2. **Redesign as if today's requirements were known from the start.** Look for the one fix behind several problems. It often looks nothing like any of them.
3. **Write a decision log.** Put each fix as a bullet with the problems it solves nested under it. This survives compaction and doubles as the PR description.
4. **Test every fix against the rules:**
   - pieces that change together end up together;
   - pieces that don't change together are not tied;
   - everything depends on what changes less.
5. **Repeat with a fresh checker** until nothing worth fixing is left.

## Done means
- As few special cases left as possible. This count is the progress measure.
- A typical change lands in one place.
- No import points at something more volatile than the importer.
- Behaviour is unchanged apart from bugs the refactor fixed, and that is tested at the end.

## Comments and tests (only when asked)
- **Comments:**
  - Remove comments that restate the code.
  - Keep comments about something outside the code (an API quirk, a proxy).
  - Remove workaround comments when the redesign removes the workaround.
- **Tests:**
  - Remove tests that only mirror the implementation or cannot fail.
  - Rewrite tests tied to internals so they test behaviour.
  - Do the tests last, because they are the safety net.

## Tips worth keeping
- **Skeleton first:** strip function bodies so the whole module fits in context.
- **Dependency graph:** script a what-imports-what graph and rerun it as you go.
- **Git as evidence:** files that change together in history are coupled, whatever the imports say.

## How to use it here
- Code reviews and refactors of this repo's own scripts. Use the three buckets as the review checklist, and report findings as a decision log.
- Not a licence to rewrite on the agent's own initiative. A refactor still needs the operator's ask. CLAUDE.md "Weakening a gate goes to the operator" still applies.
- Not lifted: "Treat this as a goal ... do not stop until there is nothing worth fixing left". That is unbounded scope, so a budget check wins.
