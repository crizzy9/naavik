---
Status: EXECUTED 2026-05-12
Type: implementation
Authored: 2026-05-09
Last updated: 2026-05-12
Depends on: 10b-phase-1-finalization (archived 2026-05-03 — EXECUTED)
---

# 10c · First-time setup ergonomics — devshell parity + signup affordance + creds surfacing

## Goal

A self-hoster who clones this repo, runs `nix run .#dev`, and opens
`http://localhost:8000` should be signed in within 30 seconds without reading
any documentation. Plan 10b shipped the moving parts; 10c closes the three
small ergonomic gaps that surfaced during 10b's smoke test. None of the items
are architectural; pure paper cuts.

## Context / why

10b ships a working signup endpoint, a real seeded credential, a vault-aware
Settings UI, and CLI subcommands — but live testing surfaced three friction
points that contradict the "30-second sign-in" goal:

1. **`nix develop` doesn't inherit the orchestrator's persistence default.**
   `flake.nix:devEnv` sets `NAAVIK_PERSISTENCE=db` so `nix run .#dev` reads
   from Postgres. `nix/devshell.nix:shellHook` does NOT set it, so an
   operator who drops into `nix develop` (or has direnv source it on `cd`)
   and runs `uv run python -m db.seed` or `uv run fastapi dev` ends up in
   memory mode by accident — same defect class as 10b item 1 / 2, just on
   the interactive-shell side instead of the orchestrator.
2. **The "Create account" link is buried.** The 10b-shipped login template
   correctly links `/login?mode=signup` from the footer, but the link sits
   between "Docs" and "Source" — the operator who wants to bootstrap on a
   fresh DB scrolls past the SSO info-card and a "Sign in" button before
   spotting it. And on a _seeded_ DB, `/login?mode=signup` renders the
   signup form anyway; the operator only learns that signup is gated when
   their POST returns 403 with no on-page explanation.
3. **The seed credential scrolls past quickly.** With `PC_DISABLE_TUI=true`
   in `flake.nix`, all four orchestrator processes (`deps`/`migrate`/`seed`/
   `app`) interleave their stdout with `[name]` prefixes. The `[seed]`
   credential line lands ~5 seconds before `[app]` reports
   "Application startup complete." and the trailing uvicorn banner. By the
   time the operator looks at the terminal, the credential has scrolled
   above the fold — the only recovery is `rm -rf .naavik/db && nix run .#dev`,
   which is loud for what should be a glance.

These are the same shape of paper cut 10b shipped (small, well-scoped,
operator-experience). 10c bundles them together as the next pre-Phase-2
follow-up so the rest of the testing playbook (POST_PHASE_1.md § Phase 1
testing playbook) can run cleanly.

## Proposal

### A · Scope

#### 10c.1 — `nix develop` honors `NAAVIK_PERSISTENCE=db`

`nix/devshell.nix:shellHook` already exports `LD_LIBRARY_PATH` and
`PYTHONPATH` for `nix develop` parity with the orchestrator. Add one more:

```nix
export NAAVIK_PERSISTENCE=db
```

Effects:

- `uv run python -m db.seed` inside `nix develop` writes to the live dev
  Postgres (port 5433) instead of mutating the in-memory shadow lists.
- `uv run fastapi dev src/main.py` inside `nix develop` (i.e. without the
  orchestrator) reads from the live DB.
- `direnv` flows pick this up automatically — `.envrc` sources `nix develop`
  on `cd`, so anyone with direnv allowed gets the same default.

**Doc cross-walk:** README § "Dev / test env vars" `NAAVIK_PERSISTENCE` row
default column changes from:

> `db` (orchestrator) · `memory` (bare Python)

to:

> `db` (orchestrator + `nix develop` + direnv) · `memory` (bare Python
> outside the dev shell)

**Verification:**

```bash
nix develop --command bash -c 'echo "$NAAVIK_PERSISTENCE"'
# → db
```

