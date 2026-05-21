"""ATS parser ensemble tests — plan 67 (0.3.4) § C.5 / T14.

Covers multi-parser score aggregation, graceful degradation when
optional deps are absent, Node subprocess timeout, and shape of
EnsembleReport.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.ats_parser_ensemble import (
    EnsembleReport,
    _openresume_script_path,
    ensemble_score,
)


def _mock_pdfplumber_report(score: float = 0.85):
    return SimpleNamespace(
        score=score,
        tier="toast" if score < 0.90 else "silent",
        fields_found={
            "name": True,
            "email": True,
            "phone": True,
            "first_experience_title": True,
            "first_experience_company": True,
            "first_experience_start_date": True,
            "education_institution": True,
            "skills_section_present": True,
        },
        fields_recovered={},
        notes=[],
    )


@pytest.mark.asyncio
async def test_ensemble_all_three_parsers_average(tmp_path):
    """All 3 parsers available + score 0.9 each → aggregate = 0.9."""
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with (
        patch(
            "services.ats_parser_ensemble.validate_parse_fidelity",
            return_value=_mock_pdfplumber_report(0.9),
        ),
        patch(
            "services.ats_parser_ensemble._try_pyresparser",
            return_value=(0.9, {}),
        ),
        patch(
            "services.ats_parser_ensemble._try_openresume",
            return_value=(0.9, {}),
        ),
    ):
        report = await ensemble_score(pdf)

    assert isinstance(report, EnsembleReport)
    assert report.aggregate_score == 0.9
    assert report.parsers_used == ["pdfplumber", "pyresparser", "openresume"]
    assert report.pdfplumber_score == 0.9
    assert report.pyresparser_score == 0.9
    assert report.openresume_score == 0.9


@pytest.mark.asyncio
async def test_ensemble_pyresparser_unavailable(tmp_path):
    """pyresparser unavailable → aggregate = mean(pdfplumber, openresume)."""
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with (
        patch(
            "services.ats_parser_ensemble.validate_parse_fidelity",
            return_value=_mock_pdfplumber_report(0.8),
        ),
        patch(
            "services.ats_parser_ensemble._try_pyresparser",
            return_value=(None, {}),
        ),
        patch(
            "services.ats_parser_ensemble._try_openresume",
            return_value=(0.7, {}),
        ),
    ):
        report = await ensemble_score(pdf)

    assert report.aggregate_score == 0.75
    assert "pyresparser" not in report.parsers_used
    assert "openresume" in report.parsers_used
    assert "pyresparser unavailable" in report.notes


@pytest.mark.asyncio
async def test_ensemble_all_optionals_unavailable_falls_back_to_pdfplumber(tmp_path):
    """When both optional parsers are missing, ensemble = pdfplumber score."""
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with (
        patch(
            "services.ats_parser_ensemble.validate_parse_fidelity",
            return_value=_mock_pdfplumber_report(0.6),
        ),
        patch(
            "services.ats_parser_ensemble._try_pyresparser",
            return_value=(None, {}),
        ),
        patch(
            "services.ats_parser_ensemble._try_openresume",
            return_value=(None, {}),
        ),
    ):
        report = await ensemble_score(pdf)

    assert report.aggregate_score == 0.6
    assert report.parsers_used == ["pdfplumber"]
    assert report.pyresparser_score is None
    assert report.openresume_score is None


@pytest.mark.asyncio
async def test_ensemble_node_subprocess_timeout_returns_none(tmp_path):
    """When OpenResume Node subprocess times out, that score becomes None."""
    import subprocess

    from services import ats_parser_ensemble

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    # Force the subprocess invocation path
    with (
        patch("services.ats_parser_ensemble.shutil.which", return_value="/usr/bin/node"),
        patch.object(
            ats_parser_ensemble,
            "_openresume_script_path",
            return_value=Path("/tmp/openresume_parser.js"),
        ),
        patch("pathlib.Path.exists", return_value=True),
        patch(
            "services.ats_parser_ensemble.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="node", timeout=10.0),
        ),
    ):
        score, fields = ats_parser_ensemble._try_openresume(pdf)
    assert score is None
    assert fields == {}


def test_openresume_no_node_returns_none(tmp_path):
    """When `node` is not on PATH, _try_openresume returns (None, {})."""
    from services.ats_parser_ensemble import _try_openresume

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with patch("services.ats_parser_ensemble.shutil.which", return_value=None):
        score, fields = _try_openresume(pdf)
    assert score is None
    assert fields == {}


def test_openresume_script_path_exists():
    """`scripts/openresume_parser.js` ships in the repo."""
    path = _openresume_script_path()
    assert path.exists(), f"openresume shim missing at {path}"
    # Sanity check the shim has the OpenResume references
    content = path.read_text(encoding="utf-8")
    assert "openresume" in content.lower() or "open-resume" in content.lower()
    assert "JSON.stringify" in content


def test_pyresparser_no_module_returns_none(tmp_path):
    """When `pyresparser` isn't installed, returns (None, {})."""
    from services.ats_parser_ensemble import _try_pyresparser

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    # importlib.import_module should raise ImportError
    with patch(
        "services.ats_parser_ensemble.importlib.import_module",
        side_effect=ImportError("no module"),
    ):
        score, fields = _try_pyresparser(pdf)
    assert score is None
    assert fields == {}


@pytest.mark.asyncio
async def test_ensemble_aggregate_score_rounding(tmp_path):
    """Aggregate is rounded to 3 decimals."""
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with (
        patch(
            "services.ats_parser_ensemble.validate_parse_fidelity",
            return_value=_mock_pdfplumber_report(0.333),
        ),
        patch(
            "services.ats_parser_ensemble._try_pyresparser",
            return_value=(0.667, {}),
        ),
        patch(
            "services.ats_parser_ensemble._try_openresume",
            return_value=(None, {}),
        ),
    ):
        report = await ensemble_score(pdf)
    # (0.333 + 0.667) / 2 = 0.5
    assert report.aggregate_score == 0.5
