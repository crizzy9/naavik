# Plan 92 — services/ layout finish: facade teardown + flat-module grouping

- **Type:** execution
- **Status:** EXECUTED (2026-07-05)
- **Predecessor:** `docs/plans/91-full-codebase-refactor-audit.md` (EXECUTED — this plan
  completes its deliberately-deferred 4.x importer flip, Phase 8 facade teardown, and
  skipped-optional 4.7 grouping)

## Goal

Retire the six plan-91 re-export facades (`application_service`, `document_generator`,
`bundle_generator`, `apply_site_resolver`, `linkedin_resolver`, `notifications`) and group
the remaining coherent flat modules into packages, so `services/` reads as a set of
domain packages with **one public surface each: the package `__init__.py`**
(`services/auth/__init__.py` is the already-shipped model). After this plan there are no
re-export facades left, and a guard test keeps retired dotted paths from creeping back.

## Locked design decision

Each package's `__init__.py` is the ONE public surface:

- Routes/services import `from services import applications` and call
  `applications.get_application(...)`.
- Conftest attribute shims and `patch("...")` strings target `services.applications.X`.
- The `svc()`/`_bg()`/`_li()` call-time accessors are re-pointed from the facade to the
  package `__init__` — or replaced with a direct import wherever the callee is **not** a
  patched/shimmed seam (checked per name against the seam inventory below).
- Importers that are themselves caller-side patch targets (e.g.
  `patch("services.scraper_service.notify_scrape_run_summary")`) keep their from-import
  binding form, re-pointed to the new home — flipping them to package-attribute reads
  would break the caller-side seam.

Two seam tiers (per-name check, not dogma):

1. **Package-surface seams** — names shimmed by conftest or patched cross-module: target
   `services.<pkg>.X`; internal cross-seam calls route through the accessor so the patch
   intercepts.
2. **Module-tier seams** — names patched where intra-module reads or call-time lazy
   from-imports resolve them (the premium-stage helpers, `portfolio_sync`, stdlib
   passthroughs like `subprocess`/`importlib`): target the implementation module
   `services.<pkg>.<mod>.X` directly; no accessor needed because patching a module's own
   global intercepts intra-module reads.

## Target tree

```
src/services/
├── __init__.py                  (stays empty)
├── applications/                __init__ ← absorbs application_service facade surface
│   ├── auto_apply.py common.py drafts.py email_suggestions.py engagement.py
│   └── export.py queries.py state.py submission.py
├── ats/                         (unchanged — submission adapters)
├── auth/                        (unchanged — already the model)
├── email/                       NEW (Phase B1)
│   ├── __init__.py              ← public surface
│   ├── service.py               (was email_service.py)
│   ├── sync.py                  (was email_sync.py)
│   ├── classifier.py            (was email_classifier.py)
│   ├── credentials.py           (was email_credentials.py)
│   ├── inference.py             (was email_application_inference.py)
│   ├── status_mapper.py         (was email_status_mapper.py)
│   ├── calendar_sync.py         (moved verbatim)
│   └── imap_host_guard.py       (moved verbatim)
├── generation/                  __init__ ← absorbs document_generator + bundle_generator
│   │                            surfaces (Phase A4/A5) + stage helpers (Phase B3)
│   ├── bullet_selection.py bundle.py bundle_premium.py common.py cost_cap.py
│   ├── cover_letter.py maintenance.py resume.py screeners.py snapshot.py trace.py
│   └── (B3 absorbed:) council.py critique_council.py _council_common.py
│       detector_loop.py tool_loop.py generation_eval.py voice_grounding.py
│       constitution.py ai_tell_blocklist.py burstiness_check.py keyword_coverage.py
│       ethics_preflight.py hiring_manager_extractor.py ats_parser_ensemble.py
│       ats_parser_fidelity.py
├── jobs/                        NEW (Phase B2)
│   ├── __init__.py service.py jd_enrichment.py extractor.py dedup.py
├── notify/                      __init__ ← absorbs notifications facade surface
│   └── channels.py events.py
├── profile/                     NEW (Phase B4)
│   ├── __init__.py service.py extraction.py portfolio_sync.py answers.py
├── resolution/                  __init__ ← absorbs apply_site_resolver +
│   │                            linkedin_resolver facade surfaces
│   └── board_probe.py common.py linkedin.py pipeline.py url_rules.py
├── scorer/                      (unchanged)
└── flat modules that stay: account_service, application_analytics, ats_postmortem,
    contact_tracker, _crypto, embedding_service, env_secrets, first_run,
    generation_dispatch, geo, html_text, jwt_rotation_service, llm_models, llm_tracker,
    outreach_service, overview_service, rate_limit, scoring_history, scraper_service,
    search_prefs, settings_service, user_service
```

