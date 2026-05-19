# Changelog

All notable changes to Naavik are documented here. Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

(work in progress under `[Epic] 0.2.0`)


## [0.1.1] - 2026-05-19

Legacy bash → Python rewrite + native mutating `task` subcommands + CHANGELOG markdown sanitization + PR_REVIEW_GATE reviewer pairing refactor. Shipped via PR #91 (squash `494ffae`). Plan: `docs/plans/archive/25-0.1.1-bash-to-python.md`. 210 tests passing in `tests/test_naavik_ops/`.

### Added
- **Native `.claude/naavik_ops/gh.py`** (0.1.1.01 / Issue #72) — full Python rewrite of `scripts/gh-project.sh` (1469 LOC bash); 20 callable CLI subcommands (18 legacy + 2 new: `update-issue-title` + `close-issue`) + 1 new Python helper function `get_issue()`.
- **Native `.claude/naavik_ops/memory.py`** (0.1.1.01 / Issue #72) — full Python rewrite of `scripts/agent-memory.sh` (843 LOC bash); 12 subcommands; A.17 jq sandbox char allowlist + identifier deny-list ported byte-for-byte (`env` / `getpath` / `path` / `paths` / `input` / `inputs` / `setpath` / `delpaths` / `debug` / `stderr` / `$ENV`).
- **5 mutating `task` subcommands** (0.1.1.01 / closes A.29 Deviation 1): `insert` / `defer` / `prioritize` / `move` / `renumber` — atomic 3-store mutation (ROADMAP rewrite + Issue title rewrite + map cache update) under `~/.naavik/naavik-ops.lock` flock with mid-loop rollback (R2 guard). Stub `exit 2 NOT_IMPLEMENTED_YET` from A.29 removed.
- **`.claude/naavik_ops/lib/roadmap.py`** — inlines the 304-line `scripts/roadmap_parser.py` legacy parser; adds the writer half (`ReleaseRow` / `ReleaseDiff` / `parse_release_section` / `write_release_section` / `rewrite_atomic`).
- **`# PR review mode` section in `.claude/agents/architect.md`** (W6) — architect joins hacker as parallel reviewer at PR_REVIEW_GATE; plan-adherence / design-coherence / sunset-guard / surface-propagation checks documented.
- **`.gitignore`** — `.claude/worktrees/` added (PR #75 hacker LOW finding folded in).

### Changed
- **PR_REVIEW_GATE reviewer pairing**: `hacker + devops` → `hacker + architect` (W6 contract refactor). Devops moves to on-demand dispatch for build-gate failures / runtime debugging via `/triage-bug` + direct manager invocation; engineer continues self-running `devops-build-gates` skill pre-PR for ruff + pytest + manual QA.
- `.claude/naavik-ops gh` + `.claude/naavik-ops memory` are now native Python entry points (no subprocess shim around legacy bash). Single-writer rule preserved by code path — same dispatcher, faster.

### Removed
- `scripts/gh-project.sh` (1469 LOC bash) — replaced by `.claude/naavik_ops/gh.py`.
- `scripts/agent-memory.sh` (843 LOC bash) — replaced by `.claude/naavik_ops/memory.py`.
- `scripts/roadmap_parser.py` (304 LOC) — inlined into `.claude/naavik_ops/lib/roadmap.py`.
- `tests/test_agent_memory.sh` — replaced by `tests/test_naavik_ops/test_memory.py` (38 cases).
- `tests/test_naavik_ops/test_{gh,memory}_wrapper.py` — replaced by direct-impl tests.
- `scripts/` folder reserved for project-wide user-runnable scripts only (currently only `scripts/README.md`).

### Security
- **CHANGELOG markdown sanitization** (0.1.1.02 / Issue #74) — `ReleaseEntry.__post_init__` escapes CommonMark special chars + collapses whitespace + rejects CR; `parse_changelog` round-trip avoids double-escape via `ReleaseEntry.from_rendered`. Defends header smuggling + link injection in commit-message bodies once future closed-Issue ingestion wires (PR #73 hacker Finding 3 closed).
- Single-writer rule still enforced by deletion-of-alternative (legacy bash entirely removed; only native Python in `.claude/naavik_ops/` writes to state stores).

### Operations
- **Post-merge bookkeeping** uses the new `naavik-ops gh close-issue <N>` subcommand to close 6 stale pre-A.29 epics (#1 Phase A, #6 Pre-Phase-2 paper cuts, #9 Phase 2, #22 Phase 1 deferred items, #65 Phase 2.5, #76 [Epic] 0.1.0) per Issue #90 (`0.1.1.03`).

## [0.1.0] - 2026-05-18

First full bundle: Phase 0 foundation + Phase 1 MVP + Pre-Phase-2 paper cuts + Phase A agent-system bootstrap + this A.29 phase-numbering migration. All work pre-Phase-2 ships as `0.1.0`.

### Added
- **Phase 0 foundation** (2026-04-25): Nix flake devShell, pyproject.toml + uv lockfile, Dockerfile, Docker Compose, PostgreSQL with pgvector.
- **Phase 1 MVP** (2026-05-03): user auth (bcrypt + JWT + CSRF), profile intake, settings UI, Typst PDF generation, LLM provider abstraction (Anthropic + OpenAI + Ollama), self-hosted single-user mode, Docker Compose deployment, `nix develop` orchestrator.
- **Pre-Phase-2 paper cuts** PC.1–PC.7.
- **Phase A agent system bootstrap** A.1–A.10 (2026-05-16).
- **Phase A v2** A.11–A.12 (2026-05-16).
- **Phase A tracing + memory** A.13–A.17 (2026-05-17).
- **Phase A board restructure** A.28 (2026-05-17).
- **Phase A machine-readable rewrite** A.16 (2026-05-18).
- **Phase A phase numbering** A.29 (2026-05-18, this release): `.claude/naavik-ops` Python dispatcher + `.claude/naavik_ops/` package.

### Changed
- Migrated all task IDs and ROADMAP rows to 4-level semver schema (`MAJOR.MINOR.PATCH[.POSITION]`). Legacy IDs preserved via `.claude/github-issue-map.json:redirects` map.
- GitHub Project Priority field role narrowed: optional intra-release impact signal at TASK level only.
- `scripts/` folder reserved for project-wide user-runnable scripts only.

### Security
- `SECRET_KEY` enforcement at module-import time (PC.5).
- Password complexity + must-change-on-first-login (PC.6).
- Broader `require_password_complete` gate (PC.6a).
- `scripts/agent-memory.sh` hardening (A.17 + A.17a).
