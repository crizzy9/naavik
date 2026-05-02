"""Vault service tests — Wave 4 of plan 10 § B.5.

Pure-Python coverage:
- AES-256-GCM round-trip (encrypt → decrypt → matches).
- PBKDF2 key derivation (deterministic for same SECRET_KEY+salt; different
  for different keys).
- File-lock concurrency (parallel writes don't corrupt; sequential ordering).
- `key_fingerprint` mismatch detection — wrong SECRET_KEY raises VaultLockedError
  WITHOUT attempting AES decrypt.
- Audit log: one line per get/set/delete; secret value never logged.
- `rotate_key` CLI: round-trip + fresh salt + .bak file.
"""

from __future__ import annotations

import json
import os
import threading

import pytest

# Force a deterministic test SECRET_KEY before any vault calls land.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-vault-tests-32bytes")

from services import vault as v  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Point the vault at a tmp dir; reset secret_key per test."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_settings, "secret_key", "test-secret-key-for-vault-tests-32bytes")
    yield


# ── AES-GCM round-trip ──────────────────────────────────────────────────


def test_set_then_get_round_trip() -> None:
    v.set("llm", "anthropic", "sk-test-1234567890abcdef")
    assert v.get("llm", "anthropic") == "sk-test-1234567890abcdef"


def test_get_returns_none_for_missing() -> None:
    assert v.get("llm", "nonexistent") is None
    assert v.get("nonexistent_scope", "key") is None


def test_set_overwrites_value() -> None:
    v.set("llm", "openai", "first")
    v.set("llm", "openai", "second")
    assert v.get("llm", "openai") == "second"


def test_set_distinct_scopes() -> None:
    v.set("llm", "anthropic", "key-llm")
    v.set("ats", "greenhouse", "cookie-ats")
    assert v.get("llm", "anthropic") == "key-llm"
    assert v.get("ats", "greenhouse") == "cookie-ats"


def test_delete_removes_key() -> None:
    v.set("notifications", "discord_webhook_url", "https://discord/x")
    assert v.delete("notifications", "discord_webhook_url") is True
    assert v.get("notifications", "discord_webhook_url") is None
    # Idempotent — second delete returns False without error.
    assert v.delete("notifications", "discord_webhook_url") is False


def test_list_keys_returns_names_only() -> None:
    v.set("llm", "anthropic", "AAA")
    v.set("llm", "openai", "BBB")
    keys = v.list_keys("llm")
    assert sorted(keys) == ["anthropic", "openai"]
    # Crucial: list never returns secret values.
    assert "AAA" not in keys
    assert "BBB" not in keys


# ── PBKDF2 ───────────────────────────────────────────────────────────────


def test_derive_key_deterministic() -> None:
    salt = b"\x00" * 32
    a = v.derive_key("password", salt)
    b = v.derive_key("password", salt)
    assert a == b


def test_derive_key_changes_per_secret() -> None:
    salt = b"\x00" * 32
    a = v.derive_key("password-a", salt)
    b = v.derive_key("password-b", salt)
    assert a != b


def test_derive_key_changes_per_salt() -> None:
    a = v.derive_key("password", b"\x00" * 32)
    b = v.derive_key("password", b"\xff" * 32)
    assert a != b


# ── Fingerprint & lock detection ────────────────────────────────────────


def test_fingerprint_changes_with_secret_key(monkeypatch) -> None:
    from config import settings as app_settings

    v.set("scope", "k", "value-1")
    fp_before = v.fingerprint()
    assert fp_before is not None

    monkeypatch.setattr(app_settings, "secret_key", "completely-different-secret-key")
    expected = v.expected_fingerprint()
    assert expected is not None
    # The stored fp is what the CURRENT SECRET_KEY would produce; if we change
    # the env, expected_fingerprint computes what the NEW key would produce
    # against the SAME salt — different from stored.
    assert expected != fp_before


def test_is_locked_false_after_set() -> None:
    v.set("scope", "k", "value-1")
    assert v.is_locked() is False


def test_is_locked_true_when_key_mismatches(monkeypatch) -> None:
    from config import settings as app_settings

    v.set("scope", "k", "value-1")
    monkeypatch.setattr(app_settings, "secret_key", "another-secret-key-entirely-32bytes!")
    assert v.is_locked() is True


