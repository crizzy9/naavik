# Naavik · Task Playbook

> **Strict if-then decision tree the manager consults at the start of every user message.**
> Every task fits one of the 9 categories below. **No improvisation. No judgment calls at category boundaries.** If a task doesn't fit, halt and ask.
>
> **Last updated:** 2026-05-17 (codified after commit `aa2f6a0` workflow miss — see `ROADMAP.md` § Phase A row A.14).

---

## Why this exists

PR #50 (PC.6) shipped via proper PR + hacker/devops review. Then commit `aa2f6a0` ("docs(agents): codify trace ERROR + BUILT/REVIEWED contract") got pushed directly to `main` — bypassing PR review for a change that touched all 6 agent prompts, `docs/AGENT_OPS.md § 7.2`/`7.3`, and the `devops-trace-manifest` skill. That was a CONTRACT_CHANGE masquerading as BOOKKEEPING.

This playbook removes the judgment surface. Manager classifies first, executes the strict procedure second. CONTRACT_CHANGE always means PR. BOOKKEEPING means direct push. No grey area.

---

## How the manager uses this

Every user message (other than gate responses) follows this loop:

```
1. CLASSIFY   → match the user's surface request to ONE of the 9 categories.
2. EXECUTE    → run the strict procedure for that category. No detours.
3. SURFACE    → emit the prescribed gate / report / question.
4. HALT       → at every gate, stop; never auto-advance to the next step.
```

If two categories seem to fit, **ask the user ONE precise question** to disambiguate. If no category fits, surface as: *"This doesn't match a playbook category — which one applies, or do we need to extend the playbook?"* and HALT.

---

## The 9 categories

| # | Category | Surface request pattern |
|---|---|---|
| **A** | STATUS | "where are we", "what's the status", "what's next", "standup", "show me budget", "show me runs" |
| **B** | INSPECT | "show me the plan", "what does X mean", "read file Y", "look at Z" |
| **C** | PLAN_GATE_RESPONSE | "approve", "revise", "cancel" + freeform notes (only valid in response to an open PLAN_GATE surface) |
| **D** | PR_REVIEW_GATE_RESPONSE | "merge", "request changes", "block" + freeform notes (only valid in response to an open PR_REVIEW_GATE surface) |
| **E** | MILESTONE_GATE_RESPONSE | "continue", "stop", "pause" + freeform notes (only valid in response to an open MILESTONE_GATE surface) |
| **F** | PRODUCT_WORK | "ship X", "build Y", "implement Z", "kick off the loop", "/build", "do PC.X / 2.X" — new product feature |
| **G** | BUG_TRIAGE | "X is broken", "Y throws an error", "Z doesn't work", "/triage-bug" |
| **H** | CONTRACT_CHANGE | "update / change / fix / codify the [agent prompt / skill / AGENTS.md / AGENT_OPS / contract / playbook / convention]" — process / instruction-set / cross-agent change |
| **I** | BOOKKEEPING | (manager-internal — post-merge ROADMAP mark-done, plan archive moves, MANIFEST refresh) — never user-initiated as a standalone request |

---

## Strict procedures

### A — STATUS

**IF** category = A **THEN:**

1. `Skill: naavik-cold-start` if not loaded this session.
2. `Skill: naavik-roadmap-status` OR `Skill: manager-standup-report` (pick whichever is more specific to the question).
3. Read relevant config / logs / git state via Read / Grep / Bash (read-only commands).
4. Reply in chat with ONE terse summary, leading with the result.
5. **No commits. No sub-agent dispatches. No pushes. No file writes (except `traces/<run-id>/manager.log` if a run is in flight).**

HALT.

---

### B — INSPECT

**IF** category = B **THEN:**

1. Use Read / Grep / Glob to pull the requested content.
2. Reply in chat with the content + minimal context.
3. **No commits. No dispatches. No file writes.**

HALT.

---

### C — PLAN_GATE_RESPONSE

**Precondition:** an open PLAN_GATE surface exists in the conversation. If not, fall back to category F (treat as new product work) or H (treat as contract change).

**IF** category = C **AND** user said **APPROVE** **THEN:**

