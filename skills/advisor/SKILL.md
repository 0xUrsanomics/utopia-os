---
name: advisor
description: Get a cold, independent second opinion or adversarial critique from a DIFFERENT model than the main agent, with a brief that does not leak the main agent's answer. Use for close calls, a sanity check before an irreversible or external-facing action, red-teaming a plan or draft, or when the operator types /advisor. Differs from critic (which grounds claims with tools) by giving an independent judgment on a decision.
trigger: /advisor, second opinion, sanity check this, advisor, red-team this, ask another model
---

# Advisor (second opinion from another model)

A second brain on a different model. If your main agent runs on one model and you have access to another (a different tier or a different family, ideally on a separate quota), asking it costs idle capacity, not the main agent's. The point is an INDEPENDENT read. If it agrees with the main agent every time, the brief is leaking the main agent's answer.

## When to call (agent's discretion)

Call the advisor when the extra view can change something:
- A close or high-stakes call where the agent is genuinely split (which of two options, ship or hold).
- A sanity check before a CONFIRM-gated, irreversible or external-facing action.
- Adversarial critique of the agent's own plan or draft ("what am I missing, what breaks this").
- A domain gut-check where a fresh read beats the agent's in-context momentum.

Do NOT call it for trivial, reversible or already-clear work. It costs latency and adds noise when over-used. The value is in the close calls.

The operator can force a call with `/advisor <question>`. Then always call.

## How to call

Spawn a FRESH subagent with a model override (never a fork: a fork inherits the parent's context and usually its model, which defeats the point):

```
Agent(
  subagent_type: "general-purpose",   # any non-fork type
  model: "<a model other than the main agent's>",
  description: "advisor second opinion",
  prompt: "<brief, see template below>"
)
```

Brief template (fill every line, keep it under about 300 words):

```
DECISION: <one sentence: what is being decided>
OPTIONS: <A / B / ... stated neutrally, same detail level each>
FACTS: <only the facts the call needs, with dates and sources>
CONSTRAINTS: <hard limits: budget, deadline, scope, security rules>
ASK: Reply in exactly this shape:
  VERDICT: <pick, or "neither, do X">
  CONFIDENCE: <low / med / high>
  WHY: <2-3 bullets>
  MOST LIKELY MISS: <the one thing the asker is probably missing>
  WHAT WOULD FLIP IT: <the fact that would change your verdict>
Plain, direct, no dashes, no hype.
```

Discipline:
- **Cold start.** A fresh agent gives a view free of the main context's bias. That independence is the whole value.
- **Do not leak the main agent's pick.** Never say which option the agent leans toward, and do not describe one option in more detail or warmer wording. A stated lean anchors the reviewer (sycophancy, Sharma et al. 2023). Form the main agent's own verdict BEFORE reading the advisor's reply, so the comparison is honest. Exception: when the ask is "red-team my draft or plan", paste the draft, since attacking it is the task.
- **Paste only the facts the question needs.** No full-memory dumps. Depth 2 max: the advisor does not spawn its own children.
- **The advisor's output is INPUT, not authority.** A subagent carries no operator authority. Weigh it, fold the good parts into the main agent's judgment, and say plainly when the agent disagrees and why. Never adopt a conclusion just because it came back confident.
- **If the call fails** (model override rejected, timeout, empty reply): retry once, then proceed on the agent's own judgment and say so in one line ("advisor unavailable, my call: X"). Never block the task on the advisor, and never fall back to a fork (a same-model view is not a second opinion).

## Reporting

Discretionary call: stay quiet unless the advisor CHANGED the answer or raised a real risk. Then one line: "Advisor flagged X, so I am adjusting to Y."

Explicit `/advisor`: always relay, in this shape (about 8 lines, chat-sized):

```
Advisor: <verdict> (<confidence>)
- <its strongest reason>
- Miss it flagged: <one line>
Me: <agree / disagree> because <one line>
Call: <final decision + next action>
```

Related: `skills/critic/SKILL.md` (tool-grounded claim check), `skills/arena/SKILL.md` (uses the same fresh-agent, other-model rule for its judge), `skills-shared/sycophancy-guard/SKILL.md`.
