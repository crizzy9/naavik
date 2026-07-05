"""Cross-user IDOR sweep (plan 91 Phase 1.1).

The safety net for the Phase-1 auth/ownership fixes. Runs on the sqlite tier
(NOT the shim tier — the conftest shims ignore `user_id`, so they structurally
cannot catch an IDOR): seeds a victim (user 2) with a contact, bullet,
application, and outreach message, then drives the routes as the attacker
(user 1, via the debug fake-session) and asserts every cross-user access is a
404 — same shape as a missing row, no existence oracle, no data leak, no
mutation. A positive control confirms the owner still gets their own data.

Against the pre-fix code every cross-user case returned 200/204 with the
victim's data (or mutated it); these assertions were authored RED.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from tests._sqlite import USER_TABLES

# Deliberately NO `uses_sample_data_shims` marker — this is the sqlite tier.

_CSRF = "idor-sweep-csrf-token"
_NOW = datetime(2026, 7, 4, tzinfo=UTC)

# Resource ids: user 1 = attacker/owner, user 2 = victim.
VICTIM_CONTACT = 2
VICTIM_BULLET = 2
VICTIM_APP = 2
VICTIM_MSG = 2
OWNER_CONTACT = 1


def _seed(sync_url: str) -> None:
    from models import Application, Contact, Experience, OutreachMessage, User
    from models.enums import (
        ApplicationBoard,
        ApplicationStatus,
        ContactType,
        DocsState,
        OutreachIntent,
        OutreachStatus,
        RecruiterState,
        ReferralState,
    )

    engine = create_engine(sync_url)
    SQLModel.metadata.create_all(engine, tables=USER_TABLES)
    now = _NOW.isoformat(sep=" ")

    # Users first (no ARRAY columns → ORM is fine).
    with Session(engine) as s:
        s.add(User(id=1, email="attacker@t.test", password_hash="x"))
        s.add(User(id=2, email="victim@t.test", password_hash="x"))
        s.commit()

    # Profile carries ARRAY(String) target_titles/target_cities + JSONB columns
    # the ORM can't bind on sqlite; owns_bullet's JOIN never reads them, so
    # raw-insert with TEXT literals. (Same reason Bullet.tags is raw below.)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO profile (id, user_id, full_name, headline, email, "
                "open_to_opportunities, work_authorization, cover_letter_base, target_titles, "
                "title_expansions, target_cities, remote_ok, score_history, "
                "created_at, updated_at) VALUES "
                "(2, 2, 'Victim', 'Eng', 'victim@t.test', 1, 'US_CITIZEN', 'null', '[]', '{}', "
                "'[]', 1, '{}', :now, :now)"
            ),
            {"now": now},
        )

    # Experience (ORM, FK → profile 2).
    with Session(engine) as s:
        s.add(
            Experience(
                id=2, profile_id=2, company="VictimCo", title="Eng", start_date=_NOW, order_index=0
            )
        )
        s.commit()

    # Bullet (raw — tags ARRAY; FK → experience 2).
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO bullet (id, experience_id, text, tags, order_index, "
                "created_at, updated_at) VALUES (:id, 2, :txt, '{}', 0, :now, :now)"
            ),
            {"id": VICTIM_BULLET, "txt": "secret bullet", "now": now},
        )

    # Contacts / application / message (ORM, no ARRAY columns).
    with Session(engine) as s:
        s.add(
            Contact(
                id=VICTIM_CONTACT, user_id=2, type=ContactType.RECRUITER, name="V", company="VC"
            )
        )
        s.add(
            Contact(
                id=OWNER_CONTACT, user_id=1, type=ContactType.RECRUITER, name="Mine", company="MC"
            )
        )
        s.add(
            Application(
                id=VICTIM_APP,
                user_id=2,
                job_id=None,
                company="VictimCo",
                role="Eng",
                status=ApplicationStatus.APPLIED,
                docs_state=DocsState.NONE,
                recruiter_state=RecruiterState.NONE,
                referral_state=ReferralState.NONE,
                board=ApplicationBoard.MANUAL,
                applied_at=_NOW,
            )
        )
        s.add(
            OutreachMessage(
                id=VICTIM_MSG,
                user_id=2,
                contact_id=VICTIM_CONTACT,
                intent=OutreachIntent.FOLLOW_UP,
                channel="linkedin",
                body="secret draft",
                status=OutreachStatus.DRAFT,
            )
        )
        s.commit()
    engine.dispose()


def _contact_deleted_at(sync_url: str, contact_id: int):
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT deleted_at FROM contact WHERE id = :id"), {"id": contact_id}
            ).first()
        return row[0] if row else "MISSING"
    finally:
        engine.dispose()


def _message_status(sync_url: str, message_id: int):
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT status FROM outreach_message WHERE id = :id"), {"id": message_id}
            ).first()
        return row[0] if row else "MISSING"
    finally:
        engine.dispose()


@pytest.fixture
def idor_ctx(tmp_path):
    """(client-as-user-1, sync_url) with a seeded victim (user 2)."""
    from db.session import get_session
    from main import app

    db_file = tmp_path / "idor.sqlite"
    sync_url = f"sqlite:///{db_file}"
    async_url = f"sqlite+aiosqlite:///{db_file}"
    _seed(sync_url)

    async def _override_session():
        # Fresh engine per request, all on the same file, created inside
        # TestClient's own event loop — avoids the in-memory loop-binding trap.
        engine = create_async_engine(async_url)
        try:
            maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with maker() as session:
                yield session
        finally:
            await engine.dispose()

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")  # attacker resolves to user 1
    client.cookies.set("naavik_csrf", _CSRF)
    try:
        yield client, sync_url
    finally:
        app.dependency_overrides.pop(get_session, None)


_CSRF_HEADERS = {"X-CSRF-Token": _CSRF}


def test_get_contact_cross_user_is_404(idor_ctx):
    client, _ = idor_ctx
    r = client.get(f"/api/v1/contacts/{VICTIM_CONTACT}")
    assert r.status_code == 404, r.text
    assert "secret" not in r.text.lower()


def test_owner_can_read_own_contact(idor_ctx):
    """Positive control — the fix must not 404 the owner's own data."""
    client, _ = idor_ctx
    r = client.get(f"/api/v1/contacts/{OWNER_CONTACT}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == OWNER_CONTACT


def test_put_contact_cross_user_is_404(idor_ctx):
    client, _ = idor_ctx
    r = client.put(
        f"/api/v1/contacts/{VICTIM_CONTACT}", json={"name": "hacked"}, headers=_CSRF_HEADERS
    )
    assert r.status_code == 404, r.text


def test_delete_contact_cross_user_is_404_and_not_deleted(idor_ctx):
    client, sync_url = idor_ctx
    r = client.request("DELETE", f"/api/v1/contacts/{VICTIM_CONTACT}", headers=_CSRF_HEADERS)
    assert r.status_code == 404, r.text
    assert _contact_deleted_at(sync_url, VICTIM_CONTACT) is None  # not soft-deleted


def test_bullet_editor_modal_cross_user_is_404(idor_ctx):
    client, _ = idor_ctx
    r = client.get(f"/_modal/bullet-editor/{VICTIM_BULLET}")
    assert r.status_code == 404, r.text
    assert "secret bullet" not in r.text


def test_bullet_row_fragment_cross_user_is_404(idor_ctx):
    client, _ = idor_ctx
    r = client.get(f"/_fragments/profile/bullet-row/{VICTIM_BULLET}")
    assert r.status_code == 404, r.text
    assert "secret bullet" not in r.text


def test_outreach_messages_by_contact_cross_user_is_404(idor_ctx):
    client, _ = idor_ctx
    r = client.get(f"/api/v1/outreach/messages?contact_id={VICTIM_CONTACT}")
    assert r.status_code == 404, r.text
    assert "secret draft" not in r.text


def test_outreach_messages_by_app_cross_user_is_404(idor_ctx):
    client, _ = idor_ctx
    r = client.get(f"/api/v1/outreach/messages?app_id={VICTIM_APP}")
    assert r.status_code == 404, r.text


def test_contacts_by_app_cross_user_is_404(idor_ctx):
    client, _ = idor_ctx
    r = client.get(f"/api/v1/contacts?app_id={VICTIM_APP}")
    assert r.status_code == 404, r.text


def test_outreach_draft_against_foreign_contact_is_404(idor_ctx):
    client, _ = idor_ctx
    r = client.post(
        "/api/v1/outreach/draft",
        json={"contact_id": VICTIM_CONTACT, "intent": "follow_up"},
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 404, r.text


def test_outreach_send_cross_user_is_404_and_not_sent(idor_ctx):
    client, sync_url = idor_ctx
    r = client.post("/api/v1/outreach/send", json={"message_id": VICTIM_MSG}, headers=_CSRF_HEADERS)
    assert r.status_code == 404, r.text
    assert _message_status(sync_url, VICTIM_MSG) == "DRAFT"  # not flipped to SENT
