"""Encrypted secrets vault — `~/.naavik/secrets.enc`.

Per BACKEND.md § H.1, § L.1, § N + DATA_MODEL.md § H + plan 10 § B.5.

The vault is the **only** place secret material lives. DB rows store
fingerprints + booleans; the actual API keys, OAuth refresh tokens, IMAP
passwords, ATS cookies, Discord webhook URLs, Telegram bot tokens, Netlify
build hooks all encrypt to this file.

File layout:
- bytes 0..32       — magic header `b"NAAVIK_VAULT_V1\\n\\0\\0\\0\\0\\0"`
                      (16 bytes magic + 16 padding)
- bytes 32..64      — `key_fingerprint = sha256(master_key)[:32]` (raw 32 bytes)
- bytes 64..96      — PBKDF2 salt (32 bytes)
- bytes 96..108     — AES-GCM nonce (12 bytes)
- bytes 108..end    — AES-GCM ciphertext + tag (encrypted JSON)

Master key derivation: `PBKDF2-HMAC-SHA256(SECRET_KEY, salt, iterations=100_000, dklen=32)`.
The `key_fingerprint` lets the server detect a `SECRET_KEY` mismatch BEFORE
attempting decrypt — fail fast with a clear error instead of silent corruption.

Concurrency: every write acquires `fcntl.LOCK_EX` on the file. Reads use
shared locks so concurrent readers don't conflict.

Audit log: every `get` / `set` / `delete` writes a line to
`~/.naavik/logs/vault-audit.log` with `{timestamp, op, scope, key, caller}`.
**Secret value is NEVER logged.**

CLI:
- `naavik vault rotate-key --old=... --new=... [--no-backup]` (cli/vault.py)
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import settings as app_settings

log = logging.getLogger(__name__)

# Format constants
MAGIC = b"NAAVIK_VAULT_V1\n\0\0\0\0\0"  # 20 bytes; padded with NULs to 32
assert len(MAGIC) <= 32

HEADER_SIZE = 32
FINGERPRINT_SIZE = 32
SALT_SIZE = 32
NONCE_SIZE = 12
PREAMBLE_SIZE = HEADER_SIZE + FINGERPRINT_SIZE + SALT_SIZE + NONCE_SIZE  # 108

PBKDF2_ITERATIONS = 100_000
KEY_BYTES = 32  # AES-256


class VaultError(Exception):
    """Vault operation failed."""


class VaultLockedError(VaultError):
    """The on-disk vault was encrypted with a different SECRET_KEY."""


# ── Path helpers ─────────────────────────────────────────────────────────


def vault_path() -> Path:
    """Resolve the vault file path. Honors `Settings.data_dir`; falls back to
    `~/.naavik/secrets.enc`."""
    raw = app_settings.data_dir
    base = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
    if not base.is_absolute():
        base = (Path.home() / base).resolve() if str(base).startswith(".") else base.resolve()
    return base / "secrets.enc"


def _lock_path() -> Path:
    """Sibling lockfile — never replaced, lives across atomic rename of the
    main vault file. All concurrent vault ops coordinate here."""
    return vault_path().with_suffix(".enc.lock")


def audit_log_path() -> Path:
    raw = app_settings.data_dir
    base = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
    if not base.is_absolute():
        base = (Path.home() / base).resolve() if str(base).startswith(".") else base.resolve()
    return base / "logs" / "vault-audit.log"


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


# ── Crypto helpers ───────────────────────────────────────────────────────


def derive_key(secret_key: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256(secret_key, salt, 100_000) → 32 bytes."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret_key.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=KEY_BYTES,
    )


def fingerprint_for_key(master_key: bytes) -> bytes:
    """sha256(master_key)[:32] — used as plaintext header to detect mismatch."""
    return hashlib.sha256(master_key).digest()


# ── File I/O ─────────────────────────────────────────────────────────────


def _encode(data: dict, master_key: bytes, salt: bytes, nonce: bytes) -> bytes:
    """Serialize {scope: {key: value}} → encrypted file bytes."""
    plaintext = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    aesgcm = AESGCM(master_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    fp = fingerprint_for_key(master_key)
    header = MAGIC.ljust(HEADER_SIZE, b"\x00")
    return header + fp + salt + nonce + ciphertext


def _decode(blob: bytes, master_key: bytes) -> tuple[dict, bytes]:
    """Decode + decrypt vault bytes → (data, salt). Raises VaultLockedError on fingerprint mismatch."""
    if len(blob) < PREAMBLE_SIZE:
        raise VaultError(f"vault file too short: {len(blob)} bytes")
    if not blob[:HEADER_SIZE].startswith(MAGIC):
        raise VaultError("vault file magic header invalid")
    stored_fp = blob[HEADER_SIZE : HEADER_SIZE + FINGERPRINT_SIZE]
    salt = blob[HEADER_SIZE + FINGERPRINT_SIZE : HEADER_SIZE + FINGERPRINT_SIZE + SALT_SIZE]
    nonce = blob[HEADER_SIZE + FINGERPRINT_SIZE + SALT_SIZE : PREAMBLE_SIZE]
    ciphertext = blob[PREAMBLE_SIZE:]

    expected_fp = fingerprint_for_key(master_key)
    if not secrets.compare_digest(stored_fp, expected_fp):
        raise VaultLockedError(
            "SECRET_KEY mismatch: vault was encrypted with a different key. "
            "Run `naavik vault rotate-key` or restore the original key."
        )

    aesgcm = AESGCM(master_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    data = json.loads(plaintext.decode("utf-8"))
    return data, salt


def _read_or_init(path: Path) -> tuple[dict, bytes]:
    """Read + decrypt the vault. If the file doesn't exist, return an empty
    vault keyed off SECRET_KEY (a fresh random salt)."""
    if not path.exists():
        salt = secrets.token_bytes(SALT_SIZE)
        return {}, salt

    with path.open("rb") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
        try:
            blob = fh.read()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    if len(blob) == 0:
        salt = secrets.token_bytes(SALT_SIZE)
        return {}, salt

    # Pre-flight: check fingerprint before computing key (we do need the salt
    # which we read from the blob, but PBKDF2 still has to run once).
    # Pull salt out without decoding.
    salt = blob[HEADER_SIZE + FINGERPRINT_SIZE : HEADER_SIZE + FINGERPRINT_SIZE + SALT_SIZE]
    master_key = derive_key(app_settings.secret_key, salt)
    data, _ = _decode(blob, master_key)
    return data, salt


def _write(path: Path, data: dict, salt: bytes) -> None:
    """Encrypt + atomically write the vault. Caller holds fcntl.LOCK_EX."""
    master_key = derive_key(app_settings.secret_key, salt)
    nonce = secrets.token_bytes(NONCE_SIZE)
    blob = _encode(data, master_key, salt, nonce)
    tmp = path.with_suffix(path.suffix + ".tmp")
    _ensure_parent(path)
    with tmp.open("wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _audit(op: str, scope: str, key: str, caller: str | None = None) -> None:
    """Append an audit-log line. Secret value never appears."""
    line = json.dumps(
        {
            "ts": datetime.now(UTC).isoformat(),
            "op": op,
            "scope": scope,
            "key": key,
            "caller": caller or "unspecified",
        },
        sort_keys=True,
    )
    p = audit_log_path()
    try:
        _ensure_parent(p)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        # Audit logging must never break the vault op; log the failure to
        # the application logger and continue.
        log.warning("vault audit log write failed: %s", exc)


# ── Public API ───────────────────────────────────────────────────────────


def get(scope: str, key: str, *, caller: str | None = None) -> str | None:
    """Read a secret. None if not present. Raises VaultLockedError on key mismatch."""
    data, _ = _read_or_init(vault_path())
    _audit("get", scope, key, caller)
    return data.get(scope, {}).get(key)


def _with_exclusive_lock(fn):
    """Run `fn()` while holding `fcntl.LOCK_EX` on the sibling lockfile.

    The lockfile is separate from the vault file because writes use
    `os.replace`, which swaps inodes — fds opened on the old inode would see
    stale content. The lockfile is never replaced, so every caller acquires
    the same shared lock object regardless of inode swap.
    """
    lock_path = _lock_path()
    _ensure_parent(lock_path)
    lfd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lfd, fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lfd, fcntl.LOCK_UN)
    finally:
        os.close(lfd)


def set(scope: str, key: str, value: str, *, caller: str | None = None) -> None:
    """Write a secret. Atomic write under exclusive lockfile."""
    if not isinstance(value, str):
        raise ValueError("vault value must be a string")
    path = vault_path()
    _ensure_parent(path)

    def op():
        if path.exists():
            blob = path.read_bytes()
            salt = blob[HEADER_SIZE + FINGERPRINT_SIZE : HEADER_SIZE + FINGERPRINT_SIZE + SALT_SIZE]
            master_key = derive_key(app_settings.secret_key, salt)
            data, _ = _decode(blob, master_key)
        else:
            salt = secrets.token_bytes(SALT_SIZE)
            data = {}
        data.setdefault(scope, {})[key] = value
        _write(path, data, salt)
        _audit("set", scope, key, caller)

    _with_exclusive_lock(op)


def delete(scope: str, key: str, *, caller: str | None = None) -> bool:
    """Delete a secret. Returns True if it existed."""
    path = vault_path()

    def op() -> bool:
        if not path.exists():
            return False
        blob = path.read_bytes()
        if not blob:
            return False
        salt = blob[HEADER_SIZE + FINGERPRINT_SIZE : HEADER_SIZE + FINGERPRINT_SIZE + SALT_SIZE]
        master_key = derive_key(app_settings.secret_key, salt)
        data, _ = _decode(blob, master_key)
        existed = scope in data and key in data[scope]
        if not existed:
            return False
        del data[scope][key]
        if not data[scope]:
            del data[scope]
        _write(path, data, salt)
        _audit("delete", scope, key, caller)
        return True

    return _with_exclusive_lock(op)


def list_keys(scope: str, *, caller: str | None = None) -> list[str]:
    """List the names of all keys in a scope (NOT their values)."""
    data, _ = _read_or_init(vault_path())
    _audit("list", scope, "*", caller)
    return sorted(data.get(scope, {}).keys())


def fingerprint() -> str | None:
    """Return the stored `key_fingerprint` (hex) or None if vault not yet created.

    Used by Settings · Deployment to detect SECRET_KEY mismatch before any
    decrypt is attempted.
    """
    path = vault_path()
    if not path.exists():
        return None
    with path.open("rb") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
        try:
            preamble = fh.read(PREAMBLE_SIZE)
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    if len(preamble) < PREAMBLE_SIZE:
        return None
    return preamble[HEADER_SIZE : HEADER_SIZE + FINGERPRINT_SIZE].hex()


def expected_fingerprint(secret_key: str | None = None) -> str | None:
    """Compute what the fingerprint *should* be given the current SECRET_KEY.

    Returns None if the vault doesn't exist (since we need its salt).
    """
    path = vault_path()
    if not path.exists():
        return None
    with path.open("rb") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
        try:
            preamble = fh.read(PREAMBLE_SIZE)
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    if len(preamble) < PREAMBLE_SIZE:
        return None
    salt = preamble[HEADER_SIZE + FINGERPRINT_SIZE : HEADER_SIZE + FINGERPRINT_SIZE + SALT_SIZE]
    sk = secret_key if secret_key is not None else app_settings.secret_key
    master_key = derive_key(sk, salt)
    return fingerprint_for_key(master_key).hex()


def is_locked() -> bool:
    """True if the vault file exists but `SECRET_KEY` doesn't match.

    Settings · Deployment surfaces a banner; writes are rejected; reads of
    secret-dependent paths return 503.
    """
    stored = fingerprint()
    if stored is None:
        return False
    expected = expected_fingerprint()
    if expected is None:
        return False
    return stored != expected


# ── Key rotation ─────────────────────────────────────────────────────────


def rotate_key(
    *,
    old_secret_key: str,
    new_secret_key: str,
    backup: bool = True,
) -> dict:
    """Re-encrypt the vault with a new master key derived from `new_secret_key`.

    Algorithm:
    1. Read + decrypt with old key.
    2. Re-derive master key from new secret + a fresh salt.
    3. Atomic write to `secrets.enc.new`.
    4. Optional backup at `secrets.enc.bak.YYYY-MM-DD-HH-MM`.
    5. `os.replace` to atomically swap.

    Returns a summary dict with the old + new fingerprints + entry count.
    """
    path = vault_path()
    if not path.exists():
        raise VaultError(f"vault not found at {path}")

    with path.open("rb") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            blob = fh.read()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    salt = blob[HEADER_SIZE + FINGERPRINT_SIZE : HEADER_SIZE + FINGERPRINT_SIZE + SALT_SIZE]
    old_key = derive_key(old_secret_key, salt)
    data, _ = _decode(blob, old_key)
    old_fp = fingerprint_for_key(old_key).hex()

    # Fresh salt + nonce on rotation so neither transitions can be replayed.
    new_salt = secrets.token_bytes(SALT_SIZE)
    new_nonce = secrets.token_bytes(NONCE_SIZE)
    new_key = derive_key(new_secret_key, new_salt)
    new_blob = _encode(data, new_key, new_salt, new_nonce)
    new_fp = fingerprint_for_key(new_key).hex()

    if backup:
        ts = time.strftime("%Y-%m-%d-%H-%M")
        backup_path = path.with_suffix(path.suffix + f".bak.{ts}")
        with backup_path.open("wb") as bfh:
            bfh.write(blob)
        os.chmod(backup_path, 0o600)

    tmp = path.with_suffix(path.suffix + ".new")
    with tmp.open("wb") as fh:
        fh.write(new_blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)

    entry_count = sum(len(v) for v in data.values())
    _audit("rotate-key", "*", "*", caller="cli/vault.rotate-key")
    return {
        "old_fingerprint": old_fp,
        "new_fingerprint": new_fp,
        "entries": entry_count,
        "scopes": sorted(data.keys()),
        "backup": backup,
    }
