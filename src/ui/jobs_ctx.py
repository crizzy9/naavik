"""Context-builder for the read-only Job detail page (plan 36 § A · D.1).

Distinct from `discover_review_ctx` (the tailor + apply workspace at
`/discover/{job_id}`). This module surfaces a single Job in isolation —
scrape metadata, duplicate-of pointer, source badge, action rail —
regardless of whether an Application has been drafted for it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from models import Job, JobScrapeRun
from models.enums import JobScrapeStatus

_SOURCE_TONE = {
    "linkedin": "indigo",
    "workday": "cyan",
    "greenhouse": "emerald",
    "lever": "indigo",
    "ashby": "cyan",
    "indeed": "amber",
    "company_direct": "emerald",
    "rsshub": "slate",
    "n8n_legacy": "amber",
    "manual": "slate",
}


def _human_when(when: datetime | None) -> str:
    """Render a datetime as "Nh ago" / "Nd ago", or "—" if missing."""
    if when is None:
        return "—"
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - when
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _salary_range(job: Job) -> str | None:
    if job.salary_min and job.salary_max:
        equity = f" + {job.equity_pct}%" if job.equity_pct else ""
        return f"${job.salary_min // 1000}-{job.salary_max // 1000}k{equity}"
    return None


def _scrape_status_tone(status: JobScrapeStatus | None) -> str:
    if status is None:
        return "slate"
    return {
        JobScrapeStatus.SUCCESS: "emerald",
        JobScrapeStatus.PARTIAL: "amber",
        JobScrapeStatus.FAILED: "rose",
        JobScrapeStatus.TIMED_OUT: "rose",
        JobScrapeStatus.RUNNING: "indigo",
    }.get(status, "slate")


async def build_job_detail_ctx(
    session: AsyncSession,
    *,
    job: Job,
    scrape_run: JobScrapeRun | None = None,
) -> dict[str, object]:
    """Project a SQLModel Job + its last JobScrapeRun into a template dict.

    The session is threaded for future enrichment (related applications,
    duplicate-canonical resolution). Today it's unused — kept on the
    signature for forward compatibility with `0.2.0.12` work that wants
    notification preview state next to the Job.
    """
    initial = (job.company or "?")[:1].upper()
    source_value = job.source.value if hasattr(job.source, "value") else str(job.source)
    tags_normalized = [t.value if hasattr(t, "value") else str(t) for t in (job.tags or [])]

    return {
        "job": {
            "id": job.id,
            "company": job.company,
            "company_initial": initial,
            "role": job.role,
            "team": job.team,
            "location": job.location,
            "remote_policy": job.remote_policy.value
            if hasattr(job.remote_policy, "value")
            else str(job.remote_policy),
            "seniority_level": (
                job.seniority_level.value
                if job.seniority_level and hasattr(job.seniority_level, "value")
                else None
            ),
            "url": job.url,
            "url_type": job.url_type,
            "source": source_value,
            "source_tone": _SOURCE_TONE.get(source_value, "slate"),
            "board": job.board.value if hasattr(job.board, "value") else str(job.board),
            "external_id": job.external_id,
            "visa_restrictions": (
                job.visa_restrictions.value
                if hasattr(job.visa_restrictions, "value")
                else str(job.visa_restrictions)
            ),
            "queue_state": (
                job.queue_state.value if hasattr(job.queue_state, "value") else str(job.queue_state)
            ),
            "score": int(round(job.score * 100)),
            "unscored": job.score == 0.0,
            "score_explanation": job.score_explanation,
            "salary_range": _salary_range(job),
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "description": job.description,
            "criteria": job.criteria or [],
            "skills_required": job.skills_required or [],
            "tags": tags_normalized,
            "found_at_human": _human_when(job.found_at),
            "posted_at_human": _human_when(job.posted_at),
            "posted_at_text": job.posted_at_text,
            "description_extracted_at_human": _human_when(job.description_extracted_at),
            "description_extraction_model": job.description_extraction_model,
            "duplicate_of_id": job.duplicate_of_id,
            "warm_intro_contact_id": job.warm_intro_contact_id,
            "match_breakdown": job.match_breakdown or {},
        },
        "scrape_run": (
            {
                "id": scrape_run.id,
                "source": (
                    scrape_run.source.value
                    if hasattr(scrape_run.source, "value")
                    else str(scrape_run.source)
                ),
                "status": (
                    scrape_run.status.value
                    if hasattr(scrape_run.status, "value")
                    else str(scrape_run.status)
                ),
                "status_tone": _scrape_status_tone(scrape_run.status),
                "started_at_human": _human_when(scrape_run.started_at),
                "finished_at_human": _human_when(scrape_run.finished_at),
                "duration_ms": scrape_run.duration_ms,
                "requests_made": scrape_run.requests_made,
                "listings_returned": scrape_run.listings_returned,
                "new_jobs": scrape_run.new_jobs,
                "updated_jobs": scrape_run.updated_jobs,
                "errors": list(scrape_run.errors or []),
            }
            if scrape_run
            else None
        ),
    }
