"""Phase 1 hardcoded fixtures — the canonical sample dataset.

Imported by page handlers (plan 09) to render the UI before the backend lands.
Imported by db/seed.py (plan 10 Wave 4) to populate the first migration.

Owner profile, sample companies, and bullet inventory anchor to AGENTS.md
§ Owner Profile and DESIGN.md § Sample Content — keep in sync.

In-memory mutation: this module exposes a tiny mutable shim
(`_apply_status_override`, `_create_draft`, etc.) so stub endpoints can persist
across requests for the lifetime of the server process. Restart resets state.

All accessors are `async def` even though they read in-memory lists, so plan 10
Wave 4 can swap function bodies for DB queries without touching call sites.

═══════════════════════════════════════════════════════════════════════════
Wave 4 of plan 10 § B.10 introduces a `NAAVIK_PERSISTENCE` env var:

    NAAVIK_PERSISTENCE=memory  (default)  → read from in-memory lists below
    NAAVIK_PERSISTENCE=db                  → read from Postgres via SQLModel

In `db` mode, accessors create their own session via `db/session.py` and
return Pydantic *shadow* instances (`db.sample_data_models.*`). Page-handler
call sites stay unchanged — both modes return identical shape.

Wave 4 ships DB-mode bodies for the high-traffic read accessors: get_profile,
get_user, get_settings, get_experiences, get_bullets_for_experience, get_jobs,
get_job, discover_queue, get_applications, get_application,
applications_visible_in_tracking, etc.

Lower-traffic accessors (KPI computations, priority_actions, mutation shims)
keep memory-mode bodies even in `db` env until Wave 6 — they're annotated with
`# Wave 4 partial swap` comments. The `NAAVIK_PERSISTENCE` env var is removed
in a follow-up cleanup once full DB-mode coverage lands.
═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta

from db.sample_data_models import (
    ApiUsage,
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    ATSCredential,
    Bullet,
    Certification,
    Contact,
    ContactApplicationLink,
    Education,
    EmailThread,
    Experience,
    GeneratedDocument,
    Job,
    JobScrapeRun,
    OutreachMessage,
    Profile,
    Project,
    Settings,
    Skill,
    User,
)
from models.enums import (
    AppEventKind,
    ApplicationBoard,
    ApplicationStatus,
    BulletSelectionOverride,
    ClosedReason,
    ContactType,
    DeploymentMode,
    DisabilityStatus,
    DocsState,
    EmailClassification,
    Gender,
    GeneratedDocumentKind,
    JobQueueState,
    JobScrapeStatus,
    JobSource,
    LLMProvider,
    OutreachIntent,
    OutreachStatus,
    Race,
    RecruiterState,
    ReferralState,
    RelocateOpenness,
    RemotePolicy,
    ScreenerAnswerSource,
    ScreenerQuestionType,
    SeniorityLevel,
    Tag,
    VeteranStatus,
    VisaRestriction,
    VisaSponsorship,
    WorkAuthorization,
)

# ─────────────────────────────────────────────────────────────────────────
# Persistence mode (Wave 4)
# ─────────────────────────────────────────────────────────────────────────


def _persistence_mode() -> str:
    """`memory` (default) or `db`. Set via NAAVIK_PERSISTENCE env."""
    return os.environ.get("NAAVIK_PERSISTENCE", "memory").strip().lower()


def _is_db_mode() -> bool:
    return _persistence_mode() == "db"


async def _shadow_from_sql(sql_obj, shadow_cls):
    """Convert a SQLModel instance to its Pydantic shadow.

    SQLModel rows have the same field names as the shadows; `model_dump`
    surfaces the data, `model_validate` revalidates against the shadow class.
    """
    if sql_obj is None:
        return None
    return shadow_cls.model_validate(sql_obj.model_dump(mode="python"))


async def _shadow_list_from_sql(sql_objs, shadow_cls) -> list:
    return [shadow_cls.model_validate(o.model_dump(mode="python")) for o in sql_objs]


# ─────────────────────────────────────────────────────────────────────────
# Anchor date — every relative timestamp computes from this so the UI's
# "{N} days ago" labels stay coherent regardless of when sample_data.py is
# read. SAMPLE_DATA.md § N.1.
# ─────────────────────────────────────────────────────────────────────────
TODAY: datetime = datetime(2026, 4, 30, 14, 0, 0, tzinfo=UTC)


def _ago(*, days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    return TODAY - timedelta(days=days, hours=hours, minutes=minutes)


def _ahead(*, days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    return TODAY + timedelta(days=days, hours=hours, minutes=minutes)


# ─────────────────────────────────────────────────────────────────────────
# 1 · User + 1 Profile (Shyam Padia)
# ─────────────────────────────────────────────────────────────────────────

USER: User = User(
    id=1,
    email="shyam.padia930@gmail.com",
    # Plan 10b (item 3, 2026-05-03): password_hash is filled in at seed time
    # via `db.seed:_resolve_dev_password()` → `services.auth.hash_password()`.
    # The shadow row keeps an empty string here so the in-memory dataset is
    # self-consistent (no fake-but-decodable bcrypt that would invite mistakes).
    # Memory-mode auth never reads this field; DB-mode receives the real hash.
    password_hash="",
    is_active=True,
    is_admin=True,
    created_at=_ago(days=120),
    updated_at=_ago(days=2),
    last_login_at=_ago(hours=3),
)

PROFILE: Profile = Profile(
    id=1,
    user_id=1,
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
    work_authorization=WorkAuthorization.H1B,
    visa_sponsorship_needed=VisaSponsorship.NEEDED_NOW,
    willing_to_relocate=RelocateOpenness.OPEN_TO_LIST,
    notice_period_days=30,
    salary_expectation_usd=290_000,
    earliest_start=_ahead(days=45),
    veteran_status=VeteranStatus.NOT_VETERAN,
    disability_status=DisabilityStatus.NO,
    race_ethnicity=Race.ASIAN,
    gender_identity=Gender.MALE,
    cover_letter_base={
        "intro": (
            "I'm a senior software engineer with eight years building ML-driven "
            "personalization, marketing tech, and platform systems."
        ),
        "close": (
            "I'd love to hear how the team thinks about platform investment vs "
            "shipping product surface area."
        ),
    },
    created_at=_ago(days=120),
    updated_at=_ago(days=2),
)

# ─────────────────────────────────────────────────────────────────────────
# 4 Experiences + 14 Bullets (per SAMPLE_DATA.md § C)
# ─────────────────────────────────────────────────────────────────────────

EXPERIENCES: list[Experience] = [
    Experience(
        id=1,
        profile_id=1,
        company="Intuit",
        title="Senior Software Engineer",
        team="Personalization / Marketing Tech",
        location="Mountain View, CA",
        start_date=datetime(2020, 9, 1, tzinfo=UTC),
        end_date=None,
        order_index=0,
        summary_short="Owns the ML personalization platform across QBO + TurboTax.",
        created_at=_ago(days=120),
        updated_at=_ago(days=15),
    ),
    Experience(
        id=2,
        profile_id=1,
        company="Plaid",
        title="Software Engineer II",
        team="Risk & Onboarding Platform",
        location="San Francisco, CA",
        start_date=datetime(2018, 7, 1, tzinfo=UTC),
        end_date=datetime(2020, 8, 31, tzinfo=UTC),
        order_index=1,
        summary_short="Built risk + onboarding flows; bank-grade KYC pipelines.",
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Experience(
        id=3,
        profile_id=1,
        company="Capital One",
        title="Software Engineer",
        team="Anti-Fraud ML",
        location="McLean, VA",
        start_date=datetime(2017, 8, 1, tzinfo=UTC),
        end_date=datetime(2018, 6, 30, tzinfo=UTC),
        order_index=2,
        summary_short="Anti-fraud ML scoring on credit card transactions.",
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Experience(
        id=4,
        profile_id=1,
        company="Northeastern University",
        title="Research Assistant — NLP Lab",
        team=None,
        location="Boston, MA",
        start_date=datetime(2016, 1, 1, tzinfo=UTC),
        end_date=datetime(2017, 5, 31, tzinfo=UTC),
        order_index=3,
        summary_short="NLP research; published on relation extraction.",
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
]

BULLETS: list[Bullet] = [
    # Intuit — 5 bullets (#1 ALWAYS_INCLUDE — the headline lift bullet)
    Bullet(
        id=1,
        experience_id=1,
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
        edited_at=_ago(days=15),
        created_at=_ago(days=120),
        updated_at=_ago(days=15),
    ),
    Bullet(
        id=2,
        experience_id=1,
        order_index=1,
        text=(
            "Designed the GenAI rewrites feature that personalized email campaign "
            "subject lines for QuickBooks SMB cohorts — Anthropic Claude in the loop, "
            "structured-output tool calls, plus an LLM-as-judge evaluator. Lift over "
            "the static-template control: +14% open rate across 4M weekly sends."
        ),
        tags=[Tag.GENAI, Tag.AI_ML, Tag.PRODUCT],
        selection_override=None,
        edited_at=_ago(days=20),
        created_at=_ago(days=120),
        updated_at=_ago(days=20),
    ),
    Bullet(
        id=3,
        experience_id=1,
        order_index=2,
        text=(
            "Led the migration of personalization inference from a Python monolith to "
            "a Go-based service mesh on EKS — p99 latency dropped from 380ms to 92ms; "
            "compute spend down 41%. Mentored four engineers through the rewrite."
        ),
        tags=[Tag.BACKEND, Tag.PLATFORM, Tag.LEADERSHIP, Tag.DEVOPS],
        selection_override=None,
        edited_at=_ago(days=40),
        created_at=_ago(days=120),
        updated_at=_ago(days=40),
    ),
    Bullet(
        id=4,
        experience_id=1,
        order_index=3,
        text=(
            "Stood up the ranking-model evaluation harness — cross-validated lift, "
            "drift detection, and shadow-traffic replay — caught two production "
            "regressions before they shipped to homepage. Adopted by three sister "
            "teams as the standard Intuit ranking eval framework."
        ),
        tags=[Tag.AI_ML, Tag.DATA_ENG, Tag.PLATFORM],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Bullet(
        id=5,
        experience_id=1,
        order_index=4,
        text=(
            "Owned the GenAI prompt-template registry — versioned prompts, A/B-tested "
            "tone variants, and integrated with the LLM cost tracker so every prompt "
            "carries a $$/call attribution. Surfaced $38k/year of overspend in the "
            "first quarter of rollout."
        ),
        tags=[Tag.GENAI, Tag.PLATFORM, Tag.PRODUCT],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    # Plaid — 4 bullets
    Bullet(
        id=6,
        experience_id=2,
        order_index=0,
        text=(
            "Designed and built Plaid's KYC verification orchestrator — Python on "
            "Kafka, idempotent job runner, retries with exponential backoff. "
            "Processed 1.4M monthly verifications with 99.97% success rate."
        ),
        tags=[Tag.BACKEND, Tag.PLATFORM, Tag.DATA_ENG],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Bullet(
        id=7,
        experience_id=2,
        order_index=1,
        text=(
            "Owned the bank-link onboarding React flow used by ~30% of US fintechs. "
            "Reduced abandonment 11% by collapsing the institution-search step into "
            "an autocomplete with fuzzy-match rather than a paginated list."
        ),
        tags=[Tag.FRONTEND, Tag.PRODUCT],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Bullet(
        id=8,
        experience_id=2,
        order_index=2,
        text=(
            "Built the institution-status dashboard that the 24/7 ops team uses to "
            "spot bank-side outages within 90 seconds of onset. Replaced a Slack "
            "channel of manually-fired alerts with a query-the-source-of-truth view."
        ),
        tags=[Tag.BACKEND, Tag.FRONTEND, Tag.DEVOPS],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Bullet(
        id=9,
        experience_id=2,
        order_index=3,
        text=(
            "Tech-led a 5-engineer pod through a quarter-long platform migration off "
            "Heroku Postgres onto a self-managed Aurora cluster. Zero customer "
            "downtime; saved $260k/year in DBaaS fees."
        ),
        tags=[Tag.LEADERSHIP, Tag.DEVOPS, Tag.BACKEND],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    # Capital One — 3 bullets (#10 NEVER_INCLUDE — early Capital One internship-y bullet)
    Bullet(
        id=10,
        experience_id=3,
        order_index=0,
        text=(
            "Wrote the EDA notebook for the anti-fraud team's first XGBoost baseline. "
            "Internal-only; deprecated within six months but seeded the eventual "
            "production model architecture."
        ),
        tags=[Tag.AI_ML, Tag.DATA_ENG],
        selection_override=BulletSelectionOverride.NEVER_INCLUDE,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Bullet(
        id=11,
        experience_id=3,
        order_index=1,
        text=(
            "Shipped a real-time fraud scoring endpoint on the credit-card "
            "transaction stream — Java + Kafka, p99 latency under 18ms — replaced a "
            "30-minute batch detector. Caught $1.1M of fraud per month that was "
            "previously slipping through the gap."
        ),
        tags=[Tag.BACKEND, Tag.AI_ML, Tag.PLATFORM],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Bullet(
        id=12,
        experience_id=3,
        order_index=2,
        text=(
            "Co-authored the team's first model-governance doc — fairness audits, "
            "drift dashboards, and on-call runbooks — adopted as the template for "
            "five sibling ML teams at Capital One."
        ),
        tags=[Tag.AI_ML, Tag.LEADERSHIP, Tag.PRODUCT],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    # Northeastern — 2 bullets
    Bullet(
        id=13,
        experience_id=4,
        order_index=0,
        text=(
            "Published a first-author paper at EMNLP'17 on weakly-supervised "
            "relation extraction, evaluated against the TACRED benchmark. Cited 60+ "
            "times since."
        ),
        tags=[Tag.AI_ML, Tag.DATA_ENG],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Bullet(
        id=14,
        experience_id=4,
        order_index=1,
        text=(
            "Built the lab's distributed annotation tool used by 12 grad students to "
            "label 40k sentences for the relation-extraction dataset. React + "
            "Postgres; open-sourced as `re-annotate` on GitHub."
        ),
        tags=[Tag.FRONTEND, Tag.BACKEND, Tag.DATA_ENG],
        selection_override=None,
        edited_at=None,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# 6 Skills, 2 Educations, 4 Projects, 1 Certification
# ─────────────────────────────────────────────────────────────────────────

SKILLS: list[Skill] = [
    Skill(
        id=1,
        profile_id=1,
        category="Languages",
        items=["Python", "Go", "TypeScript", "Java", "SQL"],
        order_index=0,
        created_at=_ago(days=120),
        updated_at=_ago(days=15),
    ),
    Skill(
        id=2,
        profile_id=1,
        category="ML / Data",
        items=["PyTorch", "scikit-learn", "XGBoost", "Airflow", "Spark", "dbt"],
        order_index=1,
        created_at=_ago(days=120),
        updated_at=_ago(days=15),
    ),
    Skill(
        id=3,
        profile_id=1,
        category="Backend",
        items=["FastAPI", "gRPC", "Kafka", "PostgreSQL", "Redis", "Elasticsearch"],
        order_index=2,
        created_at=_ago(days=120),
        updated_at=_ago(days=15),
    ),
    Skill(
        id=4,
        profile_id=1,
        category="Cloud / Infra",
        items=["AWS (EKS, Lambda, RDS, S3)", "Terraform", "Docker", "Kubernetes"],
        order_index=3,
        created_at=_ago(days=120),
        updated_at=_ago(days=15),
    ),
    Skill(
        id=5,
        profile_id=1,
        category="Frontend",
        items=["React", "Next.js", "Tailwind", "HTMX"],
        order_index=4,
        created_at=_ago(days=120),
        updated_at=_ago(days=15),
    ),
    Skill(
        id=6,
        profile_id=1,
        category="Tooling",
        items=["Git", "GitHub Actions", "Datadog", "Sentry"],
        order_index=5,
        created_at=_ago(days=120),
        updated_at=_ago(days=15),
    ),
]

EDUCATIONS: list[Education] = [
    Education(
        id=1,
        profile_id=1,
        institution="Northeastern University",
        school="Khoury College of Computer Sciences",
        location="Boston, MA",
        degree="MS Computer Science",
        start_date=datetime(2015, 9, 1, tzinfo=UTC),
        end_date=datetime(2017, 5, 31, tzinfo=UTC),
        gpa="3.84 / 4.0",
        courses=[
            "Distributed Systems",
            "Machine Learning",
            "NLP",
            "Database Internals",
        ],
        order_index=0,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
    Education(
        id=2,
        profile_id=1,
        institution="University of Mumbai",
        school="K. J. Somaiya College of Engineering",
        location="Mumbai, India",
        degree="BE Computer Engineering",
        start_date=datetime(2011, 7, 1, tzinfo=UTC),
        end_date=datetime(2015, 5, 31, tzinfo=UTC),
        gpa="8.62 CGPA",
        courses=[],
        order_index=1,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
]

PROJECTS: list[Project] = [
    Project(
        id=1,
        profile_id=1,
        title="Naavik",
        date=_ago(days=14),
        text=(
            "Open-source career automation platform. Self-hosted first (NixOS + "
            "Docker Compose); cloud tier optional. AGPL-3.0. Python + FastAPI + "
            "HTMX + Postgres + Typst."
        ),
        tags=[Tag.AI_ML, Tag.BACKEND, Tag.PLATFORM, Tag.PRODUCT],
        portfolio_slug="naavik",
        link="https://github.com/crizzy9/naavik",
        order_index=0,
        created_at=_ago(days=60),
        updated_at=_ago(days=2),
    ),
    Project(
        id=2,
        profile_id=1,
        title="Lumino",
        date=_ago(days=180),
        text=(
            "Personal homelab orchestration via NixOS modules. Traefik + SOPS + "
            "PostgreSQL + 12 self-hosted services."
        ),
        tags=[Tag.DEVOPS, Tag.PLATFORM],
        portfolio_slug="lumino",
        link=None,
        order_index=1,
        created_at=_ago(days=300),
        updated_at=_ago(days=15),
    ),
    Project(
        id=3,
        profile_id=1,
        title="crypticsoul.dev",
        date=_ago(days=400),
        text=(
            "Personal portfolio site. Astro + Tailwind, deployed to Netlify. "
            "Pulls CV data from Naavik's portfolio API at build time."
        ),
        tags=[Tag.FRONTEND, Tag.PRODUCT],
        portfolio_slug="crypticsoul",
        link="https://crypticsoul.dev",
        order_index=2,
        created_at=_ago(days=400),
        updated_at=_ago(days=20),
    ),
    Project(
        id=4,
        profile_id=1,
        title="mlretain",
        date=_ago(days=600),
        text=(
            "Open-source ML retention scoring lib. Python; ~140 GitHub stars. "
            "Implements the Buy-Til-You-Die family (Pareto/NBD, BG/NBD)."
        ),
        tags=[Tag.AI_ML, Tag.DATA_ENG],
        portfolio_slug="mlretain",
        link="https://github.com/crizzy9/mlretain",
        order_index=3,
        created_at=_ago(days=720),
        updated_at=_ago(days=120),
    ),
]

CERTIFICATIONS: list[Certification] = [
    Certification(
        id=1,
        profile_id=1,
        title="AWS Certified Solutions Architect — Associate",
        issuer="Amazon Web Services",
        date=datetime(2022, 9, 15, tzinfo=UTC),
        description="3-year cert; renews 2025-09.",
        order_index=0,
        created_at=_ago(days=120),
        updated_at=_ago(days=120),
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# 5 JobScrapeRun fixtures — last 24h of scraping. Plan 27 § D.10.
# IDs in 900-range so they never collide with Job/Application IDs.
# ─────────────────────────────────────────────────────────────────────────

JOB_SCRAPE_RUNS: list[JobScrapeRun] = [
    JobScrapeRun(
        id=901,
        user_id=1,
        source=JobSource.LINKEDIN,
        status=JobScrapeStatus.SUCCESS,
        triggered_by="cron",
        started_at=_ago(hours=2),
        finished_at=_ago(hours=1, minutes=42),
        duration_ms=18 * 60 * 1000,
        requests_made=180,
        listings_returned=42,
        new_jobs=3,
        updated_jobs=12,
        errors=[],
        raw_meta={"user_agent_pool_idx": 2, "rate_limit_hits": 0},
        created_at=_ago(hours=2),
    ),
    JobScrapeRun(
        id=902,
        user_id=1,
        source=JobSource.GREENHOUSE,
        status=JobScrapeStatus.SUCCESS,
        triggered_by="cron",
        started_at=_ago(hours=3),
        finished_at=_ago(hours=2, minutes=51),
        duration_ms=9 * 60 * 1000,
        requests_made=72,
        listings_returned=68,
        new_jobs=5,
        updated_jobs=8,
        errors=[],
        raw_meta={"companies_scanned": ["stripe", "anthropic", "figma", "plaid"]},
        created_at=_ago(hours=3),
    ),
    JobScrapeRun(
        id=903,
        user_id=1,
        source=JobSource.LEVER,
        status=JobScrapeStatus.SUCCESS,
        triggered_by="cron",
        started_at=_ago(hours=4),
        finished_at=_ago(hours=3, minutes=44),
        duration_ms=16 * 60 * 1000,
        requests_made=54,
        listings_returned=37,
        new_jobs=2,
        updated_jobs=5,
        errors=[],
        raw_meta={},
        created_at=_ago(hours=4),
    ),
    JobScrapeRun(
        id=904,
        user_id=1,
        source=JobSource.WORKDAY,
        status=JobScrapeStatus.PARTIAL,
        triggered_by="cron",
        started_at=_ago(hours=5),
        finished_at=_ago(hours=4, minutes=18),
        duration_ms=42 * 60 * 1000,
        requests_made=210,
        listings_returned=33,
        new_jobs=1,
        updated_jobs=4,
        errors=[
            "stage=fetch_detail url=https://snowflake.wd1.myworkdayjobs.com/job/JR-99812 "
            "kind=timeout msg=playwright_navigation_timeout",
            "stage=fetch_detail url=https://databricks.wd1.myworkdayjobs.com/job/JR-91234 "
            "kind=rate_limit msg=429_response_after_2_retries",
        ],
        raw_meta={"playwright_pool_size": 2},
        created_at=_ago(hours=5),
    ),
    JobScrapeRun(
        id=905,
        user_id=1,
        source=JobSource.INDEED,
        status=JobScrapeStatus.FAILED,
        triggered_by="cron",
        started_at=_ago(hours=6),
        finished_at=_ago(hours=5, minutes=58),
        duration_ms=2 * 60 * 1000,
        requests_made=4,
        listings_returned=0,
        new_jobs=0,
        updated_jobs=0,
        errors=[
            "stage=list_jobs url=https://www.indeed.com/jobs?q=ml+engineer "
            "kind=captcha msg=hcaptcha_challenge_after_3_pages",
        ],
        raw_meta={"captcha_strategy_exhausted": True},
        created_at=_ago(hours=6),
    ),
]


# ─────────────────────────────────────────────────────────────────────────
# ~20 Jobs (per SAMPLE_DATA.md § E)
# ─────────────────────────────────────────────────────────────────────────

JOBS: list[Job] = [
    # Job 101 — Stripe Atlas (the headline Discover card; UNSWIPED, hot)
    Job(
        id=101,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://stripe.com/jobs/listing/senior-ml-engineer-atlas/5894273",
        url_type="ats",
        external_id="45761d786a4a",
        company="Stripe",
        role="Senior ML Engineer",
        team="Atlas",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(hours=2),
        found_at=_ago(hours=1, minutes=15),
        description=(
            "Stripe Atlas helps founders incorporate, raise capital, and operate. "
            "We're building an ML platform for ranking + personalizing Atlas's "
            "knowledge graph, and we need a senior IC who's owned ML platforms "
            "end-to-end. You'll define the ranking + retrieval architecture, work "
            "across data engineering, modeling, and serving, and partner with "
            "product to ship surfaces that meaningfully change how founders learn."
        ),
        criteria=[
            "5+ years building production ML systems",
            "Strong Python; comfort with Go a plus",
            "Experience with ranking / retrieval / personalization at scale",
            "Owned a system from data pipeline through inference",
        ],
        skills_required=["Python", "PyTorch", "distributed systems", "Go"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=240_000,
        salary_max=290_000,
        equity_pct=0.05,
        score=0.86,
        score_explanation=(
            "Strong ai-ml + platform alignment with your Intuit personalization "
            "stack. Visa sponsorship available. Bay-Area hybrid matches "
            "preferences."
        ),
        match_breakdown={
            "ai-ml": 0.95,
            "platform": 0.88,
            "leadership": 0.82,
            "backend": 0.79,
        },
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.AI_ML, Tag.PLATFORM, Tag.BACKEND],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(hours=1, minutes=15),
        updated_at=_ago(hours=1),
    ),
    # Job 102 — Linear (UNSWIPED; warm intro to contact 202)
    Job(
        id=102,
        user_id=1,
        source=JobSource.ASHBY,
        board=ApplicationBoard.ASHBY,
        url="https://jobs.ashbyhq.com/linear/founding-eng-search/12345",
        url_type="ats",
        external_id="2fee7c1d7c48",
        company="Linear",
        role="Founding Engineer",
        team="Search",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=1, hours=4),
        found_at=_ago(days=1, hours=3),
        description=(
            "Linear is building a new search team. You'll be the founding engineer "
            "owning indexing, ranking, and the IDE-shaped query surface that "
            "developers reach for instinctively. Generalist mindset; product taste; "
            "comfort going from spec to ship."
        ),
        criteria=[
            "5+ years backend / full-stack",
            "Search or ranking experience",
            "Strong product instincts",
        ],
        skills_required=["TypeScript", "Postgres", "search"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=220_000,
        salary_max=280_000,
        equity_pct=0.10,
        score=0.81,
        score_explanation=(
            "Backend + product fit; founding-engineer stage matches your scope "
            "preference. Warm intro available."
        ),
        match_breakdown={
            "backend": 0.92,
            "platform": 0.78,
            "product": 0.85,
            "ai-ml": 0.62,
        },
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.BACKEND, Tag.PLATFORM, Tag.PRODUCT],
        warm_intro_contact_id=202,
        created_at=_ago(days=1, hours=3),
        updated_at=_ago(days=1, hours=2),
    ),
    # Job 103 — Anthropic (UNSWIPED; warm intro to Priya — contact 201)
    Job(
        id=103,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/anthropic/jobs/4123887",
        url_type="ats",
        external_id="2a1972b88f5c",
        company="Anthropic",
        role="Senior ML Engineer",
        team="Inference Platform",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=22),
        found_at=_ago(days=21, hours=18),
        description=(
            "Anthropic is looking for a senior ML engineer to own pieces of the "
            "inference platform. We serve frontier models at internet scale; you'll "
            "work on batching, KV-cache management, distributed scheduling, and "
            "the ML-systems boundary that makes Claude fast. Strong ML + systems "
            "background required."
        ),
        criteria=[
            "5+ years ML / systems engineering",
            "Distributed inference experience",
            "Comfort across the ML-systems boundary",
        ],
        skills_required=["Python", "PyTorch", "vLLM", "distributed systems"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=280_000,
        salary_max=340_000,
        equity_pct=0.07,
        score=0.92,
        score_explanation=(
            "Strong ai-ml + platform; warm intro available; visa sponsorship; "
            "GenAI work at Intuit ties in directly."
        ),
        match_breakdown={
            "ai-ml": 0.97,
            "platform": 0.93,
            "leadership": 0.85,
            "genai": 0.91,
        },
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.AI_ML, Tag.PLATFORM, Tag.GENAI],
        warm_intro_contact_id=201,
        last_scrape_run_id=902,
        created_at=_ago(days=21, hours=18),
        updated_at=_ago(days=21),
    ),
    # Job 104 — Notion (UNSWIPED; standard backend role)
    Job(
        id=104,
        user_id=1,
        source=JobSource.LEVER,
        board=ApplicationBoard.LEVER,
        url="https://jobs.lever.co/notion/sr-backend-platform/abc-789",
        url_type="ats",
        external_id="dc5ee5319dd1",
        company="Notion",
        role="Senior Backend Engineer",
        team="Platform",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=8),
        found_at=_ago(days=7, hours=20),
        description=(
            "Help build Notion's platform — the systems behind blocks, sync, and "
            "real-time collaboration. Strong distributed systems experience required."
        ),
        criteria=["5+ years backend", "Distributed systems", "Postgres at scale"],
        skills_required=["TypeScript", "Postgres", "distributed systems"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=250_000,
        salary_max=300_000,
        equity_pct=0.04,
        score=0.78,
        score_explanation="Backend + platform alignment; team is hiring fast.",
        match_breakdown={"backend": 0.91, "platform": 0.86, "leadership": 0.70},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.BACKEND, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=903,
        created_at=_ago(days=7, hours=20),
        updated_at=_ago(days=7),
    ),
    # Job 105 — Figma (APPLIED; offer in flight)
    Job(
        id=105,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/figma/sr-backend/55512",
        url_type="ats",
        external_id="b8ee5d43bea0",
        company="Figma",
        role="Staff Backend Engineer",
        team="Identity",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=32),
        found_at=_ago(days=31, hours=12),
        description=(
            "Lead the identity + auth platform at Figma. Responsibilities span "
            "tenancy, SSO, audit, and the on-call rotation that keeps every "
            "design org online."
        ),
        criteria=["7+ years backend", "Identity / auth experience", "On-call leadership"],
        skills_required=["Go", "Postgres", "OAuth"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=280_000,
        salary_max=320_000,
        equity_pct=0.04,
        score=0.84,
        score_explanation="Strong backend + leadership; visa friendly.",
        match_breakdown={"backend": 0.90, "leadership": 0.88, "platform": 0.81},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.BACKEND, Tag.LEADERSHIP, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(days=31, hours=12),
        updated_at=_ago(days=28),
    ),
    # Job 106 — Plaid (APPLIED via referral)
    Job(
        id=106,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/plaid/staff-eng/77100",
        url_type="ats",
        external_id="fc3e5ea06538",
        company="Plaid",
        role="Staff Engineer",
        team="Risk Platform",
        location="San Francisco, CA · Remote",
        posted_at=_ago(days=10),
        found_at=_ago(days=9),
        description=(
            "Build the next generation of Plaid's risk platform. Cross-product "
            "ownership; partners with onboarding, anti-fraud, and the data team."
        ),
        criteria=["7+ years backend", "Risk / fraud experience", "Distributed systems"],
        skills_required=["Python", "Go", "Kafka"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=270_000,
        salary_max=320_000,
        equity_pct=0.06,
        score=0.83,
        score_explanation="Direct alumni network; risk + platform alignment.",
        match_breakdown={"backend": 0.91, "platform": 0.88, "leadership": 0.82},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.BACKEND, Tag.PLATFORM, Tag.LEADERSHIP],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(days=9),
        updated_at=_ago(days=5),
    ),
    # Job 107 — Ramp (APPLIED, docs stale)
    Job(
        id=107,
        user_id=1,
        source=JobSource.LEVER,
        board=ApplicationBoard.LEVER,
        url="https://jobs.lever.co/ramp/em-platform/abcde",
        url_type="ats",
        external_id="d00440e0866d",
        company="Ramp",
        role="Engineering Manager",
        team="Spend Platform",
        location="New York, NY · Hybrid",
        posted_at=_ago(days=20),
        found_at=_ago(days=19),
        description=(
            "Manage the spend platform team at Ramp — owns the rails behind every "
            "Ramp card transaction. People-management + technical depth."
        ),
        criteria=["3+ years EM", "Strong IC background", "Payments / fintech a plus"],
        skills_required=["Python", "Postgres", "leadership"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=260_000,
        salary_max=320_000,
        equity_pct=0.05,
        score=0.74,
        score_explanation="Leadership + backend; NY relocation gate.",
        match_breakdown={"leadership": 0.92, "backend": 0.84, "platform": 0.71},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.LEADERSHIP, Tag.BACKEND, Tag.PRODUCT],
        warm_intro_contact_id=None,
        last_scrape_run_id=903,
        created_at=_ago(days=19),
        updated_at=_ago(days=14),
    ),
    # Job 108 — Discord (ONSITE_LOOP)
    Job(
        id=108,
        user_id=1,
        source=JobSource.LEVER,
        board=ApplicationBoard.LEVER,
        url="https://jobs.lever.co/discord/sr-backend-relevance/aa11",
        url_type="ats",
        external_id="4140a9208081",
        company="Discord",
        role="Senior Backend Engineer",
        team="Relevance",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=40),
        found_at=_ago(days=39),
        description=(
            "Discord's relevance team builds the systems behind notification "
            "ranking, search, and surfacing-the-right-message."
        ),
        criteria=["5+ years backend", "Distributed systems", "Ranking a plus"],
        skills_required=["Python", "Go", "Elasticsearch"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=260_000,
        salary_max=310_000,
        equity_pct=0.04,
        score=0.81,
        score_explanation="Backend + ranking alignment.",
        match_breakdown={"backend": 0.88, "ai-ml": 0.74, "platform": 0.82},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.BACKEND, Tag.PLATFORM, Tag.AI_ML],
        warm_intro_contact_id=None,
        last_scrape_run_id=903,
        created_at=_ago(days=39),
        updated_at=_ago(days=32),
    ),
    # Job 109 — Snowflake (CLOSED · rejected)
    Job(
        id=109,
        user_id=1,
        source=JobSource.WORKDAY,
        board=ApplicationBoard.WORKDAY,
        url="https://snowflake.wd1.myworkdayjobs.com/External_Career_Site/job/Sr-ML-Engineer/JR-12345",
        url_type="ats",
        external_id="0f9ff648a5d1",
        company="Snowflake",
        role="Senior ML Engineer",
        team="Cortex",
        location="San Mateo, CA · Hybrid",
        posted_at=_ago(days=55),
        found_at=_ago(days=53),
        description="Cortex builds embedded ML for the Snowflake data cloud.",
        criteria=["5+ years ML platform", "Distributed systems"],
        skills_required=["Python", "PyTorch", "Spark"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=240_000,
        salary_max=290_000,
        equity_pct=0.03,
        score=0.79,
        score_explanation="ML + platform; closed after recruiter screen.",
        match_breakdown={"ai-ml": 0.85, "platform": 0.79, "data-eng": 0.81},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.AI_ML, Tag.PLATFORM, Tag.DATA_ENG],
        warm_intro_contact_id=None,
        last_scrape_run_id=904,
        created_at=_ago(days=53),
        updated_at=_ago(days=44),
    ),
    # Job 110 — Airbnb (CLOSED · ghosted)
    Job(
        id=110,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/airbnb/sr-backend/99211",
        url_type="ats",
        external_id="dfdb72069cc7",
        company="Airbnb",
        role="Senior Backend Engineer",
        team="Trust",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=70),
        found_at=_ago(days=68),
        description="Build the trust platform at Airbnb — host + guest verification.",
        criteria=["5+ years backend", "Trust / safety experience"],
        skills_required=["Java", "Kafka", "Postgres"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=230_000,
        salary_max=280_000,
        equity_pct=0.03,
        score=0.72,
        score_explanation="Backend + platform; ghosted after submission.",
        match_breakdown={"backend": 0.85, "platform": 0.78, "leadership": 0.65},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.BACKEND, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(days=68),
        updated_at=_ago(days=60),
    ),
    # Job 111 — Databricks (CLOSED · withdrawn)
    Job(
        id=111,
        user_id=1,
        source=JobSource.WORKDAY,
        board=ApplicationBoard.WORKDAY,
        url="https://databricks.wd1.myworkdayjobs.com/External/job/Founding-Eng-Lakehouse/JR-99999",
        url_type="ats",
        external_id="627786264da1",
        company="Databricks",
        role="Founding Engineer",
        team="Lakehouse Apps",
        location="Mountain View, CA",
        posted_at=_ago(days=58),
        found_at=_ago(days=55),
        description="Founding engineer for a new Lakehouse-native apps platform.",
        criteria=["7+ years backend / data", "Strong product instincts"],
        skills_required=["Python", "Spark", "Scala"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=240_000,
        salary_max=300_000,
        equity_pct=0.03,
        score=0.77,
        score_explanation="Data + backend; withdrawn (comp gap).",
        match_breakdown={"backend": 0.84, "data-eng": 0.86, "platform": 0.79},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.BACKEND, Tag.DATA_ENG, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=904,
        created_at=_ago(days=55),
        updated_at=_ago(days=50),
    ),
    # Job 112 — Cresta (APPLIED, docs failed)
    Job(
        id=112,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/cresta/sr-ml/aa9912",
        url_type="ats",
        external_id="eba36b4dd059",
        company="Cresta",
        role="Senior ML Engineer",
        team="Coaching Platform",
        location="San Francisco, CA · Remote",
        posted_at=_ago(days=4),
        found_at=_ago(days=3),
        description=(
            "Cresta builds AI coaching for contact-center reps. ML team owns the "
            "real-time speech + recommendation surface."
        ),
        criteria=["5+ years ML", "Real-time inference"],
        skills_required=["Python", "PyTorch", "real-time"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=230_000,
        salary_max=290_000,
        equity_pct=0.06,
        score=0.80,
        score_explanation="ML + GenAI alignment; docs compile failed once.",
        match_breakdown={"ai-ml": 0.88, "genai": 0.82, "platform": 0.74},
        queue_state=JobQueueState.APPLIED,
        tags=[Tag.AI_ML, Tag.GENAI, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(days=3),
        updated_at=_ago(days=1),
    ),
    # Job 113 — Mercury (DRAFT · manual review-and-apply in flight)
    Job(
        id=113,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/mercury/sr-backend/123-456",
        url_type="ats",
        external_id="51cccb9c5f72",
        company="Mercury",
        role="Senior Backend Engineer",
        team="Card Platform",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=2),
        found_at=_ago(days=1, hours=12),
        description=(
            "Mercury is hiring for the card platform — own pieces of the spend, "
            "rewards, and ledger systems."
        ),
        criteria=["5+ years backend", "Payments experience"],
        skills_required=["Python", "Postgres", "ledger"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=240_000,
        salary_max=290_000,
        equity_pct=0.05,
        score=0.82,
        score_explanation="Backend + platform; user reviewing now.",
        match_breakdown={"backend": 0.90, "platform": 0.84, "product": 0.71},
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.BACKEND, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(days=1, hours=12),
        updated_at=_ago(days=1),
    ),
    # Job 114 — Modal (DRAFT · auto-apply queued + FAILED [for stuck-queue card])
    Job(
        id=114,
        user_id=1,
        source=JobSource.ASHBY,
        board=ApplicationBoard.ASHBY,
        url="https://jobs.ashbyhq.com/modal/founding-eng/zz1122",
        url_type="ats",
        external_id="73d81c517411",
        company="Modal",
        role="Founding Engineer",
        team="Runtime",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=1),
        found_at=_ago(hours=18),
        description=(
            "Modal is building the cloud runtime that lets ML teams ship code "
            "without containers. Founding engineer on the runtime."
        ),
        criteria=["5+ years systems / backend", "ML adjacency a plus"],
        skills_required=["Rust", "Python", "distributed systems"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=240_000,
        salary_max=310_000,
        equity_pct=0.08,
        score=0.87,
        score_explanation=(
            "Strong platform + backend; queued for auto-apply but ATS submission "
            "failed (auth required)."
        ),
        match_breakdown={"backend": 0.92, "platform": 0.91, "ai-ml": 0.74},
        queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY,
        tags=[Tag.BACKEND, Tag.PLATFORM, Tag.DEVOPS],
        warm_intro_contact_id=None,
        created_at=_ago(hours=18),
        updated_at=_ago(hours=2),
    ),
    # Job 115 — saved (Vercel)
    Job(
        id=115,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/vercel/sr-frontend/55-66",
        url_type="ats",
        external_id="ce6d7cd70de6",
        company="Vercel",
        role="Senior Software Engineer",
        team="Edge",
        location="San Francisco, CA · Remote",
        posted_at=_ago(days=3),
        found_at=_ago(days=2, hours=4),
        description="Edge platform engineer at Vercel.",
        criteria=["5+ years backend / edge", "TypeScript"],
        skills_required=["TypeScript", "Edge runtime", "Postgres"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=240_000,
        salary_max=290_000,
        equity_pct=0.05,
        score=0.79,
        score_explanation="Backend + frontend overlap.",
        match_breakdown={"backend": 0.84, "frontend": 0.78, "platform": 0.81},
        queue_state=JobQueueState.SAVED,
        tags=[Tag.BACKEND, Tag.FRONTEND, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(days=2, hours=4),
        updated_at=_ago(days=1),
    ),
    # Job 116 — saved (Replicate)
    Job(
        id=116,
        user_id=1,
        source=JobSource.LEVER,
        board=ApplicationBoard.LEVER,
        url="https://jobs.lever.co/replicate/sr-ml/aabb-1122",
        url_type="ats",
        external_id="726816b2b07c",
        company="Replicate",
        role="Senior ML Platform Engineer",
        team="Inference",
        location="San Francisco, CA · Remote",
        posted_at=_ago(days=4),
        found_at=_ago(days=3),
        description="Inference platform for hosted ML models.",
        criteria=["5+ years ML platform", "Cloud GPUs"],
        skills_required=["Python", "PyTorch", "K8s"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=230_000,
        salary_max=290_000,
        equity_pct=0.05,
        score=0.84,
        score_explanation="ML + platform alignment; saved for later.",
        match_breakdown={"ai-ml": 0.91, "platform": 0.88, "devops": 0.76},
        queue_state=JobQueueState.SAVED,
        tags=[Tag.AI_ML, Tag.PLATFORM, Tag.DEVOPS],
        warm_intro_contact_id=None,
        last_scrape_run_id=903,
        created_at=_ago(days=3),
        updated_at=_ago(days=2),
    ),
    # Job 117 — saved (Sourcegraph)
    Job(
        id=117,
        user_id=1,
        source=JobSource.LEVER,
        board=ApplicationBoard.LEVER,
        url="https://jobs.lever.co/sourcegraph/sr-cody/55-77",
        url_type="ats",
        external_id="762da90939a0",
        company="Sourcegraph",
        role="Senior Engineer",
        team="Cody",
        location="Remote",
        posted_at=_ago(days=6),
        found_at=_ago(days=5),
        description="Build Cody — Sourcegraph's AI coding assistant.",
        criteria=["5+ years backend / ML", "GenAI experience"],
        skills_required=["Go", "Python", "LLMs"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=220_000,
        salary_max=280_000,
        equity_pct=0.04,
        score=0.83,
        score_explanation="GenAI + backend overlap.",
        match_breakdown={"genai": 0.92, "backend": 0.84, "ai-ml": 0.85},
        queue_state=JobQueueState.SAVED,
        tags=[Tag.GENAI, Tag.BACKEND, Tag.AI_ML],
        warm_intro_contact_id=None,
        last_scrape_run_id=903,
        created_at=_ago(days=5),
        updated_at=_ago(days=4),
    ),
    # Job 118 — saved (Cohere)
    Job(
        id=118,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/cohere/sr-ml-platform/aa-bb-1234",
        url_type="ats",
        external_id="de32632f0fb7",
        company="Cohere",
        role="Senior ML Engineer",
        team="Embeddings",
        location="Toronto, ON · Hybrid",
        posted_at=_ago(days=7),
        found_at=_ago(days=6),
        description="Embeddings team at Cohere.",
        criteria=["5+ years ML", "Embedding / retrieval research"],
        skills_required=["Python", "PyTorch", "research"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=190_000,
        salary_max=240_000,
        equity_pct=0.03,
        score=0.71,
        score_explanation="Toronto relocation; salary in CAD lower.",
        match_breakdown={"ai-ml": 0.85, "genai": 0.78, "platform": 0.71},
        queue_state=JobQueueState.SAVED,
        tags=[Tag.AI_ML, Tag.GENAI],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(days=6),
        updated_at=_ago(days=5),
    ),
    # Job 119 — skipped (us_citizen_only — visa filter test)
    Job(
        id=119,
        user_id=1,
        source=JobSource.LEVER,
        board=ApplicationBoard.LEVER,
        url="https://jobs.lever.co/raytheon/sr-eng/citizens-only",
        url_type="ats",
        external_id="44182b3a3735",
        company="Raytheon",
        role="Senior Software Engineer",
        team="Defense Systems",
        location="Arlington, VA",
        posted_at=_ago(days=2),
        found_at=_ago(days=1, hours=20),
        description="Defense systems backend; US citizens only (clearance required).",
        criteria=["US citizen", "5+ years backend"],
        skills_required=["Java", "C++", "secure systems"],
        visa_restrictions=VisaRestriction.US_CITIZEN_ONLY,
        salary_min=180_000,
        salary_max=220_000,
        equity_pct=None,
        score=0.0,
        score_explanation="Score zeroed — visa filter (us_citizen_only).",
        match_breakdown={},
        queue_state=JobQueueState.SKIPPED,
        tags=[Tag.BACKEND, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=903,
        created_at=_ago(days=1, hours=20),
        updated_at=_ago(days=1, hours=18),
    ),
    # Job 120 — skipped (us_citizen_only — second visa filter)
    Job(
        id=120,
        user_id=1,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/anduril/founding-eng/citizens-only-99",
        url_type="ats",
        external_id="440e9bc587e9",
        company="Anduril",
        role="Founding Engineer",
        team="Lattice",
        location="Costa Mesa, CA",
        posted_at=_ago(days=3),
        found_at=_ago(days=2, hours=15),
        description="Founding engineer; US citizens only.",
        criteria=["US citizen", "Active TS clearance preferred"],
        skills_required=["Rust", "C++", "embedded"],
        visa_restrictions=VisaRestriction.US_CITIZEN_ONLY,
        salary_min=220_000,
        salary_max=280_000,
        equity_pct=0.05,
        score=0.0,
        score_explanation="Score zeroed — visa filter (us_citizen_only).",
        match_breakdown={},
        queue_state=JobQueueState.SKIPPED,
        tags=[Tag.BACKEND, Tag.DEVOPS],
        warm_intro_contact_id=None,
        last_scrape_run_id=902,
        created_at=_ago(days=2, hours=15),
        updated_at=_ago(days=2, hours=10),
    ),
    # Job 121 — skipped (low score)
    Job(
        id=121,
        user_id=1,
        source=JobSource.INDEED,
        board=ApplicationBoard.INDEED,
        url="https://www.indeed.com/viewjob?jk=99887766",
        url_type="ats",
        external_id="cb77d7c85cac",
        company="Local Co",
        role="Junior Backend Engineer",
        team=None,
        location="Remote",
        posted_at=_ago(days=4),
        found_at=_ago(days=3, hours=12),
        description="Junior backend role; not a senior fit.",
        criteria=["1-2 years backend"],
        skills_required=["Node.js", "REST"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=80_000,
        salary_max=110_000,
        equity_pct=None,
        score=0.32,
        score_explanation="Junior role — well below seniority + comp expectation.",
        match_breakdown={"backend": 0.45, "platform": 0.20},
        queue_state=JobQueueState.SKIPPED,
        tags=[Tag.BACKEND],
        warm_intro_contact_id=None,
        last_scrape_run_id=905,
        created_at=_ago(days=3, hours=12),
        updated_at=_ago(days=3),
    ),
    # Job 122 — UNSWIPED (medium score, amber ring — Workday)
    Job(
        id=122,
        user_id=1,
        source=JobSource.WORKDAY,
        board=ApplicationBoard.WORKDAY,
        url="https://acme.wd1.myworkdayjobs.com/External/job/Sr-Eng/JR-22222",
        url_type="ats",
        external_id="8c64d0d3fb6e",
        company="Acme Corp",
        role="Senior Software Engineer",
        team="Internal Tools",
        location="Austin, TX · Onsite",
        posted_at=_ago(days=5),
        found_at=_ago(days=4),
        description="Internal-tools team at Acme.",
        criteria=["5+ years backend", "Internal tooling"],
        skills_required=["Python", "Postgres"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=180_000,
        salary_max=220_000,
        equity_pct=None,
        score=0.55,
        score_explanation="Backend fit; relocation + onsite gate.",
        match_breakdown={"backend": 0.72, "platform": 0.55, "leadership": 0.45},
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.BACKEND, Tag.PRODUCT],
        warm_intro_contact_id=None,
        last_scrape_run_id=904,
        created_at=_ago(days=4),
        updated_at=_ago(days=3),
    ),
    # Job 123 — UNSWIPED (medium score, indigo ring — Datadog)
    Job(
        id=123,
        user_id=1,
        source=JobSource.WORKDAY,
        board=ApplicationBoard.WORKDAY,
        url="https://datadog.wd1.myworkdayjobs.com/External/job/Sr-Eng-Observability/JR-33333",
        url_type="ats",
        external_id="df2d9e62a894",
        company="Datadog",
        role="Senior Engineer",
        team="Observability",
        location="New York, NY · Hybrid",
        posted_at=_ago(days=6),
        found_at=_ago(days=5),
        description="Observability backend at Datadog.",
        criteria=["5+ years backend", "Observability / metrics"],
        skills_required=["Go", "Postgres", "Kafka"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=230_000,
        salary_max=280_000,
        equity_pct=0.03,
        score=0.69,
        score_explanation="Backend + platform; NY relocation.",
        match_breakdown={"backend": 0.82, "platform": 0.78, "devops": 0.71},
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.BACKEND, Tag.PLATFORM, Tag.DEVOPS],
        warm_intro_contact_id=None,
        last_scrape_run_id=904,
        created_at=_ago(days=5),
        updated_at=_ago(days=4),
    ),
    # Job 124 — UNSWIPED (high score, emerald ring — second hot card)
    Job(
        id=124,
        user_id=1,
        source=JobSource.LINKEDIN,
        board=ApplicationBoard.LINKEDIN,
        url="https://www.linkedin.com/jobs/view/89abcdef",
        url_type="ats",
        external_id="5e73c01cd601",
        company="OpenAI",
        role="Senior ML Engineer",
        team="Inference",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=2),
        found_at=_ago(days=1, hours=8),
        description="Senior ML engineer; inference team.",
        criteria=["5+ years ML systems"],
        skills_required=["Python", "PyTorch", "vLLM"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=290_000,
        salary_max=360_000,
        equity_pct=0.06,
        score=0.90,
        score_explanation="Direct platform-ML fit; inference work matches Anthropic JD.",
        match_breakdown={"ai-ml": 0.96, "platform": 0.92, "genai": 0.88},
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.AI_ML, Tag.PLATFORM, Tag.GENAI],
        warm_intro_contact_id=None,
        last_scrape_run_id=901,
        created_at=_ago(days=1, hours=8),
        updated_at=_ago(days=1),
    ),
    # Job 125 — UNSWIPED (mid-low score, amber — Indeed import)
    Job(
        id=125,
        user_id=1,
        source=JobSource.INDEED,
        board=ApplicationBoard.INDEED,
        url="https://www.indeed.com/viewjob?jk=11223344",
        url_type="ats",
        external_id="50af5b8b0069",
        company="Wayfair",
        role="Software Engineer",
        team="Catalog",
        location="Boston, MA · Hybrid",
        posted_at=_ago(days=2),
        found_at=_ago(days=1, hours=10),
        description="Catalog team at Wayfair.",
        criteria=["3+ years backend"],
        skills_required=["Python", "Postgres"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=170_000,
        salary_max=210_000,
        equity_pct=None,
        score=0.48,
        score_explanation="Comp + seniority gap.",
        match_breakdown={"backend": 0.65, "platform": 0.48, "product": 0.40},
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.BACKEND, Tag.PRODUCT],
        warm_intro_contact_id=None,
        last_scrape_run_id=905,
        created_at=_ago(days=1, hours=10),
        updated_at=_ago(days=1),
    ),
    # Job 126 — UNSWIPED (LinkedIn Easy Apply)
    Job(
        id=126,
        user_id=1,
        source=JobSource.LINKEDIN,
        board=ApplicationBoard.LINKEDIN,
        url="https://www.linkedin.com/jobs/view/55667788",
        url_type="ats",
        external_id="9a5ac8903eb5",
        company="Stable",
        role="Senior Engineer",
        team="Foundations",
        location="Remote",
        posted_at=_ago(days=3),
        found_at=_ago(days=2, hours=8),
        description="Senior engineer on the foundations team.",
        criteria=["5+ years backend", "Distributed systems"],
        skills_required=["Go", "Postgres"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=210_000,
        salary_max=260_000,
        equity_pct=0.04,
        score=0.66,
        score_explanation="Backend fit; smaller comp + smaller co.",
        match_breakdown={"backend": 0.78, "platform": 0.66, "leadership": 0.55},
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.BACKEND, Tag.PLATFORM],
        warm_intro_contact_id=None,
        last_scrape_run_id=901,
        created_at=_ago(days=2, hours=8),
        updated_at=_ago(days=1),
    ),
    # Job 127 — manually-added (MANUAL board)
    Job(
        id=127,
        user_id=1,
        source=JobSource.MANUAL,
        board=ApplicationBoard.MANUAL,
        url="https://example.com/manual-listing-7788",
        url_type="manual",
        external_id="5cb0a13492f3",
        company="Atlas Robotics",
        role="Senior Backend Engineer",
        team="Platform",
        location="San Francisco, CA · Hybrid",
        posted_at=_ago(days=10),
        found_at=_ago(days=10),
        description="Manually added by user — heard about it via friend.",
        criteria=["5+ years backend", "Robotics adjacency a plus"],
        skills_required=["Python", "ROS", "Postgres"],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=220_000,
        salary_max=270_000,
        equity_pct=0.05,
        score=0.62,
        score_explanation="Backend fit; user-added — manual review.",
        match_breakdown={"backend": 0.78, "platform": 0.62, "leadership": 0.50},
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.BACKEND, Tag.PLATFORM],
        warm_intro_contact_id=None,
        created_at=_ago(days=10),
        updated_at=_ago(days=10),
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# 14 Applications (per SAMPLE_DATA.md § F)
# Maps to JOBS for status APPLIED+; carries denormalized job metadata.
# Two DRAFT rows: #13 (Mercury, manual review) + #14 (Modal, auto-apply queued
# with last_failure populated for the stuck-queue card).
# ─────────────────────────────────────────────────────────────────────────

APPLICATIONS: list[Application] = [
    # 1 · Figma — OFFER (verbal extended; Overview "respond to offer" surface)
    Application(
        id=1,
        user_id=1,
        job_id=105,
        company="Figma",
        role="Staff Backend Engineer",
        team="Identity",
        location="San Francisco, CA · Hybrid",
        salary_min=280_000,
        salary_max=320_000,
        equity_pct=0.04,
        applied_at=_ago(days=28),
        board=ApplicationBoard.GREENHOUSE,
        external_url="https://figma.com/jobs/applications/55512/abc",
        status=ApplicationStatus.OFFER,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.PROVIDED,
        recruiter_state=RecruiterState.RESPONDED,
        submission_artifacts={"board_application_id": "29487532", "retry_count": 0},
        notes="Verbal offer Apr 28: $290k base + 0.04%. Reply expected by Thu.",
        created_at=_ago(days=29),
        updated_at=_ago(days=2),
    ),
    # 2 · Anthropic — ONSITE_LOOP (warm intro from Priya succeeded)
    Application(
        id=2,
        user_id=1,
        job_id=103,
        company="Anthropic",
        role="Senior ML Engineer",
        team="Inference Platform",
        location="San Francisco, CA · Hybrid",
        salary_min=280_000,
        salary_max=340_000,
        equity_pct=0.07,
        applied_at=_ago(days=21),
        board=ApplicationBoard.GREENHOUSE,
        external_url="https://anthropic.com/jobs/applications/4123887/abc123",
        status=ApplicationStatus.ONSITE_LOOP,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.PROVIDED,
        recruiter_state=RecruiterState.RESPONDED,
        submission_artifacts={"board_application_id": "abc123def", "retry_count": 0},
        notes="Final round May 8. Prep: distributed inference, vLLM, batching tradeoffs.",
        created_at=_ago(days=22),
        updated_at=_ago(days=2),
    ),
    # 3 · Stripe Atlas — RECRUITER_SCREEN (just reached out)
    Application(
        id=3,
        user_id=1,
        job_id=101,
        company="Stripe",
        role="Senior ML Engineer",
        team="Atlas",
        location="San Francisco, CA · Hybrid",
        salary_min=240_000,
        salary_max=290_000,
        equity_pct=0.05,
        applied_at=_ago(days=3),
        board=ApplicationBoard.GREENHOUSE,
        external_url="https://stripe.com/jobs/applications/5894273/zzz",
        status=ApplicationStatus.RECRUITER_SCREEN,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.REQUESTED,
        recruiter_state=RecruiterState.ENGAGED,
        submission_artifacts={"board_application_id": "5891234", "retry_count": 0},
        notes="Recruiter call set for May 2.",
        created_at=_ago(days=3),
        updated_at=_ago(days=1),
    ),
    # 4 · Linear — RECRUITER_SCREEN (silent ≥6 days — Overview '6D SILENT' badge)
    Application(
        id=4,
        user_id=1,
        job_id=102,
        company="Linear",
        role="Founding Engineer",
        team="Search",
        location="San Francisco, CA · Hybrid",
        salary_min=220_000,
        salary_max=280_000,
        equity_pct=0.10,
        applied_at=_ago(days=10),
        board=ApplicationBoard.ASHBY,
        external_url="https://linear.app/jobs/applications/12345/zzz",
        status=ApplicationStatus.RECRUITER_SCREEN,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.PROVIDED,
        recruiter_state=RecruiterState.SILENT,
        submission_artifacts={"board_application_id": "linear-9870", "retry_count": 0},
        notes="Last contact 6 days ago — needs followup.",
        created_at=_ago(days=10),
        updated_at=_ago(days=6),
    ),
    # 5 · Notion — APPLIED (no movement)
    Application(
        id=5,
        user_id=1,
        job_id=104,
        company="Notion",
        role="Senior Backend Engineer",
        team="Platform",
        location="San Francisco, CA · Hybrid",
        salary_min=250_000,
        salary_max=300_000,
        equity_pct=0.04,
        applied_at=_ago(days=7),
        board=ApplicationBoard.LEVER,
        external_url="https://jobs.lever.co/notion/abc-789/applications/9988",
        status=ApplicationStatus.APPLIED,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={"board_application_id": "9988", "retry_count": 0},
        notes=None,
        created_at=_ago(days=7),
        updated_at=_ago(days=7),
    ),
    # 6 · Plaid — APPLIED (referral requested)
    Application(
        id=6,
        user_id=1,
        job_id=106,
        company="Plaid",
        role="Staff Engineer",
        team="Risk Platform",
        location="San Francisco, CA · Remote",
        salary_min=270_000,
        salary_max=320_000,
        equity_pct=0.06,
        applied_at=_ago(days=5),
        board=ApplicationBoard.GREENHOUSE,
        external_url="https://plaid.com/jobs/applications/77100/zzz",
        status=ApplicationStatus.APPLIED,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.REQUESTED,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={"board_application_id": "7710089", "retry_count": 0},
        notes="Pinged Daniel for referral 4d ago.",
        created_at=_ago(days=5),
        updated_at=_ago(days=4),
    ),
    # 7 · Ramp — RECRUITER_SCREEN (docs stale: bullets edited after generation)
    Application(
        id=7,
        user_id=1,
        job_id=107,
        company="Ramp",
        role="Engineering Manager",
        team="Spend Platform",
        location="New York, NY · Hybrid",
        salary_min=260_000,
        salary_max=320_000,
        equity_pct=0.05,
        applied_at=_ago(days=14),
        board=ApplicationBoard.LEVER,
        external_url="https://jobs.lever.co/ramp/abcde/applications/1112",
        status=ApplicationStatus.RECRUITER_SCREEN,
        closed_reason=None,
        docs_state=DocsState.STALE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.RESPONDED,
        submission_artifacts={"board_application_id": "ramp-1112", "retry_count": 0},
        notes="Docs need re-tailor — bullets edited Apr 20.",
        created_at=_ago(days=14),
        updated_at=_ago(days=2),
    ),
    # 8 · Discord — ONSITE_LOOP (onsite scheduled in 3 days)
    Application(
        id=8,
        user_id=1,
        job_id=108,
        company="Discord",
        role="Senior Backend Engineer",
        team="Relevance",
        location="San Francisco, CA · Hybrid",
        salary_min=260_000,
        salary_max=310_000,
        equity_pct=0.04,
        applied_at=_ago(days=32),
        board=ApplicationBoard.LEVER,
        external_url="https://jobs.lever.co/discord/aa11/applications/4455",
        status=ApplicationStatus.ONSITE_LOOP,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.RESPONDED,
        submission_artifacts={"board_application_id": "discord-4455", "retry_count": 0},
        notes="Onsite May 3. 4 panels: system design, ML basics, behavioral, hiring manager.",
        created_at=_ago(days=33),
        updated_at=_ago(days=4),
    ),
    # 9 · Snowflake — CLOSED (rejected after recruiter screen)
    Application(
        id=9,
        user_id=1,
        job_id=109,
        company="Snowflake",
        role="Senior ML Engineer",
        team="Cortex",
        location="San Mateo, CA · Hybrid",
        salary_min=240_000,
        salary_max=290_000,
        equity_pct=0.03,
        applied_at=_ago(days=45),
        board=ApplicationBoard.WORKDAY,
        external_url="https://snowflake.wd1.myworkdayjobs.com/applications/JR-12345",
        status=ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.REJECTED_BY_THEM,
        docs_state=DocsState.READY,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.RESPONDED,
        submission_artifacts={
            "board_application_id": "wd-snow-99812-aaa-bbb-ccc",
            "retry_count": 0,
        },
        notes="Rejected after recruiter screen — bar bias toward more Snowflake-internal experience.",
        created_at=_ago(days=46),
        updated_at=_ago(days=38),
    ),
    # 10 · Airbnb — CLOSED (ghosted after submission)
    Application(
        id=10,
        user_id=1,
        job_id=110,
        company="Airbnb",
        role="Senior Backend Engineer",
        team="Trust",
        location="San Francisco, CA · Hybrid",
        salary_min=230_000,
        salary_max=280_000,
        equity_pct=0.03,
        applied_at=_ago(days=60),
        board=ApplicationBoard.GREENHOUSE,
        external_url="https://airbnb.com/jobs/applications/99211/zzz",
        status=ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.GHOSTED,
        docs_state=DocsState.READY,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.SILENT,
        submission_artifacts={"board_application_id": "9921100", "retry_count": 0},
        notes="No response in 60 days; auto-marked ghosted.",
        created_at=_ago(days=61),
        updated_at=_ago(days=30),
    ),
    # 11 · Databricks — CLOSED (withdrawn — comp gap)
    Application(
        id=11,
        user_id=1,
        job_id=111,
        company="Databricks",
        role="Founding Engineer",
        team="Lakehouse Apps",
        location="Mountain View, CA",
        salary_min=240_000,
        salary_max=300_000,
        equity_pct=0.03,
        applied_at=_ago(days=50),
        board=ApplicationBoard.WORKDAY,
        external_url="https://databricks.wd1.myworkdayjobs.com/applications/JR-99999",
        status=ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.WITHDRAWN_BY_ME,
        docs_state=DocsState.READY,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.RESPONDED,
        submission_artifacts={
            "board_application_id": "wd-db-11223-aaa-bbb",
            "retry_count": 0,
        },
        notes="Withdrew — comp expectation gap (offer would top out at $260k).",
        created_at=_ago(days=51),
        updated_at=_ago(days=40),
    ),
    # 12 · Cresta — APPLIED (docs failed; needs retry)
    Application(
        id=12,
        user_id=1,
        job_id=112,
        company="Cresta",
        role="Senior ML Engineer",
        team="Coaching Platform",
        location="San Francisco, CA · Remote",
        salary_min=230_000,
        salary_max=290_000,
        equity_pct=0.06,
        applied_at=_ago(days=1),
        board=ApplicationBoard.GREENHOUSE,
        external_url="https://cresta.com/jobs/applications/aa9912/zzz",
        status=ApplicationStatus.APPLIED,
        closed_reason=None,
        docs_state=DocsState.FAILED,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={"board_application_id": "cresta-12345", "retry_count": 1},
        notes="Resume Typst compile failed once; manually patched and re-submitted.",
        created_at=_ago(days=2),
        updated_at=_ago(days=1),
    ),
    # 13 · Mercury — DRAFT (manual review-and-apply in flight)
    Application(
        id=13,
        user_id=1,
        job_id=113,
        company="Mercury",
        role="Senior Backend Engineer",
        team="Card Platform",
        location="San Francisco, CA · Hybrid",
        salary_min=240_000,
        salary_max=290_000,
        equity_pct=0.05,
        applied_at=None,
        board=ApplicationBoard.GREENHOUSE,
        external_url=None,
        status=ApplicationStatus.DRAFT,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={},
        notes=None,
        created_at=_ago(days=1),
        updated_at=_ago(hours=4),
    ),
    # 14 · Modal — DRAFT (auto-apply queued; last_failure populated for stuck-queue card)
    Application(
        id=14,
        user_id=1,
        job_id=114,
        company="Modal",
        role="Founding Engineer",
        team="Runtime",
        location="San Francisco, CA · Hybrid",
        salary_min=240_000,
        salary_max=310_000,
        equity_pct=0.08,
        applied_at=None,
        board=ApplicationBoard.ASHBY,
        external_url=None,
        status=ApplicationStatus.DRAFT,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={
            "retry_count": 2,
            "last_failure": {
                "kind": "auth_required",
                "message": "Ashby session expired — reconnect Ashby to retry.",
                "captured_at": _ago(hours=2).isoformat(),
            },
        },
        notes=None,
        created_at=_ago(hours=18),
        updated_at=_ago(hours=2),
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# ~20 Contacts (per SAMPLE_DATA.md § G)
# Mix of types: 8 RECRUITER, 7 EMPLOYEE, 3 HIRING_MANAGER, 2 HR.
# ─────────────────────────────────────────────────────────────────────────

CONTACTS: list[Contact] = [
    # Anthropic warm intro
    Contact(
        id=201,
        user_id=1,
        type=ContactType.EMPLOYEE,
        name="Priya Subramanian",
        title="Staff Research Engineer",
        company="Anthropic",
        linkedin_url="https://linkedin.com/in/priyasubramanian",
        linkedin_id="priyasubramanian",
        linkedin_degree="1st",
        email=None,
        relationship="warm",
        source="manual",
        notes="Northeastern grad school. Strong advocate. Has referred 4 hires this year.",
        last_touch_at=_ago(days=3),
        created_at=_ago(days=200),
        updated_at=_ago(days=3),
    ),
    # Linear warm intro
    Contact(
        id=202,
        user_id=1,
        type=ContactType.EMPLOYEE,
        name="Daniel Kim",
        title="Senior Engineer",
        company="Linear",
        linkedin_url="https://linkedin.com/in/danielkim-sf",
        linkedin_id="danielkim-sf",
        linkedin_degree="2nd · via Priya",
        email=None,
        relationship="warm",
        source="outreach",
        notes="Mutual connection through Priya. Referred Shyam to founding-eng search.",
        last_touch_at=_ago(days=8),
        created_at=_ago(days=180),
        updated_at=_ago(days=8),
    ),
    # Stripe recruiter (Atlas)
    Contact(
        id=203,
        user_id=1,
        type=ContactType.RECRUITER,
        name="Sarah Park",
        title="Senior Recruiter",
        company="Stripe",
        linkedin_url="https://linkedin.com/in/sarah-park-stripe",
        linkedin_id="sarah-park-stripe",
        linkedin_degree="2nd",
        email="[email protected]",
        relationship="cold",
        source="outreach",
        notes="Reached out about Atlas role.",
        last_touch_at=_ago(days=2),
        created_at=_ago(days=4),
        updated_at=_ago(days=2),
    ),
    # Anthropic recruiter
    Contact(
        id=204,
        user_id=1,
        type=ContactType.RECRUITER,
        name="Marcus Chen",
        title="Talent Partner",
        company="Anthropic",
        linkedin_url="https://linkedin.com/in/marcuschen-anthropic",
        linkedin_id="marcuschen-anthropic",
        linkedin_degree="1st",
        email="[email protected]",
        relationship="warm",
        source="outreach",
        notes="Primary recruiter; warm following Priya's referral.",
        last_touch_at=_ago(days=2),
        created_at=_ago(days=22),
        updated_at=_ago(days=2),
    ),
    # Anthropic onsite coordinator (HR)
    Contact(
        id=205,
        user_id=1,
        type=ContactType.HR,
        name="Allison Tate",
        title="Onsite Coordinator",
        company="Anthropic",
        linkedin_url=None,
        linkedin_id=None,
        linkedin_degree=None,
        email="[email protected]",
        relationship="cold",
        source="outreach",
        notes="Coordinator for May 8 onsite.",
        last_touch_at=_ago(days=2),
        created_at=_ago(days=10),
        updated_at=_ago(days=2),
    ),
    # Anthropic EM (HIRING_MANAGER)
    Contact(
        id=206,
        user_id=1,
        type=ContactType.HIRING_MANAGER,
        name="James Holloway",
        title="Engineering Manager · Inference Platform",
        company="Anthropic",
        linkedin_url="https://linkedin.com/in/jamesholloway-anthropic",
        linkedin_id="jamesholloway-anthropic",
        linkedin_degree="1st",
        email=None,
        relationship="warm",
        source="outreach",
        notes="EM for the role; Shyam met him in 30-min chat last week.",
        last_touch_at=_ago(days=4),
        created_at=_ago(days=18),
        updated_at=_ago(days=4),
    ),
    # Figma recruiter
    Contact(
        id=207,
        user_id=1,
        type=ContactType.RECRUITER,
        name="Jenna Reyes",
        title="Senior Recruiter",
        company="Figma",
        linkedin_url="https://linkedin.com/in/jennareyes-figma",
        linkedin_id="jennareyes-figma",
        linkedin_degree="1st",
        email="[email protected]",
        relationship="warm",
        source="outreach",
        notes="Carried offer paperwork.",
        last_touch_at=_ago(days=1),
        created_at=_ago(days=30),
        updated_at=_ago(days=1),
    ),
    # Figma EM (HIRING_MANAGER)
    Contact(
        id=208,
        user_id=1,
        type=ContactType.HIRING_MANAGER,
        name="Tomás Diaz",
        title="Engineering Manager · Identity",
        company="Figma",
        linkedin_url="https://linkedin.com/in/tomas-diaz-figma",
        linkedin_id="tomas-diaz-figma",
        linkedin_degree="1st",
        email=None,
        relationship="warm",
        source="outreach",
        notes="Hiring manager; advocate for the offer level.",
        last_touch_at=_ago(days=3),
        created_at=_ago(days=28),
        updated_at=_ago(days=3),
    ),
    # Figma HR (offer paperwork)
    Contact(
        id=209,
        user_id=1,
        type=ContactType.HR,
        name="Rebecca Lin",
        title="Total Rewards Partner",
        company="Figma",
        linkedin_url=None,
        linkedin_id=None,
        linkedin_degree=None,
        email="[email protected]",
        relationship="cold",
        source="manual",
        notes="Offer paperwork.",
        last_touch_at=_ago(days=1),
        created_at=_ago(days=4),
        updated_at=_ago(days=1),
    ),
    # Notion sourcer (RECRUITER)
    Contact(
        id=210,
        user_id=1,
        type=ContactType.RECRUITER,
        name="Eli Brooks",
        title="Sourcer",
        company="Notion",
        linkedin_url="https://linkedin.com/in/eli-brooks-notion",
        linkedin_id="eli-brooks-notion",
        linkedin_degree="3rd",
        email=None,
        relationship="cold",
        source="outreach",
        notes="Sourced via LinkedIn DM.",
        last_touch_at=_ago(days=7),
        created_at=_ago(days=8),
        updated_at=_ago(days=7),
    ),
    # Plaid alumni (EMPLOYEE)
    Contact(
        id=211,
        user_id=1,
        type=ContactType.EMPLOYEE,
        name="Daniel Volkov",
        title="Staff Engineer",
        company="Plaid",
        linkedin_url="https://linkedin.com/in/danielvolkov",
        linkedin_id="danielvolkov",
        linkedin_degree="1st",
        email=None,
        relationship="warm",
        source="manual",
        notes="Worked with Shyam at Plaid 2018-2020. Mutual referral interest.",
        last_touch_at=_ago(days=4),
        created_at=_ago(days=300),
        updated_at=_ago(days=4),
    ),
    # Linear EM (HIRING_MANAGER)
    Contact(
        id=212,
        user_id=1,
        type=ContactType.HIRING_MANAGER,
        name="Alex Stone",
        title="Engineering Manager · Search",
        company="Linear",
        linkedin_url="https://linkedin.com/in/alexstone-linear",
        linkedin_id="alexstone-linear",
        linkedin_degree="2nd",
        email=None,
        relationship="cold",
        source="outreach",
        notes="Founding-team hire; primary EM.",
        last_touch_at=_ago(days=10),
        created_at=_ago(days=12),
        updated_at=_ago(days=10),
    ),
    # Discord recruiter
    Contact(
        id=213,
        user_id=1,
        type=ContactType.RECRUITER,
        name="Kira Patel",
        title="Senior Recruiter",
        company="Discord",
        linkedin_url="https://linkedin.com/in/kirapatel-discord",
        linkedin_id="kirapatel-discord",
        linkedin_degree="2nd",
        email="[email protected]",
        relationship="cold",
        source="outreach",
        notes="Coordinated onsite logistics.",
        last_touch_at=_ago(days=3),
        created_at=_ago(days=33),
        updated_at=_ago(days=3),
    ),
    # Snowflake recruiter (closed app)
    Contact(
        id=214,
        user_id=1,
        type=ContactType.RECRUITER,
        name="Henry Walsh",
        title="Recruiter",
        company="Snowflake",
        linkedin_url="https://linkedin.com/in/henrywalsh-snow",
        linkedin_id="henrywalsh-snow",
        linkedin_degree="3rd",
        email=None,
        relationship="cold",
        source="outreach",
        notes="Reject-bearer.",
        last_touch_at=_ago(days=38),
        created_at=_ago(days=46),
        updated_at=_ago(days=38),
    ),
    # Plaid recruiter
    Contact(
        id=215,
        user_id=1,
        type=ContactType.RECRUITER,
        name="Sophia Grant",
        title="Talent Partner",
        company="Plaid",
        linkedin_url="https://linkedin.com/in/sophiagrant-plaid",
        linkedin_id="sophiagrant-plaid",
        linkedin_degree="1st",
        email="[email protected]",
        relationship="warm",
        source="outreach",
        notes="Cold reach but warmed via Daniel Volkov referral context.",
        last_touch_at=_ago(days=5),
        created_at=_ago(days=6),
        updated_at=_ago(days=5),
    ),
    # Ramp recruiter
    Contact(
        id=216,
        user_id=1,
        type=ContactType.RECRUITER,
        name="Owen Harper",
        title="Senior Recruiter",
        company="Ramp",
        linkedin_url="https://linkedin.com/in/owen-harper-ramp",
        linkedin_id="owen-harper-ramp",
        linkedin_degree="3rd",
        email="[email protected]",
        relationship="cold",
        source="outreach",
        notes="Coordinating EM intro.",
        last_touch_at=_ago(days=2),
        created_at=_ago(days=15),
        updated_at=_ago(days=2),
    ),
    # Snowflake HIRING_MANAGER
    Contact(
        id=217,
        user_id=1,
        type=ContactType.HIRING_MANAGER,
        name="Mei Lin",
        title="Director · Cortex Platform",
        company="Snowflake",
        linkedin_url="https://linkedin.com/in/meilin-snow",
        linkedin_id="meilin-snow",
        linkedin_degree="3rd",
        email=None,
        relationship="cold",
        source="manual",
        notes="Hiring manager on closed app.",
        last_touch_at=_ago(days=42),
        created_at=_ago(days=46),
        updated_at=_ago(days=42),
    ),
    # Stripe Atlas employee (mutual coffee chat)
    Contact(
        id=218,
        user_id=1,
        type=ContactType.EMPLOYEE,
        name="Jordan Reeves",
        title="Senior Engineer · Atlas",
        company="Stripe",
        linkedin_url="https://linkedin.com/in/jordan-reeves",
        linkedin_id="jordan-reeves",
        linkedin_degree="2nd · via Daniel",
        email=None,
        relationship="warm",
        source="outreach",
        notes="Coffee chat about Atlas team scope.",
        last_touch_at=_ago(days=5),
        created_at=_ago(days=8),
        updated_at=_ago(days=5),
    ),
    # Vercel employee (cold outreach saved-job followup)
    Contact(
        id=219,
        user_id=1,
        type=ContactType.EMPLOYEE,
        name="Mara Cohen",
        title="Senior Engineer · Edge",
        company="Vercel",
        linkedin_url="https://linkedin.com/in/maracohen",
        linkedin_id="maracohen",
        linkedin_degree="2nd",
        email=None,
        relationship="cold",
        source="outreach",
        notes="Cold reach; coffee chat to learn about Edge team.",
        last_touch_at=_ago(days=11),
        created_at=_ago(days=12),
        updated_at=_ago(days=11),
    ),
    # Notion EMPLOYEE alumni
    Contact(
        id=220,
        user_id=1,
        type=ContactType.EMPLOYEE,
        name="Hassan Mehmood",
        title="Staff Engineer",
        company="Notion",
        linkedin_url="https://linkedin.com/in/hassanmehmood",
        linkedin_id="hassanmehmood",
        linkedin_degree="1st",
        email=None,
        relationship="warm",
        source="manual",
        notes="Capital One alumni; happy to refer when role opens.",
        last_touch_at=_ago(days=12),
        created_at=_ago(days=400),
        updated_at=_ago(days=12),
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# ~25 ContactApplicationLink (per SAMPLE_DATA.md § G)
# ─────────────────────────────────────────────────────────────────────────

CONTACT_APPLICATION_LINKS: list[ContactApplicationLink] = [
    # Anthropic (4 contacts on app 2)
    ContactApplicationLink(
        id=301,
        application_id=2,
        contact_id=201,  # Priya
        referral_state=ReferralState.PROVIDED,
        introduced_at=_ago(days=22),
        notes="Referred via LinkedIn DM Apr 8.",
        created_at=_ago(days=23),
        updated_at=_ago(days=22),
    ),
    ContactApplicationLink(
        id=302,
        application_id=2,
        contact_id=204,  # Marcus (recruiter)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=20),
        notes=None,
        created_at=_ago(days=20),
        updated_at=_ago(days=2),
    ),
    ContactApplicationLink(
        id=303,
        application_id=2,
        contact_id=205,  # Allison (HR)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=10),
        notes=None,
        created_at=_ago(days=10),
        updated_at=_ago(days=2),
    ),
    ContactApplicationLink(
        id=304,
        application_id=2,
        contact_id=206,  # James (EM)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=18),
        notes="EM intro chat Apr 12.",
        created_at=_ago(days=18),
        updated_at=_ago(days=4),
    ),
    # Figma (3 contacts on app 1)
    ContactApplicationLink(
        id=305,
        application_id=1,
        contact_id=207,  # Jenna (recruiter)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=29),
        notes=None,
        created_at=_ago(days=29),
        updated_at=_ago(days=1),
    ),
    ContactApplicationLink(
        id=306,
        application_id=1,
        contact_id=208,  # Tomás (EM)
        referral_state=ReferralState.PROVIDED,
        introduced_at=_ago(days=29),
        notes="Internal referral by hiring manager.",
        created_at=_ago(days=29),
        updated_at=_ago(days=3),
    ),
    ContactApplicationLink(
        id=307,
        application_id=1,
        contact_id=209,  # Rebecca (HR)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=4),
        notes=None,
        created_at=_ago(days=4),
        updated_at=_ago(days=1),
    ),
    # Stripe (2 contacts on app 3)
    ContactApplicationLink(
        id=308,
        application_id=3,
        contact_id=203,  # Sarah (recruiter)
        referral_state=ReferralState.REQUESTED,
        introduced_at=_ago(days=3),
        notes="Recruiter reached out from sourcing.",
        created_at=_ago(days=3),
        updated_at=_ago(days=2),
    ),
    ContactApplicationLink(
        id=309,
        application_id=3,
        contact_id=218,  # Jordan (Atlas employee)
        referral_state=ReferralState.IN_FLIGHT,
        introduced_at=_ago(days=8),
        notes="Coffee chat first; will refer formally next week.",
        created_at=_ago(days=8),
        updated_at=_ago(days=5),
    ),
    # Linear (2 contacts on app 4)
    ContactApplicationLink(
        id=310,
        application_id=4,
        contact_id=202,  # Daniel
        referral_state=ReferralState.PROVIDED,
        introduced_at=_ago(days=11),
        notes="Referred via Linear's referral form.",
        created_at=_ago(days=11),
        updated_at=_ago(days=11),
    ),
    ContactApplicationLink(
        id=311,
        application_id=4,
        contact_id=212,  # Alex (EM)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=10),
        notes=None,
        created_at=_ago(days=10),
        updated_at=_ago(days=10),
    ),
    # Notion (2 contacts on app 5)
    ContactApplicationLink(
        id=312,
        application_id=5,
        contact_id=210,  # Eli (sourcer)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=8),
        notes=None,
        created_at=_ago(days=8),
        updated_at=_ago(days=7),
    ),
    ContactApplicationLink(
        id=313,
        application_id=5,
        contact_id=220,  # Hassan
        referral_state=ReferralState.IN_FLIGHT,
        introduced_at=_ago(days=12),
        notes="Hassan offered to refer once role opens.",
        created_at=_ago(days=12),
        updated_at=_ago(days=10),
    ),
    # Plaid (2 contacts on app 6)
    ContactApplicationLink(
        id=314,
        application_id=6,
        contact_id=211,  # Daniel V
        referral_state=ReferralState.REQUESTED,
        introduced_at=_ago(days=4),
        notes="Asked for referral via LinkedIn DM.",
        created_at=_ago(days=4),
        updated_at=_ago(days=4),
    ),
    ContactApplicationLink(
        id=315,
        application_id=6,
        contact_id=215,  # Sophia (recruiter)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=5),
        notes=None,
        created_at=_ago(days=5),
        updated_at=_ago(days=5),
    ),
    # Ramp (1 contact on app 7)
    ContactApplicationLink(
        id=316,
        application_id=7,
        contact_id=216,  # Owen
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=14),
        notes=None,
        created_at=_ago(days=14),
        updated_at=_ago(days=2),
    ),
    # Discord (1 contact on app 8)
    ContactApplicationLink(
        id=317,
        application_id=8,
        contact_id=213,  # Kira
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=33),
        notes="Onsite scheduling.",
        created_at=_ago(days=33),
        updated_at=_ago(days=3),
    ),
    # Snowflake (2 contacts on app 9 — closed)
    ContactApplicationLink(
        id=318,
        application_id=9,
        contact_id=214,  # Henry
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=46),
        notes=None,
        created_at=_ago(days=46),
        updated_at=_ago(days=38),
    ),
    ContactApplicationLink(
        id=319,
        application_id=9,
        contact_id=217,  # Mei (HM)
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=42),
        notes=None,
        created_at=_ago(days=42),
        updated_at=_ago(days=42),
    ),
    # Airbnb (no contacts — pure cold submission, ghosted)
    # Databricks app 11 — no contacts (withdrew before recruiter intro)
    # Cresta app 12 — no contacts
    # Mercury DRAFT app 13 — no contacts
    # Modal DRAFT app 14 — no contacts (auto-apply path)
    # Vercel saved (no app yet)
    ContactApplicationLink(
        id=320,
        application_id=5,
        contact_id=219,  # Mara — extra cross-app
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=11),
        notes="Cold-reach; suggested talking when role opens.",
        created_at=_ago(days=11),
        updated_at=_ago(days=11),
    ),
    # Cross-application: Daniel V also at Stripe (recurring contact)
    ContactApplicationLink(
        id=321,
        application_id=3,
        contact_id=211,  # Daniel V also helps at Stripe
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=4),
        notes="Provided context on Atlas team culture.",
        created_at=_ago(days=4),
        updated_at=_ago(days=4),
    ),
    # Daniel Kim also at Linear app 4 (cross with 310)
    ContactApplicationLink(
        id=322,
        application_id=4,
        contact_id=220,  # Hassan offered Linear context too
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=12),
        notes=None,
        created_at=_ago(days=12),
        updated_at=_ago(days=12),
    ),
    # Mercury DRAFT — Hassan at Notion offered to introduce
    ContactApplicationLink(
        id=323,
        application_id=13,
        contact_id=220,
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=1),
        notes="Hassan said he knows the Mercury card-platform EM.",
        created_at=_ago(days=1),
        updated_at=_ago(hours=4),
    ),
    # Discord (extra — Daniel V context)
    ContactApplicationLink(
        id=324,
        application_id=8,
        contact_id=211,
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=33),
        notes=None,
        created_at=_ago(days=33),
        updated_at=_ago(days=33),
    ),
    # Stripe Atlas — Sarah Park brought in James-equivalent (Marcus from Anthropic helped Stripe context)
    ContactApplicationLink(
        id=325,
        application_id=3,
        contact_id=204,
        referral_state=ReferralState.NONE,
        introduced_at=_ago(days=2),
        notes="Marcus (Anthropic recruiter) chats periodically; mentioned Stripe contact.",
        created_at=_ago(days=2),
        updated_at=_ago(days=2),
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# ~40 OutreachMessages (per SAMPLE_DATA.md § H)
# DRAFT(4) + QUEUED(3) + SENT(18) + OPENED(5) + REPLIED(8) + BOUNCED(2) = 40
# ─────────────────────────────────────────────────────────────────────────


def _om(
    id_: int,
    contact_id: int,
    application_id: int | None,
    intent: OutreachIntent,
    status: OutreachStatus,
    body: str,
    *,
    channel: str = "linkedin_dm",
    subject: str | None = None,
    sent_days_ago: int | None = None,
    replied_days_ago: int | None = None,
    opened_days_ago: int | None = None,
    ai_generated: bool = True,
    human_edited: bool = False,
    drafted_by_model: str | None = "claude-3.5-sonnet-20250219",
) -> OutreachMessage:
    sent_at = _ago(days=sent_days_ago) if sent_days_ago is not None else None
    replied_at = _ago(days=replied_days_ago) if replied_days_ago is not None else None
    opened_at = _ago(days=opened_days_ago) if opened_days_ago is not None else None
    return OutreachMessage(
        id=id_,
        user_id=1,
        contact_id=contact_id,
        application_id=application_id,
        intent=intent,
        channel=channel,
        subject=subject,
        body=body,
        status=status,
        sent_at=sent_at,
        opened_at=opened_at,
        replied_at=replied_at,
        response_summary=None,
        ai_generated=ai_generated,
        human_edited=human_edited,
        drafted_by_model=drafted_by_model,
        created_at=_ago(days=(sent_days_ago or 1) + 1),
        updated_at=_ago(
            days=replied_days_ago if replied_days_ago is not None else (sent_days_ago or 1)
        ),
    )


OUTREACH_MESSAGES: list[OutreachMessage] = [
    # === REPLIED (8) ===
    _om(
        501,
        201,
        2,
        OutreachIntent.REFERRAL_REQUEST,
        OutreachStatus.REPLIED,
        "Hey Priya — hope grad-school crew is well. Anthropic posted a Senior ML Eng "
        "role on the Inference Platform team that lines up with my Intuit GenAI work. "
        "Would you be open to referring me?",
        sent_days_ago=23,
        replied_days_ago=22,
    ),
    _om(
        502,
        211,
        6,
        OutreachIntent.REFERRAL_REQUEST,
        OutreachStatus.REPLIED,
        "Hey Daniel — Plaid posted a Staff Eng role on Risk Platform. "
        "Would you be open to a referral?",
        sent_days_ago=6,
        replied_days_ago=4,
    ),
    _om(
        503,
        202,
        4,
        OutreachIntent.REFERRAL_REQUEST,
        OutreachStatus.REPLIED,
        "Hey Daniel — Linear is hiring a founding engineer for the Search team. "
        "Would love a referral if you're up for it.",
        sent_days_ago=11,
        replied_days_ago=11,
    ),
    _om(
        504,
        218,
        3,
        OutreachIntent.INTRO,
        OutreachStatus.REPLIED,
        "Hi Jordan — saw the Atlas Senior ML Eng posting and would love your read on "
        "the team's day-to-day. Free for a 15-min coffee chat next week?",
        sent_days_ago=8,
        replied_days_ago=7,
    ),
    _om(
        505,
        220,
        5,
        OutreachIntent.REFERRAL_REQUEST,
        OutreachStatus.REPLIED,
        "Hassan — Notion just opened a Sr Backend Plat role. Would you mind referring? "
        "Capital One personalization work transfers cleanly.",
        sent_days_ago=12,
        replied_days_ago=10,
    ),
    _om(
        506,
        220,
        4,
        OutreachIntent.INTRO,
        OutreachStatus.REPLIED,
        "Hassan — Linear is also on my list. Any read on the founding-engineer culture?",
        sent_days_ago=12,
        replied_days_ago=12,
    ),
    _om(
        507,
        220,
        13,
        OutreachIntent.INTRO,
        OutreachStatus.REPLIED,
        "Hassan — long shot, do you know anyone on Mercury's card-platform team? "
        "Their Sr Backend role looks great.",
        sent_days_ago=1,
        replied_days_ago=0,
    ),
    _om(
        508,
        211,
        3,
        OutreachIntent.INTRO,
        OutreachStatus.REPLIED,
        "Daniel — separately from Plaid, do you have read on Stripe Atlas culture? "
        "Talking to them this week.",
        sent_days_ago=4,
        replied_days_ago=3,
    ),
    # === SENT (18) — sent, no reply yet ===
    _om(
        509,
        201,
        2,
        OutreachIntent.THANK_YOU,
        OutreachStatus.SENT,
        "Priya — wanted to thank you for the referral and the warm intro to Marcus. Onsite May 8.",
        sent_days_ago=20,
    ),
    _om(
        510,
        205,
        2,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Hi Allison — looking forward to the May 8 onsite. Quick question on the "
        "agenda: is there a system design panel?",
        sent_days_ago=2,
    ),
    _om(
        511,
        207,
        1,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Hi Jenna — just confirming the offer details email — should I expect "
        "the formal letter by Wed?",
        sent_days_ago=1,
    ),
    _om(
        512,
        213,
        8,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Hi Kira — confirming the May 3 onsite logistics. Looking forward to it.",
        sent_days_ago=3,
    ),
    _om(
        513,
        215,
        6,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Sophia — checking in on the recruiter screen scheduling for the Plaid app. "
        "Daniel mentioned you were the right point of contact.",
        sent_days_ago=4,
    ),
    _om(
        514,
        216,
        7,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Owen — checking in on the EM intro for the Ramp role. Any update?",
        sent_days_ago=2,
    ),
    _om(
        515,
        219,
        None,
        OutreachIntent.INTRO,
        OutreachStatus.SENT,
        "Mara — saw your work on Edge runtime; would love a quick coffee chat on "
        "the Edge team's roadmap.",
        sent_days_ago=11,
    ),
    _om(
        516,
        203,
        3,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Hi Sarah — confirming May 2 recruiter call.",
        sent_days_ago=2,
    ),
    _om(
        517,
        204,
        2,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Marcus — quick note re onsite — any prep materials I should review?",
        sent_days_ago=2,
    ),
    _om(
        518,
        206,
        2,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "James — looking forward to the onsite. Wanted to follow up on the inference "
        "scaling questions you raised in our chat.",
        sent_days_ago=4,
    ),
    _om(
        519,
        208,
        1,
        OutreachIntent.THANK_YOU,
        OutreachStatus.SENT,
        "Tomás — thanks for the offer-stage advocacy. Hope to be on the team soon.",
        sent_days_ago=3,
    ),
    _om(
        520,
        209,
        1,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Rebecca — quick question about the equity vesting schedule on the offer.",
        sent_days_ago=1,
    ),
    _om(
        521,
        218,
        3,
        OutreachIntent.THANK_YOU,
        OutreachStatus.SENT,
        "Jordan — thanks for the team context, that helped a lot. Looking forward to "
        "next week's recruiter call.",
        sent_days_ago=5,
    ),
    _om(
        522,
        211,
        13,
        OutreachIntent.INTRO,
        OutreachStatus.SENT,
        "Daniel — also working on a Mercury app — any read on the card-platform team?",
        sent_days_ago=1,
    ),
    _om(
        523,
        220,
        5,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.SENT,
        "Hassan — checking in on the Notion referral; happy to share my updated CV if helpful.",
        sent_days_ago=10,
    ),
    _om(
        524,
        213,
        8,
        OutreachIntent.THANK_YOU,
        OutreachStatus.SENT,
        "Kira — appreciated the thoughtful feedback on the panels.",
        sent_days_ago=14,
    ),
    _om(
        525,
        207,
        1,
        OutreachIntent.THANK_YOU,
        OutreachStatus.SENT,
        "Jenna — thanks for the smooth coordination through the loop.",
        sent_days_ago=8,
    ),
    _om(
        526,
        215,
        6,
        OutreachIntent.INTRO,
        OutreachStatus.SENT,
        "Sophia — separately, would love to hear the team's read on platform "
        "investment going into Q3.",
        sent_days_ago=3,
    ),
    # === OPENED (5) — LinkedIn open-receipt fired, no reply yet ===
    _om(
        527,
        210,
        5,
        OutreachIntent.INTRO,
        OutreachStatus.OPENED,
        "Hi Eli — coming from your sourcing message; would love to chat about Notion's "
        "platform team.",
        sent_days_ago=7,
        opened_days_ago=6,
    ),
    _om(
        528,
        212,
        4,
        OutreachIntent.INTRO,
        OutreachStatus.OPENED,
        "Hi Alex — Linear's founding-eng search role looks like a great fit. Open to "
        "a 15-min intro chat?",
        sent_days_ago=10,
        opened_days_ago=8,
    ),
    _om(
        529,
        217,
        None,
        OutreachIntent.CHECK_IN,
        OutreachStatus.OPENED,
        "Mei — heard you're hiring on Cortex platform. Would love to revisit the Snowflake "
        "convo if scope has changed.",
        sent_days_ago=15,
        opened_days_ago=14,
    ),
    _om(
        530,
        214,
        None,
        OutreachIntent.CHECK_IN,
        OutreachStatus.OPENED,
        "Henry — checking in on what other teams might be hiring at Snowflake.",
        sent_days_ago=20,
        opened_days_ago=18,
    ),
    _om(
        531,
        219,
        None,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.OPENED,
        "Mara — quick nudge on the coffee chat. Free this Thurs?",
        sent_days_ago=4,
        opened_days_ago=3,
    ),
    # === QUEUED (3) — rate-limited, sending soon ===
    _om(
        532,
        219,
        None,
        OutreachIntent.INTRO,
        OutreachStatus.QUEUED,
        "Mara — separately on the Edge runtime question I mentioned…",
    ),
    _om(
        533,
        217,
        None,
        OutreachIntent.CHECK_IN,
        OutreachStatus.QUEUED,
        "Mei — quick ping in case the prior message got buried.",
    ),
    _om(
        534,
        211,
        13,
        OutreachIntent.REFERRAL_REQUEST,
        OutreachStatus.QUEUED,
        "Daniel — once Mercury reply lands, would love a referral if it's a fit.",
    ),
    # === DRAFT (4) — currently drafting on Outreach ===
    _om(
        535,
        211,
        6,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.DRAFT,
        "Daniel — quick check-in on the Plaid referral status. Appreciate any nudge.",
        ai_generated=True,
        human_edited=False,
    ),
    _om(
        536,
        215,
        6,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.DRAFT,
        "Hi Sophia — circling back on the Plaid Risk Platform recruiter screen.",
        ai_generated=True,
        human_edited=True,
    ),
    _om(
        537,
        220,
        5,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.DRAFT,
        "Hassan — short check-in on the Notion referral (re-tried in case prior "
        "message got buried).",
        ai_generated=True,
        human_edited=False,
    ),
    _om(
        538,
        218,
        3,
        OutreachIntent.FOLLOW_UP,
        OutreachStatus.DRAFT,
        "Jordan — given the Stripe recruiter call this week, any last context I should "
        "have on Atlas team scope?",
        ai_generated=True,
        human_edited=False,
    ),
    # === BOUNCED (2) — wrong email or LinkedIn deactivated ===
    _om(
        539,
        214,
        None,
        OutreachIntent.INTRO,
        OutreachStatus.BOUNCED,
        "Henry — was your email — bounced.",
        sent_days_ago=46,
        channel="email",
    ),
    _om(
        540,
        213,
        None,
        OutreachIntent.CHECK_IN,
        OutreachStatus.BOUNCED,
        "Kira — checking in on potential other roles.",
        sent_days_ago=8,
    ),
]


# ─────────────────────────────────────────────────────────────────────────
# ~20 EmailThreads (per SAMPLE_DATA.md § H)
# Distribution: 5 INTERVIEW_REQUEST + 4 REJECTION + 1 OFFER + 2 ASSESSMENT
# + 5 FOLLOW_UP + 3 OTHER = 20.
# ─────────────────────────────────────────────────────────────────────────


def _msg(
    sender: str,
    recipient: str,
    direction: str,
    body_preview: str,
    *,
    days_ago: int = 0,
    classification: EmailClassification = EmailClassification.OTHER,
    ai_classified: bool = True,
    message_id_external: str = "msg-stub",
) -> dict[str, object]:
    return {
        "sender": sender,
        "recipient": recipient,
        "sent_at": _ago(days=days_ago).isoformat(),
        "direction": direction,
        "body_preview": body_preview,
        "classification": classification.value,
        "ai_classified": ai_classified,
        "message_id_external": message_id_external,
    }


EMAIL_THREADS: list[EmailThread] = [
    # 1 · Anthropic — INTERVIEW_REQUEST (recruiter screen scheduling, app 2)
    EmailThread(
        id=601,
        user_id=1,
        application_id=2,
        contact_id=204,
        provider="gmail",
        thread_id_external="gmail-thread-601",
        subject="Re: Senior ML Engineer @ Anthropic",
        classification=EmailClassification.INTERVIEW_REQUEST,
        auto_classified=True,
        manually_verified=True,
        latest_message_at=_ago(days=18),
        message_count=4,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Hi Shyam — thanks for applying. Want to set up a recruiter screen?",
                days_ago=20,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-601-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Sounds good — Tues 2pm PT works.",
                days_ago=20,
                message_id_external="msg-601-2",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Confirmed for Tues 2pm. Calendar invite incoming.",
                days_ago=19,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-601-3",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Great call. Moving to onsite — sending logistics next week.",
                days_ago=18,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-601-4",
            ),
        ],
        created_at=_ago(days=20),
        updated_at=_ago(days=18),
    ),
    # 2 · Anthropic — INTERVIEW_REQUEST (onsite scheduling, app 2)
    EmailThread(
        id=602,
        user_id=1,
        application_id=2,
        contact_id=205,
        provider="gmail",
        thread_id_external="gmail-thread-602",
        subject="Anthropic onsite — May 8",
        classification=EmailClassification.INTERVIEW_REQUEST,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=2),
        message_count=6,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Pulling together May 8 onsite. Couple availability questions.",
                days_ago=10,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-602-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "All-day available, looking forward to it.",
                days_ago=10,
                message_id_external="msg-602-2",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Final agenda: 4 interviews + lunch. Sending docs.",
                days_ago=8,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-602-3",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Confirmed.",
                days_ago=8,
                message_id_external="msg-602-4",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Sending parking instructions.",
                days_ago=4,
                classification=EmailClassification.OTHER,
                message_id_external="msg-602-5",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Reminder — 9am sharp.",
                days_ago=2,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-602-6",
            ),
        ],
        created_at=_ago(days=10),
        updated_at=_ago(days=2),
    ),
    # 3 · Figma — OFFER (app 1)
    EmailThread(
        id=603,
        user_id=1,
        application_id=1,
        contact_id=207,
        provider="gmail",
        thread_id_external="gmail-thread-603",
        subject="Figma · Offer Letter Draft",
        classification=EmailClassification.OFFER,
        auto_classified=True,
        manually_verified=True,
        latest_message_at=_ago(days=2),
        message_count=4,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Verbal offer extended on yesterday's call. Drafting paperwork.",
                days_ago=2,
                classification=EmailClassification.OFFER,
                message_id_external="msg-603-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Thanks Jenna — looking forward to the formal letter.",
                days_ago=2,
                message_id_external="msg-603-2",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Total comp: $290k base + 0.04% equity. Letter coming Wed.",
                days_ago=1,
                classification=EmailClassification.OFFER,
                message_id_external="msg-603-3",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Confirmed — will respond by Thu.",
                days_ago=1,
                message_id_external="msg-603-4",
            ),
        ],
        created_at=_ago(days=3),
        updated_at=_ago(days=1),
    ),
    # 4 · Stripe — INTERVIEW_REQUEST (app 3)
    EmailThread(
        id=604,
        user_id=1,
        application_id=3,
        contact_id=203,
        provider="gmail",
        thread_id_external="gmail-thread-604",
        subject="Stripe Atlas Sr ML — Recruiter Screen",
        classification=EmailClassification.INTERVIEW_REQUEST,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=1),
        message_count=3,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Hi Shyam — would love to set up a 30-min recruiter chat for the Atlas role.",
                days_ago=2,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-604-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Tues May 2 at 3pm PT works.",
                days_ago=2,
                message_id_external="msg-604-2",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Confirmed. Looking forward.",
                days_ago=1,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-604-3",
            ),
        ],
        created_at=_ago(days=3),
        updated_at=_ago(days=1),
    ),
    # 5 · Linear — FOLLOW_UP gone silent (app 4 — drives "6D SILENT")
    EmailThread(
        id=605,
        user_id=1,
        application_id=4,
        contact_id=212,
        provider="gmail",
        thread_id_external="gmail-thread-605",
        subject="Linear Search · Founding Eng",
        classification=EmailClassification.FOLLOW_UP,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=6),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Quick chat went well — let me check on next steps internally.",
                days_ago=8,
                classification=EmailClassification.FOLLOW_UP,
                message_id_external="msg-605-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Sounds good — happy to follow up if helpful.",
                days_ago=6,
                message_id_external="msg-605-2",
            ),
        ],
        created_at=_ago(days=11),
        updated_at=_ago(days=6),
    ),
    # 6 · Notion — FOLLOW_UP (app 5)
    EmailThread(
        id=606,
        user_id=1,
        application_id=5,
        contact_id=210,
        provider="gmail",
        thread_id_external="gmail-thread-606",
        subject="Notion · Sr Backend Application",
        classification=EmailClassification.FOLLOW_UP,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=4),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Application received — team will review by end of week.",
                days_ago=7,
                classification=EmailClassification.FOLLOW_UP,
                message_id_external="msg-606-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Checking back with team — bandwidth is tight this week.",
                days_ago=4,
                classification=EmailClassification.FOLLOW_UP,
                message_id_external="msg-606-2",
            ),
        ],
        created_at=_ago(days=7),
        updated_at=_ago(days=4),
    ),
    # 7 · Plaid — FOLLOW_UP (app 6)
    EmailThread(
        id=607,
        user_id=1,
        application_id=6,
        contact_id=215,
        provider="gmail",
        thread_id_external="gmail-thread-607",
        subject="Plaid Risk Platform · Application Received",
        classification=EmailClassification.FOLLOW_UP,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=4),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Got the referral tag from Daniel. Team reviewing.",
                days_ago=4,
                classification=EmailClassification.FOLLOW_UP,
                message_id_external="msg-607-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Thanks Sophia — happy to chat anytime.",
                days_ago=4,
                message_id_external="msg-607-2",
            ),
        ],
        created_at=_ago(days=5),
        updated_at=_ago(days=4),
    ),
    # 8 · Ramp — INTERVIEW_REQUEST (app 7)
    EmailThread(
        id=608,
        user_id=1,
        application_id=7,
        contact_id=216,
        provider="gmail",
        thread_id_external="gmail-thread-608",
        subject="Ramp · EM Spend Platform",
        classification=EmailClassification.INTERVIEW_REQUEST,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=2),
        message_count=4,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Recruiter screen feedback positive. Setting up EM intro.",
                days_ago=10,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-608-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Looking forward.",
                days_ago=10,
                message_id_external="msg-608-2",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "EM available next Wed at 11am ET.",
                days_ago=4,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-608-3",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Confirmed.",
                days_ago=2,
                message_id_external="msg-608-4",
            ),
        ],
        created_at=_ago(days=11),
        updated_at=_ago(days=2),
    ),
    # 9 · Discord — INTERVIEW_REQUEST (app 8)
    EmailThread(
        id=609,
        user_id=1,
        application_id=8,
        contact_id=213,
        provider="gmail",
        thread_id_external="gmail-thread-609",
        subject="Discord onsite — May 3",
        classification=EmailClassification.INTERVIEW_REQUEST,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=4),
        message_count=3,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Onsite May 3 — 4 panels: design, ML basics, behavioral, hiring manager.",
                days_ago=14,
                classification=EmailClassification.INTERVIEW_REQUEST,
                message_id_external="msg-609-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Confirmed. Looking forward.",
                days_ago=14,
                message_id_external="msg-609-2",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Sending parking + lunch info.",
                days_ago=4,
                classification=EmailClassification.OTHER,
                message_id_external="msg-609-3",
            ),
        ],
        created_at=_ago(days=14),
        updated_at=_ago(days=4),
    ),
    # 10 · Snowflake — REJECTION (app 9 closed)
    EmailThread(
        id=610,
        user_id=1,
        application_id=9,
        contact_id=214,
        provider="gmail",
        thread_id_external="gmail-thread-610",
        subject="Re: Snowflake Cortex · Sr ML Eng",
        classification=EmailClassification.REJECTION,
        auto_classified=True,
        manually_verified=True,
        latest_message_at=_ago(days=38),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Recruiter screen feedback in. Team is moving forward with other candidates.",
                days_ago=38,
                classification=EmailClassification.REJECTION,
                message_id_external="msg-610-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Thanks for the update Henry. Open to other Snowflake teams down the road.",
                days_ago=38,
                message_id_external="msg-610-2",
            ),
        ],
        created_at=_ago(days=39),
        updated_at=_ago(days=38),
    ),
    # 11 · Airbnb — REJECTION (app 10 — auto-classified ghost / soft reject)
    EmailThread(
        id=611,
        user_id=1,
        application_id=10,
        contact_id=None,
        provider="gmail",
        thread_id_external="gmail-thread-611",
        subject="Re: Airbnb · Sr Backend",
        classification=EmailClassification.REJECTION,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=58),
        message_count=1,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Application received. Team will follow up if there's a fit.",
                days_ago=58,
                classification=EmailClassification.REJECTION,
                message_id_external="msg-611-1",
            ),
        ],
        created_at=_ago(days=58),
        updated_at=_ago(days=58),
    ),
    # 12 · Databricks — REJECTION (app 11)
    EmailThread(
        id=612,
        user_id=1,
        application_id=11,
        contact_id=None,
        provider="gmail",
        thread_id_external="gmail-thread-612",
        subject="Databricks Lakehouse · Withdrawn",
        classification=EmailClassification.REJECTION,
        auto_classified=False,
        manually_verified=True,
        latest_message_at=_ago(days=40),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Withdrawing — comp expectation gap. Thanks for the conversation.",
                days_ago=40,
                message_id_external="msg-612-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Understood — will keep in touch when scope changes.",
                days_ago=40,
                classification=EmailClassification.REJECTION,
                message_id_external="msg-612-2",
            ),
        ],
        created_at=_ago(days=40),
        updated_at=_ago(days=40),
    ),
    # 13 · Discord — REJECTION decoy follow-up (kept active for now)
    EmailThread(
        id=613,
        user_id=1,
        application_id=8,
        contact_id=None,
        provider="gmail",
        thread_id_external="gmail-thread-613",
        subject="Discord post-onsite",
        classification=EmailClassification.FOLLOW_UP,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=4),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Pulling together feedback — will share early next week.",
                days_ago=4,
                classification=EmailClassification.FOLLOW_UP,
                message_id_external="msg-613-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Thanks — looking forward.",
                days_ago=4,
                message_id_external="msg-613-2",
            ),
        ],
        created_at=_ago(days=5),
        updated_at=_ago(days=4),
    ),
    # 14 · Ramp — ASSESSMENT (take-home)
    EmailThread(
        id=614,
        user_id=1,
        application_id=7,
        contact_id=216,
        provider="gmail",
        thread_id_external="gmail-thread-614",
        subject="Ramp · take-home assignment",
        classification=EmailClassification.ASSESSMENT,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=8),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Take-home: design a spend platform shard-rebalance scheme. 4-hour cap.",
                days_ago=10,
                classification=EmailClassification.ASSESSMENT,
                message_id_external="msg-614-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Submitting today.",
                days_ago=8,
                message_id_external="msg-614-2",
            ),
        ],
        created_at=_ago(days=10),
        updated_at=_ago(days=8),
    ),
    # 15 · Discord — ASSESSMENT
    EmailThread(
        id=615,
        user_id=1,
        application_id=8,
        contact_id=213,
        provider="gmail",
        thread_id_external="gmail-thread-615",
        subject="Discord · pre-onsite take-home",
        classification=EmailClassification.ASSESSMENT,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=20),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Pre-onsite take-home: ranking-relevance prompt design. 3-hour cap.",
                days_ago=22,
                classification=EmailClassification.ASSESSMENT,
                message_id_external="msg-615-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Submitted.",
                days_ago=20,
                message_id_external="msg-615-2",
            ),
        ],
        created_at=_ago(days=22),
        updated_at=_ago(days=20),
    ),
    # 16 · Stripe — FOLLOW_UP
    EmailThread(
        id=616,
        user_id=1,
        application_id=3,
        contact_id=218,
        provider="gmail",
        thread_id_external="gmail-thread-616",
        subject="Atlas Engineer Coffee Chat",
        classification=EmailClassification.FOLLOW_UP,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=5),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Thanks for the chat. Helpful context on Atlas's tech bets.",
                days_ago=5,
                message_id_external="msg-616-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Anytime. Will refer once posting moves to the next round.",
                days_ago=5,
                classification=EmailClassification.FOLLOW_UP,
                message_id_external="msg-616-2",
            ),
        ],
        created_at=_ago(days=5),
        updated_at=_ago(days=5),
    ),
    # 17 · Plaid — FOLLOW_UP gone silent (alternate signal)
    EmailThread(
        id=617,
        user_id=1,
        application_id=6,
        contact_id=215,
        provider="gmail",
        thread_id_external="gmail-thread-617",
        subject="Plaid · Risk Platform · Coordinating Loop",
        classification=EmailClassification.FOLLOW_UP,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=4),
        message_count=2,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Pulling together loop next week.",
                days_ago=4,
                classification=EmailClassification.FOLLOW_UP,
                message_id_external="msg-617-1",
            ),
            _msg(
                "[email protected]",
                "[email protected]",
                "OUTBOUND",
                "Sounds good.",
                days_ago=4,
                message_id_external="msg-617-2",
            ),
        ],
        created_at=_ago(days=4),
        updated_at=_ago(days=4),
    ),
    # 18 · Notion — OTHER (sourcer general blast)
    EmailThread(
        id=618,
        user_id=1,
        application_id=5,
        contact_id=210,
        provider="gmail",
        thread_id_external="gmail-thread-618",
        subject="Notion · About your background",
        classification=EmailClassification.OTHER,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=8),
        message_count=1,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Your background looks great — would love to chat about a couple of teams.",
                days_ago=8,
                classification=EmailClassification.OTHER,
                message_id_external="msg-618-1",
            ),
        ],
        created_at=_ago(days=8),
        updated_at=_ago(days=8),
    ),
    # 19 · Anthropic — OTHER (calendar logistics)
    EmailThread(
        id=619,
        user_id=1,
        application_id=2,
        contact_id=205,
        provider="gmail",
        thread_id_external="gmail-thread-619",
        subject="Onsite parking & lunch options",
        classification=EmailClassification.OTHER,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=2),
        message_count=1,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Garage is on Howard. Lunch options across the street.",
                days_ago=2,
                classification=EmailClassification.OTHER,
                message_id_external="msg-619-1",
            ),
        ],
        created_at=_ago(days=2),
        updated_at=_ago(days=2),
    ),
    # 20 · Vercel — OTHER (cold sourcing — no app)
    EmailThread(
        id=620,
        user_id=1,
        application_id=None,
        contact_id=219,
        provider="gmail",
        thread_id_external="gmail-thread-620",
        subject="Vercel Edge — quick chat?",
        classification=EmailClassification.OTHER,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=_ago(days=11),
        message_count=1,
        messages=[
            _msg(
                "[email protected]",
                "[email protected]",
                "INBOUND",
                "Saw your background — happy to chat about Edge if you're interested.",
                days_ago=11,
                classification=EmailClassification.OTHER,
                message_id_external="msg-620-1",
            ),
        ],
        created_at=_ago(days=11),
        updated_at=_ago(days=11),
    ),
]


# ─────────────────────────────────────────────────────────────────────────
# AppEvent helper + ~150 timeline events (per SAMPLE_DATA.md § I)
# ─────────────────────────────────────────────────────────────────────────


def _ev(
    id_: int,
    application_id: int | None,
    kind: AppEventKind,
    days_ago: float,
    payload: dict[str, object] | None = None,
    *,
    actor: str | None = "system",
) -> AppEvent:
    """Build an AppEvent. `days_ago` may be fractional (hours)."""
    occurred = TODAY - timedelta(days=days_ago)
    return AppEvent(
        id=id_,
        user_id=1,
        application_id=application_id,
        kind=kind,
        occurred_at=occurred,
        payload=payload or {},
        actor=actor,
        created_at=occurred,
    )


# 14 applications × ~10 events each ≈ 150. Built in chunks so individual
# applications stay readable.

APP_EVENTS: list[AppEvent] = []
_eid = [700]


def _next_eid() -> int:
    _eid[0] += 1
    return _eid[0]


# App 1 — Figma — OFFER timeline (~12 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            1,
            AppEventKind.STATUS_CHANGE,
            29,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.DOCS_GENERATED,
            28.9,
            {
                "generated_document_id": 901,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.DOCS_GENERATED,
            28.9,
            {
                "generated_document_id": 902,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.STATUS_CHANGE,
            28,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.EMAIL_RECEIVED,
            22,
            {
                "thread_id": 603,
                "sender": "[email protected]",
                "subject_preview": "Re: Figma application",
                "classification": "follow_up",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.STATUS_CHANGE,
            22,
            {
                "from_status": "APPLIED",
                "to_status": "RECRUITER_SCREEN",
                "triggered_by": "auto-from-email",
            },
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.INTERVIEW_SCHEDULED,
            18,
            {"when": _ago(days=14).isoformat(), "where": "Figma SF HQ", "contact_ids": [208]},
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.STATUS_CHANGE,
            14,
            {
                "from_status": "RECRUITER_SCREEN",
                "to_status": "ONSITE_LOOP",
                "triggered_by": "manual",
            },
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.REFERRAL_PROVIDED,
            11,
            {"contact_id": 208, "provided_at": _ago(days=11).isoformat()},
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.STATUS_CHANGE,
            4,
            {
                "from_status": "ONSITE_LOOP",
                "to_status": "OFFER",
                "triggered_by": "manual",
                "notes": "Verbal offer extended on call",
            },
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.EMAIL_RECEIVED,
            2,
            {
                "thread_id": 603,
                "sender": "[email protected]",
                "subject_preview": "Figma · Offer Letter",
                "classification": "offer",
                "urgent": True,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            1,
            AppEventKind.NOTE_ADDED,
            1,
            {
                "note_text_preview": "Verbal offer Apr 28: $290k base + 0.04% — reply expected by Thu.",
                "full_note_field": "application.notes",
            },
            actor="user",
        ),
    ]
)

# App 2 — Anthropic — ONSITE_LOOP timeline (~14 events, with warm intro)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            2,
            AppEventKind.LINKEDIN_DM_SENT,
            23,
            {"outreach_message_id": 501, "contact_id": 201, "intent": "referral_request"},
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.REFERRAL_REQUESTED,
            23,
            {"contact_id": 201, "via_channel": "linkedin_dm"},
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.LINKEDIN_DM_REPLIED,
            22,
            {
                "outreach_message_id": 501,
                "contact_id": 201,
                "replied_at": _ago(days=22).isoformat(),
                "summary": "Glad to refer.",
            },
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.REFERRAL_PROVIDED,
            22,
            {"contact_id": 201, "provided_at": _ago(days=22).isoformat()},
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.STATUS_CHANGE,
            21.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.DOCS_GENERATED,
            21.4,
            {
                "generated_document_id": 903,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.DOCS_GENERATED,
            21.4,
            {
                "generated_document_id": 904,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.STATUS_CHANGE,
            21,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.EMAIL_RECEIVED,
            20,
            {
                "thread_id": 601,
                "sender": "[email protected]",
                "subject_preview": "Re: Senior ML Engineer",
                "classification": "interview_request",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.STATUS_CHANGE,
            20,
            {
                "from_status": "APPLIED",
                "to_status": "RECRUITER_SCREEN",
                "triggered_by": "auto-from-email",
            },
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.LINKEDIN_DM_SENT,
            20,
            {"outreach_message_id": 509, "contact_id": 201, "intent": "thank_you"},
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.INTERVIEW_SCHEDULED,
            18,
            {
                "when": _ago(days=-8).isoformat(),
                "where": "Anthropic SF HQ",
                "contact_ids": [206, 205],
            },
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.STATUS_CHANGE,
            18,
            {
                "from_status": "RECRUITER_SCREEN",
                "to_status": "ONSITE_LOOP",
                "triggered_by": "manual",
            },
        ),
        _ev(
            _next_eid(),
            2,
            AppEventKind.EMAIL_RECEIVED,
            2,
            {
                "thread_id": 619,
                "sender": "[email protected]",
                "subject_preview": "Onsite parking & lunch",
                "classification": "other",
                "urgent": False,
                "auto_classified": True,
            },
        ),
    ]
)

# App 3 — Stripe Atlas — RECRUITER_SCREEN (~9 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            3,
            AppEventKind.STATUS_CHANGE,
            3.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            3,
            AppEventKind.DOCS_GENERATED,
            3.4,
            {
                "generated_document_id": 905,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            3,
            AppEventKind.DOCS_GENERATED,
            3.4,
            {
                "generated_document_id": 906,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            3,
            AppEventKind.STATUS_CHANGE,
            3,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            3,
            AppEventKind.EMAIL_RECEIVED,
            2,
            {
                "thread_id": 604,
                "sender": "[email protected]",
                "subject_preview": "Stripe Atlas Sr ML — Recruiter Screen",
                "classification": "interview_request",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            3,
            AppEventKind.STATUS_CHANGE,
            2,
            {
                "from_status": "APPLIED",
                "to_status": "RECRUITER_SCREEN",
                "triggered_by": "auto-from-email",
            },
        ),
        _ev(
            _next_eid(),
            3,
            AppEventKind.LINKEDIN_DM_SENT,
            8,
            {"outreach_message_id": 504, "contact_id": 218, "intent": "intro"},
        ),
        _ev(
            _next_eid(),
            3,
            AppEventKind.LINKEDIN_DM_REPLIED,
            7,
            {"outreach_message_id": 504, "contact_id": 218, "replied_at": _ago(days=7).isoformat()},
        ),
        _ev(
            _next_eid(),
            3,
            AppEventKind.REFERRAL_REQUESTED,
            8,
            {"contact_id": 218, "via_channel": "linkedin_dm"},
        ),
    ]
)

# App 4 — Linear — RECRUITER_SCREEN, silent ≥6d (~10 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            4,
            AppEventKind.LINKEDIN_DM_SENT,
            11,
            {"outreach_message_id": 503, "contact_id": 202, "intent": "referral_request"},
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.LINKEDIN_DM_REPLIED,
            11,
            {
                "outreach_message_id": 503,
                "contact_id": 202,
                "replied_at": _ago(days=11).isoformat(),
            },
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.REFERRAL_REQUESTED,
            11,
            {"contact_id": 202, "via_channel": "linkedin_dm"},
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.REFERRAL_PROVIDED,
            11,
            {"contact_id": 202, "provided_at": _ago(days=11).isoformat()},
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.STATUS_CHANGE,
            10.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.DOCS_GENERATED,
            10.4,
            {
                "generated_document_id": 907,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.DOCS_GENERATED,
            10.4,
            {
                "generated_document_id": 908,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.STATUS_CHANGE,
            10,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.EMAIL_RECEIVED,
            8,
            {
                "thread_id": 605,
                "sender": "[email protected]",
                "subject_preview": "Linear Search · Founding Eng",
                "classification": "follow_up",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            4,
            AppEventKind.STATUS_CHANGE,
            8,
            {
                "from_status": "APPLIED",
                "to_status": "RECRUITER_SCREEN",
                "triggered_by": "auto-from-email",
            },
        ),
    ]
)

# App 5 — Notion — APPLIED (~7 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            5,
            AppEventKind.LINKEDIN_DM_SENT,
            12,
            {"outreach_message_id": 505, "contact_id": 220, "intent": "referral_request"},
        ),
        _ev(
            _next_eid(),
            5,
            AppEventKind.LINKEDIN_DM_REPLIED,
            10,
            {
                "outreach_message_id": 505,
                "contact_id": 220,
                "replied_at": _ago(days=10).isoformat(),
            },
        ),
        _ev(
            _next_eid(),
            5,
            AppEventKind.STATUS_CHANGE,
            7.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            5,
            AppEventKind.DOCS_GENERATED,
            7.4,
            {
                "generated_document_id": 909,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            5,
            AppEventKind.DOCS_GENERATED,
            7.4,
            {
                "generated_document_id": 910,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            5,
            AppEventKind.STATUS_CHANGE,
            7,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            5,
            AppEventKind.EMAIL_RECEIVED,
            7,
            {
                "thread_id": 606,
                "sender": "[email protected]",
                "subject_preview": "Notion · Sr Backend Application",
                "classification": "follow_up",
                "urgent": False,
                "auto_classified": True,
            },
        ),
    ]
)

# App 6 — Plaid — APPLIED, referral REQUESTED (~7 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            6,
            AppEventKind.LINKEDIN_DM_SENT,
            6,
            {"outreach_message_id": 502, "contact_id": 211, "intent": "referral_request"},
        ),
        _ev(
            _next_eid(),
            6,
            AppEventKind.LINKEDIN_DM_REPLIED,
            4,
            {"outreach_message_id": 502, "contact_id": 211, "replied_at": _ago(days=4).isoformat()},
        ),
        _ev(
            _next_eid(),
            6,
            AppEventKind.REFERRAL_REQUESTED,
            4,
            {"contact_id": 211, "via_channel": "linkedin_dm"},
        ),
        _ev(
            _next_eid(),
            6,
            AppEventKind.STATUS_CHANGE,
            5.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            6,
            AppEventKind.DOCS_GENERATED,
            5.4,
            {
                "generated_document_id": 911,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            6,
            AppEventKind.DOCS_GENERATED,
            5.4,
            {
                "generated_document_id": 912,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            6,
            AppEventKind.STATUS_CHANGE,
            5,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
    ]
)

# App 7 — Ramp — RECRUITER_SCREEN, docs STALE (~9 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            7,
            AppEventKind.STATUS_CHANGE,
            14.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            7,
            AppEventKind.DOCS_GENERATED,
            14.4,
            {
                "generated_document_id": 913,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            7,
            AppEventKind.DOCS_GENERATED,
            14.4,
            {
                "generated_document_id": 914,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            7,
            AppEventKind.STATUS_CHANGE,
            14,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            7,
            AppEventKind.EMAIL_RECEIVED,
            10,
            {
                "thread_id": 608,
                "sender": "[email protected]",
                "subject_preview": "Ramp · EM Spend Platform",
                "classification": "interview_request",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            7,
            AppEventKind.STATUS_CHANGE,
            10,
            {
                "from_status": "APPLIED",
                "to_status": "RECRUITER_SCREEN",
                "triggered_by": "auto-from-email",
            },
        ),
        _ev(
            _next_eid(),
            7,
            AppEventKind.EMAIL_RECEIVED,
            10,
            {
                "thread_id": 614,
                "sender": "[email protected]",
                "subject_preview": "Ramp · take-home assignment",
                "classification": "assessment",
                "urgent": True,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            7,
            AppEventKind.NOTE_ADDED,
            8,
            {
                "note_text_preview": "Take-home submitted; bullets edited after rev to add fintech context.",
                "full_note_field": "application.notes",
            },
            actor="user",
        ),
        _ev(
            _next_eid(),
            7,
            AppEventKind.DOCS_GENERATED,
            7,  # second generation pair
            {
                "generated_document_id": 915,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
                "regen_reason": "stale",
            },
        ),
    ]
)

# App 8 — Discord — ONSITE_LOOP (~10 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            8,
            AppEventKind.STATUS_CHANGE,
            32.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.DOCS_GENERATED,
            32.4,
            {
                "generated_document_id": 916,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.DOCS_GENERATED,
            32.4,
            {
                "generated_document_id": 917,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.STATUS_CHANGE,
            32,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.EMAIL_RECEIVED,
            22,
            {
                "thread_id": 615,
                "sender": "[email protected]",
                "subject_preview": "Discord · pre-onsite take-home",
                "classification": "assessment",
                "urgent": True,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.EMAIL_RECEIVED,
            14,
            {
                "thread_id": 609,
                "sender": "[email protected]",
                "subject_preview": "Discord onsite — May 3",
                "classification": "interview_request",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.STATUS_CHANGE,
            14,
            {
                "from_status": "APPLIED",
                "to_status": "RECRUITER_SCREEN",
                "triggered_by": "auto-from-email",
            },
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.STATUS_CHANGE,
            8,
            {
                "from_status": "RECRUITER_SCREEN",
                "to_status": "ONSITE_LOOP",
                "triggered_by": "manual",
            },
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.INTERVIEW_SCHEDULED,
            8,
            {"when": _ago(days=-3).isoformat(), "where": "Discord SF HQ", "contact_ids": [213]},
        ),
        _ev(
            _next_eid(),
            8,
            AppEventKind.EMAIL_RECEIVED,
            4,
            {
                "thread_id": 613,
                "sender": "[email protected]",
                "subject_preview": "Discord post-onsite",
                "classification": "follow_up",
                "urgent": False,
                "auto_classified": True,
            },
        ),
    ]
)

# App 9 — Snowflake — CLOSED (rejected) (~8 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            9,
            AppEventKind.STATUS_CHANGE,
            45.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            9,
            AppEventKind.DOCS_GENERATED,
            45.4,
            {
                "generated_document_id": 918,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            9,
            AppEventKind.DOCS_GENERATED,
            45.4,
            {
                "generated_document_id": 919,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            9,
            AppEventKind.STATUS_CHANGE,
            45,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            9,
            AppEventKind.EMAIL_RECEIVED,
            40,
            {
                "thread_id": 610,
                "sender": "[email protected]",
                "subject_preview": "Snowflake · Recruiter Screen",
                "classification": "interview_request",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            9,
            AppEventKind.STATUS_CHANGE,
            40,
            {
                "from_status": "APPLIED",
                "to_status": "RECRUITER_SCREEN",
                "triggered_by": "auto-from-email",
            },
        ),
        _ev(
            _next_eid(),
            9,
            AppEventKind.EMAIL_RECEIVED,
            38,
            {
                "thread_id": 610,
                "sender": "[email protected]",
                "subject_preview": "Snowflake Cortex — moving forward with others",
                "classification": "rejection",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            9,
            AppEventKind.STATUS_CHANGE,
            38,
            {
                "from_status": "RECRUITER_SCREEN",
                "to_status": "CLOSED",
                "triggered_by": "manual",
                "notes": "rejected after recruiter screen",
            },
        ),
    ]
)

# App 10 — Airbnb — CLOSED (ghosted) (~5 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            10,
            AppEventKind.STATUS_CHANGE,
            60.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            10,
            AppEventKind.DOCS_GENERATED,
            60.4,
            {
                "generated_document_id": 920,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            10,
            AppEventKind.DOCS_GENERATED,
            60.4,
            {
                "generated_document_id": 921,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            10,
            AppEventKind.STATUS_CHANGE,
            60,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            10,
            AppEventKind.STATUS_CHANGE,
            30,
            {
                "from_status": "APPLIED",
                "to_status": "CLOSED",
                "triggered_by": "manual",
                "notes": "auto-classified ghosted at 60d no response",
            },
        ),
    ]
)

# App 11 — Databricks — CLOSED (withdrawn) (~6 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            11,
            AppEventKind.STATUS_CHANGE,
            50.5,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            11,
            AppEventKind.DOCS_GENERATED,
            50.4,
            {
                "generated_document_id": 922,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            11,
            AppEventKind.DOCS_GENERATED,
            50.4,
            {
                "generated_document_id": 923,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            11,
            AppEventKind.STATUS_CHANGE,
            50,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            11,
            AppEventKind.EMAIL_RECEIVED,
            44,
            {
                "thread_id": 612,
                "sender": "[email protected]",
                "subject_preview": "Databricks Lakehouse · response",
                "classification": "follow_up",
                "urgent": False,
                "auto_classified": True,
            },
        ),
        _ev(
            _next_eid(),
            11,
            AppEventKind.STATUS_CHANGE,
            40,
            {
                "from_status": "APPLIED",
                "to_status": "CLOSED",
                "triggered_by": "manual",
                "notes": "withdrew — comp gap",
            },
        ),
    ]
)

# App 12 — Cresta — APPLIED, docs FAILED then succeeded on retry (~6 events)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            12,
            AppEventKind.STATUS_CHANGE,
            2,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            12,
            AppEventKind.DOCS_FAILED,
            1.9,
            {
                "kind": "resume",
                "error": "typst page-count overflow after 3 retries",
                "retry_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            12,
            AppEventKind.DOCS_GENERATED,
            1.5,
            {
                "generated_document_id": 924,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            12,
            AppEventKind.DOCS_GENERATED,
            1.5,
            {
                "generated_document_id": 925,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            12,
            AppEventKind.STATUS_CHANGE,
            1,
            {"from_status": "DRAFT", "to_status": "APPLIED", "triggered_by": "draft_submitted"},
        ),
        _ev(
            _next_eid(),
            12,
            AppEventKind.NOTE_ADDED,
            1,
            {
                "note_text_preview": "Resume Typst compile failed once; manually patched and re-submitted.",
                "full_note_field": "application.notes",
            },
            actor="user",
        ),
    ]
)

# App 13 — Mercury — DRAFT (~3 events; user reviewing now)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            13,
            AppEventKind.STATUS_CHANGE,
            1,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        ),
        _ev(
            _next_eid(),
            13,
            AppEventKind.DOCS_GENERATED,
            0.95,
            {
                "generated_document_id": 926,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            13,
            AppEventKind.DOCS_GENERATED,
            0.95,
            {
                "generated_document_id": 927,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
    ]
)

# App 14 — Modal — DRAFT, auto-apply queued + last_failure (~5 events; for Stuck queue)
APP_EVENTS.extend(
    [
        _ev(
            _next_eid(),
            14,
            AppEventKind.STATUS_CHANGE,
            0.75,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "auto_apply_queued"},
        ),
        _ev(
            _next_eid(),
            14,
            AppEventKind.DOCS_GENERATED,
            0.7,
            {
                "generated_document_id": 928,
                "kind": "resume",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.04,
                "token_count": 1822,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            14,
            AppEventKind.DOCS_GENERATED,
            0.7,
            {
                "generated_document_id": 929,
                "kind": "cover_letter",
                "model": "claude-3.5-sonnet-20250219",
                "cost_usd": 0.03,
                "token_count": 1421,
                "page_count": 1,
            },
        ),
        _ev(
            _next_eid(),
            14,
            AppEventKind.DOCS_FAILED,
            0.1,
            {
                "kind": "resume",
                "error": "ats:ashby:auth_required — session expired",
                "retry_count": 2,
            },
        ),
        _ev(
            _next_eid(),
            14,
            AppEventKind.NOTE_ADDED,
            0.05,
            {
                "note_text_preview": "Auto-apply submission failed twice — Ashby auth needed. Surfaced in stuck queue.",
                "full_note_field": "application.submission_artifacts.last_failure",
            },
            actor="system",
        ),
    ]
)


# ─────────────────────────────────────────────────────────────────────────
# ~30 GeneratedDocuments (per SAMPLE_DATA.md § J)
# Per app with docs_state in {READY, STALE, FAILED}: 1 resume + 1 cover_letter.
# Apps 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14 → 13 × 2 = 26 base
# App 7 (Ramp, STALE → had a re-tailor): +2
# App 12 (Cresta) had a failed attempt: +1 failed entry
# Total = 26 + 2 + 1 = 29 (plus 1 audit-trail = 30).
# ─────────────────────────────────────────────────────────────────────────

GENERATED_DOCUMENTS: list[GeneratedDocument] = []


def _doc(
    id_: int,
    application_id: int,
    kind: GeneratedDocumentKind,
    *,
    days_ago: float = 0,
    error: str | None = None,
    bullet_selection: dict[str, object] | None = None,
    cost: float | None = 0.04,
    tokens: int | None = 1822,
    page_count: int | None = 1,
    byte_size: int = 87234,
) -> GeneratedDocument:
    suffix = "resume.pdf" if kind == GeneratedDocumentKind.RESUME else "cover-letter.pdf"
    path = f"~/.naavik/data/documents/{application_id}/{suffix}"
    compiled = _ago(days=days_ago) if error is None else _ago(days=days_ago)
    return GeneratedDocument(
        id=id_,
        application_id=application_id,
        kind=kind,
        path=path,
        byte_size=byte_size,
        page_count=page_count,
        compiled_at=compiled,
        model="claude-3.5-sonnet-20250219",
        cost_usd=cost,
        token_count=tokens,
        error=error,
        bullet_selection=bullet_selection,
        created_at=compiled,
        updated_at=compiled,
    )


_default_bullet_sel = {
    "selected_ids": [1, 2, 3, 5, 6, 8, 11],
    "trimmed_lines": {
        "1": "Built Intuit's ML personalization platform; +23% homepage CTR / $4.2M revenue across 100M users",
        "2": "Designed GenAI rewrites for QBO email campaigns; +14% open rate across 4M weekly sends",
        "3": "Migrated personalization inference Python→Go on EKS; p99 380→92ms; -41% spend",
        "5": "Built versioned prompt registry with $$/call attribution — caught $38k/yr overspend",
        "6": "Built KYC verification orchestrator; 1.4M monthly verifications at 99.97% success",
        "8": "Built institution-status dashboard — replaced manual Slack alerts with truth-source view",
        "11": "Real-time fraud scoring on credit-card stream; p99 18ms; +$1.1M/mo fraud caught",
    },
}

GENERATED_DOCUMENTS.extend(
    [
        # Figma (app 1) — IDs 901, 902
        _doc(
            901,
            1,
            GeneratedDocumentKind.RESUME,
            days_ago=28.9,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            902,
            1,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=28.9,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Anthropic (app 2) — 903, 904
        _doc(
            903,
            2,
            GeneratedDocumentKind.RESUME,
            days_ago=21.4,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            904,
            2,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=21.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Stripe (app 3) — 905, 906
        _doc(
            905, 3, GeneratedDocumentKind.RESUME, days_ago=3.4, bullet_selection=_default_bullet_sel
        ),
        _doc(
            906,
            3,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=3.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Linear (app 4) — 907, 908
        _doc(
            907,
            4,
            GeneratedDocumentKind.RESUME,
            days_ago=10.4,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            908,
            4,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=10.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Notion (app 5) — 909, 910
        _doc(
            909, 5, GeneratedDocumentKind.RESUME, days_ago=7.4, bullet_selection=_default_bullet_sel
        ),
        _doc(
            910,
            5,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=7.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Plaid (app 6) — 911, 912
        _doc(
            911, 6, GeneratedDocumentKind.RESUME, days_ago=5.4, bullet_selection=_default_bullet_sel
        ),
        _doc(
            912,
            6,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=5.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Ramp (app 7) — original + STALE-regen pair: 913, 914 (orig) + 915, 930 (regen)
        _doc(
            913,
            7,
            GeneratedDocumentKind.RESUME,
            days_ago=14.4,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            914,
            7,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=14.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        _doc(
            915, 7, GeneratedDocumentKind.RESUME, days_ago=7, bullet_selection=_default_bullet_sel
        ),
        _doc(
            930,
            7,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=7,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Discord (app 8) — 916, 917
        _doc(
            916,
            8,
            GeneratedDocumentKind.RESUME,
            days_ago=32.4,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            917,
            8,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=32.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Snowflake (app 9) — 918, 919
        _doc(
            918,
            9,
            GeneratedDocumentKind.RESUME,
            days_ago=45.4,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            919,
            9,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=45.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Airbnb (app 10) — 920, 921
        _doc(
            920,
            10,
            GeneratedDocumentKind.RESUME,
            days_ago=60.4,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            921,
            10,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=60.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Databricks (app 11) — 922, 923
        _doc(
            922,
            11,
            GeneratedDocumentKind.RESUME,
            days_ago=50.4,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            923,
            11,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=50.4,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Cresta (app 12) — 924 success after retry, 925 cover; failure entry below
        _doc(
            924,
            12,
            GeneratedDocumentKind.RESUME,
            days_ago=1.5,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            925,
            12,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=1.5,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Mercury (app 13 DRAFT) — 926, 927
        _doc(
            926,
            13,
            GeneratedDocumentKind.RESUME,
            days_ago=0.95,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            927,
            13,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=0.95,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Modal (app 14 DRAFT) — 928, 929
        _doc(
            928,
            14,
            GeneratedDocumentKind.RESUME,
            days_ago=0.7,
            bullet_selection=_default_bullet_sel,
        ),
        _doc(
            929,
            14,
            GeneratedDocumentKind.COVER_LETTER,
            days_ago=0.7,
            byte_size=64511,
            cost=0.03,
            tokens=1421,
        ),
        # Cresta failed-attempt audit row (kept separately as id 931)
        _doc(
            931,
            12,
            GeneratedDocumentKind.RESUME,
            days_ago=1.9,
            error="typst page-count overflow after 3 retries",
            page_count=2,
            byte_size=0,
            cost=0.04,
            tokens=1822,
            bullet_selection=None,
        ),
    ]
)

# ─────────────────────────────────────────────────────────────────────────
# ~20 ApplicationScreenerAnswers (per SAMPLE_DATA.md § K)
# 6 AUTO + 10 DRAFTED + 4 USER. 3 DRAFTED unreviewed (incl. Mercury #13).
# ─────────────────────────────────────────────────────────────────────────


def _ans(
    id_: int,
    application_id: int,
    question: str,
    fingerprint: str,
    qtype: ScreenerQuestionType,
    answer: str | None,
    source: ScreenerAnswerSource,
    *,
    choices: list[str] | None = None,
    drafted_by: str | None = None,
    reviewed_days_ago: float | None = 0,
    required: bool = True,
    order_index: int = 0,
    days_ago: float = 1,
) -> ApplicationScreenerAnswer:
    reviewed = _ago(days=reviewed_days_ago) if reviewed_days_ago is not None else None
    return ApplicationScreenerAnswer(
        id=id_,
        application_id=application_id,
        question_text=question,
        question_fingerprint=fingerprint,
        question_type=qtype,
        choices=choices,
        required=required,
        order_index=order_index,
        answer=answer,
        source=source,
        drafted_by_model=drafted_by,
        reviewed_at=reviewed,
        created_at=_ago(days=days_ago),
        updated_at=_ago(days=days_ago),
    )


SCREENER_ANSWERS: list[ApplicationScreenerAnswer] = [
    # Anthropic (app 2) — 3 questions, all reviewed
    _ans(
        801,
        2,
        "Why are you interested in Anthropic?",
        "why-interested-company",
        ScreenerQuestionType.TEXTAREA,
        "The opportunity to work on inference infrastructure for frontier models — "
        "the constraint surface is exactly where my Intuit GenAI rewrites work has "
        "been pushing me. Plus the safety-first culture lines up with how I want to "
        "build.",
        ScreenerAnswerSource.DRAFTED,
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=21,
        days_ago=22,
    ),
    _ans(
        802,
        2,
        "Are you authorized to work in the US?",
        "us-work-authorization",
        ScreenerQuestionType.SINGLE_SELECT,
        "Yes — visa sponsored",
        ScreenerAnswerSource.AUTO,
        choices=["Yes — US citizen / GC", "Yes — visa sponsored", "No"],
        reviewed_days_ago=21,
        days_ago=22,
        order_index=1,
    ),
    _ans(
        803,
        2,
        "Earliest start date?",
        "earliest-start-date",
        ScreenerQuestionType.DATE,
        "2026-06-15",
        ScreenerAnswerSource.AUTO,
        reviewed_days_ago=21,
        days_ago=22,
        order_index=2,
    ),
    # Stripe (app 3) — 3 questions, 1 unreviewed
    _ans(
        804,
        3,
        "Why are you interested in Stripe?",
        "why-interested-company",
        ScreenerQuestionType.TEXTAREA,
        "Stripe Atlas is the rare team building developer infrastructure that "
        "actually changes founder behavior — and the Atlas ranking surface is "
        "exactly the kind of personalization-meets-product problem I love.",
        ScreenerAnswerSource.DRAFTED,
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=2,
        days_ago=3,
    ),
    _ans(
        805,
        3,
        "Are you authorized to work in the US?",
        "us-work-authorization",
        ScreenerQuestionType.SINGLE_SELECT,
        "Yes — visa sponsored",
        ScreenerAnswerSource.AUTO,
        choices=["Yes — US citizen / GC", "Yes — visa sponsored", "No"],
        reviewed_days_ago=2,
        days_ago=3,
        order_index=1,
    ),
    _ans(
        806,
        3,
        "Are you OK with on-call rotation?",
        "on-call-rotation",
        ScreenerQuestionType.SINGLE_SELECT,
        "Yes",
        ScreenerAnswerSource.DRAFTED,
        choices=["Yes", "No", "Depends on cadence"],
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=None,
        days_ago=3,
        order_index=2,
    ),
    # Notion (app 5) — 2 questions, both reviewed
    _ans(
        807,
        5,
        "Why Notion?",
        "why-interested-company",
        ScreenerQuestionType.TEXTAREA,
        "Notion is the rare collab tool I actually use — the platform behind blocks "
        "is exactly the kind of distributed-systems-meets-product surface that "
        "matches my Intuit + Plaid backgrounds.",
        ScreenerAnswerSource.DRAFTED,
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=7,
        days_ago=7,
    ),
    _ans(
        808,
        5,
        "Years of distributed-systems experience?",
        "years-distributed-systems",
        ScreenerQuestionType.NUMERIC,
        "8",
        ScreenerAnswerSource.DRAFTED,
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=7,
        days_ago=7,
        order_index=1,
    ),
    # Plaid (app 6) — 1 question
    _ans(
        809,
        6,
        "Are you OK with on-call rotation?",
        "on-call-rotation",
        ScreenerQuestionType.SINGLE_SELECT,
        "Yes",
        ScreenerAnswerSource.DRAFTED,
        choices=["Yes", "No"],
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=5,
        days_ago=5,
    ),
    # Ramp (app 7) — 2 questions
    _ans(
        810,
        7,
        "Willing to relocate to NYC?",
        "willing-to-relocate-city",
        ScreenerQuestionType.SINGLE_SELECT,
        "Yes",
        ScreenerAnswerSource.AUTO,
        choices=["Yes", "No"],
        reviewed_days_ago=14,
        days_ago=14,
    ),
    _ans(
        811,
        7,
        "Salary expectation?",
        "salary-expectation",
        ScreenerQuestionType.NUMERIC,
        "$290,000",
        ScreenerAnswerSource.AUTO,
        reviewed_days_ago=14,
        days_ago=14,
        order_index=1,
    ),
    # Discord (app 8) — 2 questions
    _ans(
        812,
        8,
        "Why Discord?",
        "why-interested-company",
        ScreenerQuestionType.TEXTAREA,
        "Discord's Relevance team is at the intersection of ranking and "
        "developer-experience that drew me to ML in the first place.",
        ScreenerAnswerSource.DRAFTED,
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=32,
        days_ago=33,
    ),
    _ans(
        813,
        8,
        "Years of ML experience?",
        "years-ml",
        ScreenerQuestionType.NUMERIC,
        "7",
        ScreenerAnswerSource.DRAFTED,
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=32,
        days_ago=33,
        order_index=1,
    ),
    # Cresta (app 12) — 2 questions; 1 USER (anecdote)
    _ans(
        814,
        12,
        "Tell us about a time you failed.",
        "tell-us-about-failure",
        ScreenerQuestionType.TEXTAREA,
        "I shipped a personalization model that overfit to a holiday-season "
        "promotion. We rolled back inside an hour and added a holdout-cohort "
        "monitor. The monitor caught two later regressions before they shipped.",
        ScreenerAnswerSource.USER,
        reviewed_days_ago=1,
        days_ago=2,
    ),
    _ans(
        815,
        12,
        "Are you authorized to work in the US?",
        "us-work-authorization",
        ScreenerQuestionType.SINGLE_SELECT,
        "Yes — visa sponsored",
        ScreenerAnswerSource.AUTO,
        choices=["Yes — US citizen / GC", "Yes — visa sponsored", "No"],
        reviewed_days_ago=1,
        days_ago=2,
        order_index=1,
    ),
    # Cohere — saved job (no app yet) — but we keep an example USER answer attached
    # to the Mercury DRAFT (app 13) for the Toronto CAD salary case
    _ans(
        816,
        13,
        "Salary expectation in CAD?",
        "salary-expectation-cad",
        ScreenerQuestionType.NUMERIC,
        "$385,000 CAD",
        ScreenerAnswerSource.DRAFTED,
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=None,
        days_ago=1,
        order_index=2,
    ),
    # Mercury (app 13 DRAFT) — 3 questions, 1 unreviewed → blocks Submit
    _ans(
        817,
        13,
        "Why are you interested in Mercury?",
        "why-interested-company",
        ScreenerQuestionType.TEXTAREA,
        "Mercury sits in the rare overlap of fintech and developer empathy — "
        "the card platform is the kind of ledger-and-rails system I love.",
        ScreenerAnswerSource.DRAFTED,
        drafted_by="claude-3.5-sonnet-20250219",
        reviewed_days_ago=None,
        days_ago=1,
    ),
    _ans(
        818,
        13,
        "Are you authorized to work in the US?",
        "us-work-authorization",
        ScreenerQuestionType.SINGLE_SELECT,
        "Yes — visa sponsored",
        ScreenerAnswerSource.AUTO,
        choices=["Yes — US citizen / GC", "Yes — visa sponsored", "No"],
        reviewed_days_ago=1,
        days_ago=1,
        order_index=1,
    ),
    _ans(
        819,
        13,
        "Salary expectation?",
        "salary-expectation",
        ScreenerQuestionType.NUMERIC,
        "$290,000",
        ScreenerAnswerSource.AUTO,
        reviewed_days_ago=1,
        days_ago=1,
        order_index=2,
    ),
    # Modal (app 14 DRAFT) — 1 USER fallback
    _ans(
        820,
        14,
        "Tell us about your most ambitious project.",
        "ambitious-project",
        ScreenerQuestionType.TEXTAREA,
        "Naavik — open-source career automation platform I'm building right now. "
        "Self-hosted-first, full pipeline from scrape through outreach.",
        ScreenerAnswerSource.USER,
        reviewed_days_ago=0.5,
        days_ago=0.7,
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# 0 ATSCredentials in Phase 1 fixtures (per SAMPLE_DATA.md § L)
# ─────────────────────────────────────────────────────────────────────────

ATS_CREDENTIALS: list[ATSCredential] = []

# ─────────────────────────────────────────────────────────────────────────
# ~30 ApiUsage rows (per SAMPLE_DATA.md § B → DATA_MODEL.md § C `ApiUsage`)
# Powers Settings · LLM Provider cost cards from day one.
# Distribution: ~24 Anthropic + ~3 OpenAI + ~3 Ollama. Spans last 30 days.
# THIS MONTH ≈ $3.42 across all providers.
# ─────────────────────────────────────────────────────────────────────────


def _usage(
    id_: int,
    provider: LLMProvider,
    model: str,
    method: str,
    prompt: str | None,
    in_tok: int,
    out_tok: int,
    cost: float,
    latency: int,
    days_ago: float,
    *,
    application_id: int | None = None,
    succeeded: bool = True,
    error_kind: str | None = None,
) -> ApiUsage:
    occurred = _ago(days=days_ago)
    return ApiUsage(
        id=id_,
        user_id=1,
        application_id=application_id,
        provider=provider,
        model=model,
        method=method,
        prompt_name=prompt,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
        latency_ms=latency,
        succeeded=succeeded,
        error_kind=error_kind,
        occurred_at=occurred,
        created_at=occurred,
    )


# Build ~30 rows summing to ~$3.42 over the last 30 days.
# Anthropic dominates (default provider).
_anthr = "claude-3.5-sonnet-20250219"
_oai = "gpt-4o"
_olla = "llama3.1:70b"

API_USAGE: list[ApiUsage] = [
    # Document generation — resume + cover letter pairs (most expensive)
    _usage(
        1001,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        412,
        0.04,
        412,
        days_ago=29,
        application_id=10,
    ),
    _usage(
        1002,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        689,
        0.03,
        689,
        days_ago=29,
        application_id=10,
    ),
    _usage(
        1003,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        422,
        0.04,
        412,
        days_ago=28,
        application_id=1,
    ),
    _usage(
        1004,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        712,
        0.03,
        689,
        days_ago=28,
        application_id=1,
    ),
    _usage(
        1005,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "answer_screener",
        512,
        220,
        0.01,
        312,
        days_ago=28,
        application_id=1,
    ),
    _usage(
        1006,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        401,
        0.04,
        412,
        days_ago=21,
        application_id=2,
    ),
    _usage(
        1007,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        698,
        0.03,
        689,
        days_ago=21,
        application_id=2,
    ),
    _usage(
        1008,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "answer_screener",
        602,
        280,
        0.01,
        312,
        days_ago=21,
        application_id=2,
    ),
    _usage(
        1009,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "answer_screener",
        488,
        199,
        0.01,
        312,
        days_ago=21,
        application_id=2,
    ),
    _usage(
        1010,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "answer_screener",
        421,
        175,
        0.01,
        312,
        days_ago=21,
        application_id=2,
    ),
    _usage(
        1011,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        410,
        0.04,
        412,
        days_ago=14,
        application_id=7,
    ),
    _usage(
        1012,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        712,
        0.03,
        689,
        days_ago=14,
        application_id=7,
    ),
    _usage(
        1013,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        415,
        0.04,
        412,
        days_ago=10,
        application_id=4,
    ),
    _usage(
        1014,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        700,
        0.03,
        689,
        days_ago=10,
        application_id=4,
    ),
    _usage(
        1015,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        405,
        0.04,
        412,
        days_ago=7,
        application_id=5,
    ),
    _usage(
        1016,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        720,
        0.03,
        689,
        days_ago=7,
        application_id=5,
    ),
    _usage(
        1017,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "answer_screener",
        500,
        240,
        0.01,
        312,
        days_ago=7,
        application_id=5,
    ),
    _usage(
        1018,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        420,
        0.04,
        412,
        days_ago=5,
        application_id=6,
    ),
    _usage(
        1019,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        712,
        0.03,
        689,
        days_ago=5,
        application_id=6,
    ),
    _usage(
        1020,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        412,
        0.04,
        412,
        days_ago=3,
        application_id=3,
    ),
    _usage(
        1021,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        700,
        0.03,
        689,
        days_ago=3,
        application_id=3,
    ),
    _usage(
        1022,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "answer_screener",
        488,
        220,
        0.01,
        312,
        days_ago=3,
        application_id=3,
    ),
    _usage(
        1023,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "select_bullets",
        1822,
        410,
        0.04,
        412,
        days_ago=1,
        application_id=13,
    ),
    _usage(
        1024,
        LLMProvider.ANTHROPIC,
        _anthr,
        "structured",
        "draft_cover_letter",
        1421,
        700,
        0.03,
        689,
        days_ago=1,
        application_id=13,
    ),
    # OpenAI mix (testing GPT-4o)
    _usage(
        1025, LLMProvider.OPENAI, _oai, "structured", "score_job", 880, 240, 0.02, 220, days_ago=12
    ),
    _usage(
        1026, LLMProvider.OPENAI, _oai, "structured", "score_job", 880, 280, 0.02, 220, days_ago=10
    ),
    _usage(
        1027,
        LLMProvider.OPENAI,
        _oai,
        "structured",
        "extract_job",
        1640,
        510,
        0.03,
        350,
        days_ago=8,
    ),
    # Ollama local (free)
    _usage(
        1028, LLMProvider.OLLAMA, _olla, "structured", "score_job", 880, 250, 0.0, 1820, days_ago=15
    ),
    _usage(
        1029,
        LLMProvider.OLLAMA,
        _olla,
        "structured",
        "extract_job",
        1640,
        480,
        0.0,
        2410,
        days_ago=14,
    ),
    _usage(
        1030,
        LLMProvider.OLLAMA,
        _olla,
        "structured",
        "auto_tag_bullets",
        420,
        110,
        0.0,
        940,
        days_ago=14,
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# 1 Settings singleton (per SAMPLE_DATA.md § L)
# ─────────────────────────────────────────────────────────────────────────

SETTINGS: Settings = Settings(
    user_id=1,
    llm_provider=LLMProvider.ANTHROPIC,
    llm_model=_anthr,
    llm_fallback_provider=None,
    auto_apply_enabled=False,
    auto_apply_score_threshold=0.85,
    auto_apply_daily_cap=None,
    eager_review_generation=True,
    daily_llm_cost_cap_usd=None,
    notify_threshold=0.80,
    notify_on_errors=True,
    notifications_enabled={
        "new_high_score_job": True,
        "application_sent": True,
        "interview_scheduled": True,
        "offer_received": True,
        "rejection": False,
    },
    portfolio_cors_allowed_origins=["https://crypticsoul.dev"],
    sources_enabled={
        "linkedin": True,
        "workday": True,
        "greenhouse": True,
        "lever": True,
        "ashby": True,
        "indeed": False,
        "rss": True,
    },
    source_schedules={
        "linkedin": "*/30 * * * *",
        "workday": "0 * * * *",
        "greenhouse": "0 * * * *",
        "lever": "0 * * * *",
        "ashby": "0 * * * *",
        "indeed": "*/90 * * * *",
        "rss": "*/15 * * * *",
    },
    workday_companies=["snowflake", "databricks"],
    deployment_mode=DeploymentMode.SELF_HOSTED,
    debug=False,
    created_at=_ago(days=120),
    updated_at=_ago(days=2),
)


# ─────────────────────────────────────────────────────────────────────────
# Async accessors per SAMPLE_DATA.md § M.
# **All `async def` from day one** so plan 10 Wave 4 swaps body-only.
# ─────────────────────────────────────────────────────────────────────────


async def by_id(items: list, item_id: int):
    return next((i for i in items if i.id == item_id), None)


# ── Profile / resume substrate ───────────────────────────────────────────


async def get_profile() -> Profile:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Profile as SQLProfile

        async with async_session() as session:
            stmt = select(SQLProfile).where(
                SQLProfile.user_id == 1,
                SQLProfile.deleted_at.is_(None),
            )
            row = (await session.exec(stmt)).one_or_none()
            if row is not None:
                return await _shadow_from_sql(row, Profile)
    return PROFILE


async def get_user() -> User:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import User as SQLUser

        async with async_session() as session:
            stmt = select(SQLUser).where(SQLUser.id == 1, SQLUser.deleted_at.is_(None))
            row = (await session.exec(stmt)).one_or_none()
            if row is not None:
                return await _shadow_from_sql(row, User)
    return USER


async def get_experiences() -> list[Experience]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Experience as SQLExperience

        async with async_session() as session:
            stmt = (
                select(SQLExperience)
                .where(SQLExperience.deleted_at.is_(None))
                .order_by(SQLExperience.order_index)
            )
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Experience)
    return list(EXPERIENCES)


async def get_experience(experience_id: int) -> Experience | None:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Experience as SQLExperience

        async with async_session() as session:
            stmt = select(SQLExperience).where(
                SQLExperience.id == experience_id,
                SQLExperience.deleted_at.is_(None),
            )
            row = (await session.exec(stmt)).one_or_none()
            if row is not None:
                return await _shadow_from_sql(row, Experience)
    return next((e for e in EXPERIENCES if e.id == experience_id), None)


async def get_bullets() -> list[Bullet]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Bullet as SQLBullet

        async with async_session() as session:
            stmt = select(SQLBullet).where(SQLBullet.deleted_at.is_(None))
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Bullet)
    return list(BULLETS)


async def get_bullet(bullet_id: int) -> Bullet | None:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Bullet as SQLBullet

        async with async_session() as session:
            stmt = select(SQLBullet).where(
                SQLBullet.id == bullet_id,
                SQLBullet.deleted_at.is_(None),
            )
            row = (await session.exec(stmt)).one_or_none()
            if row is not None:
                return await _shadow_from_sql(row, Bullet)
    return next((b for b in BULLETS if b.id == bullet_id), None)


async def get_bullets_for_experience(experience_id: int) -> list[Bullet]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Bullet as SQLBullet

        async with async_session() as session:
            stmt = (
                select(SQLBullet)
                .where(
                    SQLBullet.experience_id == experience_id,
                    SQLBullet.deleted_at.is_(None),
                )
                .order_by(SQLBullet.order_index)
            )
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Bullet)
    return sorted(
        [b for b in BULLETS if b.experience_id == experience_id],
        key=lambda b: b.order_index,
    )


async def get_skills() -> list[Skill]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Skill as SQLSkill

        async with async_session() as session:
            stmt = select(SQLSkill).order_by(SQLSkill.order_index)
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Skill)
    return sorted(SKILLS, key=lambda s: s.order_index)


async def get_educations() -> list[Education]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Education as SQLEducation

        async with async_session() as session:
            stmt = select(SQLEducation).order_by(SQLEducation.order_index)
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Education)
    return sorted(EDUCATIONS, key=lambda e: e.order_index)


async def get_projects() -> list[Project]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Project as SQLProject

        async with async_session() as session:
            stmt = (
                select(SQLProject)
                .where(SQLProject.deleted_at.is_(None))
                .order_by(SQLProject.order_index)
            )
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Project)
    return sorted(PROJECTS, key=lambda p: p.order_index)


async def get_certifications() -> list[Certification]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Certification as SQLCert

        async with async_session() as session:
            stmt = select(SQLCert).order_by(SQLCert.order_index)
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Certification)
    return sorted(CERTIFICATIONS, key=lambda c: c.order_index)


# ── Discovery ────────────────────────────────────────────────────────────


async def get_jobs() -> list[Job]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Job as SQLJob

        async with async_session() as session:
            stmt = select(SQLJob).where(SQLJob.deleted_at.is_(None))
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Job)
    return list(JOBS)


async def get_job(job_id: int) -> Job | None:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Job as SQLJob

        async with async_session() as session:
            stmt = select(SQLJob).where(
                SQLJob.id == job_id,
                SQLJob.deleted_at.is_(None),
            )
            row = (await session.exec(stmt)).one_or_none()
            if row is not None:
                return await _shadow_from_sql(row, Job)
    return next((j for j in JOBS if j.id == job_id), None)


async def discover_queue() -> list[Job]:
    """Unswiped jobs in score-desc order — the Discover page's main feed."""
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Job as SQLJob

        async with async_session() as session:
            stmt = (
                select(SQLJob)
                .where(
                    SQLJob.queue_state == JobQueueState.UNSWIPED,
                    SQLJob.deleted_at.is_(None),
                )
                .order_by(SQLJob.score.desc())
            )
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Job)
    return sorted(
        [j for j in JOBS if j.queue_state == JobQueueState.UNSWIPED],
        key=lambda j: j.score,
        reverse=True,
    )


