# Plan 93 — services/ stray regroup + UI template layout + htmx ext pin

- **Type:** execution
- **Status:** EXECUTED (2026-07-05)
- **Predecessor:** `docs/plans/92-services-layout-finish.md` (EXECUTED). Plan 92 left 22
  flat modules in `services/` and did not touch `ui/templates/`, whose `components/`
  (125 files) and `pages/` (36 files) are flat sprawls. Owner feedback: still hard to
  identify — group the strays (utils/ for the rest), give templates a proper structure,
  and fix the remaining legacy htmx-1.x extension pin (`response-targets`).

## Part 1 — services/ strays

Same seam discipline as plan 92 (package `__init__` = public surface for
conftest-shimmed APIs; module-tier for everything else; importers flipped in-slice; no
facades). New/target homes:

| Module | New home | Seam notes |
|---|---|---|
| `_crypto` | `utils/crypto.py` | no test seams |
| `geo` | `utils/geo.py` | module-tier |
| `html_text` | `utils/html_text.py` | module-tier |
| `rate_limit` | `utils/rate_limit.py` | singleton buckets — single import path, all importers flip in-slice |
| `first_run` | `utils/first_run.py` | module-tier |
| `settings_service` | `settings/service.py` | conftest-shimmed + 5 patch strings → `services.settings.X`; callers alias `from services import settings as settings_service` (avoids colliding with `config.settings`) |
| `env_secrets` | `settings/env_secrets.py` | module-tier |
| `llm_models` | `settings/llm_models.py` | conftest-shimmed module-tier → guard walk extended to map `from services.<pkg> import <mod>` |
| `outreach_service` | `outreach/service.py` | conftest-shimmed → package surface; alias `outreach as outreach_service` |
| `contact_tracker` | `outreach/contacts.py` | conftest-shimmed → package surface; alias `outreach as contact_tracker` (same module object, both name sets re-exported) |
| `jwt_rotation_service` | `auth/jwt_rotation.py` | module-tier |
| `account_service` | `auth/account.py` | module-tier |
| `user_service` | `auth/users.py` (merge `get_user` in) | conftest shim → `setattr(auth, "get_user", ...)`; auth `__init__` re-exports |
| `application_analytics` | `applications/analytics.py` | module-tier |
| `ats_postmortem` | `applications/ats_postmortem.py` | module-tier |
| `generation_dispatch` | `generation/dispatch.py` | `_tasks` + `enabled` singletons — conftest kill-switch re-pointed in-slice; module-tier |
| `embedding_service` | `scorer/embeddings.py` | module-tier (scheduler lazy imports flip) |
| `scoring_history` | `scorer/history.py` | module-tier |
| `scraper_service` | `jobs/scraping.py` | caller-side patch (`notify_scrape_run_summary` from-import binding) kept; `scheduler/scraping.py` importer flips |
| `search_prefs` | `jobs/search_prefs.py` | module-tier |

**Stays flat (deliberate, documented):** `llm_tracker.py` — the cross-cutting cost seam
every domain calls (CLAUDE.md convention path); `overview_service.py` — the Overview
page read-model (conftest-shimmed; single coherent module, no domain package fits).

All 20 retired paths are appended to `tests/test_no_retired_service_paths.py::RETIRED`.
`tests/test_shim_targets_exist.py` gets the `from services.<pkg> import <mod>` mapping
so module-tier shims stay guarded.

## Part 2 — ui/templates layout

Both trees get domain subfolders mirroring the nav + two generic buckets. All
references are quoted strings (`"components/x.html"` in py/tests/jinja) except two
audited dynamic sites: `tests/test_components.py::_CASES` (list of names — entries get
subpaths) and `settings.html {% include tab_template %}` (dict values in
`routes/settings.py` — swept). Grouping is by dominant referrer from a computed usage
map (`design_components` gallery references ignored for bucketing).

```
pages/                          components/
├── auth/      (6)              ├── common/    (27: _macros, avatar, button, card, chip_input,
├── overview/  (1)              │   confirm_modal, dropzone, editor_field, empty_state,
├── profile/   (2)              │   field_label, info_card, input, keyboard_hints, kpi_card,
├── discover/  (7)              │   modal, progress_bar, score_circle, section_anchor_nav,
├── jobs/      (2)              │   spinner, status_badge, status_dot, step_indicator,
├── tracking/  (5)              │   tag_picker, tip_card, toast, version_pill, view_toggle)
├── outreach/  (2)              ├── shell/     (3: sidebar, auth_shell, api_status_dot)
├── settings/  (10)             ├── overview/  (5)   ├── profile/  (23)
└── dev/       (1: design       ├── discover/  (21)  ├── jobs/     (3)
    gallery)                    ├── tracking/  (18)  ├── outreach/ (7)
                                └── settings/  (18)  └── ai_badge → common
```

(Exact 161-file mapping lives in the move script; the script asserts full coverage —
no file left unmapped, no mapping without a file.)

## Part 3 — htmx response-targets pin

`htmx.org@2.0.4/dist/ext/response-targets.js` is the htmx-1.x extension (same class as
the plan-91 SSE bug; 10 `hx-target-*` sites depend on it). Pin
`htmx-ext-response-targets@2.0.3/dist/response-targets.js` and live-verify an
error-response swap.

## Gate

Per slice: nix ruff check + format --check, full pytest (count only grows from
3348/15). Final: live Playwright sweep (owner user_id=2) incl. an hx-target-* error
swap, net-zero data, stack teardown (leave :8000/:5432).

## Deviations from plan

- **`user_service` had zero src consumers** — its `get_user` merged verbatim into
  `auth/users.py` (re-exported on the auth package) rather than moving as a module;
  the conftest shim + parity tests re-pointed to the package surface.
- **Two more `_pkg()` accessors were required** (`settings/service.py` for the six
  intra-module `get_or_create` calls; `outreach/service.py` for `mark_sent`'s
  `get_message` read) — same interception rule as plan 92 B4.
- **`__file__`-anchored path** — `utils/geo.py`'s `us_cities.json` lookup gained a
  directory level (`parents[2]`); caught by its own tests.
- **`tests/test_components.py::_CASES`** needed three passes (inline tuples,
  multi-line tuples, then a block-scoped rewrite) — the list mixes formats; the final
  rewrite maps every bare `X.html` inside the `_CASES` block.
- **Path-built (unquoted) template references** in `test_components` (open/glob) and
  `test_plan_86_batched_housekeeping` (`Path(...).read_text()`) were invisible to the
  quoted-string sweep — fixed by hand; the components glob is now recursive so the
  `dark:`-prefix lint keeps covering every file post-grouping.
- **`test_no_cross_user_embedding_reads`** pins the embeddings file path — re-anchored
  to `services/scorer/embeddings.py` (the lint stays meaningful).
- **Shim-guard extension**: `test_shim_targets_exist.py`'s AST walk now also maps
  `from services.<pkg> import <mod>` fixture imports, so module-tier shims
  (`settings.llm_models`) stay guarded (74 targets, none dropped).
