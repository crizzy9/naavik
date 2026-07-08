"""Plan 96a — tracking v3 bug slice, UI + route contracts.

B1: the board-move route rejects malformed payloads loudly (422) and turns
    a CLOSED-without-reason into a legible 409 — a broken drag must never
    look like success again.
B2: pending email suggestions render at page level (strip) and on the board
    card (chip), not just inside the slide-over conversation.
B4: the Track-it stage picker can represent EVERY status the email-timeline
    folder can derive — the bug class, not the Google instance.
R5: round "mark done" is the state icon on the row; the side button is gone.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


# ── B1 — /api/v1/applications/move contract ─────────────────────────────


@pytest.fixture
def client_with_user():
    from fastapi.testclient import TestClient

    from main import app
    from services.auth import require_password_complete

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False)

    async def _override():
        return user

    app.dependency_overrides[require_password_complete] = _override
    _c = TestClient(app, raise_server_exceptions=True, headers={"X-CSRF-Token": "t"})
    _c.cookies.set("naavik_csrf", "t")
    yield _c, user
    app.dependency_overrides.pop(require_password_complete, None)


def _owned_app(application_id: int = 7, owner_id: int = 42) -> SimpleNamespace:
    return SimpleNamespace(id=application_id, user_id=owner_id, status="APPLIED", deleted_at=None)


def test_move_empty_payload_is_422(client_with_user):
    """The old silent-204 branch made a payload-less drag look like success."""
    client, _ = client_with_user
    r = client.post("/api/v1/applications/move", json=None)
    assert r.status_code == 422


def test_move_missing_fields_is_422(client_with_user):
    client, _ = client_with_user
    r = client.post("/api/v1/applications/move", json={"application_id": 7})
    assert r.status_code == 422
    r = client.post("/api/v1/applications/move", json={"target_status": "OFFER"})
    assert r.status_code == 422


def test_move_unknown_status_is_422(client_with_user):
    client, _ = client_with_user
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=_owned_app())):
        r = client.post(
            "/api/v1/applications/move",
            json={"application_id": 7, "target_status": "NOT_A_STATUS"},
        )
    assert r.status_code == 422


def test_move_unknown_closed_reason_is_422(client_with_user):
    client, _ = client_with_user
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=_owned_app())):
        r = client.post(
            "/api/v1/applications/move",
            json={
                "application_id": 7,
                "target_status": "CLOSED",
                "closed_reason": "nope",
            },
        )
    assert r.status_code == 422


def test_move_closed_without_reason_is_legible_409(client_with_user):
    """The drag handler toasts `detail.message` — the 409 must carry it."""
    from services.applications import ValidationError

    client, _ = client_with_user
    with (
        patch(
            "api.applications.svc.get_application",
            new=AsyncMock(return_value=_owned_app()),
        ),
        patch(
            "api.applications.svc.update_status",
            new=AsyncMock(
                side_effect=ValidationError(
                    "closed_reason required when status=CLOSED",
                    code="closed_reason_missing",
                )
            ),
        ),
    ):
        r = client.post(
            "/api/v1/applications/move",
            json={"application_id": 7, "target_status": "CLOSED"},
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "closed_reason_missing"
    assert "closed_reason" in detail["message"]


def test_move_valid_payload_updates_status(client_with_user):
    from models.enums import ApplicationStatus

    client, _ = client_with_user
    update = AsyncMock(return_value=_owned_app())
    with (
        patch(
            "api.applications.svc.get_application",
            new=AsyncMock(return_value=_owned_app()),
        ),
        patch("api.applications.svc.update_status", new=update),
    ):
        r = client.post(
            "/api/v1/applications/move",
            json={"application_id": 7, "target_status": "RECRUITER_SCREEN"},
        )
    assert r.status_code == 204
    update.assert_awaited_once()
    args, kwargs = update.await_args
    assert args[1] == 7
    assert args[2] == ApplicationStatus.RECRUITER_SCREEN
    assert kwargs["closed_reason"] is None


def test_move_closed_with_reason_passes_it_through(client_with_user):
    from models.enums import ApplicationStatus, ClosedReason

    client, _ = client_with_user
    update = AsyncMock(return_value=_owned_app())
    with (
        patch(
            "api.applications.svc.get_application",
            new=AsyncMock(return_value=_owned_app()),
        ),
        patch("api.applications.svc.update_status", new=update),
    ):
        r = client.post(
            "/api/v1/applications/move",
            json={
                "application_id": 7,
                "target_status": "CLOSED",
                "closed_reason": "withdrawn_by_me",
            },
        )
    assert r.status_code == 204
    _, kwargs = update.await_args
    assert kwargs["closed_reason"] == ClosedReason.WITHDRAWN_BY_ME
    assert update.await_args[0][2] == ApplicationStatus.CLOSED


# ── B1 — board wiring ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    return c


def test_stage_column_dead_hx_wiring_is_gone(client):
    """`hx-trigger="end"` fired on the SOURCE column with no payload — the
    B1 root cause. The column must carry data-column for the JS handler and
    no hx-post."""
    r = client.get("/tracking")
    assert r.status_code == 200
    assert 'hx-trigger="end"' not in r.text
    assert 'hx-post="/api/v1/applications/move"' not in r.text
    assert 'data-column="APPLIED"' in r.text


def test_closed_column_carries_reason_vocabulary(client):
    """The drop handler's reason picker reads `data-closed-reasons` off the
    Closed column; every value must be a real ClosedReason member."""
    import json as _json

    from models.enums import ClosedReason

    r = client.get("/tracking?show_closed=1")
    assert r.status_code == 200
    assert "data-closed-reasons=" in r.text
    raw = r.text.split("data-closed-reasons='", 1)[1].split("'", 1)[0]
    reasons = _json.loads(raw)
    assert reasons, "closed-reasons vocabulary must not be empty"
    valid = {c.value for c in ClosedReason}
    assert {r_["value"] for r_ in reasons} <= valid


# ── B2 — suggestion strip + card chip ────────────────────────────────────


def _pending(application_id=1, message_id=475, *, suggested, current, pinned=False):
    from services.email.service import PendingSuggestion

    return PendingSuggestion(
        application_id=application_id,
        message_id=message_id,
        company="Snorkel AI",
        role="Member of Technical Staff",
        current_status=current,
        suggested_status=suggested,
        subject="Update on your Snorkel AI application",
        suggested_at=datetime.now(UTC),
        pinned=pinned,
    )


def test_pending_rejection_renders_strip_and_card_chip(client, monkeypatch):
    from models.enums import ApplicationStatus
    from services import email as email_service

    async def _fake(_session, *, user_id):
        return [
            _pending(
                suggested=ApplicationStatus.CLOSED,
                current=ApplicationStatus.ONSITE_LOOP,
            )
        ]

    monkeypatch.setattr(email_service, "list_pending_suggestions", _fake)
    r = client.get("/tracking")
    assert r.status_code == 200
    body = r.text
    # Strip: row + Apply/Dismiss posting to the existing suggestion routes.
    assert 'data-testid="pending-suggestions-strip"' in body
    assert "/api/v1/applications/1/email-suggestion/475/apply" in body
    assert "/api/v1/applications/1/email-suggestion/475/dismiss" in body
    assert "(rejection)" in body
    # No pin → no "Apply & resume".
    assert "resume=1" not in body
    # Card chip: sample application 1 sits in the OFFER column.
    assert "rejection?" in body


def test_pinned_suggestion_offers_apply_and_resume(client, monkeypatch):
    from models.enums import ApplicationStatus
    from services import email as email_service

    async def _fake(_session, *, user_id):
        return [
            _pending(
                suggested=ApplicationStatus.ONSITE_LOOP,
                current=ApplicationStatus.RECRUITER_SCREEN,
                pinned=True,
            )
        ]

    monkeypatch.setattr(email_service, "list_pending_suggestions", _fake)
    r = client.get("/tracking")
    body = r.text
    assert "/api/v1/applications/1/email-suggestion/475/apply?resume=1" in body
    # Forward suggestion chip labels with the target stage, not "rejection?".
    assert "→ Interview Stage?" in body


def test_no_pending_suggestions_renders_no_strip(client):
    r = client.get("/tracking")
    assert 'data-testid="pending-suggestions-strip"' not in r.text


# ── B4 — the picker represents every derivable status ───────────────────


def _derivable_statuses():
    """Every status `status_for_email_timeline` can return, computed by
    sweeping (classification, stage) pairs — pins the CLASS."""
    from itertools import product

    from models.enums import EmailClassification
    from services.email import status_mapper

    classes = list(EmailClassification)
    stages = [None, "screen", "interview"]
    events = list(product(classes, stages))
    derivable = set()
    for a in events:
        derivable.add(status_mapper.status_for_email_timeline([a])[0])
        for b in events:
            derivable.add(status_mapper.status_for_email_timeline([a, b])[0])
    return derivable


def test_every_derivable_status_is_a_legal_track_override():
    from ui.routes.tracking import _TRACK_STATUS_OVERRIDES

    assert _derivable_statuses() <= _TRACK_STATUS_OVERRIDES


@pytest.mark.parametrize("status", sorted(_derivable_statuses(), key=lambda s: s.value))
def test_track_picker_preselects_every_derivable_status(client, monkeypatch, status):
    """B4 instance: a group deriving CLOSED silently rendered as 'Applied'
    (browser falls back to the first option when none matches)."""
    from services.email import processes as processes_mod

    now = datetime.now(UTC)
    dp = processes_mod.DetectedProcess(
        company="Google",
        role=None,
        status=status,
        closed_reason=None,
        message_count=1,
        first_seen=now,
        last_seen=now,
        latest_subject="Re: Google Interview prep Information",
        message_ids=[1],
        possible_rejection_message_id=None,
        sender_domain="google.com",
    )

    async def _fake(_session, *, user_id):
        return [dp]

    monkeypatch.setattr(processes_mod, "list_detected_processes", _fake)
    r = client.get("/tracking")
    assert r.status_code == 200
    assert f'value="{status.value}" selected' in r.text


# ── R5 — round mark-done is the state icon on the row ───────────────────


def _render_rounds(rounds):
    from ui.templates_setup import templates

    tpl = templates.env.get_template("components/tracking/_rounds_section.html")
    return tpl.render(application={"id": 5}, rounds=rounds)


def test_round_row_state_icon_is_the_mark_done_control():
    html = _render_rounds(
        [
            {
                "id": 9,
                "kind": "system_design",
                "kind_label": "system design",
                "title": "System design",
                "state": "scheduled",
                "state_icon": "circle",
                "outcome": "pending",
                "scheduled_label": "Jul 10",
                "source": "email",
                "sessions": [],
            }
        ]
    )
    assert 'data-testid="round-mark-done-9"' in html
    assert "mark done" not in html  # the side button is gone
    assert "/api/v1/applications/5/rounds/9/state" in html


def test_completed_round_has_no_mark_done_control():
    html = _render_rounds(
        [
            {
                "id": 9,
                "kind": "system_design",
                "kind_label": "system design",
                "title": "System design",
                "state": "completed",
                "state_icon": "check-circle-2",
                "outcome": "pending",
                "scheduled_label": None,
                "source": "email",
                "sessions": [],
            }
        ]
    )
    assert 'data-testid="round-mark-done-9"' not in html
