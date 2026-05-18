"""Tests for naavik_ops.lib.semver — 4-level schema regex + parse/compare/bump."""

from __future__ import annotations

import pytest
from naavik_ops.lib import semver


class TestSchemaRegex:
    def test_accepts_3level_release(self):
        assert semver.parse("0.1.0") == (0, 1, 0, None)

    def test_accepts_4level_task(self):
        assert semver.parse("0.2.0.01") == (0, 2, 0, 1)
        assert semver.parse("0.2.0.14") == (0, 2, 0, 14)
        assert semver.parse("0.1.0.99") == (0, 1, 0, 99)

    def test_rejects_1digit_position(self):
        with pytest.raises(semver.InvalidVersion):
            semver.parse("0.2.0.1")

    def test_rejects_3digit_position(self):
        with pytest.raises(semver.InvalidVersion):
            semver.parse("0.2.0.001")

    def test_rejects_extra_levels(self):
        with pytest.raises(semver.InvalidVersion):
            semver.parse("0.2.0.01.5")

    def test_rejects_garbage(self):
        for bad in ["", "0.1", "0", "v0.1.0", "0.1.0-rc.1", "abc"]:
            with pytest.raises(semver.InvalidVersion):
                semver.parse(bad)


class TestFormat:
    def test_release_format(self):
        assert semver.format(0, 1, 0) == "0.1.0"

    def test_task_format_pads(self):
        assert semver.format(0, 2, 0, 1) == "0.2.0.01"
        assert semver.format(0, 2, 0, 14) == "0.2.0.14"

    def test_format_rejects_out_of_range_position(self):
        with pytest.raises(semver.InvalidVersion):
            semver.format(0, 2, 0, 100)
        with pytest.raises(semver.InvalidVersion):
            semver.format(0, 2, 0, -1)


class TestIsAccessors:
    def test_is_release(self):
        assert semver.is_release("0.1.0")
        assert not semver.is_release("0.2.0.05")

    def test_is_task(self):
        assert semver.is_task("0.2.0.05")
        assert not semver.is_task("0.2.0")

    def test_release_of(self):
        assert semver.release_of("0.2.0.05") == "0.2.0"
        assert semver.release_of("0.2.0") == "0.2.0"
        assert semver.release_of("0.1.1") == "0.1.1"


class TestCompare:
    def test_release_ordering(self):
        assert semver.compare("0.1.0", "0.2.0") == -1
        assert semver.compare("0.2.0", "0.1.0") == +1
        assert semver.compare("0.1.0", "0.1.0") == 0

    def test_task_ordering_within_release(self):
        assert semver.compare("0.2.0.01", "0.2.0.02") == -1
        assert semver.compare("0.2.0.14", "0.2.0.02") == +1

    def test_release_below_first_task(self):
        # Release sorts before its earliest task.
        assert semver.compare("0.2.0", "0.2.0.01") == -1

    def test_cross_release_release_vs_task(self):
        assert semver.compare("0.1.0.99", "0.2.0") == -1
        assert semver.compare("0.2.0", "0.1.0.99") == +1


class TestBump:
    def test_bump_patch(self):
        assert semver.bump("0.1.0", "patch") == "0.1.1"
        assert semver.bump("0.2.5", "patch") == "0.2.6"

    def test_bump_minor(self):
        assert semver.bump("0.1.5", "minor") == "0.2.0"

    def test_bump_major(self):
        assert semver.bump("0.5.7", "major") == "1.0.0"

    def test_bump_drops_position(self):
        assert semver.bump("0.2.0.05", "patch") == "0.2.1"

    def test_bump_rejects_unknown_kind(self):
        with pytest.raises(ValueError):
            semver.bump("0.1.0", "wrong")
