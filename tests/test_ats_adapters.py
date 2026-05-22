"""Wave 6 — ATS adapter tests.

Per plan 10 § E. Coverage:
- Greenhouse / Lever / Ashby `submit` against mocked HTTP (httpx.MockTransport)
- `SubmissionResult` shape: ok / board_application_id / error fields
- Failure classification: 401/403 → auth_required; 422 → field_mismatch;
  429 → rate_limit; other 5xx → unknown
- Resume-parsing override (canonical fields posted explicitly, not relying
  on board's PDF parser).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from models import ApplicationBoard, ScreenerAnswerSource, ScreenerQuestionType
from services.ats import dispatch
from services.ats.ashby import AshbyAdapter
from services.ats.base import (
    FAILURE_AUTH_REQUIRED,
    FAILURE_FIELD_MISMATCH,
    FAILURE_RATE_LIMIT,
    FAILURE_UNKNOWN,
    ApplicationBundle,
    SubmissionResult,
)
from services.ats.greenhouse import GreenhouseAdapter
from services.ats.lever import LeverAdapter

pytestmark = pytest.mark.uses_sample_data_shims

# ── httpx mock helper ────────────────────────────────────────────────


def _mock_client(
    *,
    response: httpx.Response | None = None,
    capture: dict | None = None,
) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient that replies with a canned response.

    If `capture` is supplied, the request is recorded into it so tests can
    assert on the multipart body.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture["url"] = str(request.url)
            capture["method"] = request.method
            capture["headers"] = dict(request.headers)
            capture["body"] = request.read()
        return response or httpx.Response(200, json={})

    transport = httpx.MockTransport(_handler)
    return httpx.AsyncClient(transport=transport, timeout=10.0)


# ── Fakes ────────────────────────────────────────────────────────────


def _tmp_pdf() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fd:
        fd.write(b"%PDF-1.7\n%fake")
        return Path(fd.name)


def _make_app(board: ApplicationBoard, url: str):
    return SimpleNamespace(
        id=1,
        user_id=1,
        company="Stripe",
        role="Senior Backend Engineer",
        location="Remote",
        external_url=url,
        board=board,
    )


def _make_resume_doc(path: Path):
    return SimpleNamespace(
        kind="resume",
        path=str(path),
        byte_size=path.stat().st_size,
    )


def _make_screener(qid, text, answer, source=ScreenerAnswerSource.AUTO, reviewed=True):
    from datetime import UTC, datetime

    return SimpleNamespace(
        id=qid,
        question_text=text,
        question_type=ScreenerQuestionType.SHORT_TEXT,
        answer=answer,
        source=source,
        reviewed_at=datetime.now(UTC) if reviewed else None,
    )


def _make_bundle(board: ApplicationBoard, url: str, with_cover: bool = True):
    pdf = _tmp_pdf()
    cover = _tmp_pdf() if with_cover else None
    app = _make_app(board, url)
    return ApplicationBundle(
        application=app,
        resume=_make_resume_doc(pdf),
        cover_letter=_make_resume_doc(cover) if cover else None,
        screener_answers=[
            _make_screener(1, "Email", "shyam@example.com"),
            _make_screener(2, "Phone", "+1 555 555 0100"),
            _make_screener(3, "Name", "Shyam Padia"),
            _make_screener(
                4, "Why Stripe?", "Because of payments infra.", source=ScreenerAnswerSource.DRAFTED
            ),
        ],
    )


# ── Dispatcher ──────────────────────────────────────────────────────


def test_dispatch_returns_correct_adapter():
    assert isinstance(dispatch(ApplicationBoard.GREENHOUSE), GreenhouseAdapter)
    assert isinstance(dispatch(ApplicationBoard.LEVER), LeverAdapter)
    assert isinstance(dispatch(ApplicationBoard.ASHBY), AshbyAdapter)


def test_dispatch_workday_returns_manual_fallback():
    """Phase 1.x boards return an auth_required stub for now."""
    adapter = dispatch(ApplicationBoard.WORKDAY)
    assert adapter.requires_credential() is True
    assert adapter.can_submit(None) is False


@pytest.mark.asyncio
async def test_workday_fallback_returns_auth_required():
    adapter = dispatch(ApplicationBoard.WORKDAY)
    result = await adapter.submit(None, None)
    assert result.ok is False
    assert result.error == FAILURE_AUTH_REQUIRED


# ── Greenhouse ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_greenhouse_submit_success():
    bundle = _make_bundle(
        ApplicationBoard.GREENHOUSE, "https://boards.greenhouse.io/stripe/jobs/123456"
    )
    client = _mock_client(response=httpx.Response(201, json={"application_id": "GH-987"}))
    adapter = GreenhouseAdapter(http_client=client)
    result = await adapter.submit(bundle.application, bundle)
    await client.aclose()
    assert result.ok is True
    assert result.board_application_id == "GH-987"


@pytest.mark.asyncio
async def test_greenhouse_submit_auth_required_on_401():
    bundle = _make_bundle(
        ApplicationBoard.GREENHOUSE, "https://boards.greenhouse.io/stripe/jobs/123"
    )
    client = _mock_client(response=httpx.Response(401, text="auth needed"))
    result = await GreenhouseAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    assert result.ok is False
    assert result.error == FAILURE_AUTH_REQUIRED


@pytest.mark.asyncio
async def test_greenhouse_submit_field_mismatch_on_422():
    bundle = _make_bundle(
        ApplicationBoard.GREENHOUSE, "https://boards.greenhouse.io/stripe/jobs/55"
    )
    client = _mock_client(response=httpx.Response(422, text="missing field: location"))
    result = await GreenhouseAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    assert result.error == FAILURE_FIELD_MISMATCH


@pytest.mark.asyncio
async def test_greenhouse_submit_rate_limit_carries_retry_after():
    bundle = _make_bundle(
        ApplicationBoard.GREENHOUSE, "https://boards.greenhouse.io/stripe/jobs/77"
    )
    client = _mock_client(
        response=httpx.Response(429, headers={"retry-after": "120"}, text="slow down")
    )
    result = await GreenhouseAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    assert result.error == FAILURE_RATE_LIMIT
    assert result.retry_after == 120


@pytest.mark.asyncio
async def test_greenhouse_submit_unknown_on_5xx():
    bundle = _make_bundle(
        ApplicationBoard.GREENHOUSE, "https://boards.greenhouse.io/stripe/jobs/99"
    )
    client = _mock_client(response=httpx.Response(500, text="oops"))
    result = await GreenhouseAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    assert result.error == FAILURE_UNKNOWN


@pytest.mark.asyncio
async def test_greenhouse_field_mismatch_when_url_unparseable():
    bundle = _make_bundle(ApplicationBoard.GREENHOUSE, "https://example.com/")
    result = await GreenhouseAdapter().submit(bundle.application, bundle)
    assert result.error == FAILURE_FIELD_MISMATCH


@pytest.mark.asyncio
async def test_greenhouse_field_mismatch_when_resume_missing():
    pdf = _tmp_pdf()
    pdf.unlink()
    app = _make_app(ApplicationBoard.GREENHOUSE, "https://boards.greenhouse.io/stripe/jobs/12")
    bundle = ApplicationBundle(
        application=app,
        resume=SimpleNamespace(path=str(pdf), byte_size=0, kind="resume"),
        cover_letter=None,
        screener_answers=[],
    )
    result = await GreenhouseAdapter().submit(app, bundle)
    assert result.error == FAILURE_FIELD_MISMATCH


@pytest.mark.asyncio
async def test_greenhouse_submit_posts_canonical_fields_explicitly():
    """Resume-parsing override: canonical email/phone go in the form payload."""
    bundle = _make_bundle(
        ApplicationBoard.GREENHOUSE, "https://boards.greenhouse.io/stripe/jobs/333"
    )

    captured: dict = {}
    client = _mock_client(
        response=httpx.Response(201, json={"application_id": "X"}),
        capture=captured,
    )

    await GreenhouseAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    body = captured["body"].decode("utf-8", errors="replace")
    # Multipart form should carry the canonical email + phone explicitly.
    assert "shyam@example.com" in body
    assert "+1 555 555 0100" in body
    # And the resume PDF goes along.
    assert "resume.pdf" in body


def test_greenhouse_can_submit_only_for_greenhouse_urls():
    job_ok = SimpleNamespace(url="https://boards.greenhouse.io/foo/jobs/1")
    job_bad = SimpleNamespace(url="https://example.com/jobs/1")
    assert GreenhouseAdapter().can_submit(job_ok) is True
    assert GreenhouseAdapter().can_submit(job_bad) is False


# ── Lever ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lever_submit_success():
    bundle = _make_bundle(ApplicationBoard.LEVER, "https://jobs.lever.co/foo/abc-123")
    client = _mock_client(response=httpx.Response(200, json={"id": "lever-app-1"}))
    result = await LeverAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    assert result.ok is True
    assert result.board_application_id == "lever-app-1"


@pytest.mark.asyncio
async def test_lever_submit_auth_required():
    bundle = _make_bundle(ApplicationBoard.LEVER, "https://jobs.lever.co/foo/x")
    client = _mock_client(response=httpx.Response(403))
    result = await LeverAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    assert result.error == FAILURE_AUTH_REQUIRED


@pytest.mark.asyncio
async def test_lever_field_mismatch_when_url_unparseable():
    bundle = _make_bundle(ApplicationBoard.LEVER, "https://example.com/")
    result = await LeverAdapter().submit(bundle.application, bundle)
    assert result.error == FAILURE_FIELD_MISMATCH


# ── Ashby ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ashby_submit_success():
    bundle = _make_bundle(ApplicationBoard.ASHBY, "https://jobs.ashbyhq.com/foo/abc-def-123")
    client = _mock_client(response=httpx.Response(200, json={"applicationId": "ashby-1"}))
    result = await AshbyAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    assert result.ok is True
    assert result.board_application_id == "ashby-1"


@pytest.mark.asyncio
async def test_ashby_submit_field_mismatch_on_422():
    bundle = _make_bundle(ApplicationBoard.ASHBY, "https://jobs.ashbyhq.com/foo/abc")
    client = _mock_client(response=httpx.Response(422, text="missing"))
    result = await AshbyAdapter(http_client=client).submit(bundle.application, bundle)
    await client.aclose()
    assert result.error == FAILURE_FIELD_MISMATCH


# ── Common: SubmissionResult shape ──────────────────────────────────


def test_submission_result_carries_all_classification_fields():
    r = SubmissionResult(
        ok=False,
        error=FAILURE_RATE_LIMIT,
        error_message="too fast",
        retry_after=42,
    )
    assert r.error == "rate_limit"
    assert r.retry_after == 42
    assert r.error_message == "too fast"
