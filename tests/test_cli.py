"""`naavik` CLI tests.

Plan 26 (0.2.0.01, 2026-05-19): the `init` + `vault` subcommands were
deleted along with the encrypted vault. Coverage retained:

- `naavik serve` (explicit + bare) routes to `cmd_serve`.
- Help text enumerates `serve` only.
- Deprecated subcommands surface a migration hint with exit code 2.

Tests use no on-disk vault fixture because the vault is gone.
"""

from __future__ import annotations

from io import StringIO


def test_dispatcher_help_lists_only_serve(capsys):
    """`naavik --help` enumerates `serve`; no `init` / `vault` after 0.2.0."""
    from cli.main import _build_parser

    parser = _build_parser()
    buf = StringIO()
    parser.print_help(file=buf)
    text = buf.getvalue()
    assert "serve" in text
    assert "init" not in text
    assert "vault" not in text


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


def test_dispatcher_explicit_serve_runs_cmd_serve(monkeypatch):
    """`naavik serve` reaches cmd_serve."""
    from cli import main as cli_main

    called = {}

    def _fake_serve(args=None):
        called["yes"] = True
        return 0

    monkeypatch.setattr(cli_main, "cmd_serve", _fake_serve)
    rc = cli_main.main(["serve"])
    assert rc == 0
    assert called.get("yes") is True


def test_dispatcher_rejects_deprecated_init(capsys):
    """`naavik init` (deprecated in 0.2.0) prints a migration hint + exits 2."""
    from cli import main as cli_main

    rc = cli_main.main(["init"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "0.2.0" in err
    assert "env vars" in err
    assert "'init'" in err


def test_dispatcher_rejects_deprecated_vault(capsys):
    """`naavik vault <...>` (deprecated in 0.2.0) prints a migration hint + exits 2."""
    from cli import main as cli_main

    rc = cli_main.main(["vault", "status"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "0.2.0" in err
    assert "env vars" in err
    assert "'vault'" in err


def test_dispatcher_rejects_deprecated_vault_rotate_key(capsys):
    """`naavik vault rotate-key ...` also rejected."""
    from cli import main as cli_main

    rc = cli_main.main(["vault", "rotate-key", "--old=x", "--new=y"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "0.2.0" in err
