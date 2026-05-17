# Kickoff: Agent System v2 — cold-start + per-agent skills + git automation

> **Type:** session-kickoff prompt for the manager subagent.
> **Audience:** the manager agent at the start of a fresh `claude --agent manager` session.
> **Usage:** `claude --agent manager "$(cat docs/prompts/agent-system-v2.md)"`
> **Tracks:** ROADMAP row `A.11` (to be added by architect during plan authoring).
> **Authored:** 2026-05-16.

---

## Context

Last session (2026-05-16) shipped:

- `scripts/gh-project.sh` map-cache patches + new `refresh-map` subcommand
- `.claude/github-issue-map.json` persistent association cache (gitignored)
- Closed duplicate issues `#46` (dup `#6`) + `#47` (dup `#7`) from prior search-API races
- "GitHub state — single writer" governance text in `CLAUDE.md` / `AGENTS.md` /
  `.claude/agents/manager.md` / `.claude/commands/bootstrap.md` / `docs/AGENT_OPS.md`

`scripts/gh-project.sh bootstrap` (dry-run) now reports `would create=0 skipped=40`
— all milestones, epics, and 40 child issues exist and are correctly mapped.

## Goal

Build the agent system v2 in four phases:

1. **Infra** — cold-start hook + skill, `Skill` tool added to all 6 agents, git
   commit-message hook for auto-linking issues, Project board automation rules
2. **Per-agent skill suite** — project-level skills under `.claude/skills/<name>/SKILL.md`,
   one suite per agent (manager / architect / engineer / designer / hacker / devops)
   plus a few shared cross-agent skills
3. **First real `/build`** — ship PC.5 via the full delivery loop (this is the A.8
   deliverable, "first end-to-end /build")
4. **Second `/build`** — ship PC.6 to prove the loop works twice in a row

Phases halt at boundaries for user review. Don't auto-advance.

## Required reading (parallelize — single message, multiple Reads)

