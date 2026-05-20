---
Status: DRAFT
Type: design
Authored: 2026-05-19
Last updated: 2026-05-19
Depends on: 28-fix-task-move-position-stability (EXECUTED); 20-A.28-board-restructure (EXECUTED); 24-A.29-phase-numbering-system (EXECUTED). Blocks no current work (BOOKKEEPING n8n move waits on this).
GitHub: (to file on PLAN_GATE approval)
---

# 40 · ROADMAP `## Backlog` section + parser / task / sync recognition

## Goal

Add a top-level `## Backlog (unprioritized)` section to `ROADMAP.md` for tasks that are **future-eligible but unprioritized** — work the user does not want to ship in any current release but does not want to delete either. Teach `.claude/naavik_ops/lib/roadmap.py` + `.claude/naavik_ops/task.py` + `.claude/naavik_ops/gh.py` to recognize the section as a synthetic "release-version" named `backlog`, so `task list backlog`, `task move <id> backlog.NN`, and `task move backlog.NN <release>.<pos>` work without breaking the 4-level-semver invariant. First migrant: `0.2.0.14` (n8n DataTable + Google Sheets migration) — every other n8n surface was superseded in the `0.2.0` sprint (cron in `0.2.0.10`, Discord in `0.2.0.12`, status tracking in `0.2.0.05`); the n8n CSV-import path is unprioritized but not impossible.

## Why

`0.2.0.14` does not have a coherent home today. Closing it `[x]` is wrong (the work is deferred, not done). Closing it as moot is wrong (`/sync-roadmap --apply` would still emit it under `0.2.0` if it stays in the section). Leaving it `[ ]` under `0.2.0` is wrong (it gates the release cut by appearing in `task list 0.2.0` + `task next-unblocked 0.2.0`).

The GitHub Project board already has the right primitive (post-A.28 `Status=Backlog` per `docs/AGENT_OPS.md § 6.3`). What's missing is the **ROADMAP-side mirror** — a section that the parser recognizes as "out of current cycle" without conflating it with a release. With the section in place, the bookkeeping commit that moves `0.2.0.14` to Backlog is trivial; without it, the section is a fiction and the parser flags it as drift.

Beyond `0.2.0.14`, the section is the right home for future deferrals (legacy ID `2.10` semantics — work shaped like "we want to remember this but it isn't part of any release"). The ROADMAP currently shoehorns deferrals into `### 0.7.0 — Agent-system follow-ups`, which is misleading because 0.7.0 *is* a release that will ship; Backlog is explicitly *not* a release.

ROADMAP row: this plan files `0.2.0.14` BOOKKEEPING move + adds the new section header + recognizes it in tooling. No new ROADMAP row needed beyond the section itself — the section header *is* the ledger entry.

## Proposal

Eight design decisions (D.1–D.8) below. Each carries an option matrix where alternatives exist; locked decisions inherit user-direction or the user-stated "zoom-through mode" preference.

### D.1 — Section position in ROADMAP

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| A. Top (between "Last updated" and `## Maintenance`) | Backlog visible immediately on ROADMAP scroll | Pushes the actively-shipping `0.2.0` section ~50 lines deeper | Distracts from current-release focus; reader's eye lands on deferred work first | Low | Low |
| **B. Bottom (after last release section `### 0.7.0`, before `## Agent System (mirror conventions)`)** (LOCKED) | Active releases stay at the top of the doc; Backlog is the "everything else" pile | Reader must scroll past 0.1.0–0.7.0 first | Backlog out of sight is fine — it's deferred work | Low | Low |
| C. Between `## Phases` heading and first `### 0.1.0` | Visually segregates "future-deferred" before "phase history" | Awkward narrative — Backlog before the shipped release | Conceptually wrong — Backlog ≠ pre-history | Low | Low |

**Lock: B.** Active-release proximity wins. `ROADMAP.md § 6` already serves the "look at deferred work" surface for executive scans.

