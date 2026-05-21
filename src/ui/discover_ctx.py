"""Project Job + Application rows into Discover swipe-card / up-next dicts.

Plan 36 (`0.2.0.11`) wired `services.job_service.list_jobs` into
`build_discover_ctx`. Plan 69 (`0.3.3.12`) removed the legacy sample_data
fallback path — every caller passes `session` + `user_id`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from models import Job as SQLJob
from models import JobFilter, JobQueueState
from models.enums import VisaRestriction
from services import application_service, contact_tracker, job_service

_COMPANY_COLORS = {
    "F": "bg-fuchsia-700",
    "A": "bg-emerald-700",
    "S": "bg-indigo-700",
    "L": "bg-purple-700",
    "N": "bg-rose-700",
    "P": "bg-amber-700",
    "R": "bg-amber-700",
    "D": "bg-indigo-700",
    "M": "bg-cyan-700",
    "C": "bg-amber-700",
    "T": "bg-sky-700",
    "G": "bg-rose-600",
    "O": "bg-emerald-700",
}

_GRADIENTS = {
    "S": ("from-indigo-600", "to-purple-600"),
    "A": ("from-emerald-600", "to-cyan-600"),
    "L": ("from-fuchsia-600", "to-indigo-600"),
    "F": ("from-amber-600", "to-rose-600"),
    "M": ("from-cyan-600", "to-indigo-600"),
    "R": ("from-emerald-600", "to-indigo-600"),
    "D": ("from-indigo-600", "to-purple-600"),
    "N": ("from-rose-600", "to-purple-600"),
    "P": ("from-amber-600", "to-emerald-600"),
    "O": ("from-emerald-600", "to-indigo-600"),
}


def _initial_color(s: str) -> tuple[str, str]:
    initial = (s or "?")[:1].upper()
    return initial, _COMPANY_COLORS.get(initial, "bg-slate-700")


def _gradient(initial: str) -> tuple[str, str]:
    return _GRADIENTS.get(initial, ("from-indigo-600", "to-purple-600"))


def _salary_range(j: SQLJob) -> str | None:
    if j.salary_min and j.salary_max:
        equity = f" + {j.equity_pct}%" if j.equity_pct else ""
        return f"${j.salary_min // 1000}-{j.salary_max // 1000}k{equity}"
    return None


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo is not None else when.replace(tzinfo=UTC)


def _relative_label(when: datetime | None) -> str:
    if when is None:
        return "—"
    delta = datetime.now(UTC) - _aware(when)
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _jd_bullets(j: SQLJob) -> list[str]:
    if j.criteria:
        return j.criteria[:5]
    return [f"Top role at {j.company}", "Strong fit for your background"]


def _tag_labels(j: SQLJob) -> list[str]:
    """Normalize tags across shadow (`list[Tag]` enum) vs SQLModel (`list[str]`)."""
    return [t.value if hasattr(t, "value") else str(t) for t in (j.tags or [])]


def swipe_card_dict(j: SQLJob, *, warm_intro_label: str | None = None) -> dict[str, object]:
    initial, color = _initial_color(j.company)
    grad_from, grad_to = _gradient(initial)
    location, work_mode = (j.location, None)
    if j.location and " · " in j.location:
        location, work_mode = j.location.split(" · ", 1)
    mb = j.match_breakdown or {}
    return {
        "id": j.id,
        "company": j.company,
        "company_initial": initial,
        "company_color": color,
        "gradient_from": grad_from,
        "gradient_to": grad_to,
        "role": j.role,
        "team": j.team,
        "score": int(round(j.score * 100)),
        "unscored": j.score == 0.0,
        "location": location,
        "salary_range": _salary_range(j),
        "work_mode": work_mode,
        "posted_relative": _relative_label(j.posted_at or j.found_at),
        "jd_bullets": _jd_bullets(j),
        "warm_intro_label": warm_intro_label,
        "tags": _tag_labels(j),
        "match_breakdown": j.match_breakdown,
        "match_overall": j.score,
        "visa_friendly": j.visa_restrictions == VisaRestriction.SPONSORSHIP_AVAILABLE,
        "visa_concern": mb.get("visa_concern", False),
        # Plan 78 § D.6 (0.4.0.15) — raw VisaRestriction value for the new
        # visa_status_chip partial. Three-state UX (sponsors / no sponsorship
        # / unknown). NOT_MENTIONED + None both render as "unknown."
        "visa_restriction": (
            j.visa_restrictions.value if j.visa_restrictions is not None else None
        ),
        # Plan 72 § Surface 1 — defensive projections so page templates can
        # read strengths/gaps/visa_note without diving into the JSONB blob.
        # score_card.html still reads from match_breakdown directly; these
        # mirror them as top-level keys for ad-hoc consumers.
        "strengths": mb.get("strengths") or [],
        "gaps": mb.get("gaps") or [],
        "visa_note": mb.get("visa_note"),
    }


def up_next_dict(j: SQLJob) -> dict[str, object]:
    initial, color = _initial_color(j.company)
    return {
        "id": j.id,
        "company": j.company,
        "company_initial": initial,
        "company_color": color,
        "role": j.role,
        "salary_range": _salary_range(j),
        "score": int(round(j.score * 100)),
    }


def stats_strip(today_apps: int) -> dict[str, int]:
    return {
        "applied": today_apps,
        "auto": 1,
        "manual": 0,
        "saved": 0,
        "skipped": 0,
        "scanned": 142,
    }


# ── Filter querystring parsing (plan 36 § A) ─────────────────────────────


_TRUE_TOKENS = {"1", "true", "True", "TRUE", "yes", "on"}


def parse_filters_from_query(params: Any) -> JobFilter:
    """Translate ``?source=…&remote_only=1&…`` querystring into a JobFilter.

    Plan 36 § D.3 URL contract; legacy ``filter=saved`` synonym preserved.
    """

    def _get(key: str) -> str | None:
        raw = params.get(key) if hasattr(params, "get") else None
        if raw is None:
            return None
        raw = str(raw).strip()
        return raw or None

    payload: dict[str, Any] = {}

    source = _get("source")
    if source is not None:
        payload["source"] = source.lower()

    visa = _get("visa")
    if visa is not None:
        payload["visa"] = visa.lower()

    seniority = _get("seniority")
    if seniority is not None:
        payload["seniority"] = seniority.lower()

    remote_only = _get("remote_only")
    if remote_only is not None:
        payload["remote_only"] = remote_only in _TRUE_TOKENS

    include_duplicates = _get("include_duplicates")
    if include_duplicates is not None:
        payload["include_duplicates"] = include_duplicates in _TRUE_TOKENS

    score_min = _get("score_min")
    if score_min is not None:
        payload["score_min"] = float(score_min)

    queue_state = _get("queue_state")
    legacy_filter = _get("filter")
    if queue_state is not None:
        payload["queue_state"] = queue_state.lower()
    elif legacy_filter == "saved":
        payload["queue_state"] = JobQueueState.SAVED.value

    company = _get("company")
    if company is not None:
        payload["company"] = company

    return JobFilter(**payload)


# ── Context builder ──────────────────────────────────────────────────────


async def _live_unswiped(
    session: AsyncSession,
    *,
    user_id: int,
    filters: JobFilter,
) -> list[SQLJob]:
    """List_jobs scoped to UNSWIPED + the user's filter."""
    effective = filters.model_copy()
    if effective.queue_state is None:
        effective.queue_state = JobQueueState.UNSWIPED
    return await job_service.list_jobs(
        session,
        user_id=user_id,
        filters=effective,
        page=0,
        page_size=50,
    )


