"""Human corrections to the email pipeline — plan 95 § 3.4.

Every affordance here writes through existing seams (classification dispatch,
alias-aware grouping) AND persists a `ClassificationCorrection` row — the
corrections table is the system's labeled dataset (few-shot exemplars in the
classify prompt, `NAAVIK_EVAL_LLM=1` regression evals). A correction is never
just a state fix; it is training signal.

- `reclassify_message` — six-label relabel; re-runs the post-classify
  dispatch so linking/transitions follow the corrected perception.
- `unlink_thread` — detach a wrongly auto-linked conversation from its
  application; the messages become detected-process candidates again.
- `merge_company` — "these two groups are the same company": writes a
  `CompanyAlias` consulted by grouping + matching forever after, and relinks
  the merged group's messages when the target has a live application.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    ClassificationCorrection,
    CompanyAlias,
    EmailMessage,
    EmailThread,
)
from models.enums import EmailClassification
from services.email.inference import (
    canonical_company_key,
    find_application_for_company,
    load_company_alias_map,
)

log = logging.getLogger(__name__)


class CorrectionError(Exception):
    """Ownership / lookup failure — routes map this to 404."""


async def _owned_message(session: AsyncSession, *, user_id: int, message_id: int) -> EmailMessage:
    msg = await session.get(EmailMessage, message_id)
    if msg is None or msg.user_id != user_id:
        raise CorrectionError("No such email message")
    return msg


async def reclassify_message(
    session: AsyncSession,
    *,
    user_id: int,
    message_id: int,
    to_classification: EmailClassification,
) -> EmailMessage:
    """Human relabels one message; the fix sticks and is recorded.

    Sets `auto_classified=False` (the LLM never overwrites a human label),
    stamps the correction row, then re-runs the post-classify dispatch so the
    corrected label drives linking + status exactly as a fresh classification
    would — minus the duplicate EMAIL_RECEIVED event and notifications.
    """
    msg = await _owned_message(session, user_id=user_id, message_id=message_id)
    from_classification = msg.classification

    session.add(
        ClassificationCorrection(
            user_id=user_id,
            message_id=message_id,
            kind="reclassify",
            from_classification=(from_classification.value if from_classification else None),
            to_classification=to_classification.value,
            from_company=msg.extracted_company,
            to_company=msg.extracted_company,
        )
    )

    msg.classification = to_classification
    msg.auto_classified = False
    msg.unclassified_reason = None
    msg.classification_at = datetime.now(UTC)
    # A stale pending suggestion from the OLD label must not survive the
    # relabel; the dispatch below derives a fresh one when warranted.
    if msg.suggestion_applied_at is None and msg.suggestion_dismissed_at is None:
        msg.suggested_status = None
        msg.suggested_at = None
    msg.updated_at = datetime.now(UTC)
    session.add(msg)

    # Thread mirrors the human's label and stops auto-promotion over it.
    thread = await session.get(EmailThread, msg.thread_id)
    if thread is not None:
        thread.classification = to_classification
        thread.auto_classified = False
        thread.manually_verified = True
        thread.updated_at = datetime.now(UTC)
        session.add(thread)

    from services.email.classifier import _post_classify_dispatch

    await _post_classify_dispatch(
        session,
        msg,
        settings=None,  # human-initiated: no notification fan-out
        stage=msg.extracted_stage,
        emit_received=False,
    )
    await session.flush()
    # Plan 96e — a correction is new information: re-derive the affected
    # application from ALL evidence under the corrected label.
    await _reconcile_after_correction(session, msg.application_id, thread_id=msg.thread_id)
    log.info(
        "reclassified message %s: %s → %s",
        message_id,
        from_classification.value if from_classification else None,
        to_classification.value,
    )
    return msg


async def _reconcile_after_correction(
    session: AsyncSession, application_id: int | None, *, thread_id: int | None = None
) -> None:
    """Plan 96e trigger — best-effort; a correction must land even when the
    follow-up reconcile trips."""
    if application_id is None:
        return
    from services.email import reconcile as reconcile_service

    try:
        await reconcile_service.reconcile_application(
            session,
            application_id=application_id,
            triggering_thread_ids={thread_id} if thread_id is not None else None,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("post-correction reconcile failed for application %s: %s", application_id, exc)


async def unlink_thread(session: AsyncSession, *, user_id: int, thread_id: int) -> int:
    """Detach a wrongly auto-linked thread from its application.

    Clears `application_id` on the thread and every message in it, stamps a
    correction row on the latest message. Returns messages unlinked.
    """
    thread = await session.get(EmailThread, thread_id)
    if thread is None or thread.user_id != user_id or thread.application_id is None:
        raise CorrectionError("No linked thread to unlink")
    detached_from = thread.application_id

    messages = (
        await session.exec(
            select(EmailMessage)
            .where(EmailMessage.thread_id == thread_id, EmailMessage.user_id == user_id)
            .order_by(EmailMessage.received_at.asc())
        )
    ).all()

    from services.email.service import unlink_thread_links

    unlink_thread_links(thread)
    thread.updated_at = datetime.now(UTC)
    session.add(thread)
    for msg in messages:
        msg.application_id = None
        msg.updated_at = datetime.now(UTC)
        session.add(msg)

    if messages:
        latest = messages[-1]
        session.add(
            ClassificationCorrection(
                user_id=user_id,
                message_id=latest.id or 0,
                kind="unlink",
                from_classification=(
                    latest.classification.value if latest.classification else None
                ),
                to_classification=(latest.classification.value if latest.classification else None),
                from_company=latest.extracted_company,
                to_company=None,
            )
        )
    await session.flush()
    # Plan 96e — losing a conversation is new information for the application
    # it was detached from (its stage may have rested on that evidence).
    await _reconcile_after_correction(session, detached_from)
    log.info("unlinked thread %s (%d messages)", thread_id, len(messages))
    return len(messages)


async def merge_company(
    session: AsyncSession, *, user_id: int, from_company: str, to_company: str
) -> int:
    """ "Merge into…" — declare `from_company` a variant of `to_company`.

    Writes the `CompanyAlias` (alias_key → canonical_key) used by grouping and
    matching from now on, then relinks the merged group's unlinked messages to
    the target's live application when one exists. Returns messages relinked.
    """
    aliases = await load_company_alias_map(session, user_id=user_id)
    alias_key = canonical_company_key(from_company)
    canonical_key = canonical_company_key(to_company, aliases=aliases)
    if not alias_key or not canonical_key:
        raise CorrectionError("Company name did not canonicalize")
    if alias_key == canonical_key:
        raise CorrectionError("Those already group as the same company")

    existing = (
        await session.exec(
            select(CompanyAlias).where(
                CompanyAlias.user_id == user_id, CompanyAlias.alias_key == alias_key
            )
        )
    ).one_or_none()
    if existing is not None:
        existing.canonical_key = canonical_key
        session.add(existing)
    else:
        session.add(CompanyAlias(user_id=user_id, alias_key=alias_key, canonical_key=canonical_key))

    # Relink the merged group's unlinked messages when the target company has
    # a live application; otherwise the groups simply merge on next render.
    group = (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.user_id == user_id,
                EmailMessage.application_id.is_(None),
                EmailMessage.process_dismissed_at.is_(None),
                EmailMessage.extracted_company.is_not(None),
            )
            .order_by(EmailMessage.received_at.asc())
        )
    ).all()
    merged = [m for m in group if canonical_company_key(m.extracted_company or "") == alias_key]

    if merged:
        session.add(
            ClassificationCorrection(
                user_id=user_id,
                message_id=merged[-1].id or 0,
                kind="merge_company",
                from_classification=None,
                to_classification=None,
                from_company=from_company,
                to_company=to_company,
            )
        )

    relinked = 0
    application = await find_application_for_company(session, user_id=user_id, company=to_company)
    if application is not None:
        linked_threads: set[int] = set()
        for msg in merged:
            msg.application_id = application.id
            msg.updated_at = datetime.now(UTC)
            session.add(msg)
            relinked += 1
            if msg.thread_id not in linked_threads:
                thread = await session.get(EmailThread, msg.thread_id)
                if thread is not None and thread.application_id is None:
                    from services.email.service import link_thread

                    link_thread(thread, application)
                    session.add(thread)
                linked_threads.add(msg.thread_id)

    await session.flush()
    # Plan 96e — the merged evidence changes what the target application's
    # timeline says; the relinked threads are the triggering conversations.
    if application is not None and relinked:
        from services.email import reconcile as reconcile_service

        try:
            await reconcile_service.reconcile_application(
                session,
                application_id=application.id or 0,
                triggering_thread_ids={m.thread_id for m in merged},
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("post-merge reconcile failed for application %s: %s", application.id, exc)
    log.info(
        "company alias %r → %r (merged=%d relinked=%d)",
        alias_key,
        canonical_key,
        len(merged),
        relinked,
    )
    return relinked
