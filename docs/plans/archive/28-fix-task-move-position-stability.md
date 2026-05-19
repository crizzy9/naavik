---
Status: EXECUTED
Type: execution
Authored: 2026-05-19
Approved: 2026-05-19 (auto-approved by manager per user directive; all 5 open questions accepted at architect's recommended defaults)
Shipped: 2026-05-19 (PR #94 squash `70ee0d3`)
Last updated: 2026-05-19
Depends on: 26 (0.2.0.01 EXECUTED — vault deprecation cleared the Settings layer; not a strict code dep, but contextual)
Supersedes: `.claude/naavik_ops/task.py:cmd_move` pre-fix behavior (auto-renumber siblings)
Implements: ad-hoc bug-fix + principle codification + dispatcher API extension (`gh clear-priority`)
GitHub: #93 (filed 2026-05-19 at plan-approval per locked decision Q4)
Locked decisions:
  - Track D in-PR (W3 commit alongside script fix)
  - task insert symmetry deferred to follow-up (out of scope)
  - Branch: fix/0.7.0.NN-task-move-position-stability
  - File 0.7.0.NN ROADMAP row + GH issue before engineer dispatch
  - clear-effort deferred to follow-up (scope creep)
---

# 28 · Fix `task move` position-stability + add `gh clear-priority` + codify the locked principle

## Goal

Make `.claude/naavik-ops task move <src-id> <new-version>.<new-pos>` honor the user-locked **patch-version position-stability principle**: a cross-release move relocates only the source task, leaves intentional gaps in the old patch version, and does not auto-renumber siblings in either the source or destination patch. Add `gh clear-priority` to the dispatcher so operators can unset Project Priority through the single-writer entry point. Codify the principle in five canonical documents so it doesn't drift away again. Land all three in a single PR; restore the 11 GH titles that the buggy `cmd_move` corrupted in the same PR as a one-shot data fix.

## Why now

The principle is **live** (`.claude/memory/knowledge/patch-version-position-stability.md`, captured 2026-05-19 in run `2026-05-19T05-40-56_194aa5`) but the script that should enforce it actively violates it. On 2026-05-19 the user invoked `task move 0.2.0.02 0.2.1.05` to defer the CLI sunset to the security cleanup release. The move succeeded — `#21` was retitled `[0.2.1.05] Sunset CLI` — but the source-section "shift up" logic also renumbered ~10 sibling tasks in `0.2.0` (`#15` `[0.2.0.05]→[0.2.0.04]`; `#10`, `#11`, `#12`, `#13`, `#14`, `#16`, `#17`, `#18`, `#19`, `#62`, `#70` all shifted analogously). Operator confidence in `task move` is currently zero — every future invocation has to be hand-audited.

In parallel, recovering from the buggy move surfaced a second gap: `cmd_set_priority` cannot clear a Project Priority field value once it is set. The buggy renumber shifted Priority along with the position (the field follows the slot, not the task), so cleaning up the drift requires per-issue `clearProjectV2ItemFieldValue` GraphQL mutations — which today only exist as raw `gh api graphql` calls, **violating the single-writer rule** (`AGENTS.md § GitHub state — single writer rule`). A `gh clear-priority` subcommand patches that gap.

Three product moves are queued behind this fix:
- `0.2.0.02` (CLI sunset) — needs a clean home; the buggy first attempt put `#21` at `[0.2.1.05]` but corrupted siblings.
- Future Phase 2 scraper deferrals (`0.2.0.NN` → `0.2.X.NN` as the scope/security trade-off lands).
- Phase 2.5 → 0.7.0 follow-up rows (`0.7.0.NN`) that may need promotion via `task move`.

None of those can proceed safely until `cmd_move` matches the principle.

## Cross-cutting context

- **Single-writer rule.** `AGENTS.md § GitHub state — single writer rule` (lines 398-411) makes `.claude/naavik-ops gh` the sole entry to Issue/Project/Milestone state. `gh clear-priority` extends that contract; no new bypasses introduced.
- **Memory knowledge entry.** `.claude/memory/knowledge/patch-version-position-stability.md` is the locked principle source-of-truth. This plan references it by slug; doc edits cross-link back. Future agents look up `naavik-memory-lookup` topic = `patch-version-position-stability` and find both the principle and the code that enforces it.
- **ROADMAP currently restored to original IDs.** The user has already manually reverted ROADMAP rows back to `0.2.0.04`/`0.2.0.05`/etc. (canonical pre-buggy-move state). The plan does NOT re-edit ROADMAP for the move; the goal is to make the next-attempted move work correctly, then restore the GH titles to match the current (correct) ROADMAP. ROADMAP is canonical; GH titles are the stale layer.
- **`0.2.0.02` status.** The pre-buggy-move `0.2.0.02` was `#21` `[Sunset CLI]`. Buggy move renamed `#21` to `[0.2.1.05] Sunset CLI`. ROADMAP has been restored to call this task `0.2.0.02` again. Track D restores `#21` title back to `[0.2.0.02] Sunset CLI`. The user can re-attempt the move with the fixed script after this PR merges.
- **CLI sunset.** No new `naavik` subcommand. No `src/cli/` extension. No vault scopes. (`AGENTS.md § Key Conventions § CLI`.) `architect-sunset-guard` self-check at end of plan-authoring confirms.
- **No new on-disk paths.** All state stays in `.claude/github-issue-map.json` + `~/.naavik/naavik-ops.lock`.

## Option matrix — Track A semantics (the key design call)

The principle says "don't auto-renumber siblings on `move`." But there are still three discrete choices to make about what `cmd_move` actually does when the source slot is vacated and the destination slot is occupied. Lay them out:

### Decision 1 — source-section behavior

Source slot becomes empty. Options:

| Option | Sibling behavior in src patch | Pros | Cons |
|---|---|---|---|
| **A. Pure gap (recommended)** | NONE renamed; `spos` becomes empty | Matches principle verbatim; no cross-references break; trivial code change (delete the `for r in src_rows ... new_pos = r.position - 1` loop) | Source ROADMAP table has a visible gap (cosmetic only); operator can `task renumber` later if they want |
| B. Compact only on explicit flag | NONE renamed by default; `--compact-src` opt-in renumbers siblings | Preserves principle as default + lets operator opt into compaction in one step | Extra surface area; `task renumber <version>` already exists for this exact purpose; redundant |
| C. Mode flag with renumber-as-default | `--no-renumber` flag flips to gap mode | Backward-compatible with current behavior | Violates principle as default; first invocation post-merge would still corrupt siblings |

**Pick A.** Principle is explicit; gaps are intentional + acceptable; `task renumber <version>` is the dedicated tool for cosmetic compaction. Adding flags is anti-principle.

### Decision 2 — destination-section collision behavior

The destination slot may be occupied. Today `cmd_move` shifts dest siblings DOWN to make room (`r.position >= dpos → r.position + 1`). Options:

| Option | Dest behavior | Pros | Cons |
|---|---|---|---|
| **A. Reject on collision (recommended)** | If `dest_occupy != None`, raise `NaavikOpsError("dest position NN already occupied by <task-id>")`. Force operator to pick a free slot. | Matches principle: positions are stable, including in dest; operator controls the destination; deterministic | Operator has to know a free slot exists (but `task list <dest-version>` is the lookup, and `99 - len(rows)` slots usually free) |
| B. Insert-and-shift dest siblings down | Status quo behavior for dest section | Preserves "operator's intent is to land at exactly this slot" | Violates principle in dest section; same problem as src auto-renumber, just in the other direction |
| C. Append at next-free position past `dpos` | If `dpos` occupied, auto-pick `dpos+1`, `dpos+2`, ... whichever is free | Always succeeds | Operator's stated `dpos` is overridden silently; harder to reason about |
| D. Idempotent (`dpos` already holds same task → no-op; else reject) | A + idempotency layer | Re-runnable; principle-preserving | Same as A semantically |

**Pick A (with D's idempotency thrown in for free — the existing `if src_version == dest_version and spos == dpos: no-op` already covers the trivial case; we just extend the collision check to also no-op when `dest_occupy.task_id == src_id` post-conceptual-move, which is impossible cross-release).**

Rationale: principle is symmetric. If we don't auto-renumber src siblings, we don't auto-renumber dest siblings. Operator-facing error message names the occupying task so they can pick another slot.

### Decision 3 — within-section move (`src_version == dest_version`)

Today: `cmd_move` delegates to `cmd_defer` when the move is intra-section. `cmd_defer`'s logic explicitly shifts siblings (it's the "defer N by 2" operation — the shift is the whole point of defer). Options:

| Option | Within-section move | Pros | Cons |
|---|---|---|---|
| **A. Keep `defer` delegation (recommended)** | Within-section `move` = `defer --to <new-pos>`; siblings shift | `defer` is semantically a shift; principle is about CROSS-release move; intra-release defer with shifts is a different operation | Asymmetric — `move 0.2.0.02 0.2.0.05` shifts, `move 0.2.0.02 0.2.1.05` doesn't |
| B. Within-section `move` becomes pure-swap with no shifts | New target-slot-must-be-empty rule applies intra-release too | Symmetric semantics across same-release vs cross-release | Breaks `cmd_defer` callers (operators expect defer-with-shift); doubles the surface area |

**Pick A.** Defer's whole purpose is "shift this task and its successors." Reusing it for within-section moves is correct. The asymmetry is intentional: cross-release move = task migration (gaps OK); within-release defer = ordering tweak (shifts OK).

Rationale + memory ref: `cmd_defer` exists explicitly to shift siblings. The bug is **specifically** in `cmd_move`'s cross-release path which used the same shift logic by accident. The intra-release path correctly delegates to `cmd_defer` and that delegation stays.

## Proposal

Four tracks, each with code edits + test plan + risks. All four land in **one PR** on branch `chore/0.7.0.NN-fix-task-move-position-stability` (see Open question 3 for branch-name resolution).

---

### Track A — Fix `task move` cross-release semantics

**File:** `.claude/naavik_ops/task.py` § `cmd_move` (current lines 825-1012)

**Code change sketch (lines 874-924 of current file — the "CROSS-RELEASE: src section shifts UP" + "dest section shifts DOWN" loops):**

Replace the two shift loops with simple filter + reject-on-collision:

```python
# BEFORE (lines 874-899): src loop shifts UP to close gap.
# DELETE this loop entirely.
new_src_rows: list[roadmap.ReleaseRow] = []
rename_pairs_src: list[tuple[str, str]] = []
for r in src_rows:
    if r.task_id == src_id:
        continue
    if r.status == "x":
        new_src_rows.append(r)
        continue
    if r.position > spos:
        new_pos = r.position - 1
        # ... shift logic ...
    else:
        new_src_rows.append(r)

# AFTER (replacement, ~5 lines): src section preserves all siblings unchanged.
new_src_rows = [r for r in src_rows if r.task_id != src_id]
rename_pairs_src: list[tuple[str, str]] = []  # always empty in cross-release path
```

```python
# BEFORE (lines 901-923): dest loop shifts DOWN to open gap.
# REPLACE entirely.
new_dest_rows: list[roadmap.ReleaseRow] = []
rename_pairs_dest: list[tuple[str, str]] = []
for r in dest_rows:
    if r.status == "x":
        new_dest_rows.append(r)
        continue
    if r.position >= dpos:
        # ... shift logic ...
    else:
        new_dest_rows.append(r)

# AFTER: dest collision check before any mutation.
dest_occupy = next((r for r in dest_rows if r.position == dpos), None)
if dest_occupy is not None:
    raise NaavikOpsError(
        f"dest position {dpos:02d} in {dest_version} already occupied by "
        f"{dest_occupy.task_id} ({dest_occupy.title!r}). Pick a free slot — "
        f"see `naavik-ops task list {dest_version}` for occupancy."
    )
new_dest_rows = list(dest_rows)
rename_pairs_dest: list[tuple[str, str]] = []  # always empty in cross-release path
```

The existing collision check at lines 863-865 (`if dest_occupy is not None and dest_occupy.status == "x"`) is REPLACED by the broader check above — any occupancy (active or done) rejects. Frozen-done rows are still rejected (subset of the broader rule).

The downstream code (lines 925-1012) keeps working as-is, because `rename_pairs_src + rename_pairs_dest` becomes empty and the title-rename loop only emits one entry (the source task itself getting its new title `[<dest-id>] <title>`). The atomic 3-store mutation pattern stays intact; just fewer rows to mutate.

**Net diff:** `task.py` loses ~50 lines (two shift loops collapse to two list comprehensions + one collision check). Gains ~5 lines (collision error message + comment block explaining the principle).

**Comment block insertion** (above `cmd_move`, lines ~822-824):

```python
# ---------------------------------------------------------------------------
# cmd_move
#
# Cross-release semantics (post-plan-28):
#   - Source-section siblings ARE NEVER RENUMBERED on cross-release move.
#     The source slot becomes a permanent gap; operator runs
#     `naavik-ops task renumber <src-version>` separately if cosmetic
#     compaction is desired. Principle: patch-version positions are sort keys,
#     not stable identifiers — but moving a task out of a patch leaves a
#     deliberate gap that preserves referential integrity for siblings.
#     See `.claude/memory/knowledge/patch-version-position-stability.md`.
#   - Destination-section collisions REJECT with an error. Pick a free slot.
#     `task list <dest-version>` shows occupancy.
#   - Within-section moves (src_version == dest_version) still delegate to
#     `cmd_defer`. Defer's whole purpose IS shifting siblings within a patch;
#     that's a different operation from cross-release migration.
# ---------------------------------------------------------------------------
```

**Test plan** (`tests/test_naavik_ops/test_task_mutating.py` § class `TestMove`):

Existing test `TestMove.test_cross_release_move` (lines 290-308) asserts the OLD buggy behavior — that the dest sibling `0.3.0.02` shifts to `0.3.0.03`. **Rewrite** to assert the NEW correct behavior:

1. **`test_cross_release_move_leaves_src_gap`** — REWRITE of `test_cross_release_move`.
   - Setup: existing fixture (`0.2.0.01`, `0.2.0.02`, `0.2.0.05`, `0.2.0.08 [x]`; `0.3.0.01`, `0.3.0.02`).
   - Move `0.2.0.05` to `0.3.0.05` (NOT `0.3.0.02` — that's now occupied; pick free slot).
   - Assert: ROADMAP has no `0.2.0.05` row (gap left behind); `0.2.0.01`/`0.2.0.02`/`0.2.0.08` IDs unchanged; `0.3.0.05` exists with the moved title + priority.
   - Map cache: `issues["0.3.0.05"] == 15` (the old `0.2.0.05` Issue #); `"0.2.0.05" not in issues`; `redirects["0.2.0.05"] == "0.3.0.05"`.
   - Sibling check: `issues["0.3.0.01"] == 30` unchanged; `issues["0.3.0.02"] == 31` unchanged.
   - Title log: ONLY `#15` retitled `[0.3.0.05] Auth hardening`; `#30` and `#31` NOT in log.

2. **`test_cross_release_move_rejects_occupied_dest`** — NEW.
   - Move `0.2.0.05` to `0.3.0.02` (occupied by Auth gate).
   - Assert `NaavikOpsError` with substring "already occupied" + the occupying task_id.
   - No mutations applied: map cache unchanged; ROADMAP unchanged; title log empty.

3. **`test_cross_release_move_rejects_dest_done_row`** — REWRITE or expand existing collision check.
   - Move `0.2.0.05` to `0.2.0.08` cross-release equivalent (need fixture: add `[x]` row at dest `0.3.0.05`).
   - Assert NaavikOpsError; subset of the broader collision check.

4. **`test_within_section_move_still_delegates_to_defer`** — KEEP existing `test_within_section_move_delegates_to_defer` (line 310-314). Confirms intra-release semantics unchanged.

5. **`test_priority_follows_task`** — KEEP existing test (line 324-330) as-is. Confirms moved task keeps its priority.

6. **`test_cross_release_move_preserves_src_section_priorities`** — NEW.
   - Move `0.2.0.01` (HIGH) to `0.3.0.05`.
   - Assert: `0.2.0.02` (no priority in fixture; would have been promoted to HIGH under buggy renumber if it had inherited the freed slot's metadata) keeps its priority unchanged in `map.priorities`.

**Existing test we KEEP**: `test_within_section_move_delegates_to_defer`, `test_done_row_rejected` (src done — that's a separate rule, src can't be `[x]`), `test_3_level_dest_rejected`, `test_priority_follows_task`.

**Quality gates:** `uv run ruff check .`; `uv run pytest tests/test_naavik_ops/test_task_mutating.py -x`.

### Track A risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Fix breaks an unintended call site (e.g. `cmd_defer` reused the same shift helper) | LOW | MEDIUM | Grep for `for r in src_rows` / `for r in dest_rows` outside `cmd_move`; `cmd_defer` has its own loop (lines 645-687), distinct from `cmd_move`. Coverage: existing `TestDefer` tests still pass post-Track-A. |
| Operator surprised by collision error | LOW | LOW | Error message includes occupying task_id + `task list <dest-version>` pointer. Test `test_cross_release_move_rejects_occupied_dest` locks the wording. |
| Fix lands but ROADMAP `0.2.0` already has gaps from prior buggy moves | N/A — current state | LOW | ROADMAP is now restored (user reverted). Future moves leave new gaps; operator runs `task renumber 0.2.0` if cosmetic compaction wanted. |
| New collision check makes legitimate same-release moves fail (false positive) | LOW | MEDIUM | Within-section path (`src_version == dest_version`) still delegates to `cmd_defer` which has its own logic; the collision check ONLY fires on cross-release `dest_occupy is not None`. Verified by `test_within_section_move_still_delegates_to_defer`. |

---

### Track B — Add `gh clear-priority <item-id>` subcommand

**File:** `.claude/naavik_ops/gh.py`

**Insertion points:**

1. **Module docstring (lines 30-34, the subcommand surface block):** add line after the `set-priority` entry:

```
  set-priority <item-id> <pri>           Project Priority field write.
  clear-priority <item-id>               Project Priority field clear (no value).
  set-effort <item-id> <effort>          Project Effort field write.
```

2. **GraphQL query template (after `_QUERY_SET_SELECT` at line 175):**

```python
_QUERY_CLEAR_FIELD = """
mutation($p:ID!, $i:ID!, $f:ID!) {
  clearProjectV2ItemFieldValue(input:{
    projectId:$p, itemId:$i, fieldId:$f
  }) { projectV2Item { id } }
}
""".strip()


def _clear_field(project_id: str, item_id: str, field_id: str) -> None:
    """Clear a Project v2 single-select field's value on `item_id`.

    GraphQL `clearProjectV2ItemFieldValue` mutation. Sole writer for the
    Priority/Effort field-clear path (the `set-*` family only writes options).
    """
    if not field_id:
        return  # field not configured — be tolerant like _set_select
    gh_graphql(
        _QUERY_CLEAR_FIELD,
        variables={"p": project_id, "i": item_id, "f": field_id},
    )
```

3. **`cmd_clear_priority` subcommand (after `cmd_set_priority` at line 481):**

```python
def cmd_clear_priority(rest: Sequence[str]) -> int:
    """clear-priority <item-id> — unset Project Priority field."""
    if len(rest) < 1:
        sys.stderr.write("usage: naavik-ops gh clear-priority <item-id>\n")
        return 2
    cache = _load_cache()
    field_id = cache.get("priority_field_id") or ""
    if not field_id:
        sys.stderr.write("warning: Priority field not configured — skipping\n")
        return 0
    item_id = rest[0]
    _clear_field(cache["project_id"], item_id, field_id)
    sys.stdout.write("priority cleared\n")
    return 0


# Programmatic helper (used by task.py if it ever needs to clear).
def clear_priority(item_id: str) -> None:
    cmd_clear_priority([item_id])
```

4. **Dispatcher registration (`.claude/naavik_ops/cli.py` — verify GROUPS table includes `gh` and that `gh.cmd_clear_priority` is auto-discovered):**

Per the dispatcher pattern in `docs/design/PHASE_NUMBERING.md § 10`, each `cmd_<name>` function in a group module is dispatched by argv → function name (`clear-priority` → `cmd_clear_priority`). Confirm `cli.py`'s dispatch is name-based (not registry-based); if registry-based, add the entry. **Architect call:** `cli.py` is name-based per the existing pattern (no registry edit needed); engineer to verify in implementation.

5. **`update-config` skill / `.claude/settings.json`:** no permission change needed — the dispatcher entry point is already permitted.

**Test plan** (`tests/test_naavik_ops/test_gh.py`):

Add a new `class TestClearPriority` (following the existing pattern of `class TestSetPriority` if it exists; otherwise inline with `TestMapCache`-style fixtures):

1. **`test_clear_priority_calls_graphql_with_clearProjectV2`** — sandbox fixture; replace `gh_graphql` with a recorder; call `cmd_clear_priority(["PVT_item_42"])`; assert one GraphQL call with `clearProjectV2ItemFieldValue` in the query string + matching `variables`.

2. **`test_clear_priority_no_op_when_field_not_configured`** — set `cache["priority_field_id"] = ""`; assert warning to stderr + exit 0 + no GraphQL call.

3. **`test_clear_priority_missing_args_returns_2`** — call with empty argv; assert exit 2 + usage on stderr.

4. **`test_clear_priority_programmatic_helper`** — call `gh.clear_priority("PVT_item_42")` (the module-level helper); assert same behavior as the CLI variant.

**Quality gates:** `uv run ruff check .`; `uv run pytest tests/test_naavik_ops/test_gh.py -x`.

### Track B risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `clearProjectV2ItemFieldValue` mutation signature wrong (GraphQL API drift) | LOW | LOW | GitHub Projects v2 GraphQL docs explicit on this mutation; same input shape as `updateProjectV2ItemFieldValue` minus `value`. Test mocks the GraphQL call, so the assertion is on the query+variables shape, not live API. Manual QA in Track D verifies on real issues. |
| Operator confuses `clear-priority` with `set-priority` semantics | LOW | LOW | Stdout messages differ verbatim ("priority cleared" vs "priority set: HIGH"). Help text in dispatcher distinguishes. |
| `cli.py` is registry-based (not name-based) and needs a registration edit | LOW | LOW | Engineer verifies during implementation; if registry-based, one-line entry add. Plan footnote: "if registry-based, expand the registration table." |

---

### Track C — Codify the principle in instructions

Five doc edits, all CONTRACT_CHANGE (PR-required per `docs/PLAYBOOK.md § H`). Each is small + targeted.

#### C.1 — `AGENTS.md § GitHub state — single writer rule` extension

**Insertion point:** after the existing bullet list (lines 404-411), add a new sub-section.

**Proposed copy (insert after line 411, before the section divider at line 413):**

```markdown

**Patch-version positions are not stable identifiers.** Captured 2026-05-19 as `.claude/memory/knowledge/patch-version-position-stability.md`. In the 4-level semver task-ID schema (`MAJOR.MINOR.PATCH[.POSITION]`), the **release-version (3-level)** is the canonical tree source. The **position (4th level)** is a sort key, not a primary key. Operational consequences:

- **Patch tasks are unprioritized + unordered by default.** HIGH/MED/LOW markers + position ASC are sort hints, not invariants.
- **Gaps in position numbering are intentional + acceptable.** Moving `0.2.0.02` out (e.g. via `naavik-ops task move 0.2.0.02 0.7.0.05`) leaves position `02` empty in `0.2.0`; remaining tasks (`0.2.0.03`, `0.2.0.04`, ...) do NOT shift to fill the gap. `naavik-ops task move` enforces this — source-section siblings are never renumbered on cross-release move.
- **Destination-section collisions reject.** Operator picks a free slot; `naavik-ops task list <dest-version>` shows occupancy.
- **Cosmetic compaction is opt-in.** Run `naavik-ops task renumber <version>` to compact gaps when you actually want renumbering — never as an automatic side-effect of `move`.
- **Within-section `defer` is different.** `naavik-ops task defer` shifts siblings by design (it's the "shove this task back N slots" operation). The non-shift rule applies to **cross-release** `move`, not intra-release `defer`.
```

#### C.2 — `docs/design/PHASE_NUMBERING.md § 1` extension

**Insertion point:** after the existing "Three orthogonal signals" sub-section (around line 29-33). Add a new sub-section titled **Position stability**.

**Proposed copy (insert after the "Three orthogonal signals" enumerated list, before the `### Regex` heading at line 36):**

```markdown

### Position stability (codified 2026-05-19 via plan 28)

Position is a **forward-fill ID slot**, not a sort invariant. Once a task is assigned position `NN` within a release, that ID is stable for the task's lifetime — including after the task moves to a different release or transitions to `[x]`. Operational consequences:

- **`naavik-ops task move <src> <dest-version>.<dest-pos>` does NOT auto-renumber siblings** in either the source patch (gap left behind) or the destination patch (collision rejects). Source-section gaps are intentional.
- **`naavik-ops task renumber <version>` is the explicit compaction tool.** Operator opts in when cosmetic alignment is wanted. Never a side-effect.
- **`naavik-ops task defer <task-id>` is the intra-release shift tool.** Defer's purpose IS shifting siblings; that's a separate semantic from cross-release migration.
- **Cross-release moves preserve referential integrity for siblings.** Archived plans that cite `0.2.0.05` continue to resolve to the same task even after another sibling moves out of the patch.

See `.claude/memory/knowledge/patch-version-position-stability.md` for the principle origin + recovery procedure if a buggy script ever renumbers siblings against the rule.
```

#### C.3 — `docs/PLAYBOOK.md § Hard rules` extension

**Insertion point:** after rule 11 (line 280), add a new rule.

**Proposed copy:**

```markdown
12. **Never auto-renumber sibling positions on `task move`.** Patch-version positions are sort keys, not primary keys (`AGENTS.md § GitHub state — single writer rule` § "Patch-version positions are not stable identifiers"). Gaps in `0.2.0.NN` after a `move` are intentional. Operator runs `naavik-ops task renumber <version>` explicitly when cosmetic compaction is wanted. See `.claude/memory/knowledge/patch-version-position-stability.md`.
```

#### C.4 — `.claude/agents/manager.md § GitHub state — single writer rule` callout

**Insertion point:** end of the existing "Specifically:" bullet list (after the "Discover duplicate ... close higher-numbered dupe" paragraph at line 31), add a one-line callout.

**Proposed copy (new paragraph after line 31):**

```markdown
**Patch-version position-stability invariant.** When the operator (or you) invokes `.claude/naavik-ops task move <src> <dest>`, source-section siblings are NOT renumbered — the source slot becomes a permanent gap by design. Cross-references to the unmoved siblings stay valid. If you find yourself thinking "let me compact the gap," stop — that's `task renumber <version>`, a separate operator-driven operation. See `.claude/memory/knowledge/patch-version-position-stability.md`.
```

#### C.5 — `.claude/skills/manager-pick-next/SKILL.md` note

**Insertion point:** at the end of the SKILL.md body, before any closing sections, add a "Notes" sub-section if one doesn't exist; otherwise append a bullet.

**Proposed copy (architect to read existing structure during implementation — if SKILL.md already has a "Notes" or "Caveats" section, append; otherwise add new "## Notes" section near the bottom):**

```markdown
## Notes

- **Gap-preservation expected.** `naavik-ops task next-unblocked <version>` iterates tasks in `priority DESC → position ASC` order; gaps in position numbering are normal (a task moved out of the patch leaves a gap). Skip the missing slot; don't surface it as a drift warning.
```

### Track C risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Doc edits drift apart over time | MEDIUM | LOW | All five reference the same `.claude/memory/knowledge/patch-version-position-stability.md` slug; future agents lookup the knowledge entry which is single-sourced. |
| New AGENTS.md sub-section breaks anchor links from other docs | LOW | LOW | New sub-section header is appended inside the existing "GitHub state — single writer rule" anchor; existing `AGENTS.md § GitHub state — single writer rule` links continue to resolve. |
| Codification doesn't prevent the next bug because the script is the ground truth | MEDIUM | MEDIUM | Track A makes the script enforce the principle; Track C makes the principle discoverable by future agents reading the prompt files. The two together are belt + suspenders. |

---

### Track D — One-shot restore of 11 GH titles + Project board state verification

**This is the data fix that runs ONCE after Tracks A/B/C land.** It is NOT a script; engineer runs the commands by hand on the merged branch as part of the W3 commit (or post-merge MILESTONE_GATE bookkeeping — architect's recommendation is in-PR W3 so the PR proves the fix works end-to-end; see Open question 1).

**Pre-flight verification (engineer reads from current state before mutating anything):**

```bash
# Confirm current GH title for each issue. Map each to ROADMAP's current (canonical) ID.
gh issue view 15 --json number,title -t "#{{.number}} {{.title}}"
gh issue view 10 --json number,title
gh issue view 11 --json number,title
gh issue view 12 --json number,title
gh issue view 13 --json number,title
gh issue view 14 --json number,title
gh issue view 16 --json number,title
gh issue view 17 --json number,title
gh issue view 18 --json number,title
gh issue view 19 --json number,title
gh issue view 62 --json number,title
gh issue view 70 --json number,title
```

**Cross-reference each title against ROADMAP's restored canonical ID.** The architect's expectation (from user context + memory entry): each of these 11 was shifted DOWN one position by the buggy `cmd_move`, so each title's bracket prefix is one slot too low. Engineer confirms the exact mapping during W3.

**Restoration (one command per issue):**

```bash
.claude/naavik-ops gh update-issue-title 15 "[0.2.0.05] <original-title>"
.claude/naavik-ops gh update-issue-title 10 "[0.2.0.??] <original-title>"
# ... 9 more commands ...
```

(Architect can't pre-fill the exact `0.2.0.??` for each because the mapping depends on what the operator sees in ROADMAP at restore time. The engineer reads ROADMAP, matches title-text → canonical ID, and emits the commands. Plan does NOT pre-bake the commands; W3 dispatch passes the issue list + ROADMAP snapshot to engineer.)

**Post-restore Project board verification (per-issue):**

For each of the 11, plus `#21` (the actually-moved task that still has the cross-release title `[0.2.1.05] Sunset CLI` — pending the user's re-attempted move post-merge):

```bash
# Resolve issue → Project item-id.
.claude/naavik-ops gh item-id <issue-num>

# Read Priority field current value.
.claude/naavik-ops gh milestone-status 0.2.0  # JSON dump per status

# If Priority is wrong (e.g. "MEDIUM" but ROADMAP says HIGH):
.claude/naavik-ops gh set-priority <item-id> HIGH

# If Priority should be unset (which is the common case for patch tasks):
.claude/naavik-ops gh clear-priority <item-id>   # NEW from Track B
```

The Priority field drift was the second-order corruption: when `cmd_move` renumbered siblings, the Project board's Priority field stayed at the OLD slot (priority follows slot, not task). Track B's `clear-priority` is what makes the fix runnable through the single-writer entry point instead of raw `gh api graphql`.

**Verification gate (final command):**

```bash
.claude/naavik-ops task check                   # ROADMAP / map cache / pyproject / nix drift lint
.claude/naavik-ops task list 0.2.0              # confirm all 11 task IDs match ROADMAP
.claude/naavik-ops gh sync                      # confirm 0 drift between ROADMAP and Project board
```

`task check` exits 0 + `task list 0.2.0` matches ROADMAP + `gh sync` reports 0 diffs = Track D done.

**Special case: `#21` (`[0.2.1.05] Sunset CLI`).** This issue is currently titled with the cross-release move's destination ID, but the move itself was botched (siblings corrupted). After the user reverts ROADMAP, the user's intent (deferring CLI sunset to `0.2.1`) is still live — they'll re-attempt the move post-merge using the FIXED script. So Track D does **not** restore `#21` to `[0.2.0.02] Sunset CLI`. Engineer leaves `#21` alone; the user re-runs `task move 0.2.0.02 0.2.1.05` after the PR merges and it works correctly the second time.

**Architect call on `#21`:** if ROADMAP currently shows `0.2.0.02` (because the user reverted ROADMAP after the buggy move), then `#21`'s title `[0.2.1.05] ...` is a drift case. Two sub-options:

| Sub-option | Behavior | Recommend |
|---|---|---|
| D-1. Restore `#21` to `[0.2.0.02] Sunset CLI` in W3; user re-runs `task move` post-merge against the fixed script | Cleanest pre-state for the post-merge move | **Yes** — restores all 12 (11 + #21) to canonical pre-buggy state |
| D-2. Leave `#21` at `[0.2.1.05]` + treat it as the destination of the (botched) move; ROADMAP edit instead of GH title edit | Avoids one extra restoration command | Worse: ROADMAP is canonical, GH title should match ROADMAP; D-1 enforces the invariant |

**Pick D-1.** Restore all 12; let the user re-attempt the move post-merge as the first real test of the fixed script.

### Track D risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Manual title-restoration introduces typos | MEDIUM | LOW | Engineer copies titles from ROADMAP (authoritative); paired-eyes review via the PR diff (`update-issue-title` runs leave a trace in the PR description). |
| Restore overwrites a manually-corrected title | LOW | MEDIUM | Pre-flight `gh issue view` step records current state; engineer compares against ROADMAP before restoring. Any GH-only correction the user made would also be reflected in ROADMAP if the user followed convention. |
| `#21` re-restoration races with the user re-running `task move` mid-PR | LOW | LOW | Restoration runs in W3 commit; the user runs `task move` post-merge. Sequencing is explicit. |
| Map cache drift after restoration | LOW | LOW | `update-issue-title` writes the map atomically. Verification gate (`task check` + `gh sync`) catches drift. |
| Priority field cleanup leaves some items at MEDIUM that should be unset | MEDIUM | LOW | Most patch tasks should have `priority` unset (per principle); engineer audits each of the 11 + #21 and uses `clear-priority` (Track B) where ROADMAP shows no priority. |

---

## Build sequence

5-commit branch `<branch>/0.7.0.NN-fix-task-move-position-stability` (see Open question 3 for branch prefix), each commit a coherent unit:

1. **W0 (commit 1):** `fix(naavik-ops): task move — remove sibling auto-renumber on cross-release move`
   - File: `.claude/naavik_ops/task.py` (Track A code change)
   - File: `tests/test_naavik_ops/test_task_mutating.py` (Track A test rewrite + 3 new tests)
   - Quality gates: `uv run ruff check .`, `uv run pytest tests/test_naavik_ops/ -x`.

2. **W1 (commit 2):** `feat(naavik-ops): gh clear-priority subcommand for unsetting Project Priority`
   - File: `.claude/naavik_ops/gh.py` (Track B code change)
   - File: `tests/test_naavik_ops/test_gh.py` (Track B test additions)
   - Verify dispatcher routing: `cli.py` discovers `cmd_clear_priority` automatically (no edit needed) OR add one-line registry entry.
   - Quality gates: `uv run ruff check .`, `uv run pytest tests/test_naavik_ops/test_gh.py -x`.

3. **W2 (commit 3):** `docs(playbook,agents): codify patch-version position-stability principle`
   - Files: `AGENTS.md` (C.1), `docs/design/PHASE_NUMBERING.md` (C.2), `docs/PLAYBOOK.md` (C.3), `.claude/agents/manager.md` (C.4), `.claude/skills/manager-pick-next/SKILL.md` (C.5).
   - No code; no tests; just documentation edits.

4. **W3 (commit 4):** `fix(github): restore 11 issue titles + verify Project board state post-buggy-move`
   - Engineer runs the 12 (11 + `#21`) `update-issue-title` commands.
   - Engineer audits Project board Priority field for each issue + uses `clear-priority` where ROADMAP says unset.
   - Engineer runs `task check` + `task list 0.2.0` + `gh sync` and pastes outputs into commit message body for audit.
   - **No file diff in this commit other than `.claude/github-issue-map.json` updates from `update-issue-title` map-cache writes.**
   - Quality gates: post-restoration `task check` exits 0.

5. **W4 (commit 5, optional / fold into W3):** `docs(plan): plan 28 - fix task move position stability`
   - File: `docs/plans/28-fix-task-move-position-stability.md` (this plan; staged into the PR).
   - File: `docs/prompts/28-fix-task-move-position-stability.md` (engineer kickoff prompt; authored after PLAN_GATE approval).

6. **Open PR via `gh pr create`** using `.github/pull_request_template.md`.

7. **PR_REVIEW_GATE** — hacker + architect review in parallel (per `docs/PLAYBOOK.md § F`/§ H — this is a CONTRACT_CHANGE PR touching `.claude/naavik_ops/**`, `.claude/agents/**`, `.claude/skills/**`, `AGENTS.md`, `docs/design/**`, `docs/PLAYBOOK.md`).

8. **Manual QA gate post-merge:**
   - User re-runs `task move 0.2.0.02 0.2.1.05` against the fixed script.
   - Assert: only `#21` title changes (to `[0.2.1.05] Sunset CLI`); no sibling shifts; ROADMAP `0.2.0` retains all current rows minus `0.2.0.02` (gap); ROADMAP `0.2.1` gains the row at position 05.
   - This is the smoke test that proves Track A's fix works end-to-end.

## Risk + mitigation (cross-track)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Migration of existing tests for `task move` introduces regressions in adjacent tests (`TestDefer`, `TestInsert`) | MEDIUM | MEDIUM | Existing tests are scoped per-class; Track A only rewrites `TestMove` tests + adds 3 new. `TestDefer` + `TestInsert` untouched. Run full suite at end of W0. |
| Future architect doesn't read the new memory knowledge entry + reintroduces shift logic in a new mutating subcommand | LOW | MEDIUM | Track C.1 + C.2 + C.3 are five doc surfaces (manager prompt + design doc + AGENTS.md + PLAYBOOK + manager-pick-next skill) that all cross-link to the memory entry. `naavik-memory-lookup` skill surfaces it on cold-start lookup. |
| The 5-doc codification is forgotten in a later refactor (e.g. when AGENTS.md restructures) | MEDIUM | LOW | All five reference the SAME memory knowledge slug — the entry is the single source of truth. Future refactors that drop a reference still leave the knowledge entry; future agents can still find it via `/memory query`. |
| Engineer can't disambiguate which Issue # got which original ID during Track D | MEDIUM | LOW | Pre-flight `gh issue view` outputs in W3 commit message; ROADMAP cross-reference by title-text (titles are unique within `0.2.0`). |
| `cli.py` is registry-based (not name-based) and Track B's `cmd_clear_priority` doesn't auto-register | LOW | LOW | Engineer verifies in W1; if registry-based, one-line table edit. Plan footnotes the verification step. |
| Track B GraphQL `clearProjectV2ItemFieldValue` doesn't behave as expected on live Project | LOW | LOW | Test mocks the mutation; Track D's manual QA exercises the live path. If a live-API surprise emerges, file as a Track D deviation. |
| Plan number 28 collides with a parallel in-flight plan (`27` is missing — possibly reserved) | LOW | LOW | Architect verifies via `ls docs/plans/` at plan-authoring time + Open question 4. |
| User re-attempts `task move` post-merge and the source patch already has gaps from intermediate edits | LOW | LOW | `task move` doesn't care about source-patch gaps; the move command operates only on the source task + destination slot. Pre-existing gaps stay as-is. |
| Doc edit (Track C) drops an anchor that an external doc/skill linked to | LOW | LOW | All Track C edits APPEND to existing sections; no anchor renames. The new sub-sections live INSIDE existing anchors (e.g. `AGENTS.md § GitHub state — single writer rule`). |

## Open questions

- [ ] **Q1. Track D scope** — restore all 11 (or 12 incl. `#21`) GH titles in this PR? Or accept current drift as "ROADMAP is canonical; GH titles are stale + will sync on next `/groom`"? **Architect recommendation:** restore in-PR (W3 commit) so the PR proves the fix end-to-end. Alternative: split into a follow-up bookkeeping commit on `main` post-merge.
- [ ] **Q2. `task insert` symmetry** — should `cmd_insert` also stop shifting siblings (gap-only, reject-on-occupied)? Today `cmd_insert` actively shifts siblings DOWN to open a slot (lines 442-580 in `task.py`). Per the principle, **inserts should probably also reject on collision** rather than shift. Same goes for `cmd_defer` cross-position cases. **Architect recommendation:** OUT OF SCOPE for plan 28 — `defer` is explicitly "shift" by name, and `insert` semantically wants to "make room"; the principle is specifically about cross-release `move`. File a follow-up `0.7.0.NN` row to debate `insert` semantics separately. Confirm with user.
- [ ] **Q3. Branch naming** — `chore/0.7.0.NN-fix-task-move-position-stability` (chore prefix, position-stability work) or `fix/0.7.0.NN-task-move-position-stability` (fix prefix, since the script is broken)? **Architect recommendation:** `fix/...` because the script genuinely is buggy. Per `docs/PLAYBOOK.md § H`, both `chore/` and `fix/` are valid for CONTRACT_CHANGE PRs; the prefix is editorial. The `feat/` prefix is forbidden (no new product code).
- [ ] **Q4. ROADMAP row needed before plan-archive?** — should architect file a new `0.7.0.NN` row in ROADMAP before plan execution? Two options:
  - **Q4a. File `0.7.0.NN` row + open Issue via `.claude/naavik-ops gh create-issue 0.7.0.NN "Fix task move position stability + clear-priority + codify principle" --priority MEDIUM --milestone 0.7.0 --parent <epic-0.7.0-issue>` at plan-approval time.** Ledger row gives the work a tracked home in the agent-system follow-up release.
  - **Q4b. Treat as inline `Phase A` mechanical follow-up; no ROADMAP row; plan archive references plan 28 directly.** Simpler; no ROADMAP edit.
  - **Architect recommendation:** Q4a — this work IS an agent-system follow-up that deserves a tracked row + Issue. The `0.7.0` epic is open (`#89`). Adding `0.7.0.12` (or whichever next-free position) makes the work mirror-trackable on the Project board.
- [ ] **Q5. `clear-priority` for Effort field too?** — same gap exists for `cmd_set_effort` (no way to clear). **Architect recommendation:** SCOPE CREEP, defer. File `0.7.0.NN` follow-up if anyone hits the Effort-clear use case. Plan 28 stays focused.

## Approval checklist

The user ticks these before the architect calls `.claude/naavik-ops gh create-issue` and engineer dispatch begins:

- [ ] Plan structure approved (4 tracks + build sequence).
- [ ] Track A semantics approved (Decision 1.A pure gap + Decision 2.A reject-on-collision + Decision 3.A keep `defer` delegation for within-section moves).
- [ ] Track B `gh clear-priority` API surface approved (no `--field` flag; priority-only this PR; Effort/Status deferred to follow-up if needed).
- [ ] Track C five doc edits approved (AGENTS.md + PHASE_NUMBERING.md + PLAYBOOK.md + manager.md + manager-pick-next/SKILL.md, each with the proposed copy as a starting point — engineer can wordsmith).
- [ ] Track D scope decision (Q1).
- [ ] `task insert` symmetry decision (Q2).
- [ ] Branch naming decision (Q3).
- [ ] ROADMAP row decision (Q4 — Q4a yes/no).
- [ ] `clear-effort` scope decision (Q5).
- [ ] Architect to file Issue via `.claude/naavik-ops gh create-issue <task-id> "<title>" --priority <P> --milestone "0.7.0" --parent <epic-#>` post-approval. Update plan frontmatter `GitHub: #<N>`.

## Deviations from plan

Promoted from `traces/2026-05-19T05-40-56_194aa5/engineer-deviations.log` at archive time per `AGENTS.md § Workflow step 7`. 3 entries, all process / mechanical:

1. **W3 commit is `--allow-empty` (audit anchor only; no in-repo diff).**
   - **Why:** `.claude/github-issue-map.json` is gitignored per-fork. The W3 `update-issue-title` writes mutate GH state + the map cache atomically, but neither produces a committable file change.
   - **Impact:** W3 stays as an audit-trail commit with a detailed message body listing all 12 restorations. PR reviewers verify the restoration via live `gh issue view` queries (architect did exactly this in the review).

2. **`#21` stays at `[0.2.1.05]` — not restored to `[0.2.0.02]` as plan body's Track D-1 suggested.**
   - **Why:** Manager's engineer dispatch prompt explicitly overrode plan body's Track D-1 commands list: "DO NOT restore #21; leave it at `[0.2.1.05]`. The plan's Track D-1 spec mentions 'restoring #21 to [0.2.0.02]' but that contradicts the user's intent (CLI sunset belongs in 0.2.1)."
   - **Impact:** User-intended move of CLI sunset to `0.2.1.05` is preserved. ROADMAP row `0.7.0.13` description reflects this. Plan body's Track D-1 text wasn't updated; this is a doc-vs-impl drift that future plan authors should flag.

3. **External branch-switching watchdog required defensive re-apply of W2 doc edits.**
   - **Why:** A parallel session (the plan 27 W2-W5 engineer continuation) checked out `feat/0.2.0.05-job-models` mid-W2-edit, reverting 4 of 5 W2 doc files in the working tree once during the first attempt.
   - **Impact:** W2 required one re-apply after branch switch. W1 required restoring staging with explicit pathspec after 10 stray files from the parallel branch got staged. No data loss. Engineer's defenses for future cross-branch concurrent work: (a) push branch upstream after each commit; (b) `git rev-parse --abbrev-ref HEAD` before each commit; (c) explicit `git commit -- <pathspec>`. **Lesson candidate** for `.claude/memory/recurring-patterns/`: cross-branch session interference in same workspace.

### Operational surface added

- **`naavik-ops gh clear-priority <item-id>`** — new subcommand. Unsets Project Priority field via `clearProjectV2ItemFieldValue` GraphQL mutation. Single-writer rule preserved (closes the prior gap where operators had to bypass dispatcher with raw `gh api graphql`).
- **5 docs codify patch-position-stability principle** with cross-links to `.claude/memory/knowledge/patch-version-position-stability.md` (knowledge entry recorded 2026-05-19 in this run).
- **12 GH issue titles restored** to canonical ROADMAP IDs: `#62→[0.2.0.03]`, `#70→[0.2.0.04]`, `#15→[0.2.0.05]`, `#10→[0.2.0.06]` through `#19→[0.2.0.14]` in sequence. `#21` correctly at `[0.2.1.05]` (intentional CLI sunset move).

### Downstream impact

- Future `task move <task-id> <new-version>.<new-pos>` calls will leave source gaps; reject on dest collision with operator-friendly error. No more buggy renumbers.
- `task insert` symmetry deferred to follow-up per locked decision Q2.
- `clear-effort` symmetry deferred to follow-up per locked decision Q5.

### Hacker findings (deferred)

Both reviewers cleared at APPROVE. Hacker findings:
- **[INFO]** `task.py:993-1005` — `gh._gh "issue edit --milestone"` runs outside the flock after `_apply_atomic_3store` returns. `dest_version` is injection-safe (derived from `semver.format(int,int,int)`). Existing try/except tolerates failure. Not exploitable in single-operator tooling.
- **[INFO]** `update_issue_title` (already-shipped helper) uses list-form subprocess — safe against title-content injection. Observation only.

Architect findings:
- **[INFO]** `_QUERY_CLEAR_SELECT` / `_clear_select()` naming refinement (plan said `_QUERY_CLEAR_FIELD` / `_clear_field()`; shipped names track sibling `_set_select()` convention — arguably better; non-blocking).

