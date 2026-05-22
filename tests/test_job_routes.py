"""Integration tests for the Discover / Job-detail routes (plan 36).

Covers the Wave 1-4 surface:

- Discover ctx swaps from `db.sample_data.discover_queue()` to
  `job_service.list_jobs` when a session + user_id are present.
- Filter querystring round-trips parse cleanly + invalid enum values 422.
- `/_fragments/discover/queue?...` returns just the queue grid (no chrome).
- Filter-with-zero-results renders the `search-x` empty state.
- `include_duplicates=1` toggle plumbs through to JobFilter.
- `/jobs/{id}` returns 200 for owner, 404 for non-owner (IDOR mitigation).
- Score-zero Job renders the "unscored" placeholder, not the 0-circle.
- `parse_filters_from_query` honors the legacy `?filter=saved` synonym.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from models.enums import (
    ApplicationBoard,
    JobQueueState,
    JobScrapeStatus,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
    VisaRestriction,
)
from ui import discover_ctx as dctx

pytestmark = pytest.mark.uses_sample_data_shims

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def _fake_job(
    *,
    jid: int = 200,
    user_id: int = 1,
    score: float = 0.85,
    company: str = "Anthropic",
    role: str = "Senior ML Engineer",
    source: JobSource = JobSource.LINKEDIN,
    external_id: str = "ln-200-zzz",
    queue_state: JobQueueState = JobQueueState.UNSWIPED,
    duplicate_of_id: int | None = None,
    description: str = "Frontier model work.",
    last_scrape_run_id: int | None = None,
    deleted_at: datetime | None = None,
    visa: VisaRestriction = VisaRestriction.SPONSORSHIP_AVAILABLE,
    tags: list[str] | None = None,
    **kw: Any,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    base = {
        "id": jid,
        "user_id": user_id,
        "source": source,
        "external_id": external_id,
        "board": ApplicationBoard.LINKEDIN,
        "url": f"https://linkedin.com/jobs/view/{jid}",
        "url_type": "ats",
        "company": company,
        "role": role,
        "team": None,
        "location": "Remote · USA",
        "remote_policy": RemotePolicy.REMOTE,
        "seniority_level": SeniorityLevel.SENIOR,
        "posted_at": None,
        "posted_at_text": None,
        "found_at": now,
        "description": description,
        "description_html": None,
        "description_extracted_at": None,
        "description_extraction_model": None,
        "criteria": ["Strong fit for your background"],
        "skills_required": ["python", "pytorch"],
        "visa_restrictions": visa,
        "salary_min": 200_000,
        "salary_max": 260_000,
        "equity_pct": None,
        "score": score,
        "score_explanation": None,
        "match_breakdown": {},
        "queue_state": queue_state,
        "tags": tags if tags is not None else [],
        "warm_intro_contact_id": None,
        "last_scrape_run_id": last_scrape_run_id,
        "duplicate_of_id": duplicate_of_id,
        "raw_meta": {},
        "created_at": now,
        "updated_at": now,
        "deleted_at": deleted_at,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── parse_filters_from_query ─────────────────────────────────────────────


def test_parse_filters_handles_empty_query():
    """No filter params → JobFilter() with all defaults."""
    out = dctx.parse_filters_from_query({})
    assert out.source is None
    assert out.remote_only is False
    assert out.visa is None
    assert out.seniority is None
    assert out.score_min == 0.0
    assert out.include_duplicates is False
    assert out.queue_state is None


def test_parse_filters_translates_source_visa_seniority():
    out = dctx.parse_filters_from_query(
        {"source": "LINKEDIN", "visa": "sponsorship_available", "seniority": "senior"}
    )
    assert out.source == JobSource.LINKEDIN
    assert out.visa == VisaRestriction.SPONSORSHIP_AVAILABLE
    assert out.seniority == SeniorityLevel.SENIOR


def test_parse_filters_remote_only_truthy_tokens():
    """0.2.0.11 URL contract — remote_only=1/true/on all coerce to True."""
    for tok in ["1", "true", "yes", "on"]:
        out = dctx.parse_filters_from_query({"remote_only": tok})
        assert out.remote_only is True
    out = dctx.parse_filters_from_query({"remote_only": "0"})
    assert out.remote_only is False


def test_parse_filters_legacy_filter_saved_maps_to_queue_state():
    """Plan 36 § E row 7 — `?filter=saved` continues to mean queue_state=SAVED."""
    out = dctx.parse_filters_from_query({"filter": "saved"})
    assert out.queue_state == JobQueueState.SAVED


def test_parse_filters_score_min_coerces_float():
    out = dctx.parse_filters_from_query({"score_min": "0.65"})
    assert out.score_min == 0.65


def test_parse_filters_include_duplicates_toggle():
    out = dctx.parse_filters_from_query({"include_duplicates": "1"})
    assert out.include_duplicates is True


# ── Discover route: live-DB wiring + filter querystring round-trip ───────


@pytest.mark.asyncio
async def test_build_discover_ctx_uses_job_service_when_session_present(monkeypatch):
    """Plan 36 § A · D.5 — live-DB path calls job_service.list_jobs."""
    from services import job_service

    captured: dict[str, Any] = {}

    async def _fake_list_jobs(session, *, user_id, filters=None, page=0, page_size=50):
        captured["user_id"] = user_id
        captured["filters"] = filters
        captured["page"] = page
        captured["page_size"] = page_size
        return [
            _fake_job(jid=300, company="Stripe", score=0.91),
            _fake_job(jid=301, company="Anthropic", score=0.88),
        ]

    monkeypatch.setattr(job_service, "list_jobs", _fake_list_jobs)

    from models import JobFilter

    ctx = await dctx.build_discover_ctx(
        SimpleNamespace(),  # session sentinel — passed through to job_service
        user_id=1,
        filters=JobFilter(source=JobSource.LINKEDIN, remote_only=True),
    )
    assert captured["user_id"] == 1
    assert captured["filters"].source == JobSource.LINKEDIN
    assert captured["filters"].remote_only is True
    # `_live_unswiped` forces queue_state=UNSWIPED when the caller leaves it None.
    assert captured["filters"].queue_state == JobQueueState.UNSWIPED
    assert ctx["unswiped_count"] == 2
    assert ctx["current_card"]["company"] == "Stripe"


@pytest.mark.asyncio
async def test_build_discover_ctx_empty_live_returns_empty_queue(monkeypatch):
    """Plan 69 (`0.3.3.12`) removed the sample-data fallback in `build_discover_ctx`.

    Empty live DB → empty queue surface (the fresh-fork blank-Discover problem is
    handled at the seed layer + the swipe_card.html `{% if not current_card %}`
    empty-state guard). This test pins the new contract; the legacy fallback path
    no longer exists.
    """
    from services import application_service, contact_tracker, job_service

    async def _empty_list_jobs(*a, **kw):
        return []

    async def _empty_stuck_drafts(*a, **kw):
        return []

    async def _empty_auto_apply_queue(*a, **kw):
        return []

    async def _empty_list_jobs_by_queue_state(*a, **kw):
        return []

    async def _none_get_contact(*a, **kw):
        return None

    monkeypatch.setattr(job_service, "list_jobs", _empty_list_jobs)
    monkeypatch.setattr(job_service, "list_jobs_by_queue_state", _empty_list_jobs_by_queue_state)
    monkeypatch.setattr(job_service, "auto_apply_queue", _empty_auto_apply_queue)
    monkeypatch.setattr(application_service, "stuck_drafts", _empty_stuck_drafts)
    monkeypatch.setattr(contact_tracker, "get_contact", _none_get_contact)

    ctx = await dctx.build_discover_ctx(SimpleNamespace(), user_id=1)
    assert ctx["unswiped_count"] == 0
    assert ctx["current_card"] is None
    assert ctx["up_next"] == []


def test_discover_route_passes_filters_through(client, auth_cookies):
    """Fake-session callers route through the sample-data fallback (no DB).

    After plan 36, real-auth callers (user is not None) hit
    `job_service.list_jobs`; fake-session (`naavik_session=fake-1`) returns
    user=None which short-circuits to sample_data, preserving the existing
    test surface contract.
    """
    r = client.get(
        "/discover?source=linkedin&remote_only=1&seniority=senior",
        cookies=auth_cookies,
    )
    assert r.status_code == 200
    # filter_toolbar renders the chips with current values
    assert "Discover" in r.text
    assert "filter-toolbar" in r.text


def test_discover_route_rejects_invalid_source_value(client, auth_cookies):
    """Unknown source enum value → 422 via Pydantic ValidationError."""
    r = client.get("/discover?source=NOT_A_REAL_SOURCE", cookies=auth_cookies)
    assert r.status_code == 422


def test_discover_queue_fragment_returns_queue_only(client, auth_cookies):
    """`/_fragments/discover/queue` must NOT include the page chrome."""
    r = client.get("/_fragments/discover/queue", cookies=auth_cookies)
    assert r.status_code == 200
    # The fragment renders the queue grid; the full page header ("Discover" h1)
    # is OUTSIDE the fragment, so it should not appear in the response.
    assert "discover-skip-btn" in r.text or "search-x" in r.text or "empty_state" in r.text
    # Page-level chrome (the h1 + filter toolbar) lives only on the full page.
    assert '<h1 class="text-2xl font-semibold text-slate-50' not in r.text


def test_discover_queue_fragment_filter_with_zero_results(client, auth_cookies):
    """Filter that matches nothing renders the search-x empty state.

    Fake-session path uses sample_data shadow filtering; force a zero-result
    slice by picking a source value sample_data doesn't seed (RSSHUB).
    """
    r = client.get(
        "/_fragments/discover/queue?source=rsshub&seniority=exec",
        cookies=auth_cookies,
    )
    assert r.status_code == 200
    assert "search-x" in r.text


@pytest.mark.asyncio
async def test_include_duplicates_filter_threads_into_job_service(monkeypatch):
    """`?include_duplicates=1` must reach JobFilter so the filter actually applies."""
    from services import job_service

    captured: dict[str, Any] = {}

    async def _capture(session, *, user_id, filters=None, **kw):
        captured["include_duplicates"] = filters.include_duplicates
        return [_fake_job(jid=410)]

    monkeypatch.setattr(job_service, "list_jobs", _capture)

    from models import JobFilter

    await dctx.build_discover_ctx(
        SimpleNamespace(),
        user_id=1,
        filters=JobFilter(include_duplicates=True),
    )
    assert captured["include_duplicates"] is True


# ── Job detail page ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_detail_renders_200_for_owner(monkeypatch):
    """`/jobs/{id}` returns 200 + renders the topbar + body sections."""
    from main import app
    from services import job_service

    target = _fake_job(jid=501, user_id=1, company="Hugging Face", score=0.0)

    async def _get_job(session, job_id):
        return target if job_id == 501 else None

    monkeypatch.setattr(job_service, "get_job", _get_job)

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/jobs/501", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 200
    assert "Hugging Face" in r.text
    assert "Back to Discover" in r.text
    assert "Job description" in r.text
    # Unscored job renders the placeholder
    assert "unscored" in r.text.lower()


@pytest.mark.asyncio
async def test_job_detail_404_when_job_missing(monkeypatch):
    """Unknown job id → 404."""
    from main import app
    from services import job_service

    async def _none(session, job_id):
        return None

    monkeypatch.setattr(job_service, "get_job", _none)

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/jobs/9999", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_job_detail_404_for_non_owner(monkeypatch):
    """IDOR mitigation: user A sees user B's job as 404 (not 403)."""
    from main import app
    from services import job_service

    other = _fake_job(jid=502, user_id=999, company="Crossover Corp")

    async def _get(session, job_id):
        return other if job_id == 502 else None

    monkeypatch.setattr(job_service, "get_job", _get)

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/jobs/502", cookies={"naavik_session": "fake-1"})
    # Fake session resolves to user_id=1; the seeded job belongs to 999.
    assert r.status_code == 404
    assert "Crossover Corp" not in r.text


