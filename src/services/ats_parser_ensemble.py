"""ATS parser ensemble — plan 67 (0.3.4) § C.5 / T6.

Cross-checks the pdfplumber-based parse-fidelity score (the FREE-tier
substrate from plan 66) with two additional optional parsers:

- `pyresparser`  — Python lib; optional dep group `premium-parsers`
- OpenResume     — Node subprocess via `scripts/openresume_parser.js`

Aggregate score = mean of parsers that returned a usable signal. The
ensemble degrades gracefully:
  - pyresparser not installed -> mean of (pdfplumber, openresume)
  - Node missing             -> mean of (pdfplumber, pyresparser)
  - both optional unavailable -> just pdfplumber

T6 locks the Node subprocess approach (vs full TypeScript -> Python port).
The 60-LOC JS shim wraps OpenResume's `parse-resume-from-pdf/` subset; we
own only the shim, OpenResume handles upstream changes.
"""

from __future__ import annotations

import importlib
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from services.ats_parser_fidelity import (
    ParseScoreReport,
    validate_parse_fidelity,
)

log = logging.getLogger(__name__)


# 8 canonical fields scored across all parsers (mirrors the pdfplumber
# field set in `ats_parser_fidelity.validate_parse_fidelity`).
_CANONICAL_FIELDS = (
    "name",
    "email",
    "phone",
    "first_experience_title",
    "first_experience_company",
    "first_experience_start_date",
    "education_institution",
    "skills_section_present",
)


def _openresume_script_path() -> Path:
    """Resolve `scripts/openresume_parser.js` relative to repo root."""
    return Path(__file__).resolve().parents[2] / "scripts" / "openresume_parser.js"


@dataclass(slots=True)
class EnsembleReport:
    """Combined parser-ensemble score for one PDF."""

    aggregate_score: float
    pdfplumber_score: float | None = None
    pyresparser_score: float | None = None
    openresume_score: float | None = None
    parsers_used: list[str] = field(default_factory=list)
    fields_found: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _try_pyresparser(pdf_path: Path) -> tuple[float | None, dict[str, bool]]:
    """Run pyresparser on `pdf_path`. Returns (score | None, fields_found)."""
    try:
        module = importlib.import_module("pyresparser")
    except ImportError:
        return None, {}
    ResumeParser = getattr(module, "ResumeParser", None)
    if ResumeParser is None:
        return None, {}
    try:
        data = ResumeParser(str(pdf_path)).get_extracted_data() or {}
    except Exception as exc:  # noqa: BLE001 — third-party may raise anything
        log.warning("pyresparser raised: %s", exc)
        return None, {}
    # Map pyresparser's output to the 8 canonical fields.
    found: dict[str, bool] = {
        "name": bool(data.get("name")),
        "email": bool(data.get("email")),
        "phone": bool(data.get("mobile_number")),
        # pyresparser exposes `experience` (list of strings); presence is signal.
        "first_experience_title": bool(data.get("designation")),
        "first_experience_company": bool(data.get("company_names")),
        "first_experience_start_date": bool(data.get("total_experience")),
        "education_institution": bool(data.get("college_name") or data.get("degree")),
        "skills_section_present": bool(data.get("skills")),
    }
    score = sum(1 for v in found.values() if v) / float(len(_CANONICAL_FIELDS))
    return round(score, 3), found


def _try_openresume(
    pdf_path: Path, *, timeout_seconds: float = 10.0
) -> tuple[float | None, dict[str, bool]]:
    """Run `scripts/openresume_parser.js` via Node. Returns (score | None, fields_found).

    Returns (None, {}) when:
    - `node` not on PATH
    - script file missing
    - subprocess exits non-zero
    - stdout doesn't parse as JSON
    - subprocess timeout
    """
    node_bin = shutil.which("node")
    if node_bin is None:
        return None, {}
    script_path = _openresume_script_path()
    if not script_path.exists():
        return None, {}
    if not pdf_path.exists():
        return None, {}
    try:
        proc = subprocess.run(  # noqa: S603 — invoking known script with controlled args
            [node_bin, str(script_path), str(pdf_path)],
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        log.warning("openresume subprocess timed out after %.1fs", timeout_seconds)
        return None, {}
    except Exception as exc:  # noqa: BLE001
        log.warning("openresume subprocess raised: %s", exc)
        return None, {}
    if proc.returncode != 0:
        log.warning(
            "openresume subprocess exited %d: %s",
            proc.returncode,
            proc.stderr.decode("utf-8", errors="ignore")[:200],
        )
        return None, {}
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="ignore") or "{}")
    except json.JSONDecodeError:
        log.warning("openresume produced non-JSON stdout")
        return None, {}
    found: dict[str, bool] = {
        "name": bool(data.get("profile", {}).get("name")),
        "email": bool(data.get("profile", {}).get("email")),
        "phone": bool(data.get("profile", {}).get("phone")),
        "first_experience_title": bool((data.get("workExperiences") or [{}])[0].get("jobTitle")),
        "first_experience_company": bool((data.get("workExperiences") or [{}])[0].get("company")),
        "first_experience_start_date": bool((data.get("workExperiences") or [{}])[0].get("date")),
        "education_institution": bool((data.get("educations") or [{}])[0].get("school")),
        "skills_section_present": bool(data.get("skills")),
    }
    score = sum(1 for v in found.values() if v) / float(len(_CANONICAL_FIELDS))
    return round(score, 3), found


async def ensemble_score(
    pdf_path: Path,
    *,
    threshold: float = 0.75,
) -> EnsembleReport:
    """Run the parser ensemble + return aggregate signal.

    `pdf_path` is the freshly-rendered resume PDF. Threshold is passed
    through to pdfplumber's tier logic (silent / toast / surface).
    """
    notes: list[str] = []
    parsers_used: list[str] = []

    pdf_path = Path(pdf_path)
    # 1. pdfplumber (always runs)
    pdfplumber_report: ParseScoreReport = validate_parse_fidelity(pdf_path, threshold=threshold)
    pdfplumber_score = pdfplumber_report.score
    parsers_used.append("pdfplumber")

    # 2. pyresparser (optional)
    pyresparser_score, _ = _try_pyresparser(pdf_path)
    if pyresparser_score is not None:
        parsers_used.append("pyresparser")
    else:
        notes.append("pyresparser unavailable")

    # 3. OpenResume via Node (optional)
    openresume_score, _ = _try_openresume(pdf_path)
    if openresume_score is not None:
        parsers_used.append("openresume")
    else:
        notes.append("openresume unavailable")

    available = [
        s for s in (pdfplumber_score, pyresparser_score, openresume_score) if s is not None
    ]
    aggregate = round(sum(available) / len(available), 3) if available else 0.0

    return EnsembleReport(
        aggregate_score=aggregate,
        pdfplumber_score=pdfplumber_score,
        pyresparser_score=pyresparser_score,
        openresume_score=openresume_score,
        parsers_used=parsers_used,
        fields_found=pdfplumber_report.fields_found,
        notes=notes,
    )
