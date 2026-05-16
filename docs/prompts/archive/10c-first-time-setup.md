---
Status: USED
Type: implementation kickoff
Plan: docs/plans/10c-first-time-setup.md
Authored: 2026-05-10
Last updated: 2026-05-12
Prerequisite: plan 10b shipped clean (475 tests pass, archived 2026-05-03). Plan 10c APPROVED 2026-05-10, EXECUTED 2026-05-12.
---

# Naavik · Plan 10c kickoff — first-time setup ergonomics

> Paste this entire file as the first message of a fresh Claude Code session. The repo is at `/home/nightwatcher/personal/dev/naavik`.
> **After 10c ships and verifies, the next move is `docs/plans/POST_PHASE_1.md` § "Phase 1 testing playbook" → Phase 2-6 plans 11–15.**

---

## Goal

Close the three first-time-setup paper cuts surfaced during 10b smoke testing so a fresh self-hoster signs in within 30 seconds of `nix run .#dev` without reading docs.

1. `nix develop` inherits the orchestrator's `NAAVIK_PERSISTENCE=db` default (10c.1).
2. The "Create account" link is a prominent CTA below the Sign-in button, and `/login?mode=signup` against a seeded single-user instance renders an explanatory banner instead of a form that POSTs to a 403 (10c.2).
3. The dev credential is persisted to `~/.naavik/dev-credentials` (mode 0600, debug + SELF_HOSTED gated) AND echoed by the FastAPI lifespan ~750 ms after startup so it's near the bottom of the orchestrator's scrollback. Retrieval is plain `cat ~/.naavik/dev-credentials` — **no new CLI subcommand** (10c.3).

After 10c, every step of the existing POST_PHASE_1 manual smoke runs cleanly without hunting through scrollback or reseeding the DB.

## Required reading (in order)

