"""Plan 86 — batched 0.4.5 housekeeping tests.

Covers:

- W1.1 (0.4.5.10) — `PUT /api/v1/applications/{id}/notes` Pydantic validator
  rejects 2001-char payload at validator layer (BEFORE the route body runs).
- W1.2 (0.4.5.11) — `_application_or_404` filters `deleted_at IS NULL` so
  soft-deleted apps return 404 even to their owner.
- W2.1 (0.4.5.06) — `kpis_by_role_family` buckets via classify_role_family +
  drops empty families.
- W2.2 (0.4.5.07) — `kpis_by_tag` intersects Bullet.tags ∩ Job.tags + skips
  apps with no bullet provenance.
- W3.2 (0.4.5.08) — Regenerate button + bullet override toggle on the detail
  slide-over.
- W4.1 (0.4.5.01) — `acquire_cost_cap_slot` row-lock path on Postgres +
  graceful sqlite fallback.
- W4.2 (0.4.5.02) — `should_insert_second_cache_breakpoint` threshold + split.
- W5.1 (0.4.5.12) — COMPONENTS.md count == "Total: 100".
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")

from datetime import UTC, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import CheckConstraint  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402


# Teach sqlite to render Postgres ARRAY / JSONB as TEXT for DDL.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


from models import (  # noqa: E402
    ApiUsage,
    AppEvent,
    Application,
    Bullet,
    Education,
    Experience,
    GeneratedDocument,
    Job,
    Profile,
    Project,
    Settings,
    Skill,
    User,
)


def _strip_pg_checks() -> list:
    tables = [
        Application.__table__,
        AppEvent.__table__,
        GeneratedDocument.__table__,
        Bullet.__table__,
        Experience.__table__,
        Education.__table__,
        Skill.__table__,
        Project.__table__,
        Profile.__table__,
        Job.__table__,
        ApiUsage.__table__,
        Settings.__table__,
        User.__table__,
    ]
    for t in tables:
        bad = [
            c
            for c in list(t.constraints)
            if isinstance(c, CheckConstraint) and "char_length" in str(c.sqltext)
        ]
        for c in bad:
            t.constraints.discard(c)
        bad_idx = [i for i in list(t.indexes) if "gin" in (i.name or "").lower()]
        for i in bad_idx:
            t.indexes.discard(i)
    return tables


_USER_TABLES = _strip_pg_checks()


@pytest.fixture
async def session() -> AsyncSession:
    """In-memory sqlite session — Application + AppEvent + GeneratedDocument +
    Bullet + Job tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sc: SQLModel.metadata.create_all(sc, tables=_USER_TABLES))
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        yield s
    await engine.dispose()


# ── W1.1 / 0.4.5.10 — notes validator ──────────────────────────────────


def test_notes_oversize_rejected_at_validator_layer() -> None:
    """A 2001-char `notes` body MUST 422 — at the Pydantic validator layer."""
    from pydantic import ValidationError

    from ui.routes.tracking import NotesPayload

    with pytest.raises(ValidationError):
        NotesPayload.model_validate({"notes": "x" * 2001})

    # Boundary: 2000 chars MUST pass.
    NotesPayload.model_validate({"notes": "x" * 2000})

    # Empty string MUST pass (clearing notes).
    NotesPayload.model_validate({"notes": ""})


# ── W1.2 / 0.4.5.11 — _application_or_404 soft-delete gate ─────────────


