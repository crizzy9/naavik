---
Status: DRAFT
Type: execution
Authored: 2026-05-16
Last updated: 2026-05-16
Depends on: none
GitHub: #48
---

# 16 · Agent System v2 — cold-start infra + per-agent skill suite + git automation

## Goal

Ship the agent-system substrate that collapses the user's day-to-day delivery loop to "approve the plan, approve the PR, approve the milestone" — three gates per task. The work lands in four phases: (1) cold-start hook + skill + `Skill` tool on every agent + git `prepare-commit-msg` hook + Project v2 automation guide; (2) per-agent skill suite under `.claude/skills/<name>/SKILL.md` (~28 skills total) so each specialist auto-loads the right context + checklist at the right moment; (3) first real `/build` shipping PC.5 end-to-end (this satisfies ROADMAP row A.8); (4) second `/build` shipping PC.6 to prove the loop is reliable. Phases halt at each boundary for user review. This plan is `Type: execution` — no design doc graduates; the plan body IS the contract.

## Why

Current state (post-A.12, 2026-05-16): 6 specialist agents + 13 slash commands + a fully-bootstrapped GitHub Project v2 mirror + 800-line ROADMAP + 11 canonical reference docs. Every fresh `claude --agent <name>` dispatch starts cold and has to re-read 6–10 files before it's productive — a drift trap because no two cold starts are identical, the engineer might skip `AGENTS.md § Key Conventions § CLI` and silently extend the vault, and the architect might miss the "single-doc-tracking" rule and duplicate ROADMAP into a plan. ROADMAP row `A.11` (HIGH priority) is the structural fix: deterministic cold-start via hook + skill, agent-specific skill suites that auto-trigger on the right phrases, and git automation that turns branch names into auto-closed Issues on merge. `A.11` blocks `A.8` (first end-to-end `/build`) — without v2, the validation would just exercise the old loop. Plans 17 (PC.5) and 18 (PC.6) author themselves out of the validation runs in Phases 3 and 4.

## Proposal

The four phases halt independently. Phase 1 is engineer-only infrastructure (this plan specifies every file). Phase 2 is a ~28-skill authoring sprint (this plan specifies the per-agent suite + naming + layout, leaving the individual skill bodies as Phase-2 engineering work). Phases 3 and 4 are user-initiated `/build` runs that validate Phases 1+2 by shipping real product work.

### A · Locked decisions (don't re-debate)

From the kickoff prompt at `docs/prompts/agent-system-v2.md` § "Decisions locked":

