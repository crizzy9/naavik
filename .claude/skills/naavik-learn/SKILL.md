---
description: Skill mirror of `/learn` slash command (dual-surface convention per AGENT_OPS § 10.2). Use when manager suggests `/learn` at the milestone gate, when the user types `/learn`, when the user says "retrospective" / "analyze last N runs" / "what did we learn this week" / "any recurring failures". Agent-invocable entry point; procedural body lives in `.claude/commands/learn.md`.
allowed-tools: Read, Bash(.claude/naavik-ops:*), Bash(jq:*), Bash(grep:*), Task, AskUserQuestion
---

# naavik-learn

Periodic retrospective of agent system itself. Analyzes last N runs (default 10) via `.claude/naavik-ops memory analyze-run` + `mine-patterns`, surfaces failure patterns / drift / token hotspots / skill activation / promotion + ROADMAP candidates, user dispositions each via AskUserQuestion. Read-only on traces; writes via `.claude/naavik_ops/memory.py` per single-writer rule.

## When to invoke

- User types `/learn` / `/learn 10` / `/learn 20`.
- Manager milestone-gate (step 15) detects `>= 5 runs since last runs-analysis/*.md mtime` and suggests `/learn`.
- User: "retrospective", "what did we learn", "any recurring failures", "should we promote anything", "analyze last N runs", "weekly review".

## What this skill does

Run canonical procedure in `.claude/commands/learn.md`. **Read that file as procedure source** — this skill body is framing + when-to-invoke + rules, not the procedure.

High-level shape (full steps in command file):

1. **Pre-flight** — confirm `.claude/memory/.keep` exists; project token spend.
2. **Per-run analysis** — `.claude/naavik-ops memory analyze-run <run-id>` per N most recent runs.
3. **Pattern mining** — `.claude/naavik-ops memory mine-patterns --lookback N`.
4. **Interactive report**, sections A–G:
   - Failure patterns (top 5 ERROR kinds).
   - Drift signals (plans with > 4 deviations).
   - Token-spend hotspots.
   - Skill activation stats (0-invocation flagged).
   - Knowledge promotion candidates (`occurrence_count >= 5`).
   - ROADMAP candidates (unfiled discussions w/ priority >= MEDIUM).
   - Alias mining (MEMORY_MISS events from manager.log).
5. **Apply dispositions** via single writer.
6. **Trace bookkeeping** — append `LEARN runs_analyzed=N patterns_mined=M promoted=K filed=L aliases=P` to manager.log.

## Canonical references

- `.claude/commands/learn.md` — full procedural body.
- `.claude/naavik-ops memory --help` — writer surface (`analyze-run`, `mine-patterns`, `promote-lesson`).
- `docs/design/AGENT_MEMORY.md` — architecture + extension.
- `docs/AGENT_OPS.md § 14.5–14.6` — Wave 2 + Wave 3 contracts.
- `.claude/agents/manager.md` § Milestone boundary gate — suggestion surface.

## When NOT to invoke

- Last `/learn` ran same session AND no new runs since.
- User typed `/standup` (different intent — current state, not retrospective). Use `manager-standup-report`.
- User asked about single run's outcome (use `/runs <N>` or read `traces/<run-id>/MANIFEST.json` directly).
- Compaction events.

## Forbidden during invocation

- Do NOT auto-promote any pattern. Threshold 5 + user consent per pattern (plan 19 § C.4 Q3 + § C.3 Q4).
- Do NOT write to `~/.claude/projects/<...>/memory/MEMORY.md`. Read-only.
- Do NOT bypass `.claude/naavik_ops/memory.py` or `.claude/naavik_ops/gh.py`. Single-writer rule.
- Do NOT bypass AskUserQuestion gates in sections A / E / F / G. Whole point = opt-in retrospective.
- Do NOT analyze runs older than `--lookback N`. Bounded by N to keep token spend predictable.
