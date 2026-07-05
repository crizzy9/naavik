"""Job-detail apply-target card + inline resolution affordances (2026-07).

Pins the right-rail card states (resolved / retrying / exhausted), the
"Re-resolve now" POST, and the manual paste-URL escape hatch (`via="manual"`).
`job_service.get_job` is monkeypatched the way `tests/test_job_routes.py`
does; resolution itself is stubbed — no network, no browser.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from datetime import UTC, datetime, timedelta  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from models import ApplicationBoard, JobSource  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims

_CSRF = "csrf-cookie-token-apply-target-aaaaaaaaaaaaaaaaaaaa"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF)
    return c


def _fake_job(*, jid=601, user_id=1, **overrides):
    from models.enums import JobQueueState, RemotePolicy, SeniorityLevel, VisaRestriction

    now = datetime.now(UTC)
    base = {
        "id": jid,
        "user_id": user_id,
        "source": JobSource.LINKEDIN,
        "external_id": str(jid),
        "board": ApplicationBoard.LINKEDIN,
        "url": f"https://www.linkedin.com/jobs/view/{jid}",
        "url_type": "external",
        "apply_url": None,
        "apply_kind": None,
        "apply_resolved_at": None,
        "apply_resolved_via": None,
        "apply_resolve_attempts": 0,
        "apply_next_resolve_at": None,
        "company": "KAYAK",
        "role": "Senior Java Software Engineer",
        "team": None,
        "location": "Boston",
        "remote_policy": RemotePolicy.HYBRID,
        "seniority_level": SeniorityLevel.SENIOR,
        "posted_at": None,
        "posted_at_text": None,
        "found_at": now,
        "description": "Build travel search.",
        "description_html": None,
        "description_extracted_at": None,
        "description_extraction_model": None,
        "criteria": [],
        "skills_required": [],
        "visa_restrictions": VisaRestriction.NOT_MENTIONED,
        "salary_min": None,
        "salary_max": None,
        "equity_pct": None,
        "score": 0.8,
        "score_explanation": None,
        "match_breakdown": {},
        "queue_state": JobQueueState.UNSWIPED,
        "tags": [],
        "warm_intro_contact_id": None,
        "last_scrape_run_id": None,
        "duplicate_of_id": None,
        "raw_meta": {},
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _install_job(monkeypatch, job):
    from services import jobs as job_service

    async def _get(session, job_id):
        return job if job_id == job.id else None

    monkeypatch.setattr(job_service, "get_job", _get)


# ── Card render states on /jobs/{id} ─────────────────────────────────────


def test_card_renders_resolved_target(client, monkeypatch):
    job = _fake_job(
        apply_url="https://job-boards.greenhouse.io/kayak/jobs/1",
        apply_kind="greenhouse",
        apply_resolved_via="linkedin_auth",
        apply_resolve_attempts=2,
        apply_resolved_at=datetime.now(UTC),
    )
    _install_job(monkeypatch, job)
    r = client.get(f"/jobs/{job.id}")
    assert r.status_code == 200
    assert 'id="apply-target-card"' in r.text
    assert "apply · Greenhouse" in r.text
    assert "job-boards.greenhouse.io/kayak/jobs/1" in r.text
    assert "linkedin_auth" in r.text
    assert 'data-testid="re-resolve-apply-btn"' in r.text
    # A resolved target needs no manual escape hatch.
    assert 'data-testid="manual-apply-url-form"' not in r.text


def test_card_renders_retry_scheduled_state(client, monkeypatch):
    job = _fake_job(
        apply_kind="external",
        apply_resolved_via="unresolved",
        apply_resolve_attempts=2,
        apply_resolved_at=datetime.now(UTC),
        apply_next_resolve_at=datetime.now(UTC) + timedelta(hours=4),
    )
    _install_job(monkeypatch, job)
    r = client.get(f"/jobs/{job.id}")
    assert r.status_code == 200
    assert "unresolved" in r.text
    assert "Next automatic retry" in r.text
    assert 'data-testid="manual-apply-url-form"' in r.text


def test_card_renders_exhausted_state_with_paste_form(client, monkeypatch):
    job = _fake_job(
        apply_kind="external",
        apply_resolved_via="exhausted",
        apply_resolve_attempts=5,
        apply_resolved_at=datetime.now(UTC),
    )
    _install_job(monkeypatch, job)
    r = client.get(f"/jobs/{job.id}")
    assert r.status_code == 200
    assert "unresolved · gave up" in r.text
    assert 'data-testid="manual-apply-url-form"' in r.text


# ── POST /api/v1/jobs/{id}/resolve-apply ─────────────────────────────────


def test_re_resolve_stamps_and_returns_fragment(client, monkeypatch):
    from services import applications as application_service
    from services import resolution as apply_site_resolver
    from services import resolution as linkedin_resolver

    job = _fake_job(apply_kind="external", apply_resolved_via="unresolved")
    _install_job(monkeypatch, job)
    monkeypatch.setattr(linkedin_resolver, "auth_available", lambda: False)
    monkeypatch.setattr(
        apply_site_resolver,
        "resolve_job",
        AsyncMock(
            return_value=apply_site_resolver.ResolvedApply(
                kind="workday",
                apply_url="https://kayak.wd5.myworkdayjobs.com/j/1",
                via="linkedin_auth",
            )
        ),
    )
    monkeypatch.setattr(application_service, "resync_draft_apply_target", AsyncMock(return_value=0))
    r = client.post(f"/api/v1/jobs/{job.id}/resolve-apply", headers={"X-CSRF-Token": _CSRF})
    assert r.status_code == 200
    assert 'id="apply-target-card"' in r.text
    assert "apply · Workday" in r.text
    assert job.apply_kind == "workday"
    assert job.apply_resolve_attempts == 1
    assert job.board == ApplicationBoard.WORKDAY


def test_re_resolve_failure_counts_attempt(client, monkeypatch):
    from services import resolution as apply_site_resolver
    from services import resolution as linkedin_resolver

    job = _fake_job(apply_kind="external", apply_resolved_via="unresolved")
    _install_job(monkeypatch, job)
    monkeypatch.setattr(linkedin_resolver, "auth_available", lambda: False)
    monkeypatch.setattr(
        apply_site_resolver, "resolve_job", AsyncMock(side_effect=RuntimeError("boom"))
    )
    r = client.post(f"/api/v1/jobs/{job.id}/resolve-apply", headers={"X-CSRF-Token": _CSRF})
    assert r.status_code == 200
    assert job.apply_resolve_attempts == 1
    assert job.apply_next_resolve_at is not None


def test_re_resolve_404_for_non_owner(client, monkeypatch):
    job = _fake_job(user_id=999)
    _install_job(monkeypatch, job)
    r = client.post(f"/api/v1/jobs/{job.id}/resolve-apply", headers={"X-CSRF-Token": _CSRF})
    assert r.status_code == 404


# ── POST /api/v1/jobs/{id}/apply-url (manual paste) ──────────────────────


def test_manual_paste_stamps_via_manual(client, monkeypatch):
    from services import applications as application_service
    from services import resolution as apply_site_resolver

    job = _fake_job(apply_kind="external", apply_resolved_via="exhausted", apply_resolve_attempts=5)
    _install_job(monkeypatch, job)
    monkeypatch.setattr(
        apply_site_resolver,
        "normalize_apply_url",
        AsyncMock(return_value=("https://jobs.ashbyhq.com/kayak/1", "ashby")),
    )
    monkeypatch.setattr(application_service, "resync_draft_apply_target", AsyncMock(return_value=0))
    r = client.post(
        f"/api/v1/jobs/{job.id}/apply-url",
        data={
            "apply_url": "https://click.appcast.io/t?url=https%3A%2F%2Fjobs.ashbyhq.com%2Fkayak%2F1"
        },
        headers={"X-CSRF-Token": _CSRF},
    )
    assert r.status_code == 200
    assert job.apply_url == "https://jobs.ashbyhq.com/kayak/1"
    assert job.apply_kind == "ashby"
    assert job.apply_resolved_via == "manual"
    assert job.apply_resolve_attempts == 5  # manual paste is not an attempt
    assert job.apply_next_resolve_at is None
    assert job.board == ApplicationBoard.ASHBY
    # Provenance: the pasted wrapper URL is kept alongside the normalized one.
    assert job.raw_meta.get("apply_url_original", "").startswith("https://click.appcast.io/")


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "ftp://x", "  "])
def test_manual_paste_rejects_non_http_schemes(client, monkeypatch, bad):
    job = _fake_job()
    _install_job(monkeypatch, job)
    r = client.post(
        f"/api/v1/jobs/{job.id}/apply-url",
        data={"apply_url": bad},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert r.status_code == 422
    assert job.apply_url is None
