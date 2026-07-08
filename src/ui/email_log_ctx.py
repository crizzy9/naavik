"""Ctx builder for the /emails log (plan 96b).

Every synced message, findable in ≤2 clicks, with its classification, link
state, and WHAT it did to the pipeline (the per-email signal detail). Pure
surfacing — the pipeline data already sits on `EmailMessage` + the
EMAIL_STATUS_SUGGESTED event payloads.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, date, datetime, time

from sqlalchemy import and_, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import AppEvent, Application, EmailMessage
from models.enums import (
    AppEventKind,
    EmailClassification,
    application_status_label,
)
from ui.tracking_ctx import _CLASSIFICATION_TONES, _relative_label

PAGE_SIZE = 50

# Link-state filter vocabulary. `linked`/`dismissed`/`unlinked` resolve in
# SQL; `detected`/`parked` need the sender-rule layer and post-filter the
# fetched page (the cursor still advances over raw rows, so pagination
# stays correct — pages can simply run short).
LINK_STATES = ("linked", "detected", "parked", "dismissed", "none")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def encode_cursor(msg: EmailMessage) -> str:
    return f"{_aware(msg.received_at).isoformat()}|{msg.id}"


def decode_cursor(raw: str | None) -> tuple[datetime, int] | None:
    if not raw or "|" not in raw:
        return None
    ts_raw, _, id_raw = raw.rpartition("|")
    try:
        return datetime.fromisoformat(ts_raw), int(id_raw)
    except ValueError:
        return None


def _sender_domain(sender_email: str) -> str:
    return sender_email.rsplit("@", 1)[-1].lower() if "@" in sender_email else ""


def _link_state(msg: EmailMessage, *, parked: bool) -> str:
    """The row's link chip, in precedence order."""
    from services.email.processes import _PROCESS_SIGNALS

    if msg.application_id is not None:
        return "linked"
    if msg.process_dismissed_at is not None:
        return "dismissed"
    if parked:
        return "parked"
    if msg.classification in _PROCESS_SIGNALS and (
        msg.extracted_end_client or msg.extracted_company
    ):
        return "detected"
    return "none"


