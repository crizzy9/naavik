"""Keyword coverage validator — plan 66 (0.3.1) § T8."""

from __future__ import annotations

import pytest

from services.generation.keyword_coverage import (
    CoverageReport,
    _normalize_keyword,
    _select_top_section,
    compute_coverage,
)

pytestmark = pytest.mark.uses_sample_data_shims


def test_normalize_keyword_collapses_whitespace_and_lowercases():
    assert _normalize_keyword("  Distributed   SYSTEMS ") == "distributed systems"
    assert _normalize_keyword("") == ""


def test_select_top_section_returns_first_30_pct_non_empty_lines():
    lines = [f"line {i}" for i in range(10)]
    top = _select_top_section(lines, top_pct=0.30)
    # 30% of 10 = 3 lines, rounded
    assert top.count("\n") == 2  # 3 lines = 2 newlines
    assert top.startswith("line 0")


def test_select_top_section_skips_empty_lines():
    lines = ["a", "", "b", "", "c", "d"]
    top = _select_top_section(lines, top_pct=0.5)
    # 50% of 4 non-empty = 2 lines
    assert top == "a\nb"


def test_compute_coverage_all_must_haves_found():
    must_haves = ["Python", "Distributed Systems", "ML"]
    # All three keywords fit on the first line (top-30% of a 2-line resume = 1 line).
    resume = "Shipped Python + Distributed Systems + ML pipeline.\nBuilt other things."
    report = compute_coverage(must_haves, resume)
    assert report.score == 1.0
    assert "python" in report.found_keywords
    assert "distributed systems" in report.found_keywords
    assert "ml" in report.found_keywords
    assert report.missing_keywords == []


def test_compute_coverage_partial_match():
    must_haves = ["Python", "Rust", "Go"]
    resume = "I shipped Python services."
    report = compute_coverage(must_haves, resume)
    assert report.score == round(1 / 3, 3)
    assert "python" in report.found_keywords
    assert "rust" in report.missing_keywords
    assert "go" in report.missing_keywords


def test_compute_coverage_misses_when_keyword_below_top_section():
    must_haves = ["Kubernetes"]
    # 10 lines; top-30% = top-3 lines. Kubernetes appears on line 9.
    resume = "\n".join([f"top line {i}" for i in range(5)] + ["", "Kubernetes here", ""])
    report = compute_coverage(must_haves, resume, top_pct=0.30)
    assert report.score == 0.0
    assert "kubernetes" in report.missing_keywords


def test_compute_coverage_whole_word_match():
    """`Go` (lang) should match but not `Going` or `Goroutines`."""
    must_haves = ["Go"]
    resume = "Shipped Go services using Goroutines."
    report = compute_coverage(must_haves, resume)
    assert report.score == 1.0
    assert "go" in report.found_keywords


def test_compute_coverage_empty_must_haves_returns_one():
    report = compute_coverage([], "anything")
    assert report.score == 1.0
    assert report.found_keywords == []


def test_compute_coverage_empty_resume_returns_zero():
    report = compute_coverage(["Python"], "")
    assert report.score == 0.0
    assert "python" in report.missing_keywords


def test_compute_coverage_deduplicates_keywords():
    """Same keyword listed multiple times counts once."""
    must_haves = ["Python", "PYTHON", "python"]
    resume = "Python rocks"
    report = compute_coverage(must_haves, resume)
    assert report.score == 1.0
    assert len(report.found_keywords) == 1


def test_coverage_report_dataclass():
    report = CoverageReport(
        score=0.5,
        found_keywords=["x"],
        missing_keywords=["y"],
    )
    assert report.score == 0.5
    assert report.threshold == 0.75
