"""Layer 2 — semantic cosine (plan 65 § D.4).

Tests run on sqlite — pgvector's `<=>` operator isn't available, so the
SQL-roundtrip path raises and `_semantic_score` returns `None`. The
"missing embedding" branches are deterministic across dialects and
cover the orchestrator's None-handling contract.

Full cosine-math validation lives in `NAAVIK_LIVE_DB=1` Postgres runs.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

from services.scorer.semantic_layer import _semantic_score  # noqa: E402


def _job_stub(id_: int = 7, user_id: int = 1):
    return SimpleNamespace(id=id_, user_id=user_id)


def _profile_emb_stub(vec):
    return SimpleNamespace(embedding=vec, user_id=1)


def _job_emb_stub(vec, *, job_id: int = 7, user_id: int = 1):
    return SimpleNamespace(embedding=vec, job_id=job_id, user_id=user_id)


@pytest.mark.asyncio
async def test_semantic_score_none_when_profile_emb_missing():
    session = AsyncMock()
    out = await _semantic_score(session, job=_job_stub(), profile_embedding=None)
    assert out is None


@pytest.mark.asyncio
async def test_semantic_score_none_when_job_emb_missing():
    session = MagicMock()
    session.exec = AsyncMock(return_value=MagicMock(one_or_none=lambda: None))
    out = await _semantic_score(
        session,
        job=_job_stub(),
        profile_embedding=_profile_emb_stub([0.1] * 768),
    )
    assert out is None


@pytest.mark.asyncio
async def test_semantic_score_none_when_dims_mismatch():
    session = MagicMock()
    session.exec = AsyncMock(return_value=MagicMock(one_or_none=lambda: _job_emb_stub([0.5] * 384)))
    out = await _semantic_score(
        session,
        job=_job_stub(),
        profile_embedding=_profile_emb_stub([0.1] * 768),
    )
    assert out is None


@pytest.mark.asyncio
async def test_semantic_score_sqlite_fallback_returns_none():
    """On sqlite (no pgvector), the `<=>` operator path raises and we
    return None — the orchestrator handles that gracefully.
    """
    # First exec: existing JobEmbedding row found.
    # Second exec: the cosine SQL fails (sqlite has no pgvector).
    exec_results = [
        MagicMock(one_or_none=lambda: _job_emb_stub([0.1] * 768)),
    ]

    async def _exec(stmt, *args, **kwargs):
        if exec_results:
            return exec_results.pop(0)
        raise RuntimeError("no such operator <=>")

    session = MagicMock()
    session.exec = AsyncMock(side_effect=_exec)

    out = await _semantic_score(
        session,
        job=_job_stub(),
        profile_embedding=_profile_emb_stub([0.1] * 768),
    )
    assert out is None


@pytest.mark.asyncio
async def test_semantic_score_clamps_postgres_result():
    """Even if the postgres-side cosine math drifts slightly out of [0,1],
    we clamp before returning.
    """
    exec_results = [
        MagicMock(one_or_none=lambda: _job_emb_stub([0.1] * 768)),
        MagicMock(one=lambda: (1.2,)),  # weird value clamps to 1.0
    ]

    async def _exec(stmt, *args, **kwargs):
        return exec_results.pop(0)

    session = MagicMock()
    session.exec = AsyncMock(side_effect=_exec)

    out = await _semantic_score(
        session,
        job=_job_stub(),
        profile_embedding=_profile_emb_stub([0.1] * 768),
    )
    assert out == 1.0


# unused-import placeholders
_ = (UTC, datetime)
