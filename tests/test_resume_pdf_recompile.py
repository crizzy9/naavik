"""Workspace bullet toggle → debounced real PDF recompile (2026-07).

The toggle used to recompile inline and toast "PDF updated" unconditionally —
a compile failure 500'd, and rapid toggles piled up one synchronous Typst
compile per click. Now:

- POST .../resume-bullet/{app}/{bullet}/toggle persists the override, commits,
  and fires `resumeSelectionChanged` (NO inline compile, no "PDF updated"
  claim). The workspace's debounced listener collapses a toggle burst into
  one recompile call.
- POST .../resume-pdf/{app}/recompile runs the LLM-free Typst recompile and
  answers honestly: `resumePdfUpdated` on success, `resumePdfStale` + warning
  toast on compile failure or when nothing was generated yet.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


class _StubSession:
    def add(self, obj):  # noqa: ANN001
        pass

    async def commit(self):
        pass

    async def flush(self):
        pass

    async def rollback(self):
        pass


@pytest.fixture
def client_with_user():
    from fastapi.testclient import TestClient

    from api.auth import require_csrf
    from db.session import get_session
    from main import app
    from services.auth import require_authed_session

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False)

    async def _user_override():
        return user

    async def _csrf_override():
        return None

    async def _session_override():
        yield _StubSession()

    app.dependency_overrides[require_authed_session] = _user_override
    app.dependency_overrides[require_csrf] = _csrf_override
    app.dependency_overrides[get_session] = _session_override
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.pop(require_authed_session, None)
    app.dependency_overrides.pop(require_csrf, None)
    app.dependency_overrides.pop(get_session, None)


def _application(overrides: dict | None = None):
    return SimpleNamespace(
        id=11,
        user_id=42,
        deleted_at=None,
        submission_artifacts={"bullet_overrides": overrides} if overrides else {},
    )


def _doc(selected_ids=(5,), page_count=1):
    return SimpleNamespace(
        bullet_selection={"selected_ids": list(selected_ids)},
        page_count=page_count,
    )


def _toggle(client, application, *, doc=_doc(), recompile_mock=None):
    recompile_mock = recompile_mock or AsyncMock()
    with (
        patch(
            "services.applications.get_application",
            new=AsyncMock(return_value=application),
        ),
        patch("services.profile.owns_bullet", new=AsyncMock(return_value=True)),
        patch(
            "services.generation._latest_error_free_doc",
            new=AsyncMock(return_value=doc),
        ),
        patch(
            "services.generation.recompile_resume_from_selection",
            new=recompile_mock,
        ),
        patch(
            "ui.discover_review_ctx.tailored_bullet_groups",
            new=AsyncMock(return_value=[]),
        ),
    ):
        r = client.post("/_fragments/apply/resume-bullet/11/5/toggle")
    return r, recompile_mock


def test_toggle_persists_override_and_defers_recompile(client_with_user):
    application = _application()
    r, recompile_mock = _toggle(client_with_user, application)
    assert r.status_code == 200
    # Selected bullet 5 toggles OUT.
    assert application.submission_artifacts["bullet_overrides"]["5"] == "never_include"
    # No inline compile — the debounced listener owns that.
    recompile_mock.assert_not_awaited()
    trig = json.loads(r.headers["HX-Trigger"])
    assert trig.get("resumeSelectionChanged") is True
    assert "resumePdfUpdated" not in trig  # nothing was compiled yet
    assert "recompiling" in trig["showToast"]["text"].lower()


def test_toggle_twice_flips_back_before_recompile(client_with_user):
    """Consecutive toggles must alternate even while the doc blob is stale —
    the override map, not the last compiled selection, carries the truth."""
    application = _application()
    _toggle(client_with_user, application)
    assert application.submission_artifacts["bullet_overrides"]["5"] == "never_include"
    r, _ = _toggle(client_with_user, application)
    assert r.status_code == 200
    assert application.submission_artifacts["bullet_overrides"]["5"] == "always_include"


def test_toggle_without_generated_resume_409s(client_with_user):
    r, _ = _toggle(client_with_user, _application(), doc=None)
    assert r.status_code == 409


def _recompile(client, *, result=None, side_effect=None):
    mock = AsyncMock(return_value=result, side_effect=side_effect)
    with (
        patch(
            "services.applications.get_application",
            new=AsyncMock(return_value=_application()),
        ),
        patch(
            "services.settings_service.get_or_create",
            new=AsyncMock(return_value=SimpleNamespace()),
        ),
        patch("services.generation.recompile_resume_from_selection", new=mock),
    ):
        r = client.post("/_fragments/apply/resume-pdf/11/recompile")
    return r, mock


def test_recompile_success_announces_fresh_pdf(client_with_user):
    r, mock = _recompile(client_with_user, result=_doc(page_count=1))
    assert r.status_code == 204
    mock.assert_awaited_once()
    trig = json.loads(r.headers["HX-Trigger"])
    assert trig.get("resumePdfUpdated") is True
    assert trig["showToast"]["tone"] == "success"


def test_recompile_overflow_warns_honestly(client_with_user):
    r, _ = _recompile(client_with_user, result=_doc(page_count=2))
    trig = json.loads(r.headers["HX-Trigger"])
    assert trig.get("resumePdfUpdated") is True
    assert trig["showToast"]["tone"] == "warning"
    assert "2 pages" in trig["showToast"]["text"]


def test_recompile_failure_marks_preview_stale(client_with_user):
    from typst.compiler import TypstError

    r, _ = _recompile(client_with_user, side_effect=TypstError("boom"))
    assert r.status_code == 204
    trig = json.loads(r.headers["HX-Trigger"])
    assert trig.get("resumePdfStale") is True
    assert "resumePdfUpdated" not in trig  # never claim an update that failed
    assert trig["showToast"]["tone"] == "warning"


def test_recompile_with_nothing_generated_is_honest(client_with_user):
    r, _ = _recompile(client_with_user, result=None)
    trig = json.loads(r.headers["HX-Trigger"])
    assert trig.get("resumePdfStale") is True
    # Both "never generated" and "stale selection" funnel to the Regen CTA.
    assert "regen" in trig["showToast"]["text"].lower()


# ── PDF serving: recompiles overwrite the same path, so the routes must
# forbid caching — default FileResponse validators (mtime, 1s granularity)
# let browsers 304/heuristic-cache the pre-recompile bytes, which kept the
# embed showing the OLD render after an honest recompile. ─────────────────


def _pdf_get(client, tmp_path, url, kind):
    pdf = tmp_path / f"{kind}.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    doc = SimpleNamespace(kind=SimpleNamespace(value=kind), path=str(pdf))
    with (
        patch(
            "services.applications.get_application",
            new=AsyncMock(return_value=_application()),
        ),
        patch(
            "services.applications.latest_documents",
            new=AsyncMock(return_value=[doc]),
        ),
    ):
        return client.get(url)


def test_resume_pdf_is_served_no_store(client_with_user, tmp_path):
    r = _pdf_get(client_with_user, tmp_path, "/api/v1/applications/11/resume.pdf", "resume")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"


def test_cover_letter_pdf_is_served_no_store(client_with_user, tmp_path):
    r = _pdf_get(
        client_with_user, tmp_path, "/api/v1/applications/11/cover-letter.pdf", "cover_letter"
    )
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
