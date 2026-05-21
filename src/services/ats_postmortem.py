"""ATS postmortem capture — HTTP trace + AI-summarized analysis on failure.

Per docs/plans/52-0.2.3.02-postmortem-on-failure.md.

Best-effort diagnostic add-on: capture failure trace + LLM-summarized analysis
to `<data_dir>/data/postmortems/<application_id>/<utc-ts>/{trace.json,
analysis.md}`. Any internal failure (LLM unavailable, disk full, schema fail)
swallows + returns None; never raises into `_record_failure`.
"""

from __future__ import annotations

import base64
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

# Plan 56 / 0.2.7.18 — value-shape patterns that match auth material echoed
# back in scraper-controlled response bodies (ATS error pages occasionally
# mirror the request's auth header). Applied to `response_body_excerpt`
# BEFORE the 32 KB truncate so the persisted trace.json + LLM postmortem
# prompt input never see the literal token. Best-effort defense in depth,
# not a comprehensive secrets scrubber — the canonical defense is the ATS
# adapter never including auth material in `raw["text"]` in the first place.
_VALUE_PATTERN_REDACTIONS = [
    # Bearer / JWT — case-insensitive header form (length-min 20 chars after prefix)
    re.compile(r"(?i)\b(?:bearer|jwt)\s+[A-Za-z0-9._\-+/=]{20,}"),
    # JWT (3-segment base64url) — bare form even without bearer prefix
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
    # Set-Cookie / Cookie / Authorization HTTP header value — match whether
    # the header sits at line start or follows scraper-prose like "failed: ".
    # `^` would miss the latter; `\b` covers both.
    re.compile(r"(?im)\b(?:Set-Cookie|Cookie|Authorization):\s*[^\n\r]+"),
    # OAuth access / refresh / id token URL params (length-min 20 chars after `=`)
    re.compile(r"(?i)(?:access_token|refresh_token|id_token)=[A-Za-z0-9._\-+/=]{20,}"),
]


def _redact_value_patterns(text: str) -> str:
    """Apply value-shape regex redactions to a raw string.

    Complements `_redact()` (which only walks dict keys) — `_redact()` never
    sees `response_body_excerpt` since the response body arrives as a raw
    string, not a dict. Used on the response body BEFORE truncate + persist
    + LLM-prompt feed (see `_build_trace`).
    """
    out = text
    for pat in _VALUE_PATTERN_REDACTIONS:
        out = pat.sub(_REDACTED, out)
    return out


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
    # Plan 63 / 0.2.7.10 § C.5 — relative-to-data_dir path to a PNG capture
    # emitted by Playwright-driven adapters via `raw["screenshot_b64"]`.
    # Always None for the 3 HTTP adapters (Greenhouse / Lever / Ashby).
    screenshot_path: str | None = None


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
    screenshot_path: str | None = None,
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
    # (forward-compat for richer adapter shapes, including plan 63 Playwright).
    body = raw.get("response_body")
    if body is None:
        body = raw.get("text")
    response_body_excerpt: str | None
    if body is None:
        response_body_excerpt = None
    elif isinstance(body, str):
        # Plan 56 / 0.2.7.18 — value-pattern redact BEFORE truncate.
        response_body_excerpt = _redact_value_patterns(body)[:_RESPONSE_BODY_CAP]
    else:
        response_body_excerpt = _redact_value_patterns(json.dumps(body, default=str))[
            :_RESPONSE_BODY_CAP
        ]

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
        screenshot_path=screenshot_path,
    )


def _write_screenshot(target_dir: Path, screenshot_b64: str) -> str | None:
    """Atomic-write a base64-PNG into the postmortem dir; return relative filename.

    Best-effort: malformed base64 / I/O error → log + return None. Per plan 63
    § C.5, the postmortem layer does NOT redact PNG content — that's the
    adapter's responsibility (e.g. Workday SSN page → adapter elects not to
    populate `raw["screenshot_b64"]`).
    """
    try:
        png_bytes = base64.b64decode(screenshot_b64, validate=False)
    except Exception as exc:  # noqa: BLE001 — diagnostic; never block
        log.warning("postmortem screenshot decode failed: %s", exc)
        return None
    if not png_bytes:
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=str(target_dir), prefix=".tmp-")
        with os.fdopen(fd, "wb") as fh:
            fh.write(png_bytes)
        os.replace(tmp, target_dir / "screenshot.png")
    except OSError as exc:
        log.warning("postmortem screenshot write failed: %s", exc)
        with contextlib.suppress(OSError, NameError):
            os.unlink(tmp)
        return None
    return "screenshot.png"


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
        root = _postmortems_root()
        target_dir = root / str(application.id) / ts

        # Plan 63 / 0.2.7.10 § C.5 — write Playwright screenshot bytes BEFORE
        # building the trace dataclass so the relative path makes it into
        # trace.json. HTTP adapters never emit `raw["screenshot_b64"]`, so
        # `screenshot_path` stays None for them.
        screenshot_path: str | None = None
        screenshot_b64 = (raw or {}).get("screenshot_b64")
        if isinstance(screenshot_b64, str) and screenshot_b64:
            screenshot_path = _write_screenshot(target_dir, screenshot_b64)

        trace = _build_trace(
            application=application,
            failure_kind=failure_kind,
            failure_message=failure_message,
            raw=raw,
            captured_at=now,
            screenshot_path=screenshot_path,
        )
        analysis = await _analyze(
            session=session, application=application, settings=settings, trace=trace
        )
        _atomic_write(target_dir / "trace.json", json.dumps(asdict(trace), indent=2, default=str))
        _atomic_write(target_dir / "analysis.md", _render_markdown(trace, analysis))
        return f"postmortems/{application.id}/{ts}"
    except Exception as exc:  # noqa: BLE001 — diagnostic; never block failure recording
        log.warning("capture_postmortem failed for application %s: %s", application.id, exc)
        return None


__all__ = ["PostmortemTrace", "capture_postmortem"]
