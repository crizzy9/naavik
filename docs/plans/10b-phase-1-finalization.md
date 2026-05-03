---
Status: AWAITING REVIEW
Type: implementation
Authored: 2026-05-03
Last updated: 2026-05-03
Depends on: 10-backend-impl (archived 2026-05-03 — Wave 3 + Wave 6 EXECUTED)
---

# 10b · Phase-1 finalization — bridge before POST_PHASE_1 testing playbook

## Goal

Close the operational gaps that block the `POST_PHASE_1.md` § "What 'Phase 1 done' looks like" smoke from running end-to-end. After plan 10b ships, a fresh self-hoster can clone the repo, run `nix run .#dev`, sign up (or log in), edit their profile, see the data persist, switch their LLM provider, and exercise every step 1-12 of the post-Phase-1 testing playbook. Plan 10's Wave-3 + Wave-6 deliverables are sound; the gaps here are the small glue items that fell between waves.

## Context / why

Plan 10 § B (Wave 3) and § C (Wave 6) shipped clean by their own acceptance criteria — 448 tests pass, security review checkpoints 1–3 PASS, the 14 services + Typst pipeline + DRAFT lifecycle + ATS adapters all work at the unit-test level. But manual end-to-end testing surfaced eight concrete defects that block the post-Phase-1 playbook:

1. **`nix run .#dev` crashes on every DB write** — `flake.nix` `devEnv` doesn't set `LD_LIBRARY_PATH`, so SQLAlchemy's `greenlet_spawn` can't load `libstdc++.so.6` on NixOS. Devshell.nix sets it; the orchestrator doesn't. Result: `ValueError: the greenlet library is required to use this function. libstdc++.so.6: cannot open shared object file`.
2. **UI shows mock data even when DB is up** — Wave 4 deviation #1 partially swapped sample-data accessors to honor `NAAVIK_PERSISTENCE=db`; Wave 6 deferred completing the swap. The accessors themselves work in DB mode; the orchestrator just doesn't set the env var, so every page reads from in-memory fixtures.
3. **No working dev credential** — `db/sample_data.py:147` seeds the User row with `password_hash="$2b$12$placeholder.hash.for.dev.password.only.not.real"`, which is **not a valid bcrypt hash**. Every login attempt fails. There is no signup endpoint and no `naavik init` CLI to bootstrap a user. A fresh self-hoster cannot get into the app.
4. **"Create account" link is dead** — `pages/login.html` links to `/login?create=1`; `ui/routes/auth.py:get_login` ignores the query param and re-renders the login form. No `POST /api/v1/auth/signup`.
5. **`naavik vault rotate-key` and `naavik init` referenced in docs but not installed** — `cli/vault.py` has working rotate-key code; `pyproject.toml [project.scripts]` only registers `naavik = main:main` and `naavik-alembic`. Self-hoster following README cannot rotate keys or initialize the vault.
6. **Settings · LLM Provider form doesn't save** — `_settings_llm.html` provider radios are not wrapped in a `<form>`; clicking Anthropic / OpenAI / Ollama updates the radio state visually but never PUTs to `/api/v1/settings/llm`. Model dropdown is hardcoded to Claude options. API-key placeholder is hardcoded `sk-ant-…`. The PUT endpoint exists and works (verified via service-layer tests); the UI just never reaches it.
7. **Settings · Deployment vault-locked banner not wired** — Wave 4 deviation #4 noted that server-side support exists (`vault.is_locked()`, `services/settings_service.get_deployment_info()` exposes the boolean + fingerprints); the template wiring was deferred. A SECRET_KEY mismatch leaves the user with a confused 503 and no actionable banner.
8. **ROADMAP "Last updated" line uses plan-internal nomenclature** — line 3 says "Plan 10 § C / Wave 6 EXECUTED" but ROADMAP's canonical labels are Wave 4 / Wave 5. Cosmetic but confusing to anyone scrolling the roadmap top matter.

These are not new feature work; they are the operational glue that ships any backend product. Plan 10b bundles them as one cohesive paper-cut plan so a fresh implementation session can close them all together.

## Proposal

### A · Scope (what 10b ships)

**Item 1: Greenlet / `libstdc++` fix in `flake.nix`**

`flake.nix` § perSystem § `devEnv` adds `export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH"`. Mirror what `nix/devshell.nix:31` already does for the interactive shell. One-line addition; no new tools, no new deps.

