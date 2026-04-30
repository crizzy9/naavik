---
Status: GRADUATED → docs/design/DATA_MODEL.md
Type: design
Authored: 2026-04-30
Last updated: 2026-04-30
Graduated: 2026-04-30
Depends on: 02-mvp-master-plan
---

> **Graduated 2026-04-30** to `docs/design/DATA_MODEL.md`. Tier-1/2/3 fixes folded in during graduation:
>
> **Tier 1 (DRAFT cascade):** § A axis table — Application pipeline now `DRAFT · APPLIED · ... · CLOSED`; § C Application sample — `status` defaults to DRAFT; `applied_at` nullable until DRAFT → APPLIED; § D enum — DRAFT added; § E state transitions — DRAFT → APPLIED, DRAFT → CLOSED, DRAFT stays-DRAFT on auto-apply persistent failure; § F KPIs — explicit "all KPIs exclude DRAFT" rule.
>
> **Tier 1 (model fill-ins):** § C now has all 18 entity definitions in full (User, Experience, Skill, Education, Project, Certification, Job, Contact, ContactApplicationLink, OutreachMessage, EmailThread, AppEvent, GeneratedDocument, ApplicationScreenerAnswer, ATSCredential, Settings — plus Profile/Bullet/Application from the original plan). EmailMessage held as JSONB list on EmailThread for Phase 1; promotable to a separate table in Phase 2+.
>
> **Tier 1 (other):** § L "Settings shape (consumer mapping)" cross-references every BACKEND.md service that consumes a Settings field; clarifies which fields are configured-bool vs fingerprint vs structured config. `encryption_key` removed (vault master key derived from `SECRET_KEY` env, not stored in DB). § M "AppEvent payload schemas" introduces per-kind Pydantic discriminated unions with concrete payload shapes for all 11 `AppEventKind` values + new `StatusChangeTrigger` enum (`manual`, `auto-from-email`, `draft_creation`, `draft_submitted`, `auto_apply_queued`, `auto_apply_submitted`, `discard`, `ats_callback`).
>
> **Tier 2:** front-matter `Approved` field omitted from canonical doc; CHECK constraint `applied_at NOT NULL WHEN status != DRAFT` added; `partial unique (user_id, job_id) WHERE deleted_at IS NULL` index added to prevent duplicate live applications per job.
>
> **Tier 3:** `GeneratedDocumentKind` enum (RESUME / COVER_LETTER) introduced; `JobSource` enum (AUTOMATED / MANUAL) introduced; `LLMProvider` and `DeploymentMode` enums added.
>
> **Bonus consistency fixes:** `Job.match_breakdown` JSONB shape spelled out; `Job.warm_intro_contact_id` FK added (drives Discover · review warm-intro pill); `Job.raw_meta` JSONB for scraper extras; `Bullet` ARRAY type for `tags` with GIN index documented; `OutreachMessage.linkedin_message_id` for platform-side linking; `EmailThread.thread_id_external` unique per user.

# 05 · Data model

## Goal

Define the canonical SQLModel definitions for the entire MVP — every entity, every field, every enum, every relationship, every index — including the **multi-axis Application state model** that plan 02 § B introduced. The catalog is what backend implementation (plan 10) builds the actual `src/models/*.py` files from, and what plan 07 (sample data) populates with realistic fixtures. When approved, this plan's content graduates to `docs/design/DATA_MODEL.md`.

## Context / why

`ROADMAP.md` carries a sketch of the data model under "Data Model" but it's not authoritative — it's a snapshot of an earlier design that stayed close to the realigned model after plan 01 but lacks the multi-axis sub-state detail (`docs_state`, `referral_state`, `recruiter_state`, etc.). Plan 02 § B mandated that the lifecycle be modeled as **multiple orthogonal axes** rather than a flat enum so cohesive state like "RECRUITER_SCREEN + referral provided + docs ready + recruiter responded" is expressible without inventing compound enum values.

This plan defines every model that the MVP needs to ship. Backend implementation (plan 10) translates these to SQLModel + Alembic migrations 1:1.

## Proposal

### A · Lifecycle modeling principle (recap from plan 02)