async def build_email_log_ctx(
    session: AsyncSession,
    *,
    user_id: int,
    classification: str | None = None,
    link_state: str | None = None,
    account_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sender_q: str | None = None,
    cursor: str | None = None,
    limit: int = PAGE_SIZE,
) -> dict[str, object]:
    from services import email as email_service
    from services.email import processes as processes_mod
    from services.email import sender_rules

    stmt = select(EmailMessage).where(EmailMessage.user_id == user_id)

    if classification == "pending":
        stmt = stmt.where(EmailMessage.classification.is_(None))
    elif classification:
        # Unknown filter values degrade to "all".
        with suppress(ValueError):
            stmt = stmt.where(EmailMessage.classification == EmailClassification(classification))

    if link_state == "linked":
        stmt = stmt.where(EmailMessage.application_id.is_not(None))
    elif link_state == "dismissed":
        stmt = stmt.where(EmailMessage.process_dismissed_at.is_not(None))
    elif link_state in ("detected", "parked", "none"):
        stmt = stmt.where(EmailMessage.application_id.is_(None))

    if account_id:
        stmt = stmt.where(EmailMessage.account_id == account_id)
    if date_from:
        with suppress(ValueError):
            stmt = stmt.where(
                EmailMessage.received_at
                >= datetime.combine(date.fromisoformat(date_from), time.min, tzinfo=UTC)
            )
    if date_to:
        with suppress(ValueError):
            stmt = stmt.where(
                EmailMessage.received_at
                <= datetime.combine(date.fromisoformat(date_to), time.max, tzinfo=UTC)
            )
    if sender_q:
        needle = f"%{sender_q.strip()}%"
        stmt = stmt.where(
            or_(
                EmailMessage.sender_email.ilike(needle),  # type: ignore[union-attr]
                EmailMessage.sender_name.ilike(needle),  # type: ignore[union-attr]
            )
        )

    decoded = decode_cursor(cursor)
    if decoded is not None:
        ts, mid = decoded
        stmt = stmt.where(
            or_(
                EmailMessage.received_at < ts,
                and_(EmailMessage.received_at == ts, EmailMessage.id < mid),
            )
        )

    stmt = stmt.order_by(EmailMessage.received_at.desc(), EmailMessage.id.desc()).limit(limit + 1)
    fetched = list((await session.exec(stmt)).all())
    has_more = len(fetched) > limit
    page = fetched[:limit]

    # Sender-rule layer once per page — parked is a read-time derivation.
    rules = await sender_rules.load_rules(session, user_id=user_id)
    parked_flags = {m.id: processes_mod._is_parked(m, rules) for m in page}

    # Batch the linked applications + their EMAIL_STATUS_SUGGESTED events.
    app_ids = {m.application_id for m in page if m.application_id is not None}
    apps_by_id: dict[int, Application] = {}
    events_by_msg: dict[int, dict] = {}
    if app_ids:
        apps = (
            await session.exec(select(Application).where(Application.id.in_(app_ids)))  # type: ignore[union-attr]
        ).all()
        apps_by_id = {a.id: a for a in apps if a.id is not None}
        events = (
            await session.exec(
                select(AppEvent).where(
                    AppEvent.application_id.in_(app_ids),  # type: ignore[union-attr]
                    AppEvent.kind == AppEventKind.EMAIL_STATUS_SUGGESTED,
                )
            )
        ).all()
        for ev in events:
            mid = (ev.payload or {}).get("message_id")
            if isinstance(mid, int):
                events_by_msg[mid] = ev.payload or {}

    rows = []
    for m in page:
        state = _link_state(m, parked=parked_flags.get(m.id, False))
        if link_state in ("detected", "parked", "none") and state != link_state:
            continue
        application = apps_by_id.get(m.application_id) if m.application_id else None

        # Plan 96b / R5 — what the email DID: suggested transition + outcome.
        suggestion = None
        if m.suggested_status is not None:
            payload = events_by_msg.get(m.id or 0, {})
            if m.suggestion_applied_at is not None or payload.get("applied"):
                outcome = "applied"
            elif m.suggestion_dismissed_at is not None:
                outcome = "dismissed"
            elif payload.get("suppressed_by_pin"):
                outcome = "suppressed_by_pin"
            else:
                outcome = "pending"
            suggestion = {
                "from_label": (
                    application_status_label(payload["current_status"])
                    if payload.get("current_status")
                    else None
                ),
                "status_label": application_status_label(m.suggested_status),
                "outcome": outcome,
            }

        classification_value = m.classification.value if m.classification else None
        rows.append(
            {
                "id": m.id,
                "received_label": _relative_label(m.received_at),
                "received_title": _aware(m.received_at).strftime("%Y-%m-%d %H:%M UTC"),
                "sender_name": m.sender_name or m.sender_email,
                "sender_email": m.sender_email,
                "sender_domain": _sender_domain(m.sender_email),
                "subject": m.subject or "(no subject)",
                "snippet": m.snippet,
                "classification": classification_value or "pending",
                "classification_tone": _CLASSIFICATION_TONES.get(
                    classification_value or "", "slate"
                ),
                "is_pending": m.classification is None,
                "unclassified_reason": (
                    m.unclassified_reason.value if m.unclassified_reason else None
                ),
                "link_state": state,
                "linked_company": application.company if application else None,
                "application_id": m.application_id,
                # Signal-detail chips (expand).
                "extracted_company": m.extracted_company,
                "extracted_role": m.extracted_role,
                "extracted_stage": m.extracted_stage,
                "extracted_round_kind": m.extracted_round_kind,
                "extracted_sender_type": m.extracted_sender_type,
                "extracted_end_client": m.extracted_end_client,
                "urgency": m.urgency,
                "suggestion": suggestion,
                "body_excerpt": m.body_excerpt,
                "can_fetch_body": bool(m.imap_uid and m.account_id),
                "provider_link": (
                    "https://mail.google.com/mail/u/0/#search/rfc822msgid:"
                    + (m.message_id_external or "").strip("<>")
                    if m.message_id_external
                    else None
                ),
            }
        )

    # Header stats — backlog visibility is the B3 lesson: an unclassified
    # count in the header would have surfaced the 37-hour stall in a day.
    from sqlalchemy import func

    total = (
        await session.exec(
            select(func.count()).select_from(EmailMessage).where(EmailMessage.user_id == user_id)
        )
    ).one()
    unclassified = (
        await session.exec(
            select(func.count())
            .select_from(EmailMessage)
            .where(EmailMessage.user_id == user_id, EmailMessage.classification.is_(None))
        )
    ).one()

    accounts = await email_service.list_accounts(session, user_id)

    return {
        "rows": rows,
        "has_more": has_more,
        "next_cursor": encode_cursor(page[-1]) if has_more and page else None,
        "total_count": total,
        "unclassified_count": unclassified,
        "accounts": [{"id": a.id, "label": a.account_email} for a in accounts],
        "filters": {
            "classification": classification or "",
            "link_state": link_state or "",
            "account_id": account_id or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "sender_q": sender_q or "",
        },
        "classification_options": [c.value for c in EmailClassification],
        "link_state_options": list(LINK_STATES),
    }
