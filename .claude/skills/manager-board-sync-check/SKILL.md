---
description: Diff the persistent issue-map cache (`.claude/github-issue-map.json`) against live GitHub state to detect drift — orphaned map entries, renamed/closed issues not yet reflected, duplicate prefixes, deleted milestones. Use before any `bootstrap` re-run, after any manual GitHub UI edit, or whenever you suspect the map is stale. Triggers on phrases like "board sync", "is the map stale", "issue map drift", "refresh map", "did someone touch GitHub", "before I bootstrap", "verify issue map".
allowed-tools: Read, Bash(scripts/gh-project.sh:*), Bash(jq:*), mcp__plugin_claude-code-home-manager_github__list_issues
---

# manager-board-sync-check

The persistent issue-map cache (`.claude/github-issue-map.json`) is the single-writer source of truth for `{task_id → issue#, phase → milestone#, phase → epic#}`. The GitHub search API is eventually consistent (~30s–2min indexing lag) and that race produced the `#46`/`#47` duplicate-issue incident — the map fix shipped in commit 7b30797. This skill detects drift early so a `refresh-map` runs BEFORE the next bootstrap or plan-driven create. Single-writer rule from `AGENTS.md § GitHub state — single writer rule` applies absolutely.

## When to invoke

- Manager's pre-flight before any `scripts/gh-project.sh bootstrap --apply` re-run.
- After any manual GitHub UI edit by the user (close issue, rename milestone, delete issue, re-open closed).
- When `next-unblocked` or `milestone-status` returns surprising output (issue you closed still showing as Todo, or vice versa).
- When the user reports "GitHub looks weird" or "my issues moved" — drift first, then investigate.

## What this skill does

1. **Read the map.**
   ```bash
   jq '{_meta, counts: {milestones: (.milestones | length), epics: (.epics | length), issues: (.issues | length)}}' .claude/github-issue-map.json
   ```
   Note the `_meta.refreshed_at` timestamp. If older than ~24h, drift risk is high regardless.

2. **Pull live GitHub state.**
   - Use `mcp__plugin_claude-code-home-manager_github__list_issues` with `state: "all"` and `perPage: 100`, paginated, OR the script's `refresh-map` recipe (which uses `gh api repos/$OWNER/$REPO/issues?state=all&per_page=100 --paginate`).
   - Extract `{number, title, state}` for each. Filter out PRs (where `pull_request != null`).

3. **Diff:**

   For each map entry under `issues`:
   - Does the issue still exist?  If GitHub returns 404, the entry is stale.
   - Is it still open?  If state=closed but ROADMAP still has `[ ]` or `[~]`, that's drift in the other direction (sync should reconcile, not the map).
   - Does its title still start with the matching `[<task-id>]` prefix?  Rename → stale.

   For each open `[<task-id>] ...` issue on GitHub:
   - Is the task-id in the map's `issues` block?  If not, that's a map miss — most likely a duplicate-issue race (matches the `#46`/`#47` pattern).

   For each `[Epic] <phase>` issue:
   - Is the phase in the map's `epics` block?
   - Are there multiple open issues with the same `[Epic] <phase>` prefix?  Duplicate.

   For each milestone:
   - Is the milestone in the map's `milestones` block?  Same reconciliation logic.

4. **Emit the drift report:**
   ```
   ISSUE-MAP DRIFT REPORT

   Stale map entries (issue gone from GitHub or renamed):
     - issues.<task-id> → #<N>  (issue closed/deleted/renamed)

   Missing map entries (issue on GitHub but not in map):
     - [<prefix>] <title>  → #<N>

   Duplicate prefixes on GitHub:
     - [<prefix>] <title>  → #<orig> (open) + #<dup> (open)
       Recommend: close higher-numbered dup, then refresh-map.

   Milestone drift:
     - milestones.<name> → #<N>  (renamed or deleted)
   ```

5. **Recommend action.**
   - Any drift → run `scripts/gh-project.sh refresh-map` to rebuild from authoritative GitHub state. Collisions on title prefix resolve to (open, lowest-#).
   - Duplicates → close the higher-numbered dup via `gh issue close <DUP> --reason "not planned"` + comment "Duplicate of #<ORIG>. Closing per CLAUDE.md § GitHub state — single writer." Then `refresh-map`.
   - Document in the relevant plan's `## Deviations from plan` section if the drift surfaced a process bug.

## Canonical references

- `scripts/gh-project.sh` § `cmd_refresh_map` (lines 1040–1127) — the reconciler.
- `AGENTS.md` § GitHub state — single writer rule (codified 2026-05-16).
- `CLAUDE.md` § GitHub state — single writer rule.
- `docs/AGENT_OPS.md` § 6.6 + § 9.5 (duplicate-issue cleanup recipe).

## When NOT to invoke

- During an active `/build` — drift checks before the run, not mid-loop.
- If `refresh-map` was already run in this session AND nothing else mutated state in between.
- Compaction events.

## Forbidden during invocation

- Do NOT hand-edit `.claude/github-issue-map.json`. Read-only. The script is the sole writer.
- Do NOT use `gh issue create` / `gh issue close` to "fix" drift — go through `scripts/gh-project.sh` subcommands. Closing a duplicate via raw `gh issue close` is acceptable cleanup, but you MUST then run `refresh-map` to reconcile.
- Do NOT run `bootstrap --apply` before drift clears. The map is what gives bootstrap idempotency; stale map → duplicate issues recreated.
