"""Burstiness check_and_score + regen path — plan 66 § T5 + plan 75 / 0.3.3.05.

Architect REQUEST_CHANGES round 1 (plan 66): `check_and_score` was tested
standalone but never invoked in the runtime flow. The bundle now records
`burstiness_std` to the audit trail.

Plan 75 / 0.3.3.05 added the one-shot REGEN of the worst-offender bullet
when std-dev < threshold: cost-cap probe gates the regen call; on success,
the bullet is substituted + std-dev recomputed; hard cap = 1 regen per
bundle (mirrors critique-council T4); `burstiness_regen_insufficient` is
recorded when post-regen std is still below threshold.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.generation import generate_bundle
from services.voice_grounding import VoiceCorpus

pytestmark = pytest.mark.uses_sample_data_shims


def _make_application(**overrides):
    base = {
        "id": 42,
        "user_id": 1,
        "job_id": 100,
        "company": "Stripe",
        "role": "Senior Engineer",
        "status": "DRAFT",
        "board": None,
        "generation_trace": None,
        "updated_at": None,
        "applied_at": None,
        "deleted_at": None,
        "submission_artifacts": None,
        "docs_state": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_settings(**overrides):
    base = {
        "user_id": 1,
        "llm_provider": "anthropic",
        "llm_model": "claude-sonnet-4-6",
        "daily_llm_cost_cap_usd": None,
        "parse_fidelity_threshold": 0.75,
        "resume_template_preference": "auto",
        "cover_letter_format": "auto",
        "ai_writing_voice_samples": "",
        "tier_2_evasion_enabled": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_job(**overrides):
    base = {
        "id": 100,
        "company": "Stripe",
        "role": "Senior Engineer",
        "description": "Build payment infrastructure.",
        "description_html": None,
        "skills_required": ["python"],
        "score": 0.30,
        "match_breakdown": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_corpus():
    return VoiceCorpus(
        full_text="# Bullets\n- Shipped distributed platform.",
        vocab_fingerprint=["distributed"],
        sentence_length_stats={"mean_words": 5.0, "std_dev_words": 0.0},
        idiomatic_phrases=[],
        voice_fingerprint_hash="sha256:test",
        source_counts={"bullets": 1},
    )


def _make_profile():
    return SimpleNamespace(
        id=99,
        user_id=1,
        full_name="Shyam Padia",
        headline="Senior Engineer",
        summary_full="Long",
        summary_short="Short",
        email="x@y",
        phone="555",
        location="SF",
        portfolio_url=None,
        linkedin_handle=None,
        github_handle=None,
        work_authorization=None,
        deleted_at=None,
    )


async def _run_bundle(session, application, settings, job, fake_resume, *, regen=None):
    fake_cover = SimpleNamespace(id=2, path="/tmp/c.pdf", bullet_selection=None)
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [(i,) for i in range(20)],
        )
    )

    # Plan 75 / 0.3.3.05 — regen call site needs a default no-op mock so tests
    # that don't care about regen behavior still pass. Callers can override
    # via the `regen` kwarg (None → identity returning original_text).
    async def _default_regen(*, original_text, **_kw):
        return original_text

    regen_mock = AsyncMock(side_effect=regen or _default_regen)

    with (
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.generation.assemble_corpus",
            AsyncMock(return_value=fake_corpus),
        ),
        patch(
            "services.generation.extract_hiring_manager",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.generation.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.generation._load_profile_experiences",
            AsyncMock(return_value=(fake_profile, [])),
        ),
        patch(
            "services.generation.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.generation.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.generation.regen_bullet_for_variance",
            regen_mock,
        ),
        patch(
            "services.generation.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)
        # `BundleResult` uses slots — attach the mock to a separate sidecar.
        return _ResultWithMock(result, regen_mock)


class _ResultWithMock:
    """Test sidecar — exposes `.generation_trace` from the bundle + the regen mock."""

    def __init__(self, result, regen_mock):
        self.result = result
        self._regen_mock = regen_mock
        self.generation_trace = result.generation_trace


@pytest.mark.asyncio
async def test_bundle_records_low_burstiness_when_bullets_uniform():
    """Uniform-length trimmed bullets → low std-dev → recorded to audit trail."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    # All bullets exactly 6 words → zero variance, well below threshold.
    uniform_bullets = {
        "1": "shipped the payment platform to users",
        "2": "designed the ML pipeline at scale",
        "3": "led the data team across geos",
        "4": "built the model serving at rate",
    }
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2, 3, 4],
            "trimmed_lines": uniform_bullets,
        },
    )

    result = await _run_bundle(session, application, settings, job, fake_resume)

    # burstiness_std is recorded (non-None, low value).
    assert result.generation_trace["burstiness_std"] is not None
    assert result.generation_trace["burstiness_std"] < 6.0