The job-search lifecycle has **multiple orthogonal state axes** modeled as separate fields, never collapsed into a flat enum. The starting axes:

| Axis | Lives on | States | Purpose |
|---|---|---|---|
| **Discovery / queue** | `Job.queue_state` | `unswiped · saved · skipped · queued_for_auto_apply · applied` | Discover-side states. `applied` flips when an Application row is created. |
| **Application pipeline** | `Application.status` | `APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED` | Post-submission Tracking pipeline. |
| **Application close reason** | `Application.closed_reason` (nullable; required when `status=CLOSED`) | `rejected_by_them · withdrawn_by_me · ghosted · accepted_other` | Hidden by default in Tracking. |
| **Document generation** | `Application.docs_state` | `none · generating · ready · stale · failed` | Drives "AI · auto-fits 1pg" badge, retry on failure. |
| **Referral** | `Application.referral_state` | `none · requested · in_flight · provided · declined` | Powers warm-intro pill on Discover · review. |
| **Recruiter engagement** | `Application.recruiter_state` | `none · engaged · responded · silent · stalled` | Auto-derived from email signals. |
| **Outreach engagement** (computed) | view over `OutreachMessage` + `Contact` for the Application | `cold · active · awaiting_reply · referred · converted` | Drives Outreach left-rail grouping. |
| **Application questions** | `Profile.application_questions` (one-time per user) | per-field enums | Filled at onboarding/profile-edit; auto-injected into application bundles. |
| **Bullet selection override** | `Bullet.selection_override` | `null · always_include · never_include` | Per-bullet manual pin; default null = AI auto-decides. |

These axes are **independent**. Compound states emerge from intersection — they are NOT new enum values.

**Two related but distinct concepts not on the axis table above:**

