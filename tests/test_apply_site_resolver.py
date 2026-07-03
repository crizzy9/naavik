"""Apply-site resolver — the real application target per job (2026-07).

Covers URL classification, slug candidates, strict title matching, per-source
resolution routing (LinkedIn offsite probe → ATS discovery → honest unknown),
board promotion, and the cron sweep's bookkeeping. All network is stubbed.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from models import ApplicationBoard, JobSource  # noqa: E402
from services import apply_site_resolver as resolver  # noqa: E402

# ── classify_apply_url ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://job-boards.greenhouse.io/gitlab/jobs/123", "greenhouse"),
        ("https://boards.greenhouse.io/acme/jobs/9", "greenhouse"),
        ("https://boards.eu.greenhouse.io/acme/jobs/9", "greenhouse"),
        ("https://jobs.lever.co/mistral/abc-def", "lever"),
        ("https://jobs.eu.lever.co/mistral/abc", "lever"),
        ("https://jobs.ashbyhq.com/perk/23477eaa", "ashby"),
        ("https://acme.wd5.myworkdayjobs.com/en-US/careers/job/x", "workday"),
        ("https://careers-acme.icims.com/jobs/123", "icims"),
        ("https://jobs.smartrecruiters.com/Acme/12345", "smartrecruiters"),
        ("https://acme.taleo.net/careersection/1/jobdetail.ftl", "taleo"),
        ("https://acme.bamboohr.com/careers/42", "bamboohr"),
        ("https://acme.recruitee.com/o/engineer", "recruitee"),
        ("https://jobs.jobvite.com/acme/job/x", "jobvite"),
        ("https://acme.breezy.hr/p/engineer", "breezy"),
        ("https://apply.workable.com/acme/j/ABC/", "workable"),
        ("https://www.linkedin.com/jobs/view/4430632291", None),
        ("https://www.indeed.com/viewjob?jk=abc", None),
        ("https://acme.com/careers/engineer", None),
        (None, None),
        ("", None),
        ("not a url", None),
        # greenhouse.io must anchor at a host boundary, not substring-match.
        ("https://notgreenhouse.iohack.com/x", None),
    ],
)
def test_classify_apply_url(url, kind):
    assert resolver.classify_apply_url(url) == kind


# ── slug candidates + title matching ─────────────────────────────────


def test_slug_candidates_shapes():
    assert resolver.slug_candidates("Perk") == ["perk"]
    assert resolver.slug_candidates("Snorkel AI") == ["snorkelai", "snorkel-ai", "snorkel"]
    assert resolver.slug_candidates("Acme, Inc.") == ["acme"]
    assert resolver.slug_candidates("") == []


def test_title_match_scores():
    assert resolver.title_match_score("Senior Software Engineer", "Senior Software Engineer") == 1.0
    # Containment (listing title ⊆ posting title) is a full match.
    assert (
        resolver.title_match_score("Senior Software Engineer", "Senior Software Engineer - Boston")
        == 1.0
    )
    assert (
        resolver.title_match_score("Senior Software Engineer", "Director of Customer Care")
        < resolver._TITLE_MATCH_THRESHOLD
    )


# ── resolve_job routing ──────────────────────────────────────────────


def _job(
    *,
    source=JobSource.LINKEDIN,
    board=ApplicationBoard.LINKEDIN,
    url="https://www.linkedin.com/jobs/view/123",
    raw_meta=None,
    company="Perk",
    role="Senior Software Engineer",
    location="Boston",
):
    return SimpleNamespace(
        id=7,
        source=source,
        board=board,
        url=url,
        raw_meta=raw_meta or {},
        company=company,
        role=role,
        location=location,
        external_id="123",
        apply_url=None,
        apply_kind=None,
        apply_resolved_at=None,
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_resolve_direct_ats_url_short_circuits():
    job = _job(
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        url="https://job-boards.greenhouse.io/gitlab/jobs/123",
    )
    out = await resolver.resolve_job(job)
    assert out.kind == "greenhouse"
    assert out.apply_url == job.url


@pytest.mark.asyncio
async def test_resolve_linkedin_easy_apply():
    job = _job()
    with patch.object(resolver, "_linkedin_is_offsite", new=AsyncMock(return_value=False)):
        out = await resolver.resolve_job(job)
    assert out.kind == "easy_apply"
    assert out.apply_url == job.url


@pytest.mark.asyncio
async def test_resolve_linkedin_offsite_discovers_ats():
    job = _job()
    discovered = resolver.ResolvedApply(
        kind="ashby",
        apply_url="https://jobs.ashbyhq.com/perk/23477eaa",
        ats_org="perk",
    )
    with (
        patch.object(resolver, "_linkedin_is_offsite", new=AsyncMock(return_value=True)),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=discovered)),
    ):
        out = await resolver.resolve_job(job)
    assert out.kind == "ashby"
    assert out.apply_url == "https://jobs.ashbyhq.com/perk/23477eaa"


@pytest.mark.asyncio
async def test_resolve_linkedin_offsite_unresolved_is_external():
    job = _job()
    with (
        patch.object(resolver, "_linkedin_is_offsite", new=AsyncMock(return_value=True)),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=None)),
    ):
        out = await resolver.resolve_job(job)
    assert out.kind == "external"
    assert out.apply_url is None


@pytest.mark.asyncio
async def test_resolve_indeed_unknown_when_no_discovery():
    job = _job(
        source=JobSource.INDEED,
        board=ApplicationBoard.INDEED,
        url="https://www.indeed.com/viewjob?jk=abc",
    )
    with patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=None)):
        out = await resolver.resolve_job(job)
    assert out.kind == "unknown"


@pytest.mark.asyncio
async def test_resolve_email_job_uses_posting_url():
    job = _job(
        source=JobSource.EMAIL,
        board=ApplicationBoard.ASHBY,
        url="manual://email/5",
        raw_meta={"posting_url": "https://jobs.ashbyhq.com/lightfield/xyz"},
    )
    out = await resolver.resolve_job(job)
    assert out.kind == "ashby"
    assert out.apply_url == "https://jobs.ashbyhq.com/lightfield/xyz"


# ── apply_resolution / board promotion ───────────────────────────────


def test_apply_resolution_promotes_board():
    job = _job()
    resolver.apply_resolution(
        job,
        resolver.ResolvedApply(
            kind="ashby", apply_url="https://jobs.ashbyhq.com/perk/x", ats_org="perk"
        ),
    )
    assert job.board == ApplicationBoard.ASHBY
    assert job.apply_kind == "ashby"
    assert job.apply_url == "https://jobs.ashbyhq.com/perk/x"
    assert job.apply_resolved_at is not None
    assert job.raw_meta["ats_org"] == "perk"


def test_apply_resolution_keeps_board_for_unknown():
    job = _job()
    resolver.apply_resolution(job, resolver.ResolvedApply(kind="unknown"))
    assert job.board == ApplicationBoard.LINKEDIN
    assert job.apply_kind == "unknown"


def test_apply_resolution_easy_apply_keeps_linkedin_board():
    job = _job()
    resolver.apply_resolution(job, resolver.ResolvedApply(kind="easy_apply", apply_url=job.url))
    assert job.board == ApplicationBoard.LINKEDIN


# ── discovery matching against stubbed board APIs ────────────────────


@pytest.mark.asyncio
async def test_discover_requires_title_above_threshold():
    postings = [
        resolver._BoardPosting(
            title="Director of Customer Care",
            url="https://jobs.ashbyhq.com/perk/1",
            location="Barcelona",
            kind="ashby",
            org="perk",
        )
    ]
    with (
        patch.object(resolver, "_greenhouse_postings", new=AsyncMock(return_value=[])),
        patch.object(resolver, "_lever_postings", new=AsyncMock(return_value=[])),
        patch.object(resolver, "_ashby_postings", new=AsyncMock(return_value=postings)),
    ):
        out = await resolver.discover_ats_posting(
            company="Perk", role="Senior Software Engineer", location="Boston"
        )
    assert out is None


@pytest.mark.asyncio
async def test_discover_region_hint_breaks_city_tie():
    """ "North America" listing + [Edinburgh, Boston] postings → Boston.

    Regression: job 72 (Perk) attached to the Edinburgh Flights posting
    because neither city token-matched "North America".
    """
    postings = [
        resolver._BoardPosting(
            title="Senior Software Engineer - Flights",
            url="https://jobs.ashbyhq.com/perk/edinburgh",
            location="Edinburgh",
            kind="ashby",
            org="perk",
        ),
        resolver._BoardPosting(
            title="Senior Software Engineer - Boston",
            url="https://jobs.ashbyhq.com/perk/boston",
            location="Boston",
            kind="ashby",
            org="perk",
        ),
    ]
    with (
        patch.object(resolver, "_greenhouse_postings", new=AsyncMock(return_value=[])),
        patch.object(resolver, "_lever_postings", new=AsyncMock(return_value=[])),
        patch.object(resolver, "_ashby_postings", new=AsyncMock(return_value=postings)),
    ):
        out = await resolver.discover_ats_posting(
            company="Perk", role="Senior Software Engineer", location="North America"
        )
    assert out is not None
    assert out.apply_url == "https://jobs.ashbyhq.com/perk/boston"


@pytest.mark.asyncio
async def test_discover_prefers_location_match():
    postings = [
        resolver._BoardPosting(
            title="Senior Software Engineer - Flights",
            url="https://jobs.ashbyhq.com/perk/edinburgh",
            location="Edinburgh",
            kind="ashby",
            org="perk",
        ),
        resolver._BoardPosting(
            title="Senior Software Engineer - Boston",
            url="https://jobs.ashbyhq.com/perk/boston",
            location="Boston",
            kind="ashby",
            org="perk",
        ),
    ]
    with (
        patch.object(resolver, "_greenhouse_postings", new=AsyncMock(return_value=[])),
        patch.object(resolver, "_lever_postings", new=AsyncMock(return_value=[])),
        patch.object(resolver, "_ashby_postings", new=AsyncMock(return_value=postings)),
    ):
        out = await resolver.discover_ats_posting(
            company="Perk", role="Senior Software Engineer", location="Boston"
        )
    assert out is not None
    assert out.apply_url == "https://jobs.ashbyhq.com/perk/boston"


# ── resolve_pending sweep ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_pending_stamps_and_counts():
    job = _job()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(all=lambda: [job]))

    resolved = resolver.ResolvedApply(kind="ashby", apply_url="https://jobs.ashbyhq.com/perk/x")
    with patch.object(resolver, "resolve_job", new=AsyncMock(return_value=resolved)):
        n = await resolver.resolve_pending(session)
    assert n == 1
    assert job.apply_kind == "ashby"
    assert job.board == ApplicationBoard.ASHBY


@pytest.mark.asyncio
async def test_resolve_pending_survives_per_job_failure():
    ok_job = _job()
    bad_job = _job()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(all=lambda: [bad_job, ok_job]))

    calls = {"n": 0}

    async def _resolve(job, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return resolver.ResolvedApply(kind="easy_apply", apply_url=job.url)

    with (
        patch.object(resolver, "resolve_job", new=AsyncMock(side_effect=_resolve)),
        patch.object(resolver.asyncio, "sleep", new=AsyncMock()),
    ):
        n = await resolver.resolve_pending(session)
    assert n == 1
    assert bad_job.apply_kind is None  # failure leaves the row untouched
    assert ok_job.apply_kind == "easy_apply"