1. Append `[ISO-ts] GATE name=plan_review outcome=approved decisions='<verbatim user notes>'` to `traces/<run-id>/manager.log`.
2. Dispatch engineer with the approved plan path + locked decisions (use Task tool).
3. Engineer creates branch `feat/<task-id>-<slug>` (UPPERCASE task-id per `docs/AGENT_OPS.md § 2.8`).
4. Continue operating loop to PR open + reviewer dispatch.

**IF** category = C **AND** user said **REVISE** **THEN:**

1. Append GATE event with `outcome=revise notes='<user's notes>'`.
2. Re-dispatch architect with revision notes.
3. HALT at next PLAN_GATE on architect's return.

**IF** category = C **AND** user said **CANCEL** **THEN:**

1. Append GATE event with `outcome=cancel`.
2. Mirror the task back to Todo on the Project board via `scripts/gh-project.sh set-status <item-id> Todo`.
3. Flip ROADMAP row from `[~]` back to `[ ]` (this is BOOKKEEPING — execute per § I).
4. Surface cancellation summary. HALT.

---

### D — PR_REVIEW_GATE_RESPONSE

**Precondition:** an open PR_REVIEW_GATE surface exists. Hacker + devops verdicts must be on the table.

**Required pre-check:** Hacker verdict must be `APPROVE` or `APPROVE_WITH_NOTES`. **If hacker = `BLOCK`,** manager surfaces *"Hacker BLOCK overrides Merge — re-asking"* and re-emits the gate. User cannot override hacker BLOCK with Merge.

**IF** category = D **AND** user said **MERGE** **THEN:**

1. `gh pr merge <N> --squash --delete-branch`.
2. `git checkout main && git pull origin main` (bring squash commit local).
3. Verify Issue closed (`Closes #N` trailer fires GitHub workflow automation).
4. Continue to **§ I BOOKKEEPING** for ROADMAP mark-done + plan archive + MANIFEST refresh.
5. If the merge closes a milestone, surface MILESTONE_GATE.

**IF** category = D **AND** user said **REQUEST CHANGES** **THEN:**

1. Append GATE event with `outcome=request_changes path=<A|B|C|...> notes='<verbatim>'`.
2. Re-dispatch engineer with change scope. Engineer adds NEW commits to the same branch (no `--amend` per `AGENTS.md § Workflow`).
3. Re-dispatch hacker + devops in parallel for delta-only re-review.
4. HALT at next PR_REVIEW_GATE.

**IF** category = D **AND** user said **BLOCK** **THEN:**

1. Append GATE event with `outcome=block reason='<verbatim>'`.
2. `gh pr close <N> --comment "<reason>"`. Branch stays (for archive / forensics).
3. Mirror task back to Todo or to a follow-up row on the Project board.
4. File any new ROADMAP rows for re-scoped work (BOOKKEEPING).
5. Surface block summary + token-waste note. HALT.

---

### E — MILESTONE_GATE_RESPONSE

**Precondition:** an open MILESTONE_GATE surface exists.

**IF** category = E **AND** user said **CONTINUE** **THEN:** loop to operating-loop step 2 (Pick next).

**IF** category = E **AND** user said **STOP** or **PAUSE** **THEN:**

1. Refresh `traces/<run-id>/MANIFEST.json` with final `outcome=delivered`, `tokens_spent`, `what_built`, `errors_encountered`.
2. Append final line to `traces/runs.log`.
3. Print closing summary. HALT.

---

### F — PRODUCT_WORK

**IF** category = F **THEN:**

1. `Skill: naavik-cold-start` if not loaded.
2. `Skill: manager-pick-next` if the user didn't specify the task; otherwise use the user-named task.
3. Mirror PC.X / 2.X / etc. → In Progress on Project board: `scripts/gh-project.sh set-status <item-id> "In Progress"`.
4. Check `docs/plans/`:
   - If `<NN>-<slug>.md` exists with `Status: APPROVED` → jump to step 7.
   - If exists with `Status: DRAFT` → surface PLAN_GATE for user review.
   - If absent → continue to step 5.
