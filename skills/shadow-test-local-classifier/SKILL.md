---
name: shadow-test-local-classifier
description: Decide whether a small local model can take over a bounded keep/skip or pick-one-of-N task before it touches a cron. Build labelled rows, hold out a split, score per label, test the longest input, then wire it as a fail-open sidecar and review after a week.
trigger: can a local model do this, offload a classification to a local model, shadow a local model, local model bench, fine-tune a small classifier, move a filter off Claude
---

# Shadow-test a local classifier on a held-out set

Use when someone asks whether a small local model (a sub-1B fine-tune, a small open-weights instruct model run through Ollama or similar) could replace a Claude step that only chooses from a short fixed list: keep or skip, one of 9 categories, flag or discard. If the answer is free text, or needs a web read or a judgment on new facts, stop: it stays on Claude.

Before installing any new model package, run `skills/audit-pypi-model-package/SKILL.md`.

## Procedure

1. **Name the decision and its allowed answers in one line.** Write down the volume (rows per day) from a count of stored inputs, not from anyone's estimate.
2. **Build labelled rows from real stored inputs** (chat archive, harvested items, feed items) using Claude subagents as teachers. Before trusting a sample, check the input file's modified time and which rows the sample can reach. Example of the trap: a sample drawn only from rows a regex had already kept can expose false positives but never false negatives. Treat a subagent's volume claim as a lead, not a count.
3. **Split train and held-out with no overlap.** Keep the held-out split out of everything the model sees, including few-shot examples and any term list in the prompt. Take the class definition from the labelled rows, not from intuition.
4. **Score untuned against tuned (or few-shot) on the held-out split, per label.** For a minority class report recall and precision, not accuracy: a model can score 93% by always answering the majority label while finding 0 of 10 of the class you care about. A class under about 10% of rows, or a "not on the list" negative label, needs a balanced retry or a yes/no prompt.
5. **Run at the longest real input** and watch memory and context while it runs. Short-prompt tests miss failures that only appear at several thousand tokens (degenerate repeated output), and a runtime's large default context can spill the model to CPU. For thinking models, turn thinking off for short answers and set the context size explicitly.
6. **Wire it as a shadow:** a sidecar log only, Claude's decision unchanged, fail-open, a GPU lock if the GPU is shared, and a kill-switch env var. Add the review date as an intention: `python3 scripts/memory/intentions.py add "review <task> shadow" --due YYYY-MM-DD`. Load and unload through one runner so nothing stays resident: `scripts/lib/local_models.py`.
7. **At the review, compare the sidecar with what the cron actually kept.** Use the model to sort, never to drop, while recall on the keep class is under about 80%. Override only the fallback branch (for example keyword defaults) at confidence 0.9 or higher.

## Output

A one-page result table (task, rows, held-out size, untuned and tuned score, per-label recall, latency, VRAM) saved to `outputs/raw/<persona>/`, plus the intentions entry for the review date.

## Caveats

- Labels from a Claude teacher measure agreement with the teacher, not truth. Count the rows where every model disagrees with the label: many of those are label noise.
- Calibration matters more than the top score. If the model's confidence at or above 0.9 holds about 95% accuracy on held-out data, an override at that threshold is safe; if it does not, no threshold is.
