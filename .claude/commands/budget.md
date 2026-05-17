---
description: Show today's token spend per agent + total vs daily ceiling. Reads .claude/budget.json (caps) and .claude/budget-ledger.json (running spend).
argument-hint:
---

Inspect the agent system's token budget. Per `docs/AGENT_OPS.md` § 8.

**Step 1 — Load files:**

Read `.claude/budget.json` for caps. Read `.claude/budget-ledger.json` for current-day spend (if absent, ledger is empty — today's spend is 0).

**Step 2 — Display report:**

Print a table:

```
Token budget — <today's date>

| Agent     | Spent today | Cap        | % used | Notes |
|-----------|-------------|------------|--------|-------|
| manager   |     152,000 |    800,000 |  19.0% |       |
| architect |     410,000 |  1,200,000 |  34.2% |       |
| engineer  |     893,000 |  1,500,000 |  59.5% |       |
| devops    |      50,000 |    700,000 |   7.1% |       |
| hacker    |     200,000 |    500,000 |  40.0% |       |
| designer  |           0 |    300,000 |   0.0% |       |
|-----------|-------------|------------|--------|-------|
| TOTAL     |   1,705,000 |  5,000,000 |  34.1% |       |
```

Format numbers with thousands separators. Highlight any agent or total >80% with a `⚠ near cap` note in the Notes column; >100% with `🛑 OVER CAP`.

**Step 3 — History (last 7 days):**

If `.claude/budget-ledger.json` has a `history` array, print a brief summary:

```
Last 7 days (totals):
  2026-05-15  4,120,000  82.4%
  2026-05-14    890,000  17.8%
  ...
```

**Step 4 — Halt action reminder:**

Print the `halt_action` value from `.claude/budget.json` (default `ask_user`). Explain: when projected spend exceeds the daily ceiling mid-`/build`, the manager halts and asks for one-time override / cap raise / stop-for-the-day.

**If `.claude/budget-ledger.json` doesn't exist:** print "Ledger empty — no runs have been logged yet. Run `/build` to start accruing spend." and stop.
