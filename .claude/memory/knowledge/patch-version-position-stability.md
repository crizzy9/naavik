---
Topic: patch-version-position-stability
Aliases: patch-version-task-numbering
First captured: 2026-05-19 (run 2026-05-19T05-40-56_194aa5)
Last referenced: 2026-05-19
Supersedes: none
Confidence: high
---

---
slug: patch-version-position-stability
aliases:
  - patch-positions-not-stable
  - task-move-renumber-bug
  - patch-version-task-numbering
confidence: HIGH
authored: 2026-05-19
source_run: 2026-05-19T05-40-56_194aa5
---

# Patch-version task positions are not stable identifiers

## Principle (user-locked 2026-05-19)

In the post-A.29 4-level semver task-ID schema (`MAJOR.MINOR.PATCH[.POSITION]`):

- **Release-version (3-level) is the canonical tree source.** E.g. `0.2.0` is the meaningful identifier.
- **Position (4th level) is NOT a stable identifier within a patch version.** It is a sort key, not a primary key.
- **Patch tasks are unprioritized + unordered by default.** The HIGH/MED/LOW markers + position ASC are only sort hints, not invariants.
- **Gaps in position numbering are intentional + acceptable.** Moving `0.2.0.02` out of the patch (e.g. to `0.2.1.05`) leaves `0.2.0.02` empty; the remaining tasks (`0.2.0.03`, `0.2.0.04`, ...) do NOT shift to fill the gap.

## Why

The user's mental model: "we don't need to change the numbers in a patch version. That's why they are not explicitly numbered and prioritized. That allows easy removal and keeps the version number as the main tree source."

Renumbering siblings creates churn:
- Cross-references break (plans cite task IDs; renumbering invalidates them silently).
- Issue map cache (`.claude/github-issue-map.json`) entries break association if the script doesn't atomic-update.
- Past archived plans that reference task IDs (e.g. plan 26's frontmatter `Implements: ROADMAP row 0.2.0.01`) become wrong if a later move shifts neighbors.
- Operators / agents grep ROADMAP for `0.2.0.05` expecting one specific task and find a different one.

Stable IDs trade a small cosmetic uglines (gaps) for major referential integrity.

## What this means operationally

### When `task move <task-id> <new-version>.<new-pos>` is invoked

**Correct behavior (target state):**
- Source slot in old patch version becomes EMPTY (gap).
- All other siblings in the old patch version KEEP their IDs.
- Destination slot in new patch version is reserved; if already occupied, error out (or insert before; design choice).
- GH issue title is updated for the moved task ONLY.
- ROADMAP row is moved across patch sections; old section gets a gap.

**Buggy behavior (current `task move` as of 0.1.1):**
- Source slot's siblings are auto-renumbered down to fill the gap (`0.2.0.04` → `0.2.0.03`, `0.2.0.05` → `0.2.0.04`, etc.).
- Issue titles get bulk-updated across all renumbered siblings.
- Priority field on the Project board stays at the OLD position (priority follows the slot, not the task content).
- Result: 10+ issue titles change unnecessarily; cross-references break; priority field mis-assigned.

### Recovery

If the buggy renumber has already fired:
- Restore the ROADMAP to original sibling IDs (positions before the move).
- Restore GH issue titles via `.claude/naavik-ops gh update-issue-title <num> "[<original-id>] <title>"`.
- Verify Project board Priority field matches the (now-restored) task content.

### Within a release (not patch) version

The rule still holds: positions are sort keys, not stable identifiers. But because release versions (e.g. `0.2.0`) carry semantic meaning ("this is the scrapers release"), moving a task between releases (e.g. `0.2.0` → `0.2.1`) IS a meaningful semantic event and the canonical `task move` command exists for it. The bug is only in the auto-renumber-siblings side-effect.

## Cross-references

- `AGENTS.md § GitHub state — single writer rule` — single-writer principle (post-fix should codify position stability)
- `docs/PLAYBOOK.md § Board status convention (post-A.28)` — board status conventions
- `docs/design/PHASE_NUMBERING.md` — A.29 design doc (post-fix should document position stability)
- `.claude/naavik_ops/task.py` — `task move` implementation
- Bug discovery context: PR #92 merge bookkeeping cycle 2026-05-19 (run `2026-05-19T05-40-56_194aa5`)

## Follow-up filed

- ROADMAP row `0.7.0.NN` (agent-system follow-up) — "Fix `task move` renumber semantics + add `clear-priority` to dispatcher"

## Status

**LIVE PRINCIPLE.** Apply on every `task move` / `task defer` / `task insert` call. Reject auto-renumber side-effects. Script fix pending.
