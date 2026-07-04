"""Bullet editor "Rewrite with AI" — style-directed variants (2026-07).

The old wiring used trim_bullet@160, so any already-short bullet came back
byte-identical and the button read as broken. Now the modal posts a
`rewrite_style` chip + the LIVE textarea text and gets back 2-3 clickable
variant cards plus a one-line model note; nothing persists until Save.
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


_BULLET = SimpleNamespace(id=7, text="Stored bullet text about shipping a platform.")


def _rewrite(client, data=None, *, llm_value=None, provider_fails=False, tracked=None):
    llm_value = llm_value or {
        "variants": ["Punchy version one.", "Punchy version two."],
        "note": "Led with the verb; dropped filler.",
    }
    tracked = tracked or AsyncMock(return_value=SimpleNamespace(value=llm_value))
    get_provider = patch("llm.get_provider", side_effect=RuntimeError("no provider"))
    if not provider_fails:
        get_provider = patch("llm.get_provider", return_value=SimpleNamespace())
    with (
        patch("services.profile_service.owns_bullet", new=AsyncMock(return_value=True)),
        patch("services.profile_service.get_bullet", new=AsyncMock(return_value=_BULLET)),
        patch(
            "services.settings_service.get_or_create",
            new=AsyncMock(return_value=SimpleNamespace()),
        ),
        get_provider,
        patch("services.llm_tracker.tracked_call", new=tracked),
    ):
        return client.post("/api/v1/bullets/7/rewrite", data=data or {}), tracked


def test_rewrite_returns_variant_cards_and_note(client_with_user):
    r, _ = _rewrite(client_with_user, {"rewrite_style": "punchier", "text": "Live WIP text."})
    assert r.status_code == 200
    assert r.text.count("data-rewrite-variant") == 2
    assert "Punchy version one." in r.text
    assert "Led with the verb; dropped filler." in r.text
    trig = json.loads(r.headers["HX-Trigger"])
    assert "showToast" in trig


def test_rewrite_uses_live_textarea_text_and_style(client_with_user):
    _, tracked = _rewrite(
        client_with_user, {"rewrite_style": "metric-forward", "text": "Cut latency 40%."}
    )
    prompt = tracked.call_args.kwargs["prompt"]
    assert "Cut latency 40%." in prompt
    assert "metric-forward" in prompt
    assert "Stored bullet text" not in prompt
    assert tracked.call_args.kwargs["prompt_name"] == "rewrite_bullet"


def test_rewrite_falls_back_to_stored_text_and_default_style(client_with_user):
    _, tracked = _rewrite(client_with_user, {"rewrite_style": "not-a-style"})
    prompt = tracked.call_args.kwargs["prompt"]
    assert "Stored bullet text" in prompt
    assert "punchier" in prompt  # DEFAULT_STYLE


def test_rewrite_caps_variants_at_three_and_drops_blanks(client_with_user):
    r, _ = _rewrite(
        client_with_user,
        {"rewrite_style": "tighter"},
        llm_value={"variants": ["a", "", "b", "c", "d"], "note": "n"},
    )
    assert r.status_code == 200
    assert r.text.count("data-rewrite-variant") == 3


def test_rewrite_no_provider_is_honest_422(client_with_user):
    r, _ = _rewrite(client_with_user, {"rewrite_style": "punchier"}, provider_fails=True)
    assert r.status_code == 422
    assert "No LLM provider configured" in r.json()["detail"]


def test_rewrite_no_usable_variants_is_502(client_with_user):
    r, _ = _rewrite(
        client_with_user,
        {"rewrite_style": "punchier"},
        llm_value={"variants": ["", "  "], "note": "n"},
    )
    assert r.status_code == 502


def test_rewrite_schema_is_openai_strict_safe():
    """BulletRewrite must survive _to_strict_schema: no defaults anywhere."""
    from llm.prompts.rewrite_bullet import BulletRewrite

    schema = BulletRewrite.model_json_schema()
    assert set(schema["required"]) == {"variants", "note"}
    assert "default" not in json.dumps(schema)
