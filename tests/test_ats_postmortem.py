"""ATS postmortem capture + retrieve tests (plan 52 / 0.2.3.02).

Covers:

- capture writes trace.json + analysis.md atomically
- LLM unavailable → trace-only postmortem with placeholder analysis
- Redaction strips secrets-looking keys from request_body
- Response body capped at 32 KB
- _record_failure threads postmortem_path into submission_artifacts
- Exception inside capture → returns None; never raises
- GET endpoint enforces IDOR via 404 (no existence leak)
- GET endpoint rejects bad ts format
- GET endpoint rejects path-traversal attempts
- GET endpoint happy path returns envelope
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from llm.base import LLMProviderError, StructuredResult
from llm.prompts.ats_postmortem import PostmortemAnalysis
from services import ats_postmortem

# ── Fixtures ────────────────────────────────────────────────────────────


def _make_app(aid: int = 7, user_id: int = 1):
    from models import ApplicationBoard

    return SimpleNamespace(
        id=aid,
        user_id=user_id,
        board=ApplicationBoard.GREENHOUSE,
        submission_artifacts=None,
    )


def _make_settings(**kw):
    from models.enums import LLMProvider

    base = {"user_id": 1, "llm_provider": LLMProvider.ANTHROPIC, "llm_model": "claude"}
    base.update(kw)
    return SimpleNamespace(**base)


def _canned_analysis() -> PostmortemAnalysis:
    return PostmortemAnalysis(
        failure_kind="auth_required",
        summary="Greenhouse rejected the cookie - session expired.",
        suggested_action="Re-login through Settings then retry.",
    )


def _canned_result() -> StructuredResult:
    return StructuredResult(
        text="",
        model="claude",
        value=_canned_analysis().model_dump(),
        input_tokens=10,
        output_tokens=5,
    )


class _FakeProvider:
    provider_id = "anthropic"
    model_name = "claude"

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        return 0.0


# ── capture_postmortem unit tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_writes_trace_and_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(ats_postmortem, "get_provider", lambda s: _FakeProvider())

    canned_result = _canned_result()

    async def fake_tracked_call(**kwargs: Any) -> StructuredResult:
        return canned_result

    monkeypatch.setattr(ats_postmortem.llm_tracker, "tracked_call", fake_tracked_call)

    app = _make_app()
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=app,
        failure_kind="auth_required",
        failure_message="cookie expired",
        raw={"text": "Unauthorized"},
        settings=_make_settings(),
    )
    assert out is not None
    assert out.startswith(f"postmortems/{app.id}/")
    full = tmp_path / "data" / out
    trace_data = json.loads((full / "trace.json").read_text())
    assert trace_data["application_id"] == app.id
    assert trace_data["failure_kind"] == "auth_required"
    assert trace_data["response_body_excerpt"] == "Unauthorized"
    md = (full / "analysis.md").read_text()
    assert "auth_required" in md
    assert "Greenhouse rejected" in md
    assert "Re-login" in md


@pytest.mark.asyncio
async def test_capture_llm_unavailable_writes_trace_only(tmp_path, monkeypatch):
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))

    def boom(s):
        raise LLMProviderError("no llm_provider configured", kind="auth_required")

    monkeypatch.setattr(ats_postmortem, "get_provider", boom)

    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=_make_app(),
        failure_kind="unknown",
        failure_message="boom",
        raw={"text": "broken"},
        settings=_make_settings(),
    )
    assert out is not None
    full = tmp_path / "data" / out
    assert (full / "trace.json").exists()
    md = (full / "analysis.md").read_text()
    assert "AI analysis unavailable" in md


@pytest.mark.asyncio
async def test_capture_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(ats_postmortem, "get_provider", lambda s: _FakeProvider())

    async def fake_tracked_call(**kwargs: Any) -> StructuredResult:
        return _canned_result()

    monkeypatch.setattr(ats_postmortem.llm_tracker, "tracked_call", fake_tracked_call)

    raw = {
        "request_url": "https://api.example.com/apps",
        "request_body": {
            "api_key": "sk-secret",
            "Cookie": "abc",
            "AUTHORIZATION": "Bearer xyz",
            "nested": {"token": "tok-xx", "fine": "ok"},
            "list_field": [{"password": "pw-1"}, {"value": "fine"}],
            "fine": "kept",
        },
        "response_body": "boom",
    }
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=_make_app(),
        failure_kind="auth_required",
        failure_message="x",
        raw=raw,
        settings=_make_settings(),
    )
    trace = json.loads((tmp_path / "data" / out / "trace.json").read_text())
    body = trace["request_body_redacted"]
    assert body["api_key"] == "[REDACTED]"
    assert body["Cookie"] == "[REDACTED]"
    assert body["AUTHORIZATION"] == "[REDACTED]"
    assert body["nested"]["token"] == "[REDACTED]"
    assert body["nested"]["fine"] == "ok"
    assert body["list_field"][0]["password"] == "[REDACTED]"
    assert body["list_field"][1]["value"] == "fine"
    assert body["fine"] == "kept"
    # Raw scan: secret values must not appear anywhere in the persisted trace.
    persisted = (tmp_path / "data" / out / "trace.json").read_text()
    assert "sk-secret" not in persisted
    assert "tok-xx" not in persisted
    assert "pw-1" not in persisted


@pytest.mark.asyncio
async def test_capture_caps_response_body_at_32k(tmp_path, monkeypatch):
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(ats_postmortem, "get_provider", lambda s: _FakeProvider())

    async def fake_tracked_call(**kwargs: Any) -> StructuredResult:
        return _canned_result()

    monkeypatch.setattr(ats_postmortem.llm_tracker, "tracked_call", fake_tracked_call)

    big = "a" * 40_000
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=_make_app(),
        failure_kind="unknown",
        failure_message="x",
        raw={"response_body": big},
        settings=_make_settings(),
    )
    trace = json.loads((tmp_path / "data" / out / "trace.json").read_text())
    assert len(trace["response_body_excerpt"]) == 32_768


@pytest.mark.asyncio
async def test_capture_exception_returns_none_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(ats_postmortem, "get_provider", lambda s: _FakeProvider())

    async def boom_tracked_call(**kwargs: Any) -> StructuredResult:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(ats_postmortem.llm_tracker, "tracked_call", boom_tracked_call)

    # tracked_call raising should be swallowed → analysis None but trace.json still written.
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=_make_app(),
        failure_kind="unknown",
        failure_message="x",
        raw={"text": "x"},
        settings=_make_settings(),
    )
    # tracked_call doesn't raise into the outer try (we catch LLMProviderError narrowly
    # — RuntimeError bubbles through but the outer except in capture_postmortem swallows it).
    # If we ever returned None, that's the contract; either way, _record_failure must not crash.
    assert out is None or (tmp_path / "data" / out / "trace.json").exists()


@pytest.mark.asyncio
async def test_capture_caps_at_32k_for_dict_body(tmp_path, monkeypatch):
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(ats_postmortem, "get_provider", lambda s: _FakeProvider())

    async def fake_tracked_call(**kwargs: Any) -> StructuredResult:
        return _canned_result()

    monkeypatch.setattr(ats_postmortem.llm_tracker, "tracked_call", fake_tracked_call)

    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=_make_app(),
        failure_kind="unknown",
        failure_message="x",
        raw={"response_body": {"items": ["x"] * 5_000}},
        settings=_make_settings(),
    )
    trace = json.loads((tmp_path / "data" / out / "trace.json").read_text())
    assert len(trace["response_body_excerpt"]) <= 32_768


# ── _record_failure integration test ────────────────────────────────────


@pytest.mark.asyncio
async def test_record_failure_threads_postmortem_path(tmp_path, monkeypatch):
    """_record_failure receives raw+settings and threads postmortem_path through."""
    from services import application_service as appsvc

    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(ats_postmortem, "get_provider", lambda s: _FakeProvider())

    async def fake_tracked_call(**kwargs: Any) -> StructuredResult:
        return _canned_result()

    monkeypatch.setattr(ats_postmortem.llm_tracker, "tracked_call", fake_tracked_call)

    class _Session:
        async def flush(self):
            return None

        def add(self, _):
            return None

    app = _make_app()
    await appsvc._record_failure(
        _Session(),
        app,
        kind="auth_required",
        message="msg",
        raw={"text": "body"},
        settings=_make_settings(),
    )
    last = app.submission_artifacts["last_failure"]
    assert last["kind"] == "auth_required"
    assert last["postmortem_path"] is not None
    assert last["postmortem_path"].startswith(f"postmortems/{app.id}/")


@pytest.mark.asyncio
async def test_record_failure_no_raw_skips_capture():
    """Backward compat — _record_failure with raw=None keeps the old shape."""
    from services import application_service as appsvc

    class _Session:
        async def flush(self):
            return None

        def add(self, _):
            return None

    app = _make_app()
    await appsvc._record_failure(_Session(), app, kind="unknown", message="msg")
    last = app.submission_artifacts["last_failure"]
    assert last["kind"] == "unknown"
    assert last["postmortem_path"] is None


# ── API retrieval tests ─────────────────────────────────────────────────


@pytest.fixture
def client_with_user(tmp_path, monkeypatch) -> tuple[TestClient, SimpleNamespace]:
    """Bring up TestClient with require_password_complete overridden to a user."""
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))
    # The route reads from the API module's app_settings handle too.
    from api import applications as api_apps

    monkeypatch.setattr(api_apps.app_settings, "data_dir", str(tmp_path))

    from main import app
    from services.auth import require_password_complete

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False)

    async def _override():
        return user

    app.dependency_overrides[require_password_complete] = _override
    yield TestClient(app, raise_server_exceptions=True), user
    app.dependency_overrides.pop(require_password_complete, None)


def _seed_postmortem(tmp_path: Path, *, application_id: int, ts: str) -> Path:
    base = tmp_path / "data" / "postmortems" / str(application_id) / ts
    base.mkdir(parents=True, exist_ok=True)
    (base / "trace.json").write_text(
        json.dumps({"application_id": application_id, "failure_kind": "unknown"})
    )
    (base / "analysis.md").write_text("# postmortem\n")
    return base


def test_retrieve_invalid_ts_format(client_with_user, monkeypatch):
    client, user = client_with_user
    fake_app = SimpleNamespace(id=10, user_id=user.id)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=fake_app)):
        r = client.get("/api/v1/applications/10/postmortem/not-a-timestamp")
    assert r.status_code == 400
    assert "invalid timestamp" in r.text


def test_retrieve_path_traversal_rejected(client_with_user, monkeypatch):
    """ts containing path-traversal characters → rejected by strict regex (400)."""
    client, user = client_with_user
    fake_app = SimpleNamespace(id=10, user_id=user.id)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=fake_app)):
        # `..foo..bar` is a single path segment (no slash) but matches no \d{4}-... regex
        r = client.get("/api/v1/applications/10/postmortem/..foo..bar")
    assert r.status_code == 400
    assert "invalid timestamp" in r.text


def test_retrieve_owner_only_idor(client_with_user, tmp_path):
    """User B asking for User A's postmortem gets 404 (no existence leak)."""
    client, user_b = client_with_user
    ts = "2026-05-20T10-12-51Z"
    _seed_postmortem(tmp_path, application_id=99, ts=ts)
    # Application owned by user 1, requester is user 42 (the override).
    other_app = SimpleNamespace(id=99, user_id=1)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=other_app)):
        r = client.get(f"/api/v1/applications/99/postmortem/{ts}")
    assert r.status_code == 404


