"""Application KPI derivations — plan 81 § D.4 / 0.4.0.07.

Per DATA_MODEL.md § F (Response/Onsite/Offer Rate · 90d + Funnel · 90d).

Pure aggregation over `Application` + `AppEvent` rows. Idempotent; no LLM,
no scraper, no notification. All four functions accept an `AsyncSession`
+ keyword-only `user_id` / `window_days`.

Test gauntlet (per plan § Test plan):
- empty history → 0.0 rates, no div-by-zero
- basic happy path with known applied → recruiter → onsite trail
- window filters out applications older than `window_days`
- cross-user IDs not aggregated (IDOR safety)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import AppEvent
from models.enums import AppEventKind, ApplicationStatus

# `AppEvent.payload.to` ordinal → "max-reached" pipeline rank. Backwards
# transitions (e.g. RECRUITER_SCREEN → CLOSED) don't degrade the rank — we
# keep the highest stage the application ever reached. Aligned with
# DATA_MODEL.md § F definition: "applications that progressed at least as
# far as <stage> at any point during the window".
_STATUS_ORDINAL: dict[str, int] = {
    ApplicationStatus.APPLIED.value: 1,
    ApplicationStatus.RECRUITER_SCREEN.value: 2,
    ApplicationStatus.ONSITE_LOOP.value: 3,
    ApplicationStatus.OFFER.value: 4,
    # DRAFT + CLOSED don't promote — they keep whatever max we've already
    # recorded from prior STATUS_CHANGE events.
}

# Application table is referenced as a string column path to keep this
# module import-light (no model graph cycle). The fully-qualified table
# names are pinned by SQLModel metadata.


@dataclass(slots=True)
class FunnelCounts:
    """How many distinct applications reached each stage at any point."""

    applied: int = 0
    recruiter: int = 0
    onsite: int = 0
    offer: int = 0


@dataclass(slots=True)
class ApplicationKpis:
    """The 4-KPI digest rendered on the analytics dashboard."""

    window_days: int
    applied_in_window: int
    response_rate: float  # fraction with ≥ RECRUITER_SCREEN at any point
    onsite_rate: float  # fraction with ≥ ONSITE_LOOP at any point
    offer_rate: float  # fraction with ≥ OFFER at any point
    funnel: FunnelCounts = field(default_factory=FunnelCounts)


@dataclass(slots=True)
class CompanyKpi:
    """Per-company aggregate for the company table."""

    company: str
    applied: int
    response_rate: float
    onsite_rate: float
    offer_rate: float


async def _load_applications_in_window(
    session: AsyncSession,
    *,
    user_id: int,
    window_days: int,
) -> list[tuple[int, str]]:
    """Return (application_id, company) for visible apps applied in window.

    Excludes DRAFT (no `applied_at`) + soft-deleted rows. Closed apps stay
    in (we count them — they reached at least APPLIED before closing).
    """
    from models import Application  # local import — module loads lighter

    threshold = datetime.now(UTC) - timedelta(days=window_days)
    stmt = (
        select(Application.id, Application.company)
        .where(Application.user_id == user_id)
        .where(Application.applied_at.is_not(None))
        .where(Application.applied_at >= threshold)
        .where(Application.deleted_at.is_(None))
        .where(Application.status != ApplicationStatus.DRAFT)
    )
    rows = (await session.exec(stmt)).all()
    # sqlmodel exec returns Row-like tuples for multi-column selects.
    return [(int(r[0]), str(r[1]) if r[1] is not None else "") for r in rows]


async def _max_reached_by_app(
    session: AsyncSession,
    *,
    application_ids: list[int],
) -> dict[int, int]:
    """For each application_id, the highest pipeline rank reached.

    Returns rank-0 (≡ APPLIED achieved by definition of being in the window)
    when no STATUS_CHANGE rows exist past APPLIED.
    """
    if not application_ids:
        return {}
    stmt = (
        select(AppEvent.application_id, AppEvent.payload)
        .where(AppEvent.application_id.in_(application_ids))
        .where(AppEvent.kind == AppEventKind.STATUS_CHANGE)
    )
    rows = (await session.exec(stmt)).all()
    per_app: dict[int, int] = dict.fromkeys(application_ids, 1)  # all reached APPLIED
    for app_id, payload in rows:
        if app_id is None:
            continue
        to = (payload or {}).get("to") if isinstance(payload, dict) else None
        rank = _STATUS_ORDINAL.get(to)
        if rank is not None and rank > per_app.get(int(app_id), 0):
            per_app[int(app_id)] = rank
    return per_app


def _empty_kpis(window_days: int) -> ApplicationKpis:
    return ApplicationKpis(
        window_days=window_days,
        applied_in_window=0,
        response_rate=0.0,
        onsite_rate=0.0,
        offer_rate=0.0,
        funnel=FunnelCounts(),
    )


def _kpis_from_max_reached(
    *,
    window_days: int,
    max_reached: dict[int, int],
) -> ApplicationKpis:
    total = len(max_reached)
    if total == 0:
        return _empty_kpis(window_days)
    funnel = FunnelCounts(
        applied=sum(1 for v in max_reached.values() if v >= 1),
        recruiter=sum(1 for v in max_reached.values() if v >= 2),
        onsite=sum(1 for v in max_reached.values() if v >= 3),
        offer=sum(1 for v in max_reached.values() if v >= 4),
    )
    return ApplicationKpis(
        window_days=window_days,
        applied_in_window=total,
        response_rate=funnel.recruiter / total,
        onsite_rate=funnel.onsite / total,
        offer_rate=funnel.offer / total,
        funnel=funnel,
    )


async def compute_kpis(
    session: AsyncSession,
    *,
    user_id: int,
    window_days: int = 90,
) -> ApplicationKpis:
    """Compute the 4 dashboard KPIs (plan 81 § D.4 / 0.4.0.07).

    Scoped strictly to `user_id`; safe to invoke from a request handler
    without additional IDOR gating because every read filters on user_id.

    Args:
      window_days: how far back to count APPLIED events (default 90d).

    Returns:
      ApplicationKpis with response/onsite/offer rates ∈ [0.0, 1.0] and
      the underlying FunnelCounts counts.
    """
    rows = await _load_applications_in_window(session, user_id=user_id, window_days=window_days)
    if not rows:
        return _empty_kpis(window_days)
    app_ids = [aid for aid, _ in rows]
    max_reached = await _max_reached_by_app(session, application_ids=app_ids)
    return _kpis_from_max_reached(window_days=window_days, max_reached=max_reached)


async def kpis_by_company(
    session: AsyncSession,
    *,
    user_id: int,
    window_days: int = 90,
    limit: int = 10,
) -> list[CompanyKpi]:
    """Top-N companies by application count over `window_days`.

    For each company, returns its per-company response/onsite/offer rate
    over the same window. Excludes the synthetic empty-company string
    that surfaces when `Application.company` is null.
    """
    rows = await _load_applications_in_window(session, user_id=user_id, window_days=window_days)
    if not rows:
        return []
    # Group app_ids per company
    per_company_ids: dict[str, list[int]] = {}
    for aid, company in rows:
        key = company or "(unknown)"
        per_company_ids.setdefault(key, []).append(aid)
    # Pre-compute max-reached across all app_ids in one go
    all_ids = [aid for aid, _ in rows]
    max_reached = await _max_reached_by_app(session, application_ids=all_ids)
    out: list[CompanyKpi] = []
    for company, ids in per_company_ids.items():
        subset = {aid: max_reached.get(aid, 1) for aid in ids}
        total = len(subset)
        if total == 0:
            continue
        recruiter = sum(1 for v in subset.values() if v >= 2)
        onsite = sum(1 for v in subset.values() if v >= 3)
        offer = sum(1 for v in subset.values() if v >= 4)
        out.append(
            CompanyKpi(
                company=company,
                applied=total,
                response_rate=recruiter / total,
                onsite_rate=onsite / total,
                offer_rate=offer / total,
            )
        )
    out.sort(key=lambda c: (-c.applied, c.company.lower()))
    return out[:limit]


async def _load_apps_with_roles(
    session: AsyncSession,
    *,
    user_id: int,
    window_days: int,
) -> list[tuple[int, str | None]]:
    """Return (application_id, role) for visible apps in the window."""
    from models import Application

    threshold = datetime.now(UTC) - timedelta(days=window_days)
    stmt = (
        select(Application.id, Application.role)
        .where(Application.user_id == user_id)
        .where(Application.applied_at.is_not(None))
        .where(Application.applied_at >= threshold)
        .where(Application.deleted_at.is_(None))
        .where(Application.status != ApplicationStatus.DRAFT)
    )
    rows = (await session.exec(stmt)).all()
    return [(int(r[0]), r[1]) for r in rows]


def _bucket_kpis(max_reached: dict[int, int]) -> dict[str, float | int]:
    """Reduce `{app_id: max_rank}` to the per-bucket KPI dict.

    Shape matches `kpis_by_company`'s per-company shape so the template can
    render any breakdown uniformly.
    """
    total = len(max_reached)
    if total == 0:
        return {"applied": 0, "response_rate": 0.0, "onsite_rate": 0.0, "offer_rate": 0.0}
    recruiter = sum(1 for v in max_reached.values() if v >= 2)
    onsite = sum(1 for v in max_reached.values() if v >= 3)
    offer = sum(1 for v in max_reached.values() if v >= 4)
    return {
        "applied": total,
        "response_rate": recruiter / total,
        "onsite_rate": onsite / total,
        "offer_rate": offer / total,
    }


async def kpis_by_role_family(
    session: AsyncSession,
    *,
    user_id: int,
    window_days: int = 90,
) -> dict[str, dict[str, float | int]]:
    """Role-family breakdown (plan 86 / 0.4.5.06).

    Buckets each in-window Application by the role-family classifier from
    `services.scoring_history.classify_role_family`. Empty families dropped
    (same convention as `aggregate_score_history`).
    """
    from services.scoring_history import classify_role_family

    apps = await _load_apps_with_roles(session, user_id=user_id, window_days=window_days)
    if not apps:
        return {}
    per_family_ids: dict[str, list[int]] = {}
    for app_id, role in apps:
        family = classify_role_family(role)
        per_family_ids.setdefault(family, []).append(app_id)
    all_ids = [aid for aid, _ in apps]
    max_reached = await _max_reached_by_app(session, application_ids=all_ids)
    out: dict[str, dict[str, float | int]] = {}
    for family, ids in per_family_ids.items():
        subset = {aid: max_reached.get(aid, 1) for aid in ids}
        out[family] = _bucket_kpis(subset)
    return out


async def _bullets_used_by_app(
    session: AsyncSession,
    *,
    application_ids: list[int],
) -> dict[int, set[int]]:
    """For each application_id, the set of Bullet IDs used in any GeneratedDocument.

    Plan 86 / W2.2 deviation from plan: bullet provenance lives on
    `GeneratedDocument.bullet_selection["selected_ids"]` (plan 66 substrate),
    not on `Application.submission_artifacts`. Aggregates across all
    documents (resume + cover_letter + audit_trail) for the application —
    a bullet shows up anywhere counts.
    """
    if not application_ids:
        return {}
    from models import GeneratedDocument

    stmt = select(GeneratedDocument.application_id, GeneratedDocument.bullet_selection).where(
        GeneratedDocument.application_id.in_(application_ids)
    )
    rows = (await session.exec(stmt)).all()
    out: dict[int, set[int]] = {}
    for row in rows:
        app_id, selection = (row[0], row[1]) if isinstance(row, tuple) else (None, None)
        if app_id is None or not isinstance(selection, dict):
            continue
        ids = selection.get("selected_ids") or []
        if not isinstance(ids, list):
            continue
        bucket = out.setdefault(int(app_id), set())
        for bid in ids:
            try:
                bucket.add(int(bid))
            except (TypeError, ValueError):
                continue
    return out


async def kpis_by_tag(
    session: AsyncSession,
    *,
    user_id: int,
    window_days: int = 90,
) -> dict[str, dict[str, float | int]]:
    """Tag-intersection breakdown (plan 86 / 0.4.5.07).

    For each in-window Application, intersects the union of `Bullet.tags`
    across bullets actually used in the resume bundle with `Job.tags`. Each
    tag in the intersection gets one count from the Application. Empty
    intersections (manual apps, legacy apps without bullet provenance) are
    skipped — bucketing them as "other" would obscure the metric.
    """
    from models import Application, Bullet, Job

    threshold = datetime.now(UTC) - timedelta(days=window_days)
    stmt = (
        select(Application.id, Application.job_id)
        .where(Application.user_id == user_id)
        .where(Application.applied_at.is_not(None))
        .where(Application.applied_at >= threshold)
        .where(Application.deleted_at.is_(None))
        .where(Application.status != ApplicationStatus.DRAFT)
        .where(Application.job_id.is_not(None))
    )
    rows = (await session.exec(stmt)).all()
    if not rows:
        return {}
    pairs = [(int(r[0]), int(r[1])) for r in rows if r[1] is not None]
    if not pairs:
        return {}
    app_ids = [a for a, _ in pairs]
    job_ids = [j for _, j in pairs]

    bullets_by_app = await _bullets_used_by_app(session, application_ids=app_ids)
    if not bullets_by_app:
        return {}

    all_bullet_ids: set[int] = set()
    for s in bullets_by_app.values():
        all_bullet_ids.update(s)
    bullet_tags_by_id: dict[int, list[str]] = {}
    if all_bullet_ids:
        b_rows = (
            await session.exec(
                select(Bullet.id, Bullet.tags).where(Bullet.id.in_(list(all_bullet_ids)))
            )
        ).all()
        for row in b_rows:
            bid = int(row[0]) if isinstance(row, tuple) else None
            tags = row[1] if isinstance(row, tuple) else None
            if bid is None:
                continue
            bullet_tags_by_id[bid] = list(tags) if tags else []

    job_tags_by_id: dict[int, set[str]] = {}
    j_rows = (await session.exec(select(Job.id, Job.tags).where(Job.id.in_(job_ids)))).all()
    for row in j_rows:
        jid = int(row[0]) if isinstance(row, tuple) else None
        tags = row[1] if isinstance(row, tuple) else None
        if jid is None:
            continue
        job_tags_by_id[jid] = set(tags) if tags else set()

    max_reached = await _max_reached_by_app(session, application_ids=app_ids)

    per_tag_ids: dict[str, list[int]] = {}
    for app_id, job_id in pairs:
        used = bullets_by_app.get(app_id)
        if not used:
            continue
        bullet_tag_union: set[str] = set()
        for bid in used:
            for t in bullet_tags_by_id.get(bid, []):
                bullet_tag_union.add(t)
        if not bullet_tag_union:
            continue
        job_tags = job_tags_by_id.get(job_id, set())
        intersection = bullet_tag_union & job_tags
        for tag in intersection:
            per_tag_ids.setdefault(tag, []).append(app_id)

    out: dict[str, dict[str, float | int]] = {}
    for tag, ids in per_tag_ids.items():
        subset = {aid: max_reached.get(aid, 1) for aid in ids}
        out[tag] = _bucket_kpis(subset)
    return out


__all__ = [
    "ApplicationKpis",
    "CompanyKpi",
    "FunnelCounts",
    "compute_kpis",
    "kpis_by_company",
    "kpis_by_role_family",
    "kpis_by_tag",
]
