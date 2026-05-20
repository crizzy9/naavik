# Naavik Agent System — Operations Guide

> **Last updated:** 2026-05-18 (A.29 Waves 1-4 — phase numbering system + `.claude/naavik-ops` Python dispatcher. New § 2.7a documents the dispatcher entry point + subcommand groups + 4-level semver task ID schema. `gh` + `memory` subcommand groups subprocess-wrap the legacy `.claude/naavik_ops/gh.py` + `.claude/naavik_ops/memory.py` during A.29 transition; A.30 (0.1.1) inlines natively. Caller references throughout migrated from `.claude/naavik_ops/gh.py` → `.claude/naavik-ops gh`. § 2.8 commit-msg hook unchanged scope; Conventional Commits enforcement added per D.18.)
> Earlier line: 2026-05-17 (A.28 — board restructure. § 6.3 extended to 4-row status table + asymmetric Backlog convention; § 2.2 fields list adds Backlog + Phase 2.5 milestone. New shared skill `manager-backlog-promote` for auto-promote workflow when Todo empties. `.claude/naavik_ops/gh.py` gains `add-status` / `create-milestone` / `item-id` / `backlog-by-epic` subcommands; `set-status` accepts `Backlog`; `cmd_sync` preserves Backlog. PLAYBOOK gains "Board status convention (post-A.28)" section.)
> Earlier line: 2026-05-17 (A.15 SHIPPED — § 14 added: agent memory + learning system. `.claude/memory/` + `.claude/naavik_ops/memory.py` + `naavik-memory-lookup` + `naavik-discussion-capture` + `naavik-learn` + `manager-promote-lesson` skills + `/memory` + `/learn` commands. Manager § PR review gate + § Milestone boundary gate updated to invoke `Skill: naavik-discussion-capture`. Plan: `docs/plans/19-agent-memory-and-learning.md`; design doc: `docs/design/AGENT_MEMORY.md`.)
> Earlier line: 2026-05-16 (plan 16 Phase 1 EXECUTED — § 2.7 + § 2.8 added: GitHub Projects v2 workflow rules + git commit-message hook install)
> **Status:** Active. This is THE single doc for using the agent-driven delivery system. Read it once; reference as needed.
> **Companion docs:** `AGENTS.md` (workflow + conventions), `ROADMAP.md` § Agent System (task ledger), `.claude/agents/` (full agent prompts), `.claude/commands/` (slash commands).

---

## 1. What this is

Naavik ships with 6 specialized Claude Code subagents and 13 slash commands at project scope. They deliver Naavik milestones end-to-end against a GitHub Project v2 board, mirroring the canonical `ROADMAP.md` task ledger onto Issues + Project items.

**The contract:**

- **`ROADMAP.md` is authoritative** (per AGENTS.md § Single-doc-tracking). The `[ ]` / `[~]` / `[x]` ledger lives only here.
- **The GitHub Project board is a one-way operational mirror.** It exists because Markdown tables can't answer "which unblocked Phase 2 issue has the highest priority?" — the Project can. Sync flows ROADMAP → Project, never reverse.
- **6 agents, scoped:** manager (orchestrator), architect (plans), engineer (implementer), devops (debugger), hacker (security), designer (UI/UX). See `.claude/agents/` for full prompts.
- **13 commands** (see § 4) wrap multi-agent flows so you don't think about agent IDs day-to-day.

**Why this exists:** Naavik is built solo with Claude Code. Without explicit gates (plan approval, security review, deviations capture, board updates), the agent system would drift from ROADMAP within one milestone. This guide is the gating apparatus made legible.

---

## 2. First-time setup (bootstrap)

Run these ONCE per fork. After bootstrap, you `/build`, `/plan`, `/standup` from then on.

### 2.1 Prerequisites

- `nix develop` shell active (gives you `gh`, `jq`, `python`, `uv`, `tmux`).
  - If `tmux` isn't on PATH, add it to `nix/devshell.nix` or run `traces/watch.sh` outside the devshell.
- `gh auth login` completed against the GitHub account that owns the fork.
- A GitHub Project v2 created — the helper script can NOT create the Project for you (Projects v2 mutations to create a project require additional scopes; create via web UI).

### 2.2 Create the GitHub Project v2

