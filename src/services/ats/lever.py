"""Lever ATS adapter — public posting API.

Per BACKEND.md § K.5. POSTs `application` + attaches resume.

Endpoint: `POST https://api.lever.co/v0/postings/{site}/{posting_id}/apply`
Body: multipart/form-data; resume + name + email + phone + custom answers.
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

_API = "https://api.lever.co/v0"
_URL_PATTERN = re.compile(
    r"https?://jobs\.lever\.co/(?P<site>[^/]+)/(?P<posting_id>[a-zA-Z0-9-]+)"
)


def _parse_url(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    m = _URL_PATTERN.search(url)
    if not m:
        return None
    return m.group("site"), m.group("posting_id")


class LeverAdapter(ATSAdapter):
    board_name = "lever"

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client

    def requires_credential(self) -> bool:
        return False

    def can_submit(self, job: Job) -> bool:
        return _parse_url(job.url) is not None

    async def submit(
        self, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        parsed = _parse_url(application.external_url)
        if parsed is None:
            return SubmissionResult(
                ok=False,
                error=FAILURE_FIELD_MISMATCH,
                error_message=f"could not parse lever URL {application.external_url!r}",
            )
        site, posting_id = parsed

        if bundle.resume is None or not Path(bundle.resume.path).exists():
            return SubmissionResult(
                ok=False,
                error=FAILURE_FIELD_MISMATCH,
                error_message="resume PDF missing",
            )

        eeo = _eeo_payload(bundle)
        data: dict[str, Any] = {
            "name": eeo.get("name") or "Applicant",
            "email": eeo.get("email") or "",
            "phone": eeo.get("phone") or "",
        }
        files = {
            "resume": (
                "resume.pdf",
                Path(bundle.resume.path).read_bytes(),
                "application/pdf",
            ),
        }
        # Lever exposes per-posting custom questions via `customQuestions[<idx>][response]`.
        for idx, q in enumerate(bundle.screener_answers):
            if q.source == ScreenerAnswerSource.USER and q.reviewed_at is None:
                continue
            data[f"customQuestions[{idx}][text]"] = q.question_text
            data[f"customQuestions[{idx}][response]"] = q.answer or ""

        endpoint = f"{_API}/postings/{site}/{posting_id}/apply"
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns = self._client is None
        try:
            response = await client.post(endpoint, data=data, files=files)
        except httpx.RequestError as exc:
            return SubmissionResult(
                ok=False, error=FAILURE_UNKNOWN, error_message=str(exc)
            )
        finally:
            if owns:
                await client.aclose()

        return _interpret_response(response)


def _eeo_payload(bundle: ApplicationBundle) -> dict[str, str]:
    out: dict[str, str] = {}
    for q in bundle.screener_answers:
        t = (q.question_text or "").lower()
        if "email" in t and q.answer:
            out["email"] = q.answer
        elif "phone" in t and q.answer:
            out["phone"] = q.answer
        elif "name" in t and q.answer:
            out["name"] = q.answer
    return out


def _interpret_response(response: httpx.Response) -> SubmissionResult:
    if 200 <= response.status_code < 300:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {}
        return SubmissionResult(
            ok=True,
            board_application_id=str(payload.get("id") or "") or None,
            raw=payload,
        )
    if response.status_code in (401, 403):
        return SubmissionResult(
            ok=False,
            error=FAILURE_AUTH_REQUIRED,
            error_message=f"lever auth rejected (HTTP {response.status_code})",
            raw={"text": response.text},
        )
    if response.status_code == 422:
        return SubmissionResult(
            ok=False,
            error=FAILURE_FIELD_MISMATCH,
            error_message=f"lever field mismatch: {response.text[:300]}",
            raw={"text": response.text},
        )
    if response.status_code == 429:
        retry_after = int(response.headers.get("retry-after") or 60)
        return SubmissionResult(
            ok=False,
            error=FAILURE_RATE_LIMIT,
            error_message="lever rate-limited",
            retry_after=retry_after,
        )
    return SubmissionResult(
        ok=False,
        error=FAILURE_UNKNOWN,
        error_message=f"lever HTTP {response.status_code}: {response.text[:300]}",
        raw={"text": response.text},
    )
