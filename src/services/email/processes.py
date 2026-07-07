"""Detected interview processes — 2026-07 tracking redesign.

Classified messages that could not be mapped to any Application (the user
applied outside Naavik: no receipt in the synced window, no library job)
still carry an `extracted_company`. This module groups them into per-company
"detected processes": a timeline of interview signals with an inferred
pipeline stage.

The Tracking page surfaces each process with a Track / Dismiss choice:

- Track → create the Job (`source=email`) + Application at the inferred
  stage, link every message/thread of that company, and write the
  STATUS_CHANGE AppEvent trail — from then on the process rides the SAME
  status pipeline as everything else.
- Dismiss → stamp `process_dismissed_at` on the group's messages; new mail
  from that company starts a fresh group (deliberate: a company you dismissed
  once may still start a real process later).

Deterministic + read-mostly; the LLM work happened at classification time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEvent,
    AppEventKind,
    Application,
    ApplicationStatus,
    DocsState,
    EmailMessage,
    EmailThread,
    RecruiterState,
    ReferralState,
    StatusChangeTrigger,
)
from models.enums import EmailClassification
from services.email import status_mapper
from services.email.inference import _company_matches, _find_library_job

log = logging.getLogger(__name__)

# Signals that indicate a live hiring process (receipts ride the deterministic
# inference path; OTHER/FOLLOW_UP alone never open a process).
_PROCESS_SIGNALS = (
    EmailClassification.INTERVIEW_REQUEST,
    EmailClassification.ASSESSMENT,
    EmailClassification.OFFER,
    EmailClassification.REJECTION,
)


@dataclass(slots=True)
class DetectedProcess:
    company: str
    role: str | None
    status: ApplicationStatus
    closed_reason: object | None
    message_count: int
    first_seen: datetime
    last_seen: datetime
    latest_subject: str
    message_ids: list[int] = field(default_factory=list)


def _norm_company(name: str) -> str:
    return " ".join(name.lower().split())


async def _unlinked_signal_messages(session: AsyncSession, *, user_id: int) -> list[EmailMessage]:
    rows = (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.user_id == user_id,
                EmailMessage.application_id.is_(None),
                EmailMessage.process_dismissed_at.is_(None),
                EmailMessage.extracted_company.is_not(None),
                EmailMessage.classification.in_(_PROCESS_SIGNALS),  # type: ignore[union-attr]
            )
            .order_by(EmailMessage.received_at.asc())
        )
    ).all()
    return list(rows)


async def list_detected_processes(session: AsyncSession, *, user_id: int) -> list[DetectedProcess]:
    """Group unlinked interview-signal messages into per-company processes."""
    messages = await _unlinked_signal_messages(session, user_id=user_id)
    groups: dict[str, list[EmailMessage]] = {}
    for msg in messages:
        groups.setdefault(_norm_company(msg.extracted_company or ""), []).append(msg)

    out: list[DetectedProcess] = []
    for _key, msgs in groups.items():
        timeline = [(m.classification, _stage_hint(m)) for m in msgs if m.classification]
        status, closed_reason = status_mapper.status_for_email_timeline(timeline)
        roles = [m.extracted_role for m in msgs if m.extracted_role]
        display_company = msgs[-1].extracted_company or ""
        out.append(
            DetectedProcess(
                company=display_company,
                role=roles[-1] if roles else None,
                status=status,
                closed_reason=closed_reason,
                message_count=len(msgs),
                first_seen=msgs[0].received_at,
                last_seen=msgs[-1].received_at,
                latest_subject=msgs[-1].subject,
                message_ids=[m.id for m in msgs if m.id is not None],
            )
        )
    out.sort(key=lambda p: p.last_seen, reverse=True)
    return out


def _stage_hint(msg: EmailMessage) -> str | None:
    """Interview-stage hint for timeline derivation (persisted at classify)."""
    return msg.extracted_stage


async def track_process(session: AsyncSession, *, user_id: int, company: str) -> Application | None:
    """User clicked "Track it" — pull the detected process into the pipeline.

    Creates (or reuses) the library Job, creates the Application at the stage
    the email timeline implies, links every message/thread of the company,
    and writes the STATUS_CHANGE AppEvent trail so the Tracking timeline
    reflects how the process actually unfolded.
    """
    messages = [
        m
        for m in await _unlinked_signal_messages(session, user_id=user_id)
        if _company_matches(company, m.extracted_company or "")
    ]
    if not messages:
        return None

    timeline = [(m.classification, _stage_hint(m)) for m in messages if m.classification]
    status, closed_reason = status_mapper.status_for_email_timeline(timeline)
    roles = [m.extracted_role for m in messages if m.extracted_role]
    role = roles[-1] if roles else None
    display_company = messages[-1].extracted_company or company

    job = await _find_library_job(session, user_id=user_id, company=display_company, role=role)
    if job is None:
        job = await _create_job_for_process(
            session,
            user_id=user_id,
            company=display_company,
            role=role,
            msg=messages[-1],
        )

    now = datetime.now(UTC)
    application = Application(
        user_id=user_id,
        job_id=job.id,
        company=job.company,
        role=job.role,
        team=job.team,
        location=job.location,
        board=job.board,
        external_url=job.url if not job.url.startswith("manual://") else None,
        status=status,
        closed_reason=closed_reason,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        applied_at=messages[0].received_at,
        submission_artifacts={
            "inferred": {
                "email_message_id": messages[0].id,
                "confirmed": True,
                "inferred_at": now.isoformat(),
                "subject": (messages[-1].subject or "")[:200],
                "via": "detected_process",
            }
        },
        created_at=now,
        updated_at=now,
    )
    session.add(application)
    await session.flush()

    # Timeline trail: APPLIED at first-email date, then the derived stage.
    session.add(
        AppEvent(
            user_id=user_id,
            application_id=application.id,
            kind=AppEventKind.STATUS_CHANGE,
            occurred_at=messages[0].received_at,
            payload={
                "from": None,
                "to": ApplicationStatus.APPLIED.value,
                "trigger": StatusChangeTrigger.AUTO_FROM_EMAIL.value,
                "is_forward": True,
                "notes": "Tracked from inbox (detected interview process)",
            },
            actor="email_process_tracker",
        )
    )
    if status != ApplicationStatus.APPLIED:
        session.add(
            AppEvent(
                user_id=user_id,
                application_id=application.id,
                kind=AppEventKind.STATUS_CHANGE,
                occurred_at=messages[-1].received_at,
                payload={
                    "from": ApplicationStatus.APPLIED.value,
                    "to": status.value,
                    "trigger": StatusChangeTrigger.AUTO_FROM_EMAIL.value,
                    "is_forward": status != ApplicationStatus.CLOSED,
                    "notes": "Stage derived from the email timeline",
                },
                actor="email_process_tracker",
            )
        )

    linked_threads: set[int] = set()
    for msg in messages:
        msg.application_id = application.id
        session.add(msg)
        if msg.thread_id not in linked_threads:
            thread = await session.get(EmailThread, msg.thread_id)
            if thread is not None and thread.application_id is None:
                thread.application_id = application.id
                session.add(thread)
            linked_threads.add(msg.thread_id)
    await session.flush()
    log.info(
        "tracked detected process company=%r status=%s messages=%d application=%s",
        display_company,
        status.value,
        len(messages),
        application.id,
    )
    return application


async def dismiss_process(session: AsyncSession, *, user_id: int, company: str) -> int:
    """User clicked "Not mine" — hide this company's current group."""
    messages = [
        m
        for m in await _unlinked_signal_messages(session, user_id=user_id)
        if _company_matches(company, m.extracted_company or "")
    ]
    now = datetime.now(UTC)
    for msg in messages:
        msg.process_dismissed_at = now
        session.add(msg)
    await session.flush()
    return len(messages)


async def _create_job_for_process(
    session: AsyncSession,
    *,
    user_id: int,
    company: str,
    role: str | None,
    msg: EmailMessage,
):
    """Metadata-only library Job for a tracked process (no posting URL known)."""
    import hashlib

    from models.enums import ApplicationBoard, JobSource
    from services import jobs as job_service
    from services.email.inference import UNKNOWN_ROLE, _sender_board

    external_id = (
        f"email-{hashlib.sha1(f'{msg.id}:{msg.message_id_external}'.encode()).hexdigest()[:12]}"
    )
    job, _created = await job_service.upsert_job(
        session,
        user_id=user_id,
        source=JobSource.EMAIL,
        external_id=external_id,
        raw={
            "board": _sender_board(msg.sender_email) or ApplicationBoard.COMPANY_DIRECT,
            "url": f"manual://email/{msg.id}",
            "url_type": "email_receipt",
            "company": company,
            "role": role or UNKNOWN_ROLE,
            "description": (
                f"Tracked from the interview email “{msg.subject}” received "
                f"{msg.received_at:%Y-%m-%d}. No posting URL was present — "
                "edit this job to attach one."
            ),
        },
    )
    return job
