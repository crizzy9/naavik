"""Plan 09a follow-up — Discover surface redesign.

User feedback after the first 09a pass:
- Buttons too big and have duplicate text below — must be small inline buttons
  with no keyboard-hint strip
- Card too small to show most details — bumped from 560px to 720px on lg
- Mobile experience must be touch-only (no buttons / no right rail), with
  tap-to-expand for review
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


def test_action_bar_hidden_on_mobile(client: TestClient, auth_cookies) -> None:
    """The desktop action bar must be `hidden lg:flex` so mobile shows no buttons."""
    body = client.get("/discover", cookies=auth_cookies).text
    assert "hidden lg:flex items-center justify-center gap-2" in body, (
        "Discover action bar must be hidden on mobile (touch-only experience)"
    )


def test_action_bar_has_no_duplicate_keyboard_hints(client: TestClient, auth_cookies) -> None:
    """Keyboard hint strip below buttons (which duplicated button labels) is gone."""
    body = client.get("/discover", cookies=auth_cookies).text
    # The old strip rendered "skip · auto-apply · save · review" labels under
    # the bar. None of those subtitle phrasings should appear.
    assert ">skip<" not in body or "skip · auto-apply" not in body
    # Specifically, the keyboard_hints partial (which produced the strip) is
    # not used in the action bar anymore.
    assert "components/keyboard_hints.html" not in body


def test_buttons_are_inline_not_stacked(client: TestClient, auth_cookies) -> None:
    """Buttons render as small inline pills (icon + label horizontal), not stacked."""
    body = client.get("/discover", cookies=auth_cookies).text
    # Smoking gun: the new class `inline-flex items-center gap-1.5 px-3 py-2`
    # is on each swipe action button.
    assert "inline-flex items-center gap-1.5 px-3 py-2" in body
    # The old stacked layout (`flex flex-col items-center justify-center gap-2 px-6 py-4`)
    # must NOT be on the action button.
    review_idx = body.find('id="discover-review-btn"')
    assert review_idx > 0
    snippet = body[review_idx : review_idx + 800]
    assert "flex-col" not in snippet, "Review button must be inline, not stacked"


def test_swipe_card_fills_desktop_width(client: TestClient, auth_cookies) -> None:
    """Card has no max-w cap on lg+ — fills the available column width."""
    body = client.get("/discover", cookies=auth_cookies).text
    assert "max-w-[460px] lg:max-w-none" in body, (
        "Issue: card must fill available desktop real estate (no max-w cap on lg+)"
    )


def test_card_has_tap_to_expand_data(client: TestClient, auth_cookies) -> None:
    """Card carries data-discover-card + cursor-pointer for tap-to-expand."""
    body = client.get("/discover", cookies=auth_cookies).text
    assert "data-discover-card" in body
    assert "cursor-pointer" in body
    # The keys.js handler must wire a click listener that fires the review btn.
    keys = client.get("/static/keys.js").text
    assert "discover-review-btn" in keys
    # Tap detection threshold for touch swipes
    assert "TAP_THRESHOLD" in keys or "tap" in keys.lower()


def test_right_rail_hidden_on_mobile(client: TestClient, auth_cookies) -> None:
    """Up Next / Saved / Tip rail hides on mobile per user redesign request."""
    body = client.get("/discover", cookies=auth_cookies).text
    # The right-rail aside must carry `hidden lg:flex`
    assert 'class="hidden lg:flex flex-col gap-4 min-w-0"' in body
