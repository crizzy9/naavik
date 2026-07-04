"""Resume PDF → AI extraction → structured Profile.

Per BACKEND.md § H.1 + plan 10 § C (extraction). Owns SSE event emission for
the Onboarding step 2 progress dots.

Flow:
1. Read uploaded PDF bytes (path or BytesIO).
2. Extract text via `pypdf` if available, else fall back to plain UTF-8 decode
   for tests using `.txt` fixtures.
3. Call `prompts.extract_resume(provider, text)` for structured output.
4. Persist Profile + Experience + Bullet rows via profile_service.
5. Emit SSE events at each step (`extracting / structuring / persisting / done`)
   so the Onboarding step-2 progress dots animate.

Wave 6 ships the pipeline; Phase 2+ adds OCR fallback for image-only PDFs.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProvider, LLMProviderError, get_provider
from models import Bullet, Experience, Profile, Settings
from services import llm_tracker

log = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Failure to extract or structure a resume."""


async def _read_pdf_text(path: Path) -> str:
    """Pull plain text out of a PDF (or fall back to raw read for tests)."""
    if not path.exists():
        raise ExtractionError(f"resume file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover — pypdf is optional in tests
            raise ExtractionError("pypdf not installed; run `uv sync` to add the dep") from exc
        try:
            reader = PdfReader(str(path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(f"PDF parse failed: {exc}") from exc
    # `.txt` and other plain-text fallbacks for tests
    return path.read_text(encoding="utf-8", errors="replace")


# ── Public API ─────────────────────────────────────────────────────────


async def extract_resume_text(path: Path) -> str:
    return await _read_pdf_text(Path(path))


async def extract_to_profile(
    session: AsyncSession,
    *,
    user_id: int,
    settings: Settings,
    pdf_path: Path,
) -> Profile:
    """Full PDF → AI → Profile bootstrap. Returns the Profile row.

    If a Profile already exists, fields are merged in (non-destructive).
    Bullets get auto-tagged via `prompts.auto_tag_bullets`.
    """
    text = await extract_resume_text(pdf_path)
    if not text.strip():
        raise ExtractionError("no extractable text in resume")
    provider = get_provider(settings)
    structured = await _structure_with_llm(
        session=session,
        user_id=user_id,
        provider=provider,
        resume_text=text,
    )
    profile = await _persist_profile(session, user_id=user_id, structured=structured)
    return profile


async def extract_to_profile_sse(
    session: AsyncSession,
    *,
    user_id: int,
    settings: Settings,
    pdf_path: Path,
) -> AsyncIterator[str]:
    """Same as `extract_to_profile` but yields SSE events for Onboarding step 2."""

    async def _gen() -> AsyncIterator[str]:
        yield _sse_event("extracting", {"step": 1, "of": 4, "label": "Reading resume"})
        try:
            text = await extract_resume_text(pdf_path)
        except ExtractionError as exc:
            yield _sse_event("error", {"message": str(exc)})
            return
        yield _sse_event("structuring", {"step": 2, "of": 4, "label": "Structuring profile"})
        try:
            provider = get_provider(settings)
            structured = await _structure_with_llm(
                session=session,
                user_id=user_id,
                provider=provider,
                resume_text=text,
            )
        except (LLMProviderError, ExtractionError) as exc:
            yield _sse_event("error", {"message": str(exc)})
            return
        yield _sse_event("persisting", {"step": 3, "of": 4, "label": "Saving"})
        try:
            await _persist_profile(session, user_id=user_id, structured=structured)
        except Exception as exc:  # noqa: BLE001
            yield _sse_event("error", {"message": str(exc)})
            return
        yield _sse_event("done", {"step": 4, "of": 4, "label": "Profile ready", "complete": True})

    return _gen()


# ── Internals ──────────────────────────────────────────────────────────


def _sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


async def _structure_with_llm(
    *,
    session: AsyncSession,
    user_id: int,
    provider: LLMProvider,
    resume_text: str,
) -> dict[str, Any]:
    # NOTE: the package __init__ re-exports the `extract_resume` FUNCTION,
    # shadowing the module attribute — import the names directly.
    from llm.prompts.extract_resume import PROMPT, TAG_VOCAB, ExtractedResume

    prompt = PROMPT.format(
        resume_text=resume_text[:30_000],
        tag_vocab=", ".join(TAG_VOCAB),
    )
    result = await llm_tracker.tracked_call(
        session=session,
        user_id=user_id,
        provider=provider,
        method="structured",
        prompt_name="extract_resume",
        prompt=prompt,
        schema=ExtractedResume,
        max_tokens=8192,
    )
    return dict(result.value)


async def _persist_profile(
    session: AsyncSession,
    *,
    user_id: int,
    structured: dict[str, Any],
) -> Profile:
    """Upsert Profile identity + REPLACE the resume-derived sections.

    The uploaded resume is the source of truth for experiences / bullets /
    educations / skills / projects — re-uploading replaces those wholesale
    (owner directive: "Update Resume … should replace the current content").
    Profile identity fields merge non-destructively so hand-edits survive.
    """
    from sqlmodel import delete, select

    from models import Certification, Education, Project, Skill

    existing = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()

    # ExtractedResume carries identity fields at the top level; older
    # callers/tests may still nest them under "profile".
    profile_payload = structured.get("profile") or structured.get("profile_data") or structured

    now = datetime.now(UTC)
    if existing is None:
        profile = Profile(
            user_id=user_id,
            full_name=profile_payload.get("full_name") or "Unknown",
            headline=profile_payload.get("headline") or "",
            email=profile_payload.get("email") or "",
            phone=profile_payload.get("phone"),
            location=profile_payload.get("location"),
            portfolio_url=profile_payload.get("portfolio_url"),
            github_handle=profile_payload.get("github_handle"),
            linkedin_handle=profile_payload.get("linkedin_handle"),
            summary_full=profile_payload.get("summary_full"),
            summary_short=profile_payload.get("summary_short"),
            created_at=now,
            updated_at=now,
        )
        session.add(profile)
        await session.flush()
    else:
        # Merge — only set known identity fields that aren't already populated.
        for key in (
            "full_name",
            "headline",
            "email",
            "phone",
            "location",
            "portfolio_url",
            "github_handle",
            "linkedin_handle",
            "summary_full",
            "summary_short",
        ):
            value = profile_payload.get(key)
            if value is None:
                continue
            if not getattr(existing, key, None):
                setattr(existing, key, value)
        existing.updated_at = now
        session.add(existing)
        await session.flush()
        profile = existing

    # Replace resume-derived sections (mirrors account_service's child→parent
    # deletion order so the SQLite test backend works without FK cascades).
    old_exp_ids = [
        exp_id
        for exp_id in (
            await session.exec(select(Experience.id).where(Experience.profile_id == profile.id))
        ).all()
        if exp_id is not None
    ]
    if old_exp_ids:
        await session.exec(delete(Bullet).where(Bullet.experience_id.in_(old_exp_ids)))
        await session.exec(delete(Experience).where(Experience.id.in_(old_exp_ids)))
    await session.exec(delete(Education).where(Education.profile_id == profile.id))
    await session.exec(delete(Skill).where(Skill.profile_id == profile.id))
    await session.exec(delete(Project).where(Project.profile_id == profile.id))
    await session.exec(delete(Certification).where(Certification.profile_id == profile.id))
    await session.flush()

    for order, exp_payload in enumerate(structured.get("experiences") or []):
        start = _parse_date(exp_payload.get("start_date")) or now
        end = _parse_date(exp_payload.get("end_date"))
        if end is not None and end <= start:
            end = None  # ck_experience_dates: start_date < end_date
        exp = Experience(
            profile_id=profile.id,
            company=exp_payload.get("company") or "",
            title=exp_payload.get("title") or exp_payload.get("role") or "",
            team=exp_payload.get("team"),
            location=exp_payload.get("location"),
            start_date=start,
            end_date=end,
            order_index=exp_payload.get("order_index", order),
            created_at=now,
            updated_at=now,
        )
        session.add(exp)
        await session.flush()
        from llm.prompts.extract_resume import TAG_VOCAB

        bullet_tags = exp_payload.get("bullet_tags") or []
        for idx, b_payload in enumerate(exp_payload.get("bullets") or []):
            if isinstance(b_payload, str):
                text = b_payload
                tags = bullet_tags[idx] if idx < len(bullet_tags) else []
            else:
                text = b_payload.get("text", "")
                tags = b_payload.get("tags", [])
            # Guardrail (ERD_v2 rec #2): only vocabulary tags reach the DB —
            # off-vocab strings from the extractor would silently poison
            # tag-based scoring and bullet selection.
            tags = [t for t in (tags or []) if t in TAG_VOCAB]
            bullet = Bullet(
                experience_id=exp.id,
                order_index=idx,
                text=text,
                tags=list(tags or []),
                edited_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(bullet)
        await session.flush()

    for order, edu_payload in enumerate(structured.get("educations") or []):
        institution = edu_payload.get("institution") or edu_payload.get("school") or ""
        if not institution:
            continue
        session.add(
            Education(
                profile_id=profile.id,
                institution=institution,
                school=edu_payload.get("school"),
                location=edu_payload.get("location"),
                degree=edu_payload.get("degree") or "",
                start_date=_parse_date(edu_payload.get("start_date")) or now,
                end_date=_parse_date(edu_payload.get("end_date")),
                gpa=edu_payload.get("gpa"),
                courses=list(edu_payload.get("courses") or []),
                order_index=order,
                created_at=now,
                updated_at=now,
            )
        )

    for order, skill_payload in enumerate(structured.get("skills") or []):
        category = skill_payload.get("category") or ""
        if not category:
            continue
        session.add(
            Skill(
                profile_id=profile.id,
                category=category,
                items=list(skill_payload.get("items") or []),
                order_index=order,
                created_at=now,
                updated_at=now,
            )
        )

    for order, proj_payload in enumerate(structured.get("projects") or []):
        title = proj_payload.get("title") or proj_payload.get("name") or ""
        if not title:
            continue
        kind = proj_payload.get("kind")
        if kind not in ("project", "open_source"):
            kind = "project"
        session.add(
            Project(
                profile_id=profile.id,
                kind=kind,
                title=title,
                date=_parse_date(proj_payload.get("date")),
                text=proj_payload.get("text") or proj_payload.get("description") or "",
                tags=list(proj_payload.get("tags") or []),
                link=proj_payload.get("link") or proj_payload.get("url"),
                order_index=order,
                created_at=now,
                updated_at=now,
            )
        )

    for order, cert_payload in enumerate(structured.get("certifications") or []):
        title = cert_payload.get("title") or cert_payload.get("name") or ""
        if not title:
            continue
        session.add(
            Certification(
                profile_id=profile.id,
                title=title,
                issuer=cert_payload.get("issuer") or "",
                date=_parse_date(cert_payload.get("date")),
                description=cert_payload.get("description"),
                order_index=order,
                created_at=now,
                updated_at=now,
            )
        )

    await session.flush()
    return profile


def _parse_date(raw: Any) -> datetime | None:
    """Parse ISO-ish date strings the extractor emits: full ISO, YYYY-MM, YYYY."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            return None
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            # asyncpg rejects naive datetimes on TIMESTAMPTZ columns.
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
        import re as _re

        m = _re.fullmatch(r"(\d{4})-(\d{2})", candidate)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=UTC)
        m = _re.fullmatch(r"(\d{4})", candidate)
        if m:
            return datetime(int(m.group(1)), 1, 1, tzinfo=UTC)
        return None
    return None


__all__ = [
    "ExtractionError",
    "extract_resume_text",
    "extract_to_profile",
    "extract_to_profile_sse",
]
