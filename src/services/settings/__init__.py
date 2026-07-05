"""Settings package — per-tab Settings CRUD, env-presence indicators, and
the provider model catalogs.

Plan 93 Part 1 grouped `settings_service` / `env_secrets` / `llm_models`
into this package. Callers alias the import (`from services import
settings as settings_service`) so the local name never collides with the
`config.settings` singleton.

Seam tiers: the service API lives on this `__init__` (conftest shims +
`patch("services.settings.X")`); `env_secrets` and `llm_models` are
module-tier (`services.settings.<mod>.X`).

`_PREMIUM_STAGE_PROMPTS` buckets cost by literal `prompt_name` values —
a de-facto schema, no renames (plan 91 rule §4 / plan 92 hard rules).
"""

from __future__ import annotations

from services.settings.service import (
    _PREMIUM_PROJECTION_FALLBACK as _PREMIUM_PROJECTION_FALLBACK,
)
from services.settings.service import (
    _PREMIUM_STAGE_PROMPTS as _PREMIUM_STAGE_PROMPTS,
)
from services.settings.service import (
    CostProjection,
    compute_premium_cost_projection,
    get_deployment_info,
    get_or_create,
    list_recent_generation_traces,
    update_auto_apply,
    update_generation,
    update_llm,
    update_notifications,
    update_sources,
)

__all__ = [
    "CostProjection",
    "compute_premium_cost_projection",
    "get_deployment_info",
    "get_or_create",
    "list_recent_generation_traces",
    "update_auto_apply",
    "update_generation",
    "update_llm",
    "update_notifications",
    "update_sources",
]