@pytest.mark.asyncio
async def test_job_detail_404_when_archived(monkeypatch):
    """Soft-deleted Job (`deleted_at` set) is invisible to /jobs/{id}."""
    from main import app
    from services import job_service

    archived = _fake_job(jid=503, deleted_at=datetime.now(UTC))

    async def _get(session, job_id):
        return archived if job_id == 503 else None

    monkeypatch.setattr(job_service, "get_job", _get)

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/jobs/503", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_job_detail_renders_duplicate_banner(monkeypatch):
    """When `duplicate_of_id` is set, the amber duplicate banner renders."""
    from main import app
    from services import job_service

    dup = _fake_job(jid=504, duplicate_of_id=501)

    async def _get(session, job_id):
        return dup if job_id == 504 else None

    monkeypatch.setattr(job_service, "get_job", _get)

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/jobs/504", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 200
    assert "data-duplicate-banner" in r.text
    assert "tier-3 fuzzy duplicate" in r.text


@pytest.mark.asyncio
async def test_job_detail_renders_scrape_run_metadata(monkeypatch):
    """When the Job has a last_scrape_run_id, the scrape-run block renders."""
    from main import app
    from services import job_service

    target = _fake_job(jid=505, last_scrape_run_id=77)
    fake_run = SimpleNamespace(
        id=77,
        source=JobSource.LINKEDIN,
        status=JobScrapeStatus.SUCCESS,
        triggered_by="cron",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=12345,
        requests_made=10,
        listings_returned=5,
        new_jobs=2,
        updated_jobs=3,
        errors=[],
    )

    async def _get(session, job_id):
        return target

    async def _get_scrape_run(session, scrape_run_id):
        return fake_run if scrape_run_id == 77 else None

    monkeypatch.setattr(job_service, "get_job", _get)
    # Plan 69 (`0.3.3.12`): `_last_scrape_run` was refactored to call
    # `job_service.get_scrape_run` instead of `session.exec(...)` directly.
    monkeypatch.setattr(job_service, "get_scrape_run", _get_scrape_run)

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/jobs/505", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 200
    assert "Last scrape run · #77" in r.text
    assert "12345ms" in r.text


