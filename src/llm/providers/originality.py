"""Originality.ai — third-party AI-detector ground-truth check.

Plan 67 (0.3.4) § C.1 + § T2. NOT a `LLMProvider(ABC)` subclass: the
API surface is single text-in -> score-out, not chat completions.

Persistence: when a `(session, user_id)` pair is provided, every call
persists an `ApiUsage` row mirroring `tracked_call` shape — provider =
`ANTHROPIC` sentinel (LLMProvider enum has no `ORIGINALITY` member;
adding one would require an alembic enum-type migration), `model =
'originality_ai_scan'`, `prompt_name = 'originality_ai_scan'`.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from models import ApiUsage
from models import LLMProvider as LLMProviderEnum

log = logging.getLogger(__name__)

# Originality.ai scan endpoint. v1 stable as of 2026-05.
ENDPOINT = "https://api.originality.ai/api/v1/scan/ai"
# Single-roundtrip charge per Originality.ai pricing page (2026-05).
COST_PER_SCAN_USD = 0.01
# Hard timeout so the detector_loop doesn't stall waiting on an unresponsive
# third-party API.
REQUEST_TIMEOUT_SECONDS = 30.0


class OriginalityProvider:
    """Wraps the Originality.ai scan API.

    Construct with an API key sourced from `Settings.originality_api_key`
    at the call site (NOT env). When the key is absent, callers receive
    `score_text(...) -> None` so the detector loop can degrade gracefully.
    """

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key or None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def score_text(self, text: str) -> float | None:
        """POST `text` to Originality.ai; return `ai_score` in [0, 1] or None.

        None on: missing api key, HTTP error, non-200 response, malformed
        body. Callers treat None as "not checked" and record
        `originality_score=None` in the audit trail.
        """
        if not self._api_key or not text:
            return None
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"content": text}
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(ENDPOINT, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            log.warning("originality.ai HTTP error: %s", exc)
            return None
        if response.status_code != 200:
            log.warning("originality.ai non-200: %s %s", response.status_code, response.text[:200])
            return None
        try:
            body = response.json()
        except ValueError:
            log.warning("originality.ai non-JSON body")
            return None
        # Response shape per docs: {"score": {"ai": 0.92, "original": 0.08}, ...}
        score_obj = body.get("score") if isinstance(body, dict) else None
        if isinstance(score_obj, dict) and "ai" in score_obj:
            try:
                return float(score_obj["ai"])
            except (TypeError, ValueError):
                return None
        # Some endpoint variants return `ai_score` flat.
        if isinstance(body, dict) and "ai_score" in body:
            try:
                return float(body["ai_score"])
            except (TypeError, ValueError):
                return None
        return None


async def _persist_usage(
    session: AsyncSession | None,
    *,
    user_id: int,
    application_id: int | None,
    succeeded: bool,
    latency_ms: int,
    cost_usd: float,
) -> None:
    """Persist one Originality.ai call to ApiUsage.

    Mirrors `services.llm_tracker._persist_usage` shape. Provider field uses
    the ANTHROPIC sentinel because the LLMProvider enum has no ORIGINALITY
    member (adding one would require an alembic enum-type migration; the
    `prompt_name` discriminator is sufficient for cost-ledger queries).
    """
    if session is None:
        return
    row = ApiUsage(
        user_id=user_id,
        application_id=application_id,
        provider=LLMProviderEnum.ANTHROPIC,
        model="originality_ai_scan",
        method="structured",
        prompt_name="originality_ai_scan",
        input_tokens=0,
        output_tokens=0,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        succeeded=succeeded,
        error_kind=None if succeeded else "originality_unavailable",
    )
    session.add(row)
    try:
        await session.flush()
    except Exception as exc:  # noqa: BLE001 — telemetry is best-effort
        log.warning("failed to persist Originality ApiUsage row: %s", exc)


async def score_text(
    *,
    text: str,
    api_key: str | None,
    session: AsyncSession | None,
    user_id: int,
    application_id: int | None = None,
) -> float | None:
    """Score `text` via Originality.ai + persist cost row.

    Returns the AI-confidence float ([0, 1]) or None when:
      - `api_key` is empty/None
      - HTTP request fails
      - response is malformed

    On any failed call the `ApiUsage` row is still persisted with
    `succeeded=False` + `cost_usd=0.0`. On success the row carries
    `cost_usd=COST_PER_SCAN_USD` so the daily cost cap counts the spend.

    `_call_at` arg is captured implicitly via `time.perf_counter` for
    `occurred_at` consistency with tracked_call (both use UTC).
    """
    provider = OriginalityProvider(api_key)
    if not provider.configured:
        return None

    _ = datetime.now(UTC)  # touch to keep import live
    start = time.perf_counter()
    score = await provider.score_text(text)
    latency_ms = int((time.perf_counter() - start) * 1000)

    succeeded = score is not None
    await _persist_usage(
        session,
        user_id=user_id,
        application_id=application_id,
        succeeded=succeeded,
        latency_ms=latency_ms,
        cost_usd=COST_PER_SCAN_USD if succeeded else 0.0,
    )
    return score