#### 10c.2 — Signup link + first-time setup affordance

Two changes to the auth UI.

**(a) Promote "Create account" out of the footer into a prominent CTA.**

`src/ui/templates/pages/login.html` currently buries the toggle:

```jinja
<footer class="… text-xs text-slate-500">
  …
  <a href="/login?mode=signup" class="…">Create account</a>
  <span aria-hidden="true">·</span>
  <a href="https://github.com/crizzy9/naavik" …>Docs</a>
```

Move the link out of the footer into a single-line affordance below the
"Sign in" button. The change:

- In sign-in mode: show an unobtrusive link below the SSO info-card —
  `<p class="mt-3 text-center text-sm text-slate-400">First time?
<a href="/login?mode=signup" class="text-indigo-300 hover:text-indigo-200
font-medium transition">Create account</a></p>`
- In sign-up mode: mirror with `<p class="mt-3 text-center text-sm
text-slate-400">Already have an account? <a href="/login" class="…">
Sign in</a></p>`
- Remove the link from the footer; keep "Docs" / "Source" only.

This keeps the visual hierarchy primary→sign-in-button, secondary→ alternate-
mode link. No icon inflation; no full-width outline button. Matches the
auth aesthetic that 10b's SSO info-card already uses.

**(b) Banner when signup is disabled on the instance.**

When the User table is non-empty AND `Settings.allow_multiple_users=False`,
the existing signup form silently posts to `/api/v1/auth/signup` and gets a
403 back — confusing for an operator who just hit the "Create account"
link. Pre-empt this on the server side.

Plumbing:

- `src/ui/routes/auth.py:get_login` queries the User count + Settings
  `allow_multiple_users` (one combined check) and computes a server-side
  `signup_disabled: bool` (`users_exist AND not allow_multiple_users`).
- Pass `signup_disabled` into `pages/login.html` template context.
- Template: `{% if is_signup and signup_disabled %}<banner>{% else %}<form>
{% endif %}`. Banner content:

  ```jinja
  <div class="mt-6 rounded-lg bg-amber-500/10 border border-amber-500/30 p-4">
    <div class="flex gap-3 items-start">
      <i data-lucide="lock" class="h-5 w-5 text-amber-300 shrink-0" stroke-width="1.5"></i>
      <div class="flex-1 min-w-0">
        <h3 class="text-sm font-medium text-amber-100">This instance already has an account.</h3>
        <p class="text-xs text-amber-200/80 mt-1">Sign-ups are disabled on a single-user instance.
          <a href="/login" class="font-medium underline underline-offset-2 hover:text-amber-50">Sign in</a>
          with the existing account, or contact your admin to enable multi-user
          (Settings · Deployment).</p>
      </div>
    </div>
  </div>
  ```

**Naming nuance:** the kickoff prompt names this flag `is_user_table_empty`.
Plan 10c uses `signup_disabled` (matching what `POST /api/v1/auth/signup`
actually rejects on) so the banner respects an admin who flipped
`Settings.allow_multiple_users=True`. Documenting up-front instead of as
a deviation. If the user prefers the simpler `is_user_table_empty` flag
(banner shows on any non-empty DB, even when multi-user is on), say so on
the approval checklist and the implementation flips a one-liner.

**Verification:**

```bash
# fresh DB (no seed)
curl -s http://localhost:8000/login?mode=signup | grep -c 'name="email"'
# → 1   (signup form rendered)

# seeded DB
curl -s http://localhost:8000/login?mode=signup | grep -c 'instance already has an account'
# → 1   (banner rendered)
```

Plus a Playwright snapshot capture of `/login?mode=signup` against the
seeded DB to commit alongside the existing baseline.

#### 10c.3 — Seed credential surfacing

Two pieces.

**(a) Persist the dev credential to disk + echo at app startup.**

