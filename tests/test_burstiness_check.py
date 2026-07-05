"""Burstiness validator — plan 66 (0.3.1) § T5."""

from __future__ import annotations

import pytest

from services.generation.burstiness_check import (
    BURSTINESS_THRESHOLD,
    BurstinessReport,
    check_and_score,
)

pytestmark = pytest.mark.uses_sample_data_shims


def test_uniform_bullets_fail_burstiness():
    # All ~10-word bullets → std-dev near 0.
    bullets = [
        "Shipped the payment service and cut latency by half",
        "Built the auth service and dropped error rate to zero",
        "Drove the data pipeline and increased throughput by ten",
        "Refactored the API gateway and cleared the backlog of bugs",
    ]
    report = check_and_score(bullets)
    assert not report.passed
    assert report.std_dev < BURSTINESS_THRESHOLD
    assert report.worst_offender_idx is not None
    assert report.suggested_target in ("short", "long")


def test_varied_bullets_pass_burstiness():
    bullets = [
        "Shipped it.",  # 2 words — very short
        "Built the auth service",  # 4 words — short
        "We redesigned the data pipeline so it could handle bursts of "
        "ten thousand events per second without queuing or dropping any "
        "of the payload mid-flight.",  # ~28 words — long
    ]
    report = check_and_score(bullets)
    assert report.passed
    assert report.std_dev >= BURSTINESS_THRESHOLD


def test_empty_bullets_pass():
    report = check_and_score([])
    assert report.passed
    assert report.std_dev == 0.0


def test_single_bullet_passes():
    report = check_and_score(["Single bullet here"])
    assert report.passed


def test_worst_offender_is_closest_to_mean():
    bullets = [
        "One two three four five six seven eight nine ten",  # 10 words
        "One two three four five six seven eight nine ten eleven",  # 11 words
        "One two",  # 2 words — outlier (further from any mean)
    ]
    report = check_and_score(bullets)
    # The worst offender (closest to the mean) is one of the 10/11-word
    # bullets — NOT the outlier.
    assert report.worst_offender_idx in (0, 1)


def test_report_carries_word_counts():
    bullets = ["one two", "one two three", "one two three four"]
    report = check_and_score(bullets)
    assert report.word_counts == [2, 3, 4]
    assert isinstance(report, BurstinessReport)
