"""Resume PDF upload — plan 0.7.0.48 Wave 2 (2026-05-25).

Pins the happy-path + validation surfaces of `/api/v1/extraction/upload`:

  - Real PDF body → 200 + confirmation partial + file written under
    `<data_dir>/uploads/<user_id>/<utc-ts>.pdf`.
  - Non-PDF content-type → 422 (no file written).
  - Empty body → 422.
  - >10 MB body → 413.

The endpoint requires real-JWT auth via `require_password_complete`; we
override the dep with a SimpleNamespace stub user (same pattern as
`tests/test_applications_idor.py`).
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_DEBUG", "1")


def _minimal_pdf_bytes() -> bytes:
    """Return a valid minimal PDF that pdfplumber can open.

    Built via pdfplumber's underlying `pdfminer.six` round-trip — generates
    a 1-page blank PDF programmatically rather than embedding a binary blob
    so the file stays inspectable.
    """
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        pytest.skip("reportlab not installed; falling back to hand-rolled PDF needed")
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "Hello Naavik test PDF")
    c.showPage()
    c.save()
    return buf.getvalue()


def _hand_rolled_pdf_bytes() -> bytes:
    """Smallest valid PDF (one empty page) — pdfplumber accepts it.

    From the PDF 1.4 spec minimum-document example; verified to round-trip
    through `pdfplumber.open(...).pages[0].extract_text()`.
    """
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000052 00000 n\n"
        b"0000000099 00000 n\n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n152\n%%EOF\n"
    )


@pytest.fixture
def client_with_user(tmp_path: Path, monkeypatch):
    """TestClient with auth + CSRF deps overridden + data_dir pointed at tmp_path.

    Plan 0.7.0.48 Wave 2 hacker MED fold-in (2026-05-25): `require_csrf`
    now gates the upload endpoint. Tests override BOTH `require_password_complete`
    and `require_csrf` so they exercise the happy + validation paths without
    needing to craft a double-submit token roundtrip per request.

    A dedicated `test_upload_csrf_enforced` (below) does NOT override
    `require_csrf` to pin the regression.
    """
    from fastapi.testclient import TestClient

    from api.auth import require_csrf
    from config import settings as app_settings
    from main import app
    from services.auth import require_password_complete

    user = SimpleNamespace(
        id=7,
        is_active=True,
        is_admin=True,
        must_change_password=False,
    )

    async def _override():
        return user

    def _csrf_pass() -> None:
        return None

    app.dependency_overrides[require_password_complete] = _override
    app.dependency_overrides[require_csrf] = _csrf_pass
    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))

    yield TestClient(app, raise_server_exceptions=True), user, tmp_path

    app.dependency_overrides.pop(require_password_complete, None)
    app.dependency_overrides.pop(require_csrf, None)


def test_upload_happy_path_writes_pdf_and_returns_partial(client_with_user):
    client, user, data_dir = client_with_user
    payload = _hand_rolled_pdf_bytes()
    r = client.post(
        "/api/v1/extraction/upload",
        files={"resume": ("my-resume.pdf", payload, "application/pdf")},
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.text
    assert "Got it" in body
    assert "my-resume.pdf" in body
    assert "Continue to your profile" in body
    assert 'href="/profile/edit"' in body

    # File persisted under <data_dir>/uploads/<user.id>/<ts>.pdf
    user_dir = data_dir / "uploads" / str(user.id)
    assert user_dir.exists(), "user upload dir not created"
    saved = list(user_dir.glob("*.pdf"))
    assert len(saved) == 1, f"expected exactly one saved PDF, got {len(saved)}"
    assert saved[0].read_bytes() == payload


def test_upload_rejects_non_pdf_content_type(client_with_user):
    client, _user, _data_dir = client_with_user
    r = client.post(
        "/api/v1/extraction/upload",
        files={"resume": ("evil.docx", b"PK\x03\x04", "application/vnd.openxmlformats")},
    )
    assert r.status_code == 422


def test_upload_rejects_empty_body(client_with_user):
    client, _user, _data_dir = client_with_user
    r = client.post(
        "/api/v1/extraction/upload",
        files={"resume": ("empty.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 422


def test_upload_rejects_oversize_body(client_with_user):
    client, _user, _data_dir = client_with_user
    # 11 MB > 10 MB cap. Bytes don't need to be valid PDF — size-check runs
    # before pdfplumber.
    big = b"%PDF-1.4\n" + (b"\x00" * (11 * 1024 * 1024))
    r = client.post(
        "/api/v1/extraction/upload",
        files={"resume": ("huge.pdf", big, "application/pdf")},
    )
    assert r.status_code == 413


def test_upload_csrf_enforced(tmp_path: Path, monkeypatch):
    """Regression for plan 0.7.0.48 Wave 2 hacker MED fold-in (2026-05-25):
    `/api/v1/extraction/upload` MUST be gated by `require_csrf`. Pre-fold,
    this state-changing route was the only POST in `src/` lacking
    double-submit CSRF enforcement — narrow exploitability today (SameSite=Strict
    on the JWT cookie blocks most browser cross-origin abuse) but a real
    gap before any multi-user deployment.

    This test asserts the route returns 403 when `require_csrf` is NOT
    overridden — i.e. the dependency actually fires. The other 4 tests in
    this file override `require_csrf` for ergonomics.
    """
    from fastapi.testclient import TestClient

    from config import settings as app_settings
    from main import app
    from services.auth import require_password_complete

    user = SimpleNamespace(
        id=7,
        is_active=True,
        is_admin=True,
        must_change_password=False,
    )

    async def _override():
        return user

    # Override ONLY the auth dep, NOT require_csrf — exercises the gate.
    app.dependency_overrides[require_password_complete] = _override
    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))

    try:
        client = TestClient(app, raise_server_exceptions=True)
        payload = _hand_rolled_pdf_bytes()
        # No CSRF cookie + header → 403 "CSRF token invalid".
        r = client.post(
            "/api/v1/extraction/upload",
            files={"resume": ("regress.pdf", payload, "application/pdf")},
        )
        assert r.status_code == 403, (
            f"upload route must enforce CSRF; got {r.status_code}: {r.text[:200]}"
        )
        assert "CSRF" in r.text
    finally:
        app.dependency_overrides.pop(require_password_complete, None)
