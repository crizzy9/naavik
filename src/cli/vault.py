"""`naavik vault rotate-key` CLI — re-encrypt the on-disk vault with a new master.

Usage:
    naavik vault rotate-key --old=$OLD_KEY --new=$NEW_KEY [--no-backup]

Per plan 10 § B.5. Self-hosters need this; rotating `SECRET_KEY` without
re-encrypting bricks the vault.

Output (typical):
    [vault] reading ~/.naavik/secrets.enc (current fingerprint: 9f3ab8...)
    [vault] decrypting 12 entries across 5 scopes ...
    [vault] re-encrypting with new key (new fingerprint: 4c2def...)
    [vault] writing ~/.naavik/secrets.enc.new (atomic rename when done)
    [vault] backup at ~/.naavik/secrets.enc.bak.2026-05-01-12-04
    [vault] done. update SECRET_KEY env to the new value before next start.
"""

from __future__ import annotations

import argparse
import sys

from services import vault as vault_svc


def cmd_rotate_key(args: argparse.Namespace) -> int:
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
        f"across {len(result['scopes'])} scopes ({', '.join(result['scopes']) or '(none)'})"
    )
    print(f"[vault] re-encrypting with new key (new fingerprint: {result['new_fingerprint'][:8]}...)")
    print(f"[vault] writing {path} (atomic rename complete)")
    if result["backup"]:
        # Find the most-recently-created bak for nicer log output.
        baks = sorted(path.parent.glob(f"{path.name}.bak.*"))
        if baks:
            print(f"[vault] backup at {baks[-1]}")
    print("[vault] done. update SECRET_KEY env to the new value before next start.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="naavik-vault", description="Vault management CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rotate = sub.add_parser("rotate-key", help="Re-encrypt the vault with a new master key")
    rotate.add_argument("--old", required=True, help="Current SECRET_KEY value")
    rotate.add_argument("--new", required=True, help="New SECRET_KEY value")
    rotate.add_argument("--no-backup", action="store_true", help="Skip writing .bak file (CI use)")
    rotate.set_defaults(func=cmd_rotate_key)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
