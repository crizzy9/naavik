"""HTML -> structured Job-field enrichment.

Per docs/design/JOB_EXTRACTION.md (graduated from plan 30 / 0.2.0.08).

Consumes a scraper-emitted `RawJob` (with `description_html` filled), runs
LLM structured-output extraction, and returns a new `RawJob` with:

- `description_text` from the LLM plain-text body
- `*_hint` enum trio (remote_policy, visa_restrictions, seniority_level)
  overwritten with the LLM authoritative reads
- `raw_meta` merged with `skills_required[]`, `criteria[]`, `tags[]`,
  `salary_min/max`, `description_extraction_model` for downstream
  `_create_payload(raw)` lift into Job columns

Wraps every LLM call via `services.llm_tracker.tracked_call` so ApiUsage
rows persist for the daily cost cap.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup
from sqlmodel.ext.asyncio.session import AsyncSession

from llm.base import LLMProvider, LLMProviderError
from llm.prompts.extract_job import PROMPT, JobExtraction
from models import Settings
from scraper.types import RawJob
from services import llm_tracker

log = logging.getLogger(__name__)

# Conservative HTML strip — see plan 30 § D.4.
# We KEEP <aside> (LinkedIn right-rail "About this job"), <main>, <article>.
_DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "img",
    "video",
    "audio",
    "canvas",
    "embed",
    "object",
    "form",
    "input",
    "button",
    "select",
    "textarea",
    "nav",
    "footer",
    "header",
)
_HTML_INPUT_CAP = 30_000  # post-strip cap; rarely trips after _strip_boilerplate


class ExtractionSkipped(Exception):
    """Raised in strict mode when RawJob has neither description_html nor
    description_text. Default path swallows + marks `raw_meta`."""


def _strip_boilerplate(html: str) -> str:
    """Drop nav/script/style/etc. + collapse whitespace.

    Returns plain text suitable for the extraction prompt.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in _DROP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


def _parse_posted_at(raw: str | None) -> datetime | None:
    """Permissive ISO 8601 parse; returns None on failure."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _mark_skipped(raw_job: RawJob, *, reason: str) -> RawJob:
    """Append `extraction_skipped` marker to raw_meta; return new RawJob otherwise unchanged."""
    raw_meta = dict(raw_job.raw_meta)
    raw_meta["extraction_skipped"] = reason
    return raw_job.model_copy(update={"raw_meta": raw_meta})


def _merge_extraction_into_raw_job(
    *,
    raw_job: RawJob,
    extraction: JobExtraction,
    model_name: str,
) -> RawJob:
    """Build a new RawJob from the seed + LLM extraction.

    LLM-authoritative fields (description_text, *_hint trio, location, posted_at)
    OVERWRITE the scraper-supplied values. Scraper-owned identity fields
    (source, external_id, source_url, board, url_type) are preserved verbatim.
    Scorer-required arrays (skills_required, criteria, tags) + salary bounds
    are merged into raw_meta for transport to _create_payload.
    """
    raw_meta = dict(raw_job.raw_meta)
    raw_meta["skills_required"] = extraction.skills_required
    raw_meta["criteria"] = extraction.criteria
    raw_meta["tags"] = extraction.tags
    if extraction.salary_min is not None:
        raw_meta["salary_min"] = extraction.salary_min
    if extraction.salary_max is not None:
        raw_meta["salary_max"] = extraction.salary_max
    if extraction.salary_raw:
        raw_meta.setdefault("salary_raw", extraction.salary_raw)
    raw_meta["description_extraction_model"] = model_name

    return RawJob(
        # Scraper-owned identity (preserved verbatim)
        source=raw_job.source,
        external_id=raw_job.external_id,
        source_url=raw_job.source_url,
        board=raw_job.board,
        url_type=raw_job.url_type,
        # User-visible — LLM may normalize over scraper's reads
        company_name=extraction.company_name or raw_job.company_name,
        position_title=extraction.position_title or raw_job.position_title,
        location_raw=extraction.location_raw or raw_job.location_raw,
        description_html=raw_job.description_html,
        description_text=extraction.description,
        # Time fields — LLM may overwrite from JD body
        posted_at_text=extraction.posted_at_text or raw_job.posted_at_text,
        posted_at=_parse_posted_at(extraction.posted_at) or raw_job.posted_at,
        # Salary raw stays available (preserved for diagnostics)
        salary_raw=extraction.salary_raw or raw_job.salary_raw,
        # *_hint trio — LLM authoritative read OVERWRITES scraper guess
        remote_policy_hint=extraction.remote_policy,
        visa_restriction_hint=extraction.visa_restrictions,
        seniority_level_hint=extraction.seniority_level,
        # Meta carries scorer-required arrays + model attribution
        raw_meta=raw_meta,
    )


async def enrich_raw_job(
    session: AsyncSession | None,
    *,
    user_id: int,
    provider: LLMProvider,
    raw_job: RawJob,
    settings: Settings | None = None,  # reserved for 0.2.0.13 per-source tuning
    strict: bool = False,
) -> RawJob:
    """Per plan 30 § D.3. Returns a new RawJob; never mutates the input.

    Default path (`strict=False`) survives per-listing extraction failures by
    returning the original raw_job with a `raw_meta["extraction_skipped"]`
    marker so scrapers can continue iterating per `SCRAPER_BASE.md § H.1`
    Tier 1 errors. `strict=True` re-raises for the `+ Add by URL` route.
    """
    # Pick the best input: prefer HTML for the boilerplate strip; fall back to
    # description_text if scraper already pre-stripped; else mark skipped.
    if raw_job.description_html:
        body_text = _strip_boilerplate(raw_job.description_html)
    elif raw_job.description_text:
        body_text = raw_job.description_text
    else:
        if strict:
            raise ExtractionSkipped(
                f"RawJob has no description_html or description_text "
                f"(source={raw_job.source.value}, external_id={raw_job.external_id})"
            )
        log.warning(
            "extraction_skipped no_html_or_text source=%s external_id=%s",
            raw_job.source.value,
            raw_job.external_id,
        )
        return _mark_skipped(raw_job, reason="no_html_or_text")

    body_text = body_text[:_HTML_INPUT_CAP]
    rendered = PROMPT.format(html=body_text)

    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="extract_job",
            prompt=rendered,
            schema=JobExtraction,
            max_tokens=2048,
        )
    except LLMProviderError as exc:
        log.exception(
            "extract_job failed source=%s external_id=%s kind=%s",
            raw_job.source.value,
            raw_job.external_id,
            exc.kind,
        )
        if strict:
            raise
        return _mark_skipped(raw_job, reason=f"llm_failure:{exc.kind}")

    try:
        extraction = JobExtraction.model_validate(result.value)
    except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError + edge cases
        log.exception(
            "extract_job schema_invalid source=%s external_id=%s",
            raw_job.source.value,
            raw_job.external_id,
        )
        if strict:
            raise LLMProviderError(
                f"extract_job schema validation failed: {exc}",
                kind="schema_validation",
            ) from exc
        return _mark_skipped(raw_job, reason="schema_invalid")

    return _merge_extraction_into_raw_job(
        raw_job=raw_job,
        extraction=extraction,
        model_name=provider.model_name,
    )


__all__ = ["ExtractionSkipped", "enrich_raw_job"]
