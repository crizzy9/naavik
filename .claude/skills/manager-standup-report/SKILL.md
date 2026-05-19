---
description: Generate the `/standup` standup-style report — current milestone state, in-flight items, blocked items, ROADMAP-vs-Project drift, recent runs, and today's token spend vs cap. Use when the user invokes `/standup`, asks "what's the status", "where are we", "give me a standup", or "what's happening with the agent system". Use also at the start of a fresh session to orient. Triggers on phrases like "standup", "status report", "where are we", "what's the state", "what's the status of <milestone>", "give me an update".
allowed-tools: Read, Bash(jq:*), Bash(tail:*)
---

# manager-standup-report

Manager owns standup format. Canonical shape: milestone state + recent activity + drift + budget. Read-only.

## When to invoke

- `/standup` slash command.
- User asks "what's the status" / "where are we" / "give me a standup" / "what's happening".
- Manager pre-flight before `/build` — confirm bootstrap + no major drift.
- After milestone closes — wrap-up standup of what shipped.

## Steps

1. **Bootstrap check.** Read `.claude/github-project.json`. Missing → halt: "Agent system not bootstrapped — run `/bootstrap` first (`docs/AGENT_OPS.md` § 2)." No fake standup against empty board.

2. **Milestone state.**
   ```bash
   .claude/naavik-ops gh milestone-status "<current-milestone>"
   ```
   Parse JSON: items by Status (`Todo`/`In Progress`/`Done`/`Backlog`). Count each. Backlog = deferred (A.28 4-status); surface as separate "Backlog by epic" line.

3. **Backlog by epic** (post-A.28).
   ```bash
   .claude/naavik-ops gh backlog-by-epic --top 3
   ```
   JSON: epics by Priority, ≤3 items each. Top epic → "Backlog top epic" line. Empty → omit.

4. **Drift signal.**
   ```bash
   .claude/naavik-ops gh sync   # dry-run, no --apply
   ```
   If lines > 0, recommend `/sync-roadmap --apply` (ROADMAP wins).

5. **Recent runs.**
   ```bash
   tail -n 5 traces/runs.log 2>/dev/null
   ```
   Lines: `[ts] run=<id> milestone=<name> outcome=<delivered|halted|failed> issues=<n> prs=<n> tokens=<n>`.

6. **Budget snapshot.**
   ```bash
   jq -r '"\(.current_day): \(.total_today)"' .claude/budget-ledger.json
   ```
   Compare vs `.claude/budget.json:daily_token_ceiling`. Flag if > 80%.

7. **Emit format:**
   ```
   STANDUP — <ISO-timestamp>

   Current milestone: <name>  (<done> / <total> done, <in-progress> in flight, <todo> open)

   Done since last standup:
     - [<task-id>] <title>  #<issue>  PR <url>
     - ...

   In flight:
     - [<task-id>] <title>  #<issue>  (agent: <name>, started <ts>)
     - ...

   Blocked:
     - [<task-id>] <title>  #<issue>  blocker: <one-line>
     - ...

   Next 3 (recommended):
     - [<task-id>] <title>  priority=<P>  estimate=<E>
     - ...

   Drift: <N>  (ROADMAP vs Project; 0=clean. >0 → recommend /sync-roadmap --apply.)

   Budget: <spent>/<cap> (<%>)  — <flag> if >80%

   Recent runs (last 5):
     <verbatim lines from traces/runs.log tail>
   ```

8. **Append to `traces/standups.log`:**
   ```
   [<ISO-timestamp>] STANDUP milestone=<name> done=<n> in_flight=<n> blocked=<n> drift=<n> tokens=<n>
   ```

## Canonical references

- `.claude/commands/standup.md` — slash-command spec.
- `.claude/agents/manager.md` § Identity invariant + § GitHub state — single writer rule.
- `.claude/naavik_ops/gh.py` subcommands `milestone-status`, `sync`, `next-unblocked`.
- `docs/AGENT_OPS.md` § 8 (Token budget) + § 7.4 (Run index).

## When NOT to invoke

- Mid-`/build` — end-of-loop or pre-loop only; don't interrupt step transitions.
- Task-specific status ("status of PC.5?") — single-issue lookup, not milestone standup.
- Compaction events.

## Forbidden during invocation

- Do NOT mutate Project board state. Read-only.
- Do NOT skip drift check — undetected drift is #1 cause of plan/reality mismatch (per `AGENTS.md § Single-doc-tracking`).
- Do NOT invent in-flight/blocked items — pull from live Project state + ROADMAP `[~]` markers.
