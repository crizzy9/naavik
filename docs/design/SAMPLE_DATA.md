# Naavik Sample Data

> **Last updated:** 2026-04-30
> **Status:** Canonical — graduated from `docs/plans/07-sample-data.md` (archived).
> **Scope:** Phase 1 hardcoded fixtures stored as a Python module (`src/db/sample_data.py`). Page handlers import directly so the UI renders before the backend lands; the same module powers the eventual seed migration via `src/db/seed.py`.
> **Companion docs:** `DESIGN.md` (visual contract), `docs/design/SCREENS.md` (functional contract), `docs/design/DATA_MODEL.md` (entity definitions and state axes).

---

## A · Storage approach + file layout

**Single Python module:** `src/db/sample_data.py`. Frozen Pydantic models (the same SQLModel classes from DATA_MODEL.md, instantiated with `model_config = {"frozen": True}` at the fixture layer) so handlers get real type-checked objects with the same shape they'll get from SQLAlchemy queries later.

```
src/db/
├── sample_data.py        ← canonical Phase 1 fixtures
├── seed.py               ← imports sample_data + INSERTs into DB at first migration
└── session.py            ← AsyncSession factory
```

**Why one module, not per-entity files:**

- Cross-entity references (Application → Job, AppEvent → Application, OutreachMessage → Contact + Job) are easier to keep consistent in one place.
- Total content is ~1500 lines of data — readable without a multi-file dance.
- Refactoring to per-entity files later is mechanical; the inverse is not.

**Why frozen Pydantic models, not dicts or YAML:**

- Type checker catches drift between sample_data.py and DATA_MODEL.md.
- Handlers consume the same object shape they'll consume post-DB.
- IDE goto-def works.
- No serialization overhead at import time.

**Module shape:**

```python
# src/db/sample_data.py
"""Phase 1 hardcoded fixtures — the canonical sample dataset.

Imported by page handlers (plan 09) to render the UI before the backend lands.
Imported by db/seed.py (plan 10 Wave 6) to populate the first migration.

Owner profile, sample companies, and bullet inventory are anchored to AGENTS.md
§ Owner Profile and DESIGN.md § Sample Content — keep in sync.
"""

from datetime import datetime, timedelta, UTC
from src.models import (
    Profile, Experience, Bullet, Skill, Education, Project, Certification,
    Job, Application, Contact, ContactApplicationLink, OutreachMessage,
    EmailThread, AppEvent, GeneratedDocument, ApplicationScreenerAnswer,
    ATSCredential, Settings, User,
)
from src.models.enums import (
    Tag, ApplicationStatus, ClosedReason, DocsState, ReferralState,
    RecruiterState, JobQueueState, ScreenerAnswerSource, ScreenerQuestionType,
    OutreachStatus, OutreachIntent, ContactType, EmailClassification,
    AppEventKind, ApplicationBoard, WorkAuthorization, VisaSponsorship,
    VeteranStatus, DisabilityStatus, Race, Gender, RelocateOpenness,
)

# ── Anchor date: every relative timestamp computed from this so the UI
#    "{N} days ago" labels stay coherent regardless of when the file is read.
TODAY = datetime(2026, 4, 30, 14, 0, 0, tzinfo=UTC)

# ── Identity ───────────────────────────────────────────────────────────────
USER: User = User(...)
PROFILE: Profile = Profile(...)

# ── Resume substrate ───────────────────────────────────────────────────────
EXPERIENCES: list[Experience] = [...]   # 4 roles
BULLETS: list[Bullet] = [...]           # 14 across roles
SKILLS: list[Skill] = [...]             # ~6 grouped categories
EDUCATIONS: list[Education] = [...]     # 2
PROJECTS: list[Project] = [...]         # 4
CERTIFICATIONS: list[Certification] = [...]  # 1

# ── Discovery + applications ───────────────────────────────────────────────
JOBS: list[Job] = [...]                 # ~20, mix of queue_states
APPLICATIONS: list[Application] = [...] # 14, mix of status × sub-states (incl. 2 DRAFT)

# ── Outreach + email ───────────────────────────────────────────────────────
CONTACTS: list[Contact] = [...]                              # ~20
CONTACT_APPLICATION_LINKS: list[ContactApplicationLink] = [...]  # ~25
OUTREACH_MESSAGES: list[OutreachMessage] = [...]             # ~40
EMAIL_THREADS: list[EmailThread] = [...]                     # ~20

# ── Timeline + artifacts ───────────────────────────────────────────────────
APP_EVENTS: list[AppEvent] = [...]                           # ~150
GENERATED_DOCUMENTS: list[GeneratedDocument] = [...]         # ~30
SCREENER_ANSWERS: list[ApplicationScreenerAnswer] = [...]    # ~20

# ── Config ─────────────────────────────────────────────────────────────────
ATS_CREDENTIALS: list[ATSCredential] = []                    # 0 in fixtures
SETTINGS: Settings = Settings(...)                           # 1 singleton

# ── Accessor helpers (§ M) ─────────────────────────────────────────────────
def by_id(...): ...
def applications_in_followup_state(): ...
def discover_queue(): ...
# ... etc
```

---

## B · Owner profile (Shyam Padia)

Anchored to `AGENTS.md` § Owner Profile + the visa rule in `CLAUDE.md`. One `User` row + one `Profile` row.

