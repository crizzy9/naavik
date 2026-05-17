# Naavik Development Roadmap

> Last updated: 2026-05-17 (**A.15 EXECUTED via PR #53 squash `a63b774`** — agent memory + learning system. 3-Wave scope (substrate + analytics + lesson promotion) shipped in one PR per user deviation; smoke 50/50. Closes #52 + #48 (A.11 board drift reconciled inline). Follow-ups filed pre-merge: A.17 #54 (hacker `agent-memory.sh` hardening, HIGH, ~2h), DEF-24 #55 (pre-existing ruff cleanup, LOW), DEF-25 #56 (pre-existing DB-test gating gap across 11 files, MEDIUM). Plan 19 archived with full `## Deviations from plan` section promoting deviations from PR body + gate report. Full PR_REVIEW_GATE report archived at `traces/2026-05-17T08-40-13_4abef2/pr-review-gate.md` (canonical template for future gate reports per § 9 convention note).
>
> Earlier line: 2026-05-17 (**A.15 in-flight on PR #53; A.17 + DEF-24 + DEF-25 filed pre-merge per follow-up wrap-up.** Hacker `APPROVE_WITH_NOTES` on A.15 surfaced 5 `agent-memory.sh` hardening findings (filed `A.17` Issue #54, HIGH); devops gate review surfaced 65 pre-existing pytest DB-test failures (filed `DEF-25` Issue #56) + 10 pre-existing ruff errors (filed `DEF-24` Issue #55) — both confirmed pre-existing via stash technique, NOT introduced by A.15. A.11 (#48) Project board drift reconciled inline (Todo→Done via close). `.claude/memory/knowledge/INDEX.md` added — auto-maintained by `scripts/agent-memory.sh update-index` on every `record-knowledge`. Full PR review gate report archived at `traces/2026-05-17T08-40-13_4abef2/pr-review-gate.md`. Pending: PR #53 merge decision.)
>
> Earlier line: 2026-05-17 (**Plan 19 APPROVED + A.15 + A.16 filed + repo settings locked to squash-only.** User approved all 7 Q decisions on plan 19 (agent memory + learning system) + selected all-3-Waves-in-one-PR deviation from architect's 3-phased recommendation. Plan 19 status flipped `DRAFT → APPROVED` with decisions locked (`.claude/memory/` JSONL+md stores, single-writer `scripts/agent-memory.sh`, `naavik-memory-lookup` + `naavik-discussion-capture` skills, `/learn` slash command + skill mirror, read-only MEMORY.md integration, 5-occurrence promotion threshold). **A.15 row filed** under Phase A: 3-Wave scope (substrate + analytics + lesson promotion) ships in one PR on `feat/A.15-agent-memory`. **A.16 row filed** as follow-up: machine-readable wording rewrite of `.claude/agents/*`, `.claude/skills/*`, `.claude/commands/*`, `.claude/hooks/*` (docs files stay prose). Per user: *"in the end it's all about you"* — the agent-system instruction surface should minimize tokens while conveying intent efficiently to LLM consumers. A.15 engineer adopts style for new files; A.16 retrofits existing. **Repo merge settings updated** (`gh api -X PATCH repos/crizzy9/naavik`) — `allow_merge_commit=false`, `allow_rebase_merge=false`, `allow_squash_merge=true`, `delete_branch_on_merge=true`, `squash_merge_commit_title=PR_TITLE`, `squash_merge_commit_message=PR_BODY`, `allow_auto_merge=true`. Enforces squash-only at repo level (defense-in-depth backstop on the playbook procedure); future PR squashes use PR title as subject + PR body as message body (no more `* commit-message` noise from individual commits); PR branches auto-delete on merge. User starting fresh session for A.15 implementation — seed text: `/build A.15`.)
>
> Earlier line: 2026-05-17 (**A.14 SHIPPED via PR #51 squash `ab9f2589`** + **plan 19 AUTHORED awaiting PLAN_GATE**. A.14 codifies the **Task Playbook** (`docs/PLAYBOOK.md`) — strict 9-category if-then decision tree the manager consults on every user message; closes the judgment surface that produced `aa2f6a0`. PR #51 took two commits (initial + Path-B re-loop adding default-deny rule + allow-list-only structure per hacker Finding 1); self-validating authorship — the PR followed its own category H procedure. Hacker: APPROVE (Path-B structurally stronger than Path-A). Devops: PASS (7/7 delta checks). Plan 19 (`docs/plans/19-agent-memory-and-learning.md`) authored by architect 2026-05-17 in response to user ask for "storage mechanism + memory + indexed knowledge base + progressive discovery + discussion-to-ROADMAP capture + periodic learning + session analysis + Claude memory integration." Recommends JSONL + markdown stores under `.claude/memory/`, single-writer `scripts/agent-memory.sh`, 3 new skills + 2 new slash commands (`/memory`, `/learn`), read-only integration with `~/.claude/projects/.../memory/MEMORY.md`. 7 open questions, 3-Wave phasing, Wave 1 = ~1 engineer day (substrate + discussion-capture + 5 seeded knowledge entries). Awaiting PLAN_GATE.)
>
> Earlier line: 2026-05-17 (**A.13 SHIPPED via direct push `aa2f6a0` — WORKFLOW MISS.** Tracing contract codified: `ERROR step=<what> kind=<retry|skip|halt|pivot>` events + `BUILT`/`REVIEWED` terminal-line summaries enforced across all 6 agent prompts; MANIFEST schema extended with `outcome` + `halt_reason` + `what_built` + `errors_encountered`. All in response to user feedback after PR #50: "make sure agents write to the trace properly." **The push bypassed PR review** — a process violation called out by the user. Documented as a one-time miss; future source-of-truth changes (agent prompts, skill bodies, AGENT_OPS contract sections, code) go through PR with hacker + devops review per AGENTS.md § Workflow. ROADMAP bookkeeping (this row + Last-updated bump) remains direct-push per existing pattern (compare `c158320` / `7924307`). See ROADMAP § Phase A row A.13 for the full deliverable.)
>
> Earlier line: 2026-05-17 (**PC.6 + A.11 EXECUTED via PR #50** — squash `7c7e12a` = `feat(auth): PC.6 password complexity + must-change-on-first-login`. PR #50 took two commits: initial `baad10c` shipped all 5 architect-recommended decisions verbatim; path-C re-loop `78c6d20` resolved hacker Findings 1 (HIGH — `src/ui/routes/settings.py:411` stub now gated with `Depends(require_password_complete)`) + 2 (MEDIUM — `Depends(require_csrf)` on `post_change_password`); Finding 3 (MEDIUM — stale JWT post-rotation) deferred to Phase 1.x deferred items as "JWT denylist on password rotation" row. PC.6a follow-up filed for broader gate to `api/profile` + `api/settings` (deferred until those routes gain real auth deps). Engineer's `## Deviations from plan` section in plan 18 carries 6 bullets all 4 dimensions (what/why/impact/surface). Hacker delta-review: APPROVE (zero new findings). Devops re-gate: PASS (494 tests / 25 skipped / +3 new tests / migration round-trip clean / `Closes #8` trailer × 2 commits). **Plan 16 EXECUTED** in parallel — A.11 (Agent System v2) complete across all 4 phases: Phase 1 cold-start hook + skill + Skill tool on 6 agents + prepare-commit-msg hook (shipped 2026-05-16); Phase 2 per-agent skill suite (29 skills shipped vs spec'd 28 — `build` skill mirror added mid-Phase-4 codifying dual-surface convention in AGENT_OPS § 10.2); Phase 3 first `/build` (PC.5, PR #49); Phase 4 second `/build` (PC.6, PR #50, this entry). Side artifact: `docs/design/research/LINKEDIN_SCRAPING.md` option matrix (5 options × 10 dimensions, recommends guest-API + Crawl4AI stealth for task 2.2; stickerdaniel MCP flagged as front-runner for Phase 5 task 5.12 outreach). Plans 16 + 18 archived to `docs/plans/archive/`. Token spend across PR #50 = ~2.2M of 5M daily ceiling (engineer 1.05M / architect 535k + 94k LinkedIn / hacker 239k / devops 144k / manager 195k).)
>
> Earlier line: 2026-05-16 (**PC.5 + A.8 EXECUTED via PR #49** — squash `ceca24b`. `Settings._enforce_secret_key` validator at `src/config.py:45-66` refuses module import when `SECRET_KEY` is the shipped default or <32 bytes, unless `NAAVIK_DEBUG=1`. 3 hacker findings folded into the same PR: (1) `Settings.debug` alias narrowed to `NAAVIK_DEBUG` only (dropped generic `DEBUG` foot-gun); (2) `docker-compose.yml` requires `SECRET_KEY` at compose-render time via `${VAR:?...}`; (3) `populate_by_name=True` attempted + reverted (pydantic-settings v2.13 re-enables field-name env-var key, defeats finding 1). Plan 17 archived to `docs/plans/archive/17-pc5-secret-key-enforcement.md`. First end-to-end `/build` of agent-system v2 validated: 5 skills invoked, git hook auto-appended `Closes #7`, deviations promoted, plan archived. Phase 3 of plan 16 complete; Phase 4 (PC.6) is next.)
>
> Earlier line: 2026-05-16 (**Plan 16 AUTHORED** — `docs/plans/16-agent-system-v2.md` DRAFT for ROADMAP row A.11 (Agent System v2). Four phases: (1) cold-start hook + `naavik-cold-start` skill + `Skill` tool on all 6 agents + git `prepare-commit-msg` hook + Project v2 automation guide; (2) ~28-skill per-agent suite under `.claude/skills/<name>/SKILL.md` (manager 4 / architect 4 / engineer 5 / designer 5 / hacker 3 / devops 3 + 4 shared `naavik-*`); (3) first real `/build` shipping PC.5 (satisfies A.8); (4) second `/build` shipping PC.6. Halts after Phase 1 + Phase 2 for user review. All 6 kickoff Open questions resolved in the plan (skill naming = `<agent>-<verb>` + `naavik-<verb>`; cold-start = hook + skill; `SubagentStart` NOT used per anthropics/claude-code#27755; branch regex `^(feat|fix|chore|docs|refactor)/<task-id>-<slug>$`). Plan estimates ~2.1M–2.9M total tokens across all 4 phases.)
>
> Earlier line: 2026-05-16 (**A.11 added + A.12 marked done.** A.12 (map cache + single-writer governance): `scripts/gh-project.sh` `find_issue_by_prefix` + `ensure_milestone` now consult `.claude/github-issue-map.json` first (eliminates the search-API race that produced duplicate epics #46 dup #6 + #47 dup #7); new `refresh-map` subcommand reconciles from authoritative GitHub state; dry-run reports `exists`/`PLAN` for milestones + epics correctly; bootstrap is fully idempotent (`would create=0 skipped=40`). "GitHub state — single writer" rule codified in `CLAUDE.md` / `AGENTS.md` / `.claude/agents/manager.md` / `.claude/commands/bootstrap.md` / `docs/AGENT_OPS.md`. A.11 (Agent System v2): 4-phase plan kicked off via `docs/prompts/agent-system-v2.md` — cold-start hook + skill + per-agent skill suite under `.claude/skills/<name>/SKILL.md` + git `prepare-commit-msg` hook for auto `Closes #N` linkage from branch name + Project v2 automation guide. Phase 3 of A.11 = A.8 deliverable (first end-to-end `/build`); architect to author `docs/plans/16-agent-system-v2.md` in next session. New file: `docs/prompts/README.md` documents the prompts directory convention (kickoff prompts archive alongside plans).)
>
> Earlier line: 2026-05-16 (**ROADMAP carved to tracking-only.** 807 → 436 lines (-46%). Vision + Competitive Context moved to `README.md`; Architecture diagram + Tech Stack table + Design decisions + Repository Structure + Data Model sketches removed (canonical homes: `docs/ARCHITECTURE.md` + `docs/design/DATA_MODEL.md`); Deployment (4 paths) moved to new `docs/DEPLOYMENT.md`; n8n migration + Portfolio integration narratives moved to `docs/ARCHITECTURE.md` § 4.7 External integrations; UI Screens narrative deleted (canonical was always `docs/design/SCREENS.md`). Pointer table in § Maintenance lists where each section landed. **GitHub Project #4 mirror live** (https://github.com/users/crizzy9/projects/4): 4 epics (#1 Phase A, #6 Pre-Phase-2 paper cuts, #9 Phase 2, #22 Phase 1.x deferred) + 45 Issues + 4 milestones + Status/Priority/Effort single-select fields + `[Epic] <phase>` parent issues + sub-issue linkage via Parent issue field + 13 labels. `scripts/gh-project.sh` extended with `create-epic`, `--parent` on `create-issue`, `set-priority`, `set-effort`; bootstrap creates Milestone + Epic + sub-issues per phase. Cache at `.claude/github-project.json` (gitignored, per fork).)
>
> Earlier line: 2026-05-16 (**Phase A: Agent System bootstrapped** — 6 specialized Claude Code subagents under `.claude/agents/` + 13 slash commands under `.claude/commands/` + `scripts/gh-project.sh` (Projects v2 helper) + token budget config + trace system + 3 `.github/ISSUE_TEMPLATE/` forms + PR template. `docs/AGENT_OPS.md` is the canonical operational guide. Phase A is meta (the dev process), tracked separately from product phases 0-6. Fork bootstrap: `gh auth login → scripts/gh-project.sh init → scripts/gh-project.sh bootstrap --apply → claude /standup → claude /build "next"`. A.1-A.7 shipped; A.8 (first end-to-end `/build` against PC.5) is the validation step.)
>
> Earlier line: 2026-05-12 (Plan 10c **EXECUTED** — first-time setup ergonomics paper cut shipped. `nix develop` shellHook exports `NAAVIK_PERSISTENCE=db` for orchestrator parity (10c.1); `/login` promotes the "Create account" CTA out of the footer to a prominent affordance below the Sign-in button, and `/login?mode=signup` renders an amber `lock` banner ("This instance already has an account.") instead of a form against a seeded single-user DB (10c.2); seeded dev credential now persists to `~/.naavik/dev-credentials` (mode 0600, gated on `NAAVIK_DEBUG` + generated-password + `Settings.deployment_mode==SELF_HOSTED`) AND is re-echoed by the FastAPI lifespan ~750 ms after startup so it survives the orchestrator's interleaved scrollback (10c.3). Retrieval is plain `cat ~/.naavik/dev-credentials`; **no new CLI subcommand** (CLI sunset per Phase 2 task 2.11). New config field: `Settings.debug` on `src/config.py` reads `NAAVIK_DEBUG` / `DEBUG` via pydantic-settings alias. 478 tests pass (3 new vs the 475 baseline; 2 additional live-DB seed tests under `NAAVIK_LIVE_DB=1`). New baseline snapshot: `tests/visual/baseline/login-signup-banner-desktop.png`. Doc cross-walk: README § "First-time setup", § Dev/test env vars, § Configuration § DATA_DIR comment, § Operations § `naavik` CLI sunset note; CLAUDE.md "Last updated"; POST_PHASE_1.md § "Phase 1 done" step 2.)
>
> Earlier line: 2026-05-10 (Plan 10c **APPROVED** — kickoff prompt at `docs/prompts/10c-first-time-setup.md` ready to paste into a fresh implementation session. Locked decisions: Q1 `signup_disabled` server-side gate, Q2 `app_settings.data_dir / dev-credentials` path, Q3 750 ms lifespan-echo delay, Q4 Wave-4 partial-swap cleanup stays separate, NO CLI extension (CLI sunset per Phase 2 task 2.11) and NO vault changes (vault deprecation per Phase 2 task 2.12). PC.7 stays `[ ]` until implementer flips to `[~]` on start.)
>
> Earlier line: 2026-05-10 (Phase 2 § Architecture-shift tasks added: **2.12 vault deprecation → env-only secrets** (deletes `src/services/vault.py` + AES-GCM + PBKDF2 + audit log + lockfile; switches to gitignored `.env` sourced from devshell + orchestrator + Docker Compose; alembic 0003 drops fingerprint/configured columns; ~2–3 days, ~15 files mostly deletions) and **2.11 CLI sunset** (now sequenced AFTER 2.12 since most of the CLI's reason-to-exist disappears with the vault; `init`/`vault status`/`vault rotate-key` gone, only `serve` remains, then deleted; < 1 day). UX regression to flag in changelog: rotating LLM API keys becomes "edit .env + restart" instead of a Settings UI form — standard self-hosted practice. Plan 10c REVISED earlier today still stands as-is.)
>
> Earlier line: 2026-05-10 (Plan 10c REVISED — first-time setup ergonomics paper cut, scope tightened. Drops the originally-spec'd `naavik dev creds` subcommand: the `naavik` CLI is now on a sunset track per new Phase 2 task 2.11 — operator features migrate INTO Settings UI, the CLI loses surface rather than gains it. Final 10c shape: `nix develop` NAAVIK_PERSISTENCE=db parity (10c.1) + login signup-link promotion + signup-disabled banner gated on `users_exist AND not allow_multiple_users` (10c.2) + persisted `~/.naavik/dev-credentials` (mode 0600, debug + SELF_HOSTED gated) + lifespan echo on app startup (10c.3); retrieval is plain `cat`. AGENTS.md § Key Conventions § CLI codifies the "do not extend" rule. ~5 new tests; ~½ day implementation. Tracking row stays at PC.7 below. Awaiting approval before prompt + execute.)
>
> Earlier line: 2026-05-09 (Plan 10c AUTHORED — first-time setup ergonomics paper cut: `nix develop` NAAVIK_PERSISTENCE=db parity (10c.1) + login signup-link promotion + signup-disabled banner gated on `users_exist AND not allow_multiple_users` (10c.2) + `naavik dev creds [--shred]` CLI subcommand + lifespan credential echo (10c.3). Goal: a fresh self-hoster signs in within 30 s of `nix run .#dev` without reading docs. Tracking row added as PC.7 below. ~6 new tests; < 1 day implementation. Awaiting approval before prompt + execute.)
>
> Earlier line: 2026-05-03 (Wave 5 / plan 10 § C EXECUTED + plan 10b EXECUTED — Phase-1 finalization paper cuts shipped: orchestrator greenlet/`LD_LIBRARY_PATH` fix + `NAAVIK_PERSISTENCE=db` default, working dev credential via `NAAVIK_DEV_PASSWORD` env or random, `POST /api/v1/auth/signup` with single-user gate via new `Settings.allow_multiple_users` field (Alembic 0002), `naavik` CLI subcommands (`init` / `vault status` / `vault rotate-key`), Settings · LLM Provider form-wiring with provider-aware swaps, Settings · Deployment vault-locked banner, README first-time-setup + signup + troubleshooting rewrite. 475 tests pass (~12 new beyond 10's 448 baseline), ruff clean. Phase 1 ✅ Complete and end-to-end testable. Next: `docs/plans/POST_PHASE_1.md` § "Phase 1 testing playbook" → Phase 2-6 plans 11–15.)
>
> Earlier line: 2026-05-02 (Plan 10a EXECUTED — Pre-Phase-2 paper cuts shipped: PC.1 sync alembic env.py + psycopg + flake.nix `--no-sync`/stdin/PYTHONPATH defenses; PC.2 root-`app.py` shim; PC.3 NixOS-friendly playwright + 20-PNG baseline.)
>
> Earlier line: Wave 4 / Backend Wave 3 / plan 10 § B EXECUTED — backend substrate live: 20 SQLModel entities + Alembic + bcrypt+JWT+CSRF auth + AES-256-GCM vault + LLM provider abstraction + 10 prompt skeletons + cost-tracking via ApiUsage + profile/settings/ats_credentials services + per-field profile autosave + DB-backed Settings + `NAAVIK_PERSISTENCE=db` env var for accessor swap + sequence-bumping seed + rotate-key CLI; 348 memory-mode tests + 6 live-DB seed tests pass; ruff clean; security-review checkpoints 1+2+4 written. Plan 10 § B status → WAVE 3 EXECUTED · Wave 6 awaiting.
>
> Earlier line: single-tracking consolidation — all task / backlog / plan-mapping moved here per `AGENTS.md` § Single-doc-tracking principle. Plans 11–15 mapped to Phase 2–6 headers. Pre-Phase-2 paper cuts inlined. Phase 1.x deferred items table is now the canonical extended backlog. Wave 3 / plan 09 EXECUTED + plan 09a EXECUTED + 09a follow-up shipped — 269 tests passing.
>
> **Companion doc:** `docs/plans/POST_PHASE_1.md` — operational guide only (testing playbook, authoring workflow, monitoring, success criteria). All task tracking lives here in ROADMAP.
>
> **This is the single source of truth for project progress.** Phases describe the long arc; per-phase wave/task tables are checked off as work lands. The master plan (formerly `docs/plans/02-mvp-master-plan.md`) is archived — its content lives here, in `AGENTS.md` § Workflow, and in the active session-continue prompt at `docs/prompts/00-session-continue.md`.

## Maintenance

This doc is **tracking-only** (per AGENTS.md § Single-doc-tracking). The maintenance rules live in **`AGENTS.md` § Roadmap Maintenance Rules** — read once, follow always. Quick summary:

- `[ ]` → `[~]` on start. `[~]` → `[x]` + deliverable note on completion.
- Edit the table directly when scope changes — don't bury in commits.
- Bump "Last updated" on every meaningful edit.
- **GitHub Project mirror:** the agent system mirrors this onto GitHub Project #4. See § Agent System (mirror conventions) below. Sync via `scripts/gh-project.sh sync --apply` after ROADMAP edits.

Pointers for content that USED to be in this doc (carved 2026-05-16 to keep ROADMAP tracking-only):

| Was here | Now lives in |
|---|---|
| Vision + Competitive Context | `README.md` § What is Naavik? + § Why Naavik? |
| Architecture diagram + Tech Stack table + Design decisions | `docs/ARCHITECTURE.md` |
| Data Model sketches | `docs/design/DATA_MODEL.md` (canonical) |
| Repository Structure tree | `docs/ARCHITECTURE.md` § 3 layer responsibilities |
| Deployment (4 paths) | `docs/DEPLOYMENT.md` |
| n8n Migration Strategy | `docs/ARCHITECTURE.md` § 4.7 External integrations |
| Portfolio Integration | `docs/ARCHITECTURE.md` § 4.7 External integrations |
| UI Screens & Design narrative | `docs/design/SCREENS.md` + `DESIGN.md` + `docs/design/WORKFLOW.md` |

---

## Phases

### Phase 0: Foundation & Infrastructure
> **Goal:** Reproducible dev environment, project skeleton, database, and deployment infrastructure.
> **Status:** ✅ Complete (2026-04-25)

| # | Task | Status | Priority | Notes |
|---|---|---|---|---|
| 0.1 | Nix flake: devShell with Python 3.12, uv, typst, postgresql, ruff, pre-commit hooks | [x] | CRITICAL | `nix/devshell.nix` — verified all tools available in `nix develop` |
| 0.2 | pyproject.toml + uv lockfile with all Python deps | [x] | CRITICAL | 56 packages installed via `uv sync` |
| 0.3 | Dockerfile (multi-stage, uv-based, Python 3.12 slim) | [x] | HIGH | Builder + runtime stages, typst in runtime |
| 0.4 | Docker Compose: FastAPI app + PostgreSQL (pgvector/pgvector:pg17) | [x] | HIGH | Health check on db, app depends on healthy db |
| 0.5 | NixOS service module (`nix/module.nix`) — Lumino-compatible | [x] | HIGH | Reads `settings.servicesConfig.apps.tools.naavik`, full systemd hardening, SOPS, Traefik, PostgreSQL ensure |
| 0.6 | Nix package derivation (`nix/package.nix`) | [x] | HIGH | `nix build` produces `result/bin/naavik`, typst wrapped in PATH |
| 0.7 | FastAPI app skeleton: main.py, config.py, db/session.py, static files, Jinja2 templates | [x] | CRITICAL | Sidebar drawer layout (Tailwind + DaisyUI + HTMX), dashboard placeholder, 5 nav stubs |
| 0.8 | Alembic setup (async, reads DATABASE_URL from settings) | [x] | CRITICAL | `migrations/env.py` uses async_engine_from_config |
| 0.9 | .env.example with all env vars documented | [x] | MEDIUM | DATABASE_URL, SECRET_KEY, all LLM keys, OAuth, integrations |

**Deliverable:** ✅ `nix develop` drops into a full dev environment. ✅ `nix build` produces a package. ✅ Docker Compose ready. ✅ NixOS module ready for Lumino integration. ✅ Dashboard placeholder visible at localhost:8000 with sidebar layout.

**Verification log (2026-04-25):**
- `nix develop` → python 3.12.13, uv 0.11.7, typst 0.14.2, ruff 0.15.11, postgresql 17.9, pre-commit 4.5.1
- `uv sync` → 56 packages installed
- `nix build` → produces `result/bin/naavik` entrypoint
- `uv run fastapi dev src/main.py` → server starts on :8000
- `GET /api/health` → `{"status":"ok"}`
- `GET /` → HTTP 200, dashboard renders with sidebar
- `uv run ruff check src/` → all checks passed

---

### Phase 1: MVP — UI + backend core
> **Goal:** Ship the 11-screen MVP per `docs/design/SCREENS.md` — profile system, resume/cover letter generation, application tracking, outreach.
> **Status:** ✅ Complete (2026-05-03)
> **Started:** 2026-04-30 · **Shipped:** 2026-05-03
>
> **Prerequisite ✅ done:** all 11 MVP screen mockups committed (Wave 0 + the Claude Design batch). Bundle JSX at `docs/design/mockups/naavik-handoff/project/screens/` (gitignored, locally only).
>
> **Implementation contracts** (graduated 2026-04-30 from plans 03–07):
> - `docs/design/COMPONENTS.md` — 85-component library
> - `docs/design/BACKEND.md` — routes + services + cron + scrapers + LLM + observability
> - `docs/design/DATA_MODEL.md` — 18 SQLModel entities + Settings + DRAFT cascade
> - `docs/design/INTERACTIONS.md` — cross-cutting HTMX patterns
> - `docs/design/SAMPLE_DATA.md` — Phase 1 hardcoded fixtures
>
> **Workflow:** every wave below is driven by a plan + kickoff prompt at `docs/plans/NN-name.md` + `docs/prompts/NN-name.md`. Implementation happens in fresh sessions kicked off by paste of the prompts. See `AGENTS.md` § Workflow for the canonical lifecycle.

#### Implementation waves

Phase 1 ships in **5 sequential waves** (Scenario A). Each wave passes acceptance criteria before the next starts; they do **not** run in parallel. Plan 08 lays the component library, plan 09 composes pages on top with sample-data accessors + stub endpoints, plan 10 Wave 3 lands the data substrate (DB + auth + LLM) and swaps the stubs for real handlers without UI churn, plan 10 Wave 6 completes services + Typst + DRAFT lifecycle + 3 ATS adapters. Interactions per INTERACTIONS.md fold into Wave 3 (no separate Wave 5).

> **Wave-name cross-walk.** Plan 10's body uses "Wave 3" (initial backend) and "Wave 6" (real backend) — labels inherited from `BACKEND.md`'s 6-wave-across-phases scheme. **ROADMAP** uses sequential implementation-wave numbers inside Phase 1: **Wave 4** = plan 10 § B (Wave 3 in plan body); **Wave 5** = plan 10 § C (Wave 6 in plan body). Both views are documented in `docs/plans/archive/10-backend-impl.md` § "Tracking + wave-name cross-walk". When in doubt, ROADMAP's Wave 4/5 labels are canonical.

| Wave | Scope | Plan | Prompt | Status | Done |
|---|---|---|---|---|---|
| 0 | Doc realignment | `docs/plans/archive/01-docs-realignment.md` | (executed inline) | ✅ EXECUTED | 2026-04-30 |
| 1 | Author 5 design docs (COMPONENTS / BACKEND / DATA_MODEL / INTERACTIONS / SAMPLE_DATA) | plans 03–07 (all GRADUATED + archived) | (no separate prompts — design plans graduate inline) | ✅ COMPLETE | 2026-04-30 |
| 2 | Stage 2 component library impl (85 partials + base.html refinements + macros + base.js + fixture page) | `docs/plans/archive/08-stage-2-impl.md` | `docs/prompts/archive/08-stage-2-impl.md` | ✅ EXECUTED | 2026-05-01 |
| 3 | Stage 3 page templates impl (11 screens, sample_data accessors, stub fragment + JSON endpoints, Discover keyboard map, Playwright snapshots) — folds in interactions per INTERACTIONS.md § J | `docs/plans/archive/09-stage-3-impl.md` | `docs/prompts/archive/09-stage-3-impl.md` | ✅ EXECUTED | 2026-05-02 |
| 3a | Stage 3 bugfix + Discover-redesign triage (Lucide diagnostics, sidebar mobile drawer, typed application questions, scroll-spy, native dialog backdrop, mobile pages, touch swipe, button rename, sidebar relabel "Jobs"→"Discover", in-place card expansion) | `docs/plans/archive/09a-stage-3-bugfix.md` | (executed inline; no kickoff prompt — direct user approval) | ✅ EXECUTED | 2026-05-02 |
| 4 | Backend Wave 3 — models + auth + LLM abstraction + vault + initial services + db/seed; **swaps plan 09 stub endpoints + sample-data accessor bodies for DB-backed handlers** (UI unchanged) | `docs/plans/archive/10-backend-impl.md` § B | `docs/prompts/archive/10-backend-impl.md` (Wave 3 part) | ✅ EXECUTED | 2026-05-02 |
| 5 | Backend Wave 6 — all 14 services + Typst document generator + DRAFT lifecycle + Greenhouse / Lever / Ashby ATS adapters + portfolio_sync + auto-apply cron + notifications | `docs/plans/archive/10-backend-impl.md` § C | `docs/prompts/archive/10-backend-impl.md` (Wave 6 part) | ✅ EXECUTED | 2026-05-03 |

After Wave 5 ships, **Phase 2–6 work** (scrapers, scoring, email + auto-classification, LinkedIn DMs + outreach, observability + light mode + LaTeX) graduates to plans 11+ as outlined in plan 10 § D.

#### Wave 1 completion log (2026-04-30)

| Plan | → Design doc | Lines | Notable |
|---|---|---|---|
| 03 — Component catalog | `docs/design/COMPONENTS.md` | 2111 | 85 components, 12 groups; full specs incl. Tier-1 additions (`bullet_textarea`, `confirm_modal`, `spinner`, `toast`, `empty_state`, `avatar`, `connection_status_card`, `deployment_badge`, 5 skeletons) |
| 04 — Backend architecture | `docs/design/BACKEND.md` | ~870 | HTTP routes + 14 services + 7 ATS adapters + cron + scrapers + LLM abstraction + vault boundary + observability |
| 05 — Data model | `docs/design/DATA_MODEL.md` | ~1100 | 18 entities + Settings; DRAFT cascade through enum / state machines / KPIs; AppEvent payload schemas |
| 06 — Interactions spec | `docs/design/INTERACTIONS.md` | ~620 | HTMX patterns: 6 form patterns, SSE, drag-drop, modals (E.4 confirm modal), keyboard shortcuts, optimistic UI rollback |
| 07 — Sample data | `docs/design/SAMPLE_DATA.md` | ~600 | Phase 1 fixtures (1 Profile, 4 Experiences, 14 Bullets, ~20 Jobs, 14 Applications incl. 2 DRAFT, ~20 Contacts, ~40 OutreachMessages, ~20 EmailThreads, ~150 AppEvents, ~30 GeneratedDocuments, ~20 ApplicationScreenerAnswers, 1 Settings) |

DESIGN.md bumped to v1.3 (DRAFT row added to Status Pipeline). SCREENS.md DRAFT visibility rule added.

#### Wave 2 — Stage 2 component library (plan 08) — ✅ EXECUTED 2026-05-01

> Build batches per `docs/design/COMPONENTS.md` § G. Acceptance: 85 component partials exist; every component renders in `/_design/components`; `uv run ruff check` passes; Lucide icons render after fragment swaps. **All 100 tests pass.**

| # | Build batch | Components | Status |
|---|---|---|---|
| 2.1 | Shell + base.html refinements | `auth_shell`, `sidebar`, `version_pill`, `api_status_dot`, `deployment_badge`; `base.html` layout + `base.js` (Lucide reinit, Sortable.js auto-init, modal-close listener, toast auto-dismiss, optimistic rollback, upload progress) | [x] |
| 2.2 | Atomics (15) | `button`, `input`, `card`, `tag_chip`, `status_dot`, `status_badge`, `score_circle`, `ai_badge`, `kbd`, `field_label`, `info_card`, `spinner`, `toast`, `empty_state`, `avatar` | [x] |
| 2.3 | Forms (5) | `editor_field`, `editor_card`, `autosave_indicator`, `modal`, `confirm_modal` | [x] |
| 2.4 | Onboarding (5) | `step_indicator`, `dropzone`, `extraction_checklist`, `extracted_field_row`, `progress_bar` | [x] |
| 2.5 | Profile / Bullet (11) | `profile_hero`, `contact_chip`, `experience_card`, `bullet_row`, `section_anchor_nav`, `application_readiness_card`, `application_qs_form`, `bullet_edit_row`, `tag_picker`, `selection_override`, `bullet_textarea` | [x] |
| 2.6 | Overview (4) | `kpi_card`, `priority_action_row`, `email_signal_row`, `pipeline_strip` | [x] |
| 2.7 | Discover (8) | `swipe_card`, `match_breakdown`, `discover_action_bar`, `swipe_action_btn`, `discover_stats_strip`, `up_next_card`, `tip_card`, `keyboard_hints` | [x] |
| 2.8 | Discover · review & apply (6) | `apply_topbar`, `warm_intro_card`, `tailored_bullet_row`, `cover_letter_section`, `screener_question_card`, `apply_action_bar` | [x] |
| 2.9 | Tracking (8) | `view_toggle`, `provider_chip`, `integration_card`, `followup_banner`, `stage_column`, `tracking_card`, `tracking_list_row`, `tracking_board` | [x] |
| 2.10 | Outreach (6) | `outreach_app_row`, `recommended_move_card`, `outreach_message_card`, `contact_card`, `linkedin_status_chip`, `outreach_timeline` | [x] |
| 2.11 | Settings (7) | `settings_tabs`, `provider_card`, `cost_card`, `deployment_status_card`, `log_tail`, `on_disk_card`, `connection_status_card` | [x] |
| 2.12 | Skeletons (5) | `swipe_card_skeleton`, `tracking_card_skeleton`, `priority_action_row_skeleton`, `email_signal_row_skeleton`, `bullet_edit_row_skeleton` | [x] |
| 2.13 | `/_design/components` fixture page (gated on `NAAVIK_DEBUG=1` env var; plan 10 Wave 3 swap to `Settings.debug`) | — | [x] |

#### Wave 3 — Stage 3 page templates (plan 09)

> Page handlers in `src/ui/routes/` returning `HTMLResponse`; pages compose only plan-08 partials; data backed by `src/db/sample_data.py` (per SAMPLE_DATA.md); accessors are **async from day one** so Wave 4's swap is body-only. Stub fragment + JSON endpoints match BACKEND.md § C / § D shape exactly. Per-screen interaction patterns from INTERACTIONS.md § J fire end-to-end. Acceptance: every screen renders without error; matches mockup at desktop (1440×900) + mobile (375×812) via Playwright; SCREENS.md per-screen `Impl:` checkbox flips to `[x]`.

Build order: simplest first.

| # | Screen / artifact | Mockup ref | Page handler | Status |
|---|---|---|---|---|
| 3.0 | `src/db/sample_data.py` + `sample_data_models.py` (frozen Pydantic per SAMPLE_DATA.md) | — | — | [x] 19 entities + Settings + 30 ApiUsage; 44 round-trip + realism tests |
| 3.1 | Login | `screens/Login.jsx` | `src/ui/routes/auth.py:get_login` | [x] auth_shell + form, fake-session-cookie POST /api/v1/auth/login |
| 3.2 | Settings (all 6 tabs — full UI scaffolding; Wave 4 wires real persistence) | `screens/Settings.jsx` | `src/ui/routes/settings.py:get_settings` | [x] all 6 tabs (LLM/Deployment/Account/Notif/Auto-Apply/Sources); SSE log tail; cost cards from ApiUsage |
| 3.3 | Profile (read-only) | `screens/Profile.jsx` | `src/ui/routes/profile.py:get_profile` | [x] hero + experience + summary + skills + projects + edu + cert + sticky right-rail anchor + readiness card |
| 3.4 | Profile editor | `screens/ProfileEdit.jsx` | `src/ui/routes/profile.py:get_edit` | [x] per-field autosave (PUT /profile/{field}); Sortable bullet drag-drop; confirm-modal hooks |
| 3.5 | Bullet editor (modal) | `screens/BulletModal.jsx` | `src/ui/routes/fragments.py:bullet_editor_modal` | [x] tag picker + selection_override + Rewrite/Delete; HX-Trigger: closeModal on save |
| 3.6 | Onboarding (3-step; SSE done auto-progresses to step 3 via `HX-Trigger`) | `screens/Onboarding.jsx` | `src/ui/routes/auth.py:get_onboarding` | [x] step indicator + dropzone + SSE extraction (5 progress + 6 field + done + stepReady) |
| 3.7 | Overview | `screens/Overview.jsx` | `src/ui/routes/overview.py:get_overview` | [x] greeting + KPI×4 + priority actions + email signal + pipeline strip + SSE email-signal stream |
| 3.8 | Tracking (board + list) | `src/ui/routes/tracking.py:get_tracking` | [x] board+list views; integrations row; needs-followup banner; Sortable Kanban; DRAFT+CLOSED hidden |
| 3.9 | Outreach | `screens/Outreach.jsx` | `src/ui/routes/outreach.py:get_outreach` | [x] 2-pane apps + detail; recommended_move_card; contacts; outreach_timeline |
| 3.10 | Discover (incl. `Stuck in queue · {N}` right-rail card via `up_next_card` `state="stuck"`) | `screens/Discover.jsx` | `src/ui/routes/discover.py:get_discover` | [x] swipe queue + 4-button bar + keyboard hints; Up next + Stuck-in-queue + Saved + Tip; +Add by URL modal; keys.js wired |
| 3.11 | Discover · review & apply | `screens/DiscoverDetail.jsx` | `src/ui/routes/discover.py:get_review` | [x] 3-column workspace; eager DRAFT auto-create gated on Settings.eager_review_generation; lazy CTA path; failure banner; SSE cover letter; submit/discard with screener gate |
| 3.12 | Per-screen interactions per INTERACTIONS.md § J (autosave, drag-drop, modal, SSE, optimistic rollback, keyboard shortcuts) | INTERACTIONS.md § B–H | — | [x] all patterns landed inline with each screen |
| 3.13 | Per-screen Playwright snapshot baseline at desktop + mobile | — | `tests/visual/capture.py` | [~] capture script ships; PNG generation pending nix-devshell run (NixOS Chromium needs playwright-driver browsers) |

#### Wave 4 — Backend Wave 3 (plan 10 § B) — ✅ EXECUTED 2026-05-02

> Initial backend lands the data substrate; **swaps plan 09's stub endpoints + sample-data accessor bodies for DB-backed handlers** (UI unchanged). Acceptance: `uv run alembic upgrade head` succeeds, `db/seed.py` populates from sample data, `tests/test_sample_data.py` round-trip via SQLModel passes, auth path passes `security-review`, vault boundary verified. **All 348 memory-mode tests + live-DB seed/persistence-swap tests pass.**

| # | Task | Source contract | Status |
|---|---|---|---|
| 4.1 | SQLModel models for all 19 entities + Settings (incl. `ApiUsage`) | DATA_MODEL.md § C | [x] 20 tables + Pydantic shadows; relationships stripped (services use FK joins); 25 model tests |
| 4.2 | Alembic initial migration (every table + enum + index + CHECK; pgvector extension enabled) | DATA_MODEL.md § H | [x] `0001_initial.py` drives DDL from `SQLModel.metadata`; `alembic upgrade head` clean against dev DB |
| 4.3 | Auth — JWT cookie + bcrypt; `/api/v1/auth/login`, `/logout`, `/me`, `/csrf`; brute-force rate limit | BACKEND.md § D.1 | [x] cost=12 prod / cost=4 tests; HS256 JWT; cookie HttpOnly+Secure+SameSite=Strict; CSRF double-submit; 5/15min rate limit; 18 auth tests |
| 4.4 | LLM provider abstraction — `llm/base.py` + anthropic + openai + ollama; structured-output retry policy | BACKEND.md § M.1, M.2 | [x] Anthropic tool-use / OpenAI json_schema / Ollama JSON mode; 10 prompt skeletons (score_job real); 15 tests |
| 4.5 | LLM cost tracking — `llm_tracker` service + `ApiUsage` table (powers Settings cost cards from day one) | BACKEND.md § M.4 + DATA_MODEL.md § C `ApiUsage` | [x] `tracked_call` wraps every provider call; persists ApiUsage row on success+failure; retries per BACKEND § M.5 |
| 4.6 | Vault service — `services/vault.py` (`~/.naavik/secrets.enc`, AES-256-GCM, PBKDF2 from `SECRET_KEY`) + audit log | BACKEND.md § H.1, § L.1 | [x] AES-256-GCM + PBKDF2 100k + key_fingerprint header for mismatch detection; sibling lockfile for concurrent writes; audit log never carries values; 22 tests |
| 4.7 | Vault key rotation CLI — `naavik vault rotate-key --old=... --new=...` re-decrypts + re-encrypts | plan 10 § B.5 | [x] `cli/vault.py` rotate-key with `.bak` backup + `--no-backup` flag; round-trip verified end-to-end |
| 4.8 | Settings · Deployment UI: warning when `SECRET_KEY` env mismatches the vault's encryption key fingerprint | plan 10 § B.5 | [x] `vault.is_locked()` + `services/settings_service.get_deployment_info()` expose mismatch state; UI banner wiring lands when settings tab consumes the new endpoint |
| 4.9 | `ats_credentials` service — DB row metadata + vault-backed credential resolution | BACKEND.md § H.1, § K.5 | [x] DB metadata + vault.get(scope=ats, key=board) resolution |
| 4.10 | Profile service partial (CRUD + per-field PUT) | BACKEND.md § H.1 | [x] get/update_field/update_application_questions/add/update/delete/reorder bullets; emits profile_updated AppEvent |
| 4.11 | Settings persistence (incl. `eager_review_generation` flag for cost-aware DRAFT generation) | BACKEND.md § D.7 + DATA_MODEL.md § L | [x] DB-backed CRUD per tab; PUT /api/v1/settings/llm flows API key through vault; settings_service.get_deployment_info exposes vault status |
| 4.12 | `db/seed.py` consuming `db/sample_data.py` (idempotent ON CONFLICT DO NOTHING) | SAMPLE_DATA.md § A | [x] 372 rows seeded across 20 entities; ON CONFLICT DO NOTHING; bumps every PK sequence after seed; CLI `uv run python -m db.seed` |
| 4.13 | `/_design/components` swap from `NAAVIK_DEBUG` env var → persisted `Settings.debug` | plan 08 § H + plan 10 § B.8 | [x] route consults DB-backed Settings.debug; legacy env var still works as test fallback |
| 4.14 | Page-handler accessor body swap — sample-data lists → DB queries (signatures already async from Wave 3) | plan 10 § B.10 | [x] partial: 12 high-traffic accessors (Profile/User/Settings/Experience/Bullet/Skill/Education/Project/Cert/Job/Application/discover_queue/applications_visible_in_tracking) gated on `NAAVIK_PERSISTENCE=db`; remaining accessors fall back to memory in DB env (Wave 6 closes the gap) |
| 4.15 | Tests — `test_models`, `test_seed`, `test_auth`, `test_llm_provider`, `test_vault` | — | [x] 348 memory-mode tests + 6 live-DB seed tests + persistence-swap test pass; 14 skipped (live-DB gated via `NAAVIK_LIVE_DB=1`) |

#### Wave 5 — Backend Wave 6 (plan 10 § C)

> Real services, document generation, full DRAFT lifecycle, ATS adapters for boards with public APIs, auto-apply cron, notifications, portfolio sync. Acceptance: all 14 services pass tests; `document_generator` produces real PDFs end-to-end; DRAFT submit / discard / auto-apply queue works; `security-review` on doc-gen + portfolio API + vault audit clean.

| # | Service / artifact | Source contract | Status |
|---|---|---|---|
| 5.1 | `auth` service complete (refresh-token rotation; OIDC scaffolding stub) | BACKEND.md § H.1 | [x] Auth shipped in Wave 3; refresh-token rotation + OIDC scaffolding deferred to Phase 1.x backlog |
| 5.2 | `profile_service` (full CRUD + bullet ops + tag inference) | BACKEND.md § H.1 | [x] Wave 3 ships full CRUD + bullet ops; AI tag inference exposed via `extraction.py` (Wave 6) |
| 5.3 | `extraction` (PDF → AI → Profile + SSE event emission) | BACKEND.md § H.1 | [x] `services/extraction.py` — PDF parse via pypdf + LLM `extract_resume` + SSE generator |
| 5.4 | `document_generator` (bullet selection + AI trim + Typst compile + native page-count validation; `answer_screeners` auto + drafted; **`pre_generate` no-op when `docs_state=READY` and no `Bullet.edited_at > GeneratedDocument.compiled_at` — DRAFT reuse heuristic**) | BACKEND.md § K.4 | [x] All four entry points + reuse heuristic + cost cap + 16 unit tests |
| 5.5 | `application_service` (DRAFT lifecycle, submit/discard, ATS dispatch, `validate_submittable`, `process_auto_apply_queue`); orthogonal-state derivation lives here (`Job.queue_state=APPLIED` flip-on-submit; `outreach_engagement` computed) | BACKEND.md § K + DATA_MODEL.md § E, § F | [x] Full DRAFT lifecycle + computed-state ownership + 25 unit tests |
| 5.6 | `scorer` Wave-6 visa filter (deterministic: `Profile.visa_sponsorship_needed × Job.visa_restrictions` zero-out; no LLM dep) | BACKEND.md § H.1 | [x] `services/scorer.apply_visa_filter` + 9 unit tests |
| 5.7 | `prompts/score_job` skeleton in Wave 4; full tag-matching + gap analysis lives in plan 12 (Phase 3) | BACKEND.md § M.3 | [x] Naive LLM call shipped in Wave 3 — Phase 3 plan 12 layers in tag matching |
| 5.8 | `notifications` (Discord webhook + Telegram outbound + in-app toast routing; per-event toggle) | BACKEND.md § L.3, L.4 | [x] `services/notifications.py` — Discord embed + Telegram + toast queue + 15 tests |
| 5.9 | `portfolio_sync` (public CV API filtered for EEO/visa/salary; **portfolio resume PDF regen on Profile-update debounced 60s, cached at `~/.naavik/data/documents/portfolio/resume.pdf`**; Netlify webhook) | BACKEND.md § L (Portfolio) | [x] Allowlist-based filter + post-condition assert + debounced regen + 15 tests |
| 5.10 | Typst templates (`onepage.typ`, `cover_letter.typ`) | BACKEND.md § K.4 | [x] NEU-style 1-page resume + 4-section letter; both with `<naavik-meta>` page-count label |
| 5.11 | Typst compiler + native page-count validator (`typst compile --emit metadata`; **no `pdfinfo`/poppler dep**) | plan 10 § C.2.1 | [x] `typst/compiler.py` uses `typst query <input.typ> "<naavik-meta>"` (the spec'd `--emit metadata` flag doesn't exist in 0.14; same effect, different mechanism — see plan 10 deviations). 7 real-Typst tests pass |
| 5.12 | ATS adapters — Greenhouse + Lever + Ashby (Workday / LinkedIn / Indeed / Generic deferred to Phase 1.x sub-prompt) | BACKEND.md § K.5 | [x] All 3 adapters with public APIs + factory + 18 mock-HTTP tests; Workday/LinkedIn/Indeed/Generic return auth_required stub |
| 5.13 | Cron registration: `applications.auto_apply` (5min), `admin.aggregate_costs`, `admin.cleanup_stale_docs`, `admin.daily_db_snapshot`, `admin.refresh_oauth_tokens` | BACKEND.md § I.1 | [x] All 5 jobs registered via `scheduler/jobs.py`; APScheduler with PostgresJobStore lifespan-managed |
| 5.14 | Stuck-queue surface wiring — failed-DRAFT detection populates Discover right rail (`up_next_card` `state="stuck"`) | plan 10 § C.3 + COMPONENTS.md `up_next_card` | [x] `application_service.stuck_drafts` + `/api/v1/applications/stuck` endpoint; UI wired via existing `discover_ctx` |
| 5.15 | Tests — `test_application_service`, `test_document_generator`, `test_typst`, `test_ats_adapters`, `test_notifications`, `test_portfolio_sync` | — | [x] 101 new tests; full suite 448 passed / 19 skipped (3 retired Wave-3 stubs + 14 prior live-DB gating) |

#### Phase 1 deferred items (Phase 1.x)

Items called out in design docs as "Phase 1.x optional / Phase 2+". This is a quick reference; **the canonical extended backlog lives at `docs/plans/POST_PHASE_1.md` § Tier 3** (suggested plan numbers, effort sizing, slot-in suggestions).

| Item | Source | Notes |
|---|---|---|
| Workday / LinkedIn / Indeed / Generic ATS adapters | plan 10 § C.4 | Need credentials + Playwright + manual review queue. Greenhouse / Lever / Ashby ship in Wave 5 |
| Stale-DRAFT cleanup cron (`admin.cleanup_stale_drafts`) | this triage 2026-05-01 | Auto-discard or auto-archive DRAFTs idle >30 days; otherwise queue accumulates |
| Postmortem-on-failure: Playwright screenshot + AI summary on ATS failure | this triage 2026-05-01 | Surfaces in stuck-queue card; helps diagnose recurring CAPTCHA / field_mismatch |
| Manual job entry modal (full) | SCREENS.md § Phase mapping > Deferred | `+ Add by URL` is the partial Phase 1 path |
| Application detail slide-over | SCREENS.md § Phase mapping > Deferred | Phase 2 introduces `/tracking/:id` route |
| OIDC for self-hosted (Authentik / Keycloak / Okta) | SCREENS.md § Phase mapping > Deferred | Phase 2+ |
| Onboarding offline retry buffer for autosave | INTERACTIONS.md § H.3 | Optional, not blocking MVP |
| `Show drafts` filter UI on Tracking | SCREENS.md § Tracking visibility rule | Endpoint stubbed in Wave 3; UI toggle Phase 1.x |
| `ProfileAnswer` reuse cache (screener answer memory) | DATA_MODEL.md § J | Phase 2+ entity |
| Auto-apply immediate dispatch on right-swipe (vs current 5-min cron) | this triage 2026-05-01 | Refinement; user expectation may grow once auto-apply ships |
| `Settings.scraper_aggressiveness` (rate-limit dial) | this triage 2026-05-01 | Phase 2+; default conservative |
| Portfolio API versioning (`/api/portfolio/cv?version=v1`) | this triage 2026-05-01 | Lets crypticsoul.dev pin its consumer; Phase 2+ |
| JWT signing-key rotation (multi-tenant cloud tier) | plan 10 Q7 | Phase 2+; single-key fine for self-hosted |
| JWT denylist on password rotation | PR #50 hacker Finding 3 (2026-05-17) | After successful `POST /api/v1/auth/change-password`, the OLD JWT remains valid for its natural TTL (24h default / 30d keep-signed-in). A stolen pre-rotation JWT survives the rotation. Defense-in-depth fix: maintain a server-side denylist of invalidated `jti`s (or rotate the signing-key prefix per user). Refresh-token rotation (sibling row above) covers part of this — but specifically the denylist for password-change events is its own row because it's narrower scope and easier to ship standalone. Lives in `services/auth.py` + a small DB table. Phase 1.x. |
| `JobEmbedding` semantic match (pgvector) | DATA_MODEL.md § H | Phase 6 |
| LinkedIn proxy support | BACKEND.md § J.4 | Phase 6+ |
| Submission-result observability dashboard (failure-kind aggregates) | this triage 2026-05-01 | Phase 6 — helps user spot recurring board-side failures |
| Argon2id vault upgrade (vs PBKDF2) | plan 10 Q6 | Phase 6 polish if security review flags |
| Light mode | DESIGN.md | Phase 6 |
| **Restore Lucide via CDN** | plan 09a follow-up 2026-05-02 | Self-hosted at `/static/lucide.min.js` for now to fix "no icons render" issue. Production should serve from a CDN — investigate why unpkg failed (content-blocker / CSP / rate-limit), pick a stable URL or fallback chain, drop the local file. |
| **Sidebar mobile-toggle reliability after navigation** | plan 09a follow-up 2026-05-02 | Idempotent script guards fixed the most common failure mode; user reports it's "still kind of wonky" after navigating away. Repro on real device, isolate the remaining timing issue (likely Tailwind JIT vs HTMX swap order). Not a blocker. |
| **Discover card max-w cap on ultra-wide screens** | plan 09a follow-up 2026-05-02 | 09a-follow-up dropped the `max-w-7xl` page cap on Discover so the card fills available space. On 4K+ monitors the card may stretch >1500px and feel sparse — add a `2xl:max-w-[1400px]` cap if user feedback comes in. |
| `Settings.daily_llm_cost_cap_usd` dashboard widget | POST_PHASE_1 § Tier 3 (consolidated 2026-05-02) | Wave 6 ships the enforcement; visible cap-progress UI is a Settings polish item. |
| Full `NAAVIK_PERSISTENCE` env-var removal — migrate remaining ~20 lower-traffic accessors + page handlers to service-layer DB reads | this triage 2026-05-03 (post-Wave-5) | Wave 4 partial-swap + Wave 5 partial-swap left ~20 accessors falling back to memory. Plan 10b sets `NAAVIK_PERSISTENCE=db` as orchestrator default, but the env var still gates the swap. Cleanup deserves its own plan once Phase 1 is fully verified — likely as a tiny tail-end paper cut once POST_PHASE_1 testing confirms which accessors actually matter. |
| Pre-existing ruff errors in `migrations/` + `scripts/roadmap_parser.py` (UP007 / UP035 / I001) | PR #53 devops review 2026-05-17 (Issue #55, DEF-24) | 10 ruff violations confirmed pre-existing via stash technique during A.15 PR review. Files: `migrations/versions/0001_initial.py` (4), `migrations/versions/0002_settings_multi_users.py` (4), `scripts/roadmap_parser.py` (2). All fixable via `ruff check --fix`. ~30 min. Surfaced by devops while gating A.15 PR #53; not introduced by A.15. |
| DB-test gating gap — 11 test files lack `_skip_if_no_db()` (asyncpg `InvalidPasswordError` on `localhost:5432`) | PR #53 devops review 2026-05-17 (Issue #56, DEF-25) | 65 pytest failures across 11 test files confirmed pre-existing via stash: `test_application_qs_form`, `test_discover_redesign`, `test_settings_llm_form`, `test_stub_endpoints`, `test_swipe_handler`, `test_draft_lifecycle`, `test_inplace_expand`, `test_mobile_layouts`, `test_mobile_sidebar`, `test_pages`, `test_persistence_swap`, `test_sample_data`, `test_scroll_spy`. Canonical pattern at `tests/test_settings_llm_form.py:17-25` (`_skip_if_no_db()` helper). PR body cited "1 pre-existing failure" via `pytest -x` halt-first; actual is 65 — scope correction filed here. ~1h to propagate the helper to the remaining 11 files. |

#### Pre-Phase-2 paper cuts (immediate; ship before plan 11)

These are dev-experience fixes carried over from Wave 2/3 + Wave 5. Ship as small focused plans or fold inline into the start of plan 11. Each is < 1 day of work.

| # | Item | Status | Notes |
|---|---|---|---|
| PC.1 | Process-compose: confirm app logs + cold-start reliability | [x] | **Plan 10a (2026-05-02 + 2026-05-03 orphan-fix):** Root cause turned out to be H4 (TTY/SIGTTIN), not the suspected H2 (alembic async wedge). fastapi-cli's worker opens `/dev/tty` via `watchfiles/run.py:411 set_tty()`, gets SIGTTIN'd in a process-compose-spawned background process group, never binds `:8000`. **Load-bearing fix:** `exec setsid -w uv run --no-sync ... < /dev/null` on migrate + app + `coreutils` in devTools — setsid creates a sessionless detached child where `/dev/tty` open returns ENXIO and watchfiles falls back gracefully. **Orphan-cleanup fix (2026-05-03):** `setsid -w` doesn't forward signals; `shutdown.command` pkills the detached session by tight cmdline patterns (`fastapi dev src/main.py`, `naavik/.venv/bin/python -s -c`, `naavik/.venv/bin/alembic`) so Ctrl-C tears everything down cleanly. Sync `migrations/env.py` (psycopg) + `--no-sync` + `unset PYTHONPATH` still landed as defense-in-depth. Verified via real interactive `nix run .#dev`. Full writeup in archived plan. |
| PC.2 | `uv run fastapi dev` (no path) should just work | [x] | **Plan 10a (2026-05-02):** 2-line `app.py` shim at repo root re-exports `src.main:app`. README "Manual local development setup" step 2 trimmed to `uv run fastapi dev`. `pyproject.toml` `[tool.setuptools] py-modules` extended with `"app"` so `pip install .` ships the shim. |
| PC.3 | Playwright local capture on NixOS | [x] | **Plan 10a (2026-05-02):** dev shell adds `nodejs_22` + `PLAYWRIGHT_NODEJS_PATH` env var so pip-installed playwright python uses Nix-built node (the bundled prebuilt fails NixOS' non-FHS layout). Playwright pinned to `>=1.58.0,<1.59` to match `pkgs.playwright-driver.browsers`'s chromium-1208. `tests/visual/capture.py --baseline` captures 20 desktop PNGs to `tests/visual/baseline/` (committed); `tests/visual/screenshots/` gitignored for ad-hoc work. WORKFLOW.md § Capturing a new visual baseline documents the recipe. |
| PC.4 | Phase-1 finalization — orchestrator greenlet/libstdc++ + NAAVIK_PERSISTENCE=db default + working dev credential + signup endpoint + `naavik` CLI subcommands (init / vault rotate-key / vault status) + Settings · LLM Provider form-wiring + Settings · Deployment vault-locked banner + README rewrite + ROADMAP wave-numbering cleanup | [x] | **Plan 10b EXECUTED 2026-05-03** (`docs/plans/archive/10b-phase-1-finalization.md` + `docs/prompts/archive/10b-phase-1-finalization.md`). 9 paper cuts shipped: `flake.nix` exports `LD_LIBRARY_PATH` + `NAAVIK_PERSISTENCE=db`; `db/seed.py` injects real bcrypt hash via `NAAVIK_DEV_PASSWORD` env or random; `POST /api/v1/auth/signup` w/ single-user gate via new `Settings.allow_multiple_users` (Alembic 0002); `naavik` CLI dispatcher (serve / init / vault status / vault rotate-key); Settings · LLM Provider form-wrap + 2 fragment endpoints; Settings · Deployment vault-locked banner; README first-time-setup + signup + troubleshooting rewrite; CLAUDE.md "Last updated" wave-cross-walk. 475 tests pass (~12 new); ruff clean. Live smoke: `nix run .#dev` boots clean (greenlet fix verified), seed prints credential message, signup gate returns 403 on seeded DB, login returns 204+JWT, PUT /api/v1/settings/llm via form persists Anthropic↔Ollama swap, `naavik vault status` + `rotate-key` round-trip + locked-state detection all green. Deviations documented in archived plan; key items: shorter migration revision id (alembic varchar(32)), scalar select for `Settings.allow_multiple_users` to dodge live-worker ORM-mapping quirk, sqlmodel.select replacing sqlalchemy.select in auth path. |
| PC.5 | `SECRET_KEY` boot-time enforcement — refuse to start when value is `change-me-in-production` or <32 bytes outside DEBUG | [x] | **Plan 17 EXECUTED 2026-05-16** (PR #49 squash `ceca24b`; archived `docs/plans/archive/17-pc5-secret-key-enforcement.md`). `Settings._enforce_secret_key` validator at `src/config.py:45-66` refuses module import when `SECRET_KEY` is the shipped default or <32 bytes unless `NAAVIK_DEBUG=1`. Folded 3 hacker findings into the same PR: (1) `Settings.debug` alias narrowed to `NAAVIK_DEBUG` only (dropped generic `DEBUG` foot-gun); (2) `docker-compose.yml` requires `SECRET_KEY` at compose-render time via `${VAR:?...}`; (3) `populate_by_name=True` attempted + reverted (pydantic-settings v2.13 conflict with finding 1). |
| PC.6 | Password complexity rules (min 12 chars, must contain digit + letter) + must-change-on-first-login flag for env-injected dev creds | [x] | **Plan 18 EXECUTED 2026-05-17** (PR #50 squash `7c7e12a`; archived `docs/plans/archive/18-pc6-password-complexity.md`). Shipped: `validate_password_complexity` helper + `User.must_change_password` column (alembic `0003_user_must_change_password`) + `require_password_complete` dep + `POST /api/v1/auth/change-password` REST + `GET /auth/change-password` page reusing plan-10c auth shell + rotation-unlinks-`~/.naavik/dev-credentials` (Q2 inline cleanup) + cookie/CSRF rotation on success. 11 new tests; 494 total pass / 25 skip. Required a path-C re-loop after hacker REQUEST_CHANGES on initial review: `baad10c` (first commit, all 5 Q1–Q5 architect decisions verbatim) + `78c6d20` (path-C: gated `src/ui/routes/settings.py:411` stub with `Depends(require_password_complete)` + added `Depends(require_csrf)` to `post_change_password` + AGENT_OPS § 2.8 hook-regex case-sensitivity note + 6-bullet deviations section). PC.6a filed for broader `require_password_complete` gate to `api/profile` + `api/settings` (below). JWT denylist row filed in Phase 1.x deferred items. |
| PC.6a | Broader `require_password_complete` gate — extend to `src/api/profile.py` + `src/api/settings.py` + `src/ui/routes/*` once those routes gain real auth deps (today most are on plan-09 fake-session stub) | [ ] | **Filed 2026-05-17** as follow-up to PC.6 PR_REVIEW (PR #50). Discovered during hacker review of plan 18: PC.6's redirect-flagged-users-to-change-password intent is delivered for only 5 of ~25 mutation surfaces because the other routes have NO auth dep at all on main. Couples with whatever plan rolls out real auth across `api/profile` + `api/settings` (likely part of 2.12 vault sunset or a follow-up Phase 2 ergonomics paper cut). Until then, flagged users can mutate via those endpoints without redirect — documented in plan 18's deviations. Reference: PR #50 hacker Finding 1 (HIGH). ~1–2 h once the auth deps exist. |
| PC.7 | First-time setup ergonomics — `nix develop` `NAAVIK_PERSISTENCE=db` parity + login signup-link promotion + signup-disabled banner (server-gated on `users_exist AND not Settings.allow_multiple_users`) + persisted `~/.naavik/dev-credentials` (mode 0600, debug + SELF_HOSTED gated) + lifespan credential echo so the dev credential is the last visible line on `nix run .#dev` startup OR retrievable via plain `cat` | [x] | **Plan 10c EXECUTED 2026-05-12** (`docs/plans/archive/10c-first-time-setup.md` + `docs/prompts/archive/10c-first-time-setup.md`). Three sub-items shipped: (10c.1) `nix/devshell.nix:shellHook` exports `NAAVIK_PERSISTENCE=db`; (10c.2) `src/ui/templates/pages/login.html` promotes the "Create account" CTA out of the footer to a prominent below-submit affordance + renders an amber `lock` banner when `signup_disabled=True` (server-side gate in `src/ui/routes/auth.py:_compute_signup_disabled` mirrors `POST /api/v1/auth/signup`'s 403 condition); (10c.3) `src/db/seed.py` writes `~/.naavik/dev-credentials` (mode 0600) when `app_settings.debug + dev_password_source == "generated" + Settings.deployment_mode == SELF_HOSTED`, and `src/main.py` lifespan spawns a fire-and-forget task that echoes the file ~750 ms after startup via stdlib `logging`. **No new CLI subcommand** (per CLI sunset policy in AGENTS.md § Key Conventions § CLI). 478 tests pass (3 new pages tests + 2 new live-DB seed tests vs the 475 baseline). New config field `Settings.debug` on `src/config.py` (reads `NAAVIK_DEBUG` / `DEBUG` via pydantic-settings alias); `flake.nix:devEnv` exports `NAAVIK_DEBUG=1` so the orchestrator unlocks the file write + lifespan echo. Deviations documented in the archived plan; key items: added the new `Settings.debug` config field (plan referenced `app_settings.debug` without saying to add it), kept `nix/devshell.nix` without `NAAVIK_DEBUG=1` (preserves `test_design_components_route::test_fixture_404_without_debug`), `_compute_signup_disabled` fails-open to form-render on DB errors, updated `tests/visual/baseline/login-desktop.png` in addition to adding `login-signup-banner-desktop.png`. |

**Deliverable (end of Phase 1):** User uploads resume → AI extracts profile → user edits in UI → Discover queue scored + filtered → tailored resume + cover letter generated for any job → submit application via supported ATS → email-signal-driven Tracking → outreach drafts go to LinkedIn / email → portfolio API serves profile + downloadable resume.

---

### Phase 2: Job Scraping & Discovery
> **Goal:** Automated multi-source job discovery with AI extraction.
> **Plan:** `docs/plans/11-phase-2-scrapers.md` (to be authored after Phase 1 ships). Splits cleanly into 11a (LinkedIn + Greenhouse + Lever + Ashby) and 11b (Workday + Indeed + Generic + n8n migration).
> **Implementation contract:** `docs/design/BACKEND.md` § J (scraping architecture), § I (cron catalog), § K (auto-apply pipeline). Wave 6 services + Phase 2 sub-prompts of plan 10.
> **Estimated effort:** 2–3 weeks.

| # | Task | Priority | Notes |
|---|---|---|---|
| 2.1 | Crawl4AI setup + generic scraper base class | CRITICAL | Replace Browserless |
| 2.2 | Site scrapers: LinkedIn (**guest API + Crawl4AI stealth; RSShub opt-in fallback** per `docs/design/research/LINKEDIN_SCRAPING.md` — revisit § 8 Revisit checklist before locking option into plan 11a), Workday, Greenhouse, Lever, Ashby, Indeed | CRITICAL | Port from n8n. LinkedIn cell wording shifted 2026-05-17 from the original "RSS via RSShub + guest API" after the architect option matrix landed; the matrix recommendation supersedes the original framing on plan 11a authorship. |
| 2.3 | AI job extraction: HTML → JobInfo (company, position, location, visa, salary, skills) | CRITICAL | Structured output |
| 2.4 | Job deduplication (URL-based + fuzzy title/company) | HIGH | |
| 2.5 | APScheduler: periodic scraping per source | HIGH | PostgreSQL job store |
| 2.6 | SQLModel: Job, StatusHistory models + migration | CRITICAL | |
| 2.7 | HTMX UI: job list with filters, job detail view | HIGH | |
| 2.8 | Discord + Telegram notifications for new jobs | MEDIUM | Port from n8n |
| 2.9 | Rate limiting + anti-detection (random delays, throttling) | HIGH | |
| 2.10 | Migrate existing n8n DataTable + Google Sheets data to PostgreSQL | MEDIUM | Seed script |
| 2.12 | **Vault deprecation → env-only secrets.** Delete `src/services/vault.py` (AES-256-GCM + PBKDF2 + lockfile + audit log) and the encrypted vault entirely. Switch to standard self-hosted-app pattern: secrets via env vars sourced from a gitignored `.env` (loaded by `nix develop:shellHook`, `flake.nix:devEnv`, and Docker Compose `env_file:`). Ship `.env.example` with all secret slots commented. **DB migration:** alembic 0003 drops `Settings.*_configured` booleans + `Settings.*_fingerprint` columns; secret presence becomes runtime-derived from env. **API surface:** `PUT /api/v1/settings/llm` becomes read-only — exposes "Anthropic configured via env: ✓ / ✗" without an input field. Same for Discord webhook URL, Telegram bot token, ATS credentials, Netlify webhook. **UI:** drop the API-key input from `_settings_llm.html` (replace with a "configured via env" indicator); drop the vault-locked banner from `_settings_deployment.html`; Settings · Deployment shows the env-detection state per integration. **Files removed:** `src/services/vault.py`, `src/cli/vault.py`, `src/cli/init.py`, `tests/test_vault.py`, vault sections of `tests/test_cli.py`. **Operational surface gone:** `~/.naavik/secrets.enc{,.lock,.bak.*}`, `~/.naavik/key.bin`, `~/.naavik/logs/vault-audit.log`. **README rewrite (~150 lines):** delete § Vault / § Rotating SECRET_KEY / § Vault audit log / § Troubleshooting "vault locked"; replace with § Configuring secrets via `.env`. **UX regression to flag in changelog:** rotating an LLM API key is now "edit `.env` + restart" instead of a Settings UI form — standard self-hosted practice but worth being explicit. **Backup discipline:** `.env` becomes the secret-restoration target; document alongside the existing `~/.naavik/data/` snapshot story. | HIGH | Sequence BEFORE 2.11 — most of the CLI's reason-to-exist is the vault. ~2–3 days. Touches ~15 files; mostly deletions. |
| 2.11 | **CLI sunset** — depends on 2.12. After 2.12 ships, the only `naavik` subcommand left is `serve`; `init` / `vault status` / `vault rotate-key` are gone with the vault. Final cleanup: delete `src/cli/`, drop `[project.scripts] naavik = "cli.main:main"` from `pyproject.toml`, collapse the server entrypoint to `python -m main` or the Nix flake's `apps.default` output. Keep `naavik-alembic` (alembic's own CLI surface, not a Naavik feature). May merge into the same PR as 2.12 if scope stays tight. **Policy in AGENTS.md § Key Conventions § CLI:** do NOT extend the CLI in interim plans; new operator features ship in the UI. | HIGH | < 1 day after 2.12. Independent of scrapers (2.1–2.10). |

**Deliverable:** Jobs scraped on schedule, AI-extracted, deduplicated, shown in dashboard with notifications. Vault deprecated; secrets via `.env`; CLI removed.

---

### Phase 3: Intelligent Scoring & Matching
> **Goal:** AI compatibility scoring with tag-based profile matching and explainable results.
> **Plan:** `docs/plans/12-phase-3-scoring.md` (to be authored after plan 11 ships).
> **Implementation contract:** `docs/design/BACKEND.md` § H.1 (`scorer` service), § M.3 (`score_job` prompt). DATA_MODEL.md § C (`Job.score`, `Job.score_explanation`, `Job.match_breakdown`).
> **Estimated effort:** 1–2 weeks.

| # | Task | Priority | Notes |
|---|---|---|---|
| 3.1 | Tag-based matching: job desc → identify tags → match against profile bullets | CRITICAL | |
| 3.2 | AI scoring: structured output (score 0-1, explanation, gap analysis) | CRITICAL | Cloud + local model support |
| 3.3 | Visa/sponsorship auto-filter (score 0 for citizenship-required / no-sponsorship) | CRITICAL | |
| 3.4 | Tailored resume preview: show which bullets selected/excluded for a job | HIGH | |
| 3.5 | One-click generation: from job detail → tailored resume + cover letter | HIGH | |
| 3.6 | Score history + analytics | MEDIUM | |
| 3.7 | HTMX UI: score card, match explanation, bullet selection preview | HIGH | |

**Deliverable:** Every job scored with explanation. User sees bullet selection preview and generates tailored docs in one click.

---

### Phase 4: Application Tracking & Auto-Apply
> **Goal:** Full application lifecycle with configurable automation level.
> **Plan:** Most of Phase 4 ships inside plan 10 Wave 6 (DRAFT lifecycle, ATS submit, semi-auto + auto-apply paths). UI polish + analytics dashboard ship as a small follow-up `13a-tracking-polish.md` post-Phase-1.
> **Implementation contract:** `docs/design/BACKEND.md` § K (auto-apply + manual paths), § K.5 (ATS adapters per board), § L.1 (Gmail/Outlook OAuth). `docs/design/DATA_MODEL.md` § A multi-axis state, § E state transitions.

| # | Task | Priority | Notes |
|---|---|---|---|
| 4.1 | Application multi-axis state model: `status` (APPLIED → RECRUITER_SCREEN → ONSITE_LOOP → OFFER → CLOSED) + `closed_reason` (rejected_by_them / withdrawn_by_me / ghosted / accepted_other) + orthogonal sub-states `docs_state`, `referral_state`, `recruiter_state`, computed `outreach_engagement`. State machine + transitions per axis. See `docs/design/DATA_MODEL.md` (plan 05) for authoritative definitions. | CRITICAL | |
| 4.2 | Manual application logger (form for external applications) | HIGH | |
| 4.3 | Semi-auto flow: generate docs → notification → human approves → submit → update status | HIGH | Default mode |
| 4.4 | Auto-apply flow: high-score jobs → generate → submit automatically (user setting, default OFF) | HIGH | Configurable threshold |
| 4.5 | Playwright form filling for supported boards (with optional review step) | MEDIUM | |
| 4.6 | Google Sheets sync (optional secondary view) | LOW | Keep for shared tracking |
| 4.7 | Application analytics dashboard | MEDIUM | Response rate, interview rate, by company/role |

**Deliverable:** Full Kanban tracking. Semi-auto or auto-apply based on user preference. Analytics.

---

### Phase 5: Email Monitoring & Outreach
> **Goal:** Monitor emails, classify responses, manage interview prep, and track recruiter/employee outreach. (Email auto-classification feeds the multi-axis Application sub-states defined in Phase 4 — `recruiter_state`, `outreach_engagement` — via Tracking; this phase adds the email + outreach mechanics behind that.)
> **Plans:** `docs/plans/13-phase-5-email.md` (Gmail/Outlook OAuth + classifier) → then `docs/plans/14-phase-5-outreach.md` (LinkedIn DM + Calendar + Discord/Telegram inbound). Both authored after plan 12 ships.
> **Implementation contract:** `docs/design/BACKEND.md` § L.1 (Gmail/Outlook), § L.2 (LinkedIn browser, account-ban risk), § L.3–L.5 (Discord/Telegram/Calendar), § H.1 (`email_classifier`, `outreach_generator`, `contact_tracker`).
> **Estimated effort:** Plan 13 1–2 weeks; plan 14 2–3 weeks (LinkedIn is the most fragile dep).

| # | Task | Priority | Notes |
|---|---|---|---|
| **Email Tracking** | | | |
| 5.1 | Gmail API / IMAP email monitoring | HIGH | Connect to user's email inbox |
| 5.2 | AI email classification: INTERVIEW_REQUEST, REJECTION, OFFER, ASSESSMENT, FOLLOW_UP | HIGH | |
| 5.3 | Auto-update job status from email classification | HIGH | |
| 5.4 | Priority notifications (HIGH for interviews/offers) | MEDIUM | |
| 5.5 | Email thread tracking per application | HIGH | |
| 5.6 | AI draft response generation | MEDIUM | |
| **Interview Prep** | | | |
| 5.7 | Interview scheduling integration (Calendly/webhook) — surfaces on Tracking application detail and Overview priority actions | MEDIUM | |
| 5.8 | Interview prep: role-specific questions from job desc + profile gaps | LOW | |
| **Recruiter & Employee Outreach** | | | |
| 5.9 | LinkedIn connection tracker: store recruiter/employee contacts per company | HIGH | |
| 5.10 | Outreach template system: personalized messages for recruiters + employees | HIGH | Uses profile + job context |
| 5.11 | AI-generated outreach messages: referral requests, follow-ups, check-ins | HIGH | Tone-appropriate, not spammy |
| 5.12 | LinkedIn automation: send connection requests + messages via API | MEDIUM | Rate-limited, anti-detection. **Re-open `docs/design/research/LINKEDIN_SCRAPING.md` option matrix when authoring plan 14** — § 5 stack-rank flags stickerdaniel/linkedin-mcp-server (1.9k stars, Apache-2.0, Patchright-based) as the front-runner for the outreach surface because authenticated session is unavoidable here, unlike task 2.2 where the guest API wins. |
| 5.13 | Outreach history tracking: sent messages, responses, acceptance rates | MEDIUM | |
| 5.14 | Warm intro finder: suggest mutual connections for warm outreach | LOW | LinkedIn API |
| 5.15 | Interview process accelerator: auto-send thank-you notes, follow-up reminders | MEDIUM | |

**Deliverable:** Email inbox monitored → job statuses auto-updated. Recruiter/employee contacts tracked → AI-assisted outreach → referral requests sent at optimal timing.

---

### Phase 6: Optimization & Polish
> **Goal:** Performance, analytics, and advanced features.
> **Plan:** `docs/plans/15-phase-6-polish.md` — splits cleanly into 15a (observability — Prometheus + Sentry + OTel), 15b (light mode), 15c (LaTeX template + ML scoring calibration). Author after plan 14 ships.
> **Implementation contract:** `docs/design/BACKEND.md` § N (observability — Prometheus, Sentry, OTel), `docs/design/DATA_MODEL.md` § H (`JobEmbedding` pgvector for semantic match), `DESIGN.md` (light mode tokens — Phase 6).
> **Estimated effort:** 3–4 weeks total (split across 15a/b/c).

| # | Task | Priority | Notes |
|---|---|---|---|
| 6.1 | Resume A/B testing (track which variants get responses) | MEDIUM | |
| 6.2 | Semantic job matching with pgvector embeddings | MEDIUM | |
| 6.3 | Weekly summary reports | LOW | |
| 6.4 | Performance: caching, batch AI calls, parallel scraping | LOW | |
| 6.5 | ML scoring calibration from application outcomes | LOW | |
| 6.6 | LaTeX template support alongside Typst (for users who prefer LaTeX) | LOW | NEU template compat, latexmk/tectonic compilation |
| 6.7 | Additional Typst/LaTeX resume templates (modern, academic, creative) | LOW | Template marketplace |

---

### Phase A: Agent System
> **Goal:** A reproducible agent-driven delivery system mirrored from this ROADMAP onto a GitHub Project v2 board. 6 specialized subagents + 13 slash commands + tracing + token budget + bootstrap tooling. Tracked separately from product phases — this is meta (the dev process), not the product.
> **Plan:** `docs/AGENT_OPS.md` (operational guide — single source for setup, daily workflow, troubleshooting).
> **Status:** 🚧 Active (bootstrap shipped 2026-05-16). Run `scripts/gh-project.sh init && scripts/gh-project.sh bootstrap --apply` once per fork to mirror this phase's tasks onto the Project board.
> **Mirror milestone:** `Phase A`.

| # | Task | Status | Priority | Notes |
|---|---|---|---|---|
| A.1 | Author 6 subagent prompts under `.claude/agents/{manager,architect,engineer,devops,hacker,designer}.md` | [x] | CRITICAL | Frontmatter (name/description/tools/model/color) + body (principles, operating loop, tracing format, escalation). Models: manager+architect+hacker on opus-4-7; engineer+devops+designer on sonnet-4-6 with `ESCALATE: opus` pattern. |
| A.2 | Author 13 slash commands under `.claude/commands/` | [x] | CRITICAL | `/build`, `/plan`, `/discuss`, `/triage-bug`, `/review-pr`, `/threat-model`, `/design-screen`, `/groom`, `/standup`, `/bootstrap`, `/sync-roadmap`, `/budget`, `/runs`. Each wraps a multi-agent flow. |
| A.3 | `scripts/gh-project.sh` — Projects v2 helper | [x] | CRITICAL | `init`, `bootstrap`, `sync`, `milestone-status`, `add-item`, `create-issue`, `set-status`, `next-unblocked`, `runs`. Idempotent; user-or-org auto-detected. Cache at `.claude/github-project.json` (gitignored). |
| A.4 | Token budget config + ledger | [x] | HIGH | `.claude/budget.json` (caps) + `.claude/budget-ledger.json` (manager-managed, gitignored). Halt at projected-spend-exceeds-cap; `/budget` to inspect. |
| A.5 | Trace system: `traces/<run-id>/` + `watch.sh` (tmux) + `runs.log` index + `MANIFEST.json` per run | [x] | HIGH | Run-id format `YYYY-MM-DDTHH-MM-SS_<6hash>`. Per-agent log format frozen in each agent's prompt. `/runs` to list history. |
| A.6 | `docs/AGENT_OPS.md` — single operational guide | [x] | CRITICAL | Bootstrap → daily workflow → commands reference → agent reference → GitHub Mirror conventions → tracing → budget → troubleshooting → extending the system. Linked from README, AGENTS.md, CLAUDE.md. |
| A.7 | `.github/` templates: 3 Issue forms (bug / feature / plan-execution) + PR template | [x] | MEDIUM | PR template aligns with AGENTS.md § Workflow step 7 (deviations summary required). |
| A.8 | First end-to-end `/build` shipping a real paper cut | [x] | HIGH | Satisfied 2026-05-16 via PR #49 (PC.5). First end-to-end `/build` of agent-system v2 validated: 5 skills invoked, git `prepare-commit-msg` hook auto-appended `Closes #7`, deviations promoted into plan 17, plan archived. Manager → architect → engineer → hacker → devops → ROADMAP update → Issue close → Project advance loop exercised. |
| A.9 | Cap retention on `traces/` (auto-delete runs > N days) | [ ] | LOW | Today: manual delete. Add a `traces/.cleanup.sh` cron-style helper once accumulation gets noisy (>50 runs). |
| A.10 | Visual run dashboard (web UI for `traces/runs.log`) | [ ] | LOW | Nice-to-have. Current state: `claude /runs` + `./traces/watch.sh` cover the inspection use cases. |
| A.11 | **Agent system v2 — cold-start infra + per-agent skill suite + git commit automation** | [x] | HIGH | **Plan 16 EXECUTED 2026-05-17** across all 4 phases (archived `docs/plans/archive/16-agent-system-v2.md`). **Phase 1** (2026-05-16): `.claude/hooks/cold-start.sh` SessionStart hook + `.claude/skills/naavik-cold-start/SKILL.md` + `Skill` tool added to all 6 agents + `.claude/hooks/git/prepare-commit-msg` auto-appends `Closes #N` from branch name using `.claude/github-issue-map.json` (case-sensitive — see AGENT_OPS § 2.8) + Project v2 automation guide. **Phase 2** (2026-05-16): per-agent skill suite under `.claude/skills/<name>/SKILL.md` — shipped 29 skills (28 spec'd; +1 = `build` skill authored mid-Phase-4 codifying dual-surface convention in AGENT_OPS § 10.2). Breakdown: manager 4 / architect 4 / engineer 5 / designer 5 / hacker 3 / devops 3 + shared 4 (`naavik-cold-start` / `naavik-roadmap-status` / `naavik-deviations-check` / `naavik-vault-sunset-guard`) + `build`. **Phase 3** (2026-05-16): first `/build` (PC.5 → PR #49 squash `ceca24b`) — satisfies A.8. **Phase 4** (2026-05-17): second `/build` (PC.6 → PR #50 squash `7c7e12a`) — surfaced the REQUEST_CHANGES → engineer-re-loop → re-review → approve path-C flow end-to-end; validates the loop's reliability on multi-finding reviews. Side artifact: `docs/design/research/LINKEDIN_SCRAPING.md` option matrix authored in parallel (Phase 2 task 2.2 + Phase 5 task 5.12 pre-staging). Kickoff prompt: `docs/prompts/agent-system-v2.md`. |
| A.12 | Map cache + single-writer governance (gh-project.sh hardening) | [x] | HIGH | Shipped 2026-05-16. `scripts/gh-project.sh` `find_issue_by_prefix` + `ensure_milestone` consult `.claude/github-issue-map.json` first (eliminates search-API race); new `refresh-map` subcommand reconciles from authoritative GitHub state (prefers open + lowest-#); dry-run now correctly reports `exists`/`PLAN` for milestones + epics (was lying with "would create if missing"); duplicate epics #46/#47 closed; "GitHub state — single writer" rule codified in CLAUDE.md / AGENTS.md / manager.md / bootstrap.md / AGENT_OPS.md. Bootstrap is now fully idempotent (`would create=0`). |
| A.13 | Tracing contract — ERROR + BUILT/REVIEWED event family + MANIFEST schema extensions | [x] | MEDIUM | Shipped 2026-05-17 via commit `aa2f6a0` (**WORKFLOW MISS:** pushed directly to `main` without PR review; should have been a PR with hacker + devops review. Logged as a one-time process violation; future source-of-truth changes will go through PR per AGENTS.md § Workflow). Adds two cross-agent event families to `docs/AGENT_OPS.md § 7.2`: (1) `ERROR step=<what> kind=<retry\|skip\|halt\|pivot> reason='<line>' attempt=<n>/<max>` — logged the moment failure happens, not buffered (sandbox denials, test flakes, plan-vs-reality pivots, self-approval blocks); (2) `BUILT` / `REVIEWED` — last line of every agent log, one-sentence summary. Extends MANIFEST schema (§ 7.3) with `outcome` (delivered\|halted\|failed), `halt_reason`, `what_built` (paragraph aggregated from BUILT/REVIEWED lines), `errors_encountered` (array auto-aggregated from per-agent ERROR lines). All 6 agent prompts gain "Tracing contract — mandatory" section; `devops-trace-manifest` skill aggregates via bash snippets. Surfaced in response to user feedback after PR #50 — "make sure agents write to the trace properly. if something went wrong or errors happened during the execution it all must be logged." Current run's MANIFEST.json retroactively backfilled with 5 `errors_encountered` entries documenting actual pivots (engineer find-replace scope, branch case, hacker self-approval block, devops destructive-rm guard, manager sandbox denial). |
| A.14 | Task Playbook — strict if-then task classification (`docs/PLAYBOOK.md`) | [x] | MEDIUM | **Shipped 2026-05-17 via PR #51 squash `ab9f2589`** = `chore(playbook): add task playbook — strict if-then task classification`. PR took two commits: initial `d882139` shipped the 9-category playbook with strict procedures + hard rules; Path-B re-loop `fda092d` resolved hacker Finding 1 by restructuring § File classification quick reference from enumerative-both-sides into **default-deny + allow-list-only**. Closes the judgment surface that produced `aa2f6a0`. **9 categories**: STATUS / INSPECT / 3 gate responses (PLAN/PR/MILESTONE) / PRODUCT_WORK / BUG_TRIAGE / CONTRACT_CHANGE / BOOKKEEPING. **Critical invariant**: Default = CONTRACT_CHANGE (PR required); BOOKKEEPING is allow-list only (`ROADMAP.md`, `docs/plans/archive/**`, `docs/prompts/archive/**`, `traces/**`, `README.md` "Last updated" only). Never mix in one commit. New file `docs/PLAYBOOK.md` (341 lines); 4 reference-file updates (`AGENTS.md` Quick Start, `docs/AGENT_OPS.md § 3`, `.claude/agents/manager.md` Task Playbook section, `.claude/skills/naavik-cold-start/SKILL.md` canonical reading list). Hacker delta-review: APPROVE — *"Path-B is structurally STRONGER than Path-A — turns the rule from enumerative-both-sides into fail-safe allow-list-only-for-BOOKKEEPING"*. Devops re-gate: PASS (7/7 checks). Self-validating authorship: PR #51 followed its own category H procedure (chore/ branch, no direct push, PR + reviewers). Total spend: ~50k tokens (engineer 18k + hacker 24k + devops 12k). |
| A.15 | **Agent memory + learning system** — persistent stores + indexed knowledge base + discussion-capture + periodic learning + session analysis | [x] | HIGH | **Plan 19 EXECUTED 2026-05-17 via PR #53 squash `a63b774`** (archived `docs/plans/archive/19-agent-memory-and-learning.md`). 3-Wave scope shipped in ONE PR (user-locked deviation from architect's 3-PR recommendation). Shipped 22 files (15 new + 7 modified) on `feat/A.15-agent-memory`. **Wave 1 (substrate)**: `.claude/memory/` + 6 stores (`decisions.jsonl`, `discussions.jsonl`, `lessons.jsonl`, `knowledge/<topic>.md` × 5 seeded + `knowledge/INDEX.md`, `recurring-patterns.jsonl`, `runs-analysis/<run-id>.md`) + `scripts/agent-memory.sh` (697-line bash single-writer, mirrors `gh-project.sh`) + 2 skills (`naavik-memory-lookup` + `naavik-discussion-capture`) + read-only `MEMORY.md` integration. **Wave 2 (analytics)**: `/learn` slash command + `naavik-learn` skill mirror + `analyze-run` + `mine-patterns` per-agent ERROR aggregation. **Wave 3 (promotion)**: `promote-lesson` threshold=5 + alias mining via MEMORY_MISS events + `manager-promote-lesson` skill + decision supersession (`--supersedes` marks state=superseded, default query filter `state=active`). Cross-walk: `docs/design/AGENT_MEMORY.md` (design doc graduation), `README.md § Operations`, `CLAUDE.md`, `AGENTS.md § Agent System`, `docs/AGENT_OPS.md § 14`, `hacker-secrets-audit/SKILL.md` (single-writer rule check). Smoke: **50/50 PASS**. Follow-ups filed pre-merge per user wrap-up: A.17 #54 (hacker hardening, HIGH), DEF-24 #55 (pre-existing ruff, LOW), DEF-25 #56 (pre-existing DB-test gating, MEDIUM); A.11 #48 board drift reconciled inline. Full PR_REVIEW_GATE report archived at `traces/2026-05-17T08-40-13_4abef2/pr-review-gate.md`. |
| A.16 | Machine-readable wording rewrite of agent-system instruction files | [ ] | HIGH | **Filed 2026-05-17** per user directive: *"make sure our wording everywhere other than docs is machine readable... minimizes tokens while conveying the same information more efficiently in a way that you can understand it best. in the end it's all about you."* Scope: rewrite `.claude/agents/*.md` (6 files), `.claude/skills/*/SKILL.md` (~29 files), `.claude/commands/*.md` (13 files), `.claude/hooks/*` prose sections — drop articles, use bullets over prose, imperative voice (no "please"/"kindly"), tables for option matrices, file:line refs, drop redundant elaboration. **OUT OF SCOPE**: docs files (`AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/AGENT_OPS.md`, `docs/PLAYBOOK.md`, `docs/RUNBOOK.md`, `docs/DEPLOYMENT.md`, `docs/ARCHITECTURE.md`, `DESIGN.md`, `docs/design/**`, `docs/plans/**`, `docs/prompts/**`) — stay prose-readable for human + LLM. Plan needed (~architect dispatch). Coupling: A.15 engineer should ADOPT this style for new agent-system files in their PR (skills + commands + scripts) but NOT retrofit existing files — that's A.16's scope. |
| A.17 | `agent-memory.sh` hardening — flock + jq sandbox + alias regex + manifest escape | [ ] | HIGH | **Filed 2026-05-17 via PR #53 hacker review** (Issue #54). Hacker `APPROVE_WITH_NOTES` verdict surfaced 5 findings (2 medium / 3 low) in `scripts/agent-memory.sh` shipped with A.15; none block A.15 merge but all worth tightening on a follow-up. (1) **medium**: `append_jsonl:49-57` lost-update race — 30 parallel writes drop ~17; add `flock` around read-modify-write under `.claude/memory/.lock`. (2) **medium**: `query:376` passes user `<jq-expr>` unescaped to `jq` — `env.*` filter exfiltrates `NAAVIK_DEV_PASSWORD`/`ANTHROPIC_API_KEY` to stdout via prompt-injection-crafted query; allowlist regex to field-access + literal-comparison. (3) **low**: `for run in $RUNS` unquoted word-split at `:506,573`. (4) **low**: front-matter injection via `--aliases "p\n---\nTopic:pwned\n---"` at `:236-247` — validate against kebab regex. (5) **low**: `MANIFEST.json` verbatim echo into markdown at `:418-424` — `printf %q` value. ~2h. Reference: PR #53 hacker.log + `traces/2026-05-17T08-40-13_4abef2/pr-review-gate.md`. |

**Deliverable (Phase A):** A fork-able agent system. `gh auth login → scripts/gh-project.sh init → scripts/gh-project.sh bootstrap --apply → claude /standup → claude /build "next"` works end-to-end. New contributors onboard via `docs/AGENT_OPS.md`.

---

## Agent System (mirror conventions)

> **Companion docs:** `docs/AGENT_OPS.md` (single operational guide), `AGENTS.md` § Agent System (workflow integration), `.claude/agents/` (full agent prompts), `.claude/commands/` (slash commands).
>
> **Reference guides loaded by agents on cold start:**
> - `docs/ROADMAP_OVERVIEW.md` — one-page roadmap digest (faster than this 800-line doc)
> - `docs/ARCHITECTURE.md` — layer responsibilities + cross-cutting concerns + pattern catalog
> - `DESIGN.md` (root) — visual contract (tokens, type, icons, voice; frozen) + `docs/design/WORKFLOW.md` — UI sub-process (skill routing, per-screen checklist, accessibility, common patterns, anti-patterns)
> - `docs/DEPLOYMENT.md` — 4 deployment paths + config + ops checklist
> - `docs/RUNBOOK.md` — devops runbook (known failure modes + diagnostic recipes + recovery)
> - `docs/plans/POST_PHASE_1.md` — testing playbook + monitoring + "when something goes wrong"

This ROADMAP is mirrored onto a GitHub Project v2 board for queryability and assignability. **ROADMAP is authoritative** (per AGENTS.md § Single-doc-tracking); the Project is a one-way operational mirror. The mapping is mechanical:

| ROADMAP element | GitHub Project equivalent |
|---|---|
| `### Phase N: <Name>` header | Milestone `Phase N` (description = `**Goal:**` line) |
| Task row in a phase table | Issue titled `[<task-id>] <description>`, body links back to ROADMAP |
| `[ ]` / `[~]` / `[x]` status | Project Status field: `Todo` / `In Progress` / `Done` |
| Priority column (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`) | Project Priority single-select |
| Phase header | Project Milestone single-select (`Phase 0`–`Phase 6`, `Phase A`, `Pre-Phase-2 paper cuts`, `Phase 1.x deferred`) |
| Notes column | Issue body |
| `Plan:` reference (e.g., `docs/plans/11-…`) | Label `plan:<NN>` on the Issue |
| `[~]` row that takes >1 day | Optionally split into sub-Issues via `/groom` |

**Sync flow:** always ROADMAP → Project. Manager updates ROADMAP first (mark `[~]` on start, `[x]` on done), then runs `scripts/gh-project.sh set-status` to push to Project. `/sync-roadmap --apply` is the bulk reconcile. If the Project drifts from ROADMAP, the Project is wrong — never edit ROADMAP to match a stale board.

**Bootstrap:** `scripts/gh-project.sh bootstrap [--apply]` parses ROADMAP's task tables and creates Milestones + Issues + Project items for the active phases (defaults to Pre-Phase-2 paper cuts + Phase A + Phase 2 + Phase 1.x deferred — completed Phase 0/1 rows are skipped). See `docs/AGENT_OPS.md` § 2 for the full setup walkthrough.

**What to do as a plan / task author:**
1. Write the task row in ROADMAP first (status `[ ]`, with Priority).
2. Run `/plan <task-id>` — architect drafts the plan, opens the GH Issue (via `scripts/gh-project.sh create-issue`), adds to Project, links back to ROADMAP.
3. Run `/build <milestone>` (or `/build "next"`) when ready to implement.

**What to do as an implementer:**
1. Mark the ROADMAP row `[~]` when starting.
2. Reference the Issue in commits: `Closes #<N>` in the last commit triggers GH's auto-close on merge.
3. Mark the ROADMAP row `[x]` + add a one-line deliverable note when done.
4. `/build` handles steps 1 + 3 automatically; manual implementers do them by hand.
