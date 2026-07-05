"""Plan 83 (0.7.0.36): first-run state probe.

After deletion of the auto-seed dev user + `~/.naavik/dev-credentials`
artifact, the probe collapses to a single signal: `user_count`.
`is_first_run == (user_count == 0)`.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

# ── FirstRunState dataclass invariants ───────────────────────────────────


def test_first_run_state_is_first_run_when_empty():
    from services.utils.first_run import FirstRunState

    state = FirstRunState(user_count=0)
    assert state.is_first_run is True
    assert state.has_users is False


def test_first_run_state_not_first_run_when_users_exist():
    from services.utils.first_run import FirstRunState

    state = FirstRunState(user_count=1)
    assert state.is_first_run is False
    assert state.has_users is True


# ── probe_first_run_state — session=None branch ─────────────────────────


async def test_probe_user_count_zero_without_session():
    """`session=None` → user_count stays 0 (no DB to query)."""
    from services.utils.first_run import probe_first_run_state

    state = await probe_first_run_state(session=None)
    assert state.user_count == 0
    assert state.has_users is False
    assert state.is_first_run is True
