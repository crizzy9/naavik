"""AppEvent payload schemas — per-kind discriminated Pydantic union.

Per DATA_MODEL.md § M. Payload JSONB on `AppEvent` is opaque to Postgres but
shaped per-kind in Python. Service layer reads typed payloads via this module's
`parse_payload(kind, raw)` helper; writes go through `dump_payload(payload)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .enums import (
    AppEventKind,
    EmailClassification,
    GeneratedDocumentKind,
    OutreachIntent,
    StatusChangeTrigger,
)


class StatusChangePayload(BaseModel):
    kind: Literal[AppEventKind.STATUS_CHANGE] = AppEventKind.STATUS_CHANGE
    from_status: str | None = None
    to_status: str
    triggered_by: StatusChangeTrigger
    notes: str | None = None


class DocsGeneratedPayload(BaseModel):
    kind: Literal[AppEventKind.DOCS_GENERATED] = AppEventKind.DOCS_GENERATED
    generated_document_id: int
    document_kind: GeneratedDocumentKind
    model: str
    cost_usd: float
    token_count: int
    page_count: int | None = None


class DocsFailedPayload(BaseModel):
    kind: Literal[AppEventKind.DOCS_FAILED] = AppEventKind.DOCS_FAILED
    document_kind: GeneratedDocumentKind
    error: str
    retry_count: int


class ReferralRequestedPayload(BaseModel):
    kind: Literal[AppEventKind.REFERRAL_REQUESTED] = AppEventKind.REFERRAL_REQUESTED
    contact_id: int
    via_channel: str


class ReferralProvidedPayload(BaseModel):
    kind: Literal[AppEventKind.REFERRAL_PROVIDED] = AppEventKind.REFERRAL_PROVIDED
    contact_id: int
    provided_at: datetime


class EmailReceivedPayload(BaseModel):
    kind: Literal[AppEventKind.EMAIL_RECEIVED] = AppEventKind.EMAIL_RECEIVED
    thread_id: int
    message_id_external: str
    sender: str
    subject_preview: str
    classification: EmailClassification
    urgent: bool = False
    auto_classified: bool = True


class EmailSentPayload(BaseModel):
    kind: Literal[AppEventKind.EMAIL_SENT] = AppEventKind.EMAIL_SENT
    thread_id: int
    message_id_external: str
    recipient: str
    subject_preview: str


class LinkedInDmSentPayload(BaseModel):
    kind: Literal[AppEventKind.LINKEDIN_DM_SENT] = AppEventKind.LINKEDIN_DM_SENT
    outreach_message_id: int
    contact_id: int
    intent: OutreachIntent


class LinkedInDmRepliedPayload(BaseModel):
    kind: Literal[AppEventKind.LINKEDIN_DM_REPLIED] = AppEventKind.LINKEDIN_DM_REPLIED
    outreach_message_id: int
    contact_id: int
    replied_at: datetime
    summary: str | None = None


class NoteAddedPayload(BaseModel):
    kind: Literal[AppEventKind.NOTE_ADDED] = AppEventKind.NOTE_ADDED
    note_text_preview: str
    full_note_field: str = "application.notes"


class InterviewScheduledPayload(BaseModel):
    kind: Literal[AppEventKind.INTERVIEW_SCHEDULED] = AppEventKind.INTERVIEW_SCHEDULED
    when: datetime
    where: str | None = None
    contact_ids: list[int] = Field(default_factory=list)
    calendar_event_id: str | None = None


AppEventPayload = Annotated[
    StatusChangePayload
    | DocsGeneratedPayload
    | DocsFailedPayload
    | ReferralRequestedPayload
    | ReferralProvidedPayload
    | EmailReceivedPayload
    | EmailSentPayload
    | LinkedInDmSentPayload
    | LinkedInDmRepliedPayload
    | NoteAddedPayload
    | InterviewScheduledPayload,
    Field(discriminator="kind"),
]


_PAYLOAD_BY_KIND: dict[AppEventKind, type[BaseModel]] = {
    AppEventKind.STATUS_CHANGE: StatusChangePayload,
    AppEventKind.DOCS_GENERATED: DocsGeneratedPayload,
    AppEventKind.DOCS_FAILED: DocsFailedPayload,
    AppEventKind.REFERRAL_REQUESTED: ReferralRequestedPayload,
    AppEventKind.REFERRAL_PROVIDED: ReferralProvidedPayload,
    AppEventKind.EMAIL_RECEIVED: EmailReceivedPayload,
    AppEventKind.EMAIL_SENT: EmailSentPayload,
    AppEventKind.LINKEDIN_DM_SENT: LinkedInDmSentPayload,
    AppEventKind.LINKEDIN_DM_REPLIED: LinkedInDmRepliedPayload,
    AppEventKind.NOTE_ADDED: NoteAddedPayload,
    AppEventKind.INTERVIEW_SCHEDULED: InterviewScheduledPayload,
}


def parse_payload(kind: AppEventKind, raw: dict) -> BaseModel:
    """Validate raw JSONB payload against the schema for `kind`."""
    schema = _PAYLOAD_BY_KIND[kind]
    return schema.model_validate({**raw, "kind": kind})


def dump_payload(payload: BaseModel) -> dict:
    """Serialize a typed payload to JSONB-shaped dict (without `kind` field)."""
    raw = payload.model_dump(mode="json")
    raw.pop("kind", None)
    return raw