**Verification:** `nix run .#dev`, hit `http://localhost:8000`, edit a profile field, autosave indicator goes `saving → saved`. No `greenlet_spawn` traceback in logs.

---

**Item 2: `NAAVIK_PERSISTENCE=db` default in orchestrator**

Same `flake.nix` `devEnv` block: `export NAAVIK_PERSISTENCE=db`. The 12 high-traffic accessors that already honor `_is_db_mode()` (Profile, User, Settings, Experience, Bullet, Skill, Education, Project, Cert, Job, Application, discover_queue, applications_visible_in_tracking) flip to DB-backed reads.

The remaining lower-traffic accessors (KPIs, priority_actions, mutation shims, outreach helpers — annotated `# Wave 4 partial swap`) continue to fall back to in-memory in DB env. Full swap is item B6 in the deferred backlog (its own follow-up plan, not 10b scope).

**Verification:** Edit a profile field via `/profile/edit`, reload, change persists. SQL query `SELECT headline FROM profile WHERE user_id=1` returns the new value.

---

**Item 3: Real seeded credential + dev login bootstrap**

Two parts:

(a) `db/seed.py` calls `services.auth.hash_password()` to produce a real bcrypt hash for the seeded user, instead of using the literal placeholder string. The plaintext password is read from env `NAAVIK_DEV_PASSWORD` if set, else generated randomly (16-char alphanumeric) and printed to stdout once at seed time:

```
[seed] dev user: shyam.padia930@gmail.com
[seed] dev password: A1b2C3d4E5f6G7h8  (set NAAVIK_DEV_PASSWORD env to override on next reseed)
```

(b) Tests use `NAAVIK_DEV_PASSWORD=test-pwd` so seeded credentials remain stable across CI runs.

**Why not always-random:** self-hosters rerunning `nix run .#dev` shouldn't need to re-read the boot log every time. Stable when env is set, surprising-but-recoverable when it isn't.

**Verification:** After `nix run .#dev`, log in via `/login` using `shyam.padia930@gmail.com` + the printed password. JWT cookie set; redirected to Overview.

---

**Item 4: Signup endpoint for first-user / multi-user (single-user MVP-friendly)**

Add `POST /api/v1/auth/signup` in `src/api/auth.py`:

