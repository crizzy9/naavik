"""Tests for naavik_ops.deps — cross-task DAG add/remove/list/check."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def sandbox_deps(tmp_path, monkeypatch):
    """Sandbox the deps module against a temp .claude/github-issue-map.json."""
    from naavik_ops import deps

    sandbox_map = tmp_path / ".claude" / "github-issue-map.json"
    sandbox_map.parent.mkdir(parents=True)
    sandbox_map.write_text(
        json.dumps({"deps": {}, "issues": {"0.2.0.01": 20, "0.2.0.02": 21, "0.2.0.05": 14}}),
        encoding="utf-8",
    )
    sandbox_lock = tmp_path / "naavik-ops.lock"

    monkeypatch.setattr(deps, "ISSUE_MAP_PATH", sandbox_map)
    monkeypatch.setattr(deps, "LOCK_PATH", sandbox_lock)
    return deps, sandbox_map


class TestAdd:
    def test_add_records_both_directions(self, sandbox_deps, capsys):
        deps, map_path = sandbox_deps
        assert deps.cmd_add(["0.2.0.02", "0.2.0.01"]) == 0
        data = json.loads(map_path.read_text())
        entry = data["deps"]["0.2.0.02"]
        assert "0.2.0.01" in entry["blocked_by"]
        inv = data["deps"]["0.2.0.01"]
        assert "0.2.0.02" in inv["blocks"]

    def test_add_is_idempotent(self, sandbox_deps, capsys):
        deps, map_path = sandbox_deps
        deps.cmd_add(["0.2.0.02", "0.2.0.01"])
        deps.cmd_add(["0.2.0.02", "0.2.0.01"])  # duplicate
        data = json.loads(map_path.read_text())
        entry = data["deps"]["0.2.0.02"]
        # No duplicates in the blocked_by list.
        assert entry["blocked_by"].count("0.2.0.01") == 1

    def test_add_rejects_self_dep(self, sandbox_deps):
        deps, _ = sandbox_deps
        from naavik_ops.lib import NaavikOpsError

        with pytest.raises(NaavikOpsError):
            deps.cmd_add(["0.2.0.02", "0.2.0.02"])

    def test_add_rejects_release_id(self, sandbox_deps):
        deps, _ = sandbox_deps
        from naavik_ops.lib import NaavikOpsError

        with pytest.raises(NaavikOpsError):
            deps.cmd_add(["0.2.0", "0.2.0.01"])

    def test_add_rejects_cycle(self, sandbox_deps):
        deps, map_path = sandbox_deps
        from naavik_ops.lib import NaavikOpsError

        deps.cmd_add(["0.2.0.02", "0.2.0.01"])
        deps.cmd_add(["0.2.0.05", "0.2.0.02"])
        # Adding 0.2.0.01 blocked_by 0.2.0.05 would create a cycle.
        with pytest.raises(NaavikOpsError):
            deps.cmd_add(["0.2.0.01", "0.2.0.05"])
        # Verify the cycle didn't persist.
        data = json.loads(map_path.read_text())
        entry = data["deps"]["0.2.0.01"]
        assert "0.2.0.05" not in (entry.get("blocked_by") or [])


class TestRemove:
    def test_remove_clears_both_directions(self, sandbox_deps):
        deps, map_path = sandbox_deps
        deps.cmd_add(["0.2.0.02", "0.2.0.01"])
        assert deps.cmd_remove(["0.2.0.02", "0.2.0.01"]) == 0
        data = json.loads(map_path.read_text())
        assert "0.2.0.01" not in (data["deps"]["0.2.0.02"]["blocked_by"] or [])
        assert "0.2.0.02" not in (data["deps"]["0.2.0.01"]["blocks"] or [])


class TestList:
    def test_list_prints_both(self, sandbox_deps, capsys):
        deps, _ = sandbox_deps
        deps.cmd_add(["0.2.0.02", "0.2.0.01"])
        deps.cmd_add(["0.2.0.05", "0.2.0.02"])
        # Reset stdout capture.
        capsys.readouterr()
        rc = deps.cmd_list(["0.2.0.02"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "blocks" in out and "0.2.0.05" in out
        assert "blocked_by" in out and "0.2.0.01" in out


class TestCheck:
    def test_check_empty(self, sandbox_deps, capsys):
        deps, _ = sandbox_deps
        rc = deps.cmd_check([])
        out = capsys.readouterr().out
        assert rc == 0
        assert "clean" in out

    def test_check_clean_with_edges(self, sandbox_deps, capsys):
        deps, _ = sandbox_deps
        deps.cmd_add(["0.2.0.02", "0.2.0.01"])
        deps.cmd_add(["0.2.0.05", "0.2.0.02"])
        capsys.readouterr()
        rc = deps.cmd_check([])
        assert rc == 0
