"""Tracking · Jobs library (UX-quality session).

Tracking is the single lifecycle surface: the Pipeline tab keeps the
board/list of applications; the Jobs library tab shows EVERY Job with
queue-state facets, search, and row actions (queue / save / skip /
restore).
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
def cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def test_tracking_page_has_tabs(client, cookies):
    r = client.get("/tracking", cookies=cookies)
    assert r.status_code == 200
    assert 'data-testid="tracking-tabs"' in r.text
    assert "Jobs library" in r.text


def test_library_tab_renders_table_with_facets(client, cookies):
    r = client.get("/tracking?tab=library", cookies=cookies)
    assert r.status_code == 200
    assert 'data-testid="tracking-library"' in r.text
    assert 'data-testid="library-facet-all"' in r.text
    assert 'data-testid="library-facet-saved"' in r.text
    assert 'data-testid="library-facet-ready_to_submit"' in r.text
    assert 'data-testid="library-search"' in r.text


def test_library_fragment_is_panel_not_page(client, cookies):
    r = client.get("/_fragments/tracking/library", cookies=cookies)
    assert r.status_code == 200
    assert 'data-testid="tracking-library"' in r.text
    assert "<html" not in r.text.lower()


def test_library_state_facet_filters(client, cookies):
    from db import sample_data as sd
    from models.enums import JobQueueState

    saved_count = len([j for j in sd.JOBS if j.queue_state == JobQueueState.SAVED])
    r = client.get("/_fragments/tracking/library?state=saved", cookies=cookies)
    assert r.status_code == 200
    assert r.text.count("library-row-") == saved_count


def test_library_unknown_action_404(client, cookies):
    r = client.post(
        "/_fragments/tracking/library/1/explode",
        cookies={**cookies, "naavik_csrf": "t" * 40},
        headers={"X-CSRF-Token": "t" * 40},
    )
    assert r.status_code == 404