async def saved_jobs() -> list[Job]:
    return [j for j in JOBS if j.queue_state == JobQueueState.SAVED]


async def skipped_jobs() -> list[Job]:
    return [j for j in JOBS if j.queue_state == JobQueueState.SKIPPED]


async def auto_apply_queue() -> list[Application]:
    """DRAFT applications attached to QUEUED_FOR_AUTO_APPLY jobs."""
    queued_job_ids = {j.id for j in JOBS if j.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY}
    return [
        a
        for a in APPLICATIONS
        if a.status == ApplicationStatus.DRAFT and a.job_id in queued_job_ids
    ]


async def stuck_drafts() -> list[Application]:
    """DRAFT applications whose auto-apply submission failed (last_failure populated)."""
    return [
        a
        for a in APPLICATIONS
        if a.status == ApplicationStatus.DRAFT
        and a.submission_artifacts
        and a.submission_artifacts.get("last_failure")
    ]


# ── Applications ─────────────────────────────────────────────────────────


async def get_applications() -> list[Application]:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Application as SQLApp

        async with async_session() as session:
            stmt = select(SQLApp).where(SQLApp.deleted_at.is_(None))
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Application)
    return [a for a in APPLICATIONS if a.deleted_at is None]


async def get_application(application_id: int) -> Application | None:
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Application as SQLApp

        async with async_session() as session:
            stmt = select(SQLApp).where(SQLApp.id == application_id)
            row = (await session.exec(stmt)).one_or_none()
            if row is not None:
                return await _shadow_from_sql(row, Application)
    return next((a for a in APPLICATIONS if a.id == application_id), None)


