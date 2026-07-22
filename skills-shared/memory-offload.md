---
name: memory-offload
description: Manages the agent's context overflow by offloading dense operational state to an Agent-Memory namespace in your knowledge graph and pulling it back when needed. This skill should ALWAYS be active as a background process. Auto-triggers when conversations get long or context-heavy. Also triggers on manual commands like "offload this", "save to memory", "dump context", "remember this for later", "store this in the graph", "memory dump", "context dump", "save state". On the PULL side, this skill triggers at the START of every conversation to check for relevant Agent-Memory pages, and mid-conversation when a topic matches stored context. Also triggers when the user says "pull my context", "load memory", "what do you have stored", "check your notes", "refresh context".
trigger: memory offload, offload context, save context, persist memory
---

# Memory Offload Skill

Manages an `Agent-Memory/` namespace in your knowledge graph as overflow storage for the agent's context window.

## Tone & Voice

Background process. applies silently. The skill should NEVER produce hype-y prose like "successfully offloaded important context". Match the operational-telemetry register: a terse confirmation ("offloaded to Agent-Memory/<page>" with a path), no ceremony. **Hard rule**: never offload sensitive content (API keys, .env contents, credentials). those stay in-session or get redacted first via `skills/redact.md`.

## Procedure (thinking step by step)

**OFFLOAD direction (push context → graph)**:
1. Detect the trigger: context approaching the limit OR an explicit user command ("offload this", "save to memory").
2. Identify the offload candidate: dense factual content, completed analysis, a finished reasoning chain.
3. Redaction check: scan for API keys, credentials, .env contents. If present, route through `skills/redact.md` first.
4. Pick a target page in the `Agent-Memory/<topic-slug>` namespace (create if missing).
5. Write the page via your knowledge-graph MCP's create/update-page tool.
6. Confirm with a one-line acknowledgement + the page path.

**PULL direction (load from graph → context)**:
1. Detect the trigger: session start, a topic match mid-conversation, an explicit "load memory" command.
2. Query the `Agent-Memory/` namespace via your graph's list/search tool for relevant pages.
3. Read the matched page(s) via your graph's read-page tool.
4. Surface the loaded content with attribution ("pulled from Agent-Memory/<page>").
5. Apply it directly to the current reasoning without re-asking the user.

## Two Operations

### 1. OFFLOAD (Write to the graph)

Store dense context that would otherwise bloat memory edits or get lost between sessions.

### 2. PULL (Read from the graph)

Retrieve stored context to restore working knowledge at conversation start or when a topic surfaces.

---

## OFFLOAD Rules

### Auto-Trigger Conditions

The agent should offload when ANY of these are true:

- The conversation exceeds ~15 back-and-forth exchanges AND contains technical configs, architecture decisions, or multi-step plans
- A complex debugging session produced findings that will be needed later
- The user shares detailed specs, requirements, or research that won't fit in memory edits
- A build/setup session produced configs, file paths, port numbers, or command sequences
- Multiple interconnected decisions were made that form a "state snapshot"
- The agent's memory edits are approaching the item limit and some items could be expanded in the graph instead

### Manual Trigger Phrases

- "offload this", "save to memory", "dump context", "store this"
- "remember this for later", "save state", "context dump"
- "put this in the graph", "save to agent memory"

### What to Offload

Good candidates for offloading:

| Category | Example |
|---|---|
| Config snapshots | File paths, port numbers, env vars, service names |
| Architecture decisions | Why X was chosen over Y, trade-offs discussed |
| Debug session findings | What broke, what fixed it, root cause |
| Build progress | Steps completed, steps remaining, blockers |
| Research synthesis | Key findings from a deep-dive, ranked options |
| Meeting/call context | Detailed notes beyond what fits in memory |
| Multi-file edit logs | Which files were changed and why |

Bad candidates (keep in memory edits instead):

- Single facts (name, location, preference)
- Short preferences or rules
- Anything under 3 lines

### Page Naming Convention

