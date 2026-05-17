---
description: Skill mirror of `/learn` slash command (dual-surface convention per AGENT_OPS § 10.2). Use when manager suggests `/learn` at the milestone gate, when the user types `/learn`, when the user says "retrospective" / "analyze last N runs" / "what did we learn this week" / "any recurring failures". Agent-invocable entry point; procedural body lives in `.claude/commands/learn.md`.
allowed-tools: Read, Bash(scripts/agent-memory.sh:*), Bash(scripts/gh-project.sh:*), Bash(jq:*), Bash(grep:*), Task, AskUserQuestion
---

# naavik-learn

Periodic retrospective of the agent system itself. Analyzes the last N runs (default 10) via `scripts/agent-memory.sh analyze-run` + `mine-patterns`, surfaces failure patterns / drift signals / token hotspots / skill activation stats / promotion candidates / ROADMAP candidates, and lets the user disposition each via AskUserQuestion. Read-only on traces; writes go through `scripts/agent-memory.sh` per single-writer rule.

## When to invoke

- User types `/learn` or `/learn 10` / `/learn 20`.
- Manager's milestone-gate (step 15) detects `>= 5 runs since last runs-analysis/*.md mtime` and suggests `/learn`.
- User asks "retrospective", "what did we learn", "any recurring failures", "should we promote anything", "analyze last N runs", "weekly review".

## What this skill does

Run the canonical procedure in `.claude/commands/learn.md`. **Read that file as the procedure source** — this skill body is the framing + the when-to-invoke + the rules, not the procedure.

High-level shape (full step list in the command file):

1. **Pre-flight** — confirm `.claude/memory/.keep` exists; project token spend.
2. **Per-run analysis** — `scripts/agent-memory.sh analyze-run <run-id>` for each of the N most recent runs.
3. **Pattern mining** — `scripts/agent-memory.sh mine-patterns --lookback N`.
4. **Interactive report** with sections A–G:
   - Failure patterns (top 5 ERROR kinds).
   - Drift signals (plans with > 4 deviations).
   - Token-spend hotspots.
   - Skill activation stats (skills with 0 invocations flagged).
   - Knowledge promotion candidates (`occurrence_count >= 5`).
   - ROADMAP candidates (unfiled discussions w/ priority >= MEDIUM).
   - Alias mining (MEMORY_MISS events from manager.log).
5. **Apply dispositions** via the single writer.
6. **Trace bookkeeping** — append `LEARN runs_analyzed=N patterns_mined=M promoted=K filed=L aliases=P` to manager.log.

## Canonical references

- `.claude/commands/learn.md` — full procedural body.
- `scripts/agent-memory.sh --help` — writer surface (`analyze-run`, `mine-patterns`, `promote-lesson`).
- `docs/design/AGENT_MEMORY.md` — architecture + extension.
- `docs/AGENT_OPS.md § 14.5–14.6` — Wave 2 + Wave 3 contracts.
- `.claude/agents/manager.md` § Milestone boundary gate — the suggestion surface.

## When NOT to invoke

- Last `/learn` ran within the same session AND no new runs occurred since.
- The user typed `/standup` (different intent — current state, not retrospective). Use `manager-standup-report` skill instead.
- The user asked about a single run's outcome (use `/runs <N>` or read `traces/<run-id>/MANIFEST.json` directly).
- Compaction events.

## Forbidden during invocation

- Do NOT auto-promote any pattern. Threshold 5 + user consent per pattern (locked per plan 19 § C.4 Q3 + § C.3 Q4).
- Do NOT write to `~/.claude/projects/<...>/memory/MEMORY.md`. Read-only.
- Do NOT bypass `scripts/agent-memory.sh` or `scripts/gh-project.sh`. Single-writer rule for both.
- Do NOT bypass the AskUserQuestion gates in sections A / E / F / G. The whole point is opt-in retrospective; an unsupervised analysis with no consent gate accumulates a backlog nobody reads.
- Do NOT analyze runs older than `--lookback N`. The retrospective is bounded by N to keep token spend predictable.
