"""Greenhouse ATS adapter — Public Boards API + Embedded API.

Per BACKEND.md § K.5. POSTs `application` + uploads resume PDF + cover letter PDF
+ answers per `Job Form Field`. No credential needed for boards.greenhouse.io;
per-company API key needed for the Embedded API path.

Endpoint shapes (well-known + documented at https://developers.greenhouse.io):

- Public Job Board API: `GET https://boards-api.greenhouse.io/v1/boards/{org}/jobs/{job_id}`
- Embedded Application Submit: `POST https://boards-api.greenhouse.io/v1/boards/{org}/jobs/{job_id}`
  body: multipart/form-data (resume + cover_letter + answers).

Workday-style "resume parsing override" not needed here — Greenhouse asks
explicitly for first_name / last_name / email and respects what you send.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from models import Application, Job, ScreenerAnswerSource

from .base import (
    FAILURE_AUTH_REQUIRED,
    FAILURE_FIELD_MISMATCH,
    FAILURE_RATE_LIMIT,
    FAILURE_UNKNOWN,
    ApplicationBundle,
    ATSAdapter,
    SubmissionResult,
)

log = logging.getLogger(__name__)

_BOARDS_API = "https://boards-api.greenhouse.io/v1/boards"
_URL_PATTERN = re.compile(
    r"https?://(?:job-?)?boards(?:-api)?\.greenhouse\.io/(?P<org>[^/]+)/jobs/(?P<job_id>\d+)"
)


def _parse_url(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    m = _URL_PATTERN.search(url)
    if not m:
        return None
    return m.group("org"), m.group("job_id")


class GreenhouseAdapter(ATSAdapter):
    board_name = "greenhouse"

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client

    def requires_credential(self) -> bool:
        # Public boards (boards-api) work without credentials. Embedded API
        # needs a per-company key, but we default to the public path.
        return False

    def can_submit(self, job: Job) -> bool:
        return _parse_url(job.url) is not None

    async def submit(
        self, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        url = application.external_url
        parsed = _parse_url(url)
        if parsed is None:
            return SubmissionResult(
                ok=False,
                error=FAILURE_FIELD_MISMATCH,
                error_message=f"could not extract greenhouse org/job_id from {url!r}",
            )
        org, job_id = parsed

        if bundle.resume is None or not Path(bundle.resume.path).exists():
            return SubmissionResult(
                ok=False,
                error=FAILURE_FIELD_MISMATCH,
                error_message="resume PDF not found on disk",
            )

        # Build the form payload — answers go in `additional_information` /
        # `answers[N]`-style keys depending on the form. We post to the public
        # Embedded JSON path: { first_name, last_name, email, phone, location,
        # resume (b64), cover_letter (b64), question_<id>: value }.
        # Resume-parsing override: pull canonical identity from screener_answers
        # (AUTO source) so we never rely on the board's PDF parser.
        eeo_payload = self._eeo_payload(bundle)
        full_name = eeo_payload.get("name") or "Applicant"
        first, _, last = full_name.partition(" ")

        files = {
            "resume": (
                "resume.pdf",
                Path(bundle.resume.path).read_bytes(),
                "application/pdf",
            ),
        }
        if bundle.cover_letter and Path(bundle.cover_letter.path).exists():
            files["cover_letter"] = (
                "cover-letter.pdf",
                Path(bundle.cover_letter.path).read_bytes(),
                "application/pdf",
            )

        data: dict[str, Any] = {
            "first_name": first or "Applicant",
            "last_name": last or first or "Applicant",
            "email": eeo_payload.get("email", ""),
            "phone": eeo_payload.get("phone", ""),
            "location": application.location or "",
        }
        for q in bundle.screener_answers:
            if q.source == ScreenerAnswerSource.USER and (q.reviewed_at is None):
                continue
            data[f"question_{q.id}"] = q.answer or ""

        endpoint = f"{_BOARDS_API}/{org}/jobs/{job_id}"
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns_client = self._client is None
        try:
            response = await client.post(endpoint, data=data, files=files)
        except httpx.RequestError as exc:
            return SubmissionResult(
                ok=False,
                error=FAILURE_UNKNOWN,
                error_message=f"network error: {exc}",
            )
        finally:
            if owns_client:
                await client.aclose()

        return _interpret_response(response)

    @staticmethod
    def _eeo_payload(bundle: ApplicationBundle) -> dict[str, str]:
        """Pull canonical identity (name/email/phone) from AUTO screener answers."""
        out: dict[str, str] = {}
        for q in bundle.screener_answers:
            text = (q.question_text or "").lower()
            if "email" in text and q.answer:
                out["email"] = q.answer
            elif "phone" in text and q.answer:
                out["phone"] = q.answer
            elif "name" in text and q.answer:
                out["name"] = q.answer
        return out


def _interpret_response(response: httpx.Response) -> SubmissionResult:
    if response.status_code == 200 or response.status_code == 201:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {}
        board_app_id = str(
            payload.get("application_id") or payload.get("id") or ""
        ) or None
        return SubmissionResult(ok=True, board_application_id=board_app_id, raw=payload)
    if response.status_code == 401 or response.status_code == 403:
        return SubmissionResult(
            ok=False,
            error=FAILURE_AUTH_REQUIRED,
            error_message=f"greenhouse rejected auth (HTTP {response.status_code})",
            raw={"text": response.text},
        )
    if response.status_code == 422:
        return SubmissionResult(
            ok=False,
            error=FAILURE_FIELD_MISMATCH,
            error_message=f"greenhouse field mismatch: {response.text[:300]}",
            raw={"text": response.text},
        )
    if response.status_code == 429:
        retry_after = int(response.headers.get("retry-after") or 60)
        return SubmissionResult(
            ok=False,
            error=FAILURE_RATE_LIMIT,
            error_message="greenhouse rate-limited",
            retry_after=retry_after,
            raw={"text": response.text},
        )
    return SubmissionResult(
        ok=False,
        error=FAILURE_UNKNOWN,
        error_message=f"greenhouse HTTP {response.status_code}: {response.text[:300]}",
        raw={"text": response.text},
    )
