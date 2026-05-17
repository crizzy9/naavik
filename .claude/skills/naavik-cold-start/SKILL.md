---
description: Load the canonical context for any Naavik agent at the start of a session or subagent dispatch — read AGENTS.md, ROADMAP_OVERVIEW.md, AGENT_OPS.md, ARCHITECTURE.md, and the agent's specific cold-start list in the correct order. Use this as the FIRST action of every new session or subagent dispatch. Triggers on phrases like "cold start", "what's the status", "where are we", "let's start", "begin", or the very first user message of any session.
allowed-tools: Read, Glob, Grep, Bash(grep:*), Bash(jq:*)
---

# naavik-cold-start

Naavik's agents land cold from a fresh `claude --agent <name>` dispatch. Without this skill the agent picks an arbitrary subset of the canonical guides and risks missing key conventions (the CLI/vault sunset is the historical example — engineer dispatches that skip `AGENTS.md § Key Conventions § CLI` have extended the vault in the past).

This skill is the deterministic cold-start: it loads the same files, in the same order, every time.

## Step 1 — Read the canonical guides (in order)

For every agent, regardless of role:

1. `AGENTS.md` § Quick Start + § Workflow (steps 2 + 4 + 5 + 7) + § Key Conventions § CLI + § Single-doc-tracking + § GitHub state — single writer rule
2. `docs/ROADMAP_OVERVIEW.md` (130 lines — full)
3. `docs/AGENT_OPS.md` § 1–7

## Step 2 — Read the agent-specific cold-start list

Look up your agent's "Required reading on cold start" section in `.claude/agents/<agent>.md`. Read those files in the order listed.

## Step 3 — Read the operational state

- `traces/runs.log` tail 10 — recent agent activity
- `.claude/budget-ledger.json` — today's spend vs cap
- `.claude/github-issue-map.json` — which Issue # implements which ROADMAP task

## Step 4 — Confirm the cold-start is complete

Output one line of `Loaded:` summary so the user knows you're oriented. Then proceed with the actual task.

## When NOT to invoke

- Compaction events — Claude Code's skill content lifecycle re-attaches invoked skills automatically. Re-invoking would waste tokens.
- The user has already told you the task and you've already read the relevant files in this turn — skip the redundant read.

## Forbidden during cold-start

- Do not extend `src/cli/` or `src/services/vault.py`. Both are on the sunset track (Phase 2 tasks 2.11 / 2.12).
- Do not propose tracking-table duplication of ROADMAP into plan files (drift trap per `AGENTS.md § Single-doc-tracking`).
- Do not write GitHub Issue / Project state directly via `gh issue create` or `gh api graphql` — all mutations go through `scripts/gh-project.sh` (per `CLAUDE.md § GitHub state — single writer rule`).
