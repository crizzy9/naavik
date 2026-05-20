"""Tests for naavik_ops.task — list / next-unblocked / check / bump / stubs."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def sandbox_task(tmp_path, monkeypatch):
    """Sandbox the task module against a temp ROADMAP + map + pyproject + flake.

    Closes 0.7.0.27 — ROADMAP is source of truth for which tasks exist + their
    status. Issue-map is consulted only for Issue # cross-ref. Default fixture
    writes 3 open 0.2.0.NN tasks (.01 HIGH unblocked, .02 unset blocked-by-.01,
    .05 HIGH unblocked) — all `[ ]`.
    """
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
                    "0.1.0.50": 71,
                },
                "deps": {
                    "0.2.0.02": {"blocks": [], "blocked_by": ["0.2.0.01"]},
                    "0.2.0.01": {"blocks": ["0.2.0.02"], "blocked_by": []},
                },
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
    roadmap.write_text(
        "# Roadmap\n\n"
        "### 0.2.0 — Test release\n\n"
        "| # | Task | Status | Priority | Legacy ID | Notes |\n"
        "|---|---|---|---|---|---|\n"
        "| 0.2.0.01 | Task one | [ ] | HIGH | x | First |\n"
        "| 0.2.0.02 | Task two | [ ] | — | x | Blocked |\n"
        "| 0.2.0.05 | Task five | [ ] | HIGH | x | Free |\n"
        "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(task, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(task, "ISSUE_MAP_PATH", issue_map)
    monkeypatch.setattr(task, "PYPROJECT_PATH", pyproject)
    monkeypatch.setattr(task, "PACKAGE_NIX_PATH", package_nix)
    monkeypatch.setattr(task, "ROADMAP_PATH", roadmap)

    return task


@pytest.fixture
def sandbox_with_mixed_status(sandbox_task):
    """Same as sandbox_task but with one shipped, one in-progress, one open."""
    sandbox_task.ROADMAP_PATH.write_text(
        "# Roadmap\n\n"
        "### 0.2.0 — Test release\n\n"
        "| # | Task | Status | Priority | Legacy ID | Notes |\n"
        "|---|---|---|---|---|---|\n"
        "| 0.2.0.01 | Task one | [x] | HIGH | x | Shipped |\n"
        "| 0.2.0.02 | Task two | [~] | — | x | In progress; blocked-by .01 done |\n"
        "| 0.2.0.05 | Task five | [ ] | HIGH | x | Free |\n"
        "\n",
        encoding="utf-8",
    )
    return sandbox_task


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
        # Status should be parsed from ROADMAP cell.
        statuses = {r["id"]: r["status"] for r in payload}
        assert statuses["0.2.0.01"] == " "

    def test_list_hides_done_by_default(self, sandbox_with_mixed_status, capsys):
        """Closes 0.7.0.27 — `[x]` rows hidden from `list` by default."""
        rc = sandbox_with_mixed_status.cmd_list(["0.2.0"])
        assert rc == 0
        out = capsys.readouterr().out
        # 0.2.0.01 is [x] — should NOT appear as a row (rows start with task-id).
        # The dep mention in BLOCKED-BY column is fine.
        task_id_lines = [line for line in out.splitlines() if line.startswith("0.2.0.")]
        ids = {line.split()[0] for line in task_id_lines}
        assert "0.2.0.01" not in ids
        assert "0.2.0.02" in ids
        assert "0.2.0.05" in ids

    def test_list_include_done(self, sandbox_with_mixed_status, capsys):
        """--include-done surfaces shipped rows."""
        rc = sandbox_with_mixed_status.cmd_list(["0.2.0", "--include-done"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "0.2.0.01" in out
        assert "[x]" in out


class TestNextUnblocked:
    def test_picks_highest_priority_unblocked(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_next_unblocked(["0.2.0"])
        assert rc == 0
        out = capsys.readouterr().out
        # 0.2.0.01 HIGH unblocked (no blocked_by), should be first.
        assert "0.2.0.01" in out
        assert "HIGH" in out

    def test_skips_done_picks_next_open(self, sandbox_with_mixed_status, capsys):
        """Closes 0.7.0.27 — `next-unblocked` no longer returns shipped rows."""
        rc = sandbox_with_mixed_status.cmd_next_unblocked(["0.2.0"])
        assert rc == 0
        out = capsys.readouterr().out
        # 0.2.0.01 is [x] — skip. 0.2.0.02 [~] is blocked-by 0.2.0.01 (which IS
        # done now), so .02 is unblocked. .02 has unset priority while .05 is
        # HIGH — but sort is priority DESC → position ASC, so HIGH .05 wins.
        assert "0.2.0.05" in out
        assert "0.2.0.01" not in out

    def test_all_done_returns_no_unblocked(self, sandbox_task, capsys):
        """When everything is [x], reports no unblocked tasks."""
        sandbox_task.ROADMAP_PATH.write_text(
            "# Roadmap\n\n"
            "### 0.2.0 — Test release\n\n"
            "| # | Task | Status | Priority | Legacy ID | Notes |\n"
            "|---|---|---|---|---|---|\n"
            "| 0.2.0.01 | Task one | [x] | HIGH | x | Done |\n"
            "| 0.2.0.05 | Task five | [x] | HIGH | x | Done |\n",
            encoding="utf-8",
        )
        rc = sandbox_task.cmd_next_unblocked(["0.2.0"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "no unblocked tasks" in out

    def test_blocked_by_unshipped_dep_skips(self, sandbox_task, capsys):
        """If blocked_by dep is open in ROADMAP, the row stays blocked."""
        # All 3 open + .02 depends on .01 → only .01 + .05 are unblocked.
        # Picks .01 (HIGH, position 1) over .05 (HIGH, position 5).
        rc = sandbox_task.cmd_next_unblocked(["0.2.0"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "0.2.0.01" in out


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


class TestRenameReleaseStillStubbed:
    """Per plan 25 Open Q1: cmd_rename_release stays stubbed in 0.1.1."""

    def test_rename_release_returns_2(self, sandbox_task, capsys):
        rc = sandbox_task.cmd_rename_release(["0.2.0", "0.3.0"])
        assert rc == 2
        assert "stays stubbed" in capsys.readouterr().err