### D.2 — Task ID scheme within Backlog

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. Preserve original release-version ID (e.g. `0.2.0.14`)** (LOCKED) | Zero churn to GH Issue title (`[0.2.0.14] …` stays) + zero churn to `.claude/github-issue-map.json:issues["0.2.0.14"]` cache + zero broken cross-refs in archived plans / commit messages | Same ID lives in two sections (`### 0.2.0` row absent; Backlog row present); parser must disambiguate by SECTION not by ID | None — section is the lookup key, not the ID prefix | Low | Low |
| B. Re-ID with `B.NN` / `BACKLOG.NN` prefix on move | Visually obvious "this is Backlog" | Breaks every GH cross-ref the moment a task is moved; requires title rewrite + redirect entry in map cache + ROADMAP commit-message search-replace | High — every archived plan referencing `0.2.0.14` becomes a stale forward pointer | High | High |
| C. Strip the patch portion (`0.2.0.14` → `0.2.14` / `0.2.x.14`) | Halfway re-ID | All of B's downsides, plus a new ID schema | High | High | High |

**Lock: A.** The ID is the *what*; the section is the *where*. Moving a row to Backlog changes only the where. This mirrors the GH Project board's existing semantics — same Issue # with `Status: Backlog` is unchanged from `Status: Todo`.

### D.3 — Synthetic release-version name for tooling

The parser + task subcommands consume a release-version string. Backlog is not a semver but the tooling pipeline needs a stable handle.

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. Literal `backlog` (no version coerce)** (LOCKED) | `task list backlog`, `task move <id> backlog`, `task move backlog <release>.<pos>` reads naturally | Bypasses `semver.parse` validation for that string; need explicit allowlist in callers | None — section name = command argument | Low | Low |
| B. Synthetic `0.0.0` semver | Reuses existing semver pipeline (no allowlist branch) | `0.0.0` is the pre-`0.1.0` foundation period; collision risk if we ever want pre-history audit; semantically wrong (Backlog ≠ "before everything") | Medium — collides with semver semantics | Medium | Medium |
| C. `999.999.999` (max sentinel) | Reuses semver | Reads as a real release in `next-unblocked`; sort ordering wrong (Backlog should NEVER sort into "next") | High | High | High |

**Lock: A.** Add a one-line allowlist (`BACKLOG_VERSION = "backlog"`) in `semver.py` and treat it as a degenerate case in three callers (`cmd_list`, `cmd_move`, `_list_release_tasks`). No semver.parse override; Backlog is a SECTION, not a VERSION.

### D.4 — Parser surface — how the writer half finds the Backlog section

`RE_RELEASE_HEADER = r"^###\s+(?P<version>\d+\.\d+\.\d+)\s+[—–-]\s+(?P<title>.+?)\s*$"` (line 84 of `lib/roadmap.py`) pins to 3-level semver. The Backlog header (`## Backlog (unprioritized)`) uses `##` (h2) instead of `###` (h3), AND has no version component.

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. Add `RE_BACKLOG_HEADER = r"^##\s+Backlog\b"` + branch in `parse_release_section` / `find_release_section_bounds`** (LOCKED) | One regex + one branch; preserves the release-only path for all existing callers (zero risk to 0.1.0–0.7.0 parsing) | Two header shapes in the writer; documented as "Backlog is the one special case" | Low | Low | Low |
| B. Relax `RE_RELEASE_HEADER` to also match `## Backlog` | One regex | Existing 3-level shape diluted; downstream consumers expecting `version` group break | Medium | Medium | Medium |
| C. New module `lib/backlog.py` mirroring `parse_release_section` | Separation-of-concerns purity | Triples the parser surface for ~80 LOC; two divergent codepaths to maintain | Medium | High | Medium |

**Lock: A.** Backlog *is* a special case — exactly one row in the dispatch tree. Branching at the regex match is the smallest possible delta.

### D.5 — Section markdown shape

