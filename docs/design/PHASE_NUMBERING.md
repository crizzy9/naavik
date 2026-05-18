# Phase Numbering — 4-level semver task-ID schema for Naavik

> **Status:** SKELETON (graduates from `docs/plans/24-A.29-phase-numbering-system.md` on PLAN_GATE approve).
> **Authored:** 2026-05-18 (skeleton REV-2)
> **Last updated:** 2026-05-18
> **Implements:** A.29 (post-migration ID: `0.1.4.01`). ROADMAP.md:465. Issue #71.
> **Canonical plan:** `docs/plans/archive/24-A.29-phase-numbering-system.md` (post-archive)
> **Sole writers:** `scripts/phase-tasks.sh` (task-ID + release-version mutations) + `scripts/gh-project.sh` (Issue / Project / Milestone mutations). Composed; not replaced.

Body lands on PLAN_GATE approve. Section stubs below capture the contract surface — full prose graduates from the plan's § D content.

---

## § 1 — Schema

Task IDs follow a **4-level semver-aligned schema**:

```
<MAJOR>.<MINOR>.<PATCH>[.<POSITION>]
```

- **3-level** (`<MAJOR>.<MINOR>.<PATCH>`) = a **release version**. e.g. `0.1.0` (MVP), `0.2.0` (Phase 2 scrapers), `0.2.1` (Phase 1 deferred security cleanup).
- **4-level** (`<MAJOR>.<MINOR>.<PATCH>.<POSITION>`) = a **task within a release**. e.g. `0.2.0.01`, `0.2.0.14`.
- Position component is **zero-padded two-digit** (`01..99`) for lex-sort stability. 99 slots per release MINOR.
- **Position is NOT priority.** Every task within a release MINOR is equally required for that release to cut. Position is a forward-fill ID slot, not an ordering statement.

**Regex:** `^\d+\.\d+\.\d+(\.\d{2})?$`

**Reading rule:**
- Release ordering: `0.1.0 < 0.1.1 < 0.2.0 < 0.3.0 < ... < 1.0.0`.
- Task ordering within a release: `0.2.0.01 < 0.2.0.02 < ... < 0.2.0.99` (lex-sort).
- Priority signal: **release-version itself.** Within a release, no priority — all sub-tasks equally required.

**Semver caveat:** 4-level IDs are a non-strict extension of semver 2.0.0. Consumers expecting strict 3-level semver (e.g. `pip install`) must strip the `.POSITION` suffix when calling external tooling. Document this in tooling integration § 6.

> Full content graduates from plan § D.1 + D.2 + D.8 + D.14.

---

## § 2 — Releases

`scripts/phase-tasks.sh release <version> [--cut] [--no-tag]` bundles the **release ceremony** — 10 mechanical steps that today are scattered across `pyproject.toml` + `nix/package.nix` + git tags + GitHub Releases UI:

1. **Pre-flight gates.** Verify all sub-tasks under `[Epic] <version>` are `[x]`; git tree clean; `git tag --list <version>` empty; acquire `~/.naavik/phase-tasks.lock` flock.
2. **Compute CHANGELOG section** from closed Issues + PR squash subjects + Conventional Commits classification (§ 3).
3. **Update `pyproject.toml`** `[project] version` field.
4. **Update `nix/package.nix`** `version` attribute.
5. **Write CHANGELOG.md release section** (prepend new release block).
6. **Commit bookkeeping** — `chore(release): <version>` + body listing closed Issues + CHANGELOG breakdown.
7. **`git tag <version>`** — annotated tag with same body as release commit.
8. **Push tag to origin.**
9. **`gh release create <version> --notes-from-tag --generate-notes`.**
10. **Close the version's epic Issue** via composed `gh-project.sh set-status`.

**Invariants:**

- **Tags cut only at release ceremony.** PRs deliver at least one meaningful patch-level increment of work but do NOT cut tags individually. The `release` command is the sole sanctioned way to bump versions.
- **`pyproject.toml` + `nix/package.nix` versions synced atomically.** The release ceremony updates both in the same commit; `phase-tasks.sh check` detects drift between them + the latest tag.
- **`--cut` flag** distinguishes dry-run from mutation. `--no-tag` skips steps 7–9 (used for migration commits where the tag gets cut by the migration script separately).

