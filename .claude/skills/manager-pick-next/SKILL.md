---
description: Identify the next unblocked GitHub Project task for the current milestone via `scripts/gh-project.sh next-unblocked` and the persistent issue-map cache. Use when manager runs the operating-loop step 2 (Pick next), when the user asks "what's next" or "pick the next task" or "what should I work on", or whenever a `/build` run needs the next item after closing the previous one. Triggers on phrases like "next task", "pick next", "what's next", "next unblocked", "what should I work on", "operating loop step 2".
allowed-tools: Read, Bash(scripts/gh-project.sh:*), Bash(jq:*)
---

# manager-pick-next

Manager's operating loop step 2 is "Pick next" — find the highest-priority unblocked **Todo** issue on the GitHub Project board for the current milestone. **Backlog items are deferred from the current cycle and skipped by `next-unblocked`. Within Backlog, items are unprioritized at the item level — only the EPICS within Backlog carry priority via their own Priority field.** When Todo is empty (`next-unblocked` returns null), invoke `Skill: manager-backlog-promote` to surface the next-priority epic in Backlog + its top unblocked items for user pick via AskUserQuestion. Manager applies the picks via `scripts/gh-project.sh set-status <id> Todo` (one MIRROR per item) then resumes the loop. This skill wraps the canonical helper (`scripts/gh-project.sh next-unblocked`) and emits a single-line summary so the loop can hand off to architect or engineer cleanly. Single-writer rule applies: only the helper script reads/writes Project state.

## When to invoke

- Manager's operating loop step 2 (`/build` flow): right after state load, before dispatching architect for plan authoring.
- User asks "what's next" / "pick next" / "what should I work on" — surface the recommended task without dispatching.
- After closing the previous task (post-merge, post-archive), looping back to pick another.

## What this skill does

1. **Run the canonical helper.**
   ```bash
   scripts/gh-project.sh next-unblocked
   ```
   This returns the next open issue with Status=Todo, sorted by Priority (`CRITICAL > HIGH > MEDIUM > LOW`), excluding items labelled `blocked` or `epic`. Output is a single JSON object or `null`.

2. **Parse the JSON output.** Extract `number`, `title`, `url`, `priority`, `labels`.

   Backlog items never appear here (`next-unblocked` filters Status=Todo only). Within Backlog, items are unprioritized at the item level — only the EPICS within Backlog carry priority via their own Priority field. `backlog-by-epic` is the read primitive for the auto-promote workflow; this skill is for the active-cycle Todo column only.

3. **Cross-reference the persistent issue map** for additional context:
   ```bash
   jq --arg t "<title>" '.issues | to_entries[] | select(.value == <issue-num>)' .claude/github-issue-map.json
   ```
   This gives the ROADMAP task-id (e.g. `PC.5`) keyed to the Issue number.

4. **Read `ROADMAP.md`** to find the row matching the task-id — pull priority, effort estimate, and notes. Use `Grep "[<task-id>]"` or `Read ROADMAP.md` with offset around the relevant phase header.

5. **Emit a one-line summary** in this exact shape:
   ```
   Next: [<task-id>] <title> (priority: <PRIORITY>, milestone: <milestone>, issue: #<N>, estimate: <X>)
   ```

   Example: `Next: [PC.5] SECRET_KEY boot-time enforcement (priority: MEDIUM, milestone: Pre-Phase-2 paper cuts, issue: #7, estimate: ~1h)`.

6. **If `next-unblocked` returns `null`,** the Todo column is empty for this milestone. **Invoke `Skill: manager-backlog-promote`** to surface the next-priority epic in Backlog + its top unblocked items for user pick via AskUserQuestion. Manager applies the picks via `scripts/gh-project.sh set-status <id> Todo` (one MIRROR per item) and resumes this skill from step 1. Do not auto-promote without user consent. If the promote skill also returns "Backlog empty," the milestone is fully cleared — emit:
   ```
   Next: <none> — milestone <name> empty (Todo + Backlog). Recommend `/standup` or pick a different milestone.
   ```

## Canonical references

- `scripts/gh-project.sh` § `cmd_next_unblocked` (lines 713–759) — the sort key + label filters.
- `.claude/agents/manager.md` § Operating loop step 2.
- `docs/AGENT_OPS.md` § 6.6 — issue-map cache structure.
- `AGENTS.md` § GitHub state — single writer rule.

## When NOT to invoke

- Inside a single-task `/build` run mid-flight — skip until the current task is merged + archived.
- When the user has already named the task (`claude /build "PC.5"`); the task is given.
- Compaction events — the skill content lifecycle re-attaches the most-recent invocation.

## Forbidden during invocation

- Do NOT call `gh issue list` / `gh api graphql` directly to find the next task — the helper is the sole writer/reader for board state. Bypassing it bypasses the persistent map cache and re-introduces the duplicate-issue race documented in `AGENTS.md § GitHub state — single writer rule`.
- Do NOT hand-edit `.claude/github-issue-map.json`. Read-only via `jq` is fine.
- Do NOT pick a task that's labelled `blocked` — the helper's filter already excludes it; if you somehow surface one, ask the user about the blocker before dispatching.
