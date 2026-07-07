"""Naavik SQLModel entities — 1:1 with `docs/design/DATA_MODEL.md` § C.

Wave 4 of plan 10 promotes the Pydantic shadow models in
`src/db/sample_data_models.py` to real `SQLModel(table=True)` rows.
Sample-data fixtures (plan 09) still use the shadow classes; seed.py
converts shadow → dict → SQLModel during `db/seed.py`.

Plan 27 (0.2.0.05, 2026-05-19) adds the `JobScrapeRun` entity for
scrape-side observability + extends the `JobSource` / `VisaRestriction` /
`RemotePolicy` / `SeniorityLevel` / `JobScrapeStatus` enum vocabulary.

Single source for `from src.models import User, Profile, ...`.
"""

from __future__ import annotations

from .api_usage import ApiUsage
from .application import (
    Application,
    ApplicationScreenerAnswer,
    ATSCredential,
    GeneratedDocument,
)
from .calendar_event import CalendarConnection, CalendarEvent
from .contact import Contact, ContactApplicationLink, OutreachMessage
from .email import EmailThread
from .email_account import EmailAccount
from .email_corrections import ClassificationCorrection, CompanyAlias, SenderRule
from .email_message import EmailMessage
from .enums import (
    AppEventKind,
    ApplicationBoard,
    ApplicationStatus,
    AtsLoginStatus,
    BulletSelectionOverride,
    ClosedReason,
    ContactType,
    DeploymentMode,
    DisabilityStatus,
    DocsState,
    EmailAccountProvider,
    EmailAccountStatus,
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
    SigningAlgorithm,
    StatusChangeTrigger,
    Tag,
    TenantSigningKeyStatus,
    UnclassifiedReason,
    VeteranStatus,
    VisaRestriction,
    VisaSponsorship,
    WorkAuthorization,
)
from .event import AppEvent
from .interview_round import InterviewRound
from .job import Job, JobCreate, JobFilter, JobRead, JobUpdate
from .job_embedding import EMBEDDING_DIM, JobEmbedding
from .job_scrape_run import JobScrapeRun, JobScrapeRunRead
from .profile import Bullet, Certification, Education, Experience, Profile, Project, Skill
from .profile_answer import ProfileAnswer
from .profile_embedding import ProfileEmbedding
from .revoked_jwt import RevokedJwt
from .settings import Settings
from .tenant import Tenant
from .tenant_signing_key import TenantSigningKey
from .user import User

__all__ = [
    # Entities
    "User",
    "Profile",
    "Experience",
    "Bullet",
    "Skill",
    "Education",
    "Project",
    "Certification",
    "Job",
    "JobEmbedding",
    "JobScrapeRun",
    "ProfileAnswer",
    "ProfileEmbedding",
    "Application",
    "ApplicationScreenerAnswer",
    "GeneratedDocument",
    "ATSCredential",
    "Contact",
    "ContactApplicationLink",
    "OutreachMessage",
    "EmailThread",
    "CalendarConnection",
    "CalendarEvent",
    "EmailAccount",
    "EmailMessage",
    "ClassificationCorrection",
    "CompanyAlias",
    "SenderRule",
    "InterviewRound",
    "AppEvent",
    "ApiUsage",
    "RevokedJwt",
    "Settings",
    "Tenant",
    "TenantSigningKey",
    # Constants
    "EMBEDDING_DIM",
    # Pydantic API schemas
    "JobCreate",
    "JobFilter",
    "JobRead",
    "JobUpdate",
    "JobScrapeRunRead",
    # Enums (re-export)
    "AppEventKind",
    "ApplicationBoard",
    "ApplicationStatus",
    "AtsLoginStatus",
    "BulletSelectionOverride",
    "ClosedReason",
    "ContactType",
    "DeploymentMode",
    "DisabilityStatus",
    "DocsState",
    "EmailAccountProvider",
    "EmailAccountStatus",
    "EmailClassification",
    "Gender",
    "GeneratedDocumentKind",
    "JobQueueState",
    "JobScrapeStatus",
    "JobSource",
    "LLMProvider",
    "OutreachIntent",
    "OutreachStatus",
    "Race",
    "RecruiterState",
    "ReferralState",
    "RelocateOpenness",
    "RemotePolicy",
    "ScreenerAnswerSource",
    "ScreenerQuestionType",
    "SeniorityLevel",
    "SigningAlgorithm",
    "StatusChangeTrigger",
    "Tag",
    "TenantSigningKeyStatus",
    "UnclassifiedReason",
    "VeteranStatus",
    "VisaRestriction",
    "VisaSponsorship",
    "WorkAuthorization",
]