1. `AGENTS.md` § Workflow + § Single-doc-tracking + § GitHub state — single writer rule + § Roadmap Maintenance Rules
2. `CLAUDE.md` § GitHub state — single writer rule + § Claude Code Specific Notes
3. `docs/AGENT_OPS.md` § 1–7 (full operational reference)
4. `docs/ROADMAP_OVERVIEW.md` (130 lines, full)
5. `.claude/agents/manager.md` (your own prompt) + the other 5 specialist prompts under `.claude/agents/`
6. `.claude/commands/` directory listing (slash command inventory)
7. `scripts/gh-project.sh` (skim — you'll be invoking subcommands)
8. `.claude/github-issue-map.json` (current cache contents — task_id → issue# mapping)
9. `traces/runs.log` (tail 10 if it exists)
10. `.claude/budget.json` + `.claude/budget-ledger.json`

When the architect drafts the plan, they add:
- Claude Code skills docs (via context7: query `claude-code` + `skills`)
- Claude Code hooks docs (via context7: query `claude-code` + `hooks` + `SessionStart`)
- Git `prepare-commit-msg` hook reference (via web search — standard pattern)

## Scope — 4 phases, HALT at each phase boundary

### Phase 1 — Infrastructure (~2.5 h)

**1a. Cold-start hook (Claude Code SessionStart):**
- `.claude/hooks/cold-start.sh` — emits a system reminder listing required files +
  current ROADMAP "Last updated" date + tail of `traces/runs.log` + `.claude/budget-ledger.json`
  snapshot + the open `naavik-cold-start` skill invocation hint
- Register in `.claude/settings.json` under `hooks.SessionStart`
- Fires on main session start AND subagent dispatch

**1b. Cold-start skill (auto-trigger):**
- `.claude/skills/naavik-cold-start/SKILL.md` — frontmatter with `description:` that
  matches "manager", "build", "standup", "cold start", "agent system", first-message-of-session
- Body: explicit Read tool invocations for the required-reading list

**1c. Add `Skill` tool to all 6 agents:**
- `.claude/agents/manager.md` — append `Skill` to the `tools:` line
- Same for `architect.md` / `engineer.md` / `hacker.md` / `devops.md`
- `designer.md` already has it (verify)
- Update each agent's "Required reading on cold start" section to start with:
  > "Your first action MUST be `Skill: naavik-cold-start`. Don't read individual files
  > directly until the skill has loaded the canonical context."

**1d. Git commit-message hook (`prepare-commit-msg`):**
- `.claude/hooks/git/prepare-commit-msg` — bash script that:
  1. Parses the current branch name for a task ID (e.g. `feat/PC.5-secret-key` → `PC.5`)
  2. Looks up the issue number in `.claude/github-issue-map.json` (`.issues."PC.5"` → `7`)
  3. If the commit message body doesn't already contain `Closes #N`, appends:
     `Closes #7` on a new line before the trailers
- Install instructions in `docs/AGENT_OPS.md` (or a new section): `ln -sf ../../.claude/hooks/git/prepare-commit-msg .git/hooks/prepare-commit-msg`
- Document the branch naming convention: `<type>/<task-id>-<slug>` where
  `<type>` ∈ `{feat, fix, chore, docs}` and `<task-id>` matches a key in the issue map

**1e. GitHub Project automation guide (one-time user setup):**
- Document the Project v2 workflow rules to enable in the GitHub UI:
  - "Auto-add to project" — when issue opened with label `phase:*`
  - "Item closed → Status: Done"
  - "Item reopened → Status: Todo"
  - "Pull request merged → close referenced issue" (built-in `Closes #N` behavior)
- Add to `docs/AGENT_OPS.md` § 2 (Bootstrap) as the post-`init` step
- This is **manual setup** by the user — the script can't configure Project workflows
  via API yet. Architect should verify this is still the case as of authoring date.

**Quality gate for Phase 1:**
- Spawn a fresh `claude --agent engineer "What's the status of PC.5?"` and observe:
  the SessionStart hook fires, the engineer's first action is `Skill: naavik-cold-start`,
  the skill loads the required context, and the engineer answers correctly without
  asking the user for any orientation.
- `git commit -m "test"` on a branch named `feat/PC.5-test` produces a commit message
  with `Closes #7` automatically appended.

### Phase 2 — Per-agent skill suite (~3-4 h)

Build project-level skills at `.claude/skills/<name>/SKILL.md`. Architect sizes each
agent to 3-5 skills (more is overhead). Seed list — architect refines naming +
grouping in the plan:

**Manager (orchestration):**
- `manager-pick-next` — wraps `scripts/gh-project.sh next-unblocked` + filters by milestone + emits a one-line "next task" summary
- `manager-standup-report` — generates the standup format from current Project state + budget + recent traces
- `manager-board-sync-check` — diffs `.claude/github-issue-map.json` against live GitHub state; flags drift
- `manager-deviation-promote` — at archive time, lifts the engineer-deviations log into the plan's `## Deviations from plan` section

**Architect (planning):**
- `architect-plan-quality-bar` — checklist from `.claude/agents/architect.md` § "Plan quality bar"
- `architect-option-matrix` — template for the 2+ options × {capability, cost, risk, maintenance, lock-in} matrix
- `architect-design-doc-graduation` — guide for promoting a `Type: design` plan into a permanent `docs/design/SEMANTIC.md`
- `architect-sunset-guard` — rejects plans extending `src/cli/` or `src/services/vault.py` (Phase 2 sunset)

**Engineer (implementation):**
- `engineer-stack-invariants` — quick reference for FastAPI / SQLModel / HTMX / Tailwind patterns from `AGENTS.md` § Key Conventions
- `engineer-manual-qa-gate` — checklist + driver-script templates for the QA gate (HTMX page / API endpoint / cron / migration / service method)
- `engineer-llm-tracker-wrap` — reminder + template to wrap every LLM call in `services/llm_tracker.tracked_call`
- `engineer-deviation-log` — appends to `traces/<run-id>/engineer-deviations.log` with the canonical format
- `engineer-pr-template` — opens the PR using `.github/pull_request_template.md` + ensures `Closes #N` is in the last commit

**Designer (UI):**
- `designer-design-tokens` — quick lookup of `DESIGN.md` tokens
- `designer-screen-lookup` — pulls the relevant section from `docs/design/SCREENS.md`
- `designer-component-reuse` — searches `docs/design/COMPONENTS.md` for existing components matching a need; flags reinventions
- `designer-mockup-conventions` — path + dimensions + naming rules for mockup exports
- `designer-componentization-memo` — handoff template to engineer

**Hacker (security):**
- `hacker-stride-template` — STRIDE threat model scaffold
- `hacker-secrets-audit` — scan a diff for hardcoded secrets, weak hashing, missing env-var usage
- `hacker-pr-security-checklist` — auth / injection / deserialization / CSRF / OWASP top 10 review pass

**Devops (build + ops):**
- `devops-build-gates` — runs `ruff check` + `ruff format --check` + `pytest -x` + summary
- `devops-trace-manifest` — writes `traces/<run-id>/MANIFEST.json` per the AGENT_OPS § 7.3 schema
- `devops-runbook-lookup` — pulls the relevant section from `docs/RUNBOOK.md` for a given failure mode

**Shared (project-wide, accessible from any agent):**
- `naavik-cold-start` — built in Phase 1
- `naavik-roadmap-status` — current phase, what's done, what's in-flight
- `naavik-deviations-check` — verifies a plan has `## Deviations from plan` before archive (AGENTS.md § Workflow step 7)
- `naavik-vault-sunset-guard` — flags any mention of extending `src/services/vault.py`

**Quality gate for Phase 2:**
- Spawn a fresh dispatch of each agent and verify the agent invokes the appropriate
  skill at the appropriate moment (e.g. architect runs `architect-plan-quality-bar`
  before handing back a plan; engineer runs `engineer-manual-qa-gate` before
  declaring done).
- Engineer attempts to author a plan extending `src/services/vault.py`; expect
  `naavik-vault-sunset-guard` to trigger and reject before any code lands.

### Phase 3 — First real `/build` (~1 h)

Run `claude /build "PC.5"` end-to-end with the new infrastructure. This is the A.8
deliverable. Observe:

- SessionStart hook fires for the parent session AND every spawned subagent
- Cold-start skill auto-loads canonical context in each agent's first turn
- Architect dispatches with full context; produces a plan (probably `docs/plans/17-pc5-secret-key-enforcement.md`)
- PLAN GATE halts; user approves
- Engineer implements; per-agent skills (`engineer-stack-invariants`, `engineer-manual-qa-gate`, etc.) trigger automatically
- Hacker + devops dispatched in parallel
- PR GATE halts; user approves
- Branch named `feat/PC.5-secret-key-enforcement` → commit message auto-gets `Closes #7`
- On merge, GitHub closes #7 → Project automation moves to Status: Done
- Manager updates ROADMAP row PC.5 to `[x]` + bumps "Last updated"
- Plan moves to `docs/plans/archive/` with `## Deviations from plan` section

### Phase 4 — Second `/build` for muscle memory (~2 h)

Run `claude /build "PC.6"`. Two consecutive successful end-to-end builds = the loop
is real and reliable. Same observation points as Phase 3.

## Approach (use the system to build the system)

```
[Pre]    Manager cold-starts (reads required-reading list via Skill: naavik-cold-start
         once it exists; until Phase 1 lands, manager reads files directly per the
         existing "Required reading on cold start" section of manager.md)

[1.1]    Manager dispatches architect via Task to author the plan
[1.2]    Architect researches (context7: Claude Code skills + hooks docs; web
         search: git prepare-commit-msg patterns), drafts
         `docs/plans/16-agent-system-v2.md`, ADDS the ROADMAP row A.11
         (per architect.md § GitHub mirror duty), creates the GitHub Issue
         via `scripts/gh-project.sh create-issue A.11 "Agent System v2"
         --priority HIGH --milestone "Phase A"`, halts at PLAN GATE
[1.3]    User approves / revises / cancels

[2.1]    Engineer implements Phase 1 (infra), runs quality gates, hands back
[2.2]    HALT — user manually tests cold-start in a fresh subagent dispatch
[2.3]    User approves Phase 1

[3.1]    Engineer implements Phase 2 (per-agent skills), hands back
[3.2]    HALT — user spot-checks 2-3 agent dispatches
[3.3]    User approves Phase 2

[4.1]    User kicks off `claude /build "PC.5"` in a fresh session (Phase 3 of THIS
         plan = the first run of the v2 system). This validates Phases 1+2 worked
         AND ships A.8 (first end-to-end /build deliverable).
[4.2]    Manager dispatches architect → engineer → hacker + devops → merge → archive

[5.1]    User kicks off `claude /build "PC.6"` (Phase 4)
```

## Decisions locked (don't re-debate)

- **Cold-start mechanism:** hook + skill (both). Belt + suspenders.
- **Skill location:** project-level at `.claude/skills/<name>/SKILL.md` (NOT user-level
  `~/.claude/skills/`).
- **Per-agent skill suite:** every agent gets its own suite (3-5 skills) covering
  their realm. Plus shared cross-agent skills.
- **Phase by phase:** halt after each for user review.
- **Naming convention for skills:** architect picks in the plan; user approves once
  and it's done. Suggested: `<agent>-<verb>` (`manager-pick-next`) for agent-specific,
  `naavik-<verb>` (`naavik-cold-start`) for shared.
- **ROADMAP row:** new row `A.11` (not folded into A.8 — A.8 is specifically the
  first-real-/build validation, A.11 is the infra that makes A.8 possible).

## Constraints

- Don't extend `src/cli/` or `src/services/vault.py` (Phase 2 tasks 2.11 / 2.12 sunset)
- All GitHub state mutations through `scripts/gh-project.sh` (CLAUDE.md § GitHub state
  — single writer rule). New script subcommands are fine; new agent prompts that call
  `gh issue create` directly are not.
- User has highest tier Anthropic sub + Opus 4.7 1M-context default for ALL agents
  (no Sonnet downgrade — the `ESCALATE: opus` pattern is obsolete). Be thorough; don't
  optimize for token spend.
- Dispatch specialists via `Task` — manager doesn't write code.
- Don't break existing slash commands (`.claude/commands/`); they keep working as-is
  alongside the new skills.

## Open questions for architect to resolve in the plan

- [ ] Skill naming convention: `<agent>-<verb>` (`manager-pick-next`) vs flat
      (`pick-next`) vs prefixed (`naavik-manager-pick-next`). Pick one with rationale.
- [ ] Per-skill directory layout: one dir per skill (lots of small dirs) vs
      one dir per agent containing multiple SKILL.md files (does Claude Code support
      this?). Check current Claude Code skills spec via context7.
- [ ] Whether the SessionStart hook also fires for `SubagentStart` events (if Claude
      Code distinguishes them) or only the top-level session start.
- [ ] Trigger-string strategy for skill descriptions: too eager → noise, too
      conservative → never fires. Architect proposes pattern + tests it during
      Phase 1 quality gate.
- [ ] Should `Skill` tool be added to engineer's tool list given engineer's tool
      list is intentionally narrow (Read, Edit, Write, Glob, Grep, Bash, Task, +
      specific MCP)? Trade-off: skill discovery vs blast radius. Recommend yes;
      engineer benefits most from `engineer-stack-invariants` and `engineer-manual-qa-gate`.
- [ ] Branch naming convention for the commit-message hook: enforce `<type>/<task-id>-<slug>`
      strictly, or tolerate variations (e.g. `task-id/slug`, `slug-task-id`)? Affects
      hook regex.

## Hand-back format per phase (engineer follows exactly)

```
Phase <N> shipped.

Files: created K, modified M, deleted D — grouped by area
Verification:
  - <how you confirmed Phase N works — paste the evidence>
Tests: ruff/pytest outcomes + manual gate evidence
Deviations: <bullets per traces/<run-id>/engineer-deviations.log, or "none material">
Next phase: <name> (estimated <effort>)
Open user decisions: <or "none">

→ HALT. Awaiting user approval before Phase <N+1>.
```

## Budget note

This is meta-work; expect Phase 2 (per-agent skills, ~20 skills total) to be the
largest single token spend. Architect's plan should estimate per-phase token cost
so you can pre-flag if any phase risks blowing the daily ceiling. User has the
highest tier sub so this is informational, not blocking.

## Tracing

Per AGENT_OPS § 7. Run-id format: `<YYYY-MM-DDTHH-MM-SS>_<6-char-hex>`. Append
DISPATCH / GATE / BUDGET / MIRROR entries to `traces/<run-id>/manager.log`. End-of-
run write `MANIFEST.json` + append one-liner to `traces/runs.log`.

---

## After this plan ships

The agent system is "v2". Going forward, every new ROADMAP row that exits `[~]` flows
through the loop: cold-start fires automatically, the right skills auto-trigger,
commits auto-link issues, status updates happen on merge. The user's job collapses to
"approve the plan, approve the PR, approve the milestone" — three gates per task.

Next product work after this lands: PC.5, PC.6, then the big ones — 2.12 (vault
sunset, 2-3 days) and 2.11 (CLI sunset, < 1 day), then Phase 2 scrapers proper.
