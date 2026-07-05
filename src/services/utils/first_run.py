"""First-run diagnostic helper (plan 83 / 0.7.0.36).

`is_first_run = (user_count == 0)`. After plan 83 deleted the auto-seed
dev user + `~/.naavik/dev-credentials` artifact, the only signal needed
to drive `/login`, `/setup-help`, and the lifespan first-boot log is the
User-table count. Empty → operator visits `/signup`; non-empty → normal
sign-in flow.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import User


@dataclass(frozen=True, slots=True)
class FirstRunState:
    """Snapshot of first-run state. `is_first_run` collapses to user_count==0."""

    user_count: int

    @property
    def has_users(self) -> bool:
        return self.user_count > 0

    @property
    def is_first_run(self) -> bool:
        return self.user_count == 0


async def probe_first_run_state(session: AsyncSession | None) -> FirstRunState:
    """Count User rows. `session=None` → user_count stays 0."""
    user_count = 0
    if session is not None:
        try:
            row = (await session.exec(select(func.count()).select_from(User))).one()
            if row is None:
                user_count = 0
            elif hasattr(row, "_mapping") or isinstance(row, tuple):
                user_count = int(row[0])
            else:
                user_count = int(row)
        except Exception:  # noqa: BLE001
            user_count = 0
    return FirstRunState(user_count=user_count)