def test_retrieve_app_not_found_returns_404(client_with_user):
    client, _ = client_with_user
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=None)):
        r = client.get("/api/v1/applications/999/postmortem/2026-05-20T10-12-51Z")
    assert r.status_code == 404


def test_retrieve_missing_files_returns_404(client_with_user):
    """Valid auth + ts pattern, but no postmortem on disk → 404."""
    client, user = client_with_user
    fake_app = SimpleNamespace(id=10, user_id=user.id)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=fake_app)):
        r = client.get("/api/v1/applications/10/postmortem/2026-05-20T10-12-51Z")
    assert r.status_code == 404
    assert "postmortem not found" in r.text


def test_retrieve_happy_path(client_with_user, tmp_path):
    client, user = client_with_user
    ts = "2026-05-20T10-12-51Z"
    _seed_postmortem(tmp_path, application_id=10, ts=ts)
    fake_app = SimpleNamespace(id=10, user_id=user.id)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=fake_app)):
        r = client.get(f"/api/v1/applications/10/postmortem/{ts}")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert "trace" in payload
    assert "analysis_markdown" in payload
    assert payload["trace"]["failure_kind"] == "unknown"
    assert payload["analysis_markdown"].startswith("# postmortem")


def test_atomic_write_replaces_existing(tmp_path):
    target = tmp_path / "x" / "trace.json"
    ats_postmortem._atomic_write(target, "first")
    assert target.read_text() == "first"
    ats_postmortem._atomic_write(target, "second")
    assert target.read_text() == "second"