`src/db/seed.py:seed()` already prints the generated credential once. Add
a write-to-disk step alongside the print, gated on:

- `dev_password_source == "generated"` (env-supplied passwords are owned by
  the operator — never persist them)
- AND `app_settings.debug` is True (production self-hosters with debug=False
  never get the file)
- AND the seeded `Settings.deployment_mode == DeploymentMode.SELF_HOSTED`
  (managed-cloud installs: never persist plaintext)

Path: `Path(app_settings.data_dir) / "dev-credentials"`, mode 0600. Resolves
to `./.naavik/dev-credentials` under the orchestrator (gitignored alongside
`./.naavik/db/`), or `~/.naavik/dev-credentials` for self-hosters who set
`DATA_DIR=~/.naavik`. File contents (two-line format, simple to parse):

```
email: shyam.padia930@gmail.com
password: K7nQ2pXa4VtRm9zL
```

A second piece — make the app re-print the credential after lifespan
startup so it's near the bottom of the orchestrator's scrollback. Add a
fire-and-forget asyncio task in `src/main.py:lifespan` that:

1. Sleeps ~750ms (lets uvicorn finish its "Application startup complete." +
   "Uvicorn running on <http://127.0.0.1:8000>" lines).
2. Reads `~/.naavik/dev-credentials` if it exists.
3. Logs the contents at INFO level via Python logging — process-compose
   prefixes the line with `[app]` so it interleaves with the rest of the
   orchestrator's stdout.

Pseudocode in `src/main.py`:

```python
async def _echo_dev_credentials_after_start():
    from config import settings as app_settings
    from pathlib import Path
    await asyncio.sleep(0.75)
    creds_path = Path(app_settings.data_dir) / "dev-credentials"
    if not creds_path.exists():
        return
    log.info("─── dev credentials (also at ~/.naavik/dev-credentials) ───")
    for line in creds_path.read_text().splitlines():
        log.info("  %s", line)
    log.info("───────────────────────────────────────────────────────")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if app_settings.debug:
        asyncio.create_task(_echo_dev_credentials_after_start())
    # … existing scheduler boot …
```

The 750ms delay is best-effort: if uvicorn's startup banner takes longer
(slow CI), the credential lands slightly above it. Acceptable — the
on-disk file at `~/.naavik/dev-credentials` is the canonical retrieval
path for any case where the timing slips.

**Spec deviation note:** the kickoff prompt's primary path was "have the
`app` step echo it on startup." A native lifespan task is cleaner than
shell-piping in `flake.nix` and works identically under Docker/NixOS.
Acceptable trade-off; fits the prompt's spirit. Documented up-front.

**(b) Document `cat ~/.naavik/dev-credentials` — no CLI extension.**

The retrieval path is plain `cat`, not a new CLI subcommand. Rationale:
the `naavik` CLI is on a sunset track per ROADMAP § Phase 2 task 2.11
(decided 2026-05-10) — operator features migrate INTO the Settings UI,
not into more CLI surface. Adding `naavik dev creds` would walk the
wrong direction. `cat` covers the same need with zero new code, zero
test scaffold, no precedent for a `dev` subcommand-namespace, and
nothing to remove on the way to the sunset.

If the operator wants shred-after-read semantics:

```bash
cat ~/.naavik/dev-credentials && rm ~/.naavik/dev-credentials
```

— a one-liner the README documents under § "First-time setup (live DB)".

The lifespan echo (10c.3(a)) above also drops the inline reference to
`naavik dev creds` from its log line — the comment renders as
`─── dev credentials (also at ~/.naavik/dev-credentials) ───` instead.

**Doc cross-walk for 10c.3:**

- README § "First-time setup (live DB)" — replace the "capture that
  line" paragraph with "If you missed the credential, run
  `cat ~/.naavik/dev-credentials` to read it back; chain with
  `&& rm ~/.naavik/dev-credentials` to clear the file once captured."
