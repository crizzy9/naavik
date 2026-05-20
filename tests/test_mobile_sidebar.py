"""Plan 09a · Issue 2 — Mobile sidebar drawer.

Confirms that the close affordance lives INSIDE the open drawer (since the
hamburger outside is occluded by `<aside>` z-40 > z-30) and that aria-expanded
+ aria-controls wiring is present.
"""

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


def test_sidebar_has_close_button_inside_drawer(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """A second [data-sidebar-toggle] must live inside the <aside>."""
    body = client.get("/", cookies=auth_cookies).text
    # Two toggles total: hamburger outside + close inside.
    assert body.count("data-sidebar-toggle") == 2, (
        "Issue 2 · expected hamburger + in-drawer close button (both data-sidebar-toggle)"
    )
    # Inside-drawer close button uses the lucide x icon and aria-label.
    assert 'aria-label="Close sidebar"' in body
    assert 'data-lucide="x"' in body


def test_sidebar_aria_expanded_wired(client: TestClient, auth_cookies: dict[str, str]) -> None:
    """Hamburger button advertises aria-expanded + aria-controls for a11y."""
    body = client.get("/", cookies=auth_cookies).text
    assert 'aria-expanded="false"' in body
    assert 'aria-controls="sidebar-drawer"' in body
    assert 'id="sidebar-drawer"' in body


def test_base_js_syncs_aria_expanded(client: TestClient) -> None:
    """base.js click handler must update aria-expanded on toggle."""
    body = client.get("/static/base.js").text
    assert "syncSidebarAria" in body, "Issue 2 · aria sync helper must be wired"
    assert "aria-expanded" in body


def test_base_js_syncs_aria_on_swap(client: TestClient) -> None:
    """0.2.2.03 · aria sync must also fire on htmx:afterSwap so navigation
    (back-button, hx-boost) re-syncs the hamburger button's aria-expanded
    even when no click event fires."""
    body = client.get("/static/base.js").text
    # Both substrings must coexist in the same module so the wiring is
    # demonstrably in place. Proximity asserted via the substring count of
    # syncSidebarAria appearing after the swap-listener registration.
    assert "htmx:afterSwap" in body
    assert "syncSidebarAria" in body
    # The new wiring registers syncSidebarAria as a listener (not just calls
    # it inline) — guard against accidental removal.
    assert "addEventListener('htmx:afterSwap', syncSidebarAria)" in body, (
        "0.2.2.03 · syncSidebarAria must be registered as htmx:afterSwap listener"
    )
