---
description: Show recent agent system runs from traces/runs.log + their outcomes. Optionally drill into a specific run's MANIFEST.json.
argument-hint: [count | run-id]
---

Inspect agent system run history. Per `docs/AGENT_OPS.md` § 7.

**If $ARGUMENTS is a run-id** (matches `YYYY-MM-DDTHH-MM-SS_<6hex>`):

1. Read `traces/<run-id>/MANIFEST.json`. Pretty-print it.
2. List all log files under `traces/<run-id>/` with line counts.
3. Suggest: `./traces/watch.sh <run-id>` to inspect interactively in tmux panes.

**If $ARGUMENTS is a number** (default: 10): show the last N runs.

```
scripts/gh-project.sh runs <count>
```

Print one line per run, formatted as a table:

```
Last N runs (from traces/runs.log):

| When           | Run ID              | Milestone            | Outcome     | Issues | PRs | Tokens     |
|----------------|---------------------|----------------------|-------------|--------|-----|------------|
| 2026-05-16 09:30 | 09-30-15_a3f2b8   | Pre-Phase-2 paper cuts | delivered |    2  |  1  |  1,705,000 |
| ...            |                     |                      |             |        |     |            |
```

**Step 3 — Drill-in hint:**

If any run had outcome=`halted` or `failed`, suggest: "Run `/runs <run-id>` to inspect the manifest + per-agent logs."

**Step 4 — Stats:**

If 5+ runs in the log, print aggregate stats:
- Total runs.
- Outcomes: delivered / halted / failed counts.
- Total tokens spent across the window.
- Average tokens per run.
- Average tokens per delivered run.

**If `traces/runs.log` doesn't exist:** print "No runs yet. Run `/build` to start." and stop.
