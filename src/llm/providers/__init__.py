"""Auxiliary LLM-adjacent providers.

Plan 67 (0.3.4) § T2 — providers that don't fit the `LLMProvider(ABC)`
chat-style contract (e.g. detector APIs returning a single score). Each
provider here is standalone; cost tracking persists `ApiUsage` rows
directly via the provider module's `_persist_usage` mirror.
"""

from .originality import OriginalityProvider, score_text

__all__ = ["OriginalityProvider", "score_text"]
