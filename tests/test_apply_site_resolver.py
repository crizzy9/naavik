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


def _guest(*, is_offsite, company_slug=None, description_text=None, posting_title=None):
    from services import linkedin_resolver

    return linkedin_resolver.GuestDetail(
        is_offsite=is_offsite,
        company_slug=company_slug,
        description_html=None,
        description_text=description_text,
        posting_title=posting_title,
    )


@pytest.mark.asyncio
async def test_resolve_linkedin_uses_full_guest_title_for_discovery():
    """The guest page's full title ("... (GO)") is what discovery matches on,
    not the scraper's truncated role."""
    job = _job(company="Catapult", role="Senior Software Engineer")
    seen_roles: list[str] = []

    async def _discover(*, company, role, location, extra_slugs, _cache):
        seen_roles.append(role)
        return resolver.ResolvedApply(
            kind="greenhouse",
            apply_url="https://job-boards.greenhouse.io/catapultsports/jobs/7960837",
            ats_org="catapultsports",
            via="ats_discovery",
        )

    with (
        patch.object(
            resolver,
            "_fetch_guest_detail",
            new=AsyncMock(
                return_value=_guest(
                    is_offsite=True,
                    company_slug="catapultsports",
                    posting_title="Senior Software Engineer (GO)",
                )
            ),
        ),
        patch.object(resolver, "discover_ats_posting", new=_discover),
    ):
        out = await resolver.resolve_job(job)
    assert seen_roles == ["Senior Software Engineer (GO)"]
    assert out.apply_url.endswith("/7960837")


@pytest.mark.asyncio
async def test_resolve_linkedin_easy_apply():
    job = _job()
    with patch.object(
        resolver, "_fetch_guest_detail", new=AsyncMock(return_value=_guest(is_offsite=False))
    ):
        out = await resolver.resolve_job(job)
    assert out.kind == "easy_apply"
    assert out.apply_url == job.url
    assert out.via == "linkedin_guest"


@pytest.mark.asyncio
async def test_resolve_linkedin_offsite_discovers_ats():
    job = _job()
    discovered = resolver.ResolvedApply(
        kind="ashby",
        apply_url="https://jobs.ashbyhq.com/perk/23477eaa",
        ats_org="perk",
        via="ats_discovery",
    )
    with (
        patch.object(
            resolver, "_fetch_guest_detail", new=AsyncMock(return_value=_guest(is_offsite=True))
        ),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=discovered)),
    ):
        out = await resolver.resolve_job(job)
    assert out.kind == "ashby"
    assert out.apply_url == "https://jobs.ashbyhq.com/perk/23477eaa"


@pytest.mark.asyncio
async def test_resolve_linkedin_guest_slug_wins_and_marks_provenance():
    """The guest company slug feeds discovery and stamps an authoritative via."""
    job = _job(company="Catapult")
    discovered = resolver.ResolvedApply(
        kind="greenhouse",
        apply_url="https://job-boards.greenhouse.io/catapultsports/jobs/7960837",
        ats_org="catapultsports",
        via="ats_discovery",
    )
    with (
        patch.object(
            resolver,
            "_fetch_guest_detail",
            new=AsyncMock(return_value=_guest(is_offsite=True, company_slug="catapultsports")),
        ),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=discovered)),
    ):
        out = await resolver.resolve_job(job)
    assert out.kind == "greenhouse"
    assert out.ats_org == "catapultsports"
    assert out.via == "linkedin_guest_slug"


@pytest.mark.asyncio
async def test_resolve_linkedin_offsite_unresolved_is_external():
    job = _job()
    with (
        patch.object(
            resolver, "_fetch_guest_detail", new=AsyncMock(return_value=_guest(is_offsite=True))
        ),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=None)),
    ):
        # auth=None (default) → Tier B skipped, honest external.
        out = await resolver.resolve_job(job)
    assert out.kind == "external"
    assert out.apply_url is None
    assert out.via == "unresolved"


@pytest.mark.asyncio
async def test_resolve_linkedin_ambiguous_discovery_prefers_auth():
    """Two near-identical postings tie → defer to the authoritative auth path."""
    from services import linkedin_resolver

    job = _job(company="Catapult")
    auth = linkedin_resolver.AuthContext(remaining=1)
    ambiguous = resolver.ResolvedApply(
        kind="greenhouse",
        apply_url="https://job-boards.greenhouse.io/catapultsports/jobs/7979941",
        ats_org="catapultsports",
        via="ats_discovery",
        ambiguous=True,
    )
    authed = resolver.ResolvedApply(
        kind="greenhouse",
        apply_url="https://job-boards.greenhouse.io/catapultsports/jobs/7960837",
        ats_org="catapultsports",
        via="linkedin_auth",
    )
    with (
        patch.object(
            resolver,
            "_fetch_guest_detail",
            new=AsyncMock(return_value=_guest(is_offsite=True, company_slug="catapultsports")),
        ),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=ambiguous)),
        patch.object(linkedin_resolver, "resolve_via_auth", new=AsyncMock(return_value=authed)),
    ):
        out = await resolver.resolve_job(job, auth=auth)
    assert out.via == "linkedin_auth"
    assert out.apply_url.endswith("/7960837")