async def applications_visible_in_tracking() -> list[Application]:
    """Default Tracking view — APPLIED through OFFER. Hides DRAFT + CLOSED."""
    visible = {
        ApplicationStatus.APPLIED,
        ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP,
        ApplicationStatus.OFFER,
    }
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Application as SQLApp

        async with async_session() as session:
            stmt = select(SQLApp).where(
                SQLApp.status.in_(visible),
                SQLApp.deleted_at.is_(None),
            )
            rows = (await session.exec(stmt)).all()
            if rows:
                return await _shadow_list_from_sql(rows, Application)
    return [a for a in APPLICATIONS if a.status in visible and a.deleted_at is None]


async def applications_by_status(status: ApplicationStatus) -> list[Application]:
    return [a for a in APPLICATIONS if a.status == status and a.deleted_at is None]


async def applications_in_followup_state() -> list[Application]:
    """Recruiter SILENT or STALLED — drives Tracking 'needs followup' banner."""
    return [
        a
        for a in APPLICATIONS
        if a.recruiter_state in {RecruiterState.SILENT, RecruiterState.STALLED}
        and a.status not in {ApplicationStatus.DRAFT, ApplicationStatus.CLOSED}
        and a.deleted_at is None
    ]


async def closed_applications() -> list[Application]:
    return [
        a for a in APPLICATIONS if a.status == ApplicationStatus.CLOSED and a.deleted_at is None
    ]


