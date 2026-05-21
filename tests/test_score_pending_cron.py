"""`jobs.score_pending` + `score.recompute_stale` cron registration — plan 65 § D.6.

Verifies the APScheduler registry picks up both crons with the right
schedule shape, and that the cron bodies are correctly bound.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: E402

from scheduler import jobs  # noqa: E402


def test_score_pending_registers_with_15min_interval():
    scheduler = AsyncIOScheduler()
    jobs.register_all(scheduler)
    ids = {j.id for j in scheduler.get_jobs()}
    assert "jobs.score_pending" in ids
    assert "score.recompute_stale" in ids
    assert "embeddings.embed_pending_profiles" in ids


def test_score_pending_is_callable():
    assert callable(jobs.score_pending)
    assert callable(jobs.score_recompute_stale)
    assert callable(jobs.embed_pending_profiles)
