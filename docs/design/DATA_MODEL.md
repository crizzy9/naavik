# Naavik Data Model

> **Last updated:** 2026-05-01 (Phase 1 entity inventory + CHECK constraint refinements per the cross-plan triage)
> **Status:** Canonical — graduated from `docs/plans/05-data-model.md` (archived).
> **Scope:** SQLModel definitions for the entire MVP — every entity, every field, every enum, every relationship, every index — including the multi-axis Application state model. Backend implementation (plan 10) builds `src/models/*.py` from this 1:1; sample data (`docs/design/SAMPLE_DATA.md`) populates with realistic fixtures.
> **Companion docs:** `DESIGN.md` (visual contract), `docs/design/SCREENS.md` (functional contract), `docs/design/BACKEND.md` (services + routes consuming this), `docs/design/SAMPLE_DATA.md` (Phase 1 fixtures).

---

## A · Lifecycle modeling principle

The job-search lifecycle has **multiple orthogonal state axes** modeled as separate fields, never collapsed into a flat enum. The starting axes:

| Axis | Lives on | States | Purpose |
|---|---|---|---|
| **Discovery / queue** | `Job.queue_state` | `unswiped · saved · skipped · queued_for_auto_apply · applied` | Discover-side states. `applied` flips when an Application transitions to APPLIED. |
| **Application pipeline** | `Application.status` | `DRAFT · APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED` | Pipeline. DRAFT is pre-submission; APPLIED..CLOSED is post-submission. Visible in Tracking: APPLIED..OFFER. Hidden by default: DRAFT, CLOSED. |
| **Application close reason** | `Application.closed_reason` (nullable; required when `status=CLOSED`) | `rejected_by_them · withdrawn_by_me · ghosted · accepted_other` | Hidden by default in Tracking. |
| **Document generation** | `Application.docs_state` | `none · generating · ready · stale · failed` | Drives "AI · auto-fits 1pg" badge, retry on failure. |
| **Referral** | `Application.referral_state` | `none · requested · in_flight · provided · declined` | Powers warm-intro pill on Discover · review. |
| **Recruiter engagement** | `Application.recruiter_state` | `none · engaged · responded · silent · stalled` | Auto-derived from email signals. |
| **Outreach engagement** (computed) | view over `OutreachMessage` + `Contact` for the Application | `cold · active · awaiting_reply · referred · converted` | Drives Outreach left-rail grouping. |
| **Application questions** | `Profile.application_questions` (one-time per user) | per-field enums | Filled at onboarding/profile-edit; auto-injected into application bundles. |
| **Bullet selection override** | `Bullet.selection_override` | `null · always_include · never_include` | Per-bullet manual pin; default null = AI auto-decides. |

These axes are **independent**. Compound states emerge from intersection — they are NOT new enum values. An application can be `RECRUITER_SCREEN` + `referral_state=provided` + `docs_state=ready` + `recruiter_state=responded` simultaneously.

**Two related but distinct concepts not on the axis table above:**

