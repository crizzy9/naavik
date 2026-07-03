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
        apply_resolved_via=None,
        apply_resolve_attempts=0,
        apply_next_resolve_at=None,
        updated_at=None,
    )


def _sweep_exec(*, due_count: int, fresh: list, retries: list | None = None) -> AsyncMock:
    """session.exec stub for resolve_pending's count → fresh → retry selects."""
    count_result = MagicMock()
    count_result.one = lambda: due_count
    results = [count_result, MagicMock(all=lambda: fresh)]
    if due_count:
        results.append(MagicMock(all=lambda: retries or []))
    return AsyncMock(side_effect=results)


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
    session.exec = _sweep_exec(due_count=0, fresh=[job])

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
    session.exec = _sweep_exec(due_count=0, fresh=[bad_job, ok_job])

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
    # A crashed attempt is bookkept, not silently skipped — the job leaves the
    # fresh queue and walks the retry ladder instead of eating budget forever.
    assert bad_job.apply_kind == "unknown"
    assert bad_job.apply_resolved_via == "unresolved"
    assert bad_job.apply_resolve_attempts == 1
    assert bad_job.apply_next_resolve_at is not None
    assert ok_job.apply_kind == "easy_apply"


# ── Retry regime — backoff ladder, terminal states, sweep ordering ────────


def _hours_from_now(dt) -> float:
    from datetime import UTC, datetime

    return (dt - datetime.now(UTC)).total_seconds() / 3600


def test_apply_resolution_unresolved_schedules_first_retry():
    job = _job()
    resolver.apply_resolution(job, resolver.ResolvedApply(kind="external", via="unresolved"))
    assert job.apply_resolve_attempts == 1
    assert job.apply_next_resolve_at is not None
    assert 0.9 < _hours_from_now(job.apply_next_resolve_at) <= 1.01


@pytest.mark.parametrize(("prior_attempts", "expect_hours"), [(1, 4), (2, 24), (3, 72)])
def test_apply_resolution_backoff_progression(prior_attempts, expect_hours):
    job = _job()
    job.apply_resolve_attempts = prior_attempts
    resolver.apply_resolution(job, resolver.ResolvedApply(kind="external", via="unresolved"))
    assert job.apply_resolve_attempts == prior_attempts + 1
    assert expect_hours - 0.1 < _hours_from_now(job.apply_next_resolve_at) <= expect_hours + 0.01


def test_apply_resolution_exhausts_at_max_attempts():
    job = _job()
    job.apply_resolve_attempts = resolver.MAX_RESOLVE_ATTEMPTS - 1
    resolver.apply_resolution(job, resolver.ResolvedApply(kind="external", via="unresolved"))
    assert job.apply_resolve_attempts == resolver.MAX_RESOLVE_ATTEMPTS
    assert job.apply_resolved_via == "exhausted"
    assert job.apply_next_resolve_at is None
    assert job.apply_kind == "external"  # honest kind survives terminalization


def test_apply_resolution_success_clears_retry_state():
    job = _job()
    job.apply_resolve_attempts = 2
    from datetime import UTC, datetime

    job.apply_next_resolve_at = datetime.now(UTC)
    resolver.apply_resolution(
        job,
        resolver.ResolvedApply(
            kind="greenhouse",
            apply_url="https://job-boards.greenhouse.io/acme/jobs/1",
            via="linkedin_auth",
        ),
    )
    assert job.apply_next_resolve_at is None
    assert job.apply_resolved_via == "linkedin_auth"


def test_apply_resolution_manual_does_not_count_attempt_and_is_sticky():
    job = _job()
    resolver.apply_resolution(
        job,
        resolver.ResolvedApply(
            kind="workday",
            apply_url="https://acme.wd5.myworkdayjobs.com/x",
            via="manual",
        ),
        count_attempt=False,
    )
    assert job.apply_resolve_attempts == 0
    assert job.apply_resolved_via == "manual"
    # Automation never overwrites the operator's ground truth.
    resolver.apply_resolution(job, resolver.ResolvedApply(kind="external", via="unresolved"))
    assert job.apply_kind == "workday"
    assert job.apply_resolved_via == "manual"
    assert job.apply_resolve_attempts == 0


def test_note_failed_attempt_terminalizes_at_max():
    job = _job()
    job.apply_kind = "external"
    job.apply_resolved_via = "unresolved"
    job.apply_resolve_attempts = resolver.MAX_RESOLVE_ATTEMPTS - 1
    resolver.note_failed_attempt(job)
    assert job.apply_resolved_via == "exhausted"
    assert job.apply_next_resolve_at is None


@pytest.mark.asyncio
async def test_resolve_pending_fresh_before_due_retries():
    """Fresh rows get the batch minus the retry reserve; retries fill the rest."""
    fresh = [_job() for _ in range(3)]
    retries = [_job() for _ in range(2)]
    for r_job in retries:
        r_job.apply_kind = "external"
        r_job.apply_resolved_via = "unresolved"
        r_job.apply_resolve_attempts = 1
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = _sweep_exec(due_count=2, fresh=fresh, retries=retries)

    seen: list = []

    async def _resolve(job, **kwargs):
        seen.append(job)
        return resolver.ResolvedApply(kind="easy_apply", apply_url="https://x")

    with (
        patch.object(resolver, "resolve_job", new=AsyncMock(side_effect=_resolve)),
        patch.object(resolver.asyncio, "sleep", new=AsyncMock()),
        patch(
            "services.application_service.resync_draft_apply_target",
            new=AsyncMock(return_value=0),
        ),
    ):
        n = await resolver.resolve_pending(session)
    assert n == 5
    assert seen[:3] == fresh  # fresh first
    assert seen[3:] == retries  # then due retries
    for r_job in retries:
        assert r_job.apply_kind == "easy_apply"
        assert r_job.apply_next_resolve_at is None


