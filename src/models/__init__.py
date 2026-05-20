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
from .contact import Contact, ContactApplicationLink, OutreachMessage
from .email import EmailThread
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
    StatusChangeTrigger,
    Tag,
    VeteranStatus,
    VisaRestriction,
    VisaSponsorship,
    WorkAuthorization,
)
from .event import AppEvent
from .job import Job, JobCreate, JobFilter, JobRead, JobUpdate
from .job_scrape_run import JobScrapeRun, JobScrapeRunRead
from .profile import Bullet, Certification, Education, Experience, Profile, Project, Skill
from .revoked_jwt import RevokedJwt
from .settings import Settings
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
    "JobScrapeRun",
    "Application",
    "ApplicationScreenerAnswer",
    "GeneratedDocument",
    "ATSCredential",
    "Contact",
    "ContactApplicationLink",
    "OutreachMessage",
    "EmailThread",
    "AppEvent",
    "ApiUsage",
    "RevokedJwt",
    "Settings",
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
    "StatusChangeTrigger",
    "Tag",
    "VeteranStatus",
    "VisaRestriction",
    "VisaSponsorship",
    "WorkAuthorization",
]