- README § Configuration § DATA_DIR comment — add
  `dev-credentials — plaintext dev login (mode 0600, debug only)` line.
- README § Operations § `naavik` CLI table — **NOT** extended (CLI sunset
  per ROADMAP § Phase 2 task 2.11). Add a one-line note at the top of
  that section pointing at the sunset row so future agents see the
  policy before reaching for a CLI fix.
- CLAUDE.md "Last updated" — bump with new operational surface
  (`dev-credentials` path) AND the CLI sunset policy reference.
- POST_PHASE_1.md § "What 'Phase 1 done' looks like" step 2 — append:
  "(credential prints on first boot AND lands at
  `~/.naavik/dev-credentials`, mode 0600, for later retrieval via
  `cat`)".

### B · File-by-file edits

| File                                                    | Item         | Change                                                                                                                                       |
| ------------------------------------------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `nix/devshell.nix`                                      | 10c.1        | Add `export NAAVIK_PERSISTENCE=db` to `shellHook`                                                                                            |
| `README.md` § Dev/test env vars                         | 10c.1        | Update `NAAVIK_PERSISTENCE` default-column wording                                                                                           |
| `src/ui/templates/pages/login.html`                     | 10c.2(a)+(b) | Promote signup link to prominent CTA; render banner when `is_signup AND signup_disabled`; drop footer link                                   |
| `src/ui/routes/auth.py:get_login`                       | 10c.2(b)     | Compute `signup_disabled = users_exist AND not allow_multiple_users`; pass into context                                                      |
| `src/db/seed.py`                                        | 10c.3(a)     | Write `dev-credentials` to disk when generated + debug + SELF_HOSTED                                                                         |
| `src/main.py`                                           | 10c.3(a)     | Add `_echo_dev_credentials_after_start()` lifespan task (gated on debug)                                                                     |
| `tests/test_pages.py`                                   | 10c.2        | Extend: `/login?mode=signup` against fresh DB renders form; against seeded DB renders banner. Plus a Playwright snapshot of the banner state |
| `tests/test_seed.py` (or new `tests/test_dev_creds.py`) | 10c.3(a)     | Assert `dev-credentials` is written on generated path + correct mode (0600) + NOT written when env-supplied                                  |
| `README.md`                                             | 10c.3        | First-time-setup paragraph + § Operations / `naavik` CLI sunset note + DATA_DIR comment (NO new CLI rows)                                    |
| `CLAUDE.md`                                             | all          | Bump "Last updated" with new operational surface line + CLI sunset policy reference                                                          |
| `ROADMAP.md` § Pre-Phase-2 paper cuts                   | all          | Add PC.7 row pointing at 10c; mark `[~]` on plan-author, `[x]` after archive; bump "Last updated"                                            |
| `docs/plans/POST_PHASE_1.md`                            | 10c.3        | Append parenthetical to "What 'Phase 1 done' looks like" step 2 about credential retrieval                                                   |

**Not modified by 10c (per CLI-sunset policy):** `src/cli/main.py`,
`src/cli/dev.py` (would have been new), `pyproject.toml [project.scripts]`,
`tests/test_cli.py`. CLI sunset is tracked at ROADMAP § Phase 2 task 2.11.

### C · Tests

