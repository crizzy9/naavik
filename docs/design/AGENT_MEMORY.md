# Agent Memory + Learning System — Design

> **Status:** Active (Wave 1+2+3 shipped 2026-05-17 via PR `feat/A.15-agent-memory`).
> **Plan of record:** `docs/plans/19-agent-memory-and-learning.md` (archived after ship). This document is the permanent reference; the plan archives with its `## Deviations from plan` section.
> **Companion docs:** `docs/AGENT_OPS.md § 14` (daily workflow), `AGENTS.md § Agent System` (infrastructure table), `scripts/agent-memory.sh` (single writer).

---

## § 1 — Architecture

The Naavik agent system accumulates three kinds of state across runs that nothing in the existing stack captures:

1. **Decisions** with rationale (why we picked JSONL over SQLite; why direct guest-API over RSShub).
2. **Discussions** the user and the agents had where something was deferred, blocked, or surfaced as a follow-up.
3. **Knowledge** — long-form captures of gotchas, option matrices, recurring patterns, and the resolution we landed on.

These complement Claude's native primitives without duplicating them:

| Surface | Owner | What it holds | Read/write |
|---|---|---|---|
| `CLAUDE.md` | repo, hand-maintained | project-level invariants Claude Code reads on every cold start | hand-edit |
| `AGENTS.md` | repo, hand-maintained | canonical workflow contract for AI agents | hand-edit |
| `~/.claude/projects/<...>/memory/MEMORY.md` | Claude Code, auto-managed | per-user personal preferences | **read-only from this system** |
| `.claude/skills/<name>/SKILL.md` | repo, hand-maintained | procedural memory (auto-trigger on phrase) | hand-edit |
| `.claude/budget-ledger.json` | manager, auto-managed | daily token spend | manager-only writer |
| `.claude/github-issue-map.json` | `scripts/gh-project.sh`, auto-managed | persistent `{task → issue#}` cache | script-only writer |
| **`.claude/memory/`** | **`scripts/agent-memory.sh`, auto-managed** | **the surfaces this doc covers** | **script-only writer** |

### Directory layout

```
.claude/memory/                               ← gitignored per-fork EXCEPT .keep + knowledge/*.md
├── .keep                                     ← directory marker (committed)
├── decisions.jsonl                           ← architectural decisions w/ rationale + supersedes
├── discussions.jsonl                         ← deferred items captured at gate boundaries
├── lessons.jsonl                             ← Wave 2: mined patterns from session analysis
├── recurring-patterns.jsonl                  ← Wave 2: auto-aggregated patterns
├── knowledge/                                ← committed shared cross-contributor corpus
│   ├── linkedin-scraping.md
│   ├── prepare-commit-msg-case.md
│   ├── hacker-self-approval.md
│   ├── destructive-rm-guard.md
│   └── sandbox-post-direct-push.md
└── runs-analysis/                            ← Wave 2: per-run summary markdown
    └── <run-id>.md
```

### Single-writer rule

`scripts/agent-memory.sh` is the **sole writer** to `.claude/memory/`. Mirrors `scripts/gh-project.sh`'s pattern for GitHub state. Enforced by:

- `hacker-secrets-audit` skill scans diffs for direct `Edit` / `Write` calls against `.claude/memory/` paths.
- Schema validation runs on every write (malformed input rejected at the boundary).
- Atomic writes via `mktemp` + `mv` — partial files never visible.
- Append-only invariant on JSONL stores. Updates go through `--supersedes <old-id>`; deletion is forbidden.
- **Concurrent writes serialized via subshell-scoped `flock` on `.claude/memory/.lock`** (codified in A.17 / plan 21 to fix the lost-update race the hacker found at the PR_REVIEW_GATE).
- **`jq` queries to memory stores are sandboxed** via regex allowlist + identifier deny-list (`env`, `input*`, `getpath`, `path*`, `setpath`, `delpaths`, `debug`, `stderr`, `$ENV`) — blocks `env.*` exfil through `cmd_query` (A.17). `--aliases` is validated to forbid newlines + `---` front-matter fences.

### Reading model

Any agent can `Read` / `Grep` / `jq` any store. Discovery happens through skills:

