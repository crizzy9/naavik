"""IMAP sync service — plan 90 (0.5.0.01).

Per-account inbox fetch over IMAP4_SSL using stdlib `imaplib` wrapped in
`asyncio.to_thread` (engineer deviation D2 — plan called for `aioimaplib` but
that's not in pyproject base deps; adding a new lib for a scaffold PR is a
heavier commitment than the threadpool path, and stdlib semantics match
exactly. `aioimaplib` swap is a follow-up if benchmarks call for it).

Sync scope:
- For each live `EmailAccount` with status=OK, fetch UIDs received since
  `last_synced_uid` (or last 50 if first sync), cap 500 per run.
- Per message: parse RFC 5322 headers, write `EmailMessage` row (classification
  left None — classifier cron picks up unprocessed rows next tick), upsert
  `EmailThread` keyed by `Message-ID` / `In-Reply-To` / `References` fallback.
- On `imaplib.IMAP4.error` with login failure: flip account status to
  AUTH_REQUIRED + bump connection_failure_count; cron skips next tick until
  user re-pastes app-password.

Network is NOT exercised in tests — `_imap_client_factory` is the dependency
seam. Tests pass a fake client that returns canned RFC 5322 messages.
"""

from __future__ import annotations

import asyncio
import email
import email.utils
import imaplib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import Message
from typing import Any, Protocol

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import EmailAccount, EmailAccountStatus, EmailMessage, EmailThread
from services import email_credentials
from services.imap_host_guard import (
    SAFE_ERROR_MESSAGE as _ERR_HOST,
)
from services.imap_host_guard import (
    ImapHostNotAllowed,
    ensure_imap_host_allowed,
)

log = logging.getLogger(__name__)

# Hard cap per-sync to bound classifier LLM cost downstream.
_MAX_MESSAGES_PER_SYNC = 500
# First sync: pull the last N messages so the user sees signal immediately.
_FIRST_SYNC_BACKFILL = 50
_IMAP_CONNECT_TIMEOUT_S = 30

# Untrusted-field caps (PR #214 hacker M1/L3). subject/sender_name mirror the
# 200-char snippet cap; sender_email caps at the RFC 5321 local+domain max.
_MAX_SUBJECT_LEN = 200
_MAX_SENDER_EMAIL_LEN = 254
_MAX_SENDER_NAME_LEN = 200

# Canonical client-facing connection errors — never echo raw `str(exc)`, which
# leaks IMAP server banners / internal-topology signal (PR #214 hacker H1/L1).
_ERR_CONN = "Could not connect to the mail server."
_ERR_AUTH = "Authentication failed — check the username and app-password."


class _IMAPClient(Protocol):
    """Minimal surface of `imaplib.IMAP4_SSL` we depend on.

    Tests pass a fake that implements only these methods.
    """

    def login(self, user: str, password: str) -> Any: ...
    def select(self, mailbox: str) -> Any: ...
    def uid(self, command: str, *args: str) -> Any: ...
    def logout(self) -> Any: ...


def _default_client_factory(host: str, port: int) -> _IMAPClient:
    return imaplib.IMAP4_SSL(host=host, port=port, timeout=_IMAP_CONNECT_TIMEOUT_S)


@dataclass(slots=True)
class SyncResult:
    account_id: int
    fetched: int = 0
    new: int = 0
    errors: list[str] = field(default_factory=list)
    status: EmailAccountStatus = EmailAccountStatus.OK


@dataclass(slots=True)
class AggregateSyncResult:
    accounts: int = 0
    fetched: int = 0
    new: int = 0
    failed: int = 0


def _parse_message(raw: bytes) -> Message:
    return email.message_from_bytes(raw)


def _extract_snippet(msg: Message, *, limit: int = 200) -> str:
    """Return the first 200 chars of the plaintext body, normalized."""
    body_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body_parts.append(payload.decode("utf-8", errors="replace"))
                break
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            body_parts.append(payload.decode("utf-8", errors="replace"))
    snippet = " ".join("".join(body_parts).split())
    return snippet[:limit]


def _extract_sender(msg: Message) -> tuple[str, str | None]:
    raw = msg.get("From") or ""
    name, addr = email.utils.parseaddr(raw)
    return addr or raw, (name or None)


def _extract_received_at(msg: Message) -> datetime:
    raw = msg.get("Date")
    if raw:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
    return datetime.now(UTC)


def _extract_thread_key(msg: Message) -> str:
    """Prefer References (root), then In-Reply-To, then Message-ID."""
    refs = msg.get("References")
    if refs:
        first = refs.split()[0].strip()
        if first:
            return first
    in_reply = msg.get("In-Reply-To")
    if in_reply:
        return in_reply.strip()
    msg_id = msg.get("Message-ID")
    if msg_id:
        return msg_id.strip()
    return f"unkeyed-{datetime.now(UTC).timestamp()}"