@pytest.mark.asyncio
async def test_resolver_stats_counts():
    session = MagicMock()
    via_result = MagicMock()
    via_result.all = lambda: [("direct", 3), ("linkedin_auth", 1), (None, 2), ("exhausted", 1)]
    counts = iter([2, 1, 4, 5])

    def _count_result():
        value = next(counts)
        m = MagicMock()
        m.one = lambda: value
        return m

    session.exec = AsyncMock(
        side_effect=[via_result, _count_result(), _count_result(), _count_result(), _count_result()]
    )
    stats = await resolver.resolver_stats(session, user_id=1)
    assert stats["by_via"] == {"direct": 3, "linkedin_auth": 1, "never": 2, "exhausted": 1}
    assert stats["pending"] == 2
    assert stats["retry_due"] == 1
    assert stats["retry_scheduled"] == 4
    assert stats["exhausted"] == 1
    assert stats["resolved"] == 5


# ── URL normalization — wrapper unwrap + redirect walking ─────────────────


@pytest.mark.parametrize(
    ("wrapped", "expected"),
    [
        (
            "https://click.appcast.io/track/abc?url=https%3A%2F%2Facme.wd5.myworkdayjobs.com%2Fj%2F1",
            "https://acme.wd5.myworkdayjobs.com/j/1",
        ),
        (
            "https://www.linkedin.com/jobs/view/externalApply/123?url=https%3A%2F%2Fjobs.lever.co%2Facme%2Fx",
            "https://jobs.lever.co/acme/x",
        ),
        # Nested wrappers peel layer by layer (bounded).
        (
            "https://t.example.com/r?dest=https%3A%2F%2Fclick.appcast.io%2Ft%3Furl%3Dhttps%253A%252F%252Fjobs.ashbyhq.com%252Facme%252F1",
            "https://jobs.ashbyhq.com/acme/1",
        ),
        # Plain URLs (no URL-valued wrapper param) pass through untouched.
        (
            "https://www.linkedin.com/jobs/view/4434079004",
            "https://www.linkedin.com/jobs/view/4434079004",
        ),
        (
            "https://acme.com/careers?utm_source=linkedin&ref=jobs",
            "https://acme.com/careers?utm_source=linkedin&ref=jobs",
        ),
    ],
)
def test_unwrap_tracking_url_variants(wrapped, expected):
    assert resolver.unwrap_tracking_url(wrapped) == expected


@pytest.mark.asyncio
async def test_normalize_apply_url_early_exit_no_network_for_known_ats():
    probe = AsyncMock(side_effect=AssertionError("network probe must not run"))
    with patch.object(resolver, "_redirect_probe", new=probe):
        final, kind = await resolver.normalize_apply_url(
            "https://click.appcast.io/t?url=https%3A%2F%2Fjob-boards.greenhouse.io%2Facme%2Fjobs%2F1"
        )
    assert final == "https://job-boards.greenhouse.io/acme/jobs/1"
    assert kind == "greenhouse"


@pytest.mark.asyncio
async def test_normalize_apply_url_follows_redirect_chain_to_workday():
    hops = {
        "https://careers.acme.com/j/1": "https://careers.acme.com/redirect/1",
        "https://careers.acme.com/redirect/1": "https://acme.wd5.myworkdayjobs.com/en-US/j/1",
    }

    async def _probe(client, url, headers):
        location = hops.get(url)
        if location is None:
            return MagicMock(status_code=200, headers={})
        return MagicMock(status_code=302, headers={"location": location})

    with (
        patch.object(resolver, "is_safe_destination", return_value=(True, "")),
        patch.object(resolver, "_redirect_probe", new=_probe),
    ):
        final, kind = await resolver.normalize_apply_url("https://careers.acme.com/j/1")
    assert final == "https://acme.wd5.myworkdayjobs.com/en-US/j/1"
    assert kind == "workday"


@pytest.mark.asyncio
async def test_normalize_apply_url_ssrf_blocked_hop_stops():
    with (
        patch.object(resolver, "is_safe_destination", return_value=(False, "private ip")),
        patch.object(
            resolver,
            "_redirect_probe",
            new=AsyncMock(side_effect=AssertionError("must not probe unsafe URL")),
        ),
    ):
        final, kind = await resolver.normalize_apply_url("https://internal.local/j/1")
    assert final == "https://internal.local/j/1"
    assert kind is None


@pytest.mark.asyncio
async def test_resolve_linkedin_auth_company_site_normalizes_to_ats():
    """A Tier-B careers-page URL that redirects onto Workday upgrades the kind."""
    from services import linkedin_resolver

    job = _job()
    guest = linkedin_resolver.GuestDetail(
        is_offsite=True, company_slug=None, description_html=None, description_text=None
    )
    auth_hit = resolver.ResolvedApply(
        kind="company_site", apply_url="https://careers.acme.com/j/1", via="linkedin_auth"
    )
    with (
        patch.object(resolver, "_fetch_guest_detail", new=AsyncMock(return_value=guest)),
        patch.object(resolver, "discover_ats_posting", new=AsyncMock(return_value=None)),
        patch.object(linkedin_resolver, "resolve_via_auth", new=AsyncMock(return_value=auth_hit)),
        patch.object(
            resolver,
            "normalize_apply_url",
            new=AsyncMock(return_value=("https://acme.wd5.myworkdayjobs.com/j/1", "workday")),
        ),
    ):
        out = await resolver.resolve_job(job, auth=object())
    assert out.kind == "workday"
    assert out.apply_url == "https://acme.wd5.myworkdayjobs.com/j/1"
    assert out.original_apply_url == "https://careers.acme.com/j/1"
    assert out.via == "linkedin_auth"