1. `AGENTS.md` § Workflow + § Roadmap Maintenance Rules + § Single-doc-tracking principle + **§ Key Conventions § CLI (sunset track — do not extend)**.
2. `docs/plans/10c-first-time-setup.md` end-to-end (the plan you're implementing — § A scope, § B file-by-file, § C tests, § D build sequence, § E out-of-scope, § Open questions, § Approval checklist).
3. `docs/plans/archive/10b-phase-1-finalization.md` § "Deviations from plan" — context for what 10b shipped (the seeded credential printer, the signup endpoint, the `naavik` CLI dispatcher you must NOT extend, the vault-locked banner you do not touch).
4. `ROADMAP.md` § Pre-Phase-2 paper cuts (PC.7 row) + § Phase 2 tasks 2.11 + 2.12 (CLI sunset + vault deprecation — these constrain what 10c may NOT do).
5. `nix/devshell.nix` `shellHook` block + `flake.nix` `devEnv` block (the parity target for 10c.1).
6. `src/ui/templates/pages/login.html` + `src/ui/routes/auth.py:get_login` (the 10c.2 surfaces).
7. `src/db/seed.py` `_resolve_dev_password()` + the `[seed] dev password:` print path (the 10c.3 write-to-disk extension point).
8. `src/main.py` lifespan block (the 10c.3 echo extension point).

## Deliverables

| Path | Description |
|---|---|
| `nix/devshell.nix` | Add `export NAAVIK_PERSISTENCE=db` to `shellHook` (one line, alongside existing `LD_LIBRARY_PATH` + `PYTHONPATH` exports) (§ B 10c.1) |
| `src/ui/routes/auth.py` | `get_login` queries User count + `Settings.allow_multiple_users` and computes server-side `signup_disabled = users_exist AND not allow_multiple_users`; passes into template context (§ B 10c.2(b)) |
| `src/ui/templates/pages/login.html` | Promote signup link out of footer to prominent CTA below Sign-in button (sign-in mode: "First time? Create account"; signup mode: "Already have an account? Sign in"); when `is_signup AND signup_disabled`, render the amber `lock` banner branch from plan § A.10c.2(b) instead of the form; remove the footer link (§ B 10c.2(a)+(b)) |
| `src/db/seed.py` | When `dev_password_source == "generated"` AND `app_settings.debug` AND `Settings.deployment_mode == DeploymentMode.SELF_HOSTED`, write `Path(app_settings.data_dir) / "dev-credentials"` (mode 0600) with two lines: `email: <addr>` / `password: <plaintext>`. NEVER write the file when env-supplied or when debug=False (§ B 10c.3(a)) |
| `src/main.py` | Add `_echo_dev_credentials_after_start()` async fn + register it as `asyncio.create_task` inside `lifespan()` (gated on `app_settings.debug`). Sleep 750 ms, read `Path(app_settings.data_dir) / "dev-credentials"` if it exists, log via stdlib `logging` at INFO level (process-compose prefixes with `[app]`). Banner format: `─── dev credentials (also at ~/.naavik/dev-credentials) ───` / `email: …` / `password: …` / `─────────────────────────…` (§ B 10c.3(a)) |
| `README.md` | (1) Update § "Dev / test env vars" `NAAVIK_PERSISTENCE` row default column to `db (orchestrator + nix develop + direnv) · memory (bare Python outside the dev shell)`. (2) Replace § "First-time setup (live DB)" "capture that line" paragraph with `cat ~/.naavik/dev-credentials` retrieval instructions + `&& rm` shred recipe. (3) Add `dev-credentials — plaintext dev login (mode 0600, debug only)` line to the § Configuration § DATA_DIR comment block. (4) Add a one-line note at the top of § Operations § "`naavik` CLI" pointing at ROADMAP § Phase 2 task 2.11/2.12 (sunset). **DO NOT add a `naavik dev creds` row to the CLI table.** (§ B all) |
| `CLAUDE.md` | Bump "Last updated" line: new operational surface `~/.naavik/dev-credentials` (mode 0600, debug + SELF_HOSTED gated) + reference to AGENTS.md § Key Conventions § CLI sunset policy (§ B all) |
| `docs/plans/POST_PHASE_1.md` | Append parenthetical to § "What 'Phase 1 done' looks like" step 2: `(credential prints on first boot AND lands at \`~/.naavik/dev-credentials\` (mode 0600) for later retrieval via \`cat\`)` (§ B 10c.3) |
| `tests/test_pages.py` | Extend with `test_login_signin_has_prominent_signup_link` (asserts the CTA exists OUTSIDE the footer in sign-in mode), `test_login_signup_mode_renders_form_on_fresh_db` (form rendered when User table empty), `test_login_signup_mode_renders_banner_on_seeded_db` (banner rendered when seeded + `allow_multiple_users=False`) (§ C) |
| `tests/test_seed.py` (live-DB, gated by `NAAVIK_LIVE_DB=1`) | Extend with `test_seed_writes_dev_credentials_when_generated_in_debug_mode` (file exists, mode 0600, contents match) and `test_seed_skips_dev_credentials_when_password_from_env` (file does NOT exist) (§ C) |
| `tests/visual/baseline/login-signup-banner-desktop.png` (new) | Playwright snapshot of `/login?mode=signup` against the seeded DB at 1440×900 viewport, captured per `tests/visual/capture.py` recipe (§ C) |

## What you MUST NOT do

| Forbidden | Why |
|---|---|
| ❌ Add ANY new `naavik <subcmd>` — including `naavik dev creds`, `naavik dev …`, `naavik creds …`, etc. | The `naavik` CLI is on a sunset track per ROADMAP § Phase 2 task 2.11. Adding to it doubles down on a path being deleted. AGENTS.md § Key Conventions § CLI codifies the policy. The retrieval path is `cat ~/.naavik/dev-credentials`. |
| ❌ Add a new vault scope, key, or helper | Encrypted vault is on a parallel sunset track per ROADMAP § Phase 2 task 2.12. Don't write helpers that pretend the vault has a future. The dev-credentials file is plaintext (mode 0600) on disk — that's intentional, NOT a vault entry. |
| ❌ Persist env-supplied dev passwords to disk | The dev-credentials file ONLY exists when `dev_password_source == "generated"`. When the operator sets `NAAVIK_DEV_PASSWORD`, they own the value; we don't echo it back to disk. |
| ❌ Write the dev-credentials file when `Settings.debug=False` | Production self-hosters never get the file. The gate is debug + SELF_HOSTED + generated, all three. |
| ❌ Touch the existing seed credential print line | The stdout `[seed] dev password: …` line stays exactly as 10b shipped it. 10c's lifespan echo + on-disk file are ADDITIONS, not replacements. |
| ❌ Modify the bcrypt hashing path or the signup endpoint | 10c is template + seed + lifespan + devshell only. Auth boundary is unchanged. |
| ❌ Touch the `_settings_deployment.html` vault-locked banner or the `_settings_llm.html` form-wiring | Both are out-of-scope. The vault deprecation in Phase 2 task 2.12 will rewrite them; don't preempt that. |
| ❌ Hardcode `/home/nightwatcher/.naavik/` or `~/.naavik/` in code | Use `Path(app_settings.data_dir) / "dev-credentials"`. The hardcoded path mismatches the orchestrator's `./.naavik/` default. README messaging may use `~/.naavik/dev-credentials` for self-hoster ergonomics — that's a doc convention, not a code path. |
| ❌ Add Alpine.js / React / inline `<script>` blocks to the login template | HTMX + Tailwind only. The signup-link promotion is pure markup. |
| ❌ Break the existing 475-test green build | All prior tests must still pass. Net new ≈ 5 tests. |
| ❌ Use non-Lucide icons or stroke-width other than 1.5 | Banner uses `<i data-lucide="lock" stroke-width="1.5">`. |
| ❌ Skip the doc cross-walk | README + CLAUDE.md + POST_PHASE_1 updates land in the SAME PR as the code. AGENTS.md § Workflow step 7 is non-negotiable. |
| ❌ Skip the `## Deviations from plan` section before archive | The plan archives only after the deviations section is filled in (or "no material deviations" with confidence). Per AGENTS.md § Workflow step 7. |

## Quality bar

```bash
nix develop --command bash -c 'echo "$NAAVIK_PERSISTENCE"'   # → db
nix run .#dev                                                # boots cleanly; orchestrator prints credential AND lifespan echoes ~750ms after startup
env -u PYTHONPATH uv run ruff check .                        # all green
env -u PYTHONPATH uv run ruff format --check src tests       # all green
env -u PYTHONPATH uv run pytest tests/                       # 475 prior + ~5 new = ~480 green
NAAVIK_LIVE_DB=1 DATABASE_URL=postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik \
  env -u PYTHONPATH uv run pytest tests/test_seed.py -v      # live-DB tests pass too
```

End-to-end (manual, must all pass before declaring 10c shipped):

1. `nix develop` then `echo $NAAVIK_PERSISTENCE` → `db` (10c.1)
2. `nix run .#dev` boots; the dev credential appears in the `[app]` log AFTER `Application startup complete.` AND `Uvicorn running on http://127.0.0.1:8000`. Last 5–6 lines of scrollback contain the credential. (10c.3a)
3. `cat ~/.naavik/dev-credentials` (or `cat .naavik/dev-credentials` in the orchestrator) returns `email: …` / `password: …` (mode 0600 — `stat -c '%a' .naavik/dev-credentials` → `600`). (10c.3a)
4. Wipe DB (`rm -rf .naavik/db`) and rerun `nix run .#dev` with `NAAVIK_DEV_PASSWORD=test-stable-pw` exported — the dev-credentials file is NOT written (env-supplied). (10c.3a)
5. Visit `http://localhost:8000/login` — "First time? **Create account**" CTA appears below the Sign-in button (NOT in the footer). Footer has only Docs / Source. (10c.2a)
6. Visit `/login?mode=signup` against the seeded DB — amber `lock` banner renders ("This instance already has an account."), no form below it. (10c.2b)
7. `rm -rf .naavik/db && nix run .#dev` (with no seed — kill the orchestrator before the seed step, or temporarily disable seeding); visit `/login?mode=signup` — the signup form renders normally. Sign up; land on `/onboarding`. (10c.2b)
8. Sign in via the credential captured in step 2 or 3 — JWT cookie set, redirected to Overview. (sanity check that 10c didn't break 10b's auth flow)

`grep` checks (must be empty):

```bash
rg --no-config 'naavik dev creds' src/                        # NO new CLI subcommand
rg --no-config 'cli/dev\.py' src/ pyproject.toml              # NO new CLI module
rg --no-config 'is_user_table_empty' src/                     # We use signup_disabled, not the prompt's flag name
```

## Hand-back format

When complete:

1. **File list** grouped by directory (per § B of the plan, plus tests).
2. **Test results** — `uv run pytest tests/ -v` summary line (must be all green, ~480 tests). Plus the live-DB run's summary line.
3. **End-to-end smoke** — every numbered bullet from § "Quality bar > End-to-end" above checked off with a brief note.
4. **Screenshots** — `/login` (sign-in) showing the prominent CTA, `/login?mode=signup` (seeded DB) showing the banner, `nix run .#dev` startup scrollback showing the credential lifespan echo.
5. **Doc-cross-walk diff** — paste the unified diff for README + CLAUDE.md + POST_PHASE_1 changes.
6. **Any deviations from the plan** with reason — promoted to the plan's `## Deviations from plan` section before archive (per `AGENTS.md` § Workflow step 7). One bullet per deviation: what / why / impact / new operational surface (if any).
7. **Archive step done** — confirm:
   - `mv docs/plans/10c-first-time-setup.md docs/plans/archive/10c-first-time-setup.md` (Status: APPROVED → EXECUTED)
   - `mv docs/prompts/10c-first-time-setup.md docs/prompts/archive/10c-first-time-setup.md` (Status: AWAITING USE → USED)
   - `ROADMAP.md` § Pre-Phase-2 paper cuts: PC.7 row marked `[x]` with deliverable note
   - `ROADMAP.md` "Last updated" bumped to today's date
8. **Next** — 10c is done; the user can re-run `docs/plans/POST_PHASE_1.md` § "Phase 1 testing playbook" with confidence and proceed to authoring plan 11 (Phase 2 scrapers).

If you hit a blocker (lifespan echo timing slips on slow hardware, the User-count + Settings query in `get_login` surfaces an ORM-mapping quirk like 10b's `select(Settings)` issue, the Playwright snapshot capture fails on a NixOS edge case), STOP and post a question. The contract is the bullet list under § A of the plan — anything that endangers a bullet gets escalated, not papered over.

## Auto-mode caveat

This kickoff prompt assumes the implementer is in **auto mode** (continuous execution). If you need to ask the user a question, do so — auto mode tolerates course corrections. But minimize the asks; defaults in the plan's § Open questions are the agreed defaults unless explicitly overridden. The five approval-checklist items already locked in: `signup_disabled` (Q1), data-dir-relative path (Q2), 750 ms delay (Q3), Wave-4 cleanup separate (Q4), no CLI extension (the policy line).
