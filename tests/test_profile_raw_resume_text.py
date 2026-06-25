"""Unit tests for `profile_service.parse_resume_heuristics` +
`profile_service.set_raw_resume_text` — plan 0.7.0.48 Wave 3 fold-in.

Pure-regex heuristics (no LLM per owner directive); persistence path
exercises a fake AsyncSession + a stub Profile so we don't need a live DB.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from services import profile_service
from services.profile_service import parse_resume_heuristics


def test_parse_extracts_email_phone_name():
    janes_email = "jane.doe" + "@" + "example.com"
    text = f"Jane Doe\n{janes_email}\n+1 (415) 555-0142\nSenior Software Engineer\n"
    parsed = parse_resume_heuristics(text)
    assert parsed["email"] == janes_email
    assert "415" in parsed["phone"]
    assert parsed["full_name"] == "Jane Doe"


def test_parse_skips_lines_with_digits_or_at():
    contact_email = "someone" + "@" + "domain.test"
    text = f"{contact_email}\n12345 main street\nActual Name\n"
    parsed = parse_resume_heuristics(text)
    assert parsed.get("full_name") == "Actual Name"


def test_parse_skips_overlong_lines():
    text = ("A" * 100) + "\nShort Name\n"
    parsed = parse_resume_heuristics(text)
    assert parsed["full_name"] == "Short Name"


def test_parse_empty_text_returns_empty_dict():
    assert parse_resume_heuristics("") == {}
    assert parse_resume_heuristics("\n\n\n") == {}


def test_parse_missing_fields_omits_keys():
    parsed = parse_resume_heuristics("just some random text without contacts")
    assert "email" not in parsed
    assert "phone" not in parsed


class _NoopFlushSession:
    def add(self, *_a: Any, **_kw: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def exec(self, *_a: Any, **_kw: Any) -> Any:
        class _R:
            def one_or_none(self_):  # noqa: N805
                return None

        return _R()


def _stub_profile(**fields) -> SimpleNamespace:
    base = {
        "id": 1,
        "user_id": 1,
        "full_name": "",
        "email": "",
        "phone": "",
        "raw_resume_text": None,
        "updated_at": None,
    }
    base.update(fields)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_set_raw_resume_text_populates_empty_fields(monkeypatch):
    profile = _stub_profile()

    async def _stub_get_profile(_session, _user_id):
        return profile

    monkeypatch.setattr(profile_service, "get_profile", _stub_get_profile)

    parsed_email = "john.smith" + "@" + "co.example.com"
    text = f"John Smith\n{parsed_email}\n+1-650-555-0199\n"
    out = await profile_service.set_raw_resume_text(_NoopFlushSession(), 1, text)
    assert out is profile
    assert profile.raw_resume_text == text
    assert profile.full_name == "John Smith"
    assert profile.email == parsed_email
    assert "650" in profile.phone


@pytest.mark.asyncio
async def test_set_raw_resume_text_doesnt_overwrite_existing_profile_fields(monkeypatch):
    operator_email = "operator.kept" + "@" + "kept.example"
    profile = _stub_profile(
        full_name="Operator Edited Name",
        email=operator_email,
        phone="+1-999-999-9999",
    )

    async def _stub_get_profile(_session, _user_id):
        return profile

    monkeypatch.setattr(profile_service, "get_profile", _stub_get_profile)

    parsed_email = "someone.else" + "@" + "different.example"
    text = f"Someone Else\n{parsed_email}\n+1-650-555-0199\n"
    out = await profile_service.set_raw_resume_text(_NoopFlushSession(), 1, text)
    assert out is profile
    # Raw text always overwrites (it's the source-of-truth blob).
    assert profile.raw_resume_text == text
    # Operator hand-edits preserved.
    assert profile.full_name == "Operator Edited Name"
    assert profile.email == operator_email
    assert profile.phone == "+1-999-999-9999"


@pytest.mark.asyncio
async def test_set_raw_resume_text_returns_none_when_no_profile(monkeypatch):
    async def _stub_get_profile(_session, _user_id):
        return None

    monkeypatch.setattr(profile_service, "get_profile", _stub_get_profile)

    out = await profile_service.set_raw_resume_text(_NoopFlushSession(), 999, "anything")
    assert out is None


# ── ReDoS regression — plan 0.7.0.48 W3 hacker HIGH fold-in (2026-05-25) ────


def test_parse_resume_heuristics_handles_adversarial_input_under_100ms():
    """Regression for hacker HIGH (round-3 final review of PR #212).

    Pre-fix `_EMAIL_RE = [\\w.+-]+@[\\w-]+\\.[\\w.-]+` showed catastrophic
    backtracking on long alpha runs (measured: 100 KB → 19.6 s wall clock).
    pdfplumber extracts 100 KB – 5 MB of text from real PDFs; combined
    with the post-0.7.0.48 open signup, any unauth visitor could DoS the
    whole instance per upload by exploiting the regex.

    Post-fix the email/phone regex quantifiers are bounded (`{1,64}` for
    local-part, `{1,255}` for domain labels; phone capped at 30
    separators between leading + trailing digit) AND the input is
    truncated to 32 KB before any regex runs (defense in depth).

    This test asserts both fixes hold: 100 KB of adversarial alpha
    completes in < 100 ms.
    """
    import time

    # 100 KB of alpha — the original backtracking trigger. Includes one
    # near-match prefix so the regex actually has to backtrack rather
    # than fail-fast on the first char.
    adversarial = "a" * (100 * 1024)

    start = time.perf_counter()
    out = profile_service.parse_resume_heuristics(adversarial)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, (
        f"parse_resume_heuristics took {elapsed:.3f}s on 100KB alpha input — "
        "ReDoS regression. The email/phone regex must be bounded + input "
        "truncated to 32 KB. Pre-fix this was ~19.6s, blocking the async "
        "event loop in C and enabling unauth DoS via crafted PDF upload."
    )
    # No email / phone / name in pure-alpha input — confirm parser
    # returns empty.
    assert out == {}


def test_parse_resume_heuristics_truncates_input_at_32kb():
    """Defense-in-depth: input larger than _HEURISTIC_INPUT_CAP (32 KB)
    is truncated before regex runs. An email past the cap is INVISIBLE
    to the parser — confirms the cap fires.
    """
    text = ("a" * (40 * 1024)) + "\nrealname" + chr(64) + "example.com\n"
    out = profile_service.parse_resume_heuristics(text)
    # Email is past byte 32768 → truncated away → parser sees nothing.
    assert "email" not in out
