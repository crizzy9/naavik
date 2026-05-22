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

from services.ats_parser_fidelity import (
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
    with patch("services.ats_parser_fidelity._ensure_pdfplumber", return_value=None):
        report = validate_parse_fidelity(pdf_path)
    assert report.score == 1.0
    assert report.tier == "silent"
    assert any("pdfplumber unavailable" in n for n in report.notes)


def test_validate_parse_fidelity_empty_text_extraction_returns_zero(tmp_path):
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    with patch("services.ats_parser_fidelity._extract_text", return_value=""):
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
    with patch("services.ats_parser_fidelity._extract_text", return_value=sample_text):
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
    with patch("services.ats_parser_fidelity._extract_text", return_value=sample_text):
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
def test_validate_parse_fidelity_on_real_onepage_ats_pdf(tmp_path):
    """End-to-end smoke test — compile the ATS template + parse-fidelity-check it."""
    import json
    import subprocess

    template_dir = Path(__file__).resolve().parent.parent / "src" / "typst" / "templates"
    template = template_dir / "onepage_ats.typ"
    data = {
        "profile": {
            "full_name": "Test Candidate",
            "headline": "Software Engineer",
            "email": "test@example.com",
            "phone": "+1 555 0100",
            "location": "City",
            "portfolio_url": None,
            "linkedin_handle": None,
            "github_handle": None,
            "summary_short": "Engineer with experience.",
        },
        "tailored_headline": None,
        "experiences": [
            {
                "company": "Acme",
                "role": "Senior Engineer",
                "location": "City",
                "start_date": "Jan 2022",
                "end_date": None,
                "bullets": ["Shipped a feature.", "Cut costs by half."],
            }
        ],
        "education": [
            {
                "institution": "University",
                "degree": "BS CS",
                "start_date": "Sep 2014",
                "end_date": "May 2018",
                "gpa": None,
            }
        ],
        "skills": [{"category": "Languages", "items": ["Python"]}],
        "projects": [],
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
