"""Naavik SQLModel entities — 1:1 with `docs/design/DATA_MODEL.md` § C.

Wave 4 of plan 10 promotes the Pydantic shadow models in
`src/db/sample_data_models.py` to real `SQLModel(table=True)` rows.
Sample-data fixtures (plan 09) still use the shadow classes; seed.py
converts shadow → dict → SQLModel during `db/seed.py`.

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
    JobSource,
    LLMProvider,
    OutreachIntent,
    OutreachStatus,
    Race,
    RecruiterState,
    ReferralState,
    RelocateOpenness,
    ScreenerAnswerSource,
    ScreenerQuestionType,
    StatusChangeTrigger,
    Tag,
    VeteranStatus,
    VisaSponsorship,
    WorkAuthorization,
)
from .event import AppEvent
from .job import Job
from .profile import Bullet, Certification, Education, Experience, Profile, Project, Skill
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
    "Settings",
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
    "JobSource",
    "LLMProvider",
    "OutreachIntent",
    "OutreachStatus",
    "Race",
    "RecruiterState",
    "ReferralState",
    "RelocateOpenness",
    "ScreenerAnswerSource",
    "ScreenerQuestionType",
    "StatusChangeTrigger",
    "Tag",
    "VeteranStatus",
    "VisaSponsorship",
    "WorkAuthorization",
]
