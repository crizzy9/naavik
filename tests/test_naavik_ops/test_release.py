"""Tests for naavik_ops.release — ceremony driver + version sync."""

from __future__ import annotations

import pytest


@pytest.fixture
def sandbox_release(tmp_path, monkeypatch):
    """Stand up a sandbox repo with pyproject.toml + nix/package.nix to mutate.

    Skips the git ops since we don't initialize a git repo here. The mutation
    ops are pure file writes — git steps are tested separately.
    """
    from naavik_ops import release

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "naavik"\nversion = "0.1.0"\n', encoding="utf-8")
    package_nix = tmp_path / "nix" / "package.nix"
    package_nix.parent.mkdir()
    package_nix.write_text(
        '{ pkgs }:\n{\n  pname = "naavik";\n  version = "0.1.0";\n}\n',
        encoding="utf-8",
    )
    changelog = tmp_path / "CHANGELOG.md"

    monkeypatch.setattr(release, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(release, "PYPROJECT_PATH", pyproject)
    monkeypatch.setattr(release, "PACKAGE_NIX_PATH", package_nix)
    monkeypatch.setattr(release, "CHANGELOG_PATH", changelog)

    return release, pyproject, package_nix, changelog


class TestVersionSync:
    def test_update_pyproject(self, sandbox_release):
        release, pyproject, _, _ = sandbox_release
        changed = release._update_pyproject("0.1.1")
        assert changed
        assert '"0.1.1"' in pyproject.read_text()

    def test_update_pyproject_idempotent(self, sandbox_release):
        release, pyproject, _, _ = sandbox_release
        release._update_pyproject("0.1.1")
        changed_again = release._update_pyproject("0.1.1")
        assert not changed_again

    def test_update_package_nix(self, sandbox_release):
        release, _, package_nix, _ = sandbox_release
        changed = release._update_package_nix("0.1.1")
        assert changed
        assert 'version = "0.1.1";' in package_nix.read_text()


class TestChangelogPrepend:
    def test_creates_file_if_missing(self, sandbox_release):
        release, _, _, changelog = sandbox_release
        assert not changelog.exists()
        release._prepend_changelog_release(
            "0.1.0",
            summary="First release",
            sections={"Added": ["Foundation", "MVP"]},
        )
        text = changelog.read_text()
        assert "[0.1.0]" in text
        assert "Added" in text
        assert "Foundation" in text

    def test_prepends_to_existing(self, sandbox_release):
        release, _, _, changelog = sandbox_release
        # Seed with an existing CHANGELOG.
        changelog.write_text(
            "# Changelog\n\n## [Unreleased]\n\n(wip)\n\n## [0.1.0] - 2026-05-01\n\n### Added\n- thing\n",
            encoding="utf-8",
        )
        release._prepend_changelog_release(
            "0.2.0",
            summary="Phase 2",
            sections={"Added": ["scrapers"]},
        )
        text = changelog.read_text()
        # New 0.2.0 block precedes the existing 0.1.0.
        assert text.find("[0.2.0]") < text.find("[0.1.0]")


class TestDryRun:
    def test_dry_run_does_not_mutate(self, sandbox_release, capsys):
        release, pyproject, package_nix, _ = sandbox_release
        pyproject_before = pyproject.read_text()
        package_nix_before = package_nix.read_text()
        rc = release.cmd_dry_run(["0.1.1"])
        assert rc == 0
        assert pyproject.read_text() == pyproject_before
        assert package_nix.read_text() == package_nix_before

    def test_dry_run_rejects_task_id(self, sandbox_release, capsys):
        release, _, _, _ = sandbox_release
        from naavik_ops.lib import NaavikOpsError

        with pytest.raises(NaavikOpsError):
            release.cmd_dry_run(["0.2.0.05"])

    def test_dry_run_rejects_invalid_version(self, sandbox_release):
        release, _, _, _ = sandbox_release
        from naavik_ops.lib import NaavikOpsError

        with pytest.raises(NaavikOpsError):
            release.cmd_dry_run(["not-a-version"])


class TestChangelogCommand:
    def test_changelog_command_emits_block(self, sandbox_release, capsys):
        release, _, _, _ = sandbox_release
        rc = release.cmd_changelog(["0.1.0"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[0.1.0]" in out
