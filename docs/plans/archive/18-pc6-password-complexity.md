---
Status: EXECUTED
Type: execution
Authored: 2026-05-17
Last updated: 2026-05-17
Depends on: plan 10b (signup endpoint), plan 10c (env-injected dev credential + signup-link UX), plan 17 (PC.5 — boot-time validator pattern)
GitHub: #8 (closed 2026-05-17 via PR #50)
Shipped: 2026-05-17 — PR #50 squash `7c7e12a` (initial `baad10c` + path-C re-loop `78c6d20`)
---

# 18 · PC.6 — Password complexity + must-change-on-first-login

## Goal

Reject weak passwords at every plaintext-entry surface (signup, password-change) with a single shared `validate_password_complexity()` helper in `src/services/auth.py` (min 12 chars · ≥ 1 ASCII letter · ≥ 1 ASCII digit). Add a `User.must_change_password: bool` column (default `False`); flip it `True` exactly when the seed flow generates a random dev password (no `NAAVIK_DEV_PASSWORD` env override). A flagged user can sign in, but `get_current_user` redirects every request to a new `/auth/change-password` page until they submit a complexity-passing replacement via the new `POST /api/v1/auth/change-password` endpoint, which clears the flag in the same transaction. Ships alembic `0003_user_must_change_password`, ~7 new tests (signup/change-password complexity, flag set on generated seed, redirect-when-flagged, clear-on-success, weak-replacement-rejected, env-supplied seed leaves flag off, complexity helper unit), and a tiny HTMX change-password page reusing the auth shell from plan 10c.

## Why

