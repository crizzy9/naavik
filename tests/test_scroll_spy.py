"""Plan 09a · Issue 9 — Profile right-rail anchor scroll-spy.

Confirms: nav advertises its target IDs via [data-anchor-targets], links carry
[data-anchor-link], and base.js wires an IntersectionObserver. Live scroll
behavior is exercised manually (no Playwright on NixOS yet — see paper-cut #3).
"""

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


def test_anchor_nav_carries_target_ids(client: TestClient, auth_cookies: dict[str, str]) -> None:
    """`<nav data-anchor-nav data-anchor-targets="summary,experience,...">`."""
    body = client.get("/profile", cookies=auth_cookies).text
    assert "data-anchor-nav" in body, "scroll-spy nav must carry data-anchor-nav"
    assert "data-anchor-targets=" in body, "scroll-spy nav must list its target IDs"
    # Targets should include the major Profile sections.
    assert "experience" in body
    assert "skills" in body


def test_anchor_links_carry_link_attribute(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """Each anchor `<a>` carries data-anchor-link='{id}' for JS to toggle is-active."""
    body = client.get("/profile", cookies=auth_cookies).text
    assert 'data-anchor-link="experience"' in body
    assert 'data-anchor-link="skills"' in body


def test_initial_active_is_first_anchor_not_hardcoded_experience(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """Initial `data-active-anchor` defaults to the first anchor, not hardcoded 'experience'."""
    body = client.get("/profile", cookies=auth_cookies).text
    # First Profile anchor is "summary" (per profile_ctx PROFILE_ANCHORS).
    assert 'data-active-anchor="summary"' in body, (
        "Initial active anchor should default to the first nav entry"
    )


def test_base_js_attaches_intersection_observer(client: TestClient) -> None:
    """base.js must register an IntersectionObserver on [data-anchor-nav]."""
    body = client.get("/static/base.js").text
    assert "attachScrollSpy" in body
    assert "IntersectionObserver" in body
    assert "data-anchor-nav" in body
