"""ATS adapter ABC + SubmissionResult forward-compat shape (plan 63 / 0.2.7.10).

Covers:
- `ATSAdapter` ABC cannot be instantiated directly
- ABC enforces `submit`, `can_submit`, `requires_credential`
- `SubmissionResult.confidence` is the new forward-compat field (default None;
  HTTP adapters can leave it None — current Greenhouse / Lever / Ashby do)
- `SubmissionResult.raw` carries the new Playwright-adapter shape keys without
  breaking the existing `{"text": "..."}` shape
"""

from __future__ import annotations

import inspect

import pytest

from services.ats.base import (
    FAILURE_AUTH_REQUIRED,
    ATSAdapter,
    SubmissionResult,
)


def test_atsadapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ATSAdapter()  # type: ignore[abstract]


def test_atsadapter_declares_three_abstract_methods():
    abstract = ATSAdapter.__abstractmethods__
    assert "submit" in abstract
    assert "can_submit" in abstract
    assert "requires_credential" in abstract


def test_atsadapter_submit_is_coroutine_function():
    # `submit` must be `async def` so dispatch can `await` uniformly across adapters.
    assert inspect.iscoroutinefunction(ATSAdapter.submit)


def test_submission_result_confidence_default_none():
    r = SubmissionResult(ok=True)
    assert r.confidence is None


def test_submission_result_confidence_round_trip():
    r = SubmissionResult(ok=True, confidence=0.92)
    assert r.confidence == 0.92


def test_submission_result_raw_carries_legacy_text_shape():
    """Existing HTTP adapters populate `raw={"text": resp.text}`; must still work."""
    r = SubmissionResult(ok=False, error=FAILURE_AUTH_REQUIRED, raw={"text": "Unauthorized"})
    assert r.raw == {"text": "Unauthorized"}


def test_submission_result_raw_carries_new_playwright_shape():
    r = SubmissionResult(
        ok=False,
        error=FAILURE_AUTH_REQUIRED,
        raw={
            "request_url": "https://workday.com/job/1",
            "response_status": None,
            "response_body": "<playwright-runtime-exception>",
            "screenshot_b64": "iVBORw0KGgo=",
            "exception_type": "TimeoutError",
        },
    )
    assert r.raw is not None
    assert r.raw["screenshot_b64"] == "iVBORw0KGgo="
    assert r.raw["exception_type"] == "TimeoutError"


def test_submission_result_is_slotted_dataclass():
    """`SubmissionResult` uses `slots=True` — adding a new attr from outside fails."""
    r = SubmissionResult(ok=True)
    with pytest.raises(AttributeError):
        r.surprise = 1  # type: ignore[attr-defined]
