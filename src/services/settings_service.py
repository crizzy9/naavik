"""Settings service — Wave 4 of plan 10 § B.8.

DB-backed CRUD for the per-user `Settings` singleton. Plan 26 (0.2.0.01)
deleted the encrypted vault: every secret (LLM API keys, OAuth refresh
tokens, IMAP passwords, ATS cookies, Discord webhook URL, Telegram bot
token, Netlify build hook) now flows through env vars consumed by
`pydantic-settings` in `src/config.py`. Settings stores no secret material
and exposes no presence indicators — those are runtime-derived via
`services/env_secrets.py`.

Plan 67 (0.3.4) carve-out: `Settings.originality_api_key` IS a secret but
lives in the per-user DB column (per-user opt-in for a third-party API
key). The vault-sunset rule applies to env-vs-vault for shared deployment
secrets; per-user knobs in the Settings UI remain DB-backed.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import ApiUsage, Application, Settings
from models import LLMProvider as LLMProviderEnum

log = logging.getLogger(__name__)

VALID_GENERATION_TIERS: frozenset[str] = frozenset({"free", "premium"})


async def get_or_create(session: AsyncSession, user_id: int) -> Settings:
    stmt = select(Settings).where(Settings.user_id == user_id)
    row = (await session.exec(stmt)).one_or_none()
    if row is not None:
        return row
    row = Settings(user_id=user_id)
    session.add(row)
    await session.flush()
    return row


# ── Per-tab updates ──────────────────────────────────────────────────────


async def update_llm(
    session: AsyncSession,
    user_id: int,
    *,
    provider: LLMProviderEnum | None = None,
    model: str | None = None,
    fallback_provider: LLMProviderEnum | None = None,
    semantic_match_enabled: bool | None = None,
    embedding_provider: str | None = None,
    semantic_match_threshold: float | None = None,
    semantic_match_sync_on_upsert: bool | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if provider is not None:
        s.llm_provider = provider
    if model is not None:
        s.llm_model = model
    if fallback_provider is not None:
        s.llm_fallback_provider = fallback_provider
    # Plan 61 (0.2.7.16) — semantic-match toggles. `None` means "skip" so
    # partial PUTs don't clobber unrelated fields.
    if semantic_match_enabled is not None:
        s.semantic_match_enabled = bool(semantic_match_enabled)
    if embedding_provider is not None:
        # Empty string = clear (user selected "Auto").
        s.embedding_provider = embedding_provider or None
    if semantic_match_threshold is not None:
        threshold = float(semantic_match_threshold)
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError("semantic_match_threshold must be between 0.0 and 1.0")
        s.semantic_match_threshold = threshold
    if semantic_match_sync_on_upsert is not None:
        s.semantic_match_sync_on_upsert = bool(semantic_match_sync_on_upsert)
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    return s


async def update_auto_apply(
    session: AsyncSession,
    user_id: int,
    *,
    auto_apply_enabled: bool | None = None,
    auto_apply_score_threshold: float | None = None,
    auto_apply_daily_cap: int | None = None,
    eager_review_generation: bool | None = None,
    daily_llm_cost_cap_usd: float | None = None,
    auto_apply_immediate_dispatch: bool | None = None,
    auto_apply_per_board_daily_caps: dict[str, int] | None = None,
    auto_apply_dry_run: bool | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if auto_apply_enabled is not None:
        s.auto_apply_enabled = auto_apply_enabled
    if auto_apply_score_threshold is not None:
        s.auto_apply_score_threshold = float(auto_apply_score_threshold)
    if auto_apply_daily_cap is not None:
        s.auto_apply_daily_cap = auto_apply_daily_cap
    if eager_review_generation is not None:
        s.eager_review_generation = eager_review_generation
    if daily_llm_cost_cap_usd is not None:
        s.daily_llm_cost_cap_usd = float(daily_llm_cost_cap_usd)
    if auto_apply_immediate_dispatch is not None:
        s.auto_apply_immediate_dispatch = auto_apply_immediate_dispatch
    # Plan 78 § D.3 — per-board daily caps. Validator: drop unknown boards,
    # coerce values to int ≥ 0, drop non-positive entries.
    if auto_apply_per_board_daily_caps is not None:
        from models import ApplicationBoard

        validated: dict[str, int] = {}
        valid_boards = {b.value for b in ApplicationBoard}
        for board, cap in auto_apply_per_board_daily_caps.items():
            if board not in valid_boards:
                continue
            try:
                v = int(cap)
            except (TypeError, ValueError):
                continue
            if v > 0:
                validated[board] = v
        s.auto_apply_per_board_daily_caps = validated
    # Plan 78 § D.5 — dry-run toggle.
    if auto_apply_dry_run is not None:
        s.auto_apply_dry_run = bool(auto_apply_dry_run)
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    return s


async def update_sources(
    session: AsyncSession,
    user_id: int,
    *,
    sources_enabled: dict[str, bool] | None = None,
    source_schedules: dict[str, str] | None = None,
    workday_companies: list[str] | None = None,
    linkedin_keywords: list[str] | None = None,
    linkedin_location: str | None = None,
    indeed_keywords: list[str] | None = None,
    indeed_location: str | None = None,
    scraper_rate_limits: dict[str, dict] | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if sources_enabled is not None:
        s.sources_enabled = sources_enabled
    if source_schedules is not None:
        s.source_schedules = source_schedules
    if workday_companies is not None:
        s.workday_companies = workday_companies
    if linkedin_keywords is not None:
        s.linkedin_keywords = linkedin_keywords
    if linkedin_location is not None:
        s.linkedin_location = linkedin_location
    if indeed_keywords is not None:
        s.indeed_keywords = indeed_keywords
    if indeed_location is not None:
        s.indeed_location = indeed_location
    if scraper_rate_limits is not None:
        from scraper.rate_limit import RateLimitConfig

        validated: dict[str, dict] = {}
        for source_value, raw in scraper_rate_limits.items():
            validated[source_value] = RateLimitConfig.model_validate(raw).model_dump()
        s.scraper_rate_limits = validated
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    # APScheduler reschedule fires here in Wave 6 — Phase 1 stubs the scheduler.
    return s


async def update_notifications(
    session: AsyncSession,
    user_id: int,
    *,
    notify_threshold: float | None = None,
    notify_on_errors: bool | None = None,
    notifications_enabled: dict[str, bool] | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if notify_threshold is not None:
        s.notify_threshold = float(notify_threshold)
    if notify_on_errors is not None:
        s.notify_on_errors = notify_on_errors
    if notifications_enabled is not None:
        s.notifications_enabled = notifications_enabled
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    return s


# ── Generation tier + Originality (plan 67 / 0.3.4) ──────────────────────


@dataclass(frozen=True, slots=True)
class CostProjection:
    """PREMIUM-tier per-bundle cost projection.

    `from_history=True` when computed from >=10 PREMIUM bundles; otherwise
    surfaces the ROADMAP-cited fallback so first-time users still see a
    meaningful estimate.
    """

    detector_usd: float
    council_usd: float
    critique_usd: float
    tool_loop_usd: float
    originality_usd: float
    total_usd: float
    from_history: bool
    sample_size: int = 0


_PREMIUM_PROJECTION_FALLBACK = CostProjection(
    detector_usd=0.10,
    council_usd=0.10,
    critique_usd=0.10,
    tool_loop_usd=0.30,
    originality_usd=0.01,
    total_usd=0.61,
    from_history=False,
    sample_size=0,
)

# Per-stage prompt_name -> projection field mapping. Anchors history lookup
# to the actual ApiUsage rows the PREMIUM stages persist.
_PREMIUM_STAGE_PROMPTS = {
    "detector_usd": (
        "detect_ai_likelihood",
        "refine_to_human",
    ),
    "council_usd": (
        "council_pragmatic_recruiter",
        "council_hiring_manager",
        "council_cultural_fit",
        "council_pragmatic_recruiter_batch",
        "council_hiring_manager_batch",
        "council_cultural_fit_batch",
    ),
    "critique_usd": (
        "critique_faang_l5_l6_hm",
        "critique_startup_founder",
        "critique_fortune_500_hr",
        "critique_faang_l5_l6_hm_batch",
        "critique_startup_founder_batch",
        "critique_fortune_500_hr_batch",
    ),
    "tool_loop_usd": (
        "orchestrate_refinement_iter_0",
        "orchestrate_refinement_iter_1",
        "orchestrate_refinement_iter_2",
        "recruiter_skim_score",
    ),
    "originality_usd": ("originality_ai_scan",),
}


async def update_generation(
    session: AsyncSession,
    user_id: int,
    *,
    generation_tier: str | None = None,
    originality_api_key: str | None = None,
    originality_api_key_clear: bool = False,
    tier_2_evasion_enabled: bool | None = None,
    ai_writing_voice_samples: str | None = None,
    cover_letter_format: str | None = None,
    resume_template_preference: str | None = None,
    parse_fidelity_threshold: float | None = None,
) -> Settings:
    """Persist Generation-tab updates. `None` per arg = skip (partial PUT).

    `originality_api_key`: non-None, non-empty string = set; None = skip
    (preserves existing). To explicitly clear, pass
    `originality_api_key_clear=True` — prevents accidental wipe when the
    Generation form re-submits without re-entering the password input.
    """
    s = await get_or_create(session, user_id)
    if generation_tier is not None:
        if generation_tier not in VALID_GENERATION_TIERS:
            raise ValueError(f"generation_tier must be one of {sorted(VALID_GENERATION_TIERS)}")
        s.generation_tier = generation_tier
    if originality_api_key_clear:
        s.originality_api_key = None
    elif originality_api_key is not None and str(originality_api_key).strip():
        s.originality_api_key = str(originality_api_key).strip()
    if tier_2_evasion_enabled is not None:
        s.tier_2_evasion_enabled = bool(tier_2_evasion_enabled)
    if ai_writing_voice_samples is not None:
        s.ai_writing_voice_samples = ai_writing_voice_samples
    if cover_letter_format is not None:
        s.cover_letter_format = cover_letter_format
    if resume_template_preference is not None:
        s.resume_template_preference = resume_template_preference
    if parse_fidelity_threshold is not None:
        threshold = float(parse_fidelity_threshold)
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError("parse_fidelity_threshold must be between 0.0 and 1.0")
        s.parse_fidelity_threshold = threshold
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    return s


async def compute_premium_cost_projection(
    session: AsyncSession,
    *,
    user_id: int,
    min_sample: int = 10,
) -> CostProjection:
    """Compute per-stage cost projection from recent PREMIUM bundles.

    History-based when at least `min_sample` Applications carry
    `generation_trace.tier == "premium"`. Otherwise returns the ROADMAP
    fallback (T12).
    """
    try:
        rows = (
            await session.exec(
                select(Application.id, Application.generation_trace)
                .where(Application.deleted_at.is_(None))
                .where(Application.user_id == user_id)
                .where(Application.generation_trace.is_not(None))
                .order_by(desc(Application.updated_at))
                .limit(50)
            )
        ).all()
    except Exception as exc:  # noqa: BLE001 — JSONB query may fall over on sqlite
        log.debug("premium cost projection history query failed: %s", exc)
        return _PREMIUM_PROJECTION_FALLBACK

    premium_app_ids: list[int] = []
    for row in rows:
        if isinstance(row, tuple):
            app_id, trace = row[0], row[1]
        else:
            app_id, trace = row.id, row.generation_trace
        if isinstance(trace, dict) and trace.get("tier") == "premium":
            premium_app_ids.append(int(app_id))
        if len(premium_app_ids) >= min_sample:
            break

    if len(premium_app_ids) < min_sample:
        return _PREMIUM_PROJECTION_FALLBACK

    try:
        usage_rows = (
            await session.exec(
                select(ApiUsage.application_id, ApiUsage.prompt_name, ApiUsage.cost_usd)
                .where(ApiUsage.user_id == user_id)
                .where(ApiUsage.application_id.in_(premium_app_ids))
                .where(ApiUsage.succeeded.is_(True))
            )
        ).all()
    except Exception as exc:  # noqa: BLE001
        log.debug("premium cost projection usage query failed: %s", exc)
        return _PREMIUM_PROJECTION_FALLBACK

    # Group cost by application + by stage
    per_app_stage: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in usage_rows:
        if isinstance(row, tuple):
            app_id, prompt_name, cost = row[0], row[1], row[2]
        else:
            app_id, prompt_name, cost = row.application_id, row.prompt_name, row.cost_usd
        if app_id is None or prompt_name is None:
            continue
        for stage_key, prompts in _PREMIUM_STAGE_PROMPTS.items():
            if prompt_name in prompts:
                per_app_stage[app_id][stage_key] += float(cost or 0.0)
                break

    # Average per-stage across applications
    sample_size = len(per_app_stage)
    if sample_size == 0:
        return _PREMIUM_PROJECTION_FALLBACK
    stage_totals: dict[str, float] = defaultdict(float)
    for app_costs in per_app_stage.values():
        for stage_key, cost in app_costs.items():
            stage_totals[stage_key] += cost
    averages: dict[str, float] = {
        stage_key: stage_totals[stage_key] / sample_size for stage_key in _PREMIUM_STAGE_PROMPTS
    }
    total = sum(averages.values())
    return CostProjection(
        detector_usd=round(averages.get("detector_usd", 0.0), 4),
        council_usd=round(averages.get("council_usd", 0.0), 4),
        critique_usd=round(averages.get("critique_usd", 0.0), 4),
        tool_loop_usd=round(averages.get("tool_loop_usd", 0.0), 4),
        originality_usd=round(averages.get("originality_usd", 0.0), 4),
        total_usd=round(total, 4),
        from_history=True,
        sample_size=sample_size,
    )


async def list_recent_generation_traces(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
) -> list[dict]:
    """Return the last `limit` Applications whose generation_trace is non-null.

    Used by the Settings · Generation tab audit-trail viewer. Returns a
    list of dicts with: `application_id`, `company`, `role`, `updated_at`,
    `tier`, `trace` (the full JSONB blob).
    """
    try:
        rows = (
            await session.exec(
                select(
                    Application.id,
                    Application.company,
                    Application.role,
                    Application.updated_at,
                    Application.generation_trace,
                )
                .where(Application.user_id == user_id)
                .where(Application.deleted_at.is_(None))
                .where(Application.generation_trace.is_not(None))
                .order_by(desc(Application.updated_at))
                .limit(limit)
            )
        ).all()
    except Exception as exc:  # noqa: BLE001
        log.debug("list_recent_generation_traces query failed: %s", exc)
        return []
    out: list[dict] = []
    for row in rows:
        if isinstance(row, tuple):
            app_id, company, role, updated_at, trace = row
        else:
            app_id = row.id
            company = row.company
            role = row.role
            updated_at = row.updated_at
            trace = row.generation_trace
        if not isinstance(trace, dict):
            continue
        out.append(
            {
                "application_id": int(app_id),
                "company": company,
                "role": role,
                "updated_at": updated_at,
                "tier": trace.get("tier", "free"),
                "trace": trace,
            }
        )
    return out


# ── Deployment metadata ──────────────────────────────────────────────────


async def get_deployment_info(session: AsyncSession, user_id: int) -> dict[str, Any]:
    """Return the bundle Settings · Deployment renders.

    Plan 26 (0.2.0.01): the vault status triplet (`vault_locked`,
    `vault_fingerprint_stored`, `vault_fingerprint_expected`) is removed
    along with the vault. Self-hosters set secrets via `.env`; filesystem
    permissions are the operative defense.
    """
    s = await get_or_create(session, user_id)
    return {
        "deployment_mode": s.deployment_mode.value,
        "debug": s.debug,
        "settings_user_id": s.user_id,
    }
