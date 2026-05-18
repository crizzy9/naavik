"""Tests for naavik_ops.memory — subprocess wrappers around agent-memory.sh."""

from __future__ import annotations

import stat

import pytest


@pytest.fixture
def sandbox_memory_script(tmp_path, monkeypatch):
    from naavik_ops import memory

    sandbox = tmp_path / "fake-mem.sh"
    sandbox.write_text(
        '#!/usr/bin/env bash\necho "MEM_ARGS:$*"\nexit 0\n',
        encoding="utf-8",
    )
    sandbox.chmod(sandbox.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setattr(memory, "SCRIPT_PATH", sandbox)
    return memory


def test_shim_capture(sandbox_memory_script):
    assert "MEM_ARGS:list decisions" in sandbox_memory_script._shim_capture("list", "decisions")


def test_cmd_list(sandbox_memory_script):
    assert sandbox_memory_script.cmd_list(["decisions"]) == 0


def test_capture_list_helper(sandbox_memory_script):
    out = sandbox_memory_script.capture_list("discussions")
    assert "list discussions" in out


def test_capture_query_helper(sandbox_memory_script):
    out = sandbox_memory_script.capture_query("decisions", '.state == "active"')
    assert "query decisions" in out
