"""Overview KPIs + pipeline strip + priority actions composition.

Plan 60 / 0.2.7.17 — new module created during the `NAAVIK_PERSISTENCE`
removal. Replaces the in-memory `kpi_active_applications`,
`kpi_response_rate_90d`, `kpi_onsite_rate_90d`, `kpi_offer_rate_90d`,
`pipeline_strip_counts`, `priority_actions` accessors that lived in
`src/db/sample_data.py:7007-7178`.

Driver: Overview landing page (`src/ui/routes/overview.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application, EmailThread
from models.enums import (
    ApplicationStatus,
    EmailClassification,
    RecruiterState,
)


@dataclass(frozen=True, slots=True)
class KPISet:
    """Bundled KPI values for the Overview landing page."""

    active_applications: int
    response_rate: float
    onsite_rate: float
    offer_rate: float
    offer_count: int


_VISIBLE_TRACKING_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {
        ApplicationStatus.APPLIED,
        ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP,
        ApplicationStatus.OFFER,
    }
)

_ENGAGED_RECRUITER_STATES: frozenset[RecruiterState] = frozenset(
    {
        RecruiterState.ENGAGED,
        RecruiterState.RESPONDED,
        RecruiterState.SILENT,
        RecruiterState.STALLED,
    }
)

_ONSITE_OR_OFFER: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.ONSITE_LOOP, ApplicationStatus.OFFER}
)


def _aware(dt: datetime) -> datetime:
    """Coerce a possibly-naive datetime to UTC-aware.

    Postgres returns tz-aware rows; sqlite (test backend) returns naive.
    Compare in tz-aware UTC consistently.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _list_active(session: AsyncSession, user_id: int) -> list[Application]:
    """Soft-delete-aware live Applications scoped to `user_id`."""
    stmt = select(Application).where(
        Application.user_id == user_id,
        Application.deleted_at.is_(None),
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def compute_kpis(
    session: AsyncSession,
    user_id: int,
    *,
    window_days: int = 90,
) -> KPISet:
    """Compute the 4 Overview KPIs + offer count in one DB read.

    Mirrors `sample_data.kpi_active_applications` / `kpi_response_rate_90d` /
    `kpi_onsite_rate_90d` / `kpi_offer_rate_90d`. Onsite rate counts current
    ONSITE_LOOP + OFFER apps (Phase 1 approximation; Phase 4 layers the
    AppEvent STATUS_CHANGE history for closed apps that reached onsite).
    """
    apps = await _list_active(session, user_id)

    active_apps = [a for a in apps if a.status in _VISIBLE_TRACKING_STATUSES]
    active_count = len(active_apps)

    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    in_window = [
        a
        for a in apps
        if a.status != ApplicationStatus.DRAFT
        and a.applied_at is not None
        and _aware(a.applied_at) >= cutoff
    ]

    if in_window:
        engaged = sum(1 for a in in_window if a.recruiter_state in _ENGAGED_RECRUITER_STATES)
        response_rate = engaged / len(in_window)

        onsite = sum(1 for a in in_window if a.status in _ONSITE_OR_OFFER)
        onsite_rate = onsite / len(in_window)

        offers = sum(1 for a in in_window if a.status == ApplicationStatus.OFFER)
        offer_rate = offers / len(in_window)
    else:
        response_rate = 0.0
        onsite_rate = 0.0
        offer_rate = 0.0

    offer_count = sum(1 for a in apps if a.status == ApplicationStatus.OFFER)

    return KPISet(
        active_applications=active_count,
        response_rate=response_rate,
        onsite_rate=onsite_rate,
        offer_rate=offer_rate,
        offer_count=offer_count,
    )


async def pipeline_strip_counts(session: AsyncSession, user_id: int) -> dict[str, int]:
    """Count of live Applications per Tracking column (excludes DRAFT)."""
    stmt = (
        select(Application.status, func.count(Application.id))
        .where(
            Application.user_id == user_id,
            Application.deleted_at.is_(None),
            Application.status != ApplicationStatus.DRAFT,
        )
        .group_by(Application.status)
    )
    rows = (await session.exec(stmt)).all()
    counts: dict[str, int] = {
        "APPLIED": 0,
        "RECRUITER_SCREEN": 0,
        "ONSITE_LOOP": 0,
        "OFFER": 0,
        "CLOSED": 0,
    }
    for row in rows:
        if isinstance(row, tuple):
            status, count = row
        else:
            status, count = row[0], row[1]
        key = status.value if hasattr(status, "value") else str(status)
        if key in counts:
            counts[key] = int(count)
    return counts


def _relative_label(when: datetime) -> str:
    """Mirror of `sample_data._relative_label` for parity with the UI strings."""
    now = datetime.now(UTC)
    delta = now - _aware(when)
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


async def compose_priority_actions(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 8,
) -> list[dict[str, object]]:
    """Synthesize Overview priority-action rows from Applications + EmailThreads.

    Priority order (matches `sample_data.priority_actions:7100-7178`):
    1. OFFER apps — most urgent.
    2. ONSITE_LOOP apps — interview prep prompts.
    3. SILENT recruiters on live apps — nudge prompts.
    4. Recent inbound INTERVIEW_REQUEST / ASSESSMENT EmailThreads — reply CTA.
    """
    apps = await _list_active(session, user_id)

    actions: list[dict[str, object]] = []

    for a in apps:
        if a.status == ApplicationStatus.OFFER:
            salary_min = a.salary_min or 0
            equity = a.equity_pct or 0
            actions.append(
                {
                    "kind": "offer",
                    "title": f"Respond to {a.company} offer",
                    "subtitle": (
                        f"${salary_min // 1000}k base + {equity}% · verbal extended · "
                        "they expect a reply by Thu"
                    ),
                    "urgency": "today",
                    "urgency_label": "TODAY",
                    "cta_label": "Open offer",
                    "cta_url": f"/tracking?app={a.id}",
                }
            )

    for a in apps:
        if a.status == ApplicationStatus.ONSITE_LOOP:
            team_suffix = f" · {a.team}" if a.team else ""
            actions.append(
                {
                    "kind": "interview",
                    "title": f"Prep for {a.company} onsite",
                    "subtitle": f"{a.role}{team_suffix} · final round in 3 days",
                    "urgency": "tomorrow",
                    "urgency_label": "3D",
                    "cta_label": "Open prep notes",
                    "cta_url": f"/tracking?app={a.id}",
                }
            )

    for a in apps:
        if a.recruiter_state == RecruiterState.SILENT and a.status not in {
            ApplicationStatus.DRAFT,
            ApplicationStatus.CLOSED,
        }:
            team_suffix = f" · {a.team}" if a.team else ""
            actions.append(
                {
                    "kind": "silent",
                    "title": f"Send nudge to {a.company} recruiter",
                    "subtitle": f"{a.role}{team_suffix} · silent for 6 days",
                    "urgency": "silent_n",
                    "urgency_label": "6D SILENT",
                    "cta_label": "Send nudge",
                    "cta_url": f"/outreach?application={a.id}",
                }
            )

    # Inbound email signals — only INTERVIEW_REQUEST / ASSESSMENT (offers
    # handled above).
    stmt = (
        select(EmailThread)
        .where(EmailThread.user_id == user_id)
        .where(
            EmailThread.classification.in_(
                [
                    EmailClassification.INTERVIEW_REQUEST,
                    EmailClassification.ASSESSMENT,
                ]
            )
        )
        .where(EmailThread.application_id.is_not(None))
        .order_by(EmailThread.latest_message_at.desc())
    )
    threads = (await session.exec(stmt)).all()
    for t in threads:
        actions.append(
            {
                "kind": "reply",
                "title": f"Reply to {t.subject[:60]}",
                "subtitle": (
                    f"{t.classification.value.replace('_', ' ').lower()} · "
                    f"{_relative_label(t.latest_message_at)}"
                ),
                "urgency": "relative",
                "urgency_label": _relative_label(t.latest_message_at).upper(),
                "cta_label": "Reply",
                "cta_url": f"/tracking?app={t.application_id}",
            }
        )

    return actions[:limit]


async def list_applications_by_status(
    session: AsyncSession,
    user_id: int,
    status: ApplicationStatus,
) -> list[Application]:
    """Soft-delete-aware list of Applications at a given status."""
    stmt = select(Application).where(
        Application.user_id == user_id,
        Application.status == status,
        Application.deleted_at.is_(None),
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)