5. Dispatch architect via Task to author `docs/plans/<NN>-<slug>.md` with locked frontmatter + open-questions + approval-checklist (per `docs/plans/README.md` conventions).
6. **HALT at PLAN_GATE** — surface plan path + goal + open questions + approval checklist. User picks Approve / Revise / Cancel → category C.
7. On approve → dispatch engineer via Task with the plan path + locked decisions + branch name `feat/<task-id>-<slug>` (UPPERCASE).
8. Engineer implements + runs quality gates + manual QA + opens PR via `gh pr create` using `.github/pull_request_template.md`.
9. Dispatch hacker + devops via Task **in parallel** (single message, multiple tool uses) for review.
10. **HALT at PR_REVIEW_GATE** — surface hacker verdict + devops verdict + engineer deviations. User picks Merge / Request changes / Block → category D.
11. On merge → category I (BOOKKEEPING).

---

### G — BUG_TRIAGE

**IF** category = G **THEN:**

1. Dispatch devops first via Task for repro + log analysis.
2. Based on devops output:
   - **Mechanical fix** (small, contained, no architectural change) → dispatch engineer per § F step 7.
   - **Structural fix** (requires re-architecting a layer) → dispatch architect for re-plan per § F step 5; HALT at PLAN_GATE.
   - **Security-sensitive** (auth / secrets / untrusted input / scrapers) → dispatch hacker for STRIDE first.
3. Continue per § F from step 7 onwards.

---

### H — CONTRACT_CHANGE

**This is the path `aa2f6a0` violated. Strict procedure — no exceptions:**

A CONTRACT_CHANGE is ANY edit to a file in this list:

