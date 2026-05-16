"""`naavik` CLI tests — plan 10b (item 5, 2026-05-03).

Coverage:
- `naavik init` writes `~/.naavik/key.bin` (mode 0600) + initializes empty vault.
- `naavik init` refuses to overwrite an existing vault.
- `naavik vault status` prints fingerprint + scope summary, no values.
- `naavik vault rotate-key` round-trips and writes a `.bak.YYYY-MM-DD-HH-MM`.

Tests use a fresh tmp_path for each run so vault state never leaks across
tests or out of the repo.
"""

from __future__ import annotations

import argparse
import os
import secrets
from io import StringIO
from pathlib import Path

import pytest


@pytest.fixture
def vault_tmp(monkeypatch, tmp_path: Path):
    """Point the vault + audit log at a per-test tmp dir + reset SECRET_KEY."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_settings, "secret_key", "k" + secrets.token_hex(32))
    return tmp_path


def test_init_creates_key_and_empty_vault(vault_tmp: Path, monkeypatch, capsys):
    """Item 5: `naavik init` provisions key.bin (mode 0600) + a usable vault."""
    from cli.init import cmd_init
    from services import vault as vault_svc

    args = argparse.Namespace(secret_key="explicit-test-secret-key", generate=False)
    rc = cmd_init(args)
    assert rc == 0

    key_path = vault_tmp / "key.bin"
    vault_path = vault_tmp / "secrets.enc"
    assert key_path.exists()
    assert vault_path.exists()
    # mode 0600 — owner-readable only, world-blind
    mode = key_path.stat().st_mode & 0o777
    assert mode == 0o600
    assert key_path.read_text() == "explicit-test-secret-key"

    # Vault opens cleanly under the key we set
    fp = vault_svc.fingerprint()
    expected = vault_svc.expected_fingerprint()
    assert fp is not None
    assert fp == expected

    out = capsys.readouterr().out
    assert "[init] wrote" in out
    assert "explicit-test-secret-key" in out


def test_init_refuses_to_overwrite_existing_vault(vault_tmp: Path, capsys):
    from cli.init import cmd_init

    args = argparse.Namespace(secret_key="first-secret-key", generate=False)
    assert cmd_init(args) == 0

    args2 = argparse.Namespace(secret_key="second-secret-key", generate=False)
    rc = cmd_init(args2)
    assert rc == 2  # explicit "vault already exists" error code

    err = capsys.readouterr().err
    assert "vault already exists" in err
    assert "rotate-key" in err

    # The key file is left alone too
    key_path = vault_tmp / "key.bin"
    assert key_path.read_text() == "first-secret-key"


def test_init_generate_flag_skips_prompt(vault_tmp: Path, capsys):
    """Belt-and-suspenders: --generate produces a non-empty SECRET_KEY non-interactively."""
    from cli.init import cmd_init

    args = argparse.Namespace(secret_key=None, generate=True)
    rc = cmd_init(args)
    assert rc == 0
    key_path = vault_tmp / "key.bin"
    assert key_path.exists()
    assert len(key_path.read_text()) >= 32  # token_urlsafe(48) → ≥ 64 chars typically


def test_vault_status_prints_fingerprint_and_scopes(vault_tmp: Path, capsys):
    """Item 5: `naavik vault status` prints path + fingerprint + scope counts.
    Crucially, it never prints secret VALUES — only key NAMES per scope.
    """
    from cli.init import cmd_init
    from cli.vault import cmd_vault_status
    from services import vault as vault_svc

    init_rc = cmd_init(argparse.Namespace(secret_key="t-secret", generate=False))
    assert init_rc == 0
    capsys.readouterr()  # drain init output

    # Plant a couple of secrets so we can check the scope summary
    vault_svc.set("llm", "anthropic", "sk-ant-DO-NOT-LOG-ME", caller="test")
    vault_svc.set("notifications", "discord_webhook_url", "https://discord/x", caller="test")

    rc = cmd_vault_status(argparse.Namespace())
    assert rc == 0
    out = capsys.readouterr().out

    assert "[vault] path:" in out
    assert "fingerprint (stored):" in out
    assert "fingerprint (expected):" in out
    assert "locked: False" in out
    # Scope names + key names appear; SECRET VALUES MUST NOT.
    assert "llm" in out
    assert "anthropic" in out
    assert "notifications" in out
    assert "discord_webhook_url" in out
    assert "sk-ant-DO-NOT-LOG-ME" not in out
    assert "https://discord/x" not in out


def test_vault_status_locked_when_secret_key_mismatch(vault_tmp: Path, capsys, monkeypatch):
    from cli.init import cmd_init
    from cli.vault import cmd_vault_status
    from config import settings as app_settings

    cmd_init(argparse.Namespace(secret_key="original-key", generate=False))
    capsys.readouterr()

    # Drift the runtime SECRET_KEY without rotating
    monkeypatch.setattr(app_settings, "secret_key", "drifted-key")

    rc = cmd_vault_status(argparse.Namespace())
    assert rc == 0
    out = capsys.readouterr().out
    assert "locked: True" in out
    assert "SECRET_KEY mismatch" in out


def test_vault_rotate_key_round_trips(vault_tmp: Path, capsys, monkeypatch):
    from cli.init import cmd_init
    from cli.vault import cmd_vault_rotate_key, cmd_vault_status
    from config import settings as app_settings
    from services import vault as vault_svc

    cmd_init(argparse.Namespace(secret_key="old-secret-key", generate=False))
    capsys.readouterr()

    # Plant a value so we can verify it survives rotation
    vault_svc.set("llm", "anthropic", "sk-ant-secret", caller="test")
    fp_before = vault_svc.fingerprint()

    rc = cmd_vault_rotate_key(
        argparse.Namespace(old="old-secret-key", new="new-secret-key", no_backup=False)
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "decrypting" in out
    assert "re-encrypting" in out
    assert "atomic rename complete" in out

    # A backup file was written
    baks = list(vault_tmp.glob("secrets.enc.bak.*"))
    assert len(baks) >= 1

    # Switch SECRET_KEY to the new value and confirm the secret still reads
    monkeypatch.setattr(app_settings, "secret_key", "new-secret-key")
    assert vault_svc.get("llm", "anthropic", caller="test") == "sk-ant-secret"

    fp_after = vault_svc.fingerprint()
    assert fp_after is not None
    assert fp_after != fp_before  # fresh salt → different fingerprint

    cmd_vault_status(argparse.Namespace())
    status_out = capsys.readouterr().out
    assert "locked: False" in status_out


def test_dispatcher_help_lists_subcommands(capsys):
    """`naavik --help` enumerates serve / init / vault."""
    from cli.main import _build_parser

    parser = _build_parser()
    buf = StringIO()
    parser.print_help(file=buf)
    text = buf.getvalue()
    assert "serve" in text
    assert "init" in text
    assert "vault" in text


def test_dispatcher_default_runs_serve(monkeypatch):
    """Bare `naavik` (no subcommand) routes to cmd_serve."""
    from cli import main as cli_main

    called = {}

    def _fake_serve(args=None):
        called["yes"] = True
        return 0

    monkeypatch.setattr(cli_main, "cmd_serve", _fake_serve)
    rc = cli_main.main([])
    assert rc == 0
    assert called.get("yes") is True


def test_dispatcher_routes_vault_status(monkeypatch):
    """`naavik vault status` reaches the status handler."""
    from cli import main as cli_main

    called = {}

    def _fake_status(args):
        called["yes"] = True
        return 0

    monkeypatch.setattr(cli_main, "_dispatch_vault_status", _fake_status)
    rc = cli_main.main(["vault", "status"])
    assert rc == 0
    assert called.get("yes") is True


# Touch the os import so linters don't flag it; it's used implicitly through
# Path.stat() above but the import keeps the pattern explicit.
_ = os.name
