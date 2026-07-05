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

# Patched seams — module attributes tests replace wholesale.
from llm import get_provider
from models import GeneratedDocumentKind  # callers reach it as generation.GeneratedDocumentKind
from services import llm_tracker
from services.generation.ats_parser_fidelity import validate_parse_fidelity
from services.generation.bullet_selection import (
    _REFINE_JD_CHARS as _REFINE_JD_CHARS,
)
from services.generation.bullet_selection import (
    RESUME_BULLET_CHAR_BUDGET,
    RESUME_BULLET_LINE_CAPACITY,
    regen_bullet_for_variance,
)
from services.generation.bullet_selection import (
    _ai_rank_bullets as _ai_rank_bullets,
)
from services.generation.bullet_selection import (
    _refine_one_bullet as _refine_one_bullet,
)
from services.generation.bullet_selection import (
    _render_rank_prompt as _render_rank_prompt,
)
from services.generation.bullet_selection import (
    _resolve_override as _resolve_override,
)
from services.generation.bullet_selection import (
    _split_bullets_by_override as _split_bullets_by_override,
)
from services.generation.bullet_selection import (
    _tailor_summary as _tailor_summary,
)
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
from services.generation.common import _ATS_BOARDS as _ATS_BOARDS
from services.generation.common import (
    _app_documents_dir as _app_documents_dir,
)
from services.generation.common import (
    _documents_dir as _documents_dir,
)
from services.generation.common import (
    _select_template as _select_template,
)
from services.generation.common import (
    _template_version as _template_version,
)
from services.generation.cost_cap import (
    CostCapExceededError,
    is_cost_capped,
)
from services.generation.cost_cap import (
    _today_spend as _today_spend,
)
from services.generation.cover_letter import (
    _render_cover_letter_prompt as _render_cover_letter_prompt,
)
from services.generation.cover_letter import (
    _render_cover_letter_sota_prompt as _render_cover_letter_sota_prompt,
)
from services.generation.cover_letter import (
    generate_cover_letter,
)
from services.generation.hiring_manager_extractor import extract_hiring_manager
from services.generation.maintenance import (
    PreGenerateResult,
    cleanup_stale,
    pre_generate,
    recompile_cover_letter_from_sections,
    recompile_resume_from_selection,
)
from services.generation.maintenance import (
    _application_text_overrides as _application_text_overrides,
)
from services.generation.maintenance import (
    _latest_error_free_doc as _latest_error_free_doc,
)
from services.generation.resume import (
    RESUME_MAX_ADDBACK,
    RESUME_MAX_START_BULLETS,
    generate_generic_resume,
    generate_resume,
)
from services.generation.resume import (
    _application_bullet_overrides as _application_bullet_overrides,
)
from services.generation.resume import (
    _build_resume_data as _build_resume_data,
)
from services.generation.resume import (
    _contact_lines as _contact_lines,
)
from services.generation.resume import (
    _date_range as _date_range,
)
from services.generation.resume import (
    _drop_lowest_priority as _drop_lowest_priority,
)
from services.generation.resume import (
    _ensure_min_one_per_experience as _ensure_min_one_per_experience,
)
from services.generation.resume import (
    _format_date as _format_date,
)
from services.generation.resume import (
    _normalize_handle as _normalize_handle,
)
from services.generation.resume import (
    _section_drop_queue as _section_drop_queue,
)
from services.generation.resume import (
    _section_included as _section_included,
)
from services.generation.resume import (
    _strip_scheme as _strip_scheme,
)
from services.generation.screeners import (
    _AUTO_FILL_FINGERPRINTS as _AUTO_FILL_FINGERPRINTS,
)
from services.generation.screeners import (
    _auto_field_for_question as _auto_field_for_question,
)
from services.generation.screeners import (
    _profile_value_for_field as _profile_value_for_field,
)
from services.generation.screeners import (
    _render_screener_prompt as _render_screener_prompt,
)
from services.generation.screeners import (
    answer_screeners,
    question_fingerprint,
)
from services.generation.snapshot import (
    ProfileSnapshot,
    can_reuse_existing_resume,
    load_profile_snapshot,
)
from services.generation.snapshot import (
    _bullet_inventory as _bullet_inventory,
)
from services.generation.snapshot import (
    _hash_jd as _hash_jd,
)
from services.generation.snapshot import (
    _latest_resume as _latest_resume,
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
from services.generation.voice_grounding import VoiceCorpus, assemble_corpus
from typst import compile as typst_compile
from typst import overflows
from typst.compiler import TypstError, template_path

__all__ = [
    "GENERATION_TRACE_SCHEMA_VERSION",
    "RESUME_BULLET_CHAR_BUDGET",
    "RESUME_BULLET_LINE_CAPACITY",
    "RESUME_MAX_ADDBACK",
    "RESUME_MAX_START_BULLETS",
    "BundleResult",
    "CostCapExceededError",
    "GeneratedDocumentKind",
    "PreGenerateResult",
    "ProfileSnapshot",
    "TypstError",
    "VoiceCorpus",
    "answer_screeners",
    "assemble_corpus",
    "can_reuse_existing_resume",
    "cleanup_stale",
    "extract_hiring_manager",
    "generate_bundle",
    "generate_cover_letter",
    "generate_generic_resume",
    "generate_resume",
    "get_provider",
    "is_cost_capped",
    "llm_tracker",
    "load_profile_snapshot",
    "overflows",
    "pre_generate",
    "question_fingerprint",
    "recompile_cover_letter_from_sections",
    "recompile_resume_from_selection",
    "regen_bullet_for_variance",
    "regenerate_cover_letter",
    "template_path",
    "typst_compile",
    "validate_parse_fidelity",
]