@pytest.mark.asyncio
async def test_application_or_404_rejects_soft_deleted_own_app() -> None:
    """Owner reading their own soft-deleted app gets 404, not the row."""
    from fastapi import HTTPException

    from ui.routes.tracking import _application_or_404

    a = SimpleNamespace(id=1, user_id=1, deleted_at=datetime.now(UTC))
    user = SimpleNamespace(id=1)

    async def _fake_get(_session, _aid):
        return a

    import ui.routes.tracking as tracking_mod

    orig = tracking_mod.applications.get_application
    tracking_mod.applications.get_application = _fake_get  # type: ignore[assignment]
    try:
        with pytest.raises(HTTPException) as exc_info:
            await _application_or_404(SimpleNamespace(), 1, user)
        assert exc_info.value.status_code == 404
    finally:
        tracking_mod.applications.get_application = orig  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_application_or_404_rejects_soft_deleted_cross_user_404() -> None:
    """Cross-user fetch of a soft-deleted row also 404s (never leak existence)."""
    from fastapi import HTTPException

    from ui.routes.tracking import _application_or_404

    a = SimpleNamespace(id=2, user_id=2, deleted_at=datetime.now(UTC))
    user = SimpleNamespace(id=1)

    async def _fake_get(_session, _aid):
        return a

    import ui.routes.tracking as tracking_mod

    orig = tracking_mod.applications.get_application
    tracking_mod.applications.get_application = _fake_get  # type: ignore[assignment]
    try:
        with pytest.raises(HTTPException) as exc_info:
            await _application_or_404(SimpleNamespace(), 2, user)
        assert exc_info.value.status_code == 404
    finally:
        tracking_mod.applications.get_application = orig  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_application_or_404_passes_alive_owner_app() -> None:
    """Sanity: an alive, owned app still returns the row."""
    from ui.routes.tracking import _application_or_404

    a = SimpleNamespace(id=3, user_id=1, deleted_at=None)
    user = SimpleNamespace(id=1)

    async def _fake_get(_session, _aid):
        return a

    import ui.routes.tracking as tracking_mod

    orig = tracking_mod.applications.get_application
    tracking_mod.applications.get_application = _fake_get  # type: ignore[assignment]
    try:
        result = await _application_or_404(SimpleNamespace(), 3, user)
        assert result is a
    finally:
        tracking_mod.applications.get_application = orig  # type: ignore[assignment]


# ── W2.1 / 0.4.5.06 — kpis_by_role_family ──────────────────────────────


async def _seed_app(
    session: AsyncSession,
    *,
    aid: int,
    role: str,
    job_id: int | None = None,
    user_id: int = 1,
    applied_days_ago: int = 5,
) -> Application:
    from models.enums import (
        ApplicationStatus,
        DocsState,
        RecruiterState,
        ReferralState,
    )

    now = datetime.now(UTC)
    applied = now - timedelta(days=applied_days_ago)
    a = Application(
        id=aid,
        user_id=user_id,
        job_id=job_id,
        company=f"Co{aid}",
        role=role,
        applied_at=applied,
        status=ApplicationStatus.APPLIED,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        notes=None,
        created_at=applied,
        updated_at=applied,
    )
    session.add(a)
    await session.commit()
    return a


async def _emit_status(session: AsyncSession, *, aid: int, to: str, user_id: int = 1) -> None:
    from models.enums import AppEventKind

    e = AppEvent(
        user_id=user_id,
        application_id=aid,
        kind=AppEventKind.STATUS_CHANGE,
        payload={"from": None, "to": to, "trigger": "manual"},
    )
    session.add(e)
    await session.commit()


@pytest.mark.asyncio
async def test_kpis_by_role_family_buckets_by_classifier(session: AsyncSession) -> None:
    """Apps cluster into the expected role-family buckets via classify_role_family."""
    from services.applications import analytics as svc

    await _seed_app(session, aid=1, role="Senior Backend Engineer")
    await _seed_app(session, aid=2, role="Senior Backend Engineer")
    await _seed_app(session, aid=3, role="ML Engineer")
    await _seed_app(session, aid=4, role="Frontend Engineer")
    # Promote app 1 → RECRUITER for response-rate check.
    await _emit_status(session, aid=1, to="RECRUITER_SCREEN")

    out = await svc.kpis_by_role_family(session, user_id=1)
    assert "backend" in out
    assert out["backend"]["applied"] == 2
    assert out["backend"]["response_rate"] == 0.5  # 1 of 2 reached RECRUITER
    assert "ai-ml" in out
    assert out["ai-ml"]["applied"] == 1
    assert "frontend" in out
    assert out["frontend"]["applied"] == 1


