---
description: Autonomous milestone delivery loop. Manager picks next epic from the GitHub Project, plans with architect, engineer implements, hacker reviews, devops gates, manager updates the board. Halts at plan / PR / milestone gates for user review. Token-budget aware.
argument-hint: <milestone name | "next">
---

Milestone: $ARGUMENTS (default: "next")

0. **Bootstrap check.** Confirm `.claude/github-project.json` exists. If not, halt + tell user: "Agent system not bootstrapped yet — run `/bootstrap` first. See `docs/AGENT_OPS.md` § 2 for walkthrough." Do NOT proceed.

1. **Bootstrap run-id**: pick string of form `YYYY-MM-DDTHH-MM-SS_<6-char-hex>` (e.g., `2026-05-16T09-30-15_a3f2b8` — use `date +%Y-%m-%dT%H-%M-%S` + `uuidgen | tr -d '-' | head -c6`). Create `traces/<run-id>/` as trace root.

2. **Budget pre-flight.** Read `.claude/budget.json` + `.claude/budget-ledger.json` (latter may be missing — treat as zeros). Today's `total_today` ≥ 90% of `daily_token_ceiling` → surface warning via AskUserQuestion before spawning manager: continue / raise cap / halt.

3. **Spawn `manager` via Task** with operating loop in its system prompt. Pass in prompt:
   - **Target milestone**: $ARGUMENTS (or "next open milestone in GitHub Project" if "next").
   - **Current ROADMAP state**: brief summary of current phase + open task ledger (manager reads `ROADMAP.md` directly to confirm).
   - **GitHub Project ID**: read from `.claude/github-project.json`. Missing → run `scripts/gh-project.sh init` first + re-read.
   - **Token budget**: read `.claude/budget.json` + pass `daily_token_ceiling` + per-agent caps. Halt if projected next-step spend exceeds remaining budget.
   - **Trace root**: `./traces/<run-id>/` — all sub-agents append to per-agent log files there.

4. **Manager runs operating loop** (defined in `.claude/agents/manager.md`) + reports at every gate.

5. **At plan gate** (manager step 4): present plan path + 1-paragraph summary. Ask user to approve via AskUserQuestion (options: Approve / Revise / Cancel + free-form notes). Do NOT proceed until user replies.

6. **At PR gate** (manager step 8): present hacker verdict + devops gate results + PR URL + engineer's deviations memo. Ask user via AskUserQuestion (options: Merge / Request changes / Block + free-form notes). Do NOT merge until user replies.

7. **At milestone gate** (manager step 13): **STOP**. Print milestone-delivery summary:
   - Issues closed (with links).
   - PRs merged (with links).
   - Files touched (grouped by area).
   - Deviations recorded across milestone's plans.
   - ROADMAP.md diff (what flipped from `[~]` to `[x]`, "Last updated" bump).
   - Token spend per agent + total vs ceiling.
   - Trace root path.
   Ask whether to continue to next milestone. Do NOT auto-advance.

8. **Trace bookkeeping** (manager owns):
   - Append run summary to `./traces/<run-id>/MANIFEST.json` (schema in AGENT_OPS.md § 7.3).
   - Append one-liner to `./traces/runs.log`: `[ISO-timestamp] run=<run-id> milestone=<name> outcome=<delivered|halted|failed> issues=<n> prs=<n> tokens=<n>`.
   - Update `.claude/budget-ledger.json` w/ run's spend (per AGENT_OPS.md § 8.2).
   - Run `scripts/gh-project.sh sync --apply` at end of run to push any ROADMAP edits manager made through to Project (idempotent; usually no-op if manager already called `set-status` per-task).
