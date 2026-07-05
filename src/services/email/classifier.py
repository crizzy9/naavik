"""Email classifier service — plan 90 (0.5.0.02).

Pulls unprocessed `EmailMessage` rows and runs `classify_email` via
`tracked_call` (mandatory wrap — `engineer-llm-tracker-wrap`). Graceful-degrade
when no LLM configured: persists `unclassified_reason=NO_PROVIDER_CONFIGURED`
and skips. Mirrors `scorer.orchestrator`'s degrade pattern (BACKEND.md § H.4
clause).

On successful classification, emits `EMAIL_RECEIVED` AppEvent and (if the
message is tied to an Application) computes a non-destructive
`SuggestedTransition` + emits `EMAIL_STATUS_SUGGESTED` AppEvent for the
human-confirm banner. Also fans out priority notifications via
`notify.notify_priority_email`.
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
    Settings,
    UnclassifiedReason,
)
from models.enums import EmailClassification
from services import llm_tracker, notify
from services.email import status_mapper as email_status_mapper
from services.email.sync import _MAX_SENDER_EMAIL_LEN, _MAX_SUBJECT_LEN

log = logging.getLogger(__name__)


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


async def _post_classify_dispatch(
    session: AsyncSession,
    msg: EmailMessage,
    *,
    settings: Settings | None,
) -> None:
    """Run the side-effects of a successful classification.

    - Emit EMAIL_RECEIVED AppEvent (matches plan 10 timeline contract).
    - If the message is linked to an Application, compute a suggestion and
      emit EMAIL_STATUS_SUGGESTED so the in-app banner can render.
    - Fire priority notifications for INTERVIEW_REQUEST / OFFER / REJECTION /
      ASSESSMENT via `notify.notify_priority_email`.
    """
    classification = msg.classification
    if classification is None:
        return

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
        },
    )

    if msg.application_id is not None:
        application = (
            await session.exec(select(Application).where(Application.id == msg.application_id))
        ).one_or_none()
        if application is not None:
            transition = email_status_mapper.suggest_status(
                application,
                classification,
                urgency=msg.urgency,
            )
            if transition is not None:
                now = datetime.now(UTC)
                msg.suggested_status = transition.suggested_status
                msg.suggested_at = now
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
                        "applied": False,
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
    pending = (
        await session.exec(
            select(EmailMessage)
            .where(EmailMessage.classification.is_(None))
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
        )
    ).all()
    processed = 0
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

        # `tracked_call` returns the provider's `StructuredResult`; the
        # `EmailClassificationResult` value sits on `.value`.
        value = getattr(result, "value", None) or result
        classification_str = getattr(value, "classification", "other")
        urgency = getattr(value, "urgency", "medium")
        try:
            msg.classification = EmailClassification(str(classification_str).lower())
        except ValueError:
            msg.classification = EmailClassification.OTHER
        msg.urgency = urgency
        msg.classification_model = getattr(provider, "model", None) or getattr(
            provider, "model_name", None
        )
        msg.classification_at = datetime.now(UTC)
        msg.unclassified_reason = None
        session.add(msg)

        await _post_classify_dispatch(session, msg, settings=settings)
        processed += 1
    return processed