- Accepts `email`, `password`, `keep_signed_in` form fields.
- 400 if email already exists.
- Hash password (cost=12), insert User + default Settings + empty Profile, issue JWT cookie, return 204 with `HX-Redirect: /onboarding`.
- Same brute-force rate-limit shared with login (5 attempts / 15min / IP).
- **Single-user MVP guard:** when the User table is non-empty AND `Settings.allow_multiple_users` is False (default), reject signup with 403. This makes signup work for the first-user bootstrap on a fresh install (when seed didn't run, or self-hoster wants a different email) but doesn't accidentally turn a self-hosted instance into a multi-tenant SaaS.

UI: replace the dead `/login?create=1` link with a real toggle in `pages/login.html` that switches the form between sign-in and sign-up. Same template, two modes.

**Verification:** On a freshly-migrated DB with no seed, hit `/login`, switch to "Create account", submit. Land on `/onboarding`. User row exists in DB.

---

**Item 5: `naavik` CLI subcommands — `init`, `vault rotate-key`, `vault status`**

Promote `src/main.py:main` from a 1-line uvicorn launcher to a proper argparse dispatcher:

```
naavik                          # default: run server (current behavior)
naavik serve                    # explicit alias for default
naavik init                     # interactive: prompt for SECRET_KEY (or generate), write to ~/.naavik/key.bin, init empty vault
naavik vault rotate-key --old=$OLD --new=$NEW [--no-backup]  # existing cli/vault.py code
naavik vault status             # print vault path, fingerprint, is_locked, scopes + key counts (no values)
```

Update `pyproject.toml [project.scripts]`: `naavik = "cli.main:main"`. Move the uvicorn launcher behind `naavik serve`. Existing `naavik-alembic` script untouched.

**Verification:** `naavik init` on a fresh install creates `~/.naavik/key.bin` (mode 0600) and a fresh empty `~/.naavik/secrets.enc`. `naavik vault status` prints fingerprint + scope summary. `naavik vault rotate-key --old=A --new=B` re-encrypts cleanly.

---

**Item 6: Settings · LLM Provider form-wiring**

`src/ui/templates/pages/_settings_llm.html` rewrite:

- Wrap provider radios + API key input + Save button in a single `<form hx-put="/api/v1/settings/llm" hx-swap="outerHTML">`.
- Per-provider model dropdown: when the radio changes, swap the model `<select>` options via HTMX `hx-trigger="change" hx-get="/_fragments/settings/llm/model-options?provider={{value}}"`. Server-side endpoint returns the right model list:
  - Anthropic: `claude-3.5-sonnet-20250219`, `claude-3.5-haiku-20250219`, `claude-3-opus-20240229`
  - OpenAI: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`
  - Ollama: `llama3.1:70b`, `llama3.1:8b`, `qwen2.5:32b`, plus a free-form input for custom local models
- Per-provider API-key placeholder + visibility:
  - Anthropic: `sk-ant-…` placeholder, key required
  - OpenAI: `sk-…` placeholder, key required
  - Ollama: API key field hidden (or shown as "not required (local model)"), `OLLAMA_BASE_URL` field shown instead
- Autosave indicator on save (existing component pattern from profile editor).
- "Test connection" button continues to work; gains visual feedback that says which provider was tested.

The `PUT /api/v1/settings/llm` endpoint already exists in `src/api/settings.py:39-50`; this item is purely template + new fragment endpoints, no service-layer changes.

**Verification:** Click Ollama on `/settings/llm-provider`. Model dropdown changes to Llama options. API-key field hides. Click Save. Reload. Ollama is selected; vault has no `llm/anthropic` overwrite.

---

**Item 7: Settings · Deployment vault-locked banner**

`src/ui/templates/pages/_settings_deployment.html` adds a top banner that consumes the new helper:

```jinja
{% if deployment.vault_locked %}
  <div class="rounded-lg bg-rose-500/10 border border-rose-500/30 p-4 mb-4">
    <div class="flex gap-3 items-start">
      <i data-lucide="alert-triangle" class="h-5 w-5 text-rose-400 shrink-0" stroke-width="1.5"></i>
      <div class="flex-1 min-w-0">
        <h3 class="text-sm font-medium text-rose-200">Vault locked — SECRET_KEY mismatch</h3>
        <p class="text-xs text-rose-300/80 mt-1">The on-disk vault was encrypted with a different
          <code class="font-mono">SECRET_KEY</code>. Reads of secrets fail; writes are rejected.
          Run <code class="font-mono">naavik vault rotate-key</code> with the old + new keys, or
          restore the original <code class="font-mono">SECRET_KEY</code> env var.</p>
        <p class="text-xs text-rose-300/60 mt-2 font-mono">
          stored fingerprint: {{ deployment.vault_fingerprint_stored | default("(none)") }}<br>
          expected fingerprint: {{ deployment.vault_fingerprint_expected | default("(none)") }}
        </p>
      </div>
    </div>
  </div>
{% endif %}
```

`get_deployment_info()` already exposes `vault_locked: bool`, `vault_fingerprint_stored: str|None`, `vault_fingerprint_expected: str|None` per the Wave 4 deviation note. Confirm those fields are present; if not, add them.

**Verification:** Set `SECRET_KEY=different-value` in env, restart server, hit `/settings/deployment`. Banner renders with both fingerprints visible. Revert the env var, banner disappears.

---

**Item 8: ROADMAP wave-numbering cleanup**

Edit `ROADMAP.md` line 3 ("Last updated") to use ROADMAP's canonical Wave 4/5 labels instead of plan-internal Wave 3/6:

> Last updated: 2026-05-03 (Wave 5 / plan 10 § C EXECUTED — 14 services + …)

No structural changes; pure rewording. Add a one-line clarification near the top of § Implementation waves explaining the cross-walk for new readers (the cross-walk already exists in the archived plan; ROADMAP just doesn't reference it).

---

**Item 9: README rewrite**

`README.md` § "Manual local development setup" + § "Operations" rewrite to reflect Phase 1 reality:

New section: **"First-time setup (live DB)"**
1. `nix run .#dev` boots Postgres + alembic + seed + FastAPI in one terminal. The orchestrator's first run prints the dev login credentials to stdout.
2. To set credentials yourself: `export NAAVIK_DEV_PASSWORD="your-password"` before `nix run .#dev`.
3. Visit `http://localhost:8000/login`, sign in with the printed credentials. JWT cookie is set; you land on Overview.
4. Visit `/settings/llm-provider`, pick a provider, paste your API key, hit Save. Test the connection. Cost cards begin populating.
5. The vault at `~/.naavik/secrets.enc` holds your API key encrypted; DB row holds only the sha256 fingerprint.

New section: **"Signup (multi-user / fresh-install)"**
1. If the User table is empty (fresh DB, no seed), hit `/login`, click "Create account", enter your email + password.
2. Single-user MVP rejects subsequent signups via 403 unless `Settings.allow_multiple_users=true`.

New troubleshooting subsection: **"`greenlet_spawn` / `libstdc++` errors under `nix run .#dev`"**
- If `nix run .#dev` was started without the `LD_LIBRARY_PATH` export and you see `the greenlet library is required to use this function`, your `flake.nix` is older than 10b. Pull the latest.

New troubleshooting subsection: **"`SECRET_KEY` mismatch / vault locked"**
- The Deployment tab in Settings surfaces a rose banner when this is the case. Either restore the original `SECRET_KEY` or run `naavik vault rotate-key --old=$OLD --new=$NEW`.

Updated env vars table: `NAAVIK_DEV_PASSWORD` (seeded credential override), retain `NAAVIK_PERSISTENCE` (now defaults to `db` under orchestrator).

---

### B · File-by-file edits

| File | Item | Change |
|---|---|---|
| `flake.nix` | 1, 2 | Add `LD_LIBRARY_PATH` + `NAAVIK_PERSISTENCE=db` to `devEnv` |
| `src/db/seed.py` | 3 | Replace placeholder hash with `hash_password(env_or_random)`; print credential |
| `src/db/sample_data.py` | 3 | Drop the placeholder string from the `USER` shadow (seed now hashes at runtime) |
| `src/api/auth.py` | 4 | Add `POST /api/v1/auth/signup` with single-user guard |
| `src/ui/templates/pages/login.html` | 4 | Toggle between sign-in / sign-up modes; replace dead `/login?create=1` link |
| `src/ui/routes/auth.py` | 4 | `GET /login?mode=signup` renders the signup variant |
| `src/cli/main.py` (new) | 5 | argparse dispatcher: serve / init / vault rotate-key / vault status |
| `src/cli/init.py` (new) | 5 | `naavik init` — prompt for SECRET_KEY, generate if blank, write to `~/.naavik/key.bin`, init empty vault |
| `src/cli/vault.py` | 5 | Rename `cmd_rotate_key` → `cmd_vault_rotate_key`; add `cmd_vault_status` |
| `pyproject.toml` | 5 | `[project.scripts] naavik = "cli.main:main"` |
| `src/main.py` | 5 | Move uvicorn launcher to `cli.main:cmd_serve`; keep `main()` as alias for backwards compat |
| `src/ui/templates/pages/_settings_llm.html` | 6 | Form-wrap; provider-aware swap; HTMX hx-trigger on radio change |
| `src/ui/routes/settings.py` | 6 | Add `GET /_fragments/settings/llm/model-options?provider=` and `GET /_fragments/settings/llm/api-key-field?provider=` |
| `src/ui/templates/pages/_settings_deployment.html` | 7 | Add vault-locked banner block |
| `src/services/settings_service.py` | 7 | Confirm `get_deployment_info()` returns `vault_locked` + both fingerprint fields; add if missing |
| `ROADMAP.md` | 8 | Reword "Last updated" line; add Wave-cross-walk pointer near § Implementation waves |
| `README.md` | 9 | Rewrite § "Manual local development setup" + add troubleshooting subsections |

### C · Tests

| File | Status | Coverage |
|---|---|---|
| `tests/test_auth.py` | extend | Add `test_signup_first_user_succeeds`, `test_signup_rejects_when_users_exist_and_multi_disabled`, `test_signup_password_hash_is_real_bcrypt` |
| `tests/test_seed.py` (live-DB) | extend | After seed, `verify_password(NAAVIK_DEV_PASSWORD or known_test_value, user.password_hash)` returns True |
| `tests/test_cli.py` (new) | new | `naavik init` writes key file; `naavik vault status` prints fingerprint; `naavik vault rotate-key` round-trips |
| `tests/test_settings_llm_form.py` (new) | new | PUT `/api/v1/settings/llm` with provider=ollama swaps Settings.llm_provider; `GET /_fragments/settings/llm/model-options?provider=ollama` returns Llama options |
| `tests/test_pages.py` | extend | `/login?mode=signup` renders signup form; `/settings/deployment` with mismatched fingerprint renders banner |

All existing 448 tests must still pass. Live-DB tests opt-in via `NAAVIK_LIVE_DB=1` per Wave 3 convention.

### D · Build sequence

Single fresh implementation session, ~1 day end-to-end:

1. Items 1, 2, 8 (orchestrator + ROADMAP wording) — 30 min, low-risk warmups.
2. Items 3, 4 (seed credential + signup) — 2 hours; touches the auth boundary.
3. Item 5 (CLI dispatcher) — 1.5 hours; pyproject scripts, argparse, two new modules.
4. Items 6, 7 (Settings UI form-wiring + vault banner) — 2 hours; pure template + fragment endpoints, no service-layer changes.
5. Item 9 (README) — 1 hour after everything else lands so screenshots / commands are accurate.
6. Tests + ruff + alembic check + manual end-to-end smoke (login, signup, settings save, vault rotate) — 1 hour.

### E · Out-of-scope (explicitly deferred to ROADMAP)

- **B2 — `SECRET_KEY` boot-time enforcement** (refuse to start with default value or <32 bytes outside DEBUG). Add as PC.4 in ROADMAP § Pre-Phase-2 paper cuts.
- **B3 — Password complexity rules** (min length, character classes, must-change-on-first-login flag). Add as PC.5 in ROADMAP § Pre-Phase-2 paper cuts.
- **B6 — Full `NAAVIK_PERSISTENCE` env-var removal** (migrate the remaining ~20 lower-traffic accessors + page handlers to service-layer DB reads). Add as a row in ROADMAP § Phase 1 deferred items, with a note that it gets its own plan when authored.
- **C1 — OIDC for self-hosted** (Authentik / Keycloak / Okta). Already in ROADMAP § Phase 1 deferred → Phase 2+.
- **C2 — Forgot-password / SMTP magic-link.** Phase 4 (`13-phase-4-email.md`).
- **C3 — JWT signing-key rotation** (multi-key kid header). Phase 6 / cloud-tier work.
- **C4 — Vault secrets browser UI** in Settings · Deployment. Phase 6 polish.

These are tracked in ROADMAP, not authored as plans yet — plan 10b doesn't touch them.

## Open questions

1. **Seed credential pattern: env-or-random vs. always-prompted?** Recommendation: **env-or-random** as drafted. Self-hosters who want stability set `NAAVIK_DEV_PASSWORD`; those who don't get a printed random value once. Always-prompt forces interactivity into a non-interactive orchestrator boot. — Awaiting confirmation.
2. **Single-user signup guard: default ON or OFF?** Recommendation: **default ON** (`Settings.allow_multiple_users=False`). Rationale: a self-hoster who exposes the app accidentally shouldn't end up with a SaaS. Multi-user is Phase 2+ proper. — Awaiting confirmation.
3. **CLI shape: subcommands under `naavik` vs. separate scripts (`naavik-init`, `naavik-vault`)?** Recommendation: **subcommands**, matches `git`, `cargo`, `kubectl`, `nix` ergonomics. — Awaiting confirmation.
4. **Should `naavik init` overwrite an existing vault?** Recommendation: **no, refuse with clear error message** ("vault exists at ~/.naavik/secrets.enc; run `naavik vault rotate-key` to change keys or delete the file manually if you really want to reset"). Prevents accidental wipe. — Awaiting confirmation.
5. **Do we need a `naavik db` namespace too?** (e.g. `naavik db migrate`, `naavik db seed`). Recommendation: **no for 10b**, keep `naavik-alembic` and `python -m db.seed` as separate scripts. Adding a `db` namespace is cosmetic and can land in a future PC plan. — Awaiting confirmation.

## Approval checklist

User ticks each item before plan moves to APPROVED.

- [ ] Scope items 1–9 are in 10b
- [ ] Out-of-scope items B2/B3/B6/C1-C4 deferred to ROADMAP backlog (not 10b)
- [ ] Q1: env-or-random seeded credential
- [ ] Q2: single-user signup guard default ON
- [ ] Q3: subcommand-style CLI (`naavik init`, `naavik vault rotate-key`)
- [ ] Q4: `naavik init` refuses to overwrite existing vault
- [ ] Q5: no `naavik db` namespace in 10b
- [ ] Build sequence ~1 day acceptable
- [ ] Test additions per § C acceptable
- [ ] File-by-file edit list per § B acceptable

Once every box is ticked, plan moves to APPROVED. Agent then authors `docs/prompts/10b-phase-1-finalization.md` (already drafted alongside this plan) — to be pasted into a fresh Claude Code session.
