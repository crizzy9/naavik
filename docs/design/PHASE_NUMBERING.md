# Phase Numbering — 4-level semver task-ID schema for Naavik

> **Status:** SKELETON (graduates from `docs/plans/24-A.29-phase-numbering-system.md` on PLAN_GATE approve).
> **Authored:** 2026-05-18 (skeleton REV-3)
> **Last updated:** 2026-05-18 (REV-3 — priority narrowed-role + single 0.1.0 fold + Python dispatcher + scripts restructure)
> **Implements:** A.29 (post-migration ID: `0.1.0.<NN>` per REV-3 single-fold). ROADMAP.md:468. Issue #71.
> **Canonical plan:** `docs/plans/archive/24-A.29-phase-numbering-system.md` (post-archive).
> **Sole writers:** `.claude/naavik-ops` (Python dispatcher — task-ID + release-version mutations + Issue/Project/Milestone via subprocess wrappers around `scripts/gh-project.sh` during A.29; native Python in A.30). Single-writer rule extends to the dispatcher entry point.

Body lands on PLAN_GATE approve. Section stubs below capture the contract surface — full prose graduates from the plan's § D content.

---

## § 1 — Schema

Task IDs follow a **4-level semver-aligned schema**:

```
<MAJOR>.<MINOR>.<PATCH>[.<POSITION>]
```

- **3-level** (`<MAJOR>.<MINOR>.<PATCH>`) = a **release version**. e.g. `0.1.0` (pre-Phase-2 bundle covering Phase 0 + Phase 1 + PC + A.1–A.29), `0.1.1` (A.30 Python rewrite of legacy bash), `0.2.0` (Phase 2 scrapers), `0.2.1` (Phase 1 deferred security cleanup).
- **4-level** (`<MAJOR>.<MINOR>.<PATCH>.<POSITION>`) = a **task within a release**. e.g. `0.2.0.01`, `0.2.0.14`.
- Position component is **zero-padded two-digit** (`01..99`) for lex-sort stability. 99 slots per release MINOR. (D.1 Option B collapse rule applied to `0.1.0` — Phase 1 Waves 1–5 each get one position; sub-tasks fold into ROADMAP Notes prose.)
- **Position is NOT priority.** It is a forward-fill ID slot, not an ordering statement.

**Three orthogonal signals** (per D.4 REV-3):

1. **Position** — canonical ID slot (forward-fill within a release).
2. **Priority** (HIGH / MEDIUM / LOW / unset) — canonical *intra-release impact signal*. Optional, sparse. **TASK-level only** (4-level IDs); patches and minor-releases never carry priority.
3. **Release version** — canonical cross-release sequence signal.

**Regex:** `^\d+\.\d+\.\d+(\.\d{2})?$`

**Reading rule:**
- Release ordering: `0.1.0 < 0.1.1 < 0.2.0 < 0.3.0 < ... < 1.0.0`.
- Task ordering within a release: `priority DESC (HIGH > MED > LOW > unset) → position ASC`.
- `next-unblocked` sort key: `release-version ASC → priority DESC → position ASC`, gated by deps.

**Semver caveat:** 4-level IDs are a non-strict extension of semver 2.0.0. Consumers expecting strict 3-level semver (e.g. `pip install`) must strip the `.POSITION` suffix when calling external tooling. Document this in tooling integration § 6.

> Full content graduates from plan § D.1 + D.2 + D.4 + D.8 + D.14.

---

## § 2 — Releases

`.claude/naavik-ops release cut <version> [--no-tag]` bundles the **release ceremony** — 10 mechanical steps that today are scattered across `pyproject.toml` + `nix/package.nix` + git tags + GitHub Releases UI:

1. **Pre-flight gates.** Verify all sub-tasks under `[Epic] <version>` are `[x]`; git tree clean; `git tag --list <version>` empty; acquire `~/.naavik/naavik-ops.lock` flock.
2. **Compute CHANGELOG section** from closed Issues + PR squash subjects + Conventional Commits classification (§ 3).
3. **Update `pyproject.toml`** `[project] version` field.
4. **Update `nix/package.nix`** `version` attribute.
5. **Write CHANGELOG.md release section** (prepend new release block).
6. **Commit bookkeeping** — `chore(release): <version>` + body listing closed Issues + CHANGELOG breakdown.
7. **`git tag <version>`** — annotated tag with same body as release commit.
8. **Push tag to origin.**
9. **`gh release create <version> --notes-from-tag --generate-notes`.**
10. **Close the version's epic Issue** via composed `naavik-ops gh set-status` (subprocess wrapper → `scripts/gh-project.sh` during A.29; native Python in A.30).

