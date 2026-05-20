"""Settings · Semantic match form persistence — plan 61 (0.2.7.16).

Sanity coverage: PUT /api/v1/settings/llm carrying the 4 new fields
threads into `settings_service.update_llm` + writes to the Settings row.
Threshold validator + invalid-type guard exercised here.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

import pytest  # noqa: E402

from services import settings_service  # noqa: E402

# Service-level guards (don't need TestClient for these).


@pytest.mark.asyncio
async def test_update_llm_persists_semantic_fields(monkeypatch):
    from unittest.mock import AsyncMock

    from models import Settings

    s = Settings(user_id=1)
    captured = {"s": s}

    async def _stub_get_or_create(session, user_id):
        return captured["s"]

    monkeypatch.setattr(settings_service, "get_or_create", _stub_get_or_create)

    session = AsyncMock()
    session.add = lambda x: None
    session.flush = AsyncMock()

    out = await settings_service.update_llm(
        session,
        user_id=1,
        semantic_match_enabled=True,
        embedding_provider="ollama",
        semantic_match_threshold=0.75,
        semantic_match_sync_on_upsert=False,
    )
    assert out.semantic_match_enabled is True
    assert out.embedding_provider == "ollama"
    assert out.semantic_match_threshold == 0.75
    assert out.semantic_match_sync_on_upsert is False


@pytest.mark.asyncio
async def test_update_llm_clears_provider_on_empty_string(monkeypatch):
    """Empty embedding_provider = clear (user picked `Auto`)."""
    from unittest.mock import AsyncMock

    from models import Settings

    s = Settings(user_id=1, embedding_provider="openai")
    captured = {"s": s}

    async def _stub_get_or_create(session, user_id):
        return captured["s"]

    monkeypatch.setattr(settings_service, "get_or_create", _stub_get_or_create)

    session = AsyncMock()
    session.add = lambda x: None
    session.flush = AsyncMock()

    out = await settings_service.update_llm(
        session,
        user_id=1,
        embedding_provider="",
    )
    assert out.embedding_provider is None


@pytest.mark.asyncio
async def test_update_llm_rejects_threshold_out_of_range(monkeypatch):
    from unittest.mock import AsyncMock

    from models import Settings

    s = Settings(user_id=1)
    captured = {"s": s}

    async def _stub_get_or_create(session, user_id):
        return captured["s"]

    monkeypatch.setattr(settings_service, "get_or_create", _stub_get_or_create)

    session = AsyncMock()
    session.add = lambda x: None
    session.flush = AsyncMock()

    with pytest.raises(ValueError) as exc:
        await settings_service.update_llm(
            session,
            user_id=1,
            semantic_match_threshold=1.5,
        )
    assert "between 0.0 and 1.0" in str(exc.value)
