"""ATS credential env-presence indicators (plan 63 / 0.2.7.10 § C.6).

`env_secrets.ats_credential_indicators()` powers the Settings · Submissions
ATS-credentials read-only panel. Workday / LinkedIn / Indeed are credential
slots; Generic (COMPANY_DIRECT) is a tunable threshold (not a credential).
"""

from __future__ import annotations

import pytest

from config import settings as app_settings
from models import ApplicationBoard
from services.settings import env_secrets

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture
def _clear_ats_env(monkeypatch):
    """Reset all 4 ATS env-loaded fields on `app_settings` to their unset shape."""
    monkeypatch.setattr(app_settings, "workday_login_token", None)
    monkeypatch.setattr(app_settings, "linkedin_session_cookie", None)
    monkeypatch.setattr(app_settings, "indeed_session_cookie", None)
    monkeypatch.setattr(app_settings, "ats_generic_llm_confidence_threshold", 0.7)


def test_all_credentials_unset_returns_false(_clear_ats_env):
    assert env_secrets.workday_credential_env_present() is False
    assert env_secrets.linkedin_session_cookie_env_present() is False
    assert env_secrets.indeed_credential_env_present() is False


def test_workday_env_set_returns_true(monkeypatch, _clear_ats_env):
    monkeypatch.setattr(app_settings, "workday_login_token", "secret-token")
    assert env_secrets.workday_credential_env_present() is True


def test_linkedin_env_set_returns_true(monkeypatch, _clear_ats_env):
    monkeypatch.setattr(app_settings, "linkedin_session_cookie", "li_at=...")
    assert env_secrets.linkedin_session_cookie_env_present() is True


def test_indeed_env_set_returns_true(monkeypatch, _clear_ats_env):
    monkeypatch.setattr(app_settings, "indeed_session_cookie", "cookie-blob")
    assert env_secrets.indeed_credential_env_present() is True


def test_dispatch_helper_workday(monkeypatch, _clear_ats_env):
    monkeypatch.setattr(app_settings, "workday_login_token", "t")
    assert env_secrets.ats_credential_env_present(ApplicationBoard.WORKDAY) is True


def test_dispatch_helper_linkedin(monkeypatch, _clear_ats_env):
    monkeypatch.setattr(app_settings, "linkedin_session_cookie", "c")
    assert env_secrets.ats_credential_env_present(ApplicationBoard.LINKEDIN) is True


def test_dispatch_helper_indeed(monkeypatch, _clear_ats_env):
    monkeypatch.setattr(app_settings, "indeed_session_cookie", "c")
    assert env_secrets.ats_credential_env_present(ApplicationBoard.INDEED) is True


def test_dispatch_helper_company_direct_returns_false(_clear_ats_env):
    """COMPANY_DIRECT is operator-tuned via threshold; the credential helper
    returns False (Generic is not a credential-based adapter)."""
    assert env_secrets.ats_credential_env_present(ApplicationBoard.COMPANY_DIRECT) is False


def test_dispatch_helper_unknown_board_returns_false(_clear_ats_env):
    """Typo guard — non-ATS boards (Greenhouse, Lever, Ashby, MANUAL) return False."""
    for board in (
        ApplicationBoard.GREENHOUSE,
        ApplicationBoard.LEVER,
        ApplicationBoard.ASHBY,
        ApplicationBoard.MANUAL,
    ):
        assert env_secrets.ats_credential_env_present(board) is False


def test_indicators_returns_four_rows(_clear_ats_env):
    """3 credential rows + 1 tunable row = 4."""
    rows = env_secrets.ats_credential_indicators()
    assert len(rows) == 4


def test_indicators_row_shape_credential(_clear_ats_env):
    rows = env_secrets.ats_credential_indicators()
    workday = next(r for r in rows if r["board"] is ApplicationBoard.WORKDAY)
    assert workday["env_var"] == "WORKDAY_LOGIN_TOKEN"
    assert workday["configured"] is False
    assert workday["kind"] == "credential"
    assert "Phase" in workday["phase"]


def test_indicators_row_shape_tunable(_clear_ats_env):
    rows = env_secrets.ats_credential_indicators()
    generic = next(r for r in rows if r["board"] is ApplicationBoard.COMPANY_DIRECT)
    assert generic["env_var"] == "ATS_GENERIC_LLM_CONFIDENCE_THRESHOLD"
    assert generic["value"] == 0.7
    assert generic["kind"] == "tunable"


def test_indicators_flip_workday_when_env_set(monkeypatch, _clear_ats_env):
    monkeypatch.setattr(app_settings, "workday_login_token", "x")
    rows = env_secrets.ats_credential_indicators()
    workday = next(r for r in rows if r["board"] is ApplicationBoard.WORKDAY)
    assert workday["configured"] is True
