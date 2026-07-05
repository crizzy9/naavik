"""Deterministic checks of the generation eval harness — item 9 (2026-07).

The LLM judge is exercised only via the (skippable) live script; these
tests pin the pure checks so the scorecard's pass/fail semantics can't
drift silently.
"""

from __future__ import annotations

from types import SimpleNamespace

from services.generation.generation_eval import (
    check_bullets_one_line,
    check_contact_line,
    check_cover_first_person,
    check_no_ai_tells,
    check_one_page,
    surfaced_trace_scores,
)


def test_one_page_check():
    assert check_one_page(1)["passed"] is True
    assert check_one_page(2)["passed"] is False
    assert check_one_page(None)["passed"] is False


def _profile(**overrides):
    base = {
        "email": "me@example.com",
        "phone": "+1 (555) 555-0100",
        "location": "Fremont, CA",
        "linkedin_handle": "shyampadia",
        "github_handle": "crizzy9",
        "portfolio_url": "crypticsoul.dev",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_contact_line_complete():
    text = (
        "Shyam Padia\nme@example.com | +1 (555) 555-0100 | Fremont, CA | "
        "linkedin.com/in/shyampadia | github.com/crizzy9 | crypticsoul.dev"
    )
    result = check_contact_line(text, _profile())
    assert result["passed"] is True, result


def test_contact_line_missing_field():
    text = "Shyam Padia\nme@example.com | Fremont, CA"
    result = check_contact_line(text, _profile())
    assert result["passed"] is False
    assert "phone" in result["value"]
    assert "github" in result["value"]


def test_contact_line_degrades_without_pdf_text():
    assert check_contact_line(None, _profile())["passed"] is None


def test_bullets_one_line_budget():
    ok = check_bullets_one_line({"1": "short bullet", "2": "x" * 112}, budget=112)
    assert ok["passed"] is True
    over = check_bullets_one_line({"1": "x" * 113}, budget=112)
    assert over["passed"] is False
    assert over["value"] == {"1": 113}


def test_no_ai_tells_flags_blocklist_and_em_dash():
    clean = check_no_ai_tells(["Shipped a Kafka pipeline that cut costs 40%"])
    assert clean["passed"] is True
    dirty = check_no_ai_tells(["Spearheaded a robust synergy — leveraging cutting-edge AI"])
    assert dirty["passed"] is False
    assert "em-dash" in dirty["value"]


def test_cover_first_person():
    good = check_cover_first_person(
        {"intro": "I build recommendation systems.", "body": "My team shipped X."},
        "Shyam Padia",
    )
    assert good["passed"] is True

    third = check_cover_first_person(
        {"intro": "Shyam has seven years of experience.", "body": "He builds systems."},
        "Shyam Padia",
    )
    assert third["passed"] is False
    assert "Shyam" in third["value"]["name_mentions"]

    empty = check_cover_first_person({"intro": "", "body": ""}, "Shyam Padia")
    assert empty["passed"] is None


def test_surfaced_trace_scores_tolerates_missing_keys():
    out = surfaced_trace_scores({})
    assert out["parse_fidelity"] is None
    assert out["keyword_coverage_missing"] == []
    out2 = surfaced_trace_scores({"parse_fidelity_score": 0.9, "keyword_coverage_score": 0.66})
    assert out2["parse_fidelity"] == 0.9
    assert out2["keyword_coverage"] == 0.66