- **Canonical EEO/visa application questions** — Phase 1 ships ten standardized US fields (work_authorization, visa_sponsorship_needed, willing_to_relocate, notice_period_days, salary_expectation_usd, earliest_start, veteran_status, disability_status, race_ethnicity, gender_identity) as flat columns on `Profile`. Filled once at onboarding/profile-edit, auto-injected into every application bundle.
- **Per-job custom screener questions** — JD-specific questions whose wording varies per board ("Why Stripe?", "Are you OK with on-call rotation?", "Years of Kafka experience?") captured during scrape and frozen on the **Application** as `ApplicationScreenerAnswer` rows (entity #17 below). AI drafts answers from Profile + JD; user reviews before submit. **Not on Profile** because they're per-job — the same topic gets re-asked with different wording, and most of them are one-off context never seen again.

See § J for the full screener-answer model and lifecycle.

### B · Entity inventory

18 SQLModel entities + 1 settings singleton. Phase 1 ships all of them; Phase 2+ extends some (e.g. scraping sources, semantic embeddings).

| # | Entity | Purpose | Phase 1 row count (rough) |
|---|---|---|---|
| 1 | `User` | Identity + auth | 1 (single-user MVP; multi-user later) |
| 2 | `Profile` | One per user — biographical, application-questions, summary | 1 |
| 3 | `Experience` | Roles in chronological list | 4–6 |
| 4 | `Bullet` | Single long-form text + tags + selection_override | 12–18 across roles |
| 5 | `Skill` | Grouped (category, items) | 5–8 categories |
| 6 | `Education` | Schools | 1–3 |
| 7 | `Project` | Portfolio projects | 3–5 |
| 8 | `Certification` | Optional | 0–3 |
| 9 | `Job` | Pre-application opportunities (scraped or manual) | ~50 active in queue |
| 10 | `Application` | Post-submission record | ~30 active (per Tracking sample) |
| 11 | `Contact` | Recruiter / employee at a company | ~20 |
| 12 | `ContactApplicationLink` | Many-to-many: which contacts know about which applications | ~25 |
| 13 | `OutreachMessage` | LinkedIn DM / email sent | ~40 |
| 14 | `EmailThread` | Auto-classified email thread | ~20 |
| 15 | `AppEvent` | Unified timeline event (any state change, any touch) | ~150 |
| 16 | `GeneratedDocument` | Resume PDF + cover letter PDF/text artifacts | ~30 (one bundle per submitted Application) |
| 17 | `ApplicationScreenerAnswer` | Per-job custom screener questions + drafted/user answers (see § J) | ~20 across submitted Apps (1–3 per app) |
| 18 | `ATSCredential` | Per-board login state metadata (DB row only; secret material lives encrypted on disk per § H secrets boundary) | 0 in Phase 1 sample |
| – | `Settings` (singleton) | Per-user LLM provider, auto-apply config, etc. | 1 |

Phase 2+ adds: `ScrapingSource`, `Notification`, `CalendarEvent`, `JobEmbedding` (pgvector), `ProfileAnswer` (screener-answer reuse cache; see § J).

### C · Sample model definitions (validate the format)

Three fully-specified entities below — `Profile`, `Application`, `Bullet`. They cover the most state-rich models. Other entities follow the same shape and get drafted at graduation time.

#### `Profile`

```python
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON
from typing import Optional
from .enums import (
    WorkAuthorization, VisaSponsorship, VeteranStatus, DisabilityStatus,
    Race, Gender, RelocateOpenness,
)


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

    # US Application questions (Phase 1: US only)
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

    # Portfolio integration
    cover_letter_base: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="profile")
    experiences: list["Experience"] = Relationship(back_populates="profile")
    skills: list["Skill"] = Relationship(back_populates="profile")
    educations: list["Education"] = Relationship(back_populates="profile")
    projects: list["Project"] = Relationship(back_populates="profile")
    certifications: list["Certification"] = Relationship(back_populates="profile")
```

**Indexes:** `user_id` (unique), `email`. **Validation:** `salary_expectation_usd >= 0`; `notice_period_days >= 0`. **Computed:** `application_readiness` (count of non-null EEO/visa fields) — done in service layer, not stored.

---

#### `Bullet`

```python
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, ARRAY, String
from .enums import Tag, BulletSelectionOverride


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

    experience: "Experience" = Relationship(back_populates="bullets")
```

**Indexes:** `experience_id`, GIN on `tags` (Postgres array search). **Validation:** `len(text) > 0`; `tags ⊆ Tag.values`. **No length cap** on `text` — AI trims at apply time. The bullet does **not** carry `oneline`, `detailed`, `default_include`, or metric fields — those were removed in 2026-04 (see plan 01).

---

#### `Application`

```python
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON
from .enums import (
    ApplicationStatus, ClosedReason, DocsState,
    ReferralState, RecruiterState, ApplicationBoard,
)


class Application(SQLModel, table=True):
    __tablename__ = "application"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    job_id: Optional[int] = Field(default=None, foreign_key="job.id", index=True)
    # job_id is nullable for manually-tracked applications without a Job row

    # Identifying metadata (denormalized from Job for resilience)
    company: str
    role: str
    team: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    equity_pct: Optional[float] = None

    # Submission
    applied_at: datetime
    board: Optional[ApplicationBoard] = None  # greenhouse / workday / lever / ashby / manual
    external_url: Optional[str] = None  # link back to the application on the board

    # ── Multi-axis state ───────────────────────────────────────────────
    status: ApplicationStatus = Field(default=ApplicationStatus.APPLIED)
    closed_reason: Optional[ClosedReason] = None  # required when status=CLOSED

    docs_state: DocsState = Field(default=DocsState.NONE)
    referral_state: ReferralState = Field(default=ReferralState.NONE)
    recruiter_state: RecruiterState = Field(default=RecruiterState.NONE)
    # outreach_engagement is COMPUTED — not stored; see KPI derivations § F

    # ATS adapter return state (plan 04 § K owns the SubmissionResult shape)
    submission_artifacts: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # opaque JSONB written by ATS adapters; e.g.
    # {board_application_id, retry_count, last_failure: {kind, message, captured_at},
    #  captcha_screenshot_path, field_mismatch_log}

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None

    # Relationships
    job: Optional["Job"] = Relationship(back_populates="applications")
    documents: list["GeneratedDocument"] = Relationship(back_populates="application")
    contact_links: list["ContactApplicationLink"] = Relationship(back_populates="application")
    events: list["AppEvent"] = Relationship(back_populates="application")
    email_threads: list["EmailThread"] = Relationship(back_populates="application")
    screener_answers: list["ApplicationScreenerAnswer"] = Relationship(back_populates="application")
```

**Indexes:** `(user_id, status)`, `job_id`, `applied_at desc`, `(user_id, status, recruiter_state)` for the "needs followup" scan. **Validation (CHECK constraint or service-layer enforcement):** `closed_reason IS NOT NULL WHEN status = 'CLOSED'`. **Transitions** are enforced at the service layer (see § E). **`submission_artifacts`** is opaque JSONB written by ATS adapters (plan 04 § K) — Naavik never queries by its contents, only reads it for retry / debugging.

### D · Enum tables

All enums live in `src/models/enums.py`. Postgres ENUM types (via SQLAlchemy `sa_Enum`) so the database protects state.

```python
from enum import StrEnum

class ApplicationStatus(StrEnum):
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
    PROVIDED = "provided"       # referral submitted internally
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
    TEXTAREA = "textarea"            # multi-line free text ("Why us?")
    SHORT_TEXT = "short_text"        # single-line free text
    SINGLE_SELECT = "single_select"  # one of N choices
    MULTI_SELECT = "multi_select"    # zero+ of N choices
    DATE = "date"
    NUMERIC = "numeric"              # years of experience, salary
    FILE = "file"                    # extra attachment beyond resume

class ScreenerAnswerSource(StrEnum):
    USER = "user"        # human-typed
    DRAFTED = "drafted"  # AI-drafted from Profile + JD; requires review_at before submit
    AUTO = "auto"        # auto-filled from canonical Profile field (e.g. earliest_start)

class AtsLoginStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"  # no credential set up yet
    OK = "ok"                          # last login succeeded
    EXPIRED = "expired"                # token / session expired; needs reconnect
    LOCKED = "locked"                  # account locked / captcha-walled / 2FA stalled
```

### E · State transitions (service-layer enforcement)

Each axis has a state machine. Backend implementation enforces in the service layer; the database holds the current value. Sample machines:

**`Application.status`:**
```
APPLIED → RECRUITER_SCREEN → ONSITE_LOOP → OFFER → CLOSED
   ↓            ↓                ↓           ↓
              CLOSED          CLOSED      CLOSED   (via closed_reason)
```
Forward-only except CLOSED is terminal. Re-opening a closed application = create a new Application row referencing the same Job.

**`Application.docs_state`:**
```
NONE → GENERATING → READY → STALE → GENERATING → READY
  ↓        ↓                            ↓
              FAILED ←─────────────── FAILED
                ↓
            GENERATING (retry)
```

**`Application.referral_state`:**
```
NONE → REQUESTED → IN_FLIGHT → PROVIDED
                       ↓
                   DECLINED
```

**`Application.recruiter_state`:**
- Auto-derived by the email classifier service every 10min
- `NONE → ENGAGED` on first inbound email
- `ENGAGED → RESPONDED` on user reply
- `RESPONDED → SILENT` after 3 days no inbound
- `SILENT → STALLED` after 14 days total no inbound

**`Job.queue_state`:**
```
UNSWIPED → SAVED  (↑ swipe)
        → SKIPPED (← swipe)
        → QUEUED_FOR_AUTO_APPLY (→ swipe) → APPLIED (background submission completes)
        → APPLIED (manual review & apply path; bypasses QUEUED state)

SAVED → QUEUED_FOR_AUTO_APPLY (user revisits and decides)
SAVED → APPLIED (user opens, reviews, submits)
```

### F · KPI derivations (cross-axis)

The Overview KPI strip and Tracking metadata derive from the model:

| KPI | Derivation |
|---|---|
| Active Applications | `count(Application WHERE user_id=? AND status IN (APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER))` |
| Response Rate · 90d | `count(Application WHERE applied_at >= now()-90d AND recruiter_state >= ENGAGED) / count(Application WHERE applied_at >= now()-90d)` |
| Onsite Rate · 90d | `count(Application WHERE applied_at >= now()-90d AND status reached ONSITE_LOOP at any point) / count(applied_in_window)` — uses `AppEvent` history |
| Offer Rate · 90d | `count(Application WHERE applied_at >= now()-90d AND status reached OFFER) / count(applied_in_window)` |
| Funnel · 90d | `(applied → recruiter → screen-pass → onsite → offer)` counts via AppEvent history |
| Needs Followup count (Tracking banner) | `count(Application WHERE recruiter_state IN (SILENT, STALLED) OR exists(OutreachMessage WHERE sent_at < now()-3d AND status=SENT))` |
| Outreach Engagement (per Application) | computed view: `referred` if any contact's link has `referral_state=PROVIDED`; `awaiting_reply` if last sent message > 0 days, no reply; `cold` if no messages or contacts; `active` otherwise |

KPI values are computed on demand (not cached for Phase 1). If perf becomes an issue, materialize them via a periodic job and cache in `Settings` or a `KPI` table.

### G · Indexes summary

Critical indexes for Phase 1:

- `User.email` (unique)
- `Profile.user_id` (unique)
- `Bullet.experience_id`
- `Bullet.tags` (GIN, for tag-based job matching)
- `Job.user_id`, `Job.queue_state`, `Job.score desc`, `Job.tags` (GIN)
- `Application.(user_id, status)`, `Application.applied_at desc`, `Application.(user_id, status, recruiter_state)`
- `Contact.user_id`, `Contact.company`
- `OutreachMessage.(user_id, contact_id, sent_at desc)`
- `EmailThread.(user_id, classification, latest_message_at desc)`
- `AppEvent.(application_id, occurred_at desc)`
- `ApplicationScreenerAnswer.(application_id)`, `ApplicationScreenerAnswer.(question_fingerprint)` (Phase 2+ for reuse cache)
- `ATSCredential.(user_id, board)` unique

Phase 6 adds `JobEmbedding` with pgvector index for semantic match (`Job.title || description` embedded; cosine sim search). Phase 2+ adds an index on `ApplicationScreenerAnswer.(question_fingerprint, user_id)` to power the reuse-cache lookup.

### H · Migration strategy

**Secrets boundary.** The DB stores **no** secret material. Anthropic / OpenAI / Ollama API keys, Gmail / Outlook OAuth refresh tokens, IMAP passwords, ATS login cookies + 2FA backups, LinkedIn session tokens — all live encrypted on disk at `~/.naavik/secrets.enc` (AES-256-GCM, master key derived from the runtime user's keyring or a passphrase set during `naavik init`). This boundary is set in `AGENTS.md` and surfaced in Settings → Deployment.

The DB-side `ATSCredential` row stores **only metadata** the UI needs to render: `(user_id, board, has_credential: bool, last_login_at, login_status: AtsLoginStatus, last_failure_kind)`. Secret resolution at use-time: the service reads the credential by `(user_id, board)` from the encrypted vault; the DB row tells the UI whether to show "connected" / "reconnect" / "set up" / "locked — see logs". Same pattern applies to `Settings.llm_provider` (DB stores the choice, key lives encrypted).

**Migration mechanics:**

- Initial migration (`migrations/versions/0001_initial.py`) creates every table, every enum, every index in this plan. Single migration; no incremental Phase 1 splits.
- All subsequent migrations are additive (new columns nullable; new tables; new indexes). Backwards-compatible.
- Enum changes: never reorder values; only append. Enum removal requires a deprecation column-rename + cleanup migration.
- Phase 2 adds: `ScrapingSource`, `ApiUsage` (cost tracking from Settings), `ProfileAnswer` (screener-answer reuse cache).
- Phase 5 adds: `Notification`, `CalendarEvent`, additional `EmailClassification` values.
- Phase 6 adds: `JobEmbedding`, KPI materialization tables.

### I · Sample data hooks (anchor for plan 07)

Plan 07 (sample data) populates the model with hardcoded fixtures. Anchors:

- 1 `User` (Shyam) + 1 `Profile`
- 4 `Experience` rows (Intuit, Plaid, ...) + 14 `Bullet` rows across them
- 3 `Skill` groups, 2 `Education`, 4 `Project`, 1 `Certification`
- ~20 `Job` rows (mix of `unswiped / saved / skipped / queued / applied`)
- ~12 `Application` rows distributed across the 5 status values + closed bucket; mix of `docs_state`, `referral_state`, `recruiter_state` to stress-test UI rendering
- ~20 `Contact` rows + ~25 `ContactApplicationLink` rows
- ~40 `OutreachMessage` rows across timeline
- ~20 `EmailThread` rows for the email-signal feed
- ~150 `AppEvent` rows for realistic timeline density
- ~30 `GeneratedDocument` rows (one per submitted Application)
- ~20 `ApplicationScreenerAnswer` rows distributed across submitted Applications (1–3 per app; mix of `source=drafted` requiring review, `source=auto` filled from Profile, and `source=user` already-answered)
- 0 `ATSCredential` rows (sample data has no live login state; Phase 1 self-host instances bootstrap credentials on first auto-apply attempt)
- 1 `Settings` singleton (Anthropic Claude selected, auto-apply OFF)

Plan 07 expands these counts and writes the actual fixture data.

### J · Custom screener questions vs canonical EEO

The Profile carries **canonical EEO/visa fields as flat columns** (10 standardized fields, fixed taxonomy) — these are the questions every US board asks. Filled once at onboarding/profile-edit, auto-injected into every application bundle.

**Custom screener questions** — those whose wording or topic varies per JD ("Why Stripe?", "Are you OK with on-call?", "Years of Kafka experience?", "Salary expectation in CAD for our Toronto office?") — live as **`ApplicationScreenerAnswer`** rows on the Application, not on Profile. Sketch:

```python
class ApplicationScreenerAnswer(SQLModel, table=True):
    __tablename__ = "application_screener_answer"

    id: int = Field(primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    question_text: str                                  # exact wording captured from JD/board
    question_fingerprint: str = Field(index=True)       # normalized hash for Phase 2+ reuse cache
    question_type: ScreenerQuestionType
    choices: Optional[list[str]] = Field(default=None, sa_column=Column(ARRAY(String)))
    required: bool = Field(default=True)
    order_index: int = Field(default=0)                 # preserves ATS form order

    answer: Optional[str] = None                        # final answer (None until user reviews drafted)
    source: ScreenerAnswerSource = Field(default=ScreenerAnswerSource.DRAFTED)
    drafted_by_model: Optional[str] = None              # e.g. "claude-3.5-sonnet-20250219"
    reviewed_at: Optional[datetime] = None              # null until user clicks "ok" on drafted answer

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    application: "Application" = Relationship(back_populates="screener_answers")
```

**Lifecycle:**

1. **Capture.** During `/discover/:id` review, the JD scraper extracts screener questions from the application form (or known board taxonomies) and creates `ApplicationScreenerAnswer` rows with `source=drafted` (or `source=auto` for trivial Profile lookups like `earliest_start`, `salary_expectation`, `notice_period_days`).
2. **Draft.** `document_generator.answer_screeners(job, profile)` (plan 04 § J) populates `answer` for `drafted` rows from Profile + JD context; sets `drafted_by_model`.
3. **Review.** UI renders them in the Discover · review & apply right column with `drafted` chip; clicking through sets `reviewed_at`. Submit blocks until all required `drafted` rows are reviewed (`reviewed_at IS NOT NULL`).
4. **Submit.** Bundle includes the answers; ATS adapter posts them per board (plan 04 § K).
5. **Persist.** Rows live forever on the Application for audit + Phase 2+ reuse-cache lookups.

**Phase 2+ reuse cache.** When the same `question_fingerprint` appears on a future application, the prior `answer` is offered as a starting point (not auto-filled). Fingerprint = lowercase + strip punctuation + remove company name + stem. Implemented as a `ProfileAnswer` table keyed by `(user_id, question_fingerprint)`. Phase 1 punts on this — users re-draft each time; the cost of re-drafting is one LLM call per question.

**What does NOT live on Profile:** anything per-job, anything with variable wording, anything that needs human judgement per application (e.g. "Tell us about a time you failed"). Those stay on `ApplicationScreenerAnswer`.

**What DOES live on Profile** (the 10 canonical fields): work_authorization, visa_sponsorship_needed, willing_to_relocate, notice_period_days, salary_expectation_usd, earliest_start, veteran_status, disability_status, race_ethnicity, gender_identity. These have stable taxonomies and are reused on every application — flat columns are the right shape.

### K · ATS adapter scope (plan 04 owns)

ATS adapter logic — submission strategy per board, login flows, captcha handling, resume-parsing overrides — is **plan 04 (BACKEND.md) territory**, not plan 05's. Plan 05 owns only the **persistence shape**:

- **`Application.submission_artifacts: JSONB`** (added in § C above) — opaque-to-the-DB blob written by ATS adapters. Holds `{board_application_id, retry_count, last_failure: {kind, message, captured_at}, captcha_screenshot_path, field_mismatch_log}` etc. Naavik never queries by its contents; the adapter reads it for retry decisions and the UI reads it for "view error details" links.
- **`Application.board: ApplicationBoard`** — already in § C. Adapter dispatch key.
- **`ATSCredential`** (entity #18) — DB row metadata only:

```python
class ATSCredential(SQLModel, table=True):
    __tablename__ = "ats_credential"
    __table_args__ = (UniqueConstraint("user_id", "board"),)

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    board: ApplicationBoard
    has_credential: bool = Field(default=False)         # true once the encrypted vault has the secret
    login_status: AtsLoginStatus = Field(default=AtsLoginStatus.NOT_CONFIGURED)
    last_login_at: Optional[datetime] = None
    last_failure_kind: Optional[str] = None             # "captcha" / "auth_required" / etc. from SubmissionResult
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

Secret material (cookies, tokens, 2FA backups) lives in the encrypted on-disk vault per § H. The DB row tells the UI whether to show "connected" / "reconnect" / "set up" / "locked".

**What lives in plan 04, NOT here:**

- The 7 ATS adapters (Greenhouse / Lever / Ashby / Workday / LinkedIn / Indeed / Generic) and their submission strategies.
- `SubmissionResult` taxonomy (`ok / captcha / rate_limit / auth_required / field_mismatch / unknown`) and the failure-classified retry policy.
- Resume-parsing override logic for upload-and-auto-extract boards (Workday): the adapter posts canonical Profile fields explicitly rather than relying on the board's PDF parser. Naavik does not "trust" a board's resume-parser output.
- Per-board login flows, 2FA handling, credential rotation, captcha-fallback to manual review queue.

Cross-reference: see plan 04 § F (services), § J (`document_generator.answer_screeners`), § K (ATS submission per board), § L (board adapters per source). Both plans graduate together; the DATA_MODEL.md and BACKEND.md design docs reference each other on these axes.

## Open questions

> **Locked 2026-04-30** — all "My recommendation:" answers below are now binding decisions per user review. Implementation follows them verbatim unless a future plan revisits the call. Two new questions (#10, #11) added during review of screener / ATS scope.

1. **`User` vs `Profile` split** — keep as two tables (proposed; auth concerns live on User, biographical on Profile) or merge? My recommendation: **keep split** — auth changes are common; profile changes shouldn't trigger auth-table writes.
2. **Single-user MVP** — `user_id` on every table is overkill for a single-user instance but trivial to add now and painful to retrofit later. My recommendation: **keep `user_id` everywhere from day 1**; multi-user is Phase 2+.
3. **`Job.queue_state` vs separate "swipe action" table** — putting `queue_state` directly on `Job` keeps queries simple (one join). Separate table allows multiple historical states. My recommendation: **on `Job`** for Phase 1; capture history via `AppEvent` if/when needed.
4. **`outreach_engagement` computed vs cached** — recompute on every read (simple, slow on large data sets) or cache in a column (fast, requires invalidation). My recommendation: **computed on demand for Phase 1**; cache in Phase 4+ when row count grows.
5. **EEO/visa fields directly on `Profile` vs separate `ApplicationQuestions` table** — flat columns on Profile (proposed; simple, fits the "11 fields, 1 user, mostly null" reality) vs a child table (cleaner if multi-region support is added). My recommendation: **flat on Profile** — multi-region (i.e. UK/EU questions) gets a separate child table when added.
6. **Soft delete vs hard delete** — for Bullets, Contacts, Applications. My recommendation: **soft delete** (`deleted_at` nullable timestamp) for all user-authored entities; hard delete only for Settings test rows and ephemeral state.
7. **`AppEvent` polymorphism** — single `AppEvent` table with `kind` enum + `payload JSONB` (proposed; flexible) or per-event-type child tables (rigid, more queryable). My recommendation: **single table with JSONB payload** — Phase 1 reads are by application_id + occurred_at, not by payload contents.
8. **Pgvector readiness** — Phase 6 adds embeddings. Should the initial migration enable the `vector` extension or wait until Phase 6? My recommendation: **enable in initial migration** (Postgres extension is cheap; lets future migrations add the table without re-touching the extension).
9. **Constraint enforcement** — Postgres CHECK constraints (DB-enforced, harder to evolve) vs Pydantic/service-layer validators (Python-enforced, easier to evolve, can drift from DB). My recommendation: **service-layer** for transitions; **DB CHECK** for invariants (`closed_reason NOT NULL WHEN status=CLOSED`, `salary_min <= salary_max`).

10. **Screener answer reuse cache (Phase 2+)** — `ProfileAnswer` table keyed by `question_fingerprint` lets users skip re-drafting the same question across applications. Tradeoff: small storage + small UX win vs. extra service-layer complexity. My recommendation: **defer to Phase 2+**. Phase 1 re-drafts each time; cost is one LLM call per question, well under the cost of getting the abstraction wrong.

11. **ATS credential storage** — DB row only carries metadata; secret material (cookies, tokens, 2FA backups) lives in `~/.naavik/secrets.enc`. Tradeoff: requires the vault layer to ship in Phase 1.x alongside the first auto-apply pipeline. My recommendation: **vault-on-disk**, consistent with API key boundary in AGENTS.md. The vault layer is small (one file, AES-256-GCM, master key from runtime keyring or passphrase); shipping it before the first board adapter is the cleanest path.

## Approval checklist

- [x] Lifecycle modeling principle (§ A) — multi-axis, cohesive, exactly the axes from plan 02; canonical EEO vs custom screener boundary called out.
- [x] Entity inventory (§ B) — 18 entities + 1 settings singleton; ApplicationScreenerAnswer and ATSCredential added during review.
- [x] Sample model definitions (§ C) — Profile, Bullet, Application show the format works; Application now carries `submission_artifacts` for ATS adapter return state; the rest follow same shape.
- [x] Enum tables (§ D) — every enum exhaustive for Phase 1; ScreenerQuestionType, ScreenerAnswerSource, AtsLoginStatus added.
- [x] State transitions (§ E) — five state machines; service-layer enforcement.
- [x] KPI derivations (§ F) — cross-axis computations spelled out.
- [x] Indexes (§ G) — covers the hot query paths; revisit when row counts grow.
- [x] Migration strategy (§ H) — single initial migration; subsequent additive; secrets boundary explicit (DB never holds secret material).
- [x] Sample data hooks (§ I) — anchors for plan 07; ApplicationScreenerAnswer counts added.
- [x] Custom screener vs canonical EEO (§ J) — full ApplicationScreenerAnswer model + lifecycle + reuse-cache deferral to Phase 2+.
- [x] ATS adapter scope (§ K) — plan 05 owns persistence; plan 04 owns adapter logic; ATSCredential model + secrets boundary spelled out.
- [x] Open questions (1–11) — locked in; #10 (reuse cache deferral) and #11 (vault-on-disk) added during review.
- [x] After approval: graduates verbatim to `docs/design/DATA_MODEL.md` (with all 18 model definitions filled in to the format § C / § J / § K demonstrate). Plan is archived. Plan 07 (sample data) and plan 10 (backend impl) consume this directly.