@pytest.mark.asyncio
async def test_bundle_records_high_burstiness_when_bullets_varied():
    """Varied-length bullets → high std-dev → audit trail captures pass signal."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    # Bullets with markedly different word counts → high variance.
    varied_bullets = {
        "1": "shipped it",
        "2": "designed the ML inference pipeline serving 50K requests per second across three regions",
        "3": "built tools",
        "4": (
            "led a cross-functional team that delivered the new payment platform after deeply "
            "redesigning the distributed transaction layer for greater throughput"
        ),
    }
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2, 3, 4],
            "trimmed_lines": varied_bullets,
        },
    )

    result = await _run_bundle(session, application, settings, job, fake_resume)

    assert result.generation_trace["burstiness_std"] is not None
    assert result.generation_trace["burstiness_std"] >= 6.0


@pytest.mark.asyncio
async def test_bundle_skips_burstiness_when_one_bullet():
    """<2 bullets → no variance signal; burstiness_std stays None or zero-ish."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    one_bullet = {"1": "shipped the payment platform"}
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={"selected_ids": [1], "trimmed_lines": one_bullet},
    )

    result = await _run_bundle(session, application, settings, job, fake_resume)

    # check_and_score is guarded by `len(trimmed) >= 2` so std stays at initial None.
    assert result.generation_trace["burstiness_std"] is None


# ── Plan 75 / 0.3.3.05 — regen path tests ──────────────────────────────