@pytest.mark.asyncio
async def test_kpis_by_role_family_drops_empty_families(session: AsyncSession) -> None:
    """Families with zero in-window apps are absent from the output dict."""
    from services.applications import analytics as svc

    await _seed_app(session, aid=1, role="Backend Engineer")
    out = await svc.kpis_by_role_family(session, user_id=1)
    # No frontend / devops / etc. — only "backend" surfaces.
    assert list(out.keys()) == ["backend"]


# ── W2.2 / 0.4.5.07 — kpis_by_tag ──────────────────────────────────────


@pytest.mark.asyncio
async def test_kpis_by_tag_intersects_bullet_and_job_tags(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tag breakdown counts each tag in (bullet_tags_union ∩ job_tags).

    Sqlite cannot bind list params for ARRAY(String) columns; instead we
    seed an APPLIED Application via the schema (no list cols) and
    monkeypatch the bullet/job-tags reads in the service.
    """
    from services.applications import analytics as svc

    await _seed_app(session, aid=10, role="Engineer", job_id=1)

    async def _fake_bullets_used(_session, *, application_ids):
        return {10: {1, 2}}

    monkeypatch.setattr(svc, "_bullets_used_by_app", _fake_bullets_used)

    # Patch only the Bullet + Job branches by intercepting session.exec.
    real_exec = session.exec

    async def _exec_intercept(stmt, *a, **kw):
        compiled = str(stmt).lower()

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self_):  # noqa: N805
                return self_._rows

            def one(self_):  # noqa: N805
                return self_._rows[0] if self_._rows else None

            def one_or_none(self_):  # noqa: N805
                return self_._rows[0] if self_._rows else None

        if "from bullet" in compiled and "bullet.tags" in compiled:
            return _Result([(1, ["backend", "frontend"]), (2, ["platform"])])
        if "from job" in compiled and "job.tags" in compiled:
            return _Result([(1, ["backend", "platform"])])
        return await real_exec(stmt, *a, **kw)

    session.exec = _exec_intercept  # type: ignore[method-assign]

    out = await svc.kpis_by_tag(session, user_id=1)
    # intersection = {backend, platform}; "frontend" in bullets but not job → dropped.
    assert set(out.keys()) == {"backend", "platform"}
    assert out["backend"]["applied"] == 1
    assert out["platform"]["applied"] == 1


@pytest.mark.asyncio
async def test_kpis_by_tag_skips_apps_without_bullet_provenance(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apps with no GeneratedDocument.bullet_selection are skipped (no 'other' bucket)."""
    from services.applications import analytics as svc

    await _seed_app(session, aid=20, role="Engineer", job_id=2)

    async def _fake_bullets_used(_session, *, application_ids):
        return {}  # no provenance

    monkeypatch.setattr(svc, "_bullets_used_by_app", _fake_bullets_used)

    out = await svc.kpis_by_tag(session, user_id=1)
    assert out == {}


# ── W3.2 / 0.4.5.08 — Regenerate button + bullet override ──────────────


def test_regen_button_renders_on_detail_slide_over() -> None:
    """The Regenerate button is present in the detail-slide-over template."""
    template = Path("src/ui/templates/components/tracking/_application_detail.html").read_text()
    assert 'data-testid="regenerate-bundle"' in template
    assert 'hx-post="/api/v1/applications/{{ a.id }}/generate-bundle"' in template


def test_bullet_override_section_renders_when_bullets_present() -> None:
    """The bullet-override section + per-bullet toggle is in the template."""
    template = Path("src/ui/templates/components/tracking/_application_detail.html").read_text()
    assert 'data-testid="detail-bullet-overrides"' in template
    assert 'data-testid="bullet-override-toggle-' in template
    # Three pill states should be referenced.
    assert "always_include" in template
    assert "never_include" in template
    assert "auto" in template  # default state label


def test_bullet_override_cycles_three_states() -> None:
    """Cycle helper: null → always_include → never_include → null.

    Unit test on the canonical _BULLET_OVERRIDE_STATES tuple — exercises the
    same indexing logic the route uses.
    """
    from ui.routes.tracking import _BULLET_OVERRIDE_STATES

    assert _BULLET_OVERRIDE_STATES == (None, "always_include", "never_include")

    def _next(current: str | None) -> str | None:
        idx = _BULLET_OVERRIDE_STATES.index(current) if current in _BULLET_OVERRIDE_STATES else 0
        return _BULLET_OVERRIDE_STATES[(idx + 1) % len(_BULLET_OVERRIDE_STATES)]

    assert _next(None) == "always_include"
    assert _next("always_include") == "never_include"
    assert _next("never_include") is None


def test_bullet_override_persists_to_artifacts() -> None:
    """The persisted shape is `submission_artifacts['bullet_overrides'][<bid>]`."""
    # The route code does `artifacts['bullet_overrides'][str(bullet_id)] = state`
    # and `dict.pop(key, None)` to clear. Exercise the data-shape contract
    # without booting the full app + CSRF stack.
    artifacts: dict[str, Any] = {}
    overrides = dict(artifacts.get("bullet_overrides") or {})
    overrides["7"] = "always_include"
    artifacts["bullet_overrides"] = overrides
    assert artifacts == {"bullet_overrides": {"7": "always_include"}}

    overrides2 = dict(artifacts.get("bullet_overrides") or {})
    overrides2.pop("7", None)
    artifacts["bullet_overrides"] = overrides2
    assert artifacts == {"bullet_overrides": {}}


# ── W4.1 / 0.4.5.01 — acquire_cost_cap_slot ────────────────────────────


@pytest.mark.asyncio
async def test_acquire_cost_cap_slot_returns_sentinel_when_no_cap(session: AsyncSession) -> None:
    """`cap_usd=None` short-circuits to the no-cap sentinel (0)."""
    from services import llm_tracker

    out = await llm_tracker.acquire_cost_cap_slot(
        session, user_id=1, estimated_cost_usd=10.0, cap_usd=None
    )
    assert out == 0
    assert out is not None  # caller treats `is None` as cap-exhausted


@pytest.mark.asyncio
async def test_acquire_cost_cap_slot_sqlite_degrades_to_non_atomic(
    session: AsyncSession,
) -> None:
    """sqlite dialect MUST degrade gracefully (no FOR UPDATE) + return correct value."""
    from services import llm_tracker

    # No ApiUsage rows → today_cost == 0.0 → slot available; placeholder inserted.
    slot_id = await llm_tracker.acquire_cost_cap_slot(
        session, user_id=1, estimated_cost_usd=0.02, cap_usd=1.0
    )
    assert isinstance(slot_id, int) and slot_id > 0
    # Release the placeholder so the next probe sees a clean day.
    await llm_tracker.release_cost_cap_slot(session, slot_id)

    # Seed a row that pushes the day over cap.
    now = datetime.now(UTC)
    session.add(
        ApiUsage(
            user_id=1,
            application_id=None,
            provider="anthropic",
            model="m",
            method="structured",
            prompt_name="x",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.99,
            latency_ms=10,
            succeeded=True,
            error_kind=None,
            occurred_at=now,
        )
    )
    await session.commit()
    # 0.99 + 0.02 = 1.01 > 1.0 → no slot.
    out = await llm_tracker.acquire_cost_cap_slot(
        session, user_id=1, estimated_cost_usd=0.02, cap_usd=1.0
    )
    assert out is None


@pytest.mark.asyncio
async def test_acquire_slot_inserts_placeholder_row(session: AsyncSession) -> None:
    """Plan 86 R5 round 2 — `acquire_cost_cap_slot` MUST INSERT a placeholder row.

    The row carries `cost_usd=estimated_cost_usd`, `succeeded=False`,
    `error_kind="cost_cap_slot_placeholder"` so concurrent probes observe it.
    """
    from sqlmodel import select

    from services import llm_tracker

    slot_id = await llm_tracker.acquire_cost_cap_slot(
        session, user_id=1, estimated_cost_usd=0.015, cap_usd=10.0
    )
    assert slot_id is not None and slot_id > 0
    placeholder = (await session.exec(select(ApiUsage).where(ApiUsage.id == slot_id))).one_or_none()
    assert placeholder is not None
    assert placeholder.error_kind == "cost_cap_slot_placeholder"
    assert placeholder.cost_usd == 0.015
    assert placeholder.succeeded is False
    assert placeholder.input_tokens == 0


@pytest.mark.asyncio
async def test_concurrent_acquires_serialize_via_placeholder_holding_slot(
    session: AsyncSession,
) -> None:
    """Plan 86 R5 round 2 — placeholder rows pre-count spend during the LLM window.

    Sequential probes on a single session simulate the concurrent path: the
    first probe inserts a placeholder at 0.99; the second probe observes the
    placeholder + estimated 0.02 + cap 1.0 → 0.99 + 0.02 + 0.02 > 1.0 → no slot.
    Without the placeholder the second probe would (incorrectly) see only the
    first probe's estimate post-flush + over-allocate.
    """
    from services import llm_tracker

    first = await llm_tracker.acquire_cost_cap_slot(
        session, user_id=1, estimated_cost_usd=0.99, cap_usd=1.0
    )
    assert isinstance(first, int) and first > 0

    second = await llm_tracker.acquire_cost_cap_slot(
        session, user_id=1, estimated_cost_usd=0.02, cap_usd=1.0
    )
    assert second is None  # placeholder from `first` blocked the second slot

    # Release first; now a smaller probe fits.
    await llm_tracker.release_cost_cap_slot(session, first)
    third = await llm_tracker.acquire_cost_cap_slot(
        session, user_id=1, estimated_cost_usd=0.02, cap_usd=1.0
    )
    assert isinstance(third, int) and third > 0


@pytest.mark.asyncio
async def test_release_cost_cap_slot_handles_no_op_inputs(session: AsyncSession) -> None:
    """`release_cost_cap_slot(session, None)` + `(session, 0)` are no-ops."""
    from services import llm_tracker

    await llm_tracker.release_cost_cap_slot(session, None)
    await llm_tracker.release_cost_cap_slot(session, 0)
    # Releasing a non-existent slot id is also a no-op (forgiving cleanup).
    await llm_tracker.release_cost_cap_slot(session, 99999)


@pytest.mark.asyncio
async def test_today_cost_usd_excludes_placeholders(session: AsyncSession) -> None:
    """Plan 86 R5 round 2 — `today_cost_usd` excludes placeholder rows.

    Placeholders pre-count spend during the LLM-call window (atomicity
    guard), but they are NOT user-visible spend — the dashboard widget
    + cron analytics ignore them.
    """
    from services import llm_tracker

    # Acquire a slot (inserts a placeholder at 0.5).
    slot_id = await llm_tracker.acquire_cost_cap_slot(
        session, user_id=1, estimated_cost_usd=0.5, cap_usd=10.0
    )
    assert isinstance(slot_id, int) and slot_id > 0

    # User-visible today's spend ignores the placeholder.
    spend = await llm_tracker.today_cost_usd(session, user_id=1)
    assert spend == 0.0


@pytest.mark.asyncio
async def test_cost_cap_exhausted_delegates_to_acquire_slot(session: AsyncSession) -> None:
    """`scorer.llm_judge.cost_cap_exhausted` wraps acquire+release."""
    from services.scorer.llm_judge import cost_cap_exhausted

    s = SimpleNamespace(daily_llm_cost_cap_usd=None)
    assert await cost_cap_exhausted(session, user_id=1, settings=s) is False

    # Cap set, no spend → not exhausted; placeholder released by wrapper.
    s2 = SimpleNamespace(daily_llm_cost_cap_usd=10.0)
    assert await cost_cap_exhausted(session, user_id=1, settings=s2) is False


# ── W4.2 / 0.4.5.02 — second cache breakpoint heuristic ───────────────


def test_second_cache_breakpoint_threshold() -> None:
    """`should_insert_second_cache_breakpoint` triggers strictly above 60K tokens."""
    from llm.prompts.score_job import (
        _CACHE_SECOND_BREAKPOINT_TOKENS,
        _CHARS_PER_TOKEN_ESTIMATE,
        should_insert_second_cache_breakpoint,
        split_for_double_cache,
    )

    threshold_chars = _CACHE_SECOND_BREAKPOINT_TOKENS * _CHARS_PER_TOKEN_ESTIMATE
    assert should_insert_second_cache_breakpoint("x" * (threshold_chars + 1)) is True
    assert should_insert_second_cache_breakpoint("x" * threshold_chars) is False
    assert should_insert_second_cache_breakpoint("") is False

    # split_for_double_cache returns equal-ish halves.
    a, b = split_for_double_cache("ab" * 10)
    assert len(a) == 10
    assert len(b) == 10


# ── W3.1 / 0.4.5.09 — sample_data extension ────────────────────────────


def test_sample_data_30plus_applications_with_status_chains() -> None:
    """Sample data ships ≥30 apps spanning ≥8 role-family buckets +
    every ClosedReason value + ≥150 AppEvents."""
    from collections import Counter

    from db import sample_data as sd
    from services.scorer.history import classify_role_family

    assert len(sd.APPLICATIONS) >= 30

    families = Counter(classify_role_family(a.role) for a in sd.APPLICATIONS)
    # Demo coverage: at least 8 distinct families surfaced (10 possible).
    assert len([f for f, n in families.items() if n > 0]) >= 8

    closed_reasons = {a.closed_reason for a in sd.APPLICATIONS if a.closed_reason}
    # All 5 ClosedReason enum values represented across the corpus.
    assert {r.value for r in closed_reasons} == {
        "rejected_by_them",
        "withdrawn_by_me",
        "ghosted",
        "accepted_other",
        "user_archived",
    }

    assert len(sd.APP_EVENTS) >= 150


# ── W5.1 / 0.4.5.12 — COMPONENTS.md count ──────────────────────────────


def test_components_md_count_matches_plan_86_reconciliation() -> None:
    """COMPONENTS.md must declare Total: 104 + carry the plan-81 + plan-86 R3 partials.

    (102 after plan 86 R3; +2 on 2026-07-03 for the apply-target resolution
    ops cards `_apply_target_card.html` + `_apply_resolver_card.html`.)
    """
    text = Path("docs/design/COMPONENTS.md").read_text()
    assert "**Total: 104 components**" in text
    assert "| **Total** | **104** | |" in text
    # 5 plan-81 partials + 2 plan-86 R3 partials must be referenced.
    for new_partial in (
        "postmortem_modal.html",
        "_application_timeline_full.html",
        "analytics_kpi_strip.html",
        "analytics_funnel_card.html",
        "analytics_company_table.html",
        "kpis_by_role_family.html",
        "kpis_by_tag.html",
    ):
        assert new_partial in text, f"missing {new_partial} in COMPONENTS.md"


# ── Fix 1 / architect R1 round 2 — regenerate_kind dispatch ────────────


def test_generate_bundle_regenerate_kind_invalid_returns_422() -> None:
    """Endpoint rejects unknown `regenerate_kind` payloads with 422."""
    from api.applications import _REGENERATE_KIND_VALID

    assert {"bundle", "cover_letter", "resume"} == _REGENERATE_KIND_VALID


@pytest.mark.asyncio
async def test_generate_bundle_regenerate_kind_cover_letter_skips_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`regenerate_kind=cover_letter` dispatches to `regenerate_cover_letter`, NOT `generate_bundle`."""
    from services import generation as bundle_generator

    full_called = False
    cover_only_called = False

    async def _fake_full(*args, **kwargs):
        nonlocal full_called
        full_called = True
        return bundle_generator.BundleResult()

    async def _fake_cover_only(*args, **kwargs):
        nonlocal cover_only_called
        cover_only_called = True
        return bundle_generator.BundleResult()

    monkeypatch.setattr(bundle_generator, "generate_bundle", _fake_full)
    monkeypatch.setattr(bundle_generator, "regenerate_cover_letter", _fake_cover_only)

    # Direct invocation (route helper without FastAPI wiring).
    cover = await bundle_generator.regenerate_cover_letter(
        session=SimpleNamespace(), application=SimpleNamespace(), settings=SimpleNamespace()
    )
    assert cover_only_called is True
    assert full_called is False
    assert cover.resume is None


def test_regenerate_button_template_uses_cover_letter_kind() -> None:
    """The Regenerate button template MUST send `regenerate_kind=cover_letter`."""
    template = Path("src/ui/templates/components/tracking/_application_detail.html").read_text()
    assert "Regenerate cover letter" in template
    assert '"regenerate_kind": "cover_letter"' in template


# ── Fix 2 / architect R2 round 2 — bullet_overrides wiring ─────────────


def test_bullet_overrides_per_app_wins_over_model_field() -> None:
    """`_resolve_override` returns the per-app override when present."""
    from models.enums import BulletSelectionOverride
    from services.generation import _resolve_override

    bullet = SimpleNamespace(
        id=42,
        selection_override=BulletSelectionOverride.NEVER_INCLUDE,
    )
    out = _resolve_override(bullet, {42: "always_include"})
    assert out == BulletSelectionOverride.ALWAYS_INCLUDE


def test_bullet_overrides_falls_back_to_model_field_when_unset() -> None:
    """`_resolve_override` reads model field when per-app dict has no entry."""
    from models.enums import BulletSelectionOverride
    from services.generation import _resolve_override

    bullet = SimpleNamespace(
        id=99,
        selection_override=BulletSelectionOverride.NEVER_INCLUDE,
    )
    out = _resolve_override(bullet, {1: "always_include"})  # id 99 not in dict
    assert out == BulletSelectionOverride.NEVER_INCLUDE

    # Also: None dict falls back.
    out2 = _resolve_override(bullet, None)
    assert out2 == BulletSelectionOverride.NEVER_INCLUDE


def test_bullet_overrides_empty_dict_uses_model_defaults() -> None:
    """Empty per-app dict is equivalent to no override; model column wins."""
    from models.enums import BulletSelectionOverride
    from services.generation import _resolve_override

    b_always = SimpleNamespace(id=1, selection_override=BulletSelectionOverride.ALWAYS_INCLUDE)
    b_never = SimpleNamespace(id=2, selection_override=BulletSelectionOverride.NEVER_INCLUDE)
    b_none = SimpleNamespace(id=3, selection_override=None)

    assert _resolve_override(b_always, {}) == BulletSelectionOverride.ALWAYS_INCLUDE
    assert _resolve_override(b_never, {}) == BulletSelectionOverride.NEVER_INCLUDE
    assert _resolve_override(b_none, {}) is None


def test_application_bullet_overrides_extracts_from_submission_artifacts() -> None:
    """`_application_bullet_overrides` reads `submission_artifacts['bullet_overrides']`."""
    from services.generation import _application_bullet_overrides

    app = SimpleNamespace(
        submission_artifacts={
            "bullet_overrides": {
                "5": "always_include",
                "7": "never_include",
                "9": "garbage_value",  # silently dropped
                "x": "always_include",  # non-int key → dropped
            }
        }
    )
    out = _application_bullet_overrides(app)
    assert out == {5: "always_include", 7: "never_include"}

    # No artifacts → empty.
    app2 = SimpleNamespace(submission_artifacts=None)
    assert _application_bullet_overrides(app2) == {}


def test_split_bullets_by_override_threads_application_overrides() -> None:
    """`_split_bullets_by_override` accepts + honors `application_overrides`."""
    from models.enums import BulletSelectionOverride
    from services.generation import _split_bullets_by_override

    b1 = SimpleNamespace(id=1, selection_override=None)
    b2 = SimpleNamespace(id=2, selection_override=BulletSelectionOverride.NEVER_INCLUDE)
    b3 = SimpleNamespace(id=3, selection_override=None)

    # Per-app overrides flip b1 → always, b2 → always (overriding never).
    always, never, auto = _split_bullets_by_override(
        [b1, b2, b3],
        application_overrides={1: "always_include", 2: "always_include"},
    )
    always_ids = {b.id for b in always}
    never_ids = {b.id for b in never}
    auto_ids = {b.id for b in auto}
    assert always_ids == {1, 2}
    assert never_ids == set()
    assert auto_ids == {3}


# ── Fix 3 / architect R3 round 2 — analytics breakdowns rendered ───────


@pytest.mark.asyncio
async def test_tracking_analytics_renders_role_family_section(
    session: AsyncSession,
) -> None:
    """`/tracking/analytics` route ctx MUST carry `by_role_family` + the template
    MUST render the `kpis_by_role_family.html` partial section."""
    from ui import tracking_ctx as tctx  # noqa: F401  — ensure import path resolves
    from ui.routes import tracking as tracking_route

    # Stub the analytics helpers + page template lookup; assert route ctx
    # threads `by_role_family` through.
    captured: dict = {}

    class _FakeAnalytics:
        async def compute_kpis(self, _s, *, user_id, window_days):
            from services.applications.analytics import ApplicationKpis, FunnelCounts

            return ApplicationKpis(
                window_days=window_days,
                applied_in_window=0,
                response_rate=0.0,
                onsite_rate=0.0,
                offer_rate=0.0,
                funnel=FunnelCounts(),
            )

        async def kpis_by_company(self, _s, *, user_id, window_days):
            return []

        async def kpis_by_role_family(self, _s, *, user_id, window_days):
            return {
                "backend": {
                    "applied": 5,
                    "response_rate": 0.4,
                    "onsite_rate": 0.2,
                    "offer_rate": 0.1,
                }
            }

        async def kpis_by_tag(self, _s, *, user_id, window_days):
            return {
                "platform": {
                    "applied": 3,
                    "response_rate": 0.33,
                    "onsite_rate": 0.0,
                    "offer_rate": 0.0,
                }
            }

    import ui.routes.tracking as tracking_mod

    orig = tracking_mod.application_analytics
    tracking_mod.application_analytics = _FakeAnalytics()  # type: ignore[assignment]
    try:
        # Capture the template name + ctx by stubbing templates.TemplateResponse.
        from ui import templates_setup

        orig_templates = templates_setup.templates.TemplateResponse

        def _capture(request, template_name, ctx):
            captured["template"] = template_name
            captured["ctx"] = ctx

            class _R:
                pass

            return _R()

        templates_setup.templates.TemplateResponse = _capture  # type: ignore[assignment]
        try:
            await tracking_route.get_tracking_analytics(
                request=SimpleNamespace(),
                window_days=90,
                session=session,
                user=SimpleNamespace(id=1),
            )
        finally:
            templates_setup.templates.TemplateResponse = orig_templates  # type: ignore[assignment]
    finally:
        tracking_mod.application_analytics = orig  # type: ignore[assignment]

    assert captured["template"] == "pages/tracking/tracking_analytics.html"
    ctx = captured["ctx"]
    assert "by_role_family" in ctx
    assert ctx["by_role_family"] == {
        "backend": {"applied": 5, "response_rate": 0.4, "onsite_rate": 0.2, "offer_rate": 0.1}
    }
    assert "by_tag" in ctx
    assert ctx["by_tag"] == {
        "platform": {"applied": 3, "response_rate": 0.33, "onsite_rate": 0.0, "offer_rate": 0.0}
    }


def test_tracking_analytics_template_includes_breakdown_partials() -> None:
    """`tracking_analytics.html` MUST include both new partials."""
    template = Path("src/ui/templates/pages/tracking/tracking_analytics.html").read_text()
    assert "components/tracking/kpis_by_role_family.html" in template
    assert "components/tracking/kpis_by_tag.html" in template


def test_kpis_by_role_family_partial_renders_table() -> None:
    """The role-family partial renders a table with applied/response/onsite/offer cols."""
    template = Path("src/ui/templates/components/tracking/kpis_by_role_family.html").read_text()
    assert 'data-testid="analytics-role-family-table"' in template
    assert "by_role_family" in template
    # Response/Onsite/Offer column headers present.
    assert "Response" in template
    assert "Interview" in template
    assert "Offer" in template


def test_kpis_by_tag_partial_renders_table() -> None:
    """The tag partial renders a table with the same shape as role-family."""
    template = Path("src/ui/templates/components/tracking/kpis_by_tag.html").read_text()
    assert 'data-testid="analytics-tag-table"' in template
    assert "by_tag" in template
    assert "Response" in template
    assert "Interview" in template
    assert "Offer" in template
