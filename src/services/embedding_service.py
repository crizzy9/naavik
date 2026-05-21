"""JobEmbedding service — plan 61 (0.2.7.16).

Owns:
- `embed_job(session, job, settings)` — compute embedding for a Job, persist
  the JobEmbedding row (upsert on `job_id`). Skip when content_hash + model
  already match (idempotent).
- `search_similar(session, user_id, query_embedding, ...)` — cosine-similarity
  top-K over JobEmbedding rows. Per-user only (decision D8).
- `delete_orphan_embeddings(session)` — nightly sweep helper.

LLM call rule: every embedding call goes through `llm_tracker.tracked_call`
so ApiUsage cost rows persist (per `engineer-llm-tracker-wrap` skill).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProvider, LLMProviderError, get_embedding_provider
from models import (
    EMBEDDING_DIM,
    Bullet,
    Experience,
    Job,
    JobEmbedding,
    Profile,
    ProfileEmbedding,
    Settings,
)
from services import llm_tracker

log = logging.getLogger(__name__)


def _content_hash(job: Job) -> str:
    """SHA-1 of (title || description) — detects when Job text changed."""
    blob = ((job.role or "") + "\n" + (job.description or "")).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()


def _embed_text(job: Job) -> str:
    """Compose the per-job text that gets embedded.

    Concatenates company + role + key extracted fields. Bounded by typical
    embedding-model context windows (8K tokens for OpenAI; 2K-4K for nomic).
    """
    parts: list[str] = []
    if job.company:
        parts.append(f"Company: {job.company}")
    if job.role:
        parts.append(f"Role: {job.role}")
    if job.team:
        parts.append(f"Team: {job.team}")
    if job.location:
        parts.append(f"Location: {job.location}")
    if job.description:
        parts.append("")
        parts.append(job.description)
    return "\n".join(parts).strip()


def _model_identifier(provider: LLMProvider, dim: int) -> str:
    """Provenance string stored on the row.

    `<provider_id>/<model>@<dim>` (Ollama omits the dim suffix to match the
    upstream model id convention).
    """
    base = f"{provider.provider_id}/{provider.model_name}"
    return base if provider.provider_id == "ollama" else f"{base}@{dim}"


async def embed_job(
    session: AsyncSession,
    *,
    job: Job,
    settings: Settings,
) -> JobEmbedding | None:
    """Persist (or skip) an embedding row for `job`.

    Skip conditions (no LLM call):
    - `settings.semantic_match_enabled` is False
    - No embedding provider resolves (env not set)
    - Existing row's `content_hash` AND `model` already match.

    Returns the persisted row, or None for any skip path.
    """
    provider = get_embedding_provider(settings)
    if provider is None:
        return None

    expected_hash = _content_hash(job)
    expected_model = _model_identifier(provider, EMBEDDING_DIM)

    existing_stmt = select(JobEmbedding).where(
        JobEmbedding.job_id == job.id,
        JobEmbedding.user_id == job.user_id,
    )
    existing = (await session.exec(existing_stmt)).one_or_none()
    if (
        existing is not None
        and existing.content_hash == expected_hash
        and existing.model == expected_model
    ):
        return existing

    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=job.user_id,
            provider=provider,
            method="embed",
            prompt_name="embed_job",
            text=_embed_text(job),
        )
    except LLMProviderError as exc:
        log.warning("embed_job LLM failed for job %s: %s", job.id, exc)
        return None

    vector = list(result.vector)
    if len(vector) != EMBEDDING_DIM:
        log.warning(
            "embed_job provider returned dim=%d, expected %d; skipping persist",
            len(vector),
            EMBEDDING_DIM,
        )
        return None

    now = datetime.now(UTC)
    if existing is None:
        row = JobEmbedding(
            job_id=job.id,
            user_id=job.user_id,
            embedding=vector,
            model=expected_model,
            dim=EMBEDDING_DIM,
            content_hash=expected_hash,
        )
    else:
        existing.embedding = vector
        existing.model = expected_model
        existing.dim = EMBEDDING_DIM
        existing.content_hash = expected_hash
        existing.updated_at = now
        row = existing
    session.add(row)
    await session.flush()
    return row


async def search_similar(
    session: AsyncSession,
    *,
    user_id: int,
    query_embedding: list[float],
    threshold: float = 0.65,
    limit: int = 20,
) -> list[tuple[int, float]]:
    """Cosine-similarity top-K. Per-user scoped (decision D8).

    Returns `[(job_id, similarity)]` ordered DESC by similarity, with
    similarity >= `threshold`. Raw SQL is encapsulated here — route handlers
    never see it (per AGENTS.md § Key Conventions § DB).

    The cosine-distance operator `<=>` from pgvector returns 0 (identical)
    .. 2 (opposite). Similarity = 1 - distance / 2 maps that to [0, 1]
    where 1 = identical. The `(WHERE user_id = :user_id)` predicate is the
    multi-tenant boundary; never remove.
    """
    if len(query_embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"query_embedding must have dim={EMBEDDING_DIM}, got {len(query_embedding)}"
        )

    # pgvector's parameterized cosine-distance call. Bind the query vector
    # as a string literal matching pgvector's input syntax `[v1,v2,...]`.
    # Bound via :params so SQLAlchemy escapes safely.
    vector_literal = "[" + ",".join(f"{v}" for v in query_embedding) + "]"
    distance_cutoff = (1.0 - threshold) * 2.0

    stmt = text(
        """
        SELECT job_id, embedding <=> CAST(:qvec AS vector) AS distance
        FROM job_embedding
        WHERE user_id = :uid
          AND embedding <=> CAST(:qvec AS vector) <= :dist_cutoff
        ORDER BY distance ASC
        LIMIT :lim
        """
    )
    result = await session.exec(
        stmt.bindparams(qvec=vector_literal, uid=user_id, dist_cutoff=distance_cutoff, lim=limit)
    )
    out: list[tuple[int, float]] = []
    for row in result.all():
        job_id = int(row[0])
        distance = float(row[1])
        similarity = max(0.0, 1.0 - (distance / 2.0))
        out.append((job_id, similarity))
    return out


async def delete_orphan_embeddings(session: AsyncSession) -> int:
    """Drop JobEmbedding rows whose Job is gone or soft-deleted.

    Nightly-batch second-pass. Returns count deleted. Idempotent.
    """
    stmt = text(
        """
        DELETE FROM job_embedding
        WHERE job_id NOT IN (
            SELECT id FROM job WHERE deleted_at IS NULL
        )
        """
    )
    result = await session.exec(stmt)
    count = result.rowcount if hasattr(result, "rowcount") else 0
    await session.flush()
    return int(count or 0)


async def needs_embedding(session: AsyncSession, *, job: Job, settings: Settings) -> bool:
    """True iff `job` would produce work for the nightly batch.

    Helper for the scheduler-job + Settings UI status indicators.
    """
    provider = get_embedding_provider(settings)
    if provider is None:
        return False
    expected_hash = _content_hash(job)
    expected_model = _model_identifier(provider, EMBEDDING_DIM)
    existing = (
        await session.exec(
            select(JobEmbedding).where(
                JobEmbedding.job_id == job.id,
                JobEmbedding.user_id == job.user_id,
            )
        )
    ).one_or_none()
    if existing is None:
        return True
    return existing.content_hash != expected_hash or existing.model != expected_model


# ── ProfileEmbedding — plan 65 (0.3.0.03) ──────────────────────────────


_PROFILE_TOP_BULLETS = 20


def _profile_embed_text(profile: Profile, bullets: list[Bullet]) -> str:
    """Compose the per-profile text that gets embedded.

    `Profile.headline + summary + top-K bullet texts`, ordered by
    `Experience.order_index ASC, Bullet.order_index ASC` (preserving the
    user's resume order). Bounded by the top-K constant.
    """
    parts: list[str] = []
    if profile.headline:
        parts.append(f"Headline: {profile.headline}")
    if profile.summary_short:
        parts.append(f"Summary: {profile.summary_short}")
    if profile.summary_full and profile.summary_full != profile.summary_short:
        parts.append(profile.summary_full)
    if bullets:
        parts.append("Experience bullets:")
        for b in bullets[:_PROFILE_TOP_BULLETS]:
            if b.text:
                parts.append(f"- {b.text}")
    return "\n".join(parts).strip()


def _profile_content_hash(profile: Profile, top_bullets_text: str) -> str:
    """SHA-1 of (headline || summary_short || summary_full || top_bullets_text)."""
    blob = (
        (profile.headline or "")
        + "\n"
        + (profile.summary_short or "")
        + "\n"
        + (profile.summary_full or "")
        + "\n"
        + top_bullets_text
    ).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()


async def _fetch_top_bullets(
    session: AsyncSession, *, profile: Profile, limit: int = _PROFILE_TOP_BULLETS
) -> list[Bullet]:
    """Top-K bullets across the profile ordered by experience order_index."""
    if profile.id is None:
        return []
    stmt = (
        select(Bullet)
        .join(Experience, Bullet.experience_id == Experience.id)
        .where(
            Experience.profile_id == profile.id,
            Bullet.deleted_at.is_(None),
            Experience.deleted_at.is_(None),
        )
        .order_by(Experience.order_index.asc(), Bullet.order_index.asc())
        .limit(limit)
    )
    return list((await session.exec(stmt)).all())


async def embed_profile(
    session: AsyncSession,
    *,
    profile: Profile,
    settings: Settings,
) -> ProfileEmbedding | None:
    """Persist (or skip) an embedding row for `profile`. Plan 65 § D.3.

    Skip conditions (no LLM call):
    - `settings.semantic_match_enabled` is False
    - No embedding provider resolves (env not set)
    - Existing row's `content_hash` AND `model` already match.

    Returns the persisted row, or None for any skip path.
    """
    provider = get_embedding_provider(settings)
    if provider is None:
        return None

    bullets = await _fetch_top_bullets(session, profile=profile)
    text_blob = _profile_embed_text(profile, bullets)
    expected_hash = _profile_content_hash(profile, text_blob)
    expected_model = _model_identifier(provider, EMBEDDING_DIM)

    existing_stmt = select(ProfileEmbedding).where(ProfileEmbedding.user_id == profile.user_id)
    existing = (await session.exec(existing_stmt)).one_or_none()
    if (
        existing is not None
        and existing.content_hash == expected_hash
        and existing.model == expected_model
    ):
        return existing

    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=profile.user_id,
            provider=provider,
            method="embed",
            prompt_name="embed_profile",
            text=text_blob,
        )
    except LLMProviderError as exc:
        log.warning("embed_profile LLM failed for user %s: %s", profile.user_id, exc)
        return None

    vector = list(result.vector)
    if len(vector) != EMBEDDING_DIM:
        log.warning(
            "embed_profile provider returned dim=%d, expected %d; skipping persist",
            len(vector),
            EMBEDDING_DIM,
        )
        return None

    now = datetime.now(UTC)
    if existing is None:
        row = ProfileEmbedding(
            user_id=profile.user_id,
            embedding=vector,
            model=expected_model,
            dim=EMBEDDING_DIM,
            content_hash=expected_hash,
        )
    else:
        existing.embedding = vector
        existing.model = expected_model
        existing.dim = EMBEDDING_DIM
        existing.content_hash = expected_hash
        existing.updated_at = now
        row = existing
    session.add(row)
    await session.flush()
    return row


async def needs_profile_embedding(
    session: AsyncSession, *, profile: Profile, settings: Settings
) -> bool:
    """True iff `profile` would produce work for the refresh cron."""
    provider = get_embedding_provider(settings)
    if provider is None:
        return False
    bullets = await _fetch_top_bullets(session, profile=profile)
    text_blob = _profile_embed_text(profile, bullets)
    expected_hash = _profile_content_hash(profile, text_blob)
    expected_model = _model_identifier(provider, EMBEDDING_DIM)
    existing = (
        await session.exec(
            select(ProfileEmbedding).where(ProfileEmbedding.user_id == profile.user_id)
        )
    ).one_or_none()
    if existing is None:
        return True
    return existing.content_hash != expected_hash or existing.model != expected_model


async def maybe_refresh_profile_embedding(
    session: AsyncSession, *, user_id: int
) -> ProfileEmbedding | None:
    """Best-effort on-edit hook (plan 65 § D.3 OQ-6).

    Called from `profile_service` after profile/bullet mutations. Resolves
    Profile + Settings, calls `embed_profile`. Errors are swallowed +
    logged; nightly cron is the safety net. Returns the row or None.
    """
    try:
        profile = (
            await session.exec(select(Profile).where(Profile.user_id == user_id))
        ).one_or_none()
        if profile is None:
            return None
        settings = (
            await session.exec(select(Settings).where(Settings.user_id == user_id))
        ).one_or_none()
        if settings is None or not settings.semantic_match_enabled:
            return None
        return await embed_profile(session, profile=profile, settings=settings)
    except Exception as exc:  # noqa: BLE001
        # Best-effort — nightly cron picks up missed refreshes.
        log.warning("maybe_refresh_profile_embedding swallowed for user %s: %s", user_id, exc)
        return None
