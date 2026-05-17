---
description: Generate the `/standup` standup-style report — current milestone state, in-flight items, blocked items, ROADMAP-vs-Project drift, recent runs, and today's token spend vs cap. Use when the user invokes `/standup`, asks "what's the status", "where are we", "give me a standup", or "what's happening with the agent system". Use also at the start of a fresh session to orient. Triggers on phrases like "standup", "status report", "where are we", "what's the state", "what's the status of <milestone>", "give me an update".
allowed-tools: Read, Bash(scripts/gh-project.sh:*), Bash(jq:*), Bash(tail:*)
---

# manager-standup-report

Manager owns the standup format. This skill captures the canonical shape so every `/standup` invocation produces the same structure — current milestone state, recent activity, drift signals, budget snapshot. Reads only; never mutates board state.

## When to invoke

- User invokes `/standup` (slash command).
- User asks "what's the status" / "where are we" / "give me a standup" / "what's happening".
- Manager pre-flight check before `/build` — confirm the system is bootstrapped + no major drift.
- After a milestone closes — emit a wrap-up standup capturing what shipped.

## What this skill does

1. **Bootstrap check.** Read `.claude/github-project.json`. If missing, halt with: "Agent system not bootstrapped — run `/bootstrap` first (see `docs/AGENT_OPS.md` § 2)." Do not fake a standup against an empty board.

2. **Pull milestone state.**
   ```bash
   scripts/gh-project.sh milestone-status "<current-milestone>"
   ```
   Parse the JSON output: items grouped by Status (`Todo` / `In Progress` / `Done`). Count each.

3. **Pull drift signal.**
   ```bash
   scripts/gh-project.sh sync   # dry-run, no --apply
   ```
   Count drift lines. If > 0, recommend `/sync-roadmap --apply` (ROADMAP wins).

4. **Pull recent runs.**
   ```bash
   tail -n 5 traces/runs.log 2>/dev/null
   ```
   Each line: `[ts] run=<id> milestone=<name> outcome=<delivered|halted|failed> issues=<n> prs=<n> tokens=<n>`.

5. **Pull budget snapshot.**
   ```bash
   jq -r '"\(.current_day): \(.total_today)"' .claude/budget-ledger.json
   ```
   Compare against `.claude/budget.json:daily_token_ceiling`. Flag if > 80%.

6. **Emit the canonical standup format:**
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

   Drift: <N>  (ROADMAP vs Project; <N>=0 means clean. If >0, recommend /sync-roadmap --apply.)

   Budget: <spent>/<cap> (<%>)  — <flag> if >80%

   Recent runs (last 5):
     <verbatim lines from traces/runs.log tail>
   ```

7. **Append a one-liner to `traces/standups.log`** for the standup history:
   ```
   [<ISO-timestamp>] STANDUP milestone=<name> done=<n> in_flight=<n> blocked=<n> drift=<n> tokens=<n>
   ```

## Canonical references

- `.claude/commands/standup.md` — slash-command spec (the steps above are derived from it).
- `.claude/agents/manager.md` § Identity invariant + § GitHub state — single writer rule.
- `scripts/gh-project.sh` subcommands `milestone-status`, `sync`, `next-unblocked`.
- `docs/AGENT_OPS.md` § 8 (Token budget) + § 7.4 (Run index).

## When NOT to invoke

- Mid-`/build` — the standup format is end-of-loop or pre-loop reporting; don't interrupt step transitions.
- For task-specific status ("status of PC.5?") — that's a single-issue lookup, not a milestone standup.
- Compaction events — re-attaches automatically.

## Forbidden during invocation

- Do NOT mutate Project board state. This is a read-only report.
- Do NOT skip the drift check — undetected drift is the #1 cause of plan/reality mismatch (codified in `AGENTS.md § Single-doc-tracking`).
- Do NOT invent in-flight or blocked items — pull them from the live Project state + ROADMAP `[~]` markers, not assumption.
