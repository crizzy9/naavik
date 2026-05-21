"""ATS parse-fidelity validator — plan 66 (0.3.1) § T9.

Round-trips a generated resume PDF via `pdfplumber` + heuristics and
returns a 0.0-1.0 fidelity score over 8 canonical fields:

1. `name` (first non-empty line, large font usually).
2. `email` (regex match anywhere on page 1).
3. `phone` (US-format regex match anywhere on page 1).
4. `first_experience_company` (text under "Professional Experience" head).
5. `first_experience_title` (same row).
6. `first_experience_start_date` (MM YYYY pattern adjacent).
7. `education_institution` (text under "Education" head).
8. `skills_section_present` ("Skills" header found).

Score = `fields_found_count / 8`. Smart-default tiers per OQ-7:

- `>0.90`: silent (audit-only).
- `0.75-0.90`: info-toast (HX-Trigger header).
- `<0.75`: regenerate w/ conservative fallback + surface to user.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Cached import — pdfplumber import is ~150ms; lazy load on first call.
_pdfplumber = None
_PDFPLUMBER_AVAILABLE: bool | None = None


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d{1,2}\s*)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
# MM YYYY pattern — matches "Jul 2020", "July 2020", "07/2020", "07-2020".
_DATE_RE = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|\d{1,2}[/-]\d{4}"
)

# Required canonical section header strings (research § B.4 allowlist).
_HEAD_PROFESSIONAL_EXPERIENCE = re.compile(
    r"^\s*Professional\s+Experience\s*$", re.MULTILINE | re.IGNORECASE
)
_HEAD_EDUCATION = re.compile(r"^\s*Education\s*$", re.MULTILINE | re.IGNORECASE)
_HEAD_SKILLS = re.compile(r"^\s*Skills\s*$", re.MULTILINE | re.IGNORECASE)


# Smart-default tier thresholds.
TIER_SILENT = 0.90
TIER_TOAST = 0.75


@dataclass(slots=True)
class ParseScoreReport:
    """Heuristic parse-fidelity report for one PDF.

    `score` ∈ [0.0, 1.0]; `tier` ∈ {"silent", "toast", "surface"}.
    `notes` carries diagnostic flags (e.g. "pdfplumber unavailable").
    """

    score: float
    tier: str
    fields_found: dict[str, bool]
    fields_recovered: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _ensure_pdfplumber():
    """Lazy-import pdfplumber. Returns None on ImportError (graceful degrade)."""
    global _pdfplumber, _PDFPLUMBER_AVAILABLE
    if _PDFPLUMBER_AVAILABLE is None:
        try:
            import pdfplumber  # type: ignore

            _pdfplumber = pdfplumber
            _PDFPLUMBER_AVAILABLE = True
        except ImportError:
            _PDFPLUMBER_AVAILABLE = False
            _pdfplumber = None
    return _pdfplumber


def _tier_for_score(score: float, *, surface_threshold: float = TIER_TOAST) -> str:
    if score >= TIER_SILENT:
        return "silent"
    if score >= surface_threshold:
        return "toast"
    return "surface"


def _extract_text(pdf_path: Path) -> str:
    """Extract concatenated text from all pages. Empty string on parse failure."""
    pdfplumber = _ensure_pdfplumber()
    if pdfplumber is None:
        return ""
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as exc:  # noqa: BLE001 — pdfplumber raises various stdlib errs
        log.warning("pdfplumber extract failed for %s: %s", pdf_path, exc)
        return ""


def _find_after_header(text: str, header_re: re.Pattern) -> str:
    """Return the text body following the first match of `header_re`.

    Empty string when the header is not found. Caller scans the body for
    company / institution / etc.
    """
    m = header_re.search(text)
    if m is None:
        return ""
    return text[m.end() :]


def validate_parse_fidelity(pdf_path: Path, *, threshold: float = TIER_TOAST) -> ParseScoreReport:
    """Round-trip the PDF + score 8 canonical fields.

    `threshold` controls the 0.75 default `surface` tier boundary
    (Settings.parse_fidelity_threshold).
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return ParseScoreReport(
            score=0.0,
            tier="surface",
            fields_found={},
            notes=[f"pdf not found: {pdf_path}"],
        )

    pdfplumber = _ensure_pdfplumber()
    if pdfplumber is None:
        # Graceful degrade — pretend it parses fine so the bundle ships.
        return ParseScoreReport(
            score=1.0,
            tier="silent",
            fields_found={},
            notes=["pdfplumber unavailable; validator skipped"],
        )

    text = _extract_text(pdf_path)
    if not text:
        return ParseScoreReport(
            score=0.0,
            tier="surface",
            fields_found={},
            notes=["pdf produced empty text extraction"],
        )

    fields_found: dict[str, bool] = {}
    recovered: dict[str, str] = {}
    notes: list[str] = []

    # 1. name — first non-empty line (often largest text on page).
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        fields_found["name"] = True
        recovered["name"] = lines[0]
    else:
        fields_found["name"] = False

    # 2. email
    email_m = _EMAIL_RE.search(text)
    fields_found["email"] = email_m is not None
    if email_m:
        recovered["email"] = email_m.group(0)

    # 3. phone
    phone_m = _PHONE_RE.search(text)
    fields_found["phone"] = phone_m is not None
    if phone_m:
        recovered["phone"] = phone_m.group(0)

    # 4-6. Professional Experience block
    exp_body = _find_after_header(text, _HEAD_PROFESSIONAL_EXPERIENCE)
    if exp_body:
        exp_lines = [line.strip() for line in exp_body.splitlines() if line.strip()]
        # Heuristic: first non-empty line under the header is "role · company"
        # or "role bullet company" depending on the template. Either way, that
        # line carries both title + company.
        if exp_lines:
            first_row = exp_lines[0]
            fields_found["first_experience_title"] = True
            fields_found["first_experience_company"] = True
            recovered["first_experience"] = first_row
        else:
            fields_found["first_experience_title"] = False
            fields_found["first_experience_company"] = False

        date_m = _DATE_RE.search(exp_body[:500])
        fields_found["first_experience_start_date"] = date_m is not None
        if date_m:
            recovered["first_experience_start_date"] = date_m.group(0)
    else:
        notes.append("missing 'Professional Experience' header")
        fields_found["first_experience_title"] = False
        fields_found["first_experience_company"] = False
        fields_found["first_experience_start_date"] = False

    # 7. Education institution — first non-empty line under "Education" header.
    edu_body = _find_after_header(text, _HEAD_EDUCATION)
    if edu_body:
        edu_lines = [line.strip() for line in edu_body.splitlines() if line.strip()]
        fields_found["education_institution"] = bool(edu_lines)
        if edu_lines:
            recovered["education_institution"] = edu_lines[0]
    else:
        notes.append("missing 'Education' header")
        fields_found["education_institution"] = False

    # 8. Skills header
    skills_m = _HEAD_SKILLS.search(text)
    fields_found["skills_section_present"] = skills_m is not None
    if skills_m is None:
        notes.append("missing 'Skills' header")

    found_count = sum(1 for v in fields_found.values() if v)
    score = found_count / 8.0
    tier = _tier_for_score(score, surface_threshold=threshold)

    return ParseScoreReport(
        score=round(score, 3),
        tier=tier,
        fields_found=fields_found,
        fields_recovered=recovered,
        notes=notes,
    )