- **`naavik-memory-lookup`** — triggers on topic phrases, points the caller at the right knowledge file.
- **`naavik-discussion-capture`** — manager invokes at PR/milestone gates to surface deferred items.
- **`naavik-learn`** — skill mirror of `/learn` command (Wave 2 retrospective).
- **`manager-promote-lesson`** — promotes a recurring pattern to a lesson + knowledge stub (Wave 3).

---

## § 2 — Stores

### 2.1 `decisions.jsonl`

One line per locked architectural decision with rationale + supersession chain.

Schema:

```json
{"id": "storage-backend", "verdict": "JSONL + markdown", "rationale": "see plan 19 § C.1",
 "captured_at": "2026-05-17T08:50:00Z", "state": "active", "run_id": "2026-05-17T08-40-13_4abef2"}
```

Fields:

- `id` — kebab-case identifier (unique active). Duplicate id rejected unless `--supersedes` provided.
- `verdict` — one-line outcome of the decision.
- `rationale` — pointer to the plan / option matrix / trace where rationale lives.
- `captured_at` — ISO-8601 UTC.
- `state` — `active` | `superseded`.
- `superseded_by` (optional) — set when a newer decision overrides this one.
- `supersedes` (optional) — set on the new decision pointing back at what it overrides.
- `run_id` (optional) — the trace run that produced the decision.

Query default filter: `state == "active"`.

Write surface: `scripts/agent-memory.sh record-decision <id> <verdict> <rationale> [--supersedes <id>] [--run-id <id>]`.

### 2.2 `discussions.jsonl`

One line per deferred item captured at a gate boundary. NOT a task ledger — that's ROADMAP. This is the audit trail of "the user and the agents discussed X; here is how it was dispositioned."

Schema:

```json
{"id": "20260517-a3f2b8", "topic": "JWT denylist on password rotation",
 "surface": "manager.log", "priority": "MEDIUM", "phase": "Phase 1.x deferred items",
 "filed_as": "#54", "captured_at": "2026-05-17T08:55:00Z", "run_id": "2026-05-17T08-40-13_4abef2"}
```

Fields:

- `id` — auto-generated `<YYYYMMDD>-<6hex>`.
- `topic` — one-line subject.
- `surface` — where the deferred item surfaced (`manager.log` / `architect.log` / `user-message` / `pr-comment`).
- `priority` — `CRITICAL` | `HIGH` | `MEDIUM` | `LOW`.
- `phase` (optional) — ROADMAP phase the item belongs to.
- `filed_as` (optional) — Issue `#N` if mirrored, `skipped` if explicitly skipped at gate, or absent if memory-only.
- `captured_at` — ISO-8601 UTC.
- `run_id` (optional).

Append-only. No supersede semantics — re-disposition produces a new row referencing the old via `surface: "discussions.jsonl#<old-id>"`.

Write surface: `scripts/agent-memory.sh record-discussion <topic> <surface> [...]`.

### 2.3 `lessons.jsonl` (Wave 2)

One line per promoted recurring pattern. Threshold 5 occurrences before promotion (`scripts/agent-memory.sh promote-lesson <pattern_id>` rejects below).

Schema:

```json
{"id": "lesson-pytest-x-flaked", "pattern": "tests/test_X intermittent on parallel-run",
 "evidence_runs": ["2026-05-17T03-16-16_75a522", "..."], "proposed_action": "split test_X into _a + _b",
 "captured_at": "2026-05-17T09:00:00Z", "state": "active"}
```

Write surface: `scripts/agent-memory.sh record-lesson <id> <pattern> <evidence-runs-csv> [...]`. Manual record-lesson is also available; auto-write happens via `promote-lesson` on patterns with `count >= 5`.

### 2.4 `recurring-patterns.jsonl` (Wave 2)

Auto-aggregated patterns from per-run `ERROR` events. Written by `scripts/agent-memory.sh mine-patterns [--lookback N]`.

Schema:

```json
{"pattern_id": "find-replace__pivot", "step": "find-replace", "kind": "pivot",
 "occurrence_count": 3, "runs": ["2026-05-17T...", "2026-05-17T..."],
 "first_seen": "2026-05-17T03:16:16Z", "last_seen": "2026-05-17T09:00:00Z",
 "proposed_action": ""}
```

`pattern_id` shape: `<step>__<kind>`. `mine-patterns` is idempotent — re-runs overwrite the pattern row with the current count.

### 2.5 `knowledge/<topic>.md`