1. Navigate to `https://github.com/users/<your-handle>?tab=projects` (user-owned) OR `https://github.com/orgs/<your-org>/projects` (org-owned).
2. Click **New project** → **Board** layout.
3. Name it `naavik` (or whatever you prefer; you'll feed the number to `init`).
4. **Add three single-select custom fields** (Project settings → Fields → "+ New field"):
   - **Status** (already exists by default) — options: `Todo`, `In Progress`, `Done`, **`Backlog`** (added 2026-05-17 per A.28; deferred-from-current-cycle state — see § 6.3). If your project came with only the first 3, run `.claude/naavik-ops gh add-status Backlog --color GRAY` after `init` to add the fourth.
   - **Priority** — options: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
   - **Milestone** — options created as you bootstrap (`Phase 0`, `Phase 1`, …, `Phase A`, `Pre-Phase-2 paper cuts`, `Phase 2.5`). You can pre-create or let `bootstrap` add them.
5. Note the project number from the URL (`.../projects/<N>`).

### 2.3 Cache the Project IDs

```bash
.claude/naavik-ops gh init
```

You'll be prompted for owner / repo / project number. The script queries GitHub via GraphQL, resolves the Project ID + field IDs + status option IDs, and caches them to `.claude/github-project.json`. This file is gitignored — every fork runs `init` once.

Re-run `init` any time you rename a field option or add a Project; it's idempotent.

### 2.4 Bootstrap Milestones + Issues from ROADMAP

```bash
.claude/naavik-ops gh bootstrap                # dry-run — prints what it would create
.claude/naavik-ops gh bootstrap --apply        # actually creates milestones + issues
```

What it does:

- **Creates GitHub Milestones** for each phase header it finds in `ROADMAP.md` (`Phase 0`, `Phase 1`, …, `Phase A`, plus `Pre-Phase-2 paper cuts`). Skips if the milestone already exists by name.
- **Creates GitHub Issues** for each `[ ]` or `[~]` row in the active phases (defaults to: Pre-Phase-2 paper cuts + Phase A + Phase 2 + Phase 1.x deferred). Completed (`[x]`) rows are skipped. Title format: `[<task-id>] <task description>` (e.g., `[2.11] CLI sunset`). Body links back to `ROADMAP.md`.
- **Adds each Issue to the Project**, setting Status (`Todo` for `[ ]`, `In Progress` for `[~]`), Priority (from the row's Priority column), and Milestone (the phase).
- **Idempotent:** matches existing issues by title prefix `[<task-id>]`; updates fields if they drifted from ROADMAP.

After bootstrap:

```bash
.claude/naavik-ops gh milestone-status         # JSON of items grouped by Status
.claude/naavik-ops gh next-unblocked           # next Todo item, highest priority
```

### 2.5 Confirm the system is live

```bash
claude /standup
```

This spawns the manager, who reads ROADMAP + queries the Project + reports current milestone, in-flight items, blocked items, drift (if any), token budget. If `/standup` returns a coherent state, you're bootstrapped.

### 2.6 (Optional) First end-to-end build

```bash
claude /build pre-phase-2-paper-cuts
```

Manager picks the next unblocked paper cut, walks the operating loop. Halts at the plan gate for your approval.

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

If you change Project ID later, re-run `.claude/naavik-ops gh init` so the
field option IDs cache stays current. Workflow rules survive this; they live
on the Project itself.

### 2.7a `naavik-ops` dispatcher entry point (new in A.29, 2026-05-18)

Agent-system operations route through **`.claude/naavik-ops`** — an executable Python
dispatcher at the `.claude/` package boundary. Subcommand groups: `task` (release-version
task ops), `release` (release ceremony — pyproject + nix/package.nix + CHANGELOG + tag
atomically), `deps` (cross-task dependency graph), `plan` (plan-lifecycle ops — archive
+ validate-deviations; new in `0.7.0.21`), `gh` (GitHub Project + Issue ops), `memory`
(`.claude/memory/` ops).

```bash
.claude/naavik-ops --help                                  # group surface
.claude/naavik-ops task list 0.2.0                         # tasks for release (priority DESC → position ASC)
.claude/naavik-ops task next-unblocked 0.2.0               # next unblocked task in 0.2.0
.claude/naavik-ops task check                              # version drift lint (pyproject + nix/package.nix + tags)
.claude/naavik-ops task bump patch                         # preview release bump
.claude/naavik-ops release dry-run 0.1.0                   # preview release ceremony
.claude/naavik-ops deps add 0.2.0.06 0.2.0.05              # record cross-task dep edge
.claude/naavik-ops plan archive docs/plans/NN-name.md      # canonical archive path (lifts deviations + git mv)
.claude/naavik-ops plan validate-deviations docs/plans/...  # read-only PASS/BLOCK check
.claude/naavik-ops gh next-unblocked                       # legacy: .claude/naavik-ops gh next-unblocked
.claude/naavik-ops memory list discussions                 # legacy: .claude/naavik-ops memory list discussions
```

**Single-writer rule** (extends `AGENTS.md § GitHub state — single writer rule`): all
agent prompts MUST route through `.claude/naavik-ops` for state mutations. During the
A.29 transition the `gh` and `memory` groups subprocess-wrap the legacy
`.claude/naavik_ops/gh.py` + `.claude/naavik_ops/memory.py` — both paths preserve the
single-writer invariant. A.30 (0.1.1) inlines native Python + deletes the bash scripts.

**Lock:** `~/.naavik/naavik-ops.lock` (fcntl.flock; serializes concurrent mutations).

**Schema (4-level semver task IDs):** `MAJOR.MINOR.PATCH[.POSITION]` — regex
`^\d+\.\d+\.\d+(\.\d{2})?$`. 3-level = release version (e.g. `0.2.0`); 4-level = task
within release (e.g. `0.2.0.05`). Position is 2-digit zero-padded for lex-sort
stability. Sort: priority DESC → position ASC. See `docs/design/PHASE_NUMBERING.md`
for the full schema + dispatcher design.

**Migration runbook:** `.claude/migrations/A.29-phase-renumber.py` ships in the A.29 PR
but **does NOT run during this PR**. Wave 5 (post-merge) invokes it with `--apply`.

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

**Branch task-id case is enforced uppercase.** The hook regex matches `PC`, `DEF`, `A`
etc. case-sensitively. Lowercase branch names like `feat/pc.6-foo` silently no-op the
`Closes #N` append — your commit will lack the trailer and the issue won't auto-close
on merge. Always use UPPERCASE task-id in branch names: `feat/PC.6-foo`,
`fix/DEF-12-bar`, `chore/A.11-baz`. Surfaced 2026-05-17 during plan 18 / PC.6 (PR #50)
when the original lowercase branch dispatch silently dropped the trailer; documented
here as a one-time gotcha so future authors notice before pushing. The hook itself is
unchanged — flipping the regex to case-insensitive is a separate paper cut someone
can file standalone.

---

## 3. Daily workflow

**Manager's task router:** `docs/PLAYBOOK.md` — strict if-then classification of every user message into one of 9 categories (STATUS / INSPECT / PLAN_GATE / PR_REVIEW_GATE / MILESTONE_GATE / PRODUCT_WORK / BUG_TRIAGE / CONTRACT_CHANGE / BOOKKEEPING) with the canonical procedure for each. Codified after the `aa2f6a0` workflow miss (ROADMAP § Phase A row A.14). **Manager consults the playbook before every action.** Read it once per session via the cold-start skill; reference it whenever a task surface is ambiguous between "this is bookkeeping" and "this needs a PR."

Once bootstrapped, your day with the agent system looks like:

```
morning:    /standup         → see what's open
            /build "next"    → deliver one milestone (or stop at the next gate)
            /discuss <topic> → multi-agent debate when scope is ambiguous
            /plan <scope>    → architect drafts a plan; you approve via checklist
            /triage-bug <X>  → root-cause + fix
afternoon:  /review-pr <#N>  → engineer + hacker review
            /threat-model    → before merging anything security-sensitive
            /design-screen   → when a new UI screen is up
weekly:     /groom           → reconcile board priorities with ROADMAP
            /sync-roadmap    → diff ROADMAP vs Projects, push ROADMAP wins
            /budget          → check daily token spend vs caps
            /runs            → review run history + outcomes
```

You should never need to manually:

- Mark a ROADMAP row `[~]` / `[x]` — manager does it during `/build`.
- Update a Project Status column — manager does it via `.claude/naavik-ops gh set-status` (subprocess-wraps `.claude/naavik_ops/gh.py` during A.29).
- Open a GitHub Issue for a planned task — architect does it via `/plan` (which calls `.claude/naavik-ops gh create-issue`).
- Write a `## Deviations from plan` section — engineer + manager assemble it from `traces/<run-id>/engineer-deviations.log`.

If you find yourself doing those manually, something in the system is broken — file it as a paper cut.

---

## 4. Commands reference

Each row is a **slash command** the user can type. The **Skill mirror** column lists the agent-invocable `Skill: <name>` entry point (per § 10.2 dual-surface convention). `✓ explicit` means a canonical `.claude/skills/<name>/SKILL.md` exists; `auto` means the harness exposes the slash command as a skill implicitly (no explicit SKILL.md yet — author one when an agent needs to invoke the flow ambient-triggered, using `build` as the template).

| Command | Skill mirror | Purpose | Argument |
|---|---|---|---|
| `/build` | ✓ explicit | Autonomous milestone delivery loop. Halts at plan / PR / milestone gates. | `<milestone name \| "next">` |
| `/plan` | auto | Architect drafts a plan + opens the GH Issue + adds to Project. | `<scope description or roadmap task id>` |
| `/discuss` | auto | Multi-agent debate; synthesizes verdicts. | `<topic, PR URL, plan path, design doc path>` |
| `/triage-bug` | auto | devops repros → engineer patches → hacker reviews if security-sensitive. | `<bug description, issue URL, stack trace>` |
| `/review-pr` | auto | engineer + hacker review in parallel, post combined verdict. | `<PR number or URL>` |
| `/threat-model` | auto | hacker produces STRIDE table for a feature / design doc / plan. | `<feature, doc path, plan path>` |
| `/design-screen` | auto | designer mocks a screen per DESIGN.md + SCREENS.md. | `<screen name>` |
| `/groom` | auto | manager grooms the board against ROADMAP. | `[milestone name]` |
| `/standup` | auto | Current milestone state + drift + budget snapshot. | — |
| `/bootstrap` | auto | First-time setup wrapper: `init` + create Project fields check + `bootstrap`. | — |
| `/sync-roadmap` | auto | Diff ROADMAP vs Projects; with `--apply` pushes ROADMAP → Project. | `[--apply]` |
| `/budget` | auto | Token spend ledger vs caps; today + week. | — |
| `/runs` | auto | Recent runs from `traces/runs.log` with outcomes + trace links. | `[count]` |
| `/memory` | auto | Read-only inspection of `.claude/memory/` stores (decisions / discussions / lessons / patterns / knowledge / runs-analysis). | `<list\|query\|knowledge> [args]` |
| `/learn` | ✓ explicit | Manual retrospective. Analyzes last N runs, mines patterns, surfaces promotion + ROADMAP candidates. | `[N]` (default 10) |

Each command spawns the relevant agent(s) via the Task tool. You see the agent's output, you approve at each gate.

---

## 5. Agent reference

| Agent | Color | Model | MCPs | Role |
|---|---|---|---|---|
| **manager** | pink | opus-4-7 | github | Orchestrator. Owns ROADMAP + Project sync, gates every transition, never writes code. |
| **architect** | blue | opus-4-7 | context7, nixos, tavily, github | Planner. Writes `docs/plans/NN-name.md`. Opens GH Issue. Researches via live docs (context7/nixos/tavily); searches existing issues/PRs via github. |
| **engineer** | green | sonnet-4-6 | context7, nixos, github (PR-subset) | Implementer. Reads plan in full, codes per AGENTS.md conventions, runs ruff + pytest + Playwright. Escalates to opus on tagged tasks (`ESCALATE: opus <reason>`). |
| **devops** | orange | sonnet-4-6 | github, context7, nixos, n8n | Debugger + quality gates + runbook author. Reproduces before patching; root cause not symptom. nixos for Nix debugging; context7 for library bugs; n8n for the transitional n8n migration (Phase 2 task 2.10). |
| **hacker** | red | opus-4-7 | github, context7 | Security. STRIDE for design docs (writes `docs/design/THREAT_MODEL-*.md`), line-level audit for PRs. Verdict: APPROVE / APPROVE_WITH_NOTES / REQUEST_CHANGES / BLOCK. |
| **designer** | yellow | sonnet-4-6 | — (uses Skill tool for huashu-design / impeccable / ui-ux-pro-max / frontend-design / banner-design) | UI/UX. Designs per DESIGN.md tokens; uses skills for variant generation + critique. |

Full system prompts: `.claude/agents/<name>.md`. Models are baked into frontmatter; per-task `effortLevel` is NOT a frontmatter field (Claude Code ignores it for opus-4.7) — reasoning depth is wired into each prompt body.

**MCP selection rationale** (single source of truth for "why this MCP for this agent"):

- **context7** — live library docs (FastAPI, SQLModel, Pydantic, Alembic, Anthropic SDK, OpenAI SDK, Typst, Crawl4AI, Playwright). Wired to: architect (research), engineer (impl), devops (debugging), hacker (CVE research).
- **github** — GitHub API for PRs, Issues, Code search. Wired to: manager (Projects ops), architect (search existing work), engineer (PR creation + reviews), devops (CI log analysis), hacker (PR review submission via pending-review workflow).
- **nixos** — live nixpkgs + NixOS options. Wired to: architect (research), engineer (flake.nix edits), devops (orchestrator + flake debugging).
- **tavily** — general web research. Wired to: architect only (deep research for design decisions).
- **n8n** — n8n workflow ops (transitional; Naavik is migrating away from n8n in Phase 2 task 2.10). Wired to: devops only.
- **Skill tool** — pre-installed Skills (huashu-design, impeccable, ui-ux-pro-max, frontend-design, banner-design, design-system, ui-styling, slides, brand). Wired to: designer only.

**Explicitly NOT wired** (personal tools, not for codebase work): `claude_ai_Gmail`, `claude_ai_Google_Calendar`, `claude_ai_Google_Drive`. Don't add these to any agent.

---

## 6. GitHub Mirror conventions

ROADMAP.md → GitHub Project v2 mapping is mechanical and frozen. **Treat any drift as a bug.**

### 6.1 Phase → Milestone

Each `### Phase N: <Name>` header in ROADMAP becomes a GitHub Milestone named `Phase N`. The phase's `**Goal:**` line becomes the Milestone description.

| ROADMAP phase | Milestone |
|---|---|
| Phase 0: Foundation & Infrastructure | `Phase 0` (closed — already done) |
| Phase 1: MVP — UI + backend core | `Phase 1` (closed — already done) |
| Phase 2: Job Scraping & Discovery | `Phase 2` |
| Phase 3: Intelligent Scoring & Matching | `Phase 3` |
| Phase 4: Application Tracking & Auto-Apply | `Phase 4` |
| Phase 5: Email Monitoring & Outreach | `Phase 5` |
| Phase 6: Optimization & Polish | `Phase 6` |
| Phase A: Agent System | `Phase A` (this system; tracked separately from product phases) |
| Pre-Phase-2 paper cuts | `Pre-Phase-2 paper cuts` (cleanup before plan 11) |

### 6.2 Task row → Issue

Each task row in a phase table becomes a GitHub Issue.

**Title format:** `[<task-id>] <one-line description>`
- `<task-id>` is the row's # cell: `2.11`, `5.13`, `PC.5`, `A.3`, etc.
- One-line description is the row's `Task` cell, trimmed to 70 chars.
- Example: `[2.11] CLI sunset — delete src/cli/`.

**Body:**
```
Bootstrapped from ROADMAP.md § Phase <N> task <id>.

<Notes column verbatim>

---
Auto-managed by `.claude/naavik_ops/gh.py`. ROADMAP.md is authoritative.
```

**Labels:**
- `phase:<N>` (or `phase:A`, `phase:pre-2`)
- `priority:<lower-case>` (e.g., `priority:critical`)
- Optional: `paper-cut`, `phase-1-deferred`, `bug`, `blocked` (latter is honored by `next-unblocked`).

### 6.3 Status checkboxes → Project Status field

The board carries **four** Status options (post-A.28, 2026-05-17). Three of them map symmetrically to ROADMAP checkboxes; the fourth (`Backlog`) is asymmetric.

| ROADMAP | Project Status |
|---|---|
| `[ ]` | `Todo` |
| `[~]` | `In Progress` |
| `[x]` | `Done` (Issue also closed) |
| (no ROADMAP-checkbox equivalent) | `Backlog` — Project-only status for items deferred from current cycle |

**Asymmetric `Backlog` semantics.** ROADMAP rows for Backlog items stay `[ ]` (they're not "in progress" or "done"); the `Backlog` status lives only on the Project. The mapping is asymmetric: `[ ]` can mean Todo OR Backlog, distinguished by the Project Status column. Sync direction stays ROADMAP → Project; `/sync-roadmap --apply` does NOT touch Backlog status (it only flips `[ ]/[~]/[x]` → Todo/In Progress/Done; it never knows what to do with Backlog because Backlog is a board-only decision). To move a Project item from Todo → Backlog, use `.claude/naavik-ops gh set-status <item-id> Backlog` directly; the change is board-only and ROADMAP doesn't reflect it. To promote a Backlog item back into the current cycle, run `set-status <item-id> Todo` explicitly (or invoke the `manager-backlog-promote` skill for the consent-gated auto-promote flow).

Within Backlog, items are unprioritized at the item level — only the **epics** within Backlog carry priority via their own Priority field on the epic Issue. Promotion ordering uses epic priority, not individual item priority. Use `.claude/naavik-ops gh backlog-by-epic --top N` to surface deferred work grouped by parent epic, ordered by epic priority.

**`next-unblocked` skips Backlog.** Operating-loop step 2 ignores Backlog items. When Todo is empty mid-loop, manager invokes `Skill: manager-backlog-promote` for the user-consent gate (per A.28 PLAN_GATE Q3 lock).

**`bootstrap` is idempotent on Backlog.** When `bootstrap` re-runs against an existing Issue, it `continue`s without touching Status (handled by the existing `EXISTING && SKIP` branch). Backlog status is never overwritten by re-bootstrap. `cmd_sync` was hardened post-A.28 to preserve Backlog: ROADMAP `[ ]` maps to Todo OR Backlog, and Backlog → Todo is not flagged as drift.

### 6.4 Priority column → Project Priority field

The Priority column in ROADMAP tables (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) maps 1:1 to the Project Priority single-select. Rows without an explicit Priority default to `MEDIUM`.

### 6.5 Sync direction

Always: **ROADMAP → Project.** Manager edits ROADMAP first (mark `[~]` on start, `[x]` on done), then runs `.claude/naavik-ops gh set-status` to push to Project. `/sync-roadmap` is the bulk-reconcile.

If the Project drifts from ROADMAP (e.g., someone manually moved an Issue), `/sync-roadmap --apply` overwrites the Project to match ROADMAP. Never the reverse — the Markdown ledger wins.

### 6.6 Issue-map cache + single-writer rule (codified 2026-05-16)

`.claude/github-issue-map.json` is the persistent `{phase → epic#, task_id → issue#, phase → milestone#}` association cache. Schema:

```json
{
  "_meta": { "owner": "...", "repo": "...", "project_number": N, "refreshed_at": "ISO-8601", "note": "..." },
  "milestones": { "Phase A": 1, "Pre-Phase-2 paper cuts": 2, ... },
  "epics":      { "Phase A": 1, "Pre-Phase-2 paper cuts": 6, ... },
  "issues":     { "PC.5": 7, "2.1": 10, ... }
}
```

**Why.** The GitHub `search/issues` API is eventually consistent (~30s–2min indexing lag). Pre-cache, bootstrap's `find_issue_by_prefix` queried that API and treated indexing lag as "issue doesn't exist," creating duplicates (`#46` dup `#6`, `#47` dup `#7`). The map gives bootstrap + plan-driven creates instant, deterministic idempotency: every create writes the new number to the map, every existence check reads the map first.

**Sole writer:** `.claude/naavik_ops/gh.py`. Subcommands `create-issue`, `create-epic`, and `bootstrap` write to the map on success; `find_issue_by_prefix` and `ensure_milestone` consult the map before falling back to the API.

**Reconciler:** `.claude/naavik-ops gh refresh-map` rebuilds the map from authoritative GitHub state. Collisions on title prefix (e.g. two open issues both titled `[PC.5] …`) resolve to (open, lowest-issue-number). Run after any manual UI edit (rename/close/delete an issue, rename a milestone) or whenever you suspect drift.

**Operational rules:**

- All `gh issue create` / `gh issue close` / Project field writes go through `.claude/naavik_ops/gh.py` subcommands. Don't call `gh` or `gh api graphql` for those from agent prompts or one-off scripts.
- Don't hand-edit the map; it's machine-managed. If you must inspect, `jq '.epics' .claude/github-issue-map.json` is read-safe.
- The dry-run (`.claude/naavik-ops gh bootstrap` without `--apply`) reads the map and reports `exists` vs `PLAN` for milestones, epics, AND child issues. If a dry-run shows `PLAN` for something you suspect exists, run `refresh-map` and re-dry-run before applying — the map may be stale.
- The `manager` agent is the sole entry point for delivery-loop state mutations (status moves during step 9/12 of the operating loop). Other agents may invoke `.claude/naavik-ops gh create-issue` for plan-driven issue creation, but must never call raw `gh` for Issue/Project state.

---

## 7. Trace system

Every multi-agent run creates a per-run trace directory.

### 7.1 Run-id format

```
traces/<YYYY-MM-DDTHH-MM-SS>_<6-char-hash>/
```

Example: `traces/2026-05-16T09-30-15_a3f2b8/`

- Timestamp is ISO-8601-ish (colons replaced with dashes for filesystem safety).
- Hash is `uuidgen | tr -d '-' | head -c6` (collision-resistant within a day).
- Manager picks the run-id at `/build` start and passes it to all sub-agents.

### 7.2 Per-agent logs

Each agent writes one file in the run dir, format frozen per agent's prompt. Three event families apply to ALL agents (codified 2026-05-17 per "Tracing contract"):

- **Agent-specific events** — the canonical shapes per role.
- **`ERROR`** — fires the moment something fails, retries, gets skipped, gets halted, or pivots away from the dispatched plan. Append-only; one line per failure event. Format frozen across all agents:
  ```
  [ISO-timestamp] ERROR step=<what-failed> kind=<retry|skip|halt|pivot> reason=<one-line> attempt=<n>/<max>
  ```
  Examples:
  - `[ts] ERROR step=pytest-x kind=retry reason='tests/test_seed::test_X flaked' attempt=2/3`
  - `[ts] ERROR step=gh-pr-create kind=halt reason='sandbox denied gh subcommand after direct-push' attempt=1/1`
  - `[ts] ERROR step=find-replace kind=pivot reason='plan § C.8 said 25 sites; grep returned 5; pivoting to file PC.6a follow-up' attempt=1/1`
  - `[ts] ERROR step=live-orchestrator-boot kind=pivot reason='auto-mode destructive-rm guard blocked .naavik/db wipe; pivoting to TestClient surrogate' attempt=1/1`
- **`BUILT` / `REVIEWED`** — one summary line at the end of every dispatch (last line in the agent's log). `BUILT` for agents that produce artifacts (architect, engineer, designer, manager) when authoring artifacts; `REVIEWED` for agents that gate (hacker, architect when reviewing, devops when invoked for build-gate verification). Architect emits `BUILT` when authoring a plan/design doc, `REVIEWED` when on PR_REVIEW_GATE duty. One sentence in `summary='...'`. Format frozen across all agents:
  ```
  [ts] BUILT files_added=<n> files_modified=<n> files_deleted=<n> summary='<one-sentence>'
  [ts] BUILT plans=<n> design_docs=<n> research_docs=<n> summary='<one-sentence>'   # architect variant
  [ts] BUILT mockups=<n> components_referenced=<n> components_new=<n> summary='<one-sentence>'   # designer variant
  [ts] REVIEWED scope=<PR-or-target> verdict=<PASS|FAIL_BLOCKING|...|APPROVE|REQUEST_CHANGES> findings=<n> summary='<one-sentence>'
  ```

#### Per-agent shapes

- `manager.log` — `[ts] DISPATCH agent=<name> task=<one-line> reason=<why>` + `[ts] GATE name=<...> outcome=<...>` + `[ts] MIRROR action=<set-status|sync> item=<id> from=<state> to=<state>` + `[ts] BUDGET spent=<n> remaining=<n>` + `[ts] AGENT_RETURN agent=<name> verdict=<...> tokens=<n>` + `[ts] COMMIT_PUSH sha=<...> branch=<...> note=<line>` + `[ts] MERGE pr=#<N> squash=<sha> base=<branch>` + `[ts] ARCHIVE plan=<NN> path=<archive-path> status=EXECUTED` + `[ts] ROADMAP_EDIT row=<id> change=<line>` + `[ts] BLOCKED action=<...> reason=<line>` + `ERROR` + `BUILT`.
- `architect.log` — `[ts] START plan=<path> decision=<line>` + `[ts] RESEARCH source=<context7|web|tavily|nixos|github> what=<line>` + `[ts] OPTION_MATRIX plan=<path> decision=<which-decision-locked>` + `[ts] RECOMMENDATION plan=<path> decision=<chosen-option>` + `[ts] OPEN_QUESTION plan=<path> count=<n>` + `[ts] DONE plan=<path>` + `ERROR` + `BUILT`.
- `engineer.log` — `[ts] EDIT <path> reason=<one-line>` + `[ts] TEST <suite> result=<PASS|FAIL> count=<n>` + `[ts] DEVIATION plan=<path> what=<...> why=<...>` + `[ts] COMMIT <sha> branch=<name> trailer=<closes-N>` + `[ts] PUSH origin/<branch> <range>` + `[ts] PR_BODY_UPDATE pr=#<N>` + `[ts] QA_GATE surface=<...> outcome=<pass|fail>` + `ERROR` + `BUILT`.
- `devops.log` — `[ts] REPRO <line>` + `[ts] HYPOTHESIS <line>` + `[ts] EVIDENCE <line>` + `[ts] FIX <line>` + `[ts] TEST <suite> result=<PASS|FAIL>` + `[ts] VERIFY <surface> outcome=<pass|fail>` + `[ts] VERDICT <PASS|FAIL_BLOCKING|FAIL_RECOVERABLE>` + `ERROR` + `REVIEWED`.
- `hacker.log` — `[ts] SCAN surface=<input|auth|secrets|csrf|sql|xss|...> finding_count=<n>` + `[ts] FINDING severity=<low|medium|high|critical> file=<path>:<line> issue=<one-line>` + `[ts] VERDICT <APPROVE|APPROVE_WITH_NOTES|REQUEST_CHANGES|BLOCK> severity=<...>` + `[ts] PR_REVIEW_POSTED pr=#<N> verdict=<...> state=<APPROVED|CHANGES_REQUESTED|COMMENTED>` + `ERROR` + `REVIEWED`.
- `designer.log` — `[ts] DESIGN screen=<slug> source=<skill> output=<path>` + `[ts] REUSE component=<name>` + `[ts] NEW_VARIANT component=<name> args=<...>` + `[ts] HANDOFF memo=<path> engineer=<dispatch-id>` + `ERROR` + `BUILT`.
- `engineer-deviations.log` — append-only one-liner per deviation. Format: `[ts] DEVIATION plan=<path> what=<line> why=<line> impact=<line>`. Promoted into the plan's `## Deviations from plan` section at archive time.
- `*-qa.log` (optional, when manual QA is significant) — append-only per-smoke-step record. Format: `[ts] SMOKE step=<id> surface=<...> outcome=<pass|fail> evidence=<line>`.

#### Tracing contract — enforcement rules

1. **Log errors as they happen, not at the end.** Buffering errors and writing them at hand-back loses the ordering signal that helps the next debugger.
2. **Every dispatch ends with a `BUILT` or `REVIEWED` line.** Empty-dispatch case still gets the line (`summary='no changes — investigation revealed pre-existing state was already correct'`).
3. **Free-text rationale in logs is OK** but doesn't substitute for an explicit `ERROR` event. If your devops surrogate pivoted because of a sandbox guard, write the `ERROR` line first, THEN the longer `RATIONALE` if you need it.
4. **Devops's `MANIFEST.json` writer (per `devops-trace-manifest` skill) aggregates `ERROR` and `BUILT`/`REVIEWED` events** from all per-agent logs into the manifest's `errors_encountered` array + `what_built` summary string. Manager owns the final manifest flip from `outcome=halted` → `outcome=delivered` at merge.
5. **Manager records its own `ERROR` events** for sandbox denials, ROADMAP-vs-Project drift discoveries, retry-protocol triggers, gate halt-because-of-failure. Don't bury those in free-text BLOCKED entries.

### 7.3 Run manifest

At end of run, devops writes `traces/<run-id>/MANIFEST.json` via `Skill: devops-trace-manifest`. Manager flips `outcome` from `halted` → `delivered` at merge, refreshes `tokens_spent` from the ledger, and re-writes:

```json
{
  "run_id": "2026-05-16T09-30-15_a3f2b8",
  "started_at": "2026-05-16T09:30:15Z",
  "ended_at": "2026-05-16T11:45:02Z",
  "milestone": "Pre-Phase-2 paper cuts",
  "outcome": "delivered",
  "halt_reason": null,
  "issues_closed": [42, 43],
  "prs_merged": ["https://github.com/crizzy9/naavik/pull/87"],
  "files_touched": ["src/cli/init.py", "..."],
  "deviations_recorded": ["docs/plans/archive/10d-secret-key-hardening.md § Deviations"],
  "tokens_spent": {"manager": 152000, "architect": 410000, "engineer": 893000, "hacker": 200000, "devops": 50000},
  "what_built": "<one-paragraph plain-English summary of what shipped this run — typically 2–4 sentences naming the headline deliverable, the side artifacts, and any follow-ups filed>",
  "errors_encountered": [
    {"agent": "engineer", "step": "find-replace", "kind": "pivot", "reason": "plan § C.8 said 25 sites; grep returned 5; filed PC.6a follow-up", "attempt": "1/1"},
    {"agent": "hacker", "step": "pr-review-write", "kind": "pivot", "reason": "self-approval blocked on own-author PR; posted as COMMENTED with REQUEST_CHANGES in body", "attempt": "1/1"},
    {"agent": "devops", "step": "live-orchestrator-boot", "kind": "pivot", "reason": "auto-mode destructive-rm guard blocked .naavik/db wipe; pivoted to TestClient surrogate", "attempt": "1/1"},
    {"agent": "manager", "step": "gh-project.sh create-issue PC.6a", "kind": "halt", "reason": "sandbox denial post-direct-push to main", "attempt": "1/1"}
  ]
}
```

**Field semantics:**

- `outcome` — one of `delivered` / `halted` / `failed`. Devops writes `halted` at end of dispatch; manager flips to `delivered` on merge or `failed` if the 3-attempt protocol bottoms out.
- `halt_reason` — `null` when `outcome=delivered`; else short string (`pr_review_gate` / `plan_review_gate` / `milestone_boundary` / `budget_ceiling` / `three_attempt_exhaustion`).
- `what_built` — plain-English run summary. Reader skims this BEFORE drilling into per-agent logs. Manager populates from each agent's terminal `BUILT`/`REVIEWED` lines.
- `errors_encountered` — list of every `ERROR` event from every per-agent log. Auto-aggregated by `devops-trace-manifest` skill. Empty array if nothing failed.

If you find yourself adding fields not in this schema (`screenshots_captured`, `migrations_run`, etc.), extend the schema doc here AND `devops-trace-manifest/SKILL.md` first — don't fork the format silently.

### 7.4 Run index

`traces/runs.log` — one line per run, append-only:

```
[ts] run=<run-id> milestone=<name> outcome=<delivered|halted|failed> issues=<n> prs=<n> tokens=<n>
```

### 7.5 Inspect interactively

```bash
./traces/watch.sh                  # tmux session, one pane per agent log, latest run
./traces/watch.sh <run-id>         # specific run
claude /runs 10                    # list last 10 runs from runs.log with summaries
```

### 7.6 Retention

Traces are gitignored. Manually delete `traces/<old-run-id>/` to reclaim disk. No auto-rotation today; add to ROADMAP § Phase A as a follow-up if accumulation gets noisy.

---

## 8. Token budget

### 8.1 Caps

`.claude/budget.json`:

```json
{
  "daily_token_ceiling": 5000000,
  "per_agent_caps": {
    "manager": 800000, "architect": 1200000, "engineer": 1500000,
    "devops": 700000, "hacker": 500000, "designer": 300000
  },
  "halt_action": "ask_user",
  "reset_at": "00:00 local"
}
```

Edit to tighten; tighter caps surface scope creep earlier.

### 8.2 Ledger

`.claude/budget-ledger.json` (gitignored, auto-managed by manager):

```json
{
  "current_day": "2026-05-16",
  "spent_today": {
    "manager": 152000, "architect": 410000, "engineer": 893000,
    "devops": 50000, "hacker": 200000, "designer": 0
  },
  "total_today": 1705000,
  "history": [
    {"day": "2026-05-15", "total": 4120000, "by_agent": { /* ... */ }}
  ]
}
```

Manager appends per-run spend at end of `/build`, rolls over `current_day` at midnight local.

### 8.3 Halt behavior

If projected next-step spend would exceed `daily_token_ceiling - total_today`, manager halts and asks. Same for per-agent caps. You can:

- Approve a one-time override (manager continues; adds an annotation to the run manifest).
- Halt for the day (manager closes the run, prints summary).
- Raise the cap permanently (edit `.claude/budget.json`).

### 8.4 Inspect

```bash
claude /budget                     # today's spend, % of cap per agent
```

---

## 9. Troubleshooting

### 9.1 "Project not cached" / "github-project.json missing"

Run `.claude/naavik-ops gh init`. The file is gitignored — every fork bootstraps once.

### 9.2 "Status field not found" / "option id is null"

Your Project's Status field uses non-standard names (e.g., `Backlog`/`Ready`/`Done` instead of `Todo`/`In Progress`/`Done`). Either:

- Rename the options in the Project's web UI to `Todo` / `In Progress` / `Done`, or
- Edit `.claude/naavik_ops/gh.py` § `cmd_init` to match your names (search for `Todo` / `In Progress` / `Done`).

Re-run `init` after fixing.

### 9.3 "User vs organization" project mismatch

`init` auto-detects user vs org by trying both GraphQL roots. If your project is owned by an organization but you ran `init` against your user handle, you'll see `project not found`. Re-run `init` with the org name as owner.

### 9.4 ROADMAP drift / "Issue says Todo but ROADMAP says `[~]`"

Run `.claude/naavik-ops gh sync` (dry-run), confirm the diff, then `--apply`. ROADMAP wins. If you want the Project state to win for a particular row, edit ROADMAP first, then sync — never the reverse, or you'll keep re-introducing drift.

### 9.5 Bootstrap created duplicate issues

Most common cause (before 2026-05-16): `find_issue_by_prefix` queried the GitHub search API, which is eventually consistent (~30s–2min indexing lag). A re-run of bootstrap shortly after the first apply caused the search API to miss freshly-created issues, so bootstrap created them again. **Symptom:** two open issues with identical `[<task-id>]` or `[Epic] <phase>` titles (e.g. `#46` dup of `#6` for `[Epic] Pre-Phase-2 paper cuts`; `#47` dup of `#7` for `[PC.5]`).

**Fix shipped 2026-05-16:** `.claude/github-issue-map.json` persistent association cache + `.claude/naavik-ops gh refresh-map` reconciler. Bootstrap now consults the map first and only falls through to the search API on a cache miss. See § 6.6 for the full single-writer rule.

**Cleanup when you find a duplicate:**

```bash
# Identify dupes by parsed task-id prefix.
gh issue list --state all --limit 200 --json number,title,state \
  | jq '[.[] | select(.title | test("^\\[[^\\]]+\\]")) | {num: .number, key: (.title | capture("^\\[(?<id>[^\\]]+)\\]").id), state}]
       | group_by(.key) | map(select(length > 1))'

# Close the higher-numbered duplicate (the original is the lower #).
gh issue comment <DUP_NUM> --body "Duplicate of #<ORIG>. Closing per CLAUDE.md § GitHub state — single writer."
gh issue close <DUP_NUM> --reason "not planned"

# Reconcile the map so it points to the surviving canonical issue.
.claude/naavik-ops gh refresh-map
```

Other (less common) cause: you renamed a task ID in ROADMAP (e.g. `2.11` → `2.11a`); bootstrap creates a new Issue for the new ID without closing the old. Either close the old Issue manually + `refresh-map`, or revert the rename and add a sub-task instead.

### 9.6 Token budget halts mid-`/build`

Either approve a one-time override, raise the cap in `.claude/budget.json`, or split the milestone. The cap is per-day, so waiting until tomorrow resets it (manager auto-resets `current_day` at the next post-midnight run).

### 9.7 `tmux` not found when running `watch.sh`

`tmux` isn't in the default `nix develop` shell. Either add to `nix/devshell.nix` (`pkgs.tmux`), or run `watch.sh` from a parent shell where tmux is installed.

### 9.8 Agent doesn't appear in `claude /agents`

Frontmatter validation failed. Check `.claude/agents/<name>.md`:

- `name:` matches the filename (without `.md`).
- `model:` is a valid model ID (`claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`).
- `color:` is a known color (`red`, `blue`, `green`, `orange`, `pink`, `yellow`, `cyan`, `purple`).
- `tools:` is a comma-separated list of tool names + MCP wildcards.

### 9.9 The agent ignored my instruction / extended the CLI

Both AGENTS.md § Key Conventions § CLI and every relevant agent prompt forbid extending `src/cli/` or the vault (Phase 2 sunset tasks 2.11 / 2.12). If an agent does it anyway, paste the offending diff into `/discuss` and call out the violation explicitly — the multi-agent debate will surface why the rule was crossed and let you correct course.

---

## 10. Extending the system

### 10.1 Add a new agent

1. Write `.claude/agents/<name>.md` with the standard frontmatter (`name`, `description`, `tools`, `model`, `color`).
2. Body: principles + operating loop + output format + tracing format + escalation rules.
3. Append a row to AGENTS.md § Agent System table.
4. Bake reasoning depth into the prompt body — `effortLevel:` is ignored.

### 10.2 Add a new slash command (and the matching skill mirror)

Naavik's orchestration surface is **dual**: the user-typed `/<name>` slash command AND an agent-invocable `Skill: <name>` mirror. Both exist; both point at the same underlying procedure. The pattern is codified by `/build` (canonical example shipped 2026-05-17).

**Two files, complementary roles:**

| File | Role | Triggered by |
|---|---|---|
| `.claude/commands/<name>.md` | The procedural body — numbered orchestration steps, Task dispatches, AskUserQuestion gates. Authoritative source for "what the command does." | User typing `/<name>` in the chat. |
| `.claude/skills/<name>/SKILL.md` | The agent-invocable mirror — thin frontmatter (`description` with rich trigger phrases, `allowed-tools`), short body that points at the command file as the procedure source, plus auto-trigger conditions, "when NOT to invoke," and "forbidden during invocation." | Any agent calling `Skill: <name>`, or the harness ambient-triggering on the description's trigger phrases (e.g. "kick off the loop" → `Skill: build`). |

**Authoring sequence:**

1. Write `.claude/commands/<name>.md` with frontmatter (`description`, `argument-hint`) and the full numbered procedure (Task dispatches + AskUserQuestion gates + trace bookkeeping).
2. Write `.claude/skills/<name>/SKILL.md` with frontmatter (`description` containing canonical-purpose sentence + trigger phrases; `allowed-tools` listing the read/write surfaces the skill needs) and a thin body:
   - `## When to invoke` — the user-phrase triggers + the manager-operating-loop step it serves.
   - `## What this skill does` — high-level shape (3–8 bullets), then "**Read `.claude/commands/<name>.md` as the procedure source**" so callers know where the full step list lives. Do NOT duplicate the procedural body — drift between the two files is the failure mode this convention is designed to prevent.
   - `## Canonical references` — pointers to the command file, the relevant agent prompt, AGENT_OPS sections, AGENTS.md sections.
   - `## When NOT to invoke` — conditions where the skill should be skipped (wrong context, system not bootstrapped, already mid-flight).
   - `## Forbidden during invocation` — the hard rules (CLI/vault sunset, single-writer rule, manual-merge gate, etc.).
3. Append a row to AGENT_OPS.md § 4 commands reference table noting both surfaces.
4. Bump "Last updated" if the new command/skill changes a phase deliverable or the agent-system contract.

**Why the dual surface:** the slash command is what the user types; the skill is what the agent (or the harness, ambient-triggered) invokes. Without the skill mirror, the manager can only invoke `/<name>`-flavored behavior by reproducing the command's body in its operating loop — invisible to other agents and brittle to drift. With the skill mirror, any agent (or a fresh session's ambient trigger on a user phrase) can call the same canonical procedure. The command file stays authoritative for the steps; the skill file is the discoverable entry point.

**Don't duplicate the procedural body.** The skill body should describe *when* and *why* to invoke + the high-level shape; the *how* lives in the command file. If you find yourself copying the full numbered step list into the skill, stop — the procedure has one home (the command file), and that home is what callers Read.

**Existing slash commands without skill mirrors (as of 2026-05-17):** `bootstrap`, `standup`, `groom`, `sync-roadmap`, `budget`, `runs`, `plan`, `discuss`, `triage-bug`, `review-pr`, `threat-model`, `design-screen`. These work today because Claude Code's harness auto-exposes slash commands as skills implicitly, but the canonical SKILL.md artifact doesn't exist. Author them on demand using the `build` skill as the template; the auto-exposed entry is harmlessly superseded by the explicit one.

### 10.3 Add a new trace event format

Append to the agent's tracing-format spec in their `.claude/agents/<name>.md` prompt. Keep one event per line; keep the format greppable.

### 10.4 Add a new GitHub Project field

1. Add the field in the Project web UI.
2. Re-run `.claude/naavik-ops gh init` so the cache picks up the new field ID.
3. Update `.claude/naavik_ops/gh.py` GraphQL queries + helper functions to read/write the new field.
4. Document the field in AGENT_OPS.md § 6 (GitHub Mirror conventions).

### 10.5 Adjust the workflow

Workflow changes live in `AGENTS.md` § Workflow. Update there first, then propagate to agent prompts. If a change affects bootstrap behavior, update AGENT_OPS.md § 2 and bump the "Last updated" line.

---

## 11. What this system is NOT

- **It is not autonomous-merge.** Every PR halts at a user gate. The agents propose; you dispose.
- **It is not multi-tenant.** It assumes one human + one Claude session at a time. If two `/build` runs collide on the same milestone, the trace logs will interleave and the second one will likely error on a Project board write race.
- **It is not a replacement for AGENTS.md.** AGENTS.md is the workflow contract; this guide is the operational manual.
- **It is not a substitute for thinking.** The agents are good at execution; they need you to set the scope, weigh the trade-offs at gates, and call out when the system is wrong.

---

## 12. Reference guides (read these BEFORE invoking agents)

The agent system relies on a small set of canonical guides. Each is the single source for its domain. Load them on demand.

| Guide | Path | Read when... |
|---|---|---|
| **Roadmap overview** | `ROADMAP.md` | You need state-at-a-glance + plan-to-phase mapping + active work + recently shipped. Faster than the 800-line ROADMAP. |
| **Architecture guide** | `docs/ARCHITECTURE.md` | You're about to author a plan, ship code, or reason about layer responsibilities + cross-cutting concerns (auth / vault / async / LLM observability / HTMX patterns). Entry point to BACKEND.md + DATA_MODEL.md + INTERACTIONS.md. |
| **Visual contract** | `DESIGN.md` (root) | You're doing UI work. Tokens, type, icons, voice. Frozen. |
| **UI sub-process** | `docs/design/WORKFLOW.md` | You're doing UI work. Skill routing, read-order, per-screen checklist, accessibility, common patterns, anti-patterns, mockup conventions. Pairs with DESIGN.md. |
| **Deployment guide** | `docs/DEPLOYMENT.md` | You're deploying. 4 paths (NixOS / Docker / Cloud / Dev), full config, ops checklist. |
| **Devops runbook** | `docs/RUNBOOK.md` | Something's broken. Or you're debugging. Or you're a devops dispatch. Single source for known failure modes + diagnostic recipes + recovery procedures + monitoring queries. |
| **Workflow contract** | `AGENTS.md` § Workflow | Authoring/reviewing a plan, archiving, or running the deviations gate. |
| **CLI/vault sunset policy** | `AGENTS.md` § Key Conventions § CLI | Authoring or reviewing ANY plan that might touch `src/cli/` or vault. |
| **Post-Phase-1 playbook** | `docs/plans/POST_PHASE_1.md` | End-to-end smoke testing, monitoring playbook, "when something goes wrong" common categories. |
| **Plan conventions** | `docs/plans/README.md` | Authoring a plan (file naming, frontmatter, archive flow). |
| **Design contracts (deep)** | `docs/design/COMPONENTS.md`, `BACKEND.md`, `DATA_MODEL.md`, `INTERACTIONS.md`, `SAMPLE_DATA.md` | Implementing — need the spec, not the overview. |
| **Visual contract** | `DESIGN.md` (root) | Token values + voice + iconography rules. Frozen. |

**Agent-specific required reading** is encoded in each agent's prompt (`.claude/agents/<name>.md` § "Required reading on cold start"). The agents load the right subset automatically; the table above is for humans + for designing new agents.

---

## 13. Quick reference card

```
# First-time setup (once per fork)
gh auth login
.claude/naavik-ops gh init                     # cache project IDs
.claude/naavik-ops gh bootstrap --apply        # create milestones + open issues
claude /standup                                 # confirm live

# Daily
claude /standup                                 # see state
claude /build "next"                            # deliver milestone (halts at gates)
claude /plan "feature description"              # architect drafts plan
claude /triage-bug "stack trace"                # devops + engineer fix
claude /review-pr 87                            # engineer + hacker review
claude /budget                                  # check spend

# Periodic
claude /groom                                   # reconcile board priorities
claude /sync-roadmap --apply                    # push ROADMAP → Project
claude /runs 20                                 # review run history

# Inspect a run interactively
./traces/watch.sh                               # tmux panes, latest run
```

That's the system. Read AGENTS.md once for the workflow; reference this doc for operations.

---

## 14. Memory + learning system

Phase A row A.15 (shipped 2026-05-17 via `feat/A.15-agent-memory`) added the agent system's memory layer. Six stores under `.claude/memory/`, a single writer script, discovery via skills, and a manual `/learn` retrospective command. Complements Claude's native primitives (CLAUDE.md, MEMORY.md, Skills) without duplicating them.

**Canonical design doc:** `docs/design/AGENT_MEMORY.md` (full architecture + schemas + extension guide).

### 14.1 The map

```
.claude/memory/                                ← gitignored per-fork EXCEPT .keep + knowledge/*.md
├── decisions.jsonl                            ← locked architectural decisions w/ rationale + supersede
├── discussions.jsonl                          ← deferred items captured at gate boundaries
├── lessons.jsonl                              ← promoted recurring patterns (threshold 5)
├── recurring-patterns.jsonl                   ← auto-aggregated ERROR-event patterns
├── knowledge/<topic>.md                       ← long-form markdown corpus (5 seeded; committed)
└── runs-analysis/<run-id>.md                  ← per-run summary written by /learn

.claude/naavik-ops memory                        ← single writer (subcommands: init, record-*, list, query, analyze-run, mine-patterns, promote-lesson)

.claude/skills/                                ← 4 memory-aware skills
├── naavik-memory-lookup/SKILL.md              ← "have we hit this before?" → check knowledge/<topic>.md
├── naavik-discussion-capture/SKILL.md         ← manager fires at PR_REVIEW_GATE + MILESTONE_GATE
├── naavik-learn/SKILL.md                      ← skill mirror of /learn
└── manager-promote-lesson/SKILL.md            ← consent-gated promote-lesson wrapper (threshold 5)

.claude/commands/                              ← 2 slash commands
├── memory.md                                  ← /memory list|query|knowledge — read-only
└── learn.md                                   ← /learn [N] — analyze last N runs, surface candidates
```

### 14.2 Invariants

- **Single writer.** `.claude/naavik_ops/memory.py` is the sole writer to `.claude/memory/`. Mirror of `.claude/naavik_ops/gh.py` for GitHub state. No `Edit` / `Write` against memory store paths — `hacker-secrets-audit` enforces.
- **Append-only JSONL.** Duplicate ids rejected. `--supersedes <old-id>` is the upgrade path; deletion forbidden.
- **Atomic writes.** Every write uses `mktemp` + `mv`. Partial files never visible to readers.
- **Markdown knowledge entries** carry machine-parseable front-matter (`Topic`, `Aliases`, `First captured`, `Last referenced`, `Supersedes`, `Confidence`). Body is free-form prose.
- **Gitignored per-fork** except `.keep` + `knowledge/*.md`. Knowledge files are committed as shared cross-contributor reference; structured stores stay per-fork.
- **`MEMORY.md` integration is read-only.** Never write to `~/.claude/projects/<...>/memory/MEMORY.md` programmatically. If a lesson should graduate there, system surfaces a suggestion at the next milestone gate.

### 14.3 Daily workflow integration

```
during /build:
  manager step 10 (PR_REVIEW_GATE follow-up)   → Skill: naavik-discussion-capture
  manager step 15 (MILESTONE_GATE)             → Skill: naavik-discussion-capture
                                                  + suggest /learn if runs-since-last-analysis >= 5

ad-hoc:
  /memory list knowledge                       → see the corpus
  /memory query decisions '.state == "active"' → list active decisions
  /memory knowledge linkedin-scraping          → read a specific entry
  /learn 10                                    → analyze last 10 runs; interactive promotion candidates
```

### 14.4 Relationship to existing primitives

| Surface | Owner | What it holds | Memory system relation |
|---|---|---|---|
| `CLAUDE.md` | repo, hand-edit | project invariants Claude Code reads on every cold start | read-only; never writes |
| `AGENTS.md` | repo, hand-edit | canonical workflow contract | read-only; never writes |
| `~/.claude/projects/<...>/memory/MEMORY.md` | Claude Code, auto-managed | per-user personal preferences | read-only; never writes (locked Q6 per plan 19) |
| `.claude/skills/<name>/SKILL.md` | repo, hand-edit | procedural memory (auto-trigger on phrase) | extends — adds memory-aware skills for situational memory |
| `.claude/budget-ledger.json` | manager, auto-managed | daily token spend | unaffected |
| `.claude/github-issue-map.json` | `.claude/naavik_ops/gh.py`, auto-managed | persistent `{task → issue#}` cache | unaffected |
| `.claude/memory/**` | `.claude/naavik_ops/memory.py`, auto-managed | decisions / discussions / lessons / knowledge / patterns / runs-analysis | **the new layer** |

### 14.5 Wave 2 analytics surfaces

`/learn [N]` (default N=10) produces an interactive markdown report covering:

- **Failure patterns** — top 5 ERROR kinds across last N runs.
- **Drift signals** — plans whose deviation count exceeded 4.
- **Token-spend hotspots** — agents over their cap on N runs out of last 10.
- **Skill activation stats** — invocation count per skill across N runs.
- **Knowledge promotion candidates** — patterns with `occurrence_count >= 5` and no `knowledge/` entry yet.
- **ROADMAP candidates** — discussions in `discussions.jsonl` without `filed_as: #N`.

Each section ends with an AskUserQuestion (promote pattern / file discussion / accept / skip). Backed by `.claude/naavik-ops memory analyze-run <run-id>` + `.claude/naavik-ops memory mine-patterns --lookback N`.

### 14.6 Wave 3 promotion + alias mining

- **Lesson promotion.** Patterns with `occurrence_count >= 5` are promotable via `.claude/naavik-ops memory promote-lesson <pattern_id>`. Creates a `lessons.jsonl` row + a `knowledge/<auto-slug>.md` stub from the pattern's `proposed_action`. Manager surfaces consent via `Skill: manager-promote-lesson` before invoking.
- **Alias mining.** `.claude/naavik-ops memory mine-patterns --aliases` scans `manager.log` for `MEMORY_MISS topic=<X> phrase=<Y>` events. Surfaces alias proposals via AskUserQuestion before mutating front-matter on `knowledge/<X>.md`.
- **Decision supersession.** `.claude/naavik-ops memory record-decision <new-id> ... --supersedes <old-id>` marks the old row as `state: "superseded"` + `superseded_by: <new-id>`. `/memory query decisions` defaults to `state == "active"` filter.

