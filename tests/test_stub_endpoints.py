"""Per-stub-endpoint shape + ?fail=1 failure-mode coverage (plan 09 § I).

Wave 4 swap: profile/bullet endpoints are now DB-backed real handlers.
Tests that hit them are gated on a reachable Postgres at `DATABASE_URL` —
they're effectively integration tests now. The pure-shape tests for
endpoints that don't touch the DB (logout, csrf, error responses, reorder)
keep running unconditionally.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

# DB-backed handlers run only when NAAVIK_LIVE_DB=1 is set. Plain pytest runs
# skip them — the unit tests for auth/vault/llm cover the same code paths
# without needing live DB.
_LIVE_DB = os.environ.get("NAAVIK_LIVE_DB", "").strip().lower() in {"1", "true", "yes"}


def _skip_if_no_db() -> None:
    if not _LIVE_DB:
        pytest.skip("set NAAVIK_LIVE_DB=1 to run DB-backed integration tests")


# Matching CSRF pair threaded through any POST that hits a `require_csrf`-gated
# route (plan 44 / 0.2.0.11b — discover swipe endpoints). HTMX `base.html` injects
# the header globally in production; tests have to thread it explicitly.
_CSRF_TOKEN = "csrf-cookie-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_CSRF_HEADERS = {"X-CSRF-Token": _CSRF_TOKEN}


@pytest.fixture(scope="module")
def client() -> TestClient:
    """TestClient carrying the plan-09 fake-session cookie by default.

    Plan 23 (PC.6a, 2026-05-18) broadened `require_authed_session` across the
    mutation surface — naked-call routes that previously accepted any caller
    now 401 without an auth cookie. The tests below were written against the
    pre-gate substrate, so the fixture pre-seeds the fake-session cookie to
    match the way every other stub-endpoint test in the suite already calls.
    Individual tests that want to test the unauthenticated path can clear
    the cookie via `client.cookies.clear()`.

    Plan 44 (0.2.0.11b) added `Depends(require_csrf)` to the discover swipe
    endpoints; the fixture also seeds the CSRF cookie so the matching header
    threaded through each affected call passes the double-submit check.
    """
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    return c


@pytest.fixture(autouse=True)
def _restore_state():
    """Restore mutable in-memory lists across endpoint smoke tests."""
    from db import sample_data as sd

    apps_snap = [a.model_copy(deep=True) for a in sd.APPLICATIONS]
    bullets_snap = [b.model_copy(deep=True) for b in sd.BULLETS]
    jobs_snap = [j.model_copy(deep=True) for j in sd.JOBS]
    om_snap = [m.model_copy(deep=True) for m in sd.OUTREACH_MESSAGES]
    yield
    sd.APPLICATIONS.clear()
    sd.APPLICATIONS.extend(apps_snap)
    sd.BULLETS.clear()
    sd.BULLETS.extend(bullets_snap)
    sd.JOBS.clear()
    sd.JOBS.extend(jobs_snap)
    sd.OUTREACH_MESSAGES.clear()
    sd.OUTREACH_MESSAGES.extend(om_snap)


# ── Auth ────────────────────────────────────────────────────────────────
#
# Plan 10 Wave 4 swapped these stubs for real bcrypt + JWT + CSRF handlers
# in `src/api/auth.py`. End-to-end auth coverage now lives in:
# - `tests/test_auth.py` (unit tests on bcrypt / JWT / CSRF / rate limit)
# - integration tests run against the live dev DB during smoke
# (see `tests/test_seed.py` pattern). The stub-shape tests below are
# preserved for the endpoints that survive plan-09 (logout + csrf — these
# don't need DB).


def test_auth_logout(client):
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert r.headers.get("hx-redirect") == "/login"


def test_auth_me_unauthenticated(client):
    # Brand-new client to drop cookies.
    from fastapi.testclient import TestClient as TC

    from main import app

    bare = TC(app, raise_server_exceptions=True)
    r = bare.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_auth_csrf(client):
    r = client.get("/api/v1/auth/csrf")
    assert r.status_code == 200
    assert "csrf_token" in r.json()


# ── Profile / bullets ────────────────────────────────────────────────────


def test_profile_field_put_returns_oob_indicator(client):
    _skip_if_no_db()
    r = client.put("/api/v1/profile/full_name", data={"value": "Shyam P."})
    assert r.status_code == 200
    assert 'id="autosave"' in r.text
    assert "Auto-saved" in r.text


def test_profile_field_put_fail_returns_error_indicator(client):
    r = client.put("/api/v1/profile/full_name?fail=1", data={"value": "x"})
    assert r.status_code == 422
    assert "retry" in r.text.lower() or "couldn" in r.text.lower()


def test_profile_field_put_unknown_field_returns_404(client):
    r = client.put("/api/v1/profile/random_field_xyz", data={"value": "x"})
    assert r.status_code == 404


def test_bullets_post_get_put_delete_roundtrip(client):
    _skip_if_no_db()
    # POST
    r = client.post("/api/v1/bullets", data={"text": "Test bullet", "experience_id": 1})
    assert r.status_code == 200
    assert "Test bullet" in r.text
    # PUT
    # extract id from the data-bullet-id attribute
    import re

    m = re.search(r'data-bullet-id="(\d+)"', r.text)
    assert m
    bid = int(m.group(1))
    r2 = client.put(f"/api/v1/bullets/{bid}", data={"text": "Edited bullet"})
    assert r2.status_code == 200
    assert "closeModal" in r2.headers.get("hx-trigger", "")
    # DELETE
    r3 = client.delete(f"/api/v1/bullets/{bid}")
    assert r3.status_code == 204


def test_bullets_rewrite(client):
    _skip_if_no_db()
    r = client.post("/api/v1/bullets/1/rewrite")
    assert r.status_code == 200
    assert r.json().get("edited") is True


def test_bullets_reorder(client):
    r = client.post("/api/v1/bullets/reorder", json={"bullet_ids": [1, 2, 3]})
    assert r.status_code == 204


# ── Discover / jobs ──────────────────────────────────────────────────────


def test_jobs_list(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert len(body["items"]) > 0


def test_jobs_get_by_id(client, monkeypatch):
    """Plan 36 § A moved `GET /api/v1/jobs/{id}` from `ui/routes/discover.py`
    to `ui/routes/jobs.py` and tightened it to require auth + scope to the
    requesting user. Plan 46 / 0.2.0.11c then swapped the JSON projection to
    `JobRead.model_validate(job)` to keep `raw_meta` JSONB off the public API.
    The stub now mirrors the full JobRead shape so `model_validate` succeeds
    without a live DB.
    """
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from models import (
        ApplicationBoard,
        JobQueueState,
        JobSource,
        RemotePolicy,
        SeniorityLevel,
        VisaRestriction,
    )
    from services import job_service

    now = datetime.now(UTC)

    async def _get_job(session, job_id):
        if job_id != 101:
            return None
        return SimpleNamespace(
            id=101,
            user_id=1,
            source=JobSource.LINKEDIN,
            board=ApplicationBoard.LINKEDIN,
            external_id="ln-101-zzz",
            url="https://linkedin.com/jobs/view/101",
            url_type="ats",
            company="Stripe",
            role="Senior Engineer",
            team=None,
            location="Remote · USA",
            remote_policy=RemotePolicy.REMOTE,
            seniority_level=SeniorityLevel.SENIOR,
            posted_at=None,
            posted_at_text=None,
            found_at=now,
            description="Payments infra.",
            description_extracted_at=None,
            description_extraction_model=None,
            criteria=[],
            skills_required=[],
            visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
            salary_min=None,
            salary_max=None,
            equity_pct=None,
            score=0.85,
            score_explanation=None,
            match_breakdown={},
            queue_state=JobQueueState.UNSWIPED,
            tags=[],
            warm_intro_contact_id=None,
            last_scrape_run_id=None,
            duplicate_of_id=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    monkeypatch.setattr(job_service, "get_job", _get_job)
    r = client.get("/api/v1/jobs/101")
    assert r.status_code == 200
    body = r.json()
    assert body["company"] == "Stripe"
    # raw_meta intentionally absent (plan 46 / 0.2.0.11c).
    assert "raw_meta" not in body


def test_jobs_by_url_real_pipeline(client, monkeypatch):
    """P6.2 — the by-url endpoint fetches the REAL page, extracts, upserts,
    scores, and returns an HTML result fragment + queue-refresh trigger
    (the old stub fabricated 'Stable Inc' / score 0.84 and dumped JSON)."""
    from types import SimpleNamespace

    from llm.base import LLMProviderError
    from scraper.crawl4ai_client import Crawl4AIClient
    from services import job_service, profile_service

    async def _fake_fetch(self, url):
        return "<html><title>Staff Engineer - Acme</title><body>JD text</body></html>"

    monkeypatch.setattr(Crawl4AIClient, "fetch_html", _fake_fetch)

    import llm as llm_module

    def _no_provider(_settings):
        raise LLMProviderError("no provider", kind="auth_required")

    monkeypatch.setattr(llm_module, "get_provider", _no_provider)

    captured = {}

    async def _fake_upsert(session, *, user_id, source, external_id, raw, scrape_run_id=None):
        captured["raw"] = raw
        job = SimpleNamespace(
            id=999, role=raw["role"], company=raw["company"], url=raw["url"], score=0.0
        )
        return job, True

    monkeypatch.setattr(job_service, "upsert_job", _fake_upsert)

    async def _no_profile(session, user_id):
        return None

    monkeypatch.setattr(profile_service, "get_profile", _no_profile)

    r = client.post(
        "/api/v1/jobs/by-url",
        json={"url": "https://example.com/job/123"},
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 200, r.text
    # HTML fragment, not JSON — real extracted identity from the <title>.
    assert "Added" in r.text
    assert "Staff Engineer" in r.text and "Acme" in r.text
    assert "queue-refresh" in r.headers.get("HX-Trigger", "")
    # Nothing fabricated: no fake score / SF location in the payload.
    assert captured["raw"].get("score") is None
    assert captured["raw"].get("location") is None


def test_jobs_by_url_unfetchable_returns_error_fragment(client, monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient

    async def _fake_fetch(self, url):
        return None

    monkeypatch.setattr(Crawl4AIClient, "fetch_html", _fake_fetch)
    r = client.post(
        "/api/v1/jobs/by-url",
        json={"url": "https://example.com/job/456"},
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 422
    assert "Could not fetch" in r.text


def test_discover_skip_returns_swipe_card(client):
    r = client.post("/api/v1/discover/124/skip", headers=_CSRF_HEADERS)
    assert r.status_code == 200
    assert 'id="discover-card"' in r.text


def test_discover_skip_fail(client):
    r = client.post("/api/v1/discover/124/skip?fail=1", headers=_CSRF_HEADERS)
    assert r.status_code == 502


def test_discover_save_returns_swipe_card(client):
    r = client.post("/api/v1/discover/115/save", headers=_CSRF_HEADERS)
    assert r.status_code == 200


def test_auto_submit_creates_draft(client):
    from db import sample_data as sd

    n_before = len([a for a in sd.APPLICATIONS if a.status.value == "DRAFT"])
    r = client.post("/api/v1/applications/126/auto-submit", headers=_CSRF_HEADERS)
    assert r.status_code == 200
    n_after = len([a for a in sd.APPLICATIONS if a.status.value == "DRAFT"])
    assert n_after == n_before + 1


# ── Applications ─────────────────────────────────────────────────────────


def test_applications_list(client):
    r = client.get("/api/v1/applications")
    assert r.status_code == 200
    assert "items" in r.json()


def test_applications_get(client):
    r = client.get("/api/v1/applications/1")
    assert r.status_code == 200
    assert r.json()["company"] == "Figma"


@pytest.mark.skip(
    reason=(
        "Wave-3 stub-behavior test. Wave 6 swap moved /api/v1/applications/move "
        "to src/api/applications.py with auth required. Behavior is "
        "tested at the service level in test_application_service.py."
    )
)
def test_applications_move(client):
    pass


@pytest.mark.skip(
    reason="Wave-6 endpoint no longer accepts ?fail= query param (test was a stub artifact)."
)
def test_applications_move_fail(client):
    pass


def test_applications_manual_creates_row(client):
    # Plan 56 / 0.2.7.19 — `Depends(require_csrf)` added; thread the matching header.
    r = client.post(
        "/api/v1/applications/manual",
        data={"company": "Test Co", "role": "Sr Eng"},
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 204
    assert r.headers.get("hx-redirect") == "/tracking"


def test_applications_bundle_409_when_nothing_generated(client):
    """Hardening pass: the bundle download now serves REAL generated PDFs (was
    a stub that zipped "%PDF-1.4\\n%placeholder" bytes). With no generated
    documents it returns an honest 409 rather than a fake ZIP."""
    r = client.get("/api/v1/applications/1/bundle")
    assert r.status_code == 409
    assert "generate" in r.text.lower()


# ── Settings ─────────────────────────────────────────────────────────────


def test_settings_test_connection_ok(client):
    r = client.post("/_fragments/settings/test-connection")
    assert r.status_code == 200
    assert "Connection ok" in r.text


def test_settings_test_connection_fail(client):
    r = client.post("/_fragments/settings/test-connection?fail=1")
    assert r.status_code == 200
    assert "check your key" in r.text or "Couldn" in r.text


def test_settings_llm_usage(client):
    r = client.get("/api/v1/settings/llm/usage")
    assert r.status_code == 200
    body = r.json()
    assert "month_cost_usd" in body
    assert body["month_cost_usd"] > 0


def _override_account_password_dep(*, flagged: bool):
    """Inject a fake `get_current_user` so the gated Settings · Account
    password stub is reachable from a TestClient without a real JWT cookie.
    Returns the (app, restore) tuple so callers can clean up.
    """
    from main import app
    from models import User
    from services.auth import get_current_user

    def _fake():
        return User(
            id=1,
            email="dev@local",
            password_hash="$2b$04$placeholder.hash.for.test.only",
            is_active=True,
            is_admin=True,
            must_change_password=flagged,
        )

    app.dependency_overrides[get_current_user] = _fake
    return app, lambda: app.dependency_overrides.pop(get_current_user, None)


def test_settings_account_password_wrong_current_returns_422(client):
    """Hardening pass: the Settings · Account password change is now a REAL
    mutation (was a stub that always returned "Password updated."). A wrong
    current password is rejected with 422 before any DB write — no more
    fake-success.
    """
    _app, restore = _override_account_password_dep(flagged=False)
    try:
        r = client.put(
            "/api/v1/settings/account/password",
            data={"current": "definitely-wrong", "new": "N3w-Strong-Pw!"},
            headers=_CSRF_HEADERS,
        )
    finally:
        restore()
    assert r.status_code == 422
    assert "incorrect" in r.text.lower()
    assert "Password updated" not in r.text


def test_settings_account_password_requires_csrf(client):
    """State-changing password route is CSRF-gated (double-submit)."""
    _app, restore = _override_account_password_dep(flagged=False)
    try:
        r = client.put(
            "/api/v1/settings/account/password",
            data={"current": "x", "new": "y"},
            headers={"X-CSRF-Token": "mismatched-token"},
        )
    finally:
        restore()
    assert r.status_code == 403


def test_settings_account_password_redirects_flagged_user(client):
    """Plan 18 (PC.6) re-loop (hacker Finding 1, HIGH): a flagged user
    (`must_change_password=True`) hitting the alternate Settings · Account
    password endpoint must NOT see the "Password updated" stub success —
    `require_password_complete` raises 303 to /auth/change-password instead,
    closing the complexity-bypass surface the hacker review flagged.
    """
    _app, restore = _override_account_password_dep(flagged=True)
    try:
        r = client.put(
            "/api/v1/settings/account/password",
            data={"current": "x", "new": "y"},
            follow_redirects=False,
        )
    finally:
        restore()
    assert r.status_code == 303
    assert r.headers.get("hx-redirect") == "/auth/change-password"
    assert r.headers.get("location") == "/auth/change-password"
    # Importantly: the stub's success blob is NOT in the response body.
    assert "Password updated" not in r.text


def test_settings_deployment_restart_endpoint_removed(client):
    """The fake in-app "Restart" endpoint (returned 202 without restarting)
    was removed in the hardening pass — process lifecycle belongs to the
    supervisor (Docker/systemd). The route no longer exists."""
    r = client.post("/api/v1/settings/deployment/restart")
    assert r.status_code == 404


def test_settings_notifications_test_discord_reports_unconfigured(client):
    """Notification test is now a REAL send (was a fake "Sent test message").
    With no DISCORD_WEBHOOK_URL configured it honestly reports 422 rather than
    pretending success."""
    r = client.post(
        "/api/v1/settings/notifications/test?channel=discord",
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 422
    assert "DISCORD_WEBHOOK_URL" in r.text


# ── Integrations + email ─────────────────────────────────────────────────


def test_integrations_list(client):
    r = client.get("/api/v1/integrations")
    assert r.status_code == 200
    items = r.json()
    providers = {i["provider"] for i in items}
    assert {"gmail", "outlook", "calendar"}.issubset(providers)


def test_gmail_connect_redirects_to_callback(client):
    r = client.get("/api/v1/integrations/gmail/connect", follow_redirects=False)
    assert r.status_code == 302
    assert "callback" in r.headers["location"]


def test_gmail_callback_then_disconnect(client):
    r = client.get("/api/v1/integrations/gmail/callback?code=fake-1", follow_redirects=False)
    assert r.status_code == 302
    assert "/tracking?connected=gmail" in r.headers["location"]
    r2 = client.post("/api/v1/integrations/gmail/disconnect")
    assert r2.status_code == 204
    assert r2.headers.get("hx-redirect") == "/tracking"


def test_email_threads_list(client):
    r = client.get("/api/v1/email/threads")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_email_thread_get(client):
    r = client.get("/api/v1/email/threads/601")
    assert r.status_code == 200
    assert r.json()["subject"].startswith("Re: Senior ML")


def test_email_thread_draft_reply(client):
    r = client.post("/api/v1/email/threads/601/draft-reply", json={"intent": "follow_up"})
    assert r.status_code == 200
    assert "body" in r.json()


# ── Outreach / contacts ──────────────────────────────────────────────────


def test_contacts_list(client):
    r = client.get("/api/v1/contacts")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_contacts_find(client):
    r = client.post("/api/v1/contacts/find", json={"company": "Stripe"})
    assert r.status_code == 200
    assert len(r.json()) >= 3


def test_outreach_draft(client):
    r = client.post("/api/v1/outreach/draft", json={"contact_id": 211, "intent": "follow_up"})
    assert r.status_code == 200
    assert "body" in r.json()


def test_outreach_send(client):
    # Draft first to get a known ID.
    r0 = client.post("/api/v1/outreach/draft", json={"contact_id": 211, "intent": "follow_up"})
    msg_id = r0.json()["id"]
    r = client.post("/api/v1/outreach/send", json={"message_id": msg_id})
    assert r.status_code == 200
    assert r.json()["status"] == "sent"


# ── Fragments ────────────────────────────────────────────────────────────


def test_fragment_next_card(client):
    r = client.get("/_fragments/discover/next-card")
    assert r.status_code == 200
    assert 'id="discover-card"' in r.text or "No more matches" in r.text


def test_fragment_priority_actions(client):
    r = client.get("/_fragments/overview/priority-actions")
    assert r.status_code == 200


def test_fragment_email_signal(client):
    r = client.get("/_fragments/overview/email-signal")
    assert r.status_code == 200


def test_fragment_pipeline_strip(client):
    r = client.get("/_fragments/overview/pipeline-strip")
    assert r.status_code == 200
    assert "overview-pipeline" in r.text


def test_fragment_tracking_board(client):
    r = client.get("/_fragments/tracking/board")
    assert r.status_code == 200


def test_fragment_tracking_list(client):
    r = client.get("/_fragments/tracking/list")
    assert r.status_code == 200


def test_fragment_tracking_followup(client):
    r = client.get("/_fragments/tracking/followup-banner")
    assert r.status_code == 200


def test_fragment_outreach_app_detail(client):
    r = client.get("/_fragments/outreach/app-detail/2")
    assert r.status_code == 200
    assert "Anthropic" in r.text


def test_fragment_match_breakdown(client):
    r = client.get("/_fragments/discover/match-breakdown/101")
    assert r.status_code == 200


def test_fragment_tailored_bullets(client):
    r = client.get("/_fragments/apply/tailored-bullets/113")
    assert r.status_code == 200


def test_fragment_cover_letter_section_view(client):
    r = client.get("/_fragments/apply/cover-letter-section/13/intro")
    assert r.status_code == 200
    assert "INTRO" in r.text


def test_fragment_cover_letter_section_edit(client):
    r = client.get("/_fragments/apply/cover-letter-section/13/intro?mode=edit")
    assert r.status_code == 200
    assert "<form" in r.text or "<textarea" in r.text


def test_fragment_screener(client):
    r = client.get("/_fragments/apply/screener/13/817")
    assert r.status_code == 200


def test_modal_bullet_editor(client):
    r = client.get("/_modal/bullet-editor/1")
    assert r.status_code == 200
    assert "bullet-editor-modal" in r.text


def test_modal_add_by_url(client):
    r = client.get("/_modal/add-by-url")
    assert r.status_code == 200
    assert "add-by-url-modal" in r.text


def test_onboarding_step_fragment(client):
    """Plan 0.7.0.48 Wave 2 (2026-05-25): onboarding collapsed to single
    upload step. Step 1 still works; steps 2 + 3 are gone (404).
    """
    r1 = client.get("/_fragments/onboarding/step/1")
    assert r1.status_code == 200
    r2 = client.get("/_fragments/onboarding/step/2")
    assert r2.status_code == 404
    r3 = client.get("/_fragments/onboarding/step/3")
    assert r3.status_code == 404


# Plan 0.7.0.48 Wave 2 (2026-05-25): `/api/v1/extraction/upload` is no longer
# a stub — it now requires real-JWT auth + a parseable PDF. Happy-path coverage
# lives in `tests/test_extraction_upload.py`. The legacy stub-shape tests
# (`Reading your resume` SSE handoff + `?fail=1` synthetic 422) are deleted.
