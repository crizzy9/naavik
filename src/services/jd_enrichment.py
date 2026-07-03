"""JD enrichment — replace thin descriptions with the canonical ATS posting.

Indeed listings carry truncated JDs (~1.2k chars) and email-inferred jobs
only a receipt sentence (~150 chars). Once the apply-site resolver pins the
canonical posting (Greenhouse / Lever / Ashby), the board's PUBLIC API gives
the full description — this module swaps it in and resets the scoring
breakdown so the 15-min `score_pending` cron re-scores against the real JD
(strengths / what's-missing then populate honestly).
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Job, JobSource
from services import apply_site_resolver

log = logging.getLogger(__name__)

# Below this, a description can't carry a real posting; always try to enrich.
THIN_JD_CHARS = 800
# The replacement must be substantial — never swap a real JD for a stub.
_MIN_REPLACEMENT_CHARS = 400


def html_to_text(html: str | None) -> str:
    """Board-API description HTML → plain text (Greenhouse double-escapes)."""
    if not html:
        return ""
    unescaped = html_lib.unescape(html)
    soup = BeautifulSoup(unescaped, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _apply_description(job: Job, *, text: str, html: str | None) -> None:
    job.description = text
    job.description_html = html_lib.unescape(html) if html else None
    job.description_extracted_at = datetime.now(UTC)
    job.description_extraction_model = "ats_board_api"
    # Wipe the breakdown so `score_pending` (scored_at gone) re-scores
    # against the REAL posting text.
    job.match_breakdown = {}
    job.score = 0.0
    job.score_explanation = None
    job.raw_meta = {**(job.raw_meta or {}), "jd_enriched": True}
    job.updated_at = datetime.now(UTC)


def maybe_apply_discovered_description(job: Job, resolved) -> bool:
    """Enrich straight from a discovery result (no extra network). True if applied."""
    text = (resolved.description_text or "").strip() or html_to_text(resolved.description_html)
    if len(text) < _MIN_REPLACEMENT_CHARS:
        return False
    current_len = len(job.description or "")
    if current_len >= THIN_JD_CHARS and len(text) <= current_len:
        return False
    _apply_description(job, text=text, html=resolved.description_html)
    return True


async def _fetch_posting_description(job: Job) -> tuple[str, str | None] | None:
    """(text, html) for an already-resolved job, via its board's public API."""
    org = (job.raw_meta or {}).get("ats_org")
    kind = job.apply_kind
    url = job.apply_url
    if not url or kind not in ("greenhouse", "lever", "ashby"):
        return None

    postings: list[apply_site_resolver._BoardPosting] = []
    if org:
        fetcher = {
            "greenhouse": apply_site_resolver._greenhouse_postings,
            "lever": apply_site_resolver._lever_postings,
            "ashby": apply_site_resolver._ashby_postings,
        }[kind]
        postings = await fetcher(org)
    else:
        # No org recorded (direct ATS scrape) — derive it from the URL path.
        m = re.search(r"(?:greenhouse\.io|lever\.co|ashbyhq\.com)/([^/?#]+)", url)
        if not m:
            return None
        fetcher = {
            "greenhouse": apply_site_resolver._greenhouse_postings,
            "lever": apply_site_resolver._lever_postings,
            "ashby": apply_site_resolver._ashby_postings,
        }[kind]
        postings = await fetcher(m.group(1))

    def _norm(u: str) -> str:
        return u.rstrip("/").split("?")[0].lower()

    target = _norm(url)
    for p in postings:
        if _norm(p.url) == target:
            text = (p.description_text or "").strip() or html_to_text(p.description_html)
            if len(text) >= _MIN_REPLACEMENT_CHARS:
                return text, p.description_html
            return None
    return None


async def enrich_thin_descriptions(
    session: AsyncSession,
    *,
    batch_size: int = 15,
) -> int:
    """Sweep: fetch the canonical JD for resolved-but-thin jobs.

    Targets INDEED / EMAIL jobs (chronically truncated) plus anything under
    `THIN_JD_CHARS`, once per job (`raw_meta.jd_enriched` marks attempts —
    even failed ones, so a posting that 404s doesn't get re-fetched forever).
    """
    stmt = (
        select(Job)
        .where(
            Job.deleted_at.is_(None),
            Job.apply_url.is_not(None),
            Job.apply_kind.in_(("greenhouse", "lever", "ashby")),
            Job.raw_meta.op("->>")("jd_enriched").is_(None),
            (func.length(Job.description) < THIN_JD_CHARS)
            | (Job.source.in_((JobSource.INDEED, JobSource.EMAIL))),
        )
        .limit(batch_size)
    )
    jobs = (await session.exec(stmt)).all()

    enriched = 0
    for job in jobs:
        try:
            fetched = await _fetch_posting_description(job)
        except Exception as exc:  # noqa: BLE001 — sweep must not die on one job
            log.warning("jd enrichment failed for job %s: %s", job.id, exc)
            fetched = None
        if fetched is None:
            # Mark attempted — honest no-op beats an infinite refetch loop.
            job.raw_meta = {**(job.raw_meta or {}), "jd_enriched": False}
            session.add(job)
            await session.flush()
            continue
        text, html = fetched
        current_len = len(job.description or "")
        if current_len >= THIN_JD_CHARS and len(text) <= current_len:
            job.raw_meta = {**(job.raw_meta or {}), "jd_enriched": False}
            session.add(job)
            await session.flush()
            continue
        _apply_description(job, text=text, html=html)
        session.add(job)
        await session.flush()
        enriched += 1
        log.info(
            "jd enriched job=%s company=%s %d -> %d chars",
            job.id,
            job.company,
            current_len,
            len(text),
        )
    return enriched


__all__ = [
    "THIN_JD_CHARS",
    "enrich_thin_descriptions",
    "html_to_text",
    "maybe_apply_discovered_description",
]
