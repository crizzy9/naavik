"""Enum vocabulary for Naavik per DATA_MODEL.md § D.

Plan 09 imports these into `src/db/sample_data_models.py` (Pydantic) and
plan 10 Wave 4 promotes them to Postgres ENUM types via SQLAlchemy `sa_Enum`.
String values are stable contracts — never reorder.
"""

from __future__ import annotations

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
    STALE = "stale"
    FAILED = "failed"


class ReferralState(StrEnum):
    NONE = "none"
    REQUESTED = "requested"
    IN_FLIGHT = "in_flight"
    PROVIDED = "provided"
    DECLINED = "declined"


class RecruiterState(StrEnum):
    NONE = "none"
    ENGAGED = "engaged"
    RESPONDED = "responded"
    SILENT = "silent"
    STALLED = "stalled"


class JobQueueState(StrEnum):
    UNSWIPED = "unswiped"
    SAVED = "saved"
    SKIPPED = "skipped"
    QUEUED_FOR_AUTO_APPLY = "queued_for_auto_apply"
    APPLIED = "applied"


class JobSource(StrEnum):
    AUTOMATED = "automated"
    MANUAL = "manual"


class BulletSelectionOverride(StrEnum):
    ALWAYS_INCLUDE = "always_include"
    NEVER_INCLUDE = "never_include"


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
    OPEN_TO_LIST = "open_to_list"
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