ROADMAP § Pre-Phase-2 paper cuts row PC.6 (`ROADMAP.md:264`): the signup endpoint today enforces only `len(password) >= 8` (`src/api/auth.py:153` + `:183-187`), a comment explicitly defers real rules to "PC.5" (stale — PR #49's PC.5 covered SECRET_KEY hardening, leaving password complexity for this plan). Worse, plan 10c's dev seed (`src/db/seed.py:109`) generates a 16-char alphanumeric secret + writes it to `~/.naavik/dev-credentials` (mode 0600) when `NAAVIK_DEBUG=1` + `NAAVIK_DEV_PASSWORD` unset + `SELF_HOSTED`. A self-hoster who follows the README to the letter never changes it; their production install keeps a server-generated dev secret as the admin's permanent password, sitting on disk in plaintext. The must-change flag closes that loop. This plan also satisfies plan 16 Phase 4 — the second `/build` paper cut after PC.5/plan 17, locking in the manager → architect → engineer → hacker → devops loop with a slightly more interesting shape (DB migration + cross-cutting middleware-shaped dependency + new HTMX page) than PC.5's single-file validator.

## Proposal

### A · `validate_password_complexity()` — single source of truth

New helper in `src/services/auth.py`, placed directly above `hash_password` at line 66 so it can short-circuit `hash_password` callers AND be import-tested standalone:

```python
# Plan 18 (PC.6, 2026-05-17): shared complexity validator. Called by every
# plaintext-entry path: POST /api/v1/auth/signup, POST /api/v1/auth/change-password,
# and (defensively) `hash_password` itself for any future caller. Rejects:
#   - < 12 chars total (count by chars, not bytes — see § B.4)
#   - no ASCII letter [A-Za-z]
#   - no ASCII digit [0-9]
# Returns the offending rule's user-facing message or None on pass.
PASSWORD_MIN_LENGTH = 12

def validate_password_complexity(plain: str) -> str | None:
    """Return None if `plain` meets PC.6 rules; else a user-facing error message.

    Caller renders the returned string in the `_login_error_card` HTMX swap or
    similar surface. Constant-time-ness is not relevant — these rules run on
    operator-typed plaintext, not on a credential that could leak via timing.
    """
    if not plain:
        return "Password must not be empty."
    if len(plain) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if not any("a" <= c.lower() <= "z" for c in plain):
        return "Password must contain at least one letter (a-z)."
    if not any("0" <= c <= "9" for c in plain):
        return "Password must contain at least one digit (0-9)."
    return None
```

`hash_password` (currently `src/services/auth.py:66-71`) **does NOT** call this helper. Reason: `hash_password` is invoked by the seed path with a generator-controlled plaintext that we know satisfies the rules (see § C); making `hash_password` enforce the rules would either break the seed (if we kept the current alphabet) or force us to thread a `skip_complexity_check=True` knob everywhere. Cleaner: every plaintext-entry route calls `validate_password_complexity(plain)` before `hash_password(plain)`. The plan also adds **one** safety belt: a separate `hash_password_with_complexity_check()` wrapper that the API endpoints use (see § D.2). Helps the linter catch any future hash-without-validate path.

### B · Decisions (option matrices)

#### B.1 — Storage of "must change password" flag

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **Boolean column `User.must_change_password`** | Simple persistence; one bool per row; flips atomically with password-change | One alembic migration; one model field | Trivial; mirrors `is_admin` shape | Future plans can add `password_changed_at: datetime` alongside if rotation policy lands | None — column trivial to drop |
| Derived from `created_at == last_login_at == NULL` + missing `password_changed_at` | No schema change | Brittle — requires adding `password_changed_at: datetime` column anyway, AND a "force flip on env-injected creds" override; reads like spaghetti | Bugs at every state-machine seam | Future authors will misread the heuristic | High — once UI surfaces "you must change", consumers depend on the flag |
| Per-session cookie `naavik_must_change=1` | No schema change | The flag dies when the session expires — flagged users escape it by clearing cookies + signing in again | Defeats the entire control | Same | High — invariant evaporates on session reset |

**Recommendation: dedicated boolean column.** Mirrors `User.is_admin` (`src/models/user.py:29`) which is already in use. Alembic 0003 is ~10 lines of `op.add_column`. The "derived from timestamps" option seems clever but ends up with more schema (still needs `password_changed_at`) AND a fragile derivation; cookie-based fails outright (forge-able + escapable). Trade-off accepted: a future "force every user to rotate after 90 days" feature would still need `password_changed_at`; we can add it then. The single boolean is the minimum honest representation.

#### B.2 — Where the flagged-user redirect happens (route dependency vs middleware vs per-route check)

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **Wrap `get_current_user` with `Depends(require_password_complete)` for HTMX + API routes** | The chokepoint already exists — `get_current_user` runs on every authed route. New dep checks `user.must_change_password` and raises an `HTTPException` with `HX-Redirect: /auth/change-password` header | Light — one new fn in `services/auth.py`; switch ~15 routes from `Depends(get_current_user)` → `Depends(require_password_complete)`; keep `get_current_user` for the change-password endpoint itself | Low — same dep pattern as everywhere else | One line per route; ruff catches misses | None — easy to flatten back |
| Starlette `BaseHTTPMiddleware` that inspects the JWT, fetches the user, and 302s | Catches every request without per-route opt-in | High — middleware needs DB session out-of-band (we have `engine` but no clean session-per-request middleware pattern today); doubles the user-lookup cost | Sessions opened in middleware without `await session.close()` leak | Future readers wonder why auth lives in two places | Middle — moving it later means re-doing the dep wiring |
| Per-route `if user.must_change_password: raise HTTPException(...)` | Most explicit | Highest — ~15 routes to touch; easy to forget the next new route | High — drift inevitable | Worst | None |

**Recommendation: dep wrapping.** FastAPI dependency injection is the canonical chokepoint; the codebase already routes every authed access through `get_current_user` (`src/services/auth.py:220`, used at `src/api/applications.py:33,65,84,127,155` + 9 other places per grep). New `require_password_complete(user: User = Depends(get_current_user))` raises `HTTPException(status_code=303, headers={"HX-Redirect": "/auth/change-password", "Location": "/auth/change-password"})`. The exemption list is exactly: `/auth/change-password` page (which uses bare `get_current_user`), `POST /api/v1/auth/change-password` (same), `POST /api/v1/auth/logout` (same), the static-file mount, `/api/health`. Everything else swaps to `require_password_complete`. Trade-off accepted: ~12 line-level changes in route signatures (find-replace `Depends(get_current_user)` → `Depends(require_password_complete)`). Middleware would centralize it in 1 place at the cost of a session-management headache the codebase doesn't have today.

#### B.3 — Scope: env-injected dev creds only, or any server-generated password?

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **Flag only the seed's `dev_password_source == "generated"` path** | Targets the actual operator surprise from PC.6 wording ("env-injected dev creds"); doesn't disrupt UX for operators who set `NAAVIK_DEV_PASSWORD` (env-supplied = operator-owned, per plan 10c § 10c.3a gate-2) | Smallest — one if-branch in seed | None | One source of truth | None |
| Also flag any password created by an admin invitation flow / random-password reset | Broader anti-pattern coverage | None of those code paths exist yet — speculative scope | Adds policy code with no consumer; will drift before it ships | Higher | Lower |
| Flag every password change including admin-set values, *and* every signup | Strictest | Breaks signup UX — user creates account, immediately forced to change password | High — defeats user trust | Higher | Higher |

**Recommendation: option 1, narrowly scoped to the seed-generated path.** ROADMAP's PC.6 wording specifically says "env-injected dev creds" — i.e. the credential the operator did NOT pick. The plan-10c gate-1 ("dev_password_source == 'generated'") already encodes this distinction. Signup-created passwords have just passed `validate_password_complexity()`, so they're already strong; forcing a change-on-first-login on a brand-new account would be theater. Trade-off accepted: a future admin-invitation flow (Phase 2+, multi-user) will need to opt into this flag itself. That plan can extend the policy then; we're not pre-paving for code that doesn't exist.

#### B.4 — "Letter" and "digit" precision under Unicode

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **ASCII-only: `[A-Za-z]` for letter, `[0-9]` for digit** | Aligns with what `secrets.token_urlsafe` + a typical password manager generate; predictable error text | None | Minor — Hindi/CJK-only passwords get rejected (very rare for an open-source dev tool); easy to add later | Lowest | None |
| Unicode `str.isalpha()` + `str.isdigit()` | Accepts `पासवर्ड1` and `пароль1` | None | `'1'.isdigit() == True` AND `'\u0660'.isdigit() == True` — Arabic-Indic digits silently pass, which is fine but inconsistent with HMAC tooling everywhere else | Middle | Low |
| Unicode `str.isalpha()` + ASCII `[0-9]` only | Mixed precedent | Lowest | Inconsistent message → user confusion | Middle | Low |

**Recommendation: ASCII-only.** The bcrypt key derivation operates on UTF-8 bytes either way; restricting to ASCII for the rule check just constrains the operator's password space slightly, but the constraint matches the implicit assumption every other open-source self-hosted tool ships (Bitwarden, Vaultwarden, Authentik defaults). Importantly, length is checked by **char count** (`len(plain)`), not byte count — a 12-character Hindi password like `पासवर्ड12345` has 12 chars but ~36 UTF-8 bytes, and would pass the length check. Trade-off accepted: a user who types a password of all Cyrillic letters + ASCII digits passes (good — digit is present), but a user who types all Cyrillic letters + Devanagari digits fails our check despite each being a "letter" and a "digit" semantically. We can liberalize in a future plan once a real user complaint surfaces. The validator's error string says "letter (a-z)" and "digit (0-9)" explicitly so the rejection is self-documenting.

#### B.5 — Seed-time validation of `NAAVIK_DEV_PASSWORD`

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **Allow weak `NAAVIK_DEV_PASSWORD`; do NOT set the flag (operator-owned)** | Mirrors plan 10c § 10c.3a gate-2 ("env-supplied passwords are owned by the operator; never echo them back to disk") + does not invent policy the user didn't sign up for | None | Operator may set `NAAVIK_DEV_PASSWORD=test` for CI convenience and ship a weak dev DB to a public instance — but this is debug-mode-only and they already chose the value | Same | None |
| Reject weak `NAAVIK_DEV_PASSWORD` at seed time | Forces strong dev passwords too | Surprises CI configs already pinned to short strings (e.g. `test_seeded_user_password_hash_is_real_bcrypt` reads `NAAVIK_DEV_PASSWORD`); ripples through `tests/test_seed.py:131` | Higher — breaks the CI test that ships today | Same | Same |
| Reject weak; ALSO set the must-change flag | Strictest | Same CI breakage + redundant — if it's strong, no flag needed; if weak, rejected before set | Highest | Same | Same |

**Recommendation: option 1.** PC.6's wording targets "env-injected dev creds" — but plan 10c established a clear semantic: env-supplied = operator chose, generated = naavik picked for them. We honor it. CI's existing `NAAVIK_DEV_PASSWORD=test-stable-pw` (16 chars, has digit, has letter — passes complexity anyway, but the principle holds) stays working. The new must-change flag fires only when `dev_password_source == "generated"`. Trade-off accepted: if an operator sets `NAAVIK_DEV_PASSWORD=pwd` for a one-off reproduction, signs in, and forgets to clear the env var before going to prod, they've still chosen that value; not our policy problem.

#### B.6 — Change-password endpoint location: REST under `/api/v1/auth/` vs UI route

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **`POST /api/v1/auth/change-password` (REST) + `GET /auth/change-password` (HTMX page)** | Mirrors signup shape: page handler in `src/ui/routes/auth.py`, JSON-ish endpoint in `src/api/auth.py` | Two routes, but they parallel `GET /login` + `POST /api/v1/auth/login` exactly | None | Conventional | None |
| Single HTMX route `POST /auth/change-password` that returns the next-step HTML | Fewer files | Diverges from the signup/login pattern | Inconsistent surface for future tooling | Higher | Middle |
| CLI: `naavik change-password` | — | **FORBIDDEN** by AGENTS.md § Key Conventions § CLI (sunset track per ROADMAP § Phase 2 task 2.11) | — | — | — |

**Recommendation: option 1, matching the existing pattern.** `GET /auth/change-password` (page) lives in `src/ui/routes/auth.py` next to `get_login`; `POST /api/v1/auth/change-password` (form-encoded) lives in `src/api/auth.py` next to `post_login`. The form submits via HTMX, swapping `#change-password-card` (mirror of the `#login-card` pattern). On success, the response is `204 + HX-Redirect: /`. The CLI option is explicitly listed only to make the rejection unambiguous — and to remind reviewers that the `architect-sunset-guard` skill rejects it on sight. Trade-off accepted: two files touched instead of one. The pattern parity is worth it for engineer's read-it-and-write-the-diff speed.

### C · File-by-file edits

#### C.1 · `src/models/user.py` — add the flag

Before line 28 (`is_active: bool = ...`), add:

```python
    # Plan 18 (PC.6, 2026-05-17): set True at seed time when the dev password
    # is server-generated (no NAAVIK_DEV_PASSWORD override). Cleared on the
    # first successful POST /api/v1/auth/change-password that satisfies
    # services.auth.validate_password_complexity. While True,
    # services.auth.require_password_complete redirects every authed request
    # to /auth/change-password.
    must_change_password: bool = Field(default=False)
```

Update the module docstring's "Per DATA_MODEL.md § C `User`" line to add a parenthetical: `(plan 18 adds must_change_password — DATA_MODEL.md will sync in plan 11+ when the User entity is next touched)`. We do NOT update `docs/design/DATA_MODEL.md` in this plan — single-doc tracking + the model definition's docstring is authoritative for engineer.

#### C.2 · `migrations/versions/0003_user_must_change_password.py` — new revision

```python
"""user.must_change_password — PC.6 first-login forced rotation.

Revision ID: 0003_user_must_change_pw
Revises: 0002_settings_multi_users
Create Date: 2026-05-17

Plan 18 (PC.6): boolean flag on User. Set True at seed time when the dev
password is server-generated; cleared by POST /api/v1/auth/change-password
on the first complexity-passing replacement.

Revision id intentionally short — Alembic stores version_num in varchar(32)
by default (see plan 10b's 0002 for the same constraint).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_must_change_pw"
down_revision: Union[str, None] = "0002_settings_multi_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "must_change_password")
```

Alembic head jumps from `0002_settings_multi_users` → `0003_user_must_change_pw`. The `server_default=sa.false()` is load-bearing: existing User rows in production DBs receive `must_change_password=False` automatically, so no existing operator gets locked out of their instance on next `alembic upgrade head`.

#### C.3 · `src/services/auth.py` — validator + new dependency + safety belt

**Three additions** to this file:

1. **`validate_password_complexity()`** — per § A above. Placed at line 49 (between the `_login_attempts` dict and the existing `# ── Password hashing ─` comment).

2. **`hash_password_with_complexity_check()`** safety belt — placed directly after `hash_password` (currently lines 66-71):

```python
def hash_password_with_complexity_check(plain: str) -> str:
    """`hash_password` after validating complexity. The canonical entry
    point for the auth API; bare `hash_password` is reserved for the seed
    path (which generates passwords that satisfy the rules by construction)
    and for tests that need to inject known weak hashes.
    """
    err = validate_password_complexity(plain)
    if err is not None:
        raise ValueError(err)
    return hash_password(plain)
```

The `ValueError` is intentional — the caller (`post_signup` / `post_change_password`) catches it and renders the message in the HTMX swap. Letting it bubble out as `ValueError` (not `HTTPException`) keeps the validator pure-Python testable.

3. **`require_password_complete()`** dependency — placed directly after `get_current_user` (currently lines 220-234):

```python
async def require_password_complete(
    user: User = Depends(get_current_user),
) -> User:
    """Like `get_current_user`, but raises 303 with HX-Redirect when the
    user must change their password. Wrap every authed route except the
    change-password page + endpoint with this.

    Plan 18 (PC.6, 2026-05-17). Use `get_current_user` directly only for
    the /auth/change-password page + POST /api/v1/auth/change-password +
    POST /api/v1/auth/logout. Every other authed route uses this.
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
```

303 (See Other) is chosen over 302/307 because the semantic is "your request was understood, but you need to GET this other resource first" — RFC 7231 § 6.4.4. HTMX honors `HX-Redirect` regardless of status code for HTMX-initiated requests; for browser-initiated (page load) requests, the `Location` header lets the browser follow the redirect. Both are sent.

#### C.4 · `src/api/auth.py` — wire the validator + add change-password

**Three edits:**

1. **Delete** lines 150-153 (the `# Plan 10b (item 4)...` comment + `_SIGNUP_MIN_PASSWORD_LEN = 8`).

2. **Replace** lines 183-187 (the current `len(password) < _SIGNUP_MIN_PASSWORD_LEN` check) with:

```python
    complexity_err = validate_password_complexity(password)
    if complexity_err is not None:
        return _login_error_card(complexity_err, 422)
```

Import: add `validate_password_complexity` to the existing `from services.auth import (...)` block (line 28).

3. **Add** new endpoint `post_change_password`, placed directly after `post_signup` (currently ends at line 270):

```python
@router.post("/change-password", name="api_auth_change_password")
async def post_change_password(
    request: Request,
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Change-password endpoint. Re-verifies current password (defense in
    depth — even though `get_current_user` already validated the JWT, this
    pins the operation to a live cred-presenting actor). Validates the new
    password against PC.6 complexity rules. On success, clears
    `User.must_change_password` and updates `password_hash` atomically.

    Returns 204 + HX-Redirect: / on success (mirror of /login + /signup).
    Returns 422/400 + `_login_error_card` HTMX swap on validation failure.
    """
    from services.auth import hash_password_with_complexity_check, verify_password

    ip = get_client_ip(request)
    if is_rate_limited(ip):
        return _login_error_card(
            "Too many attempts. Try again in 15 minutes.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if not verify_password(current_password, user.password_hash):
        record_login_attempt(ip, success=False)
        return _login_error_card("Current password is incorrect.", 422)

    try:
        new_hash = hash_password_with_complexity_check(new_password)
    except ValueError as exc:
        return _login_error_card(str(exc), 422)

    if new_password == current_password:
        return _login_error_card(
            "New password must differ from your current password.",
            422,
        )

    user.password_hash = new_hash
    user.must_change_password = False
    await session.commit()
    record_login_attempt(ip, success=True)

    # Rotate session + CSRF cookies on credential change (auth event).
    secure = not request.app.debug if hasattr(request.app, "debug") else True
    jwt_value = issue_jwt(user.id, keep_signed_in=False)
    csrf_value = issue_csrf_token()

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/"
    _set_session_cookies(
        response,
        jwt_value=jwt_value,
        csrf_value=csrf_value,
        keep_signed_in=False,
        secure=secure,
    )
    return response
```

Cookie rotation on password change matches the `services.auth` module docstring (`src/services/auth.py:12-13`: "Rotated on auth events (login / logout / password change)") — the existing code rotates on login + logout but had no path to rotate on password change because there WAS no change-password endpoint.

#### C.5 · `src/ui/routes/auth.py` — `GET /auth/change-password` page

After `get_onboarding` (currently ends around line 109), add:

```python
@router.get("/auth/change-password", response_class=HTMLResponse, name="change_password_page")
async def get_change_password(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Plan 18 (PC.6, 2026-05-17): forced-rotation page. Reached when the
    user's `must_change_password` flag is True. The page renders even when
    the flag is False (so an operator can change their password
    voluntarily); the must-change banner appears only when flagged.
    """
    return templates.TemplateResponse(
        request,
        "pages/change_password.html",
        {
            "active_sidebar": None,
            "active_template_path": "/auth/change-password",
            "must_change": user.must_change_password,
            "email": user.email,
        },
    )
```

Import `get_current_user` and `User` (these are not yet imported in this file — add to the import block at the top).

#### C.6 · `src/ui/templates/pages/change_password.html` — new HTMX page

Reuse the auth-shell layout from `login.html`. Structure:

```jinja
{% extends "components/auth_shell.html" %}
{% block title %}Change password — Naavik{% endblock %}

{% block caller %}
<div id="change-password-card" class="w-full max-w-[440px] bg-slate-900 border border-slate-800 rounded-xl p-7 shadow-2xl shadow-black/45">
  {# header — Naavik logo + heading (copy from login.html lines 9-17) #}
  <div class="flex items-center gap-3 mb-6">
    {# lucide circle-compass logo — copy from login.html #}
  </div>

  {% if must_change %}
  <div class="mb-5 rounded-lg bg-amber-500/10 border border-amber-500/30 p-4">
    <div class="flex gap-3 items-start">
      <i data-lucide="key-round" class="h-5 w-5 text-amber-300 shrink-0" stroke-width="1.5"></i>
      <div class="flex-1 min-w-0">
        <h3 class="text-sm font-medium text-amber-100">Change your password to continue.</h3>
        <p class="text-xs text-amber-200/80 mt-1">
          You're signed in with a server-generated dev password. Pick a new
          one (12+ characters, with at least one letter and one digit) before
          continuing.
        </p>
      </div>
    </div>
  </div>
  {% endif %}

  <h1 class="text-2xl font-semibold text-slate-50 tracking-tight">
    {% if must_change %}Set a new password{% else %}Change password{% endif %}
  </h1>
  <p class="mt-1.5 text-sm text-slate-400">Signed in as <span class="text-slate-200">{{ email }}</span>.</p>

  <form class="mt-6 flex flex-col gap-4"
        hx-post="/api/v1/auth/change-password"
        hx-target="#change-password-card"
        hx-swap="outerHTML"
        hx-disabled-elt="find button[type=submit]">
    <div>
      {% with label="CURRENT PASSWORD", for_id="cp-current" %}{% include "components/field_label.html" %}{% endwith %}
      {% with name="current_password", type="password", id="cp-current", required=true, autocomplete="current-password" %}
        {% include "components/input.html" %}
      {% endwith %}
    </div>
    <div>
      {% with label="NEW PASSWORD", for_id="cp-new" %}{% include "components/field_label.html" %}{% endwith %}
      {% with name="new_password", type="password", id="cp-new", required=true, autocomplete="new-password" %}
        {% include "components/input.html" %}
      {% endwith %}
      <p class="mt-1.5 text-xs text-slate-500">At least 12 characters with a letter and a digit.</p>
    </div>

    <button type="submit" class="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-white font-medium text-sm transition focus:outline-none focus:ring-2 focus:ring-indigo-500/40 disabled:opacity-50 disabled:cursor-not-allowed">
      <span class="htmx-show-loading hidden">{% include "components/spinner.html" %}</span>
      <span class="htmx-hide-loading">Change password</span>
    </button>

    {% if not must_change %}
    <p class="mt-1 text-center text-sm text-slate-400">
      <a href="/" class="text-indigo-300 hover:text-indigo-200 font-medium transition">← Back to Overview</a>
    </p>
    {% endif %}
  </form>
</div>
{% endblock %}
```

Lucide icon (`key-round`) — already approved per DESIGN.md (`docs/design/COMPONENTS.md` § Iconography). Tailwind classes mirror `login.html` exactly so visual parity with the existing auth shell is preserved.

#### C.7 · `src/db/seed.py` — flip `must_change_password` on generated path

The fresh-user branch is currently `lines 229-237` of `src/db/seed.py`:

```python
        for sql_cls, rows, pk_cols in _TABLE_ORDER:
            if sql_cls is User and not user_existed:
                # Fresh DB — inject the real bcrypt hash before insert.
                count = await _seed_one(
                    session,
                    sql_cls,
                    rows,
                    pk_cols,
                    overrides={"password_hash": hash_password(dev_password)},
                )
            else:
                count = await _seed_one(session, sql_cls, rows, pk_cols)
```

Replace `overrides={"password_hash": hash_password(dev_password)},` with:

```python
                    overrides={
                        "password_hash": hash_password(dev_password),
                        # Plan 18 (PC.6, 2026-05-17): server-generated dev
                        # credential forces a change on first login. Env-
                        # supplied creds are operator-owned (matches
                        # plan 10c's "echo to disk" gate-2 logic).
                        "must_change_password": dev_password_source == "generated",
                    },
```

`dev_password_source` is already in scope at this line via line 220 (`dev_password, dev_password_source = _resolve_dev_password()`).

**Important:** `src/db/sample_data.py` (Phase 1 fixture for `USER`) does NOT set `must_change_password`. The override path above injects it for the seed insert. For tests that import the shadow model directly without going through `_seed_one`, the default value (`False`) flows through Pydantic — see § D.4 for the test that pins this.

#### C.8 · Route signatures: swap `get_current_user` → `require_password_complete`

Find-replace across the codebase (engineer to confirm via ruff after):

```
src/api/applications.py:33    Depends(get_current_user) → Depends(require_password_complete)
src/api/applications.py:65    Depends(get_current_user) → Depends(require_password_complete)
src/api/applications.py:84    Depends(get_current_user) → Depends(require_password_complete)
src/api/applications.py:127   Depends(get_current_user) → Depends(require_password_complete)
src/api/applications.py:155   Depends(get_current_user) → Depends(require_password_complete)
src/api/profile.py:*          (audit: every endpoint)
src/api/settings.py:*         (audit: every endpoint)
src/api/portfolio.py:*        (portfolio is no-auth — DO NOT TOUCH)
src/ui/routes/overview.py:*   (audit: every endpoint EXCEPT static / health)
src/ui/routes/profile.py:*    (audit)
src/ui/routes/discover.py:*   (audit)
src/ui/routes/tracking.py:*   (audit)
src/ui/routes/outreach.py:*   (audit)
src/ui/routes/settings.py:*   (audit)
src/ui/routes/fragments.py:*  (audit)
src/ui/routes/integrations.py:* (audit)
src/ui/routes/email.py:*      (audit)
src/ui/routes/design.py:*     (audit — but its endpoints are env-gated, not user-gated)
```

**Routes that MUST stay on bare `get_current_user`** (exemption list):

```
src/api/auth.py:get_me                              — change-password page needs /me; user resolution must not 303
src/api/auth.py:post_change_password (new)          — the endpoint that clears the flag
src/api/auth.py:post_logout                         — logout must work even if must-change
src/ui/routes/auth.py:get_change_password (new)     — the page that lets the user change
```

The find-replace is mechanical; engineer runs `grep -rn "Depends(get_current_user)" src/` after the rewrite to verify only the four exempt endpoints remain.

#### C.9 · `src/api/auth.py` — `post_login` post-success redirect

After line 138 (`return response`), no change is required: the existing `HX-Redirect: /` will be intercepted at the next page-load by `require_password_complete` because the `must_change_password=True` user hitting `/` will 303 to `/auth/change-password`. **Sequence:** login → HX-Redirect to `/` → browser GET `/` → `require_password_complete` raises 303 → browser follows to `/auth/change-password` → user changes → HX-Redirect to `/` → succeeds.

This means engineer doesn't add a login-side check. The redirect happens automatically via the dependency. The plan-level test in § D.6 verifies this end-to-end.

#### C.10 · `tests/test_auth.py` — extend with complexity tests

Add to the bottom of the file:

```python
# ── Plan 18 (PC.6) — password complexity validator ──────────────────────


def test_validate_password_complexity_passes_strong():
    from services.auth import validate_password_complexity
    assert validate_password_complexity("StrongPass123") is None
    assert validate_password_complexity("a" * 12 + "1") is None


def test_validate_password_complexity_fails_too_short():
    from services.auth import validate_password_complexity
    msg = validate_password_complexity("abc123")
    assert msg is not None
    assert "12" in msg


def test_validate_password_complexity_fails_no_digit():
    from services.auth import validate_password_complexity
    msg = validate_password_complexity("abcdefghijklmn")
    assert msg is not None
    assert "digit" in msg.lower()


def test_validate_password_complexity_fails_no_letter():
    from services.auth import validate_password_complexity
    msg = validate_password_complexity("123456789012345")
    assert msg is not None
    assert "letter" in msg.lower()


def test_validate_password_complexity_empty():
    from services.auth import validate_password_complexity
    msg = validate_password_complexity("")
    assert msg is not None


def test_hash_password_with_complexity_check_rejects_weak():
    import pytest
    from services.auth import hash_password_with_complexity_check
    with pytest.raises(ValueError) as exc:
        hash_password_with_complexity_check("short")
    assert "12" in str(exc.value)


def test_hash_password_with_complexity_check_accepts_strong():
    from services.auth import hash_password_with_complexity_check
    h = hash_password_with_complexity_check("StrongPass123")
    assert h.startswith("$2b$")
```

#### C.11 · `tests/test_pages.py` — change-password page renders

Add:

```python
def test_change_password_page_renders_with_banner_when_flagged(client: TestClient, monkeypatch):
    """When the user is flagged must_change_password=True, the page shows
    the amber must-change banner."""
    # The fake-session middleware uses `FAKE_SESSION_VALUE` already; we
    # monkeypatch the dependency to return a flagged user object.
    from src.services import auth as auth_svc
    from src.models import User
    async def _fake(*args, **kwargs):
        return User(
            id=1,
            email="dev@local",
            password_hash="$2b$04$placeholder",
            is_active=True,
            is_admin=True,
            must_change_password=True,
        )
    monkeypatch.setattr(auth_svc, "get_current_user", _fake)
    r = client.get("/auth/change-password")
    assert r.status_code == 200
    body = r.text
    assert "Change your password to continue" in body
    assert 'hx-post="/api/v1/auth/change-password"' in body
    assert "data-lucide=\"key-round\"" in body


def test_change_password_page_no_banner_when_not_flagged(client: TestClient, monkeypatch):
    from src.services import auth as auth_svc
    from src.models import User
    async def _fake(*args, **kwargs):
        return User(
            id=1, email="dev@local", password_hash="$2b$04$x",
            is_active=True, is_admin=True, must_change_password=False,
        )
    monkeypatch.setattr(auth_svc, "get_current_user", _fake)
    r = client.get("/auth/change-password")
    assert r.status_code == 200
    body = r.text
    assert "Change your password to continue" not in body
    assert "← Back to Overview" in body
```

Note: the existing `tests/test_pages.py` uses a fake-session pattern (see `src/ui/auth_stub.py:FAKE_SESSION_VALUE` referenced at `src/ui/routes/auth.py:27`). The monkeypatch approach above is the cleanest way to inject a `must_change_password=True` user without spinning up a real DB. Engineer to verify the existing client fixture works against the new route; if not, fall back to the route's TestClient + dependency-override pattern.

#### C.12 · `tests/test_seed.py` — flag set on generated, cleared on env

Add to the `Plan 18 (PC.6)` section at the bottom:

```python
# ── Plan 18 (PC.6) — must-change flag on generated dev password ─────────


async def test_seed_sets_must_change_password_when_generated(monkeypatch, tmp_path):
    """When `dev_password_source == "generated"`, the seeded User row gets
    `must_change_password=True`. Plan 18 (PC.6, 2026-05-17).
    """
    from sqlalchemy import text
    from config import settings as app_settings
    from db import seed as seed_mod

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_settings, "debug", True)
    monkeypatch.delenv("NAAVIK_DEV_PASSWORD", raising=False)

    sm, engine = _fresh_session()
    async with sm() as session:
        await session.execute(text('TRUNCATE TABLE "user" RESTART IDENTITY CASCADE'))
        await session.commit()
    await engine.dispose()

    await seed_mod.seed()

    sm2, engine2 = _fresh_session()
    async with sm2() as session:
        user = (await session.scalars(select(User).where(User.id == 1))).first()
        assert user is not None
        assert user.must_change_password is True
    await engine2.dispose()


async def test_seed_leaves_must_change_unset_when_env_supplied(monkeypatch, tmp_path):
    """When `NAAVIK_DEV_PASSWORD` is exported, the seeded User row gets
    `must_change_password=False` (env-supplied creds are operator-owned).
    Plan 18 (PC.6, 2026-05-17).
    """
    from sqlalchemy import text
    from config import settings as app_settings
    from db import seed as seed_mod

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_settings, "debug", True)
    monkeypatch.setenv("NAAVIK_DEV_PASSWORD", "OperatorPicked1234")

    sm, engine = _fresh_session()
    async with sm() as session:
        await session.execute(text('TRUNCATE TABLE "user" RESTART IDENTITY CASCADE'))
        await session.commit()
    await engine.dispose()

    await seed_mod.seed()

    sm2, engine2 = _fresh_session()
    async with sm2() as session:
        user = (await session.scalars(select(User).where(User.id == 1))).first()
        assert user is not None
        assert user.must_change_password is False
    await engine2.dispose()
```

Both tests are live-DB-gated via the file's existing `pytestmark = pytest.mark.skipif(not _LIVE, ...)` at line 35. Engineer runs them under `NAAVIK_LIVE_DB=1 uv run pytest tests/test_seed.py`.

#### C.13 · `src/ui/templates/pages/login.html` — bump the hint text

Line 67: `<p class="mt-1.5 text-xs text-slate-500">At least 8 characters.</p>` → `<p class="mt-1.5 text-xs text-slate-500">At least 12 characters, with a letter and a digit.</p>`.

One-line change. The form submits to the existing `/api/v1/auth/signup`; the server enforces the rules and renders the per-rule error message into `#login-card` on failure.

### D · Build sequence

1. **Read** `src/services/auth.py:1-244` (full file), `src/api/auth.py:1-321` (full file), `src/db/seed.py:1-308` (full file), `src/models/user.py:1-47`, `migrations/versions/0002_settings_multi_users.py:1-45`.
2. **Edit** `src/models/user.py` — add `must_change_password` field.
3. **Create** `migrations/versions/0003_user_must_change_password.py`.
4. **Run** `uv run alembic upgrade head` against the dev DB; verify column added.
5. **Edit** `src/services/auth.py` — add `validate_password_complexity`, `hash_password_with_complexity_check`, `require_password_complete`.
6. **Edit** `src/api/auth.py` — wire complexity check into `post_signup`; add `post_change_password`.
7. **Edit** `src/ui/routes/auth.py` — add `get_change_password` page handler.
8. **Create** `src/ui/templates/pages/change_password.html`.
9. **Edit** `src/db/seed.py` — flip `must_change_password` in the override dict.
10. **Edit** `src/ui/templates/pages/login.html` — bump hint text to 12 chars.
11. **Find-replace** `Depends(get_current_user)` → `Depends(require_password_complete)` per § C.8; preserve exemption list.
12. **Add** `tests/test_auth.py` extension (7 tests per § C.10).
13. **Add** `tests/test_pages.py` extension (2 tests per § C.11).
14. **Add** `tests/test_seed.py` extension (2 tests per § C.12; live-DB-gated).
15. **Run quality gates** via `devops-build-gates` skill:
    ```bash
    uv run ruff check .
    uv run ruff format --check .
    uv run pytest -x
    NAAVIK_LIVE_DB=1 uv run pytest tests/test_seed.py -x
    ```
16. **Manual QA** via `engineer-manual-qa-gate` skill (see § F).
17. **Mark ROADMAP row PC.6 `[x]`**, add deliverable note pointing at the archived plan.

### E · Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Find-replace at § C.8 misses a route → user gets to an authed page without rotating | MEDIUM | Defeats the entire control for the missed route | After replace, `grep -rn "Depends(get_current_user)" src/` MUST return exactly four matches — the exemption list. Engineer commits the grep output into the PR description. |
| Find-replace HITS an exempt route → flagged user can't reach change-password | MEDIUM | Infinite-redirect or 303 loop on the change-password page itself | Same grep. The four exempt routes are named in § C.8. The plan-level test in § C.11 (`test_change_password_page_renders_with_banner_when_flagged`) catches this — if the page wraps with `require_password_complete`, the test 303s instead of returning 200. |
| Existing users in production DBs end up flagged after `alembic upgrade head` | LOW | Everyone has to rotate; surprises operators | Migration `server_default=sa.false()` (§ C.2) writes `False` to every existing row. New users created via signup also default to `False` (model field default). Only the seed-generated path flips True. |
| `verify_password(current_password, user.password_hash)` inside `post_change_password` against the seeded dev password — does the operator know it? | MEDIUM | UX friction — operator has to fish the credential out of `~/.naavik/dev-credentials` or scrollback | Plan 10c already established `cat ~/.naavik/dev-credentials` as the canonical recovery path; the must-change banner text could mention it. Plan-level decision: keep the banner text generic ("server-generated dev password"); a follow-up `## Deviations` may add a "find your current password at `~/.naavik/dev-credentials`" line to the banner if user testing shows confusion. |
| Find-replace breaks the `/api/portfolio/cv` public endpoint (the only no-auth API) | LOW | Portfolio sync starts demanding auth | `src/api/portfolio.py` uses no auth dependency today — verified at planning time; the find-replace pattern `Depends(get_current_user)` doesn't match `src/api/portfolio.py`. Plan § C.8 names this exemption explicitly. |
| New `change_password.html` template lacks `data-lucide` icon initialization | LOW | Icon doesn't render; page looks broken | The auth-shell layout already wires `lucide.createIcons()` in `base.html` (per the existing login flow); the new template reuses the same `data-lucide="key-round"` pattern. |
| Test `test_change_password_page_renders_with_banner_when_flagged` monkeypatches `get_current_user` — but the dep injection might resolve from a different module path | MEDIUM | Test silently passes by hitting the unmonkeypatched dep | The test imports from `services.auth` (the original module); FastAPI dependency injection caches by callable identity, so monkeypatching the module attribute won't affect already-resolved deps. Fallback: use FastAPI's `app.dependency_overrides[get_current_user] = _fake` pattern. Engineer to verify which pattern test fixtures already use; the existing `test_login_signup_mode_renders_form_on_fresh_db` (`tests/test_pages.py:209`) monkeypatches `auth_routes._compute_signup_disabled` successfully — same shape should work for the dep. |
| Login + signup endpoints already invoke `hash_password` directly — should they switch to `hash_password_with_complexity_check`? | CERTAIN (correct) | Without the swap, signup's complexity check happens BEFORE `hash_password` (the validator runs in `post_signup` already; OK), but a defense-in-depth refactor would call `hash_password_with_complexity_check` to eliminate ordering risk | Signup's `hash_password(password)` call at `src/api/auth.py:234` runs AFTER the new `validate_password_complexity` check at § C.4 step 2. Engineer's choice: belt-and-suspenders swap of `hash_password` → `hash_password_with_complexity_check` at the signup site is +1 line and 0 cost. The change-password endpoint already uses `hash_password_with_complexity_check`. Recommendation: yes, swap at signup too. |
| Migration revision id collides with a future plan that picks `0003_` | LOW | Alembic refuses to upgrade | Standard alembic conflict resolution: rename + bump. `0003_user_must_change_pw` is the descriptive-but-short slug (consistent with `0002_settings_multi_users` short-id convention noted in 0002's docstring). |
| Operational artifact: a new HTML page lives at `/auth/change-password` — but the route prefix is NOT under `/api/v1/`; URL collision with onboarding's `?step=2` flow? | LOW | None — different URL | `/auth/change-password` is a fresh path; the existing onboarding lives at `/onboarding`; the existing login lives at `/login`. No collision. Engineer to verify the FastAPI router mounts in `main.py` don't re-prefix `/auth/`. |
| Plan 10c's `dev-credentials` file persists the OLD password after the user rotates | LOW | The file becomes stale and misleading (a `cat ~/.naavik/dev-credentials` after rotation shows the wrong credential) | Out-of-scope for PC.6; surfaces only after rotation. Two clean options for a follow-up plan: (a) delete the file on `must_change_password` flip-to-False inside `post_change_password`; (b) prepend a `# STALE — rotated YYYY-MM-DD` line. Option (a) is cleaner. **Plan-level decision: defer to a `## Deviations from plan` follow-up note** — if engineer ships it inline, great; if not, file a follow-up paper cut. |

### F · Manual QA gate

Engineer runs per `engineer-manual-qa-gate` skill § "Auth + middleware-shaped dependencies". Four reproductions:

```bash
# 1. Weak password rejected at signup (fresh DB).
#    Reset .naavik/db, start nix run .#dev, visit /login?mode=signup,
#    submit email + "short" → expect inline 422 with "12 characters" message.

# 2. Weak password rejected at change-password.
#    Sign in as the seeded dev user (must_change_password=True), follow the
#    303 to /auth/change-password, submit current + "short" → expect inline
#    422 with the same message.

# 3. Strong password succeeds; flag clears; redirect to /.
#    Same flow, submit current + "StrongerThanThat1" → expect 204 +
#    HX-Redirect:/. Browser lands on Overview.

# 4. Generated-seed user is flagged.
#    On a fresh seed (rm -rf .naavik/, nix run .#dev with NAAVIK_DEV_PASSWORD
#    UNSET), sign in via the credential at ~/.naavik/dev-credentials. Expect
#    immediate 303 to /auth/change-password on the next page load.

# 5. Env-supplied seed is NOT flagged.
#    NAAVIK_DEV_PASSWORD=OperatorPicked1234 nix run .#dev (after fresh wipe).
#    Sign in. Expect landing on Overview without redirect.
```

Capture the five outcomes verbatim into engineer's hand-back's `manual QA:` block. Per `engineer-manual-qa-gate` skill § "Evidence capture for the hand-back".

### G · Files NOT modified (explicit scope guard)

- `src/cli/` — CLI sunset (ROADMAP § Phase 2 task 2.11). Change-password is a UI route, not a CLI command. `architect-sunset-guard` clean.
- `src/services/vault.py` — vault sunset (ROADMAP § Phase 2 task 2.12). PC.6 is plain DB column + bcrypt; no secret material lands in the vault.
- `docs/design/DATA_MODEL.md` — single-doc tracking: the User model definition in the plan IS the contract; DATA_MODEL.md will sync when the User entity is next touched (likely plan 11+).
- `src/api/portfolio.py` — public no-auth endpoint; not in the find-replace scope.
- `README.md` — operational surface (the new `/auth/change-password` page) is internal; not in README's § Configuration table. If engineer disagrees, a one-line note in README § Configuration's "Authentication" stub is fine — record in deviations either way.
- `flake.nix` / `nix/devshell.nix` — no new env vars or shellHook changes.
- `docs/plans/POST_PHASE_1.md` — the must-change-on-first-login flow becomes part of the standard end-to-end smoke; engineer adds one bullet to step 2 ("Plan 18: if the dev credential was server-generated, you'll be redirected to /auth/change-password on first authed access") at archive time. **This is a deviation-section line item, not a plan-internal edit.**

`architect-sunset-guard` skill check at plan author time: no `src/cli/` touched, no vault scope added, no new `naavik <verb>` subcommand, no `~/.naavik/<artifact>` paths added (the existing `~/.naavik/dev-credentials` is referenced for context but not modified). Clean.

## Open questions

The plan is mostly self-resolving via the § B option matrices, but the following five questions block approval — each is a decision the user (Shyam) should sign off on explicitly because they shape user-facing behavior and would be expensive to undo in a follow-up:

- [ ] **Q1 — Strict-equal old-vs-new check at change-password.** § C.4's `post_change_password` rejects `new_password == current_password`. Acceptable? Or should we allow it (some operators may genuinely want to "rotate" by re-typing the same strong password to clear the flag)? **Recommendation: reject.** The flag exists because the current password was server-picked; allowing re-use makes the rotation theatrical.
- [ ] **Q2 — Auto-delete `~/.naavik/dev-credentials` after a successful flag-clearing rotation?** Per the risk table's last row: the file becomes stale once rotated. Should `post_change_password` `Path.unlink(missing_ok=True)` it inline (option a in the risk row), or defer? **Recommendation: inline delete.** Engineer adds ~3 lines to `post_change_password`; staleness becomes a non-issue. If user prefers defer, we surface a `## Deviations` row.
- [ ] **Q3 — Should signup-created accounts ALSO get `must_change_password=False` (their default) OR should the first-user signup flow flip it True the first time a non-admin signs up (Phase 2+ multi-user shape)?** § B.3 recommends "narrow scope — seed-generated only". Confirms?
- [ ] **Q4 — Migration revision id.** `0003_user_must_change_pw` (short slug, abbreviated). Alternative: `0003_must_change_pw` or `0003_user_pwchange_flag`. Any preference? **Recommendation: `0003_user_must_change_pw`** — names the column + the parent table.
- [ ] **Q5 — `validate_password_complexity` error text.** Each rule has a one-sentence message. Should we collect all violated rules and report them together ("Password must be at least 12 characters AND contain a digit"), or stop at the first violation as drafted? **Recommendation: stop at the first.** Simpler to test, more focused UX — the user fixes the most-important rule first and the next try surfaces the next rule.

## Approval checklist

- [ ] **Flag storage:** dedicated boolean column `User.must_change_password` (per § B.1)
- [ ] **Redirect mechanism:** wrapping `get_current_user` with `require_password_complete` dependency (per § B.2); exemption list of 4 routes named in § C.8
- [ ] **Scope:** flag set ONLY when `dev_password_source == "generated"` (per § B.3); env-supplied passwords remain operator-owned
- [ ] **Complexity rules:** min 12 chars (char-count, not byte-count) · ≥ 1 ASCII letter [A-Za-z] · ≥ 1 ASCII digit [0-9] (per § B.4 + § A)
- [ ] **Seed-time validation:** `NAAVIK_DEV_PASSWORD` is NOT validated for complexity (operator-owned per § B.5)
- [ ] **Endpoint location:** `GET /auth/change-password` (page) + `POST /api/v1/auth/change-password` (REST), matching signup pattern (per § B.6); no new CLI subcommand
- [ ] **Migration revision id:** `0003_user_must_change_pw` (per Open question Q4)
- [ ] **Strict-equal old-vs-new rejection:** `post_change_password` rejects `new_password == current_password` (per Open question Q1)
- [ ] **Stale-credentials-file cleanup:** `post_change_password` deletes `~/.naavik/dev-credentials` on successful rotation (per Open question Q2)
- [ ] **Error-message strategy:** first-violation-only message in `validate_password_complexity` (per Open question Q5)
- [ ] **Test surface:** 7 unit tests in `tests/test_auth.py` + 2 page tests in `tests/test_pages.py` + 2 live-DB tests in `tests/test_seed.py` (per § C.10–C.12); existing tests preserved (no regression — engineer verifies via full-suite run)
- [ ] **Find-replace audit:** post-replace `grep -rn "Depends(get_current_user)" src/` returns EXACTLY the 4 exempt-route matches in § C.8; engineer commits grep output to PR description

## Deviations from plan

PR #50 shipped on `feat/PC.6-password-complexity` with three named deviations, one
observation, and a Path-C re-loop after hacker (HIGH) + devops (FAIL_RECOVERABLE)
review. All four are listed below per `AGENTS.md § Workflow step 7` (what / why /
impact / surface).

- **Find-replace scope reduction (§ C.8: ~25 routes → 5 routes).** what: Only
  `src/api/applications.py` (5 sites) carried `Depends(get_current_user)`; the rest
  of the routes the plan named — `src/api/profile.py`, `src/api/settings.py`, every
  `src/ui/routes/*.py` — still use the plan-09 fake-session stub
  (`ui/auth_stub.is_authenticated`, cookie `naavik_session=fake-1`) and have no
  FastAPI auth dep at all. The swap therefore landed only where a real dep already
  existed. why: Wave 6 of plan 10 migrated only `api/applications` off the stub; the
  broader migration is queued behind whatever plan rolls real auth across
  `api/profile` + `api/settings` + UI routes (likely sequenced near 2.12 vault sunset
  or as a follow-up Phase 2 ergonomics paper cut). impact: PC.6's redirect intent
  fires only on `api/applications/*` mutations + the `GET /auth/change-password` page
  itself. A flagged user can still see UI page chrome until they touch any
  mutation-bearing API. Filed as ROADMAP § Pre-Phase-2 paper cuts row **PC.6a**
  (2026-05-17): "Broader `require_password_complete` gate — extend to api/profile +
  api/settings + ui/routes once those routes gain real auth deps." ~1–2 h once the
  auth deps exist. surface: ROADMAP row PC.6a (new tracking row, no code/operator
  surface yet).

- **Branch name uppercase enforcement (`feat/PC.6-...`).** what: Implementation
  branch shipped as `feat/PC.6-password-complexity` instead of the original prompt's
  lowercase `pc.6-...` framing. why: `.claude/hooks/git/prepare-commit-msg` regex
  matches `PC\.[0-9]+` (and `[A-Z]+\.[0-9]+[a-z]?` for the generic shape)
  case-sensitively; lowercase silently no-ops the `Closes #N` append. impact: This
  PR's commits all carry `Closes #8` correctly. Future authors must use UPPERCASE
  task-id in branch names. surface: `docs/AGENT_OPS.md` § 2.8 gained a one-paragraph
  "Branch task-id case is enforced uppercase" note in the re-loop (this PR). The
  hook itself is unchanged — flipping its regex to case-insensitive is a separate
  paper cut someone can file standalone if recurrence pain warrants.

- **Exempt-route count is 3 routes + 1 internal wrapper, not 4 routes.** what:
  Plan § C.8 listed `post_logout` as the 4th exempt route. In reality
  `post_logout` doesn't take an auth dep — its signature is
  `async def post_logout(request: Request)` — so the find-replace grep
  `Depends(get_current_user)` doesn't surface it. The grep result the PR commits is
  honest about 4 matches whose composition is 3 routes (`get_change_password` page,
  `post_change_password` endpoint, `get_me`) + 1 internal definition
  (`require_password_complete` wrapper signature in `services/auth.py:274`). why:
  Plan-author drafting error; intent was unaffected. impact: Behavior identical to
  plan intent — logout works while flagged because no auth dep blocks it. Semantic
  fix to the plan's § C.8 wording, nothing else. surface: none.

- **Pre-existing live-DB failures (11 on main, unrelated to PC.6).** what:
  `NAAVIK_LIVE_DB=1 uv run pytest` shows 11 failures (`test_pages.py` signup-form
  rendering, `test_draft_lifecycle.py` lazy CTA, `test_stub_endpoints.py` bullets
  CRUD, etc.). These are state-pollution / memory-persistence artifacts of running
  the suite under live DB. why: Verified on main via `git stash` of the PC.6 diff +
  re-run — identical set of failures persists. Not introduced by PC.6. impact: Live-
  DB suite is unreliable as a green gate today; selective `pytest tests/test_seed.py`
  + `pytest tests/test_auth.py` works cleanly and is what the build-gates skill runs
  in this context. Broader live-DB stability is the kind of thing PC.5 / PC.7 paper-
  cut work was supposed to be addressing; current state has it as an ambient nuisance
  rather than a blocking gate. surface: none (no new code or operator surface — just
  a pinned expectation that live-DB selective runs are the trustworthy signal).

- **Hacker Finding 3 deferred to Phase 1.x — JWT denylist on password rotation.**
  what: `POST /api/v1/auth/change-password` issues a fresh JWT but does not
  invalidate the OLD one — a stolen pre-rotation JWT remains valid for its natural
  TTL (24h default / 30d keep-signed-in). The auth module docstring's "Rotated on
  auth events" is half-delivered. why: Server-side denylist (or per-user signing-key
  prefix rotation) is a deeper change than PC.6's scope — own service + own DB table
  + cron to expire entries. Refresh-token rotation is already queued in Phase 1.x
  deferred items; this row is narrower scope and deserves its own line. impact: A
  defense-in-depth gap, not a behavioral break. Filed as ROADMAP § Phase 1.x deferred
  items row (2026-05-17): "JWT denylist on password rotation (PR #50 hacker
  Finding 3)." Phase 1.x; ships with whatever broader auth ergonomics plan picks it
  up. surface: ROADMAP row in Phase 1.x deferred items (new tracking row, no code or
  operator surface yet).