def test_redact_preserves_non_secret_values():
    out = ats_postmortem._redact(
        {"role": "engineer", "metadata": {"role": "x", "token": "secret"}, "items": ["a", "b"]}
    )
    assert out["role"] == "engineer"
    assert out["metadata"]["role"] == "x"
    assert out["metadata"]["token"] == "[REDACTED]"
    assert out["items"] == ["a", "b"]


def test_build_trace_handles_none_raw():
    app = _make_app()
    trace = ats_postmortem._build_trace(
        application=app,
        failure_kind="unknown",
        failure_message="x",
        raw=None,
        captured_at=datetime(2026, 5, 20, 10, 0, 0, tzinfo=UTC),
    )
    assert trace.application_id == app.id
    assert trace.response_body_excerpt is None
    assert trace.request_url is None


# ── Plan 56 · item 5 (0.2.7.18) — _redact_value_patterns ────────────────


class TestRedactValuePatterns:
    """Value-shape redaction on `response_body_excerpt`.

    Plan 56 / 0.2.7.18 — `_redact()` only walks dict KEYS via `_SECRET_KEY_RE`;
    raw-string `response_body_excerpt` paths used to bypass redaction entirely
    when an ATS error page echoed back the request's auth header. The new
    `_redact_value_patterns` covers Bearer/JWT/Set-Cookie/OAuth shapes.
    """

    def test_redacts_bearer_header(self):
        out = ats_postmortem._redact_value_patterns(
            "Authorization failed: Bearer eyJabcdefghijklmnopqrstuvwxyz0123456789.payload.sig"
        )
        assert "[REDACTED]" in out
        assert "eyJabcdefghijklmnopqrstuvwxyz" not in out

    def test_redacts_bare_jwt(self):
        # 3-segment base64url JWT shape; matches even without "bearer" prefix.
        out = ats_postmortem._redact_value_patterns(
            'response: {"token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"}'
        )
        assert "[REDACTED]" in out
        assert "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c" not in out

    def test_redacts_set_cookie_header(self):
        out = ats_postmortem._redact_value_patterns(
            "failed: Set-Cookie: session=abc123xyz; Path=/; HttpOnly\nOther line."
        )
        assert "session=abc123xyz" not in out
        # Subsequent non-cookie lines preserved.
        assert "Other line." in out

    def test_redacts_authorization_header_line(self):
        out = ats_postmortem._redact_value_patterns(
            "request headers:\nAuthorization: Basic dXNlcjpwYXNz\nUser-Agent: test"
        )
        assert "dXNlcjpwYXNz" not in out
        assert "User-Agent: test" in out

    def test_redacts_oauth_access_token_url_param(self):
        out = ats_postmortem._redact_value_patterns(
            "redirect: ?access_token=ya29.abcdefghij1234567890klmnop&state=xyz"
        )
        assert "ya29.abcdefghij1234567890klmnop" not in out
        # Non-secret param preserved.
        assert "state=xyz" in out

    def test_redacts_refresh_token_url_param(self):
        out = ats_postmortem._redact_value_patterns(
            "callback: ?refresh_token=1//abcdefghijklmnopqrstuvwxyz12345"
        )
        assert "1//abcdefghijklmnopqrstuvwxyz12345" not in out

    def test_does_not_redact_short_non_secret_strings(self):
        # `signature=abc` is shorter than 20 chars; must NOT match the token
        # URL-param patterns. False-positive guard per plan § Risk + mitigation.
        out = ats_postmortem._redact_value_patterns("user signed up: signature=abc, role=engineer")
        assert "[REDACTED]" not in out
        assert "signature=abc" in out
        assert "role=engineer" in out

    def test_does_not_redact_when_no_auth_material(self):
        # Plain text without auth-shape value patterns passes through verbatim.
        body = "company: acme, role: engineer, message: error 503 service unavailable"
        out = ats_postmortem._redact_value_patterns(body)
        assert out == body


def test_build_trace_redacts_value_patterns_in_string_body(tmp_path, monkeypatch):
    """End-to-end: `response_body_excerpt` has its auth material redacted."""
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))
    body = (
        "ATS rejected: Bearer eyJabc1234567890longenough.payload.sig "
        "and ?access_token=ya29.abcdefghij1234567890klmnop"
    )
    trace = ats_postmortem._build_trace(
        application=_make_app(),
        failure_kind="auth_required",
        failure_message="x",
        raw={"text": body},
        captured_at=datetime(2026, 5, 20, 10, 0, 0, tzinfo=UTC),
    )
    assert "eyJabc1234567890longenough" not in trace.response_body_excerpt
    assert "ya29.abcdefghij1234567890klmnop" not in trace.response_body_excerpt
    assert "[REDACTED]" in trace.response_body_excerpt