The Backlog section uses the same task-table shape as release sections so reader + parser get the same surface. The header carries a one-line preamble + the table header + rows; no `**Goal:**` / `**Status:**` / `**Plan:**` blockquote lines (Backlog has no goal — it's a pile).

Final shape:

```markdown
## Backlog (unprioritized)

> Future-eligible tasks deferred from any current release. **Not part of any release cut.** `naavik-ops task list backlog` lists these; `naavik-ops task next-unblocked <release>` SKIPS these (per ID-section disambiguation in `task.py:_list_release_tasks`). To pull a Backlog row into a release, run `naavik-ops task move <id> <release>.<pos>` (the ID is preserved; the section move re-files it). Project board mirror: `Status=Backlog` on the corresponding GH Issue (post-A.28; see `docs/AGENT_OPS.md § 6.3`).
>
> **Section header is the ledger entry.** No `**Last updated**`, no `**Goal**`. Rows are added when moved in; removed when moved out.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.0.14 | Migrate existing n8n DataTable + Google Sheets data to PostgreSQL | [ ] | — | 2.10 | **Moved to Backlog 2026-05-19** — every other n8n surface was superseded in the `0.2.0` sprint (cron `0.2.0.10`, Discord `0.2.0.12`, status `0.2.0.05`). CSV-import path is unprioritized but not impossible; promote to a release when n8n migration becomes load-bearing again. Seed script. |
```

### D.6 — `task list backlog` semantics

`task.py:_list_release_tasks(version)` filters `.claude/github-issue-map.json:issues` by parsing each key as a 4-level semver and comparing `semver.format(major, minor, patch) == version`. For Backlog, we need an explicit per-task tag.

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. New `.claude/github-issue-map.json:backlog` array of task IDs** (LOCKED) | One-line set membership check; preserved across `gh refresh-map` (which already reads Project board state to rebuild map; will see `Status=Backlog` and write the IDs into the array); `task list backlog` filter is `task_id in set(map.get("backlog", []))` | Adds one top-level key to the map schema | Low — additive | Low | Low |
| B. Parse ROADMAP `## Backlog` section at every `task list` call | Truth-source-grounded (ROADMAP wins) | I/O on every call; couples task ops to ROADMAP path | Low | Medium | Low |
| C. Per-issue label `backlog` on GH | Hand-grained | Requires GH API for every `task list` call (rate limit); coupling beyond what the map cache solves | Medium | Medium | Medium |

**Lock: A.** Single-writer rule (`.claude/naavik-ops gh refresh-map` populates the array from Project Status=Backlog; `cmd_move` writes the array on `<src> backlog` move and removes on `backlog <dest>` move). `task list backlog` reads the array directly; `task list <release>` filters OUT any task in the array even if the task ID matches the release (this is the "section disambiguates the ID" rule).

`task next-unblocked <release>` likewise filters OUT array members. So `0.2.0.14` keeps its ID, lives in the Backlog section, lives in the `backlog` map array, and is invisible to `task list 0.2.0` + `task next-unblocked 0.2.0`.

### D.7 — `task move` argument shape

Cross-release move today: `naavik-ops task move 0.2.0.02 0.2.1.05`. Backlog needs symmetric ergonomics.

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. `task move <task-id> backlog` (no position required for Backlog dest) + `task move <task-id> <release>.<pos>` (existing shape, accepts a Backlog task-id as source)** (LOCKED) | Symmetric with existing UX; "Backlog has no positions" reflects the no-priority no-ordering semantics | Two argument shapes for `move`: with or without position; documented under `task move --help` | Low — argparse-style branching at first non-flag arg | Low | Low |
| B. `task backlog <task-id>` as a new top-level command (separate from move) | Verb purity | Two commands for one concept; `move <src> <dest>` is the canonical primitive; introducing `task backlog` invites bikeshed naming for the reverse (`task unbacklog`?) | Medium | Medium | Medium |
| C. `task move <task-id> backlog.NN` (require a synthetic position) | Reuses existing 4-level arg parser | Forces operator to pick a position with no meaning; collision logic just to keep types uniform | Medium | High | Medium |

**Lock: A.** `task move 0.2.0.14 backlog` sends to Backlog (preserves original ID). `task move 0.2.0.14 0.2.1.05` pulls from Backlog INTO `0.2.1.05` (the move command discovers Backlog membership by checking the `backlog` array — see D.6 — and treats the source as a Backlog row regardless of which section the task table originally rendered it in).

The arg-parser branches on the literal `backlog`: if `rest[1] == "backlog"`, the dest is Backlog (no position required); else the existing 4-level dest path runs. Reverse direction (Backlog → release) is the normal cross-release path; the only difference is the source-section ROADMAP edit happens on the Backlog table instead of a release table.

### D.8 — Closed-as-moot vs Backlog distinction

| Concept | ROADMAP shape | When |
|---|---|---|
| **Closed-as-moot** | `[x]` in release section, Notes column carries `**Auto-closed YYYY-MM-DD as moot — <reason>.**` Status flips to Done on Project board. | Work is now impossible / superseded / no longer required (e.g. `0.2.1.03` Argon2id upgrade auto-closed when vault deleted). |
| **Backlog** | `[ ]` in `## Backlog` section, original ID preserved, Status flips to Backlog on Project board. | Work is unprioritized but not impossible — could be promoted to any future release. |

**Lock: 0.2.0.14 goes to Backlog.** The n8n migration is unprioritized (every other n8n surface was superseded), but not impossible — the CSV-import path could become load-bearing again if a user actually has n8n state to migrate post-0.2.0.10 cron + 0.2.0.05 Job models + 0.2.0.12 notifications. Closed-as-moot would foreclose that future.

### Build sequence

1. **W0 — Plan kickoff** (architect; this file). Lock D.1–D.8 at PLAN_GATE.
2. **W1 — Semver allowlist + parser branch** (`engineer`; ~30 min).
   - `.claude/naavik_ops/lib/semver.py`: add `BACKLOG_VERSION = "backlog"` constant + `is_backlog(version: str) -> bool` helper. `parse()` raises `InvalidVersion` for `backlog` (existing behaviour); callers must check `is_backlog()` BEFORE `parse()` when accepting user input.
   - `.claude/naavik_ops/lib/roadmap.py`: add `RE_BACKLOG_HEADER = re.compile(r"^##\s+Backlog\b")`. Modify `parse_release_section(version)` + `find_release_section_bounds(version)` + `write_release_section(version, rows)`: if `version == "backlog"`, walk for `RE_BACKLOG_HEADER` instead of `RE_RELEASE_HEADER`; bounds extend until next `## ` header (top-level h2; in ROADMAP the next one is `## Agent System (mirror conventions)`).
3. **W2 — Task subcommands recognize `backlog`** (`engineer`; ~45 min).
   - `.claude/naavik_ops/task.py:_list_release_tasks(version)`: branch on `version == "backlog"`. Backlog path reads `.claude/github-issue-map.json:backlog` array; non-Backlog path additionally FILTERS OUT array members (D.6 disambiguation rule).
   - `cmd_list("backlog")`, `cmd_next_unblocked("backlog")` (returns "(no current-cycle tasks; backlog is not a cycle)" message and exits 0; no surprise).
   - `cmd_move(<id> backlog)`: arg-parse branch when `rest[1] == "backlog"`. Operations:
     a. Parse `src_id` as 4-level (existing path).
     b. Read source section: `roadmap.parse_release_section(src_version)`.
     c. Find + remove the row from source rows; rewrite source section with the gap (per `0.7.0.13` position-stability rule).
     d. Parse Backlog section: `roadmap.parse_release_section("backlog")`. APPEND the row (no position; position field stays 0 / empty in markdown).
     e. Write the Backlog section with the appended row + write the source section without it.
     f. Update map: add `src_id` to `backlog` array; preserve `issues[src_id]` (Issue # stays mapped); preserve `priorities[src_id]` (priority follows the task per existing `cmd_move` semantics).
     g. GH Issue title stays `[<src_id>] <title>` (no rewrite — D.2 lock).
     h. Project board: `gh.set_status(item_id, "Backlog")` via existing helper.
   - `cmd_move(backlog <dest>)`: arg-parse branch when `src_id` is in `map.backlog` array. Reverse of above: remove from Backlog section, prepend to dest section at the requested position (existing collision-rejection rule per `0.7.0.13`), remove from `backlog` array, `gh.set_status(item_id, "Todo")`.
4. **W3 — Sync + bootstrap awareness** (`engineer`; ~15 min).
   - `.claude/naavik_ops/gh.py:cmd_sync`: skip rows where `task_id in map.backlog` (these are intentionally board-divergent from ROADMAP `[ ]` Todo mapping).
   - `cmd_refresh_map`: rebuild the `backlog` array from authoritative Project state (`Status=Backlog` items). Already iterates items; just adds the array collector.
   - `cmd_bootstrap` (`--apply`): parse `## Backlog` section like a release section but call `set-status Backlog` instead of `Todo` when creating new Issues; idempotent on existing Issues (preserves current Status field).
5. **W4 — Tests** (`engineer`; ~1 hr).
   - `tests/test_naavik_ops/test_roadmap.py`: 3 new tests — `RE_BACKLOG_HEADER` matches `## Backlog (unprioritized)`; `parse_release_section("backlog")` returns rows from the Backlog table; `find_release_section_bounds("backlog")` returns the right line range.
   - `tests/test_naavik_ops/test_task.py`: 2 new tests — `task list backlog` reads from map array; `task list 0.2.0` filters out array members.
   - `tests/test_naavik_ops/test_task_mutating.py`: 4 new tests — `move <id> backlog` updates ROADMAP + map array + status (mock `gh.set_status`); `move backlog-source-id 0.2.0.NN` reverses the move; arg-parse rejects `move <id> backlog.05` (positions disallowed on Backlog dest); arg-parse rejects `move 0.2.0.14 backlog` when `0.2.0.14` is `[x]` (done rows are frozen, per `0.7.0.13` rule).
   - `tests/test_naavik_ops/test_gh.py`: 1 new test — `cmd_sync` skips Backlog-array rows (no STATUS drift emitted for them).
6. **W5 — Docs propagation** (`engineer` + manager finalization; ~30 min).
   - `docs/AGENT_OPS.md § 6.3`: extend Backlog asymmetry table — add a footnote *"ROADMAP-side mirror: rows live under `## Backlog (unprioritized)`; section is recognized by `naavik-ops task list backlog`. See `docs/plans/40-roadmap-backlog-section.md` for the design."*
   - `docs/PLAYBOOK.md § Board status convention (post-A.28)`: add one paragraph naming the ROADMAP section as the canonical authoring surface; reference `naavik-ops task move <id> backlog`.
   - `ROADMAP.md`: ADD `## Backlog (unprioritized)` section (per D.5 shape); MOVE `0.2.0.14` row from `### 0.2.0` table to the new section. Bump "Last updated".
   - `AGENT_OPS.md § 14.X`-style canonical mention not needed (this is tooling, not memory).
   - `CLAUDE.md` / `AGENTS.md`: no edits — Backlog is a ROADMAP-internal concept, no new env / CLI / on-disk artifact surface.
7. **W6 — Bookkeeping commit** (`manager`; direct-push per PLAYBOOK § I — ROADMAP edits are BOOKKEEPING when they're row-state flips + section adds without contract changes; HOWEVER this PR also touches `.claude/naavik_ops/**` + `tests/**` + `docs/PLAYBOOK.md` + `docs/AGENT_OPS.md`, so the whole change ships as a CONTRACT_CHANGE PR per PLAYBOOK § H, then the BOOKKEEPING n8n-row move is a separate direct-push commit AFTER the PR merges — that commit moves the row using the now-shipped `naavik-ops task move 0.2.0.14 backlog`).

Branch: `chore/0.7.0.NN-roadmap-backlog-section` (next free `0.7.0` slot since this is agent-system tooling; manager files the row).

### Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Parser regression: existing release-section parsing breaks because the new `RE_BACKLOG_HEADER` branch swallows `## ` headers that aren't Backlog | LOW | HIGH | Regex anchors on literal `Backlog\b`; existing test suite (210 in `tests/test_naavik_ops/`) catches via test_roadmap.py round-trips on real ROADMAP fixture; W4 adds explicit test that `## Maintenance` (existing h2 in ROADMAP at line 85) is not parsed as a Backlog header |
| Map cache schema drift: forks that ran A.29 migration but don't have `backlog` array in their map cache | MEDIUM | LOW | `_list_release_tasks` uses `data.get("backlog") or []` (already the pattern for `priorities` / `deps`); no migration needed — array materializes on first `move <id> backlog` or `refresh-map` |
| `cmd_sync` accidentally moves a Backlog row to Todo because someone manually edited ROADMAP to flip `[ ]` → `[~]` in the Backlog section | LOW | MEDIUM | W3 lint: `cmd_sync` skips Backlog-array rows entirely; manual ROADMAP edits to Backlog row status are ignored on sync (intentional asymmetry — Backlog deferral is a board-only decision per AGENT_OPS § 6.3) |
| Refresh-map races: `Status=Backlog` items get added to array on next refresh, but a concurrent `task list <release>` reads the stale map and includes them | LOW | LOW | `refresh-map` writes the map atomically via `jsonl.write_json` (existing primitive); `task list` reads via `jsonl.read_json` (atomic); no concurrent-modification window in practice (single-operator workflow) |
| Backlog section grows unboundedly | LOW | LOW | Operator can `task move <id> <release>.<pos>` at any time; nothing in the system pressures Backlog growth — it's a pull surface, not a push |
| 0.2.0.14 move accidentally fires `/sync-roadmap --apply` and reverts the Backlog status to Todo | LOW | LOW | W3 explicitly skips Backlog rows in `cmd_sync`; same fix lands in the same PR |
| Backlog ID collision: someone moves `0.2.1.05` to Backlog while `0.2.1.05` is still occupied in the `0.2.1` section | LOW | MEDIUM | `cmd_move` checks for `src_id` row in the source section (existing path); the row IS the move source, so removing it leaves the section without conflict. Reverse move (`backlog <dest>`) hits the existing dest-collision-reject path per `0.7.0.13` |
| Multi-row Backlog migration mid-cycle (e.g. moving 5 tasks at once for a triage) | LOW | LOW | `task move` is one-at-a-time per the existing atomic-3-store mutation pattern; operator scripts the loop if needed |

## Open questions

- [ ] **OQ.1 — Should the Backlog section carry a `Status:` column at all?** Rows in Backlog are by definition unprioritized + unblocked-by-being-deferred. Three options: (A) preserve the column for visual consistency with release sections (LOCKED if unset); (B) drop the column to signal "this is a different kind of table"; (C) drop the column AND drop the Priority column. **Default: A** — visual consistency with release tables matters more than visual signaling of asymmetry; the section preamble already carries the asymmetry message.
- [ ] **OQ.2 — Should the `backlog` map-cache array also carry move-timestamps for forensic audit?** E.g. `{"backlog": [{"task_id": "0.2.0.14", "moved_at": "2026-05-19T...", "from_version": "0.2.0", "from_position": 14}, ...]}`. **Default: NO** — start with a flat array of task IDs; if forensic queries become common, the map's `redirects` sub-key (already populated on cross-release moves per plan 25) can absorb the audit role without schema change here. Move-history is an A.30+ ergonomics concern, not a release-cut blocker.
- [ ] **OQ.3 — Does `task next-unblocked backlog` make sense?** "What's the next thing to promote out of Backlog?" If yes, sort key would be... what? (Original release-version ASC? Move-date DESC?). **Default: NO** — Backlog is unordered by design (D.3 lock + D.6 lock). `next-unblocked backlog` returns "(no current-cycle tasks; backlog is not a cycle)" stub. Use `gh backlog-by-epic --top N` (existing) for the "what's in Backlog grouped by epic" view; that surface already covers the operator's promotion-decision use case.
- [ ] **OQ.4 — Is the bookkeeping move of `0.2.0.14` part of this PR or a follow-up commit?** Two options: (A) PR ships tooling + ROADMAP section header + n8n row move in one merge; (B) PR ships tooling only, then BOOKKEEPING direct-push moves `0.2.0.14` post-merge. **Default: A** — single coherent change; the n8n move USES the new tooling (eats own dogfood); reviewers see the section actually populated. PR diff is still scoped: 4 code files + 4 doc files + 1 ROADMAP edit + ~10 new tests.
- [ ] **OQ.5 — Should `task move <id> backlog` require explicit confirmation (`--yes` flag)?** Moves a task out of a release cycle; could be a foot-gun. **Default: NO** — existing `task move` doesn't require confirmation for cross-release moves either; consistency wins. Operator can always `task move <id> <original-release>.<original-pos>` to reverse.
- [ ] **OQ.6 — Issue # in Backlog: does the GH Issue stay open or close?** **Default: STAY OPEN** — `Status=Backlog` on a Project board is an OPEN issue; closing would imply Done. Per AGENT_OPS § 6.3, Backlog Issues are open + parked. This is consistent with the existing Project state (post-A.28 board restructure).

## Approval checklist

- [ ] D.1 — Position section at BOTTOM of `## Phases` (after `### 0.7.0`, before `## Agent System`)
- [ ] D.2 — Preserve original release-version IDs (`0.2.0.14` keeps its name)
- [ ] D.3 — Use literal `backlog` as synthetic release-version handle (no semver coerce)
- [ ] D.4 — Add `RE_BACKLOG_HEADER` regex + branch in writer-half (`parse_release_section` / `find_release_section_bounds` / `write_release_section` all accept `version == "backlog"`)
- [ ] D.5 — Section markdown shape: h2 header + preamble blockquote + standard 6-column table
- [ ] D.6 — `.claude/github-issue-map.json:backlog` array as the per-task tag; `task list <release>` filters OUT array members; `task list backlog` reads the array
- [ ] D.7 — `task move <id> backlog` (no position arg) sends to Backlog; `task move <backlog-id> <release>.<pos>` pulls into a release; positions are REJECTED on Backlog dest
- [ ] D.8 — `0.2.0.14` n8n migration goes to **Backlog** (not closed-as-moot; deferred but not impossible)
- [ ] OQ.1 — Preserve Status column in Backlog table (visual consistency)
- [ ] OQ.2 — Flat array of task IDs in map cache (no timestamps for now)
- [ ] OQ.3 — `task next-unblocked backlog` is a no-op (Backlog is not a cycle)
- [ ] OQ.4 — Ship tooling + section header + n8n row move in ONE PR
- [ ] OQ.5 — `task move <id> backlog` does NOT require `--yes`
- [ ] OQ.6 — Backlog Issues stay OPEN on GitHub (closed = Done conflict)

## Doc graduation

`Type: design`. On approval, this plan's content graduates into the existing canonical docs (no new top-level design doc needed):

- `docs/AGENT_OPS.md § 6.3` — extended with ROADMAP-side mirror description (one paragraph).
- `docs/PLAYBOOK.md § Board status convention (post-A.28)` — extended with the `naavik-ops task move <id> backlog` workflow (one paragraph).
- `docs/design/PHASE_NUMBERING.md` — the existing canonical schema doc gets a `## Backlog as synthetic release-version` subsection (the `backlog` literal sits alongside the 3-level + 4-level semver in the schema regex's allowlist) (~20 lines).

This plan archives to `docs/plans/archive/40-roadmap-backlog-section.md` on completion; no new permanent design doc is created — the schema doc absorbs the Backlog convention.

## Implementation prompt

Authored at `docs/prompts/40-roadmap-backlog-section.md` on PLAN_GATE approval. Includes:

1. **Goal** — one sentence: implement plan 40 W1-W5 + bookkeeping ROADMAP edit + 0.2.0.14 move.
2. **Required reading** — this plan; `lib/roadmap.py` + `lib/semver.py` + `task.py` + `gh.py:cmd_sync,cmd_refresh_map,cmd_bootstrap`; `docs/AGENT_OPS.md § 6.3`; `docs/PLAYBOOK.md § Board status convention`.
3. **Deliverables** — 4 code files (`lib/semver.py`, `lib/roadmap.py`, `task.py`, `gh.py`), ~10 tests (1 file each in `test_roadmap.py`, `test_task.py`, `test_task_mutating.py`, `test_gh.py`), 4 doc files (`docs/AGENT_OPS.md`, `docs/PLAYBOOK.md`, `docs/design/PHASE_NUMBERING.md`, `ROADMAP.md`), 1 bookkeeping ROADMAP commit.
4. **Quality bar** — `uv run ruff check .` clean; `uv run ruff format --check .` clean; `uv run pytest tests/test_naavik_ops/ -x` clean (existing 210 tests + ~10 new); `naavik-ops task list backlog` shows 0.2.0.14; `naavik-ops task list 0.2.0` does NOT show 0.2.0.14; `naavik-ops task next-unblocked 0.2.0` does NOT return 0.2.0.14; `naavik-ops gh sync` shows no STATUS drift on 0.2.0.14.
5. **Forbidden** — no new `naavik` CLI subcommand; no `src/services/vault.py` extension; no new top-level `.claude/` package paths (extend `naavik_ops/` modules instead); no new on-disk artifacts outside `~/.naavik/naavik-ops.lock` (existing flock path).
6. **Hand-back format** — file list + screenshot of `task list backlog` output + deviations summary.
