---
description: Manual retrospective. Analyze last N runs (default 10), mine recurring patterns from per-agent ERROR events, surface promotion + ROADMAP candidates as interactive AskUserQuestion gates. Reads-only the trace logs; writes go through `.claude/naavik-ops memory` (single writer; subprocess-wraps `.claude/naavik_ops/memory.py` during A.29).
argument-hint: [N]
---

N: ${ARGUMENTS:-10}

Procedure:

### 1. Pre-flight

- Read `traces/runs.log` tail $N to identify run-ids in scope.
- Read `.claude/budget-ledger.json` to compute today's spend (`/learn` dispatch is ~50k–150k tokens). Halt with one-line cap warning if projected spend would breach `daily_token_ceiling - total_today`.
- `.claude/memory/.keep` missing → halt with `error: run .claude/naavik-ops memory init first`.

### 2. Per-run analysis

Per each of last $N run-ids:

```bash
.claude/naavik-ops memory analyze-run <run-id>
```

Each run produces `.claude/memory/runs-analysis/<run-id>.md` (idempotent — overwrites). Skip per-run analysis if file already exists AND its mtime is newer than run dir's youngest log file.

### 3. Pattern mining

```bash
.claude/naavik-ops memory mine-patterns --lookback $N
```

Aggregates `ERROR step=<X> kind=<Y>` across N runs; writes/updates `recurring-patterns.jsonl`. Patterns with `occurrence_count >= 2` are recorded; threshold for promotion is 5.

### 4. Compose interactive report

Render markdown report in chat w/ these sections. Each section ends w/ AskUserQuestion gate for actionable items.

#### Section A — Failure patterns

Top 5 ERROR kinds across N runs. Group by `kind` (pivot / retry / halt / skip), show count + example run-ids. Per each pattern w/ `occurrence_count >= 5` + no knowledge entry yet:

```
AskUserQuestion: Promote pattern <pattern_id> (count=N) to lesson + knowledge stub?
  - Yes → `.claude/naavik-ops memory promote-lesson <pattern_id>` (Wave 3 path)
  - No → skip; pattern stays in recurring-patterns.jsonl
  - Defer → ask again next /learn
```

#### Section B — Drift signals

Plans whose `## Deviations from plan` count exceeded 4. Suggests architect under-research before plan authoring. Surface for awareness only — no AskUserQuestion.

#### Section C — Token-spend hotspots

Per-agent average over N runs; flag agents above their cap on N runs out of last 10. Surface for awareness only.

#### Section D — Skill activation stats

Per each `.claude/skills/<name>/SKILL.md`, count invocations across N runs (parse `manager.log` DISPATCH events + per-agent log invocation lines). Flag skills w/ 0 invocations (potentially mistargeted trigger phrases).

#### Section E — Knowledge promotion candidates

Patterns in `recurring-patterns.jsonl` w/ `occurrence_count >= 5` + no `.claude/memory/knowledge/<slug>.md` entry. AskUserQuestion per candidate (same shape as Section A).

#### Section F — ROADMAP candidates

Discussions in `.claude/memory/discussions.jsonl` without `filed_as: #N` link AND with `priority >= MEDIUM`. AskUserQuestion per candidate:

```
AskUserQuestion: File discussion <id> ("<topic>") as new ROADMAP row?
  - Yes → manager edits ROADMAP.md (BOOKKEEPING) + .claude/naavik-ops gh create-issue
  - No → record-discussion ... --filed-as skipped (explicit dismiss)
  - Defer → ask again next /learn
```

#### Section G — Alias mining (Wave 3)

```bash
.claude/naavik-ops memory mine-patterns --aliases --lookback $N
```

Surfaces MEMORY_MISS events from manager.log. AskUserQuestion per candidate: add `<phrase>` as alias on `.claude/memory/knowledge/<topic>.md`?

### 5. Apply dispositions

Per each user-accepted response, manager (single writer per its scope) invokes matching write:

- `.claude/naavik-ops memory promote-lesson <pattern_id>` for Section A/E.
- `.claude/naavik-ops memory record-discussion ... --filed-as skipped` or ROADMAP edit + `.claude/naavik-ops gh create-issue ...` for Section F.
- `.claude/naavik-ops memory record-knowledge <slug> <body-file> --aliases "<merged-list>" --overwrite` for Section G accepted aliases.

### 6. Trace bookkeeping

Append to `traces/<run-id>/manager.log` (current run, not analyzed runs):

```
[ISO-timestamp] LEARN runs_analyzed=N patterns_mined=M promoted=K filed=L aliases=P
```

### Forbidden

- Do NOT auto-promote patterns. User consent required per pattern (locked Q3 per plan 19).
- Do NOT modify `~/.claude/projects/<...>/memory/MEMORY.md` from `/learn`. That file is Claude Code's auto-managed memory.
- Do NOT bypass `.claude/naavik-ops memory`. All writes to `.claude/memory/` go through single writer (subprocess-wraps `.claude/naavik_ops/memory.py` during A.29).
- Do NOT bypass `.claude/naavik-ops gh` for ROADMAP-mirror Issue creation. Per single-writer rule.

### Canonical references

- `.claude/naavik-ops memory analyze-run | mine-patterns | promote-lesson` — write surface.
- `docs/design/AGENT_MEMORY.md § 6` — extension guide.
- `docs/AGENT_OPS.md § 14.5–14.6` — Wave 2 + Wave 3 surfaces.
- `.claude/skills/naavik-learn/SKILL.md` — skill mirror (dual-surface per AGENT_OPS § 10.2).
