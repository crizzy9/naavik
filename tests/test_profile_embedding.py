"""ProfileEmbedding service — plan 65 (0.3.0.03).

Mirrors `tests/test_embedding_service.py` shape. Covers `embed_profile`
(skip on no provider, skip on hash match, re-embed on change),
`needs_profile_embedding`, `maybe_refresh_profile_embedding` (best-effort
swallow + gated by `Settings.semantic_match_enabled`).
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from llm.base import EmbeddingResult  # noqa: E402
from models import EMBEDDING_DIM  # noqa: E402
from services import embedding_service  # noqa: E402


def _profile_stub(user_id: int = 1, *, id_: int = 100, headline: str = "Senior SWE"):
    from models import Profile

    return Profile(
        id=id_,
        user_id=user_id,
        full_name="Shyam Padia",
        headline=headline,
        email="s@example.com",
        summary_short="Builder of platforms",
        summary_full=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _settings_stub(
    *,
    enabled: bool = True,
    provider: str = "ollama",
    user_id: int = 1,
):
    from models import Settings

    return Settings(
        user_id=user_id,
        semantic_match_enabled=enabled,
        embedding_provider=provider,
        llm_model="gpt-4o",
    )


def _bullet_stubs(n: int = 3):
    from models import Bullet

    out = []
    for i in range(n):
        out.append(
            Bullet(
                id=i + 1,
                experience_id=10,
                text=f"Built a thing #{i}",
                tags=["ai-ml"],
                order_index=i,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    return out


# ── _profile_content_hash + _profile_embed_text ──────────────────────


def test_profile_content_hash_changes_on_headline_edit():
    p1 = _profile_stub(headline="Senior SWE")
    p2 = _profile_stub(headline="Senior Staff SWE")
    text_blob = embedding_service._profile_embed_text(p1, [])
    text_blob2 = embedding_service._profile_embed_text(p2, [])
    assert embedding_service._profile_content_hash(
        p1, text_blob
    ) != embedding_service._profile_content_hash(p2, text_blob2)


def test_profile_content_hash_stable_for_same_input():
    p = _profile_stub()
    text_blob = embedding_service._profile_embed_text(p, [])
    h1 = embedding_service._profile_content_hash(p, text_blob)
    h2 = embedding_service._profile_content_hash(p, text_blob)
    assert h1 == h2


def test_profile_embed_text_includes_bullets():
    p = _profile_stub()
    bullets = _bullet_stubs(2)
    text = embedding_service._profile_embed_text(p, bullets)
    assert "Headline:" in text
    assert "Summary:" in text
    assert "Built a thing #0" in text
    assert "Built a thing #1" in text


# ── embed_profile ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_profile_skip_when_no_provider(monkeypatch):
    monkeypatch.setattr("services.embedding_service.get_embedding_provider", lambda s: None)
    session = AsyncMock()
    out = await embedding_service.embed_profile(
        session, profile=_profile_stub(), settings=_settings_stub(enabled=False)
    )
    assert out is None
    session.exec.assert_not_called()


@pytest.mark.asyncio
async def test_embed_profile_invokes_tracked_call_with_prompt_name():
    from models import ProfileEmbedding

    profile = _profile_stub()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "ollama"
        model_name = "nomic-embed-text"

        async def embed(self, text):
            return EmbeddingResult(
                vector=[0.01] * EMBEDDING_DIM,
                input_tokens=10,
                output_tokens=0,
                model=self.model_name,
            )

        def estimate_cost(self, **kw):
            return 0.0

    captured: dict = {}

    async def _stub_tracked_call(**kwargs):
        captured.update(kwargs)
        return await kwargs["provider"].embed(text=kwargs["text"])

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    # Two exec calls: fetch_top_bullets returns []; existing-row lookup returns None.
    exec_calls = [
        MagicMock(all=lambda: []),  # bullets
        MagicMock(one_or_none=lambda: None),  # existing row
    ]
    session.exec = AsyncMock(side_effect=exec_calls)

    with (
        patch.object(
            embedding_service,
            "get_embedding_provider",
            return_value=_FakeProvider(),
        ),
        patch.object(
            embedding_service.llm_tracker,
            "tracked_call",
            side_effect=_stub_tracked_call,
        ),
    ):
        row = await embedding_service.embed_profile(session, profile=profile, settings=settings)

    assert isinstance(row, ProfileEmbedding)
    assert row.dim == EMBEDDING_DIM
    assert row.model.startswith("ollama/")
    assert captured["prompt_name"] == "embed_profile"
    assert captured["method"] == "embed"
    assert "Senior SWE" in captured["text"]  # headline propagates


@pytest.mark.asyncio
async def test_embed_profile_skip_on_hash_and_model_match():
    from models import ProfileEmbedding

    profile = _profile_stub()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "ollama"
        model_name = "nomic-embed-text"

        async def embed(self, text):
            raise AssertionError("should not be called")

        def estimate_cost(self, **kw):
            return 0.0

    text_blob = embedding_service._profile_embed_text(profile, [])
    existing = ProfileEmbedding(
        user_id=profile.user_id,
        embedding=[0.0] * EMBEDDING_DIM,
        model=embedding_service._model_identifier(_FakeProvider(), EMBEDDING_DIM),
        dim=EMBEDDING_DIM,
        content_hash=embedding_service._profile_content_hash(profile, text_blob),
    )

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    exec_calls = [
        MagicMock(all=lambda: []),  # bullets
        MagicMock(one_or_none=lambda: existing),  # existing row
    ]
    session.exec = AsyncMock(side_effect=exec_calls)

    with patch.object(
        embedding_service,
        "get_embedding_provider",
        return_value=_FakeProvider(),
    ):
        row = await embedding_service.embed_profile(session, profile=profile, settings=settings)

    assert row is existing


@pytest.mark.asyncio
async def test_embed_profile_re_embeds_on_content_change():
    from models import ProfileEmbedding

    profile = _profile_stub()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "ollama"
        model_name = "nomic-embed-text"

        async def embed(self, text):
            return EmbeddingResult(
                vector=[0.5] * EMBEDDING_DIM,
                input_tokens=12,
                output_tokens=0,
                model=self.model_name,
            )

        def estimate_cost(self, **kw):
            return 0.0

    stale = ProfileEmbedding(
        user_id=profile.user_id,
        embedding=[0.0] * EMBEDDING_DIM,
        model=embedding_service._model_identifier(_FakeProvider(), EMBEDDING_DIM),
        dim=EMBEDDING_DIM,
        content_hash="stale-hash",
    )

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    exec_calls = [
        MagicMock(all=lambda: []),  # bullets
        MagicMock(one_or_none=lambda: stale),  # existing row (stale)
    ]
    session.exec = AsyncMock(side_effect=exec_calls)

    async def _stub_tracked_call(**kwargs):
        return await kwargs["provider"].embed(text=kwargs["text"])

    with (
        patch.object(
            embedding_service,
            "get_embedding_provider",
            return_value=_FakeProvider(),
        ),
        patch.object(
            embedding_service.llm_tracker,
            "tracked_call",
            side_effect=_stub_tracked_call,
        ),
    ):
        row = await embedding_service.embed_profile(session, profile=profile, settings=settings)

    assert row is stale
    assert row.embedding == [0.5] * EMBEDDING_DIM
    assert row.content_hash != "stale-hash"


@pytest.mark.asyncio
async def test_embed_profile_swallows_provider_error():
    from llm import LLMProviderError

    profile = _profile_stub()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "ollama"
        model_name = "nomic-embed-text"

        async def embed(self, text):
            raise RuntimeError("boom")

        def estimate_cost(self, **kw):
            return 0.0

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    exec_calls = [
        MagicMock(all=lambda: []),
        MagicMock(one_or_none=lambda: None),
    ]
    session.exec = AsyncMock(side_effect=exec_calls)

    async def _raising_tracked_call(**kwargs):
        raise LLMProviderError("boom", kind="provider_error")

    with (
        patch.object(
            embedding_service,
            "get_embedding_provider",
            return_value=_FakeProvider(),
        ),
        patch.object(
            embedding_service.llm_tracker,
            "tracked_call",
            side_effect=_raising_tracked_call,
        ),
    ):
        row = await embedding_service.embed_profile(session, profile=profile, settings=settings)

    assert row is None


# ── needs_profile_embedding ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_needs_profile_embedding_no_provider(monkeypatch):
    monkeypatch.setattr("services.embedding_service.get_embedding_provider", lambda s: None)
    session = AsyncMock()
    assert not await embedding_service.needs_profile_embedding(
        session, profile=_profile_stub(), settings=_settings_stub(enabled=False)
    )


@pytest.mark.asyncio
async def test_needs_profile_embedding_missing_row():
    profile = _profile_stub()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "ollama"
        model_name = "nomic-embed-text"

        def estimate_cost(self, **kw):
            return 0.0

    session = MagicMock()
    exec_calls = [
        MagicMock(all=lambda: []),  # bullets
        MagicMock(one_or_none=lambda: None),  # existing row None
    ]
    session.exec = AsyncMock(side_effect=exec_calls)

    with patch.object(
        embedding_service,
        "get_embedding_provider",
        return_value=_FakeProvider(),
    ):
        out = await embedding_service.needs_profile_embedding(
            session, profile=profile, settings=settings
        )
    assert out is True


# ── maybe_refresh_profile_embedding (on-edit hook) ────────────────────


@pytest.mark.asyncio
async def test_maybe_refresh_skips_when_semantic_disabled():
    """The hook is a no-op when `Settings.semantic_match_enabled = False`."""
    settings = _settings_stub(enabled=False)
    profile = _profile_stub()

    session = MagicMock()
    exec_calls = [
        MagicMock(one_or_none=lambda: profile),  # profile lookup
        MagicMock(one_or_none=lambda: settings),  # settings lookup
    ]
    session.exec = AsyncMock(side_effect=exec_calls)

    out = await embedding_service.maybe_refresh_profile_embedding(session, user_id=1)
    assert out is None


@pytest.mark.asyncio
async def test_maybe_refresh_swallows_unexpected_errors():
    """Best-effort: nightly cron is safety net. Exceptions never propagate."""
    session = MagicMock()
    session.exec = AsyncMock(side_effect=RuntimeError("db gone"))

    out = await embedding_service.maybe_refresh_profile_embedding(session, user_id=1)
    assert out is None
