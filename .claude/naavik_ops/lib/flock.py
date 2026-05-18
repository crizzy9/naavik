"""flock — fcntl.flock context manager for single-writer serialization.

Mirrors the semantics of `scripts/agent-memory.sh:with_lock` (flock -x) so that
`naavik-ops task insert / defer / prioritize / move / renumber / sync` and the
release ceremony serialize against concurrent invocations.

Lock files live at user-controlled paths (e.g. `~/.naavik/naavik-ops.lock`,
`~/.naavik/A.29-migration.lock`). Caller passes the path.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def acquire(lock_path: str | os.PathLike[str], blocking: bool = True) -> Iterator[None]:
    """Acquire an exclusive flock on `lock_path` for the duration of the with-block.

    `blocking=True` waits indefinitely; `blocking=False` raises BlockingIOError
    on contention (caller handles retry/abort).

    The lock file is created if missing. Parent directories are not — caller
    ensures the directory exists.

    On exception inside the with-block the lock releases (try/finally guaranteed
    by context manager protocol).
    """
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        fcntl.flock(fd, flags)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def held(lock_path: str | os.PathLike[str]) -> bool:
    """Probe whether `lock_path` is currently held by another process.

    Returns True if a non-blocking acquire would fail. Useful for diagnostics
    + pre-flight gates in the migration runbook.
    """
    path = Path(lock_path)
    if not path.exists():
        return False
    fd = os.open(path, os.O_WRONLY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)
