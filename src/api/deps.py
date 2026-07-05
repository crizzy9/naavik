"""Auth + ownership-guard FastAPI dependencies.

Two families live here:

- **Session deps** (`get_current_user`, `require_password_complete`,
  `require_authed_session`) — moved out of `services/auth.py` in plan 91
  Phase 4.1. They are HTTP concerns (cookies, redirects, HX headers), and
  hosting them in the delivery layer removes the service-layer
  `from ui.auth_stub import` violation. They call the token/user primitives
  THROUGH the `services.auth` facade (`auth.verify_jwt_async(...)`) so the
  existing `monkeypatch.setattr(services.auth, "verify_jwt_async", ...)`
  test seams keep intercepting them.

- **Ownership guards** (plan 91 Phase 1.4) — centralize the
  fetch-then-ownership-check that was hand-rolled ~40× across route
  handlers, and *forgotten* on the contacts / bullet-fragment / outreach
  routes (the IDOR bugs Phase 1 fixed). Expressing the check as a
  dependency puts it in the route signature, where it cannot be silently
  omitted the way an inline `if row.user_id != uid` can.

`require_authed_session` returns `User | None` — None is the debug fake-session,
which maps to the seeded owner (user 1) via `effective_user_id`. In production
the fake session is rejected, so an unauthenticated caller never reaches these.
"""

from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import Application, Bullet, Contact, User
from services import auth
from services.auth import SESSION_COOKIE


def effective_user_id(user: User | None) -> int:
    """Acting user id; the debug fake-session (None) maps to the owner."""
    return user.id if user is not None else 1


# ── Session deps (formerly services/auth.py) ─────────────────────────────


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    naavik_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    """Resolve the user via JWT cookie. Raise 401 on missing/invalid."""
    if not naavik_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    result = await auth.verify_jwt_async(session, naavik_session)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user_id, jti, _ = result
    if await auth.is_jwt_revoked(session, jti=jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")
    user = await auth.get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
    return user


async def require_password_complete(
    user: User = Depends(get_current_user),
) -> User:
    """Like `get_current_user`, but raises 303 with HX-Redirect when the
    user must change their password. Wrap every authed route except the
    change-password page + endpoint with this.

    Plan 18 (PC.6, 2026-05-17). Use `get_current_user` directly only for
    the /auth/change-password page + POST /api/v1/auth/change-password +
    POST /api/v1/auth/logout + GET /api/v1/auth/me. Every other authed
    route uses this.
    """
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Password change required.",
            headers={
                "HX-Redirect": "/auth/change-password",
                "Location": "/auth/change-password",
            },
        )
    return user


