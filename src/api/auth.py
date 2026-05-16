"""Real `/api/v1/auth/*` handlers — replaces plan-09 stubs in `ui/routes/auth.py`.

Wave 4 of plan 10 § B.3. Mounted under `/api/v1/auth` in `main.py`.
The HTML page handlers (`GET /login`, `GET /onboarding`) stay in
`ui/routes/auth.py` — only the JSON API endpoints move here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import Profile, Settings, User
from services.auth import (
    CSRF_COOKIE,
    JWT_TTL_DEFAULT,
    JWT_TTL_KEEP_SIGNED_IN,
    SESSION_COOKIE,
    authenticate,
    get_client_ip,
    get_current_user,
    get_user_by_email,
    hash_password,
    is_rate_limited,
    issue_csrf_token,
    issue_jwt,
    record_login_attempt,
    validate_csrf,
)

router = APIRouter(prefix="/api/v1/auth")


def _login_error_card(message: str, status_code: int) -> HTMLResponse:
    """Inline HTMX-swappable card for failed-login error."""
    safe = message.replace("<", "&lt;").replace(">", "&gt;")
    body = (
        '<div id="login-card" class="w-full max-w-[440px] bg-slate-900 border '
        'border-slate-800 rounded-xl p-7 shadow-2xl shadow-black/45">'
        '<div class="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 '
        f'text-rose-200 text-sm" role="alert">{safe}</div>'
        '<p class="mt-4 text-xs text-slate-500">'
        '<a href="/login" class="text-indigo-400 hover:text-indigo-300">'
        "← Back to sign in</a></p>"
        "</div>"
    )
    return HTMLResponse(content=body, status_code=status_code)


def _set_session_cookies(
    response: Response,
    *,
    jwt_value: str,
    csrf_value: str,
    keep_signed_in: bool,
    secure: bool = True,
) -> None:
    max_age_jwt = (
        int(JWT_TTL_KEEP_SIGNED_IN.total_seconds())
        if keep_signed_in
        else int(JWT_TTL_DEFAULT.total_seconds())
    )
    response.set_cookie(
        SESSION_COOKIE,
        jwt_value,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=max_age_jwt,
        path="/",
    )
    # CSRF cookie is NOT HttpOnly — JS reads it for the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_value,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=max_age_jwt,
        path="/",
    )


@router.post("/login", name="api_auth_login")
async def post_login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    keep_signed_in: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
):
    ip = get_client_ip(request)
    if is_rate_limited(ip):
        return _login_error_card(
            "Too many failed attempts. Try again in 15 minutes.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if not email or not password:
        return _login_error_card("Email and password are required.", 422)

    user = await authenticate(session, email, password)
    if user is None:
        record_login_attempt(ip, success=False)
        return _login_error_card("Invalid credentials. Try again.", 401)

    record_login_attempt(ip, success=True)
    user.last_login_at = _now()
    await session.commit()

    secure = not request.app.debug if hasattr(request.app, "debug") else True
    jwt_value = issue_jwt(user.id, keep_signed_in=bool(keep_signed_in))
    csrf_value = issue_csrf_token()

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/"
    _set_session_cookies(
        response,
        jwt_value=jwt_value,
        csrf_value=csrf_value,
        keep_signed_in=bool(keep_signed_in),
        secure=secure,
    )
    return response


@router.post("/logout", name="api_auth_logout")
async def post_logout(request: Request):
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/login"
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


# Plan 10b (item 4, 2026-05-03): minimum viable plaintext-password length.
# Real complexity rules (character classes, breached-password check) ship
# with PC.5 in ROADMAP § Pre-Phase-2 paper cuts.
_SIGNUP_MIN_PASSWORD_LEN = 8


@router.post("/signup", name="api_auth_signup")
async def post_signup(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    keep_signed_in: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
):
    """First-user bootstrap + multi-user signup (gated by Settings.allow_multiple_users).

    On a fresh DB (no User row) any signup succeeds and the new account is
    flagged `is_admin=True`. Once the first user exists, subsequent signups
    return 403 unless the admin opted into multi-user via Settings.
    """
    from sqlalchemy import func
    from sqlmodel import select

    ip = get_client_ip(request)
    if is_rate_limited(ip):
        return _login_error_card(
            "Too many attempts. Try again in 15 minutes.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if not email or not password:
        return _login_error_card("Email and password are required.", 422)

    if len(password) < _SIGNUP_MIN_PASSWORD_LEN:
        return _login_error_card(
            f"Password must be at least {_SIGNUP_MIN_PASSWORD_LEN} characters.",
            422,
        )

    norm_email = email.strip().lower()

    if "@" not in norm_email or "." not in norm_email.split("@", 1)[-1]:
        return _login_error_card("Enter a valid email address.", 422)

    # Single-user MVP guard: if any User exists, signup is gated by
    # Settings.allow_multiple_users on the existing instance Settings row.
    # `session.exec(select(func.count()))` under SQLModel returns a Row, not
    # the bare int — unwrap explicitly so the > 0 comparison works.
    count_row = (await session.exec(select(func.count()).select_from(User))).one()
    if hasattr(count_row, "_mapping"):
        # SQLAlchemy Row → first column.
        existing_count = int(count_row[0])
    elif isinstance(count_row, tuple):
        existing_count = int(count_row[0])
    else:
        existing_count = int(count_row)

    if existing_count > 0:
        # Query the single boolean column directly. Loading the full Settings
        # row via `select(Settings)` and reading the attribute hit a SQLAlchemy
        # "_key_not_found" KeyError on `allow_multiple_users` under the live
        # FastAPI worker (cached compiled SELECT did not pick up the freshly
        # migrated column). Scalar select sidesteps the cache + ORM mapping.
        allow_multi_scalar = await session.exec(
            select(Settings.allow_multiple_users).order_by(Settings.user_id).limit(1)
        )
        allow_multi = bool(allow_multi_scalar.one_or_none())
        if not allow_multi:
            record_login_attempt(ip, success=False)
            return _login_error_card(
                "Sign-ups are disabled on this instance (single-user MVP). "
                "Sign in with the existing account instead.",
                status.HTTP_403_FORBIDDEN,
            )

    if await get_user_by_email(session, norm_email) is not None:
        return _login_error_card(
            "Email already registered. Sign in instead.",
            status.HTTP_400_BAD_REQUEST,
        )

    is_first_user = existing_count == 0
    user = User(
        email=norm_email,
        password_hash=hash_password(password),
        is_active=True,
        is_admin=is_first_user,
    )
    session.add(user)
    await session.flush()

    # Default Settings + skeleton Profile so the rest of the UI doesn't trip
    # over a missing per-user singleton on the next page load.
    session.add(Settings(user_id=user.id))
    session.add(
        Profile(
            user_id=user.id,
            full_name=norm_email.split("@", 1)[0],
            headline="",
            email=norm_email,
        )
    )
    user.last_login_at = _now()
    await session.commit()

    record_login_attempt(ip, success=True)

    secure = not request.app.debug if hasattr(request.app, "debug") else True
    jwt_value = issue_jwt(user.id, keep_signed_in=bool(keep_signed_in))
    csrf_value = issue_csrf_token()

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/onboarding"
    _set_session_cookies(
        response,
        jwt_value=jwt_value,
        csrf_value=csrf_value,
        keep_signed_in=bool(keep_signed_in),
        secure=secure,
    )
    return response


@router.get("/me", name="api_auth_me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.get("/csrf", name="api_auth_csrf")
async def get_csrf(
    request: Request,
    naavik_csrf: str | None = Cookie(default=None, alias=CSRF_COOKIE),
):
    """Return current CSRF token, rotating when missing."""
    token = naavik_csrf or issue_csrf_token()
    response = Response(content=f'{{"csrf_token":"{token}"}}', media_type="application/json")
    if not naavik_csrf:
        secure = True
        response.set_cookie(
            CSRF_COOKIE,
            token,
            httponly=False,
            secure=secure,
            samesite="strict",
            path="/",
        )
    return response


def require_csrf(
    request: Request,
    naavik_csrf: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    """Reusable dependency for state-changing routes — validates double-submit."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if not validate_csrf(naavik_csrf, x_csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token invalid")


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
