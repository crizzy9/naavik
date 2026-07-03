"""Plan 09a · Issue 8D — In-place expansion of Discover swipe card."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def test_discover_main_is_swap_target(client: TestClient, auth_cookies) -> None:
    """`/discover` wraps the queue grid in #discover-main for in-place expand."""
    body = client.get("/discover", cookies=auth_cookies).text
    assert 'id="discover-main"' in body, "Issue 8D · #discover-main must be the swap target"


def test_review_button_targets_inline_workspace(client: TestClient, auth_cookies) -> None:
    """P3 — Review & apply expands THAT job's workspace into #discover-main
    (restores the SCREENS.md § 7 plan-09a wiring; the plan-77 preview-card
    detour dumped the user back onto the queue)."""
    body = client.get("/discover", cookies=auth_cookies).text
    review_idx = body.find('id="discover-review-btn"')
    assert review_idx > 0
    snippet = body[review_idx : review_idx + 600]
    assert "/_fragments/discover/expanded/" in snippet, (
        "Review button must open the job's inline review workspace"
    )
    assert 'hx-target="#discover-main"' in snippet, (
        "Review button must swap the workspace into #discover-main"
    )


def test_expanded_fragment_returns_workspace_with_back_button(
    client: TestClient, auth_cookies
) -> None:
    """`/_fragments/discover/expanded/{id}` returns the workspace + Back button."""
    r = client.get("/_fragments/discover/expanded/101", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # Back to queue button
    assert "Back to queue" in body
    assert "/_fragments/discover/queue" in body
    assert 'hx-target="#discover-main"' in body
    # Workspace content — the three-column match analysis (WHAT THEY WANT
    # restored 2026-07 round 2) is the canonical workspace marker.
    assert "YOUR STRENGTHS" in body


def test_queue_fragment_returns_swipe_grid(client: TestClient, auth_cookies) -> None:
    """`/_fragments/discover/queue` returns the 2-col swipe grid."""
    r = client.get("/_fragments/discover/queue", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # Swipe card + action bar present
    assert 'id="discover-card"' in body
    assert 'id="discover-skip-btn"' in body
    assert 'id="discover-review-btn"' in body
    # Right rail content
    assert "Up next" in body
    # NOT a full HTML doc — fragment should not include <html> / <body>
    assert "<html" not in body
    assert "<body" not in body


def test_full_page_route_still_works(client: TestClient, auth_cookies) -> None:
    """`/discover/{id}` direct nav still returns the full page (link-shareable URL)."""
    r = client.get("/discover/101", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # Full page → has <html> / <body>
    assert "<html" in body
    assert "<body" in body
    # And the workspace
    assert "YOUR STRENGTHS" in body


def test_inline_fragment_links_to_full_page(client: TestClient, auth_cookies) -> None:
    """Inline fragment includes a 'open as full page' link to /discover/{id}."""
    r = client.get("/_fragments/discover/expanded/101", cookies=auth_cookies)
    body = r.text
    assert 'href="/discover/101"' in body
    assert "open as full page" in body
