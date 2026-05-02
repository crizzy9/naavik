"""Plan 09a · Issue 4 — Typed dropdowns + human labels for application questions."""

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


# ---- Profile editor: dropdowns replace text inputs ----------------------

_EDIT_FIELDS = [
    "work_authorization",
    "visa_sponsorship_needed",
    "willing_to_relocate",
    "veteran_status",
    "disability_status",
    "race_ethnicity",
    "gender_identity",
]


def test_app_questions_render_as_selects(client: TestClient, auth_cookies: dict[str, str]) -> None:
    """Each enum-backed field must ship as a `<select>`, not `<input type=text>`."""
    body = client.get("/profile/edit", cookies=auth_cookies).text
    for field in _EDIT_FIELDS:
        assert f'name="{field}"' in body, f"{field} missing from /profile/edit"
        # `<select id="editor-{field}"` is the smoking-gun for typed dropdown.
        assert "<select" in body and f'id="editor-{field}"' in body, (
            f"{field} should render as a <select>, not <input>"
        )


def test_app_questions_have_practical_labels(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """Question labels must read like a real job application, not enum names."""
    body = client.get("/profile/edit", cookies=auth_cookies).text
    # Spot-check 3 of the rephrased questions per Q3 user direction.
    assert "ARE YOU AUTHORIZED TO WORK IN THE US?" in body
    assert "WILL YOU REQUIRE VISA SPONSORSHIP?" in body
    assert "ARE YOU OPEN TO RELOCATING?" in body


def test_select_options_use_human_labels(client: TestClient, auth_cookies: dict[str, str]) -> None:
    """Dropdown options must show human labels (e.g. 'H-1B Visa Holder', not 'h1b')."""
    body = client.get("/profile/edit", cookies=auth_cookies).text
    # Visa sponsorship — phrased per the plan's Q3 example.
    assert "Yes — Now" in body
    assert "Yes — In the Future" in body
    assert "No — sponsorship not needed" in body
    # Work auth — 'h1b' raw enum should NOT appear as user-visible text.
    assert "H-1B Visa Holder" in body


def test_select_autosave_uses_change_trigger(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """`<select>` autosave fires on `change`, not `blur changed`."""
    body = client.get("/profile/edit", cookies=auth_cookies).text
    # The select for work_authorization should carry hx-trigger="change..."
    assert 'hx-put="/api/v1/profile/work_authorization"' in body
    # Find the surrounding <select> tag and confirm it carries change-trigger.
    # The class string is large (Tailwind + inline SVG arrow), so widen the window.
    select_idx = body.find('id="editor-work_authorization"')
    assert select_idx > 0
    snippet = body[select_idx : select_idx + 2000]
    assert 'hx-trigger="change' in snippet, "select autosave should trigger on change"


# ---- Profile read-only: human labels on display ------------------------


def test_profile_read_only_displays_human_labels(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """Read-only profile must show human labels, not raw enum values."""
    body = client.get("/profile", cookies=auth_cookies).text
    # Seeded profile is Shyam — H1B + needs sponsorship now.
    assert "H-1B Visa Holder" in body
    assert "Yes — Now" in body
    # Raw enum strings should NOT appear as a value (they're allowed in form
    # `option value=...` HTML, but Profile is read-only — no `<option>` tags).
    # Sanity: profile page contains no `<option>` tags.
    assert "<option" not in body, (
        "Profile read-only view should not contain <option> tags (no forms)"
    )
