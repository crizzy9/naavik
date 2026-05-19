# Changelog

All notable changes to Naavik are documented here. Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

(work in progress under `[Epic] 0.2.0`)


## [0.1.1] - 2026-05-19

Release bundle for 0.1.1. Detailed entries reconstructed from closed Issues post-merge.
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
