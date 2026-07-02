"""Job-search preferences — expansion refresh, derivation, title matching.

Per docs/design/JOB_SEARCH_PREFERENCES.md. The profile-level preferences
(`Profile.target_titles` / `title_expansions` / `target_cities` /
`remote_ok`) are the primary input for every scraper; the legacy
per-source `Settings.linkedin_keywords`-style fields survive only as
explicit overrides (empty = derived from profile).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError, get_provider
from llm.prompts.expand_titles import TitleExpansions, render_prompt
from models import Experience, Profile, Settings
from models.enums import JobSource
from services import llm_tracker
from services.geo import normalize_city

log = logging.getLogger(__name__)

_ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5"}


def _norm_title(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    tokens = [_ROMAN.get(t, t) for t in text.split()]
    return " ".join(tokens)


def expanded_title_set(profile: Profile) -> set[str]:
    """All normalized title variants the profile targets (incl. raw titles).

    Reads via getattr — legacy fixtures (and rows loaded before migration
    0027) may lack the preference attributes entirely.
    """
    out: set[str] = set()
    expansions = getattr(profile, "title_expansions", None) or {}
    for title in getattr(profile, "target_titles", None) or []:
        out.add(_norm_title(title))
        entry = expansions.get(title) or {}
        for variant in entry.get("expanded") or []:
            out.add(_norm_title(variant))
    out.discard("")
    return out


def title_matches(job_role: str | None, profile: Profile) -> bool:
    """True when a job title matches any targeted title variant.

    Normalized containment in either direction — "Senior Software Engineer,
    Payments" matches the "senior software engineer" variant. With no
    preferences configured, everything matches (never drop data).
    """
    variants = expanded_title_set(profile)
    if not variants:
        return True
    role = _norm_title(job_role or "")
    if not role:
        return False
    return any(v in role or role in v for v in variants)


async def refresh_title_expansions(
    session: AsyncSession,
    *,
    profile: Profile,
    settings: Settings,
    force: bool = False,
) -> bool:
    """(Re)generate LLM expansions for titles that lack one.

    Graceful degrade: with no LLM provider configured (or a failed call)
    the expansion is just the raw title with model="none" — search still
    works, matching is exact-title only. Returns True when anything changed.
    """
    titles = [t for t in (profile.target_titles or []) if t.strip()]
    existing = dict(profile.title_expansions or {})

    pending = [
        t
        for t in titles
        if force or not (existing.get(t) or {}).get("expanded") or existing[t].get("model") == "none"
    ]
    # Prune expansions for removed titles.
    pruned = {k: v for k, v in existing.items() if k in titles}
    changed = pruned != existing

    if pending:
        generated_at = datetime.now(UTC).isoformat()
        try:
            provider = get_provider(settings)
            result = await llm_tracker.tracked_call(
                session=session,
                user_id=settings.user_id,
                provider=provider,
                method="structured",
                prompt_name="expand_titles",
                prompt=render_prompt(titles=pending, headline=profile.headline),
                schema=TitleExpansions,
                max_tokens=1024,
            )
            parsed = TitleExpansions.model_validate(result.value)
            by_title = {e.title: e.expanded for e in parsed.expansions}
            for title in pending:
                expanded = by_title.get(title) or [title]
                if title.lower() not in {v.lower() for v in expanded}:
                    expanded = [title, *expanded]
                pruned[title] = {
                    "expanded": expanded,
                    "generated_at": generated_at,
                    "model": provider.model_name,
                }
        except LLMProviderError as exc:
            log.info("title expansion degraded to raw titles: %s", exc)
            for title in pending:
                pruned[title] = {
                    "expanded": [title],
                    "generated_at": generated_at,
                    "model": "none",
                }
        changed = True

    if changed:
        profile.title_expansions = pruned
        profile.updated_at = datetime.now(UTC)
        session.add(profile)
        await session.flush()
    return changed


def derive_source_inputs(
    profile: Profile | None,
    settings: Settings,
    source: JobSource,
) -> tuple[list[str], str | None, bool]:
    """(keywords, location, is_override) for a keyword-driven source.

    Override precedence: a non-empty per-source Settings value wins;
    otherwise derive from profile preferences — raw target titles as
    keywords, first target city as location (no location when remote-ok
    with no city configured).
    """
    if source is JobSource.LINKEDIN:
        override_kw = list(settings.linkedin_keywords or [])
        override_loc = settings.linkedin_location
    elif source is JobSource.INDEED:
        override_kw = list(settings.indeed_keywords or [])
        override_loc = settings.indeed_location
    else:
        return [], None, False

    if override_kw:
        return override_kw, override_loc, True

    titles = [t for t in (getattr(profile, "target_titles", None) or []) if t.strip()]
    cities = [c for c in (getattr(profile, "target_cities", None) or []) if c.strip()]
    location = override_loc or (cities[0] if cities else None)
    return titles, location, False


async def prefill_search_prefs(session: AsyncSession, *, profile: Profile) -> bool:
    """Seed empty preferences from the parsed resume.

    Called after resume extraction persists the profile: current title from
    the most-recent experience (fallback: headline), city from
    `Profile.location` when it maps to a known US city. Never overwrites a
    non-empty preference. Returns True when anything was seeded.
    """
    changed = False

    if not profile.target_titles:
        title: str | None = None
        if profile.id is not None:
            stmt = (
                select(Experience)
                .where(Experience.profile_id == profile.id, Experience.deleted_at.is_(None))
                .order_by(Experience.start_date.desc())
                .limit(1)
            )
            latest = (await session.exec(stmt)).first()
            title = getattr(latest, "title", None)
        if not title and profile.headline:
            # Headlines commonly read "Senior Software Engineer at Intuit".
            title = re.split(r"\s+(?:at|@)\s+", profile.headline, maxsplit=1)[0].strip()
        if title:
            profile.target_titles = [title]
            changed = True

    if not profile.target_cities and profile.location:
        city = normalize_city(profile.location)
        if city:
            profile.target_cities = [city]
            changed = True

    if changed:
        profile.updated_at = datetime.now(UTC)
        session.add(profile)
        await session.flush()
    return changed
