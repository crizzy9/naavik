"""Daily LLM cost-cap probe (spend query + cap comparison).

Split out of services/document_generator.py in plan 91 Phase 4.3;
behaviour unchanged. Internal calls to patched seams go through `svc()`
(the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    ApiUsage,
    Settings,
)
from services.generation.common import svc

log = logging.getLogger(__name__)


class CostCapExceededError(Exception):
    """Today's LLM spend exceeded `Settings.daily_llm_cost_cap_usd`."""


async def _today_spend(session: AsyncSession, user_id: int) -> float:
    """Sum `ApiUsage.cost_usd` for the current UTC day for one user."""
    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
    stmt = select(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0)).where(
        ApiUsage.user_id == user_id,
        ApiUsage.occurred_at >= today_start,
        ApiUsage.succeeded.is_(True),
    )
    result = (await session.exec(stmt)).one()
    if isinstance(result, tuple):
        result = result[0]
    return float(result or 0.0)


async def is_cost_capped(session: AsyncSession, user_id: int, settings: Settings) -> bool:
    """Return True if `daily_llm_cost_cap_usd` is set and reached."""
    if settings.daily_llm_cost_cap_usd is None:
        return False
    spent = await svc()._today_spend(session, user_id)
    return spent >= float(settings.daily_llm_cost_cap_usd)
