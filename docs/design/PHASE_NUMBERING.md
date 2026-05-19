# Phase Numbering — 4-level semver task-ID schema for Naavik

> **Status:** GRADUATED FROM PLAN (post-A.29 PLAN_GATE approve).
> **Authored:** 2026-05-18 (REV-3)
> **Last updated:** 2026-05-18 (Wave 4 graduation — skeleton expanded to full prose).
> **Implements:** A.29 (post-migration ID: `0.1.0.<NN>` per REV-3 single-fold). ROADMAP.md:468. Issue #71.
> **Canonical plan:** `docs/plans/archive/24-A.29-phase-numbering-system.md` (post-archive).
> **Sole writer entry:** `.claude/naavik-ops` (Python dispatcher routing task-ID + release-version + Issue/Project/Milestone + memory mutations). During A.29 the `gh` + `memory` groups subprocess-wrap `.claude/naavik_ops/gh.py` + `.claude/naavik_ops/memory.py`; A.30 (0.1.1) inlines natively in Python.

This doc is the permanent contract for how Naavik tracks tasks, releases, and dependencies. The 4-level semver task-ID schema replaced the legacy two-level scheme (`A.29`, `PC.6a`, `2.12`, `DEF-05`) on 2026-05-18 via the A.29 migration runbook (`.claude/migrations/A.29-phase-renumber.py`). The original plan that produced this contract is archived; this doc supersedes for forward-looking changes.

---

## § 1 — Schema

Task IDs follow a **4-level semver-aligned schema**:

```
<MAJOR>.<MINOR>.<PATCH>[.<POSITION>]
```

- **3-level** (`<MAJOR>.<MINOR>.<PATCH>`) = a **release version**. e.g. `0.1.0` (pre-Phase-2 bundle covering Phase 0 + Phase 1 + PC + A.1–A.29), `0.1.1` (A.30 — Python rewrite of legacy bash), `0.2.0` (Phase 2 scrapers), `0.2.1` (Phase 1 deferred security cleanup, first of six thematic patches).
- **4-level** (`<MAJOR>.<MINOR>.<PATCH>.<POSITION>`) = a **task within a release**. e.g. `0.2.0.01`, `0.2.0.14`.
- Position component is **zero-padded two-digit** (`01..99`) for lex-sort stability. 99 slots per release MINOR.
- **Position is NOT priority.** It is a forward-fill ID slot, not an ordering statement.

### Three orthogonal signals

Three fields independently describe a task's position in the work queue. Each has exactly one canonical meaning; they compose without overloading.

1. **Position** — canonical *ID slot* (forward-fill within a release MINOR). Sets the task's lex-sortable identifier; does NOT imply ship order.
2. **Priority** (HIGH / MEDIUM / LOW / unset) — canonical *intra-release impact signal*. Optional, sparse. **TASK-level only** (4-level IDs); patches and minor-releases never carry priority. Default = unset (= unprioritized).
3. **Release version** — canonical *cross-release sequence signal*. `0.1.X` ships before `0.2.0` before `0.3.0`.

### Position stability (codified 2026-05-19 via plan 28)

Position is a **forward-fill ID slot**, not a sort invariant. Once a task is assigned position `NN` within a release, that ID is stable for the task's lifetime — including after the task moves to a different release or transitions to `[x]`. Operational consequences:

- **`naavik-ops task move <src> <dest-version>.<dest-pos>` does NOT auto-renumber siblings** in either the source patch (gap left behind) or the destination patch (collision rejects). Source-section gaps are intentional.
- **`naavik-ops task renumber <version>` is the explicit compaction tool.** Operator opts in when cosmetic alignment is wanted. Never a side-effect.
- **`naavik-ops task defer <task-id>` is the intra-release shift tool.** Defer's purpose IS shifting siblings; that's a separate semantic from cross-release migration.
- **Cross-release moves preserve referential integrity for siblings.** Archived plans that cite `0.2.0.05` continue to resolve to the same task even after another sibling moves out of the patch.

See `.claude/memory/knowledge/patch-version-position-stability.md` for the principle origin + recovery procedure if a buggy script ever renumbers siblings against the rule.

### Regex

```
^\d+\.\d+\.\d+(\.\d{2})?$
```

The same regex matches both 3-level release versions and 4-level task IDs. Consumers branch on whether the position group captured. Reference implementation: `.claude/naavik_ops/lib/semver.py:SCHEMA_REGEX`.

