"""Tests for naavik_ops.lib.github_api.paginate — full hasNextPage loop.

The pagination helper is the fix for Risk (e) in plan § Risk: existing
`gh-project.sh sync` caps at 200 items because the GraphQL `first:` arg never
re-issues with a cursor. This test simulates 3 pages of 100 items each via a
monkeypatched gh_graphql.
"""

from __future__ import annotations

import pytest


def _make_page(start: int, end: int, has_next: bool, cursor: str | None) -> dict:
    """Build a fake projectV2.items page payload."""
    return {
        "data": {
            "user": {
                "projectV2": {
                    "items": {
                        "nodes": [{"number": n} for n in range(start, end)],
                        "pageInfo": {
                            "hasNextPage": has_next,
                            "endCursor": cursor,
                        },
                    }
                }
            }
        }
    }


def test_paginate_walks_pages(monkeypatch):
    from naavik_ops.lib import github_api

    pages = [
        _make_page(0, 100, True, "cursor-1"),
        _make_page(100, 200, True, "cursor-2"),
        _make_page(200, 250, False, None),
    ]
    page_iter = iter(pages)

    def fake_gh_graphql(query: str, variables=None):
        return next(page_iter)

    monkeypatch.setattr(github_api, "gh_graphql", fake_gh_graphql)

    items = github_api.paginate(
        query="(unused)",
        variables=None,
        page_path=["user", "projectV2", "items"],
    )
    assert len(items) == 250
    assert items[0] == {"number": 0}
    assert items[-1] == {"number": 249}


def test_paginate_handles_single_page(monkeypatch):
    from naavik_ops.lib import github_api

    monkeypatch.setattr(
        github_api,
        "gh_graphql",
        lambda *a, **k: _make_page(0, 50, False, None),
    )
    items = github_api.paginate(
        query="(unused)",
        variables=None,
        page_path=["user", "projectV2", "items"],
    )
    assert len(items) == 50


def test_paginate_bails_on_runaway(monkeypatch):
    from naavik_ops.lib import NaavikOpsError, github_api

    # Always returns "more pages" — should trip the safety limit.
    def runaway(*a, **k):
        return _make_page(0, 1, True, "cursor")

    monkeypatch.setattr(github_api, "gh_graphql", runaway)
    with pytest.raises(NaavikOpsError):
        github_api.paginate(
            query="(unused)",
            variables=None,
            page_path=["user", "projectV2", "items"],
        )
