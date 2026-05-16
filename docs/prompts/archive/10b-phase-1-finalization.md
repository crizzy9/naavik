---
Status: USED
Type: implementation kickoff
Plan: docs/plans/10b-phase-1-finalization.md
Authored: 2026-05-03
Last updated: 2026-05-03
Prerequisite: plan 10 (Wave 3 + Wave 6) shipped clean — 448 tests pass, plan + prompt archived 2026-05-03, security-review checkpoints 1+2+3 PASS. ROADMAP § Phase 1 marked ✅ Complete.
---

# Naavik · Plan 10b kickoff — Phase-1 finalization

> Paste this entire file as the first message of a fresh Claude Code session. The repo is at `/home/nightwatcher/personal/dev/naavik`.
> **After 10b ships and verifies, you can move on to `docs/plans/POST_PHASE_1.md` for the full Phase-1 testing playbook + Phase 2-6 plan authoring.**

---

## Goal

Close the operational gaps in plan 10 (Wave 3 + Wave 6) that block the `POST_PHASE_1.md` testing playbook. Specifically:

1. Make `nix run .#dev` actually work end-to-end (greenlet/libstdc++ env fix + `NAAVIK_PERSISTENCE=db` default).
2. Give a self-hoster a working credential — fix the seeded user's bcrypt hash + add a real signup endpoint.
3. Wire the `naavik init` and `naavik vault rotate-key` CLI subcommands that the README references but that don't actually install.
4. Wire the Settings · LLM Provider form so users can switch providers + paste their API key + save.
5. Wire the Settings · Deployment vault-locked banner (server-side support already exists).
6. Tidy a wave-numbering wording bug in ROADMAP and rewrite the README's setup section to reflect Phase 1 reality.

After 10b, every step 1–12 of `POST_PHASE_1.md` § "What 'Phase 1 done' looks like" runs cleanly without manual SQL hacks.

## Required reading (in order)