**Invariants:**

- **Tags cut only at release ceremony.** PRs deliver at least one meaningful patch-level increment of work but do NOT cut tags individually. The `release cut` command is the sole sanctioned way to bump versions.
- **`pyproject.toml` + `nix/package.nix` versions synced atomically.** The release ceremony updates both in the same commit; `naavik-ops task check` detects drift between them + the latest tag.
- **`naavik-ops release dry-run <version>`** previews actions without mutating. **`--no-tag`** skips steps 7–9 (used for migration commits where the tag gets cut by the migration script separately).

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

**Initial content** generated by migration script (Wave 2.5, REV-3 simplified): ONE retroactive `0.1.0` release section covering everything pre-Phase-2 (Phase 0 + Phase 1 + PC.1–PC.7 + A.1–A.29). ~80 lines initial bootstrap. A.30 (0.1.1) appends its section when it ships.

> Full content graduates from plan § D.16.

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

**Subcommands** (under `.claude/naavik-ops deps`):

- `add <task-id> <dep-id>` — record `<task-id> blocked_by <dep-id>` + inverse `blocks` entry on `<dep-id>`. Idempotent.
- `remove <task-id> <dep-id>` — inverse.
- `list <task-id>` — print both `blocks` + `blocked_by` for the task.
- `check` — verify no cycles, no closed-blocking-open inversions, all referenced IDs exist in the issue map.

**Integration:** `naavik-ops task next-unblocked` (and underlying `cmd_next_unblocked` in `scripts/gh-project.sh` during A.29 subprocess-wrap) consults the deps store. A task is "blocked" if any entry in its `blocked_by` is `[ ]` or `[~]`. `next-unblocked` sort key per D.4 REV-3: **priority DESC → position ASC, ties broken by Issue number.**

**Cross-release deps** explicitly supported (`0.2.1.05 blocked_by 0.2.0.07` — a patch fix waits on a 0.2.0 task).

> Full content graduates from plan § D.17.

---

## § 5 — Migration

**One-time bootstrap** via `python .claude/migrations/A29_phase_renumber.py --apply` after this design doc graduates. Migration scope is full retroactive — every ROADMAP row + every GitHub Issue + every Milestone + every Project Epic + every plan-archive frontmatter + every agent-prompt embedded ID. Trace logs in `traces/<run-id>/` stay as-is (historic).

**13-step flow** (per plan § D.12 REV-3):

1. Pre-flight gates (no in-flight gates; git tree clean; acquire `~/.naavik/A.29-migration.lock` via `fcntl.flock`).
2. Compute target IDs for every existing row → rename map JSON. Priority column populated only for 4-level IDs per D.4 REV-3.
3. User confirmation gate.
4. Create new Milestones for each release-version (REV-3 simplified set: `0.1.0` + `0.1.1` + `0.2.0`–`0.2.6` + `0.3.0`–`0.6.0`).
5. Create new Project Epics for each release-version.
6. For each row in mapping table: rewrite Issue title (composed via `naavik-ops gh` subprocess wrapper) + update map cache + add to `redirects` dict + re-link Milestone + re-link Epic + set Project Priority field per REV-3 D.4 (4-level only) + log MIRROR event.
7. Rewrite `ROADMAP.md` — full release-version section restructure (everything pre-Phase-2 → `### 0.1.0` single section; Phase 2 → `### 0.2.0` sub-tasks; DEF → `### 0.2.1`–`### 0.2.6` thematic patches; Phase 3–6 → `### 0.3.0`–`### 0.6.0`; A.30 → `### 0.1.1`). D.1 Option B collapse rule applied to Phase 1 Waves.
8. Close superseded Milestones (`Pre-Phase-2 paper cuts`, `Phase A`, `Phase 1 deferred items`, `Phase 2.5`).
9. Rewrite plan archive frontmatter — every `docs/plans/archive/NN-*.md` `Implements:` line updates to new ID + `(was <old>, frozen)` parenthetical. Body unchanged.
10. Rewrite agent prompts + skills + commands + docs per caller-rewrite list (~35 sites REV-3). Includes path migration `scripts/gh-project.sh` → `naavik-ops gh` and `scripts/agent-memory.sh` → `naavik-ops memory`.
11. Bootstrap `CHANGELOG.md` — generate ONE retroactive `0.1.0` release section (~80 lines).
12. Verification — `naavik-ops task check` exits 0.
13. Commit migration as `chore(release): A.29 — phase numbering migration to semver + naavik-ops dispatcher`. Update `pyproject.toml` + `nix/package.nix` to `0.1.0`. Tag `0.1.0` post-merge.

