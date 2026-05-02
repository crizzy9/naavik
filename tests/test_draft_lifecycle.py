"""DRAFT state-machine tests (plan 09 § I).

Per plan 09:
- GET /discover/{id} creates a DRAFT for a new (user, job) (eager mode).
- GET /discover/{id} renders the lazy CTA when eager_review_generation=False
  (and no DRAFT exists yet).
- POST /api/v1/applications/{id}/submit flips DRAFT → APPLIED.
- DELETE /api/v1/applications/{id}/discard flips DRAFT → CLOSED with
  closed_reason=withdrawn_by_me.
- Submitting with unreviewed required screeners returns 409.
- DRAFTs with submission_artifacts.last_failure surface in the stuck queue.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


@pytest.fixture(autouse=True)
def _restore_application_state():
    """Snapshot + restore in-memory APPLICATIONS / SCREENER_ANSWERS state so the
    lifecycle tests don't pollute count-based assertions in other test files.
    """
    from db import sample_data as sd

    apps_snapshot = [a.model_copy(deep=True) for a in sd.APPLICATIONS]
    screen_snapshot = [s.model_copy(deep=True) for s in sd.SCREENER_ANSWERS]
    settings_eager = sd.SETTINGS.eager_review_generation
    yield
    sd.APPLICATIONS.clear()
    sd.APPLICATIONS.extend(apps_snapshot)
    sd.SCREENER_ANSWERS.clear()
    sd.SCREENER_ANSWERS.extend(screen_snapshot)
    sd.SETTINGS.eager_review_generation = settings_eager


def test_eager_visit_creates_draft(client, auth_cookies):
    """GET /discover/{job_id} for a job without an Application creates a DRAFT."""
    from db import sample_data as sd

    # Pick a job from the queue that doesn't yet have an Application.
    candidate = None
    for j in sd.JOBS:
        if j.id < 100:
            continue
        if not any(a.job_id == j.id for a in sd.APPLICATIONS):
            candidate = j
            break
    assert candidate is not None, "no candidate job without app"

    n_before = len(sd.APPLICATIONS)
    sd.SETTINGS.eager_review_generation = True
    r = client.get(f"/discover/{candidate.id}", cookies=auth_cookies)
    assert r.status_code == 200
    n_after = len(sd.APPLICATIONS)
    assert n_after == n_before + 1, "DRAFT not created on eager visit"
    new_app = sd.APPLICATIONS[-1]
    assert new_app.status.value == "DRAFT"
    assert new_app.job_id == candidate.id
    # Cleanup so other tests aren't affected.
    sd.APPLICATIONS.remove(new_app)


def test_lazy_visit_shows_cta_no_draft(client, auth_cookies):
    """When eager_review_generation=False AND no app exists, lazy CTA renders
    without creating a DRAFT.
    """
    from db import sample_data as sd

    candidate = None
    for j in sd.JOBS:
        if j.id < 100:
            continue
        if not any(a.job_id == j.id for a in sd.APPLICATIONS):
            candidate = j
            break
    assert candidate is not None

    sd.SETTINGS.eager_review_generation = False
    n_before = len(sd.APPLICATIONS)
    r = client.get(f"/discover/{candidate.id}", cookies=auth_cookies)
    assert r.status_code == 200
    assert "Tailor for this job" in r.text
    assert "Submit application" not in r.text
    assert len(sd.APPLICATIONS) == n_before
    # Restore eager mode.
    sd.SETTINGS.eager_review_generation = True


def test_submit_with_unreviewed_screeners_returns_409(client):
    """Mercury DRAFT (#13) has 1 unreviewed required screener — submit must 409."""
    from db import sample_data as sd

    # Reset Mercury's screener to unreviewed.
    a = next(s for s in sd.SCREENER_ANSWERS if s.id == 817)
    a.reviewed_at = None
    r = client.post("/api/v1/applications/13/submit")
    assert r.status_code == 409


def test_submit_after_review_succeeds(client):
    """After reviewing all required screeners, submit flips DRAFT → APPLIED."""
    from db import sample_data as sd
    from models.enums import ApplicationStatus

    # Make sure Mercury's app is DRAFT
    app = next(a for a in sd.APPLICATIONS if a.id == 13)
    app.status = ApplicationStatus.DRAFT
    app.applied_at = None

    # Mark all required screeners reviewed
    for s in sd.SCREENER_ANSWERS:
        if s.application_id == 13 and s.required:
            s.reviewed_at = datetime.now(UTC)

    r = client.post("/api/v1/applications/13/submit")
    assert r.status_code == 204
    assert r.headers.get("hx-redirect") == "/tracking"

    # Re-read app
    app = next(a for a in sd.APPLICATIONS if a.id == 13)
    assert app.status == ApplicationStatus.APPLIED
    assert app.applied_at is not None


def test_discard_flips_draft_to_closed(client):
    """DELETE /api/v1/applications/{id}/discard flips DRAFT → CLOSED with
    withdrawn_by_me + sets deleted_at.
    """
    from db import sample_data as sd
    from models.enums import ApplicationStatus, ClosedReason

    # Use the Modal stuck DRAFT (#14) — make sure it's DRAFT first.
    app = next(a for a in sd.APPLICATIONS if a.id == 14)
    app.status = ApplicationStatus.DRAFT
    app.deleted_at = None
    app.closed_reason = None

    r = client.delete("/api/v1/applications/14/discard")
    assert r.status_code == 204
    assert r.headers.get("hx-redirect") == "/discover"

    app = next(a for a in sd.APPLICATIONS if a.id == 14)
    assert app.status == ApplicationStatus.CLOSED
    assert app.closed_reason == ClosedReason.WITHDRAWN_BY_ME
    assert app.deleted_at is not None


def test_stuck_drafts_appear_in_discover_right_rail(client, auth_cookies):
    """DRAFT with submission_artifacts.last_failure surfaces in the Stuck-in-queue card."""
    from db import sample_data as sd
    from models.enums import ApplicationStatus

    # Seed a stuck-failed DRAFT if none currently exist (e.g. discard test ran first).
    if not any(
        a.status == ApplicationStatus.DRAFT
        and a.submission_artifacts
        and a.submission_artifacts.get("last_failure")
        for a in sd.APPLICATIONS
    ):
        # Restore Modal #14 to DRAFT-with-failure state.
        app = next(a for a in sd.APPLICATIONS if a.id == 14)
        app.status = ApplicationStatus.DRAFT
        app.closed_reason = None
        app.deleted_at = None
        app.submission_artifacts = {
            "retry_count": 2,
            "last_failure": {
                "kind": "auth_required",
                "message": "session expired",
                "captured_at": datetime.now(UTC).isoformat(),
            },
        }

    r = client.get("/discover", cookies=auth_cookies)
    assert r.status_code == 200
    assert "Stuck in queue" in r.text
