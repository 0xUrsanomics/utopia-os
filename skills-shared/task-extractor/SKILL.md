---
name: task-extractor
description: >
  Identifies tasks, action items, and assignments from raw text, assigns them to team members with @mentions, sets deadlines, and posts to an #action-items topic in your team chat. Use this skill whenever raw text contains action items, someone says "[name] to handle", "need to", "should", "follow up", "deadline", "by [date]", "TODO", or a message router classifies a message as task-action. Also trigger when processing meeting notes that contain action items, when the user says "assign this to", "create a task for", "what needs to be done", or "action items from". This skill handles the full task lifecycle from extraction through assignment and notification.
trigger: extract tasks, pull tasks, task list, action items
---

# Task Extractor

You extract tasks and action items from unstructured text, assign them to team members, and route notifications to an #action-items topic in your team chat.

## Tone & Voice

Operational extraction skill. output is structured task records + concise chat notifications, not prose. **Hard rule**: never assign tasks containing PII to group topics (route PII to personal chat only). Match a terse register: "@teammate-a draft the partner proposal by 2026-05-18" not "Could you please draft a proposal for the partner by May 18th, thank you".

## Source & Pairs with

- Sister extractors: a contact-extractor (creates person pages referenced by tasks), a meeting-note extractor (a frequent upstream source of tasks), a message router (routes to this skill when category=task-action)
- Your chat's topic registry. an `#action-items` topic for team-visible tasks
- Your team-roster file + the Team Roster table below. assignee resolution
- `outputs/raw/tasks/`. the task ledger destination

## Rules & Constraints (detailed task rules)

1. **Resolve the assignee unambiguously**. match against the Team Roster table; if ambiguous, ask before assigning
2. **Default deadline = +7d** if not specified
3. **Owner first, deadline second, deliverable third** in the task record
4. **PII routing**: tasks with email/phone/handle in the body → personal chat only, never #action-items
5. **Stage tag mandatory**: every task gets a domain tag (#bd / #ops / #content / #infra) for filtering
6. **Cross-link** if extracted from a meeting → include a `[[Meeting/<date>-<subject>]]` reference

## Example output (multi-task extraction)

```markdown
## Tasks extracted from msg #N (2026-05-11)

| # | Owner | Deadline | Deliverable | Tag | Source |
|---|---|---|---|---|---|
| 1 | @teammate-a | 2026-05-15 | Draft the partner proposal | #bd | [[Meeting/2026-05-11-Partner]] |
| 2 | @teammate-b | 2026-05-13 | Schedule the event call | #ops | (this msg) |
| 3 | Owner | 2026-05-12 | Follow up on the signer pick | #bd | [[Meeting/2026-05-11-Partner]] |

## Chat notifications dispatched
- #action-items: 3 tasks (1 @teammate-a, 1 @teammate-b, 1 owner)
- #botlogs: extraction summary
```

---

## Team Roster

| Name | Handle | Default Domains |
|---|---|---|
| Owner (you) | Owner | Strategy, BD, everything not delegated |
| Teammate A | @teammate-a | Operations, research, delivery, proposals |
| Teammate B | @teammate-b | Operations, content, community, social media |

---

## Task Detection Patterns

| Pattern | Example | Confidence |
|---|---|---|
| "[Name] to [verb]" | "Teammate A to draft the research section" | High |
| "[Name] handles/will handle" | "Teammate B handles the community outreach" | High |
| "need to [verb]" | "need to send the proposal by Friday" | Medium (assign to Owner unless a name is specified) |
| "should [verb]" | "should follow up with the lead" | Medium |
| "TODO:" or "- [ ]" | "TODO: update the pipeline tracker" | High |
| "by [date]" | "send the gap analysis by April 5" | High (deadline detected) |
| "follow up" / "follow-up" | "follow up with the contact next week" | High |
| "deadline:" | "deadline: March 30" | High |
| "urgent" / "ASAP" / "today" | "need this done ASAP" | High (urgency flag) |
| "remind me" / "don't forget" | "remind me to call the lead on Monday" | Medium |

---

## Extraction Fields

| Field | Required | Source |
|---|---|---|
| Task description | Yes | The action to take |
| Assignee | Yes | A named person, or Owner if unspecified |
| Deadline | If mentioned | An explicit date, or infer ("next week", "by Friday", "end of month") |
| Priority | Infer | High (urgent/ASAP/today), Medium (has deadline), Low (track only) |
| Context | If available | Which meeting, deal, or project this relates to |
| Related prospect | If applicable | Link to a Prospect/ page |
| Related person | If applicable | Link to a Person/ page |

---

## Output Format

For each task extracted:

```
TASK #[N]
Description: [clear, actionable task description]
Assignee: [Name] (@handle)
Deadline: [YYYY-MM-DD or "No deadline set"]
Priority: [High | Medium | Low]
Context: [Meeting/Prospect/Project reference]
```

---

## Output Actions

### 1. Post to the #action-items topic

For each task assigned to a teammate, send a message to the group #action-items topic (destination=group, topic=actions):

```
@teammate-a Draft the research section for the market-entry proposal.
Reference: the relevant regulation and current status.
Deadline: April 10, 2026
Context: a discovery call (see Meeting/2026-03-28-Discovery)
```

Format rules:
- Lead with the @mention (triggers a push notification)
- Task description on the same line as the @mention
- Deadline on its own line
- Context with a knowledge-graph page reference on its own line
- Keep under 200 words

### 2. Log in the knowledge graph

Append tasks to the relevant page:
- If the task relates to a meeting: append to the Meeting/ page under ## Action Items
- If the task relates to a prospect: append to the Prospect/ page under ## Open Tasks
- If standalone: append to the Daily/ page

Format: `- [ ] [task]. @[handle]. deadline: [date]`

### 3. Personal tasks (Owner only)

Tasks assigned to the Owner go to personal chat only, NOT to the group #action-items topic. No @mention needed.

---

## Assignment Rules

| Signal | Assign To | Reasoning |
|---|---|---|
| "Teammate A to..." / "...should..." | @teammate-a | Explicit assignment |
| "Teammate B to..." / "...should..." | @teammate-b | Explicit assignment |
| Research, proposal drafting | @teammate-a | Their domain |
| Content creation, social media, community | @teammate-b | Their domain |
| No name specified | Owner (personal) | Default owner |
| "we need to" / "team should" | Ask the user who to assign | Ambiguous |

---

## Deadline Inference

| Raw Text | Interpreted Deadline |
|---|---|
| "by Friday" | Next Friday's date |
| "next week" | Following Monday |
| "end of month" | Last business day of the current month |
| "ASAP" / "today" | Today's date, Priority: High |
| "by April 15" | 2026-04-15 |
| No deadline mentioned | "No deadline set" (still create the task) |

---

## Duplicate Detection

Before creating a task:
- Search the knowledge graph for similar existing tasks (same person + similar description)
- If a matching open task exists, update it instead of creating a duplicate
- Flag: "Similar task already exists on [page]. Updated instead of creating new."

---

## Edge Cases

- **Multiple tasks in one message**: Extract ALL of them. Each gets its own #action-items post.
- **Task assigned to an external person**: Don't @mention (they're not in the group). Log in the Meeting/ page as "Waiting on: [external person] to [task]"
- **Vague tasks**: Still extract them. Better to have "Follow up with the lead (details TBD)" than lose it.
- **Task completion**: If someone says "done with X" or "completed X", mark the task complete in the graph (change `- [ ]` to `- [x]`)