**Cross-reference to A.27** (deferred to a future `0.2.X` thematic patch-epic): **A.27 must address version-tag implications when scheduled** — release branches per MINOR? release-branch promotion ceremony? Whether `main` becomes release/stable + `develop` becomes integration? Out of scope for this design doc; A.27 owns the decision.

> Full content graduates from plan § D.15 + D.14.1.

---

## § 3 — Changelog

`CHANGELOG.md` follows [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/) format. Sections per release:

- **Added** — new features.
- **Changed** — changes to existing functionality.
- **Deprecated** — features marked for removal.
- **Removed** — features removed in this release.
- **Fixed** — bug fixes.
- **Security** — security-related changes.

**Auto-classification from Conventional Commits:**

| Commit prefix | CHANGELOG section |
|---|---|
| `feat:` / `feat(<scope>):` | Added |
| `feat:!` / `feat(<scope>)!:` / body contains `BREAKING CHANGE:` | Changed (forces MAJOR bump post-1.0; allowed in MINOR pre-1.0) |
| `fix:` / `fix(<scope>):` | Fixed |
| `chore(security):` / `feat(security):` | Security |
| `deprecate:` / body contains `DEPRECATED:` | Deprecated |
| `remove:` / body contains `REMOVED:` | Removed |
| `chore:` / `docs:` / `refactor:` / `test:` / `perf:` / `build:` / `ci:` / `style:` | NOT in CHANGELOG (internal noise) |

**Initial content** generated by migration script (Wave 2.5): retroactive `0.0.0`, `0.1.0`, `0.1.1`, `0.1.2`, `0.1.3`, `0.1.4` release notes from archived plans' deliverable narratives. ~120 lines initial bootstrap.

> Full content graduates from plan § D.16.

---

## § 4 — Deps

`scripts/phase-tasks.sh deps <task-id> [add | remove | list | check]` tracks **explicit cross-task + cross-version dependencies** in `.claude/github-issue-map.json:deps`:

```json
{
  "deps": {
    "0.2.0.02": { "blocks": [], "blocked_by": ["0.2.0.01"] },
    "0.2.0.06": { "blocks": ["0.2.0.07","0.2.0.08","0.2.0.09"], "blocked_by": ["0.2.0.05"] },
    "0.2.1.05": { "blocks": ["0.3.0.01"], "blocked_by": ["0.2.0.07"] }
  }
}
```

**Subcommands:**

- `deps <task-id> add <dep-id>` — record `<task-id> blocked_by <dep-id>` + inverse `blocks` entry on `<dep-id>`. Idempotent.
- `deps <task-id> remove <dep-id>` — inverse.
- `deps <task-id> list` — print both `blocks` + `blocked_by` for the task.
- `deps check` — verify no cycles, no closed-blocking-open inversions, all referenced IDs exist in the issue map.

**Integration:** `scripts/gh-project.sh:cmd_next_unblocked` consults the deps store. A task is "blocked" if any entry in its `blocked_by` is `[ ]` or `[~]`. `next-unblocked` returns the lex-asc-first ID that's not blocked.

**Cross-release deps** explicitly supported (`0.2.1.05 blocked_by 0.2.0.07` — a patch fix waits on a 0.2.0 task).

> Full content graduates from plan § D.17.

---

## § 5 — Migration

**One-time bootstrap** via `scripts/A.29-phase-renumber.sh --apply` after this design doc graduates. Migration scope is full retroactive — every ROADMAP row + every GitHub Issue + every Milestone + every Project Epic + every plan-archive frontmatter + every agent-prompt embedded ID. Trace logs in `traces/<run-id>/` stay as-is (historic).

**13-step flow** (per plan § D.12):

