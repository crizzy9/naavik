"""Daily LLM cost-cap probe (spend query + cap comparison).

Split out of services/document_generator.py in plan 91 Phase 4.3;
behaviour unchanged. Internal calls to patched seams go through `svc()`
(the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Settings,
)
from services.generation.common import svc

log = logging.getLogger(__name__)


class CostCapExceededError(Exception):
    """Today's LLM spend exceeded `Settings.daily_llm_cost_cap_usd`."""


async def _today_spend(session: AsyncSession, user_id: int) -> float:
    """Today's spend for the cap comparison — delegates to the canonical
    `llm_tracker.today_cost_usd`.

    Plan 91 6.2: this used to be a THIRD competing spend implementation with
    two bugs — `datetime.combine(date.today(), ...)` used the operator's
    LOCAL calendar date while labelling it UTC (wrong window for non-UTC
    operators), and `succeeded IS TRUE` excluded failed-call spend that the
    tracker counts. Kept as a delegating wrapper because three tests patch
    `services.document_generator._today_spend` as the cost seam.
    """
    return await svc().llm_tracker.today_cost_usd(session, user_id=user_id)


async def is_cost_capped(session: AsyncSession, user_id: int, settings: Settings) -> bool:
    """Return True if `daily_llm_cost_cap_usd` is set and reached."""
    if settings.daily_llm_cost_cap_usd is None:
        return False
    spent = await svc()._today_spend(session, user_id)
    return spent >= float(settings.daily_llm_cost_cap_usd)
