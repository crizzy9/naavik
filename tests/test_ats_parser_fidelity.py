"""ATS parse-fidelity validator — plan 66 (0.3.1) § T9.

Smoke tests on the actual `onepage_ats.typ` template + happy/sad paths
on text-only inputs (mock pdfplumber). Avoids shipping binary PDF
fixtures (gitignored anyway); the round-trip is exercised end-to-end
via the manual QA gate.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from services.generation.ats_parser_fidelity import (
    TIER_SILENT,
    TIER_TOAST,
    ParseScoreReport,
    _tier_for_score,
    validate_parse_fidelity,
)

pytestmark = pytest.mark.uses_sample_data_shims

_HAS_TYPST = shutil.which("typst") is not None


def test_tier_for_score_boundaries():
    assert _tier_for_score(0.95) == "silent"
    assert _tier_for_score(TIER_SILENT) == "silent"
    assert _tier_for_score(0.80) == "toast"
    assert _tier_for_score(TIER_TOAST) == "toast"
    assert _tier_for_score(0.70) == "surface"
    assert _tier_for_score(0.0) == "surface"


def test_validate_parse_fidelity_missing_pdf_returns_zero(tmp_path):
    report = validate_parse_fidelity(tmp_path / "nonexistent.pdf")
    assert report.score == 0.0
    assert report.tier == "surface"
    assert any("not found" in n for n in report.notes)


def test_validate_parse_fidelity_pdfplumber_unavailable_returns_one(tmp_path):
    """Graceful degrade — when pdfplumber is missing, validator no-ops to 1.0."""
    # Real PDF file must exist for the not-found check to pass.
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    with patch("services.generation.ats_parser_fidelity._ensure_pdfplumber", return_value=None):
        report = validate_parse_fidelity(pdf_path)
    assert report.score == 1.0
    assert report.tier == "silent"
    assert any("pdfplumber unavailable" in n for n in report.notes)


def test_validate_parse_fidelity_empty_text_extraction_returns_zero(tmp_path):
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    with patch("services.generation.ats_parser_fidelity._extract_text", return_value=""):
        report = validate_parse_fidelity(pdf_path)
    assert report.score == 0.0
    assert report.tier == "surface"


def test_validate_parse_fidelity_full_resume_text_scores_high(tmp_path):
    """Mocked text extraction returning a full ATS-friendly resume scores 8/8."""
    sample_text = """Shyam Padia
Senior ML Platform Engineer · 8 yrs
shyam@example.com • +1 555 555 0100 • Boston, MA

Summary
Backend + ML engineer with 8+ years.

Professional Experience
Senior Software Engineer • Intuit, Mountain View
Jul 2020 - Present
• Shipped ML platform with 99.99% uptime
• Cut latency from 80ms to 12ms

Skills
Languages: Python, Go, Rust

Education
Northeastern • MS Computer Science (GPA: 3.85)
Sep 2014 - May 2016
"""
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    with patch("services.generation.ats_parser_fidelity._extract_text", return_value=sample_text):
        report = validate_parse_fidelity(pdf_path)
    assert report.score >= 0.875  # at least 7/8 fields
    assert report.tier in ("silent", "toast")
    assert report.fields_found["name"]
    assert report.fields_found["email"]
    assert report.fields_found["phone"]
    assert report.fields_found["skills_section_present"]


def test_validate_parse_fidelity_missing_headers_scores_low(tmp_path):
    """No 'Professional Experience' / 'Education' / 'Skills' headers → low score."""
    sample_text = """Shyam Padia
shyam@example.com

I do stuff.
"""
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    with patch("services.generation.ats_parser_fidelity._extract_text", return_value=sample_text):
        report = validate_parse_fidelity(pdf_path)
    assert report.score < TIER_TOAST
    assert report.tier == "surface"


def test_parse_score_report_dataclass_shape():
    report = ParseScoreReport(score=0.5, tier="toast", fields_found={"x": True})
    assert report.score == 0.5
    assert report.tier == "toast"
    assert report.fields_found == {"x": True}
    assert report.notes == []


@pytest.mark.skipif(not _HAS_TYPST, reason="typst not on PATH")
def test_validate_parse_fidelity_on_real_onepage_pdf(tmp_path):
    """End-to-end smoke test — compile the consolidated onepage template +
    parse-fidelity-check its output."""
    import json
    import subprocess

    template_dir = Path(__file__).resolve().parent.parent / "src" / "typst" / "templates"
    template = template_dir / "onepage.typ"
    # Item 2 (2026-07): payload matches the cv.tex-conversion template shape
    # (structured jobentry/educationentry fields; no headline).
    data = {
        "profile": {"full_name": "Test Candidate"},
        "contact_lines": [
            [
                {"text": "+1 555 0100", "href": None},
                {"text": "test@example.com", "href": "mailto:test@example.com"},
                {"text": "City", "href": None},
            ],
            [{"text": "linkedin.com/in/test", "href": "https://linkedin.com/in/test"}],
        ],
        "summary": "Engineer with experience.",
        "experiences": [
            {
                "company": "Acme",
                "title": "Senior Engineer",
                "location": "City",
                "dates": "Jan 2022 – Present",
                "bullets": ["Shipped a feature.", "Cut costs by half."],
            }
        ],
        "education": [
            {
                "institution": "University",
                "school": None,
                "location": "City",
                "dates": "Sep 2014 – May 2018",
                "degree": "BS CS",
                "gpa": None,
            }
        ],
        "skills": [{"category": "Languages", "items": ["Python"]}],
        "projects": [
            {
                "title": "Sideproject",
                "date": "Feb 2024",
                "text": "Built a thing that does things.",
                "link": "https://example.com/sideproject",
            }
        ],
        "open_source": [],
        "certifications": [],
    }
    out_pdf = tmp_path / "out.pdf"
    cmd = [
        "typst",
        "compile",
        "--root",
        str(template_dir),
        "--input",
        f"data={json.dumps(data)}",
        str(template),
        str(out_pdf),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert out_pdf.exists()

    report = validate_parse_fidelity(out_pdf)
    # The ATS template should score very high on its own output.
    assert report.score >= 0.75
    assert report.fields_found["skills_section_present"]