| File                           | Status | Coverage                                                                                                                                               |
| ------------------------------ | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/test_pages.py`          | extend | `test_login_signup_mode_renders_banner_on_seeded_db`, `test_login_signup_mode_renders_form_on_fresh_db`, `test_login_signin_has_prominent_signup_link` |
| `tests/test_seed.py` (live-DB) | extend | `test_seed_writes_dev_credentials_when_generated_in_debug_mode`, `test_seed_skips_dev_credentials_when_password_from_env`                              |
| `tests/visual/baseline/`       | extend | One new desktop PNG: `login-signup-banner-desktop.png` (banner state)                                                                                  |

Net new tests: **~5** (3 page tests + 2 seed-credential tests). All 475 existing tests must still pass.

### D · Build sequence

Single fresh implementation session, ~½ day end-to-end:

1. **10c.1 + README env-var table** — 15 min, near-trivial.
2. **10c.2(a)** — login.html promotion of signup link — 30 min, template-only.
3. **10c.2(b)** — `get_login` server-side gate + banner template + tests — 1 hour.
4. **10c.3(a)** — seed write-file + lifespan echo + tests — 1.5 hours; touches three files (seed + main + config-import).
5. **README + CLAUDE.md + POST_PHASE_1 updates** — 30 min (including the README § Operations sunset note).
6. **Tests + ruff + ruff format check + manual smoke** — 30 min.

### E · Out-of-scope (explicitly deferred)

- **CLI extension of any kind.** Decided 2026-05-10. The `naavik` CLI is
  on a sunset track at **ROADMAP § Phase 2 task 2.11**; the encrypted
  vault that the CLI mostly serves is on a parallel sunset track at
  **task 2.12** (env-based secrets via gitignored `.env`, sequenced
  before 2.11). 10c writes no new subcommands. Bare `naavik` not being
  on PATH today is a known defect — it gets fixed at sunset (deletion
  makes the bug disappear), not by adding a wrapper script. AGENTS.md
  § Key Conventions § CLI captures the policy for future agents.
- **Vault changes of any kind.** 10c continues to use the existing
  vault for any DB-stored fingerprint references (it doesn't touch
  them), but does NOT add new scopes, keys, or vault helpers. The
  vault is being removed in 2.12; new secret material goes through
  env vars per that task's pattern when it ships.
- **Wave-4 partial-swap accessor cleanup (B6 in ROADMAP § Phase 1 deferred).**
  10c sets the env var default for `nix develop`; the long-tail accessor
  swap stays separate.
- **`Settings.allow_multiple_users` default flip.** Stays `False`. 10c.2(b)
  surfaces signup-disabled state cleanly; flipping the default is a Phase 2+
  multi-tenancy decision.
- **OIDC integration.** Phase 2+, plan TBD.
- **Multi-step onboarding for first-user signup.** First user lands on
  `/onboarding`, which is already wired (10b). 10c does not touch that
  flow.
- **PC.5 / PC.6 (`SECRET_KEY` boot-time enforcement, password complexity).**
  Stay as their own ROADMAP rows; 10c does not bundle them.
- **Cloud-tier credential surfacing.** The `dev-credentials` file is gated
  on `Settings.deployment_mode == SELF_HOSTED + Settings.debug`. Cloud-tier
  installs run with debug=False and never produce the file. No further
  hardening needed in 10c.

## Open questions

1. **Banner gate: `is_user_table_empty` vs `signup_disabled`?** Recommendation:
   `signup_disabled` (= `users_exist AND not allow_multiple_users`) so the
   banner respects an admin who toggled multi-user on. Slightly more state
   to plumb (one extra Settings query in `get_login`), but matches what
   `POST /api/v1/auth/signup` actually rejects on. Falls back to
   `is_user_table_empty` (one less query) on user request — single-line flip.
2. **`dev-credentials` path resolution.** Recommendation: write
   `Path(app_settings.data_dir) / "dev-credentials"`. This respects DATA_DIR
   overrides. Alternative: hardcode `~/.naavik/dev-credentials`. The hardcode
   mismatches the orchestrator default (`./.naavik/`); recommend the
   data-dir-relative path. Path also gets documented in README §
   Configuration § DATA_DIR comment so self-hosters know where to look.
3. **Lifespan echo: 750 ms delay vs alternative scheduling?** Recommendation:
   start with 750 ms (safe enough on warm reload, may print slightly above
   the uvicorn banner on cold boot). Alternative: subscribe to an
   `app.on_event("startup")` and rely on event ordering — but FastAPI's
   lifespan handlers run BEFORE uvicorn logs "Application startup complete.",
   so an explicit delay is the cleanest portable approach. If 750 ms is too
   long during reload cycles, drop to 500 ms; if too short on slow boots,
   bump to 1500 ms. `cat ~/.naavik/dev-credentials` is the canonical
   recovery path either way.
4. **Should 10c also fold in Wave 4 partial-swap accessor cleanup?**
   Recommendation: **no**, it's its own plan once POST_PHASE_1 testing
   confirms which accessors actually matter. 10c stays scoped to first-
   time-setup ergonomics.

## Approval checklist

APPROVED 2026-05-10 — all items signed off; the next agent authors
`docs/prompts/10c-first-time-setup.md` and the user pastes it into a
fresh implementation session.

- [x] 10c.1 / 10c.2 / 10c.3 are the right slice for one paper-cut plan
- [x] Q1: `signup_disabled` (not `is_user_table_empty`) for the banner gate
- [x] Q2: dev-credentials file written at `app_settings.data_dir / dev-credentials`
- [x] Q3: 750 ms delay on the lifespan echo, `cat ~/.naavik/dev-credentials` as canonical recovery
- [x] Q4: Wave 4 partial-swap cleanup stays separate
- [x] No CLI extension — `naavik dev creds` dropped; CLI sunset tracked at ROADMAP § Phase 2 task 2.11
- [x] Build sequence ~½ day acceptable
- [x] Test additions per § C acceptable (~5 new)
- [x] File-by-file edit list per § B acceptable
- [x] Tracking row for 10c lands as PC.7 in ROADMAP § Pre-Phase-2 paper cuts
- [x] POST_PHASE_1.md gets the one-line append on step 2 of the smoke
- [x] CLAUDE.md "Last updated" bump captures the new `dev-credentials` operational surface AND the CLI sunset policy

Once APPROVED, the next agent authors `docs/prompts/10c-first-time-setup.md`
(matching numbering) and the user pastes that into a fresh implementation
session.

## Deviations from plan

Bullets follow `AGENTS.md` § Workflow step 7 — what changed, why, impact, and
any new operational surface.

- **Added `debug: bool = False` field to `src/config.py:Settings` (pydantic-settings) reading from `NAAVIK_DEBUG` / `DEBUG` env via `validation_alias=AliasChoices(...)`.** Why: the plan's pseudocode references `app_settings.debug` (from `config.py`), but no such field existed before 10c — `Settings.debug` is the DB-persisted column on `models/settings.py`, which is a different object. The shipped code now matches the plan's wording exactly. Impact: zero behavior change in production (default False, no env var set); the orchestrator (`flake.nix:devEnv`) now exports `NAAVIK_DEBUG=1` so the dev-credentials file write + lifespan echo fire under `nix run .#dev`. Consolidates with the existing `_legacy_env_gate()` in `ui/routes/design.py` so `/_design/components` ALSO unlocks under `nix run .#dev` for free. **New operational surface:** `NAAVIK_DEBUG` env var becomes a boot-time gate for the dev-credentials file + lifespan echo (in addition to its legacy role gating `/_design/components`). README § "Dev / test env vars" + CLAUDE.md "Last updated" both updated to reflect this.
- **Did NOT export `NAAVIK_DEBUG=1` from `nix/devshell.nix:shellHook`.** Why: the existing `tests/test_design_components_route.py::test_fixture_404_without_debug` asserts `assert "NAAVIK_DEBUG" not in os.environ` and would fail when pytest runs inside `nix develop`. The orchestrator (`flake.nix:devEnv`) DOES export it, so `nix run .#dev` still gets the credential file. Operators who run `uv run python -m db.seed` interactively from `nix develop` see the credential on stdout (the existing `[seed]` print line) — they're at an interactive prompt, so scrollback is not a problem there. Impact: minor — the dev-credentials file is orchestrator-only; under bare `nix develop` you read the credential from the seed's stdout. POST_PHASE_1.md § "Phase 1 done" step 2 already documents both retrieval paths.
- **`src/ui/routes/auth.py:_compute_signup_disabled` falls through to `False` (form renders) on any DB exception, not `True` (banner renders).** Why: failing closed would block a fresh-install operator from signing up if the DB query itself raised (e.g. migration not yet applied, transient driver issue). Showing the form and letting `POST /api/v1/auth/signup` enforce the gate is the safer fallback — the operator at most gets a 403 with the existing error card, exactly what 10b shipped. The 10c gate is purely an ergonomic preempt. Impact: zero behavior change for the happy paths; on a DB outage the operator sees a form that might 403, which matches pre-10c behavior. Documented inline in the helper's docstring.
- **`src/ui/routes/auth.py:_compute_signup_disabled` uses scalar selects (`select(Settings.allow_multiple_users)`) instead of loading the whole Settings row.** Why: same SQLModel-vs-SQLAlchemy `_key_not_found` quirk that 10b's deviations doc described — `select(Settings)` followed by `.allow_multiple_users` raised `KeyError` under the live FastAPI worker's cached compiled SELECT. Scalar select sidesteps the cache + ORM mapping path. Impact: zero behavior change; this is the same dodge plan 10b applied in `src/api/auth.py:post_signup`. Should be folded into the wider Wave-4 cleanup tracked in ROADMAP § Phase 1 deferred backlog (B6: full `NAAVIK_PERSISTENCE` env-var removal + sqlmodel-vs-sqlalchemy unification).
- **Updated `tests/visual/baseline/login-desktop.png` (existing baseline) in addition to adding `tests/visual/baseline/login-signup-banner-desktop.png` (new baseline).** Why: the sign-in mode's prominent "First time? Create account" CTA replaces the footer link, which is a visible diff against the plan-10a baseline. Leaving the old baseline would surface as a noisy visual regression on the next per-PR diff gate. Impact: one extra PNG churns in the baseline directory; matches the plan's intent. No new test infrastructure needed.
- **Live-DB seed test uses `session.execute(text(...))` instead of `session.exec(text(...))`.** Why: `tests/test_seed.py:_fresh_session()` returns a vanilla SQLAlchemy `async_sessionmaker` over `AsyncSession`, not the SQLModel async session, so the `.exec()` shortcut isn't available. Cosmetic; same SQL runs either way. **No operational surface change.**
- **`naavik dev creds` subcommand explicitly NOT added.** Why: this was the plan's primary spec-deviation note (locked at approval time). The `naavik` CLI is on a sunset track per ROADMAP § Phase 2 task 2.11; new operator surfaces ship as Settings UI or `.env`. The retrieval path is `cat ~/.naavik/dev-credentials`. README § Operations § `naavik` CLI gets a one-line "sunset track — do not extend" note at the top so future agents see the policy before reaching for a CLI fix. AGENTS.md § Key Conventions § CLI codifies the rule project-wide.
- **End-to-end smoke step 2 ("`[app]` lifespan echo appears in orchestrator scrollback") verified out-of-band rather than via the orchestrator's stdout capture.** Why: process-compose with `PC_DISABLE_TUI=true` routes per-process stdout through internal pipes that don't always flush to the parent's combined log file (we saw the `[seed]` lines but not the `[app]` lines in `/tmp/claude-1000/.../bou0g76yx.output`; the same lines did appear in the interactive terminal under `nix run .#dev`). The lifespan function `_echo_dev_credentials_after_start` was invoked directly under `python` against the actual `~/.naavik/dev-credentials` file and produced the exact banner-format expected (verified at hand-back); the orchestrator-side echo is the same code path. Impact: low — `cat ~/.naavik/dev-credentials` is the canonical recovery path and was verified end-to-end. The lifespan echo is a convenience; the on-disk file is the contract.
