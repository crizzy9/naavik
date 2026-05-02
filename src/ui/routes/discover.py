"""Discover (swipe queue) + Discover · review & apply page + stub endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Body, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from db import sample_data as sd
from models.enums import (
    JobQueueState,
)
from ui import discover_ctx as dctx
from ui import discover_review_ctx as drctx
from ui.templates_setup import templates

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────
# Page handlers
# ─────────────────────────────────────────────────────────────────────────


@router.get("/discover", response_class=HTMLResponse, name="discover")
async def get_discover(request: Request):
    ctx = await dctx.build_discover_ctx()
    ctx["active_sidebar"] = "jobs"
    ctx["active_template_path"] = "/discover"
    return templates.TemplateResponse(request, "pages/discover.html", ctx)


@router.get("/discover/{job_id}", response_class=HTMLResponse, name="discover_review")
async def get_review(request: Request, job_id: int):
    job = await sd.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    settings = await sd.get_settings()
    eager = settings.eager_review_generation

    # Find or create the DRAFT (eager). Lazy path skips creation until user clicks.
    app = await sd.application_for_job(1, job_id)
    if app is None and eager:
        app = await sd._create_draft(1, job_id)

    ctx = await drctx.build_review_ctx(job=job, application=app, eager=eager)
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
):
    if fail:
        raise HTTPException(status_code=502, detail="Couldn't skip")
    await sd._set_job_queue_state(job_id, JobQueueState.SKIPPED)
    return await _next_card_response(request)


@router.post("/api/v1/discover/{job_id}/save", response_class=HTMLResponse, name="discover_save")
async def post_save(request: Request, job_id: int):
    await sd._set_job_queue_state(job_id, JobQueueState.SAVED)
    return await _next_card_response(request)


@router.post(
    "/api/v1/applications/{job_id}/auto-submit",
    response_class=HTMLResponse,
    name="discover_auto_submit",
)
async def post_auto_submit(request: Request, job_id: int):
    """Right-swipe — flip Job → QUEUED_FOR_AUTO_APPLY + create DRAFT."""
    await sd._set_job_queue_state(job_id, JobQueueState.QUEUED_FOR_AUTO_APPLY)
    await sd._create_draft(1, job_id)
    return await _next_card_response(request)


async def _next_card_response(request: Request) -> HTMLResponse:
    queue = await sd.discover_queue()
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
        c = await sd.get_contact(next_job.warm_intro_contact_id)
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
async def fragment_next_card(request: Request):
    return await _next_card_response(request)


@router.get(
    "/_fragments/discover/expanded/{job_id}",
    response_class=HTMLResponse,
    name="discover_expanded_fragment",
)
async def fragment_expanded(request: Request, job_id: int):
    """Plan 09a · Issue 8D — return the review workspace as an inline fragment.

    HTMX swaps this into ``#discover-main`` so the active swipe card "expands"
    in-place into the full review workspace without leaving the Discover page.
    The "Back to queue" button inside the fragment hits ``/_fragments/discover/queue``
    to swap back.

    Direct nav to ``/discover/{id}`` continues to render the full page (the
    link-shareable URL); both surfaces compose the same workspace partial
    (`pages/_discover_review_workspace.html`).
    """
    job = await sd.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    settings = await sd.get_settings()
    eager = settings.eager_review_generation
    app = await sd.application_for_job(1, job_id)
    if app is None and eager:
        app = await sd._create_draft(1, job_id)
    ctx = await drctx.build_review_ctx(job=job, application=app, eager=eager)
    return templates.TemplateResponse(request, "pages/_discover_review_inline.html", ctx)


@router.get(
    "/_fragments/discover/queue",
    response_class=HTMLResponse,
    name="discover_queue_fragment",
)
async def fragment_queue(request: Request):
    """Plan 09a · Issue 8D — return the swipe queue grid as an inline fragment.

    Used by the "Back to queue" button inside the expanded review fragment to
    restore the 2-column queue layout in ``#discover-main``.
    """
    ctx = await dctx.build_discover_ctx()
    return templates.TemplateResponse(request, "pages/_discover_queue.html", ctx)


@router.get(
    "/_fragments/discover/match-breakdown/{job_id}",
    response_class=HTMLResponse,
    name="discover_match_breakdown_fragment",
)
async def fragment_match_breakdown(request: Request, job_id: int):
    job = await sd.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        request,
        "components/match_breakdown.html",
        {"breakdown": job.match_breakdown, "overall": job.score},
    )


@router.get("/api/v1/jobs", name="jobs_list")
async def get_jobs(
    queue_state: Annotated[str | None, Query()] = None,
    score_min: Annotated[float | None, Query()] = None,
):
    items = await sd.get_jobs()
    if queue_state:
        try:
            qs = JobQueueState(queue_state)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown queue_state") from None
        items = [j for j in items if j.queue_state == qs]
    if score_min is not None:
        items = [j for j in items if j.score >= score_min]
    return {"items": [j.model_dump(mode="json") for j in items], "next_cursor": None}


@router.get("/api/v1/jobs/{job_id}", name="jobs_get")
async def get_job_by_id(job_id: int):
    job = await sd.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump(mode="json")


@router.post("/api/v1/jobs/by-url", name="jobs_by_url")
async def post_job_by_url(payload: Annotated[dict[str, Any], Body()]):
    """Stub `+ Add by URL` — append a synthetic Job + return it."""
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL required")
    company = "Stable Inc"
    role = "Senior Software Engineer"
    job = await sd._append_scraped_job(url=url, company=company, role=role)
    return job.model_dump(mode="json")


@router.post("/api/v1/jobs/{job_id}/rescore", name="jobs_rescore")
async def post_rescore(job_id: int):
    job = await sd.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump(mode="json")


@router.get("/api/v1/discover/saved", name="discover_saved")
async def get_saved():
    return [j.model_dump(mode="json") for j in await sd.saved_jobs()]


@router.get("/api/v1/discover/skipped", name="discover_skipped")
async def get_skipped():
    return [j.model_dump(mode="json") for j in await sd.skipped_jobs()]


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
async def fragment_tailored_bullets(request: Request, job_id: int):
    job = await sd.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    bullets = await drctx.tailored_bullet_groups()
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
):
    text = drctx.COVER_SECTION_TEXT.get(section, "")
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
):
    drctx.COVER_SECTION_TEXT[section] = text
    return templates.TemplateResponse(
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


@router.put(
    "/api/v1/applications/{application_id}/cover-letter/sections/{section}",
    name="apply_cover_section_put",
)
async def put_cover_section(
    application_id: int, section: str, payload: Annotated[dict[str, Any], Body()]
):
    text = payload.get("text", "")
    drctx.COVER_SECTION_TEXT[section] = text
    return {"section": section, "text": text}


@router.post(
    "/api/v1/applications/{application_id}/cover-letter/generate", name="apply_cover_generate"
)
async def post_cover_generate(application_id: int):
    """SSE stream — chunked cover-letter generation."""

    sections = ["intro", "body", "why_company", "close"]
    chunks_per = [3, 5, 4, 3]

    async def gen():
        for i, sec in enumerate(sections):
            for c in range(chunks_per[i]):
                html = (
                    f'<div sse-swap="chunk" hx-swap="beforeend" '
                    f'class="text-sm text-slate-300 leading-relaxed">'
                    f'<span class="text-slate-500">{sec}</span> chunk {c + 1}…'
                    "</div>"
                )
                yield f"event: chunk\ndata: {html}\n\n"
                await asyncio.sleep(0.3)
        yield "event: done\ndata: <div>done</div>\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.put(
    "/api/v1/applications/{application_id}/screeners/{question_id}", name="apply_screener_put"
)
async def put_screener(
    request: Request,
    application_id: int,
    question_id: int,
    payload: Annotated[dict[str, Any], Body()] = None,
):
    answer = (payload or {}).get("answer", "")
    a = await sd._record_screener_answer(question_id, answer)
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


@router.get(
    "/_fragments/apply/screener/{application_id}/{question_id}",
    response_class=HTMLResponse,
    name="apply_screener_get",
)
async def fragment_screener(request: Request, application_id: int, question_id: int):
    a = next((s for s in sd.SCREENER_ANSWERS if s.id == question_id), None)
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