```
Agent-Memory/[Topic-Name]
```

Examples:
- `Agent-Memory/Daemon-Systemd-Setup`
- `Agent-Memory/Project-Alpha-Architecture`
- `Agent-Memory/HTTPS-Research`
- `Agent-Memory/Content-Producer-Debug-Log`

Use descriptive, specific names. Avoid generic names like `Agent-Memory/Notes` or `Agent-Memory/Stuff`.

### Page Format

Every offloaded page must follow this structure:

```markdown
type:: context-offload
status:: active
created:: YYYY-MM-DD
last-updated:: YYYY-MM-DD
topic:: [brief topic description]
tags:: [relevant tags, comma-separated]

- ## Summary
	- [2-3 sentence overview of what this page contains and why it was stored]
- ## Context
	- [The actual content being offloaded]
	- [Use sub-bullets, tables, code blocks as needed]
	- [Be thorough. This needs to make sense when pulled back weeks later.]
- ## Related
	- [Links to related graph pages if any, e.g. [[Project/Alpha]]]
- ## Retrieval Hints
	- [Keywords and phrases that should trigger pulling this page]
	- [e.g. "daemon setup", "systemd", "MCP server restart"]
```

### Offload Procedure

1. Identify content worth offloading (auto or manual trigger)
2. Check if a relevant `Agent-Memory/` page already exists for this topic
   - If yes: UPDATE the existing page
   - If no: CREATE a new page
3. Notify the user briefly: "Offloaded [topic] to Agent-Memory/[Page-Name]"
4. If the offloaded content was previously in memory edits, consider whether those edits can now be simplified (point to the graph page instead of storing full detail)

### Staleness Management

- When updating an existing page, always update the `last-updated::` property
- If a page hasn't been updated in 30+ days and the context is no longer relevant, set `status:: stale`
- Stale pages are still searchable but deprioritized in pulls

---

## PULL Rules

### Conversation-Start Check

At the beginning of every conversation, the agent should:

1. Scan the user's memory store for their current active projects and recent work
2. Search with 2-3 broad keywords matching recent activity
3. If relevant `Agent-Memory/` pages exist, silently load the key context
4. Do NOT announce the pull unless the user asks "what do you remember" or similar

This should be lightweight. One search call, scan results, internalize. No output unless asked.

### Topic-Triggered Deep Pull

When a conversation touches a specific topic that matches a stored page:

1. Search the `Agent-Memory/` namespace for matching keywords
2. Read the full page content
3. Apply the context naturally without narrating ("I pulled your notes on X")
4. If the pulled context changes your understanding, adjust your responses accordingly

### Manual Pull Phrases

- "pull my context", "load memory", "check your notes"
- "what do you have stored", "refresh context"
- "what's in agent memory", "show me my offloaded context"

For manual pulls, list what pages exist and offer to load specific ones.

### Pull Procedure

1. Search with relevant keywords, filtered to the Agent-Memory namespace
2. For matching pages, read the full content
3. Parse the page structure (Summary, Context, Related)
4. Integrate it into the current conversation context
5. If multiple pages match, prioritize by:
   - `last-updated::` date (newer = higher priority)
   - `status:: active` over `status:: stale`
   - Direct keyword match over fuzzy match

---

## Edge Cases

### Conflicting Information
If an Agent-Memory page contains info that conflicts with current memory edits, the memory edits take priority (they're more recent). Flag the conflict to the user and offer to update the graph page.

### Page Cleanup
If the user says "clean up memory", "prune old context", or "what's stale":
1. List all Agent-Memory pages with their dates and status
2. Let the user decide what to keep, archive, or delete
3. Delete confirmed pages via your graph's delete tool

### Size Limits
Keep individual pages under ~2000 words. If a topic needs more, split into sub-pages:
- `Agent-Memory/Project-Alpha-Architecture`
- `Agent-Memory/Project-Alpha-Contracts`
- `Agent-Memory/Project-Alpha-Frontend-Stack`
