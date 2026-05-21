"""ATS adapter base interfaces.

Per BACKEND.md § K.5 + plan 10 § C.4. Wave 6 ships Greenhouse / Lever / Ashby
(public APIs); Workday / LinkedIn / Indeed / Generic are Phase 1.x.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

from models import Application, ApplicationScreenerAnswer, GeneratedDocument, Job

# Failure-classification taxonomy — maps to Application.submission_artifacts.last_failure.kind
FAILURE_CAPTCHA = "captcha"
FAILURE_RATE_LIMIT = "rate_limit"
FAILURE_AUTH_REQUIRED = "auth_required"
FAILURE_FIELD_MISMATCH = "field_mismatch"
FAILURE_UNKNOWN = "unknown"

ALL_FAILURE_KINDS = frozenset(
    {
        FAILURE_CAPTCHA,
        FAILURE_RATE_LIMIT,
        FAILURE_AUTH_REQUIRED,
        FAILURE_FIELD_MISMATCH,
        FAILURE_UNKNOWN,
    }
)


class ATSError(Exception):
    """Adapter exploded in a way the caller didn't predict."""


@dataclass(slots=True)
class SubmissionResult:
    """Per-board submission outcome.

    `raw` carries provider response for audit + postmortem. Recognized keys
    (plan 63 / 0.2.7.10 § C.5; HTTP adapters populate a subset):

    - `request_url: str | None`    — URL the adapter POSTed to
    - `request_body: dict | None`  — request payload (redacted in postmortem)
    - `response_status: int | None`
    - `response_body: str | None`  — raw response body (replaces legacy `text`)
    - `text: str | None`           — legacy alias for `response_body`
    - `screenshot_b64: str | None` — base64 PNG for Playwright adapters; the
      postmortem layer writes it to
      `<data_dir>/data/postmortems/<app>/<ts>/screenshot.png`
    - `exception_type: str | None` — Playwright-runtime-exception class name

    `confidence` (plan 63 § D.5) — HTTP adapters always emit 1.0; Generic
    adapter emits the LLM-form-fill confidence. Below
    `Settings.ats_generic_llm_confidence_threshold` (default 0.7) → caller
    treats as `FAILURE_FIELD_MISMATCH` regardless of `ok`.
    """

    ok: bool
    board_application_id: str | None = None
    error: str | None = None  # one of FAILURE_* when ok=False
    error_message: str | None = None
    retry_after: int | None = None  # seconds before next attempt (rate_limit)
    raw: dict | None = None
    confidence: float | None = None


@dataclass(slots=True)
class ApplicationBundle:
    """Everything an ATS adapter needs to submit."""

    application: Application
    resume: GeneratedDocument | None
    cover_letter: GeneratedDocument | None
    screener_answers: list[ApplicationScreenerAnswer] = field(default_factory=list)
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ATSAdapter(ABC):
    """Per-board adapter contract."""

    board_name: str = "abstract"

    @abstractmethod
    async def submit(self, application: Application, bundle: ApplicationBundle) -> SubmissionResult:
        """Submit the bundle to the board. Never raises for predictable failures —
        return SubmissionResult(ok=False, error=<FAILURE_*>) instead.

        Raises ATSError only for adapter-internal bugs.
        """

    @abstractmethod
    def can_submit(self, job: Job) -> bool:
        """True if this adapter knows how to dispatch to the given Job."""

    @abstractmethod
    def requires_credential(self) -> bool:
        """True for boards that need stored cookies / API keys per user."""