async def require_authed_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    naavik_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User | None:
    """Transitional auth dep for the plan-09 fake-session substrate.

    Plan 23 (PC.6a, 2026-05-18). Gates state-changing UI + API routes whose
    callers still send the fake-session cookie (`naavik_session=fake-1`)
    rather than a real JWT. Retires when the fake-session stub is deleted
    (post-Phase-2 task 2.12 / a real-auth migration). At that time:
    `Depends(require_authed_session)` → `Depends(require_password_complete)`.
    Also tighten `_user: User | None` -> `User` on dependent handlers because
    `require_password_complete` returns `User`, not `User | None`.

    Resolution order:
      1. Missing cookie → 401.
      2. Cookie equals `FAKE_SESSION_VALUE` → return None. No user resolution.
      3. Otherwise treat as JWT. On invalid/expired → 401. On valid → look
         up the user; if `must_change_password` is True, raise:
           - 307 + `HX-Redirect: /auth/change-password` for UI paths
             (anything NOT prefixed with `/api/v1/`).
           - 403 with `{"detail": "must change password"}` for API paths
             (prefix `/api/v1/`). API consumers shouldn't auto-follow a
             redirect to an HTML page.

    Routes that USE this dep accept `_user: User | None` because the
    fake-session path returns None; the handler body keeps reading
    `sample_data` accessors the same way it does today.
    """
    # Import inside the function to keep the fake-session constant a
    # single source of truth and avoid a top-of-file circular import.
    from ui.auth_stub import FAKE_SESSION_VALUE

    # Plan 75 / 0.3.3.22 (refined plan 0.7.0.39, 2026-05-21) — three surfaces:
    #   API (`/api/v1/*`)             → bare 401 (SDK consumers want 401)
    #   HTMX UI (HX-Request)          → 401 + `HX-Redirect: /login`
    #   Browser top-nav (neither)     → 307 + `Location: /login`
    # The 307 path is what makes `http://localhost:8003/` from a cookieless
    # browser land on `/login` instead of a JSON error page.
    is_htmx = request.headers.get("hx-request", "").lower() == "true"
    is_api = request.url.path.startswith("/api/v1/")

    def _raise_unauthenticated(detail: str) -> None:
        if is_api:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
            )
        if is_htmx:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
                headers={"HX-Redirect": "/login"},
            )
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail=detail,
            headers={"Location": "/login"},
        )

    if not naavik_session:
        _raise_unauthenticated("Not authenticated")

    # SECURITY (production hardening): the plan-09 `fake-1` cookie is a dev-only
    # bootstrap that maps every caller to the seeded owner (user_id=1). Honoring
    # it in production is a full authentication bypass — any request carrying
    # `Cookie: naavik_session=fake-1` gains owner access. Gate it behind
    # `settings.debug` (NAAVIK_DEBUG=1), which is already documented as dev-only
    # and loosens other guards (SECRET_KEY validator). Outside debug the fake
    # value is treated as an invalid session and rejected like any other.
    if naavik_session == FAKE_SESSION_VALUE:
        from config import settings as _app_settings

        if _app_settings.debug:
            return None
        _raise_unauthenticated("Not authenticated")

    result = await auth.verify_jwt_async(session, naavik_session)
    if result is None:
        _raise_unauthenticated("Session expired")
    user_id, jti, _ = result
    if await auth.is_jwt_revoked(session, jti=jti):
        _raise_unauthenticated("Session revoked")
    user = await auth.get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        _raise_unauthenticated("Account disabled")
    if user.must_change_password:
        # Path-based split per dispatch brief. `HX-Redirect` is set on
        # both branches so HTMX clients (which always set `HX-Request` and
        # may target either path) navigate the browser regardless. The
        # 403 vs 307 distinction matters for non-HTMX consumers (curl,
        # SDKs) that should not auto-follow a redirect to an HTML page.
        # `is_api` already resolved at the top of this dep for the 401
        # branch (plan 75 / 0.3.3.22).
        if is_api:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="must change password",
                headers={"HX-Redirect": "/auth/change-password"},
            )
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Password change required.",
            headers={
                "HX-Redirect": "/auth/change-password",
                "Location": "/auth/change-password",
            },
        )

    # Sidebar identity: prefer the profile's full name, fall back to the
    # email local-part. Read by base.html via `request.state` so every page
    # shows the real signed-in user (the sidebar used to hardcode the
    # sample-data owner's name for every account).
    display_name = user.email.split("@", 1)[0]
    try:
        from models import Profile as _Profile

        profile_name = (
            await session.exec(
                select(_Profile.full_name).where(
                    _Profile.user_id == user.id, _Profile.deleted_at.is_(None)
                )
            )
        ).one_or_none()
        if profile_name:
            display_name = profile_name
    except Exception:  # noqa: BLE001 — identity chrome must never 500 a page
        pass
    request.state.user_display_name = display_name
    return user


# ── Ownership guards (plan 91 Phase 1.4) ─────────────────────────────────


async def get_owned_contact(
    contact_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
) -> Contact:
    """Fetch a contact the caller owns, else 404 (same shape as a missing row —
    no cross-user existence oracle)."""
    from services import contact_tracker

    contact = await contact_tracker.get_contact(session, contact_id)
    if contact is None or contact.user_id != effective_user_id(user):
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


async def get_owned_bullet(
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
) -> Bullet:
    """Fetch a bullet the caller owns (bullet → experience → profile → user),
    else 404."""
    from services import profile_service

    uid = effective_user_id(user)
    if not await profile_service.owns_bullet(session, bullet_id=bullet_id, user_id=uid):
        raise HTTPException(status_code=404, detail="Bullet not found")
    bullet = await profile_service.get_bullet(session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return bullet


async def get_owned_application(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
) -> Application:
    """Fetch an application the caller owns, else 404."""
    from services import application_service

    application = await application_service.get_application(session, application_id)
    if application is None or application.user_id != effective_user_id(user):
        raise HTTPException(status_code=404, detail="Application not found")
    return application
