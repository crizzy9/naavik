"""ATS postmortem capture — HTTP trace + AI-summarized analysis on failure.

Per docs/plans/52-0.2.3.02-postmortem-on-failure.md.

Best-effort diagnostic add-on: capture failure trace + LLM-summarized analysis
to `<data_dir>/data/postmortems/<application_id>/<utc-ts>/{trace.json,
analysis.md}`. Any internal failure (LLM unavailable, disk full, schema fail)
swallows + returns None; never raises into `_record_failure`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from llm import LLMProviderError, get_provider
from llm.prompts.ats_postmortem import PROMPT, PostmortemAnalysis
from models import Application, Settings
from services import llm_tracker

log = logging.getLogger(__name__)

_RESPONSE_BODY_CAP = 32_768
_SECRET_KEY_RE = re.compile(
    r"api[_-]?key|cookie|token|password|secret|authorization", re.IGNORECASE
)
_REDACTED = "[REDACTED]"
_TIMESTAMP_FMT = "%Y-%m-%dT%H-%M-%SZ"


@dataclass(slots=True)
class PostmortemTrace:
    """Structured failure trace persisted as `trace.json`."""

    application_id: int
    board: str
    captured_at: str  # ISO 8601 UTC
    failure_kind: str
    failure_message: str
    request_url: str | None
    request_body_redacted: Any
    response_status: int | None
    response_body_excerpt: str | None
    screenshot_path: str | None = None  # 0.2.3.01 placeholder


def _postmortems_root() -> Path:
    raw = app_settings.data_dir
    base = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
    if not base.is_absolute():
        base = base.resolve()
    return base / "data" / "postmortems"


def _redact(value: Any) -> Any:
    """Recursively strip secret-looking keys from dicts/lists."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _SECRET_KEY_RE.search(k):
                out[k] = _REDACTED
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _build_trace(
    *,
    application: Application,
    failure_kind: str,
    failure_message: str,
    raw: dict | None,
    captured_at: datetime,
) -> PostmortemTrace:
    raw = raw or {}
    request_url = raw.get("request_url")
    response_status = raw.get("response_status")
    if isinstance(response_status, str):
        try:
            response_status = int(response_status)
        except ValueError:
            response_status = None

    # The 3 shipped adapters populate `raw={"text": response.text}` on failure.
    # `request_url` / `response_status` / `response_body` are honored when present
    # (forward-compat for richer adapter shapes, including 0.2.3.01 Playwright).
    body = raw.get("response_body")
    if body is None:
        body = raw.get("text")
    response_body_excerpt: str | None
    if body is None:
        response_body_excerpt = None
    elif isinstance(body, str):
        response_body_excerpt = body[:_RESPONSE_BODY_CAP]
    else:
        response_body_excerpt = json.dumps(body, default=str)[:_RESPONSE_BODY_CAP]

    request_body = raw.get("request_body")
    request_body_redacted = _redact(request_body) if request_body is not None else None

    return PostmortemTrace(
        application_id=application.id,
        board=application.board.value if application.board else "unknown",
        captured_at=captured_at.isoformat(),
        failure_kind=failure_kind,
        failure_message=failure_message,
        request_url=request_url,
        request_body_redacted=request_body_redacted,
        response_status=response_status,
        response_body_excerpt=response_body_excerpt,
    )


async def _analyze(
    *,
    session: AsyncSession,
    application: Application,
    settings: Settings,
    trace: PostmortemTrace,
) -> PostmortemAnalysis | None:
    """LLM-summarize the trace via `tracked_call`. None if provider unavailable."""
    try:
        provider = get_provider(settings)
    except LLMProviderError as exc:
        log.info("postmortem skipping LLM analysis: %s", exc)
        return None

    rendered = PROMPT.format(trace_json=json.dumps(asdict(trace), default=str))
    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=application.user_id,
            provider=provider,
            method="structured",
            prompt_name="ats_postmortem",
            application_id=application.id,
            prompt=rendered,
            schema=PostmortemAnalysis,
        )
    except LLMProviderError as exc:
        log.warning("postmortem LLM call failed: %s", exc)
        return None
    try:
        return PostmortemAnalysis.model_validate(result.value)
    except Exception as exc:  # noqa: BLE001 — Pydantic ValidationError + edge cases
        log.warning("postmortem analysis schema invalid: %s", exc)
        return None


def _render_markdown(trace: PostmortemTrace, analysis: PostmortemAnalysis | None) -> str:
    header = (
        f"# ATS postmortem — application {trace.application_id}\n\n"
        f"- Board: `{trace.board}`\n"
        f"- Captured at: `{trace.captured_at}`\n"
        f"- Failure kind: `{trace.failure_kind}`\n"
        f"- Failure message: {trace.failure_message}\n\n"
    )
    if analysis is None:
        body = (
            "## Analysis\n\n"
            "AI analysis unavailable - LLM provider not configured or unreachable.\n\n"
            "See `trace.json` for the raw request/response trace.\n"
        )
    else:
        body = (
            f"## Analysis\n\n"
            f"**Classified as:** `{analysis.failure_kind}`\n\n"
            f"### Summary\n\n{analysis.summary}\n\n"
            f"### Suggested action\n\n{analysis.suggested_action}\n"
        )
    return header + body


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


async def capture_postmortem(
    *,
    session: AsyncSession,
    application: Application,
    failure_kind: str,
    failure_message: str,
    raw: dict | None,
    settings: Settings,
) -> str | None:
    """Persist a postmortem; return relative path stored in submission_artifacts.

    Best-effort: any exception → log + return None. Never raises into the
    caller (`_record_failure`) — the postmortem is a diagnostic add-on, not
    a submission gate.

    Returns relative-to-data_dir path stem `postmortems/<application_id>/<ts>`.
    """
    try:
        now = datetime.now(UTC)
        ts = now.strftime(_TIMESTAMP_FMT)
        trace = _build_trace(
            application=application,
            failure_kind=failure_kind,
            failure_message=failure_message,
            raw=raw,
            captured_at=now,
        )
        analysis = await _analyze(
            session=session, application=application, settings=settings, trace=trace
        )
        root = _postmortems_root()
        target_dir = root / str(application.id) / ts
        _atomic_write(target_dir / "trace.json", json.dumps(asdict(trace), indent=2, default=str))
        _atomic_write(target_dir / "analysis.md", _render_markdown(trace, analysis))
        return f"postmortems/{application.id}/{ts}"
    except Exception as exc:  # noqa: BLE001 — diagnostic; never block failure recording
        log.warning("capture_postmortem failed for application %s: %s", application.id, exc)
        return None


__all__ = ["PostmortemTrace", "capture_postmortem"]
