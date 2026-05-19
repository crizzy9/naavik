# Naavik · Job Model

> **Canonical reference** — graduated from `docs/plans/archive/27-0.2.0.05-job-models.md` per `AGENTS.md` § Workflow step 4.
> **Status:** Active. This is the single source for the `Job` SQLModel, the `JobScrapeRun` scrape-lifecycle table, the 5 Job-domain enums, the dedup story, and the `services/job_service.py` 8-function contract.
> **Last updated:** 2026-05-19 (plan 27 / `0.2.0.05` shipped).
> **Companion docs:** `docs/design/DATA_MODEL.md` (cross-entity model overview — Job + JobScrapeRun cross-ref here), `docs/design/SCRAPER_BASE.md` (canonical `ScraperBase` ABC + `RawJob` DTO that maps onto `Job`; plan 29), `docs/design/BACKEND.md` § J (scraper pipeline that writes through `upsert_job`), `docs/design/BACKEND.md` § H (scorer reading `Job.visa_restrictions`), `docs/ARCHITECTURE.md` § 3.7 (models layer rules).
> **Downstream plans depending on this contract:** `0.2.0.06` (Crawl4AI base), `0.2.0.07` (per-source site scrapers), `0.2.0.08` (AI extraction), `0.2.0.09` (dedup), `0.2.0.10` (scheduler), `0.2.0.11` (Discover UI), `0.2.0.12` (notifications), `0.2.0.13` (rate limiting), `0.2.0.14` (n8n migration).

---

## A · One-paragraph contract

A `Job` is a pre-application opportunity — scraped from a board or `+ Add by URL`'d by the user. Each row carries the user-visible fields the Discover UI renders (`company`, `role`, `salary_min/max`, `description`, `tags`, `score`), plus the scraper-pipeline plumbing that lets downstream sub-tasks land cleanly: `external_id` (per-source stable identifier), `visa_restrictions` (typed enum), `remote_policy` (filter toggle), `seniority_level` (filter toggle), `last_scrape_run_id` (FK back to the JobScrapeRun row that last touched this Job), `description_extracted_at` (so dedup `0.2.0.09` can decide "re-fetch this description"), and `raw_meta` JSONB for source-specific extras. Soft-delete via `deleted_at` is honored everywhere; the `(user_id, source, external_id)` partial-unique index — the **primary dedup constraint** — applies only to live rows. Pipeline-level status (`DRAFT → APPLIED → … → CLOSED`) lives on `Application` + is audited row-by-row by `AppEvent + StatusChangePayload`; scrape-side observability ("when did the LinkedIn scraper last run, how many listings, how many errors") lives on `JobScrapeRun` — distinct from `AppEvent` (which is per-Application history).

---

## B · Entity inventory

### B.1 `Job`

| Property | Value |
|---|---|
| File | `src/models/job.py` |
| Table name | `job` |
| PK | `id: int` (autoincrement) |
| User scope | `user_id: int = FK(user.id)` (every row scoped to a user; single-user MVP, multi-tenant-ready) |
| Soft-delete | `deleted_at: datetime \| None` |
| Phase 1 row count | 27 fixtures in `src/db/sample_data.py` |

### B.2 `JobScrapeRun`

| Property | Value |
|---|---|
| File | `src/models/job_scrape_run.py` |
| Table name | `job_scrape_run` |
| PK | `id: int` |
| User scope | `user_id: int = FK(user.id)` |
| Soft-delete | NONE — scrape-run rows are operator audit data; pruned by a future cron at scale (Phase 6+) |
| Phase 1 row count | 5 fixtures (last 24h of scraping, mixed `SUCCESS` / `PARTIAL` / `FAILED` statuses) |

---

## C · Enums

All enums live in `src/models/enums.py`. Postgres ENUM types via SQLAlchemy default `.name` binding (UPPERCASE in the DB; lowercase values in Python via `StrEnum`).

### C.1 `JobSource` (10 values)

```python
class JobSource(StrEnum):
    LINKEDIN = "linkedin"
    WORKDAY = "workday"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    INDEED = "indeed"
    COMPANY_DIRECT = "company_direct"   # generic scraper / +Add by URL with known ATS
    RSSHUB = "rsshub"                   # RSS-only inbound (rsshub.luminolab.net)
    N8N_LEGACY = "n8n_legacy"           # 0.2.0.14 migration source
    MANUAL = "manual"                   # user-entered, no scraper
```

