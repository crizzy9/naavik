"""`naavik` CLI dispatcher.

Plan 10b (item 5, 2026-05-03): promotes `naavik` from a 1-line uvicorn
launcher to a subcommand-based CLI. Plan 26 (0.2.0.01, 2026-05-19):
deletes the `init` + `vault` subparsers along with the encrypted vault.
Plan 0.2.0.02 (queued): deletes `serve` itself, leaving only the bare
`naavik` -> uvicorn invocation. The whole CLI sunsets in the same Phase 2
sequence per AGENTS.md § Key Conventions § CLI.

Current surface:

    naavik                   # default: serve
    naavik serve             # explicit alias for default

Deprecated subcommands `naavik init` / `naavik vault <subcommand>` are
surfaced via a custom error handler that prints a migration hint with
exit code 2. See CHANGELOG.md ## [0.2.0] § Removed.
"""

from __future__ import annotations

import argparse
import sys

_DEPRECATED_SUBCOMMANDS = frozenset({"init", "vault"})

_VAULT_DEPRECATED_MESSAGE = (
    "Unknown subcommand {sub!r}. The encrypted vault was deleted in 0.2.0; "
    "secrets are now configured via env vars in `.env` (see CHANGELOG.md "
    "## [0.2.0] § Removed + README § Configuration)."
)


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

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] in _DEPRECATED_SUBCOMMANDS:
        print(
            _VAULT_DEPRECATED_MESSAGE.format(sub=argv[0]),
            file=sys.stderr,
        )
        return 2

    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        # Bare `naavik` -> run the server. Preserves the prior behavior.
        return cmd_serve(args)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
