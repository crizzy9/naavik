"""Discover (swipe queue) + Discover · review & apply page + stub endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import JobRead, User
from models.enums import (
    JobQueueState,
)
from services import (
    application_service,
    contact_tracker,
    job_service,
    settings_service,
)
from services.auth import require_authed_session
from services.rate_limit import check_generate_bundle_rate_limit, check_rescore_rate_limit
from ui import discover_ctx as dctx
from ui import discover_review_ctx as drctx
from ui.templates_setup import templates

log = logging.getLogger(__name__)

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    """Resolve the per-request user_id for live-DB scoping.

    Real JWT sessions return `user.id`; the fake-session transitional stub
    maps to the seeded owner (id=1) per `db/sample_data.py:USER.id == 1`.
    """
    return user.id if user is not None else 1


def _with_toast(response, tone: str, text: str):
    """Attach a showToast HX-Trigger — P5 universal feedback for actions
    whose swap alone is easy to miss (job-detail buttons use hx-swap=none;
    swipes advance the card but say nothing about what just happened)."""
    import json as _json

    response.headers["HX-Trigger"] = _json.dumps({"showToast": {"tone": tone, "text": text}})
    return response


def _parse_filters_or_422(request: Request) -> dctx.JobFilter:
    """Parse the request querystring; surface Pydantic errors as 422."""
    try:
        return dctx.parse_filters_from_query(request.query_params)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────
# Page handlers
# ─────────────────────────────────────────────────────────────────────────


@router.get("/discover", response_class=HTMLResponse, name="discover")
async def get_discover(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    filters = _parse_filters_or_422(request)
    ctx = await dctx.build_discover_ctx(
        session,
        user_id=_effective_user_id(user),
        filters=filters,
    )
    ctx["active_sidebar"] = "jobs"
    ctx["active_template_path"] = "/discover"
    return templates.TemplateResponse(request, "pages/discover.html", ctx)


async def _job_or_404(session: AsyncSession, job_id: int, user_id: int):
    job = await job_service.get_job(session, job_id)
    if job is None or job.user_id != user_id or job.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def _ensure_draft_and_dispatch(
    session: AsyncSession, *, user_id: int, job_id: int
) -> tuple[object | None, bool]:
    """Resolve the DRAFT for the review workspace without blocking on generation.

    When `eager_review_generation` is on and the docs are NONE/STALE, mark
    GENERATING, commit, and spawn the bundle in the background — the caller
    renders instantly and the workspace polls until the state settles.

    Returns `(application, eager)`.
    """
    from models.enums import DocsState
    from services import generation_dispatch

    settings = await settings_service.get_or_create(session, user_id=user_id)
    eager = settings.eager_review_generation

    app = await application_service.get_application_for_job(session, user_id=user_id, job_id=job_id)
    if app is None and eager:
        app = await application_service.get_or_create_draft(
            session, user_id=user_id, job_id=job_id, settings=settings
        )
    if app is not None and eager and app.docs_state in {DocsState.NONE, DocsState.STALE}:
        await generation_dispatch.mark_generating(session, app)
        await session.commit()
        generation_dispatch.spawn_generation(app.id)
    elif app is not None and generation_dispatch.is_generation_stale(app):
        # Orphaned by a restart — surface as failed so the retry CTA shows.
        app.docs_state = DocsState.FAILED
        session.add(app)
        await session.commit()
    else:
        await session.commit()
    return app, eager


@router.get("/discover/{job_id}", response_class=HTMLResponse, name="discover_review")
async def get_review(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    job = await _job_or_404(session, job_id, user_id)
    app, eager = await _ensure_draft_and_dispatch(session, user_id=user_id, job_id=job_id)

    ctx = await drctx.build_review_ctx(
        session, user_id=user_id, job=job, application=app, eager=eager
    )
    ctx["active_sidebar"] = "jobs"
    ctx["active_template_path"] = "/discover/:id"
    return templates.TemplateResponse(request, "pages/discover_review.html", ctx)


# ─────────────────────────────────────────────────────────────────────────
# Discover JSON / fragment stubs (BACKEND.md § D.3)
# ─────────────────────────────────────────────────────────────────────────


@router.post("/api/v1/discover/{job_id}/skip", response_class=HTMLResponse, name="discover_skip")
async def post_skip(
    request: Request,
    job_id: int,
    fail: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    if fail:
        raise HTTPException(status_code=502, detail="Couldn't skip")
    user_id = _effective_user_id(user)
    try:
        await job_service.set_queue_state(
            session, job_id, user_id=user_id, state=JobQueueState.SKIPPED
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    await session.commit()
    return _with_toast(
        await _next_card_response(request, session, user_id=user_id), "info", "Skipped."
    )


@router.post("/api/v1/discover/{job_id}/save", response_class=HTMLResponse, name="discover_save")
async def post_save(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    user_id = _effective_user_id(user)
    try:
        await job_service.set_queue_state(
            session, job_id, user_id=user_id, state=JobQueueState.SAVED
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    await session.commit()
    return _with_toast(
        await _next_card_response(request, session, user_id=user_id),
        "success",
        "Saved for later.",
    )


@router.post(
    "/api/v1/applications/{job_id}/auto-submit",
    response_class=HTMLResponse,
    name="discover_auto_submit",
)
async def post_auto_submit(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Right-swipe — flip Job → QUEUED_FOR_AUTO_APPLY + create DRAFT.

    Honest by construction: the toast says what will ACTUALLY happen given
    the user's settings and the job's board (auto-submit vs prepared-for-you
    handoff vs dry-run), and document generation starts immediately in the
    background so the queue visibly moves.
    """
    from models.enums import DocsState
    from services import generation_dispatch
    from services.ats import board_supports_auto_submit

    user_id = _effective_user_id(user)
    job = await _job_or_404(session, job_id, user_id)
    settings = await settings_service.get_or_create(session, user_id=user_id)
    draft = await application_service.queue_auto_apply(
        session, user_id=user_id, job_id=job_id, settings=settings
    )
    docs_missing = draft.docs_state in {DocsState.NONE, DocsState.STALE, DocsState.FAILED}
    if docs_missing:
        draft.docs_state = DocsState.GENERATING
    await session.commit()
    if docs_missing:
        generation_dispatch.spawn_generation(draft.id)
    await _maybe_dispatch_auto_apply_now(session, user_id=user_id)

    board = getattr(job, "board", None)
    if not board_supports_auto_submit(board):
        board_label = board.value if board else "manual"
        toast = (
            f"Queued — {board_label} can't be auto-submitted. Documents are "
            "being prepared; you'll get a ready-to-submit handoff."
        )
        tone = "info"
    elif not getattr(settings, "auto_apply_enabled", False):
        toast = (
            "Queued — auto-apply is OFF in Settings, so documents will be "
            "prepared for you to submit manually."
        )
        tone = "info"
    elif getattr(settings, "auto_apply_dry_run", False):
        toast = "Queued (dry-run) — documents will be prepared; no real submission will fire."
        tone = "info"
    else:
        toast = "Queued — documents are being tailored and will be submitted automatically."
        tone = "success"
    return _with_toast(
        await _next_card_response(request, session, user_id=user_id),
        tone,
        toast,
    )


