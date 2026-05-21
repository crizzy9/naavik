"""Postmortem `screenshot_path` wiring (plan 63 / 0.2.7.10 § C.5).

`capture_postmortem` now writes `raw["screenshot_b64"]` as
`<data_dir>/data/postmortems/<app_id>/<ts>/screenshot.png` (atomic) and
threads the relative path into `PostmortemTrace.screenshot_path` so it
shows up in `trace.json`.

HTTP adapters never emit `screenshot_b64` — backward-compatible path:
`screenshot_path` stays None for Greenhouse / Lever / Ashby flows.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any

import pytest

from llm.base import StructuredResult
from llm.prompts.ats_postmortem import PostmortemAnalysis
from services import ats_postmortem

_TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4//8/AwAI/AL+XJ/PtgAAAABJRU5ErkJggg=="


def _make_app(aid: int = 7, user_id: int = 1):
    from models import ApplicationBoard

    return SimpleNamespace(
        id=aid,
        user_id=user_id,
        board=ApplicationBoard.WORKDAY,
        submission_artifacts=None,
    )


def _make_settings(**kw):
    from models.enums import LLMProvider

    base = {"user_id": 1, "llm_provider": LLMProvider.ANTHROPIC, "llm_model": "claude"}
    base.update(kw)
    return SimpleNamespace(**base)


def _canned_result() -> StructuredResult:
    return StructuredResult(
        text="",
        model="claude",
        value=PostmortemAnalysis(
            failure_kind="unknown",
            summary="Playwright crashed mid-form.",
            suggested_action="Retry; if persistent, file a bug.",
        ).model_dump(),
        input_tokens=10,
        output_tokens=5,
    )


class _FakeProvider:
    provider_id = "anthropic"
    model_name = "claude"

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        return 0.0


@pytest.fixture
def _patched_llm(monkeypatch):
    """Patch the LLM provider + tracked_call so postmortem analysis succeeds."""
    monkeypatch.setattr(ats_postmortem, "get_provider", lambda s: _FakeProvider())
    canned = _canned_result()

    async def fake_tracked_call(**kwargs: Any) -> StructuredResult:
        return canned

    monkeypatch.setattr(ats_postmortem.llm_tracker, "tracked_call", fake_tracked_call)


@pytest.mark.asyncio
async def test_screenshot_b64_written_as_png_alongside_trace(tmp_path, monkeypatch, _patched_llm):
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))

    app = _make_app()
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=app,
        failure_kind="unknown",
        failure_message="playwright timeout",
        raw={
            "request_url": "https://workday.com/job/1",
            "response_status": None,
            "response_body": "<playwright-runtime-exception>",
            "screenshot_b64": _TINY_PNG_B64,
        },
        settings=_make_settings(),
    )
    assert out is not None
    full = tmp_path / "data" / out
    png_path = full / "screenshot.png"
    assert png_path.exists(), "screenshot.png not written"
    assert png_path.read_bytes() == base64.b64decode(_TINY_PNG_B64)

    trace = json.loads((full / "trace.json").read_text())
    assert trace["screenshot_path"] == "screenshot.png"


@pytest.mark.asyncio
async def test_no_screenshot_when_raw_omits_screenshot_b64(tmp_path, monkeypatch, _patched_llm):
    """HTTP adapters (Greenhouse / Lever / Ashby) never emit `screenshot_b64`."""
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))

    app = _make_app()
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=app,
        failure_kind="auth_required",
        failure_message="cookie expired",
        raw={"text": "Unauthorized"},  # legacy HTTP-adapter shape
        settings=_make_settings(),
    )
    assert out is not None
    full = tmp_path / "data" / out
    assert not (full / "screenshot.png").exists()
    trace = json.loads((full / "trace.json").read_text())
    assert trace["screenshot_path"] is None


@pytest.mark.asyncio
async def test_malformed_screenshot_b64_does_not_raise(tmp_path, monkeypatch, _patched_llm):
    """Best-effort: invalid base64 → log + skip; trace.json still writes cleanly."""
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))

    app = _make_app()
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=app,
        failure_kind="unknown",
        failure_message="boom",
        raw={"screenshot_b64": "!!!not-base64!!!"},
        settings=_make_settings(),
    )
    assert out is not None  # capture didn't blow up
    full = tmp_path / "data" / out
    trace = json.loads((full / "trace.json").read_text())
    # Decoded to zero bytes → no PNG file → path stays None
    assert trace["screenshot_path"] is None
    assert not (full / "screenshot.png").exists()


@pytest.mark.asyncio
async def test_empty_screenshot_b64_skipped(tmp_path, monkeypatch, _patched_llm):
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))

    app = _make_app()
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=app,
        failure_kind="unknown",
        failure_message="boom",
        raw={"screenshot_b64": ""},
        settings=_make_settings(),
    )
    assert out is not None
    full = tmp_path / "data" / out
    trace = json.loads((full / "trace.json").read_text())
    assert trace["screenshot_path"] is None


@pytest.mark.asyncio
async def test_screenshot_path_carried_into_trace_json(tmp_path, monkeypatch, _patched_llm):
    """End-to-end: trace.json on disk carries the relative `screenshot.png`."""
    monkeypatch.setattr(ats_postmortem.app_settings, "data_dir", str(tmp_path))

    app = _make_app(aid=42)
    out = await ats_postmortem.capture_postmortem(
        session=None,
        application=app,
        failure_kind="unknown",
        failure_message="playwright runtime",
        raw={"screenshot_b64": _TINY_PNG_B64, "request_url": "https://x.com/job/1"},
        settings=_make_settings(),
    )
    assert out is not None
    assert f"postmortems/{app.id}/" in out
    full = tmp_path / "data" / out
    trace = json.loads((full / "trace.json").read_text())
    assert trace["screenshot_path"] == "screenshot.png"
    assert trace["request_url"] == "https://x.com/job/1"
