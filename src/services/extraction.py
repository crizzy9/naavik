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
    schema = __import__("llm.prompts.extract_resume", fromlist=["ExtractedResume"]).ExtractedResume
    prompt = (
        "Extract structured fields from this resume.\n\n"
        f"Resume text:\n{resume_text[:8000]}\n\n"
        "Return ExtractedResume with profile + experiences + bullets."
    )
    result = await llm_tracker.tracked_call(
        session=session,
        user_id=user_id,
        provider=provider,
        method="structured",
        prompt_name="extract_resume",
        prompt=prompt,
        schema=schema,
    )
    return dict(result.value)


async def _persist_profile(
    session: AsyncSession,
    *,
    user_id: int,
    structured: dict[str, Any],
) -> Profile:
    """Upsert Profile + Experience + Bullet rows from the structured payload."""
    from sqlmodel import select

    existing = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()

    profile_payload = structured.get("profile") or structured.get("profile_data") or {}

    now = datetime.now(UTC)
    if existing is None:
        profile = Profile(
            user_id=user_id,
            full_name=profile_payload.get("full_name", "Unknown"),
            headline=profile_payload.get("headline", ""),
            email=profile_payload.get("email", ""),
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
        # Merge — only set fields that aren't already populated.
        for key, value in profile_payload.items():
            if value is None:
                continue
            if hasattr(existing, key) and not getattr(existing, key, None):
                setattr(existing, key, value)
        existing.updated_at = now
        session.add(existing)
        await session.flush()
        profile = existing

    # Persist experiences + bullets if present.
    for exp_payload in structured.get("experiences", []):
        exp = Experience(
            profile_id=profile.id,
            company=exp_payload.get("company", ""),
            title=exp_payload.get("title") or exp_payload.get("role", ""),
            location=exp_payload.get("location"),
            start_date=_parse_date(exp_payload.get("start_date")) or now,
            end_date=_parse_date(exp_payload.get("end_date")),
            order_index=exp_payload.get("order_index", 0),
            created_at=now,
            updated_at=now,
        )
        session.add(exp)
        await session.flush()
        for idx, b_payload in enumerate(exp_payload.get("bullets", [])):
            bullet = Bullet(
                experience_id=exp.id,
                order_index=idx,
                text=b_payload if isinstance(b_payload, str) else b_payload.get("text", ""),
                tags=(b_payload.get("tags", []) if isinstance(b_payload, dict) else []),
                edited_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(bullet)
            await session.flush()
    return profile


def _parse_date(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


__all__ = [
    "ExtractionError",
    "extract_resume_text",
    "extract_to_profile",
    "extract_to_profile_sse",
]
