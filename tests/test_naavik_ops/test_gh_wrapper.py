"""Tests for naavik_ops.gh — subprocess wrappers around scripts/gh-project.sh.

Strategy: monkeypatch `SCRIPT_PATH` to a sandbox script that echoes its args.
This validates the wrapper's arg-forwarding contract without touching live
GitHub state. Real round-trip parity is checked manually during Manual QA Gate.
"""

from __future__ import annotations

import stat

import pytest


@pytest.fixture
def sandbox_gh_script(tmp_path, monkeypatch):
    """Plant a tiny shell script + monkeypatch SCRIPT_PATH to it."""
    from naavik_ops import gh

    sandbox = tmp_path / "fake-gh.sh"
    sandbox.write_text(
        '#!/usr/bin/env bash\necho "ARGS:$*"\necho "to_stderr" >&2\nexit 0\n',
        encoding="utf-8",
    )
    sandbox.chmod(sandbox.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setattr(gh, "SCRIPT_PATH", sandbox)
    return gh


def test_shim_capture_returns_stdout(sandbox_gh_script):
    out = sandbox_gh_script._shim_capture("foo", "bar")
    assert "ARGS:foo bar" in out


def test_cmd_set_status_routes_through_shim(sandbox_gh_script):
    rc = sandbox_gh_script.cmd_set_status(["abc123", "Todo"])
    assert rc == 0


def test_helper_set_status_passes_args(sandbox_gh_script, capsys):
    # Programmatic helper should not raise.
    sandbox_gh_script.set_status("PVT_xxx", "Todo")


def test_helper_set_status_rejects_empty(sandbox_gh_script):
    from naavik_ops.lib import NaavikOpsError

    with pytest.raises(NaavikOpsError):
        sandbox_gh_script.set_status("", "Todo")


def test_missing_script_raises(tmp_path, monkeypatch):
    from naavik_ops import gh
    from naavik_ops.lib import NaavikOpsError

    monkeypatch.setattr(gh, "SCRIPT_PATH", tmp_path / "does-not-exist.sh")
    with pytest.raises(NaavikOpsError):
        gh._shim_capture("anything")


def test_failed_script_translates_to_error(tmp_path, monkeypatch):
    import stat

    from naavik_ops import gh
    from naavik_ops.lib import NaavikOpsError

    fail = tmp_path / "fail.sh"
    fail.write_text('#!/usr/bin/env bash\necho "bad" >&2\nexit 3\n', encoding="utf-8")
    fail.chmod(fail.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setattr(gh, "SCRIPT_PATH", fail)
    with pytest.raises(NaavikOpsError):
        gh._shim_capture("anything")
