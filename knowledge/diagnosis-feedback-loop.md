# Diagnosis: build the feedback loop first

Adapted (not copied) from `mattpocock/skills`, `engineering/diagnosing-bugs` (MIT). Pairs with `skills-shared/debugging-discipline/SKILL.md`.

**Why this file exists.** Most diagnosis doctrine is the RESTRAINT half: count before you conclude (two samples are a hypothesis, not a pattern), never let a diagnostic print its own conclusion, measure a fix against the size of the defect, read the cheap source first. All of that is about not believing the wrong thing. None of it says how to produce the evidence. That is this file.

## The claim

> **Build a feedback loop. This is the skill. Everything else is mechanical.**

A **tight** loop is a pass/fail signal that goes RED on this specific bug and green otherwise. With one, you will find the cause, because bisection, hypothesis testing and instrumentation all just consume it. Without one, no amount of reading code substitutes.

So spend most of the early effort here, before theorising. The urge to start reasoning about causes is the thing to hold back until the loop exists.

## Ten ways to build one, roughly in order of preference

1. **Failing test** at whatever seam reaches the bug.
2. **curl or HTTP script** against a running service.
3. **CLI call with a fixture**, diffing stdout against a known-good snapshot.
4. **Headless browser script** driving the UI, asserting on DOM, console or network.
5. **Replay a captured trace.** Save the real payload or event log to disk, replay it through the code path in isolation.
6. **Throwaway harness.** Minimal subset of the system, mocked dependencies, one function call.
7. **Property or fuzz loop.** For "sometimes wrong output": run 1000 random inputs and look for the shape.
8. **Bisection harness.** If it appeared between two known states, automate "boot at state X, check, repeat" so `git bisect run` can drive it.
9. **Differential loop.** Same input through old and new (or two configs), diff the outputs.
10. **Human-in-the-loop script.** Last resort. If a person must click, drive them with a structured script so the loop still has a shape and the captured output feeds back.

## Treat the loop as a product, then tighten it

Once you have a loop, improve it before using it:

- **Faster.** Cache setup, skip unrelated init, narrow the scope.
- **Sharper.** Assert on the specific symptom, not "did not crash".
- **More deterministic.** Pin time, seed the RNG, isolate the filesystem, freeze the network.

A 30-second flaky loop is barely better than no loop. A 2-second deterministic one changes how fast you can work.

## Non-deterministic bugs: raise the RATE, do not chase a clean repro

The goal is not a reliable reproduction; it is a higher reproduction rate. Loop the trigger 100 times, run in parallel, add stress, narrow timing windows, inject sleeps. A bug that fails 50% of the time is debuggable. One that fails 1% of the time is not. Keep raising the rate until it is, instead of calling the bug unreproducible and moving on.

## How this fits with the restraint rules

The loop is what makes the restraint rules cheap:

- **Counting before concluding** is trivial once the loop can run over a whole corpus instead of two hand-picked examples.
- **A diagnostic must not print its conclusion** is easier to honour when the loop emits a bare pass/fail with no room for editorialising.
- **Measure a fix against the defect** needs a before-number, which is what a loop gives you.

**Order of operations: loop first, then restraint, then fix.** A confident diagnosis produced before any loop exists is the most common way this goes wrong.

Evidence levels for "fixed" claims: `knowledge/evidence-ladder.md` (a passing loop is L4; the live surface is L5).
