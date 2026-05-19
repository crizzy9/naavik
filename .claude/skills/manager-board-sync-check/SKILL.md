---
description: Diff the persistent issue-map cache (`.claude/github-issue-map.json`) against live GitHub state to detect drift — orphaned map entries, renamed/closed issues not yet reflected, duplicate prefixes, deleted milestones. Use before any `bootstrap` re-run, after any manual GitHub UI edit, or whenever you suspect the map is stale. Triggers on phrases like "board sync", "is the map stale", "issue map drift", "refresh map", "did someone touch GitHub", "before I bootstrap", "verify issue map".
allowed-tools: Read, Bash(.claude/naavik-ops:*), Bash(jq:*), mcp__plugin_claude-code-home-manager_github__list_issues
---

# manager-board-sync-check

`.claude/github-issue-map.json` is single-writer source for `{task_id → issue#, phase → milestone#, phase → epic#}`. GitHub search API is eventually consistent (~30s–2min lag); that race produced the `#46`/`#47` duplicate-issue incident — map fix shipped in commit 7b30797. Detect drift early so `refresh-map` runs BEFORE next bootstrap or plan-driven create. Single-writer rule applies absolutely (per `AGENTS.md § GitHub state — single writer rule`).

## When to invoke

- Pre-flight before any `.claude/naavik-ops gh bootstrap --apply` re-run.
- After manual GitHub UI edit (close issue, rename milestone, delete, re-open).
- When `next-unblocked` / `milestone-status` returns surprising output (closed issue still Todo, etc.).
- User reports "GitHub looks weird" / "my issues moved" — drift first, then investigate.

## Steps

1. **Read map.**
   ```bash
   jq '{_meta, counts: {milestones: (.milestones | length), epics: (.epics | length), issues: (.issues | length)}}' .claude/github-issue-map.json
   ```
   Note `_meta.refreshed_at`. Older than ~24h → drift risk high regardless.

2. **Pull live GitHub state.**
   - Use `mcp__plugin_claude-code-home-manager_github__list_issues` with `state: "all"`, `perPage: 100`, paginated, OR script's `refresh-map` recipe (`gh api repos/$OWNER/$REPO/issues?state=all&per_page=100 --paginate`).
   - Extract `{number, title, state}`. Filter out PRs (`pull_request != null`).

3. **Diff:**

   Per map `issues` entry:
   - Issue still exists? 404 → stale entry.
   - Still open? state=closed but ROADMAP `[ ]`/`[~]` → drift other direction (sync reconciles, not map).
   - Title still starts with `[<task-id>]`? Rename → stale.

   Per open `[<task-id>] ...` issue on GitHub:
   - task-id in map's `issues` block? Missing → map miss (likely duplicate race, `#46`/`#47` pattern).

   Per `[Epic] <phase>` issue:
   - Phase in map's `epics` block?
   - Multiple open issues w/ same `[Epic] <phase>` prefix? Duplicate.

   Per milestone:
   - In map's `milestones` block? Same reconciliation.

4. **Emit report:**
   ```
   ISSUE-MAP DRIFT REPORT

   Stale map entries (issue gone or renamed):
     - issues.<task-id> → #<N>  (closed/deleted/renamed)

   Missing map entries (issue on GitHub but not in map):
     - [<prefix>] <title>  → #<N>

   Duplicate prefixes on GitHub:
     - [<prefix>] <title>  → #<orig> (open) + #<dup> (open)
       Recommend: close higher-# dup, then refresh-map.

   Milestone drift:
     - milestones.<name> → #<N>  (renamed/deleted)

   Status options (post-A.28): board has 4 Status options — Todo / In Progress / Done /
   Backlog. `.claude/github-project.json` must have `.status_options.backlog` populated;
   if missing, run `.claude/naavik-ops gh add-status Backlog --color GRAY` then re-run
   init. Backlog asymmetric with ROADMAP (ROADMAP `[ ]` → Todo OR Backlog).
   ```

5. **Recommend action.**
   - Any drift → `.claude/naavik-ops gh refresh-map` rebuilds from authoritative GitHub. Title-prefix collisions resolve (open, lowest-#).
   - Duplicates → close higher-# dup via `gh issue close <DUP> --reason "not planned"` + comment "Duplicate of #<ORIG>. Closing per CLAUDE.md § GitHub state — single writer." Then `refresh-map`.
   - Document drift in plan's `## Deviations from plan` if it surfaced a process bug.

## Canonical references

- `.claude/naavik_ops/gh.py` § `cmd_refresh_map` (lines 1040–1127).
- `AGENTS.md` § GitHub state — single writer rule (codified 2026-05-16).
- `CLAUDE.md` § GitHub state — single writer rule.
- `docs/AGENT_OPS.md` § 6.6 + § 9.5 (duplicate-issue cleanup recipe).

## When NOT to invoke

- During active `/build` — drift checks pre-run, not mid-loop.
- `refresh-map` already ran this session AND nothing mutated state since.
- Compaction events.

## Forbidden during invocation

- Do NOT hand-edit `.claude/github-issue-map.json`. Read-only.
- Do NOT use `gh issue create` / `gh issue close` to "fix" drift — go through `.claude/naavik_ops/gh.py`. Closing a duplicate via raw `gh issue close` is acceptable cleanup, but MUST run `refresh-map` after.
- Do NOT run `bootstrap --apply` before drift clears. Stale map → duplicate issues recreated.