1. `AGENTS.md` § Workflow + § Roadmap Maintenance Rules + § Single-doc-tracking principle.
2. `docs/plans/10b-phase-1-finalization.md` end-to-end (the plan you're implementing — § A scope, § B file-by-file, § C tests, § D build sequence, § E out-of-scope).
3. `docs/plans/archive/10-backend-impl.md` § "Deviations from plan (Wave 3 / § B EXECUTED 2026-05-02 · Wave 6 / § C EXECUTED 2026-05-03)" — the deviations 10b is closing, in their original wording.
4. `docs/plans/POST_PHASE_1.md` § "What 'Phase 1 done' looks like" — the smoke 10b unblocks.
5. `docs/design/BACKEND.md` § D.1 (auth routes), § D.7 (settings routes), § O (Settings shape).
6. `docs/design/DATA_MODEL.md` § C `User`, `Settings`.

## Deliverables

| Path | Description |
|---|---|
| `flake.nix` | Add `LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH` and `NAAVIK_PERSISTENCE=db` exports to `devEnv` block (§ B item 1, 2) |
| `src/db/seed.py` | Replace placeholder password hash with `hash_password(env_or_random)`; print credential at boot (§ B item 3) |
| `src/db/sample_data.py` | Drop the placeholder string from the `USER` shadow row — seed now hashes at runtime (§ B item 3) |
| `src/api/auth.py` | New `POST /api/v1/auth/signup` with single-user guard via `Settings.allow_multiple_users` (default False) (§ B item 4) |
| `src/ui/templates/pages/login.html` | Toggle between sign-in / sign-up modes; replace dead `/login?create=1` link (§ B item 4) |
| `src/ui/routes/auth.py` | `GET /login?mode=signup` renders signup variant of the same template (§ B item 4) |
| `src/cli/main.py` (new) | argparse dispatcher: `naavik serve`, `naavik init`, `naavik vault rotate-key`, `naavik vault status` (§ B item 5) |
| `src/cli/init.py` (new) | `naavik init` — prompt-for-or-generate SECRET_KEY, write `~/.naavik/key.bin` (mode 0600), init empty vault. Refuses to overwrite an existing vault (§ B item 5) |
| `src/cli/vault.py` | Rename existing `cmd_rotate_key` to `cmd_vault_rotate_key`; add `cmd_vault_status` printing fingerprint + scope key counts (NEVER values) (§ B item 5) |
| `pyproject.toml` | `[project.scripts] naavik = "cli.main:main"`. Move uvicorn launcher into `cli.main:cmd_serve` (§ B item 5) |
| `src/main.py` | Keep `main()` as backwards-compat alias that calls `cli.main:cmd_serve()` (§ B item 5) |
| `src/models/settings.py` | Add `allow_multiple_users: bool = False` field. Generate Alembic migration (§ B item 4) |
| `migrations/versions/0002_*.py` (new) | Alembic migration adding `Settings.allow_multiple_users` (§ B item 4) |
| `src/ui/templates/pages/_settings_llm.html` | Form-wrap; provider-aware swap; HTMX `hx-trigger="change"` on radio (§ B item 6) |
| `src/ui/routes/settings.py` | Add `GET /_fragments/settings/llm/model-options?provider=` and `GET /_fragments/settings/llm/api-key-field?provider=` fragment endpoints (§ B item 6) |
| `src/ui/templates/pages/_settings_deployment.html` | Vault-locked banner block consuming `deployment.vault_locked / vault_fingerprint_stored / vault_fingerprint_expected` (§ B item 7) |
| `src/services/settings_service.py` | Confirm `get_deployment_info()` returns the three vault-status fields; add if missing (§ B item 7) |
| `ROADMAP.md` | Reword "Last updated" line line 3 to use ROADMAP Wave 4/5 labels; add Wave-cross-walk pointer near § Implementation waves (§ B item 8) |
| `README.md` | Rewrite § "Manual local development setup" + add troubleshooting subsections per § A item 9 (§ B item 9) |
| `tests/test_auth.py` | extend — signup tests (first-user succeeds, subsequent rejected, password is real bcrypt) |
| `tests/test_seed.py` | extend (live-DB) — verify_password against seeded hash returns True |
| `tests/test_cli.py` (new) | `naavik init` writes key file; `naavik vault status` prints fingerprint; `naavik vault rotate-key` round-trips |
| `tests/test_settings_llm_form.py` (new) | PUT `/api/v1/settings/llm` round-trips via the new form; fragment endpoints return correct provider model lists |
| `tests/test_pages.py` | extend — `/login?mode=signup` renders signup form; `/settings/deployment` with mismatched fingerprint renders banner |

## Quality bar

```bash
nix run .#dev                             # boots cleanly; orchestrator prints dev login credential
env -u PYTHONPATH uv run alembic upgrade head    # 0001_initial + 0002 (Settings.allow_multiple_users)
env -u PYTHONPATH uv run ruff check .            # all green
env -u PYTHONPATH uv run pytest tests/           # 448 prior + ~12 new = ~460 green
nix shell nixpkgs#ruff -c ruff format --check src tests   # all green
```

End-to-end (manual, must all pass before declaring 10b shipped):

- `nix run .#dev` boots, no `greenlet_spawn` traceback, dev credential printed to stdout
- `http://localhost:8000/login`, sign in with printed credential — JWT cookie set, redirected to Overview
- `/profile/edit`, change `headline`, autosave indicator goes `saving → saved`, reload — change persists (verify with `psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c "SELECT headline FROM profile WHERE user_id=1"`)
- `/login` "Create account" toggles to signup form; on a fresh DB this signs up; on a seeded DB returns 403 ("single-user instance; signup disabled")
- `/settings/llm-provider` — click Ollama radio; model dropdown swaps to Llama options; API-key field hides; type a base URL into the Ollama field; click Save; reload; Ollama is selected
- `naavik vault status` prints fingerprint + scope summary (no secret values); `naavik vault rotate-key --old=$OLD --new=$NEW` succeeds and writes `.bak.YYYY-MM-DD-HH-MM`
- Set `SECRET_KEY=different-value`, restart server, hit `/settings/deployment` — rose banner renders showing both fingerprints
- Revert env, banner disappears

`grep` checks (must be empty):

```bash
rg --no-config 'placeholder.hash.for.dev.password' src/    # no placeholder bcrypt hash
rg --no-config '/login\?create=1' src/                     # no dead create-account link
```

## Forbidden patterns

- ❌ **Storing plaintext passwords anywhere.** `password_hash` is bcrypt, period. No fallback shortcuts. Tests must use `NAAVIK_BCRYPT_COST=4`, not skip hashing.
- ❌ **Logging secret values.** `naavik vault status` prints fingerprints + scope key NAMES, never values. Audit log line per vault op stays the only persistence of who-touched-what.
- ❌ **Reverting the auth boundary.** Auth-protected `/api/v1/applications/*` routes from Wave 6 stay protected. Signup is its own endpoint with its own rate-limit gate.
- ❌ **Touching the in-memory `db/sample_data.py` accessor swap further.** 10b only sets `NAAVIK_PERSISTENCE=db` in the orchestrator; full removal of the env var is item B6 in the deferred backlog (its own plan).
- ❌ **Adding feature flags or compat shims for deprecated patterns.** No `legacy_signup` etc. Replace, don't shim.
- ❌ **Overwriting an existing `~/.naavik/secrets.enc`** in `naavik init`. Refuse with a clear error.
- ❌ **Multi-user opening for self-hosted by default.** `Settings.allow_multiple_users = False` is the default; signup gate enforces.
- ❌ **Skipping the README rewrite.** This is half the user-facing value of 10b. Item 9 of § B.

## Hand-back format

When complete:

1. **File list** grouped by directory (per § B of the plan, plus tests).
2. **Test results** — `uv run pytest tests/ -v` output (must be all green, ~460 tests).
3. **End-to-end smoke** — every bullet from § "Quality bar > End-to-end" above checked off with a brief note.
4. **`naavik` CLI demo** — paste output of:
   ```
   naavik vault status
   naavik vault rotate-key --old=A --new=B --no-backup
   naavik vault status     # confirm fingerprint changed
   ```
5. **Manual signup demo** — paste output of `curl -X POST -d email=test@example.com -d password=hunter2hunter2 http://localhost:8000/api/v1/auth/signup` against a fresh DB (succeeds), and against a seeded DB (403).
6. **Settings · LLM form demo** — switch provider via UI, confirm `SELECT llm_provider, llm_api_key_fingerprint FROM settings WHERE user_id=1` reflects the change.
7. **Vault-locked banner screenshot** (or text dump of the rendered HTML when SECRET_KEY mismatches).
8. **Any deviations from the plan** with reason — promoted to the plan's `## Deviations from plan` section before archive (per `AGENTS.md` § Workflow step 7).
9. **Archive step done** — confirm:
   - `mv docs/plans/10b-phase-1-finalization.md docs/plans/archive/10b-phase-1-finalization.md` (Status: AWAITING REVIEW → APPROVED → EXECUTED)
   - `mv docs/prompts/10b-phase-1-finalization.md docs/prompts/archive/10b-phase-1-finalization.md` (Status: AWAITING USE → USED)
   - `ROADMAP.md` § Pre-Phase-2 paper cuts: PC.4 row marked `[x]` with deliverable note
   - `ROADMAP.md` "Last updated" bumped to today's date
10. **Next** — 10b is done; Phase 1 is fully verifiable. The user's next move is to read `docs/plans/POST_PHASE_1.md` § "Phase 1 testing playbook (post-Wave-6)" and run it end-to-end.

If you hit a blocker (greenlet fix doesn't take on a different NixOS version, signup endpoint conflicts with an existing CSRF middleware, the LLM form-wiring runs into HTMX state-sync issues), STOP and post a question. The contract is the bullet list under § A of the plan — anything that endangers a bullet gets escalated, not papered over.

## Auto-mode caveat

This kickoff prompt assumes the implementer is in **auto mode** (continuous execution). If you need to ask the user a question (e.g. "should we add password complexity in 10b after all?"), do so — auto mode tolerates course corrections. But minimize the asks; defaults in the plan's § Open questions are the agreed defaults unless explicitly overridden.