**Planned skips (recorded as deviations at execution):**

- `services/llm_support/` is NOT created. `llm_tracker` has the largest importer fan-in
  in `services/` (17 src files + conftest + CLAUDE.md's "wrap every LLM call in
  `services/llm_tracker.tracked_call`" convention + the engineer-llm-tracker-wrap skill).
  Grouping two already-coherent modules buys zero decomposition and churns ~30 seams on
  the single most safety-critical seam in the codebase (cost tracking).
- Everything in the "flat modules that stay" list above — single-purpose modules where a
  move buys nothing (plan 91's 4.2 deviation already covers application_analytics /
  ats_postmortem / generation_dispatch).

## Seam-migration table (old patch path → new)

| Old seam | New seam | Notes |
|---|---|---|
| `patch("services.notifications.X")` (8 refs) | `patch("services.notify.X")` | all names incl. `_telegram_token`/`_discord_url`/`_send_*_scrape_run` re-exported in `notify/__init__` |
| `from services.notifications import y` (tests+src) | `from services.notify import y` | from-import form kept where caller-side patches pin it (scraper_service) |
| `from services import linkedin_resolver [as lr]` + `patch.object(lr, ...)` | `from services import resolution [as lr]` | linkedin names merge into `resolution/__init__`; `_AUTH_LOCK` + `settings` re-exported as bound names (singleton rule) |
| `from services import apply_site_resolver [as resolver]` + `patch.object` | `from services import resolution [as resolver]` | `asyncio` + `is_safe_destination` re-exports kept |
| `patch("services.apply_site_resolver._greenhouse_postings")` | `patch("services.resolution._greenhouse_postings")` | jd_enrichment flips to package-attr read |
| `patch("services.bundle_generator.X")` (26 refs) | `patch("services.generation.X")` | |
| `patch("services.bundle_generator.dg.Y")` (22 refs) | A4 interim: `patch("services.document_generator.Y")` → A5 final: `patch("services.generation.Y")` | both dotted paths mutate the same module object tests relied on |
| `patch("services.document_generator.X")` (20 refs) | `patch("services.generation.X")` | |
| `patch("services.document_generator.llm_tracker.tracked_call")` | `patch("services.generation.llm_tracker.tracked_call")` | `llm_tracker`/`get_provider`/`typst_compile`/`overflows` module re-exports kept in `generation/__init__` |
| `from services import document_generator as dg` (6 test files, 9 src) | `from services import generation as dg` | |
| `patch("services.application_service.X")` (9 refs) | `patch("services.applications.X")` | incl. the `ats_dispatch` alias |
| conftest `setattr(application_service, ...)` ×19 | `from services import applications` + setattr | `test_shim_targets_exist.py` AST walk resolves the new module path automatically |
| `patch("services.email_sync.{sync_account,test_imap_connection}")` | `patch("services.email.{...}")` | routes flip to package-attr reads |
| `patch("services.calendar_sync.{fetch_ics,validate_ics_url}")` | `patch("services.email.{...}")` | |
| conftest `setattr(email_service, ...)` ×3 | `from services import email as email_service` + setattr | alias avoids shadowing stdlib-`email` usage and local vars |
| `patch("services.job_service.get_job")` | `patch("services.jobs.get_job")` | |
| `patch("services.job_extractor.enrich_raw_job")` | `patch("services.jobs.enrich_raw_job")` | jd_enrichment reads package attr |
| conftest `setattr(job_service, ...)` ×9 | `from services import jobs as job_service` + setattr | alias keeps call sites and avoids `jobs` local-var shadowing in routes |
| `patch("services.profile_service.X")` (5 refs) | `patch("services.profile.X")` | |
| conftest `setattr(profile_service, ...)` ×12 | `from services import profile as profile_service` + setattr | alias avoids ubiquitous `profile` local-var shadowing |
| `patch("services.portfolio_sync.X")` (3 refs) | `patch("services.profile.portfolio_sync.X")` | module-tier |
| `patch("services.{council,critique_council,detector_loop,tool_loop,ats_parser_ensemble,ats_parser_fidelity,hiring_manager_extractor}.X")` | `patch("services.generation.<mod>.X")` | module-tier; premium stages are lazy from-imports read at call time |
| `patch("services.{tool_loop,detector_loop}.dg.is_cost_capped")` | `patch("services.generation.is_cost_capped")` | `dg` attr replaced by the `.common` svc() accessor when absorbed |
| `patch("services.ats_parser_ensemble.{subprocess,importlib,shutil}.X")` | `patch("services.generation.ats_parser_ensemble.{...}.X")` | stdlib module objects — any resolvable route works |
| `services.llm_tracker.*`, `services.llm_models.*` | **unchanged** | llm_support/ skipped (see deviations) |

Accessor re-targets:

| Accessor | Old target | New target |
|---|---|---|
| `notify/{channels,events}.svc()` | `services.notifications` facade | `services.notify` package |
| `resolution/common.svc()` | `services.apply_site_resolver` facade | `services.resolution` package |
| `resolution/linkedin._li()` | `services.linkedin_resolver` facade | `services.resolution` package |
| `resolution/pipeline` lazy `from services import linkedin_resolver` | facade | `svc()` (package-attr reads — linkedin machinery stays lazy) |
| `generation/common.svc()` | `services.document_generator` facade | `services.generation` package |
| `generation/{bundle,bundle_premium}._bg()` + top-level `dg` binds | `services.bundle_generator` / `document_generator` facades | `svc()` from `.common` (single accessor; avoids parent-package self-import at module load) |
| `applications/common.svc()` | `services.application_service` facade | `services.applications` package |

## Phase A — per-facade retirement (one commit-slice each, smallest seam surface first)

Per facade: (1) move re-exports into package `__init__`; (2) re-point conftest shims,
patch strings, monkeypatch targets, and test imports; (3) re-target/remove accessors;
(4) flip every src/ importer; (5) delete the legacy module. Full gate green per slice.

- **A1 notifications → notify/** — 8 patch refs, 1 test import file, 8 src importers
  (incl. scheduler lazy imports at jobs.py:39,444 and scraping.py:44).
- **A2 linkedin_resolver → resolution/** — no string patches; 5 test files import it +
  `patch.object`; 5 src importers (all lazy in pipeline.py + settings/fragments).
- **A3 apply_site_resolver → resolution/** — 1 string patch, 4 test files, 8 src
  importers; `svc()` re-point unlocks here.
- **A4 bundle_generator → generation/** — 26+22 patch refs, 8 test files, 6 src
  importers; `dg.*` strings re-point to `services.document_generator.*` (interim).
- **A5 document_generator → generation/** — 20 patch refs, ~10 test files, ~19 src
  importers; the `dg.*` interim strings collapse to `services.generation.*`.
- **A6 application_service → applications/** — 9 patch refs, ~20 test files, 16 src
  importers, 19 conftest setattrs + the fixture import list.

## Phase B — group remaining flat modules (importers flipped in-slice; NO new facades)

- **B1 services/email/** — the 8 email modules; scheduler jobs.py:344,364,365 lazy
  imports re-pointed; `services.email` inside the package never shadows stdlib `email`
  (absolute imports), but importers that also use stdlib email alias the package import.
- **B2 services/jobs/** — job_service→service, jd_enrichment, job_extractor→extractor,
  dedup.
- **B3 generation/ absorption** — the 15 stage helpers listed in the tree; per-file fit
  check; `bundle.py`/`bundle_premium.py` sibling imports become
  `services.generation.<mod>`; premium lazy imports in bundle_premium re-pointed.
- **B4 services/profile/** — profile_service→service, extraction, portfolio_sync,
  profile_answer_service→answers.

## Phase C — final sweep

- `tests/test_no_retired_service_paths.py`: scans src/ + tests/ for any dotted reference
  to the retired module paths (the six facades + every Phase-B-moved flat module); fails
  with the new path in the message.
- Update the architecture trees in `CLAUDE.md` and `docs/ARCHITECTURE.md`.
- Note completion in plan 91's Deviations section.

## Hard rules (carried from plan 91, still binding)

1. NEVER move the 24 scheduler job functions (`NaavikJsonJobStore.FUNC_REF_ALLOWLIST`
   pins `scheduler.jobs:*` / `scheduler.scraping:*`) or rename `scraping.<source>` job
   ids — the UI string-parses them. (Verified: no allowlisted callable lives in
   `services/`; the job bodies lazy-import services functions — those import lines are
   updated in the owning slice.)
2. Module-level singletons stay single-instance: `rate_limit` buckets,
   `services/auth/throttle._login_attempts`, `generation_dispatch._tasks` + `enabled`,
   `resolution/linkedin._AUTH_LOCK` + the session-health file. Package `__init__`
   re-exports bind the existing objects; never re-create.
3. `prompt_name` strings and `llm.prompts` module names are a de-facto schema — no
   renames (`settings_service._PREMIUM_STAGE_PROMPTS` buckets cost by them).
4. Lazy imports that remain are load-bearing cycle-breakers — don't hoist blindly.
   New rule for package internals: no submodule imports its parent package at module
   load; cross-seam routing is call-time via the accessor.
5. `tests/test_shim_targets_exist.py` must stay meaningful after each slice (its AST
   walk maps `from services import X as Y` → `services.X`, so re-pointed conftest
   imports keep it live).

## Gate (per slice + final)

- `nix develop -c ruff check .` && `nix develop -c ruff format --check .` (nix ruff only)
- `nix develop -c uv run pytest` — baseline 2847 passed / 15 skipped; count only grows
- Final: live Playwright pass via `nix run .#dev` (owner session, user_id=2), net-zero
  on real profile data, full stack teardown (kill process-compose + :8003/:5433; leave
  the :8000 uvicorn and :5432 Postgres alone)
- Commits local on `main`, explicit staged paths + `git commit -F <file>`

## Deviations from plan

- **llm_support/ skipped as planned** — recorded here per the "planned skips"
  section: `llm_tracker` + `llm_models` stay flat (largest importer fan-in,
  CLAUDE.md-documented convention path, zero decomposition gain).
- **Email sync/calendar seams landed module-tier, not package-tier.** The
  plan table mapped `services.calendar_sync.{fetch_ics,validate_ics_url}` →
  `services.email.{...}`; they landed at `services.email.calendar_sync.{...}`
  because those names are read intra-module (`sync_ics_calendar` reads its
  own module globals) — a package-tier patch would silently stop
  intercepting. Same per-name logic kept `classifier`/`inference`/
  `credentials`/`status_mapper`/`imap_host_guard` module-tier; only the
  conftest-shimmed thread API + the route-called `sync_account` /
  `test_imap_connection` / `sync_all_accounts` live on the package surface.
- **`profile/service.py` needed a new `_pkg()` accessor** (not in the plan's
  accessor table): pre-split, `update_field`/`set_raw_resume_text`/bullet +
  dossier CRUD called sibling seams (`get_profile`, `get_bullet`, …) as
  module globals — which WAS the patch surface. With seams moved to the
  package `__init__`, those intra-module reads had to route through the
  package or the conftest shims would silently stop intercepting
  (caught by `test_profile_bulk_put` going red mid-slice).
- **`bundle_generator.dg.*` patch strings took a two-hop migration** (A4 →
  `services.document_generator.*`, A5 → `services.generation.*`) exactly as
  planned; noting here that the interim hop was real (6 test files touched
  twice).
- **The guard test caught five vacuous scraper-site tests** — 
  `tests/test_scraper_sites/test_{greenhouse,lever,indeed,workday,linkedin}.py`
  pop/assert `sys.modules["services.job_extractor"]` to pin the lazy-import
  contract; after B2 they held the stale path and asserted vacuously.
  Re-pointed to `services.jobs.extractor` in Phase C.
- **`ats_parser_ensemble` repo-root resolution** — `_openresume_script_path`
  computed `parents[2]` from its old flat location; the B3 move added a
  directory level (`parents[3]`). Caught by its own regression test.
- **Import-flip mechanics:** multi-line parenthesized `from services import
  (...)` blocks and trailing-comment forms escaped the first grep passes in
  A6/B2/B4; a per-slice AST scan (ImportFrom walk) became the closing
  verification step. Callers keep domain-name aliases where the bare package
  name would shadow locals or stdlib (`jobs as job_service`,
  `profile as profile_service`, `email as email_service`) — the dotted seam
  (`services.jobs.X`) is what the design locked, not the local name.
