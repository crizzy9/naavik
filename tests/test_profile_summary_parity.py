"""Profile summary — view/edit parity (2026-07 follow-up).

Parsed resumes often populate only `summary_short`, leaving `summary_full`
an empty string. The view page falls back (`summary_full or summary_short`);
the edit form must show the SAME text, not an empty textarea that reads as
data loss.
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


def test_edit_summary_falls_back_to_summary_short(client, auth_cookies, monkeypatch):
    """summary_full == "" → the edit textarea shows summary_short instead."""
    from db import sample_data

    monkeypatch.setattr(sample_data.PROFILE, "summary_full", "")

    body = client.get("/profile/edit", cookies=auth_cookies).text
    assert sample_data.PROFILE.summary_short[:40] in body


def test_edit_summary_prefers_summary_full_when_present(client, auth_cookies):
    from db import sample_data

    body = client.get("/profile/edit", cookies=auth_cookies).text
    assert sample_data.PROFILE.summary_full[:40] in body
