"""`/api/v1/profile-answers/*` — plan 61 (0.2.7.14).

Single mutating endpoint: `POST /api/v1/profile-answers/{id}/accept`. The
"reuse-prompt" UI fires this when the user accepts a suggested answer; we
bump `times_accepted` + `last_used_at`. The screener-answer prefill itself
is wired in `services/document_generator.py:answer_screeners` — this route
only records the acceptance signal.

Per-user IDOR enforced via `_effective_user_id`. Cross-user accept returns
404 (decision D8).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import User
from services import profile_answer_service
from services.auth import require_authed_session

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    return user.id if user is not None else 1


@router.post(
    "/api/v1/profile-answers/{profile_answer_id}/accept",
    name="api_profile_answers_accept",
)
async def post_accept(
    profile_answer_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    user_id = _effective_user_id(_user)
    ok = await profile_answer_service.record_acceptance(
        session, user_id=user_id, profile_answer_id=profile_answer_id
    )
    if not ok:
        raise HTTPException(status_code=404, detail="profile_answer not found")
    await session.commit()
    return {"ok": True, "profile_answer_id": profile_answer_id}
