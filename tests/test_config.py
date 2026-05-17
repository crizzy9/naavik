"""PC.5 — boot-time enforcement of SECRET_KEY rules.

Each test constructs Settings() with explicit kwargs to isolate from the
ambient process env (which under `nix develop` has NAAVIK_DEBUG=1 set,
and tests run with whatever .env supplies). _env_isolated() further clears
NAAVIK_DEBUG / DEBUG / SECRET_KEY so the validator sees only the kwargs.
"""

import os
from contextlib import contextmanager

import pytest
from pydantic import ValidationError

from config import Settings


@contextmanager
def _env_isolated():
    """Strip env vars that pydantic-settings would otherwise read."""
    keys = ("NAAVIK_DEBUG", "DEBUG", "SECRET_KEY")
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_default_secret_key_raises_when_not_debug():
    with _env_isolated(), pytest.raises(ValidationError) as exc:
        Settings(secret_key="change-me-in-production", debug=False)
    msg = str(exc.value)
    assert "change-me-in-production" in msg
    assert "NAAVIK_DEBUG" in msg


def test_short_secret_key_raises_when_not_debug():
    with _env_isolated(), pytest.raises(ValidationError) as exc:
        Settings(secret_key="too-short", debug=False)
    msg = str(exc.value)
    assert "32" in msg
    assert "NAAVIK_DEBUG" in msg


def test_valid_secret_key_passes_when_not_debug():
    # 48 base64url chars ≈ 36 bytes — comfortably above 32.
    strong = "x" * 48
    with _env_isolated():
        s = Settings(secret_key=strong, debug=False)
    assert s.secret_key == strong
    assert s.debug is False


def test_default_secret_key_allowed_in_debug():
    # Settings.debug uses validation_alias=AliasChoices("NAAVIK_DEBUG","DEBUG")
    # without populate_by_name=True, so kwarg debug=True is dropped (extra="ignore").
    # Set the alias env var inside isolation instead.
    with _env_isolated():
        os.environ["NAAVIK_DEBUG"] = "1"
        s = Settings(secret_key="change-me-in-production")
    assert s.debug is True
    assert s.secret_key == "change-me-in-production"