- **Canonical EEO/visa application questions** — Phase 1 ships ten standardized US fields (work_authorization, visa_sponsorship_needed, willing_to_relocate, notice_period_days, salary_expectation_usd, earliest_start, veteran_status, disability_status, race_ethnicity, gender_identity) as flat columns on `Profile`. Filled once at onboarding/profile-edit, auto-injected into every application bundle.
- **Per-job custom screener questions** — JD-specific questions whose wording varies per board ("Why Stripe?", "Are you OK with on-call?", "Years of Kafka?") captured during scrape and frozen on the **Application** as `ApplicationScreenerAnswer` rows (entity #17 below). AI drafts answers from Profile + JD; user reviews before submit.

See § J for the full screener-answer model and lifecycle.

---

## B · Entity inventory

22 SQLModel entities + 1 settings singleton. Phase 1 ships 19; plan 27 (`0.2.0.05`) adds `JobScrapeRun` (entity #20); plan 61 (`0.2.7.16`) adds `JobEmbedding` (entity #21); plan 65 (`0.3.0.03`) adds `ProfileEmbedding` (entity #22).

| # | Entity | Purpose | Phase 1 row count (per SAMPLE_DATA.md) |
|---|---|---|---|
| 1 | `User` | Identity + auth | 1 |
| 2 | `Profile` | One per user — biographical, EEO/visa application questions, summary | 1 |
| 3 | `Experience` | Roles in chronological list | 4 |
| 4 | `Bullet` | Single long-form text + tags + selection_override | 14 across roles |
| 5 | `Skill` | Grouped (category, items) | 6 categories |
| 6 | `Education` | Schools | 2 |
| 7 | `Project` | Portfolio projects | 4 |
| 8 | `Certification` | Optional | 1 |
| 9 | `Job` | Pre-application opportunities (scraped or manual) — see `docs/design/JOB_MODEL.md` for the post-plan-27 hardened shape | ~20 |
| 10 | `Application` | Pre + post-submission record (DRAFT through CLOSED) | 14 (incl. 2 DRAFT) |
| 11 | `Contact` | Recruiter / employee at a company | ~20 |
| 12 | `ContactApplicationLink` | Many-to-many: which contacts know about which applications | ~25 |
| 13 | `OutreachMessage` | LinkedIn DM / email sent | ~40 |
| 14 | `EmailThread` | Auto-classified email thread (messages stored as JSONB list on the row) | ~20 |
| 15 | `AppEvent` | Unified timeline event (any state change, any touch) | ~150 |
| 16 | `GeneratedDocument` | Resume PDF + cover letter PDF artifacts | ~30 |
| 17 | `ApplicationScreenerAnswer` | Per-job custom screener questions + drafted/user answers (see § J) | ~20 |
| 18 | `ATSCredential` | Per-board login state metadata (DB row only; secret material in `~/.naavik/secrets.enc`) | 0 in Phase 1 fixtures |
| 19 | `ApiUsage` | Per-LLM-call cost + token + latency log; powers Settings · LLM Provider cost cards | grows with usage; fixtures seed ~30 historical rows |
| 20 | `JobScrapeRun` | One row per scraper invocation — `(source, status, started_at, finished_at, requests_made, listings_returned, new_jobs, updated_jobs, errors[], duration_ms, raw_meta)`. Plan 27 (`0.2.0.05`). See `docs/design/JOB_MODEL.md` § B.2 + § C for the canonical shape. | 5 fixtures (last 24h per source) |
| 21 | `JobEmbedding` | Sibling table — one dense `vector(768)` per Job (1:1 keyed by `job_id`). Plan 61 (`0.2.7.16`). Materialized by nightly `embeddings.embed_pending_jobs` cron. | grows with scoring run |
| 22 | `ProfileEmbedding` | Sibling table — one dense `vector(768)` per user (1:1 keyed by `user_id`). Plan 65 (`0.3.0.03`). On-edit hook in `profile_service` + nightly `embeddings.embed_pending_profiles` cron. | 1 per active user |
| – | `Settings` (singleton) | Per-user LLM provider, auto-apply config, etc. (see § L for full shape) | 1 |

Phase 2+ adds: `Notification`, `CalendarEvent`, `ProfileAnswer` (screener-answer reuse cache; see § J). `ScrapingSource` is subsumed by `Settings.sources_enabled` + the `JobSource` enum + per-run `JobScrapeRun` rows — no separate entity ships.

`ApiUsage` was promoted from Phase 2+ to Phase 1 entity #19 on 2026-05-01 because Settings · LLM Provider's "THIS MONTH" / "AVG / GENERATION" / "RATE LIMIT" cost cards (SCREENS.md § 11) need it from day one. Adding the table later would mean a migration + a broken cost-card interim.

---

## C · Model definitions

All models inherit from `SQLModel, table=True`. Common conventions:

- `id: int = Field(primary_key=True)` — auto-incrementing PK.
- `user_id: int = Field(foreign_key="user.id", index=True)` — every row scoped to a user (single-user MVP, multi-user-ready).
- `created_at: datetime = Field(default_factory=datetime.utcnow)`, `updated_at` — audit timestamps.
- `deleted_at: Optional[datetime] = None` — soft-delete on user-authored entities (Bullets, Contacts, Applications, OutreachMessages); hard-delete on Settings test rows + ephemeral state.
- Relationships back-populate explicitly via `Relationship(back_populates=...)`.

Imports omitted in samples for readability — implementer adds standard `from sqlmodel import ...`, `from sqlalchemy import Column, JSON, ARRAY, String, ...`, `from .enums import ...`.

### `User`

```python
class User(SQLModel, table=True):
    __tablename__ = "user"

    id: int = Field(primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str  # bcrypt; never logged

    is_active: bool = Field(default=True)
    is_admin: bool = Field(default=False)  # Phase 2+ multi-user; single-user MVP all True

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    profile: Optional["Profile"] = Relationship(back_populates="user")
    settings: Optional["Settings"] = Relationship(back_populates="user")
```

**Indexes:** `email` (unique). **Validation:** `email` matches RFC 5322; `password_hash` always bcrypt cost=12.

### `Profile`

```python
class Profile(SQLModel, table=True):
    __tablename__ = "profile"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", unique=True, index=True)

    # Identity
    full_name: str
    headline: str  # e.g. "Senior Software Engineer"
    current_company: Optional[str] = None
    location: Optional[str] = None
    email: str = Field(index=True)
    phone: Optional[str] = None
    portfolio_url: Optional[str] = None
    github_handle: Optional[str] = None
    linkedin_handle: Optional[str] = None
    open_to_opportunities: bool = Field(default=True)

    # Summary (full + short)
    summary_full: Optional[str] = None
    summary_short: Optional[str] = None

    # US Application questions (Phase 1: US only — see § A note)
    work_authorization: Optional[WorkAuthorization] = None
    visa_sponsorship_needed: Optional[VisaSponsorship] = None
    willing_to_relocate: Optional[RelocateOpenness] = None
    notice_period_days: Optional[int] = None
    salary_expectation_usd: Optional[int] = None
    earliest_start: Optional[datetime] = None
    veteran_status: Optional[VeteranStatus] = None
    disability_status: Optional[DisabilityStatus] = None
    race_ethnicity: Optional[Race] = None
    gender_identity: Optional[Gender] = None

    # Cover letter base — placeholder paragraph dict
    cover_letter_base: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    user: User = Relationship(back_populates="profile")
    experiences: list["Experience"] = Relationship(back_populates="profile")
    skills: list["Skill"] = Relationship(back_populates="profile")
    educations: list["Education"] = Relationship(back_populates="profile")
    projects: list["Project"] = Relationship(back_populates="profile")
    certifications: list["Certification"] = Relationship(back_populates="profile")
```

**Indexes:** `user_id` (unique), `email`. **Validation:** `salary_expectation_usd >= 0`; `notice_period_days >= 0`. **Computed (service-layer):** `application_readiness` = count of non-null EEO/visa fields.

### `Experience`

```python
class Experience(SQLModel, table=True):
    __tablename__ = "experience"

    id: int = Field(primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)

    company: str
    title: str
    team: Optional[str] = None
    location: Optional[str] = None
    start_date: datetime  # required
    end_date: Optional[datetime] = None  # null = current role
    order_index: int = Field(default=0)  # display order (most-recent first via ORDER BY end_date DESC NULLS FIRST is the natural default; order_index lets users override)

    summary_short: Optional[str] = None  # one-line role summary; rendered in profile_hero compact view

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    profile: Profile = Relationship(back_populates="experiences")
    bullets: list["Bullet"] = Relationship(back_populates="experience")
```

**Indexes:** `profile_id`. **Validation:** `start_date < end_date OR end_date IS NULL`.

### `Bullet`

```python
class Bullet(SQLModel, table=True):
    __tablename__ = "bullet"

    id: int = Field(primary_key=True)
    experience_id: int = Field(foreign_key="experience.id", index=True)
    order_index: int = Field(default=0)  # for drag-drop reorder

    text: str  # SINGLE long-form, no length cap
    tags: list[Tag] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    selection_override: Optional[BulletSelectionOverride] = None  # null = AI auto-decides

    edited_at: Optional[datetime] = None  # last user edit (vs LLM-generated)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    experience: Experience = Relationship(back_populates="bullets")
```

**Indexes:** `experience_id`, GIN on `tags`. **Validation:** `len(text) > 0`; `tags ⊆ Tag.values`. No length cap on `text` — AI trims at apply time. The bullet does NOT carry `oneline`, `detailed`, `default_include`, or metric fields — those were removed in 2026-04.

### `Skill`

```python
class Skill(SQLModel, table=True):
    __tablename__ = "skill"

    id: int = Field(primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)

    category: str  # e.g. "Languages", "ML / Data"
    items: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    order_index: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    profile: Profile = Relationship(back_populates="skills")
```

**Indexes:** `profile_id`. **Validation:** `len(category) > 0`; `len(items) > 0`.

### `Education`

```python
class Education(SQLModel, table=True):
    __tablename__ = "education"

    id: int = Field(primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)

    institution: str
    school: Optional[str] = None  # e.g. "Khoury College of Computer Sciences"
    location: Optional[str] = None
    degree: str  # "MS Computer Science"
    start_date: datetime
    end_date: Optional[datetime] = None
    gpa: Optional[str] = None  # string to allow "3.84/4.0" or "8.62 CGPA"
    courses: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    order_index: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    profile: Profile = Relationship(back_populates="educations")
```

**Indexes:** `profile_id`.

### `Project`

```python
class Project(SQLModel, table=True):
    __tablename__ = "project"

    id: int = Field(primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)

    title: str
    date: Optional[datetime] = None
    text: str
    tags: list[Tag] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    portfolio_slug: Optional[str] = None  # for crypticsoul.dev linking
    link: Optional[str] = None  # GitHub / live demo URL
    order_index: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    profile: Profile = Relationship(back_populates="projects")
```

**Indexes:** `profile_id`, GIN on `tags`.

### `Certification`

```python
class Certification(SQLModel, table=True):
    __tablename__ = "certification"

    id: int = Field(primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)

    title: str
    issuer: str
    date: Optional[datetime] = None
    description: Optional[str] = None
    order_index: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    profile: Profile = Relationship(back_populates="certifications")
```

**Indexes:** `profile_id`.

### `Job`

> **Canonical reference for the hardened post-plan-27 shape:** `docs/design/JOB_MODEL.md` § B.1 + § C.
> This section sketches the same surface for cross-doc orientation; the canonical SQLModel + constraint list lives there.

```python
class Job(SQLModel, table=True):
    __tablename__ = "job"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)

    # Plan 27 (0.2.0.05): JobSource is now 10-valued per-source enum
    # (LINKEDIN / WORKDAY / GREENHOUSE / LEVER / ASHBY / INDEED /
    # COMPANY_DIRECT / RSSHUB / N8N_LEGACY / MANUAL). AUTOMATED dropped.
    source: JobSource
    board: ApplicationBoard
    # Plan 27: stable per-source identifier — e.g. `linkedin_job_id`,
    # `greenhouse_internal_id`. MANUAL source synthesizes `manual-<uuid4>`.
    external_id: str
    url: str = Field(index=True)
    url_type: str  # "ats" | "company_direct" | "rss" | "manual" | "external"

    company: str
    role: str
    team: Optional[str] = None
    location: Optional[str] = None
    # Plan 27 (D.6): Discover filter toggle "Remote only".
    remote_policy: RemotePolicy = Field(default=RemotePolicy.UNKNOWN)
    seniority_level: Optional[SeniorityLevel] = None

    posted_at: Optional[datetime] = None
    posted_at_text: Optional[str] = None      # plan 27: raw scraper string
    found_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    description: str
    description_html: Optional[str] = None
    description_extracted_at: Optional[datetime] = None      # plan 27
    description_extraction_model: Optional[str] = None       # plan 27
    criteria: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    skills_required: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    # Plan 27 (D.5): promoted from free-form str to typed VisaRestriction enum.
    visa_restrictions: VisaRestriction = Field(default=VisaRestriction.NOT_MENTIONED)

    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    equity_pct: Optional[float] = None

    score: float = Field(default=0.0)
    score_explanation: Optional[str] = None
    match_breakdown: dict = Field(default_factory=dict, sa_column=Column(JSON))

    queue_state: JobQueueState = Field(default=JobQueueState.UNSWIPED)
    tags: list[Tag] = Field(default_factory=list, sa_column=Column(ARRAY(String)))

    warm_intro_contact_id: Optional[int] = Field(default=None, foreign_key="contact.id")
    # Plan 27 (D.2): FK to the JobScrapeRun row that last touched this Job.
    last_scrape_run_id: Optional[int] = Field(default=None, foreign_key="job_scrape_run.id")
    raw_meta: dict = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None
```

**Indexes:** `user_id`, `(user_id, queue_state)`, `score desc`, `found_at desc`, GIN on `tags`, `(user_id, url)` partial-unique WHERE `deleted_at IS NULL`, `(user_id, source, external_id)` partial-unique WHERE `deleted_at IS NULL` (plan 27 § D.3 — primary dedup). **Validation:** `0.0 <= score <= 1.0`; `salary_min <= salary_max OR salary_min IS NULL`. **Phase 6+:** `JobEmbedding` (pgvector) sibling table for semantic match (plan 61 / `0.2.7.16`).

**`match_breakdown` canonical shape (plan 65 § T7):** the JSONB column is written by `services/scorer/orchestrator.py:_persist_score` with exactly the 18 keys below. New keys require a plan; existing-key shape changes bump `schema_version`. Surfaces for consumers: Discover card (`per_dimension`, `visa_concern`, `score`), `/jobs/{id}/match` modal (`strengths`, `gaps`, `visa_note`), document generator's bullet selection seed (`suggested_bullets`), debug surfaces (`tag_score`, `semantic_score`, `composite_pre_llm`, `layers_run`, `judge_skipped_reason`, `layer_4_provider`/`_model`, `scored_at`).

```json
{
    "score": 0.86,
    "per_dimension": {"ai-ml": 0.95, "platform": 0.88},
    "matched_tags": ["ai-ml", "platform"],
    "strengths": ["10+ years AI/ML"],
    "gaps": ["Kubernetes"],
    "suggested_bullets": [3, 7, 12],
    "visa_concern": false,
    "visa_note": null,
    "layers_run": ["tag", "semantic", "llm_judge"],
    "judge_skipped": false,
    "judge_skipped_reason": null,
    "layer_4_provider": "anthropic",
    "layer_4_model": "claude-sonnet-4-6",
    "scored_at": "2026-05-21T03:14:15Z",
    "tag_score": 0.78,
    "semantic_score": 0.82,
    "composite_pre_llm": 0.806,
    "schema_version": 1
}
```

**Service contract.** Job CRUD + dedup-aware upsert + scrape-run lifecycle go through `src/services/job_service.py` (8 functions per plan 27 § D.9): `upsert_job` / `get_job` / `list_jobs` / `archive_job` / `restore_job` / `create_manual_job` / `count_jobs_by_source` / `record_scrape_run`. No raw SQL in route handlers; scrapers (0.2.0.06+) write through `upsert_job` which is idempotent on `(user_id, source, external_id)`. Scoring goes through `src/services/scorer/orchestrator.py:score_job_layered` (plan 65 / 0.3.0).

### `JobScrapeRun`

> **Plan 27 (`0.2.0.05`) addition.** Canonical reference: `docs/design/JOB_MODEL.md` § B.2 + § C.

One row per scraper invocation — distinct from `AppEvent` (which is per-Application history). Powers the future Scrapes operator panel + `0.2.0.13` rate-limiting + `0.2.0.09` dedup observability.

```python
class JobScrapeRun(SQLModel, table=True):
    __tablename__ = "job_scrape_run"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)

    source: JobSource
    status: JobScrapeStatus      # RUNNING | SUCCESS | PARTIAL | FAILED | TIMED_OUT
    triggered_by: str            # "cron" | "manual" | "test" | "migration" (free-form)

    started_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    finished_at: Optional[datetime] = None

    requests_made: int = 0
    listings_returned: int = 0
    new_jobs: int = 0
    updated_jobs: int = 0

    errors: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    # errors[i] format: "stage=<list_jobs|fetch_detail|persist> url=<...> kind=<rate_limit|captcha|timeout|parse_failure|other> msg=<...>"

    duration_ms: Optional[int] = None
    raw_meta: dict = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Indexes:** `(source, started_at)`, `(user_id, status, started_at)`, `started_at`. **Validation:** `finished_at IS NULL OR finished_at >= started_at`; `requests_made / listings_returned / new_jobs / updated_jobs >= 0`. **Soft-delete:** NONE — scrape-run rows are operator audit data, pruned by a future cron at scale (Phase 6+).

### `JobEmbedding`

> **Plan 61 (`0.2.7.16`) addition.** Sibling table — one dense vector per Job (1:1 keyed by `job_id`).

```python
class JobEmbedding(SQLModel, table=True):
    __tablename__ = "job_embedding"
    job_id: int = Field(primary_key=True, foreign_key="job.id")
    user_id: int = Field(foreign_key="user.id", index=True)
    embedding: list[float] = Field(sa_column=Column(Vector(768), nullable=False))
    model: str = Field(max_length=128)        # `<provider>/<model>@<dim>`
    dim: int = Field(default=768)
    content_hash: str = Field(max_length=64, index=True)
    created_at: datetime
    updated_at: datetime
```

**Indexes:** HNSW `embedding vector_cosine_ops` (Postgres only); `content_hash` for idempotency lookup. **Validation:** `dim == 768`; provider-returned vector length must match — orchestrator drops mismatches. **Materialization:** nightly `embeddings.embed_pending_jobs` cron (02:00 UTC) + optional sync via `Settings.semantic_match_sync_on_upsert`. **Provenance:** `model` carries `<provider>/<model>@<dim>` so a provider swap invalidates the row + nightly refill replays. **Cosine sim**: pgvector `<=>` (distance), converted to similarity via `1 - d/2`.

### `ProfileEmbedding`

> **Plan 65 (`0.3.0.03`) addition.** Mirrors `JobEmbedding` — sibling table, 1:1 keyed by `user_id`.

```python
class ProfileEmbedding(SQLModel, table=True):
    __tablename__ = "profile_embedding"
    user_id: int = Field(primary_key=True, foreign_key="user.id")
    embedding: list[float] = Field(sa_column=Column(Vector(768), nullable=False))
    model: str = Field(max_length=128)
    dim: int = Field(default=768)
    content_hash: str = Field(max_length=64, index=True)
    created_at: datetime
    updated_at: datetime
```

**Indexes:** HNSW `embedding vector_cosine_ops` (Postgres only); `content_hash`. **Embed text:** `headline + summary_short + summary_full + top-20 Bullet.text` ordered by `Experience.order_index ASC, Bullet.order_index ASC`. **Refresh policy (OQ-6):** on-edit via `services/profile_service.update_field` / `update_application_questions` / `update_bullet` (best-effort, gated by `Settings.semantic_match_enabled`) AND nightly `embeddings.embed_pending_profiles` cron (02:30 UTC). **Idempotency:** SHA-1 of the embed text + the `model` identifier; matches skip the LLM call. **Cosine sim**: same operator as JobEmbedding — orchestrator inlines the SQL via `services/scorer/semantic_layer.py:_semantic_score`.

### `Application`

```python
class Application(SQLModel, table=True):
    __tablename__ = "application"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    job_id: Optional[int] = Field(default=None, foreign_key="job.id", index=True)
    # job_id is nullable for manually-tracked external applications

    # Identifying metadata (denormalized from Job for resilience)
    company: str
    role: str
    team: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    equity_pct: Optional[float] = None

    # Submission
    applied_at: Optional[datetime] = None  # NULL until DRAFT → APPLIED transition
    board: Optional[ApplicationBoard] = None
    external_url: Optional[str] = None  # link back on the board

    # ── Multi-axis state ───────────────────────────────────────────────
    status: ApplicationStatus = Field(default=ApplicationStatus.DRAFT)
    closed_reason: Optional[ClosedReason] = None  # required when status=CLOSED

    docs_state: DocsState = Field(default=DocsState.NONE)
    referral_state: ReferralState = Field(default=ReferralState.NONE)
    recruiter_state: RecruiterState = Field(default=RecruiterState.NONE)
    # outreach_engagement is COMPUTED — not stored; see KPI derivations § F

    # ATS adapter return state (BACKEND.md § K owns the SubmissionResult shape)
    submission_artifacts: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # opaque JSONB; e.g.
    # {board_application_id, retry_count, last_failure: {kind, message, captured_at},
    #  captcha_screenshot_path, field_mismatch_log}

    # Plan 66 (0.3.1): bundle generation audit trail. Opaque JSONB matching
    # `submission_artifacts` pattern. OVERWRITES on regenerate (single bundle =
    # single trace; historical audit lives in GeneratedDocument rows). Canonical
    # 17-key shape lives in `docs/design/RESUME_GENERATION.md § L` (alembic 0018).
    generation_trace: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None
    notes: Optional[str] = None

    job: Optional[Job] = Relationship(back_populates="applications")
    documents: list["GeneratedDocument"] = Relationship(back_populates="application")
    contact_links: list["ContactApplicationLink"] = Relationship(back_populates="application")
    events: list["AppEvent"] = Relationship(back_populates="application")
    email_threads: list["EmailThread"] = Relationship(back_populates="application")
    screener_answers: list["ApplicationScreenerAnswer"] = Relationship(back_populates="application")
```

**Indexes:** `(user_id, status)`, `job_id`, `applied_at desc`, `(user_id, status, recruiter_state)` for the "needs followup" scan, partial unique `(user_id, job_id) WHERE deleted_at IS NULL` to prevent duplicate live applications per job. **CHECK constraints:**
- `closed_reason IS NOT NULL WHEN status = 'CLOSED'`
- `applied_at IS NOT NULL OR status = 'DRAFT' OR deleted_at IS NOT NULL` — covers (a) DRAFT rows that haven't been submitted yet, (b) submitted rows in any post-submission status, and (c) discarded DRAFTs that flip to `CLOSED` with `closed_reason = withdrawn_by_me` and a non-null `deleted_at` (soft-delete) without ever having an `applied_at`. The previous "applied_at NOT NULL when status != DRAFT" formulation rejected discarded DRAFTs and was corrected 2026-05-01.

**Transitions** are enforced at the service layer (see § E). **`submission_artifacts`** is opaque JSONB written by ATS adapters (BACKEND.md § K) — Naavik never queries by its contents, only reads it for retry / debugging. When `submission_artifacts.last_failure` is populated AND `status = DRAFT`, the row surfaces in Discover's "Stuck in queue · {N}" right-rail card (`up_next_card` `state="stuck"`).

**`submission_artifacts.last_failure` sub-shape** (populated by `application_service._record_failure`; consumer: `up_next_card` chip + `GET /api/v1/applications/{id}/postmortem/{ts}`; graduated from plan 52 / `0.2.3.02`):

- `kind: str` — one of `FAILURE_*` taxonomy (`services/ats/base.py`: `captcha` / `rate_limit` / `auth_required` / `field_mismatch` / `unknown`).
- `message: str` — operator-facing failure message (truncated by adapter).
- `captured_at: str` — ISO 8601 UTC timestamp of the failure record.
- `postmortem_path: str | null` — relative path stem under `<data_dir>/data/postmortems/` (e.g. `postmortems/42/2026-05-20T10-12-51Z`). `null` when the postmortem write skipped or failed (LLM unconfigured / disk error / schema invalid). Two files at `<path>/{trace.json, analysis.md}`.

### `Contact`

```python
class Contact(SQLModel, table=True):
    __tablename__ = "contact"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)

    type: ContactType  # RECRUITER / EMPLOYEE / HIRING_MANAGER / HR
    name: str
    title: Optional[str] = None
    company: str = Field(index=True)
    linkedin_url: Optional[str] = None
    linkedin_id: Optional[str] = None  # vanity slug after /in/
    linkedin_degree: Optional[str] = None  # "1st" / "2nd · via Priya"
    email: Optional[str] = None
    relationship: Optional[str] = None  # "warm" / "cold"
    source: Optional[str] = None  # "scraped" / "manual" / "outreach"
    notes: Optional[str] = None
    last_touch_at: Optional[datetime] = None  # for "Mutual silence" sorting

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    application_links: list["ContactApplicationLink"] = Relationship(back_populates="contact")
    outreach_messages: list["OutreachMessage"] = Relationship(back_populates="contact")
```

**Indexes:** `(user_id, company)`, `linkedin_id` (partial unique per user), `email` (partial unique per user).

### `ContactApplicationLink`

```python
class ContactApplicationLink(SQLModel, table=True):
    __tablename__ = "contact_application_link"
    __table_args__ = (UniqueConstraint("application_id", "contact_id"),)

    id: int = Field(primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)

    referral_state: ReferralState = Field(default=ReferralState.NONE)
    introduced_at: Optional[datetime] = None
    notes: Optional[str] = None  # e.g. "intro'd by Priya 2026-04-15"

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    application: Application = Relationship(back_populates="contact_links")
    contact: Contact = Relationship(back_populates="application_links")
```

**Indexes:** `application_id`, `contact_id`, unique on `(application_id, contact_id)`. **Note:** `Application.referral_state` is the **derived** roll-up across all this application's links — `provided` if any link is provided, else `in_flight` if any is, etc. The roll-up runs in the service layer; this table is the source of truth per-link.

### `OutreachMessage`

```python
class OutreachMessage(SQLModel, table=True):
    __tablename__ = "outreach_message"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)

    intent: OutreachIntent  # INTRO / REFERRAL_REQUEST / FOLLOW_UP / THANK_YOU / CHECK_IN
    channel: str  # "linkedin_dm" | "email"
    subject: Optional[str] = None  # email only
    body: str

    status: OutreachStatus = Field(default=OutreachStatus.DRAFT)
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None  # LinkedIn DM open-receipt
    replied_at: Optional[datetime] = None
    response_summary: Optional[str] = None  # one-line summary of reply

    ai_generated: bool = Field(default=False)
    human_edited: bool = Field(default=False)
    drafted_by_model: Optional[str] = None
    linkedin_message_id: Optional[str] = None  # platform-side ID for linking

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    contact: Contact = Relationship(back_populates="outreach_messages")
```

**Indexes:** `(user_id, contact_id, sent_at desc)`, `status`, `application_id`.

### `EmailThread`

```python
class EmailThread(SQLModel, table=True):
    __tablename__ = "email_thread"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)
    contact_id: Optional[int] = Field(default=None, foreign_key="contact.id", index=True)

    provider: str  # "gmail" | "outlook" | "imap"
    thread_id_external: str  # Gmail thread id / equivalent
    subject: str
    classification: EmailClassification
    auto_classified: bool = Field(default=True)
    manually_verified: bool = Field(default=False)

    latest_message_at: datetime = Field(index=True)
    message_count: int = Field(default=0)
    messages: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    # JSONB list per Phase 1; each message: {sender, recipient, sent_at, direction (INBOUND/OUTBOUND),
    # body_preview (first 500 chars), classification, ai_classified, message_id_external}
    # Full body fetched on-demand from Gmail per BACKEND.md § G.13.

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    application: Optional[Application] = Relationship(back_populates="email_threads")
```

**Indexes:** `(user_id, classification, latest_message_at desc)`, `(user_id, thread_id_external)` unique.

**Phase 2+:** if message volume per thread grows, promote `messages` to a separate `EmailMessage` table with `thread_id` FK.

### `AppEvent`

```python
class AppEvent(SQLModel, table=True):
    __tablename__ = "app_event"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)
    # nullable for user-level events (e.g. profile_updated) that don't belong to one application

    kind: AppEventKind
    occurred_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # See § M for per-kind payload schemas.

    actor: Optional[str] = None  # "user" | "system" | "scheduler" | "<service_name>"

    created_at: datetime = Field(default_factory=datetime.utcnow)

    application: Optional[Application] = Relationship(back_populates="events")
