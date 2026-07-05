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


@pytest.fixture(autouse=True)
def _override_csrf():
    """Plan 0.7.0.48 hacker F6 (2026-06-25): `put_profile_bulk` now enforces
    `require_csrf` (matches `put_llm` / `put_notifications` / `put_account`).
    Override the dep here so the existing surface-shape tests don't need to
    craft a double-submit token roundtrip per request. The dedicated
    CSRF-enforcement regression at the bottom of this file pops the override
    via a wrapper decorator to exercise the real gate.
    """
    from api.auth import require_csrf
    from main import app

    def _csrf_pass() -> None:
        return None

    app.dependency_overrides[require_csrf] = _csrf_pass
    yield
    app.dependency_overrides.pop(require_csrf, None)


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


# ── CSRF enforcement regression — plan 0.7.0.48 hacker F6 fold-in 2026-06-25 ──


def _without_csrf_override(test_fn):
    """Decorator: temporarily pop the autouse fixture's `require_csrf` override
    so the wrapped test exercises the real gate. Restored after the test runs
    (the autouse cleanup re-pops anyway, so this is safe). Mirrors the
    pattern in `tests/test_settings_save_fragment_response.py`.
    """
    import functools

    @functools.wraps(test_fn)
    def wrapper(*args, **kwargs):
        from api.auth import require_csrf
        from main import app

        saved = app.dependency_overrides.pop(require_csrf, None)
        try:
            return test_fn(*args, **kwargs)
        finally:
            if saved is not None:
                app.dependency_overrides[require_csrf] = saved

    return wrapper


@_without_csrf_override
def test_bulk_put_csrf_enforced(client: TestClient, auth_cookies):
    """Regression: `PUT /api/v1/profile` MUST gate on `require_csrf`. Pre-fix
    this was the lone state-changing settings/profile mutation without CSRF
    after the W4 fold-in shipped `require_csrf` on every sibling. The hacker
    F6 finding on PR #212 flagged the asymmetry. Test asserts the gate fires
    when no CSRF token is present (cookies + headers stripped of CSRF).
    """
    r = client.put(
        "/api/v1/profile",
        data={"full_name": "Should Not Persist"},
        cookies=auth_cookies,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
    assert "CSRF" in r.text


# ── Chip editors (2026-07): repeated form keys accumulate ───────────────────
# Project/OSS tags became vocab toggle-chips and skill items a push-chip
# editor — both submit ONE input per value under the same
# `<prefix>_<field>_<id>` name plus an empty sentinel (so zero chips still
# clears). Legacy single-CSV inputs keep parsing.


def test_collect_entity_edits_accumulates_repeated_chip_keys():
    from api.profile import _collect_entity_edits

    edits = _collect_entity_edits(
        [
            ("skill_items_7", ""),  # sentinel
            ("skill_items_7", "Python"),
            ("skill_items_7", "Go"),
            ("skill_items_7", "Python"),  # dup collapses
            ("proj_tags_3", ""),
            ("proj_tags_3", "genai"),
            ("proj_tags_3", "backend"),
            ("oss_tags_4", "platform, devops"),  # legacy CSV still splits
        ]
    )
    assert edits[("skill", 7)]["items"] == ["Python", "Go"]
    assert edits[("proj", 3)]["tags"] == ["genai", "backend"]
    assert edits[("oss", 4)]["tags"] == ["platform", "devops"]


def test_collect_entity_edits_sentinel_only_clears():
    from api.profile import _collect_entity_edits

    edits = _collect_entity_edits([("skill_items_7", ""), ("proj_tags_3", "")])
    assert edits[("skill", 7)]["items"] == []
    assert edits[("proj", 3)]["tags"] == []


def test_bulk_put_skill_items_chips_reach_service(client: TestClient, auth_cookies, monkeypatch):
    """Repeated `skill_items_<id>` inputs (chip editor) arrive at
    `update_skill` as ONE accumulated list, sentinel filtered out."""
    from unittest.mock import AsyncMock

    from services import profile as profile_service

    update = AsyncMock()
    monkeypatch.setattr(profile_service, "owns_skill", AsyncMock(return_value=True))
    monkeypatch.setattr(profile_service, "update_skill", update)
    r = client.put(
        "/api/v1/profile",
        data={"skill_items_1": ["", "Rust", "Zig"]},
        cookies=auth_cookies,
    )
    assert r.status_code == 200, r.text
    assert update.call_args.kwargs["items"] == ["Rust", "Zig"]


def test_bulk_put_project_tag_chips_enforce_vocab(client: TestClient, auth_cookies, monkeypatch):
    """Checkbox-chip `proj_tags_<id>` submissions accumulate and are filtered
    to the 9-tag vocabulary before reaching `update_project`."""
    from unittest.mock import AsyncMock

    from services import profile as profile_service

    update = AsyncMock()
    monkeypatch.setattr(profile_service, "owns_project", AsyncMock(return_value=True))
    monkeypatch.setattr(profile_service, "update_project", update)
    r = client.put(
        "/api/v1/profile",
        data={"proj_tags_1": ["", "genai", "backend", "not-a-vocab-tag"]},
        cookies=auth_cookies,
    )
    assert r.status_code == 200, r.text
    assert update.call_args.kwargs["tags"] == ["genai", "backend"]
