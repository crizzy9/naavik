# Naavik — Entity-Relationship Diagram

> **Authored:** 2026-05-25 (plan 89 / 0.7.0.48 Wave 2 item 6 — owner-requested visual data model review)
> **Source of truth:** `src/models/**.py` SQLModel definitions (this doc is a mermaid render of those)
> **Complement, not replacement:** `docs/design/DATA_MODEL.md` is the field-level + state-transition reference; this doc is the visual + critique surface
> **Render hint:** mermaid blocks below render inline in GitHub markdown — view via the PR diff or `gh pr view 212 --web`

---

## Index

27 SQLModel tables split across 6 domains:

1. **Auth & Identity** — `User`, `Settings`, `RevokedJwt`, `Tenant`, `TenantSigningKey`
2. **Profile** — `Profile`, `Experience`, `Bullet`, `Skill`, `Education`, `Project`, `Certification`, `ProfileEmbedding`, `ProfileAnswer`
3. **Jobs & Scraping** — `Job`, `JobEmbedding`, `JobScrapeRun`
4. **Applications & Documents** — `Application`, `GeneratedDocument`, `ApplicationScreenerAnswer`, `ATSCredential`, `AppEvent`
5. **Contacts & Outreach** — `Contact`, `ContactApplicationLink`, `OutreachMessage`, `EmailThread`
6. **Observability** — `ApiUsage`

Cardinality glyphs (mermaid): `||--o{` one-to-many, `||--||` one-to-one, `||--o|` one-to-zero-or-one, `}o--o|` many-to-zero-or-one.

