"""Recruiter-priority headline generation — plan 66 (0.3.1) § T7.

Gates on `JobScore.score >= 0.50` (the JD-fit floor where it's worth
spending the LLM token to tailor a headline). Below threshold returns
None — caller falls back to `Profile.headline` static value.

H1B sponsorship signal threads into the headline ONLY when the
candidate's `work_authorization` indicates a constraint (H1B, OPT_STEM,
F1_OPT). Other auths suppress the signal.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError, get_provider
from llm.prompts.tailor_headline import TailoredHeadline, tailor_headline
from models import Experience, Job, Profile, Settings
from models.enums import WorkAuthorization
from services import llm_tracker

log = logging.getLogger(__name__)

# Gate threshold per T7 — don't tailor headline for jobs below this score.
HEADLINE_SCORE_GATE = 0.50

# Auths that warrant a `sponsorship_signal` line in the headline.
_SPONSORSHIP_AUTHS: frozenset[WorkAuthorization] = frozenset(
    {
        WorkAuthorization.H1B,
        WorkAuthorization.OPT_CPT,
        WorkAuthorization.OTHER_REQUIRES_SPONSORSHIP,
    }
)


def _years_from_experiences(experiences: list[Experience]) -> int:
    """Sum role spans (truncated to integer years; min 0)."""
    total_days = 0
    now = datetime.now(UTC)
    for exp in experiences:
        if exp.start_date is None:
            continue
        end = exp.end_date or now
        delta = end - exp.start_date
        if delta.days > 0:
            total_days += delta.days
    return max(0, total_days // 365)


def _wants_sponsorship_signal(profile: Profile) -> bool:
    auth = profile.work_authorization
    return auth is not None and auth in _SPONSORSHIP_AUTHS


async def tailor_headline_for_application(
    session: AsyncSession,
    *,
    user_id: int,
    settings: Settings,
    profile: Profile,
    experiences: list[Experience],
    job: Job,
    job_score: float,
    matched_tags: list[str],
    application_id: int | None = None,
    system: str | None = None,
    cache_system: bool = False,
) -> TailoredHeadline | None:
    """Run the headline LLM call. Returns None when gated below threshold.

    Wraps `tailor_headline` in `llm_tracker.tracked_call` so cost +
    latency flow into ApiUsage (mandatory per AGENTS.md § Key
    Conventions § LLM Integration).
    """
    if job_score < HEADLINE_SCORE_GATE:
        return None

    provider = get_provider(settings)
    profile_payload: dict[str, Any] = {
        "full_name": profile.full_name,
        "headline": profile.headline,
        "summary_full": profile.summary_full,
        "summary_short": profile.summary_short,
        "years_experience": _years_from_experiences(experiences),
        "work_authorization": (
            profile.work_authorization.value if profile.work_authorization is not None else None
        )
        if _wants_sponsorship_signal(profile)
        else None,
        "tags": [],  # populated upstream by orchestrator if needed
    }
    job_payload = {
        "role": job.role,
        "role_family": "",  # 0.3.0 didn't add this; leave blank
        "company": job.company,
        "description": job.description or job.description_html or "",
    }

    try:
        # Use tracked_call so ApiUsage rows persist. The prompt wrapper takes
        # the provider directly + does the structured call; we wrap it here.
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="tailor_headline",
            application_id=application_id,
            prompt=_format_prompt(profile_payload, job_payload, matched_tags),
            schema=TailoredHeadline,
            system=system,
            cache_system=cache_system,
        )
        return TailoredHeadline.model_validate(result.value)
    except LLMProviderError as exc:
        log.warning("tailor_headline LLM failed; falling back to static headline: %s", exc)
        return None


def _format_prompt(profile: dict, job: dict, matched_tags: list[str]) -> str:
    """Mirror the prompt template in `llm/prompts/tailor_headline.py`.

    Keeps the rendering identical to the direct-callable path so behavior
    is consistent across both surfaces (tracked + non-tracked).
    """
    from llm.prompts.tailor_headline import PROMPT

    return PROMPT.format(
        full_name=profile.get("full_name", ""),
        existing_headline=profile.get("headline", ""),
        summary=(profile.get("summary_full") or profile.get("summary_short") or "")[:600],
        years=profile.get("years_experience", 0),
        work_auth=profile.get("work_authorization") or "unspecified",
        profile_tags=", ".join(profile.get("tags", [])),
        role=job.get("role", ""),
        role_family=job.get("role_family", ""),
        company=job.get("company", ""),
        description=(job.get("description") or "")[:1500],
        matched_tags=", ".join(matched_tags),
    )


# Re-export for callers (orchestrator + bundle generator).
__all__ = [
    "HEADLINE_SCORE_GATE",
    "TailoredHeadline",
    "tailor_headline",
    "tailor_headline_for_application",
]
