"""Plan 09a · Issue 1 — Lucide diagnostics + readyState fallback.

Asserts that base.js carries the new safety nets so future regressions get
caught at the test layer rather than surfacing only as missing icons.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def test_base_js_warns_when_lucide_missing(client: TestClient) -> None:
    """Silent guard must surface Lucide load failures to the console."""
    body = client.get("/static/base.js").text
    assert "[naavik] window.lucide missing" in body, (
        "Issue 1 · diagnostic warning must be in base.js"
    )


def test_base_js_handles_late_load(client: TestClient) -> None:
    """Initial paint must run even if DOMContentLoaded already fired."""
    body = client.get("/static/base.js").text
    assert "document.readyState !== 'loading'" in body, (
        "Issue 1 · readyState fallback must cover the post-DCL race"
    )
