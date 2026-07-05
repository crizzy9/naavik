"""Generation package — resume/cover-letter/screener generation + the
bundle orchestrators.

Plan 91 Phases 4.3/4.4 decomposed `services/document_generator.py` and
`services/bundle_generator.py` into
`{common,cost_cap,snapshot,bullet_selection,resume,cover_letter,screeners,
maintenance,trace,bundle,bundle_premium}.py`; plan 92 retired the facades
and made this `__init__` the one public surface.
`patch("services.generation.X")` targets intercept internal calls because
the submodules route cross-seam calls back through this package at call
time (`svc()` in `common.py`).
"""

from __future__ import annotations

from services.ats_parser_fidelity import validate_parse_fidelity
from services.generation.bundle import (
    BundleResult,
    generate_bundle,
    regenerate_cover_letter,
)
from services.generation.bundle import (
    _extract_must_haves as _extract_must_haves,
)
from services.generation.bundle import (
    _load_profile_experiences as _load_profile_experiences,
)
from services.generation.bundle import (
    _resume_text_for_coverage as _resume_text_for_coverage,
)
from services.generation.bundle_premium import (
    _generate_bundle_premium as _generate_bundle_premium,
)
from services.generation.trace import (
    GENERATION_TRACE_SCHEMA_VERSION,
)
from services.generation.trace import (
    _initial_trace as _initial_trace,
)
from services.generation.trace import (
    _persist_trace as _persist_trace,
)
from services.hiring_manager_extractor import extract_hiring_manager
from services.voice_grounding import VoiceCorpus, assemble_corpus

__all__ = [
    "GENERATION_TRACE_SCHEMA_VERSION",
    "BundleResult",
    "VoiceCorpus",
    "assemble_corpus",
    "extract_hiring_manager",
    "generate_bundle",
    "regenerate_cover_letter",
    "validate_parse_fidelity",
]
