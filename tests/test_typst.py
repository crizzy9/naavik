"""Wave 6 — Typst compiler + validator tests.

Per plan 10 § E. Verifies:
- `compiler.compile` produces a valid PDF.
- `--emit metadata` (here: `typst query`) yields page count without poppler.
- `validate_page_count` correctly reflects the compiled doc.
- Multi-page overflow detection works.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from typst import compile as typst_compile
from typst import overflows, validate_page_count
from typst.compiler import CompileResult, TypstError

_HAS_TYPST = shutil.which("typst") is not None

pytestmark = [
    pytest.mark.skipif(not _HAS_TYPST, reason="typst CLI not on PATH; install via Nix devshell"),
    pytest.mark.uses_sample_data_shims,
]


@pytest.fixture
def tmp_output_dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="naavik-typst-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _minimal_resume_data() -> dict:
    # Item 2 (2026-07): the cv.tex-conversion template shape — structured
    # jobentry/educationentry fields, no headline, + certs/open-source lists.
    return {
        "profile": {"full_name": "Shyam Padia"},
        "contact_links": [
            {"text": "shyam.padia930@gmail.com", "href": "mailto:shyam.padia930@gmail.com"},
            {"text": "+1 555 555 0100", "href": None},
            {"text": "Boston, MA", "href": None},
            {"text": "linkedin.com/in/shyampadia", "href": "https://linkedin.com/in/shyampadia"},
            {"text": "github.com/crizzy9", "href": "https://github.com/crizzy9"},
            {"text": "crypticsoul.dev", "href": "https://crypticsoul.dev"},
        ],
        "summary": (
            "Backend + ML engineer with 8+ years building personalization platforms at scale."
        ),
        "experiences": [
            {
                "company": "Intuit, Personalization",
                "title": "Senior Software Engineer",
                "location": "Mountain View, CA",
                "dates": "Jul 2020 – Present",
                "bullets": [
                    "Built ML personalization platform serving 100M+ users; +23% homepage CTR",
                    "Led 3-engineer team migrating legacy services to Kubernetes",
                ],
            }
        ],
        "education": [
            {
                "institution": "Northeastern University",
                "school": "Khoury CCIS",
                "location": "Boston, MA",
                "dates": "2017 – 2019",
                "degree": "MS Computer Science",
                "gpa": "3.8",
            }
        ],
        "skills": [
            {"category": "Languages", "items": ["Python", "Go", "TypeScript"]},
            {"category": "Infra", "items": ["AWS", "Kubernetes", "Terraform"]},
        ],
        "projects": [
            {
                "title": "Naavik",
                "date": "Feb 2026",
                "text": "Open-source career automation platform",
                "link": "https://github.com/crizzy9/naavik",
            }
        ],
        "certifications": [
            {"title": "AWS Solutions Architect - Associate", "date": "Oct 2019", "text": None}
        ],
        "open_source": [
            {"title": "Mopidy - Python Music Server", "date": "2024", "text": None, "link": None}
        ],
    }


def _minimal_letter_data() -> dict:
    return {
        "profile": {
            "full_name": "Shyam Padia",
            "email": "shyam.padia930@gmail.com",
            "phone": "+1 555 555 0100",
            "location": "Boston, MA",
        },
        "job": {"company": "Stripe", "role": "Senior Backend Engineer"},
        "recipient": {"name": "Jane Doe", "title": "Engineering Manager"},
        "greeting": "Dear Jane Doe,",
        "letter": {
            "intro": "I'm excited to apply for the Senior Backend Engineer role at Stripe.",
            "body": ("At Intuit I led the personalization platform that served 100M+ users."),
            "why_company": "Stripe's emphasis on durable infrastructure resonates.",
            "close": "I would love to contribute to your team.",
        },
        "today": "May 3, 2026",
    }


@pytest.mark.asyncio
async def test_compile_resume_produces_valid_pdf(tmp_output_dir):
    out = tmp_output_dir / "resume.pdf"
    result = await typst_compile("onepage", _minimal_resume_data(), out)
    assert isinstance(result, CompileResult)
    assert out.exists()
    assert out.stat().st_size > 1000  # real PDF, not a stub
    assert result.byte_size == out.stat().st_size
    # PDF magic bytes
    head = out.read_bytes()[:4]
    assert head == b"%PDF"


@pytest.mark.asyncio
async def test_compile_returns_page_count_without_poppler(tmp_output_dir):
    out = tmp_output_dir / "resume.pdf"
    result = await typst_compile("onepage", _minimal_resume_data(), out)
    assert result.page_count >= 1
    # Validator agrees
    assert validate_page_count(result, expected=result.page_count) is True
    assert validate_page_count(result, expected=result.page_count + 1) is False


@pytest.mark.asyncio
async def test_compile_cover_letter_one_page(tmp_output_dir):
    out = tmp_output_dir / "cover.pdf"
    result = await typst_compile("cover_letter", _minimal_letter_data(), out)
    assert result.page_count == 1
    assert overflows(result, max_pages=1) is False


@pytest.mark.asyncio
async def test_compile_overflow_detected(tmp_output_dir):
    """Cram so many bullets that the resume must spill to page 2."""
    data = _minimal_resume_data()
    bullet_template = (
        "Built ML personalization platform serving millions of users daily, "
        "delivering measurable revenue lift and lowering p99 latency by 38%, "
        "while mentoring 5 engineers and shipping 12 production releases."
    )
    data["experiences"][0]["bullets"] = [bullet_template] * 80
    out = tmp_output_dir / "overflow.pdf"
    result = await typst_compile("onepage", data, out)
    assert result.page_count > 1
    assert overflows(result, max_pages=1) is True


@pytest.mark.asyncio
async def test_compile_unknown_template_raises():
    out = Path("/tmp/naavik-test-bogus.pdf")
    with pytest.raises(TypstError):
        await typst_compile("does-not-exist", {}, out)


@pytest.mark.asyncio
async def test_compile_invalid_data_raises(tmp_output_dir):
    """Missing required field → typst error, not silent garbage."""
    out = tmp_output_dir / "broken.pdf"
    with pytest.raises(TypstError):
        # Missing `profile` entirely
        await typst_compile("onepage", {"experiences": []}, out)


def test_compile_result_pydantic_shape():
    """CompileResult validates as a Pydantic model with proper fields."""
    cr = CompileResult(
        output_path=Path("/tmp/x.pdf"),
        page_count=1,
        byte_size=1024,
        compiled_at=datetime.now(UTC),
    )
    assert cr.page_count == 1
    assert cr.byte_size == 1024