- `src/**` (code)
- `tests/**` (tests)
- `migrations/**` (alembic migrations)
- `scripts/**` (helper scripts)
- `.claude/agents/**` (agent prompts)
- `.claude/skills/**` (skill bodies)
- `.claude/commands/**` (slash commands)
- `.claude/hooks/**` (Claude Code hooks + git hooks)
- `.claude/settings.json`, `.claude/settings.local.json` (config)
- `AGENTS.md`, `CLAUDE.md` (workflow contract + Claude conventions)
- `docs/AGENT_OPS.md`, `docs/PLAYBOOK.md`, `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, `docs/DEPLOYMENT.md` (operational contracts)
- `DESIGN.md` (visual contract)
- `docs/design/**` (design contracts — except `docs/design/mockups/**` which is gitignored)
- `docs/plans/<NN>-<slug>.md` while in `DRAFT` or `APPROVED` state (the active plan file)
- `docs/prompts/<NN>-<slug>.md` (active kickoff prompts)
- `README.md` § Configuration / § Operations (anything beyond a `Last updated` bump)

**IF** category = H **THEN:**

1. Create branch: `chore/<task-id>-<slug>` OR `docs/<task-id>-<slug>` (NOT `feat/` — `feat/` is for product code; `chore/` is for process / docs / tooling; `docs/` for pure documentation).
2. `git checkout -b <branch>`.
3. Make edits to the affected files.
4. Commit with `chore(<scope>):` or `docs(<scope>):` prefix.
5. `git push -u origin <branch>`.
6. Open PR: `gh pr create --title "..." --body "..."` using `.github/pull_request_template.md`.
7. Dispatch hacker + devops in parallel for review (even for doc-only changes — they verify forward pointers, deviations sections, and stack-invariant compliance).
8. **HALT at PR_REVIEW_GATE.**
9. On merge → category I (BOOKKEEPING).

**NEVER push directly to `main` for category H changes.** If you find yourself drafting `git commit -am ...` against `main` for any file in the CONTRACT_CHANGE list above, **stop**. That's category H. PR required.

**This rule supersedes the appearance of expedience.** Doc-only changes still need review for:
- Forward pointers to ROADMAP rows / other docs (must resolve).
- Convention conflicts with sibling docs.
- Single-doc-tracking violations (don't duplicate ROADMAP ledger in plans / skills).
- Sunset compliance (no new CLI / vault extensions).
- Tracing-contract compliance (new agent procedures must include ERROR + BUILT/REVIEWED requirements).

---

### I — BOOKKEEPING

**These are mechanical post-merge / post-decision edits. Direct push to `main` is the canonical path.**

**Allowed files for BOOKKEEPING (direct push):**

- `ROADMAP.md` — row state flips (`[~]` → `[x]`, `[ ]` → `[~]`), "Last updated" bumps, new row additions for follow-ups (PC.6a, DEF-23, etc.), Notes column updates with deliverable narratives.
- `docs/plans/<NN>-<slug>.md` → `docs/plans/archive/<NN>-<slug>.md` — plan archive moves via `git mv` (or `mv` + `git add` of both paths).
- `docs/plans/archive/<NN>-<slug>.md` — frontmatter `Status: DRAFT|APPROVED → EXECUTED`, `Shipped:` line additions, `## Deviations from plan` section appends (if the engineer didn't fold them in the PR squash).
- `docs/prompts/<NN>-<slug>.md` → `docs/prompts/archive/<NN>-<slug>.md` — kickoff prompt archive moves.
- `traces/**` — gitignored, but for completeness: MANIFEST.json schema refreshes, runs.log appends, per-agent log appends.
- `README.md` "Last updated" line bumps (one-liners only).

**NOT allowed in BOOKKEEPING** (these are CONTRACT_CHANGE — require PR):

- Any edit to `.claude/agents/**`, `.claude/skills/**`, `.claude/hooks/**`, `.claude/commands/**`, `.claude/settings*.json`.
- Any edit to `docs/AGENT_OPS.md`, `docs/PLAYBOOK.md`, `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, `docs/DEPLOYMENT.md`.
- Any edit to `AGENTS.md`, `CLAUDE.md` (except possibly `Last updated` line — but prefer PR).
- Any edit to `src/**`, `tests/**`, `migrations/**`, `scripts/**`.
- Any edit to `docs/design/**` (except mockups, which are gitignored).
- Any NEW file outside the allowed BOOKKEEPING list above.

**IF** category = I **THEN:**

1. Make edits to allowed files on `main` (already on `main` or `git checkout main && git pull` first).
2. `git add <specific-paths>` (use explicit paths; never `git add -A` or `git add .`).
3. Commit with one of these message prefixes:
   - `docs(roadmap): mark <task-id> done — PR #<N> squash <sha>`
   - `docs(archive): archive plan <NN>-<slug> — Status EXECUTED`
   - `docs(roadmap): file <task-id> + <task-id> follow-ups`
   - `docs(roadmap): bump Last updated — <one-line>`
4. `git push origin main`.
5. If new ROADMAP rows were added that need Project board sync, run `scripts/gh-project.sh create-issue <task-id> "<title>" --priority <P> --effort <E> --milestone "<M>" --parent <epic-#>` per the single-writer rule (`AGENTS.md § GitHub state — single writer rule`). NEVER `gh issue create` directly.

---

## Hard rules (apply across all categories)

1. **Never push CONTRACT_CHANGE files directly to `main`.** Always go through PR.
2. **Never `git push --force` to main/master.** Period.
3. **Never `git commit --amend` to fix pre-commit-hook failures.** Create a NEW commit. (`AGENTS.md § Workflow`.)
4. **Never skip the deviations section before archiving a plan.** (`AGENTS.md § Workflow step 7`.)
5. **Never write GitHub Issue / Project state directly.** Use `scripts/gh-project.sh` per single-writer rule.
6. **Never extend `src/cli/` or `src/services/vault.py`.** Both on sunset track (`ROADMAP.md` § Phase 2 tasks 2.11 + 2.12).
7. **Always log `ERROR` events as failures happen.** (`docs/AGENT_OPS.md § 7.2`.)
8. **Always emit `BUILT` / `REVIEWED` summary line at end of every dispatch.** Last line of the agent's log.
9. **Always halt at gates — never auto-advance.** User approval required at PLAN_GATE, PR_REVIEW_GATE, MILESTONE_GATE.
10. **Always classify before acting.** First step of every user message is "which category does this fit?" — answer that, then run the strict procedure.
11. **If unsure, ask ONE targeted question.** Don't improvise. Don't combine categories silently.

---

## File classification quick reference

For fast lookup when you're about to edit a file:

| Path glob | Default category | Push path |
|---|---|---|
| `src/**` | H — CONTRACT_CHANGE | PR |
| `tests/**` | H — CONTRACT_CHANGE | PR |
| `migrations/**` | H — CONTRACT_CHANGE | PR |
| `scripts/**` | H — CONTRACT_CHANGE | PR |
| `.claude/agents/**` | H — CONTRACT_CHANGE | PR |
| `.claude/skills/**` | H — CONTRACT_CHANGE | PR |
| `.claude/commands/**` | H — CONTRACT_CHANGE | PR |
| `.claude/hooks/**` | H — CONTRACT_CHANGE | PR |
| `.claude/settings*.json` | H — CONTRACT_CHANGE | PR |
| `AGENTS.md` | H — CONTRACT_CHANGE | PR |
| `CLAUDE.md` | H — CONTRACT_CHANGE | PR |
| `docs/AGENT_OPS.md` | H — CONTRACT_CHANGE | PR |
| `docs/PLAYBOOK.md` (this file) | H — CONTRACT_CHANGE | PR |
| `docs/ARCHITECTURE.md` | H — CONTRACT_CHANGE | PR |
| `docs/RUNBOOK.md` | H — CONTRACT_CHANGE | PR |
| `docs/DEPLOYMENT.md` | H — CONTRACT_CHANGE | PR |
| `DESIGN.md` | H — CONTRACT_CHANGE | PR |
| `docs/design/**` (not mockups) | H — CONTRACT_CHANGE | PR |
| `docs/plans/<NN>-<slug>.md` (active) | H — CONTRACT_CHANGE | PR (bundles with the implementation PR) |
| `docs/prompts/<NN>-<slug>.md` (active) | H — CONTRACT_CHANGE | PR |
| `docs/plans/archive/**` | I — BOOKKEEPING | direct push (at archive time) |
| `docs/prompts/archive/**` | I — BOOKKEEPING | direct push (at archive time) |
| `ROADMAP.md` | I — BOOKKEEPING | direct push |
| `README.md` § Configuration / Operations | H — CONTRACT_CHANGE | PR |
| `README.md` "Last updated" only | I — BOOKKEEPING | direct push |
| `traces/**` | n/a (gitignored) | n/a |
| `docs/design/mockups/**` | n/a (gitignored) | n/a |

**If a single commit would touch BOTH categories** (e.g. archiving plan 18 to `docs/plans/archive/` AND ALSO updating an agent prompt), split into two commits / two PRs / one PR + one bookkeeping commit. Don't mix categories in one push.

---

## Worked example — this playbook's own authorship

The playbook itself fits category **H — CONTRACT_CHANGE**. Procedure:

1. ✅ Branch `chore/A.14-task-playbook` created from `main`.
2. ✅ `docs/PLAYBOOK.md` (this file) authored.
3. ✅ `.claude/agents/manager.md` updated to require playbook consultation.
4. ✅ `.claude/skills/naavik-cold-start/SKILL.md` updated to include `docs/PLAYBOOK.md` in canonical reading.
5. ✅ `docs/AGENT_OPS.md § 3` updated with pointer.
6. ✅ `AGENTS.md` Quick Start updated with pointer.
7. → Commit with `chore(playbook): add docs/PLAYBOOK.md — strict if-then task classification` prefix.
8. → `git push -u origin chore/A.14-task-playbook`.
9. → `gh pr create --title "chore(playbook): add task playbook — strict if-then rules" --body "..."`.
10. → Dispatch hacker + devops in parallel for review.
11. → **HALT at PR_REVIEW_GATE.**
12. → On merge: BOOKKEEPING commit adds ROADMAP A.14 row + "Last updated" bump (direct push).

This procedure is what should have happened for `aa2f6a0`. The playbook makes it the only path going forward.

---

## Extensions

This playbook covers 9 categories that cover the task surface as of 2026-05-17. New task types (e.g. "scheduled maintenance run", "rollback PR", "force-restart-orchestrator") get new categories — but adding a category is itself a CONTRACT_CHANGE (PR to `docs/PLAYBOOK.md`). Don't add categories inline.
