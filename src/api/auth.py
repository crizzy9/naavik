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
from models import User
from services.auth import (
    CSRF_COOKIE,
    JWT_TTL_DEFAULT,
    JWT_TTL_KEEP_SIGNED_IN,
    SESSION_COOKIE,
    authenticate,
    get_client_ip,
    get_current_user,
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
