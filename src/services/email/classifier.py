"""Email classifier service — plan 90 (0.5.0.02), redesigned 2026-07.

Pulls unprocessed `EmailMessage` rows and runs `classify_email` via
`tracked_call` (mandatory wrap — `engineer-llm-tracker-wrap`). Graceful-degrade
when no LLM configured: persists `unclassified_reason=NO_PROVIDER_CONFIGURED`
and skips. Mirrors `scorer.orchestrator`'s degrade pattern (BACKEND.md § H.4
clause).

2026-07 tracking redesign — per classified message:
1. Persist classification + the extracted employer/role/stage.
2. Map the message to an Application: thread link → receipt link → fuzzy
   company match on the extracted employer. Linked threads inherit the
   application so the rest of the thread auto-links.
3. Promote the thread's classification (threads used to be stuck at the
   OTHER default forever).
4. Feed the SAME status pipeline as manual tracking
   (`services.applications.update_status`): forward transitions
   (screen / interview / offer) are applied automatically with
   `trigger=AUTO_FROM_EMAIL`; REJECTION → CLOSED stays a human-confirm
   suggestion so one misclassified email can never kill a live application.
5. Unlinked messages keep their extracted company — `services.email.processes`
   groups them into the "detected interview processes" panel where the user
   can opt in ("Track it") for out-of-Naavik applications.

Priority notifications fan out via `notify.notify_priority_email`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError, get_provider
from llm.prompts.classify_email import PROMPT as CLASSIFY_PROMPT
from llm.prompts.classify_email import EmailClassificationResult
from models import (
    AppEventKind,
    Application,
    EmailMessage,
    EmailThread,
    Settings,
    UnclassifiedReason,
)
from models.enums import ApplicationStatus, EmailClassification, StatusChangeTrigger
from services import llm_tracker, notify
from services.email import status_mapper as email_status_mapper
from services.email.sync import _MAX_SENDER_EMAIL_LEN, _MAX_SUBJECT_LEN

log = logging.getLogger(__name__)

_MAX_EXTRACTED_LEN = 160


async def _get_settings(session: AsyncSession, *, user_id: int) -> Settings | None:
    return (await session.exec(select(Settings).where(Settings.user_id == user_id))).one_or_none()


async def _emit_event(
    session: AsyncSession,
    *,
    user_id: int,
    application_id: int | None,
    kind: AppEventKind,
    payload: dict[str, Any] | None = None,
) -> None:
    from models import AppEvent

    ev = AppEvent(
        user_id=user_id,
        application_id=application_id,
        kind=kind,
        payload=payload or {},
        occurred_at=datetime.now(UTC),
    )
    session.add(ev)
    await session.flush()


def _parse_result(result: Any) -> EmailClassificationResult:
    """Unpack `tracked_call`'s return into the prompt schema.

    `StructuredResult.value` is a plain dict (llm/base.py) — the pre-redesign
    code read it with `getattr(value, "classification", "other")`, which on a
    dict ALWAYS returned the default. Every email landed OTHER and the whole
    tracking pipeline sat dead. Validate explicitly instead so a schema
    mismatch is a visible failure, never a silent OTHER.
    """
    value = getattr(result, "value", None)
    if isinstance(value, EmailClassificationResult):
        return value
    if isinstance(value, dict):
        return EmailClassificationResult.model_validate(value)
    if isinstance(result, EmailClassificationResult):
        return result
    if isinstance(result, dict):
        return EmailClassificationResult.model_validate(result)
    raise ValueError(f"unexpected structured result shape: {type(result).__name__}")


def _clip(text: str | None) -> str | None:
    cleaned = (text or "").strip()
    return cleaned[:_MAX_EXTRACTED_LEN] or None


async def _link_by_company(session: AsyncSession, msg: EmailMessage) -> None:
    """Map an unlinked message to an Application via the extracted employer.

    Agency/platform/outplacement mail links via its named END-CLIENT only —
    the agency name is an intermediary, never the process (plan 95 § 3.3).
    """
    from services.email.inference import find_application_for_company
    from services.email.sender_rules import PARKED_SENDER_TYPES

    if msg.application_id is not None:
        return
    if msg.extracted_sender_type in PARKED_SENDER_TYPES:
        company = msg.extracted_end_client
    else:
        company = msg.extracted_company
    if not company:
        return

    application = await find_application_for_company(
        session, user_id=msg.user_id, company=company, role=msg.extracted_role
    )
    if application is None:
        return
    msg.application_id = application.id
    session.add(msg)
    thread = await session.get(EmailThread, msg.thread_id)
    if thread is not None and thread.application_id is None:
        thread.application_id = application.id
        session.add(thread)


async def _promote_thread_classification(session: AsyncSession, msg: EmailMessage) -> None:
    """Threads default to OTHER at sync time; carry the message signal up."""
    if msg.classification in (None, EmailClassification.OTHER):
        return
    thread = await session.get(EmailThread, msg.thread_id)
    if thread is None or thread.manually_verified:
        return
    thread.classification = msg.classification
    thread.auto_classified = True
    thread.updated_at = datetime.now(UTC)
    session.add(thread)


async def _post_classify_dispatch(
    session: AsyncSession,
    msg: EmailMessage,
    *,
    settings: Settings | None,
    stage: str | None,
    emit_received: bool = True,
) -> None:
    """Run the side-effects of a successful classification.

    - Emit EMAIL_RECEIVED AppEvent (matches plan 10 timeline contract) —
      skipped on human-reclassify re-runs (`emit_received=False`), which
      would otherwise duplicate the timeline entry (plan 95 § 3.4).
    - Link to an Application by extracted company when the thread didn't
      already carry one.
    - Feed the shared status pipeline: forward transitions auto-apply
      (`trigger=AUTO_FROM_EMAIL`); rejections surface as suggestions.
    - Fire priority notifications for INTERVIEW_REQUEST / OFFER / REJECTION /
      ASSESSMENT via `notify.notify_priority_email`.
    """
    classification = msg.classification
    if classification is None:
        return

    await _link_by_company(session, msg)
    await _promote_thread_classification(session, msg)

    if emit_received:
        await _emit_event(
            session,
            user_id=msg.user_id,
            application_id=msg.application_id,
            kind=AppEventKind.EMAIL_RECEIVED,
            payload={
                "thread_id": msg.thread_id,
                "message_id_external": msg.message_id_external,
                "sender": msg.sender_email,
                "subject_preview": msg.subject[:120],
                "classification": classification.value,
                "urgent": msg.urgency == "high",
                "auto_classified": msg.auto_classified,
                "company": msg.extracted_company,
            },
        )

    if msg.application_id is None:
        return
    application = (
        await session.exec(select(Application).where(Application.id == msg.application_id))
    ).one_or_none()
    if application is None:
        return

    # Plan 95 § 3.1 producer 1 — an interview/assessment email naming a
    # round upserts it on the linked application. Same application, next
    # round: never a second application, never a second detected process;
    # reminder spam collapses into the existing row (idempotent upsert).
    if msg.extracted_round_kind and classification in (
        EmailClassification.INTERVIEW_REQUEST,
        EmailClassification.ASSESSMENT,
    ):
        from services import applications as applications_service

        try:
            await applications_service.upsert_round(
                session,
                application=application,
                kind=msg.extracted_round_kind,
                source="email",
                state="scheduled",
                email_message_id=msg.id,
            )
        except Exception as exc:  # noqa: BLE001 — rounds must not sink classify
            log.warning("round upsert failed for message %s: %s", msg.id, exc)

    transition = email_status_mapper.suggest_status(
        application,
        classification,
        urgency=msg.urgency,
        stage=stage,
    )
    if transition is not None:
        now = datetime.now(UTC)
        msg.suggested_status = transition.suggested_status
        msg.suggested_at = now
        auto_applied = transition.suggested_status != ApplicationStatus.CLOSED
        if auto_applied:
            from services import applications as applications_service

            application = await applications_service.update_status(
                session,
                application.id,
                transition.suggested_status,
                notes=transition.reason_text,
                trigger=StatusChangeTrigger.AUTO_FROM_EMAIL,
            )
            msg.suggestion_applied_at = now
        session.add(msg)
        await _emit_event(
            session,
            user_id=msg.user_id,
            application_id=msg.application_id,
            kind=AppEventKind.EMAIL_STATUS_SUGGESTED,
            payload={
                "message_id": msg.id,
                "classification": classification.value,
                "current_status": transition.current_status.value,
                "suggested_status": transition.suggested_status.value,
                "reason": transition.reason_text,
                "applied": auto_applied,
                "dismissed": False,
            },
        )
    if settings is not None:
        try:
            await notify.notify_priority_email(
                settings=settings,
                application=application,
                classification=classification,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("notify_priority_email errored: %s", exc)


async def classify_unprocessed(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> int:
    """Classify pending EmailMessage rows.

    Picks rows with `classification IS NULL`. Returns the number of rows whose
    classification field was set on this run (LLM success path AND the
    NO_PROVIDER_CONFIGURED graceful-degrade path both count as "processed";
    transient LLM failures leave `classification=None` for the next tick).
    """
    from services.email import sender_rules

    pending = (
        await session.exec(
            select(EmailMessage)
            .where(EmailMessage.classification.is_(None))
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
        )
    ).all()
    processed = 0
    rules_cache: dict[int, list] = {}
    for msg in pending:
        settings = await _get_settings(session, user_id=msg.user_id)
        if settings is None:
            msg.unclassified_reason = UnclassifiedReason.NO_PROVIDER_CONFIGURED
            msg.classification_at = datetime.now(UTC)
            session.add(msg)
            continue
        try:
            provider = get_provider(settings)
        except LLMProviderError as exc:
            if exc.kind == "auth_required":
                msg.unclassified_reason = UnclassifiedReason.NO_PROVIDER_CONFIGURED
                msg.classification_at = datetime.now(UTC)
                msg.auto_classified = False
                session.add(msg)
                continue
            raise

        # Cap untrusted fields before they reach the prompt (PR #214 hacker M1).
        # New rows are capped at persist; this also bounds any pre-existing
        # uncapped row's prompt-injection budget.
        rendered = CLASSIFY_PROMPT.format(
            sender=msg.sender_email[:_MAX_SENDER_EMAIL_LEN],
            subject=msg.subject[:_MAX_SUBJECT_LEN],
            body=msg.snippet,
        )
        try:
            result = await llm_tracker.tracked_call(
                session=session,
                user_id=msg.user_id,
                provider=provider,
                method="structured",
                prompt_name="classify_email",
                prompt=rendered,
                schema=EmailClassificationResult,
            )
            parsed = _parse_result(result)
        except LLMProviderError as exc:
            msg.unclassified_reason = (
                UnclassifiedReason.RATE_LIMITED
                if exc.kind == "rate_limit"
                else UnclassifiedReason.LLM_FAILED
            )
            msg.classification_at = datetime.now(UTC)
            session.add(msg)
            continue
        except Exception as exc:  # noqa: BLE001
            log.warning("classify_email errored: %s", exc)
            msg.unclassified_reason = UnclassifiedReason.LLM_FAILED
            msg.classification_at = datetime.now(UTC)
            session.add(msg)
            continue

        try:
            msg.classification = EmailClassification(str(parsed.classification).strip().lower())
        except ValueError:
            msg.classification = EmailClassification.OTHER
        msg.urgency = parsed.urgency
        msg.extracted_company = _clip(parsed.company)
        msg.extracted_role = _clip(parsed.role)
        stage = (parsed.stage or "").strip().lower() or None
        if stage not in ("screen", "interview"):
            stage = None
        msg.extracted_stage = stage

        # Plan 95 § 3.1 — the specific round the email names.
        from models.interview_round import ROUND_KINDS

        round_kind = (parsed.round_kind or "").strip().lower() or None
        if round_kind not in ROUND_KINDS:
            round_kind = None
        msg.extracted_round_kind = round_kind

        # Plan 95 § 3.3 — who is talking. sender_type outside the vocabulary
        # degrades to None (LLM guess only; rules below still apply);
        # end_client must appear VERBATIM in the text the model saw, or an
        # agency email would invent clients (deterministic post-check).
        sender_type = (parsed.sender_type or "").strip().lower() or None
        if sender_type not in sender_rules.SENDER_TYPE_VOCAB:
            sender_type = None
        msg.extracted_sender_type = sender_type
        end_client = _clip(parsed.end_client)
        if end_client and end_client.lower() not in f"{msg.subject}\n{msg.snippet}".lower():
            end_client = None
        msg.extracted_end_client = end_client

        # User rule > deterministic seed > the LLM guess above.
        if msg.user_id not in rules_cache:
            rules_cache[msg.user_id] = await sender_rules.load_rules(session, user_id=msg.user_id)
        treatment = sender_rules.treatment_for(
            rules_cache[msg.user_id],
            sender_email=msg.sender_email,
            company=msg.extracted_company,
        )
        sender_rules.apply_treatment(msg, treatment)

        msg.classification_model = getattr(provider, "model", None) or getattr(
            provider, "model_name", None
        )
        msg.classification_at = datetime.now(UTC)
        msg.unclassified_reason = None
        session.add(msg)

        await _post_classify_dispatch(session, msg, settings=settings, stage=stage)
        processed += 1
    return processed