@pytest.mark.asyncio
async def test_burstiness_regen_triggers_when_std_below_threshold():
    """Uniform bullets → regen called once + pre/post std recorded."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    uniform_bullets = {
        "1": "shipped the payment platform to users",
        "2": "designed the ML pipeline at scale",
        "3": "led the data team across geos",
        "4": "built the model serving at rate",
    }
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2, 3, 4],
            "trimmed_lines": uniform_bullets,
        },
    )

    # Regen returns a much-longer bullet — should widen std.
    async def _wider_regen(*, original_text, **_kw):
        return (
            "led the cross-functional team that delivered the new payment platform "
            "after redesigning the distributed transaction layer for greater throughput"
        )

    result = await _run_bundle(session, application, settings, job, fake_resume, regen=_wider_regen)

    trace = result.generation_trace
    assert trace["burstiness_std_pre_regen"] is not None
    assert trace["burstiness_std_pre_regen"] < 6.0
    # Post-regen std written into `burstiness_std`.
    assert trace["burstiness_std"] is not None
    assert trace["burstiness_std"] > trace["burstiness_std_pre_regen"]
    # Exactly 1 regen invocation (hard cap).
    assert result._regen_mock.await_count == 1


@pytest.mark.asyncio
async def test_burstiness_regen_skipped_on_cost_cap():
    """Cost-cap exhausted before burstiness regen → skip flag recorded.

    Plan 85 / 0.3.3.24 — replaces the prior counting probe (`len(probes) >= 6`)
    with a deterministic stack-frame inspection: `is_cost_capped` returns True
    iff the burstiness branch has already written `burstiness_std_pre_regen`
    into the caller's `trace` dict (the regen-gating probe is the only one
    invoked after that marker is set). This is robust to pipeline changes
    that add new cost-cap probes earlier in the flow.
    """
    import inspect

    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    uniform_bullets = {
        "1": "shipped the payment platform to users",
        "2": "designed the ML pipeline at scale",
        "3": "led the data team across geos",
        "4": "built the model serving at rate",
    }
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2, 3, 4],
            "trimmed_lines": uniform_bullets,
        },
    )

    fake_cover = SimpleNamespace(id=2, path="/tmp/c.pdf", bullet_selection=None)
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()
    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [(i,) for i in range(20)],
        )
    )

    async def _capped_at_burstiness(_session, _user_id, _settings):
        # Look up the caller's locals for the `trace` dict. The burstiness
        # branch writes `trace["burstiness_std_pre_regen"]` IMMEDIATELY
        # before its cost-cap probe (`bundle_generator.py:530-532`); every
        # OTHER probe in the pipeline runs before that key is set. So a
        # truthy lookup means we're at the burstiness gate; otherwise False
        # so the pipeline keeps making progress.
        frame = inspect.currentframe()
        # Walk back through frames; the bundle_generator call site holds `trace`.
        while frame is not None:
            trace = frame.f_locals.get("trace")
            if isinstance(trace, dict):
                return "burstiness_std_pre_regen" in trace
            frame = frame.f_back
        return False

    regen_mock = AsyncMock(return_value="should-never-be-called")

    with (
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(side_effect=_capped_at_burstiness),
        ),
        patch(
            "services.generation.assemble_corpus",
            AsyncMock(return_value=fake_corpus),
        ),
        patch(
            "services.generation.extract_hiring_manager",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.generation.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.generation._load_profile_experiences",
            AsyncMock(return_value=(fake_profile, [])),
        ),
        patch(
            "services.generation.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.generation.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.generation.regen_bullet_for_variance",
            regen_mock,
        ),
        patch(
            "services.generation.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)

    trace = result.generation_trace
    # Plan 85 / 0.3.3.24 — assertions are now deterministic. The stack-frame
    # inspection guarantees the burstiness branch IS reached (all prior
    # cost-cap probes return False) AND the regen-gating probe IS the only
    # one that returns True. So `burstiness_std_pre_regen` is always set and
    # the skip flag is always recorded — no conditional escape hatch needed.
    assert trace.get("burstiness_std_pre_regen") is not None
    assert trace.get("burstiness_regen_skipped_cost_cap") is True
    # The regen LLM call was NOT made.
    regen_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_burstiness_regen_insufficient_when_post_still_low():
    """Regen returns a bullet that doesn't widen variance → insufficient flag."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    uniform_bullets = {
        "1": "shipped the payment platform to users",
        "2": "designed the ML pipeline at scale",
        "3": "led the data team across geos",
        "4": "built the model serving at rate",
    }
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2, 3, 4],
            "trimmed_lines": uniform_bullets,
        },
    )

    # Regen returns another same-length bullet — std stays below threshold.
    async def _same_length_regen(*, original_text, **_kw):
        return "delivered the payment system for thousands of users"  # 7 words

    result = await _run_bundle(
        session, application, settings, job, fake_resume, regen=_same_length_regen
    )

    trace = result.generation_trace
    assert trace.get("burstiness_regen_insufficient") is True
    assert result._regen_mock.await_count == 1


@pytest.mark.asyncio
async def test_burstiness_regen_failed_marks_trace_when_helper_returns_original():
    """Plan 85 / 0.3.3.24 — regen helper swallows `LLMProviderError` and returns
    the original text unchanged; bundle marks `burstiness_regen_failed=True`
    in the audit trail so a debugger reading the trace can distinguish
    "regen attempted + failed" from "regen never ran" (skipped by cost-cap
    or non-burstiness branch). Hard cap of 1 regen still holds.
    """
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    uniform_bullets = {
        "1": "shipped the payment platform to users",
        "2": "designed the ML pipeline at scale",
        "3": "led the data team across geos",
        "4": "built the model serving at rate",
    }
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2, 3, 4],
            "trimmed_lines": uniform_bullets,
        },
    )

    # Mirror the production fallback: helper catches `LLMProviderError` and
    # returns the original_text unchanged.
    async def _failed_regen(*, original_text, **_kw):
        return original_text

    result = await _run_bundle(
        session, application, settings, job, fake_resume, regen=_failed_regen
    )

    trace = result.generation_trace
    assert trace.get("burstiness_regen_failed") is True
    # No substitution → `burstiness_regen_insufficient` is NOT also set
    # (the helper return-equivalent-to-original is its own bucket).
    assert trace.get("burstiness_regen_insufficient") is not True
    assert result._regen_mock.await_count == 1
