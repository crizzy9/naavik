"""Plan 09a · Issue 3 — Touch swipe pointer-event handler on Discover."""

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


def test_keys_js_registers_swipe_handler(client: TestClient) -> None:
    """`keys.js` must define `attachDiscoverSwipe` and bind pointer events."""
    body = client.get("/static/keys.js").text
    assert "attachDiscoverSwipe" in body
    assert "pointerdown" in body
    assert "pointermove" in body
    assert "pointerup" in body
    assert "pointerType === 'mouse'" in body, "mouse must stay on keyboard + buttons"


def test_swipe_handler_uses_renamed_button_ids(client: TestClient) -> None:
    """Handler clicks on the namespaced IDs landed in Issue 11."""
    body = client.get("/static/keys.js").text
    assert "discover-skip-btn" in body
    assert "discover-auto-apply-btn" in body
    assert "discover-save-btn" in body


def test_swipe_card_renders_three_stamps(client: TestClient, auth_cookies) -> None:
    """`swipe_card.html` ships SKIP / APPLY / SAVE stamps (CSS-revealed during drag)."""
    body = client.get("/discover", cookies=auth_cookies).text
    assert 'data-stamp="left"' in body
    assert 'data-stamp="right"' in body
    assert 'data-stamp="up"' in body
    assert ">SKIP<" in body
    assert ">APPLY<" in body
    assert ">SAVE<" in body


def test_styles_css_reveals_stamps_on_swipe_class(client: TestClient) -> None:
    """`.is-swipe-{dir}` on the card reveals the matching stamp via opacity."""
    body = client.get("/static/styles.css").text
    assert "is-swipe-left" in body
    assert "is-swipe-right" in body
    assert "is-swipe-up" in body


def test_interactions_doc_documents_touch_swipe() -> None:
    """INTERACTIONS.md must have § F.4 documenting the pattern."""
    with open("docs/design/INTERACTIONS.md", encoding="utf-8") as f:
        content = f.read()
    assert "F.4 Touch swipe conventions" in content
    assert "Pointer Events" in content
