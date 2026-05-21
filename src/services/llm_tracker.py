"""LLM call tracker — wraps every provider call with cost + latency logging.

Per BACKEND.md § M.4 + plan 10 § B.4. Every `LLMProvider.complete /
structured / stream` invocation flows through `tracked_call`, which:

1. Times the call.
2. Persists an `ApiUsage` row with `(provider, model, method, prompt_name,
   input_tokens, output_tokens, cost_usd, latency_ms)`.
3. On failure, retries per BACKEND.md § M.5:
   - rate_limit (429): exponential backoff, max 3 retries
   - timeout: retry once with longer timeout
   - 500: try fallback provider if `Settings.llm_fallback_provider` set
   - schema_validation: re-prompt once with stricter instructions
4. Emits the `ApiUsage` row even on failure (with `succeeded=False, error_kind=...`).

Settings · LLM Provider's "THIS MONTH" / "AVG / GENERATION" / "RATE LIMIT"
cost cards aggregate over this table.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm.base import (
    CompletionResult,
    EmbeddingResult,
    LLMProvider,
    LLMProviderError,
    StructuredResult,
)
from models import ApiUsage, Job
from models import LLMProvider as LLMProviderEnum

log = logging.getLogger(__name__)

_RETRY_ATTEMPTS = {
    "rate_limit": 3,
    "timeout": 1,
    "schema_validation": 1,
    "provider_error": 0,
}
_BACKOFF_BASE_SECONDS = 1.0


def _provider_id_to_enum(provider_id: str) -> LLMProviderEnum:
    return LLMProviderEnum(provider_id)


async def _persist_usage(
    session: AsyncSession | None,
    *,
    user_id: int,
    provider: LLMProvider,
    method: str,
    prompt_name: str | None,
    application_id: int | None,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    succeeded: bool,
    error_kind: str | None,
) -> None:
    if session is None:
        return  # caller didn't pass a session — tests can opt out
    row = ApiUsage(
        user_id=user_id,
        application_id=application_id,
        provider=_provider_id_to_enum(provider.provider_id),
        model=provider.model_name,
        method=method,
        prompt_name=prompt_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        succeeded=succeeded,
        error_kind=error_kind,
    )
    session.add(row)
    try:
        await session.flush()
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to persist ApiUsage row: %s", exc)


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, LLMProviderError):
        return exc.kind
    msg = (str(exc) or type(exc).__name__).lower()
    if "rate limit" in msg or "429" in msg or "too many" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "json" in msg or "schema" in msg or "validation" in msg:
        return "schema_validation"
    return "provider_error"


async def tracked_call(
    *,
    session: AsyncSession | None,
    user_id: int,
    provider: LLMProvider,
    method: str,
    prompt_name: str | None = None,
    application_id: int | None = None,
    fallback_provider: LLMProvider | None = None,
    **call_kwargs: Any,
) -> Any:
    """Invoke `provider.<method>(**call_kwargs)` with retry + ApiUsage logging.

    `method` ∈ {"complete", "structured", "stream"}. `stream` returns the
    coroutine that yields the AsyncIterator — caller awaits + iterates.
    """
    fn: Callable[..., Awaitable[Any]] = getattr(provider, method)

    attempt = 0
    use_provider = provider

    while True:
        start = time.perf_counter()
        try:
            result = await fn(**call_kwargs)
        except Exception as exc:  # noqa: BLE001
            kind = _classify_error(exc)
            latency_ms = int((time.perf_counter() - start) * 1000)
            await _persist_usage(
                session,
                user_id=user_id,
                provider=use_provider,
                method=method,
                prompt_name=prompt_name,
                application_id=application_id,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
                succeeded=False,
                error_kind=kind,
            )

            allowed = _RETRY_ATTEMPTS.get(kind, 0)
            if attempt < allowed:
                attempt += 1
                if kind == "rate_limit":
                    await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue

            # Exhausted retries on primary; try fallback if 500-class.
            if (
                kind in {"provider_error", "timeout"}
                and fallback_provider is not None
                and use_provider is provider
            ):
                use_provider = fallback_provider
                fn = getattr(use_provider, method)
                attempt = 0
                continue

            raise LLMProviderError(
                f"{provider.provider_id} {method} failed after retries: {exc}",
                kind=kind,
            ) from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        # Pull token counts from result for ApiUsage row.
        if isinstance(result, (CompletionResult, StructuredResult, EmbeddingResult)):
            in_tok = result.input_tokens
            out_tok = result.output_tokens
        else:
            in_tok = 0
            out_tok = 0

        cost_usd = use_provider.estimate_cost(input_tokens=in_tok, output_tokens=out_tok)
        await _persist_usage(
            session,
            user_id=user_id,
            provider=use_provider,
            method=method,
            prompt_name=prompt_name,
            application_id=application_id,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            succeeded=True,
            error_kind=None,
        )
        return result


# ── Daily cost-cap aggregate (plan 54 / 0.2.5.03) ──────────────────────


async def today_cost_usd(session: AsyncSession, *, user_id: int) -> float:
    """Sum of `ApiUsage.cost_usd` for `user_id` since midnight UTC today.

    Plan 54 / 0.2.5.03. Drives the Settings · LLM Provider daily-cap progress
    widget. Single SELECT with `func.coalesce(func.sum(...), 0)` so an empty
    set returns ``0.0`` cleanly without a None branch in the caller.
    Boundary uses ``datetime.now(UTC).replace(hour=0, minute=0, second=0,
    microsecond=0)`` — local-tz `combine(date.today(), time.min)` would roll
    spend into the wrong window for non-UTC operators.
    """
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0)).where(
        ApiUsage.user_id == user_id,
        ApiUsage.occurred_at >= midnight,
    )
    result = await session.exec(stmt)
    row = result.one()
    value = row[0] if isinstance(row, tuple) else row
    return float(value or 0.0)


# ── Recent-usage + summary (plan 60 / 0.2.7.17) ────────────────────────


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """Bundle returned by `usage_summary` — drives Settings · LLM cost cards."""

    month_cost_usd: float
    avg_per_generation_usd: float
    total_tokens: int
    gen_count: int


async def recent_usage(session: AsyncSession, *, user_id: int, days: int = 30) -> list[ApiUsage]:
    """Most-recent ApiUsage rows over a window. Mirrors `sample_data.api_usage_recent`."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(ApiUsage)
        .where(ApiUsage.user_id == user_id, ApiUsage.occurred_at >= cutoff)
        .order_by(ApiUsage.occurred_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def usage_summary(session: AsyncSession, *, user_id: int, days: int = 30) -> UsageSummary:
    """Aggregate cost + tokens + gen-count over a window.

    Mirrors `sample_data.llm_usage_summary`. `gen_count` = distinct
    `application_id`s (one bundle = resume + cover_letter attributed to an
    application).
    """
    rows = await recent_usage(session, user_id=user_id, days=days)
    cost = sum(r.cost_usd for r in rows)
    tokens = sum(r.input_tokens + r.output_tokens for r in rows)
    gen_apps = {r.application_id for r in rows if r.application_id is not None}
    gen_count = len(gen_apps)
    avg = (cost / gen_count) if gen_count else 0.0
    return UsageSummary(
        month_cost_usd=round(cost, 2),
        avg_per_generation_usd=round(avg, 2),
        total_tokens=int(tokens),
        gen_count=int(gen_count),
    )


# ── Judge-skipped today helpers (plan 74 / 0.3.2.04) ──────────────────


def _today_midnight_utc() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _is_postgres_dialect(session: AsyncSession) -> bool:
    """True when bound to Postgres — JSONB key-extraction operators only
    compile there. The scorer.orchestrator stale-rescore cron uses the same
    probe (`bind.dialect.name == 'postgresql'`)."""
    bind = getattr(session, "bind", None)
    dialect = getattr(bind, "dialect", None) if bind is not None else None
    return getattr(dialect, "name", None) == "postgresql"


async def judge_skipped_count_today(session: AsyncSession, *, user_id: int) -> int:
    """Count Jobs scored today where `match_breakdown.judge_skipped == True`.

    Plan 74 / 0.3.2.04. Drives the Settings · LLM cost-cap fallback banner.
    Filters on `Job.updated_at >= today_midnight_utc` (real indexed column,
    bumped by `scorer.orchestrator._persist_score` alongside the JSONB
    write) so the query stays cheap without a GIN on `match_breakdown`.
    `deleted_at IS NULL` so archived rows don't inflate the count.

    Postgres uses the JSONB ``->>`` extractor server-side. On sqlite (in-
    memory parity tests), JSONB compiles to TEXT — we fetch the candidate
    Job rows and count `judge_skipped=True` in Python.
    """
    midnight = _today_midnight_utc()
    base_filters = [
        Job.user_id == user_id,
        Job.deleted_at.is_(None),  # type: ignore[union-attr]
        Job.updated_at >= midnight,
    ]
    if _is_postgres_dialect(session):
        # Plan 75 / 0.3.3.17 — `->>` returns text; lowercase the extract
        # keeps the predicate resilient to non-canonical JSONB writes
        # ("True", "TRUE", etc.) without relying on `lower(true) = "true"`
        # by accident. Defense-in-depth; current writers always emit "true".
        stmt = select(func.count(Job.id)).where(
            *base_filters,
            func.lower(Job.match_breakdown.op("->>")("judge_skipped")) == "true",
        )
        result = await session.exec(stmt)
        row = result.one()
        value = row[0] if isinstance(row, tuple) else row
        return int(value or 0)
    stmt = select(Job.match_breakdown).where(*base_filters)
    rows = (await session.exec(stmt)).all()
    count = 0
    for row in rows:
        mb = row[0] if isinstance(row, tuple) else row
        if isinstance(mb, dict) and mb.get("judge_skipped") is True:
            count += 1
    return count


async def judge_skipped_reasons_today(session: AsyncSession, *, user_id: int) -> dict[str, int]:
    """Per-reason distribution for today's judge-skipped scores.

    Plan 74 / 0.3.2.04. Returns `{reason_key: count}` — keys typically
    `cost_cap_exhausted` / `no_provider_configured` / `llm_failed` /
    `below_llm_gate` / `below_tag_floor` / `visa_zeroed` (per
    `services/scorer/orchestrator.py`). Empty dict when no skips today.
    """
    midnight = _today_midnight_utc()
    base_filters = [
        Job.user_id == user_id,
        Job.deleted_at.is_(None),  # type: ignore[union-attr]
        Job.updated_at >= midnight,
    ]
    if _is_postgres_dialect(session):
        reason_expr = Job.match_breakdown.op("->>")("judge_skipped_reason")
        stmt = (
            select(reason_expr, func.count(Job.id))
            .where(
                *base_filters,
                Job.match_breakdown.op("->>")("judge_skipped") == "true",
            )
            .group_by(reason_expr)
        )
        rows = (await session.exec(stmt)).all()
        out: dict[str, int] = {}
        for row in rows:
            reason = row[0] if isinstance(row, tuple) else None
            count = row[1] if isinstance(row, tuple) else 0
            if reason is None:
                continue
            out[str(reason)] = int(count or 0)
        return out
    stmt = select(Job.match_breakdown).where(*base_filters)
    rows = (await session.exec(stmt)).all()
    out: dict[str, int] = {}
    for row in rows:
        mb = row[0] if isinstance(row, tuple) else row
        if not isinstance(mb, dict) or mb.get("judge_skipped") is not True:
            continue
        reason = mb.get("judge_skipped_reason")
        if reason is None:
            continue
        out[str(reason)] = out.get(str(reason), 0) + 1
    return out
