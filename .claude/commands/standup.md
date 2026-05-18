---
description: Manager reports current milestone state — what's done, in-flight, blocked, next, and any drift between ROADMAP.md and the GitHub Project.
argument-hint:
---

0. **Bootstrap check.** `.claude/github-project.json` missing → print "Agent system not bootstrapped — run `/bootstrap` first (see `docs/AGENT_OPS.md` § 2)." + halt. Don't fake standup against empty board.

1. **Spawn `manager` via Task** with:
   - **ROADMAP state**: manager reads `ROADMAP.md` directly (current phase, open task ledger, "Last updated" date, recent earlier-line entries).
   - **GitHub Project state**: manager queries via `.claude/naavik-ops gh milestone-status` (current milestone's open / in-progress / done counts + titles).
   - **Recent run log**: manager reads last 5 entries from `./traces/runs.log` if exists.
   - **Budget snapshot**: manager reads `.claude/budget.json` + `.claude/budget-ledger.json` for today's spend.
   - **Drift check**: manager runs `.claude/naavik-ops gh sync` (dry-run) to detect any ROADMAP-vs-Project disagreement.

2. **Manager produces** structured standup:
   - **Current milestone** — name + % complete (closed / total issues).
   - **Done since last standup** — list w/ PR links (cross-reference against `./traces/runs.log` since last `/standup` invocation, or last 24h if none).
   - **In-flight** — items marked `[~]` in ROADMAP or "In Progress" on board; per each, name responsible agent (per run log).
   - **Blocked** — items flagged blocked + blocker (open question, dep on external API, awaiting user input).
   - **Backlog by epic** (post-A.28) — top epic in Backlog by Priority + item count. Use `.claude/naavik-ops gh backlog-by-epic --top 3`. Surface deferred work at glance so operator can decide whether to promote.
   - **Next 3 items** — manager's recommended next items from ROADMAP ledger (unblocked, highest priority, Status=Todo). Backlog items excluded (deferred from current cycle).
   - **Drift** — output of `.claude/naavik-ops gh sync` (drift count + diffs). > 0 → recommend `/sync-roadmap --apply` to reconcile (ROADMAP wins). Note: `sync` preserves Backlog (Backlog → Todo is not drift).
   - **Token budget** — today's `total_today` + % of `daily_token_ceiling`. > 80% → flag.

3. **Print** standup to stdout AND **append** to `./traces/standups.log` (one entry per `/standup`, timestamped):

   ```
   [ISO-timestamp] STANDUP milestone=<name> done=<n> in_flight=<n> blocked=<n> drift=<n> tokens=<n>
   ```
