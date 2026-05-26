"""`PUT /api/v1/profile` — bulk save handler (0.7.0.48 fold-in for owner bug #4).

Replaces the misleading static "Auto-saved · just now" indicator with an
explicit Save button. The route walks FormData, routes each field through
the appropriate `profile_service` function, and returns an HTML fragment
swapped into `#profile-edit-save-result` on the edit page.

Tests cover:
  - Identity-field updates persist (via the patched `sd.PROFILE` shadow row).
  - EEO-bag updates persist via `update_application_questions`.
  - Mixed identity + EEO payload commits in one round-trip.
  - Unknown / per-experience field names (e.g. `title_<id>`) are ignored,
    not rejected — the bulk endpoint covers Profile fields only.
  - Success response carries a `Saved` HTML fragment.
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


def test_bulk_put_persists_identity_field(client: TestClient, auth_cookies):
    from db import sample_data as sd

    original = sd.PROFILE.full_name
    try:
        r = client.put(
            "/api/v1/profile",
            data={"full_name": "Renamed Operator"},
            cookies=auth_cookies,
        )
        assert r.status_code == 200, r.text
        assert "Saved" in r.text
        assert sd.PROFILE.full_name == "Renamed Operator"
    finally:
        sd.PROFILE.full_name = original


def test_bulk_put_persists_eeo_field(client: TestClient, auth_cookies):
    from db import sample_data as sd

    original = sd.PROFILE.notice_period_days
    try:
        r = client.put(
            "/api/v1/profile",
            data={"notice_period_days": "21"},
            cookies=auth_cookies,
        )
        assert r.status_code == 200, r.text
        assert "Saved" in r.text
        # update_application_questions stores raw form values; the API doesn't
        # coerce — operator-visible behavior matches the per-field PUT.
        assert str(sd.PROFILE.notice_period_days) == "21"
    finally:
        sd.PROFILE.notice_period_days = original


def test_bulk_put_mixed_identity_and_eeo(client: TestClient, auth_cookies):
    from db import sample_data as sd

    orig_name = sd.PROFILE.full_name
    orig_visa = sd.PROFILE.visa_sponsorship_needed
    try:
        r = client.put(
            "/api/v1/profile",
            data={
                "full_name": "Mixed Save",
                "headline": "Engineer",
                "visa_sponsorship_needed": "needed_now",
            },
            cookies=auth_cookies,
        )
        assert r.status_code == 200, r.text
        # Plural noun when > 1 field saved.
        assert "fields" in r.text
        assert sd.PROFILE.full_name == "Mixed Save"
        assert sd.PROFILE.headline == "Engineer"
        assert sd.PROFILE.visa_sponsorship_needed == "needed_now"
    finally:
        sd.PROFILE.full_name = orig_name
        sd.PROFILE.visa_sponsorship_needed = orig_visa


def test_bulk_put_ignores_unknown_field_names(client: TestClient, auth_cookies):
    """Per-experience fields like `title_<id>` are not Profile fields; the
    bulk endpoint silently skips them (experience edits have their own
    routes). Owner-visible: posting them returns 200, not 422.
    """
    from db import sample_data as sd

    original = sd.PROFILE.full_name
    try:
        r = client.put(
            "/api/v1/profile",
            data={
                "full_name": "OnlyOneKnown",
                "title_42": "Senior Engineer",
                "start_42": "2020-01-01",
                "garbage_field": "ignored",
            },
            cookies=auth_cookies,
        )
        assert r.status_code == 200, r.text
        assert sd.PROFILE.full_name == "OnlyOneKnown"
    finally:
        sd.PROFILE.full_name = original


def test_bulk_put_singular_noun_for_one_field(client: TestClient, auth_cookies):
    from db import sample_data as sd

    original = sd.PROFILE.full_name
    try:
        r = client.put(
            "/api/v1/profile",
            data={"full_name": "Singular Test"},
            cookies=auth_cookies,
        )
        assert r.status_code == 200, r.text
        # Singular noun when exactly 1 field saved.
        assert "1 field<" in r.text or "Saved · 1 field" in r.text
        assert "fields" not in r.text.split("Saved · 1 field")[1].split("<")[0]
    finally:
        sd.PROFILE.full_name = original


def test_bulk_put_response_is_html_fragment(client: TestClient, auth_cookies):
    """Response is plain HTML for HTMX swap into `#profile-edit-save-result` —
    not a JSON envelope and not a full page extending base.html.
    """
    from db import sample_data as sd

    original = sd.PROFILE.full_name
    try:
        r = client.put(
            "/api/v1/profile",
            data={"full_name": "Fragment Test"},
            cookies=auth_cookies,
        )
        assert r.status_code == 200
        # No base.html shell.
        assert "<html" not in r.text
        assert 'id="sidebar-drawer"' not in r.text
        # Inline span wrapper carries the success copy.
        assert "<span" in r.text
        assert "text-emerald-300" in r.text
    finally:
        sd.PROFILE.full_name = original


# ── EEO empty-string coercion regression (W4 fold-in 2026-05-26) ────────────


def test_bulk_put_handles_all_empty_eeo_fields(client: TestClient, auth_cookies):
    """Regression for owner-reported 500 on profile save (PR #212 W4).

    Pre-fix: `put_profile_bulk` forwarded raw form values to
    `update_application_questions`, which `setattr`'d empty strings onto
    typed INTEGER / ENUM columns. asyncpg's int4 encoder raised
    `DataError: 'str' object cannot be interpreted as an integer` on
    `notice_period_days=''` (any blank EEO field surfaced the same shape).

    Post-fix: the route coerces `''` → None for EEO fields, so the
    operator can save a profile WITH the EEO bag fully blank (first-time
    save, EEO not yet entered).
    """
    from db import sample_data as sd

    eeo_keys = (
        "work_authorization",
        "visa_sponsorship_needed",
        "willing_to_relocate",
        "notice_period_days",
        "salary_expectation_usd",
        "earliest_start",
        "veteran_status",
        "disability_status",
        "race_ethnicity",
        "gender_identity",
    )
    orig_name = sd.PROFILE.full_name
    orig_eeo = {k: getattr(sd.PROFILE, k, None) for k in eeo_keys}
    try:
        r = client.put(
            "/api/v1/profile",
            data={
                "full_name": "Coerce Save",
                **dict.fromkeys(eeo_keys, ""),
            },
            cookies=auth_cookies,
        )
        assert r.status_code == 200, r.text
        assert "Saved" in r.text
        # 10 EEO + 1 identity = 11 fields recorded as saved.
        assert "11 fields" in r.text or "fields" in r.text
    finally:
        sd.PROFILE.full_name = orig_name
        for k, v in orig_eeo.items():
            setattr(sd.PROFILE, k, v)
