"""Bundle generator — facade over `services/generation/` (plan 91 4.4).

The former 1076-LOC module is decomposed into
`services/generation/{trace,bundle,bundle_premium}.py`. This module
re-exports the public surface plus the seams tests touch:

- `dg` binds the `services.document_generator` facade module, so
  `patch("services.bundle_generator.dg.is_cost_capped")` (which mutates the
  shared module object) keeps intercepting every internal `dg.X` call;
- `generate_bundle` stays patchable here — the premium pipeline calls the
  free composite back through this facade;
- `assemble_corpus` / `extract_hiring_manager` module attributes are
  preserved for the tests that patch them on this module.

Facade teardown happens in Phase 8, after importers are flipped.
"""

from __future__ import annotations

from services import document_generator as dg
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
    "dg",
    "extract_hiring_manager",
    "generate_bundle",
    "regenerate_cover_letter",
    "validate_parse_fidelity",
]
