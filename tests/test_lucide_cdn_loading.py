"""Plan 51 · 0.2.2.02 — Lucide CDN with self-hosted fallback.

Restores jsDelivr CDN as the primary Lucide source while keeping the vendored
`/static/lucide.min.js` as `onerror` fallback. The vendored version pin must
match the CDN tag so the UMD global shape stays compatible.
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


def test_base_html_loads_lucide_from_jsdelivr(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """Primary Lucide source must be jsDelivr (CDN) pinned to v0.469.0."""
    body = client.get("/", cookies=auth_cookies).text
    assert "cdn.jsdelivr.net/npm/lucide" in body, (
        "0.2.2.02 · base.html must load Lucide from jsDelivr CDN"
    )
    assert "lucide@0.469.0" in body, (
        "0.2.2.02 · Lucide CDN URL must pin to v0.469.0 (matches vendored fallback banner)"
    )


def test_base_html_falls_back_to_self_hosted_lucide(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """`onerror` handler must reference `/static/lucide.min.js` so the local
    file kicks in when the CDN fails."""
    body = client.get("/", cookies=auth_cookies).text
    assert "onerror" in body, "0.2.2.02 · CDN script tag must carry onerror fallback"
    assert "/static/lucide.min.js" in body, (
        "0.2.2.02 · onerror fallback must point at the vendored /static/lucide.min.js"
    )


def test_static_lucide_min_js_still_served(client: TestClient) -> None:
    """The vendored file remains served by the FastAPI static mount so the
    `onerror` fallback resolves."""
    response = client.get("/static/lucide.min.js")
    assert response.status_code == 200, (
        "0.2.2.02 · /static/lucide.min.js must remain served as the fallback"
    )
    # Vendored file's version banner must match the CDN pin so the UMD shape is identical.
    assert "v0.469.0" in response.text[:200], (
        "0.2.2.02 · vendored lucide.min.js banner must match the v0.469.0 CDN pin"
    )
