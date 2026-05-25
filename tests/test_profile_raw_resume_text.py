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
