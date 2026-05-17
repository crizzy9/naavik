---
description: Before answering questions about LinkedIn scraping, prepare-commit-msg case sensitivity, hacker self-approval pivots, destructive-rm guard, sandbox post-direct-push denials, or any topic with a captured knowledge entry, check `.claude/memory/knowledge/<topic>.md`. Run `scripts/agent-memory.sh list knowledge` to see the index. Use whenever an agent is about to research a topic that may have been captured before. Triggers on phrases like "have we hit this before", "what did we decide about", "memory lookup", "knowledge entry", "lookup the topic", "is there a knowledge file", "do we know about", "captured pattern", "linkedin scraping", "branch case sensitivity", "self-approval", "destructive rm", "sandbox denial".
allowed-tools: Read, Glob, Grep, Bash(scripts/agent-memory.sh:*), Bash(jq:*)
---

# naavik-memory-lookup

Memory + learning system reading surface (A.15 Wave 1). Use before researching a topic from scratch — the answer may already be captured. Single-writer rule applies for writes; this skill is read-only.

## When to invoke

- Architect picks a new design decision (check `decisions.jsonl` for prior captures).
- Engineer hits a gotcha mid-implementation (check `knowledge/` for prior pivots).
- Hacker sees a familiar attack surface (check for prior PR review pivots).
- Devops debugs an orchestrator failure (check for prior failure-mode entries).
- Manager surfaces a deferred item (check `discussions.jsonl` for prior dispositions).
- Any user-phrase trigger matching topic alias front-matter across knowledge files.

## What this skill does

### Step 1 — Enumerate captured topics

```bash
scripts/agent-memory.sh list knowledge
```

Returns table of `TOPIC | CONFIDENCE | ALIASES` from every `.claude/memory/knowledge/*.md`.

### Step 2 — Read the matching topic file

```
Read .claude/memory/knowledge/<slug>.md
```

Front-matter contains `Topic`, `Aliases`, `First captured`, `Last referenced`, `Supersedes`, `Confidence`. Body is markdown — context, resolution, related links.

### Step 3 — Cross-reference structured stores

For prior decisions on the topic:

```bash
scripts/agent-memory.sh query decisions '.rationale | test("<topic-keyword>"; "i")'
```

For prior discussions:

```bash
scripts/agent-memory.sh query discussions '.topic | test("<topic-keyword>"; "i")'
```

For prior lessons (Wave 2+):

```bash
scripts/agent-memory.sh query lessons '.pattern | test("<topic-keyword>"; "i")'
```

### Step 4 — Decide whether the captured knowledge is current

- `Last referenced` older than 90 days + `Confidence: low` → re-verify before trusting.
- `Supersedes: <slug>` field present → also read the predecessor for context (don't act on it).
- Decision row with `state: "superseded"` → action lives in the `superseded_by` row.

### Step 5 — Record a miss

If the topic the agent is researching has NO knowledge entry but feels like it should, log a miss to `manager.log`:

```
[ISO-timestamp] MEMORY_MISS topic=<slug-candidate> phrase='<user-phrase-or-task-keyword>'
```

Wave 3's `mine-patterns --aliases` aggregates these to propose alias additions.

## Capturing new knowledge (write path)

This skill is read-only. To capture a new entry the agent (or user) routes through the single writer:

```bash
echo "<body markdown>" | scripts/agent-memory.sh record-knowledge <slug> - \
  --aliases "phrase1, phrase2, phrase3" --confidence high --run-id <run-id>
```

Or for a decision:

```bash
scripts/agent-memory.sh record-decision <id> '<one-line verdict>' '<rationale>' \
  --run-id <run-id>
```

NEVER use `Edit` or `Write` directly against `.claude/memory/` — single-writer rule is enforced by the hacker-secrets-audit skill scan.

## Canonical references

- `docs/design/AGENT_MEMORY.md` — full architecture + store schemas.
- `docs/AGENT_OPS.md § 14` — daily workflow integration.
- `scripts/agent-memory.sh` — the single writer.
- `.claude/memory/knowledge/` — current corpus of captured topics.
- `~/.claude/projects/<...>/memory/MEMORY.md` — Claude Code's auto-managed personal memory (**read-only**; never write).
- `CLAUDE.md` — project-level invariants Claude Code reads on every cold start.

## When NOT to invoke

- The topic clearly has no prior capture (novel domain, first-time decision).
- Same skill already invoked this turn — corpus hasn't changed.
- Compaction events — skill content lifecycle re-attaches invoked skills.

## Forbidden during invocation

- Do NOT `Edit` or `Write` against `.claude/memory/`. All writes go through `scripts/agent-memory.sh`.
- Do NOT write to `~/.claude/projects/<...>/memory/MEMORY.md`. That file is Claude Code's; we read only.
- Do NOT trust a `Confidence: low` entry over the live source it cites — re-read the linked `traces/<run-id>/<log>.log` or `docs/plans/archive/<NN>.md` before acting.
- Do NOT mass-promote knowledge entries inline. Promotion goes through `/learn` → `scripts/agent-memory.sh promote-lesson` (Wave 3) so the audit trail survives.
