"""Project Job + Application rows into Discover swipe-card / up-next dicts.

Plan 36 (`0.2.0.11`, 2026-05-19) wires `services.job_service.list_jobs` into
`build_discover_ctx` so the swipe queue reflects rows persisted by the
scraper crons (`0.2.0.10`). Fake-session callers (the test suite, the
`/_design/components` fixture) keep falling through to `db.sample_data`,
which preserves the memory-mode dev story.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from db import sample_data as sd
from db.sample_data_models import Job as ShadowJob
from models import Job as SQLJob
from models import JobFilter, JobQueueState
from models.enums import VisaRestriction
from services import job_service

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


def _salary_range(j: ShadowJob | SQLJob) -> str | None:
    if j.salary_min and j.salary_max:
        equity = f" + {j.equity_pct}%" if j.equity_pct else ""
        return f"${j.salary_min // 1000}-{j.salary_max // 1000}k{equity}"
    return None


def _relative_label(when: datetime | None) -> str:
    if when is None:
        return "—"
    delta = sd.TODAY - when
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _jd_bullets(j: ShadowJob | SQLJob) -> list[str]:
    if j.criteria:
        return j.criteria[:5]
    return [f"Top role at {j.company}", "Strong fit for your background"]


def _tag_labels(j: ShadowJob | SQLJob) -> list[str]:
    """Normalize tags across shadow (`list[Tag]` enum) vs SQLModel (`list[str]`).

    Shadow Jobs store `Tag` enum members; the real SQLModel Job stores the
    `.value` strings directly (per `models/job.py` ARRAY(String)). Templates
    iterate raw strings, so coerce both shapes into a flat `list[str]`.
    """
    return [t.value if hasattr(t, "value") else str(t) for t in (j.tags or [])]


def swipe_card_dict(
    j: ShadowJob | SQLJob, *, warm_intro_label: str | None = None
) -> dict[str, object]:
    initial, color = _initial_color(j.company)
    grad_from, grad_to = _gradient(initial)
    location, work_mode = (j.location, None)
    if j.location and " · " in j.location:
        location, work_mode = j.location.split(" · ", 1)
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
        # Plan 65 § D.1 — surface the visa_concern chip on the Discover card.
        # The orchestrator writes `match_breakdown.visa_concern = True` when
        # the deterministic visa filter zeroes the job out. Falls back to None
        # so the template can `{% if visa_concern %}`.
        "visa_concern": (j.match_breakdown or {}).get("visa_concern", False),
    }


def up_next_dict(j: ShadowJob | SQLJob) -> dict[str, object]:
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


# Mapping of querystring key → (JobFilter field, coercion). Keeps the
# URL contract documented in plan 36 § D.3 honored at one site.
_TRUE_TOKENS = {"1", "true", "True", "TRUE", "yes", "on"}


def parse_filters_from_query(params: Any) -> JobFilter:
    """Translate ``?source=…&remote_only=1&…`` querystring into a JobFilter.

    Accepts anything that exposes ``.get(key)`` (FastAPI's ``Request.query_params``
    or a plain ``dict``). Unknown / blank values are dropped; Pydantic v2 enum
    coercion raises ``ValidationError`` for invalid values — callers translate
    that into a 422 at the route boundary.

    Plan 36 § D.3 locks the URL contract:
    ``/discover?source=LINKEDIN&remote_only=1&visa=NOT_MENTIONED&seniority=SENIOR
              &score_min=0.5&include_duplicates=0``

    Legacy ``filter=saved`` is preserved as a synonym for
    ``queue_state=SAVED`` so existing links keep working (plan 36 § E row 7).
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

    # Legacy `filter=saved` → queue_state=SAVED. Preserves the existing
    # `/discover?filter=saved` link surface (header chip in discover.html).
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


# ── Context builder (plan 36 § A) ────────────────────────────────────────