Long-form markdown, one file per topic. Front-matter is machine-parseable; body is free-form prose with `## Context`, `## Resolution / pattern`, `## Related` sections.

Front-matter:

```markdown
---
Topic: linkedin-scraping
Aliases: linkedin, scrapers, RSShub, guest API, voyager
First captured: 2026-05-17 (run 2026-05-17T08-40-13_4abef2)
Last referenced: 2026-05-17
Supersedes: none
Confidence: high
---
```

`Aliases` are the discovery surface — `naavik-memory-lookup` skill triggers on alias phrases. Wave 3's `mine-patterns --aliases` proposes alias additions from `MEMORY_MISS` events.

Write surface: `scripts/agent-memory.sh record-knowledge <slug> <body-source|-> [...]`. Refuses overwrite unless `--overwrite`; supersession via `--supersedes <slug>`.

### 2.6 `runs-analysis/<run-id>.md` (Wave 2)

Per-run summary produced by `scripts/agent-memory.sh analyze-run <run-id>`. Idempotent — re-runs overwrite. Contents:

- Run metadata (started, ended, milestone, outcome, halt_reason).
- Per-agent token spend.
- ERROR events grouped by kind.
- `BUILT` / `REVIEWED` terminal summaries from each agent log.
- Files touched (from MANIFEST).
- Deviations (from `engineer-deviations.log`).

---

## § 3 — Skills + commands

### Skills (auto-trigger surface)

| Skill | Wave | Purpose |
|---|---|---|
| `naavik-memory-lookup` | 1 | Before researching a topic, check `.claude/memory/knowledge/<topic>.md`. Triggers on alias phrases. |
| `naavik-discussion-capture` | 1 | Manager invokes at PR_REVIEW_GATE + MILESTONE_GATE to surface deferred items. AskUserQuestion per candidate; one of file-as-ROADMAP / file-as-memory-only / skip / merge. |
| `naavik-learn` | 2 | Skill mirror of `/learn` (dual-surface convention per AGENT_OPS § 10.2). Thin body; points at `.claude/commands/learn.md` as procedure source. |
| `manager-promote-lesson` | 3 | Wraps `scripts/agent-memory.sh promote-lesson`. Consent flow + auto-slugging + knowledge stub template. |

### Commands (slash command surface)

| Command | Wave | Purpose |
|---|---|---|
| `/memory <list\|query\|knowledge> [args]` | 1 | Read-only inspection of all stores. Delegates to `scripts/agent-memory.sh list` / `query`. |
| `/learn [N]` | 2 | Manual retrospective. Analyzes last N runs (default 10), mines patterns, surfaces interactive promotion candidates. |

---

## § 4 — Discussion-capture gate procedure

Locked decision per plan 19 § C.3 Q2: **surface-then-ask at every PR_REVIEW_GATE + MILESTONE_GATE**. Not auto-file. Not classifier-based hybrid. Direct answer to user's "are we doing this?" check.

Manager invokes `Skill: naavik-discussion-capture` at:

- **PR_REVIEW_GATE** (manager operating loop step 10), BEFORE closing the gate.
- **MILESTONE_GATE** (manager operating loop step 15), BEFORE printing the milestone summary.

Procedure (full body in `.claude/skills/naavik-discussion-capture/SKILL.md`):

1. Scan current run's `manager.log` for `SIDE_TASK`, `BLOCKED`, `OPEN_QUESTION`, `ROADMAP_EDIT row=<new>` events.
2. Cap candidates at 5 (rank by SIDE_TASK > OPEN_QUESTION > BLOCKED > ROADMAP_EDIT, most recent first).
3. Surface AskUserQuestion — one row per candidate. Options: file-as-ROADMAP / file-as-memory-only / skip / merge-with-#N.
4. Apply dispositions via `scripts/agent-memory.sh record-discussion` AND (if filed) `scripts/gh-project.sh create-issue` (single-writer rule).
5. Append `DISCUSSION_CAPTURE candidates=<N> filed=<M> skipped=<K> merged=<L>` to `manager.log`.

---

## § 5 — Integration with Claude's native primitives

### 5.1 `MEMORY.md` — read-only

`~/.claude/projects/<...>/memory/MEMORY.md` is Claude Code's auto-managed personal-preferences file. The agent memory system **READS** it during context assembly but **NEVER WRITES** to it.