@router.post(
    "/_fragments/discover/{job_id}/pause-auto-apply",
    response_class=HTMLResponse,
    name="discover_pause_auto_apply",
)
async def post_pause_auto_apply(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Plan 78 § D.4 — per-job pause: flip Job.queue_state QUEUED_FOR_AUTO_APPLY
    → SAVED. Returns the next swipe card so the Discover stack advances on
    pause, matching the skip/save UX.
    """
    user_id = _effective_user_id(user)
    job = await application_service.pause_auto_apply_for_job(
        session, user_id=user_id, job_id=job_id
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await session.commit()
    return await _next_card_response(request, session, user_id=user_id)


async def _maybe_dispatch_auto_apply_now(session: AsyncSession, *, user_id: int) -> None:
    """Schedule a transient `scheduler.jobs:auto_apply` one-off when the
    user's `Settings.auto_apply_immediate_dispatch` is True.

    Best-effort — caller must not propagate exceptions. The 5-min cron is
    the fallback path for every failure mode here (scheduler not running,
    Settings row missing, `add_job` raises).
    """
    try:
        from datetime import UTC, datetime
        from uuid import uuid4

        from apscheduler.triggers.date import DateTrigger

        from scheduler import get_scheduler
        from scheduler.jobs import auto_apply as auto_apply_func

        s = await settings_service.get_or_create(session, user_id=user_id)
        if not s.auto_apply_immediate_dispatch:
            return
        scheduler = get_scheduler()
        if scheduler is None or not scheduler.running:
            log.info(
                "auto_apply_immediate_dispatch=True but scheduler not running; "
                "5-min cron will pick up queue"
            )
            return
        now = datetime.now(UTC)
        manual_id = f"applications.auto_apply-immediate-{uuid4().hex[:8]}"
        scheduler.add_job(
            auto_apply_func,
            DateTrigger(run_date=now),
            id=manual_id,
            name=manual_id,
            args=[],
            kwargs={},
            max_instances=1,
            coalesce=True,
            replace_existing=False,
        )
        log.info("scheduled immediate auto_apply manual_id=%s", manual_id)
    except Exception as exc:  # noqa: BLE001 — best-effort
        log.warning("immediate auto_apply dispatch failed: %s", exc)


async def _next_card_response(
    request: Request, session: AsyncSession, *, user_id: int
) -> HTMLResponse:
    queue = await job_service.list_jobs(
        session,
        user_id=user_id,
        filters=dctx.JobFilter(queue_state=JobQueueState.UNSWIPED),
        page=0,
        page_size=10,
    )
    if not queue:
        return templates.TemplateResponse(
            request,
            "components/empty_state.html",
            {
                "icon": "check-circle-2",
                "line": "No more matches. Naavik scans hourly — check back soon.",
            },
        )
    next_job = queue[0]
    warm_label = None
    if next_job.warm_intro_contact_id:
        c = await contact_tracker.get_contact(session, next_job.warm_intro_contact_id)
        warm_label = c.name.split()[0] if c else None
    return templates.TemplateResponse(
        request,
        "components/swipe_card.html",
        {"job": dctx.swipe_card_dict(next_job, warm_intro_label=warm_label)},
    )


@router.get(
    "/_fragments/discover/next-card",
    response_class=HTMLResponse,
    name="discover_next_card_fragment",
)
async def fragment_next_card(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    return await _next_card_response(request, session, user_id=_effective_user_id(user))


@router.get(
    "/_fragments/discover/expanded/{job_id}",
    response_class=HTMLResponse,
    name="discover_expanded_fragment",
)
async def fragment_expanded(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Plan 09a · Issue 8D — return the review workspace as an inline fragment."""
    user_id = _effective_user_id(user)
    job = await _job_or_404(session, job_id, user_id)
    app, eager = await _ensure_draft_and_dispatch(session, user_id=user_id, job_id=job_id)
    ctx = await drctx.build_review_ctx(
        session, user_id=user_id, job=job, application=app, eager=eager
    )
    return templates.TemplateResponse(request, "pages/_discover_review_inline.html", ctx)


@router.get(
    "/_fragments/discover/workspace/{job_id}",
    response_class=HTMLResponse,
    name="discover_workspace_fragment",
)
async def fragment_workspace(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Poll target while docs are GENERATING — re-renders `#review-workspace`.

    Same granularity as the swap root (`hx-swap="outerHTML"` on
    `#review-workspace`), so the fragment guard holds. Does NOT dispatch
    generation — polling must be a pure read.
    """
    user_id = _effective_user_id(user)
    job = await _job_or_404(session, job_id, user_id)
    settings = await settings_service.get_or_create(session, user_id=user_id)
    app = await application_service.get_application_for_job(session, user_id=user_id, job_id=job_id)

    from services import generation_dispatch

    if app is not None and generation_dispatch.is_generation_stale(app):
        from models.enums import DocsState

        app.docs_state = DocsState.FAILED
        session.add(app)
        await session.commit()

    ctx = await drctx.build_review_ctx(
        session,
        user_id=user_id,
        job=job,
        application=app,
        eager=settings.eager_review_generation,
    )
    return templates.TemplateResponse(request, "pages/_discover_review_workspace.html", ctx)


@router.post(
    "/_fragments/discover/tailor/{job_id}",
    response_class=HTMLResponse,
    name="discover_tailor_fragment",
)
async def fragment_tailor(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
    _rate_limit: None = Depends(check_generate_bundle_rate_limit),
):
    """'Tailor for this job' CTA on the lazy workspace — create the DRAFT,
    dispatch background generation, and return the workspace in GENERATING
    state (the root then polls until docs settle)."""
    from services import generation_dispatch

    user_id = _effective_user_id(user)
    job = await _job_or_404(session, job_id, user_id)
    settings = await settings_service.get_or_create(session, user_id=user_id)
    app = await application_service.get_or_create_draft(
        session, user_id=user_id, job_id=job_id, settings=settings
    )
    await generation_dispatch.mark_generating(session, app)
    await session.commit()
    generation_dispatch.spawn_generation(app.id)

    ctx = await drctx.build_review_ctx(
        session, user_id=user_id, job=job, application=app, eager=False
    )
    return templates.TemplateResponse(request, "pages/_discover_review_workspace.html", ctx)


@router.get(
    "/_fragments/discover/queue",
    response_class=HTMLResponse,
    name="discover_queue_fragment",
)
async def fragment_queue(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Plan 09a / 36 — swipe queue grid as an HTMX-swappable fragment."""
    filters = _parse_filters_or_422(request)
    ctx = await dctx.build_discover_ctx(
        session,
        user_id=_effective_user_id(user),
        filters=filters,
    )
    return templates.TemplateResponse(request, "pages/_discover_queue.html", ctx)


@router.get(
    "/_fragments/discover/match-breakdown/{job_id}",
    response_class=HTMLResponse,
    name="discover_match_breakdown_fragment",
)
async def fragment_match_breakdown(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    job = await _job_or_404(session, job_id, user_id)
    return templates.TemplateResponse(
        request,
        "components/match_breakdown.html",
        {"breakdown": job.match_breakdown, "overall": job.score},
    )


@router.get("/api/v1/jobs", name="jobs_list")
async def get_jobs(
    queue_state: Annotated[str | None, Query()] = None,
    score_min: Annotated[float | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    filters = dctx.JobFilter()
    if queue_state:
        try:
            filters = filters.model_copy(update={"queue_state": JobQueueState(queue_state)})
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown queue_state") from None
    if score_min is not None:
        filters = filters.model_copy(update={"score_min": score_min})
    items = await job_service.list_jobs(session, user_id=user_id, filters=filters)
    return {
        "items": [JobRead.model_validate(j).model_dump(mode="json") for j in items],
        "next_cursor": None,
    }


@router.post("/api/v1/jobs/by-url", name="jobs_by_url")
async def post_job_by_url(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """`+ Add by URL` — fetch the REAL posting, extract, score, enqueue.

    Replaces the plan-56 stub that fabricated a job ("Stable Inc", score
    0.84, San Francisco) and dumped raw JSON into the modal. Pipeline:
    SSRF guard → Crawl4AI fetch → LLM extraction (graceful degrade to
    <title> heuristics without a provider) → upsert (dedup on URL hash)
    → immediate layered scoring → honest HTML result fragment + queue
    refresh via HX-Trigger. Errors return 422 fragments the modal shows
    via hx-target-error.
    """
    import hashlib
    import json as _json
    import re as _re

    from llm import LLMProviderError, get_provider
    from models.enums import ApplicationBoard, JobSource
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.types import RawJob
    from scraper.url_guard import is_safe_destination
    from services.job_extractor import enrich_raw_job

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        url = str((body or {}).get("url") or "").strip()
    else:
        form = await request.form()
        url = str(form.get("url") or "").strip()

    def _error(msg: str) -> HTMLResponse:
        return HTMLResponse(f'<span class="text-rose-300">{msg}</span>', status_code=422)

    if not url:
        return _error("URL required.")
    safe, reason = is_safe_destination(url)
    if not safe:
        return _error(f"URL rejected: {reason or 'unsafe destination'}.")

    user_id = _effective_user_id(user)
    client = Crawl4AIClient(rate_limit_per_minute=30.0, random_delay_seconds=(0.0, 0.1))
    html = await client.fetch_html(url)
    if not html:
        return _error("Could not fetch that URL — the site may block bots or be unreachable.")

    # Seed identity from <title> ("Role - Company" patterns); the LLM
    # extraction below overwrites with the authoritative read when available.
    title_match = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.IGNORECASE | _re.DOTALL)
    page_title = (title_match.group(1).strip()[:160] if title_match else "") or "Unknown role"
    seed_role, seed_company = page_title, "Unknown"
    for sep in (" | ", " – ", " — ", " - ", " · "):
        if sep in page_title:
            left, right = page_title.split(sep, 1)
            seed_role = left.strip() or "Unknown role"
            seed_company = right.strip() or "Unknown"
            break

    external_id = f"manual-{hashlib.sha1(url.encode()).hexdigest()[:12]}"
    raw_job = RawJob(
        source=JobSource.MANUAL,
        external_id=external_id,
        source_url=url,
        board=ApplicationBoard.MANUAL,
        url_type="manual",
        company_name=seed_company,
        position_title=seed_role,
        description_html=html,
    )

    settings = await settings_service.get_or_create(session, user_id=user_id)
    try:
        provider = get_provider(settings)
        raw_job = await enrich_raw_job(session, user_id=user_id, provider=provider, raw_job=raw_job)
    except LLMProviderError as exc:
        log.info("add-by-url enrichment skipped (no provider): %s", exc)

    job, created = await job_service.upsert_job(
        session,
        user_id=user_id,
        source=JobSource.MANUAL,
        external_id=external_id,
        raw=raw_job.to_upsert_payload(),
    )

    # Score immediately so the card lands with a real score, not a blank.
    score_note = "unscored — no profile yet"
    from services import profile_service
    from services.scorer import score_job_layered

    profile = await profile_service.get_profile(session, user_id)
    if profile is not None:
        try:
            result = await score_job_layered(
                session, user_id=user_id, job=job, profile=profile, settings=settings
            )
            score_note = f"score {int(round(result.score * 100))}"
        except Exception as exc:  # noqa: BLE001 — job creation must survive scorer issues
            log.warning("add-by-url scoring failed for job %s: %s", job.id, exc)
            score_note = "scoring failed — will retry on the next cron"

    await session.commit()

    response = HTMLResponse(
        '<span class="text-emerald-300">'
        f"{'Added' if created else 'Already tracked — refreshed'}: "
        f"{job.role} at {job.company} · {score_note}</span>"
    )
    response.headers["HX-Trigger"] = _json.dumps(
        {
            "closeModal": True,
            "queue-refresh": True,
            "showToast": {
                "tone": "success",
                "text": f"{job.role} at {job.company} added to the queue ({score_note}).",
            },
        }
    )
    return response


@router.post("/api/v1/jobs/{job_id}/rescore", name="jobs_rescore")
async def post_rescore(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
    _rate_limit: None = Depends(check_rescore_rate_limit),
):
    """Manual re-score of a single Job — plan 65 § D.6 (T10 trigger 3).

    CSRF-gated; IDOR via the `Job.user_id == effective_user_id` check.
    Plan 75 / 0.3.3.02 — rate limited 10/min, 60/hr per user.
    """
    if user is None:
        # Real-auth only.
        raise HTTPException(status_code=401, detail="Authentication required")
    effective_uid = user.id

    from sqlmodel import select as _select

    from models import Job, Profile, Settings
    from services.scorer.orchestrator import score_job_layered

    job = (
        await session.exec(_select(Job).where(Job.id == job_id, Job.deleted_at.is_(None)))
    ).one_or_none()
    if job is None or job.user_id != effective_uid:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = (
        await session.exec(_select(Profile).where(Profile.user_id == effective_uid))
    ).one_or_none()
    if profile is None:
        raise HTTPException(status_code=409, detail="No profile configured")
    settings = (
        await session.exec(_select(Settings).where(Settings.user_id == effective_uid))
    ).one_or_none()
    if settings is None:
        raise HTTPException(status_code=409, detail="No settings configured")

    try:
        await score_job_layered(
            session,
            user_id=effective_uid,
            job=job,
            profile=profile,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("rescore failed for job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail="Rescore failed; see logs") from exc
    await session.commit()
    return JobRead.model_validate(job).model_dump(mode="json")


@router.get("/api/v1/discover/saved", name="discover_saved")
async def get_saved(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    items = await job_service.list_jobs_by_queue_state(
        session, user_id=_effective_user_id(user), state=JobQueueState.SAVED
    )
    return [JobRead.model_validate(j).model_dump(mode="json") for j in items]


@router.get("/api/v1/discover/skipped", name="discover_skipped")
async def get_skipped(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    items = await job_service.list_jobs_by_queue_state(
        session, user_id=_effective_user_id(user), state=JobQueueState.SKIPPED
    )
    return [JobRead.model_validate(j).model_dump(mode="json") for j in items]


# ─────────────────────────────────────────────────────────────────────────
# `+ Add by URL` modal
# ─────────────────────────────────────────────────────────────────────────


@router.get("/_modal/add-by-url", response_class=HTMLResponse, name="modal_add_by_url")
async def add_by_url_modal(request: Request):
    return templates.TemplateResponse(
        request,
        "components/add_by_url_modal.html",
        {},
    )


# ─────────────────────────────────────────────────────────────────────────
# Discover · review & apply — fragment + JSON stubs
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/_fragments/apply/tailored-bullets/{job_id}",
    response_class=HTMLResponse,
    name="apply_tailored_bullets_fragment",
)
async def fragment_tailored_bullets(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    job = await _job_or_404(session, job_id, user_id)
    del job  # presence-checked; bullets are profile-scoped, not job-scoped
    bullets = await drctx.tailored_bullet_groups(session, user_id=user_id)
    return templates.TemplateResponse(
        request,
        "pages/_apply_tailored_bullets.html",
        {"groups": bullets},
    )


@router.get(
    "/_fragments/apply/cover-letter-section/{application_id}/{section}",
    response_class=HTMLResponse,
    name="apply_cover_section_get",
)
async def fragment_cover_section(
    request: Request,
    application_id: int,
    section: str,
    mode: Annotated[str, Query()] = "view",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Render one cover-letter section — text sourced from the real generated
    document (was a process-global placeholder dict)."""
    sections = await application_service.get_latest_cover_sections(session, application_id) or {}
    text = sections.get(section, "")
    return templates.TemplateResponse(
        request,
        "components/cover_letter_section.html",
        {
            "application_id": application_id,
            "section": section,
            "label": drctx.COVER_LABELS.get(section, section.upper()),
            "text": text,
            "mode": mode,
        },
    )


@router.post(
    "/_fragments/apply/cover-letter-section/{application_id}/{section}",
    response_class=HTMLResponse,
    name="apply_cover_section_save",
)
async def fragment_cover_section_save(
    request: Request,
    application_id: int,
    section: str,
    text: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Persist an edited cover-letter section (per-application, IDOR-checked)
    AND recompile the letter PDF so the embed matches the saved text.

    Item 2 (2026-07): the edit form used to POST to
    `/api/v1/applications/{id}/cover-letter/{section}` — a route that never
    existed — so every save 404'd and the edit was lost. The form now posts
    here; on success the recompiled PDF is announced via the
    `coverPdfUpdated` HX-Trigger (base.js reloads the iframe).
    """
    import json as _json

    from services import document_generator as dg
    from services import settings_service

    user_id = _effective_user_id(user)
    ok = await application_service.update_cover_section(
        session,
        application_id=application_id,
        user_id=user_id,
        section=section,
        text=text,
    )
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Generate a cover letter first, then edit its sections.",
        )
    application = await application_service.get_application(session, application_id)
    user_settings = await settings_service.get_or_create(session, user_id=user_id)
    toast = {"tone": "success", "text": "Section saved — letter PDF updated."}
    compiled = True
    try:
        await dg.recompile_cover_letter_from_sections(session, application, settings=user_settings)
    except Exception as exc:  # noqa: BLE001 — save must survive a compile hiccup
        log.warning("cover-letter recompile after edit failed: %s", exc)
        compiled = False
        toast = {
            "tone": "warning",
            "text": "Section saved, but the PDF recompile failed — Regen to refresh it.",
        }
    await session.commit()
    response = templates.TemplateResponse(
        request,
        "components/cover_letter_section.html",
        {
            "application_id": application_id,
            "section": section,
            "label": drctx.COVER_LABELS.get(section, section.upper()),
            "text": text,
            "mode": "view",
        },
    )
    # Only announce a fresh PDF when one was actually compiled — reloading
    # the embed after a failed compile pretends the update happened.
    payload = {"showToast": toast}
    if compiled:
        payload["coverPdfUpdated"] = True
    response.headers["HX-Trigger"] = _json.dumps(payload)
    return response


async def _application_owned_or_404(session, application_id: int, user_id: int):
    application = await application_service.get_application(session, application_id)
    if (
        application is None
        or application.user_id != user_id
        or getattr(application, "deleted_at", None) is not None
    ):
        raise HTTPException(status_code=404, detail="Application not found")
    return application


async def _ledger_response(
    request: Request,
    session: AsyncSession,
    *,
    user_id: int,
    application,
    doc,
    toast: dict | None = None,
    triggers: dict | None = None,
) -> HTMLResponse:
    """Re-render the tailored-bullets ledger, with caller-chosen HX-Triggers.

    Callers own the trigger set so a selection change that merely SCHEDULES
    a recompile fires `resumeSelectionChanged`, while a completed recompile
    fires `resumePdfUpdated` — the embed only reloads when the PDF really
    changed.
    """
    import json as _json

    groups = await drctx.tailored_bullet_groups(session, user_id=user_id, application=application)
    page_count = getattr(doc, "page_count", None) if doc is not None else None
    response = templates.TemplateResponse(
        request,
        "pages/_apply_tailored_bullets.html",
        {
            "groups": groups,
            "application_id": application.id,
            "resume_page_count": page_count,
        },
    )
    payload = dict(triggers or {})
    if toast is not None:
        payload["showToast"] = toast
    if payload:
        response.headers["HX-Trigger"] = _json.dumps(payload)
    return response


@router.post(
    "/_fragments/apply/resume-bullet/{application_id}/{bullet_id}/toggle",
    response_class=HTMLResponse,
    name="apply_resume_bullet_toggle",
)
async def fragment_resume_bullet_toggle(
    request: Request,
    application_id: int,
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Toggle a bullet in/out of THIS application's resume.

    Writes the per-app `bullet_overrides` map (same machinery the tracking
    detail uses) and commits immediately. The Typst recompile is NOT inline:
    the response fires `resumeSelectionChanged`, which the workspace's
    debounced listener turns into one `/resume-pdf/{id}/recompile` call per
    toggle burst — so rapid toggles cost one compile, and the "PDF updated"
    toast only fires when the PDF really updated.
    """
    from models.enums import BulletSelectionOverride
    from services import document_generator as dg
    from services import profile_service

    user_id = _effective_user_id(user)
    application = await _application_owned_or_404(session, application_id, user_id)
    if not await profile_service.owns_bullet(session, bullet_id=bullet_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Bullet not found")

    doc_before = await dg._latest_error_free_doc(
        session, application_id, dg.GeneratedDocumentKind.RESUME
    )
    if doc_before is None or not doc_before.bullet_selection:
        raise HTTPException(status_code=409, detail="Generate the resume first, then edit it.")
    selected_ids = {int(b) for b in (doc_before.bullet_selection.get("selected_ids") or [])}
    overrides_before = dict((application.submission_artifacts or {}).get("bullet_overrides") or {})
    prior = overrides_before.get(str(bullet_id))
    currently_in = (
        prior != BulletSelectionOverride.NEVER_INCLUDE.value if prior else bullet_id in selected_ids
    )

    artifacts = dict(application.submission_artifacts or {})
    overrides = dict(artifacts.get("bullet_overrides") or {})
    overrides[str(bullet_id)] = (
        BulletSelectionOverride.NEVER_INCLUDE.value
        if currently_in
        else BulletSelectionOverride.ALWAYS_INCLUDE.value
    )
    artifacts["bullet_overrides"] = overrides
    application.submission_artifacts = artifacts
    session.add(application)
    await session.commit()

    verb = "removed from" if currently_in else "added to"
    toast = {"tone": "info", "text": f"Bullet {verb} this resume — recompiling the PDF…"}
    return await _ledger_response(
        request,
        session,
        user_id=user_id,
        application=application,
        doc=doc_before,
        toast=toast,
        triggers={"resumeSelectionChanged": True},
    )


@router.post(
    "/_fragments/apply/resume-pdf/{application_id}/recompile",
    name="apply_resume_pdf_recompile",
)
async def fragment_resume_pdf_recompile(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> Response:
    """Recompile the tailored resume PDF from the stored selection + per-app
    overrides. No LLM call — pure Typst.

    Debounce target for `resumeSelectionChanged` (bullet toggles). Responds
    with honest triggers only: `resumePdfUpdated` when a new PDF is on disk,
    `resumePdfStale` + a warning toast when the compile failed or there is
    nothing to recompile — never a success toast for work that didn't happen.
    """
    import json as _json

    from services import document_generator as dg
    from services import settings_service
    from typst.compiler import TypstError

    user_id = _effective_user_id(user)
    application = await _application_owned_or_404(session, application_id, user_id)
    user_settings = await settings_service.get_or_create(session, user_id=user_id)
    try:
        doc = await dg.recompile_resume_from_selection(session, application, settings=user_settings)
    except TypstError as exc:
        log.warning("resume recompile failed for application %d: %s", application_id, exc)
        await session.rollback()
        payload: dict[str, Any] = {
            "resumePdfStale": True,
            "showToast": {
                "tone": "warning",
                "text": "PDF recompile failed — the preview is stale. Use Regen to rebuild.",
            },
        }
    else:
        if doc is None:
            # Covers both "never generated" and "saved selection no longer
            # maps to the live profile" (e.g. resume re-uploaded since).
            payload = {
                "resumePdfStale": True,
                "showToast": {
                    "tone": "warning",
                    "text": (
                        "Couldn't recompile — no usable tailored selection. "
                        "Use Regen to rebuild the documents."
                    ),
                },
            }
        else:
            await session.commit()
            toast = {"tone": "success", "text": "PDF updated."}
            if (doc.page_count or 1) > 1:
                toast = {
                    "tone": "warning",
                    "text": (
                        f"PDF updated — now {doc.page_count} pages. "
                        "Remove something to get back to one."
                    ),
                }
            payload = {"resumePdfUpdated": True, "showToast": toast}
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = _json.dumps(payload)
    return response


@router.post(
    "/_fragments/apply/resume-bullet/{application_id}/{bullet_id}",
    response_class=HTMLResponse,
    name="apply_resume_bullet_save",
)
async def fragment_resume_bullet_save(
    request: Request,
    application_id: int,
    bullet_id: int,
    text: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Save an edited bullet line FOR THIS APPLICATION and recompile the PDF.

    The edit lives in `submission_artifacts.bullet_text_overrides` — the
    profile's master bullet is untouched.
    """
    from services import document_generator as dg
    from services import profile_service, settings_service

    user_id = _effective_user_id(user)
    application = await _application_owned_or_404(session, application_id, user_id)
    if not await profile_service.owns_bullet(session, bullet_id=bullet_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Bullet not found")
    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Bullet text cannot be empty")

    artifacts = dict(application.submission_artifacts or {})
    text_overrides = dict(artifacts.get("bullet_text_overrides") or {})
    text_overrides[str(bullet_id)] = cleaned
    artifacts["bullet_text_overrides"] = text_overrides
    application.submission_artifacts = artifacts
    session.add(application)
    await session.flush()

    from typst.compiler import TypstError

    user_settings = await settings_service.get_or_create(session, user_id=user_id)
    try:
        doc = await dg.recompile_resume_from_selection(session, application, settings=user_settings)
    except TypstError as exc:
        # The edit must survive a compile hiccup — commit it, then say the
        # preview is stale instead of claiming a recompile that didn't happen.
        log.warning("resume recompile after bullet edit failed: %s", exc)
        await session.commit()
        return await _ledger_response(
            request,
            session,
            user_id=user_id,
            application=application,
            doc=None,
            toast={
                "tone": "warning",
                "text": "Line saved, but the PDF recompile failed — the preview is stale.",
            },
            triggers={"resumePdfStale": True},
        )
    if doc is None:
        raise HTTPException(status_code=409, detail="Generate the resume first, then edit it.")
    await session.commit()

    toast = {"tone": "success", "text": "Bullet updated for this application — PDF recompiled."}
    if (doc.page_count or 1) > 1:
        toast = {
            "tone": "warning",
            "text": f"Bullet saved — the resume now runs {doc.page_count} pages.",
        }
    return await _ledger_response(
        request,
        session,
        user_id=user_id,
        application=application,
        doc=doc,
        toast=toast,
        triggers={"resumePdfUpdated": True},
    )


@router.put(
    "/api/v1/applications/{application_id}/cover-letter/sections/{section}",
    name="apply_cover_section_put",
)
async def put_cover_section(
    application_id: int,
    section: str,
    payload: Annotated[dict[str, Any], Body()],
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    text = payload.get("text", "")
    ok = await application_service.update_cover_section(
        session,
        application_id=application_id,
        user_id=_effective_user_id(user),
        section=section,
        text=text,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="No cover letter to edit yet.")
    await session.commit()
    return {"section": section, "text": text}


@router.post("/_fragments/apply/generate/{application_id}", name="apply_generate_fragment")
async def fragment_generate_bundle(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
    _rate_limit: None = Depends(check_generate_bundle_rate_limit),
):
    """Kick off bundle generation and re-render the workspace in GENERATING state.

    Backs the 'Generate tailored documents' / 'Regen' buttons. Generation runs
    in a background task (`services.generation_dispatch`) — the response
    returns immediately with `docs_state=GENERATING` and the workspace polls
    `/_fragments/discover/workspace/{job_id}` until docs settle to READY/FAILED.
    """
    import json as _json

    from services import generation_dispatch

    user_id = _effective_user_id(user)
    application = await application_service.get_application(session, application_id)
    if (
        application is None
        or application.user_id != user_id
        or getattr(application, "deleted_at", None) is not None
    ):
        raise HTTPException(status_code=404, detail="Application not found")

    job = None
    if application.job_id:
        job = await job_service.get_job(session, application.job_id)
    if job is None:
        raise HTTPException(status_code=409, detail="Application has no job attached")

    await generation_dispatch.mark_generating(session, application)
    await session.commit()
    spawned = generation_dispatch.spawn_generation(application.id)
    toast = {
        "tone": "info",
        "text": "Generating tailored documents — the workspace updates when they're ready.",
    }
    if not spawned:
        toast = {"tone": "info", "text": "Generation already in progress."}

    ctx = await drctx.build_review_ctx(
        session, user_id=user_id, job=job, application=application, eager=False
    )
    response = templates.TemplateResponse(request, "pages/_discover_review_workspace.html", ctx)
    response.headers["HX-Trigger"] = _json.dumps({"showToast": toast})
    return response


@router.get("/api/v1/applications/{application_id}/resume.pdf", name="apply_resume_pdf")
async def get_resume_pdf(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Serve the latest generated resume PDF for preview (IDOR-guarded)."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    user_id = _effective_user_id(user)
    application = await application_service.get_application(session, application_id)
    if application is None or application.user_id != user_id:
        raise HTTPException(status_code=404, detail="Application not found")

    docs = await application_service.latest_documents(session, application_id)
    resume = next((d for d in docs if str(d.kind.value) == "resume"), None)
    if resume is None or not resume.path or not Path(resume.path).is_file():
        raise HTTPException(status_code=404, detail="No generated resume PDF yet")
    # no-store: recompiles overwrite the SAME path, and FileResponse's default
    # mtime-based validators (1s granularity) + browser heuristic freshness
    # kept serving the pre-recompile bytes — the embed reloaded but showed the
    # old render, and Regen on old applications looked like a no-op.
    return FileResponse(
        resume.path, media_type="application/pdf", headers={"Cache-Control": "no-store"}
    )


@router.get("/api/v1/applications/{application_id}/cover-letter.pdf", name="apply_cover_letter_pdf")
async def get_cover_letter_pdf(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Serve the latest generated cover-letter PDF (IDOR-guarded) — the
    workspace embeds it inline, same treatment as the resume."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    user_id = _effective_user_id(user)
    application = await application_service.get_application(session, application_id)
    if application is None or application.user_id != user_id:
        raise HTTPException(status_code=404, detail="Application not found")

    docs = await application_service.latest_documents(session, application_id)
    cover = next((d for d in docs if str(d.kind.value) == "cover_letter"), None)
    if cover is None or not cover.path or not Path(cover.path).is_file():
        raise HTTPException(status_code=404, detail="No generated cover letter PDF yet")
    # no-store for the same reason as the resume route above.
    return FileResponse(
        cover.path, media_type="application/pdf", headers={"Cache-Control": "no-store"}
    )


@router.post(
    "/api/v1/applications/{application_id}/cover-letter/generate", name="apply_cover_generate"
)
async def post_cover_generate(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
    _rate_limit: None = Depends(check_generate_bundle_rate_limit),
):
    """Really (re)generate the cover letter for `application_id` and return the
    refreshed cover-text fragment.

    Was a fake SSE stream that emitted "intro chunk 1…" placeholders without
    calling the LLM. Now runs `bundle_generator.regenerate_cover_letter` and
    re-renders the persisted section text. IDOR-checked; returns a friendly
    422 when no LLM provider is configured.
    """
    from llm.base import LLMProviderError
    from services.generation import regenerate_cover_letter

    user_id = _effective_user_id(user)
    application = await application_service.get_application(session, application_id)
    if (
        application is None
        or application.user_id != user_id
        or getattr(application, "deleted_at", None) is not None
    ):
        raise HTTPException(status_code=404, detail="Application not found")

    settings = await settings_service.get_or_create(session, user_id=user_id)
    try:
        await regenerate_cover_letter(session, application, settings=settings)
        await session.commit()
    except LLMProviderError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail=(
                "No LLM provider configured. Set ANTHROPIC_API_KEY / OPENAI_API_KEY "
                "or OLLAMA_BASE_URL in .env and restart to generate a cover letter."
            ),
        ) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    fetched = await application_service.get_latest_cover_sections(session, application_id) or {}
    cover_generated = any(str(v).strip() for v in fetched.values())
    cover_sections = [
        {"id": key, "label": drctx.COVER_LABELS.get(key, key.upper()), "text": fetched.get(key, "")}
        for key in ("intro", "body", "why_company", "close")
    ]
    return templates.TemplateResponse(
        request,
        "pages/_apply_cover_letter_text.html",
        {
            "application": {"id": application_id},
            "cover_sections": cover_sections,
            "cover_generated": cover_generated,
        },
    )


@router.put(
    "/api/v1/applications/{application_id}/screeners/{question_id}", name="apply_screener_put"
)
async def put_screener(
    request: Request,
    application_id: int,
    question_id: int,
    payload: Annotated[dict[str, Any], Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    answer = (payload or {}).get("answer", "")
    owner_user_id = _user.id if _user is not None else None
    a = await application_service.record_screener_answer(
        session, question_id, answer, owner_user_id=owner_user_id
    )
    if a is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    await session.commit()
    return templates.TemplateResponse(
        request,
        "components/screener_question_card.html",
        {
            "answer": {
                "id": a.id,
                "question": a.question_text,
                "body": a.answer or "",
                "source": a.source.value,
                "reviewed_at": a.reviewed_at,
            },
        },
    )


@router.get(
    "/_fragments/apply/screener/{application_id}/{question_id}",
    response_class=HTMLResponse,
    name="apply_screener_get",
)
async def fragment_screener(
    request: Request,
    application_id: int,
    question_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    # Plan 75 / 0.3.3.15 — IDOR boundary. `_user is None` preserves the
    # fake-session bypass for legacy fixtures; real auth threads
    # `owner_user_id` into the service which JOINs through Application.
    owner_user_id = _user.id if _user is not None else None
    a = await application_service.get_screener_answer(
        session, question_id, owner_user_id=owner_user_id
    )
    if a is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    return templates.TemplateResponse(
        request,
        "components/screener_question_card.html",
        {
            "answer": {
                "id": a.id,
                "question": a.question_text,
                "body": a.answer or "",
                "source": a.source.value,
                "reviewed_at": a.reviewed_at,
            },
        },
    )


# NOTE: the plan-75/77 "review & apply two-step" preview cluster
# (GET /_fragments/apply/preview/by-job/{job_id}, GET .../preview/{application_id},
# POST .../confirm/{application_id}, GET .../cancel-preview + the
# apply_preview_card.html partial) was deleted in plan 91 (Q3). The Review &
# apply CTA was rewired to GET /_fragments/discover/expanded/{job_id} (the
# inline review workspace) and nothing issued requests into the cluster.
