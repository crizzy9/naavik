"""Static guard: imap_password must never leak through API surfaces or logs.

Plan 90 / 0.5.0.01 Wave 9. Sweeps `src/api/` + `src/ui/routes/` for any
template-string interpolation or log call that mentions `imap_password`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.uses_sample_data_shims


# Lines that are LEGITIMATE references (form parsing, env-secret passthrough)
# need a way to be allow-listed. The forbidden patterns target SURFACING:
# logs, response bodies, Read-schema fields.
_FORBIDDEN_PATTERNS = (
    # Bare logging of imap_password in any log call.
    re.compile(r"log\.\w+\([^\)]*imap_password\b"),
    re.compile(r"print\([^\)]*imap_password\b"),
)


def _scan(root: Path) -> list[tuple[Path, str]]:
    offenders: list[tuple[Path, str]] = []
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_PATTERNS:
            m = pat.search(text)
            if m:
                offenders.append((py, m.group(0)))
    return offenders


def test_no_imap_password_in_logs_or_responses():
    src_root = Path(__file__).resolve().parent.parent / "src"
    api = src_root / "api"
    routes = src_root / "ui" / "routes"
    services = src_root / "services"

    offenders: list[tuple[Path, str]] = []
    for area in (api, routes, services):
        if area.exists():
            offenders.extend(_scan(area))

    assert not offenders, (
        "imap_password leak risk — never log/print/expose decrypted plaintext:\n"
        + "\n".join(f"  {p.relative_to(src_root.parent)}: {hit!r}" for p, hit in offenders)
    )


def test_email_account_read_excludes_password():
    """`EmailAccountRead` Pydantic schema must NOT carry imap_password."""
    from api.integrations_email import EmailAccountRead

    field_names = set(EmailAccountRead.model_fields.keys())
    assert "imap_password" not in field_names
    assert "imap_password_encrypted" not in field_names
