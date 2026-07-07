"""Silence as a signal — plan 95 § 3.2 (slice 95e).

The pipeline is event-driven; a company that stops replying used to leave a
card on the board forever. `last_signal_at` is DERIVED from the AppEvent log
(never a column, so it can never drift from the truth); a weekly sweep flags
active applications with no signal for `staleness_stale_days` (flat 30d for
every stage — owner decision 2026-07-07).

Nothing closes without a click unless `auto_close_ghosted_after_days` is
explicitly set (asymmetric autonomy: close is the expensive failure).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import AppEvent, Application, Settings
from models.enums import ApplicationStatus, ClosedReason, StatusChangeTrigger

log = logging.getLogger(__name__)

# Stages the sweep watches — CLOSED is done, DRAFT never started.
ACTIVE_STATUSES = (
    ApplicationStatus.APPLIED,
    ApplicationStatus.RECRUITER_SCREEN,
    ApplicationStatus.ONSITE_LOOP,
    ApplicationStatus.OFFER,
)

_SNOOZE_KEY = "staleness_snoozed_until"
DEFAULT_STALE_DAYS = 30
SNOOZE_DAYS = 14


@dataclass(slots=True)
class QuietApplication:
    application: Application
    last_signal_at: datetime
    days_quiet: int


class StalenessError(Exception):
    """Ownership / lookup failure — routes map this to 404."""


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _last_signal_map(
    session: AsyncSession, *, application_ids: list[int]
) -> dict[int, datetime]:
    if not application_ids:
        return {}
    rows = (
        await session.exec(
            select(AppEvent.application_id, func.max(AppEvent.occurred_at))
            .where(AppEvent.application_id.in_(application_ids))  # type: ignore[union-attr]
            .group_by(AppEvent.application_id)
        )
    ).all()
    return {int(app_id): when for app_id, when in rows if app_id is not None and when is not None}


def _last_signal_for(application: Application, event_max: datetime | None) -> datetime:
    """Max of the event log, with applied_at/created_at as the baseline for
    event-less rows. Deliberately NOT `updated_at` — housekeeping writes
    (snooze itself, bullet overrides, doc regen) are not process signal."""
    candidates = [event_max, application.applied_at, application.created_at]
    known = [_aware(c) for c in candidates if c is not None]
    return max(known) if known else datetime.now(UTC)


def _snoozed_until(application: Application) -> datetime | None:
    raw = (application.submission_artifacts or {}).get(_SNOOZE_KEY)
    if not isinstance(raw, str):
        return None
    try:
        return _aware(datetime.fromisoformat(raw))
    except ValueError:
        return None


async def list_going_quiet(
    session: AsyncSession,
    *,
    user_id: int,
    stale_days: int = DEFAULT_STALE_DAYS,
    now: datetime | None = None,
) -> list[QuietApplication]:
    """Active applications with no signal for >= stale_days, snooze honored."""
    now = now or datetime.now(UTC)
    apps = (
        await session.exec(
            select(Application).where(
                Application.user_id == user_id,
                Application.deleted_at.is_(None),
                Application.status.in_(ACTIVE_STATUSES),  # type: ignore[union-attr]
            )
        )
    ).all()
    signal = await _last_signal_map(
        session, application_ids=[a.id for a in apps if a.id is not None]
    )
    out: list[QuietApplication] = []
    for a in apps:
        last = _last_signal_for(a, signal.get(a.id or 0))
        days = (now - last).days
        if days < stale_days:
            continue
        snoozed = _snoozed_until(a)
        if snoozed is not None and snoozed > now:
            continue
        out.append(QuietApplication(application=a, last_signal_at=last, days_quiet=days))
    out.sort(key=lambda q: q.days_quiet, reverse=True)
    return out


async def snooze(
    session: AsyncSession, *, user_id: int, application_id: int, days: int = SNOOZE_DAYS
) -> Application:
    """ "Snooze 2w" — JSONB `submission_artifacts` slot, no migration."""
    application = await session.get(Application, application_id)
    if application is None or application.user_id != user_id:
        raise StalenessError("No such application")
    artifacts = dict(application.submission_artifacts or {})
    artifacts[_SNOOZE_KEY] = (datetime.now(UTC) + timedelta(days=days)).isoformat()
    application.submission_artifacts = artifacts
    application.updated_at = datetime.now(UTC)
    session.add(application)
    await session.flush()
    return application


async def mark_ghosted(session: AsyncSession, *, user_id: int, application_id: int) -> Application:
    """One-click "Mark ghosted" — through the single status write path."""
    from services import applications as applications_service

    application = await session.get(Application, application_id)
    if application is None or application.user_id != user_id:
        raise StalenessError("No such application")
    return await applications_service.update_status(
        session,
        application_id,
        ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.GHOSTED,
        notes="Marked ghosted from the going-quiet strip",
        trigger=StatusChangeTrigger.MANUAL,
    )


async def sweep(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """`tracking.staleness_sweep` weekly job.

    Flagging is computed live at page render; the sweep's job is the
    OPT-IN auto-close: when `auto_close_ghosted_after_days` is set, anything
    past that threshold closes with `trigger=CLEANUP_STALE`. Default off —
    the sweep then only counts (observability), and closes nothing.
    """
    from services import applications as applications_service

    now = now or datetime.now(UTC)
    settings_rows = (await session.exec(select(Settings))).all()
    flagged = closed = 0
    for settings in settings_rows:
        stale_days = int(getattr(settings, "staleness_stale_days", DEFAULT_STALE_DAYS) or 0)
        if stale_days <= 0:
            stale_days = DEFAULT_STALE_DAYS
        quiet = await list_going_quiet(
            session, user_id=settings.user_id, stale_days=stale_days, now=now
        )
        flagged += len(quiet)
        auto_close_days = getattr(settings, "auto_close_ghosted_after_days", None)
        if not auto_close_days:
            continue
        for q in quiet:
            if q.days_quiet < int(auto_close_days):
                continue
            try:
                await applications_service.update_status(
                    session,
                    q.application.id,
                    ApplicationStatus.CLOSED,
                    closed_reason=ClosedReason.GHOSTED,
                    notes=f"Auto-closed after {q.days_quiet}d without signal",
                    trigger=StatusChangeTrigger.CLEANUP_STALE,
                )
                closed += 1
            except applications_service.ApplicationServiceError as exc:
                log.warning("staleness auto-close failed for %s: %s", q.application.id, exc)
    log.info("staleness_sweep flagged=%d auto_closed=%d", flagged, closed)
    return {"flagged": flagged, "auto_closed": closed}