```python
USER = User(
    id=1,
    email="shyam.padia930@gmail.com",
    password_hash="$2b$12$...",  # placeholder; real seed has bcrypt of dev password
    created_at=TODAY - timedelta(days=120),
)

PROFILE = Profile(
    id=1,
    user_id=1,

    # Identity
    full_name="Shyam Padia",
    headline="Senior Software Engineer",
    current_company="Intuit",
    location="San Francisco, CA",
    email="shyam.padia930@gmail.com",
    phone="+1 (415) 555-0142",
    portfolio_url="https://crypticsoul.dev",
    github_handle="crizzy9",
    linkedin_handle="shyampadia",
    open_to_opportunities=True,

    # Summary
    summary_full=(
        "Senior software engineer with 8+ years building ML-driven personalization, "
        "marketing-tech, and platform systems at scale. At Intuit owns the personalization "
        "stack across QuickBooks and TurboTax; before that built risk and onboarding "
        "infrastructure at Plaid. Comfortable across the full stack — Python and Go on "
        "the backend, PyTorch and Airflow for ML, and the discipline to write clean "
        "frontends in TypeScript / React when the product needs it. H1B visa, i-140 pending."
    ),
    summary_short=(
        "Senior SWE — ML personalization at Intuit. 8+ yrs across personalization, "
        "marketing, and platform. Open to senior IC + EM roles requiring sponsorship."
    ),

    # Application questions (10 canonical EEO/visa fields, all populated)
    work_authorization=WorkAuthorization.H1B,
    visa_sponsorship_needed=VisaSponsorship.NEEDED_NOW,
    willing_to_relocate=RelocateOpenness.OPEN_TO_LIST,  # SF, Seattle, NYC
    notice_period_days=30,
    salary_expectation_usd=290_000,
    earliest_start=TODAY + timedelta(days=45),
    veteran_status=VeteranStatus.NOT_VETERAN,
    disability_status=DisabilityStatus.NO,
    race_ethnicity=Race.ASIAN,
    gender_identity=Gender.MALE,

    # Cover letter base — placeholder paragraph dict
    cover_letter_base={
        "intro": "I'm a senior software engineer with eight years of...",
        "close": "I'd love to hear how the team thinks about...",
    },

    created_at=TODAY - timedelta(days=120),
    updated_at=TODAY - timedelta(days=2),
)
```

**Visa rule honored:** `work_authorization=H1B` + `visa_sponsorship_needed=NEEDED_NOW` means the scoring service automatically zeros any job with `visa_restrictions = "us_citizen_only"` or `"green_card_required"` per CLAUDE.md scoring rule.

---

## C · Experience + Bullet inventory (4 roles, 14 bullets)

Four roles spanning 8 years, in reverse chronological order. Bullets are the **single long-form** version per DATA_MODEL.md — AI trims at apply time.

| # | Company | Title | Team | Dates | Bullets |
|---|---|---|---|---|---|
| 1 | Intuit | Senior Software Engineer | Personalization / Marketing Tech | 2020-09 → present (5y 8mo) | 5 |
| 2 | Plaid | Software Engineer II | Risk & Onboarding Platform | 2018-07 → 2020-08 (2y 2mo) | 4 |
| 3 | Capital One | Software Engineer | Anti-Fraud ML | 2017-08 → 2018-06 (11mo) | 3 |
| 4 | Northeastern (Co-op / RA) | Research Assistant | NLP Lab | 2016-01 → 2017-05 (1y 5mo) | 2 |

**Tag distribution across the 14 bullets:**

| Tag | Bullets tagged |
|---|---|
| `ai-ml` | 6 |
| `backend` | 8 |
| `platform` | 5 |
| `data-eng` | 4 |
| `genai` | 2 (Intuit only — recent work) |
| `leadership` | 3 |
| `frontend` | 1 (Plaid onboarding flow) |
| `devops` | 2 |
| `product` | 4 |

