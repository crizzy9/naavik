"""Behavioral tests for naavik_ops.gh (native Python; plan 25 D.7).

These tests mock the subprocess + GraphQL surface so no live GitHub state is
touched. They lock down:

  - Map-cache-first idempotency (the 2026-05-16 #46/#47 dup regression).
  - Atomic map cache writes.
  - Per-subcommand argv parsing + dispatch.
  - update-issue-title + close-issue (NEW helpers per D.7).
  - next-unblocked sort order (CRITICAL > HIGH > MEDIUM > LOW).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from naavik_ops import gh
from naavik_ops.lib import NaavikOpsError


@pytest.fixture
def sandbox_gh(tmp_path, monkeypatch):
    """Plant temp cache + map paths; stub network helpers; return the module."""
    cache_path = tmp_path / ".claude" / "github-project.json"
    map_path = tmp_path / ".claude" / "github-issue-map.json"
    runs_path = tmp_path / "traces" / "runs.log"
    cache_path.parent.mkdir(parents=True)
    runs_path.parent.mkdir(parents=True)

    cache_data = {
        "owner": "crizzy9",
        "repo": "naavik",
        "scope": "user",
        "project_id": "PVT_x",
        "project_number": 4,
        "status_field_id": "F_status",
        "priority_field_id": "F_priority",
        "effort_field_id": "F_effort",
        "status_options": {
            "todo": "opt_todo",
            "in_progress": "opt_inprog",
            "done": "opt_done",
            "backlog": "opt_backlog",
        },
        "priority_options": {
            "critical": "opt_crit",
            "high": "opt_high",
            "medium": "opt_med",
            "low": "opt_low",
        },
        "effort_options": {
            "xs": "opt_xs",
            "s": "opt_s",
            "m": "opt_m",
            "l": "opt_l",
            "xl": "opt_xl",
        },
    }
    cache_path.write_text(json.dumps(cache_data), encoding="utf-8")

    monkeypatch.setattr(gh, "CACHE_PATH", cache_path)
    monkeypatch.setattr(gh, "ISSUE_MAP_PATH", map_path)
    monkeypatch.setattr(gh, "RUNS_LOG_PATH", runs_path)

    # Sandbox: any unmocked _gh / gh_graphql / _gh_api call fails loudly.
    def _no_network(*args, **kwargs):
        raise RuntimeError(f"unexpected network call: args={args} kwargs={kwargs}")

    monkeypatch.setattr(gh, "_gh", _no_network)
    monkeypatch.setattr(gh, "_gh_api", _no_network)
    monkeypatch.setattr(gh, "_gh_api_paginate", _no_network)
    monkeypatch.setattr(gh, "gh_graphql", _no_network)
    monkeypatch.setattr(gh, "_set_select", lambda *a, **kw: None)
    return gh


def _allow(gh_module, name, return_value=None, side_effect=None):
    """Helper: replace a sandboxed function with a recorder."""
    calls: list[Any] = []

    def _record(*args, **kwargs):
        calls.append((args, kwargs))
        if side_effect is not None:
            return side_effect(*args, **kwargs)
        return return_value

    setattr(gh_module, name, _record)
    return calls


# ---------------------------------------------------------------------------
# Map-cache idempotency — the headline behavioral contract
# ---------------------------------------------------------------------------


class TestMapCache:
    def test_lookup_returns_none_when_absent(self, sandbox_gh):
        assert sandbox_gh._map_lookup("epics", "Phase A") is None

    def test_set_creates_file_and_persists(self, sandbox_gh):
        sandbox_gh._map_set("epics", "Phase A", 1)
        assert sandbox_gh.ISSUE_MAP_PATH.is_file()
        data = json.loads(sandbox_gh.ISSUE_MAP_PATH.read_text(encoding="utf-8"))
        assert data["epics"]["Phase A"] == 1
        # _meta scaffolding present.
        assert "_meta" in data
        assert data["_meta"]["owner"] == "crizzy9"

    def test_set_updates_existing(self, sandbox_gh):
        sandbox_gh._map_set("epics", "Phase A", 1)
        sandbox_gh._map_set("epics", "Phase A", 99)
        assert sandbox_gh._map_lookup("epics", "Phase A") == 99

    def test_set_preserves_other_categories(self, sandbox_gh):
        sandbox_gh._map_set("milestones", "Phase A", 1)
        sandbox_gh._map_set("epics", "Phase A", 2)
        sandbox_gh._map_set("issues", "A.1", 10)
        assert sandbox_gh._map_lookup("milestones", "Phase A") == 1
        assert sandbox_gh._map_lookup("epics", "Phase A") == 2
        assert sandbox_gh._map_lookup("issues", "A.1") == 10


# ---------------------------------------------------------------------------
# find_issue_by_prefix — map-first then live search
# ---------------------------------------------------------------------------


class TestFindIssueByPrefix:
    def test_map_hit_skips_search(self, sandbox_gh, monkeypatch):
        sandbox_gh._map_set("issues", "A.1", 42)
        called = _allow(sandbox_gh, "_gh_api")
        result = sandbox_gh._find_issue_by_prefix("[A.1]", "issues", "A.1")
        assert result == 42
        assert called == [], "_gh_api MUST NOT be called when map hits"

    def test_search_fallback_backfills_map(self, sandbox_gh, monkeypatch):
        responses = {
            "items": [{"number": 7, "title": "[PC.5] sample"}],
        }
        _allow(sandbox_gh, "_gh_api", return_value=responses)
        # Map empty → search hit → backfill expected.
        result = sandbox_gh._find_issue_by_prefix("[PC.5]", "issues", "PC.5")
        assert result == 7
        # Now map should have the entry.
        assert sandbox_gh._map_lookup("issues", "PC.5") == 7

    def test_search_miss_returns_none(self, sandbox_gh, monkeypatch):
        _allow(sandbox_gh, "_gh_api", return_value={"items": []})
        assert sandbox_gh._find_issue_by_prefix("[unknown]", "issues", "unknown") is None


# ---------------------------------------------------------------------------
# set-status / set-priority / set-effort
# ---------------------------------------------------------------------------


class TestSetStatus:
    def test_routes_known_status_to_option_id(self, sandbox_gh, monkeypatch):
        captured = []

        def _record(project_id, item_id, field_id, option_id):
            captured.append((project_id, item_id, field_id, option_id))

        monkeypatch.setattr(sandbox_gh, "_set_select", _record)
        rc = sandbox_gh.cmd_set_status(["PVT_item_1", "Todo"])
        assert rc == 0
        assert captured == [("PVT_x", "PVT_item_1", "F_status", "opt_todo")]

    def test_in_progress_alias(self, sandbox_gh, monkeypatch):
        captured = []
        monkeypatch.setattr(
            sandbox_gh,
            "_set_select",
            lambda *a, **kw: captured.append(a),
        )
        rc = sandbox_gh.cmd_set_status(["item", "In Progress"])
        assert rc == 0
        assert captured[0][3] == "opt_inprog"

    def test_unknown_status_raises(self, sandbox_gh):
        with pytest.raises(NaavikOpsError, match="unknown status"):
            sandbox_gh.cmd_set_status(["item", "Bogus"])

    def test_missing_args_returns_2(self, sandbox_gh, capsys):
        rc = sandbox_gh.cmd_set_status(["only-one"])
        assert rc == 2
        assert "usage" in capsys.readouterr().err

    def test_helper_rejects_empty(self, sandbox_gh):
        with pytest.raises(NaavikOpsError, match="non-empty"):
            sandbox_gh.set_status("", "Todo")


class TestSetPriority:
    def test_routes_critical(self, sandbox_gh, monkeypatch):
        captured = []
        monkeypatch.setattr(
            sandbox_gh,
            "_set_select",
            lambda *a, **kw: captured.append(a),
        )
        rc = sandbox_gh.cmd_set_priority(["item", "CRITICAL"])
        assert rc == 0
        assert captured[0][3] == "opt_crit"

    def test_unknown_priority_raises(self, sandbox_gh):
        with pytest.raises(NaavikOpsError, match="unknown priority"):
            sandbox_gh.cmd_set_priority(["item", "MEDIUMHIGH"])


class TestClearPriority:
    def test_invokes_graphql_with_clear_mutation(self, sandbox_gh, monkeypatch):
        captured = []

        def _record(query, variables=None):
            captured.append((query, variables))
            return {}

        monkeypatch.setattr(sandbox_gh, "gh_graphql", _record)
        rc = sandbox_gh.cmd_clear_priority(["PVT_item_42"])
        assert rc == 0
        assert len(captured) == 1
        query, variables = captured[0]
        assert "clearProjectV2ItemFieldValue" in query
        assert variables == {"p": "PVT_x", "i": "PVT_item_42", "f": "F_priority"}

    def test_no_op_when_priority_field_not_configured(self, sandbox_gh, monkeypatch, capsys):
        # Strip priority_field_id from the cache.
        cache_data = json.loads(sandbox_gh.CACHE_PATH.read_text(encoding="utf-8"))
        cache_data["priority_field_id"] = ""
        sandbox_gh.CACHE_PATH.write_text(json.dumps(cache_data), encoding="utf-8")

        # Network must NOT be called when the field is unconfigured.
        called = []
        monkeypatch.setattr(sandbox_gh, "gh_graphql", lambda *a, **kw: called.append((a, kw)) or {})

        rc = sandbox_gh.cmd_clear_priority(["PVT_item_42"])
        assert rc == 0
        assert called == []
        assert "Priority field not configured" in capsys.readouterr().err

    def test_missing_args_returns_2(self, sandbox_gh, capsys):
        rc = sandbox_gh.cmd_clear_priority([])
        assert rc == 2
        assert "usage" in capsys.readouterr().err

    def test_programmatic_helper_matches_cli(self, sandbox_gh, monkeypatch):
        captured = []

        def _record(query, variables=None):
            captured.append((query, variables))
            return {}

        monkeypatch.setattr(sandbox_gh, "gh_graphql", _record)
        sandbox_gh.clear_priority("PVT_item_99")
        assert len(captured) == 1
        assert "clearProjectV2ItemFieldValue" in captured[0][0]
        assert captured[0][1]["i"] == "PVT_item_99"


class TestSetEffort:
    def test_routes_xs(self, sandbox_gh, monkeypatch):
        captured = []
        monkeypatch.setattr(
            sandbox_gh,
            "_set_select",
            lambda *a, **kw: captured.append(a),
        )
        rc = sandbox_gh.cmd_set_effort(["item", "XS"])
        assert rc == 0
        assert captured[0][3] == "opt_xs"


# ---------------------------------------------------------------------------
# update-issue-title (NEW per D.7)
# ---------------------------------------------------------------------------


class TestUpdateIssueTitle:
    def test_rekeys_map_when_prefix_changes(self, sandbox_gh, monkeypatch):
        sandbox_gh._map_set("issues", "0.2.0.05", 14)

        called = _allow(sandbox_gh, "_gh", return_value="")
        rc = sandbox_gh.cmd_update_issue_title(["14", "[0.2.0.06] Title After Shift"])
        assert rc == 0
        # Old key removed, new key inserted.
        assert sandbox_gh._map_lookup("issues", "0.2.0.05") is None
        assert sandbox_gh._map_lookup("issues", "0.2.0.06") == 14
        # gh CLI call shape: ['issue', 'edit', '14', '--repo', ...].
        cmd = called[0][0]
        assert cmd[:3] == ("issue", "edit", "14")

    def test_no_rekey_when_prefix_unchanged(self, sandbox_gh, monkeypatch):
        sandbox_gh._map_set("issues", "0.2.0.05", 14)
        _allow(sandbox_gh, "_gh", return_value="")
        rc = sandbox_gh.cmd_update_issue_title(["14", "[0.2.0.05] New body"])
        assert rc == 0
        assert sandbox_gh._map_lookup("issues", "0.2.0.05") == 14

    def test_missing_args_returns_2(self, sandbox_gh, capsys):
        rc = sandbox_gh.cmd_update_issue_title(["14"])
        assert rc == 2
        assert "usage" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# close-issue (NEW per D.7)
# ---------------------------------------------------------------------------


class TestCloseIssue:
    def test_close_completed_calls_gh(self, sandbox_gh):
        called = _allow(sandbox_gh, "_gh", return_value="")
        rc = sandbox_gh.cmd_close_issue(["76"])
        assert rc == 0
        cmd = called[0][0]
        assert cmd[:3] == ("issue", "close", "76")

    def test_close_not_planned_passes_reason(self, sandbox_gh):
        called = _allow(sandbox_gh, "_gh", return_value="")
        rc = sandbox_gh.cmd_close_issue(["76", "--reason", "not_planned"])
        assert rc == 0
        cmd = called[0][0]
        assert "--reason" in cmd
        assert "not planned" in cmd

    def test_validates_int_argv(self, sandbox_gh):
        with pytest.raises(NaavikOpsError, match="integer"):
            sandbox_gh.cmd_close_issue(["abc"])

    def test_rejects_bad_reason(self, sandbox_gh):
        with pytest.raises(NaavikOpsError, match="completed.+not_planned"):
            sandbox_gh.cmd_close_issue(["76", "--reason", "bogus"])


# ---------------------------------------------------------------------------
# next-unblocked sort order
# ---------------------------------------------------------------------------


class TestNextUnblocked:
    def _items_payload(self, *combos):
        out = []
        for n, status, priority, labels in combos:
            out.append(
                {
                    "id": f"item_{n}",
                    "content": {
                        "__typename": "Issue",
                        "number": n,
                        "title": f"[T.{n}] Title {n}",
                        "url": f"https://example.test/{n}",
                        "state": "OPEN",
                        "labels": {"nodes": [{"name": lbl} for lbl in labels]},
                    },
                    "fieldValues": {
                        "nodes": [
                            {
                                "name": status,
                                "field": {"name": "Status"},
                            },
                            {
                                "name": priority,
                                "field": {"name": "Priority"},
                            },
                        ]
                    },
                }
            )
        return out

    def test_critical_first(self, sandbox_gh, monkeypatch, capsys):
        items = self._items_payload(
            (1, "Todo", "LOW", []),
            (2, "Todo", "CRITICAL", []),
            (3, "Todo", "MEDIUM", []),
        )
        monkeypatch.setattr(sandbox_gh, "_items_payload", lambda cache: items)
        rc = sandbox_gh.cmd_next_unblocked([])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["number"] == 2
        assert payload["priority"] == "CRITICAL"

    def test_skips_blocked_label(self, sandbox_gh, monkeypatch, capsys):
        items = self._items_payload(
            (1, "Todo", "HIGH", ["blocked"]),
            (2, "Todo", "LOW", []),
        )
        monkeypatch.setattr(sandbox_gh, "_items_payload", lambda cache: items)
        rc = sandbox_gh.cmd_next_unblocked([])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["number"] == 2

    def test_skips_backlog(self, sandbox_gh, monkeypatch, capsys):
        items = self._items_payload(
            (1, "Backlog", "HIGH", []),
            (2, "Todo", "LOW", []),
        )
        monkeypatch.setattr(sandbox_gh, "_items_payload", lambda cache: items)
        rc = sandbox_gh.cmd_next_unblocked([])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["number"] == 2

    def test_skips_epic_label(self, sandbox_gh, monkeypatch, capsys):
        items = self._items_payload(
            (1, "Todo", "CRITICAL", ["epic"]),
            (2, "Todo", "LOW", []),
        )
        monkeypatch.setattr(sandbox_gh, "_items_payload", lambda cache: items)
        rc = sandbox_gh.cmd_next_unblocked([])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["number"] == 2

    def test_empty_returns_null(self, sandbox_gh, monkeypatch, capsys):
        monkeypatch.setattr(sandbox_gh, "_items_payload", lambda cache: [])
        rc = sandbox_gh.cmd_next_unblocked([])
        assert rc == 0
        assert json.loads(capsys.readouterr().out) is None


# ---------------------------------------------------------------------------
# refresh-map — collision handling
# ---------------------------------------------------------------------------


class TestRefreshMap:
    def test_open_wins_over_closed_on_prefix_collision(self, sandbox_gh, monkeypatch):
        # Two `[Epic] Pre-Phase-2 paper cuts` issues — #6 open, #46 closed.
        monkeypatch.setattr(
            sandbox_gh,
            "_gh_api_paginate",
            lambda path: (
                [
                    {"title": "Pre-Phase-2 paper cuts", "number": 2}
                    if "milestones" in path
                    else None,
                ]
                if "milestones" in path
                else [
                    {
                        "number": 6,
                        "title": "[Epic] Pre-Phase-2 paper cuts",
                        "state": "open",
                        "pull_request": None,
                    },
                    {
                        "number": 46,
                        "title": "[Epic] Pre-Phase-2 paper cuts",
                        "state": "closed",
                        "pull_request": None,
                    },
                    {
                        "number": 5,
                        "title": "[PC.5] sample",
                        "state": "closed",
                        "pull_request": None,
                    },
                    {
                        "number": 47,
                        "title": "[PC.5] sample",
                        "state": "open",
                        "pull_request": None,
                    },
                ]
            ),
        )
        rc = sandbox_gh.cmd_refresh_map([])
        assert rc == 0
        data = json.loads(sandbox_gh.ISSUE_MAP_PATH.read_text(encoding="utf-8"))
        # Open #47 wins over closed #5 (same prefix).
        assert data["issues"]["PC.5"] == 47
        # Open #6 wins over closed #46 for epic.
        assert data["epics"]["Pre-Phase-2 paper cuts"] == 6

    def test_preserves_existing_priorities_deps(self, sandbox_gh, monkeypatch):
        # Seed an existing map with priorities + deps subtrees.
        sandbox_gh.ISSUE_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        sandbox_gh.ISSUE_MAP_PATH.write_text(
            json.dumps(
                {
                    "_meta": {"note": "old"},
                    "milestones": {"Old": 1},
                    "epics": {"Old": 2},
                    "issues": {"OLD.1": 3},
                    "priorities": {"0.2.0.05": "HIGH"},
                    "deps": {"0.2.0.02": {"blocks": [], "blocked_by": ["0.2.0.01"]}},
                    "statuses": {"OLD.1": "x"},
                }
            ),
            encoding="utf-8",
        )

        # paginate returns empty for both calls.
        monkeypatch.setattr(sandbox_gh, "_gh_api_paginate", lambda path: [])

        rc = sandbox_gh.cmd_refresh_map([])
        assert rc == 0
        data = json.loads(sandbox_gh.ISSUE_MAP_PATH.read_text(encoding="utf-8"))
        # priorities / deps / statuses preserved.
        assert data["priorities"]["0.2.0.05"] == "HIGH"
        assert data["deps"]["0.2.0.02"]["blocked_by"] == ["0.2.0.01"]
        assert data["statuses"]["OLD.1"] == "x"


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------


class TestRuns:
    def test_no_log_file(self, sandbox_gh, capsys):
        rc = sandbox_gh.cmd_runs([])
        assert rc == 0
        assert "no runs yet" in capsys.readouterr().out

    def test_tail_default_10(self, sandbox_gh, capsys):
        sandbox_gh.RUNS_LOG_PATH.write_text(
            "\n".join(f"line {i}" for i in range(20)) + "\n",
            encoding="utf-8",
        )
        rc = sandbox_gh.cmd_runs([])
        assert rc == 0
        out = capsys.readouterr().out
        # Last 10 lines.
        assert "line 10" in out
        assert "line 19" in out
        assert "line 0" not in out

    def test_tail_explicit_count(self, sandbox_gh, capsys):
        sandbox_gh.RUNS_LOG_PATH.write_text(
            "\n".join(f"line {i}" for i in range(10)) + "\n",
            encoding="utf-8",
        )
        rc = sandbox_gh.cmd_runs(["3"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "line 7" in out
        assert "line 9" in out
        assert "line 6" not in out


# ---------------------------------------------------------------------------
# Bootstrap idempotency — R1 guard (#46/#47 regression)
# ---------------------------------------------------------------------------


class TestBootstrapIdempotency:
    def test_existing_map_skips_create(self, sandbox_gh, monkeypatch, capsys, tmp_path):
        # Seed map: milestone + epic for Phase A; issue for A.1.
        sandbox_gh._map_set("milestones", "Phase A", 1)
        sandbox_gh._map_set("epics", "Phase A", 100)
        sandbox_gh._map_set("issues", "A.1", 200)

        # Plant a minimal ROADMAP via the roadmap module.
        roadmap_text = (
            "# Roadmap\n\n"
            "### Phase A: Agent System\n\n"
            "| # | Task | Status | Priority | Notes |\n"
            "|---|---|---|---|---|\n"
            "| A.1 | First | [ ] | HIGH | seeded |\n"
            "| A.2 | Second | [ ] | MEDIUM | new |\n"
        )
        roadmap_file = tmp_path / "ROADMAP.md"
        roadmap_file.write_text(roadmap_text, encoding="utf-8")
        from naavik_ops.lib import roadmap as rmod

        monkeypatch.setattr(rmod, "ROADMAP_PATH", roadmap_file)

        # `_find_issue_by_prefix` returns the map hit for A.1, miss for A.2.
        def _find(prefix, category=None, key=None):
            if category and key:
                return sandbox_gh._map_lookup(category, key)
            return None

        monkeypatch.setattr(sandbox_gh, "_find_issue_by_prefix", _find)
        monkeypatch.setattr(sandbox_gh, "_lookup_milestone", lambda n: 1)

        # Dry-run only — should not call any mutator.
        rc = sandbox_gh.cmd_bootstrap(["--phase=Phase A"])
        assert rc == 0
        out = capsys.readouterr().out
        # A.1 exists in map → SKIP. A.2 dry-runs as PLAN.
        assert "SKIP" in out
        assert "A.1" in out
        assert "PLAN" in out
        assert "A.2" in out
        # No CREATE in dry-run.
        assert "CREATE" not in out