async def draft_applications() -> list[Application]:
    return [a for a in APPLICATIONS if a.status == ApplicationStatus.DRAFT and a.deleted_at is None]


async def application_for_job(user_id: int, job_id: int) -> Application | None:
    return next(
        (
            a
            for a in APPLICATIONS
            if a.user_id == user_id and a.job_id == job_id and a.deleted_at is None
        ),
        None,
    )


async def documents_for_application(application_id: int) -> list[GeneratedDocument]:
    return sorted(
        [d for d in GENERATED_DOCUMENTS if d.application_id == application_id and d.error is None],
        key=lambda d: d.compiled_at,
        reverse=True,
    )


async def screener_answers_for_application(application_id: int) -> list[ApplicationScreenerAnswer]:
    return sorted(
        [s for s in SCREENER_ANSWERS if s.application_id == application_id],
        key=lambda s: s.order_index,
    )


async def unreviewed_required_screeners(application_id: int) -> int:
    answers = await screener_answers_for_application(application_id)
    return sum(1 for a in answers if a.required and a.reviewed_at is None)


async def app_events_for_application(application_id: int) -> list[AppEvent]:
    return sorted(
        [e for e in APP_EVENTS if e.application_id == application_id],
        key=lambda e: e.occurred_at,
        reverse=True,
    )


