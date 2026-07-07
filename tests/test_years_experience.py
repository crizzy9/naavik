"""profile_service.total_years_experience — merged-interval YoE (2026-07).

One number feeds the profile hero chip, the score_job judge prompt, and the
match_analysis coverage prompt, so the math is pinned here: interval UNION
(concurrent roles never double-count), gaps excluded, open-ended roles run
to now, missing dates degrade to None.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from services.profile import total_years_experience


def _exp(start: datetime | None, end: datetime | None):
    return SimpleNamespace(start_date=start, end_date=end)


def test_none_when_no_experiences():
    assert total_years_experience([]) is None
    assert total_years_experience(None) is None
    assert total_years_experience([_exp(None, None)]) is None


def test_single_closed_range():
    years = total_years_experience(
        [_exp(datetime(2018, 1, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC))]
    )
    assert 2.9 < years < 3.1


def test_open_ended_runs_to_now():
    start = datetime.now(UTC) - timedelta(days=730)
    years = total_years_experience([_exp(start, None)])
    assert 1.9 < years < 2.1


def test_overlapping_roles_do_not_double_count():
    a = _exp(datetime(2018, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, tzinfo=UTC))
    b = _exp(datetime(2019, 1, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC))
    years = total_years_experience([a, b])
    assert 2.9 < years < 3.1  # union 2018→2021, NOT 2+2


def test_gaps_between_roles_excluded():
    a = _exp(datetime(2015, 1, 1, tzinfo=UTC), datetime(2016, 1, 1, tzinfo=UTC))
    b = _exp(datetime(2019, 1, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC))
    years = total_years_experience([a, b])
    assert 2.9 < years < 3.1  # 1 + 2, the 3-year gap doesn't count


def test_naive_datetimes_tolerated():
    years = total_years_experience([_exp(datetime(2018, 1, 1), datetime(2019, 1, 1))])
    assert 0.9 < years < 1.1