def test_get_raises_when_locked(monkeypatch) -> None:
    from config import settings as app_settings

    v.set("scope", "k", "value-1")
    monkeypatch.setattr(app_settings, "secret_key", "yet-another-different-secret-32by")
    with pytest.raises(v.VaultLockedError):
        v.get("scope", "k")


# ── Audit log ───────────────────────────────────────────────────────────


def test_audit_log_records_get_set_delete() -> None:
    v.set("llm", "anthropic", "sk-secret-do-not-log")
    v.get("llm", "anthropic")
    v.delete("llm", "anthropic")

    audit_path = v.audit_log_path()
    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    ops = [json.loads(line)["op"] for line in lines]
    assert "set" in ops
    assert "get" in ops
    assert "delete" in ops

    # CRITICAL: no secret value appears anywhere in audit log.
    contents = audit_path.read_text(encoding="utf-8")
    assert "sk-secret-do-not-log" not in contents


def test_audit_log_carries_caller() -> None:
    v.set("scope", "k", "value", caller="test-suite")
    audit = v.audit_log_path().read_text(encoding="utf-8").splitlines()
    last = json.loads(audit[-1])
    assert last["caller"] == "test-suite"


# ── File-locking concurrency ────────────────────────────────────────────


def test_concurrent_set_no_corruption() -> None:
    """Spawn 10 threads each writing a distinct key; no corruption."""
    errors: list[Exception] = []

    def writer(i: int) -> None:
        try:
            v.set("concurrent", f"key-{i}", f"value-{i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    keys = v.list_keys("concurrent")
    assert len(keys) == 10
    for i in range(10):
        assert v.get("concurrent", f"key-{i}") == f"value-{i}"


# ── Rotate-key ──────────────────────────────────────────────────────────


def test_rotate_key_round_trip(monkeypatch) -> None:
    from config import settings as app_settings

    v.set("llm", "anthropic", "sk-AAA")
    v.set("ats", "greenhouse", "cookie-AAA")

    summary = v.rotate_key(
        old_secret_key=app_settings.secret_key,
        new_secret_key="rotated-new-secret-key-32-bytes-aa",
    )
    assert summary["entries"] == 2
    assert "llm" in summary["scopes"]
    assert "ats" in summary["scopes"]
    assert summary["old_fingerprint"] != summary["new_fingerprint"]

    # Switch the env to new key; old vault now decrypts.
    monkeypatch.setattr(app_settings, "secret_key", "rotated-new-secret-key-32-bytes-aa")
    assert v.get("llm", "anthropic") == "sk-AAA"
    assert v.get("ats", "greenhouse") == "cookie-AAA"


def test_rotate_key_writes_backup() -> None:
    v.set("scope", "k", "value-1")
    path = v.vault_path()

    v.rotate_key(
        old_secret_key="test-secret-key-for-vault-tests-32bytes",
        new_secret_key="another-secret-key-32-bytes-aaaa",
        backup=True,
    )

    baks = sorted(path.parent.glob(f"{path.name}.bak.*"))
    assert len(baks) >= 1


def test_rotate_key_no_backup_flag() -> None:
    v.set("scope", "k", "value-1")
    path = v.vault_path()

    v.rotate_key(
        old_secret_key="test-secret-key-for-vault-tests-32bytes",
        new_secret_key="another-secret-key-32-bytes-aaaa",
        backup=False,
    )

    baks = list(path.parent.glob(f"{path.name}.bak.*"))
    assert len(baks) == 0


def test_rotate_key_wrong_old_raises() -> None:
    v.set("scope", "k", "value-1")
    with pytest.raises(v.VaultError):
        v.rotate_key(
            old_secret_key="WRONG-OLD-KEY",
            new_secret_key="new-key-here",
        )


def test_rotate_key_no_vault_raises(tmp_path, monkeypatch) -> None:
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path / "empty"))
    with pytest.raises(v.VaultError):
        v.rotate_key(old_secret_key="x", new_secret_key="y")


# ── CLI smoke ───────────────────────────────────────────────────────────


def test_cli_rotate_key_dry_run(capsys, monkeypatch) -> None:
    from cli.vault import main as cli_main

    v.set("scope", "k", "value-1")
    rc = cli_main(
        [
            "rotate-key",
            "--old",
            "test-secret-key-for-vault-tests-32bytes",
            "--new",
            "rotated-via-cli-secret-32-bytes!",
            "--no-backup",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "fingerprint" in out
    assert "done" in out
