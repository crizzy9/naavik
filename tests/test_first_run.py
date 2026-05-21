"""Plan 71 (0.3.3.14): first-run state probe + lifespan WARN.

Covers `services.first_run.probe_first_run_state` (the canonical
diagnostic) + the boot-time WARN emitter in `main._emit_first_run_warning_if_broken`.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def env_settings(monkeypatch):
    """Reset every env-derived setting that the probe consumes."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "debug", False)
    monkeypatch.setattr(app_settings, "data_dir", str(Path("/tmp/naavik-test-first-run")))
    return app_settings


# ── FirstRunState dataclass invariants ───────────────────────────────────


def test_first_run_state_broken_when_trifecta_trips():
    from services.first_run import FirstRunState

    state = FirstRunState(
        debug_enabled=False,
        user_count=1,
        dev_credentials_present=False,
        dev_credentials_path="/tmp/whatever",
    )
    assert state.broken is True
    assert state.has_users is True


def test_first_run_state_healthy_when_debug_on():
    from services.first_run import FirstRunState

    state = FirstRunState(
        debug_enabled=True,
        user_count=1,
        dev_credentials_present=False,
        dev_credentials_path="/tmp/whatever",
    )
    assert state.broken is False


def test_first_run_state_healthy_when_no_users():
    from services.first_run import FirstRunState

    state = FirstRunState(
        debug_enabled=False,
        user_count=0,
        dev_credentials_present=False,
        dev_credentials_path="/tmp/whatever",
    )
    assert state.broken is False
    assert state.has_users is False


def test_first_run_state_healthy_when_creds_present():
    from services.first_run import FirstRunState

    state = FirstRunState(
        debug_enabled=False,
        user_count=1,
        dev_credentials_present=True,
        dev_credentials_path="/tmp/whatever",
    )
    assert state.broken is False


# ── probe_first_run_state — env + filesystem sensitivity ─────────────────


async def test_probe_reads_debug_flag(env_settings, monkeypatch, tmp_path):
    from services.first_run import probe_first_run_state

    monkeypatch.setattr(env_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(env_settings, "debug", True)
    state = await probe_first_run_state(session=None)
    assert state.debug_enabled is True


async def test_probe_detects_dev_credentials_file(env_settings, monkeypatch, tmp_path):
    from services.first_run import probe_first_run_state

    monkeypatch.setattr(env_settings, "data_dir", str(tmp_path))
    creds_path = tmp_path / "dev-credentials"
    creds_path.write_text("user: shyam\npassword: secret\n")
    state = await probe_first_run_state(session=None)
    assert state.dev_credentials_present is True
    assert state.dev_credentials_path == str(creds_path)


async def test_probe_handles_missing_dev_credentials(env_settings, monkeypatch, tmp_path):
    from services.first_run import probe_first_run_state

    monkeypatch.setattr(env_settings, "data_dir", str(tmp_path))
    state = await probe_first_run_state(session=None)
    assert state.dev_credentials_present is False


async def test_probe_user_count_zero_without_session(env_settings, monkeypatch, tmp_path):
    """`session=None` → user_count stays 0 (no DB to query)."""
    from services.first_run import probe_first_run_state

    monkeypatch.setattr(env_settings, "data_dir", str(tmp_path))
    state = await probe_first_run_state(session=None)
    assert state.user_count == 0
    assert state.has_users is False


# ── lifespan WARN emitter — observable via log capture ───────────────────


async def test_lifespan_warn_fires_when_broken(env_settings, monkeypatch, tmp_path, caplog):
    """`main._emit_first_run_warning_if_broken` logs WARN when state.broken."""
    import logging

    from main import _emit_first_run_warning_if_broken
    from services import first_run

    monkeypatch.setattr(env_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(env_settings, "debug", False)

    fake_state = first_run.FirstRunState(
        debug_enabled=False,
        user_count=1,
        dev_credentials_present=False,
        dev_credentials_path=str(tmp_path / "dev-credentials"),
    )

    async def _fake_probe(session):
        return fake_state

    monkeypatch.setattr(first_run, "probe_first_run_state", _fake_probe)

    # Patch the session factory so the function doesn't try to open Postgres.
    class _FakeSessionCtx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr("db.session.async_session", lambda: _FakeSessionCtx())

    with caplog.at_level(logging.WARNING, logger="main"):
        await _emit_first_run_warning_if_broken()

    assert any(
        "first-run auth gap" in r.message and r.levelno == logging.WARNING for r in caplog.records
    ), f"WARN missing — records: {[r.message for r in caplog.records]}"


async def test_lifespan_warn_silent_when_healthy(env_settings, monkeypatch, tmp_path, caplog):
    """No WARN when state.broken is False."""
    import logging

    from main import _emit_first_run_warning_if_broken
    from services import first_run

    monkeypatch.setattr(env_settings, "data_dir", str(tmp_path))

    fake_state = first_run.FirstRunState(
        debug_enabled=True,
        user_count=1,
        dev_credentials_present=True,
        dev_credentials_path=str(tmp_path / "dev-credentials"),
    )

    async def _fake_probe(session):
        return fake_state

    monkeypatch.setattr(first_run, "probe_first_run_state", _fake_probe)

    class _FakeSessionCtx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr("db.session.async_session", lambda: _FakeSessionCtx())

    with caplog.at_level(logging.WARNING, logger="main"):
        await _emit_first_run_warning_if_broken()

    assert not any("first-run auth gap" in r.message for r in caplog.records)


async def test_lifespan_warn_swallows_probe_errors(env_settings, monkeypatch, tmp_path, caplog):
    """Probe raising → swallowed via the try/except; never blocks boot."""
    import logging

    from main import _emit_first_run_warning_if_broken
    from services import first_run

    monkeypatch.setattr(env_settings, "data_dir", str(tmp_path))

    async def _angry_probe(session):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(first_run, "probe_first_run_state", _angry_probe)

    class _FakeSessionCtx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr("db.session.async_session", lambda: _FakeSessionCtx())

    with caplog.at_level(logging.DEBUG, logger="main"):
        # Should not raise.
        await _emit_first_run_warning_if_broken()

    # DEBUG line acknowledges the swallowed probe; no WARN fires.
    assert any(
        "first-run state probe skipped at boot" in r.message and r.levelno == logging.DEBUG
        for r in caplog.records
    )
