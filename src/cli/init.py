"""`naavik init` — initialize the on-disk state directory + encrypted vault.

Plan 10b (item 5, 2026-05-03). Self-hosters running outside the dev
orchestrator need a one-shot bootstrap that:

1. Resolves SECRET_KEY (prompt → entered value, blank → generate, --generate
   forces a fresh value, --secret-key sets explicitly).
2. Writes the value to `~/.naavik/key.bin` (mode 0600) so the operator has
   a secondary copy if their SECRET_KEY env / SOPS file gets misplaced.
3. Initializes an empty encrypted vault at `~/.naavik/secrets.enc` keyed
   off the resolved SECRET_KEY (writes a probe entry then deletes it,
   forcing the file into existence with a known fingerprint).

Refuses to overwrite an existing vault — the operator must run
`naavik vault rotate-key` to change keys, or remove the file manually.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys


def cmd_init(args: argparse.Namespace) -> int:
    from services import vault as vault_svc

    vault_path = vault_svc.vault_path()
    data_dir = vault_path.parent
    key_path = data_dir / "key.bin"

    if vault_path.exists():
        print(f"[init] error: vault already exists at {vault_path}", file=sys.stderr)
        print(
            "       run `naavik vault rotate-key --old=$OLD --new=$NEW` to change keys,",
            file=sys.stderr,
        )
        print(
            "       or remove the file manually if you really want to reset.",
            file=sys.stderr,
        )
        return 2

    secret_key = _resolve_secret_key(args)

    data_dir.mkdir(parents=True, exist_ok=True)

    # key.bin is a secondary copy of SECRET_KEY for operators who lose env
    # state. Mode 0600 so other users on the host can't read it.
    if key_path.exists():
        print(
            f"[init] warning: {key_path} already exists; leaving untouched.",
            file=sys.stderr,
        )
    else:
        key_path.write_bytes(secret_key.encode("utf-8"))
        os.chmod(key_path, 0o600)
        print(f"[init] wrote {key_path} (mode 0600)")

    # Override app_settings.secret_key in-process so vault_svc derives the
    # right master key for the probe write below. Vault reads settings at
    # call time, not import time, so this is enough.
    from config import settings as app_settings

    app_settings.secret_key = secret_key

    # Force vault file creation by writing-then-deleting a probe entry.
    vault_svc.set("__init__", "marker", "1", caller="naavik-init")
    vault_svc.delete("__init__", "marker", caller="naavik-init")

    print()
    print("[init] SECRET_KEY (capture this — you must export it on every server start):")
    print()
    print(f"       export SECRET_KEY='{secret_key}'")
    print()
    print(f"[init] initialized empty vault at {vault_path}")
    print(f"[init] fingerprint: {vault_svc.fingerprint()}")
    print("[init] done.")
    return 0


def _resolve_secret_key(args: argparse.Namespace) -> str:
    """Pick the SECRET_KEY based on flags, env, or prompt → fall back to generate."""
    if getattr(args, "secret_key", None):
        return str(args.secret_key)

    if getattr(args, "generate", False):
        return secrets.token_urlsafe(48)

    # Non-interactive (pipe, CI) → silently generate.
    if not sys.stdin.isatty():
        return secrets.token_urlsafe(48)

    try:
        sys.stdout.flush()
        entered = input("[init] enter SECRET_KEY (leave blank to generate a fresh value): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return secrets.token_urlsafe(48)

    return entered or secrets.token_urlsafe(48)
