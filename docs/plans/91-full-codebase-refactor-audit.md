---
Status: APPROVED (2026-07-04 — owner said "go for it", defaults accepted)
Type: execution
Authored: 2026-07-04
Last updated: 2026-07-04
Depends on: docs/plans/archive/26-0.2.0.01-vault-deprecation.md (vault sunset — strands `ats_credentials.py`), docs/plans/archive/90-0.5.0-email-monitoring.md (EmailMessage/AppEventKind surface this plan touches)
---

# 91 · Full-codebase refactor — audit + phased plan (zero functionality loss)

## Goal

Refactor Naavik for modularity and maintainability, raise test coverage, and
fix the structural and data-model defects that have accumulated — **without
losing any functionality**. This plan is the synthesis of a six-front read-only
audit (services, data model, routes, infra, tests, dead code) whose
load-bearing findings were each re-verified against the actual code before
landing here. It is sequenced **safety-net-first**: characterization tests and
the full route/scheduler-job inventory (Appendices A–C) come *before* any
restructuring, so behaviour is provably preserved. Every phase is a set of
small, independently committable steps that each end green; **no behaviour
change is ever bundled into a "move" commit.**

## Context / why

`src/` is ~55.8k LOC over 202 modules, 169 templates, 197 HTTP routes, 24
scheduled jobs, 2689 tests. The pain is concentrated and now measured:

- **`services/` is a 61-module, 24k-LOC sprawl** with two true god-modules
  (`application_service.py` 2216 LOC / ≥7 responsibilities;
  `document_generator.py` 1989 LOC / ≥8) plus five more >500-LOC modules.
- **Verified functional bugs — cross-account data bleed.** Three routes read
  user-owned rows with **no auth at all**
  (`GET /api/v1/contacts/{id}`, `GET /_modal/bullet-editor/{id}`,
  `GET /_fragments/profile/bullet-row/{id}`), and several outreach/contacts
  routes are authed-but-unscoped IDOR (cross-user delete, read, mutate).
  Verified live in `src/ui/routes/outreach.py:152,176` and
  `src/ui/routes/fragments.py:149,174`.
- **Verified upgrade-crash bug.** Four `AppEventKind.AUTO_APPLY_*` members
  (`enums.py:195`) have no `ALTER TYPE appeventkind ADD VALUE` migration; any
  DB whose `0001` predates plan 78 raises `invalid input value for enum
  appeventkind` the first time auto-apply emits one.
- **Verified infra correctness bugs.** The LLM retry ladder is dead
  (`llm_tracker._classify_error` trusts `LLMProviderError.kind`, but every
  provider wraps SDK errors without setting it → 429/timeout retries never
  fire); the generation cost-cap uses a **local calendar date mislabeled UTC**
  as a third competing spend implementation (`document_generator.py:106`); the
  stored `llm_fallback_provider` setting is **inert** (`get_provider(fallback=True)`
  and `tracked_call(fallback_provider=…)` have zero call sites).
- **Duplication clusters:** council/critique batch dispatch (~110 lines, plus a
  `council_*`-vs-`critique_*` mislabel bug at `_council_common.py:57`), three
  scraper-site skeletons (~150 lines), a Fernet-from-SECRET_KEY helper copied
  verbatim across two crypto modules, five BeautifulSoup html→text copies, and
  ~16× hand-rolled LLM-call boilerplate.
- **Dead code:** one fully-dead module (`ats_credentials.py`), ~330 lines of
  CERTAIN-dead functions, ~320 lines of unreferenced templates, five
  settings routes that are **dead only by router-registration order** (a
  refactor that reorders `include_router` calls silently swaps real handlers
  for `{"ok": true}` stubs), and one unreachable route shadowed by a `{field}`
  catch-all.
- **The test suite is broad but brittle for *this* refactor:** `conftest`
  monkeypatches ~60 service functions **by attribute name**, so moving any of
  them silently un-shims 189 test files (green-but-meaningless, not red).
  ~100+ `patch("services.X.y")` string targets pin dotted module paths.
  → **Every symbol move must ship a same-name re-export in the same commit, and
  a shim-target guard test (Phase 0.1) must exist first.**

### Cross-cutting refactor rules (the hazards that make naïve moves unsafe)

These apply to **every** move/split step below:

1. **Re-export facades are mandatory.** When a symbol moves, the old module
   must re-export it (`from .new_home import foo`) until the final teardown
   phase. This keeps the 100+ `patch("services.X.y")` targets and the
   ~60 conftest attribute-shims resolving. The Phase 0.1 guard test enforces it.
2. **Scheduler job callables are allowlisted string refs.**
   `NaavikJsonJobStore.FUNC_REF_ALLOWLIST` (`scheduler/json_jobstore.py:47-82`)
   pins all 24 job functions as `module:qualname`. Moving/renaming any job
   function (or the `scheduler.jobs`/`scheduler.scraping` modules) must update
   the allowlist **in the same commit**, or persisted rows fail the allowlist
   at next boot and are deleted (losing `next_run_time` + pending manual runs).
   The UI also string-parses job ids (`fragments.py:91`, `settings.py:847`) —
   job ids must not change. **Keep all 24 job functions where they are; wrap,
   don't move.**
3. **Lazy imports are load-bearing cycle-breakers** (`apply_site_resolver`
   ↔ `linkedin_resolver`, `↔ jd_enrichment`, `↔ application_service`;
   `application_service` → `bundle_generator`; `ats/__init__` per-board). Do
   **not** hoist them to top-level during a move; the `resolution/` split
   (Phase 4.5) dissolves the biggest cycle deliberately.