# ── Outreach ─────────────────────────────────────────────────────────────


async def get_contacts() -> list[Contact]:
    return [c for c in CONTACTS if c.deleted_at is None]


async def get_contact(contact_id: int) -> Contact | None:
    return next((c for c in CONTACTS if c.id == contact_id), None)


async def contacts_for_company(company: str) -> list[Contact]:
    return [c for c in CONTACTS if c.company == company and c.deleted_at is None]


async def contacts_for_application(application_id: int) -> list[Contact]:
    contact_ids = {
        link.contact_id
        for link in CONTACT_APPLICATION_LINKS
        if link.application_id == application_id
    }
    return [c for c in CONTACTS if c.id in contact_ids and c.deleted_at is None]


async def outreach_messages_for_contact(contact_id: int) -> list[OutreachMessage]:
    return sorted(
        [m for m in OUTREACH_MESSAGES if m.contact_id == contact_id and m.deleted_at is None],
        key=lambda m: m.created_at,
        reverse=True,
    )


async def outreach_messages_for_application(application_id: int) -> list[OutreachMessage]:
    return sorted(
        [
            m
            for m in OUTREACH_MESSAGES
            if m.application_id == application_id and m.deleted_at is None
        ],
        key=lambda m: m.created_at,
        reverse=True,
    )