If a lesson in `lessons.jsonl` graduates to "this should be in MEMORY.md," the system surfaces a one-line suggestion at the next milestone gate; the user manually copies it. Locked per plan 19 § C.6 Q6.

Rationale: programmatic writes to `MEMORY.md` race against Claude Code's own management of the file (it reformats on its own schedule); per-user-per-machine writes also break the multi-contributor story.

### 5.2 `CLAUDE.md` + `AGENTS.md` — read-only

Same posture as `MEMORY.md`. The memory system reads but doesn't write. `CLAUDE.md` / `AGENTS.md` carry project-wide invariants edited by hand through PR; the memory system layers session-derived facts on top.

### 5.3 `.claude/skills/` — extension, not replacement

The skill system is the **discovery mechanism** Claude Code ships for procedural memory. The memory system extends it for situational memory (a knowledge file per topic with rich aliases) but doesn't replace it.

If a pattern matures from "captured 5 times in `recurring-patterns.jsonl`" to "every dispatch needs to know this," the right answer is often **author a new skill** (procedural memory) rather than only adding it to `knowledge/`. Wave 3's `promote-lesson` surfaces both options.

### 5.4 Anthropic Memory tool — out of scope

The `memory_20250818` API-level tool is not exposed in Claude Code. Revisit if Anthropic ships it. Until then, the file-based approach in this doc is canonical.

### 5.5 MCP memory servers — out of scope

`mem0` cloud + `mcp-memory-keeper` self-hosted + `mcp-knowledge-graph` are all viable for semantic search but violate "self-host first, no third-party always-on" (`AGENTS.md`). Revisit if the corpus exceeds 10k entries (current corpus: ~5 + growing slowly).

---

## § 6 — How to extend

### 6.1 Add a new store

1. Extend `scripts/agent-memory.sh`:
   - Add a `record-<thing>` subcommand following the `record-decision` pattern (validate, append, atomic).
   - Add the new file path to the constants block at the top.
   - Add the store to the `list` and `query` dispatchers.
2. Add the schema to § 2 of this doc.
3. Update `.gitignore` if the store should be committed (default: gitignored).
4. Add tests to `tests/test_agent_memory.sh`.

### 6.2 Add a new lookup skill

1. Author `.claude/skills/<name>/SKILL.md` with rich trigger phrases.
2. Body documents which stores to query + which knowledge files to read.
3. Link from § 3 of this doc.

### 6.3 Mine a new pattern

`recurring-patterns.jsonl` aggregates `ERROR step=<X> kind=<Y>` from per-agent logs. To mine on a different event family:

1. Extend `cmd_mine_patterns` in `scripts/agent-memory.sh` with a new event regex.
2. Document the new pattern shape in § 2.4.

### 6.4 Promote a recurring pattern to a lesson + knowledge entry

User flow:

```bash
/learn                                              # surface promotion candidates
/memory query patterns '.occurrence_count >= 5'     # inspect
# manager invokes via Skill: manager-promote-lesson
scripts/agent-memory.sh promote-lesson <pattern_id> # threshold-gated
```

Manager surfaces consent via AskUserQuestion before invoking.

### 6.5 Add an alias to an existing knowledge entry

Wave 3 surfaces alias proposals via `scripts/agent-memory.sh mine-patterns --aliases`. To add an alias manually:

```bash
# Read the current entry, copy the body, re-write with merged aliases:
scripts/agent-memory.sh record-knowledge <slug> <body-file> \
  --aliases "<merged-alias-list>" --overwrite
```

---

## § 7 — Open follow-ups (Phase A backlog)

- **Decision supersession across runs.** The current `--supersedes` flag handles within-store supersession. Cross-store (decision → lesson → knowledge promotion chain) needs a future audit pass.
- **`MEMORY.md` suggestion surface.** The Wave 1 design has manager surface a suggestion at milestone gates; Wave 2/3 may want this on every promote-lesson event.
- **Prune subcommand.** Stores grow without bound. When `decisions.jsonl` or `discussions.jsonl` crosses ~1MB (or knowledge corpus crosses ~50 files), add a `prune` subcommand that archives `state == "superseded"` rows older than 1 year to `.claude/memory/archive/`.
- **SQLite FTS5 migration trigger.** If corpus crosses 10k entries OR grep latency exceeds 1s on a representative lookup, revisit SQLite FTS5 per plan 19 § C.1.
