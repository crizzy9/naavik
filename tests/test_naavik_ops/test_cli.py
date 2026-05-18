"""Tests for naavik_ops.cli — argparse-style dispatcher routing.

Verify:
  - --help / --version exit 0.
  - Unknown groups exit 2.
  - Group routes to module + cmd_<name> function.
  - Unknown commands within a group exit 2.
"""

from __future__ import annotations

from naavik_ops.cli import main


def _run(args, capsys):
    rc = main(args)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


class TestTopLevel:
    def test_no_args_prints_help(self, capsys):
        rc, out, _ = _run([], capsys)
        assert rc == 0
        assert "naavik-ops" in out
        assert "Groups:" in out

    def test_help_exits_zero(self, capsys):
        rc, out, _ = _run(["--help"], capsys)
        assert rc == 0
        assert "naavik-ops" in out

    def test_version_exits_zero(self, capsys):
        rc, out, _ = _run(["--version"], capsys)
        assert rc == 0
        assert "naavik-ops" in out

    def test_unknown_group_exits_2(self, capsys):
        rc, _, err = _run(["bogus"], capsys)
        assert rc == 2
        assert "unknown group" in err


class TestTaskRoute:
    def test_group_help(self, capsys):
        rc, out, _ = _run(["task", "--help"], capsys)
        assert rc == 0
        assert "task" in out

    def test_unknown_command(self, capsys):
        rc, _, err = _run(["task", "nonsense"], capsys)
        assert rc == 2
        assert "unknown command" in err

    def test_bump_invokes(self, capsys):
        # `task bump patch` is read-only + should exit 0.
        rc, out, _ = _run(["task", "bump", "patch"], capsys)
        assert rc == 0
        assert "after patch bump" in out


class TestDepsRoute:
    def test_deps_check_clean(self, capsys, tmp_path, monkeypatch):
        # Use a sandbox issue-map so we don't touch the repo state.
        from naavik_ops import deps

        sandbox = tmp_path / ".claude" / "github-issue-map.json"
        sandbox.parent.mkdir(parents=True)
        sandbox.write_text('{"deps": {}}', encoding="utf-8")
        monkeypatch.setattr(deps, "ISSUE_MAP_PATH", sandbox)
        monkeypatch.setattr(deps, "LOCK_PATH", tmp_path / "lock")

        rc, out, _ = _run(["deps", "check"], capsys)
        assert rc == 0
        assert "clean" in out


class TestReleaseRoute:
    def test_release_help(self, capsys):
        rc, out, _ = _run(["release", "--help"], capsys)
        assert rc == 0
        assert "release" in out

    def test_release_changelog_invalid_version(self, capsys):
        rc, _, err = _run(["release", "changelog", "not-a-version"], capsys)
        assert rc == 1
        assert "match" in err or "does not match" in err

    def test_release_changelog_release_id(self, capsys):
        rc, out, _ = _run(["release", "changelog", "0.1.0"], capsys)
        assert rc == 0
        assert "0.1.0" in out
