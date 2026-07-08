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
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
    ApplicationStatus,
    EmailMessage,
    EmailThread,
    StatusChangeTrigger,
)
from models.enums import EmailClassification
from services.email import status_mapper
from services.email.inference import (
    _company_matches,
    _find_library_job,
    canonical_company_key,
    load_company_alias_map,
)

log = logging.getLogger(__name__)

# Signals that indicate a live hiring process (receipts ride the deterministic
# inference path; OTHER/FOLLOW_UP alone never open a process).
_PROCESS_SIGNALS = (
    EmailClassification.INTERVIEW_REQUEST,
    EmailClassification.ASSESSMENT,
    EmailClassification.OFFER,
    EmailClassification.REJECTION,
)

# Rejection-shaped phrasing (plan 95 § 3.4.4, regex approved by owner).
# A tiebreaker prompt to the HUMAN only — a match flags "possible rejection —
# confirm?" on the group; it never flips state itself.
REJECTION_SHAPE_RE = re.compile(
    r"not moving forward|moving forward with other|other candidates"
    r"|position has been filled|role has been filled|unable to move forward"
    r"|decided not to proceed|not to move forward|no longer under consideration"
    r"|pursue other applicants|will not be progressing|decided to go (?:in )?another direction",
    re.I,
)


@dataclass(slots=True)
class ParkedSenderGroup:
    """Agency/platform/outplacement mail with no named end-client — parked
    in a collapsed panel section, never a process, never notified (§ 3.3)."""

    sender_domain: str
    company: str
    message_count: int
    last_seen: datetime
    latest_subject: str
    latest_message_id: int | None


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
    # § 3.4.4 rejection guard: a later FOLLOW_UP/OTHER email of this company
    # matches the rejection regex — surface a confirm chip, change nothing.
    possible_rejection_message_id: int | None = None
    # Latest message's sender domain — the "Flag sender…" unit (§ 3.3).
    sender_domain: str = ""


def _norm_company(name: str, aliases: dict[str, str] | None = None) -> str:
    # Canonical key so company variants ("Brico"/"Brico.ai") land in ONE
    # group; the display name still comes from the raw extracted value.
    return canonical_company_key(name, aliases=aliases)


def _group_company(msg: EmailMessage) -> str:
    """The company a message evidences a process AT: the named end-client
    for agency mail, the extracted employer otherwise (plan 95 § 3.3)."""
    return msg.extracted_end_client or msg.extracted_company or ""


def _is_parked(msg: EmailMessage, rules: list | None = None) -> bool:
    """Parked = intermediary sender with no named end-client.

    Checks the persisted sender_type AND the rule/seed layers at read time —
    mail classified before the sender_type column existed (or before a rule
    landed) must park retroactively, not linger as a detected process.
    """
    from services.email import sender_rules

    if msg.extracted_end_client:
        return False
    if msg.extracted_sender_type in sender_rules.PARKED_SENDER_TYPES:
        return True
    treatment = sender_rules.treatment_for(
        rules or [], sender_email=msg.sender_email, company=msg.extracted_company
    )
    return treatment == "agency"


def _aware(dt: datetime) -> datetime:
    # The sqlite test substrate round-trips DateTime(timezone=True) as naive;
    # normalize before comparing across separately-loaded rows.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _sender_domain(sender_email: str) -> str:
    from services.email.sender_rules import sender_domain

    return sender_domain(sender_email)


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


async def _rejection_shaped_strays(
    session: AsyncSession, *, user_id: int
) -> dict[str, EmailMessage]:
    """FOLLOW_UP/OTHER messages whose text matches the rejection regex,
    keyed by canonical company — candidates for the § 3.4.4 confirm chip
    (misfiled rejections group outside the signal query above)."""
    aliases = await load_company_alias_map(session, user_id=user_id)
    rows = (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.user_id == user_id,
                EmailMessage.application_id.is_(None),
                EmailMessage.process_dismissed_at.is_(None),
                EmailMessage.extracted_company.is_not(None),
                EmailMessage.classification.in_(  # type: ignore[union-attr]
                    (EmailClassification.FOLLOW_UP, EmailClassification.OTHER)
                ),
            )
            .order_by(EmailMessage.received_at.asc())
        )
    ).all()
    out: dict[str, EmailMessage] = {}
    for msg in rows:
        text_seen = f"{msg.subject}\n{msg.body_excerpt or msg.snippet}"
        if REJECTION_SHAPE_RE.search(text_seen):
            out[_norm_company(msg.extracted_company or "", aliases)] = msg
    return out


