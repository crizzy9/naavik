"""Plan 09a follow-up — idempotency guards on base.js + keys.js.

Why: hx-boost re-executes <script src="/static/...js"> on every navigation. Without
the guard, every listener piles up — the sidebar click handler in particular ends
up running N times after N navigations, which made the toggle "die" after the user
navigated to a new page.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def test_base_js_has_idempotency_guard(client: TestClient) -> None:
    body = client.get("/static/base.js").text
    assert "_naavikBaseLoaded" in body, (
        "base.js must guard against hx-boost re-execution stacking listeners"
    )
    # The early-return on re-run should still paint icons for the new content.
    assert "lucide.createIcons" in body


def test_keys_js_has_idempotency_guard(client: TestClient) -> None:
    body = client.get("/static/keys.js").text
    assert "_naavikKeysLoaded" in body, (
        "keys.js must guard against hx-boost re-execution stacking listeners"
    )


def test_lucide_is_self_hosted(client: TestClient) -> None:
    """Lucide UMD bundle must be served from /static (not unpkg CDN)."""
    r = client.get("/static/lucide.min.js")
    assert r.status_code == 200
    assert "createIcons" in r.text, "lucide bundle must export createIcons"


def test_base_html_references_self_hosted_lucide(
    client: TestClient,
) -> None:
    body = client.get("/login").text
    assert 'src="/static/lucide.min.js"' in body
    assert "unpkg.com/lucide" not in body, "should not load Lucide from unpkg"