(Tags are per-bullet; each bullet carries 2-3 tags average. Distribution chosen to exercise the JD-match scoring's sensitivity across the full vocabulary.)

**Selection override mix:**

- 1 bullet `selection_override=ALWAYS_INCLUDE` — the headline Intuit lift bullet (the $4.2M one — every tailored resume should include it)
- 1 bullet `selection_override=NEVER_INCLUDE` — an early Capital One internship bullet (kept for context but doesn't ship to employers)
- 12 bullets `selection_override=None` (AI auto-decides per JD)

**Sample bullet** (the headline Intuit one — anchored to DESIGN.md § Sample Content):

```python
Bullet(
    id=1,
    experience_id=1,  # Intuit
    order_index=0,
    text=(
        "Built and shipped Intuit's ML personalization platform from prototype to "
        "production, serving 100M+ users across QuickBooks and TurboTax surfaces. "
        "Owned the full stack — feature pipelines in Airflow, ranking models in "
        "PyTorch, online inference in Go. Lifted homepage CTR by 23% and recovered "
        "an estimated $4.2M in annual revenue based on lift-tested A/B reads."
    ),
    tags=[Tag.AI_ML, Tag.PLATFORM, Tag.PRODUCT],
    selection_override=BulletSelectionOverride.ALWAYS_INCLUDE,
    edited_at=TODAY - timedelta(days=15),
    created_at=TODAY - timedelta(days=120),
    updated_at=TODAY - timedelta(days=15),
)
```

The remaining 13 bullets follow the same pattern, drawn from the existing OnePage/FullProfile resume artifacts.

---

## D · Skills, Education, Projects, Certifications

**Skills — 6 grouped categories:**

| Category | Items |
|---|---|
| Languages | Python, Go, TypeScript, Java, SQL |
| ML / Data | PyTorch, scikit-learn, XGBoost, Airflow, Spark, dbt |
| Backend | FastAPI, gRPC, Kafka, PostgreSQL, Redis, Elasticsearch |
| Cloud / Infra | AWS (EKS, Lambda, RDS, S3), Terraform, Docker, Kubernetes |
| Frontend | React, Next.js, Tailwind, HTMX |
| Tooling | Git, GitHub Actions, Datadog, Sentry |

**Educations — 2:**

- MS Computer Science, Northeastern University (2015 – 2017), GPA 3.84 / 4.0
- BE Computer Engineering, University of Mumbai (2011 – 2015), CGPA 8.62 / 10

**Projects — 4** (anchored to crypticsoul.dev portfolio):

1. **Naavik** (this) — career automation platform, AGPL-3.0, self-hosted first
2. **Lumino** — personal homelab orchestration via NixOS modules
3. **Crypticsoul.dev** — portfolio site, Astro + Tailwind, deployed to Netlify
4. **`mlretain`** — open-source ML retention scoring lib, ~140 GitHub stars

**Certifications — 1:**

- AWS Certified Solutions Architect — Associate (2022)

---

## E · Job queue (~20 jobs)

Twenty jobs distributed across queue_states + score buckets:

| queue_state | count | typical scores | purpose |
|---|---|---|---|
| `unswiped` | 8 | 60–95 | Discover queue (default landing) |
| `saved` | 4 | 70–88 | "Saved for later · {N}" rail |
| `skipped` | 3 | 30–55 | history; not shown by default |
| `queued_for_auto_apply` | 2 | 87–93 | high-score, auto-apply pipeline (DRAFT applications attached; see § F) |
| `applied` | 3 | varies | flipped because Application row exists; sample of historical apps |

**Companies** (per DESIGN.md § Sample Content + a few extras for variety): Stripe, Anthropic, Plaid, Linear, Notion, Figma, Ramp, Discord, Snowflake, Airbnb, Databricks, Vercel, Zed Industries, Mercury, Stable, Replicate, Modal, Cresta, Sourcegraph, Cohere.

**Coverage rules (every variant exercised at least once):**

- 2 jobs with `visa_restrictions = us_citizen_only` → score forced to 0 (visa filter test)
- 3 jobs from each major board: Greenhouse, Lever, Ashby (so adapter dispatch is exercised)
- 2 jobs from Workday (the upload-and-auto-extract path)
- 2 jobs from LinkedIn Easy Apply (rate-limited path)
- 1 manually-added job (`source = MANUAL`, board = `MANUAL`)
- 4 jobs with `team` populated (e.g. "Atlas", "Search", "Onboarding"); 16 with `team = None`
- Mix of remote / hybrid / onsite per `location` field

**Sample job** (the headline Discover card from SCREENS.md § 7):

```python
Job(
    id=101,
    user_id=1,
    source=JobSource.AUTOMATED,
    url="https://stripe.com/jobs/listing/senior-ml-engineer-atlas/5894273",
    url_type="ats",
    board=ApplicationBoard.GREENHOUSE,
    company="Stripe",
    role="Senior ML Engineer",
    team="Atlas",
    location="San Francisco, CA · Hybrid",
    posted_at=TODAY - timedelta(hours=2),
    found_at=TODAY - timedelta(hours=1, minutes=15),
    description="...",  # full JD text, ~2KB
    criteria=["5+ years ML experience", "Python fluency", "production ML systems"],
    skills_required=["Python", "PyTorch", "distributed systems"],
    visa_restrictions="sponsorship_available",
    salary_min=240_000,
    salary_max=290_000,
    equity_pct=0.05,
    score=0.86,
    score_explanation="Strong ai-ml + platform alignment; visa sponsorship available...",
    match_breakdown={
        Tag.AI_ML: 0.95,
        Tag.PLATFORM: 0.88,
        Tag.LEADERSHIP: 0.82,
        Tag.BACKEND: 0.79,
    },
    queue_state=JobQueueState.UNSWIPED,
    tags=[Tag.AI_ML, Tag.PLATFORM, Tag.BACKEND],
    warm_intro_contact_id=None,  # populated for the Linear and Anthropic jobs
    created_at=TODAY - timedelta(hours=1, minutes=15),
    updated_at=TODAY - timedelta(hours=1),
)
```

Two jobs (Linear, Anthropic) carry `warm_intro_contact_id` pointing into CONTACTS so the warm-intro pill renders on Discover · review.

---

## F · Application pipeline (14 applications)

Fourteen applications distributed across all 6 status values (DRAFT + 5 visible) + closed bucket. Each carries a coherent multi-axis state combination — the table below is the canonical mix:

| # | Company | Role | status | closed_reason | docs_state | referral_state | recruiter_state | applied_at | Why included |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Figma | Staff Backend | OFFER | — | ready | provided | responded | -28d | Overview "respond to offer" priority action |
| 2 | Anthropic | Senior ML | ONSITE_LOOP | — | ready | provided | responded | -21d | warm-intro success path; final round next week |
| 3 | Stripe | Senior ML (Atlas) | RECRUITER_SCREEN | — | ready | requested | engaged | -3d | post-submission, recruiter just reached out |
| 4 | Linear | Founding Engineer | RECRUITER_SCREEN | — | ready | provided | silent | -10d | silent for 6 days → "needs followup" |
| 5 | Notion | Senior Backend | APPLIED | — | ready | none | none | -7d | recently applied, no response yet |
| 6 | Plaid | Staff Engineer | APPLIED | — | ready | requested | none | -5d | referral requested, awaiting confirmation |
| 7 | Ramp | Eng Manager | RECRUITER_SCREEN | — | stale | none | responded | -14d | bullets edited after generation; docs need re-tailor |
| 8 | Discord | Senior Backend | ONSITE_LOOP | — | ready | none | responded | -32d | onsite scheduled in 3 days |
| 9 | Snowflake | Senior ML | CLOSED | rejected_by_them | ready | none | responded | -45d | typical rejection after recruiter screen |
| 10 | Airbnb | Senior Backend | CLOSED | ghosted | ready | none | silent | -60d | silent → ghosted; default-hidden in Tracking |
| 11 | Databricks | Founding Engineer | CLOSED | withdrawn_by_me | ready | none | responded | -50d | user withdrew (compensation gap) |
| 12 | Cresta | Senior ML | APPLIED | — | failed | none | none | -1d | Typst compile error on resume gen; needs retry |
| **13** | **Mercury** | **Senior Backend** | **DRAFT** | — | **ready** | none | none | (none — not submitted) | **manual review-and-apply in flight** — user opened /discover/:id, generated bundle, hasn't clicked Submit yet |
| **14** | **Modal** | **Founding Engineer** | **DRAFT** | — | **ready** | none | none | (none — not submitted) | **auto-apply queued** — user right-swiped on Discover; Job.queue_state=queued_for_auto_apply; cron will submit on next run |

Applications #13 and #14 exercise the DRAFT status surface — they have `applied_at = None`, `status = DRAFT`, fully generated `docs_state = ready`. Tracking hides them by default; Discover · review & apply (for #13) and the auto-apply queue card on Discover (for #14) surface them. Per DESIGN.md v1.3 / SCREENS.md "Tracking visibility rule", neither shows in the Kanban board / List view by default.

Application #12 (`docs_state=failed`) intentionally exercises the failed-doc-generation surface in Discover · review & apply ("Couldn't compile resume — see logs").

**Each Application carries:**

- `submission_artifacts: JSONB` populated for boards that returned an `external_id` on successful submit (~7 of 12 submitted; see DATA_MODEL.md § C / § K). Empty `{}` for the manual one, the failed one, and both DRAFT applications.
- `notes` populated for ~4 of them with realistic recruiter-prep notes
- `board` matches the Job's board (or `MANUAL` for the one manually-tracked app)

---

## G · Contacts + ContactApplicationLink (~20 + ~25)

**Contacts (20):** mix of types per ContactType enum. **All names are fictional but realistic-sounding** — no real LinkedIn folks.

| Type | count | examples |
|---|---|---|
| `RECRUITER` | 8 | Anthropic recruiter, Stripe recruiter, Notion sourcer, Discord recruiter… |
| `EMPLOYEE` | 7 | mutual connections at Linear, Plaid, Anthropic (the warm-intro path) |
| `HIRING_MANAGER` | 3 | Figma EM (the offer one), Linear founding-team manager, Snowflake director |
| `HR` | 2 | Figma offer-paperwork HR, Anthropic onsite-coordinator |

**ContactApplicationLinks (25):** many-to-many between contacts and applications. Distribution:

- Most applications have 1–2 contacts (the recruiter + maybe the EM)
- Anthropic has 4 contacts (warm-intro source + recruiter + onsite coordinator + EM)
- Figma has 3 (recruiter + EM + HR)
- Some contacts span multiple applications (a recurring recruiter, the warm-intro friend who's referred to two companies)

Each link carries `referral_state` per DATA_MODEL.md (the application-side referral_state is **derived** from the strongest link — `provided` if any link is provided, else `in_flight` if any is, etc.).

**Sample contact** (the warm-intro friend at Anthropic):

```python
Contact(
    id=201,
    user_id=1,
    type=ContactType.EMPLOYEE,
    name="Priya Subramanian",
    title="Staff Research Engineer",
    company="Anthropic",
    linkedin_url="https://linkedin.com/in/priyasubramanian",
    linkedin_id="priyasubramanian",
    email=None,  # outreach via LinkedIn DM
    relationship="warm",
    source="manual",  # added by user via Outreach search
    notes="Northeastern grad school. Strong advocate. Has referred 4 hires this year.",
    last_touch_at=TODAY - timedelta(days=3),
    degree="1st",
    created_at=TODAY - timedelta(days=200),
    updated_at=TODAY - timedelta(days=3),
)
```

---

## H · OutreachMessage + EmailThread (~40 + ~20)

**OutreachMessages (40):** sent across LinkedIn DM (most) + email (some). Distribution:

| status | count | purpose |
|---|---|---|
| `DRAFT` | 4 | currently-drafting messages on Outreach |
| `QUEUED` | 3 | rate-limited; sending in N minutes |
| `SENT` | 18 | sent, no reply yet |
| `OPENED` | 5 | LinkedIn opened-receipt fired (LinkedIn DM only) |
| `REPLIED` | 8 | conversation in progress |
| `BOUNCED` | 2 | wrong email / LinkedIn deactivated |

(OutreachMessage.status enum is independent of Application.status — outreach messages have their own DRAFT meaning ≠ Application DRAFT status.)

**Intent mix:**

- `INTRO` — 12 (initial reach-outs)
- `REFERRAL_REQUEST` — 8 (warm-intro asks)
- `FOLLOW_UP` — 14 (the "no reply in 5 days, check in" pattern)
- `THANK_YOU` — 4 (post-screen / post-onsite)
- `CHECK_IN` — 2 (longer-cycle "are you back from PTO" follow-ups)

**EmailThreads (20):** auto-classified email threads anchored to Applications. Distribution per `EmailClassification`:

- `INTERVIEW_REQUEST` — 5 (Recruiter Screen → Onsite scheduling, etc.)
- `REJECTION` — 4 (rejection emails — corresponds to the 4 CLOSED applications + 1 in-flight rejection)
- `OFFER` — 1 (the Figma offer)
- `ASSESSMENT` — 2 (take-home assignments)
- `FOLLOW_UP` — 5 (in-flight back-and-forth)
- `OTHER` — 3 (general updates, scheduling logistics)

Each EmailThread has 2–6 messages; `manually_verified=True` on ~5 of the 20 (the rest classified by AI without user override).

---

## I · AppEvent timeline (~150)

One hundred fifty AppEvents span the 14 Applications, distributed by event kind:

| kind | count | typical density |
|---|---|---|
| `STATUS_CHANGE` | 32 | 2–3 per submitted application; 1 per DRAFT (initial creation) |
| `DOCS_GENERATED` | 14 | 1 per application (one for Cresta retry shows DOCS_FAILED instead) |
| `DOCS_FAILED` | 2 | Cresta initial + a Workday one for variety |
| `EMAIL_RECEIVED` | 35 | 2–4 per submitted application; drives the email-signal feed |
| `EMAIL_SENT` | 18 | user replies to recruiters |
| `LINKEDIN_DM_SENT` | 22 | matches OutreachMessage `SENT` status |
| `LINKEDIN_DM_REPLIED` | 10 | matches OutreachMessage `REPLIED` status |
| `REFERRAL_REQUESTED` | 4 | per ContactApplicationLink with that state |
| `REFERRAL_PROVIDED` | 3 | the successful referrals (Anthropic, Linear, Figma) |
| `INTERVIEW_SCHEDULED` | 8 | one per onsite-loop / recruiter-screen application |
| `NOTE_ADDED` | 6 | user-added notes |

**Each AppEvent's `payload JSONB`** carries kind-specific keys per DATA_MODEL.md schemas:

- `EMAIL_RECEIVED.payload` → `{thread_id, sender, subject_preview, classification, urgent}`
- `STATUS_CHANGE.payload` → `{from_status, to_status, triggered_by: "manual" | "auto-from-email" | "ats_callback" | "draft_creation" | "draft_submitted"}`
- `DOCS_GENERATED.payload` → `{generated_document_id, model, cost_usd, token_count, page_count}`

Timeline density gives Tracking application detail and Outreach contact rows realistic activity.

---

## J · GeneratedDocument (~30)

Thirty documents — accounting for:

- 1 resume + 1 cover letter per application that has `docs_state=ready` (12 apps × 2 = 24, including the 2 DRAFT apps which have generated bundles)
- 1 retry pair for the Ramp `stale` application (it has the original + a regenerated set = 4 total)
- 1 retry pair for Cresta on the second attempt (the `failed` one will retry; sample assumes 1 success after retry = 2 total)

**Each row carries:**

- `path` — relative path under `~/.naavik/data/documents/{app_id}/{kind}.pdf`
- `compiled_at` — when Typst finished
- `bullet_selection JSONB` — which bullet IDs were selected + their AI-trimmed text (the apply-time artifact)
- `cost_usd` and `token_count` — from the LLM cost tracker
- `model` — e.g. `claude-3.5-sonnet-20250219`
- `byte_size` — for the UI to show file size

**No actual PDF binary in fixtures.** The path points to a placeholder PDF generated once by the dev orchestrator (`nix run .#dev` populates `.naavik/data/documents/sample/onepage.pdf` with a real Typst-compiled output of the OnePage template against the sample profile). UI links work end-to-end without requiring fixture-time compilation.

---

## K · ApplicationScreenerAnswer (~20)

Twenty rows distributed across submitted + DRAFT applications. Per DATA_MODEL.md § J each carries `question_text`, `question_fingerprint`, `question_type`, `choices`, `answer`, `source`, `drafted_by_model`, `reviewed_at`.

**Distribution:**

| source | count | review state |
|---|---|---|
| `auto` | 6 | always reviewed (auto-fills from Profile — earliest_start, salary_expectation, notice_period, work_authorization, visa_sponsorship_needed, willing_to_relocate) |
| `drafted` | 10 | 7 reviewed, 3 unreviewed (the unreviewed ones surface the "blocked from submit" UI on apps still in workflow — including Mercury DRAFT #13) |
| `user` | 4 | always reviewed (user-typed) |

**Question variety:**

- "Why are you interested in {company}?" (TEXTAREA, drafted) — 6 instances across companies
- "Are you authorized to work in the US?" (SINGLE_SELECT, auto) — 6 instances
- "Are you OK with on-call rotation?" (SINGLE_SELECT, drafted) — 3
- "Years of {tech} experience?" (NUMERIC, drafted) — 2
- "Earliest start date?" (DATE, auto) — covered above
- "Tell us about a time you failed" (TEXTAREA, user) — 1 (Cresta — user-typed)
- "Salary expectation in CAD" (NUMERIC, drafted) — 1 (one of the Toronto-flagged jobs)

`drafted_by_model` populated with `claude-3.5-sonnet-20250219` for all DRAFTED rows.

---

## L · Settings singleton

```python
SETTINGS = Settings(
    user_id=1,
    llm_provider=LLMProvider.ANTHROPIC,  # default per AGENTS.md
    llm_model="claude-3.5-sonnet-20250219",
    llm_api_key_fingerprint="sha256:abc123...",  # metadata only; real key in vault
    auto_apply_enabled=False,                     # default OFF per ROADMAP.md
    auto_apply_score_threshold=0.85,
    auto_apply_daily_cap=None,                    # unlimited
    discord_webhook_url=None,
    telegram_bot_token=None,
    portfolio_webhook_url="https://api.netlify.com/build_hooks/redacted",
    deployment_mode=DeploymentMode.SELF_HOSTED,
    deployment_version="0.4.2",
    notifications_enabled={
        "new_high_score_job": True,
        "application_sent": True,
        "interview_scheduled": True,
        "offer_received": True,
        "rejection": False,
    },
    sources_enabled={
        "linkedin": True,
        "workday": True,
        "greenhouse": True,
        "lever": True,
        "ashby": True,
        "indeed": False,
        "rss": True,
    },
    created_at=TODAY - timedelta(days=120),
    updated_at=TODAY - timedelta(days=2),
)
```

**No secret material.** `llm_api_key_fingerprint` is a sha256 hash so the UI can show "key set" without holding the key. Real key lives in `~/.naavik/secrets.enc` per DATA_MODEL.md § H.

`ATSCredential` is empty (`[]`) per DATA_MODEL.md § I — sample data has no live login state.

---

## M · Loader / accessor pattern

Page handlers import named accessors, not raw lists. The accessors keep handlers free of LINQ-style filtering and centralize the fixture's "known" combinations.

```python
# src/db/sample_data.py — accessors at the bottom of the module

def by_id(items: list, item_id: int):
    """Find an entity by id, returning None if missing."""
    return next((i for i in items if i.id == item_id), None)

# ── Profile / resume substrate ────────────────────────────────────────────
def get_profile() -> Profile:
    return PROFILE

def get_experiences() -> list[Experience]:
    return list(EXPERIENCES)

def get_bullets_for_experience(experience_id: int) -> list[Bullet]:
    return [b for b in BULLETS if b.experience_id == experience_id]

# ── Discovery ─────────────────────────────────────────────────────────────
def discover_queue() -> list[Job]:
    """Unswiped jobs in score-desc order — the Discover page's main feed."""
    return sorted(
        [j for j in JOBS if j.queue_state == JobQueueState.UNSWIPED],
        key=lambda j: j.score, reverse=True,
    )

def saved_jobs() -> list[Job]:
    return [j for j in JOBS if j.queue_state == JobQueueState.SAVED]

def auto_apply_queue() -> list[Application]:
    """DRAFT applications attached to queued_for_auto_apply jobs — the Discover queue card."""
    return [a for a in APPLICATIONS if a.status == ApplicationStatus.DRAFT and a.job
            and a.job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY]

# ── Tracking ──────────────────────────────────────────────────────────────
def applications_visible_in_tracking() -> list[Application]:
    """Default Tracking view: APPLIED through OFFER. DRAFT and CLOSED hidden."""
    return [a for a in APPLICATIONS if a.status in {
        ApplicationStatus.APPLIED, ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP, ApplicationStatus.OFFER,
    }]

def applications_by_status(status: ApplicationStatus) -> list[Application]:
    return [a for a in APPLICATIONS if a.status == status]

def applications_in_followup_state() -> list[Application]:
    """Recruiter silent ≥3d OR outbound message unanswered ≥3d.
    Drives the Tracking 'needs followup' banner."""
    return [a for a in APPLICATIONS if a.recruiter_state in
            {RecruiterState.SILENT, RecruiterState.STALLED}]

def closed_applications() -> list[Application]:
    return [a for a in APPLICATIONS if a.status == ApplicationStatus.CLOSED]

def draft_applications() -> list[Application]:
    """Pre-submission applications. Hidden in Tracking by default; surfaced in Discover."""
    return [a for a in APPLICATIONS if a.status == ApplicationStatus.DRAFT]

# ── Outreach ──────────────────────────────────────────────────────────────
def contacts_for_company(company: str) -> list[Contact]:
    return [c for c in CONTACTS if c.company == company]

def outreach_messages_for_contact(contact_id: int) -> list[OutreachMessage]:
    return sorted(
        [m for m in OUTREACH_MESSAGES if m.contact_id == contact_id],
        key=lambda m: m.created_at, reverse=True,
    )

# ── Overview ──────────────────────────────────────────────────────────────
def priority_actions(limit: int = 8) -> list[dict]:
    """Synthesizes the Overview priority-action rows from applications + events.
    Returns ranked dicts with {kind, title, subtitle, urgency, cta_label, cta_url}."""
    # implementation pulls from APPLICATIONS + EMAIL_THREADS + APP_EVENTS
    pass

def kpi_response_rate_90d() -> float:
    """Cross-axis derivation per DATA_MODEL.md § F. DRAFT excluded."""
    cutoff = TODAY - timedelta(days=90)
    in_window = [a for a in APPLICATIONS
                 if a.status != ApplicationStatus.DRAFT
                 and a.applied_at and a.applied_at >= cutoff]
    engaged = [a for a in in_window if a.recruiter_state >= RecruiterState.ENGAGED]
    return len(engaged) / len(in_window) if in_window else 0.0

def kpi_active_applications() -> int:
    """Active = APPLIED through OFFER. Excludes DRAFT and CLOSED."""
    return len([a for a in APPLICATIONS if a.status in {
        ApplicationStatus.APPLIED, ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP, ApplicationStatus.OFFER,
    }])

def email_signal_feed(limit: int = 6) -> list[EmailThread]:
    """Most recent email signals — Overview right rail."""
    return sorted(EMAIL_THREADS, key=lambda t: t.latest_message_at, reverse=True)[:limit]
```

**Accessor naming convention:**

- `get_<entity>` — return a single item or singleton (Profile, Settings)
- `<plural>_for_<scope>` — filter by FK (`bullets_for_experience`, `contacts_for_company`)
- `<feature_specific_name>` — purpose-named for UI surfaces (`discover_queue`, `priority_actions`, `email_signal_feed`, `applications_in_followup_state`, `auto_apply_queue`, `draft_applications`)
- `kpi_<name>_<window>` — cross-axis KPI computations (mirrors DATA_MODEL.md § F)

Page handlers import accessors, not raw lists:

```python
# src/api/discover.py (Phase 1 sample-data version)
from src.db.sample_data import discover_queue, saved_jobs, auto_apply_queue, by_id, JOBS

@router.get("/discover", response_class=HTMLResponse)
async def get_discover(request: Request):
    queue = discover_queue()
    saved = saved_jobs()
    drafts = auto_apply_queue()  # DRAFT applications waiting in auto-apply
    return templates.TemplateResponse("pages/discover.html", {
        "request": request,
        "current_card": queue[0] if queue else None,
        "up_next": queue[1:5],
        "saved_count": len(saved),
        "auto_apply_drafts": drafts,
    })
```

---

## N · Realism rules

Rules every fixture must follow:

1. **Date anchoring.** Every timestamp computed from `TODAY = 2026-04-30 14:00 UTC`. Never use absolute past dates — they go stale. Relative offsets (`TODAY - timedelta(days=N)`) keep the UI's "{N} days ago" labels coherent regardless of when sample_data.py is read.
2. **Time zones.** All timestamps in UTC; UI does the local conversion (`PT` for the owner's location). Mockups show `09:14 PT` — the UI converts on render.
3. **Salary realism.** SF Bay Area senior IC range: $200–320k base, 0.04–0.10% equity. Manager / staff: $260–360k. Don't invent $500k unicorn comp.
4. **Visa filter coverage.** At least 2 jobs with `visa_restrictions = us_citizen_only` so the visa-filter test path is exercised. Both score 0.
5. **Score distribution.** The 8 unswiped jobs span score ranges 60–95 to exercise all four score-circle thresholds (≥80 emerald, 60–79 indigo, 40–59 amber, <40 rose) per DESIGN.md § Score circle.
6. **Recruiter silence stress test.** At least one application is `recruiter_state=silent` for 6+ days so the Overview "6D SILENT" rose urgency badge has data.
7. **Closed bucket size.** ≥3 CLOSED applications with mix of `closed_reason` (rejected_by_them, ghosted, withdrawn_by_me — at minimum). Tracking's "Show closed" toggle needs density.
8. **DRAFT coverage.** 2 DRAFT applications (#13 manual review-and-apply in flight, #14 auto-apply queued). Both have `docs_state=ready` and full screener-answer rows so the pre-submission UI surfaces have data.
9. **Realistic JD bodies.** Each Job's `description` field carries 1–3 paragraphs of plausible JD prose for the 5 most-rendered jobs (Stripe, Anthropic, Linear, Notion, Figma); short stubs for the rest.
10. **Owner data only — no fake user multiplexing.** Phase 1 is single-user MVP; every row's `user_id = 1`.
11. **Fictional contacts with realistic-sounding names.** Names like Priya Subramanian, Daniel Kim, Sarah Park — not real recruiters / employees from Shyam's LinkedIn. LinkedIn URLs use the synthetic handle.
12. **PDFs are placeholders.** GeneratedDocument paths point to a single dev-orchestrator-compiled placeholder PDF, not unique per-application binaries.
13. **`submission_artifacts` realism.** For applications submitted via Greenhouse / Lever / Ashby, `board_application_id` is a plausible 6–8 digit integer string. For Workday / LinkedIn, `board_application_id` is a UUID-ish string. For MANUAL or DRAFT, the field is `None`.
14. **CI round-trip test.** A `tests/test_sample_data.py` validates every fixture round-trips through Pydantic — fails CI if a model field is added in DATA_MODEL.md but missing in fixtures. Cheap insurance against drift.

---

## O · Worked sample (Anthropic application end-to-end)

To validate the format works, the sample below shows the Anthropic application with all related rows wired together. Every other application follows the same pattern.

```python
# Job (entered queue 21 days ago, applied 21 days ago)
JOBS.append(Job(
    id=104,
    user_id=1,
    source=JobSource.AUTOMATED,
    url="https://job-boards.greenhouse.io/anthropic/jobs/4123887",
    board=ApplicationBoard.GREENHOUSE,
    company="Anthropic",
    role="Senior ML Engineer",
    team="Inference Platform",
    location="San Francisco, CA · Hybrid",
    posted_at=TODAY - timedelta(days=22),
    found_at=TODAY - timedelta(days=21, hours=18),
    description="Anthropic is looking for...",
    visa_restrictions="sponsorship_available",
    salary_min=280_000, salary_max=340_000, equity_pct=0.07,
    score=0.92,
    score_explanation="Strong ai-ml + platform; warm intro available; visa sponsorship.",
    match_breakdown={Tag.AI_ML: 0.97, Tag.PLATFORM: 0.93, Tag.LEADERSHIP: 0.85},
    queue_state=JobQueueState.APPLIED,  # flipped when Application created with status=APPLIED
    tags=[Tag.AI_ML, Tag.PLATFORM, Tag.GENAI],
    warm_intro_contact_id=201,  # Priya
))

# Application (applied 21d ago, currently ONSITE_LOOP — never DRAFT, was a manual review-and-apply that successfully submitted)
APPLICATIONS.append(Application(
    id=12, user_id=1, job_id=104,
    company="Anthropic", role="Senior ML Engineer", team="Inference Platform",
    location="San Francisco, CA · Hybrid",
    salary_min=280_000, salary_max=340_000, equity_pct=0.07,
    applied_at=TODAY - timedelta(days=21),
    board=ApplicationBoard.GREENHOUSE,
    external_url="https://anthropic.com/jobs/applications/4123887/abc123",
    status=ApplicationStatus.ONSITE_LOOP,
    closed_reason=None,
    docs_state=DocsState.READY,
    referral_state=ReferralState.PROVIDED,
    recruiter_state=RecruiterState.RESPONDED,
    submission_artifacts={"board_application_id": "abc123def", "retry_count": 0},
    notes="Final round May 8. Prep: distributed inference, vLLM, batching tradeoffs.",
))

# ContactApplicationLink — Priya referred Shyam
CONTACT_APPLICATION_LINKS.append(ContactApplicationLink(
    id=308,
    application_id=12,
    contact_id=201,  # Priya
    referral_state=ReferralState.PROVIDED,
    introduced_at=TODAY - timedelta(days=22),
))

# Three OutreachMessages for the Anthropic flow:
OUTREACH_MESSAGES.extend([
    OutreachMessage(id=520, user_id=1, contact_id=201, application_id=12,
                    intent=OutreachIntent.REFERRAL_REQUEST,
                    body="Hey Priya, hope you're doing well...",
                    status=OutreachStatus.REPLIED,
                    sent_at=TODAY - timedelta(days=23),
                    replied_at=TODAY - timedelta(days=22, hours=4)),
    OutreachMessage(id=521, user_id=1, contact_id=201, application_id=12,
                    intent=OutreachIntent.THANK_YOU,
                    body="Priya — wanted to thank you for the referral...",
                    status=OutreachStatus.SENT,
                    sent_at=TODAY - timedelta(days=20)),
    OutreachMessage(id=522, user_id=1, contact_id=205, application_id=12,
                    intent=OutreachIntent.FOLLOW_UP,
                    body="Hi Sarah, looking forward to next week's onsite...",
                    status=OutreachStatus.SENT,
                    sent_at=TODAY - timedelta(days=2)),
])

# Two EmailThreads (recruiter screen scheduling + onsite scheduling)
EMAIL_THREADS.extend([
    EmailThread(id=412, user_id=1, application_id=12, contact_id=204,
                subject="Re: Senior ML Engineer @ Anthropic",
                classification=EmailClassification.INTERVIEW_REQUEST,
                latest_message_at=TODAY - timedelta(days=18),
                manually_verified=True,
                messages=[...]),  # 4 messages
    EmailThread(id=413, user_id=1, application_id=12, contact_id=205,
                subject="Anthropic onsite — May 8",
                classification=EmailClassification.INTERVIEW_REQUEST,
                latest_message_at=TODAY - timedelta(days=2),
                manually_verified=False,
                messages=[...]),  # 6 messages
])

# AppEvents — chronological timeline (~14 events for this single application)
APP_EVENTS.extend([
    AppEvent(application_id=12, kind=AppEventKind.LINKEDIN_DM_SENT,
             occurred_at=TODAY - timedelta(days=23), payload={"contact_id": 201, ...}),
    AppEvent(application_id=12, kind=AppEventKind.REFERRAL_REQUESTED,
             occurred_at=TODAY - timedelta(days=23), payload={"contact_id": 201}),
    AppEvent(application_id=12, kind=AppEventKind.REFERRAL_PROVIDED,
             occurred_at=TODAY - timedelta(days=22, hours=4), payload={"contact_id": 201}),
    AppEvent(application_id=12, kind=AppEventKind.STATUS_CHANGE,
             occurred_at=TODAY - timedelta(days=21, hours=3),
             payload={"from_status": None, "to_status": "DRAFT",
                      "triggered_by": "draft_creation"}),
    AppEvent(application_id=12, kind=AppEventKind.DOCS_GENERATED,
             occurred_at=TODAY - timedelta(days=21, hours=2),
             payload={"generated_document_id": 712, "model": "claude-3.5-sonnet-20250219",
                      "cost_usd": 0.04, "token_count": 1822, "page_count": 1}),
    AppEvent(application_id=12, kind=AppEventKind.STATUS_CHANGE,
             occurred_at=TODAY - timedelta(days=21),
             payload={"from_status": "DRAFT", "to_status": "APPLIED",
                      "triggered_by": "draft_submitted"}),
    AppEvent(application_id=12, kind=AppEventKind.EMAIL_RECEIVED,
             occurred_at=TODAY - timedelta(days=18),
             payload={"thread_id": 412, "sender": "anthropic-recruiter@...",
                      "classification": "interview_request"}),
    AppEvent(application_id=12, kind=AppEventKind.STATUS_CHANGE,
             occurred_at=TODAY - timedelta(days=18),
             payload={"from_status": "APPLIED", "to_status": "RECRUITER_SCREEN",
                      "triggered_by": "auto-from-email"}),
    # ... 7 more events through onsite scheduling
])

# GeneratedDocuments (resume + cover letter)
GENERATED_DOCUMENTS.extend([
    GeneratedDocument(id=712, application_id=12, kind="resume",
                      path="~/.naavik/data/documents/12/resume.pdf",
                      compiled_at=TODAY - timedelta(days=21, hours=2),
                      bullet_selection={"selected_ids": [1, 3, 5, 7, 8, 11],
                                         "trimmed_lines": {"1": "Built Intuit's ML personalization platform; +23% homepage CTR / $4.2M revenue", ...}},
                      cost_usd=0.04, token_count=1822, model="claude-3.5-sonnet-20250219",
                      byte_size=87234),
    GeneratedDocument(id=713, application_id=12, kind="cover_letter",
                      path="~/.naavik/data/documents/12/cover-letter.pdf",
                      compiled_at=TODAY - timedelta(days=21, hours=2),
                      cost_usd=0.03, token_count=1421, model="claude-3.5-sonnet-20250219",
                      byte_size=64511),
])

# ApplicationScreenerAnswers (3 screener questions for Anthropic)
SCREENER_ANSWERS.extend([
    ApplicationScreenerAnswer(id=801, application_id=12,
        question_text="Why are you interested in Anthropic?",
        question_fingerprint="why-interested-company",
        question_type=ScreenerQuestionType.TEXTAREA,
        answer="The opportunity to work on inference infrastructure for frontier models...",
        source=ScreenerAnswerSource.DRAFTED,
        drafted_by_model="claude-3.5-sonnet-20250219",
        reviewed_at=TODAY - timedelta(days=21, hours=1)),
    ApplicationScreenerAnswer(id=802, application_id=12,
        question_text="Are you authorized to work in the US?",
        question_fingerprint="us-work-authorization",
        question_type=ScreenerQuestionType.SINGLE_SELECT,
        choices=["Yes — US citizen / GC", "Yes — visa sponsored", "No"],
        answer="Yes — visa sponsored",
        source=ScreenerAnswerSource.AUTO,
        reviewed_at=TODAY - timedelta(days=21, hours=1)),
    ApplicationScreenerAnswer(id=803, application_id=12,
        question_text="Earliest start date?",
        question_fingerprint="earliest-start-date",
        question_type=ScreenerQuestionType.DATE,
        answer="2026-06-15",
        source=ScreenerAnswerSource.AUTO,
        reviewed_at=TODAY - timedelta(days=21, hours=1)),
])
```

This single Anthropic application generates: 1 Job, 1 Application (with full DRAFT → APPLIED → RECRUITER_SCREEN → ONSITE_LOOP transition history in AppEvents), 1 ContactApplicationLink (to Priya), 3 OutreachMessages, 2 EmailThreads, ~14 AppEvents, 2 GeneratedDocuments (resume + cover letter), 3 ApplicationScreenerAnswers.

Across all 14 applications, totals naturally land at the targets in § F–§ K.
