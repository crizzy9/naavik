"""Tests for the `/_design/components` fixture route.

Plan 08 acceptance:
- With NAAVIK_DEBUG=1 → 200 with all 12 anchor IDs.
- Without NAAVIK_DEBUG → 404.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture
def client_debug(monkeypatch) -> TestClient:
    monkeypatch.setenv("NAAVIK_DEBUG", "1")
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def client_no_debug(monkeypatch) -> TestClient:
    monkeypatch.delenv("NAAVIK_DEBUG", raising=False)
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def test_fixture_renders_all_12_anchors(client_debug: TestClient) -> None:
    r = client_debug.get("/_design/components")
    assert r.status_code == 200
    body = r.text
    for i in range(1, 13):
        assert f'id="batch-{i}-' in body, f"batch-{i} anchor missing in fixture"


def test_fixture_no_arbitrary_hex_in_components(client_debug: TestClient) -> None:
    """Sanity check: rendered fixture should contain zero arbitrary Tailwind hex."""
    import re

    r = client_debug.get("/_design/components")
    # Allow Tailwind's `#xxx` arbitrary value pattern only if it's not in a class.
    matches = re.findall(r'class="[^"]*\[#[0-9a-fA-F]', r.text)
    assert matches == [], f"Found arbitrary Tailwind hex in classes: {matches[:3]}"


def test_fixture_404_without_debug(client_no_debug: TestClient) -> None:
    # Make absolutely sure NAAVIK_DEBUG isn't leaking.
    assert "NAAVIK_DEBUG" not in os.environ
    r = client_no_debug.get("/_design/components")
    assert r.status_code == 404


def test_fixture_includes_batch_section_titles(client_debug: TestClient) -> None:
    r = client_debug.get("/_design/components")
    body = r.text
    # Sanity-check a few headings.
    assert "Atomics" in body
    assert "Onboarding" in body
    assert "Tracking" in body
    assert "Skeletons" in body