# ── Email ────────────────────────────────────────────────────────────────


async def get_email_threads() -> list[EmailThread]:
    return list(EMAIL_THREADS)


async def get_email_thread(thread_id: int) -> EmailThread | None:
    return next((t for t in EMAIL_THREADS if t.id == thread_id), None)


async def email_threads_for_application(application_id: int) -> list[EmailThread]:
    return sorted(
        [t for t in EMAIL_THREADS if t.application_id == application_id],
        key=lambda t: t.latest_message_at,
        reverse=True,
    )


async def email_signal_feed(limit: int = 6) -> list[EmailThread]:
    """Most recent email signals — Overview right rail + Tracking integrations."""
    return sorted(EMAIL_THREADS, key=lambda t: t.latest_message_at, reverse=True)[:limit]


# ── Settings + cost cards ────────────────────────────────────────────────


async def get_settings() -> Settings:
    """Settings singleton accessor.

    Plan 10b (item 6, 2026-05-03): Wave 4 catalogued get_settings as a
    DB-swap target but the body shipped reading from the in-memory shadow.
    Closed here so the Settings · LLM Provider form's PUT round-trip
    reflects DB state on reload.
    """
    if _is_db_mode():
        from sqlmodel import select

        from db.session import async_session
        from models import Settings as SQLSettings

        async with async_session() as session:
            stmt = select(SQLSettings).where(SQLSettings.user_id == 1)
            row = (await session.exec(stmt)).one_or_none()
            shadow = await _shadow_from_sql(row, Settings)
            if shadow is not None:
                return shadow
        return SETTINGS
    return SETTINGS


