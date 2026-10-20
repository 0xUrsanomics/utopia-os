# Skills index

Every skill folder in this repo, with the one-line description from its `SKILL.md`. Generated from frontmatter; regenerate it when you add a skill.

| Skill | What it does |
|---|---|
| `skills/advisor` | Get a cold, independent second opinion or adversarial critique from a DIFFERENT model than the main agent, with a brief that does not leak the main agent's answ |
| `skills/agent-dispatch` | Domain-aware subagent dispatcher. Maps task → domain (research / build / draft / verify / ops) → recommended subagent_type + tool boundaries + briefing scaffold |
| `skills/arena` | Run N parallel candidates at the same high-stakes drafting or design task, with a rubric fixed BEFORE fan-out and a judge from a different model, then pick a ba |
| `skills/audit-pypi-model-package` | Decide whether a PyPI package that downloads or loads model weights is safe to install, and clean it up if it loses the bench. Covers the stand-down check, the  |
| `skills/branching-workflow` | When and how to use the coding-agent CLI's `/rewind` to abandon a bad branch and restart from a prior turn. Documents the recovery primitive for the layered eva |
| `skills/code-review` | Staff engineer code review for scripts, tools, and infrastructure changes |
| `skills/critic` | Tool-grounded Critic skill (layered eval architecture, Layer 2). Dispatched as a subagent on high-stakes outputs. Grounds the verdict against tool-fetched evide |
| `skills/cron-child-oauth-audit` | Diagnose a cron or daemon-spawned "claude --print" child that fails silently because it launched without an auth token, when a scheduled task's critic or subpro |
| `skills/daily-forest` | Daily 21:30 (local) skill. Synthesize today's Signal/ harvest into a forest-level read. movers / silences / tone shifts / cross-stitches / anomalies. Indexed ba |
| `skills/deep-research` | > |
| `skills/diagnose-cron-timeout` | Decide whether a scheduled claude_code cron that ended "timed out" with an empty trace was cut at its time cap while still working, or truly hung, by reading th |
| `skills/dreaming` | Automated memory consolidation. 3-phase process that promotes high-quality memories and decays stale ones |
| `skills/eod-summary` | End-of-day digest pulling today's wins, decisions, status changes, follow-ups, new artifacts, tomorrow's queue from session.jsonl + tasks + tracker files. User- |
| `skills/filing` | Give received artifacts a canonical home AND an index entry so recall can reach them. Intake, placement, indexing. Not a filesystem beautification pass. |
| `skills/forest-synthesis` | Weekly cross-corpus synthesis across accumulated daily-forest digests. Cross-day pattern extraction invisible to single-day reading. Use weekly not daily. |
| `skills/goals` | Active-goal registry. Tier-1 north star steering. Maintains memory/state/active_goals.json with goals + milestones + requirements. Slash command for list/new/do |
| `skills/graph-hygiene` | Logseq knowledge-graph maintenance lint. scans 7 categories (stale pages, orphans, missing properties, dead links, missing compiled-truth/timeline structure, ta |
| `skills/idea` | Capture ad-hoc thought into the active project's Inbox section. Falls back to side-quests if no active project. Lightweight quick-drop primitive. no friction, n |
| `skills/inline-tags` | Append 1-3 hashtag tags to the end of every TG reply for native TG search. Domain + project + status taxonomy. Replaces full TG-Topics migration without rebuild |
| `skills/intel-analyzer` | > |
| `skills/loop-experiment` | Run a Karpathy-loop / autoresearch-style optimization experiment on any task with measurable fitness. Bounds the loop with the stack's discipline (fitness-funct |
| `skills/loop-library` | Catalog of repeatable agent-loop workflows (goal -> iterate w/ verification -> stopping condition -> output). Each loop is a reusable SOP for autonomous iterati |
| `skills/meta-memory-review` | Periodic self-optimization of the memory STRUCTURE (not its content). Review tier layout, dedupe, prune, and re-index the memory system. |
| `skills/office-hours` | Force assumptions into the open before code is written. 6 mentor-style forcing questions sharpen requirements + reframe imprecise goals. Goal-type mode-mapping  |
| `skills/plan-ceo-review` | Product-strategist mode review on a draft plan. 4 scope-modes (EXPAND / SELECTIVE / HOLD / REDUCE) chosen explicitly upfront and committed-to throughout. Catche |
| `skills/plan-design-review` | Designer's-eye plan review. Rate each design dimension 0-10, explain what would make it a 10, then fix the plan to get there. 7 passes (info architecture / inte |
| `skills/prd` | Structured PRD/spec generator. Transforms vague ideas (skill / infra / process / feature) into requirements, success metrics, build phases, and go-or-park gates |
| `skills/progressive-disclosure` | When a chat reply exceeds the wall-of-text threshold, attach as a .md file with a 3-line summary in chat instead. Reduces mobile reading friction + token tax on |
| `skills/reality-feedback-create` | Layered eval architecture, Layer 4 auto-create. Fires from the Stop hook chain after critic_dispatch. Appends an entry to the reality_feedback.sqlite ledger whe |
| `skills/reality-review-weekly` | Layered eval architecture, Layer 4 weekly review. Cron-fired weekly. Queries reality_feedback.sqlite for entries where outcome IS NULL AND timestamp + window ha |
| `skills/recall` | Semantic recall across the agent's full knowledge base via the vector_brain index (knowledge-graph pages, knowledge files, memory, reviewed outputs, persona mem |
| `skills/reconcile-extraction` | Check that a scan, scrape or aggregator pull is complete and in the right unit by reconciling what the parser produced against a number the source states about  |
| `skills/redact` | Per-entry redaction primitive for memory/ + outputs/ files. Strips matching content, replaces with [REDACTED YYYY-MM-DD reason] marker, logs to logs/redact-log. |
| `skills/repo-audit` | 4-option triage when you drop a GitHub repo URL. doc-mine / clone-audit / install-direct / park. Default to clone-audit for anything that touches credentials, f |
| `skills/research-digest` | Weekly full-read digest of the week's research reports (research firms, banks, central banks, regulators, multilaterals). Daily harvesters flatten a report to o |
| `skills/review-gate` | Knowledge quality gate. review raw outputs, approve/flag/merge before writing to the knowledge graph |
| `skills/run-long-job-detached` | Run a script that takes longer than about 30 minutes so it survives session restarts and background-agent deaths, and still reports its result when it finishes. |
| `skills/save` | Session summary extraction. review recent session, extract preferences/decisions/context/voice/learnings, write to the appropriate memory/ tier files. |
| `skills/scope` | Assumption-first scoping. Restate the ask, surface assumptions, ask for corrections before acting. MANDATORY before every CONFIRM-gate action. Also use for comp |
| `skills/self-audit` | Agent reads its own error logs, identifies recurring failures and capability gaps, proposes and applies fixes |
| `skills/shadow-test-local-classifier` | Decide whether a small local model can take over a bounded keep/skip or pick-one-of-N task before it touches a cron. Build labelled rows, hold out a split, scor |
| `skills/signal-scorer` | Score and assess intel signals on 6 dimensions |
| `skills/skill-audit` | Pre-install structural security audit for SKILL.md artifacts. Detects 3 threat chains (Hidden Override / Disguised Transfer / Remote Bootstrap) and runs 5 detec |
| `skills/skill-chaining` | Execute multiple skills in sequence as a pipeline. context passes between each step |
| `skills/spawn-agent-in-tenant` | > |
| `skills/spawn-tenant` | > |
| `skills/split-log-rows-by-session-kind` | Check whether a hook or error metric is polluted by child sessions (critic, subagent, cron) by joining logged session ids to their transcripts and splitting on  |
| `skills/subagent-delegation` | > |
| `skills/telegram-dump-router` | > |
| `skills/telegram-reply-tool` | Enforcement protocol for always sending responses via the Telegram reply tool in interactive sessions. Tracks and prevents reply-tool misses. |
| `skills/verify-stack` | Drive-and-prove check for a long-running agent stack. Proves that features actually reach the person who uses them (evidence level L5), not just that processes  |
| `skills/wave-plan` | Dependency-wave execution for multi-step tasks. Parse the ask into sub-tasks, build a DAG of dependencies, group into topo-sorted waves, execute each wave as pa |
| `skills/weekly-retro` | Weekly retrospective across the entire stack. Reviews what shipped, what broke, what to improve over the past 7 days. Use this skill on a Sunday cron or wheneve |
| `skills-shared/ai-seo` | Optimize content to get cited by AI search engines. ChatGPT, Perplexity, Google AI Overviews, Claude, Gemini, Copilot. Use when you want your content to appear  |
| `skills-shared/anti-ai-slop` | > |
| `skills-shared/autoresearch` | > |
| `skills-shared/autoresearch-system` | Karpathy loop for the entire agent architecture. simulate end-to-end workflows, score, find the weakest link, fix, iterate. |
| `skills-shared/content-humanizer` | Makes AI-generated content sound genuinely human. not just cleaned up, but alive. Use when content feels robotic, uses too many AI clichés, lacks personality, o |
| `skills-shared/debugging-discipline` | Evergreen debugging + restart heuristics + cognitive-bias antidotes. Tier-2 (recall-fetched on-demand, NOT always-loaded). Lifted in condensed form from gsd-bui |
| `skills-shared/decision-council` | > |
| `skills-shared/marketing-psychology` | When the user wants to apply psychological principles, mental models, or behavioral science to marketing. Also use when the user mentions 'psychology,' 'mental  |
| `skills-shared/memory-offload` | Manages the agent's context overflow by offloading dense operational state to an Agent-Memory namespace in your knowledge graph and pulling it back when needed. |
| `skills-shared/negotiation` | > |
| `skills-shared/premortem` | Run a premortem on any plan, launch, product, hire, strategy, or decision. Assumes it already failed 6 months from now and works backward to find every reason w |
| `skills-shared/schedule` | Create a scheduled task that can be run on demand or automatically on an interval. Use when the user says 'schedule X', 'remind me in N minutes', 'every weekday |
| `skills-shared/skill-creator` | Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an e |
| `skills-shared/sycophancy-guard` | Always-on background filter preventing sycophantic belief drift. Based on Chandra et al. 2026 proving even ideal Bayesian users spiral from sycophantic AI, incl |
| `skills-shared/task-extractor` | > |
| `skills-shared/test-before-bulk` | Mandatory gate before any batch operation that writes to a CRM, a knowledge graph, a spreadsheet, a vector index, or any other durable store. Test 3-5 first, fi |
| `skills-shared/vendored-deps` | Track manually-installed GitHub dependencies (tools/binaries/repos adopted OUTSIDE a package manager) for upstream updates we would otherwise silently miss. |
| `skills-shared/voice-profiler` | Extract voice patterns from session history and update Voice-Profile.md |