```

**Indexes:** `(application_id, occurred_at desc)`, `(user_id, kind, occurred_at desc)`. Per § M, payload schemas vary per `kind` — application code reads via discriminated Pydantic union.

### `GeneratedDocument`

```python
class GeneratedDocument(SQLModel, table=True):
    __tablename__ = "generated_document"

    id: int = Field(primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    kind: GeneratedDocumentKind  # RESUME / COVER_LETTER
    path: str  # relative path under ~/.naavik/data/documents/<app_id>/
    byte_size: int
    page_count: Optional[int] = None
    compiled_at: datetime
    model: Optional[str] = None  # e.g. "claude-3.5-sonnet-20250219"
    cost_usd: Optional[float] = None
    token_count: Optional[int] = None
    error: Optional[str] = None  # populated when compile failed

    bullet_selection: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # Resume-only. Shape:
    # {
    #   "selected_ids": [1, 3, 5, 7, 8, 11],
    #   "trimmed_lines": {
    #     "1": "Built Intuit's ML personalization platform; +23% homepage CTR / $4.2M revenue",
    #     ...
    #   }
    # }

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    application: Application = Relationship(back_populates="documents")
```

**Indexes:** `(application_id, kind, compiled_at desc)`. **Storage boundary:** PDFs live on the filesystem at the path; the DB row is metadata. Backups/snapshots include both.

### `ApplicationScreenerAnswer`

See § J for full lifecycle. Model:

```python
class ApplicationScreenerAnswer(SQLModel, table=True):
    __tablename__ = "application_screener_answer"

    id: int = Field(primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    question_text: str
    question_fingerprint: str = Field(index=True)
    question_type: ScreenerQuestionType
    choices: Optional[list[str]] = Field(default=None, sa_column=Column(ARRAY(String)))
    required: bool = Field(default=True)
    order_index: int = Field(default=0)

    answer: Optional[str] = None
    source: ScreenerAnswerSource = Field(default=ScreenerAnswerSource.DRAFTED)
    drafted_by_model: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    application: Application = Relationship(back_populates="screener_answers")
```

### `ATSCredential`

See § K for full lifecycle. Model:

```python
class ATSCredential(SQLModel, table=True):
    __tablename__ = "ats_credential"
    __table_args__ = (UniqueConstraint("user_id", "board"),)

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    board: ApplicationBoard
    has_credential: bool = Field(default=False)
    login_status: AtsLoginStatus = Field(default=AtsLoginStatus.NOT_CONFIGURED)
    last_login_at: Optional[datetime] = None
    last_failure_kind: Optional[str] = None  # "captcha" / "auth_required" / etc.

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

**No secret material here.** Cookies, tokens, 2FA backups all live in `~/.naavik/secrets.enc` (see § H).

### `ApiUsage`

Per-call audit + cost tracking for every LLM invocation. Wrapped around every `LLMProvider.complete / structured / stream` call by `services/llm_tracker.py` (BACKEND.md § M.4). Aggregated daily by the `admin.aggregate_costs` cron and surfaced in Settings · LLM Provider cost cards.

```python
class ApiUsage(SQLModel, table=True):
    __tablename__ = "api_usage"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)
    # Optional FK so cost can be attributed to a specific Application bundle when relevant
    # (e.g. document_generator pre_generate calls); user-level / scraping-level calls leave it null.

    provider: LLMProvider              # anthropic | openai | ollama
    model: str                         # e.g. "claude-3.5-sonnet-20250219"
    method: str                        # "complete" | "structured" | "stream"
    prompt_name: Optional[str] = None  # e.g. "score_job", "draft_cover_letter" — blank for ad-hoc

    input_tokens: int
    output_tokens: int
    cost_usd: float                    # provider.estimate_cost(input_tokens, output_tokens)
    latency_ms: int

    succeeded: bool = Field(default=True)
    error_kind: Optional[str] = None   # "rate_limit" | "timeout" | "schema_validation" | "provider_error" | None

    occurred_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Indexes:** `(user_id, occurred_at desc)`, `(user_id, provider, occurred_at desc)`, `(application_id)` (partial). Aggregation queries hit the (user_id, occurred_at) index for time-window sums.

### `Settings` (singleton)

See § L for the full field listing and consumer mapping. Model definition:

```python
class Settings(SQLModel, table=True):
    __tablename__ = "settings"

    user_id: int = Field(primary_key=True, foreign_key="user.id")

    # LLM
    llm_provider: LLMProvider = Field(default=LLMProvider.ANTHROPIC)
    llm_model: str = Field(default="claude-3.5-sonnet-20250219")
    llm_api_key_fingerprint: Optional[str] = None  # sha256:abc... (real key in vault)
    llm_fallback_provider: Optional[LLMProvider] = None

    # Auto-apply
    auto_apply_enabled: bool = Field(default=False)
    auto_apply_score_threshold: float = Field(default=0.85)
    auto_apply_daily_cap: Optional[int] = None  # None = unlimited

    # Cost-aware DRAFT generation
    eager_review_generation: bool = Field(default=True)
    # True (default): /discover/{id} GET auto-creates DRAFT + pre_generates resume + cover letter + screeners
    # False: lazy path — empty workspace with explicit "Tailor for this job" CTA on first visit;
    #        DRAFT created and bundle generated only on click. Cost-conscious users opt in.
    daily_llm_cost_cap_usd: Optional[float] = None
    # When set, hitting the cap auto-flips eager_review_generation to lazy for the remainder of the day
    # (resets at midnight UTC). UI shows a banner on Discover · review when capped.

    # Plan 66 (0.3.1): bundle generation knobs (alembic 0018). Canonical
    # reference: `docs/design/RESUME_GENERATION.md § N`.
    ai_writing_voice_samples: str = Field(default="")  # 0-5000 chars; supplements voice corpus
    cover_letter_format: str = Field(default="auto")  # "auto" | "standard" | "pain_letter"
    resume_template_preference: str = Field(default="auto")  # "auto" | "ats" | "creative"
    tier_2_evasion_enabled: bool = Field(default=False)  # opt-in; advanced
    parse_fidelity_threshold: float = Field(default=0.75)  # OQ-7 tier boundary

    # Notifications
    notify_threshold: float = Field(default=0.80)  # score gate for new-job alerts
    notify_on_errors: bool = Field(default=True)
    notifications_enabled: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # Shape: {"new_high_score_job": True, "application_sent": True, "interview_scheduled": True,
    #         "offer_received": True, "rejection": False}

    # Channels (URL/token in vault; bool here flags whether configured)
    discord_webhook_configured: bool = Field(default=False)
    telegram_bot_configured: bool = Field(default=False)
    portfolio_webhook_configured: bool = Field(default=False)
    portfolio_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["https://crypticsoul.dev"],
        sa_column=Column(ARRAY(String)),
    )
    # Self-hosters can edit to point at their own portfolio domain(s) without code changes.

    # Sources
    sources_enabled: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # {"linkedin": True, "workday": True, "greenhouse": True, "lever": True,
    #  "ashby": True, "indeed": False, "rss": True}
    source_schedules: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # {"linkedin": "*/30 * * * *", "greenhouse": "0 * * * *", ...} — overrides BACKEND.md § I.1 defaults
    workday_companies: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    scraper_proxy_configured: bool = Field(default=False)  # Phase 6+ — URL in vault

    # Deployment
    deployment_mode: DeploymentMode = Field(default=DeploymentMode.SELF_HOSTED)
    # deployment_version is runtime-populated via package metadata; not stored in DB

    # Misc
    debug: bool = Field(default=False)  # gates /_design/components

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    user: User = Relationship(back_populates="settings")
```

---

## D · Enum tables

All enums live in `src/models/enums.py`. Postgres ENUM types via SQLAlchemy `sa_Enum` so the database protects state.

```python
from enum import StrEnum


class ApplicationStatus(StrEnum):
    DRAFT = "DRAFT"
    APPLIED = "APPLIED"
    RECRUITER_SCREEN = "RECRUITER_SCREEN"
    ONSITE_LOOP = "ONSITE_LOOP"
    OFFER = "OFFER"
    CLOSED = "CLOSED"


class ClosedReason(StrEnum):
    REJECTED_BY_THEM = "rejected_by_them"
    WITHDRAWN_BY_ME = "withdrawn_by_me"
    GHOSTED = "ghosted"
    ACCEPTED_OTHER = "accepted_other"


class DocsState(StrEnum):
    NONE = "none"
    GENERATING = "generating"
    READY = "ready"
    STALE = "stale"      # bullets edited after generation; needs re-tailor
    FAILED = "failed"


class ReferralState(StrEnum):
    NONE = "none"
    REQUESTED = "requested"
    IN_FLIGHT = "in_flight"     # contact agreed to refer, hasn't done it yet
    PROVIDED = "provided"
    DECLINED = "declined"


class RecruiterState(StrEnum):
    NONE = "none"
    ENGAGED = "engaged"          # they reached out / replied
    RESPONDED = "responded"      # active back-and-forth
    SILENT = "silent"            # waiting on them ≥ 3 days
    STALLED = "stalled"          # ≥ 14 days no movement


class JobQueueState(StrEnum):
    UNSWIPED = "unswiped"
    SAVED = "saved"
    SKIPPED = "skipped"
    QUEUED_FOR_AUTO_APPLY = "queued_for_auto_apply"
    APPLIED = "applied"


class JobSource(StrEnum):
    """Per-source provenance — plan 27 (`0.2.0.05`) replaced the AUTOMATED catch-all
    with 9 per-source values + MANUAL. Pre-plan-27 rows with source='automated'
    are remapped to per-board values by alembic 0005 (board::text::jobsource).
    `automated` lingers in the Postgres ENUM type only (no clean DROP VALUE
    before PG16); follow-up `0.2.5.NN` cosmetic cleanup row tracks the purge.
    Canonical reference: `docs/design/JOB_MODEL.md` § C.1.
    """
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


class VisaRestriction(StrEnum):
    """Plan 27 (`0.2.0.05`) promoted from `Job.visa_restrictions: str | None`.
    AI extraction emits one of these 4 values; the scorer's visa filter (plan
    10 § C.1) matches against `US_CITIZEN_ONLY` / `GREEN_CARD_REQUIRED` when
    `Profile.visa_sponsorship_needed = NEEDED_NOW`.
    Canonical reference: `docs/design/JOB_MODEL.md` § C.2.
    """
    US_CITIZEN_ONLY = "us_citizen_only"
    GREEN_CARD_REQUIRED = "green_card_required"
    SPONSORSHIP_AVAILABLE = "sponsorship_available"
    NOT_MENTIONED = "not_mentioned"


class RemotePolicy(StrEnum):
    """Discover filter toggle "Remote only" — plan 27 (`0.2.0.05`).
    AI extraction populates this; default `UNKNOWN` when JD doesn't say.
    Canonical reference: `docs/design/JOB_MODEL.md` § C.3.
    """
    REMOTE = "remote"          # fully remote
    HYBRID = "hybrid"          # 1-3 days in-office
    ONSITE = "onsite"          # 4-5 days in-office
    UNKNOWN = "unknown"


class SeniorityLevel(StrEnum):
    """Discover filter toggle — plan 27 (`0.2.0.05`). 7-value resolution
    covers the universe of US tech postings; AI extraction maps job-title
    variants onto one of these. Canonical reference: `docs/design/JOB_MODEL.md` § C.4.
    """
    ENTRY = "entry"            # 0-2 yrs
    MID = "mid"                # 2-5 yrs
    SENIOR = "senior"          # 5-8 yrs
    STAFF = "staff"            # 8+ yrs IC; design / influence wide
    PRINCIPAL = "principal"    # tech-lead / architect
    EXEC = "exec"              # VP+
    UNKNOWN = "unknown"


class JobScrapeStatus(StrEnum):
    """Lifecycle status of a JobScrapeRun row — plan 27 (`0.2.0.05`, § D.2).
    Canonical reference: `docs/design/JOB_MODEL.md` § C.5.
    """
    RUNNING = "running"
    SUCCESS = "success"        # all listings processed, 0 errors
    PARTIAL = "partial"        # some listings processed, some errors
    FAILED = "failed"          # zero listings persisted
    TIMED_OUT = "timed_out"    # cron hit budget before completing


class BulletSelectionOverride(StrEnum):
    ALWAYS_INCLUDE = "always_include"
    NEVER_INCLUDE = "never_include"
    # null = AI auto-decides per JD


class Tag(StrEnum):
    AI_ML = "ai-ml"
    BACKEND = "backend"
    FRONTEND = "frontend"
    DEVOPS = "devops"
    DATA_ENG = "data-eng"
    GENAI = "genai"
    LEADERSHIP = "leadership"
    PLATFORM = "platform"
    PRODUCT = "product"


class WorkAuthorization(StrEnum):
    US_CITIZEN = "us_citizen"
    GREEN_CARD = "green_card"
    H1B = "h1b"
    OPT_CPT = "opt_cpt"
    OTHER_REQUIRES_SPONSORSHIP = "other_requires_sponsorship"


class VisaSponsorship(StrEnum):
    NOT_NEEDED = "not_needed"
    NEEDED_NOW = "needed_now"
    NEEDED_FUTURE = "needed_future"


class VeteranStatus(StrEnum):
    NOT_VETERAN = "not_veteran"
    VETERAN = "veteran"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class DisabilityStatus(StrEnum):
    NO = "no"
    YES = "yes"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class Race(StrEnum):
    ASIAN = "asian"
    BLACK = "black"
    HISPANIC = "hispanic"
    NATIVE_AMERICAN = "native_american"
    PACIFIC_ISLANDER = "pacific_islander"
    WHITE = "white"
    TWO_OR_MORE = "two_or_more"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class RelocateOpenness(StrEnum):
    OPEN = "open"
    OPEN_TO_LIST = "open_to_list"   # specific cities listed in profile
    REMOTE_ONLY = "remote_only"
    NO = "no"


class ApplicationBoard(StrEnum):
    GREENHOUSE = "greenhouse"
    WORKDAY = "workday"
    LEVER = "lever"
    ASHBY = "ashby"
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    COMPANY_DIRECT = "company_direct"
    MANUAL = "manual"


class AppEventKind(StrEnum):
    STATUS_CHANGE = "status_change"
    DOCS_GENERATED = "docs_generated"
    DOCS_FAILED = "docs_failed"
    REFERRAL_REQUESTED = "referral_requested"
    REFERRAL_PROVIDED = "referral_provided"
    EMAIL_RECEIVED = "email_received"
    EMAIL_SENT = "email_sent"
    LINKEDIN_DM_SENT = "linkedin_dm_sent"
    LINKEDIN_DM_REPLIED = "linkedin_dm_replied"
    NOTE_ADDED = "note_added"
    INTERVIEW_SCHEDULED = "interview_scheduled"


class StatusChangeTrigger(StrEnum):
    """Used in AppEvent.payload for STATUS_CHANGE events."""
    MANUAL = "manual"
    AUTO_FROM_EMAIL = "auto-from-email"
    DRAFT_CREATION = "draft_creation"
    DRAFT_SUBMITTED = "draft_submitted"
    AUTO_APPLY_QUEUED = "auto_apply_queued"
    AUTO_APPLY_SUBMITTED = "auto_apply_submitted"
    DISCARD = "discard"
    ATS_CALLBACK = "ats_callback"


class OutreachStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENT = "sent"
    OPENED = "opened"
    REPLIED = "replied"
    BOUNCED = "bounced"


class OutreachIntent(StrEnum):
    INTRO = "intro"
    REFERRAL_REQUEST = "referral_request"
    FOLLOW_UP = "follow_up"
    THANK_YOU = "thank_you"
    CHECK_IN = "check_in"


class ContactType(StrEnum):
    RECRUITER = "recruiter"
    EMPLOYEE = "employee"
    HIRING_MANAGER = "hiring_manager"
    HR = "hr"


class EmailClassification(StrEnum):
    INTERVIEW_REQUEST = "interview_request"
    REJECTION = "rejection"
    OFFER = "offer"
    ASSESSMENT = "assessment"
    FOLLOW_UP = "follow_up"
    OTHER = "other"


class ScreenerQuestionType(StrEnum):
    TEXTAREA = "textarea"
    SHORT_TEXT = "short_text"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    DATE = "date"
    NUMERIC = "numeric"
    FILE = "file"


class ScreenerAnswerSource(StrEnum):
    USER = "user"
    DRAFTED = "drafted"
    AUTO = "auto"


class AtsLoginStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    OK = "ok"
    EXPIRED = "expired"
    LOCKED = "locked"


class GeneratedDocumentKind(StrEnum):
    RESUME = "resume"
    COVER_LETTER = "cover_letter"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class DeploymentMode(StrEnum):
    SELF_HOSTED = "self_hosted"
    CLOUD = "cloud"
```

---

## E · State transitions

Each axis has a state machine. Backend services enforce; the database holds the current value. CHECK constraints enforce invariants only (e.g. `closed_reason NOT NULL WHEN status=CLOSED`).

### `Application.status`

```
                            ┌──────[discard]──────────┐
                            ▼                         │
DRAFT  ──[submit_success]──→  APPLIED  →  RECRUITER_SCREEN  →  ONSITE_LOOP  →  OFFER  →  CLOSED
  │                            │              │                  │             │
  │                            └──────────────┴──────────────────┴─────────────┴───→ CLOSED (via closed_reason)
  │
  └──────[auto-apply persistent failure (CAPTCHA / auth_required)]── stays DRAFT
                                                                     submission_artifacts.last_failure populated
                                                                     surfaces in /discover review queue
```

- DRAFT created when user opens `/discover/{job_id}` (manual review path) or right-swipes on Discover (auto-apply path).
- Forward-only progression APPLIED → CLOSED. Re-opening a closed application = create a new Application row referencing the same Job.
- Backwards transitions (e.g. ONSITE_LOOP → RECRUITER_SCREEN) are NOT modeled; if a recruiter "demotes" the application, treat as `manual_status_override` AppEvent with notes.
- DRAFT cannot transition to RECRUITER_SCREEN or later directly — it must go through APPLIED first.

### `Application.docs_state`

```
NONE → GENERATING → READY → STALE → GENERATING → READY
  ↓        ↓                            ↓
       FAILED ←─────────────────── FAILED
         ↓
     GENERATING (retry)
```

- STALE is set when any selected `Bullet` is `edited_at > GeneratedDocument.compiled_at`. Triggers user prompt to regen.
- FAILED retry preserves the prior bundle's path until success (no broken UI link).

### `Application.referral_state`

```
NONE → REQUESTED → IN_FLIGHT → PROVIDED
                       ↓
                   DECLINED
```

Roll-up rule: `Application.referral_state` = max-state across all `ContactApplicationLink` rows. PROVIDED beats IN_FLIGHT beats REQUESTED beats DECLINED beats NONE.

### `Application.recruiter_state`

Auto-derived by `application_service.derive_recruiter_states()` cron every 30min:

- `NONE → ENGAGED` on first inbound `EmailThread` classified as `INTERVIEW_REQUEST`, `ASSESSMENT`, or `FOLLOW_UP`.
- `ENGAGED → RESPONDED` on first outbound message (`EmailThread.messages[].direction = OUTBOUND`).
- `RESPONDED → SILENT` after 3 days no inbound message.
- `SILENT → STALLED` after 14 days total no inbound message.
- `STALLED` is terminal until a new email arrives, which jumps back to `RESPONDED` (or `ENGAGED` if no prior outbound).

### `Job.queue_state`

```
UNSWIPED → SAVED  (↑ swipe)
        → SKIPPED (← swipe)
        → QUEUED_FOR_AUTO_APPLY (→ swipe) → APPLIED (background submission completes)
        → APPLIED (manual review & apply path; bypasses QUEUED state)

SAVED → QUEUED_FOR_AUTO_APPLY (user revisits and decides)
SAVED → APPLIED (user opens, reviews, submits)

QUEUED_FOR_AUTO_APPLY → SAVED (user un-queues; only if Application not yet submitted)
```

`Job.queue_state` flips to APPLIED when the Application linked to this Job transitions to APPLIED (`status=APPLIED`). The relation is enforced by `application_service.submit_draft()`.

---

## F · KPI derivations (cross-axis)

The Overview KPI strip and Tracking metadata derive from the model. **All KPIs exclude DRAFT applications** — they're not part of the funnel until submitted.

| KPI | Derivation |
|---|---|
| Active Applications | `count(Application WHERE user_id=? AND status IN (APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER))` |
| Response Rate · 90d | `count(Application WHERE applied_at >= now()-90d AND recruiter_state >= ENGAGED) / count(Application WHERE applied_at >= now()-90d)` |
| Onsite Rate · 90d | `count(Application WHERE applied_at >= now()-90d AND status reached ONSITE_LOOP at any point) / count(applied_in_window)` — uses `AppEvent` history |
| Offer Rate · 90d | `count(Application WHERE applied_at >= now()-90d AND status reached OFFER) / count(applied_in_window)` |
| Funnel · 90d | `(applied → recruiter → screen-pass → onsite → offer)` counts via AppEvent history |
| Needs Followup count (Tracking banner) | `count(Application WHERE status != DRAFT AND (recruiter_state IN (SILENT, STALLED) OR exists(OutreachMessage WHERE sent_at < now()-3d AND status=SENT)))` |
| Outreach Engagement (per Application) | computed view: `referred` if any contact_link's `referral_state=PROVIDED`; `awaiting_reply` if last sent message > 0 days, no reply; `cold` if no messages or contacts; `active` otherwise |
| Auto-apply queue count (Discover up-next) | `count(Application WHERE status=DRAFT AND job.queue_state=QUEUED_FOR_AUTO_APPLY)` |

KPI values are computed on demand (not cached for Phase 1). If perf becomes an issue, materialize them via a periodic job and cache in `Settings` or a `KPI` table.

---

## G · Indexes summary

Critical indexes for Phase 1:

- `User.email` (unique)
- `Profile.user_id` (unique)
- `Bullet.experience_id`, GIN on `Bullet.tags`
- `Job.user_id`, `Job.queue_state`, `Job.score desc`, `Job.found_at desc`, GIN on `Job.tags`, partial unique on `Job.url` per user
- `Application.(user_id, status)`, `Application.applied_at desc`, `Application.(user_id, status, recruiter_state)`, partial unique `(user_id, job_id) WHERE deleted_at IS NULL`
- `Contact.user_id`, `Contact.company`, partial unique on `Contact.linkedin_id` per user
- `OutreachMessage.(user_id, contact_id, sent_at desc)`, `OutreachMessage.status`
- `EmailThread.(user_id, classification, latest_message_at desc)`, `(user_id, thread_id_external)` unique
- `AppEvent.(application_id, occurred_at desc)`, `(user_id, kind, occurred_at desc)`
- `ApplicationScreenerAnswer.(application_id)`, `ApplicationScreenerAnswer.(question_fingerprint)` (Phase 2+ for reuse cache)
- `ATSCredential.(user_id, board)` unique
- `ApiUsage.(user_id, occurred_at desc)`, `ApiUsage.(user_id, provider, occurred_at desc)`, `ApiUsage.(application_id)` partial
- `GeneratedDocument.(application_id, kind, compiled_at desc)`

Phase 6 adds `JobEmbedding` with pgvector index for semantic match (`Job.title || description` embedded; cosine sim search). Phase 2+ adds an index on `ApplicationScreenerAnswer.(question_fingerprint, user_id)` to power the reuse-cache lookup.

---

## H · Migration strategy

**Secrets boundary.** The DB stores **no** secret material. Anthropic / OpenAI / Ollama API keys, Gmail / Outlook OAuth refresh tokens, IMAP passwords, ATS login cookies + 2FA backups, LinkedIn session tokens, Discord webhook URLs, Telegram bot tokens, Netlify build hooks — all live encrypted on disk at `~/.naavik/secrets.enc` (AES-256-GCM, master key derived from `SECRET_KEY` env or a passphrase set during `naavik init`). This boundary is set in `AGENTS.md` and surfaced in Settings → Deployment.

Resolution at use-time: every service that touches a secret reads via `vault.get(scope, key)` (per BACKEND.md § H.1 `vault` service). DB rows store only "configured" booleans or sha256 fingerprints so the UI can show "key set" / "reconnect needed" without holding the secret.

**Migration mechanics:**

- Initial migration (`migrations/versions/0001_initial.py`) creates every table, every enum, every index in this doc. Single migration; no incremental Phase 1 splits.
- All subsequent migrations are additive (new columns nullable; new tables; new indexes). Backwards-compatible.
- Enum changes: never reorder values; only append. Enum removal requires a deprecation column-rename + cleanup migration.
- Phase 2 adds: `ScrapingSource`, `ApiUsage` (cost tracking from Settings), `ProfileAnswer` (screener-answer reuse cache).
- Phase 5 adds: `Notification`, `CalendarEvent`, additional `EmailClassification` values.
- Phase 6 adds: `JobEmbedding`, KPI materialization tables.

**`vector` extension** enabled in initial migration (cheap, lets future migrations add the table without re-touching the extension).

---

## I · Sample data hooks

Phase 1 fixtures are canonical in `docs/design/SAMPLE_DATA.md`. Counts are referenced in § B above. Every fixture row round-trips through Pydantic via a CI test (`tests/test_sample_data.py`) — fails CI if a field added here is missing in fixtures.

---

## J · Custom screener questions vs canonical EEO

The Profile carries **canonical EEO/visa fields as flat columns** (10 standardized fields, fixed taxonomy) — these are the questions every US board asks. Filled once at onboarding/profile-edit, auto-injected into every application bundle.

**Custom screener questions** — those whose wording or topic varies per JD ("Why Stripe?", "Are you OK with on-call?", "Years of Kafka experience?", "Salary expectation in CAD for our Toronto office?") — live as **`ApplicationScreenerAnswer`** rows on the Application, not on Profile.

**Lifecycle:**

1. **Capture.** During `/discover/{job_id}` review (per BACKEND.md § K.3), the JD scraper extracts screener questions from the application form (or known board taxonomies) and creates `ApplicationScreenerAnswer` rows on the DRAFT Application — `source=DRAFTED` for AI-drafted answers, `source=AUTO` for trivial Profile lookups (earliest_start, salary_expectation, work_authorization, visa_sponsorship_needed, willing_to_relocate, race_ethnicity, gender_identity, veteran_status, disability_status — anything matching a flat EEO column).
2. **Draft.** `document_generator.answer_screeners(application)` populates `answer` for `DRAFTED` rows from Profile + JD context; sets `drafted_by_model`.
3. **Review.** UI renders them in the Discover · review & apply right column with `drafted` chip; clicking through sets `reviewed_at`. Submit blocks until all required `DRAFTED` rows are reviewed (`reviewed_at IS NOT NULL`). `AUTO` rows are auto-marked reviewed at creation time.
4. **Submit.** Bundle includes the answers; ATS adapter posts them per board.
5. **Persist.** Rows live forever on the Application for audit + Phase 2+ reuse-cache lookups.

**Phase 2+ reuse cache.** When the same `question_fingerprint` appears on a future application, the prior `answer` is offered as a starting point (not auto-filled). Fingerprint = lowercase + strip punctuation + remove company name + stem. Implemented as a `ProfileAnswer` table keyed by `(user_id, question_fingerprint)`. Phase 1 punts on this — users re-draft each time; the cost of re-drafting is one LLM call per question.

**What does NOT live on Profile:** anything per-job, anything with variable wording, anything that needs human judgement per application (e.g. "Tell us about a time you failed"). Those stay on `ApplicationScreenerAnswer`.

**What DOES live on Profile** (the 10 canonical fields): work_authorization, visa_sponsorship_needed, willing_to_relocate, notice_period_days, salary_expectation_usd, earliest_start, veteran_status, disability_status, race_ethnicity, gender_identity. These have stable taxonomies and are reused on every application — flat columns are the right shape.

---

## K · ATS adapter scope (BACKEND.md owns)

ATS adapter logic — submission strategy per board, login flows, captcha handling, resume-parsing overrides — is **`docs/design/BACKEND.md` § K territory**, not this doc. DATA_MODEL.md owns only the **persistence shape**:

- **`Application.submission_artifacts: JSONB`** — opaque-to-the-DB blob written by ATS adapters. Holds `{board_application_id, retry_count, last_failure: {kind, message, captured_at}, captcha_screenshot_path, field_mismatch_log}` etc. Naavik never queries by its contents; the adapter reads it for retry decisions and the UI reads it for "view error details" links.
- **`Application.board: ApplicationBoard`** — adapter dispatch key.
- **`ATSCredential`** (entity #18) — DB row metadata only (`has_credential`, `login_status`, `last_login_at`, `last_failure_kind`). Secret material (cookies, tokens, 2FA backups) lives in the encrypted on-disk vault per § H.

**What lives in BACKEND.md, NOT here:**

- The 7 ATS adapters (Greenhouse / Lever / Ashby / Workday / LinkedIn / Indeed / Generic) and their submission strategies.
- `SubmissionResult` taxonomy (`ok / captcha / rate_limit / auth_required / field_mismatch / unknown`) and the failure-classified retry policy.
- Resume-parsing override logic for upload-and-auto-extract boards.
- Per-board login flows, 2FA handling, credential rotation, captcha-fallback to manual review queue.

Cross-reference: BACKEND.md § A (file layout: `services/ats/`), § H.1 (services), § K.5 (ATS submission per board), § J (`document_generator.answer_screeners`).

---

## L · Settings shape (consumer mapping)

The full Settings model (per § C) carries these fields. The mapping below shows which BACKEND.md service or UI surface consumes each.

| Field | Consumer (BACKEND.md ref) | Notes |
|---|---|---|
| `llm_provider`, `llm_model` | `llm/__init__.py:get_provider()` (M.2) | API key resolved via `vault.get(scope="llm", key=<provider>)`, not stored here |
| `llm_api_key_fingerprint` | UI (Settings · LLM Provider) | sha256 of the key for "key set" display — never the key itself |
| `llm_fallback_provider` | `llm_tracker.tracked_call` (M.5) | Optional |
| `auto_apply_enabled`, `auto_apply_score_threshold`, `auto_apply_daily_cap` | `application_service.process_auto_apply_queue()` (K.2) | |
| `eager_review_generation`, `daily_llm_cost_cap_usd` | `application_service.get_or_create_draft()` (K.3) | Default eager (matches SCREENS.md § 8 "generating skeletons"). Lazy path = empty `pages/discover_review.html` with explicit "Tailor for this job" CTA. Cap-trigger flips eager → lazy mid-day. |
| `portfolio_cors_allowed_origins` | `services/portfolio_sync.py` CORS middleware | Default `["https://crypticsoul.dev"]`; self-hosters edit Settings · Account to point at their own portfolio domain(s). |
| `notify_threshold` | `scraper_service.scrape()` (J.3) | High-score Discord/Telegram notification gate |
| `notify_on_errors` | `services/notifications.py` (N) | Critical-error Discord gate |
| `notifications_enabled` (JSONB dict) | `services/notifications.py` | Per-event-type toggles |
| `discord_webhook_configured` | UI display only | Actual URL in vault (`scope="notifications", key="discord_webhook_url"`) |
| `telegram_bot_configured` | UI display only | Actual token in vault |
| `portfolio_webhook_configured` | UI display only | Netlify build hook URL in vault |
| `sources_enabled`, `source_schedules` (JSONB) | `scheduler/jobs.py`, `scraper_service` (I, J) | Per-source enable + cron override |
| `workday_companies` | `scraper/workday.py` (J.2) | Per-tenant watchlist |
| `scraper_proxy_configured` | `scraper/base.py` (J.4) | Phase 6+; URL in vault |
| `deployment_mode` | `services/portfolio_sync.py`, Settings UI | `self_hosted` vs `cloud` |
| `debug` | `/_design/components` route gate (B) | |
| `score_per_dim_weights` (JSONB) | `services/scorer/weights.py:resolve_weights` | Plan 65 (0.3.0.02). Per-tag operator-tunable weights for layer-1 tag overlap. Defaults to `{}` → all-1.0. JSONB validator drops unknown Tag keys; values clamped [0, 3]. UI editor ships in 0.3.2.04; v1 ships JSONB editable via PUT route only. |
| `semantic_match_enabled` | `services/embedding_service.embed_job` + `embed_profile`; `scorer.orchestrator.score_unscored_jobs` | Plan 61 / 0.2.7.16 + plan 65 / 0.3.0. Master gate for semantic + LLM scoring; default OFF so a fresh self-host doesn't bill embedding calls until the operator opts in. |

**`encryption_key` is NOT on Settings.** The vault's master key is derived from the `SECRET_KEY` env var (or a passphrase set during `naavik init`). Storing the key in the DB would defeat the encryption boundary.

---

## M · AppEvent payload schemas

Per `AppEvent.kind`, payload JSONB has a kind-specific shape. Implementer uses Pydantic discriminated unions in Python; Postgres enforces nothing on the JSONB beyond well-formed JSON.

```python
# src/models/app_event_payloads.py — schemas per kind

class StatusChangePayload(BaseModel):
    from_status: Optional[str]              # ApplicationStatus value or None (initial creation)
    to_status: str                          # ApplicationStatus value
    triggered_by: StatusChangeTrigger
    notes: Optional[str] = None             # human-readable context for manual transitions

class DocsGeneratedPayload(BaseModel):
    generated_document_id: int
    kind: GeneratedDocumentKind
    model: str
    cost_usd: float
    token_count: int
    page_count: Optional[int]

class DocsFailedPayload(BaseModel):
    kind: GeneratedDocumentKind
    error: str
    retry_count: int

class ReferralRequestedPayload(BaseModel):
    contact_id: int
    via_channel: str                        # "linkedin_dm" | "email"

class ReferralProvidedPayload(BaseModel):
    contact_id: int
    provided_at: datetime

class EmailReceivedPayload(BaseModel):
    thread_id: int
    message_id_external: str
    sender: str
    subject_preview: str
    classification: EmailClassification
    urgent: bool                            # auto-flagged by classifier
    auto_classified: bool

class EmailSentPayload(BaseModel):
    thread_id: int
    message_id_external: str
    recipient: str
    subject_preview: str

class LinkedInDmSentPayload(BaseModel):
    outreach_message_id: int
    contact_id: int
    intent: OutreachIntent

class LinkedInDmRepliedPayload(BaseModel):
    outreach_message_id: int
    contact_id: int
    replied_at: datetime
    summary: Optional[str]                  # one-line response summary

class NoteAddedPayload(BaseModel):
    note_text_preview: str                  # first 200 chars
    full_note_field: str = "application.notes"

class InterviewScheduledPayload(BaseModel):
    when: datetime
    where: Optional[str]                    # location or video link
    contact_ids: list[int]                  # interviewers
    calendar_event_id: Optional[str]        # if synced via Google Calendar (Phase 5)
```

Reading: `AppEvent.payload` deserializes to the schema matching `AppEvent.kind` via discriminated union. Writing: `AppEvent` row creation goes through a service helper that validates the payload shape before serializing to JSON.

---

## N · Decisions (locked 2026-04-30 — original Open Questions from plan 05)

All 11 open questions from plan 05 graduated as locked decisions:

1. **`User` vs `Profile` split** — Kept split. Auth changes are common; profile changes shouldn't trigger auth-table writes.
2. **`user_id` on every table** — Yes, even single-user MVP. Cheap now; multi-user is Phase 2+.
3. **`Job.queue_state` placement** — On `Job` for Phase 1; capture history via `AppEvent` if/when needed.
4. **`outreach_engagement` computed vs cached** — Computed on demand for Phase 1; cache in Phase 4+ when row count grows.
5. **EEO/visa fields** — Flat columns on `Profile`. Multi-region (UK/EU) gets a separate child table when added.
6. **Soft delete vs hard delete** — Soft delete (`deleted_at` nullable timestamp) for all user-authored entities; hard delete only for Settings test rows and ephemeral state.
7. **`AppEvent` polymorphism** — Single table with JSONB payload + per-kind Pydantic schemas (§ M).
8. **pgvector readiness** — Enable in initial migration; Phase 6 adds the `JobEmbedding` table.
9. **Constraint enforcement** — Service layer for transitions; DB CHECK for invariants (`closed_reason NOT NULL WHEN status=CLOSED`, `salary_min <= salary_max`, `applied_at NOT NULL WHEN status != DRAFT`).
10. **Screener answer reuse cache** — Defer to Phase 2+. Phase 1 re-drafts each time.
11. **ATS credential storage** — Vault on disk; DB row carries metadata only.
