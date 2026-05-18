---
description: Load the canonical context for any Naavik agent at the start of a session or subagent dispatch — read AGENTS.md, ROADMAP_OVERVIEW.md, AGENT_OPS.md, ARCHITECTURE.md, and the agent's specific cold-start list in the correct order. Use this as the FIRST action of every new session or subagent dispatch. Triggers on phrases like "cold start", "what's the status", "where are we", "let's start", "begin", or the very first user message of any session.
allowed-tools: Read, Glob, Grep, Bash(grep:*), Bash(jq:*)
---

# naavik-cold-start

Agents land cold from fresh `claude --agent <name>` dispatch. Without deterministic cold-start, agents pick arbitrary canonical-guide subsets and miss key conventions (historical regression: engineer dispatches skipped `AGENTS.md § Key Conventions § CLI` and extended vault).

This skill loads same files, same order, every time.

## Step 1 — Canonical guides (in order)

Every agent, regardless of role:

1. `AGENTS.md` § Quick Start + § Workflow (steps 2 + 4 + 5 + 7) + § Key Conventions § CLI + § Single-doc-tracking + § GitHub state — single writer rule
2. `docs/PLAYBOOK.md` (full — strict if-then task classification; consult FIRST per user message; codified after `aa2f6a0` workflow miss, ROADMAP A.14)
3. `docs/ROADMAP_OVERVIEW.md` (130 lines, full)
4. `docs/AGENT_OPS.md` § 1–7

## Step 2 — Agent-specific list

Read your agent's "Required reading on cold start" in `.claude/agents/<agent>.md`. Order matters.

## Step 3 — Operational state

- `traces/runs.log` tail 10 — recent activity
- `.claude/budget-ledger.json` — today spend vs cap
- `.claude/github-issue-map.json` — Issue # per ROADMAP task

## Step 4 — Confirm

Emit one `Loaded:` summary line. Proceed with task.

## When NOT to invoke

- Compaction events — Claude Code re-attaches invoked skills; re-invoking wastes tokens.
- User already gave task AND relevant files already read this turn.

## Forbidden during cold-start

- Do NOT extend `src/cli/` or `src/services/vault.py` (sunset, Phase 2 tasks 2.11 / 2.12).
- Do NOT propose tracking-table duplication of ROADMAP in plans (drift trap per `AGENTS.md § Single-doc-tracking`).
- Do NOT write GitHub Issue / Project state via raw `gh issue create` / `gh api graphql` — all mutations via `scripts/gh-project.sh` (per `CLAUDE.md § GitHub state — single writer rule`).