1. Pre-flight gates (no in-flight gates; git tree clean; acquire `~/.naavik/A.29-migration.lock`).
2. Compute target IDs for every existing row → rename map JSON.
3. User confirmation gate.
4. Create new Milestones for each release-version (`0.0.0`–`0.2.6`).
5. Create new Project Epics for each release-version.
6. For each row in mapping table: rewrite Issue title (composed via `gh-project.sh`) + update map cache + add to `redirects` dict + re-link Milestone + re-link Epic + log MIRROR event.
7. Rewrite `ROADMAP.md` — full release-version section restructure (Phase 0/1/PC/done-A → `0.0.0`–`0.1.3`; Phase 2 → `0.2.0` sub-tasks; DEF → `0.2.X` thematic patches; Phase 3–6 → `0.3.0`–`0.6.0`).
8. Close superseded Milestones (`Pre-Phase-2 paper cuts`, `Phase A`, `Phase 1 deferred items`, `Phase 2.5`).
9. Rewrite plan archive frontmatter — every `docs/plans/archive/NN-*.md` `Implements:` line updates to new ID + `(was <old>, frozen)` parenthetical. Body unchanged.
10. Rewrite agent prompts + skills + commands + docs per caller-rewrite list (25 sites).
11. Bootstrap `CHANGELOG.md` — generate retroactive `0.0.0` and `0.1.0`–`0.1.4` release notes.
12. Verification — `phase-tasks.sh check` exits 0.
13. Commit migration as `chore(release): A.29 — phase numbering migration to semver`. Update `pyproject.toml` + `nix/package.nix` to `0.1.4`. Tag `0.1.4` post-merge.

**Per-task add flow** (operator surface, post-migration):

```bash
# Add a new task at position 0.2.0.05 (shifts 0.2.0.05+ down by 1):
scripts/phase-tasks.sh insert 0.2.0.05 "AI extraction retry policy" --effort M

# Or defer an existing task:
scripts/phase-tasks.sh defer 0.2.0.07 --by 2

# Cross-release relocate:
scripts/phase-tasks.sh move 0.2.0.14 0.3.0.05

# Cross-version dep:
scripts/phase-tasks.sh deps 0.2.1.05 add 0.2.0.07

# Release ceremony:
scripts/phase-tasks.sh release 0.2.0 --cut
```

> Full content graduates from plan § D.6 + D.7 + D.9 + D.10 + D.12 + D.14.2 + D.19.

---

## § 6 — Tooling integration

Callers that read the schema (must be updated when § 1 changes):