**Migration history.** Plan 27 § D.4 replaced the 2-value catch-all (`AUTOMATED` + `MANUAL`) with this 10-value per-source form. Alembic 0005 added the 9 new values via `ALTER TYPE jobsource ADD VALUE IF NOT EXISTS '<value>'` (wrapped in `op.get_context().autocommit_block()` because Postgres' `UnsafeNewEnumValueUsage` forbids using a just-added enum value in the same transaction). Existing rows with `source='AUTOMATED'` were remapped via `UPDATE job SET source = board::text::jobsource` — the `ApplicationBoard` ENUM members are byte-for-byte identical to the new `JobSource` per-source values, so the cast composes. `AUTOMATED` lingers in the type definition because Postgres has no `ALTER TYPE ... DROP VALUE` before PG16; follow-up `0.2.5.NN` cosmetic cleanup row planned. **Regression lint** `tests/test_no_legacy_jobsource_imports.py` fails if any `src/` file references `JobSource.AUTOMATED`.

**Why not collapse into `ApplicationBoard`?** Locked decision D.4: `Job.source` tells the scraper pipeline + dedup which row produced this Job (LinkedIn vs Greenhouse vs RSShub); `Job.board` tells the ATS adapter which form to submit to at apply time. Two-axis split matters at submit time, not at scrape time. Two values that look similar (e.g. `JobSource.LINKEDIN` + `ApplicationBoard.LINKEDIN`) are kept aligned by byte-equality of the underlying string.

### C.2 `VisaRestriction` (4 values)

```python
class VisaRestriction(StrEnum):
    US_CITIZEN_ONLY = "us_citizen_only"
    GREEN_CARD_REQUIRED = "green_card_required"
    SPONSORSHIP_AVAILABLE = "sponsorship_available"
    NOT_MENTIONED = "not_mentioned"          # AI extraction default
```

**Migration history.** Plan 27 § D.5 promoted from `Job.visa_restrictions: str | None`. Alembic 0005 added the new ENUM type + did a 4-step column change on `Job.visa_restrictions`: ADD COLUMN `visa_restrictions_new` (nullable enum), UPDATE-CASE backfill (lower-trim matches `us_citizen_only` / `green_card_required` / `LIKE '%sponsorship%'` → enum members; everything else → `NOT_MENTIONED`), DROP COLUMN old, RENAME new → original (NOT NULL + `server_default='NOT_MENTIONED'`).

**Consumed by.** `services/scorer.py` (visa filter: `Profile.visa_sponsorship_needed == NEEDED_NOW` + `Job.visa_restrictions ∈ {US_CITIZEN_ONLY, GREEN_CARD_REQUIRED}` → score 0). AI extraction (`src/llm/prompts/extract_job.py`) writes one of these 4 values; Pydantic `provider.structured(...)` validates the LLM output structurally.

### C.3 `RemotePolicy` (4 values)

```python
class RemotePolicy(StrEnum):
    REMOTE = "remote"          # fully remote
    HYBRID = "hybrid"          # 1-3 days in-office expected
    ONSITE = "onsite"          # 4-5 days in-office
    UNKNOWN = "unknown"        # AI extraction default
```

**Consumed by.** Discover filter toggle "Remote only" (`JobFilter.remote_only: bool` → `WHERE Job.remote_policy = REMOTE`). AI extraction populates this; `UNKNOWN` is the default when the JD doesn't say.

### C.4 `SeniorityLevel` (7 values)

```python
class SeniorityLevel(StrEnum):
    ENTRY = "entry"            # 0-2 yrs
    MID = "mid"                # 2-5 yrs
    SENIOR = "senior"          # 5-8 yrs
    STAFF = "staff"            # 8+ yrs IC; design / influence wide
    PRINCIPAL = "principal"    # tech-lead / architect
    EXEC = "exec"              # VP+
    UNKNOWN = "unknown"
```

**Consumed by.** Discover filter (`JobFilter.seniority`). AI extraction maps job-title variants onto one of these — e.g. `"Sr Software Engineer"` / `"Senior SDE II"` / `"Software Engineer III"` → `SENIOR`. Phase 1 conservative; finer-grained split (e.g. `STAFF_I` / `STAFF_II`) is a future-future plan if filtering ergonomics demand it.

### C.5 `JobScrapeStatus` (5 values)

```python
class JobScrapeStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"        # all listings processed, 0 errors
    PARTIAL = "partial"        # some listings processed, some errors (degraded)
    FAILED = "failed"          # zero listings persisted; full failure
    TIMED_OUT = "timed_out"    # cron hit its budget before completing
```

**Consumed by.** `JobScrapeRun.status` (lifecycle field). `services/job_service.py:record_scrape_run` writes the initial row at `RUNNING`; scraper finalize step updates to one of the 4 terminal values. Operator UI ("Scrapes" panel, future) groups by source + status for at-a-glance health.

---

## D · Field-by-field reference (`Job`)

| Field | Type | Nullable | Indexed | Source-of-truth | Notes |
|---|---|---|---|---|---|
| `id` | `int` | NO | PK | autoincrement | |
| `user_id` | `int` | NO | yes | FK → `user.id` | multi-tenant scope |
| `source` | `JobSource` | NO | yes (partial-unique) | scraper sets at upsert | enum, 10 values |
| `board` | `ApplicationBoard` | NO | — | scraper sets | ATS adapter routing at apply time |
| `external_id` | `str` | NO | yes (partial-unique) | scraper sets; MANUAL synthesizes `manual-<uuid4>[:12]` | primary dedup |
| `url` | `str` | NO | yes (partial-unique) | scraper sets | URL-match dedup fallback |
| `url_type` | `str` | NO | — | scraper or service | `"ats"` / `"company_direct"` / `"rss"` / `"manual"` / `"external"` |
| `company` | `str` | NO | — | AI extraction | |
| `role` | `str` | NO | — | AI extraction | |
| `team` | `str` | YES | — | AI extraction | |
| `location` | `str` | YES | — | AI extraction | |
| `remote_policy` | `RemotePolicy` | NO | — | AI extraction | default `UNKNOWN`; Discover filter |
| `seniority_level` | `SeniorityLevel` | YES | — | AI extraction | Discover filter |
| `posted_at` | `datetime` | YES | — | AI extraction | normalized from `posted_at_text` |
| `posted_at_text` | `str` | YES | — | scraper | raw "Posted 3 days ago" before AI normalization; diagnostics |
| `found_at` | `datetime` | NO | yes (DESC) | service-set on first upsert | ordering / "this just landed" UI |
| `description` | `str` | NO | — | AI extraction | plain-text JD |
| `description_html` | `str` | YES | — | scraper | original; for re-extraction |
| `description_extracted_at` | `datetime` | YES | — | service-set on each upsert | dedup `0.2.0.09` uses this to decide "this Job's description is stale by N hours; re-fetch" |
| `description_extraction_model` | `str` | YES | — | service-set | which LLM model populated the structured fields; helps debug "Anthropic vs OpenAI differ on `skills_required`" |
| `criteria` | `list[str]` | NO | — | AI extraction | ARRAY(String) |
| `skills_required` | `list[str]` | NO | — | AI extraction | ARRAY(String) |
| `visa_restrictions` | `VisaRestriction` | NO | — | AI extraction | default `NOT_MENTIONED`; consumed by scorer visa filter |
| `salary_min` | `int` | YES | — | AI extraction | annual USD; `0` if hourly converted at apply time |
| `salary_max` | `int` | YES | — | AI extraction | annual USD |
| `equity_pct` | `float` | YES | — | AI extraction | percent ownership signal |
| `score` | `float` | NO | yes (DESC) | scorer | `0.0` to `1.0`; CHECK constraint enforces range |
| `score_explanation` | `str` | YES | — | scorer | LLM rationale |
| `match_breakdown` | `dict` | NO | — | scorer | JSONB; per-tag sub-scores |
| `queue_state` | `JobQueueState` | NO | yes (compound) | UI / cron sets | `UNSWIPED` / `SAVED` / `SKIPPED` / `QUEUED_FOR_AUTO_APPLY` / `APPLIED` |
| `tags` | `list[Tag]` | NO | GIN | AI extraction | ARRAY(String) |
| `warm_intro_contact_id` | `int` | YES | — | service | FK → `contact.id`; surfaces warm-intro UI on Discover card |
| `last_scrape_run_id` | `int` | YES | — | service-set per upsert | FK → `job_scrape_run.id`; "this listing last refreshed via LinkedIn 2h ago" UI |
| `raw_meta` | `dict` | NO | — | scraper | JSONB; source-specific extras (e.g. `{"rsshub_endpoint": "...", "linkedin_job_id": "..."}`) |
| `created_at` | `datetime` | NO | — | service-set | audit |
| `updated_at` | `datetime` | NO | — | service-set | audit |
| `deleted_at` | `datetime` | YES | — | `archive_job` | soft-delete sentinel |

### D.1 Indexes + constraints on `Job`

| Name | Type | Columns | Predicate |
|---|---|---|---|
| `(pk)` | btree unique | `id` | — |
| (FK `user_id`) | btree | `user_id` | — |
| `ck_job_score_range` | CHECK | `score` | `score >= 0.0 AND score <= 1.0` |
| `ck_job_salary_min_le_max` | CHECK | `salary_min, salary_max` | `salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max` |
| `ix_job_user_queue` | btree | `user_id, queue_state` | — |
| `ix_job_score_desc` | btree | `score` | — |
| `ix_job_found_at_desc` | btree | `found_at` | — |
| `ix_job_tags_gin` | GIN | `tags` | — |
| `ix_job_user_url_unique_alive` | btree unique | `user_id, url` | `deleted_at IS NULL` (URL-match dedup fallback) |
| `ix_job_user_source_external_id_unique_alive` | btree unique | `user_id, source, external_id` | `deleted_at IS NULL` (**primary dedup** per plan 27 § D.3) |
| `fk_job_last_scrape_run_id` | FK | `last_scrape_run_id` | → `job_scrape_run.id`; nullable |

---

## D.2 Field-by-field reference (`JobScrapeRun`)

| Field | Type | Nullable | Indexed | Source-of-truth | Notes |
|---|---|---|---|---|---|
| `id` | `int` | NO | PK | autoincrement | |
| `user_id` | `int` | NO | yes | FK → `user.id` | |
| `source` | `JobSource` | NO | yes (compound) | service-set | which scraper ran |
| `status` | `JobScrapeStatus` | NO | yes (compound) | service-set | lifecycle |
| `triggered_by` | `str` | NO | — | service-set | `"cron"` / `"manual"` / `"test"` / `"migration"`; free-form |
| `started_at` | `datetime` | NO | yes | service-set | timezone-aware UTC |
| `finished_at` | `datetime` | YES | — | service-set on finalize | NULL while RUNNING |
| `requests_made` | `int` | NO | — | counter | # HTTP / Crawl4AI requests fired |
| `listings_returned` | `int` | NO | — | counter | # RawJob rows yielded |
| `new_jobs` | `int` | NO | — | counter | # new Job rows persisted |
| `updated_jobs` | `int` | NO | — | counter | # existing Jobs touched |
| `errors` | `list[str]` | NO | — | scraper-write | ARRAY(String); per-error `"stage=<...> url=<...> kind=<rate_limit\|captcha\|timeout\|parse_failure\|other> msg=<...>"` |
| `duration_ms` | `int` | YES | — | service computes | `finished_at - started_at` ms |
| `raw_meta` | `dict` | NO | — | scraper | JSONB; scraper-specific (e.g. `{"rsshub_endpoint": ..., "rate_limit_hits": 0}`) |
| `created_at` | `datetime` | NO | — | service-set | audit |

### D.2.1 Indexes + constraints on `JobScrapeRun`

| Name | Type | Columns | Predicate |
|---|---|---|---|
| `(pk)` | btree unique | `id` | — |
| (FK `user_id`) | btree | `user_id` | — |
| `ck_job_scrape_run_finish_after_start` | CHECK | `started_at, finished_at` | `finished_at IS NULL OR finished_at >= started_at` |
| `ck_job_scrape_run_counters_nonneg` | CHECK | `requests_made, listings_returned, new_jobs, updated_jobs` | `>= 0` each |
| `ix_job_scrape_run_source_started` | btree | `source, started_at` | per-source recent-history query |
| `ix_job_scrape_run_user_status_started` | btree | `user_id, status, started_at` | operator "show me the failed runs in the last 24h" query |
| `ix_job_scrape_run_started_at` | btree | `started_at` | cross-source recent-history |

---

## E · FK graph (Job ↔ Application ↔ Contact ↔ JobScrapeRun)

```
                        ┌─────────────────────┐
                        │ user.id (PK)        │
                        └─────────┬───────────┘
                                  │ user_id
                ┌─────────────────┼─────────────────┐
                │                 │                 │
        ┌───────▼────────┐ ┌──────▼──────┐   ┌──────▼──────┐
        │ job            │ │ contact     │   │ job_scrape_ │
        │  id (PK)       │ │  id (PK)    │   │ run         │
        │  warm_intro_   │ │             │   │  id (PK)    │
        │   contact_id ──┼─┘             │   └──┬──────────┘
        │  last_scrape_  │               │      │
        │   run_id ──────┼───────────────┼──────┘
        │                │               │
        └───────┬────────┘               │
                │ job.id                 │ contact.id
                │                        │
        ┌───────▼────────┐               │
        │ application    │               │
        │  job_id (nul)  │               │
        │                │               │
        └───────┬────────┘               │
                │ application.id         │
                │                        │
        ┌───────▼────────────────────────▼──┐
        │ contact_application_link          │
        │  application_id + contact_id      │
        └───────────────────────────────────┘
```

- `Job → Contact` via `warm_intro_contact_id` (nullable; surfaces warm-intro UI on Discover card).
- `Job → JobScrapeRun` via `last_scrape_run_id` (nullable; UI "this listing last refreshed via LinkedIn 2h ago").
- `Application.job_id` is **nullable** — manually-tracked external applications without a corresponding scraped `Job` row are allowed.
- `JobScrapeRun.user_id` mirrors `Job.user_id` so cron loops can iterate `for user in users:` and the FK boundary still applies.

---

## F · Service contract (`src/services/job_service.py`)

The middle layer between routes / cron and the Postgres surface. Every Job CRUD operation goes through this module; routes never write raw SQL.

### F.1 `upsert_job` — the load-bearing helper

```python
async def upsert_job(
    session: AsyncSession,
    *,
    user_id: int,
    source: JobSource,
    external_id: str,
    raw: dict,
    scrape_run_id: int | None = None,
) -> tuple[Job, bool]:
    """Idempotent on (user_id, source, external_id). Returns (job, created).
    `created=True` iff a new row was inserted; `created=False` on hit.
    On hit, refreshes `description_extracted_at`, merges `raw_meta`, bumps
    `last_scrape_run_id`. Field-level merge (diff description / skills /
    salary) is deferred to 0.2.0.09 dedup work.
    """
```

**Idempotency** is structurally guaranteed by the `ix_job_user_source_external_id_unique_alive` partial-unique index: two concurrent scraper invocations cannot persist two live rows with the same `(user_id, source, external_id)` triple. Soft-deleted rows do not occupy the slot, so `restore_job` performs a collision check before clearing `deleted_at`.

**`raw` payload contract.** Required keys on the create path: `board`, `url`, `url_type`, `company`, `role`, `description`. Optional keys map onto the SQLModel field of the same name when present. Unknown keys are dropped at the boundary. The `_create_payload` helper supplies typed defaults for fields the scraper legitimately can omit (`remote_policy = UNKNOWN`, `visa_restrictions = NOT_MENTIONED`, `criteria = []`, etc.).

### F.2 `get_job` / `list_jobs` / `archive_job` / `restore_job`

```python
async def get_job(session, job_id: int) -> Job | None: ...

async def list_jobs(
    session, *,
    user_id: int,
    filters: JobFilter | None = None,
    page: int = 0,
    page_size: int = 50,
) -> list[Job]:
    """ORDER BY score DESC, found_at DESC; soft-deleted rows excluded."""

async def archive_job(session, job_id: int) -> None:
    """Soft-delete (sets deleted_at = now()). No-op if already archived."""

async def restore_job(session, job_id: int) -> Job:
    """Clears deleted_at. Raises if a live row with the same
    (user_id, source, external_id) already exists — caller resolves the
    collision before retrying.
    """
```

### F.3 `create_manual_job`

```python
async def create_manual_job(
    session,
    payload: JobCreate,
    *,
    user_id: int,
) -> Job:
    """+ Add by URL path. source=MANUAL; external_id = manual-<uuid4>[:12].
    url_type = "external" when board=MANUAL; "ats" otherwise (board is the
    known ATS for the URL, e.g. greenhouse/lever/ashby).
    """
```

### F.4 Aggregates + lifecycle

```python
async def count_jobs_by_source(session, user_id: int) -> dict[JobSource, int]:
    """For `/standup` + the future Scrapes operator panel."""

async def record_scrape_run(
    session, *,
    user_id: int,
    source: JobSource,
    status: JobScrapeStatus,
    triggered_by: str = "cron",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    requests_made: int = 0,
    listings_returned: int = 0,
    new_jobs: int = 0,
    updated_jobs: int = 0,
    errors: list[str] | None = None,
    raw_meta: dict | None = None,
) -> JobScrapeRun:
    """Append a JobScrapeRun row. Computes duration_ms when both
    timestamps are present; leaves None on an in-flight row (the scraper
    invokes the helper twice — once at RUNNING with started_at, once on
    finalize with finished_at).
    """
```

### F.5 Pydantic API schemas (co-located)

In `src/models/job.py`:

- `JobFilter` — query-param shape for `/api/v1/jobs` (Phase 2.0.11 surface): `company` / `source` / `board` / `visa` / `remote_only: bool` / `seniority` / `queue_state` / `score_min: float` / `score_max: float` / `tag` / `posted_within_days: int | None`.
- `JobCreate` — input shape for `create_manual_job` (`+ Add by URL`): `url` / `board` / `company` / `role` / `description` / `team` / `location` / `remote_policy` / `seniority_level` / `salary_min` / `salary_max` / `visa_restrictions`.
- `JobUpdate` — partial-update shape for future inline-edit UI.
- `JobRead` — `/api/v1/jobs/{id}` output shape; includes all Job fields except `deleted_at`.

In `src/models/job_scrape_run.py`:

- `JobScrapeRunRead` — `/api/v1/scrape-runs/{id}` output shape (Phase 2.5+).

---

## G · Dedup story (URL → external_id → fuzzy, the 3-tier waterfall)

Production dedup spec (`BACKEND.md` § J.3 step 2.c). Plan 27 ships the **first two tiers** structurally; fuzzy match is `0.2.0.09` work.

1. **Exact `(source, external_id)` match.** Fast structural dedup using each board's stable identifier. Bulletproof when scrapers populate `external_id` correctly. Enforced by `ix_job_user_source_external_id_unique_alive`.
2. **URL match.** `ix_job_user_url_unique_alive` (kept from plan 10 Wave 4). Covers `+ Add by URL` paths where the scraper hasn't run yet + paranoid double-check when LinkedIn URLs change canonical form between job-list and job-detail pages.
3. **Fuzzy title + company.** Levenshtein on `(company.lower() strip)` + `(role.lower() strip)` — deferred to `0.2.0.09`. Will live in `services/dedup.py` (new module).

**Cross-board cross-posting** (e.g. a Stripe job appearing on LinkedIn + Greenhouse simultaneously) is handled by tier 3 — two `Job` rows with different `source` values can both be live at the same time; `0.2.0.09` merges them when fuzzy match scores high.

**MANUAL source** uses `external_id = f"manual-{uuid4().hex[:12]}"` so the partial-unique index has a non-null per-row value. Manual entries can therefore re-trip dedup only against themselves — by design, `+ Add by URL` is the user explicitly saying "this is a new opportunity I want to track separately."

**N8N_LEGACY source** (for `0.2.0.14` import) uses `external_id = legacy_row["internal_id"]` from the CSV, so re-importing the same n8n DataTable is idempotent.

---

## H · How scrapers + AI extraction + scorer consume this

| Consumer | File | Reads | Writes |
|---|---|---|---|
| Scraper service (Phase 2.0.06+) | `services/scraper_service.py` (canonical: `docs/design/SCRAPER_BASE.md § F`) | `Job.found_at`, `Job.description_extracted_at` | `upsert_job(...)`, `record_scrape_run(...)` |
| Per-source scrapers | `src/scraper/sites/<source>.py` (canonical: `docs/design/SCRAPER_BASE.md § I`) | `Settings.workday_companies`, etc. | `RawJob` instances yielded to scraper_service |
| AI extraction prompt | `src/llm/prompts/extract_job.py` | scraper-fetched HTML | `ExtractedJob` w/ `visa_restrictions: VisaRestriction` enum |
| Scorer (visa filter, Wave 6) | `src/services/scorer.py` | `Job.visa_restrictions` enum, `Profile.visa_sponsorship_needed` | `Job.score = 0.0` when filter trips |
| Scorer (LLM scoring, Phase 3) | same | `Job` row, `Profile`, `Settings.llm_provider` | `Job.score` + `score_explanation` + `match_breakdown` |
| Discover UI | `src/ui/routes/discover.py` + `discover_ctx.py` | `list_jobs(filters=JobFilter(...))` | (read-only) |
| Discover swipe handlers | `src/ui/routes/discover.py` | (job lookup) | `Job.queue_state` flips |
| Application service (DRAFT lifecycle) | `services/application_service.py` | `Job.id`, `Job.company`, `Job.role`, `Job.url`, `Job.board` | `Application(job_id=...)` |
| Auto-apply submit | `services/application_service.py:submit_draft` | `Job.queue_state == QUEUED_FOR_AUTO_APPLY` | flips `Job.queue_state` → `APPLIED` |
| Notifications (Phase 2.0.12) | `services/notifications.py` | `Job.score >= Settings.notify_threshold` | Discord webhook payload |
| Rate limiter (Phase 2.0.13) | `services/rate_limiter.py` | `JobScrapeRun.requests_made` per-source recent window | adjusts cron cadence |

**Scorer pattern (post-plan-27).** The visa filter zero-outs jobs against the typed enum:

```python
_BLOCKING_RESTRICTIONS = frozenset(
    {VisaRestriction.US_CITIZEN_ONLY, VisaRestriction.GREEN_CARD_REQUIRED}
)

def needs_visa_zero_out(profile: Profile, job: Job) -> bool:
    if profile.visa_sponsorship_needed != VisaSponsorship.NEEDED_NOW:
        return False
    return job.visa_restrictions in _BLOCKING_RESTRICTIONS
```

The defensive string→enum conversion in the live implementation handles the in-memory shadow + LLM-output paths where bare strings still flow through (boundary code; not raw SQL).

---

## I · Migration history

| Migration | Date | What |
|---|---|---|
| `0001_initial.py` | 2026-04-25 | Initial `job` table — Phase 1 placeholder shape (per plan 10 Wave 4). 2-value `JobSource` (`AUTOMATED` / `MANUAL`); `visa_restrictions: str | None` free-form; URL-match dedup only. |
| `0002_pgvector.py` | 2026-04-26 | pgvector extension. Not Job-touching. |
| `0003_*.py` | (intermediate) | Not Job-touching. |
| `0004_drop_vault_columns.py` | 2026-05-19 | Drops 5 vault-derived `Settings` columns (plan 26). Not Job-touching. |
| `0005_job_hardening.py` | 2026-05-19 | **Plan 27 / `0.2.0.05`.** Adds 9 per-source `JobSource` values; remaps `AUTOMATED` rows to per-board values via `board::text::jobsource`; promotes `Job.visa_restrictions` from `varchar` to `visarestriction` enum (4-step ALTER TABLE); adds 4 new ENUM types (`visarestriction` / `remotepolicy` / `senioritylevel` / `jobscrapestatus`); adds 6 new `Job` columns (`external_id` NOT NULL after sha1 backfill; `remote_policy` NOT NULL default `UNKNOWN`; `seniority_level` nullable; `posted_at_text`; `description_extracted_at`; `description_extraction_model`; `last_scrape_run_id`); creates `job_scrape_run` table (17 cols + 2 CHECK + 3 indexes); creates the primary dedup partial-unique index. |

**Round-trip verified.** `tests/test_alembic_0005.py` (3 cases on sqlite; live Postgres round-trip verified by engineer). Downgrade reverses additive columns + new ENUM types cleanly; the `JobSource` per-source values stay in the type definition because Postgres has no clean `ALTER TYPE ... DROP VALUE` before PG16 — operators reverting would need to revert both code + DB to roll back fully.

---

## J · Sample data fixtures

`src/db/sample_data.py` ships:

- **27 `Job` rows** (`JOBS: list[Job]`, IDs 101-127). Every row has `external_id` (deterministic `sha1(url)[:12]`); `source` is fanned out per board (`board=GREENHOUSE → source=GREENHOUSE`, etc.); `MANUAL` board → `MANUAL` source. `remote_policy` defaults to `HYBRID` for most rows; `seniority_level` defaults to `SENIOR` (matches owner profile); `visa_restrictions` is `SPONSORSHIP_AVAILABLE` for canonical sponsor-friendly fixtures (Stripe / Anthropic / OpenAI / Linear / Figma) and `NOT_MENTIONED` for the rest.
- **5 `JobScrapeRun` rows** (`JOB_SCRAPE_RUNS: list[JobScrapeRun]`, IDs 901-905) — last 24h of scraping per source:
  - 901 LinkedIn / SUCCESS / 42 listings / 3 new
  - 902 Greenhouse / SUCCESS / 68 listings / 5 new
  - 903 Lever / SUCCESS / 37 listings / 2 new
  - 904 Workday / PARTIAL / 33 listings / 1 new / 2 errors (timeout + rate-limit)
  - 905 Indeed / FAILED / 0 listings / 1 captcha error

24 of the 27 Job rows have `last_scrape_run_id` wired to one of these runs; the 3 outliers are `MANUAL` source jobs that never came through a scraper.

Pydantic shadows in `src/db/sample_data_models.py` mirror the SQLModel shape (`class Job`, `class JobScrapeRun`); the seed pipeline in `src/db/seed.py` converts shadow → dict → SQLModel + appends `(JobScrapeRun, sd.JOB_SCRAPE_RUNS, ("id",))` BEFORE `(Job, sd.JOBS, ("id",))` in the `_TABLE_ORDER` list (FK ordering: `Job.last_scrape_run_id` references `job_scrape_run.id`).

---

## K · Pointer index

| Topic | File / Location |
|---|---|
| `Job` SQLModel | `src/models/job.py` |
| `JobScrapeRun` SQLModel | `src/models/job_scrape_run.py` |
| Job-domain enums | `src/models/enums.py` (`JobSource` / `VisaRestriction` / `RemotePolicy` / `SeniorityLevel` / `JobScrapeStatus`) |
| Pydantic API schemas | `src/models/job.py` (`JobCreate` / `JobUpdate` / `JobFilter` / `JobRead`) + `src/models/job_scrape_run.py` (`JobScrapeRunRead`) |
| Service layer | `src/services/job_service.py` (8 functions) |
| Alembic migration | `migrations/versions/0005_job_hardening.py` |
| Round-trip test | `tests/test_alembic_0005.py` (3 cases) |
| Service-layer tests | `tests/test_job_service.py` (15 cases) |
| Regression lint | `tests/test_no_legacy_jobsource_imports.py` |
| Sample data fixtures | `src/db/sample_data.py` (`JOBS`, `JOB_SCRAPE_RUNS`) |
| Sample-data shadows | `src/db/sample_data_models.py` |
| Scraper consumption | `src/services/scraper_service.py` (Phase 2.0.06+) |
| AI extraction prompt | `src/llm/prompts/extract_job.py` |
| Scorer visa filter | `src/services/scorer.py` |
| Pipeline narrative | `docs/design/BACKEND.md` § J.3 |
| Cross-entity entity inventory | `docs/design/DATA_MODEL.md` § B + § C (Job, JobScrapeRun) |
| Plan archive (rationale) | `docs/plans/archive/27-0.2.0.05-job-models.md` |
| ROADMAP row | `ROADMAP.md` `0.2.0.05` |
| GitHub Issue | #15 |
