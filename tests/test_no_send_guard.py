"""Static no-send guard — plan 96f (owner decisions #5, #6).

Naavik must demonstrably be UNABLE to send mail: the scheduling assistant
drafts, the OWNER sends. This walks the entire `src/` tree and fails on any
send capability — an SMTP client, a sendmail invocation, a Gmail/Graph send
scope or send endpoint. If a future consented "send rung" ever ships, it
arrives by consciously editing THIS test alongside the owner-approved plan,
never by accident.
"""

from __future__ import annotations

import pathlib
import re

_SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

_FORBIDDEN = (
    # (human label, pattern)
    ("smtplib import", re.compile(r"\bimport\s+smtplib\b|\bfrom\s+smtplib\b")),
    ("aiosmtplib import", re.compile(r"\baiosmtplib\b")),
    ("SMTP client construction", re.compile(r"\bSMTP(?:_SSL)?\s*\(")),
    ("sendmail call", re.compile(r"\bsendmail\s*\(|\bsend_message\s*\(")),
    ("Gmail send scope", re.compile(r"gmail\.send|gmail\.compose\b|gmail\.modify")),
    ("Gmail API send endpoint", re.compile(r"/gmail/v1/users/[^\"']*/messages/send")),
    ("Graph sendMail endpoint", re.compile(r"\bsendMail\b")),
)


def test_src_tree_has_no_send_capability():
    offenders: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in _FORBIDDEN:
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(_SRC)}:{line_no} — {label}")
    assert not offenders, "send capability found in src/:\n" + "\n".join(offenders)


def test_no_smtp_dependency_declared():
    pyproject = (_SRC.parent / "pyproject.toml").read_text(encoding="utf-8")
    for needle in ("aiosmtplib", "yagmail", "redmail"):
        assert needle not in pyproject, f"mail-sending dependency {needle!r} declared"


def test_gmail_link_is_compose_only():
    """The one Gmail URL Naavik produces is the COMPOSE deep-link (view=cm) —
    a page the owner's browser opens, not an API Naavik calls."""
    from services.scheduling import gmail_compose_url

    url = gmail_compose_url(to="a@b.co", subject="s", body="b")
    assert url.startswith("https://mail.google.com/mail/?")
    assert "view=cm" in url
