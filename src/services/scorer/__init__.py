"""Naavik scorer — hybrid layered scoring substrate (plan 65, 0.3.0).

Module structure per plan 65 § T11:

    src/services/scorer/
    ├── __init__.py           ← re-exports + module-level constants
    ├── visa.py               ← layer 1a (deterministic visa filter)
    ├── tag_layer.py          ← layer 1b (weighted tag overlap)
    ├── semantic_layer.py     ← layer 2 (pgvector cosine)
    ├── weights.py            ← per-tag weight resolution
    ├── llm_judge.py          ← layer 4 (LLM-as-judge + cost-cap probe)
    └── orchestrator.py       ← end-to-end score_job_layered + cron entries

Backward-compat: every existing import (`from services.scorer import
apply_visa_filter, needs_visa_zero_out`) continues to resolve via the
re-exports below — no callsite changes required.
"""

from __future__ import annotations

# ── Module-level constants (orchestrator + tests reference) ───────────
# Layer 1 floor — below this, short-circuit with `judge_skipped="below_tag_floor"`.
_TAG_FLOOR = 0.10

# Layer 3 gate — composite (0.4·tag + 0.6·semantic) must clear this for LLM judge.
_LLM_GATE = 0.50

# Composite weights — favor semantic over tag (richer signal per research § D.7).
_TAG_WEIGHT = 0.4
_SEMANTIC_WEIGHT = 0.6

# Cost-cap probe — conservative bound on a single Sonnet 4.6 judge call.
# ~5K input + 500 output tokens → ~$0.015. Tighten post-launch from ApiUsage.
_ESTIMATED_JUDGE_COST_USD = 0.015

# Top-K bullets passed to the LLM judge as candidate context. The LLM then
# returns up to MAX_SUGGESTED_BULLETS (=8) IDs from this pool.
_K_CANDIDATE_BULLETS = 12

# Cron batch size — one invocation processes this many jobs per user.
_BATCH_SIZE = 50


# ── Backward-compat re-exports (existing callsites) ───────────────────
from .visa import (  # noqa: E402
    _BLOCKING_RESTRICTIONS,
    apply_visa_filter,
    needs_visa_zero_out,
)


def __getattr__(name):
    """Lazy re-export to avoid importing orchestrator at package import time.

    Orchestrator pulls Bullet/Experience/ProfileEmbedding + the LLM stack;
    loading it eagerly would force every scorer.* consumer into that import
    graph. Pull on demand instead.
    """
    if name == "score_job_layered":
        from .orchestrator import score_job_layered

        return score_job_layered
    if name == "score_unscored_jobs":
        from .orchestrator import score_unscored_jobs

        return score_unscored_jobs
    if name == "rescore_stale_jobs":
        from .orchestrator import rescore_stale_jobs

        return rescore_stale_jobs
    raise AttributeError(f"module 'services.scorer' has no attribute {name!r}")


__all__ = [
    # Constants
    "_TAG_FLOOR",
    "_LLM_GATE",
    "_TAG_WEIGHT",
    "_SEMANTIC_WEIGHT",
    "_ESTIMATED_JUDGE_COST_USD",
    "_K_CANDIDATE_BULLETS",
    "_BATCH_SIZE",
    "_BLOCKING_RESTRICTIONS",
    # Re-exports
    "apply_visa_filter",
    "needs_visa_zero_out",
    # Lazy re-exports (via __getattr__)
    "score_job_layered",
    "score_unscored_jobs",
    "rescore_stale_jobs",
]