- **`scripts/gh-project.sh`** § `cmd_create_issue`, `cmd_next_unblocked`, `cmd_sync`, `cmd_backlog_by_epic` — drop Priority writes, sort by 4-level task-ID, drift detection compares title `[<expected-id>]` against ROADMAP, gate next-unblocked on deps.
- **`scripts/agent-memory.sh`** — knowledge entries reference task IDs in body; redirects map preserves legacy lookups.
- **`.claude/hooks/git/prepare-commit-msg`** — extended for Conventional Commits regex validation (§ 7) + auto-`Closes #N` from branch name (existing).
- **`pyproject.toml`** `[project] version` — written atomically by `phase-tasks.sh release`. `phase-tasks.sh check` detects manual drift.
- **`nix/package.nix`** `version` attribute — same atomicity contract.
- **`.claude/agents/manager.md`**, **`.claude/skills/manager-*`**, **`.claude/commands/*`** — sort by release-version + 4-level lex; references update to new schema.
- **`docs/AGENT_OPS.md § 6`** (GitHub Mirror conventions) + **§ 2.8** (commit-message hook).
- **`docs/PLAYBOOK.md § F`** (PRODUCT_WORK) + **§ File classification** (`phase-tasks.sh` is CONTRACT_CHANGE — PR required).
- **`AGENTS.md § GitHub state — single writer rule`** — extends to add `phase-tasks.sh` as second sole writer for task-ID + release-version mutations.
- **`.claude/github-issue-map.json`** — schema extension: `milestones` (per release-version), `epics` (per release-version), `issues` (4-level key → issue#), `redirects` (legacy → new ID), `deps` (cross-task graph).

**Semver consumers external to Naavik** (`pip install`-style, Docker tag conventions) — strip the `.POSITION` suffix when passing through. Document caveat in `pyproject.toml` comment + `nix/package.nix` comment.

> Full content graduates from plan § D.13's 25-row enumeration table.

---

## § 7 — Threats

| Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Two operators run `phase-tasks.sh insert` concurrently | Low | Medium | flock `~/.naavik/phase-tasks.lock` serializes; second invocation blocks until first releases. |
| New fork inherits stale schema | Low | Low | `scripts/A.29-phase-renumber.sh` is idempotent; re-run on fork sees existing schema + no-ops. |
| Future task lands on a freed slot of a frozen done ID | Medium | High | `phase-tasks.sh insert` rejects with diagnostic; operator picks next-available slot. Test asserted. |
| Issue title rewrite fails mid-batch (cross-release `move`) | Low | High | `.tmp` write pattern + rollback if any single rewrite fails. Atomicity proof in `tests/test_phase_tasks.sh`. |
| GraphQL pagination cap (200 items) | Medium | Medium | Full-pagination helper in `phase-tasks.sh` (vs. existing `gh-project.sh` which caps at 200). |
| Operator edits Issue title manually in GitHub UI | High | Low | `phase-tasks.sh check` detects drift on next invocation; `sync --apply` overwrites to match ROADMAP. |
| Cycles in deps DAG | Low | Medium | `phase-tasks.sh deps check` verifies — refuses to add an edge that creates a cycle. |
| Partial migration — Wave 2.X script aborts mid-flow | Low | High | Idempotent steps + redirects-key-based skip. Re-run continues from last successful step. |
| `pyproject.toml` / `nix/package.nix` desync between releases | Medium | Medium | `phase-tasks.sh check` detects; `release` is the only sanctioned bump path. |
| Conventional Commits hook regressing existing BOOKKEEPING styles | Medium | Medium | Branch-aware enforcement — strict on feature branches, lenient on `main`. Bypass via `--no-verify`. |
| Operator runs `release 0.2.0 --cut` while open `0.2.0.NN` task exists | Low | High | Pre-flight gate (step 1) fails fast; test asserts. |
| Tag-vs-pyproject drift via manual edit between releases | Medium | Medium | `check` reads all three sources (pyproject, flake, latest tag); exits non-zero on mismatch. |
| CHANGELOG.md merge conflict during parallel release ops | Very low | Low | Single-engineer + flock; won't happen in practice. Documented. |

> Full content graduates from plan § Risk + mitigation rows (a)–(q).

---

## § 8 — Future

**When MAJOR bumps to `1.0.0`:** user-signaled at the Phase 6 / "first MVP-public-ready" cut, OR earlier if scope matures. Until then all work is `0.X.Y.NN`. The `release` ceremony enforces breakage-detection-via-Conventional-Commits (`BREAKING CHANGE:` footer → forces MAJOR post-1.0; allowed in MINOR pre-1.0).

**Agent-system-as-plugin separation:** user signaled "agent system will go away from this repo and become its own plugin at a later time." When that split happens (probably post-1.0 or via Phase 2.5 / Phase 3 separation), `naavik-agent-system` becomes its own package with its own semver. Until then, all A.* items (now `0.1.X` retroactive) version with the main package. After split: redirects entries point to the plugin's separate semver via the `_meta.plugin_origin` field on each affected redirect; plugin maintains its own CHANGELOG + release ceremony via its own `phase-tasks.sh` instance.

**When any release MINOR exhausts 99 slots:** unlikely (largest historic batch was Phase A at ~34 items). When hit, split into a follow-up PATCH (`0.2.0` exhausts → next batch becomes `0.2.1`) OR split the MINOR cleanly. Migration: `phase-tasks.sh rename-release` handles bulk rewrites.

**When Project board UI Priority field cleanup happens:** after ~1 month post-migration, optionally delete the Priority field via Project settings UI (one-click). All write paths to that field have been removed by Wave 3. Field's existence is vestigial until explicit cleanup.

**When ROADMAP Priority column drops:** after ~1 release post-migration. Until then, kept as informational hint — operator reads "this is HIGH" and trusts release-version reflects it; `phase-tasks.sh check` warns if mismatch.

**LTS at 2.0+:** not in current scope. Deferred until user signal post-1.0.

**Distribution channels (dev / stable / beta):** not in current scope. Out of scope per user lock in REV-2.

**Pre-release tags (`0.2.0-rc.1`):** explicitly dropped (user lock E3 in REV-2). Add when needed; not a hurdle.

> Full content lands on graduation. Add new threats / extensibility scenarios here as the schema accretes operational experience.
