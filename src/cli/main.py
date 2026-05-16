"""`naavik` CLI dispatcher.

Plan 10b (item 5, 2026-05-03): promote `naavik` from a 1-line uvicorn launcher
to a proper subcommand-based CLI:

    naavik                   # default: serve (back-compat)
    naavik serve             # explicit alias for default
    naavik init              # generate SECRET_KEY, write key.bin, init empty vault
    naavik vault status      # print path, fingerprint, scope key counts (NO values)
    naavik vault rotate-key  # re-encrypt vault with new master key

The legacy `python -m main` path keeps working because `src/main.py:main()`
is preserved as a back-compat alias that delegates here.
"""

from __future__ import annotations

import argparse
import sys


def cmd_serve(args: argparse.Namespace | None = None) -> int:
    """Run the FastAPI app via uvicorn (the original `naavik` behavior)."""
    import uvicorn

    from config import settings as app_settings

    uvicorn.run(
        "main:app",
        host=app_settings.host,
        port=app_settings.port,
        reload=False,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="naavik",
        description="Naavik — open-source self-hosted career automation platform",
    )
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="Run the FastAPI server (default)")
    serve.set_defaults(func=cmd_serve)

    init_p = sub.add_parser(
        "init",
        help="Initialize ~/.naavik (write key.bin + create empty encrypted vault)",
    )
    init_p.add_argument(
        "--secret-key",
        default=None,
        help="Use this value for SECRET_KEY (default: prompt interactively or generate)",
    )
    init_p.add_argument(
        "--generate",
        action="store_true",
        help="Always generate a SECRET_KEY (skip the interactive prompt)",
    )
    # Defer import so `naavik --help` doesn't pull in heavy deps.
    init_p.set_defaults(func=_dispatch_init)

    vault_p = sub.add_parser("vault", help="Vault operations")
    vault_sub = vault_p.add_subparsers(dest="vault_cmd", required=True)

    rotate = vault_sub.add_parser(
        "rotate-key",
        help="Re-encrypt the vault with a new master key",
    )
    rotate.add_argument("--old", required=True, help="Current SECRET_KEY value")
    rotate.add_argument("--new", required=True, help="New SECRET_KEY value")
    rotate.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip writing the .bak.<timestamp> snapshot (CI use)",
    )
    rotate.set_defaults(func=_dispatch_vault_rotate_key)

    status = vault_sub.add_parser(
        "status",
        help="Print vault path, fingerprint, scope key counts (no values)",
    )
    status.set_defaults(func=_dispatch_vault_status)

    return parser


def _dispatch_init(args: argparse.Namespace) -> int:
    from cli.init import cmd_init

    return cmd_init(args)


def _dispatch_vault_rotate_key(args: argparse.Namespace) -> int:
    from cli.vault import cmd_vault_rotate_key

    return cmd_vault_rotate_key(args)


def _dispatch_vault_status(args: argparse.Namespace) -> int:
    from cli.vault import cmd_vault_status

    return cmd_vault_status(args)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        # Bare `naavik` → run the server. Preserves the prior behavior.
        return cmd_serve(args)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
