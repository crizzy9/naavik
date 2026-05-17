---
description: Write `traces/<run-id>/MANIFEST.json` at the end of a `/build` or `/triage-bug` run, per the schema in `docs/AGENT_OPS.md § 7.3`. Captures run-id, start/end timestamps, milestone, issues closed, PRs merged, files touched, deviations recorded, tokens spent per agent, halt reason. Use at end of every multi-agent run, when devops is invoked to close out a run, when manager finalizes a milestone. Triggers on phrases like "trace manifest", "manifest.json", "write the manifest", "end of run", "close out the run", "run summary", "tokens spent".
allowed-tools: Read, Glob, Write, Bash(jq:*)
---

# devops-trace-manifest

Every multi-agent run (`/build`, `/triage-bug`, `/threat-model`, `/design-screen`) writes a manifest at the end so the run is auditable: what shipped, who touched what, how many tokens. The schema is frozen in `docs/AGENT_OPS.md § 7.3`. This skill enforces the canonical shape + writes the file atomically.

## When to invoke

- End of a `/build` run — manager's final step before MILESTONE GATE.
- End of a `/triage-bug` run — when the fix is verified + closed.
- End of a `/threat-model` run — when the threat doc lands.
- End of a `/design-screen` run — when mockup + handoff memo ship.
- Anytime devops is invoked to "close out a run".

## What this skill does

1. **Confirm RUN_ID.** Every multi-agent run has a RUN_ID format `<YYYY-MM-DDTHH-MM-SS>_<6hex>` (e.g. `2026-05-16T21-00-00_a11v2x`). The trace dir is `traces/<RUN_ID>/`.

2. **Gather data from the trace logs:**

   ```bash
   ls traces/<RUN_ID>/
   ```

   Expect:
   - `manager.log` (orchestration events)
   - `architect.log` (if architect was dispatched)
   - `engineer.log` (if engineer was dispatched)
   - `engineer-deviations.log` (if any deviations)
   - `devops.log` (if devops was dispatched)
   - `hacker.log` (if hacker was dispatched)
   - `designer.log` (if designer was dispatched)

3. **Parse the canonical schema** from `docs/AGENT_OPS.md § 7.3`:

   ```json
   {
     "run_id": "2026-05-16T09-30-15_a3f2b8",
     "started_at": "2026-05-16T09:30:15Z",
     "ended_at": "2026-05-16T11:45:02Z",
     "milestone": "Pre-Phase-2 paper cuts",
     "issues_closed": [42, 43],
     "prs_merged": ["https://github.com/crizzy9/naavik/pull/87"],
     "files_touched": ["src/cli/init.py", "..."],
     "deviations_recorded": ["docs/plans/archive/10d-secret-key-hardening.md § Deviations"],
     "tokens_spent": {"manager": 152000, "architect": 410000, "engineer": 893000, "hacker": 200000, "devops": 50000, "designer": 0},
     "halt_reason": null
   }
   ```

   Fields:

   - **`run_id`** — the RUN_ID string.
   - **`started_at`** — first timestamp from `manager.log` line 1, ISO-8601 UTC.
   - **`ended_at`** — last timestamp across all logs, ISO-8601 UTC.
   - **`milestone`** — current milestone name (e.g. `Pre-Phase-2 paper cuts`, `Phase A`).
   - **`issues_closed`** — numeric list of Issue numbers closed during this run (from `manager.log` GATE events or PR `Closes #N` lines).
   - **`prs_merged`** — URL list of merged PRs (from `manager.log` MIRROR events or `gh pr list --state merged --search "<branch>"`).
   - **`files_touched`** — paths edited, derived from `engineer.log` EDIT events.
   - **`deviations_recorded`** — list of `docs/plans/<NN-name>.md § Deviations from plan` references (promoted via `manager-deviation-promote` skill).
   - **`tokens_spent`** — per-agent token spend, from `.claude/budget-ledger.json` delta over the run window.
   - **`halt_reason`** — `null` if completed; otherwise one of `budget_exceeded`, `user_halted`, `hacker_block`, `failure_recovery_exhausted`, `manual_pause`.

4. **Write atomically:**

   ```bash
   cat > traces/<RUN_ID>/MANIFEST.json.tmp <<EOF
   {
     "run_id": "<run-id>",
     "started_at": "<iso>",
     "ended_at": "<iso>",
     "milestone": "<name>",
     "issues_closed": [<nums>],
     "prs_merged": [<urls>],
     "files_touched": [<paths>],
     "deviations_recorded": [<refs>],
     "tokens_spent": {<per-agent>},
     "halt_reason": <null | "reason">
   }
   EOF
   mv traces/<RUN_ID>/MANIFEST.json.tmp traces/<RUN_ID>/MANIFEST.json
   ```

   Use `jq` to validate before the move:
   ```bash
   jq empty traces/<RUN_ID>/MANIFEST.json.tmp && mv traces/<RUN_ID>/MANIFEST.json.tmp traces/<RUN_ID>/MANIFEST.json
   ```

5. **Append a one-liner to the run index:**

   ```bash
   ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   echo "[$ISO] run=<run-id> milestone=<name> outcome=<delivered|halted|failed> issues=<n> prs=<n> tokens=<total>" >> traces/runs.log
   ```

   Outcome values:
   - `delivered` — `halt_reason == null` AND `issues_closed` non-empty.
   - `halted` — `halt_reason != null` (budget / user / hacker block / failure).
   - `failed` — `halt_reason == "failure_recovery_exhausted"` specifically.

## Worked example

For a `/build` run that delivered PC.5:

```json
{
  "run_id": "2026-05-17T10-15-30_b8c2f1",
  "started_at": "2026-05-17T10:15:30Z",
  "ended_at": "2026-05-17T11:08:42Z",
  "milestone": "Pre-Phase-2 paper cuts",
  "issues_closed": [7],
  "prs_merged": ["https://github.com/crizzy9/naavik/pull/52"],
  "files_touched": ["src/config.py", "tests/test_config.py", "README.md", "docs/plans/17-pc5-secret-key-enforcement.md"],
  "deviations_recorded": ["docs/plans/archive/17-pc5-secret-key-enforcement.md § Deviations from plan"],
  "tokens_spent": {
    "manager": 95000,
    "architect": 210000,
    "engineer": 340000,
    "hacker": 130000,
    "devops": 28000,
    "designer": 0
  },
  "halt_reason": null
}
```

Runs.log line:
```
[2026-05-17T11:08:45Z] run=2026-05-17T10-15-30_b8c2f1 milestone=Pre-Phase-2 paper cuts outcome=delivered issues=1 prs=1 tokens=803000
```

## Canonical references

- `docs/AGENT_OPS.md` § 7.3 — manifest schema (source).
- `docs/AGENT_OPS.md` § 7.4 — run index format.
- `.claude/agents/manager.md` § Tracing.
- `.claude/agents/devops.md` § Tracing.

## When NOT to invoke

- Single-agent dispatches that didn't create a run-id (one-off bug investigations, ad-hoc skill invocations).
- Compaction events.

## Forbidden during invocation

- Do NOT skip the manifest at run end. Without it, `claude /runs` shows ghosts.
- Do NOT invent `tokens_spent` values — pull from `.claude/budget-ledger.json` delta.
- Do NOT mark `halt_reason: null` when the run actually halted. Honesty here matters for retrospectives.
- Do NOT write the file non-atomically (without the `.tmp` + `mv` dance). Partial writes corrupt the manifest.
- Do NOT omit the runs.log append. The trace index is the searchable history.
