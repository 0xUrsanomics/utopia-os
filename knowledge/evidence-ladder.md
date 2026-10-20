# Evidence ladder ("how sure are you")

Adapted from pstack `blast-radius` (github.com/cursor/plugins, MIT, Lauren Tan). Use it for any "it's safe / it works / it's not installed" claim, in critic verdicts, and in the done standard.

## The levels

For each fact a claim depends on, push it as far down this list as is cheap, and SAY which level it reached.

| Level | Name | What it means |
|---|---|---|
| L1 | said so | I believe it. Worthless on its own. |
| L2 | pointed at it | A real `file:line`, a config value, the vendor's own doc or source. |
| L3 | walked it | Traced the failure step by step and showed it cannot happen. |
| L4 | ran it | A script, test or command against the REAL code or data that would fail loudly if wrong. |
| L5 | reproduced live | Hit the actual running instance or the surface the user sees (the real port, the real bot, the real inbox). |

## Rules

1. **Find the one fact.** Most risky-looking changes are safe because of a single fact. Name it, then spend the effort proving that fact, not listing maybes.
2. **State the level with the claim.** For example "local model runtime not installed (L4, checked the Linux side only)". Writing the scope next to the level is what exposes a gap: here, the other OS was never checked.
3. **Absence claims need L4 over the full scope.** "Not installed / not in the index / no results" is only as good as where you looked. Name the scope.
4. **"Live" means L5.** A fresh one-shot run is L4; a long-running process needs L5, because the running process can hold old code.
5. **A convincing writeup is still L1.** Prose that sounds right reads the same whether or not it is true.

## Where it is used

- `skills/critic/SKILL.md`: the verdict `reason` tags the strongest claim with its level.
- `skills/save/SKILL.md` Step 3.3: a SHIPPED or LIVE entry carries a `verified_working::` observation with its level.
- `skills/arena/SKILL.md` Phase F (verify): every factual claim in the final artifact carries a level.
- `skills/verify-stack/SKILL.md` and `scripts/eval/verify_stack.py`: L5 drive-and-prove for a long-running stack.
- `knowledge/diagnosis-feedback-loop.md`: a passing feedback loop is L4.