async def _get_or_create_thread(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    thread_key: str,
    subject: str,
    received_at: datetime,
) -> EmailThread:
    existing = (
        await session.exec(
            select(EmailThread).where(
                EmailThread.user_id == user_id,
                EmailThread.thread_id_external == thread_key,
            )
        )
    ).one_or_none()
    if existing is not None:
        existing.message_count = (existing.message_count or 0) + 1
        if received_at > existing.latest_message_at:
            existing.latest_message_at = received_at
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
        return existing
    # Default unclassified — classifier cron promotes.
    from models.enums import EmailClassification

    thread = EmailThread(
        user_id=user_id,
        provider=provider,
        thread_id_external=thread_key,
        subject=subject,
        classification=EmailClassification.OTHER,
        auto_classified=True,
        manually_verified=False,
        latest_message_at=received_at,
        message_count=1,
    )
    session.add(thread)
    await session.flush()
    return thread


def _fetch_imap_messages(
    client: _IMAPClient,
    *,
    username: str,
    password: str,
    last_synced_uid: str | None,
) -> list[tuple[str, bytes]]:
    """Synchronous IMAP block — runs inside `asyncio.to_thread`.

    Returns list of `(uid, raw_rfc822_bytes)` newest-first, capped at
    `_MAX_MESSAGES_PER_SYNC`. Raises on protocol errors; caller maps those
    to `EmailAccountStatus`.
    """
    client.login(username, password)
    client.select("INBOX")

    if last_synced_uid:
        criterion = f"UID {int(last_synced_uid) + 1}:*"
        typ, data = client.uid("SEARCH", None, criterion)  # type: ignore[arg-type]
    else:
        typ, data = client.uid("SEARCH", "ALL")  # type: ignore[arg-type]
    if typ != "OK" or not data or not data[0]:
        client.logout()
        return []
    raw_uids = data[0].split() if isinstance(data[0], bytes) else data[0].encode().split()
    uids = [u.decode("ascii") for u in raw_uids][-_MAX_MESSAGES_PER_SYNC:]

    out: list[tuple[str, bytes]] = []
    for uid in reversed(uids):
        typ, fetched = client.uid("FETCH", uid, "(RFC822)")
        if typ != "OK" or not fetched:
            continue
        for part in fetched:
            if isinstance(part, tuple) and len(part) >= 2:
                raw = part[1]
                if isinstance(raw, bytes):
                    out.append((uid, raw))
                    break
    client.logout()
    return out


