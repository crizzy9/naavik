"""Tests for naavik_ops.lib.flock — fcntl.flock context manager."""

from __future__ import annotations

import multiprocessing
import time

import pytest
from naavik_ops.lib import flock


def _child_acquire(lock_path: str, duration: float):
    """Acquire the lock for `duration` seconds, then release."""
    with flock.acquire(lock_path):
        time.sleep(duration)


def test_acquire_creates_file(tmp_path):
    lock_path = tmp_path / "test.lock"
    with flock.acquire(lock_path):
        assert lock_path.exists()
    assert lock_path.exists()


def test_acquire_releases_on_exit(tmp_path):
    lock_path = tmp_path / "test.lock"
    with flock.acquire(lock_path):
        pass
    # Subsequent non-blocking acquire must succeed.
    with flock.acquire(lock_path, blocking=False):
        pass


def test_acquire_releases_on_exception(tmp_path):
    lock_path = tmp_path / "test.lock"
    with pytest.raises(RuntimeError), flock.acquire(lock_path):
        raise RuntimeError("boom")
    # Released after the exception.
    with flock.acquire(lock_path, blocking=False):
        pass


def test_held_probe(tmp_path):
    lock_path = tmp_path / "test.lock"
    assert not flock.held(lock_path)

    proc = multiprocessing.Process(target=_child_acquire, args=(str(lock_path), 0.3))
    proc.start()
    # Wait for the child to actually grab the lock.
    time.sleep(0.05)
    try:
        assert flock.held(lock_path)
    finally:
        proc.join()
    assert not flock.held(lock_path)


def test_non_blocking_raises_under_contention(tmp_path):
    lock_path = tmp_path / "test.lock"
    proc = multiprocessing.Process(target=_child_acquire, args=(str(lock_path), 0.3))
    proc.start()
    time.sleep(0.05)
    try:
        with pytest.raises(BlockingIOError), flock.acquire(lock_path, blocking=False):
            pass
    finally:
        proc.join()
