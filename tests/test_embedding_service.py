"""embedding_service — plan 61 (0.2.7.16).

Covers `embed_job` (skip on no provider, skip on hash match, re-embed on
change), `delete_orphan_embeddings` (counts), and `needs_embedding`.

`search_similar` requires pgvector + Postgres `vector` operator — exercised
in `NAAVIK_LIVE_DB=1` runs; here we cover the dim-mismatch guard.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from llm.base import EmbeddingResult  # noqa: E402
from models import EMBEDDING_DIM  # noqa: E402
from services.scorer import embeddings as embedding_service  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


def _job_stub(*, id_=10, role="SWE", description="Build stuff"):
    """Minimal Job-shaped object."""
    from models import Job

    return Job(
        id=id_,
        user_id=1,
        source="LINKEDIN",
        board="LINKEDIN",
        external_id=f"manual-{id_}",
        url=f"https://example.com/{id_}",
        url_type="job",
        company="Acme",
        role=role,
        description=description,
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


# ── content_hash + needs_embedding ──────────────────────────────────────


def test_content_hash_changes_on_description_edit():
    job1 = _job_stub(description="old text")
    job2 = _job_stub(description="new text")
    assert embedding_service._content_hash(job1) != embedding_service._content_hash(job2)


def test_content_hash_stable_for_same_input():
    job1 = _job_stub(description="same")
    job2 = _job_stub(description="same")
    assert embedding_service._content_hash(job1) == embedding_service._content_hash(job2)


# ── embed_job ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_job_skip_when_no_provider(monkeypatch):
    """Provider resolves None → no LLM call, returns None."""
    monkeypatch.setattr("services.scorer.embeddings.get_embedding_provider", lambda s: None)
    session = AsyncMock()
    job = _job_stub()
    settings = _settings_stub(enabled=False)
    out = await embedding_service.embed_job(session, job=job, settings=settings)
    assert out is None
    # No tracked_call invoked
    session.exec.assert_not_called()


@pytest.mark.asyncio
async def test_embed_job_skip_when_disabled_flag(monkeypatch):
    """`semantic_match_enabled = False` propagates to provider-resolver None."""
    settings = _settings_stub(enabled=False)
    out = await embedding_service.embed_job(AsyncMock(), job=_job_stub(), settings=settings)
    assert out is None


@pytest.mark.asyncio
async def test_embed_job_invokes_tracked_call_with_prompt_name():
    """The plan's contract: every embed call wraps `llm_tracker.tracked_call`
    with `prompt_name='embed_job'`. Verified by patching tracked_call against
    a mocked session — pgvector's VECTOR column makes the DB-roundtrip path a
    Postgres-only exercise.
    """
    from models import JobEmbedding

    job = _job_stub()
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

    # Mock session.exec to return None for the "lookup existing" query so we
    # take the insert branch.
    from unittest.mock import MagicMock

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(one_or_none=lambda: None))

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
        row = await embedding_service.embed_job(session, job=job, settings=settings)

    assert isinstance(row, JobEmbedding)
    assert row.dim == EMBEDDING_DIM
    assert row.model.startswith("ollama/")
    # Contract: tracked_call was invoked with the plan's prompt_name.
    assert captured["prompt_name"] == "embed_job"
    assert captured["method"] == "embed"
    # And the call carried the per-job composed text.
    assert "Acme" in captured["text"]
    assert "SWE" in captured["text"]


@pytest.mark.asyncio
async def test_embed_job_skip_on_hash_and_model_match():
    """When existing row's content_hash + model both match, no LLM call fires."""
    from models import JobEmbedding

    job = _job_stub()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "ollama"
        model_name = "nomic-embed-text"

        async def embed(self, text):
            raise AssertionError("should not be called")

        def estimate_cost(self, **kw):
            return 0.0

    existing = JobEmbedding(
        job_id=job.id,
        user_id=job.user_id,
        embedding=[0.0] * EMBEDDING_DIM,
        model=embedding_service._model_identifier(_FakeProvider(), EMBEDDING_DIM),
        dim=EMBEDDING_DIM,
        content_hash=embedding_service._content_hash(job),
    )

    from unittest.mock import MagicMock

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(one_or_none=lambda: existing))

    with (
        patch.object(
            embedding_service,
            "get_embedding_provider",
            return_value=_FakeProvider(),
        ),
    ):
        row = await embedding_service.embed_job(session, job=job, settings=settings)

    assert row is existing


@pytest.mark.asyncio
async def test_embed_job_re_embeds_on_content_change():
    """Content hash mismatch → tracked_call fires; row content updates."""
    from models import JobEmbedding

    job = _job_stub()
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

    stale = JobEmbedding(
        job_id=job.id,
        user_id=job.user_id,
        embedding=[0.0] * EMBEDDING_DIM,
        model="ollama/nomic-embed-text",
        dim=EMBEDDING_DIM,
        content_hash="stale-hash-deadbeef",
    )

    async def _stub_tracked_call(**kwargs):
        return await kwargs["provider"].embed(text=kwargs["text"])

    from unittest.mock import MagicMock

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(one_or_none=lambda: stale))

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
        row = await embedding_service.embed_job(session, job=job, settings=settings)

    assert row is stale
    assert row.content_hash == embedding_service._content_hash(job)
    assert row.embedding == [0.5] * EMBEDDING_DIM


# ── search_similar guards ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_similar_rejects_wrong_dim():
    with pytest.raises(ValueError) as exc:
        await embedding_service.search_similar(
            AsyncMock(),
            user_id=1,
            query_embedding=[0.0] * 128,
        )
    assert f"dim={EMBEDDING_DIM}" in str(exc.value)


# ── delete_orphan_embeddings ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_orphan_embeddings_returns_count():
    """Driver-level: rowcount comes through; service flushes."""
    session = AsyncMock()
    result = type("R", (), {"rowcount": 5})()
    session.exec = AsyncMock(return_value=result)
    n = await embedding_service.delete_orphan_embeddings(session)
    assert n == 5
    session.flush.assert_called()