async def api_usage_recent(days: int = 30) -> list[ApiUsage]:
    cutoff = TODAY - timedelta(days=days)
    return [u for u in API_USAGE if u.occurred_at >= cutoff]


async def llm_usage_summary(days: int = 30) -> dict[str, float]:
    """Return {month_cost_usd, avg_per_generation_usd, total_tokens, gen_count}.

    Drives Settings · LLM Provider cost cards.
    """
    rows = await api_usage_recent(days)
    cost = sum(r.cost_usd for r in rows)
    tokens = sum(r.input_tokens + r.output_tokens for r in rows)
    # "generation" here = bundle (resume + cover_letter) attributed to an Application
    gen_apps = {r.application_id for r in rows if r.application_id is not None}
    gen_count = len(gen_apps)
    avg = (cost / gen_count) if gen_count else 0.0
    return {
        "month_cost_usd": round(cost, 2),
        "avg_per_generation_usd": round(avg, 2),
        "total_tokens": tokens,
        "gen_count": gen_count,
    }


# ── Overview KPIs (per DATA_MODEL.md § F) ────────────────────────────────


async def kpi_active_applications() -> int:
    apps = await applications_visible_in_tracking()
    return len(apps)


async def kpi_response_rate_90d() -> float:
    cutoff = TODAY - timedelta(days=90)
    in_window = [
        a
        for a in APPLICATIONS
        if a.status != ApplicationStatus.DRAFT
        and a.applied_at is not None
        and a.applied_at >= cutoff
        and a.deleted_at is None
    ]
    if not in_window:
        return 0.0
    engaged_states = {
        RecruiterState.ENGAGED,
        RecruiterState.RESPONDED,
        RecruiterState.SILENT,
        RecruiterState.STALLED,
    }
    engaged = [a for a in in_window if a.recruiter_state in engaged_states]
    return len(engaged) / len(in_window)


