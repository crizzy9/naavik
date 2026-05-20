"""Model-level sanity for ProfileAnswer + JobEmbedding — plan 61.

In-memory checks that the SQLModel field definitions register correctly
(table name, columns, constants). Round-trip-against-DB coverage lives in
`tests/test_alembic_0012.py` + `tests/test_alembic_0013.py`.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")

from models import EMBEDDING_DIM, JobEmbedding, ProfileAnswer  # noqa: E402


def test_profile_answer_metadata():
    assert ProfileAnswer.__tablename__ == "profile_answer"
    cols = {c.name for c in ProfileAnswer.__table__.columns}
    for required in (
        "id",
        "user_id",
        "question_fingerprint",
        "question_text_sample",
        "answer",
        "source_screener_answer_id",
        "times_offered",
        "times_accepted",
        "last_used_at",
    ):
        assert required in cols, required


def test_profile_answer_unique_constraint_present():
    constraints = {c.name for c in ProfileAnswer.__table__.constraints}
    assert "uq_profile_answer_user_fingerprint" in constraints


def test_job_embedding_metadata():
    assert JobEmbedding.__tablename__ == "job_embedding"
    cols = {c.name for c in JobEmbedding.__table__.columns}
    for required in (
        "job_id",
        "user_id",
        "embedding",
        "model",
        "dim",
        "content_hash",
    ):
        assert required in cols, required


def test_embedding_dim_constant():
    assert EMBEDDING_DIM == 768


def test_job_embedding_default_dim_matches_constant():
    inst = JobEmbedding(
        job_id=1,
        user_id=1,
        embedding=[0.0] * EMBEDDING_DIM,
        model="ollama/nomic-embed-text",
        content_hash="x" * 40,
    )
    assert inst.dim == EMBEDDING_DIM