- **Path-C re-loop after hacker REQUEST_CHANGES (HIGH).** what: After the initial
  PC.6 commit `baad10c3`, hacker raised 3 findings (1 HIGH, 2 MEDIUM). User
  selected Path C ("address findings in this PR with new commits, do not amend").
  The re-loop added: (a) `Depends(require_password_complete)` to the Phase-1 stub at
  `src/ui/routes/settings.py:411` so flagged users can't bypass the must-change flow
  + complexity check via the Settings · Account form (Finding 1, HIGH); (b)
  `Depends(require_csrf)` to `POST /api/v1/auth/change-password` so credential-
  mutation routes carry the same double-submit defense as the rest of the auth
  surface (Finding 2, MEDIUM); (c) `require_csrf` definition relocated above
  `post_change_password` in the same file (function ordering); (d) test coverage —
  one redirect-when-flagged test on the gated stub + two CSRF tests (missing-token
  rejection + matching-token pass-through) on the change-password endpoint; (e)
  AGENT_OPS § 2.8 hook-regex case-sensitivity note (deviation row 2 above); (f) this
  Deviations section (the row you are reading now). The HTMX form on
  `pages/change_password.html` already carries `X-CSRF-Token` via the global
  `base.html` `hx-headers` attribute, so the CSRF dep is invisible to honest clients
  — verified via manual QA smoke 8d. why: Hacker review surfaced a complexity-bypass
  surface that the original find-replace scope reduction had unintentionally left
  open. Path C kept the merge surface tight (one branch, narrow commits) instead of
  re-opening the plan. impact: Resolves Finding 1 + Finding 2 cleanly without
  broadening scope; Finding 3 deferred (above). PR commits all carry `Closes #8`
  thanks to the uppercase branch convention. surface: existing stub gated (not
  removed) — the Phase-1 mock response shape preserved for the unflagged path so the
  Settings · Account UI doesn't regress; flagged users get 303 + HX-Redirect to
  `/auth/change-password` (the canonical mutation surface).
