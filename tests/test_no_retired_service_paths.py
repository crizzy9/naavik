"""Guard: retired `services.*` dotted paths must not creep back in.

Plan 92 retired the six plan-91 re-export facades and grouped the flat
modules into packages (`services/{applications,generation,resolution,notify,
email,jobs,profile}/`). Each retired module maps to a new home below; this
lint fails on any dotted reference to a retired path in src/ or tests/ —
imports, `patch("...")` strings, and monkeypatch targets alike — so a stale
copy-paste can't silently resurrect a facade path (which would import-error
at best, or un-shim a test at worst).

If this test goes red: use the new path from `RETIRED`, or — if you are
deliberately re-introducing a module at the old location — delete its entry
here in the same commit and say why in the plan/commit message.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

# old dotted path (without the `services.` prefix) → new home
RETIRED: dict[str, str] = {
    # Phase A — plan-91 facades
    "notifications": "services.notify",
    "linkedin_resolver": "services.resolution (linkedin surface)",
    "apply_site_resolver": "services.resolution",
    "bundle_generator": "services.generation",
    "document_generator": "services.generation",
    "application_service": "services.applications",
    # Phase B1 — email package
    "email_service": "services.email (package surface)",
    "email_sync": "services.email.sync (seams: services.email)",
    "email_classifier": "services.email.classifier",
    "email_credentials": "services.email.credentials",
    "email_application_inference": "services.email.inference",
    "email_status_mapper": "services.email.status_mapper",
    "calendar_sync": "services.email.calendar_sync",
    "imap_host_guard": "services.email.imap_host_guard",
    # Phase B2 — jobs package
    "job_service": "services.jobs (package surface)",
    "jd_enrichment": "services.jobs.jd_enrichment",
    "job_extractor": "services.jobs.extractor",
    "dedup": "services.jobs.dedup",
    # Phase B3 — generation absorption
    "council": "services.generation.council",
    "critique_council": "services.generation.critique_council",
    "_council_common": "services.generation._council_common",
    "detector_loop": "services.generation.detector_loop",
    "tool_loop": "services.generation.tool_loop",
    "generation_eval": "services.generation.generation_eval",
    "voice_grounding": "services.generation.voice_grounding",
    "constitution": "services.generation.constitution",
    "ai_tell_blocklist": "services.generation.ai_tell_blocklist",
    "burstiness_check": "services.generation.burstiness_check",
    "keyword_coverage": "services.generation.keyword_coverage",
    "ethics_preflight": "services.generation.ethics_preflight",
    "hiring_manager_extractor": "services.generation.hiring_manager_extractor",
    "ats_parser_ensemble": "services.generation.ats_parser_ensemble",
    "ats_parser_fidelity": "services.generation.ats_parser_fidelity",
    # Phase B4 — profile package
    "profile_service": "services.profile (package surface)",
    "extraction": "services.profile.extraction",
    "portfolio_sync": "services.profile.portfolio_sync",
    "profile_answer_service": "services.profile.answers",
}

_SELF = Path(__file__).resolve()

# `services.X` where X is retired and not part of a longer dotted/word chain.
# A preceding dot (e.g. `services.jobs.dedup`) must NOT match `services.dedup`,
# which the literal-prefix form below already guarantees.
_PATTERNS = {name: re.compile(rf"\bservices\.{re.escape(name)}\b") for name in RETIRED}

# Import forms that bypass the dotted prefix: `from services import X [as y]`
# (single-line and inside parenthesized blocks).
_IMPORT_RE = re.compile(r"from\s+services\s+import\s+(?:\([^)]*\)|[^\n]*)", re.DOTALL)
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _scan_files() -> list[Path]:
    files = []
    for base in ("src", "tests"):
        files.extend(
            f
            for f in (_REPO / base).rglob("*.py")
            if "__pycache__" not in f.parts and f.resolve() != _SELF
        )
    return sorted(files)


@pytest.mark.parametrize("path", _scan_files(), ids=lambda p: str(p.relative_to(_REPO)))
def test_no_retired_service_paths(path: Path):
    text = path.read_text(encoding="utf-8")
    violations: list[str] = []

    for name, new_home in RETIRED.items():
        for m in _PATTERNS[name].finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            violations.append(f"line {line}: services.{name} → use {new_home}")

    for m in _IMPORT_RE.finditer(text):
        block = m.group(0)
        # first bound name only matters per alias; walk all names before `as`
        for part in block.replace("(", " ").replace(")", " ").split(","):
            bound = _NAME_RE.findall(part.split(" as ")[0].replace("import", " "))
            for name in bound:
                if name in RETIRED and name != "services":
                    line = text.count("\n", 0, m.start()) + 1
                    violations.append(
                        f"line {line}: from services import {name} → use {RETIRED[name]}"
                    )

    assert not violations, (
        f"{path.relative_to(_REPO)} references retired services paths "
        f"(plan 92):\n  " + "\n  ".join(violations)
    )