Owner cuts to the chase: jump to [§ Observations / open questions](#observations--open-questions) — the architect's critique with actionable suggestions.

---

## 1 · Auth & Identity

```mermaid
erDiagram
    User ||--o| Settings : "has 1"
    User ||--o| Profile : "has 1"
    User ||--o{ RevokedJwt : "rotates jti to"
    Tenant ||--o{ TenantSigningKey : "owns N keys"

    User {
        int id PK
        string email UK "RFC 5322"
        string password_hash "bcrypt cost=12"
        bool is_active
        bool is_admin "VESTIGIAL — see Obs 1"
        bool must_change_password "PC.6 forced-rotation"
        datetime created_at
        datetime updated_at
        datetime last_login_at
        datetime deleted_at "soft delete"
    }

    Settings {
        int user_id PK "FK → User.id (1:1)"
        enum llm_provider "ANTHROPIC|OPENAI|OLLAMA"
        string llm_model
        bool auto_apply_enabled
        float auto_apply_score_threshold
        json auto_apply_per_board_daily_caps
        bool eager_review_generation
        float daily_llm_cost_cap_usd
        float notify_threshold
        json notifications_enabled
        json sources_enabled
        json source_schedules
        array workday_companies
        array linkedin_keywords
        string linkedin_location
        json consecutive_scrape_failures
        json scraper_rate_limits
        bool semantic_match_enabled
        string embedding_provider
        float semantic_match_threshold
        json score_per_dim_weights
        int jwt_rotation_days
        int jwt_rotation_grace_days
        enum deployment_mode "SELF_HOSTED|CLOUD"
        bool allow_multiple_users "DEPRECATED — see Obs 2"
        bool debug
        datetime created_at
        datetime updated_at
    }

    RevokedJwt {
        int id PK
        string jti UK
        int user_id FK
        datetime revoked_at
        datetime expires_at
    }

    Tenant {
        int id PK
        string name UK "self-hosted=1 row"
        datetime created_at
    }

    TenantSigningKey {
        int id PK
        int tenant_id FK
        string kid UK
        enum algorithm "HS256|RS256|EdDSA"
        enum status "ACTIVE|RETIRING|RETIRED"
        text public_key_pem "nullable"
        text private_key_pem "nullable / HS256 secret"
        datetime created_at
        datetime activated_at
        datetime retired_at
    }
```

**Notes:**
- `User.id` is the FK target for every per-user-scoped row in the whole schema.
- `Settings` is keyed by `user_id` directly (not its own `id` PK), enforcing 1:1.
- `TenantSigningKey` is **NOT** scoped to `User` — it's scoped to `Tenant`. On self-host there's one `Tenant` row (`id=1, name='self-hosted'`), but the indirection is there for future multi-tenant blast-radius isolation (per plan 62 / 0.2.7.07).

---

## 2 · Profile

```mermaid
erDiagram
    User ||--o| Profile : "has 1"
    User ||--o| ProfileEmbedding : "1 dense vector"
    User ||--o{ ProfileAnswer : "screener-reuse cache"
    Profile ||--o{ Experience : "N roles"
    Profile ||--o{ Skill : "N categories"
    Profile ||--o{ Education : "N schools"
    Profile ||--o{ Project : "N projects"
    Profile ||--o{ Certification : "N certs"
    Experience ||--o{ Bullet : "N bullets"
    ApplicationScreenerAnswer ||--o{ ProfileAnswer : "source-of-answer"

    Profile {
        int id PK
        int user_id FK "UK 1:1 → User"
        string full_name
        string headline
        string current_company
        string location
        string email "denormalized from User"
        string phone
        string portfolio_url
        string github_handle
        string linkedin_handle
        bool open_to_opportunities
        text summary_full
        text summary_short
        enum work_authorization "US_CITIZEN|GREEN_CARD|H1B|..."
        enum visa_sponsorship_needed "NOT_NEEDED|NEEDED_NOW|..."
        enum willing_to_relocate
        int notice_period_days
        int salary_expectation_usd
        datetime earliest_start
        enum veteran_status
        enum disability_status
        enum race_ethnicity
        enum gender_identity
        json cover_letter_base
        json score_history "per-role-family 30d trends"
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    Experience {
        int id PK
        int profile_id FK
        string company
        string title
        string team
        string location
        datetime start_date
        datetime end_date
        int order_index
        text summary_short
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    Bullet {
        int id PK
        int experience_id FK
        int order_index
        text text "single long-form; AI trims at apply time"
        array tags "9-tag vocab — see Obs 6"
        enum selection_override "ALWAYS|NEVER|null"
        datetime edited_at
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    Skill {
        int id PK
        int profile_id FK
        string category
        array items
        int order_index
        datetime created_at
        datetime updated_at
    }

    Education {
        int id PK
        int profile_id FK
        string institution "e.g. Northeastern University"
        string school "e.g. Khoury College — see Obs 7"
        string location
        string degree
        datetime start_date
        datetime end_date
        string gpa
        array courses
        int order_index
        datetime created_at
        datetime updated_at
    }

    Project {
        int id PK
        int profile_id FK
        string title
        datetime date
        text text
        array tags
        string portfolio_slug
        string link
        int order_index
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    Certification {
        int id PK
        int profile_id FK
        string title
        string issuer
        datetime date
        text description
        int order_index
        datetime created_at
        datetime updated_at
    }

    ProfileEmbedding {
        int user_id PK "FK → User (1:1)"
        vector embedding "768d pgvector"
        string model "provider/model@dim"
        int dim
        string content_hash "SHA-1 invalidation"
        datetime created_at
        datetime updated_at
    }

    ProfileAnswer {
        int id PK
        int user_id FK
        string question_fingerprint "SHA-1 normalized"
        text question_text_sample
        text answer
        int source_screener_answer_id FK "→ ApplicationScreenerAnswer"
        int times_offered
        int times_accepted
        datetime last_used_at
        datetime created_at
        datetime updated_at
    }
```

**Notes:**
- `Profile.email` duplicates `User.email`. Per `DATA_MODEL.md`, intentional denormalization for resume rendering (Profile is the resume contract).
- `Bullet.text` is single-field long-form — AI trims at apply time. `tags` use a closed 9-value vocab (AI_ML, BACKEND, FRONTEND, DEVOPS, DATA_ENG, GENAI, LEADERSHIP, PLATFORM, PRODUCT) but the column is `array<string>` not `array<enum>`. See Obs 6.
- `ProfileAnswer.source_screener_answer_id` FKs back into `ApplicationScreenerAnswer` — that's the only profile-domain row with a cross-domain FK.

---

## 3 · Jobs & Scraping

```mermaid
erDiagram
    User ||--o{ Job : "scoped to"
    User ||--o{ JobScrapeRun : "scoped to"
    User ||--o{ JobEmbedding : "scoped to"
    Job ||--o| JobEmbedding : "1 dense vector"
    Job }o--o| JobScrapeRun : "last touched by"
    Job }o--o| Job : "duplicate_of (self-FK, tier-3 dedup)"
    Job }o--o| Contact : "warm_intro_contact_id"

    Job {
        int id PK
        int user_id FK
        enum source "LINKEDIN|WORKDAY|GREENHOUSE|LEVER|ASHBY|INDEED|COMPANY_DIRECT|RSSHUB|N8N_LEGACY|MANUAL"
        enum board "ApplicationBoard"
        string external_id "per-source stable ID"
        string url
        string url_type
        string company "DENORMALIZED — see Obs 5"
        string role
        string team
        string location
        enum remote_policy "REMOTE|HYBRID|ONSITE|UNKNOWN"
        enum seniority_level "ENTRY|MID|SENIOR|STAFF|PRINCIPAL|EXEC|UNKNOWN"
        datetime posted_at
        string posted_at_text
        datetime found_at
        text description
        text description_html
        datetime description_extracted_at
        string description_extraction_model
        array criteria
        array skills_required
        enum visa_restrictions "US_CITIZEN_ONLY|GREEN_CARD_REQUIRED|SPONSORSHIP_AVAILABLE|NOT_MENTIONED"
        int salary_min
        int salary_max
        float equity_pct
        float score "0.0 to 1.0"
        text score_explanation
        json match_breakdown "tag → score map"
        enum queue_state "UNSWIPED|SAVED|SKIPPED|QUEUED_FOR_AUTO_APPLY|APPLIED"
        array tags
        int warm_intro_contact_id FK "→ Contact"
        int last_scrape_run_id FK "→ JobScrapeRun"
        int duplicate_of_id FK "→ Job (self-FK)"
        json raw_meta
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    JobScrapeRun {
        int id PK
        int user_id FK
        enum source "JobSource"
        enum status "RUNNING|SUCCESS|PARTIAL|FAILED|TIMED_OUT"
        string triggered_by "cron|manual|test|migration"
        datetime started_at
        datetime finished_at
        int requests_made
        int listings_returned
        int new_jobs
        int updated_jobs
        array errors
        int duration_ms
        json raw_meta
        datetime created_at
    }

    JobEmbedding {
        int job_id PK "FK → Job (1:1)"
        int user_id FK
        vector embedding "768d pgvector"
        string model "provider/model@dim"
        int dim
        string content_hash "SHA-1 of title||desc"
        datetime created_at
        datetime updated_at
    }
```

**Notes:**
- Primary dedup constraint: partial-unique index on `(user_id, source, external_id) WHERE deleted_at IS NULL`. The `duplicate_of_id` self-FK is tier-3 fuzzy dedup (per plan 34 / 0.2.0.09).
- `JobEmbedding.user_id` is **redundant with `Job.user_id`** — kept as a denormalized index for fast per-user vector search (plan 61 decision D5).
- `Job.warm_intro_contact_id` is the only direct Job → Contact FK; the rest of the application-contact graph flows via `ContactApplicationLink`.

---

## 4 · Applications, Documents, Events

```mermaid
erDiagram
    User ||--o{ Application : "owns N"
    User ||--o{ ATSCredential : "1 per board (max 8)"
    User ||--o{ AppEvent : "owns N"
    Job ||--o{ Application : "applied to"
    Application ||--o{ GeneratedDocument : "resume + cover PDFs"
    Application ||--o{ ApplicationScreenerAnswer : "N screener Qs"
    Application ||--o{ AppEvent : "N timeline events"

    Application {
        int id PK
        int user_id FK
        int job_id FK "nullable — manual entries"
        string company "DENORMALIZED from Job — resilient to mutation"
        string role
        string team
        string location
        int salary_min
        int salary_max
        float equity_pct
        datetime applied_at "nullable for DRAFT"
        enum board "ApplicationBoard"
        string external_url
        enum status "DRAFT|APPLIED|RECRUITER_SCREEN|ONSITE_LOOP|OFFER|CLOSED"
        enum closed_reason "REJECTED_BY_THEM|WITHDRAWN|GHOSTED|ACCEPTED_OTHER|USER_ARCHIVED"
        enum docs_state "NONE|GENERATING|READY|STALE|FAILED"
        enum referral_state "NONE|REQUESTED|IN_FLIGHT|PROVIDED|DECLINED — ROLLED UP from link"
        enum recruiter_state "NONE|ENGAGED|RESPONDED|SILENT|STALLED"
        json submission_artifacts
        json generation_trace "audit trail for bundle gen"
        text notes
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    GeneratedDocument {
        int id PK
        int application_id FK
        enum kind "RESUME|COVER_LETTER"
        string path "on disk"
        int byte_size
        int page_count
        datetime compiled_at
        string model
        float cost_usd
        int token_count
        text error
        json bullet_selection "which bullets included"
        datetime created_at
        datetime updated_at
    }

    ApplicationScreenerAnswer {
        int id PK
        int application_id FK
        text question_text
        string question_fingerprint
        enum question_type "TEXTAREA|SHORT_TEXT|SINGLE_SELECT|MULTI_SELECT|DATE|NUMERIC|FILE"
        array choices
        bool required
        int order_index
        text answer
        enum source "USER|DRAFTED|AUTO"
        string drafted_by_model
        datetime reviewed_at
        datetime created_at
        datetime updated_at
    }

    ATSCredential {
        int id PK
        int user_id FK
        enum board "ApplicationBoard"
        bool has_credential "metadata only — values in env"
        enum login_status "NOT_CONFIGURED|OK|EXPIRED|LOCKED"
        datetime last_login_at
        string last_failure_kind
        datetime created_at
        datetime updated_at
    }

    AppEvent {
        int id PK
        int user_id FK
        int application_id FK "nullable for user-scoped events"
        enum kind "STATUS_CHANGE|DOCS_GENERATED|EMAIL_RECEIVED|...|AUTO_APPLY_VISA_BLOCKED (14 kinds)"
        datetime occurred_at
        json payload "discriminated union per kind"
        string actor
        datetime created_at
    }
```

**Notes:**
- `Application` denormalizes 5 identifying fields from `Job` (`company`, `role`, `team`, `location`, `salary_*`). Intentional — Job can mutate; the Application snapshot is what you applied to.
- `Application.referral_state` is a **service-layer rollup** of all `ContactApplicationLink.referral_state` rows for the same application; not directly stored as the source of truth. See `application_service._roll_up_referral_state`.
- `AppEvent.payload` is JSONB but shaped per `AppEventKind` via Pydantic discriminated union in `app_event_payloads.py` (14 payload classes; opaque to Postgres, typed in Python).
- `ATSCredential.has_credential` is metadata — actual secret material lives in `.env` since plan 26 (vault sunset).

---

## 5 · Contacts & Outreach

```mermaid
erDiagram
    User ||--o{ Contact : "owns N"
    User ||--o{ OutreachMessage : "owns N"
    User ||--o{ EmailThread : "owns N"
    Contact ||--o{ ContactApplicationLink : "N apps"
    Application ||--o{ ContactApplicationLink : "N contacts"
    Contact ||--o{ OutreachMessage : "N messages"
    Application }o--o| OutreachMessage : "optional anchor"
    Application }o--o{ EmailThread : "N threads"
    Contact }o--o{ EmailThread : "N threads"

    Contact {
        int id PK
        int user_id FK
        enum type "RECRUITER|EMPLOYEE|HIRING_MANAGER|HR"
        string name
        string title
        string company "DENORMALIZED — see Obs 5"
        string linkedin_url
        string linkedin_id "unique per user when set"
        string linkedin_degree
        string email "no uniqueness — see model comment"
        string relationship
        string source
        text notes
        datetime last_touch_at
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    ContactApplicationLink {
        int id PK
        int application_id FK
        int contact_id FK
        enum referral_state "NONE|REQUESTED|IN_FLIGHT|PROVIDED|DECLINED"
        datetime introduced_at
        text notes
        datetime created_at
        datetime updated_at
    }

    OutreachMessage {
        int id PK
        int user_id FK
        int contact_id FK
        int application_id FK "nullable"
        enum intent "INTRO|REFERRAL_REQUEST|FOLLOW_UP|THANK_YOU|CHECK_IN"
        string channel
        string subject
        text body
        enum status "DRAFT|QUEUED|SENT|OPENED|REPLIED|BOUNCED"
        datetime sent_at
        datetime opened_at
        datetime replied_at
        text response_summary
        bool ai_generated
        bool human_edited
        string drafted_by_model
        string linkedin_message_id
        datetime created_at
        datetime updated_at
        datetime deleted_at
    }

    EmailThread {
        int id PK
        int user_id FK
        int application_id FK "nullable"
        int contact_id FK "nullable"
        string provider "gmail|outlook|imap"
        string thread_id_external "unique per (user, provider)"
        string subject
        enum classification "INTERVIEW_REQUEST|REJECTION|OFFER|ASSESSMENT|FOLLOW_UP|OTHER"
        bool auto_classified
        bool manually_verified
        datetime latest_message_at
        int message_count
        json messages "list of msg dicts — see Obs 8"
        datetime created_at
        datetime updated_at
    }
```

**Notes:**
- `ContactApplicationLink` is the canonical many-to-many. Per-link `referral_state` is source of truth; `Application.referral_state` is the service-layer rollup.
- `EmailThread.messages` stores the full message list as JSONB (no separate `EmailMessage` table). DATA_MODEL.md flags this as "Phase 2+ may promote to a separate `EmailMessage` table." See Obs 8.

---

## 6 · Observability

```mermaid
erDiagram
    User ||--o{ ApiUsage : "owns N (per LLM call)"
    Application }o--o| ApiUsage : "optional attribution"

    ApiUsage {
        int id PK
        int user_id FK
        int application_id FK "nullable — non-app calls"
        enum provider "ANTHROPIC|OPENAI|OLLAMA"
        string model
        string method "complete|structured|stream"
        string prompt_name
        int input_tokens
        int output_tokens
        float cost_usd
        int latency_ms
        bool succeeded
        string error_kind
        datetime occurred_at
        datetime created_at
    }
```

**Notes:**
- Every LLM call routes through `services/llm_tracker.tracked_call(...)` which writes one `ApiUsage` row. Powers the daily cost cap + Settings · LLM cost cards.
- `application_id` is nullable for non-application LLM work (resume parse, embeddings, scoring without a draft).

---

## 7 · External (not SQLModel — for context)

The schema also touches a few non-model surfaces relevant to the data model:

- **APScheduler jobstore tables** — `apscheduler_jobs` is created by APScheduler itself (alembic doesn't manage it). Lives in the same Postgres DB; opaque to Naavik's models.
- **pgvector extension** — backs `JobEmbedding.embedding` and `ProfileEmbedding.embedding` (both `vector(768)`).
- **Alembic migrations** — 22 migration files (`migrations/versions/0001` through `0022`) — head is `0022_closed_reason_user_archived`. Schema changes flow through alembic, not SQLModel autogen alone.

---

## Observations / open questions

Architect's lens applied to the data model. Each item is **actionable** — owner can pick which to file as `0.7.0.49+` follow-up rows or roll into a future cleanup plan.

### Obs 1 — `User.is_admin` is vestigial; remove the concept entirely (HIGH)

**Finding:** `is_admin` is set during signup (`is_first_user = existing_count == 0` → `User.is_admin=is_first_user`) and returned in the `/api/v1/auth/me` payload, but **no code path anywhere in `src/` gates on it.** No `if user.is_admin:` checks, no admin-only routes, no admin-scoped service operations. The owner's question in plan 89 W2 item 2 is correct: there are no admin-only operations in this app.

Plan 89 Wave 2 item 2 currently plans to "flip default to True; keep column for schema compat; drop in 0.7.0.49." That's the right transitional move. But the **stronger position** is: there is no concept of admin in a single-tenant self-hosted app where every user owns only their own data. The model invariant should be "all signed-up users are equal." Recommend:

1. **Now (this PR):** flip default to `True` as planned (column drop deferred to 0.7.0.49) — matches the plan.
2. **0.7.0.49 (next):** alembic migration to **DROP the column**, not just deprecate. Remove from `/api/v1/auth/me` response. Remove from `User` model.
3. **Future (if multi-tenant SaaS):** introduce a `Role` enum (`OWNER|MEMBER|VIEWER`) per **`Tenant`**, not per `User`. `is_admin` boolean was an MVP shortcut; even multi-tenant deserves better.

**Why this matters:** keeping vestigial fields is the leading cause of "this codebase feels confusing" — they signal capability that doesn't exist, and the next implementer wastes a half-day searching for the admin gate. The plan's "flip default" half-measure is correct for this PR's scope; commit to the full removal in 0.7.0.49.

### Obs 2 — `Settings.allow_multiple_users` should drop in same 0.7.0.49 (MEDIUM)

**Finding:** Already marked deprecated in `src/models/settings.py:196-200`. Field is no longer read by code (plan 89 W1 removed the signup gate). The column will sit in production DBs as a vestigial `boolean DEFAULT true` taking 1 byte/row × however many self-hosted instances. Trivial overhead, but **semantic noise**: a new contributor reads the model file and asks "is this a feature flag I can flip?"

**Recommendation:** Bundle this drop with the `is_admin` drop into one alembic migration in 0.7.0.49. Both are vestigial 1-byte booleans from the same MVP gating concept. A combined "remove single-user MVP vestiges" migration is cleaner than two separate ones.

### Obs 3 — Company is denormalized as a STRING across 3 tables; no `Company` entity (HIGH)

**Finding:** `Job.company`, `Application.company`, `Contact.company` are all free-form `string` columns. No FK to a `Company` table. Consequences:

- "Find all jobs at Stripe" — fuzzy string match (the existing GIN trigram index on `lower(company)` per plan 34 acknowledges this pain).
- "How many applications at company X" — depends on perfect string consistency across scrape runs ("Stripe" vs "Stripe Inc" vs "Stripe, Inc.").
- Contact relationships are weakened — "show me everyone I know at Stripe" needs the same fuzzy join.

**Recommendation (low-urgency but architecturally significant):** Introduce a `Company` entity in a Phase 2.5 or Phase 3 cleanup plan:

```
Company {
    id PK
    canonical_name (e.g. "Stripe")
    aliases array<string> (e.g. ["Stripe Inc", "Stripe, Inc."])
    website
    linkedin_url
    industry
    size_category
    created_at, updated_at
}
```

Then `Job.company_id FK`, `Application.company_id FK`, `Contact.company_id FK`. Keep the denormalized string columns for backward compat + display fallback; populate `*_id` lazily via a normalization service. This unlocks: per-company application history, "you have 3 contacts here" badge on Job cards, real warm-intro discovery, application-rate analytics by company.

**Cost:** ~2 weeks of design + migration. Worth a Phase 3 design plan, not a quick W2 follow-up.

### Obs 4 — `Tenant` + `TenantSigningKey` are over-engineered for the current single-tenant MVP (MEDIUM)

**Finding:** Plan 62 / 0.2.7.07 introduced JWT key rotation via a per-tenant signing-key table. The `Tenant` table exists with exactly one row (`id=1, name='self-hosted'`) on every self-host. `TenantSigningKey.tenant_id` always = 1. This is **forward-looking architecture** for multi-tenant SaaS that doesn't ship until Phase 0.8.x at earliest.

**Trade-off analysis:**

| Option | Pro | Con |
|---|---|---|
| Keep current (Tenant + TenantSigningKey) | Future-proof; one less migration when SaaS lands | Adds a JOIN to every JWT verification; 2 extra tables; conceptually confusing for self-hosters reading the schema |
| Collapse to `SigningKey` (drop Tenant, drop tenant_id FK) | Simpler; 1 fewer table; matches single-tenant reality | Pays migration cost twice — once now, once when SaaS lands |
| Status quo | (same as option 1) | (same as option 1) |

**Recommendation:** Keep status quo. The cost (1 JOIN on JWT verify, 1 fixed row in `tenant`) is trivial; the future migration cost is non-trivial. **But add a doc-line** in the `Tenant` model docstring stating that the table will stay 1-row until multi-tenant SaaS ships, so contributors don't try to "use" it for organization-scoping or similar shoehorns.

### Obs 5 — Profile and Settings could collapse, BUT shouldn't (LOW — design note)

**Finding:** Owner's hand-back mentioned this as a possible simplification. Worth addressing:

`Profile` and `Settings` are both 1:1 with `User`. Why not one row?

**Why they're correctly separate:**

1. **Different lifecycle.** `Profile` is the resume/CV contract — fields are PII (name, EEO, salary expectation). `Settings` is operator config — LLM provider, auto-apply toggles, cron schedules. Different update cadences, different review surfaces (Profile · Edit vs Settings).
2. **Different contributor.** Resume gets edited monthly; Settings gets touched at setup + rare ops changes.
3. **Different export.** `GET /api/portfolio/cv` (public, no auth) reads Profile, never Settings.
4. **Different validation.** Profile fields are user-facing (name regex, email RFC); Settings fields are operator-facing (URL validation, enum constraints).

**Recommendation:** keep them separate. The 1:1 relationship is the right shape — both are "extension tables on User" with different concerns.

### Obs 6 — `Bullet.tags` is `array<string>` but the vocab is closed 9 values (LOW)

**Finding:** `Tag` enum exists in `src/models/enums.py` with exactly 9 values (`AI_ML`, `BACKEND`, `FRONTEND`, `DEVOPS`, `DATA_ENG`, `GENAI`, `LEADERSHIP`, `PLATFORM`, `PRODUCT`). But `Bullet.tags: array<string>` accepts any string. Risk: typo-tags pollute the field (`backed`, `devp`).

**Recommendation:** In a quick cleanup row (`0.7.0.NN`), add a Pydantic validator in the API surface (`BulletCreate`/`BulletUpdate`) that constrains tags to the 9-value enum. Optionally add a `CHECK` constraint at the DB level (PG supports `CHECK (tags <@ ARRAY['ai-ml','backend',...])`). Same fix applies to `Project.tags` (also `array<string>`).

### Obs 7 — `Education.institution` AND `Education.school` columns both exist (LOW)

**Finding:** Both columns are present in `src/models/profile.py:208-209`. Both are rendered in `src/ui/templates/pages/profile.html:83` as `{{ e.institution }}{% if e.school %} · {{ e.school }}{% endif %}` (institution = "Northeastern University", school = "Khoury College of Computer Sciences"). So they ARE semantically distinct (institution = parent org, school = sub-division), but the naming is unhelpful and DATA_MODEL.md doesn't document the distinction.

**Recommendation:** Rename `school` → `department` (more universally meaningful) OR document the distinction inline in the model docstring. Cheap rename + alembic column rename + 1 template + 1 ctx-builder reference. File as `0.7.0.NN` cleanup.

### Obs 8 — `EmailThread.messages` as JSONB blob is a known smell (MEDIUM, deferred)

**Finding:** `EmailThread.messages: list = Field(sa_column=Column(JSONB, ...))` stores the full message list inline. DATA_MODEL.md already flags this as "Phase 2+ may promote to a separate `EmailMessage` table."

**Consequences right now:**
- Can't query individual messages (e.g. "find emails containing 'salary'" requires full JSONB scan).
- Can't link an individual message to an `AppEvent` (kind=`EMAIL_RECEIVED` payload references `message_id_external` as a string, not a FK).
- Thread row grows unbounded with reply chains.

**Recommendation:** This is correctly deferred. Phase 5 (Email Monitoring & Outreach) is the natural home for the `EmailMessage` table promotion. Don't pre-build it now. But add a note in DATA_MODEL.md § C.14 (EmailThread) tying the promotion to a specific Phase 5 task ID once Phase 5 plans materialize.

### Obs 9 — Soft-delete inconsistency (LOW)

**Finding:** `deleted_at` columns appear on `User`, `Profile`, `Experience`, `Bullet`, `Project`, `Job`, `Application`, `Contact`, `OutreachMessage`. But NOT on `Skill`, `Education`, `Certification`, `Settings`, `ATSCredential`, `GeneratedDocument`, `ApplicationScreenerAnswer`, `JobScrapeRun`, `JobEmbedding`, `ProfileEmbedding`, `ProfileAnswer`, `AppEvent`, `ApiUsage`, `EmailThread`, `ContactApplicationLink`, `RevokedJwt`, `Tenant`, `TenantSigningKey`.

`DATA_MODEL.md § C` says the rule is "soft-delete on user-authored entities; hard-delete on Settings test rows + ephemeral state." That mostly tracks, but: **why is `Skill` hard-delete when `Bullet` is soft-delete?** Both are user-authored Profile children. Same for `Education` (hard) vs `Project` (soft).

**Recommendation:** Either add `deleted_at` to `Skill` + `Education` + `Certification` for consistency, OR document why those three are intentionally hard-delete (e.g. "operator can re-add easily; no audit trail value"). The current mix is undocumented inconsistency.

### Obs 10 — `JobEmbedding.user_id` is redundant with `Job.user_id` (INFO)

**Finding:** `JobEmbedding` has both `job_id PK` (which already implies a `Job` row) and `user_id FK` (denormalized from `Job`). Plan 61 decision D5 justified this as a perf index for per-user vector search.

**Recommendation:** This is correct as designed. Mentioning for transparency only — owner reading the schema will notice the apparent duplication. Worth a one-line comment in the JobEmbedding docstring linking to plan 61 § D5.

### Obs 11 — Naming consistency check (INFO)

**Finding:** All table names are `snake_case` singular (`user`, `application`, `job_scrape_run`). All column names are `snake_case`. No camelCase leakage. Enum values are mixed: some `UPPER_SNAKE_CASE` (`DRAFT`, `APPLIED`, `RUNNING`), some `lower_snake_case` (`rejected_by_them`, `linkedin`, `greenhouse`).

**Recommendation:** The enum value casing inconsistency is real but **expensive to fix** — every enum value is a stored string in Postgres; flipping case is an alembic data migration per enum. Not worth chasing for cosmetic consistency. Document the pattern in DATA_MODEL.md § D so the next contributor knows: "STATUS-type enums use UPPER (DRAFT, APPLIED); SOURCE/CATEGORY-type enums use lower (linkedin, greenhouse)." That's actually a defensible pattern.

### Obs 12 — Multi-tenant readiness — `user_id` everywhere (INFO)

**Finding:** Every per-user table carries `user_id FK` directly. Cross-user data leak attack surface is "did the service layer remember to filter by user_id?" — this is exactly what 0.3.3.15 closed for the screener IDOR.

**Recommendation:** Already on the right track. The `tests/test_no_cross_user_embedding_reads.py` regression-lint pattern is good — extend it to assertion templates that flag any `select(<Model>)` without a `.where(<Model>.user_id == ...)` in service code. File as a 0.7.0.NN test-tooling improvement if useful.

---

## Footer

This ERD complements — does NOT replace — `docs/design/DATA_MODEL.md`. Cross-reference:

- **Field-level spec + state transitions + KPI derivations + sample row counts:** see DATA_MODEL.md § C–F.
- **Migration strategy (alembic head, autogen vs handwritten):** DATA_MODEL.md § H.
- **Enum vocabulary tables (full enum-to-int maps):** DATA_MODEL.md § D.
- **AppEvent payload schemas (per-kind Pydantic discriminated union):** DATA_MODEL.md § M + `src/models/app_event_payloads.py`.
- **Job model deep-dive (post plan-27 hardening):** `docs/design/JOB_MODEL.md`.
- **JWT rotation key lifecycle:** `docs/design/JWT_ROTATION.md` (if present) + plan 62 § B.1.

**Update cadence:** this doc is regenerated when significant model surgery lands (new entity, dropped column, new FK). Light field tweaks don't need a re-render — DATA_MODEL.md absorbs those. Re-render trigger phrases for future runs: "regenerate ERD," "update the entity diagram," "ERD is stale."
