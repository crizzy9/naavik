"""US-city autocomplete dataset + search tests (services/geo.py)."""

from __future__ import annotations

import pytest

from services import geo

pytestmark = pytest.mark.uses_sample_data_shims


def test_dataset_loads_and_is_population_ranked():
    cities = geo._cities()
    assert len(cities) > 20_000
    assert cities[0]["label"] == "New York, NY"


def test_search_prefix_ranks_most_populous_first():
    items = geo.search_cities("bost")
    assert items[0]["label"] == "Boston, MA"
    assert all(i["state"] for i in items)


def test_search_is_typo_tolerant():
    labels = [i["label"] for i in geo.search_cities("bostn")]
    assert "Boston, MA" in labels


def test_search_substring_matches():
    labels = [i["label"] for i in geo.search_cities("francisco")]
    assert "San Francisco, CA" in labels


def test_search_empty_query_returns_nothing():
    assert geo.search_cities("") == []
    assert geo.search_cities("   ") == []


def test_normalize_city_variants():
    assert geo.normalize_city("Boston") == "Boston, MA"
    assert geo.normalize_city("Boston, MA") == "Boston, MA"
    assert geo.normalize_city("Boston, Massachusetts") == "Boston, MA"
    assert geo.normalize_city("boston, ma, usa") == "Boston, MA"
    assert geo.normalize_city("Not A Real City XYZ") is None
    assert geo.normalize_city("") is None
