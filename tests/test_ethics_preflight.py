"""Ethics pre-flight — plan 66 (0.3.1) § B.6."""

from __future__ import annotations

import pytest

from services.generation.ethics_preflight import EthicsReport, preflight_check

pytestmark = pytest.mark.uses_sample_data_shims


def test_preflight_passes_when_all_bullets_in_profile():
    selected = [1, 2, 3]
    trimmed = {1: "First", 2: "Second", 3: "Third"}
    available = {1, 2, 3, 4, 5}
    report = preflight_check(selected, trimmed, available)
    assert report.passed
    assert report.dropped_bullets == []
    assert not report.surface_to_user
    assert selected == [1, 2, 3]  # unchanged
    assert trimmed == {1: "First", 2: "Second", 3: "Third"}


def test_preflight_drops_bullets_not_in_profile():
    selected = [1, 99, 2]
    trimmed = {1: "First", 99: "Fabricated", 2: "Second"}
    available = {1, 2, 3}
    report = preflight_check(selected, trimmed, available)
    assert not report.passed
    assert len(report.dropped_bullets) == 1
    assert report.dropped_bullets[0]["bullet_id"] == 99
    assert report.dropped_bullets[0]["trimmed_line"] == "Fabricated"
    assert selected == [1, 2]
    assert 99 not in trimmed


def test_preflight_surface_to_user_when_many_drops():
    selected = [101, 102, 103, 104]
    trimmed = {bid: f"f-{bid}" for bid in selected}
    available = {1, 2, 3}
    report = preflight_check(selected, trimmed, available)
    assert not report.passed
    assert len(report.dropped_bullets) == 4
    assert report.surface_to_user  # > 2 drops


def test_preflight_does_not_surface_for_few_drops():
    selected = [1, 99]
    trimmed = {1: "ok", 99: "fab"}
    available = {1}
    report = preflight_check(selected, trimmed, available)
    assert not report.passed
    assert len(report.dropped_bullets) == 1
    assert not report.surface_to_user  # 1 drop ≤ 2


def test_ethics_report_dataclass_defaults():
    report = EthicsReport(passed=True)
    assert report.dropped_bullets == []
    assert report.flags == []
    assert not report.surface_to_user
