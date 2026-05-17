---
description: Autonomous milestone delivery loop. Manager picks next epic from the GitHub Project, plans with architect, engineer implements, hacker reviews, devops gates, manager updates the board. Halts at plan / PR / milestone gates for user review. Token-budget aware.
argument-hint: <milestone name | "next">
---

Milestone: $ARGUMENTS (default: "next")

0. **Bootstrap check.** Confirm `.claude/github-project.json` exists. If not, halt and tell the user: "Agent system not bootstrapped yet — run `/bootstrap` first. See `docs/AGENT_OPS.md` § 2 for the walkthrough." Do NOT proceed.

1. **Bootstrap the run-id**: pick a string of the form `YYYY-MM-DDTHH-MM-SS_<6-char-hex>` (e.g., `2026-05-16T09-30-15_a3f2b8` — use `date +%Y-%m-%dT%H-%M-%S` + `uuidgen | tr -d '-' | head -c6`). Create `traces/<run-id>/` as the trace root.

2. **Budget pre-flight.** Read `.claude/budget.json` and `.claude/budget-ledger.json` (latter may be missing — treat as zeros). If today's `total_today` ≥ 90% of `daily_token_ceiling`, surface a warning via AskUserQuestion before spawning the manager: continue / raise cap / halt.

3. **Spawn `manager` via Task** with the operating loop in its system prompt. Pass in the prompt:
   - **Target milestone**: $ARGUMENTS (or "the next open milestone in the GitHub Project" if "next").
   - **Current ROADMAP state**: a brief summary of the current phase + the open task ledger (manager reads `ROADMAP.md` directly to confirm).
   - **GitHub Project ID**: read from `.claude/github-project.json`. If missing, run `scripts/gh-project.sh init` first and re-read.
   - **Token budget**: read `.claude/budget.json` and pass `daily_token_ceiling` + per-agent caps. Halt if projected next-step spend exceeds remaining budget.
   - **Trace root**: `./traces/<run-id>/` — all sub-agents append to per-agent log files there.

4. **Manager runs the operating loop** (defined in `.claude/agents/manager.md`) and reports at every gate.

5. **At plan gate** (manager step 4): present the plan path and a 1-paragraph summary. Ask the user to approve via AskUserQuestion (options: Approve / Revise / Cancel + free-form notes). Do NOT proceed until the user replies.

6. **At PR gate** (manager step 8): present the hacker verdict + devops gate results + the PR URL + the engineer's deviations memo. Ask the user via AskUserQuestion (options: Merge / Request changes / Block + free-form notes). Do NOT merge until the user replies.

7. **At milestone gate** (manager step 13): **STOP**. Print a milestone-delivery summary:
   - Issues closed (with links).
   - PRs merged (with links).
   - Files touched (grouped by area).
   - Deviations recorded across the milestone's plans.
   - ROADMAP.md diff (what flipped from `[~]` to `[x]`, "Last updated" bump).
   - Token spend per agent + total vs ceiling.
   - Trace root path.
   Ask whether to continue to the next milestone. Do NOT auto-advance.

8. **Trace bookkeeping** (manager owns):
   - Append run summary to `./traces/<run-id>/MANIFEST.json` (schema in AGENT_OPS.md § 7.3).
   - Append a one-liner to `./traces/runs.log`: `[ISO-timestamp] run=<run-id> milestone=<name> outcome=<delivered|halted|failed> issues=<n> prs=<n> tokens=<n>`.
   - Update `.claude/budget-ledger.json` with the run's spend (per AGENT_OPS.md § 8.2).
   - Run `scripts/gh-project.sh sync --apply` at end of run to push any ROADMAP edits the manager made through to the Project (idempotent; usually a no-op if the manager already called `set-status` per-task).
