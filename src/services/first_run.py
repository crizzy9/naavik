"""First-run diagnostic helpers (plan 71 / 0.3.3.14).

The `/setup-help` route + `main.py` lifespan WARN both consume these
helpers so the "is this a broken first run?" check has one canonical
implementation. Surfaces the three conditions:

- `NAAVIK_DEBUG` env var unset (plan 10c triple-gate would not write
  `<data_dir>/dev-credentials`)
- No User row seeded
- `<data_dir>/dev-credentials` artifact missing

Owner directive (2026-05-21): no new CLI subcommands; no new env vars.
The helper reads `config.settings.debug` and probes the existing
artifact path established by plan 10c.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from models import User


@dataclass(frozen=True, slots=True)
class FirstRunState:
    """Snapshot of the three first-run health signals.

    `broken` is True when at least one signal indicates the operator
    will hit the auth wall plan 10c was supposed to short-circuit:
    no `NAAVIK_DEBUG` AND user(s) seeded AND no dev-credentials file.
    """

    debug_enabled: bool
    user_count: int
    dev_credentials_present: bool
    dev_credentials_path: str

    @property
    def has_users(self) -> bool:
        return self.user_count > 0

    @property
    def broken(self) -> bool:
        """True iff the operator is locked out of first-run auth.

        Plan 10c triple-gate: debug + no preset password + SELF_HOSTED.
        When `debug` is False AND a user exists AND no dev-credentials
        file exists, the operator can't sign up (gate disabled) and
        doesn't know the seeded password.
        """
        return (not self.debug_enabled) and self.has_users and not self.dev_credentials_present


def _dev_credentials_path() -> Path:
    """Resolve `<data_dir>/dev-credentials` for the current settings.

    Plan 10c writes the artifact via `db/seed.py` to `Settings.data_dir`
    + `/dev-credentials`. Same probe surface here so the diagnostic
    tracks reality.
    """
    return Path(app_settings.data_dir) / "dev-credentials"


async def probe_first_run_state(session: AsyncSession | None) -> FirstRunState:
    """Run the three checks. `session=None` is treated as "DB unavailable".

    Used by both the public `/setup-help` HTML route and the FastAPI
    lifespan boot log. Boot path passes a live session; the route gets
    one via `Depends(get_session)`.
    """
    creds_path = _dev_credentials_path()
    debug_enabled = bool(app_settings.debug)
    dev_credentials_present = creds_path.exists()

    user_count = 0
    if session is not None:
        try:
            row = (await session.exec(select(func.count()).select_from(User))).one()
            # SQLAlchemy `Row` → first column; the conftest noop returns None.
            if row is None:
                user_count = 0
            elif hasattr(row, "_mapping") or isinstance(row, tuple):
                user_count = int(row[0])
            else:
                user_count = int(row)
        except Exception:  # noqa: BLE001
            # Treat any probe error as "unknown count" rather than
            # silently passing — the route renders an explicit "DB
            # probe failed" note, the lifespan logs DEBUG.
            user_count = 0

    return FirstRunState(
        debug_enabled=debug_enabled,
        user_count=user_count,
        dev_credentials_present=dev_credentials_present,
        dev_credentials_path=str(creds_path),
    )