**Per-task add flow** (operator surface, post-migration):

```bash
# Add a new task at position 0.2.0.05 (shifts 0.2.0.05+ down by 1):
.claude/naavik-ops task insert 0.2.0.05 "AI extraction retry policy" --effort M --priority MEDIUM

# Or defer an existing task:
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

> Full content graduates from plan § D.6 + D.7 + D.9 + D.10 + D.12 + D.14.2 + D.19.

---

## § 6 — Tooling integration

Callers that read the schema (must be updated when § 1 changes):

- **`.claude/naavik-ops`** entry point — Python dispatcher. Routes `<group> <command>` per D.22.
- **`.claude/naavik_ops/gh.py`** — A.29: subprocess wrappers around `scripts/gh-project.sh`. A.30: native Python rewrite. Sort by 4-level task-ID + priority DESC; drift detection compares title + priority against ROADMAP; gate next-unblocked on deps.
- **`scripts/gh-project.sh`** (legacy, during A.29 transition) — `cmd_create_issue`, `cmd_next_unblocked`, `cmd_sync`, `cmd_backlog_by_epic` narrowed: `--priority` accepted on 4-level IDs only (warn-skip on 3-level); sort gains priority DESC primary.
- **`.claude/naavik_ops/memory.py`** — A.29: subprocess wrappers around `scripts/agent-memory.sh`. A.30: native Python rewrite. Knowledge entries reference task IDs in body; redirects map preserves legacy lookups.
- **`.claude/hooks/git/prepare-commit-msg`** — extended for Conventional Commits regex validation (§ 7) + auto-`Closes #N` from branch name (existing).
- **`pyproject.toml`** `[project] version` — written atomically by `naavik-ops release cut`. `naavik-ops task check` detects manual drift.
- **`nix/package.nix`** `version` attribute — same atomicity contract.
- **`.claude/agents/manager.md`**, **`.claude/skills/manager-*`**, **`.claude/commands/*`** — sort by release-version + priority DESC + 4-level lex; references update to new schema; path refs `scripts/` → `naavik-ops`.
- **`docs/AGENT_OPS.md § 2.X`** (NEW — naavik-ops entry point) + **§ 6** (GitHub Mirror conventions) + **§ 2.8** (commit-message hook) + **§ 14** (memory).
- **`docs/PLAYBOOK.md § F`** (PRODUCT_WORK) + **§ File classification** (`.claude/naavik_ops/**` is CONTRACT_CHANGE — PR required).
- **`AGENTS.md § GitHub state — single writer rule`** — `.claude/naavik-ops` is the new single-writer entry; underlying scripts may delegate.
- **`.claude/github-issue-map.json`** — schema extension: `milestones` (per release-version), `epics` (per release-version), `issues` (4-level key → issue#), `redirects` (legacy → new ID), `deps` (cross-task graph).
- **`scripts/README.md`** (NEW) — documents the `.claude/naavik_ops/` vs `scripts/` convention split.

**Semver consumers external to Naavik** (`pip install`-style, Docker tag conventions) — strip the `.POSITION` suffix when passing through. Document caveat in `pyproject.toml` comment + `nix/package.nix` comment.

> Full content graduates from plan § D.13's ~35-row enumeration table.

---

## § 7 — Threats

| Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Two operators run `naavik-ops task insert` concurrently | Low | Medium | `fcntl.flock` on `~/.naavik/naavik-ops.lock` serializes; second invocation blocks until first releases. |
| New fork inherits stale schema | Low | Low | `.claude/migrations/A.29-phase-renumber.py` is idempotent; re-run on fork sees existing schema + no-ops. |
| Future task lands on a freed slot of a frozen done ID | Medium | High | `naavik-ops task insert` rejects with diagnostic; operator picks next-available slot. Test asserted. |
| Issue title rewrite fails mid-batch (cross-release `move`) | Low | High | `.tmp` write pattern + rollback if any single rewrite fails. Atomicity proof in `tests/test_naavik_ops/`. |
| GraphQL pagination cap (200 items) | Medium | Medium | Full-pagination helper in `naavik_ops/lib/github_api.py` (vs. existing `gh-project.sh` which caps at 200). |
| Operator edits Issue title manually in GitHub UI | High | Low | `naavik-ops task check` detects drift on next invocation; `sync --apply` overwrites to match ROADMAP. |
| Cycles in deps DAG | Low | Medium | `naavik-ops deps check` verifies — refuses to add an edge that creates a cycle. |
| Partial migration — Wave 2.X script aborts mid-flow | Low | High | Idempotent steps + redirects-key-based skip. Re-run continues from last successful step. |
| `pyproject.toml` / `nix/package.nix` desync between releases | Medium | Medium | `naavik-ops task check` detects; `release cut` is the only sanctioned bump path. |
| Conventional Commits hook regressing existing BOOKKEEPING styles | Medium | Medium | Branch-aware enforcement — strict on feature branches, lenient on `main`. Bypass via `--no-verify`. |
| Operator runs `release cut 0.2.0` while open `0.2.0.NN` task exists | Low | High | Pre-flight gate (step 1) fails fast; test asserts. |
| Tag-vs-pyproject drift via manual edit between releases | Medium | Medium | `check` reads all three sources (pyproject, flake, latest tag); exits non-zero on mismatch. |
| CHANGELOG.md merge conflict during parallel release ops | Very low | Low | Single-engineer + flock; won't happen in practice. Documented. |
| **(REV-3) Python shebang fails on non-Nix env** | Low | Medium | Document Nix devshell as supported env; shebang `#!/usr/bin/env python3` defers to PATH discovery; macOS users get python3 via brew. |
| **(REV-3) Subprocess wrapper leaks bash error semantics** | Medium | Medium | Pin script SHA in wrapper docstrings; CI test asserts script unchanged during A.29; document error-translation convention in `lib/__init__.py`. |
| **(REV-3) Mid-A.29 bash script edits drift wrapper signatures** | Medium | Medium | Wave 1.6 + 1.7 parity tests; hacker review checks `git diff scripts/` during PR_REVIEW_GATE. |

> Full content graduates from plan § Risk + mitigation rows (a)–(v).

---

## § 8 — Future

**When MAJOR bumps to `1.0.0`:** user-signaled at the Phase 6 / "first MVP-public-ready" cut, OR earlier if scope matures. Until then all work is `0.X.Y.NN`. The `release` ceremony enforces breakage-detection-via-Conventional-Commits (`BREAKING CHANGE:` footer → forces MAJOR post-1.0; allowed in MINOR pre-1.0).

**Agent-system-as-plugin separation:** user signaled "agent system will go away from this repo and become its own plugin at a later time." When that split happens (probably post-1.0 or via Phase 2.5 / Phase 3 separation), `naavik-agent-system` becomes its own package with its own semver. Until then, all A.* items (now `0.1.X` retroactive) version with the main package. After split: redirects entries point to the plugin's separate semver via the `_meta.plugin_origin` field on each affected redirect; plugin maintains its own CHANGELOG + release ceremony via its own `phase-tasks.sh` instance.

**When any release MINOR exhausts 99 slots:** unlikely for active releases (largest historic batch was Phase A at ~34 items; `0.1.0` historical fold may push toward 99 — see D.1 Option B collapse rule which keeps it ~50). When hit, split into a follow-up PATCH (`0.2.0` exhausts → next batch becomes `0.2.1`) OR split the MINOR cleanly. Migration: `naavik-ops task rename-release` handles bulk rewrites.

**Project board UI Priority field:** **PRESERVED under REV-3** per D.4 narrowed-role. Field populated only on TASK-level Issues (4-level IDs); patches and epics leave it empty. No cleanup needed.

**When ROADMAP Priority column drops:** **NEVER under REV-3** — column is preserved as the narrowed-role intra-release impact signal per D.4 REV-3. `naavik-ops task check` warns on drift between ROADMAP Priority column and Project Priority field.

**LTS at 2.0+:** not in current scope. Deferred until user signal post-1.0.

**Distribution channels (dev / stable / beta):** not in current scope. Out of scope per user lock in REV-2.

**Pre-release tags (`0.2.0-rc.1`):** explicitly dropped (user lock E3 in REV-2). Add when needed; not a hurdle.

> Full content lands on graduation. Add new threats / extensibility scenarios here as the schema accretes operational experience.

---

## § 9 — Restructure (NEW in REV-3)

Scripts folder convention per D.21 REV-3:

- **`.claude/naavik_ops/`** — Python package. Agent-system internal. The dispatcher entry point `.claude/naavik-ops` + subcommand group modules.
- **`.claude/migrations/`** — One-shot historical migration runbooks (e.g. A.28, A.29). Maintainer-only invocation.
- **`scripts/`** at repo root — **Project-wide user-runnable scripts only**. Empty initially after A.30.

**Transition state during A.29** (locked option B per D.21):

- `scripts/gh-project.sh` (1469 LOC bash) — STAYS during A.29. Subprocess-wrapped by `.claude/naavik_ops/gh.py`.
- `scripts/agent-memory.sh` (843 LOC bash) — STAYS during A.29. Subprocess-wrapped by `.claude/naavik_ops/memory.py`.
- `scripts/A.28-board-restructure.sh` (one-shot, done) — STAYS during A.29; A.30 moves to `.claude/migrations/`.
- `scripts/roadmap_parser.py` (304 LOC Python) — STAYS during A.29; A.30 rolls into `.claude/naavik_ops/lib/roadmap.py`.

**End-state after A.30 (0.1.1) ships:**

```
.claude/
├── naavik-ops                  # executable Python entry point
├── naavik_ops/                 # Python package
│   ├── cli.py task.py release.py deps.py gh.py memory.py
│   └── lib/ flock.py github_api.py jsonl.py roadmap.py semver.py changelog.py
└── migrations/
    ├── A.28-board-restructure.sh   (historic bash)
    └── A.29-phase-renumber.py      (Python)

scripts/
└── README.md                   (documents convention)
```

**Subprocess wrapper pattern** (A.29 implementation example):

```python
# .claude/naavik_ops/gh.py (A.29 version)
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "gh-project.sh"

class NaavikOpsError(RuntimeError): ...

def _shim(*args: str) -> str:
    try:
        result = subprocess.run([str(SCRIPT_PATH), *args],
                                check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise NaavikOpsError(f"gh-project.sh {' '.join(args)} failed: {e.stderr}") from e

def cmd_set_status(item_id: str, status: str) -> None:
    sys.stdout.write(_shim("set-status", item_id, status))
```

A.30 replaces `_shim` calls with native Python equivalents (gh CLI subprocess for one-shot; httpx for GraphQL).

> Full content graduates from plan § D.21.

---

## § 10 — Dispatcher (NEW in REV-3)

`.claude/naavik-ops` executable Python entry point per D.22 REV-3:

**Subcommand groups + routing:**

```
.claude/naavik-ops <group> <command> [args]

Groups:
  task     list / insert / defer / prioritize / move / renumber / check / bump / sync / next-unblocked
  release  cut / dry-run / changelog
  deps     add / remove / list / check
  gh       (subprocess wrappers; A.30 native Python)
  memory   (subprocess wrappers; A.30 native Python)

Direct (no group):
  --help, --version
```

**Each group is a Python module** (`task.py`, `release.py`, `deps.py`, `gh.py`, `memory.py`). **Each command is a function.** Dispatcher (`cli.py`) does argparse + module load + function dispatch.

**Entry point implementation** (`.claude/naavik-ops`):

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

**Dispatcher implementation** (`.claude/naavik_ops/cli.py`):

```python
"""naavik-ops CLI dispatcher."""
import argparse, importlib, sys
from typing import Sequence

GROUPS = {
    "task":    "naavik_ops.task",
    "release": "naavik_ops.release",
    "deps":    "naavik_ops.deps",
    "gh":      "naavik_ops.gh",
    "memory":  "naavik_ops.memory",
}

def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="naavik-ops")
    parser.add_argument("group", choices=list(GROUPS.keys()) + ["--help", "--version"])
    parser.add_argument("command", nargs="?")
    parser.add_argument("rest", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    if args.group in ("--help", "--version"):
        return _handle_top_level(args.group)

    module = importlib.import_module(GROUPS[args.group])
    fn_name = f"cmd_{args.command.replace('-', '_')}"
    if not hasattr(module, fn_name):
        sys.stderr.write(f"naavik-ops {args.group}: unknown command '{args.command}'\n")
        return 2
    return getattr(module, fn_name)(args.rest) or 0
```

**Forbidden patterns** (REV-3 explicit):
- No CLI extension to `naavik` (e.g. `naavik task list` is FORBIDDEN — that's a CLI subcommand; the sunset rule applies).
- No vault extension under any subcommand group.
- `naavik-ops` is sibling to (not nested in) the user-facing `naavik` CLI.

**Single-writer rule extension:** `.claude/naavik-ops` becomes the new single-writer entry point per AGENTS.md § GitHub state — single writer rule. During A.29, the actual writes still go through `scripts/gh-project.sh` + `scripts/agent-memory.sh` via subprocess; A.30 inlines.

> Full content graduates from plan § D.22.
