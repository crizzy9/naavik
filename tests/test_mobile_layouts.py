"""Plan 09a · Issue 10 — Mobile layout fixes (10.a–10.g)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


# ---- 10.a · Discover review mobile tabs ---------------------------------


def test_discover_review_has_mobile_tabs(client: TestClient, auth_cookies) -> None:
    body = client.get("/discover/101", cookies=auth_cookies).text
    assert "data-review-tabs" in body
    assert 'data-review-tab-trigger="jd"' in body
    assert 'data-review-tab-trigger="resume"' in body
    assert 'data-review-tab-trigger="cover"' in body
    assert 'data-review-tab-pane="jd"' in body
    assert 'data-review-tab-pane="resume"' in body
    assert 'data-review-tab-pane="cover"' in body


def test_discover_review_resume_pane_hidden_on_mobile(client: TestClient, auth_cookies) -> None:
    """Middle + right columns ship `hidden lg:flex` so they collapse on mobile."""
    body = client.get("/discover/101", cookies=auth_cookies).text
    # Resume pane wrapper must carry `hidden lg:flex`
    assert 'data-review-tab-pane="resume"' in body
    snippet_idx = body.find('data-review-tab-pane="resume"')
    snippet = body[snippet_idx : snippet_idx + 200]
    assert "hidden lg:flex" in snippet


# ---- 10.b · Onboarding min-h gated to lg+ -------------------------------


def test_onboarding_min_h_gated_to_lg(client: TestClient, auth_cookies) -> None:
    body = client.get("/onboarding?step=1", cookies=auth_cookies).text
    assert "lg:min-h-[520px]" in body, "Issue 10.b · onboarding min-h should be lg-only"
    # Bare `min-h-[520px]` must not appear on the step section.
    assert "rounded-xl p-7 min-h-[520px]" not in body


# ---- 10.c · Tracking board stacks on mobile -----------------------------


def test_tracking_board_stacks_on_mobile(client: TestClient, auth_cookies) -> None:
    body = client.get("/tracking", cookies=auth_cookies).text
    # `flex flex-col lg:flex-row` indicates vertical stack on mobile.
    assert "flex flex-col lg:flex-row" in body, (
        "Issue 10.c · tracking board must stack columns vertically on mobile"
    )


# ---- 10.e · Overview columns bound on desktop ---------------------------


def test_overview_columns_bound_on_desktop(client: TestClient, auth_cookies) -> None:
    body = client.get("/", cookies=auth_cookies).text
    assert "lg:max-h-[28rem]" in body, "Issue 10.e · overview columns should bound on desktop"
    assert "lg:overflow-y-auto" in body


# ---- 10.f · Profile editor drag-handle visible on mobile ----------------


def test_profile_editor_drag_handle_visible_on_mobile(client: TestClient, auth_cookies) -> None:
    body = client.get("/profile/edit", cookies=auth_cookies).text
    # Drag handle: opacity-100 default, lg:opacity-0 (hover-only on desktop).
    assert "drag-handle opacity-100 lg:opacity-0" in body, (
        "Issue 10.f · drag handle must be visible by default on mobile"
    )


# ---- 10.g · Outreach left pane min-h gated to lg ------------------------


def test_outreach_left_pane_min_h_gated_to_lg(client: TestClient, auth_cookies) -> None:
    body = client.get("/outreach", cookies=auth_cookies).text
    # The lg:min-h-[520px] should be present; bare min-h-[520px] should not be.
    assert "lg:min-h-[520px]" in body, "Issue 10.g · outreach left pane min-h should be lg-only"
