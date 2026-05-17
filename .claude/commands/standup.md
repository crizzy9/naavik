---
description: Manager reports current milestone state — what's done, in-flight, blocked, next, and any drift between ROADMAP.md and the GitHub Project.
argument-hint:
---

0. **Bootstrap check.** If `.claude/github-project.json` is missing, print "Agent system not bootstrapped — run `/bootstrap` first (see `docs/AGENT_OPS.md` § 2)." and halt. Don't fake a standup against an empty board.

1. **Spawn `manager` via Task** with:
   - **ROADMAP state**: manager reads `ROADMAP.md` directly (current phase, open task ledger, "Last updated" date, recent earlier-line entries).
   - **GitHub Project state**: manager queries via `scripts/gh-project.sh milestone-status` (current milestone's open / in-progress / done counts + titles).
   - **Recent run log**: manager reads the last 5 entries from `./traces/runs.log` if it exists.
   - **Budget snapshot**: manager reads `.claude/budget.json` + `.claude/budget-ledger.json` for today's spend.
   - **Drift check**: manager runs `scripts/gh-project.sh sync` (dry-run) to detect any ROADMAP-vs-Project disagreement.

2. **Manager produces** a structured standup:
   - **Current milestone** — name + % complete (closed / total issues).
   - **Done since last standup** — list with PR links (cross-reference against `./traces/runs.log` since last `/standup` invocation, or last 24h if none).
   - **In-flight** — items marked `[~]` in ROADMAP or "In Progress" on the board; for each, name the responsible agent (per the run log).
   - **Blocked** — items flagged blocked + the blocker (open question, dep on external API, awaiting user input).
   - **Backlog by epic** (post-A.28) — top epic in Backlog by Priority + item count. Use `scripts/gh-project.sh backlog-by-epic --top 3`. Surface deferred work at a glance so the operator can decide whether to promote.
   - **Next 3 items** — manager's recommended next items from the ROADMAP ledger (unblocked, highest priority, Status=Todo). Backlog items are excluded (they're deferred from the current cycle).
   - **Drift** — output of `scripts/gh-project.sh sync` (drift count + diffs). If > 0, recommend `/sync-roadmap --apply` to reconcile (ROADMAP wins). Note: `sync` preserves Backlog (Backlog → Todo is not a drift).
   - **Token budget** — today's `total_today` + % of `daily_token_ceiling`. If > 80%, flag.

3. **Print** the standup to stdout AND **append** to `./traces/standups.log` (one entry per `/standup`, timestamped):

   ```
   [ISO-timestamp] STANDUP milestone=<name> done=<n> in_flight=<n> blocked=<n> drift=<n> tokens=<n>
   ```