4. **Dynamic prompt imports + `prompt_name` strings are a de-facto schema.**
   `document_generator.py:360,586,1779` use `__import__("llm.prompts.X")`;
   `settings_service._PREMIUM_STAGE_PROMPTS` buckets cost by literal
   `prompt_name` values. Renaming a prompt module or a `prompt_name` breaks at
   call-time / breaks cost attribution, invisible to static import tooling.
5. **Module-level singletons must stay single-instance:** `notifications._TOAST_QUEUE`,
   `rate_limit` buckets, `auth._login_attempts`, `generation_dispatch._tasks`
   + `enabled` (the autouse test kill-switch). A facade must re-export the
   module object / bound name, never re-create the state.

### Green gate (run at the end of every phase; a phase is not "done" until all pass)

- `nix develop -c ruff check .` and `nix develop -c ruff format --check .`
  (the nix-provided ruff; `uv run ruff` fails on NixOS dynamic linking).
- `nix develop -c uv run pytest` — full suite green (2689 baseline; count only
  grows).
- Live **Playwright** pass per `CLAUDE.md` for any phase touching routes/UI
  (headed chromium for PDF-embed checks per memory
  [[reference_playwright_pdf_embeds]]).
- **Net-zero on real profile data:** anything created while testing against the
  dev DB is deleted; mint a throwaway session per
  [[reference_dev_session_mint]] (owner is `user_id=2`).
- **Shut down every process started** — the `nix run .#dev` orchestrator leaks
  FastAPI children; kill them before declaring done (memory
  [[feedback_shutdown_processes]]). Never point destructive gates at the dev DB
  (memory [[feedback_destructive_test_gates]]).
- Commit locally on `main`, explicit paths + `git commit -F <file>` (memory
  [[feedback_git_commit_permissions]]). No push, no PR.

---

## Proposal — phase sequence

Nine phases, 0→8. Phases 0 and 3 are the safety net (tests only). Phases 1, 6,
7 are behaviour changes (bug fixes), each pinned by a test, each committed
separately from any move. Phases 2, 4, 5, 8 are behaviour-preserving
(deletion / moves / dedup). Ordering rationale: net first → fix the verified
functional bugs while the net is fresh → delete dead weight so we restructure
less code → pin god-module behaviour → decompose → dedup → infra correctness →
data model → tear down scaffolding.

### Phase 0 — Safety net (tests + inventory only; **zero `src/` behaviour change**)

| Step | Work | Files |
|---|---|---|
| 0.1 | **Shim-target guard test** — iterate the `(module, attr)` pairs `conftest._patch_services_to_sample_data` patches and assert each still exists on the un-patched real module via `getattr`. Turns "moved function silently un-shims 189 files" into a hard failure. **Prerequisite for all of Phase 4.** | `tests/test_shim_targets_exist.py` (new) |
| 0.2 | Extract the sqlite-tier engine/JSONB/ARRAY/CHECK-strip fixture (copied in ~22 files, canonical at `test_service_layer_parity.py:33-146`) into one importable helper. | `tests/_sqlite.py` (new) |
| 0.3 | Centralize the `client` / `auth_cookies` / `csrf` fixture trio in `conftest.py` (79 files self-roll `TestClient` + cookie/CSRF boilerplate today). | `tests/conftest.py` |
| 0.4 | Autouse `sample_data` snapshot/restore fixture (generalize `test_stub_endpoints.py:62-80`) to kill cross-test mutation pollution before refactor churn reshuffles order. | `tests/conftest.py` |
| 0.5 | **Commit this document** as the canonical no-regression checklist — Appendix A (197 routes), Appendix B (24 scheduler jobs), Appendix C (fire-and-forget + in-memory state). | this file |

Gate: pytest green (new tests pass and are meaningful — 0.1 must go red if you
temporarily rename a shimmed function, then green when restored). No `src/`
diff in this phase.

### Phase 1 — Security & correctness bugfixes (behaviour change; each = one bug + one test; not moves)

