"""Per-tag weight resolution + Pydantic validator (plan 65 § T2).

`Settings.score_per_dim_weights` is a JSONB shape `{tag_value: float}`.
Defaults to `{}` (empty dict → all tags weighted 1.0). Operators tune
via the Settings UI (UI editor lands in 0.3.2.04; v1 ships JSONB editable
via PUT route only). Unknown keys are dropped; values clamp to [0, 3.0].
"""

from __future__ import annotations

from pydantic import RootModel, field_validator

from models.enums import Tag


class PerDimWeights(RootModel[dict[str, float]]):
    """Strictly typed wrapper for `Settings.score_per_dim_weights`.

    Pydantic v2 RootModel — the root payload IS the dict. Validator drops
    unknown keys (security: bounds the JSONB shape) and clamps values to
    [0.0, 3.0] (caps over-weighting any single dimension).
    """

    @field_validator("root", mode="before")
    @classmethod
    def _validate(cls, v: dict[str, float] | None) -> dict[str, float]:
        allowed = {t.value for t in Tag}
        out: dict[str, float] = {}
        for k, val in (v or {}).items():
            if k not in allowed:
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            out[k] = max(0.0, min(3.0, num))
        return out


def resolve_weights(settings: object) -> dict[str, float]:
    """Return per-tag weights for scoring; defaults to all-1.0 when unset.

    `settings` is duck-typed (real Settings row, fixture, or namespace —
    any object with `.score_per_dim_weights` attr). Missing attr falls
    through to defaults.
    """
    raw = getattr(settings, "score_per_dim_weights", None) or {}
    validated = PerDimWeights(root=raw).root
    return {t.value: validated.get(t.value, 1.0) for t in Tag}


__all__ = ["PerDimWeights", "resolve_weights"]