### Reading rule

- **Release ordering:** `0.1.0 < 0.1.1 < 0.2.0 < 0.3.0 < ... < 1.0.0`.
- **Task ordering within a release:** `priority DESC (HIGH > MED > LOW > unset) → position ASC`.
- **`next-unblocked` sort key:** `release-version ASC → priority DESC → position ASC`, gated by deps.

Example for release `0.2.0`:

```
0.2.0.01 HIGH    Vault deprecation (Tier-2 wave 1)
0.2.0.05 HIGH    SQLModel Job models (hard-dep for every scraper)
0.2.0.02 unset   CLI sunset (depends on 0.2.0.01)
0.2.0.03 unset   PC.6a — already shipped, [x]
0.2.0.04 unset   Onboarding bypass
0.2.0.06 unset   Crawl4AI base class
...
0.2.0.14 unset   Migrate n8n DataTable
```

`naavik-ops task next-unblocked 0.2.0` returns `0.2.0.01 HIGH` first (highest priority, lowest position), then `0.2.0.05 HIGH` after `0.2.0.01` closes, then `0.2.0.02 unset` once `0.2.0.01`'s blocked_by clears, etc.

### Semver caveat

4-level IDs are a non-strict extension of [semver 2.0.0](https://semver.org/spec/v2.0.0.html). Consumers expecting strict 3-level semver (e.g. `pip install`, Docker tag conventions) must strip the `.POSITION` suffix when calling external tooling. `pyproject.toml [project] version` and `nix/package.nix` `version` attribute always hold the 3-level release version; the 4-level ID is internal to the Naavik tracker.

### Frozen done-item IDs

Once a task transitions to `[x]` in ROADMAP, its 4-level ID is **frozen forever**. Legacy IDs (pre-migration) survive via the `.claude/github-issue-map.json:redirects` map. Example:

```json
{
  "redirects": {
    "PC.5":  "0.1.0.21",
    "A.29":  "0.1.0.50",
    "2.12":  "0.2.0.01",
    "DEF-05": "0.2.1.01"
  }
}
```

Archived plans at `docs/plans/archive/NN-*.md` carry the new ID in their `Implements:` frontmatter line with `(was <old>, frozen)` parenthetical for searchability.

---

## § 2 — Releases

`.claude/naavik-ops release cut <version> [--no-tag] [--apply]` bundles the **release ceremony** — 10 mechanical steps that today are scattered across `pyproject.toml` + `nix/package.nix` + git tags + GitHub Releases UI:

1. **Pre-flight gates.** Verify all sub-tasks under `[Epic] <version>` are `[x]`; git tree clean; `git tag --list <version>` empty; acquire `~/.naavik/naavik-ops.lock` flock.
2. **Compute CHANGELOG section** from closed Issues + PR squash subjects + Conventional Commits classification (§ 3).
3. **Update `pyproject.toml`** `[project] version` field.
4. **Update `nix/package.nix`** `version` attribute.
5. **Write CHANGELOG.md release section** (prepend new release block immediately after the `## [Unreleased]` anchor).
6. **Commit bookkeeping** — `chore(release): <version>` + body listing closed Issues + CHANGELOG breakdown.
7. **`git tag <version>`** — annotated tag with the same body as the release commit.
8. **Push tag to origin** (`git push origin <version>`).
9. **`gh release create <version> --notes-from-tag --generate-notes`** — creates GitHub Release; auto-generates additional notes from the PR list.
10. **Close the version's epic Issue** via composed `naavik-ops gh set-status` (subprocess wrapper → `.claude/naavik_ops/gh.py` during A.29; native Python in A.30).

### Invariants

- **Tags cut only at release ceremony.** PRs deliver at least one meaningful patch-level increment of work but do NOT cut tags individually. The `release cut` command is the sole sanctioned way to bump versions.
- **`pyproject.toml` + `nix/package.nix` versions synced atomically.** The release ceremony updates both in the same commit; `naavik-ops task check` detects drift between them + the latest tag.
- **`--no-tag`** skips steps 7–9 (used for the A.29 migration commit; the tag is cut post-merge in Wave 5).
- **`naavik-ops release dry-run <version>`** previews actions without mutating. Use as a preview gate.

### Pre-release tags

Explicitly dropped (user lock E3 in plan REV-2). No `-rc.1` / `-alpha.N` / `-beta.N` markers. Add when needed; not a hurdle today.

### Cross-reference to A.27 (deferred to a future `0.2.X` thematic patch-epic)

**A.27 must address version-tag implications when scheduled.** Open questions:
- Release branches per MINOR?
- Release-branch promotion ceremony?
- Whether `main` becomes release/stable + `develop` becomes integration?

These are out of scope for this design doc; A.27 owns the decision. Plan-frontmatter comment lives in the A.29 archived plan's § Cross-references.

---

## § 3 — Changelog

`CHANGELOG.md` follows [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/) format. Sections per release:

- **Added** — new features.
- **Changed** — changes to existing functionality.
- **Deprecated** — features marked for removal.
- **Removed** — features removed in this release.
- **Fixed** — bug fixes.
- **Security** — security-related changes.

### Auto-classification from Conventional Commits

| Commit prefix | CHANGELOG section |
|---|---|
| `feat:` / `feat(<scope>):` | **Added** |
| `feat:!` / `feat(<scope>)!:` / body contains `BREAKING CHANGE:` | **Changed** (forces MAJOR bump post-1.0; allowed in MINOR pre-1.0) |
| `fix:` / `fix(<scope>):` | **Fixed** |
| `chore(security):` / `feat(security):` | **Security** |
| `deprecate:` / body contains `DEPRECATED:` | **Deprecated** |
| `remove:` / body contains `REMOVED:` | **Removed** |
| `chore:` / `docs:` / `refactor:` / `test:` / `perf:` / `build:` / `ci:` / `style:` | **NOT in CHANGELOG** (internal noise) |

Reference implementation: `.claude/naavik_ops/lib/changelog.py:classify_commit`.

### Initial bootstrap

ONE retroactive `0.1.0` release section covering everything pre-Phase-2 (Phase 0 + Phase 1 + PC.1–PC.7 + A.1–A.29). ~80 lines initial content, written by the migration runbook (`.claude/migrations/A.29-phase-renumber.py:step_11_bootstrap_changelog`). A.30 (0.1.1) appends its section when it ships.

### Conventional Commits enforcement

`.claude/hooks/git/prepare-commit-msg` extends to validate commit subjects on feature branches. Branch-aware: strict on `feat/*` / `fix/*` / `chore/*` / `docs/*` / `refactor/*`; lenient on `main` (BOOKKEEPING direct-push convention preserved). Bypass via `git commit --no-verify`.

Subject regex:

```
^(feat|fix|chore|docs|refactor|test|perf|build|ci|style|deprecate|remove)(\([a-z0-9-]+\))?!?: .+$
```

---

## § 4 — Deps

`.claude/naavik-ops deps <subcommand>` tracks **explicit cross-task + cross-version dependencies** in `.claude/github-issue-map.json:deps`:

```json
{
  "deps": {
    "0.2.0.02": { "blocks": [], "blocked_by": ["0.2.0.01"] },
    "0.2.0.06": { "blocks": ["0.2.0.07","0.2.0.08","0.2.0.09"], "blocked_by": ["0.2.0.05"] },
    "0.2.1.05": { "blocks": ["0.3.0.01"], "blocked_by": ["0.2.0.07"] }
  }
}
```

### Subcommands

```
.claude/naavik-ops deps add <task-id> <dep-id>      record <task-id> blocked_by <dep-id>; inverse blocks edge added
.claude/naavik-ops deps remove <task-id> <dep-id>   inverse of add
.claude/naavik-ops deps list <task-id>              print blocks + blocked_by for the task
.claude/naavik-ops deps check                       verify no cycles, no asymmetric edges, all IDs valid
```

### Properties

- **Symmetric edges.** Every `<A>.blocked_by += <B>` writes an inverse `<B>.blocks += <A>` atomically; `check` flags asymmetric edges as data corruption.
- **No cycles.** `add` rejects edges that would create a cycle (iterative DFS, runs after mutation; rolls back on detect). `check` verifies the full graph.
- **Cross-release deps explicitly supported.** `0.2.1.05 blocked_by 0.2.0.07` — a patch fix waits on a 0.2.0 task. Useful when a follow-up depends on a feature from the main release.
- **Release-level IDs rejected.** Deps only meaningful on 4-level task IDs; `naavik-ops deps add 0.2.0 ...` errors fast.

### Integration

`naavik-ops task next-unblocked` consults the deps store. A task is "blocked" if any entry in its `blocked_by` is `[ ]` or `[~]`. Sort key per § 1: priority DESC → position ASC, ties broken by Issue number (oldest first).

Reference implementation: `.claude/naavik_ops/deps.py`.

---

## § 5 — Migration

**One-time bootstrap** via `python .claude/migrations/A.29-phase-renumber.py --apply` after the A.29 PR merges. Migration scope is full retroactive — every ROADMAP row + every GitHub Issue + every Milestone + every Project Epic + every plan-archive frontmatter + every agent-prompt embedded ID. Trace logs in `traces/<run-id>/` stay as-is (historic).

### 13-step flow

1. **Pre-flight gates** — git tree clean; `~/.naavik/A.29-migration.lock` acquired via `fcntl.flock`.
2. **Compute target IDs** for every ROADMAP row → rename map CSV at `traces/<run-id>/A.29-rename-map.csv`. Priority column populated only for 4-level IDs.
3. **User confirmation gate** — `apply` requires explicit `yes` typed.
4. **Create new Milestones** (`0.1.0`, `0.1.1`, `0.2.0`..`0.2.6`, `0.3.0`..`0.6.0`).
5. **Create new Project Epics** (`[Epic] 0.1.0`, etc.) for each release-version.
6. **Per-row renumber** — rewrite Issue title + map cache `issues` key + `redirects` entry + relink milestone + relink epic + set Project Priority field per § 1 (only on 4-level IDs).
7. **Rewrite ROADMAP.md** — full release-version section restructure. Phase 0 + Phase 1 + Pre-PC + done-A → consolidated `### 0.1.0` section; Phase 2 → `### 0.2.0`; DEF → `### 0.2.1–0.2.6`; Phase 3–6 → `### 0.3.0–0.6.0`; A.30 → `### 0.1.1`. Architect-built patch per Wave 5 dispatch.
8. **Close superseded Milestones** (`Phase A`, `Pre-Phase-2 paper cuts`, `Phase 1 deferred items`, `Phase 2`, `Phase 2.5`).
9. **Rewrite plan-archive frontmatter** — every `docs/plans/archive/NN-*.md` `Implements:` line updates to new ID + `(was <old>, frozen)` parenthetical. Body unchanged.
10. **Caller rewrites** — already shipped in Wave 3 of the A.29 PR; runbook step 10 is a no-op pointer.
11. **Bootstrap CHANGELOG.md** — generate retroactive `0.1.0` release section.
12. **Verification** — `naavik-ops task check` exits 0 post-migration.
13. **Commit migration** as `chore(release): A.29 — phase numbering migration + 0.1.0 baseline`. Print rename map to commit body for future audit. Update `pyproject.toml` + `nix/package.nix` to `0.1.0`. Tag `0.1.0` post-merge via `naavik-ops release cut 0.1.0`.

### Safety invariants

- **No `eval`.** All subprocess calls use argv arrays. No untrusted-string interpolation.
- **`--apply` is NEVER the silent default.** Bare invocation = `--dry-run`.
- **Lock-protected.** Concurrent invocations fail fast (exit 1) on `BlockingIOError`.
- **Trace logs in `traces/<run-id>/` NEVER rewritten** (historic record).
- **Idempotent.** Re-runs check `redirects` map; skip already-migrated rows.

### Per-task operator surface (post-migration)

```bash
# Add a new task at position 0.2.0.05 (shifts 0.2.0.05+ down by 1):
.claude/naavik-ops task insert 0.2.0.05 "AI extraction retry policy" --effort M --priority MEDIUM

# Or defer an existing task (within same release):
.claude/naavik-ops task defer 0.2.0.07 --by 2

# Set priority on an existing task:
.claude/naavik-ops task prioritize 0.2.0.05 --to-priority HIGH

# Cross-release relocate:
.claude/naavik-ops task move 0.2.0.14 0.3.0.05

# Cross-version dep:
.claude/naavik-ops deps add 0.2.1.05 0.2.0.07

# Release ceremony:
.claude/naavik-ops release cut 0.2.0
```

A.29 Wave 1 ships read-only paths (`list`, `next-unblocked`, `check`, `bump`) + the release ceremony driver. Mutating per-task ops (`insert` / `defer` / `prioritize` / `move` / `renumber` / `rename-release`) are stubbed as `NOT_IMPLEMENTED` during A.29; A.30 (0.1.1) finishes them natively as part of the Python rewrite (since per-task ops on pre-migration IDs would require double-renumber logic — the migration runbook is the canonical bulk-mutation surface during A.29 transition).

---

## § 6 — Tooling integration

Callers that read the schema (must be updated when § 1 changes):

- **`.claude/naavik-ops`** entry point — Python dispatcher (executable). Routes `<group> <command>` per § 10.
- **`.claude/naavik_ops/gh.py`** — A.29: subprocess wrappers around `.claude/naavik_ops/gh.py`. A.30: native Python rewrite. Sort by 4-level task-ID + priority DESC; drift detection compares title + priority against ROADMAP; gate next-unblocked on deps.
- **`.claude/naavik_ops/memory.py`** — A.29: subprocess wrappers around `.claude/naavik_ops/memory.py`. A.30: native Python rewrite. Knowledge entries reference task IDs in body; redirects map preserves legacy lookups.
- **`.claude/naavik_ops/task.py`** — release-version task ops. Reads `.claude/github-issue-map.json:issues` + `priorities` + `deps`; emits sorted list / next-unblocked / check report.
- **`.claude/naavik_ops/release.py`** — 10-step ceremony driver (cut / dry-run / changelog).
- **`.claude/naavik_ops/deps.py`** — cross-task DAG with cycle rejection + flock serialization.
- **`.claude/naavik_ops/lib/semver.py`** — parse / compare / bump / regex.
- **`.claude/naavik_ops/lib/changelog.py`** — keepachangelog v1.1.0 reader/writer + Conventional Commits classification.
- **`.claude/naavik_ops/lib/github_api.py`** — GraphQL helper with **full `hasNextPage` pagination** (fixes the 200-item cap in `.claude/naavik-ops gh sync`).
- **`.claude/naavik_ops/gh.py`** (legacy, during A.29 transition) — `cmd_create_issue`, `cmd_next_unblocked`, `cmd_sync`, `cmd_backlog_by_epic` narrowed: `--priority` accepted on 4-level IDs only (warn-skip on 3-level); sort gains priority DESC primary.
- **`.claude/hooks/git/prepare-commit-msg`** — extended for Conventional Commits regex validation + auto-`Closes #N` from branch name. Branch regex accepts both 2-level (legacy) and 4-level (post-A.29) task IDs.
- **`pyproject.toml`** `[project] version` — written atomically by `naavik-ops release cut`. `naavik-ops task check` detects manual drift.
- **`nix/package.nix`** `version` attribute — same atomicity contract.
- **`.claude/agents/manager.md`**, **`.claude/skills/manager-*`**, **`.claude/commands/*`** — sort by release-version + priority DESC + 4-level lex; references updated to new schema; path refs `scripts/` → `naavik-ops`.
- **`docs/AGENT_OPS.md § 2.7a`** (NEW) + **§ 6** (GitHub Mirror conventions) + **§ 2.8** (commit-message hook + Conventional Commits) + **§ 14** (memory).
- **`docs/PLAYBOOK.md § H`** (CONTRACT_CHANGE list extended for `.claude/naavik_ops/**` + `.claude/migrations/**`) + **§ File classification** + **§ Hard rules** (#5).
- **`AGENTS.md § GitHub state — single writer rule`** — `.claude/naavik-ops` codified as new single-writer entry; underlying scripts may delegate during A.29 transition.
- **`.claude/github-issue-map.json`** — schema extension: `milestones` (per release-version), `epics` (per release-version), `issues` (4-level key → issue#), `redirects` (legacy → new ID), `deps` (cross-task graph), optional `priorities` (4-level ID → HIGH|MED|LOW), optional `statuses` (4-level ID → roadmap-status-letter).
- **`scripts/README.md`** (NEW) — documents the `.claude/naavik_ops/` (agent-system tooling) vs `scripts/` (project-wide) convention split.
- **`CHANGELOG.md`** (NEW, A.29 migration apply) — keepachangelog v1.1.0 + Conventional Commits auto-classification.

### External-tool semver consumers

External tools that expect strict semver 2.0.0 (`pip install`, Docker tags, `nix flake` version pinning) must strip the 4-level position suffix when passing the version through. Document this caveat inline at the version reference site (e.g. `pyproject.toml` comment + `nix/package.nix` comment). Within Naavik's own tooling, the 4-level form is canonical for task IDs; 3-level for release versions.

---

## § 7 — Threats

| Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Two operators run `naavik-ops task insert` concurrently | Low | Medium | `fcntl.flock` on `~/.naavik/naavik-ops.lock` serializes; second invocation blocks until first releases. |
| New fork inherits stale schema | Low | Low | `.claude/migrations/A.29-phase-renumber.py` is idempotent; re-run on fork sees existing schema + no-ops. |
| Future task lands on a freed slot of a frozen done ID | Medium | High | `naavik-ops task insert` rejects with diagnostic; operator picks next-available slot. Test asserts (A.30 builds the mutating subcommands). |
| Issue title rewrite fails mid-batch (cross-release `move`) | Low | High | `.tmp` write pattern + rollback if any single rewrite fails. Migration script step 6 idempotency via `redirects` key check. |
| GraphQL pagination cap (200 items) | Medium | Medium | Full-pagination helper in `naavik_ops/lib/github_api.py` (vs. existing `gh-project.sh` which caps at 200). Tested up to 250 items. |
| Operator edits Issue title manually in GitHub UI | High | Low | `naavik-ops task check` detects drift on next invocation; `sync --apply` overwrites to match ROADMAP. |
| Cycles in deps DAG | Low | Medium | `naavik-ops deps check` verifies — refuses to add an edge that creates a cycle (cycle check after mutation, rolls back). |
| Partial migration — Wave 2.X script aborts mid-flow | Low | High | Idempotent steps + redirects-key-based skip. Re-run continues from last successful step. |
| `pyproject.toml` / `nix/package.nix` desync between releases | Medium | Medium | `naavik-ops task check` detects; `release cut` is the only sanctioned bump path. |
| Conventional Commits hook regressing existing BOOKKEEPING styles | Medium | Medium | Branch-aware enforcement — strict on feature branches, lenient on `main`. Bypass via `--no-verify`. |
| Operator runs `release cut 0.2.0` while open `0.2.0.NN` task exists | Low | High | Pre-flight gate (step 1) fails fast; documented in § 2 invariants. |
| Tag-vs-pyproject drift via manual edit between releases | Medium | Medium | `check` reads all three sources (pyproject, nix/package.nix, latest tag); exits non-zero on mismatch. |
| CHANGELOG.md merge conflict during parallel release ops | Very low | Low | Single-engineer + flock; won't happen in practice. |
| Python shebang fails on non-Nix env | Low | Medium | Document Nix devshell as supported env; shebang `#!/usr/bin/env python3` defers to PATH discovery; macOS users have python3 via brew. |
| Subprocess wrapper leaks bash error semantics | Medium | Medium | Wrappers translate `subprocess.CalledProcessError` to `NaavikOpsError` with stderr captured. Parity tests in `tests/test_naavik_ops/test_gh_wrapper.py`. |
| Mid-A.29 bash script edits drift wrapper signatures | Medium | Medium | Subprocess wrappers are intentionally thin (just argv forwarding); signature changes in bash are visible immediately as wrapper exit-1. Hacker review at PR_REVIEW_GATE checks `git diff scripts/` for any signature change during A.29 review. |

---

## § 8 — Future

### When MAJOR bumps to `1.0.0`

User-signaled at the Phase 6 / "first MVP-public-ready" cut, OR earlier if scope matures. Until then all work is `0.X.Y.NN`. The `release` ceremony enforces breakage-detection-via-Conventional-Commits (`BREAKING CHANGE:` footer → forces MAJOR post-1.0; allowed in MINOR pre-1.0).

### Agent-system-as-plugin separation

User signaled "agent system will go away from this repo and become its own plugin at a later time." When that split happens (probably post-1.0 or via Phase 2.5 / Phase 3 separation), `naavik-agent-system` becomes its own package with its own semver. Until then, all `A.*` items (now folded into `0.1.0` retroactive) version with the main package.

After split: redirects entries for affected items get a `_meta.plugin_origin` field pointing to the plugin's separate semver; plugin maintains its own CHANGELOG + release ceremony via its own `naavik-ops` instance. The schema in § 1 stays canonical for both; only the `redirects` map carries the cross-package pointer.

### Slot exhaustion (99 positions per release)

Unlikely for active releases (largest historic batch was Phase A at ~34 items; `0.1.0` historical fold lands ~50 positions per the D.1 Option B collapse rule). When hit, split into a follow-up PATCH (e.g. `0.2.0` exhausts → next batch becomes `0.2.0a` if a 25th-hour micro-patch convention emerges, OR more cleanly, the batch becomes `0.2.7`).

Migration: `naavik-ops task rename-release` handles bulk rewrites (A.30 ships this; A.29 stubs it).

### Project board UI Priority field

**PRESERVED.** Field populated only on TASK-level Issues (4-level IDs); patches and epics leave it empty. No cleanup needed. `naavik-ops task check` warns on drift between ROADMAP Priority column and Project Priority field.

### ROADMAP Priority column

**PRESERVED** as narrowed-role intra-release impact signal per § 1.

### LTS at 2.0+

Not in current scope. Deferred until user signal post-1.0.

### Distribution channels (dev / stable / beta)

Out of scope; user lock at plan REV-2.

### Pre-release tags (`0.2.0-rc.1`)

Explicitly dropped (user lock E3 in plan REV-2). Add when needed; not a hurdle.

---

## § 9 — Restructure

Scripts folder convention:

- **`.claude/naavik_ops/`** — Python package. Agent-system internal. Houses the dispatcher modules + shared lib (`flock`, `semver`, `jsonl`, `github_api`, `roadmap`, `changelog`).
- **`.claude/migrations/`** — One-shot historical migration runbooks (e.g. A.28 board restructure, A.29 phase renumber). Maintainer-only invocation; documented in PLAYBOOK.md as `.claude/migrations/**` CONTRACT_CHANGE files.
- **`scripts/`** at repo root — **Project-wide user-runnable scripts only** (future build / deploy / test wrappers that the maintainer invokes directly). Empty initially after A.30 (no project-wide scripts exist today). Documented in `scripts/README.md`.

### Transition state during A.29 (locked per plan D.21)

- `.claude/naavik_ops/gh.py` (1469 LOC bash) — STAYS at current path. Subprocess-wrapped by `.claude/naavik_ops/gh.py`.
- `.claude/naavik_ops/memory.py` (843 LOC bash) — STAYS at current path. Subprocess-wrapped by `.claude/naavik_ops/memory.py`.
- `scripts/A.28-board-restructure.sh` — MOVED to `.claude/migrations/A.28-board-restructure.sh` in Wave 2 of A.29 (one-shot historic).
- `.claude/naavik_ops/lib/roadmap.py` (304 LOC Python) — STAYS at current path during A.29; A.30 rolls into `.claude/naavik_ops/lib/roadmap.py`.

### End-state after A.30 ships (0.1.1)

```
.claude/
├── naavik-ops                       # executable Python entry point
├── naavik_ops/
│   ├── cli.py task.py release.py deps.py gh.py memory.py
│   └── lib/ flock.py github_api.py jsonl.py roadmap.py semver.py changelog.py
└── migrations/
    ├── A.28-board-restructure.sh    # historic bash one-shot (preserved)
    └── A.29-phase-renumber.py       # Python migration runbook

scripts/
└── README.md                        # documents convention; empty until project-wide scripts land
```

### Subprocess wrapper pattern (A.29 implementation)

```python
# .claude/naavik_ops/gh.py (A.29 version)
"""GitHub state subcommand group.

During A.29 transition: subprocess wrappers around .claude/naavik-ops gh.
A.30 (0.1.1): native Python rewrite — drop these wrappers.

Bash error semantics: .claude/naavik-ops gh uses `set -euo pipefail` so any
non-zero exit propagates via subprocess.run(check=True) → CalledProcessError.
We re-raise as a Python-native NaavikOpsError with the bash stderr captured.
"""
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "gh-project.sh"


class NaavikOpsError(RuntimeError):
    """Wrapped bash error from a subprocess shim."""


def _shim_capture(*args: str) -> str:
    """Invoke .claude/naavik-ops gh with args; return stdout."""
    try:
        result = subprocess.run(
            ["bash", str(SCRIPT_PATH), *args],
            check=True, capture_output=True, text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise NaavikOpsError(
            f"gh-project.sh {' '.join(args)} failed (exit {e.returncode}): {e.stderr}"
        ) from e


def cmd_set_status(rest):
    return _shim_capture("set-status", *rest)
```

The wrapper is intentionally thin — no business logic, just argument forwarding + error translation. A.30 will replace `_shim_capture` calls with native Python equivalents (gh CLI subprocess for one-shot commands; httpx for GraphQL with full pagination via `lib/github_api.py`).

---

## § 10 — Dispatcher

`.claude/naavik-ops` is the executable Python entry point. Subcommand groups + routing per plan D.22:

### Subcommand groups

```
.claude/naavik-ops <group> <command> [args]

Groups:
  task     list / insert / defer / prioritize / move / renumber / check / bump / sync / next-unblocked
  release  cut / dry-run / changelog
  deps     add / remove / list / check
  gh       bootstrap / init / set-status / set-priority / set-effort / next-unblocked /
           create-issue / create-epic / create-milestone / refresh-map / sync / item-id /
           backlog-by-epic / add-status / runs
           (A.29 ships as subprocess wrappers; A.30 rewrites in Python)
  memory   init / record-decision / record-discussion / record-knowledge / record-lesson /
           list / query / analyze-run / mine-patterns / promote-lesson / update-index
           (A.29 ships as subprocess wrappers; A.30 rewrites in Python)

Direct (no group):
  --help, --version
```

Each group is a Python module (`task.py`, `release.py`, `deps.py`, `gh.py`, `memory.py`). Each command is a `cmd_<name>` function. Dispatcher (`cli.py`) does argparse + module load + function dispatch.

### Entry point implementation

```python
#!/usr/bin/env python3
"""naavik-ops — agent-system operations dispatcher."""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from naavik_ops.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

### Dispatcher implementation

```python
"""naavik-ops CLI dispatcher."""
from __future__ import annotations
import importlib
import sys
from collections.abc import Sequence

from naavik_ops import __version__

GROUPS: dict[str, str] = {
    "task":    "naavik_ops.task",
    "release": "naavik_ops.release",
    "deps":    "naavik_ops.deps",
    "gh":      "naavik_ops.gh",
    "memory":  "naavik_ops.memory",
}


def main(argv: Sequence[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        return _print_help()
    if argv[0] in ("-V", "--version"):
        return _print_version()

    group = argv[0]
    if group not in GROUPS:
        sys.stderr.write(f"naavik-ops: unknown group '{group}'\n")
        return 2

    # ... group --help / command dispatch ...
```

### Forbidden patterns

- **No CLI extension to `naavik`** (e.g. `naavik task list` is FORBIDDEN — that's a CLI subcommand; the sunset rule applies per `ROADMAP.md § Phase 2 task 2.11`).
- **No vault extension** under any subcommand group.
- **`naavik-ops` is sibling to (not nested in) the user-facing `naavik` CLI.**

### Single-writer rule extension

`.claude/naavik-ops` is the new single-writer entry point per AGENTS.md § GitHub state — single writer rule. Documented in D.13 caller rewrite for `AGENTS.md`. During A.29, the actual writes still go through `.claude/naavik_ops/gh.py` + `.claude/naavik_ops/memory.py` via subprocess; A.30 inlines.

### Lock file

`~/.naavik/naavik-ops.lock` — `fcntl.flock`-protected pidfile. Mirrors `.claude/naavik-ops memory:.claude/memory/.lock` pattern semantically (single-writer serialization). Different path from agent-memory's lock (no collision). Different path from `~/.naavik/secrets.enc.lock` (vault — Phase 2 task 2.12 sunset).

Migration lock at `~/.naavik/A.29-migration.lock` is separate from the main `naavik-ops.lock` — one-shot migration apply isolates from day-to-day mutations.

---

## Cross-references

- **Implementing plan:** `docs/plans/archive/24-A.29-phase-numbering-system.md` (post-merge).
- **Migration runbook:** `.claude/migrations/A.29-phase-renumber.py` (ships in A.29 PR; applies post-merge via Wave 5).
- **A.30 follow-up:** ROADMAP.md:469, Issue #72, MEDIUM, ships as `0.1.1` — Python rewrite of legacy bash scripts.
- **A.27 future:** `develop` branch workflow move; deferred to a future `0.2.X` thematic patch-epic. Owns the release-branch decision.
- **AGENTS.md § GitHub state — single writer rule** — codifies dispatcher as new single-writer entry.
- **docs/AGENT_OPS.md § 2.7a** — operator surface for `naavik-ops`.
- **docs/PLAYBOOK.md § H** — `.claude/naavik_ops/**` is CONTRACT_CHANGE; PR required.
- **`keepachangelog.com/en/1.1.0/`** — CHANGELOG.md format spec.
- **`semver.org/spec/v2.0.0.html`** — semver spec; 4-level is non-strict extension.
