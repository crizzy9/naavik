---
description: Identify the next unblocked GitHub Project task for the current milestone via `.claude/naavik-ops gh next-unblocked` and the persistent issue-map cache. Use when manager runs the operating-loop step 2 (Pick next), when the user asks "what's next" or "pick the next task" or "what should I work on", or whenever a `/build` run needs the next item after closing the previous one. Triggers on phrases like "next task", "pick next", "what's next", "next unblocked", "what should I work on", "operating loop step 2".
allowed-tools: Read, Bash(.claude/naavik-ops:*), Bash(jq:*)
---

# manager-pick-next

Operating loop step 2: find highest-priority unblocked **Todo** issue for current milestone. Backlog items are deferred + skipped by `next-unblocked`. Within Backlog, only EPICS carry Priority (item-level unprioritized). When Todo empty (`next-unblocked` → null), invoke `Skill: manager-backlog-promote` to surface top-priority Backlog epic + items for user pick via AskUserQuestion. Manager applies picks via `.claude/naavik-ops gh set-status <id> Todo` (one MIRROR per item) then resumes loop. Single-writer rule: only helper script reads/writes Project state.

## When to invoke

- Manager operating loop step 2 (`/build`): right after state load, before architect dispatch.
- User asks "what's next" / "pick next" / "what should I work on" — surface recommendation without dispatching.
- Post-merge, post-archive — looping back to pick another.

## Steps

1. **Run helper.**
   ```bash
   .claude/naavik-ops gh next-unblocked
   ```
   Returns next open issue with Status=Todo, sorted by Priority (`CRITICAL > HIGH > MEDIUM > LOW`), excluding `blocked`/`epic` labels. Single JSON object or `null`.

2. **Parse JSON.** Extract `number`, `title`, `url`, `priority`, `labels`.

   Backlog items never appear (filter is Status=Todo only). Within Backlog, only EPICS carry Priority. `backlog-by-epic` is read primitive for auto-promote; this skill is for active-cycle Todo only.

3. **Cross-reference issue map** for context:
   ```bash
   jq --arg t "<title>" '.issues | to_entries[] | select(.value == <issue-num>)' .claude/github-issue-map.json
   ```
   Gives ROADMAP task-id (e.g. `PC.5`) keyed to Issue #.

4. **Read `ROADMAP.md`** for row matching task-id — priority, effort, notes. Use `Grep "[<task-id>]"` or `Read ROADMAP.md` with offset around phase header.

5. **Emit one-line summary:**
   ```
   Next: [<task-id>] <title> (priority: <PRIORITY>, milestone: <milestone>, issue: #<N>, estimate: <X>)
   ```
   Example: `Next: [PC.5] SECRET_KEY boot-time enforcement (priority: MEDIUM, milestone: Pre-Phase-2 paper cuts, issue: #7, estimate: ~1h)`.

6. **If `next-unblocked` returns `null`,** Todo column empty for milestone. **Invoke `Skill: manager-backlog-promote`** to surface next-priority Backlog epic + items via AskUserQuestion. Manager applies picks via `.claude/naavik-ops gh set-status <id> Todo` (one MIRROR per item) and resumes step 1. No auto-promote without user consent. If promote skill also returns "Backlog empty," milestone fully cleared — emit:
   ```
   Next: <none> — milestone <name> empty (Todo + Backlog). Recommend `/standup` or pick a different milestone.
   ```

## Canonical references

- `.claude/naavik_ops/gh.py` § `cmd_next_unblocked` (lines 713–759) — sort key + label filters.
- `.claude/agents/manager.md` § Operating loop step 2.
- `docs/AGENT_OPS.md` § 6.6 — issue-map cache structure.
- `AGENTS.md` § GitHub state — single writer rule.

## When NOT to invoke

- Mid-flight single-task `/build` — skip until current task merged + archived.
- User already named task (`claude /build "PC.5"`) — task is given.
- Compaction events.

## Notes

- **Gap-preservation expected.** `naavik-ops task next-unblocked <version>` iterates tasks in `priority DESC → position ASC` order; gaps in position numbering are normal (a task moved out of the patch leaves a gap). Skip the missing slot; don't surface it as a drift warning. Codified in `.claude/memory/knowledge/patch-version-position-stability.md` + enforced in `naavik-ops task move` from 0.7.0.13 (plan 28).

## Forbidden during invocation

- Do NOT call `gh issue list` / `gh api graphql` directly — helper is sole reader/writer; bypassing it re-introduces the duplicate-issue race (`AGENTS.md § GitHub state — single writer rule`).
- Do NOT hand-edit `.claude/github-issue-map.json`. Read-only via `jq` fine.
- Do NOT pick `blocked`-labelled task — filter excludes it; if surfaced, ask user about blocker before dispatching.
