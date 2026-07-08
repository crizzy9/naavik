"""Slot suggestion + owner-voice draft — plan 96 slice 96f.

Detect → suggest → draft; **Naavik never sends** (owner decisions #5/#6):
no SMTP, no send scopes — the panel offers Copy and a Gmail COMPOSE
deep-link (`view=cm`, a URL the owner's browser opens; not an API). The
only persistence is a NOTE_ADDED AppEvent recording that a draft was
produced — never the prose.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import AppEventKind, Application, CalendarEvent, EmailMessage, Settings
from services.scheduling.slots import Slot, format_slot, free_slots, parse_window

log = logging.getLogger(__name__)

_BUSY_HORIZON_DAYS = 14
# Gmail compose URLs 400 past ~2k chars — the Copy button is the primary
# affordance; the deep-link truncates gracefully (§ 6 risk).
_MAX_COMPOSE_BODY = 1600
_SLOT_COUNT = 3


class SchedulingError(Exception):
    """Lookup/validation failure — routes map this to 404/422."""


def resolve_timezone(settings: Settings | None) -> ZoneInfo:
    """Explicit Settings override, else the host's current zone (the owner's
    calendar follows the device — owner decision 2026-07-08).

    Host detection must yield a NAMED zone, not a fixed offset —
    `datetime.now().astimezone().tzinfo` returns a bare "EDT" offset object
    that ZoneInfo can't parse (caught in live QA: slots rendered UTC), and a
    fixed offset would break DST-correct slots across a transition. TZ env
    first, then the /etc/localtime symlink, then UTC.
    """
    name = getattr(settings, "scheduling_timezone", None)
    if name:
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001 — bad override degrades to auto
            log.warning("scheduling: unknown timezone %r, using host zone", name)
    tz_env = os.environ.get("TZ")
    if tz_env:
        try:
            return ZoneInfo(tz_env)
        except Exception:  # noqa: BLE001
            pass
    try:
        localtime = os.path.realpath("/etc/localtime")
        if "/zoneinfo/" in localtime:
            return ZoneInfo(localtime.split("/zoneinfo/", 1)[1])
    except Exception:  # noqa: BLE001
        pass
    return ZoneInfo("UTC")


async def busy_intervals(
    session: AsyncSession, *, user_id: int, horizon_days: int = _BUSY_HORIZON_DAYS
) -> list[tuple[datetime, datetime]]:
    """Blocking intervals: synced calendar events + final invites (96d)."""
    from services.email.invites import final_invites_for_user

    now = datetime.now(UTC)
    hi = now + timedelta(days=horizon_days)
    out: list[tuple[datetime, datetime]] = []
    events = (
        await session.exec(
            select(CalendarEvent).where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.starts_at >= now - timedelta(hours=12),
                CalendarEvent.starts_at <= hi,
            )
        )
    ).all()
    for e in events:
        if e.starts_at is None:
            continue
        start = e.starts_at if e.starts_at.tzinfo else e.starts_at.replace(tzinfo=UTC)
        end = (
            e.ends_at
            if (e.ends_at and e.ends_at.tzinfo)
            else (e.ends_at or start + timedelta(hours=1))
        )
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        out.append((start, end))
    for invite in await final_invites_for_user(session, user_id=user_id):
        if invite.starts_at is None:
            continue
        start = (
            invite.starts_at if invite.starts_at.tzinfo else invite.starts_at.replace(tzinfo=UTC)
        )
        end = invite.ends_at or start + timedelta(hours=1)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if start <= hi:
            out.append((start, end))
    return out


@dataclass(slots=True)
class SchedulingDraft:
    application_id: int
    company: str
    slots: list[Slot]
    slot_labels: list[str]
    tz_label: str
    body: str | None  # None when no LLM provider is configured
    to: str | None
    subject: str
    gmail_url: str | None
    degraded_reason: str | None = None


async def suggest_slots(
    session: AsyncSession, *, user_id: int, settings: Settings | None, count: int = _SLOT_COUNT
) -> tuple[list[Slot], ZoneInfo]:
    tz = resolve_timezone(settings)
    window = parse_window(getattr(settings, "scheduling_window", None))
    busy = await busy_intervals(session, user_id=user_id)
    slots = free_slots(busy=busy, tz=tz, window=window, now=datetime.now(UTC), count=count)
    return slots, tz


def gmail_compose_url(*, to: str, subject: str, body: str) -> str:
    """Gmail compose deep-link (`view=cm`) — a URL, not an API; truncates
    past the compose-URL budget (Copy is the primary affordance)."""
    trimmed = body[:_MAX_COMPOSE_BODY]
    query = urllib.parse.urlencode(
        {"view": "cm", "fs": "1", "to": to, "su": subject, "body": trimmed}
    )
    return f"https://mail.google.com/mail/?{query}"


async def build_scheduling_draft(
    session: AsyncSession, *, user_id: int, application_id: int
) -> SchedulingDraft:
    """Slots + owner-voice draft for one application's scheduling ask.

    Degrades honestly: without an LLM provider the panel still shows the
    slots (Copy-able) with a reason line. The ONLY write is the NOTE_ADDED
    AppEvent stamping that a draft was produced.
    """
    from llm import LLMProviderError, get_provider
    from llm.prompts.draft_scheduling_reply import PROMPT, SchedulingReplyResult
    from services import llm_tracker
    from services.email.reconcile import _render_conversation

    application = await session.get(Application, application_id)
    if application is None or application.user_id != user_id or application.deleted_at is not None:
        raise SchedulingError("No such application")
    settings = (
        await session.exec(select(Settings).where(Settings.user_id == user_id))
    ).one_or_none()

    slots, tz = await suggest_slots(session, user_id=user_id, settings=settings)
    slot_labels = [format_slot(s, tz) for s in slots]
    tz_label = datetime.now(tz).strftime("%Z") or str(tz)

    messages = (
        await session.exec(
            select(EmailMessage)
            .where(EmailMessage.application_id == application_id)
            .order_by(EmailMessage.received_at.desc())
            .limit(6)
        )
    ).all()
    anchor = next(
        (m for m in messages if m.action_needed not in (None, "none")),
        messages[0] if messages else None,
    )
    subject = f"Re: {anchor.subject}" if anchor else f"Scheduling — {application.company}"
    to = anchor.sender_email if anchor else None

    body: str | None = None
    degraded_reason: str | None = None
    if not slots:
        degraded_reason = "No open slots in the working window — widen it in Settings."
    if settings is None:
        degraded_reason = degraded_reason or "No settings row — connect an LLM provider first."
    else:
        try:
            provider = get_provider(settings)
        except LLMProviderError:
            provider = None
            degraded_reason = degraded_reason or "No LLM provider configured — slots only."
        if provider is not None and slots:
            from services.profile import get_profile  # profile owns the owner's name

            first_name = "Shyam"
            try:
                profile = await get_profile(session, user_id)
                if profile is not None and profile.full_name:
                    first_name = profile.full_name.split()[0]
                    if first_name.isupper():
                        # Resume-style "SHYAM PADIA" must not shout in a reply.
                        first_name = first_name.capitalize()
            except Exception:  # noqa: BLE001 — the draft must not die on a name
                pass
            from services.scheduling.detect import ACTION_LABELS

            action_label = ACTION_LABELS.get(
                (anchor.action_needed if anchor else None) or "", "share availability"
            )
            role_clause = f" for the role {application.role!r}" if application.role else ""
            rendered = PROMPT.format(
                company=application.company,
                role_clause=role_clause,
                conversation=_render_conversation(list(messages)) or "(no stored excerpt)",
                tz_label=tz_label,
                slots="\n".join(f"- {label}" for label in slot_labels),
                first_name=first_name,
                action_label=action_label,
            )
            try:
                raw = await llm_tracker.tracked_call(
                    session=session,
                    user_id=user_id,
                    provider=provider,
                    method="structured",
                    prompt_name="draft_scheduling_reply",
                    prompt=rendered,
                    schema=SchedulingReplyResult,
                )
                value = getattr(raw, "value", raw)
                parsed = (
                    value
                    if isinstance(value, SchedulingReplyResult)
                    else SchedulingReplyResult.model_validate(value)
                )
                body = parsed.body.strip() or None
            except Exception as exc:  # noqa: BLE001 — slots still render
                log.warning("scheduling draft failed for application %s: %s", application_id, exc)
                degraded_reason = "Draft generation failed — slots only."

    gmail_url = gmail_compose_url(to=to, subject=subject, body=body) if (to and body) else None

    # Auditability without storing prose (owner #5): the event says a draft
    # was produced; the text lives only in the response.
    from models import AppEvent

    session.add(
        AppEvent(
            user_id=user_id,
            application_id=application_id,
            kind=AppEventKind.NOTE_ADDED,
            payload={
                "source": "scheduling_draft",
                "message_id": anchor.id if anchor else None,
                "slots": slot_labels,
                "drafted": body is not None,
            },
            occurred_at=datetime.now(UTC),
        )
    )
    await session.flush()

    return SchedulingDraft(
        application_id=application_id,
        company=application.company,
        slots=slots,
        slot_labels=slot_labels,
        tz_label=tz_label,
        body=body,
        to=to,
        subject=subject,
        gmail_url=gmail_url,
        degraded_reason=degraded_reason,
    )