async def build_discover_ctx(
    session: AsyncSession,
    *,
    user_id: int,
    filters: JobFilter | None = None,
) -> dict[str, object]:
    """Build the Discover context dict against live DB."""
    from services import settings_service

    effective_filters = filters or JobFilter()
    queue = await _live_unswiped(session, user_id=user_id, filters=effective_filters)
    saved = await job_service.list_jobs_by_queue_state(
        session, user_id=user_id, state=JobQueueState.SAVED
    )
    drafts = await job_service.auto_apply_queue(session, user_id=user_id)
    stuck = await application_service.stuck_drafts(session, user_id=user_id)
    # Plan 78 § D.5 (0.4.0.20) — surface the dry-run flag so the page can
    # render a warning banner above the swipe stack.
    user_settings = await settings_service.get_or_create(session, user_id=user_id)
    auto_apply_dry_run = bool(getattr(user_settings, "auto_apply_dry_run", False))

    current = queue[0] if queue else None
    warm_label = None
    if current is not None and getattr(current, "warm_intro_contact_id", None) is not None:
        c = await contact_tracker.get_contact(session, current.warm_intro_contact_id)
        warm_label = c.name.split()[0] if c else None

    up_next = [up_next_dict(j) for j in queue[1:5]]

    stuck_views: list[dict[str, object]] = []
    for app in stuck:
        if not app.job_id:
            continue
        job = await job_service.get_job(session, app.job_id)
        if not job:
            continue
        v = up_next_dict(job)
        v["state"] = "stuck"
        v["last_failure"] = (app.submission_artifacts or {}).get("last_failure")
        v["application_id"] = app.id
        stuck_views.append(v)

    auto_apply_views: list[dict[str, object]] = []
    for d in drafts:
        auto_apply_views.append(up_next_dict(d))

    return {
        "current_card": (
            swipe_card_dict(current, warm_intro_label=warm_label) if current else None
        ),
        "up_next": up_next,
        "stuck_drafts": stuck_views,
        "saved_count": len(saved),
        "auto_apply_drafts": auto_apply_views,
        "stats": stats_strip(today_apps=2),
        "unswiped_count": len(queue),
        "filters": effective_filters,
        "filters_active": _active_chip_count(effective_filters),
        "auto_apply_dry_run": auto_apply_dry_run,
    }


def _active_chip_count(filters: JobFilter) -> int:
    """How many of the 6 active chips are non-default."""
    count = 0
    if filters.source is not None:
        count += 1
    if filters.remote_only:
        count += 1
    if filters.visa is not None:
        count += 1
    if filters.seniority is not None:
        count += 1
    if filters.score_min > 0.0:
        count += 1
    if filters.include_duplicates:
        count += 1
    return count