async def kpi_onsite_rate_90d() -> float:
    cutoff = TODAY - timedelta(days=90)
    in_window = [
        a
        for a in APPLICATIONS
        if a.status != ApplicationStatus.DRAFT
        and a.applied_at is not None
        and a.applied_at >= cutoff
        and a.deleted_at is None
    ]
    if not in_window:
        return 0.0
    # Onsite = ever reached ONSITE_LOOP or beyond. Approximate from current status
    # plus a derived check via app-events for closed apps.
    onsite_states = {ApplicationStatus.ONSITE_LOOP, ApplicationStatus.OFFER}
    reached_onsite = [a for a in in_window if a.status in onsite_states]
    closed_reached = [
        a
        for a in in_window
        if a.status == ApplicationStatus.CLOSED
        and any(
            e.application_id == a.id
            and e.kind == AppEventKind.STATUS_CHANGE
            and e.payload.get("to_status") in {"ONSITE_LOOP", "OFFER"}
            for e in APP_EVENTS
        )
    ]
    return (len(reached_onsite) + len(closed_reached)) / len(in_window)


async def kpi_offer_rate_90d() -> float:
    cutoff = TODAY - timedelta(days=90)
    in_window = [
        a
        for a in APPLICATIONS
        if a.status != ApplicationStatus.DRAFT
        and a.applied_at is not None
        and a.applied_at >= cutoff
        and a.deleted_at is None
    ]
    if not in_window:
        return 0.0
    offered = [a for a in in_window if a.status == ApplicationStatus.OFFER]
    return len(offered) / len(in_window)


async def pipeline_strip_counts() -> dict[str, int]:
    apps = [a for a in APPLICATIONS if a.deleted_at is None]
    counts = {
        "APPLIED": 0,
        "RECRUITER_SCREEN": 0,
        "ONSITE_LOOP": 0,
        "OFFER": 0,
        "CLOSED": 0,
    }
    for a in apps:
        if a.status == ApplicationStatus.DRAFT:
            continue
        if a.status.value in counts:
            counts[a.status.value] += 1
    return counts


async def priority_actions(limit: int = 8) -> list[dict[str, object]]:
    """Synthesize Overview priority-action rows from APPLICATIONS + EMAIL_THREADS."""
    actions: list[dict[str, object]] = []

    # Offers — most urgent
    for a in APPLICATIONS:
        if a.status == ApplicationStatus.OFFER and a.deleted_at is None:
            actions.append(
                {
                    "kind": "offer",
                    "title": f"Respond to {a.company} offer",
                    "subtitle": f"${a.salary_min // 1000}k base + {a.equity_pct}% · verbal extended · they expect a reply by Thu",
                    "urgency": "today",
                    "urgency_label": "TODAY",
                    "cta_label": "Open offer",
                    "cta_url": f"/tracking?app={a.id}",
                }
            )

    # Onsite scheduled within 7 days
    for a in APPLICATIONS:
        if a.status == ApplicationStatus.ONSITE_LOOP and a.deleted_at is None:
            actions.append(
                {
                    "kind": "interview",
                    "title": f"Prep for {a.company} onsite",
                    "subtitle": f"{a.role}{(' · ' + a.team) if a.team else ''} · final round in 3 days",
                    "urgency": "tomorrow",
                    "urgency_label": "3D",
                    "cta_label": "Open prep notes",
                    "cta_url": f"/tracking?app={a.id}",
                }
            )

    # Recruiter SILENT ≥ 3 days
    for a in APPLICATIONS:
        if (
            a.recruiter_state == RecruiterState.SILENT
            and a.status not in {ApplicationStatus.DRAFT, ApplicationStatus.CLOSED}
            and a.deleted_at is None
        ):
            actions.append(
                {
                    "kind": "silent",
                    "title": f"Send nudge to {a.company} recruiter",
                    "subtitle": f"{a.role}{(' · ' + a.team) if a.team else ''} · silent for 6 days",
                    "urgency": "silent_n",
                    "urgency_label": "6D SILENT",
                    "cta_label": "Send nudge",
                    "cta_url": f"/outreach?application={a.id}",
                }
            )

    # Recent inbound emails — Reply CTA
    for t in sorted(EMAIL_THREADS, key=lambda x: x.latest_message_at, reverse=True):
        if t.application_id is None:
            continue
        if t.classification not in {
            EmailClassification.INTERVIEW_REQUEST,
            EmailClassification.ASSESSMENT,
            EmailClassification.OFFER,
        }:
            continue
        # Skip already-handled offers (we already added an offer action above)
        if t.classification == EmailClassification.OFFER:
            continue
        actions.append(
            {
                "kind": "reply",
                "title": f"Reply to {t.subject[:60]}",
                "subtitle": f"{t.classification.value.replace('_', ' ').lower()} · {_relative_label(t.latest_message_at)}",
                "urgency": "relative",
                "urgency_label": _relative_label(t.latest_message_at).upper(),
                "cta_label": "Reply",
                "cta_url": f"/tracking?app={t.application_id}",
            }
        )

    return actions[:limit]


def _relative_label(when: datetime) -> str:
    """Return a tight relative time label (mirrors the UI strings)."""
    delta = TODAY - when
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


# ─────────────────────────────────────────────────────────────────────────
# In-memory mutation shim
# Stub endpoints write through these so changes persist for the server-process
# lifetime. Tests reset state via fixtures.
# ─────────────────────────────────────────────────────────────────────────


def _next_id(items: list) -> int:
    return max((i.id for i in items), default=0) + 1


async def _apply_status_override(
    app_id: int, status: ApplicationStatus, *, closed_reason: ClosedReason | None = None
) -> Application | None:
    a = await get_application(app_id)
    if a is None:
        return None
    a.status = status
    if closed_reason is not None:
        a.closed_reason = closed_reason
    a.updated_at = datetime.now(UTC)
    return a


async def _create_draft(user_id: int, job_id: int) -> Application:
    """Create a DRAFT Application for (user_id, job_id) if one doesn't exist."""
    existing = await application_for_job(user_id, job_id)
    if existing is not None:
        return existing
    j = await get_job(job_id)
    new_id = _next_id(APPLICATIONS)
    now = datetime.now(UTC)
    a = Application(
        id=new_id,
        user_id=user_id,
        job_id=job_id,
        company=j.company if j else "Unknown",
        role=j.role if j else "Unknown",
        team=j.team if j else None,
        location=j.location if j else None,
        salary_min=j.salary_min if j else None,
        salary_max=j.salary_max if j else None,
        equity_pct=j.equity_pct if j else None,
        applied_at=None,
        board=j.board if j else None,
        external_url=None,
        status=ApplicationStatus.DRAFT,
        closed_reason=None,
        docs_state=DocsState.READY,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={},
        notes=None,
        created_at=now,
        updated_at=now,
    )
    APPLICATIONS.append(a)
    APP_EVENTS.append(
        _ev(
            _next_id(APP_EVENTS),
            new_id,
            AppEventKind.STATUS_CHANGE,
            0,
            {"from_status": None, "to_status": "DRAFT", "triggered_by": "draft_creation"},
        )
    )
    return a


async def _record_screener_answer(answer_id: int, body: str) -> ApplicationScreenerAnswer | None:
    a = next((s for s in SCREENER_ANSWERS if s.id == answer_id), None)
    if a is None:
        return None
    a.answer = body
    a.reviewed_at = datetime.now(UTC)
    a.updated_at = datetime.now(UTC)
    return a


async def _apply_failure_to_draft(app_id: int, kind: str, message: str) -> Application | None:
    a = await get_application(app_id)
    if a is None:
        return None
    artifacts = dict(a.submission_artifacts or {})
    artifacts["last_failure"] = {
        "kind": kind,
        "message": message,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    artifacts["retry_count"] = (artifacts.get("retry_count") or 0) + 1
    a.submission_artifacts = artifacts
    a.updated_at = datetime.now(UTC)
    return a


async def _set_job_queue_state(job_id: int, state: JobQueueState) -> Job | None:
    j = await get_job(job_id)
    if j is None:
        return None
    j.queue_state = state
    j.updated_at = datetime.now(UTC)
    return j


async def _append_outreach_message(
    contact_id: int,
    application_id: int | None,
    intent: OutreachIntent,
    body: str,
    *,
    status: OutreachStatus = OutreachStatus.DRAFT,
    channel: str = "linkedin_dm",
) -> OutreachMessage:
    new_id = _next_id(OUTREACH_MESSAGES)
    now = datetime.now(UTC)
    m = OutreachMessage(
        id=new_id,
        user_id=1,
        contact_id=contact_id,
        application_id=application_id,
        intent=intent,
        channel=channel,
        body=body,
        status=status,
        ai_generated=True,
        drafted_by_model="claude-3.5-sonnet-20250219",
        created_at=now,
        updated_at=now,
    )
    OUTREACH_MESSAGES.append(m)
    return m


async def _append_manual_application(
    *,
    company: str,
    role: str,
    team: str | None,
    location: str | None,
    salary_min: int | None,
    salary_max: int | None,
    notes: str | None = None,
) -> Application:
    new_id = _next_id(APPLICATIONS)
    now = datetime.now(UTC)
    a = Application(
        id=new_id,
        user_id=1,
        job_id=None,
        company=company,
        role=role,
        team=team,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        equity_pct=None,
        applied_at=now,
        board=ApplicationBoard.MANUAL,
        external_url=None,
        status=ApplicationStatus.APPLIED,
        closed_reason=None,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={"board_application_id": None, "manual": True},
        notes=notes,
        created_at=now,
        updated_at=now,
    )
    APPLICATIONS.append(a)
    APP_EVENTS.append(
        _ev(
            _next_id(APP_EVENTS),
            new_id,
            AppEventKind.STATUS_CHANGE,
            0,
            {"from_status": None, "to_status": "APPLIED", "triggered_by": "manual"},
        )
    )
    return a


async def _append_scraped_job(*, url: str, company: str, role: str) -> Job:
    """Stub for `+ Add by URL` — append a synthetic high-score Job."""
    new_id = _next_id(JOBS)
    now = datetime.now(UTC)
    ext_id = hashlib.sha1(url.encode()).hexdigest()[:12]
    j = Job(
        id=new_id,
        user_id=1,
        source=JobSource.MANUAL,
        board=ApplicationBoard.MANUAL,
        external_id=f"manual-{ext_id}",
        url=url,
        url_type="manual",
        company=company,
        role=role,
        team=None,
        location="San Francisco, CA · Hybrid",
        remote_policy=RemotePolicy.HYBRID,
        seniority_level=SeniorityLevel.SENIOR,
        posted_at=now,
        found_at=now,
        description="Scraped via + Add by URL.",
        criteria=[],
        skills_required=[],
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        salary_min=240_000,
        salary_max=290_000,
        equity_pct=0.05,
        score=0.84,
        score_explanation="Auto-scored from manual URL submit.",
        match_breakdown={"backend": 0.88, "platform": 0.82, "ai-ml": 0.74},
        queue_state=JobQueueState.UNSWIPED,
        tags=[Tag.BACKEND, Tag.PLATFORM],
        warm_intro_contact_id=None,
        created_at=now,
        updated_at=now,
    )
    JOBS.append(j)
    return j


# ─────────────────────────────────────────────────────────────────────────
# Public re-exports
# ─────────────────────────────────────────────────────────────────────────

__all__ = [
    # Anchor + helpers
    "TODAY",
    # Singletons
    "USER",
    "PROFILE",
    "SETTINGS",
    # Lists
    "EXPERIENCES",
    "BULLETS",
    "SKILLS",
    "EDUCATIONS",
    "PROJECTS",
    "CERTIFICATIONS",
    "JOBS",
    "JOB_SCRAPE_RUNS",
    "APPLICATIONS",
    "CONTACTS",
    "CONTACT_APPLICATION_LINKS",
    "OUTREACH_MESSAGES",
    "EMAIL_THREADS",
    "APP_EVENTS",
    "GENERATED_DOCUMENTS",
    "SCREENER_ANSWERS",
    "ATS_CREDENTIALS",
    "API_USAGE",
    # Accessors
    "by_id",
    "get_user",
    "get_profile",
    "get_experiences",
    "get_experience",
    "get_bullets",
    "get_bullet",
    "get_bullets_for_experience",
    "get_skills",
    "get_educations",
    "get_projects",
    "get_certifications",
    "get_jobs",
    "get_job",
    "discover_queue",
    "saved_jobs",
    "skipped_jobs",
    "auto_apply_queue",
    "stuck_drafts",
    "get_applications",
    "get_application",
    "applications_visible_in_tracking",
    "applications_by_status",
    "applications_in_followup_state",
    "closed_applications",
    "draft_applications",
    "application_for_job",
    "documents_for_application",
    "screener_answers_for_application",
    "unreviewed_required_screeners",
    "app_events_for_application",
    "get_contacts",
    "get_contact",
    "contacts_for_company",
    "contacts_for_application",
    "outreach_messages_for_contact",
    "outreach_messages_for_application",
    "get_email_threads",
    "get_email_thread",
    "email_threads_for_application",
    "email_signal_feed",
    "get_settings",
    "api_usage_recent",
    "llm_usage_summary",
    "kpi_active_applications",
    "kpi_response_rate_90d",
    "kpi_onsite_rate_90d",
    "kpi_offer_rate_90d",
    "pipeline_strip_counts",
    "priority_actions",
    # Mutation shim
    "_apply_status_override",
    "_create_draft",
    "_record_screener_answer",
    "_apply_failure_to_draft",
    "_set_job_queue_state",
    "_append_outreach_message",
    "_append_manual_application",
    "_append_scraped_job",
]
