"""Plan 53 § D (0.2.4.04) — show drafts filter on Tracking page tests."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ["NAAVIK_PERSISTENCE"] = "memory"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    return c


def test_tracking_renders_show_drafts_toggle(client: TestClient) -> None:
    """The header carries the `Show drafts` chip with HTMX hx-include."""
    r = client.get("/tracking")
    assert r.status_code == 200
    body = r.text
    assert 'data-testid="tracking-show-drafts"' in body
    assert 'name="show_drafts"' in body
    assert "Show drafts" in body
    assert "hx-include=\"[name='show_closed'],[name='show_drafts']\"" in body


def test_tracking_show_drafts_default_off_unchecked(client: TestClient) -> None:
    """Default (no query param) renders the checkbox unchecked."""
    r = client.get("/tracking")
    assert r.status_code == 200
    # checkbox should NOT have `checked` attribute when show_drafts=0
    assert 'name="show_drafts" value="1"' in r.text
    # The `checked` attribute only appears with show_drafts=1
    body_chunk = r.text
    pre_check = body_chunk.split('name="show_drafts"', 1)[1].split(">", 1)[0]
    assert "checked" not in pre_check


def test_tracking_show_drafts_query_param_checks_box(client: TestClient) -> None:
    """`?show_drafts=1` renders the checkbox as `checked`."""
    r = client.get("/tracking?show_drafts=1")
    assert r.status_code == 200
    body = r.text
    pre_check = body.split('name="show_drafts"', 1)[1].split(">", 1)[0]
    assert "checked" in pre_check


def test_tracking_show_drafts_0_omits_draft_cards(client: TestClient) -> None:
    """`?show_drafts=0` does NOT render DRAFT applications in the board."""
    r = client.get("/tracking?show_drafts=0")
    assert r.status_code == 200
    body = r.text
    # Default board has 4 visible status columns; DRAFT does NOT appear
    assert 'data-column="DRAFT"' not in body


def test_tracking_show_drafts_1_includes_drafts(client: TestClient) -> None:
    """`?show_drafts=1` exposes draft applications on the board."""
    import asyncio

    from db import sample_data as sd

    async def _drafts():
        return await sd.draft_applications()

    drafts = asyncio.run(_drafts())
    if not drafts:
        pytest.skip("no draft applications in sample_data fixture")

    r = client.get("/tracking?show_drafts=1")
    assert r.status_code == 200
    # At least one DRAFT row's company should be present on the page somewhere.
    # Cards render `role` + `company` per tracking_card.html. Mercury / Modal
    # are common DRAFT seeds in sample_data.
    found = any(d.company in r.text or d.role in r.text for d in drafts)
    assert found, "draft fixtures must surface on the tracking page when show_drafts=1"


def test_tracking_fragment_board_show_drafts_passthru(client: TestClient) -> None:
    """`/_fragments/tracking/board?show_drafts=1` propagates the filter."""
    r = client.get("/_fragments/tracking/board?show_drafts=1")
    assert r.status_code == 200


def test_tracking_fragment_list_show_drafts_passthru(client: TestClient) -> None:
    """`/_fragments/tracking/list?show_drafts=1` propagates the filter."""
    r = client.get("/_fragments/tracking/list?show_drafts=1")
    assert r.status_code == 200


def test_build_tracking_ctx_show_drafts_merges_drafts() -> None:
    """`build_tracking_ctx(show_drafts=True)` merges draft_applications into visible."""
    import asyncio

    from db import sample_data as sd
    from ui.tracking_ctx import build_tracking_ctx

    async def _run():
        base = await build_tracking_ctx(show_drafts=False)
        with_drafts = await build_tracking_ctx(show_drafts=True)
        drafts = await sd.draft_applications()
        return base, with_drafts, drafts

    base, with_drafts, drafts = asyncio.run(_run())
    if drafts:
        assert len(with_drafts["rows"]) > len(base["rows"]), (
            "show_drafts=True must add draft rows when fixtures exist"
        )
    assert base["show_drafts"] is False
    assert with_drafts["show_drafts"] is True


def test_build_tracking_ctx_show_drafts_default_false() -> None:
    """Default show_drafts is False."""
    import asyncio

    from ui.tracking_ctx import build_tracking_ctx

    ctx = asyncio.run(build_tracking_ctx())
    assert ctx["show_drafts"] is False
