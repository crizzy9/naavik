"""Vault CLI handlers — wired into `naavik vault <subcommand>`.

Plan 10b (item 5, 2026-05-03) renames the original `cmd_rotate_key` to
`cmd_vault_rotate_key` to align with the new dispatcher's naming, and
introduces `cmd_vault_status` for at-a-glance vault inspection that NEVER
prints secret values. The old standalone `naavik-vault` entry point is
preserved as `main()` for back-compat with any operator wrapper scripts.

Usage (via the new dispatcher):

    naavik vault status
    naavik vault rotate-key --old=$OLD_KEY --new=$NEW_KEY [--no-backup]

Output (rotate-key, typical):

    [vault] reading ~/.naavik/secrets.enc (current fingerprint: 9f3ab8…)
    [vault] decrypting 12 entries across 5 scopes …
    [vault] re-encrypting with new key (new fingerprint: 4c2def…)
    [vault] writing ~/.naavik/secrets.enc (atomic rename when done)
    [vault] backup at ~/.naavik/secrets.enc.bak.2026-05-01-12-04
    [vault] done. update SECRET_KEY env to the new value before next start.

Output (status, typical):

    [vault] path: /home/me/.naavik/secrets.enc
    [vault] fingerprint (stored):   9f3ab8…
    [vault] fingerprint (expected): 9f3ab8…
    [vault] locked: False
    [vault] 3 scope(s):
            llm                 1 key(s): anthropic
            notifications       1 key(s): discord_webhook_url
            integrations        1 key(s): netlify_build_hook
"""

from __future__ import annotations

import argparse
import sys

from services import vault as vault_svc

# ── rotate-key ──────────────────────────────────────────────────────────


def cmd_vault_rotate_key(args: argparse.Namespace) -> int:
    """Re-encrypt the vault with `--new` after decrypting with `--old`."""
    path = vault_svc.vault_path()
    if not path.exists():
        print(f"[vault] error: no vault at {path}", file=sys.stderr)
        return 1

    print(f"[vault] reading {path} (current fingerprint: {vault_svc.fingerprint() or '(empty)'})")
    try:
        result = vault_svc.rotate_key(
            old_secret_key=args.old,
            new_secret_key=args.new,
            backup=not args.no_backup,
        )
    except vault_svc.VaultError as exc:
        print(f"[vault] error: {exc}", file=sys.stderr)
        return 2

    print(
        f"[vault] decrypting {result['entries']} entries "
        f"across {len(result['scopes'])} scopes "
        f"({', '.join(result['scopes']) or '(none)'})"
    )
    print(f"[vault] re-encrypting with new key (new fingerprint: {result['new_fingerprint'][:8]}…)")
    print(f"[vault] writing {path} (atomic rename complete)")
    if result["backup"]:
        baks = sorted(path.parent.glob(f"{path.name}.bak.*"))
        if baks:
            print(f"[vault] backup at {baks[-1]}")
    print("[vault] done. update SECRET_KEY env to the new value before next start.")
    return 0


# ── status ──────────────────────────────────────────────────────────────


def cmd_vault_status(args: argparse.Namespace) -> int:
    """Print path / fingerprint / scope summary. NEVER prints secret values."""
    path = vault_svc.vault_path()
    if not path.exists():
        print(f"[vault] no vault at {path}")
        print("[vault] run `naavik init` to create one.")
        return 1

    stored = vault_svc.fingerprint()
    expected = vault_svc.expected_fingerprint()
    locked = vault_svc.is_locked()

    print(f"[vault] path: {path}")
    print(f"[vault] fingerprint (stored):   {stored or '(none)'}")
    print(f"[vault] fingerprint (expected): {expected or '(none)'}")
    print(f"[vault] locked: {locked}")

    if locked:
        print(
            "[vault] cannot enumerate scopes — SECRET_KEY mismatch. "
            "Run `naavik vault rotate-key` or restore the original key."
        )
        return 0

    # Read decrypted data so we can list scope + per-scope key counts.
    # Internal helper, but the audit log already records `read` / `list` ops
    # so this stays auditable.
    try:
        data, _ = vault_svc._read_or_init(path)
    except vault_svc.VaultLockedError:
        print("[vault] cannot enumerate scopes — vault locked.")
        return 0

    if not data:
        print("[vault] (empty — 0 scopes)")
    else:
        print(f"[vault] {len(data)} scope(s):")
        for scope in sorted(data.keys()):
            keys = data[scope]
            names = ", ".join(sorted(keys.keys()))
            print(f"        {scope:24s} {len(keys):3d} key(s): {names}")
    return 0


# ── Standalone `naavik-vault` entry point (back-compat) ─────────────────


def main(argv: list[str] | None = None) -> int:
    """Stand-alone CLI for the legacy `naavik-vault` invocation.

    Plan 10b prefers `naavik vault <subcommand>` via the unified dispatcher,
    but this stays callable so existing wrapper scripts don't break.
    """
    parser = argparse.ArgumentParser(prog="naavik-vault", description="Vault management CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rotate = sub.add_parser("rotate-key", help="Re-encrypt the vault with a new master key")
    rotate.add_argument("--old", required=True, help="Current SECRET_KEY value")
    rotate.add_argument("--new", required=True, help="New SECRET_KEY value")
    rotate.add_argument("--no-backup", action="store_true", help="Skip writing .bak file (CI use)")
    rotate.set_defaults(func=cmd_vault_rotate_key)

    status = sub.add_parser(
        "status",
        help="Print vault path, fingerprint, scope summary (no values)",
    )
    status.set_defaults(func=cmd_vault_status)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