@pytest.mark.asyncio
async def test_api_v1_jobs_get_json_404_for_non_owner(monkeypatch):
    """`GET /api/v1/jobs/{id}` (moved to jobs.py) enforces same IDOR boundary."""
    from main import app
    from services import job_service

    other = _fake_job(jid=506, user_id=999)

    async def _get(session, job_id):
        return other if job_id == 506 else None

    monkeypatch.setattr(job_service, "get_job", _get)

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/api/v1/jobs/506", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_v1_jobs_get_json_uses_jobread_projection(monkeypatch):
    """Plan 46 / 0.2.0.11c: response projects through `JobRead` (not the
    raw SQLModel). `raw_meta` JSONB is scraper-controlled and must not
    appear in the public API response, even though the owner-only IDOR
    gate already restricts cross-user reads.
    """
    from main import app
    from services import job_service

    own = _fake_job(
        jid=507,
        user_id=1,
        raw_meta={"linkedin_job_id": "abc", "vendor_secret": "leak-me-if-you-can"},
    )

    async def _get(session, job_id):
        return own if job_id == 507 else None

    monkeypatch.setattr(job_service, "get_job", _get)

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/api/v1/jobs/507", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 200
    body = r.json()
    # raw_meta is intentionally absent from the public projection.
    assert "raw_meta" not in body
    assert "leak-me-if-you-can" not in r.text
    # Known JobRead fields still present.
    assert body["id"] == 507
    assert body["company"] == "Anthropic"
    assert body["role"] == "Senior ML Engineer"
    assert body["source"] == JobSource.LINKEDIN.value
