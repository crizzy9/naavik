---
description: Promote a recurring pattern (occurrence_count >= 5) to a lesson + knowledge stub. Consent-gated wrapper around `.claude/naavik-ops memory promote-lesson <pattern_id>` (subprocess-wraps `.claude/naavik_ops/memory.py` during A.29). Use when /learn surfaces a promotion candidate, when manager has user approval to promote a specific pattern, when the user says "promote this pattern" / "make this a lesson" / "this should be a knowledge entry". Triggers on phrases like "promote lesson", "promote pattern", "lesson promotion", "make this a lesson", "knowledge stub from pattern", "threshold 5".
allowed-tools: Read, Bash(.claude/naavik-ops:*), Bash(jq:*), AskUserQuestion
---

# manager-promote-lesson

Wave 3 promotion wrapper. Patterns crossing `occurrence_count >= 5` are candidates for `lessons.jsonl` + `knowledge/<auto-slug>.md` stub. Consent-gated path manager invokes from `/learn` Section A / E.

## When to invoke

- `/learn` surfaces "promote pattern X (count=N >= 5)?" AND user replied "Yes".
- Manager manually promotes specific pattern after reviewing `.claude/memory/recurring-patterns.jsonl`.
- User: "promote pattern <id>" / "make this a lesson" / "this gotcha is permanent now".

## Steps

### 1 — Verify pattern qualifies

```bash
.claude/naavik-ops memory query patterns ".pattern_id == \"<pattern_id>\""
```

Confirm:
- Pattern exists.
- `occurrence_count >= 5`.
- No existing `lessons.jsonl` row with id `lesson-<pattern_id_with_underscores_to_hyphens>`.

`occurrence_count < 5` → halt: `error: pattern has count=<N>; threshold is 5`. No override.

### 2 — Auto-slug knowledge stub

`pattern_id` shape: `<step>__<kind>`. Slug derivation:

```
slug = pattern_id.split("__")[0].lower().replace(/[^a-z0-9-]/g, '-')
```

Examples:
- `find-replace__pivot` → `find-replace`
- `pytest-x-flaked__retry` → `pytest-x-flaked`
- `gh-pr-create__halt` → `gh-pr-create`

`.claude/memory/knowledge/<slug>.md` already exists → `promote-lesson` leaves it as-is (operator owns file). No conflict.

### 3 — Surface consent

Outside `/learn` flow → AskUserQuestion:

```
Promote pattern '<pattern_id>' (count=<N>) to lesson '<lesson_id>' + knowledge stub '<slug>.md'?
  - Yes → run promotion
  - No → halt
  - Inspect → output pattern full row + last 3 example runs, re-ask
```

### 4 — Run promotion

```bash
.claude/naavik-ops memory promote-lesson <pattern_id>
```

Creates `lessons.jsonl` row + `knowledge/<slug>.md` stub from `proposed_action`. Output:

```
lesson: lesson-<pattern_id-with-hyphens>
promote-lesson: lesson <lesson-id> + knowledge stub <path>
```

### 5 — Surface result

```
Promoted:
  - .claude/memory/lessons.jsonl row: <lesson_id>
  - .claude/memory/knowledge/<slug>.md (stub — operator should expand Resolution + Related)
```

### 6 — Optional follow-up

Operator expands auto-generated stub via:

```bash
.claude/naavik-ops memory record-knowledge <slug> <body-file> \
  --aliases "<merged-list>" --confidence high --overwrite
```

Opt-in — stub is functional out of box.

## Knowledge-stub template

`promote-lesson` auto-generates:

```markdown
---
Topic: <slug>
Aliases:
First captured: <YYYY-MM-DD> (run <run-id>)
Last referenced: <YYYY-MM-DD>
Supersedes: none
Confidence: medium
---


# <slug>

## Context

Promoted from recurring pattern `<pattern_id>` after <N> occurrences across runs.

## Pattern

<step> / <kind>

## Proposed action

<proposed_action from pattern row, or "(none captured — update via record-knowledge --overwrite)">

## Related

- pattern: <pattern_id>
- lesson: <lesson_id>
- runs: <comma-separated run-ids>
```

Operator job after: replace `## Context` + `## Pattern` w/ prose; merge useful `Aliases`; bump `Confidence: medium → high` once resolution verified.

## Canonical references

- `.claude/naavik-ops memory promote-lesson <pattern_id>` — underlying write.
- `.claude/commands/learn.md` § Section A + § Section E — consent-collection surface.
- `docs/design/AGENT_MEMORY.md § 6.4` — promotion extension guide.
- `docs/AGENT_OPS.md § 14.6` — Wave 3 surface documentation.

## When NOT to invoke

- `occurrence_count < 5`. Hard threshold.
- `knowledge/<slug>.md` exists AND content is non-stub (operator wrote prose). Leave alone.
- Outside `/learn` flow AND user hasn't explicitly named pattern to promote.
- Compaction events.

## Forbidden during invocation

- Do NOT override threshold-5 gate. `.claude/naavik-ops memory promote-lesson` enforces.
- Do NOT auto-promote without user consent. AskUserQuestion gate is the point.
- Do NOT bypass auto-slug rule. Deterministic slug → promotion idempotent across re-runs.
- Do NOT bulk-promote. One pattern per invocation.
- Do NOT write directly to `lessons.jsonl` / `knowledge/`. Single-writer rule.