async def list_detected_processes(session: AsyncSession, *, user_id: int) -> list[DetectedProcess]:
    """Group unlinked interview-signal messages into per-company processes.

    Parked mail (agency/platform/outplacement with no named end-client) is
    excluded — it lives in `list_parked_sender_groups` instead. Agency mail
    WITH an end-client groups under the end-client (§ 3.3).
    """
    from services.email import sender_rules

    aliases = await load_company_alias_map(session, user_id=user_id)
    rules = await sender_rules.load_rules(session, user_id=user_id)
    messages = await _unlinked_signal_messages(session, user_id=user_id)
    groups: dict[str, list[EmailMessage]] = {}
    for msg in messages:
        if _is_parked(msg, rules):
            continue
        groups.setdefault(_norm_company(_group_company(msg), aliases), []).append(msg)
    strays = await _rejection_shaped_strays(session, user_id=user_id)

    out: list[DetectedProcess] = []
    for key, msgs in groups.items():
        timeline = [(m.classification, _stage_hint(m)) for m in msgs if m.classification]
        status, closed_reason = status_mapper.status_for_email_timeline(timeline)
        roles = [m.extracted_role for m in msgs if m.extracted_role]
        display_company = _group_company(msgs[-1])
        stray = strays.get(key)
        possible_rejection = (
            stray.id
            if stray is not None
            and status != ApplicationStatus.CLOSED
            and _aware(stray.received_at) > _aware(msgs[0].received_at)
            else None
        )
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
                possible_rejection_message_id=possible_rejection,
                sender_domain=_sender_domain(msgs[-1].sender_email),
            )
        )
    out.sort(key=lambda p: p.last_seen, reverse=True)
    return out


def _stage_hint(msg: EmailMessage) -> str | None:
    """Interview-stage hint for timeline derivation (persisted at classify)."""
    return msg.extracted_stage


async def list_parked_sender_groups(
    session: AsyncSession, *, user_id: int
) -> list[ParkedSenderGroup]:
    """The collapsed "Agencies & platforms" section (§ 3.3): parked so
    nothing is irrecoverably dropped, fully silent otherwise."""
    from services.email import sender_rules
    from services.email.sender_rules import sender_domain

    rules = await sender_rules.load_rules(session, user_id=user_id)
    messages = await _unlinked_signal_messages(session, user_id=user_id)
    groups: dict[str, list[EmailMessage]] = {}
    for msg in messages:
        if _is_parked(msg, rules):
            groups.setdefault(sender_domain(msg.sender_email), []).append(msg)

    out = [
        ParkedSenderGroup(
            sender_domain=domain,
            company=msgs[-1].extracted_company or domain,
            message_count=len(msgs),
            last_seen=msgs[-1].received_at,
            latest_subject=msgs[-1].subject,
            latest_message_id=msgs[-1].id,
        )
        for domain, msgs in groups.items()
    ]
    out.sort(key=lambda g: g.last_seen, reverse=True)
    return out


async def track_process(
    session: AsyncSession,
    *,
    user_id: int,
    company: str,
    status_override: ApplicationStatus | None = None,
) -> Application | None:
    """User clicked "Track it" — pull the detected process into the pipeline.

    Creates (or reuses) the library Job, creates the Application at the stage
    the email timeline implies, links every message/thread of the company,
    and writes the STATUS_CHANGE AppEvent trail so the Tracking timeline
    reflects how the process actually unfolded.

    `status_override` is the § 3.4 "Wrong stage?" affordance: the human's
    stage pick replaces the derived one at track time.
    """
    from services.email import sender_rules

    aliases = await load_company_alias_map(session, user_id=user_id)
    rules = await sender_rules.load_rules(session, user_id=user_id)
    messages = [
        m
        for m in await _unlinked_signal_messages(session, user_id=user_id)
        if not _is_parked(m, rules)
        and _company_matches(company, _group_company(m), aliases=aliases)
    ]
    if not messages:
        return None

    timeline = [(m.classification, _stage_hint(m)) for m in messages if m.classification]
    status, closed_reason = status_mapper.status_for_email_timeline(timeline)
    overridden = status_override is not None and status_override != status
    if overridden and status_override is not None:
        # Plan 96a / B4 — an explicit human CLOSED pick needs a reason for
        # the trail writer; the timeline can only have derived one when it
        # already said CLOSED (in which case there is no override), so the
        # human pick defaults to rejected_by_them.
        if status_override == ApplicationStatus.CLOSED:
            from models.enums import ClosedReason

            status, closed_reason = status_override, ClosedReason.REJECTED_BY_THEM
        else:
            status, closed_reason = status_override, None
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

    from services import applications as applications_service

    now = datetime.now(UTC)
    # Plan 95 § 3.7 — one shared trail-writing path for mid-stage creation
    # (this flow and the manual "Where does this stand?" control).
    application = await applications_service.create_tracked_application(
        session,
        user_id=user_id,
        job=job,
        status=status,
        closed_reason=closed_reason,
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
        actor="email_process_tracker",
        first_note="Tracked from inbox (detected interview process)",
        stage_note=(
            "Stage set by you at track time"
            if overridden
            else "Stage derived from the email timeline"
        ),
        stage_occurred_at=messages[-1].received_at,
        stage_trigger=(
            StatusChangeTrigger.MANUAL if overridden else StatusChangeTrigger.AUTO_FROM_EMAIL
        ),
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
    aliases = await load_company_alias_map(session, user_id=user_id)
    messages = [
        m
        for m in await _unlinked_signal_messages(session, user_id=user_id)
        if _company_matches(company, _group_company(m), aliases=aliases)
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
