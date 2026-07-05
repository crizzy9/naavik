"""Generation-trace scaffolding (schema version, initial shape, persistence).

Split out of services/bundle_generator.py in plan 91 Phase 4.4;
behaviour unchanged. `dg` binds the services.document_generator facade,
so `patch("services.bundle_generator.dg.X")` (which mutates that shared
module object) keeps intercepting; the premium pipeline calls the free
composite through the bundle facade for the same reason.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
    Experience,
    Profile,
    Settings,
)
from services.voice_grounding import VoiceCorpus

log = logging.getLogger(__name__)


GENERATION_TRACE_SCHEMA_VERSION = 1


async def _initial_trace(*, settings: Settings, corpus: VoiceCorpus | None) -> dict[str, Any]:
    """Boilerplate fields applied to every trace at start of run."""
    return {
        "schema_version": GENERATION_TRACE_SCHEMA_VERSION,
        "tier": "free",
        "stages_run": [],
        "stages_skipped": [],
        "stage_costs_usd": {},
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
        "llm_calls": 0,
        "bullet_selections": [],
        # Plan 72 § Surface 2 — per-bullet selection ledger with rationale.
        # Each entry: {bullet_id, selected: bool, why_selected: str|null,
        # why_dropped: str|null}. Drives the inline rationale line under each
        # tailored_bullet_row on Discover · review. Additive to bullet_selections;
        # existing readers of bullet_selections are unaffected.
        "bullet_selection_log": [],
        "jd_keywords_extracted": [],
        "cover_letter_format": "standard",
        "hiring_manager": None,
        "voice_fingerprint_hash": corpus.voice_fingerprint_hash if corpus else None,
        "constitution_version": "v1",
        "parse_fidelity_score": None,
        "parse_fidelity_tier": None,
        "parse_fidelity_fields_missing": [],
        "keyword_coverage_score": None,
        "keyword_coverage_missing": [],
        "ai_tell_violations": [],
        "burstiness_std": None,
        "ethics_pre_flight": {"passed": True, "dropped_bullets": [], "flags": []},
        "degraded_mode": False,
        "cost_cap_at_exhaustion": None,
        "headline_used": None,
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def _load_profile_experiences(
    session: AsyncSession, user_id: int
) -> tuple[Profile | None, list[Experience]]:
    profile = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()
    if profile is None:
        return None, []
    experiences = (
        await session.exec(
            select(Experience)
            .where(Experience.profile_id == profile.id, Experience.deleted_at.is_(None))
            .order_by(Experience.order_index)
        )
    ).all()
    return profile, list(experiences)


async def _persist_trace(
    session: AsyncSession, application: Application, trace: dict[str, Any]
) -> None:
    """Write `trace` to `application.generation_trace`. OVERWRITES (no append)."""
    application.generation_trace = trace
    application.updated_at = datetime.now(UTC)
    session.add(application)
    await session.flush()
