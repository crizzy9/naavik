"""Tests for naavik_ops.task — list / next-unblocked / check / bump / stubs."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def sandbox_task(tmp_path, monkeypatch):
    """Sandbox the task module against a temp ROADMAP + map + pyproject + flake."""
    from naavik_ops import task

    issue_map = tmp_path / ".claude" / "github-issue-map.json"
    issue_map.parent.mkdir(parents=True)
    issue_map.write_text(
        json.dumps(
            {
                "issues": {
                    "0.2.0.01": 20,
                    "0.2.0.02": 21,
                    "0.2.0.05": 14,
                    "0.1.0.50": 71,  # ignored when filtering 0.2.0
                },
                "priorities": {
                    "0.2.0.01": "HIGH",
                    "0.2.0.05": "HIGH",
                },
                "deps": {
                    "0.2.0.02": {"blocks": [], "blocked_by": ["0.2.0.01"]},
                    "0.2.0.01": {"blocks": ["0.2.0.02"], "blocked_by": []},
                },
                "statuses": {},
            }
        ),
        encoding="utf-8",
    )

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")

    package_nix = tmp_path / "nix" / "package.nix"
    package_nix.parent.mkdir()
    package_nix.write_text('{ }: { version = "0.1.0"; }\n', encoding="utf-8")

    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text("# stub\n", encoding="utf-8")

    monkeypatch.setattr(task, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(task, "ISSUE_MAP_PATH", issue_map)
    monkeypatch.setattr(task, "PYPROJECT_PATH", pyproject)
    monkeypatch.setattr(task, "PACKAGE_NIX_PATH", package_nix)
    monkeypatch.setattr(task, "ROADMAP_PATH", roadmap)

    return task


class TestList:
    def test_list_filters_by_release(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_list(["0.2.0"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "0.2.0.01" in out
        assert "0.2.0.05" in out
        assert "0.1.0.50" not in out

    def test_list_sorts_priority_desc_then_position(self, sandbox_task, capsys):
        assert sandbox_task.cmd_list(["0.2.0"]) == 0
        out = capsys.readouterr().out
        lines = [line for line in out.splitlines() if line.startswith("0.2.0.")]
        # HIGH-priority tasks come first; among them, position ASC.
        # Expected order: 0.2.0.01 HIGH, 0.2.0.05 HIGH, 0.2.0.02 unset.
        assert lines[0].startswith("0.2.0.01")
        assert lines[1].startswith("0.2.0.05")
        assert lines[2].startswith("0.2.0.02")

    def test_list_json(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_list(["0.2.0", "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 3


class TestNextUnblocked:
    def test_picks_highest_priority_unblocked(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_next_unblocked(["0.2.0"])
        assert rc == 0
        out = capsys.readouterr().out
        # 0.2.0.01 HIGH unblocked (no blocked_by), should be first.
        assert "0.2.0.01" in out
        assert "HIGH" in out


class TestCheck:
    def test_check_clean(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_check([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "clean" in out

    def test_check_detects_version_drift(self, sandbox_task, capsys):
        # Make pyproject + package.nix versions disagree.
        sandbox_task.PYPROJECT_PATH.write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
        sandbox_task.PACKAGE_NIX_PATH.write_text('{ }: { version = "0.2.0"; }\n', encoding="utf-8")
        rc = sandbox_task.cmd_check([])
        assert rc == 1
        err = capsys.readouterr().err
        assert "drift" in err


class TestBump:
    def test_bump_patch(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_bump(["patch"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "0.1.1" in out

    def test_bump_minor(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_bump(["minor"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "0.2.0" in out

    def test_bump_rejects_unknown(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_bump(["fizz"])
        assert rc == 2
        assert "major|minor|patch" in capsys.readouterr().err


class TestMutatingStubs:
    def test_insert_returns_not_implemented(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_insert(["0.2.0.05", "Title"])
        assert rc == 2
        assert "not implemented during A.29" in capsys.readouterr().err

    def test_defer_returns_not_implemented(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_defer(["0.2.0.05", "--by", "2"])
        assert rc == 2

    def test_move_returns_not_implemented(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_move(["0.2.0.05", "0.3.0.05"])
        assert rc == 2
