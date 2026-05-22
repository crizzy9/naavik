"""ATS skeleton adapter envelopes (plan 63 / 0.2.7.10 § C.7).

Skeletons return `FAILURE_AUTH_REQUIRED` rather than raising — UX-equivalent
to `_ManualFallbackAdapter` but with board-named log lines so the dispatcher
resolves to a concrete class. Per-adapter PRs (0.4.0.NN / 0.8.0.NN) overwrite
each skeleton with the real Playwright flow.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models import ApplicationBoard
from services.ats import dispatch
from services.ats.base import FAILURE_AUTH_REQUIRED, ApplicationBundle, ATSAdapter
from services.ats.generic import GenericAdapter
from services.ats.indeed import IndeedAdapter
from services.ats.linkedin_apply import LinkedInAdapter
from services.ats.workday import WorkdayAdapter

pytestmark = pytest.mark.uses_sample_data_shims


def _empty_bundle(board: ApplicationBoard) -> ApplicationBundle:
    app = SimpleNamespace(id=1, user_id=1, board=board, submission_artifacts=None, external_url="")
    return ApplicationBundle(application=app, resume=None, cover_letter=None)


def test_dispatch_returns_workday_skeleton():
    adapter = dispatch(ApplicationBoard.WORKDAY)
    assert isinstance(adapter, WorkdayAdapter)
    # Per plan: skeleton's `requires_credential()` is True (consumed by Settings UI).
    assert adapter.requires_credential() is True


def test_dispatch_returns_linkedin_skeleton():
    adapter = dispatch(ApplicationBoard.LINKEDIN)
    assert isinstance(adapter, LinkedInAdapter)


def test_dispatch_returns_indeed_skeleton():
    adapter = dispatch(ApplicationBoard.INDEED)
    assert isinstance(adapter, IndeedAdapter)


def test_dispatch_returns_generic_for_company_direct():
    adapter = dispatch(ApplicationBoard.COMPANY_DIRECT)
    assert isinstance(adapter, GenericAdapter)


def test_dispatch_falls_through_manual_fallback_for_manual_only():
    """Per plan § C.7 — only MANUAL falls through to `_ManualFallbackAdapter`."""
    adapter = dispatch(ApplicationBoard.MANUAL)
    # MANUAL adapter is the `_ManualFallbackAdapter` — not exported, so we check
    # by name + by the `board` ivar present on the fallback.
    assert isinstance(adapter, ATSAdapter)
    assert getattr(adapter, "board_name", "") == "manual"


@pytest.mark.parametrize(
    "board, expected_phase_hint",
    [
        (ApplicationBoard.WORKDAY, "Phase 4"),
        (ApplicationBoard.LINKEDIN, "Phase 5"),
        (ApplicationBoard.INDEED, "Phase 5"),
        (ApplicationBoard.COMPANY_DIRECT, "Phase 5"),
    ],
)
@pytest.mark.asyncio
async def test_skeleton_submit_returns_auth_required_with_phase_pointer(board, expected_phase_hint):
    adapter = dispatch(board)
    bundle = _empty_bundle(board)
    result = await adapter.submit(bundle.application, bundle)
    assert result.ok is False
    assert result.error == FAILURE_AUTH_REQUIRED
    # The error message names the future-PR row so operators see a forward pointer.
    assert expected_phase_hint in result.error_message


def test_skeleton_can_submit_always_false():
    """`can_submit(job)` returns False — the auto-apply queue won't pick skeletons up."""
    for adapter_cls in (WorkdayAdapter, LinkedInAdapter, IndeedAdapter, GenericAdapter):
        adapter = adapter_cls()
        assert adapter.can_submit(None) is False  # type: ignore[arg-type]


def test_skeleton_requires_credential_true():
    for adapter_cls in (WorkdayAdapter, LinkedInAdapter, IndeedAdapter, GenericAdapter):
        adapter = adapter_cls()
        assert adapter.requires_credential() is True


@pytest.mark.parametrize(
    "adapter_cls",
    [WorkdayAdapter, LinkedInAdapter, IndeedAdapter, GenericAdapter],
)
@pytest.mark.asyncio
async def test_skeleton_internal_submit_with_context_raises_notimplementederror(
    adapter_cls,
):
    """`_submit_with_context` is the per-adapter PR's hook; in skeletons it's unreachable
    via `submit()` but raises NotImplementedError if a future caller invokes it directly.
    Sanity check that the deferred slot is named correctly.
    """
    adapter = adapter_cls()
    with pytest.raises(NotImplementedError):
        await adapter._submit_with_context(None, None, None)  # type: ignore[arg-type]


def test_skeleton_adapters_inherit_from_playwright_base():
    """All 4 skeleton adapters share the `_PlaywrightATSAdapter` substrate."""
    from services.ats._playwright_base import _PlaywrightATSAdapter

    for adapter_cls in (WorkdayAdapter, LinkedInAdapter, IndeedAdapter, GenericAdapter):
        assert issubclass(adapter_cls, _PlaywrightATSAdapter)


def test_playwright_base_requires_browser_pool_attr_true():
    """`requires_browser_pool` is the per-adapter PR's wiring signal."""
    from services.ats._playwright_base import _PlaywrightATSAdapter

    assert _PlaywrightATSAdapter.requires_browser_pool is True
