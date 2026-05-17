---
description: Promote a recurring pattern (occurrence_count >= 5) to a lesson + knowledge stub. Consent-gated wrapper around `scripts/agent-memory.sh promote-lesson <pattern_id>`. Use when /learn surfaces a promotion candidate, when manager has user approval to promote a specific pattern, when the user says "promote this pattern" / "make this a lesson" / "this should be a knowledge entry". Triggers on phrases like "promote lesson", "promote pattern", "lesson promotion", "make this a lesson", "knowledge stub from pattern", "threshold 5".
allowed-tools: Read, Bash(scripts/agent-memory.sh:*), Bash(jq:*), AskUserQuestion
---

# manager-promote-lesson

Wave 3 promotion wrapper. Patterns crossing `occurrence_count >= 5` are candidates for `lessons.jsonl` + a `knowledge/<auto-slug>.md` stub. This skill is the consent-gated path manager invokes from inside `/learn` Section A / E.

## When to invoke

- `/learn` surfaces a "promote pattern X (count=N >= 5)?" candidate AND the user replied "Yes" to the AskUserQuestion.
- Manager wants to manually promote a specific pattern after reviewing `.claude/memory/recurring-patterns.jsonl`.
- User types or says "promote pattern <id>" / "make this a lesson" / "this gotcha is permanent now".

## What this skill does

### Step 1 — Verify the pattern qualifies

```bash
scripts/agent-memory.sh query patterns ".pattern_id == \"<pattern_id>\""
```

Confirm:
- The pattern exists.
- `occurrence_count >= 5`.
- No existing `lessons.jsonl` row with id `lesson-<pattern_id_with_underscores_to_hyphens>`.

If `occurrence_count < 5`, halt with `error: pattern has count=<N>; threshold is 5`. No override.

### Step 2 — Auto-slug the knowledge stub

`pattern_id` has shape `<step>__<kind>` (e.g. `find-replace__pivot`). Slug derivation:

```
slug = pattern_id.split("__")[0].lower().replace(/[^a-z0-9-]/g, '-')
```

Examples:
- `find-replace__pivot` → `find-replace`
- `pytest-x-flaked__retry` → `pytest-x-flaked`
- `gh-pr-create__halt` → `gh-pr-create`

If `.claude/memory/knowledge/<slug>.md` already exists, the `promote-lesson` invocation leaves it as-is (operator owns the existing file). No conflict.

### Step 3 — Surface consent

If invoked outside `/learn`'s flow (where consent was already collected), surface an AskUserQuestion:

```
AskUserQuestion: Promote pattern '<pattern_id>' (count=<N>) to lesson '<lesson_id>' + knowledge stub '<slug>.md'?
  - Yes → run the promotion
  - No → halt
  - Inspect → output the pattern's full row + last 3 example runs, then re-ask
```

### Step 4 — Run the promotion

```bash
scripts/agent-memory.sh promote-lesson <pattern_id>
```

This creates the `lessons.jsonl` row AND the `knowledge/<slug>.md` stub from the pattern's `proposed_action`. Outputs:

```
lesson: lesson-<pattern_id-with-hyphens>
promote-lesson: lesson <lesson-id> + knowledge stub <path>
```

### Step 5 — Surface the result

Print the new files to the user:

```
Promoted:
  - .claude/memory/lessons.jsonl row: <lesson_id>
  - .claude/memory/knowledge/<slug>.md (stub — operator should expand the Resolution + Related sections)
```

### Step 6 — Optional follow-up

Suggest the operator expand the auto-generated stub by editing the `## Resolution / pattern` and `## Related` sections via:

```bash
scripts/agent-memory.sh record-knowledge <slug> <body-file> \
  --aliases "<merged-list>" --confidence high --overwrite
```

This is opt-in — the stub is functional out of the box.

## Knowledge-stub template

The `promote-lesson` subcommand auto-generates this shape:

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

<proposed_action from the pattern row, or "(none captured — update via record-knowledge --overwrite)">

## Related

- pattern: <pattern_id>
- lesson: <lesson_id>
- runs: <comma-separated run-ids>
```

Operator's job after promotion: replace the auto-generated `## Context` and `## Pattern` sections with prose; merge useful `Aliases` from the user's vocabulary; bump `Confidence: medium → high` once the resolution is verified.

## Canonical references

- `scripts/agent-memory.sh promote-lesson <pattern_id>` — the underlying write.
- `.claude/commands/learn.md` § Section A + § Section E — the consent-collection surface this skill closes.
- `docs/design/AGENT_MEMORY.md § 6.4` — extension guide for promotion.
- `docs/AGENT_OPS.md § 14.6` — Wave 3 surface documentation.

## When NOT to invoke

- The pattern's `occurrence_count < 5`. Threshold is hard.
- A `knowledge/<slug>.md` already exists AND its content is non-stub (i.e. operator has already written prose). Leave operator's work alone.
- Outside a `/learn` flow AND the user hasn't explicitly named the pattern to promote.
- Compaction events.

## Forbidden during invocation

- Do NOT override the threshold-5 gate. `scripts/agent-memory.sh promote-lesson` enforces; this skill doesn't bypass.
- Do NOT auto-promote without user consent. The whole point of the wrapper is the AskUserQuestion gate (or the prior `/learn` consent).
- Do NOT bypass the auto-slug rule. The slug derivation is deterministic so promotion is idempotent across re-runs.
- Do NOT bulk-promote. One pattern per invocation. `/learn` calls this skill repeatedly with consent per pattern.
- Do NOT write directly to `lessons.jsonl` / `knowledge/`. Single-writer rule applies — the script does the writes.