async def _live_unswiped(
    session: AsyncSession,
    *,
    user_id: int,
    filters: JobFilter,
) -> list[SQLJob]:
    """Live-DB queue: list_jobs scoped to UNSWIPED + the user's filter.

    The Discover queue surfaces UNSWIPED rows by default; the toolbar may
    refine the slice via the other filter axes. When `filters.queue_state`
    is already set (e.g. legacy `?filter=saved`), honor it; otherwise force
    UNSWIPED so the swipe stack doesn't include already-swiped jobs.
    """
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
    session: AsyncSession | None = None,
    *,
    user_id: int | None = None,
    filters: JobFilter | None = None,
) -> dict[str, object]:
    """Build the Discover context dict.

    Live path (plan 36 § A — when session+user_id are present): the queue
    is read via `job_service.list_jobs`. Sample-data fallback covers the
    fake-session path used by the test suite + the `/_design/components`
    fixture (anywhere `require_authed_session` returns None).
    """
    use_live = session is not None and user_id is not None
    effective_filters = filters or JobFilter()
    queue: list[SQLJob | ShadowJob]

    if use_live:
        # Refine type for static checkers — `use_live` is gated above.
        assert session is not None and user_id is not None  # noqa: S101
        live_queue = await _live_unswiped(session, user_id=user_id, filters=effective_filters)
        if live_queue:
            queue = list(live_queue)
        else:
            # Empty live table (fresh DB before crons fire) — degrade to
            # sample data so the dev experience isn't a blank Discover.
            # Filters are best-effort applied to the shadow rows for
            # parity. § E row 1 mitigation.
            queue = list(_filter_shadow_queue(await sd.discover_queue(), effective_filters))
    else:
        queue = list(_filter_shadow_queue(await sd.discover_queue(), effective_filters))

    saved = await sd.saved_jobs()
    drafts = await sd.auto_apply_queue()
    stuck = await sd.stuck_drafts()

    current = queue[0] if queue else None
    warm_label = None
    if current is not None and getattr(current, "warm_intro_contact_id", None) is not None:
        c = await sd.get_contact(current.warm_intro_contact_id)
        warm_label = c.name.split()[0] if c else None

    up_next = [up_next_dict(j) for j in queue[1:5]]

    stuck_views = []
    for app in stuck:
        if not app.job_id:
            continue
        job = await sd.get_job(app.job_id)
        if not job:
            continue
        v = up_next_dict(job)
        v["state"] = "stuck"
        v["last_failure"] = (app.submission_artifacts or {}).get("last_failure")
        v["application_id"] = app.id
        stuck_views.append(v)

    return {
        "current_card": (
            swipe_card_dict(current, warm_intro_label=warm_label) if current else None
        ),
        "up_next": up_next,
        "stuck_drafts": stuck_views,
        "saved_count": len(saved),
        "auto_apply_drafts": [
            up_next_dict(await sd.get_job(d.job_id))
            for d in drafts
            if d.job_id and await sd.get_job(d.job_id) is not None
        ]
        if drafts
        else [],
        "stats": stats_strip(today_apps=2),
        "unswiped_count": len(queue),
        "filters": effective_filters,
        "filters_active": _active_chip_count(effective_filters),
    }


def _filter_shadow_queue(queue: list[ShadowJob], filters: JobFilter) -> list[ShadowJob]:
    """Best-effort filter application against in-memory shadow Jobs.

    Mirrors the SQL-level filters in `job_service.list_jobs` so the empty-DB
    sample-data fallback honors the same toolbar contract. Tier-3 dedup is
    a no-op here (shadow Jobs lack `duplicate_of_id`).
    """
    result = queue
    if filters.source is not None:
        result = [j for j in result if j.source == filters.source]
    if filters.visa is not None:
        result = [j for j in result if j.visa_restrictions == filters.visa]
    if filters.remote_only:
        result = [j for j in result if j.remote_policy.value == "remote"]
    if filters.seniority is not None:
        result = [j for j in result if j.seniority_level == filters.seniority]
    if filters.score_min > 0.0:
        result = [j for j in result if j.score >= filters.score_min]
    if filters.queue_state is not None:
        result = [j for j in result if j.queue_state == filters.queue_state]
    return result


def _active_chip_count(filters: JobFilter) -> int:
    """How many of the 6 active chips are non-default — used to render the
    "Filters · N" affordance + URL-bar contract in discover.html."""
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
