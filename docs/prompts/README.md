# `docs/prompts/` — Session-kickoff prompts

This directory holds **session-kickoff prompts** — self-contained markdown briefings
the user pastes (or `cat`s) into a fresh Claude session to start a piece of work.
A prompt names its purpose, briefs the agent on prior context, sets scope + open
questions + constraints, and ends with a hand-back format the agent is expected to
follow.

## What goes here vs elsewhere

| Type of doc | Lives in | Owned by | Lifecycle |
|---|---|---|---|
| **Session-kickoff prompt** (what you paste to start a session) | `docs/prompts/` | architect (for plan-execution prompts) or user (for ad-hoc) | move to `docs/prompts/archive/` when the work ships |
| **Implementation plan** (Goal / Why / Proposal / Risk / Open Q / Approval) | `docs/plans/` | architect | move to `docs/plans/archive/` when the work ships with `## Deviations from plan` section |
| **Permanent design doc** (semantic name like `AUTH.md`, `DATA_MODEL.md`) | `docs/design/` | architect (graduated from a `Type: design` plan on approval) | lives forever; updated as the design evolves |
| **Operational guide** (cross-cutting, "how do I X") | `docs/` (top level) | architect / devops | lives forever; updated as conventions change |
| **Agent prompt** (system prompt for a subagent) | `.claude/agents/<name>.md` | architect | rarely changes; touch with care |
| **Slash command** (`/foo` flow) | `.claude/commands/<name>.md` | architect | add when a multi-step flow earns its own surface |

If you find a kickoff prompt drifting toward "this is really a plan," graduate it to
`docs/plans/NN-name.md` and have the architect rewrite the kickoff as a thin pointer.

## Naming convention

```
docs/prompts/<NN-kebab-name>.md     ← active prompts (current session work)
docs/prompts/<topic>.md             ← evergreen kickoffs (session-continue, cold-start helpers)
docs/prompts/archive/<NN-kebab-name>.md  ← prompts whose work has shipped
```

- `NN` matches the plan ordinal where applicable (e.g. plan `10c-first-time-setup` →
  prompt `10c-first-time-setup.md`).
- Evergreen prompts use semantic names (e.g. `00-session-continue.md`).
- Archive when the corresponding plan archives. Don't delete — they're history.

## Required structure

```markdown
# Kickoff: <title>

> **Type:** session-kickoff prompt for <subagent name>.
> **Audience:** <which agent reads this first, in what session>.
> **Usage:** `claude --agent <name> "$(cat docs/prompts/<file>.md)"`
> **Tracks:** ROADMAP row `<id>` (or "to be added by architect").
> **Authored:** YYYY-MM-DD.

## Context
<What's been done that this builds on. ~1 paragraph.>

## Goal
<One sentence + a few bullets. What artifact ships.>

## Required reading
<Numbered list of paths the agent should load before doing anything else. Parallelize.>

## Scope — N phases, HALT at each phase boundary
<Phase 1 ... Phase N each with deliverables + quality gate.>

## Approach
<Step-by-step: who dispatches whom, what halts when.>

## Decisions locked
<Decisions the user has already made — agent shouldn't re-debate.>

## Constraints
<Sunset rules, budget notes, single-writer rules, etc.>

## Open questions for architect (or relevant agent)
<Things to resolve during plan authoring. Each blocks PLAN GATE.>

## Hand-back format
<Exact format the agent uses when reporting back.>
```

Optional sections (use when relevant): **Budget note**, **Tracing**, **After this
plan ships** (what unlocks next).

## How to use a prompt

```bash
# Recommended — gives the manager full context as the first user message:
claude --agent manager "$(cat docs/prompts/agent-system-v2.md)"

# Alternative — fresh session, then paste the prompt:
claude --agent manager
# (paste the prompt body)

# Or if the prompt is generic enough for the main session (no specific agent):
claude "$(cat docs/prompts/00-session-continue.md)"
```

The `--agent` flag opens a subagent session directly with that agent's system
prompt. If you don't pass `--agent`, the prompt enters a normal Claude session and
Claude routes to subagents itself via the `Task` tool.

## Authorship

Per `AGENTS.md` § Workflow step 4 and `.claude/agents/architect.md` § "Implementation
prompt", the architect authors a kickoff prompt for any plan whose execution writes
code. The prompt is co-located in time with the plan: both ship together, the user
approves the plan + reads the prompt together, the implementer (engineer) executes
from the prompt with the plan as the canonical source.

For meta-prompts (like `agent-system-v2.md` or `00-session-continue.md`) that don't
correspond to a single plan, the user or any agent may author them. Keep the
structure consistent with above.

## Archive lifecycle

When a plan moves from `docs/plans/` to `docs/plans/archive/` (after shipping +
deviations section is written), the corresponding kickoff prompt also moves to
`docs/prompts/archive/`. The reason: prompts reference paths, decisions, and ROADMAP
rows that may shift; archiving keeps the active directory uncluttered while
preserving the audit trail.

Both directories are checked in. We don't gitignore prompts — they're project
history alongside plans.