@pytest.mark.asyncio
async def test_resolve_linkedin_ambiguous_discovery_best_effort_without_auth():
    """No auth → keep the ambiguous Tier-A guess (right company + board)."""
    job = _job(company="Catapult")
    ambiguous = resolver.ResolvedApply(
        kind="greenhouse",
        apply_url="https://job-boards.greenhouse.io/catapultsports/jobs/7979941",
        ats_org="catapultsports",
        via="ats_discovery",
        ambiguous=True,
    )
    with (
        patch.object(
            resolver,
            "_fetch_guest_detail",
            new=AsyncMock(return_value=_guest(is_offsite=True, company_slug="catapultsports")),
        ),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=ambiguous)),
    ):
        out = await resolver.resolve_job(job, auth=None)
    assert out.kind == "greenhouse"
    assert out.via == "linkedin_guest_slug"  # slug still drove the discovery


@pytest.mark.asyncio
async def test_resolve_linkedin_auth_fallback_when_discovery_misses():
    """Discovery misses → the authenticated resolver supplies the offsite URL."""
    from services import linkedin_resolver

    job = _job(company="Weirdco")
    auth = linkedin_resolver.AuthContext(remaining=1)
    authed = resolver.ResolvedApply(
        kind="greenhouse",
        apply_url="https://job-boards.greenhouse.io/weirdco/jobs/42",
        ats_org="weirdco",
        via="linkedin_auth",
    )
    with (
        patch.object(
            resolver, "_fetch_guest_detail", new=AsyncMock(return_value=_guest(is_offsite=True))
        ),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=None)),
        patch.object(linkedin_resolver, "resolve_via_auth", new=AsyncMock(return_value=authed)),
    ):
        out = await resolver.resolve_job(job, auth=auth)
    assert out.kind == "greenhouse"
    assert out.via == "linkedin_auth"


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
            kind="ashby",
            apply_url="https://jobs.ashbyhq.com/perk/x",
            ats_org="perk",
            via="linkedin_guest_slug",
        ),
    )
    assert job.board == ApplicationBoard.ASHBY
    assert job.apply_kind == "ashby"
    assert job.apply_url == "https://jobs.ashbyhq.com/perk/x"
    assert job.apply_resolved_at is not None
    assert job.apply_resolved_via == "linkedin_guest_slug"
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
async def test_discover_extra_slug_tried_before_name_guess():
    """The guest company slug ("catapultsports") resolves what the display
    name ("Catapult" → "catapult") never could."""
    hit = resolver._BoardPosting(
        title="Senior Software Engineer (GO)",
        url="https://job-boards.greenhouse.io/catapultsports/jobs/7960837",
        location="Boston, MA",
        kind="greenhouse",
        org="catapultsports",
    )

    async def _gh(slug):
        # The board only exists under the LinkedIn slug, not the name guess.
        return [hit] if slug == "catapultsports" else []

    with (
        patch.object(resolver, "_greenhouse_postings", new=AsyncMock(side_effect=_gh)),
        patch.object(resolver, "_lever_postings", new=AsyncMock(return_value=[])),
        patch.object(resolver, "_ashby_postings", new=AsyncMock(return_value=[])),
    ):
        out = await resolver.discover_ats_posting(
            company="Catapult",
            role="Senior Software Engineer",
            location="Boston",
            extra_slugs=["catapultsports"],
        )
    assert out is not None
    assert out.kind == "greenhouse"
    assert out.ats_org == "catapultsports"
    assert out.apply_url == "https://job-boards.greenhouse.io/catapultsports/jobs/7960837"
    assert out.via == "ats_discovery"


@pytest.mark.asyncio
async def test_discover_sanitizes_bad_extra_slug():
    """A malformed guest slug is dropped, not passed to the board API."""
    seen: list[str] = []

    async def _gh(slug):
        seen.append(slug)
        return []

    with (
        patch.object(resolver, "_greenhouse_postings", new=AsyncMock(side_effect=_gh)),
        patch.object(resolver, "_lever_postings", new=AsyncMock(return_value=[])),
        patch.object(resolver, "_ashby_postings", new=AsyncMock(return_value=[])),
    ):
        await resolver.discover_ats_posting(
            company="Perk", role="x", extra_slugs=["evil.com/../v0"]
        )
    assert "evil.com/../v0" not in seen  # sanitized out


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
    with (
        patch.object(resolver, "resolve_job", new=AsyncMock(return_value=resolved)),
        patch(
            "services.application_service.resync_draft_apply_target",
            new=AsyncMock(return_value=0),
        ),
    ):
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
        patch(
            "services.application_service.resync_draft_apply_target",
            new=AsyncMock(return_value=0),
        ),
    ):
        n = await resolver.resolve_pending(session)
    assert n == 1
    assert bad_job.apply_kind is None  # failure leaves the row untouched
    assert ok_job.apply_kind == "easy_apply"