async def sync_account(
    session: AsyncSession,
    account: EmailAccount,
    *,
    client_factory=_default_client_factory,
) -> SyncResult:
    """Fetch + persist new messages for one EmailAccount.

    Caller awaits + commits. On AUTH_REQUIRED the account row is flipped in
    place + persisted via `session.add` so the next cron tick skips it.
    """
    result = SyncResult(account_id=account.id or 0)
    password = email_credentials.load_imap_password(account)
    if password is None:
        # Ciphertext no longer decrypts (SECRET_KEY rotated, or never stored).
        # Fail closed: flip to AUTH_REQUIRED so the operator re-pastes the
        # app-password; never attempt a login with a missing credential.
        account.status = EmailAccountStatus.AUTH_REQUIRED
        account.connection_failure_count = (account.connection_failure_count or 0) + 1
        account.last_error_message = (
            "credential decrypt failed (SECRET_KEY rotated?); re-paste app-password"
        )
        account.updated_at = datetime.now(UTC)
        session.add(account)
        result.status = EmailAccountStatus.AUTH_REQUIRED
        result.errors.append("decrypt: credential could not be decrypted")
        return result

    def _runner() -> list[tuple[str, bytes]]:
        # Re-check the host at every sync (not just at connect) so a DNS-rebind
        # to an internal target between connect-time and now is caught here.
        ensure_imap_host_allowed(account.imap_host, account.imap_port)
        client = client_factory(account.imap_host, account.imap_port)
        return _fetch_imap_messages(
            client,
            username=account.imap_username,
            password=password,
            last_synced_uid=account.last_synced_uid,
        )

    try:
        rows = await asyncio.to_thread(_runner)
    except ImapHostNotAllowed as exc:
        # Fail closed: a now-disallowed host (e.g. DNS-rebind) stops syncing
        # until the operator re-connects, which re-runs the guard.
        log.warning("email_sync: blocked host account_id=%s reason=%s", account.id, exc.reason)
        account.status = EmailAccountStatus.AUTH_REQUIRED
        account.connection_failure_count = (account.connection_failure_count or 0) + 1
        account.last_error_message = _ERR_HOST
        account.updated_at = datetime.now(UTC)
        session.add(account)
        result.status = EmailAccountStatus.AUTH_REQUIRED
        result.errors.append(_ERR_HOST)
        return result
    except imaplib.IMAP4.error as exc:
        log.warning("email_sync: auth error account_id=%s err=%s", account.id, exc)
        account.status = EmailAccountStatus.AUTH_REQUIRED
        account.connection_failure_count = (account.connection_failure_count or 0) + 1
        account.last_error_message = _ERR_AUTH
        account.updated_at = datetime.now(UTC)
        session.add(account)
        result.status = EmailAccountStatus.AUTH_REQUIRED
        result.errors.append(_ERR_AUTH)
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("email_sync: transport error account_id=%s err=%s", account.id, exc)
        account.connection_failure_count = (account.connection_failure_count or 0) + 1
        account.last_error_message = _ERR_CONN
        account.updated_at = datetime.now(UTC)
        session.add(account)
        result.errors.append(_ERR_CONN)
        return result

    result.fetched = len(rows)
    highest_uid = account.last_synced_uid
    for uid, raw in rows:
        try:
            msg = _parse_message(raw)
            sender_email, sender_name = _extract_sender(msg)
            sender_email = sender_email[:_MAX_SENDER_EMAIL_LEN]
            if sender_name is not None:
                sender_name = sender_name[:_MAX_SENDER_NAME_LEN]
            subject = (msg.get("Subject") or "").strip()[:_MAX_SUBJECT_LEN]
            received_at = _extract_received_at(msg)
            thread_key = _extract_thread_key(msg)
            message_id_external = (msg.get("Message-ID") or f"uid-{uid}").strip()
            snippet = _extract_snippet(msg)

            thread = await _get_or_create_thread(
                session,
                user_id=account.user_id,
                provider=account.provider.value,
                thread_key=thread_key,
                subject=subject,
                received_at=received_at,
            )
            # Dedup on (thread_id, message_id_external).
            existing = (
                await session.exec(
                    select(EmailMessage).where(
                        EmailMessage.thread_id == thread.id,
                        EmailMessage.message_id_external == message_id_external,
                    )
                )
            ).one_or_none()
            if existing is not None:
                continue

            row = EmailMessage(
                user_id=account.user_id,
                thread_id=thread.id,
                account_id=account.id,
                application_id=thread.application_id,
                provider=account.provider.value,
                message_id_external=message_id_external,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                received_at=received_at,
            )
            session.add(row)
            result.new += 1
            if highest_uid is None or int(uid) > int(highest_uid):
                highest_uid = uid
        except Exception as exc:  # noqa: BLE001
            log.warning("email_sync: skipping malformed message uid=%s err=%s", uid, exc)
            result.errors.append(f"parse-uid-{uid}: {exc}")

    account.last_sync_at = datetime.now(UTC)
    if highest_uid is not None:
        account.last_synced_uid = highest_uid
    account.status = EmailAccountStatus.OK
    account.connection_failure_count = 0
    account.last_error_message = None
    account.updated_at = datetime.now(UTC)
    session.add(account)
    return result


async def sync_all_accounts(
    session: AsyncSession,
    *,
    client_factory=_default_client_factory,
) -> AggregateSyncResult:
    accounts = (
        await session.exec(
            select(EmailAccount).where(
                EmailAccount.deleted_at.is_(None),
                EmailAccount.status != EmailAccountStatus.DISABLED,
            )
        )
    ).all()
    agg = AggregateSyncResult(accounts=len(accounts))
    for account in accounts:
        # Skip already-broken accounts; user must re-paste via Settings.
        if account.status == EmailAccountStatus.AUTH_REQUIRED:
            agg.failed += 1
            continue
        res = await sync_account(session, account, client_factory=client_factory)
        agg.fetched += res.fetched
        agg.new += res.new
        if res.errors:
            agg.failed += 1
    return agg


async def test_imap_connection(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    client_factory=_default_client_factory,
) -> tuple[bool, str | None]:
    """One-shot login+logout — used by Connect IMAP form to verify creds.

    Returns a canonical error message on failure (never the raw `str(exc)`):
    the SSRF guard runs first, then the connection itself; details are logged
    server-side only (PR #214 hacker H1/L1).
    """

    def _runner() -> None:
        ensure_imap_host_allowed(host, port)
        client = client_factory(host, port)
        client.login(username, password)
        client.select("INBOX")
        client.logout()

    try:
        await asyncio.to_thread(_runner)
        return True, None
    except ImapHostNotAllowed as exc:
        log.warning("test_imap_connection: blocked host=%r reason=%s", host, exc.reason)
        return False, _ERR_HOST
    except imaplib.IMAP4.error as exc:
        log.warning("test_imap_connection: auth error host=%r err=%s", host, exc)
        return False, _ERR_AUTH
    except Exception as exc:  # noqa: BLE001
        log.warning("test_imap_connection: transport error host=%r err=%s", host, exc)
        return False, _ERR_CONN