Cross-account data bleed is a functional bug (user's framing). These land
against fresh tests, RED first.

| Step | Work | Files |
|---|---|---|
| 1.1 | Generalize `test_applications_idor.py` into a **parametrized cross-user sweep** over every id-bearing route (jobs, contacts, outreach, generated-doc/PDF download, screeners, profile children). Author RED against current bugs. The shim `_get_job` ignores `user_id` (`conftest.py:203`) so these must run on the **sqlite tier** (0.2), not the shim tier. | `tests/test_cross_user_idor_sweep.py` (new) |
| 1.2 | Add `require_authed_session` + owner filter to the **unauthenticated DB-read** routes: `GET /api/v1/contacts/{id}` (`outreach.py:152`), `GET /_modal/bullet-editor/{id}` and `GET /_fragments/profile/bullet-row/{id}` (`fragments.py:149,174`). | `outreach.py`, `fragments.py`, `contact_tracker.py`, `profile_service.py` |
| 1.3 | Push `user_id` into the unscoped service signatures so IDOR can't recur: `contact_tracker.get_contact`, `outreach_service.{list_messages_for_application,list_messages_for_contact,mark_sent}`. Add ownership 404 to contacts delete/put (`outreach.py:176,164`) and outreach messages/draft/send/skip (`outreach.py:228-291`); ownership-check the `app_id`/`contact_id` params on draft creation. | `contact_tracker.py`, `outreach_service.py`, `outreach.py` |
| 1.4 | Introduce `get_owned_application` / `get_owned_contact` FastAPI dependencies (the ownership check is hand-rolled ~40× today) and adopt them in the Phase-1 routes. Full rollout deferred to 5.6. | `src/api/deps.py` (new) |
| 1.5 | **Migration:** `ALTER TYPE appeventkind ADD VALUE IF NOT EXISTS` ×4 for `AUTO_APPLY_DRY_RUN/DRAINED/VISA_BLOCKED/QUEUED` (autocommit block, mirrors 0022/0024). + up/down test. | `migrations/versions/00NN_*.py` (new), `tests/test_alembic_00NN.py` |
| 1.6 | CSRF consistency: add `require_csrf` to state-changing routes whose siblings have it but they lack it (contacts/bullets/screener/profile-field/email-draft/outreach — the client already sends the header via `base.html:29`, so UI is unaffected; verify with Playwright + tests). | `outreach.py`, `api/profile.py`, `discover.py`, `email.py` |

Gate per step + Playwright confirming the fixed routes still work for the owner.

### Phase 2 — Dead code removal (CERTAIN tier; mechanical, no behaviour change)

Each independently committable. Only CERTAIN-verified items here; SUSPECTED
items go to Open Questions.

| Step | Work |
|---|---|
| 2.1 | Delete `src/services/ats_credentials.py` (0 refs anywhere — triple-verified; vault-era orphan). |
| 2.2 | Delete CERTAIN-dead functions: `application_service.derive_recruiter_states` (`:1700`), `auth.get_or_create_settings` (`:457`), `settings_service.update_account_password` (`:205`), `extraction.extract_to_profile_sse` (`:92`), `contact_tracker.{upsert_contact,soft_delete,infer_link_referral_state,update_link_referral_state,silent_contacts_for_user}`, `notifications.notify_auto_apply_failed` (`:383`), `discover_ctx.up_next_dict`, `auth_stub.is_authenticated`, `models/_common.{tz_datetime_column,array_text_column,jsonb_column}`, `scheduler/jobs.registered_job_ids` (`:657`). |
| 2.3 | Resolve the toast SSE path: `notifications.stream_toasts` (`:65`) has zero refs and `push_toast` fills a `_TOAST_QUEUE` nothing drains — the live toast path is `HX-Trigger:{"showToast"}` via `base.js`. **Delete `stream_toasts`+`_TOAST_QUEUE`+`Toast`; convert `push_toast` callers to the `HX-Trigger` path or drop them.** (See Open Q4.) |
| 2.4 | Delete dead templates: `components/_audit_trail_viewer.html`, `_email_suggestion_banner.html`, `_profile_answer_diff.html`, `placeholder.html`, `kbd.html`, `tag_chip.html` (last two superseded by `_macros.html` macros; remove their `test_components.py` rows). |
| 2.5 | **Remove the 5 registration-order-shadowed settings stubs** in `ui/routes/settings.py`: `put_auto_apply` (`:981`), `put_sources` (`:989`), `put_notifications` (`:997`), `put_account` (`:1082`) `{"ok":true}` stubs, and the duplicate real `get_deployment` (`:1045`). The `api/settings.py` versions are canonical. This removes a silent-breakage landmine before any router reorg. |
| 2.6 | Fix the unreachable `PUT /api/v1/profile/application-questions` (`api/profile.py:615`, shadowed by `PUT /api/v1/profile/{field}` `:573`) — delete it (its function is unused) or move above the catch-all. |
| 2.7 | Drop `pyresume` from the `[premium-parsers]` extra in `pyproject.toml` (never imported). |

Gate. Deletions verified against Appendix A/B so no live route/job is touched.

### Phase 3 — God-module characterization tests (behaviour-pinning **before** the splits)

The document_generator tests today pin the *private call graph* (21
`patch("services.document_generator._private")`), not behaviour — they'd break
on the split without proving preservation. Fix that first.

| Step | Work |
|---|---|
| 3.1 | `application_service`: status-transition matrix as a table-driven test; AppEvent-emission assertions per mutation; auto-apply queue characterization (`process_auto_apply_queue`). |
| 3.2 | `document_generator`: one end-to-end test faking **only** `llm.get_provider` + `typst.compile`, letting `load_profile_snapshot`/spend-check/prompt modules run against a seeded sqlite session — the test that survives the split. |
| 3.3 | `profile_service`: sqlite-tier CRUD for `add_bullet`/`update_bullet`/`delete_bullet`/`reorder_bullets`/`owns_certification` (currently only exercised under the `NAAVIK_LIVE_DB` gate). |
| 3.4 | `apply_site_resolver`: MockTransport-level tests of `_fetch`/`_redirect_probe` classification (redirect/404/timeout) — network layer is wholesale-AsyncMock'd today. |
| 3.5 | `bundle_generator`: failure-path (partial bundle on typst failure) + the untested `answer_screener` leg. |

Gate.

### Phase 4 — Structural decomposition (behind re-export facades; one module per commit-cluster)

Rule from cross-cutting §1: create target package → move code → old module
re-exports every public name **and** the aliased patch seams → flip importers
file-by-file → tests + 0.1 guard stay green. Facades dropped only in Phase 8.

| Step | Split | Target layout |
|---|---|---|
| 4.1 | **`auth.py`** (675) → `services/auth/` `{passwords,tokens,csrf,throttle}.py`; **move FastAPI deps** (`get_current_user`, `require_authed_session`, `require_password_complete`) to `src/api/deps.py` (fixes the `auth.py:568 from ui.auth_stub` layering violation + the HTTP-in-service smell). `services.auth` re-exports all (24 importers). Merge `auth._login_attempts` into `throttle` with `rate_limit.py`. |
| 4.2 | **`application_service.py`** (2216) → `services/applications/` `{state,drafts,submission,auto_apply,email_suggestions,engagement,queries,export}.py` + fold `application_analytics`, `ats_postmortem`, `profile_answer_service`, `generation_dispatch`. Facade `__init__` re-exports public names + patch seams (`ats_dispatch` alias at `:56`, etc.). |
| 4.3 | **`document_generator.py`** (1989) → `services/generation/` `{cost_cap,snapshot,bullet_selection,resume,cover_letter,screeners,maintenance}.py`. Preserve the `__import__("llm.prompts.X")` paths and `dg.is_cost_capped` attribute-style access from `bundle_generator`/`tool_loop`. |
| 4.4 | **`bundle_generator.py`** (1076) → `generation/bundle.py` + `stages_free.py` + `stages_premium.py` + `trace.py` (stage-runner abstraction: probe-cap → run → append-trace). **Safest split** — only 2 public fns, low test-brittleness. |
| 4.5 | **`apply_site_resolver.py`** (905) + **`linkedin_resolver.py`** (495) → `services/resolution/` `{url_rules,board_probe,pipeline,linkedin}.py`. Dissolves the resolver↔linkedin and resolver↔jd_enrichment lazy-import cycles. Preserve `linkedin_resolver._AUTH_LOCK` single-instance + session-health file (memory [[reference_linkedin_auth_resolver]]). |
| 4.6 | **`notifications.py`** (690) → `services/notify/` `{channels,events}.py` (toasts removed in 2.3). Single event→message model rendered per channel (kills the `_embed_for_*`/`_telegram_text_for_*` dual encoding). Preserve `_telegram_token`/`_chat_id` patch seams (10 tests). |
| 4.7 | (Lower priority; do if time) `profile_service`, `job_service` (`scrape_runs.py` split), `settings_service` (premium cost-projection → `generation/`), `email_*`+`calendar_sync` → `services/email/`, `llm_tracker`+`llm_models` → `services/llm_support/`. |

Gate after **each** step; 0.1 guard must stay green throughout.

### Phase 5 — Duplication consolidation (behaviour-preserving)

| Step | Work |
|---|---|
| 5.1 | Council engine: extend `_council_common` with `run_persona_batch()`; collapse `council.py`/`critique_council.py` (~110 lines). **Fix the `_council_common.py:57` bug** — it hardcodes `prompt_name=f"council_{req.custom_id}"`, mislabeling critique-council sync-fallback usage rows as `council_*`. |
| 5.2 | Scraper-site template method in `_base_site` (`iter_list_payloads`/`rows_of`/`build_job`) — collapses greenhouse/lever/ashby skeletons + the JSON-unwrap triple (~150 lines) and the workday/indeed search-loop pair. Site classes are not scheduler funcs, but `scraping.<source>` job ids are — do not rename sources. Also fix greenhouse's missing `_skip_known` (re-fetches every detail page). |
| 5.3 | Shared `run_structured_llm(session,user_id,settings,prompt,schema,prompt_name)` in `llm_support` to remove the ~16× prompt-build→`get_provider`→`tracked_call`→`model_validate` boilerplate (~300-400 lines). Route the 11 bare prompt-module convenience wrappers through it or delete them (they're tracker-bypass traps; one already diverged from its shipped prompt). |
| 5.4 | Consolidate the Fernet-from-SECRET_KEY helper (`email_credentials.py:31`, `calendar_sync.py:53`) into one `services/_crypto.py` — crypto in one place. |
| 5.5 | One `html_to_text` helper (5 divergent BeautifulSoup copies: `jd_enrichment`, `job_extractor`, greenhouse/workday/indeed/lever). |
| 5.6 | Roll `get_owned_application`/`get_owned_contact` (from 1.4) out to the remaining ~40 hand-rolled ownership checks. |

Gate.

### Phase 6 — Infra correctness (functional bugs; each with a test)

| Step | Work |
|---|---|
| 6.1 | LLM retry ladder: map SDK exception types (`RateLimitError`/`APITimeoutError`) → `kind` in each provider, or make `_classify_error` fall through to message-sniffing when `kind` is the default. Test: a simulated 429 retries with backoff. |
| 6.2 | Cost-cap day boundary: delete `document_generator._today_spend` (local-date-as-UTC + `succeeded IS TRUE`); call `llm_tracker.today_cost_usd`. Test the UTC boundary. |
| 6.3 | Fallback provider (Open Q5): **wire** `fallback_provider` through the `tracked_call` call sites (it's a stored user setting), or remove the setting. Recommendation: wire. |
| 6.4 | tracked_call gaps: wrap `api/settings.py:216` ping; add `AnthropicProvider.tool_use()` so `tool_loop.py:413` stops using `provider._client` + loses failure telemetry; persist council batch on poll-timeout; delete/rewrap the 11 bare prompt wrappers (with 5.3). |
| 6.5 | Embedding provider model-id bug: `get_embedding_provider` builds providers with the *chat* model → wrong `ApiUsage.model`, ~125× cost overstatement, embedding-provenance invalidation. Pass `model=None`; persist `result.model`; add embedding pricing to `estimate_cost`. |
| 6.6 | Scheduler: set `misfire_grace_time` (e.g. 3600) on the 18 `jobs.py` cron registrations (only the 6 scraping jobs set it today → nightly crons skipped across a restart). Fix LinkedIn rpm drift (class attr 2.0 vs resolver table 0.4; cron uses the table). |
| 6.7 | Typst: wrap the `typst query` page-count pass in `TypstError` (`compiler.py:134` leaks raw `TimeoutError`); document the fixed-`resume.pdf`-path concurrency race. |

Gate.

### Phase 7 — Data model (migrations; safety-first, each with up/down test)

| Step | Work | Migration? |
|---|---|---|
| 7.1 | Index hygiene: add missing FK indexes (`job.warm_intro_contact_id`, `job.last_scrape_run_id`, `profile_answer.source_screener_answer_id`), `Job.role` trgm, `(Contact.user_id, email)`; drop redundant duplicate indexes (`job.found_at` ×2, redundant `user_id` singles). **Add the migration-only indexes** (`ix_job_company_trgm`, HNSW ×2, one-active-per-tenant partial) **to `__table_args__`** to stop `--autogenerate` proposing their drop. | yes |
| 7.2 | Money `float`→`Numeric(10,4)`: `ApiUsage.cost_usd`, `GeneratedDocument.cost_usd`, cap comparisons. | yes |
| 7.3 | Closed-vocabulary `str` columns → native enums or CHECKs (14 columns: `Job.url_type/apply_kind/apply_resolved_via`, `Project.kind`, `EmailThread/Message.provider`, `OutreachMessage.channel`, `ApiUsage.method`, `Settings.*`, …). | yes + code |
| 7.4 | Input validation at the Pydantic edge: `max_length` + URL/email validators on unbounded Profile/Job/Contact strings; bound the free-`dict[str,Any]` route bodies (settings/outreach/contacts PUT/POST) so bad input is 422, not a 500 from asyncpg. | code |
| 7.5 | **(Gated by Open Q2 — likely a follow-up plan.)** JSONB→relational: `application_bullet_override` table (FK'd bullet ids, replacing the un-FK'd `submission_artifacts.bullet_overrides` + `generated_document.bullet_selection`); append-only generation-trace table (stop overwriting on regenerate); point the draft-reply read path at `email_message` (not the legacy `email_thread.messages` dual-store). | yes (invasive) |

Gate; migration steps additionally get the chain-replay note (leave
`NAAVIK_CHAIN_REPLAY_DB_URL` unset locally per memory
[[feedback_destructive_test_gates]]).

### Phase 8 — Facade teardown + final cleanup

- Drop the re-export facades once all importers are flipped; update the
  conftest shim dotted paths to the new homes (0.1 guard proves completeness).
- Final full gate: ruff + format + pytest + Playwright + net-zero data + process
  shutdown.

---

## Risk table

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | A moved function silently un-shims 189 test files → suite stays green but tests nothing. | High without guard | High | Phase 0.1 guard test **before** any move; re-export facades (rule §1). |
| R2 | Scheduler job function moved → allowlist mismatch at boot → persisted jobs deleted, manual runs lost. | Med | High | Rule §2: keep all 24 job funcs in place; if ever moved, update `FUNC_REF_ALLOWLIST` + job-id parsers in the same commit. |
| R3 | Hoisting a lazy import during a move creates a real circular-import crash. | Med | Med | Rule §3: never hoist; `resolution/` split (4.5) removes the biggest cycle deliberately. |
| R4 | Security fix (ownership/CSRF) breaks a legitimate owner flow. | Med | High | RED-first IDOR sweep (1.1) + Playwright owner-path check each step; client already sends CSRF header. |
| R5 | Enum/type migration breaks fresh-vs-upgraded install divergence. | Med | High | Follow the 0001-synthetic-metadata + `ADD VALUE IF NOT EXISTS` patterns; up/down test + gated chain-replay. |
| R6 | Deleting a "dead" template/route that is actually reached by a runtime-built URL. | Low-Med | Med | Only CERTAIN items in Phase 2; SUSPECTED-dead fragments → Open Q3, confirmed via Playwright/traffic before deletion. |
| R7 | Data pollution on the real dev DB during Playwright/live tests. | Med | Med | Throwaway session (owner `user_id=2`), net-zero cleanup, never point destructive gates at dev DB (memories). |
| R8 | Scope creep: Phase 7.5 (JSONB normalization) balloons the plan. | Med | Med | Gate 7.5 behind Open Q2; default = defer to a follow-up plan. |

---

## Open questions (recommended default in **bold**; none block Phase 0–1 security fixes)

1. **Tenancy model.** The tenant layer is incoherent: JWTs are signed by
   tenant 1 for everyone (`auth.py:61,254`), any authed user can rotate that
   shared key (`api/settings.py:769`), the Security view reads `tenant_id=user_id`
   (a non-existent tenant for user≥2), and `api/portfolio.py` hardcodes
   `user_id=1`. Is Naavik **firmly single-operator** (→ make single-tenant
   explicit: view reads tenant 1, restrict the rotate route, portfolio stays
   user 1 — **recommended**, matches self-hosted-first + owner profile) or
   **genuinely multi-user** (→ seed a Tenant per user + sign per-tenant, a
   larger change)? *Note: the Phase-1 auth/IDOR fixes are correct either way;
   only this coherence fix waits on the answer.*
2. **Data-model normalization appetite (Phase 7.5).** Do the invasive JSONB→
   relational migrations now, or **defer to a follow-up plan** (do 7.1–7.4 —
   indexes/types/validation — this round)? **Recommend defer.**
3. **Scaffolding/test-only modules.** Delete or keep: `recruiter_optimization.py`
   + `tailor_headline.py` (retired headline stage — **recommend delete**);
   `ats_generic_form_fill.py` (staged for ROADMAP 0.8.0 — **keep**);
   `app_event_payloads.py` (documents the `AppEvent.payload` contract — **keep**);
   `scraper/sites/sample.py` (test-by-design — **keep**). Also the ~13
   SUSPECTED-dead fragment routes (Appendix A footnotes) — confirm via traffic
   before deleting; **recommend a one-session Playwright/log sweep, then delete
   the confirmed-dead apply-preview cluster (4 routes)**.
4. **Toast SSE mechanism (2.3).** `stream_toasts` is unrouted and `push_toast`
   fills an undrained queue. **Recommend delete the queue path** (live toasts
   go through `HX-Trigger`); alternative is to wire an SSE consumer route.
5. **Fallback LLM provider (6.3).** Wire the stored `llm_fallback_provider`
   through `tracked_call` (**recommend**) or remove the inert setting.
6. **RAS→RPC auth convergence.** The `require_authed_session` (fake-session
   tolerant) → `require_password_complete` retirement touches ~150 routes.
   **Recommend out of scope here; follow-up plan.** This round only hardens the
   debug-gate and the specific broken routes.

---

## Approval checklist (tick to approve; plan-acceptance gate, not implementation tracking)

- [x] Phase sequence and safety-net-first ordering approved.
- [x] Q1 tenancy model → **single-tenant explicit** (recommended default accepted).
- [x] Q2 data-model appetite → **defer 7.5** to a follow-up plan (7.1–7.4 this round).
- [x] Q3 scaffolding → delete `recruiter_optimization`+`tailor_headline`; keep `ats_generic_form_fill`, `app_event_payloads`, `sample.py`; sweep+delete confirmed-dead apply-preview cluster.
- [x] Q4 toast SSE → **delete** the unrouted queue path (live toasts via `HX-Trigger`).
- [x] Q5 fallback-provider → **wire** it through `tracked_call`.
- [x] Q6 RAS→RPC convergence → **out of scope** (follow-up plan).
- [x] Green-gate definition (ruff via nix + pytest + Playwright + net-zero data + process shutdown) accepted.
- [x] Phase 0 (tests-only, zero `src/` behaviour change) authorized and in progress.

---

## Appendix A — Route inventory (197 routes = the no-regression checklist)

Auth legend: `RAS`=`require_authed_session` (JWT, or `fake-1` cookie **only**
when `settings.debug`), `RPC`=`require_password_complete`, `GCU`=`get_current_user`,
`CSRF`=`require_csrf`, `RL:*`=per-user rate limit, `none`=no auth dep. `†`=verified
defect (unauthenticated DB read / IDOR / dead-by-order). `‡`=SUSPECTED-dead
fragment (confirm before deleting — Open Q3).

**main.py:** `GET /api/health` (none, JSON) · `GET /favicon.ico` (none, file) ·
`mount /static` (none) · lifespan starts/stops scheduler.

**ui/routes/auth.py:** `GET /login` (none, page) · `GET /onboarding` (none) ·
`GET /auth/change-password` (GCU) · `POST /api/v1/extraction/upload` (RPC+CSRF, fragment).

**ui/routes/design.py:** `GET /_design/components` (debug-gate, page).

**ui/routes/discover.py:** `GET /discover` (RAS) · `GET /discover/{job_id}` (RAS) ·
`POST /api/v1/discover/{job_id}/skip` (RAS+CSRF) · `.../save` (RAS+CSRF) ·
`POST /api/v1/applications/{job_id}/auto-submit` (RAS+CSRF; note `{job_id}` not `{application_id}`) ·
`POST /_fragments/discover/{job_id}/pause-auto-apply` (RAS+CSRF) ·
`GET /_fragments/discover/next-card` (RAS)‡ · `.../expanded/{job_id}` (RAS) ·
`.../workspace/{job_id}` (RAS, poll target) · `POST .../tailor/{job_id}` (RAS+CSRF+RL:bundle) ·
`GET .../queue` (RAS) · `.../match-breakdown/{job_id}` (RAS)‡ ·
`GET /api/v1/jobs` (RAS, JSON) · `POST /api/v1/jobs/by-url` (RAS+CSRF, fat) ·
`POST /api/v1/jobs/{job_id}/rescore` (RAS+CSRF+RL:rescore) · `GET /api/v1/discover/saved` (RAS) ·
`.../skipped` (RAS) · `GET /_modal/add-by-url` (none) · `GET /_fragments/apply/tailored-bullets/{job_id}` (RAS)‡ ·
`GET/POST /_fragments/apply/cover-letter-section/{application_id}/{section}` (RAS[+CSRF]) ·
`POST /_fragments/apply/resume-bullet/{application_id}/{bullet_id}/toggle` (RAS+CSRF) ·
`POST /_fragments/apply/resume-pdf/{application_id}/recompile` (RAS+CSRF) ·
`POST /_fragments/apply/resume-bullet/{application_id}/{bullet_id}` (RAS+CSRF) ·
`PUT /api/v1/applications/{application_id}/cover-letter/sections/{section}` (RAS+CSRF, JSON twin) ·
`POST /_fragments/apply/generate/{application_id}` (RAS+CSRF+RL:bundle) ·
`GET /api/v1/applications/{application_id}/resume.pdf` (RAS, file) · `.../cover-letter.pdf` (RAS, file) ·
`POST /api/v1/applications/{application_id}/cover-letter/generate` (RAS+CSRF+RL:bundle) ·
`PUT /api/v1/applications/{application_id}/screeners/{question_id}` (RAS, **no CSRF**) ·
`GET /_fragments/apply/screener/{application_id}/{question_id}` (RAS)‡ ·
`GET /_fragments/apply/preview/by-job/{job_id}` (RAS)‡ · `.../preview/{application_id}` (RAS)‡ ·
`POST /_fragments/apply/confirm/{application_id}` (RAS+CSRF+RL:bundle)‡ ·
`GET /_fragments/apply/cancel-preview` (none)‡. *(preview/confirm/cancel = dead cluster of 4.)*

**ui/routes/email.py:** `GET /api/v1/email/threads` (RAS) · `.../{thread_id}` (RAS) ·
`POST .../{thread_id}/draft-reply` (RAS, **no CSRF**) ·
`POST /api/v1/applications/{app_id}/email-suggestion/{message_id}/apply` (RAS+CSRF) · `.../dismiss` (RAS+CSRF).

**ui/routes/fragments.py:** `GET /_fragments/scrape-status` (RAS) · `GET /_modal/confirm` (none) ·
`GET /_modal/bullet-editor/{bullet_id}` (**none — DB read**)† · `GET /_fragments/profile/bullet-row/{bullet_id}` (**none — DB read**)†‡ ·
`GET /_fragments/onboarding/step/{step}` (none).

**ui/routes/integrations.py (stubs):** `GET /integrations/email` (RAS, page) ·
`GET /api/v1/integrations` (**none, stub**)† · gmail connect/callback (none, stub) ·
`POST .../gmail/disconnect` (RAS, no CSRF) · `{provider}` connect/callback/disconnect (none / RAS-no-CSRF, stub).

**ui/routes/jobs.py:** `GET /jobs/{job_id}` (RAS, page) · `GET /_fragments/jobs/{job_id}` (RAS)‡ ·
`GET /api/v1/jobs/{job_id}` (RAS, JSON) · `GET /_modal/manual-job` (none) ·
`POST /api/v1/jobs/manual` (RAS+CSRF) · `POST /api/v1/jobs/{job_id}/resolve-apply` (RAS+CSRF) · `.../apply-url` (RAS+CSRF).

**ui/routes/outreach.py:** `GET /outreach` (RAS, page) · `GET /_fragments/outreach/app-detail/{application_id}` (RAS)‡ ·
`POST /_fragments/outreach/draft/{contact_id}` (RAS, no CSRF)‡ · `GET /api/v1/contacts` (RAS) ·
`POST /api/v1/contacts` (RAS, no CSRF) · `GET /api/v1/contacts/{contact_id}` (**none — DB read**)† ·
`PUT /api/v1/contacts/{contact_id}` (RAS, no CSRF; unscoped)† · `DELETE .../{contact_id}` (RAS, no CSRF; **IDOR delete**)† ·
`POST /api/v1/contacts/find` (RAS, no CSRF, stub) · `GET /api/v1/outreach/messages` (RAS; unscoped `app_id`/`contact_id`)† ·
`POST /api/v1/outreach/draft` (RAS, no CSRF; foreign-contact)† · `POST .../send` (RAS, no CSRF; **IDOR mutate**)† · `POST .../skip` (RAS, no CSRF).

**ui/routes/overview.py:** `GET /` (RAS, page) · `GET /_fragments/overview/priority-actions` (RAS)‡ ·
`.../email-signal` (RAS)‡ · `.../pipeline-strip` (RAS)‡ · `GET /api/v1/tracking/email-signals` (RAS, **SSE**).

**ui/routes/profile.py:** `GET /profile` (RAS) · `GET /profile/edit` (RAS) · `GET /_fragments/profile/cities` (RAS).

**ui/routes/settings.py:** `GET /settings` (RAS) · `/settings/sources` (RAS) ·
`POST /_fragments/settings/sources/{source}/run` (RAS+CSRF, transient job) ·
`GET /settings/{llm-provider,generation,auto-apply,submissions}` (RAS, legacy aliases) ·
`/settings/security` (RAS) · `/settings/{tab}` (RAS) · `GET /api/v1/settings/llm/usage` (RAS) ·
`PUT /api/v1/settings/{auto-apply,sources,notifications}` (RAS, **dead stubs**)† ·
`POST /api/v1/settings/notifications/test` (RAS+CSRF) · `GET /api/v1/settings/deployment` (RAS, **dead — shadowed**)† ·
`GET /api/v1/settings/account` (RAS) · `PUT /api/v1/settings/account` (RAS, **dead stub**)† ·
`PUT /api/v1/settings/account/password` (RPC+CSRF; **dup of api/auth change-password**) ·
`POST /api/v1/settings/account/delete` (RPC+CSRF) ·
`POST /_fragments/settings/test-connection` (RAS, no CSRF, **fake**)‡ · `GET /_fragments/settings/llm/model-options` (RAS)‡.

**ui/routes/setup_help.py:** `GET /setup-help` (none, intentional).

**ui/routes/tracking.py:** `GET /tracking` (RAS) · `GET /_fragments/tracking/board` (RAS) · `.../list` (RAS) ·
`.../library` (RAS) · `POST /_fragments/tracking/library/{job_id}/{action}` (RAS+CSRF) · `.../followup-banner` (RAS) ·
`GET /tracking/analytics` (RAS) · `GET /tracking/{application_id}` (RAS) · `GET /_fragments/tracking/application/{application_id}` (RAS) ·
`GET /_modal/postmortem/{application_id}/{ts}` (RAS) · `GET /_fragments/tracking/timeline/{application_id}` (RAS) ·
`PUT /api/v1/applications/{application_id}/notes` (RAS+CSRF) · `POST .../inferred/confirm` (RAS+CSRF) · `.../inferred/dismiss` (RAS+CSRF) ·
`PUT .../bullet-override` (RAS+CSRF) · `POST .../retry` (RAS+CSRF) · `POST /api/v1/applications/manual` (RAS+CSRF) ·
`GET /api/v1/applications` (RAS) · `GET /api/v1/applications/export.csv` (RAS, CSV) · `GET .../{application_id}` (RAS) · `.../{application_id}/bundle` (RAS, ZIP) ·
`POST /_fragments/tracking/bulk/move-stage` (RAS+CSRF) · `.../bulk/archive` (RAS+CSRF).

**api/applications.py (prefix /api/v1/applications):** `POST .../{id}/submit` (RPC, no CSRF) ·
`DELETE .../{id}/discard` (RPC, no CSRF) · `PUT .../{id}/status` (RPC, no CSRF) · `POST .../move` (RPC, no CSRF) ·
`GET .../{id}/postmortem/{ts}` (RPC, file-path gauntlet) · `.../{id}/auto-apply-artifacts/{filename}` (RPC, file) ·
`POST .../{id}/generate-bundle` (RPC+CSRF+RL:bundle) · `GET .../stuck` (RPC).

**api/auth.py (prefix /api/v1/auth):** `POST .../login` (IP-RL) · `.../logout` (none) · `.../signup` (IP-RL) ·
`.../change-password` (GCU+CSRF) · `GET .../me` (GCU) · `.../csrf` (none).

**api/geo.py:** `GET /api/v1/geo/cities` (RAS, JSON).
**api/integrations_calendar.py:** `POST /api/v1/integrations/calendar` (RAS+CSRF) · `.../sync-now` (RAS+CSRF) · `DELETE .../calendar` (RAS+CSRF).
**api/integrations_email.py:** `GET /api/v1/integrations/email` (RAS) · `POST .../imap` (RAS+CSRF) · `.../gmail` (RAS+CSRF) ·
`POST .../{account_id}/test` (RAS+CSRF) · `DELETE .../{account_id}` (RAS+CSRF) · `POST .../{account_id}/sync-now` (RAS+CSRF+RL:emailsync).
**api/portfolio.py (prefix /api/portfolio — public by design):** `GET .../cv` (none, PII-filtered, user_id=1) · `.../resume.pdf` (none, file) · `OPTIONS .../cv` · `OPTIONS .../resume.pdf`.
**api/profile.py:** `PUT /api/v1/profile` (RAS+CSRF) · `.../search-prefs` (RAS+CSRF) ·
`POST/DELETE /api/v1/{experiences,educations,projects,skills,certifications}[/{id}]` (RAS+CSRF) ·
`PUT /api/v1/profile/{field}` (RAS, no CSRF) · `PUT /api/v1/profile/application-questions` (**unreachable — shadowed**)† ·
`POST /api/v1/bullets` (RAS, no CSRF) · `PUT/DELETE .../bullets/{id}` (RAS, no CSRF) · `POST .../bullets/{id}/rewrite` (RAS+CSRF) · `POST .../bullets/reorder` (RAS, no CSRF).
**api/profile_answer.py:** `POST /api/v1/profile-answers/{id}/accept` (RAS, no CSRF; only UI caller is a dead template).
**api/scheduler.py (prefix /api/v1/scheduler):** `GET .../jobs` (RAS) · `POST .../jobs/{job_id}/{run,pause,resume}` (RAS+CSRF; shared jobs — see Open Q1/authz).
**api/settings.py:** `GET/PUT /api/v1/settings/llm` (RAS[+CSRF]) · `POST .../llm/test` (RAS, no CSRF, real ping) ·
`PUT .../auto-apply` (RAS+CSRF) · `.../ai-automation` (RAS+CSRF, union save) · `POST .../auto-apply/drain-queue` (RAS+CSRF) ·
`PUT .../sources` (RAS+CSRF) · `.../generation` (RAS+CSRF) · `.../notifications` (RAS+CSRF) · `GET .../deployment` (RAS, wins over ui) ·
`POST .../security/rotate-jwt-key` (RAS+CSRF; **authz gap — rotates shared tenant-1 key**)† · `PUT .../account` (RAS+CSRF, wins over ui).

## Appendix B — Scheduled jobs (24; the FUNC_REF_ALLOWLIST — do not move/rename)

`applications.auto_apply` (5min) · `admin.aggregate_costs` (00:30, log-only) ·
`admin.cleanup_stale_docs` (Sun 03:00) · `admin.cleanup_stale_drafts` (Sun 03:30) ·
`admin.cleanup_revoked_jwts` (03:30) · `admin.expire_retiring_signing_keys` (04:00) ·
`admin.daily_db_snapshot` (02:00, marker-only) · `admin.refresh_oauth_tokens` (6h, no-op skeleton) ·
`embeddings.embed_pending_jobs` (02:00) · `embeddings.embed_pending_profiles` (02:30) ·
`embeddings.embed_orphan_sweep` (03:00) · `jobs.score_pending` (15min) ·
`score.recompute_stale` (03:30) · `score.aggregate_daily` (03:35) ·
`tracking.sync_emails` (10min) · `tracking.classify_emails` (10min, +2min first) ·
`tracking.sync_calendars` (45min) · `jobs.resolve_apply_sites` (20min) ·
`scraping.{linkedin(*/30),workday,greenhouse,lever,ashby}` (crontab, misfire_grace 300) ·
`scraping.indeed` (90min interval). Transient: `scraping.<source>-manual-<hex>` (Run-now),
`<job>-manual-<uuid8>` (scheduler run), `applications.auto_apply-immediate-*`.

## Appendix C — Non-HTTP behaviours (no-regression checklist)

- **Lifespan:** APScheduler start/shutdown (`main.py:44`); non-fatal on boot failure (memory-jobstore downgrade).
- **Fire-and-forget:** `generation_dispatch.spawn_generation` (`create_task`; discover.py:117/233/466/1220, tracking.py:197) — bundle generation is background + workspace poll (`/_fragments/discover/workspace/{id}`); `portfolio_sync` debounced regen (`profile_service.py:819`); on-demand portfolio PDF regen (`portfolio.py:129`).
- **In-memory state (resets on restart):** login rate-limit buckets (`auth.py:70`), per-user limiters (`rate_limit.py`), integration stub state (`integrations.py`), generation in-flight registry (`generation_dispatch`), LinkedIn session-health file (disk).
