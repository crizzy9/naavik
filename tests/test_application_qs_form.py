"""Plan 09a · Issue 4 — Typed dropdowns + human labels for application questions."""

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


def test_profile_edit_selects_have_no_per_field_autosave(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """0.7.0.48 fold-in for owner bug #4: per-field autosave is OFF on the
    profile editor. Fields submit via the explicit Save button (parent
    `#profile-edit-form` PUTs `/api/v1/profile`). The misleading static
    "Auto-saved · just now" indicator is gone.
    """
    body = client.get("/profile/edit", cookies=auth_cookies).text
    # No per-field PUTs anywhere in the profile editor form.
    assert 'hx-put="/api/v1/profile/work_authorization"' not in body
    assert 'hx-put="/api/v1/profile/visa_sponsorship_needed"' not in body
    assert 'hx-put="/api/v1/profile/full_name"' not in body
    # The bulk PUT form is present.
    assert 'hx-put="/api/v1/profile"' in body
    assert 'data-testid="profile-edit-save"' in body


def test_editor_field_select_uses_change_trigger_when_autosave_enabled() -> None:
    """The select-autosave-on-change wiring is preserved for OTHER consumers
    of `editor_field.html` that opt into autosave (e.g. settings tabs). When
    `autosave_enabled=true` + `type="select"`, the partial emits
    `hx-trigger="change delay:200ms"`. Direct template render, no HTTP.
    """
    from jinja2 import ChainableUndefined, Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader("src/ui/templates"),
        autoescape=True,
        undefined=ChainableUndefined,
    )
    tmpl = env.get_template("components/editor_field.html")
    out = tmpl.render(
        label="WORK AUTH",
        name="work_authorization",
        value="h1b",
        type="select",
        options=[("h1b", "H-1B Visa Holder"), ("citizen", "US Citizen")],
        autosave_enabled=True,
    )
    assert 'hx-put="/api/v1/profile/work_authorization"' in out
    assert 'hx-trigger="change delay:200ms"' in out


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
