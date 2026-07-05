"""Public Portfolio API — `/api/portfolio/cv` + `/api/portfolio/resume.pdf`.

Per BACKEND.md § L (Portfolio) + plan 10 § C.6.

These endpoints are **public** (no auth) and CORS-restricted to the
configured `Settings.portfolio_cors_allowed_origins`. Filters EEO/visa/salary
out of the Profile JSON. The PDF is served from the cached portfolio path
(regenerated debounced on Profile updates).
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import (
    Education,
    Experience,
    Profile,
    Project,
    Settings,
    Skill,
)
from services.profile import portfolio_sync

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio")


async def _get_settings(session: AsyncSession) -> Settings:
    """Load the singleton `Settings` row (Phase 1: user_id=1)."""
    s = (await session.exec(select(Settings).where(Settings.user_id == 1))).one_or_none()
    if s is None:
        s = Settings(user_id=1)
    return s


def _cors_response(origin: str | None, settings: Settings) -> dict[str, str]:
    headers = {}
    if origin and portfolio_sync.is_cors_allowed(settings, origin):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
    return headers


@router.get("/cv", name="portfolio_cv")
async def get_cv(
    request: Request,
    origin: str | None = Header(default=None, alias="origin"),
    version: Annotated[Literal["v1"], Query()] = "v1",
    session: AsyncSession = Depends(get_session),
):
    """Public CV — Profile JSON, filtered for PII/EEO/visa/salary.

    Plan 57 / 0.2.7.15 — reserves a version surface for cv.astro pinning.
    `version=v1` is the only shape today; future schema-breaking changes
    will branch the payload-build step at line 92. Pydantic Literal rejects
    unknown values with 422 (FastAPI default; close enough to 400 for the
    "fail loudly on client drift" intent).
    """
    settings = await _get_settings(session)
    profile = (
        await session.exec(
            select(Profile).where(Profile.user_id == 1, Profile.deleted_at.is_(None))
        )
    ).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    experiences = (
        await session.exec(
            select(Experience)
            .where(Experience.profile_id == profile.id, Experience.deleted_at.is_(None))
            .order_by(Experience.order_index)
        )
    ).all()
    skills = (
        await session.exec(
            select(Skill).where(Skill.profile_id == profile.id).order_by(Skill.order_index)
        )
    ).all()
    education = (
        await session.exec(
            select(Education)
            .where(Education.profile_id == profile.id)
            .order_by(Education.order_index)
        )
    ).all()
    projects = (
        await session.exec(
            select(Project)
            .where(Project.profile_id == profile.id, Project.deleted_at.is_(None))
            .order_by(Project.order_index)
        )
    ).all()
    payload = portfolio_sync.public_cv_payload(
        profile,
        experiences=experiences,
        skills=skills,
        education=education,
        projects=projects,
    )
    portfolio_sync.assert_no_pii(payload)
    return JSONResponse(
        payload,
        headers=_cors_response(origin, settings),
    )


@router.get("/resume.pdf", name="portfolio_resume_pdf")
async def get_resume(
    request: Request,
    origin: str | None = Header(default=None, alias="origin"),
    session: AsyncSession = Depends(get_session),
):
    """Public generic-resume PDF (cached at `~/.naavik/data/documents/portfolio/resume.pdf`).

    If the file is missing (fresh install), regenerate on demand.
    """
    settings = await _get_settings(session)
    path = portfolio_sync.portfolio_resume_path()
    if not path.exists():
        try:
            await portfolio_sync.regenerate_generic_resume(
                settings=settings, session=session, user_id=1
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("on-demand portfolio regen failed: %s", exc)
    if not path.exists():
        raise HTTPException(status_code=404, detail="portfolio resume not yet generated")
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename="resume.pdf",
        headers=_cors_response(origin, settings),
    )


@router.options("/cv", name="portfolio_cv_options")
async def cv_options(
    origin: str | None = Header(default=None, alias="origin"),
    session: AsyncSession = Depends(get_session),
):
    settings = await _get_settings(session)
    headers = _cors_response(origin, settings)
    headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    headers["Access-Control-Max-Age"] = "86400"
    return Response(status_code=204, headers=headers)


@router.options("/resume.pdf", name="portfolio_resume_options")
async def resume_options(
    origin: str | None = Header(default=None, alias="origin"),
    session: AsyncSession = Depends(get_session),
):
    settings = await _get_settings(session)
    headers = _cors_response(origin, settings)
    headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    headers["Access-Control-Max-Age"] = "86400"
    return Response(status_code=204, headers=headers)