- **Cold-start mechanism** = hook + skill (belt + suspenders). Research confirms `SessionStart` fires only on parent sessions (not `Task`-dispatched subagents); `SubagentStart` does fire on subagents but cannot block. The `naavik-cold-start` skill is the only mechanism that works in every context — the hooks are the deterministic backstop that fires before the agent even starts thinking.
- **Skill location** = project-level `.claude/skills/<name>/SKILL.md` (committed to the repo, per-fork). NOT user-level `~/.claude/skills/` (would diverge per contributor).
- **Per-agent suite** = 3–5 skills per agent + 4 shared cross-agent skills. Total ~28 skills.
- **Phase by phase** = HALT after Phase 1 + HALT after Phase 2 for user review. Phases 3 + 4 are user-initiated.
- **Skill naming** = `<agent>-<verb>` for agent-specific (e.g. `manager-pick-next`), `naavik-<verb>` for shared (e.g. `naavik-cold-start`). See § C.1 for rationale.
- **ROADMAP row** = `A.11` (new row, not folded into `A.8`; `A.8` is the validation deliverable, `A.11` is the infra that makes it meaningful).
- **All agents stay on `claude-opus-4-7[1m]`.** User has the highest-tier Anthropic sub; no Sonnet downgrade in Phase 1 (the engineer prompt's legacy `ESCALATE: opus` pattern is now stale — flag for Phase 2 cleanup as a tangential one-liner per-prompt). This plan ships nothing in `model:` frontmatter under `.claude/agents/*.md`.

### B · Research summary (locked from authoring research, 2026-05-16)

| Topic | Finding | Source |
| --- | --- | --- |
| `SessionStart` matchers | `startup` / `resume` / `clear` / `compact`. Does NOT fire for `Task` dispatches. | [Claude Code hooks reference](https://code.claude.com/docs/en/hooks) |
| `SessionStart` output | Plain `echo` to stdout is injected as `<system-reminder>` context. JSON with `hookSpecificOutput.additionalContext` is the structured form. Both are valid. | Same |
| `SubagentStart` | Fires on `Task` tool dispatch. Matchable by `agent_type`. Cannot block. Output via `additionalContext` JSON. **Known unreliability** ([anthropics/claude-code#27755](https://github.com/anthropics/claude-code/issues/27755)) — sometimes doesn't fire from settings.json. | Same; GitHub issue tracker |
| Skill spec | One directory per skill (`<name>/SKILL.md` required; supporting files allowed alongside). Frontmatter: `description` is the auto-trigger heuristic. Pushy descriptions trigger more reliably ("Use when…", "Triggers on phrases like…"). | [Claude Code skills reference](https://code.claude.com/docs/en/skills) |
| Skill content lifecycle | Once invoked, skill content stays in context for the rest of the session; auto-compaction re-attaches the most-recent invocation (5k tokens, 25k shared budget). | Same |
| Project-level vs user-level | Project skills load from `.claude/skills/` in starting dir + every parent up to repo root + every nested `.claude/skills/` discovered on demand. Live change detection works without restart for edits within an already-watched dir. | Same |
| `prepare-commit-msg` args | `$1` = commit-msg file path, `$2` = source (`message` \| `template` \| `merge` \| `squash` \| `commit`), `$3` = SHA on amend. Edit `$1` in place; exit non-zero aborts. | [git-scm.com/docs/githooks](https://git-scm.com/docs/githooks) |
| Project v2 automation API | Programmatic configuration of Project v2 workflow rules (auto-add, PR-closes-issue, status-on-close) is NOT exposed through GraphQL as of 2026-05; manual UI setup required. | GitHub Projects API docs (confirmed via web search) |

### C · Open questions — resolved here (no Open questions remaining)

All 6 questions from the kickoff prompt have been resolved by research. They appear in the Approval checklist for user sign-off; this section captures the option matrix + recommendation for each so the user can review the reasoning before approving.

#### C.1 — Skill naming convention

| Option | Clarity | Collision risk | Discoverability | Tree readability |
| --- | --- | --- | --- | --- |
| Flat (`pick-next`, `stack-invariants`) | Lowest — "pick-next from where?" | High — collides with built-in `pick-next` if Anthropic ships one | Worst — alphabetical sort mixes agents | Worst — 28 dirs in a flat list |
| `naavik-<agent>-<verb>` (`naavik-manager-pick-next`) | High | Lowest — fully namespaced | Good but verbose | Good but verbose |
| **`<agent>-<verb>` agent-specific + `naavik-<verb>` shared** | High | Low — agent prefix dedupes | Good — `manager-*` groups visually | Good — 6 agent prefixes + 4 `naavik-*` |

**Recommendation: hybrid.** `<agent>-<verb>` for agent-scoped skills (`manager-pick-next`, `architect-plan-quality-bar`, `engineer-stack-invariants`); `naavik-<verb>` for shared cross-agent skills (`naavik-cold-start`, `naavik-roadmap-status`, `naavik-deviations-check`, `naavik-vault-sunset-guard`). Lowest token cost in names + clean alphabetical grouping in `.claude/skills/` directory listings + the `naavik-` prefix communicates "any agent can invoke this" without forcing every name to repeat it.

#### C.2 — Per-skill directory layout

| Option | Supported by Claude Code? | Notes |
| --- | --- | --- |
| One dir per skill (`.claude/skills/<name>/SKILL.md`) | **Yes — canonical** | Per the spec, "Each skill is a directory with `SKILL.md` as the entrypoint." Supporting files (scripts, references, assets) live alongside. |
| One dir per agent, multiple `SKILL.md` files inside | **No** | The spec is unambiguous: `<skill-name>/SKILL.md` is the entrypoint. Nested `SKILL.md`s are not loaded as separate skills. |

**Recommendation: one dir per skill.** Forced by the spec — no trade-off to weigh.

#### C.3 — Cold-start mechanism (SessionStart vs SubagentStart vs skill)

| Option | Fires on parent? | Fires on subagent? | Can inject context? | Reliable? |
| --- | --- | --- | --- | --- |
| `SessionStart` hook only | Yes | **No** | Yes (stdout / additionalContext) | Yes |
| `SubagentStart` hook only | No | Yes (Task dispatch) | Yes (additionalContext) | **No** ([#27755](https://github.com/anthropics/claude-code/issues/27755) — known unreliable) |
| `Skill: naavik-cold-start` only | Yes (manual / pushy description) | Yes (manual / pushy description) | Yes (skill body) | Yes |
| **Hook (SessionStart only) + Skill (everywhere)** | Yes (hook) | Yes (skill) | Yes | Yes |

**Recommendation: hook + skill.** `SessionStart` hook fires deterministically on the parent session and reminds Claude to invoke the skill; the `naavik-cold-start` skill is the only mechanism that works reliably in subagent dispatches (the `SubagentStart` hook is documented but unreliable per the upstream issue tracker, so we don't depend on it). The agent prompts get one updated line: "Your first action MUST be `Skill: naavik-cold-start`." That makes the skill self-invoking even if both hooks fail.

#### C.4 — Trigger-string strategy

Per the skills spec: "Claude has a tendency to undertrigger skills; descriptions should be pushy." Recommended pattern for every skill:

```
description: <one-line capability>. Use when <concrete trigger 1>, <concrete trigger 2>, or <concrete trigger 3>. Triggers on phrases like "<exact phrase>", "<exact phrase>".
```

Example for `manager-pick-next`:

```
description: Identify the next unblocked GitHub Project task for the current milestone via scripts/gh-project.sh next-unblocked. Use when manager needs to pick the next task in the operating loop, when the user asks "what's next" or "pick next task", or whenever step 2 of manager.md's operating loop fires. Triggers on phrases like "next task", "what should I work on", "pick next", "next unblocked".
```

**Validation:** Phase 1 quality gate explicitly fires a fresh `claude --agent engineer "What's the status of PC.5?"` dispatch and observes whether the right skills auto-load. If a skill doesn't fire on a generic-shape prompt, iterate the description's trigger-phrases section. The 1,536-char description cap (per spec) is plenty of room.

#### C.5 — `Skill` tool on engineer

Engineer's `tools:` line today: `Read, Edit, Write, Glob, Grep, Bash, Task, mcp__plugin_claude-code-home-manager_context7__*, mcp__plugin_claude-code-home-manager_nixos__*, mcp__plugin_claude-code-home-manager_github__pull_request_*, mcp__plugin_claude-code-home-manager_github__add_comment_to_pending_review, mcp__plugin_claude-code-home-manager_github__create_pull_request, mcp__plugin_claude-code-home-manager_github__get_file_contents, mcp__plugin_claude-code-home-manager_github__list_pull_requests`.

The narrow tool list reflects security intent: engineer can read + write code + commit + open PRs but not run arbitrary `gh api graphql` mutations against the Project board. **Adding `Skill` is safe** because skills are read-only markdown documentation + checklists, not tool grants. The skill body might reference a `Bash` invocation, but engineer ALREADY has `Bash` — the skill doesn't widen the blast radius. `allowed-tools:` per-skill could narrow it further if we ever want; out of scope for v1.

**Recommendation: yes.** Engineer benefits most from `engineer-stack-invariants`, `engineer-manual-qa-gate`, `engineer-llm-tracker-wrap`, `engineer-deviation-log`, `engineer-pr-template`.

#### C.6 — Branch-naming regex

Strict format proposed: `^(feat|fix|chore|docs|refactor)/(?<task_id>[A-Z]+\.\d+(?:[a-z])?|PC\.\d+|DEF-\d+|A\.\d+)-[a-z0-9-]+$`

| Branch | Matches? | Task-id extracted |
| --- | --- | --- |
| `feat/PC.5-secret-key-enforcement` | yes | `PC.5` |
| `fix/2.11-cli-sunset` | yes | `2.11` |
| `docs/A.11-agent-system-v2` | yes | `A.11` |
| `chore/DEF-03-stale-draft-cleanup` | yes | `DEF-03` |
| `refactor/2.12a-vault-deprecation-prep` | yes | `2.12a` |
| `feat/whatever-no-task-id` | no | (silent no-op, no `Closes #N` appended) |
| `main` / `feature-branch` / `experimental/foo` | no | (silent no-op) |

**Recommendation: strict regex; hook bails silently (no `Closes #N`) on non-match.** Bailing silently means the hook never interferes with experimental branches or rebases — operator can always commit by hand. The hook logs to stderr (one line: `prepare-commit-msg: branch <X> does not match task-id pattern; skipping Closes-N append`) for debuggability.

### D · Phase 1 — Infrastructure (engineer-dominant)

Every file is specified. The engineer should not need to re-research.

#### D.1 — `.claude/hooks/cold-start.sh` (new file)

Bash script. Reads `SessionStart` JSON payload from stdin (we only care about `source` to gate on `startup` and skip noisy `compact` injections). Emits a plain-text reminder to stdout (which Claude Code injects as `<system-reminder>`).

```bash
#!/usr/bin/env bash
# .claude/hooks/cold-start.sh
# Fires on SessionStart (matchers: startup, resume — not compact: ROADMAP already gets
# re-attached via skill content lifecycle). Injects a pinned "required reading" block +
# current state snapshot so every fresh session lands oriented.
#
# Subagent dispatches DO NOT receive SessionStart (per Claude Code hook spec, 2026-05).
# The `naavik-cold-start` skill is the subagent equivalent — each agent prompt requires
# it as the first action. Belt + suspenders.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 0  # fail open — never block session startup

# Read the SessionStart event payload (we only use source to skip compact).
INPUT="$(cat || true)"
SOURCE="$(echo "$INPUT" | jq -r '.source // "startup"' 2>/dev/null || echo "startup")"

# On compact, skip — the skill content lifecycle re-attaches invoked skills automatically.
if [[ "$SOURCE" == "compact" ]]; then
  exit 0
fi

# Surface the current ROADMAP "Last updated" line for "what's fresh".
LAST_UPDATED="$(grep -m1 '^> Last updated:' ROADMAP.md 2>/dev/null | sed 's/^> //' || echo 'unknown')"

# Tail recent agent activity.
RUNS_TAIL=""
if [[ -f traces/runs.log ]]; then
  RUNS_TAIL="$(tail -n 5 traces/runs.log 2>/dev/null || true)"
fi

# Budget snapshot (gitignored; may not exist on fresh clone).
BUDGET=""
if [[ -f .claude/budget-ledger.json ]]; then
  BUDGET="$(jq -r '"today=\(.current_day) total=\(.total_today)"' .claude/budget-ledger.json 2>/dev/null || true)"
fi

cat <<EOF
Naavik cold-start reminder. Your first action MUST be: Skill: naavik-cold-start

That skill will load the canonical context (AGENTS.md, ROADMAP_OVERVIEW.md, AGENT_OPS.md, etc.) in the right order for your role. Until it has run, do not read individual files directly.

Current state snapshot (use this to decide whether the skill needs to re-fetch state):
- ROADMAP $LAST_UPDATED
- Recent runs:
$(echo "$RUNS_TAIL" | sed 's/^/    /')
- Budget: $BUDGET

If you are a subagent dispatched via Task, this hook did NOT fire for you (SessionStart only fires on parent sessions). Invoke Skill: naavik-cold-start regardless — your agent prompt's "Required reading on cold start" section enforces this.
EOF

exit 0
```

Permission: `chmod +x .claude/hooks/cold-start.sh` (engineer adds via `git update-index --chmod=+x` or `chmod +x` then `git add`).

#### D.2 — `.claude/settings.json` (modify)

Current contents:

```json
{
  "enabledPlugins": {
    "frontend-design@claude-plugins-official": true
  }
}
```

Add a `hooks` block. Final state:

```json
{
  "enabledPlugins": {
    "frontend-design@claude-plugins-official": true
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/cold-start.sh"
          }
        ]
      },
      {
        "matcher": "resume",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/cold-start.sh"
          }
        ]
      }
    ]
  }
}
```

Note: do NOT register a `compact` matcher — the skill content lifecycle handles compaction re-attachment per the spec. Do NOT register a `SubagentStart` hook — known unreliable; the skill mechanism is the canonical replacement.

#### D.3 — `.claude/skills/naavik-cold-start/SKILL.md` (new file)

```yaml
---
description: Load the canonical context for any Naavik agent at the start of a session or subagent dispatch — read AGENTS.md, ROADMAP_OVERVIEW.md, AGENT_OPS.md, ARCHITECTURE.md, and the agent's specific cold-start list in the correct order. Use this as the FIRST action of every new session or subagent dispatch. Triggers on phrases like "cold start", "what's the status", "where are we", "let's start", "begin", or the very first user message of any session.
allowed-tools: Read, Glob, Grep, Bash(grep:*), Bash(jq:*)
---

# naavik-cold-start

Naavik's agents land cold from a fresh `claude --agent <name>` dispatch. Without this skill the agent picks an arbitrary subset of the canonical guides and risks missing key conventions (the CLI/vault sunset is the historical example — engineer dispatches that skip `AGENTS.md § Key Conventions § CLI` have extended the vault in the past).

This skill is the deterministic cold-start: it loads the same files, in the same order, every time.

## Step 1 — Read the canonical guides (in order)

For every agent, regardless of role:

1. `AGENTS.md` § Quick Start + § Workflow (steps 2 + 4 + 5 + 7) + § Key Conventions § CLI + § Single-doc-tracking + § GitHub state — single writer rule
2. `docs/ROADMAP_OVERVIEW.md` (130 lines — full)
3. `docs/AGENT_OPS.md` § 1–7

## Step 2 — Read the agent-specific cold-start list

Look up your agent's "Required reading on cold start" section in `.claude/agents/<agent>.md`. Read those files in the order listed.

## Step 3 — Read the operational state

- `traces/runs.log` tail 10 — recent agent activity
- `.claude/budget-ledger.json` — today's spend vs cap
- `.claude/github-issue-map.json` — which Issue # implements which ROADMAP task

## Step 4 — Confirm the cold-start is complete

Output one line of `Loaded:` summary so the user knows you're oriented. Then proceed with the actual task.

## When NOT to invoke

- Compaction events — Claude Code's skill content lifecycle re-attaches invoked skills automatically. Re-invoking would waste tokens.
- The user has already told you the task and you've already read the relevant files in this turn — skip the redundant read.

## Forbidden during cold-start

- Do not extend `src/cli/` or `src/services/vault.py`. Both are on the sunset track (Phase 2 tasks 2.11 / 2.12).
- Do not propose tracking-table duplication of ROADMAP into plan files (drift trap per `AGENTS.md § Single-doc-tracking`).
- Do not write GitHub Issue / Project state directly via `gh issue create` or `gh api graphql` — all mutations go through `scripts/gh-project.sh` (per `CLAUDE.md § GitHub state — single writer rule`).
```

#### D.4 — `.claude/agents/{manager,architect,engineer,hacker,devops}.md` (modify)

Each agent's `tools:` line needs `Skill` appended (`designer` already has it per kickoff prompt — verify in Phase 1).

**Exact edits per agent (one-line each):**

| File | Current `tools:` line — append `, Skill` at the end |
| --- | --- |
| `.claude/agents/manager.md:4` | `tools: Bash, Read, Glob, Grep, Edit, Write, Task, WebSearch, WebFetch, mcp__plugin_claude-code-home-manager_github__*` → append `, Skill` |
| `.claude/agents/architect.md:4` | `tools: Read, Glob, Grep, Edit, Write, Bash, WebSearch, WebFetch, Task, mcp__plugin_claude-code-home-manager_context7__*, mcp__plugin_claude-code-home-manager_nixos__*, mcp__plugin_claude-code-home-manager_tavily__*, mcp__plugin_claude-code-home-manager_github__*` → append `, Skill` |
| `.claude/agents/engineer.md:4` | `tools: Read, Edit, Write, Glob, Grep, Bash, Task, mcp__plugin_claude-code-home-manager_context7__*, mcp__plugin_claude-code-home-manager_nixos__*, mcp__plugin_claude-code-home-manager_github__pull_request_*, mcp__plugin_claude-code-home-manager_github__add_comment_to_pending_review, mcp__plugin_claude-code-home-manager_github__create_pull_request, mcp__plugin_claude-code-home-manager_github__get_file_contents, mcp__plugin_claude-code-home-manager_github__list_pull_requests` → append `, Skill` |
| `.claude/agents/hacker.md:4` | `tools: Read, Write, Glob, Grep, Bash, WebSearch, WebFetch, Task, mcp__plugin_claude-code-home-manager_github__*, mcp__plugin_claude-code-home-manager_context7__*` → append `, Skill` |
| `.claude/agents/devops.md:4` | `tools: Bash, Read, Write, Edit, Glob, Grep, Task, WebSearch, WebFetch, mcp__plugin_claude-code-home-manager_github__*, mcp__plugin_claude-code-home-manager_context7__*, mcp__plugin_claude-code-home-manager_nixos__*, mcp__plugin_claude-code-home-manager_n8n__*` → append `, Skill` |
| `.claude/agents/designer.md:4` | `tools: Read, Edit, Write, Glob, Grep, Bash, Task, Skill, WebSearch, WebFetch` — **verify only**; already has `Skill` per kickoff prompt. |

Each agent's `# Required reading on cold start` section gets one inserted line at the top of that section:

> Your first action MUST be `Skill: naavik-cold-start`. Don't read individual files directly until the skill has loaded the canonical context. The list below is what the skill loads — kept here for reference.

The existing numbered list stays — it's the contract the skill enforces. The line above just makes the skill the entry point.

#### D.5 — `.claude/hooks/git/prepare-commit-msg` (new file)

Bash script. Parses current branch name, extracts task-id via the regex from § C.6, looks up Issue # in `.claude/github-issue-map.json`, appends `Closes #N` to the commit message if not already present. Silent no-op on non-matching branches.

```bash
#!/usr/bin/env bash
# .claude/hooks/git/prepare-commit-msg
# Auto-appends `Closes #<N>` to commit messages on branches named
# <type>/<task-id>-<slug> when the task-id is in .claude/github-issue-map.json.
#
# Install:
#   ln -sf ../../.claude/hooks/git/prepare-commit-msg .git/hooks/prepare-commit-msg
#
# Args:
#   $1 = path to commit message file (mandatory; passed by git)
#   $2 = commit source (message | template | merge | squash | commit)
#   $3 = SHA-1 (only set on amends)
#
# Bails out silently when:
#   - $2 is merge | squash | commit (don't munge those messages)
#   - branch name doesn't match the regex
#   - .claude/github-issue-map.json is missing or doesn't have the task-id
#   - the commit message already contains "Closes #" or "Fixes #" or "Resolves #"

set -euo pipefail

MSG_FILE="${1:?usage: prepare-commit-msg <msg-file> [source] [sha]}"
SOURCE="${2:-}"

# Skip merge / squash / amends — those messages are not authored by the operator
# (they're git-generated or pre-filled), and we don't want to munge them.
case "$SOURCE" in
  merge|squash|commit) exit 0 ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[[ -n "$REPO_ROOT" ]] || exit 0

ISSUE_MAP="$REPO_ROOT/.claude/github-issue-map.json"
[[ -f "$ISSUE_MAP" ]] || { echo "prepare-commit-msg: no issue map; skipping" >&2; exit 0; }

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
[[ -n "$BRANCH" && "$BRANCH" != "HEAD" ]] || exit 0

# Regex: <type>/<task-id>-<slug>
# task-id ∈ { A.11, 2.11, 2.12a, PC.5, DEF-03 }
REGEX='^(feat|fix|chore|docs|refactor)/([A-Z]+\.[0-9]+[a-z]?|PC\.[0-9]+|DEF-[0-9]+|A\.[0-9]+)-[a-z0-9-]+$'

if [[ ! "$BRANCH" =~ $REGEX ]]; then
  echo "prepare-commit-msg: branch '$BRANCH' does not match task-id pattern; skipping Closes-N append" >&2
  exit 0
fi

TASK_ID="${BASH_REMATCH[2]}"

ISSUE_NUM="$(jq -r --arg k "$TASK_ID" '.issues[$k] // empty' "$ISSUE_MAP" 2>/dev/null || true)"
if [[ -z "$ISSUE_NUM" ]]; then
  echo "prepare-commit-msg: task-id '$TASK_ID' not in issue map; skipping" >&2
  exit 0
fi

# Bail if any closing reference already present (case-insensitive).
if grep -qiE '^(closes|fixes|resolves) #[0-9]+' "$MSG_FILE"; then
  exit 0
fi

# Append a blank line + the Closes-N trailer before any existing trailers.
# Simple approach: append to end of file. Trailers convention is "last block";
# `git commit` will reflow it.
{
  echo ""
  echo "Closes #$ISSUE_NUM"
} >> "$MSG_FILE"

exit 0
```

Permission: `chmod +x .claude/hooks/git/prepare-commit-msg`.

#### D.6 — `docs/AGENT_OPS.md` § 2.7 (new sub-section between § 2.6 and § 3)

Append to `docs/AGENT_OPS.md` § 2 (Bootstrap), after § 2.6:

```markdown
### 2.7 Enable GitHub Project v2 workflow automation (one-time, manual)

GitHub Projects v2 workflow rules — the things that auto-close, auto-add, and
auto-move items — can NOT be configured via the GraphQL API as of 2026-05.
Configure them once via the GitHub UI:

1. Navigate to your project (e.g. `https://github.com/users/<owner>/projects/<N>`).
2. Click the `…` menu (top right) → **Workflows**.
3. Enable these rules:
   - **Auto-add to project** — when an Issue is opened with label `phase:*`. This
     covers `phase:A`, `phase:pre-2`, `phase:1.x`, `phase:2`, etc.
   - **Item closed** — set Status to `Done`.
   - **Item reopened** — set Status to `Todo`.
   - **Pull request merged** — close referenced Issue (uses GitHub's built-in
     `Closes #N` / `Fixes #N` / `Resolves #N` detection).
4. Save each rule.

After this is set, the per-task delivery flow collapses to:
- Branch `feat/PC.5-secret-key-enforcement` → commit message auto-gets
  `Closes #7` via `.claude/hooks/git/prepare-commit-msg`.
- PR merge → GitHub auto-closes issue #7 → Project Status moves to `Done`.
- Manager only needs to flip the ROADMAP row to `[x]` + archive the plan.

If you change Project ID later, re-run `scripts/gh-project.sh init` so the
field option IDs cache stays current. Workflow rules survive this; they live
on the Project itself.
```

#### D.7 — `docs/AGENT_OPS.md` § 2.8 (new sub-section)

Append after § 2.7:

```markdown
### 2.8 Install the git commit-message hook (one-time, per-clone)

The `.claude/hooks/git/prepare-commit-msg` script auto-appends `Closes #<N>` to
commit messages when the current branch matches `<type>/<task-id>-<slug>`
and `<task-id>` is in `.claude/github-issue-map.json`. This is what makes the
"PR merge → Issue closes → Project Status: Done" automation work.

Install once per clone (git hooks are not committed via the .git dir):

```bash
ln -sf ../../.claude/hooks/git/prepare-commit-msg .git/hooks/prepare-commit-msg
chmod +x .git/hooks/prepare-commit-msg  # if not already executable via the symlink target
```

**Branch naming convention** (enforced by the hook regex):

```
<type>/<task-id>-<slug>
  type    ∈ { feat, fix, chore, docs, refactor }
  task-id ∈ { A.11, 2.11, 2.12a, PC.5, PC.7, DEF-03 } — must be a key in .claude/github-issue-map.json
  slug    = kebab-case description
```

Examples that auto-append the trailer:
- `feat/PC.5-secret-key-enforcement` → appends `Closes #7`
- `fix/2.11-cli-sunset` → appends `Closes #21`
- `docs/A.11-agent-system-v2` → appends `Closes #<N>` once A.11's Issue exists

Examples that silently no-op (no `Closes #N` appended; commit message untouched):
- `main` / `experimental/foo` / `feature-branch` — don't match the regex
- `feat/whatever-no-task-id-PC.99-slug` — `PC.99` not in issue map
- `git commit --amend` / merge / squash commits — hook skips per `$2` source

The hook never aborts a commit. If you need to bypass it, `git commit --no-verify`
works (but you shouldn't need to — non-matching branches are already silent).
```

#### D.8 — `AGENTS.md` § Agent System (modify — small append)

After the existing "Infrastructure" bullet list (around line 527), confirm the existing lines that say `.claude/skills/` and `.claude/hooks/` are "Planned by Phase A.11" stay accurate — they SHIP in this plan. Update to reflect the post-Phase-1 state:

- Replace `.claude/skills/` bullet's "Planned by Phase A.11" → "Shipped by Phase A.11 Phase 1 (`naavik-cold-start`) + Phase 2 (per-agent suites). One directory per skill (`<name>/SKILL.md`). Six agent prefixes (`manager-*`, `architect-*`, etc.) + shared `naavik-*` prefix for cross-agent skills."
- Replace `.claude/hooks/` bullet's "Planned by Phase A.11" → "Shipped by Phase A.11 Phase 1. Holds `cold-start.sh` (SessionStart, injects required-reading context) and `git/prepare-commit-msg` (auto-appends `Closes #N` from branch name using `.claude/github-issue-map.json`). Git hook installed via symlink (see `docs/AGENT_OPS.md` § 2.8)."

#### D.9 — `CLAUDE.md` (modify — small append after Quickstart)

Append to `CLAUDE.md` "Claude Code Quickstart" section, after step 6:

```markdown
**Cold-start invariant (post-A.11):** every agent's first action MUST be
`Skill: naavik-cold-start`. The `.claude/hooks/cold-start.sh` SessionStart hook
reminds the parent session of this; the agent prompts enforce it on subagent
dispatches. Do not read individual canonical files (AGENTS.md, ROADMAP, etc.)
before the skill has run — that path is what plan 16 fixed.
```

Bump `CLAUDE.md` "Last updated" line to `2026-05-16` and add a one-line summary of plan 16 Phase 1.

#### D.10 — `.gitignore` (verify, no change expected)

Current `.gitignore` (verified during plan authoring) does NOT exclude `.claude/skills/` or `.claude/hooks/`. Both directories are committed (the skill bodies and hook scripts are project assets, per-fork stability is the whole point). `.claude/github-project.json`, `.claude/github-issue-map.json`, and `.claude/budget-ledger.json` stay gitignored — those are per-fork machine-managed state. No edit needed; engineer confirms during Phase 1 implementation.

### E · Phase 2 — Per-agent skill suite (engineer-dominant)

~28 skills total. Per-agent suite scoped here; the individual SKILL.md body (frontmatter description + body content) is the Phase 2 implementation work. Naming follows § C.1.

**Manager suite (4 skills)** — `.claude/skills/manager-*/SKILL.md`:

| Skill | Purpose |
| --- | --- |
| `manager-pick-next` | Wraps `scripts/gh-project.sh next-unblocked` + filters by current milestone + emits a one-line "next task" summary for the operating loop step 2. |
| `manager-standup-report` | Generates the `/standup` format from current Project state + budget + recent traces. |
| `manager-board-sync-check` | Diffs `.claude/github-issue-map.json` against live GitHub state via `gh issue list`; flags drift; suggests `refresh-map` if mismatched. |
| `manager-deviation-promote` | At plan archive time, lifts `traces/<run-id>/engineer-deviations.log` lines into the plan's `## Deviations from plan` section per the AGENTS.md § Workflow step 7 contract. |

**Architect suite (4 skills)** — `.claude/skills/architect-*/SKILL.md`:

| Skill | Purpose |
| --- | --- |
| `architect-plan-quality-bar` | Checklist from `.claude/agents/architect.md` § "Plan quality bar" — runs before any plan hand-back. |
| `architect-option-matrix` | Template for the 2+ options × {capability, cost, risk, maintenance, lock-in} matrix that every non-trivial design decision must surface. |
| `architect-design-doc-graduation` | Guide for promoting a `Type: design` plan into a permanent `docs/design/SEMANTIC.md` per AGENTS.md § Workflow step 4. |
| `architect-sunset-guard` | Rejects any plan that extends `src/cli/` or `src/services/vault.py` (Phase 2 sunset tasks 2.11 / 2.12). Forces the redesign-toward-Settings-UI path. |

**Engineer suite (5 skills)** — `.claude/skills/engineer-*/SKILL.md`:

| Skill | Purpose |
| --- | --- |
| `engineer-stack-invariants` | Quick reference for FastAPI / SQLModel / HTMX / Tailwind / DaisyUI / Lucide patterns from `AGENTS.md § Key Conventions`. |
| `engineer-manual-qa-gate` | Checklist + driver-script templates for the per-surface QA gate (HTMX page / API endpoint / cron / migration / service method) per `.claude/agents/engineer.md § Manual QA Gate`. |
| `engineer-llm-tracker-wrap` | Reminder + template to wrap every LLM call in `services/llm_tracker.tracked_call` so ApiUsage persists. |
| `engineer-deviation-log` | Append-only template for `traces/<run-id>/engineer-deviations.log` with the canonical `[ts] DEVIATION plan=<path> what=<...> why=<...> impact=<...>` format. |
| `engineer-pr-template` | Opens the PR using `.github/pull_request_template.md` + ensures the last commit message has `Closes #N` per branch convention. |

**Designer suite (5 skills)** — `.claude/skills/designer-*/SKILL.md`:

| Skill | Purpose |
| --- | --- |
| `designer-design-tokens` | Quick lookup of `DESIGN.md` tokens (color, type, icon, voice). |
| `designer-screen-lookup` | Pulls the relevant section from `docs/design/SCREENS.md` for a given screen slug. |
| `designer-component-reuse` | Searches `docs/design/COMPONENTS.md` for existing components matching a need; flags reinventions per the "85-partial catalog" rule. |
| `designer-mockup-conventions` | Path + dimensions + naming rules for mockup exports (`docs/design/mockups/{n}-{slug}-{desktop\|mobile}.png`, 1440×900 / 375×812). |
| `designer-componentization-memo` | Handoff template to engineer per `.claude/agents/designer.md § Componentization notes`. |

**Hacker suite (3 skills)** — `.claude/skills/hacker-*/SKILL.md`:

| Skill | Purpose |
| --- | --- |
| `hacker-stride-template` | STRIDE threat model scaffold per `.claude/agents/hacker.md § Threat model output` — writes to `docs/design/THREAT_MODEL-<slug>.md`. |
| `hacker-secrets-audit` | Scans a diff for hardcoded secrets, weak hashing, env-var bypasses; cross-checks `~/.naavik/dev-credentials` gating per plan 10c. |
| `hacker-pr-security-checklist` | Auth / injection / deserialization / CSRF / OWASP-top-10 review pass per `.claude/agents/hacker.md § Default attack surfaces`. |

**Devops suite (3 skills)** — `.claude/skills/devops-*/SKILL.md`:

| Skill | Purpose |
| --- | --- |
| `devops-build-gates` | Runs `uv run ruff check .` + `uv run ruff format --check .` + `uv run pytest -x` + (live-DB-gated) `NAAVIK_LIVE_DB=1 uv run pytest -x` + summary report. |
| `devops-trace-manifest` | Writes `traces/<run-id>/MANIFEST.json` per the `docs/AGENT_OPS.md § 7.3` schema at end of run. |
| `devops-runbook-lookup` | Pulls the relevant section from `docs/RUNBOOK.md` for a given failure-mode symptom (uses the jump table in `.claude/agents/devops.md`). |

**Shared cross-agent suite (4 skills)** — `.claude/skills/naavik-*/SKILL.md`:

| Skill | Purpose |
| --- | --- |
| `naavik-cold-start` | (Shipped Phase 1.) Loads canonical context for every agent at session/subagent start. |
| `naavik-roadmap-status` | Current phase summary, what's done, what's in-flight — reads `ROADMAP.md` + `docs/ROADMAP_OVERVIEW.md`. |
| `naavik-deviations-check` | Verifies a plan has a non-empty `## Deviations from plan` section before archive per `AGENTS.md § Workflow step 7`. |
| `naavik-vault-sunset-guard` | Flags any mention or proposal of extending `src/services/vault.py`; suggests the env/Settings-UI alternative per the 2.12 pattern. |

**Total: 4 + 4 + 5 + 5 + 3 + 3 + 4 = 28 skills.** Phase 2 budget assumes ~3k tokens per skill on engineer side (description + body + cross-refs to existing docs) = ~85k tokens engineer-dominant work + ~15k tokens manager + ~10k tokens validation = ~110k total. See § H budget table.

**Phase 2 quality gate:**
- Spawn fresh dispatch of each agent and verify each invokes the appropriate skill at the appropriate moment. Example: architect's first hand-back invokes `architect-plan-quality-bar`; engineer's pre-handback step invokes `engineer-manual-qa-gate`.
- Adversarial probe: have engineer attempt to author code that extends `src/services/vault.py`; expect `naavik-vault-sunset-guard` to trigger before any code lands. Same probe for `src/cli/` (expect `architect-sunset-guard` on the planning side).

### F · Phase 3 — First real `/build` (PC.5)

User-initiated. Validates Phases 1+2 + ships `A.8` deliverable simultaneously.

Run: `claude /build "PC.5"`.

Observation checklist (manager surfaces this in the run's MANIFEST):

1. SessionStart hook fires on parent session; `naavik-cold-start` skill loads canonical context within the first ~5 reads
2. Manager dispatches architect via `Task` → architect's first action is `Skill: naavik-cold-start` (subagent path)
3. Architect produces plan at `docs/plans/17-pc5-secret-key-enforcement.md`, opens GitHub Issue, halts at PLAN GATE
4. User approves at PLAN GATE
5. Manager dispatches engineer → engineer's `Skill: engineer-stack-invariants` + `Skill: engineer-manual-qa-gate` trigger automatically
6. Engineer creates branch `feat/PC.5-secret-key-enforcement`, implements, commits — `prepare-commit-msg` hook appends `Closes #7`
7. Manager dispatches hacker + devops in PARALLEL via one `Task` message (one message, two `Task` calls per manager § 6)
8. PR GATE — user approves merge
9. On merge, GitHub auto-closes issue #7 → Project automation moves to Status: Done (assumes user enabled § 2.7 rules)
10. Manager updates ROADMAP row PC.5 to `[x]` + bumps "Last updated"
11. Plan archived at `docs/plans/archive/17-pc5-secret-key-enforcement.md` with `## Deviations from plan` section + `naavik-deviations-check` skill verifies

Halt boundary: MILESTONE GATE per manager step 15. Don't auto-advance.

### G · Phase 4 — Second `/build` (PC.6)

User-initiated. Same observation checklist as Phase 3. PC.6 is "Password complexity rules" (~2h, MEDIUM priority per `docs/ROADMAP_OVERVIEW.md § 3`). Two clean end-to-end runs confirms muscle memory.

### H · Build sequence (Phase 1 only — engineer reads this and ships)

1. **Author `.claude/skills/naavik-cold-start/SKILL.md`** first. The hook references it; ordering matters so the hook has something to invoke. Verify the description triggers on a generic prompt (`What's the status?`) before moving on.
2. **Author `.claude/hooks/cold-start.sh`**. `chmod +x`. Test by running it directly: `echo '{"source": "startup"}' | ./.claude/hooks/cold-start.sh` — expect plain-text output ending with the "If you are a subagent…" paragraph.
3. **Register in `.claude/settings.json`** (D.2). Restart `claude` to pick up the new hook registration (per spec, settings.json hooks are loaded at session start, not live).
4. **Append `Skill` to each agent's `tools:` line** (D.4 — 5 edits via `Edit` tool, one per agent file). Insert the "Your first action MUST be `Skill: naavik-cold-start`" line at the top of each agent's "Required reading on cold start" section.
5. **Author `.claude/hooks/git/prepare-commit-msg`** (D.5). `chmod +x`. Document install path in `docs/AGENT_OPS.md § 2.8`.
6. **Test the git hook in isolation** before symlinking: create a throwaway branch `feat/PC.5-test`, run `echo "test commit" > /tmp/msg`, then `./.claude/hooks/git/prepare-commit-msg /tmp/msg message`. Expect `/tmp/msg` to contain `test commit\n\nCloses #7`. Test the no-op path with branch `main` (already on `main` likely — `git checkout -b experimental/foo` and re-run; expect unchanged `/tmp/msg`).
7. **Add `docs/AGENT_OPS.md § 2.7`** (Project v2 workflow rules) **and `§ 2.8`** (git hook install).
8. **Update `AGENTS.md § Agent System` Infrastructure bullets** (D.8) — flip the "Planned by Phase A.11" wording on `.claude/skills/` and `.claude/hooks/` to "Shipped by Phase A.11 Phase 1".
9. **Update `CLAUDE.md` Quickstart + "Last updated"** (D.9).
10. **Run Phase 1 quality gate** (§ I).
11. **Hand back per § J — HALT.**

### I · Phase 1 quality gate

- **Fresh subagent dispatch test.** Open a fresh `claude --agent engineer` session and submit: "What's the status of PC.5?". Observe:
  - The cold-start hook fired (presence of the system-reminder in the transcript prelude).
  - Engineer's first action is `Skill: naavik-cold-start`.
  - The skill loads `AGENTS.md`, `docs/ROADMAP_OVERVIEW.md`, `docs/AGENT_OPS.md`, the engineer-specific cold-start list, `traces/runs.log`, `.claude/budget-ledger.json` — in that order.
  - Engineer answers the question coherently (PC.5 is `SECRET_KEY` boot-time enforcement, MEDIUM priority, ~1h, not yet started, Issue #7) without asking the user for orientation.
- **Git hook test.** From the repo root:
  ```bash
  git checkout -b feat/PC.5-secret-key-test
  ln -sf ../../.claude/hooks/git/prepare-commit-msg .git/hooks/prepare-commit-msg
  chmod +x .git/hooks/prepare-commit-msg
  echo "test" > /tmp/msg
  ./.git/hooks/prepare-commit-msg /tmp/msg message
  cat /tmp/msg
  # Expected: "test\n\nCloses #7"
  ```
  Then test no-op: `git checkout -b experimental/foo` + same script; expect `/tmp/msg` unchanged.
- **Quality gates passed.** `uv run ruff check .` + `uv run ruff format --check .` clean (these are bash + JSON edits, so the only ruff-touchable change is settings.json — must be valid JSON). `uv run pytest -x` clean (no Python changes — but run to confirm no regression).

If any of the above fails, fix before hand-back. Engineer's standard 3-attempt protocol applies.

### J · Hand-back format (engineer follows verbatim)

```
Phase 1 of plan 16 shipped.

Files: created K, modified M, deleted D — grouped by area
  Created:
    .claude/hooks/cold-start.sh
    .claude/hooks/git/prepare-commit-msg
    .claude/skills/naavik-cold-start/SKILL.md
  Modified:
    .claude/settings.json (hooks.SessionStart block)
    .claude/agents/manager.md (tools: + Skill, Required reading preamble)
    .claude/agents/architect.md (same)
    .claude/agents/engineer.md (same)
    .claude/agents/hacker.md (same)
    .claude/agents/devops.md (same)
    .claude/agents/designer.md (Required reading preamble only — Skill already present)
    docs/AGENT_OPS.md (§ 2.7 + § 2.8 appended)
    AGENTS.md § Agent System (Infrastructure bullets updated)
    CLAUDE.md (Quickstart cold-start invariant line + "Last updated" bump)

Verification:
  - Cold-start hook test:    <paste the system-reminder text emitted on fresh `claude` launch>
  - Engineer fresh-dispatch test: <paste the engineer's first action + cold-start skill load summary>
  - Git hook positive test:  echo 'test' > /tmp/msg && .git/hooks/prepare-commit-msg /tmp/msg message → cat /tmp/msg = "test\n\nCloses #7"
  - Git hook negative test:  git checkout -b experimental/foo + repeat → /tmp/msg unchanged + stderr "branch ... does not match"

Tests:
  ruff check .          PASS (no Python changes; settings.json valid JSON)
  ruff format --check . PASS
  pytest -x             PASS (no Python regressions)

Deviations: <bullets per traces/<run-id>/engineer-deviations.log, or "no material deviations">

Next phase: 2 (per-agent skill suite — ~28 skills, estimated <Y>k tokens; details in plan 16 § E)
Open user decisions: <or "none">

→ HALT. Awaiting user approval before Phase 2.
```

### Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| `SessionStart` hook does not fire for subagent dispatches (confirmed by Claude Code spec) | CERTAIN | Subagents land cold without the system reminder | The agent prompts mandate `Skill: naavik-cold-start` as first action regardless. Skill is self-invoking via pushy description. Belt + suspenders. |
| Skill `description:` triggers too eagerly OR too conservatively | MEDIUM | Noise (eager) or undertrigger (conservative) | Phase 1 QA gate explicitly tests a fresh engineer dispatch with a generic "what's the status" prompt. Iterate description's trigger-phrases section if it doesn't fire. Skills spec advises "pushy" descriptions — embrace it. |
| Git hook breaks `git rebase --interactive` / `git commit --amend` / `git commit --squash` flows | LOW | Operator can't rebase | Hook bails out early on `$2 ∈ {merge, squash, commit}`. Documented in install instructions. Operator can `--no-verify` if anything else breaks. |
| `<task-id>` regex too strict; hook silently no-ops on a valid intent | LOW | One missing `Closes #N` per offending branch (recoverable: `git commit --amend`) | Hook logs to stderr on no-op so the operator sees why. Documented regex in `docs/AGENT_OPS.md § 2.8`. If the regex turns out brittle in practice, this plan's Phase-2 list adds a `manager-board-sync-check` follow-up. |
| Phase 1 token cost over-runs the engineer cap (1.5M) | LOW | Engineer hits cap mid-implementation; manager halts | Phase 1 is ~30k tokens total (small bash scripts + agent prompt edits + JSON edits + doc appends). Budget table § H is generous. Manager pre-flights before dispatch. |
| Skill content lifecycle drops a skill after compaction | LOW | Engineer mid-implementation loses `engineer-stack-invariants` context | Per spec, the most-recently-invoked skill stays attached (5k tokens). Re-invoke explicitly if behavior drifts. Document in `engineer-stack-invariants` body. |
| `Skill` tool not yet on engineer's `tools:` line breaks fallback path | LOW | Engineer can't invoke skill even if cold-start hook fires | Phase 1 D.4 ships the tool addition. Quality gate validates. |
| `SubagentStart` hook reliability ([anthropics/claude-code#27755](https://github.com/anthropics/claude-code/issues/27755)) makes Phase 1 hook design brittle | KNOWN | Don't depend on it | Phase 1 does NOT register a `SubagentStart` hook. Cold-start for subagents lives in the skill + agent prompts. |
| Plan 16 ships Phase 1 but Phase 2 / 3 / 4 get descoped or de-prioritized | MEDIUM | Half-built v2 (cold-start works but no per-agent skills) | Phase boundaries are halt-points; each phase is independently usable. Phase 1 alone is a 10× improvement over today's cold drift. Document the half-state in the Deviations section if it happens. |

## Token budget estimate (per phase)

Rough estimates. User has the highest-tier sub; this is informational, not blocking.

| Phase | Estimated tokens | Notes |
| --- | --- | --- |
| 1 (infra) | ~200k–300k | Engineer-dominant. 3 new files (1 skill + 2 hooks, all small) + 6 agent prompt edits + 1 JSON edit + 2 doc-section appends + quality gate. Sub-300k. |
| 2 (skill suite) | ~600k–900k | Engineer-dominant. ~28 skills × ~3k tokens body each (description + body + cross-refs) = ~85k just for the skill files. Plus ~28 × ~10k tokens engineer-context-load per skill draft = ~280k. Plus QA gate per agent (6 fresh dispatches × ~100k each = ~600k). Phase 2 is the heaviest single phase. |
| 3 (PC.5 build) | ~600k–800k | Full `/build` loop: architect plan (200k) + engineer impl (300k) + hacker review (100k) + devops gates (50k) + manager orchestration (100k). PC.5 is the smallest paper cut (~1h human-equivalent). |
| 4 (PC.6 build) | ~700k–900k | Same shape as Phase 3 but PC.6 is ~2h work; expect ~25% more engineer tokens. |
| **Total** | **~2.1M–2.9M** | All 4 phases together. Well under the 5M daily ceiling. Phase 2 is the only single-phase budget risk; even worst-case 900k is within the 1.5M engineer cap. |

Manager pre-flights the budget before each phase dispatch per `.claude/agents/manager.md § Budget enforcement`. If projected spend exceeds the cap, halt for user decision per the existing protocol.

## Open questions

(none — all 6 questions from the kickoff prompt resolved in § C above)

## Approval checklist

- [ ] Skill naming convention: `<agent>-<verb>` for agent-specific, `naavik-<verb>` for shared (§ C.1)
- [ ] Skill location: project-level `.claude/skills/<name>/SKILL.md`, one directory per skill (§ C.2 — forced by Claude Code spec)
- [ ] Cold-start mechanism: hook + skill (both); `SubagentStart` hook NOT used (known-unreliable per [anthropics/claude-code#27755](https://github.com/anthropics/claude-code/issues/27755)) (§ C.3)
- [ ] Trigger-string strategy: pushy descriptions per § C.4, validated at Phase 1 QA gate
- [ ] `Skill` tool added to manager / architect / engineer / hacker / devops; designer already has it (§ C.5)
- [ ] Git hook branch regex: `^(feat|fix|chore|docs|refactor)/<task-id>-<slug>$`; silent no-op + stderr log on mismatch (§ C.6)
- [ ] Per-agent skill suite sizes: manager 4 / architect 4 / engineer 5 / designer 5 / hacker 3 / devops 3 + shared 4 = 28 total (§ E)
- [ ] Phase boundaries: HALT after Phase 1 + HALT after Phase 2 for user review; Phases 3 + 4 are user-initiated `/build` runs (§ F + § G)
- [ ] Token budget: ~2.1M–2.9M total across 4 phases, well under 5M daily ceiling; Phase 2 is the heaviest at ~900k worst-case (§ H token budget table)
- [ ] ROADMAP row A.11 wording landed correctly (verified during architect's mirror duty)
- [ ] All agents stay on `claude-opus-4-7[1m]`; no Sonnet downgrade in scope; legacy `ESCALATE: opus` pattern flagged for Phase 2 cleanup as tangential
