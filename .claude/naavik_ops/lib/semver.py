"""semver — 4-level semver task-ID schema parse / compare / bump.

Schema (per design doc § 1):
  <MAJOR>.<MINOR>.<PATCH>[.<POSITION>]

  3-level = release version (e.g. 0.1.0, 0.2.0, 0.2.1)
  4-level = task within release (e.g. 0.2.0.01, 0.1.0.50)

  Position is zero-padded 2-digit (01..99). 99 slots per release MINOR.

Regex: ^\\d+\\.\\d+\\.\\d+(\\.\\d{2})?$
"""

from __future__ import annotations

import re

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.(\d{2}))?$")

#: Schema regex as a string for downstream consumers (commit-msg hook, etc.).
SCHEMA_REGEX = r"^\d+\.\d+\.\d+(\.\d{2})?$"


class InvalidVersion(ValueError):
    """Raised when a version string doesn't match the 4-level schema."""


def parse(version: str) -> tuple[int, int, int, int | None]:
    """Parse a version string into (major, minor, patch, position|None).

    Position is None for 3-level (release) versions; 0-99 for 4-level (task).

    >>> parse("0.1.0")
    (0, 1, 0, None)
    >>> parse("0.2.0.01")
    (0, 2, 0, 1)
    >>> parse("0.2.0.14")
    (0, 2, 0, 14)
    """
    m = _VERSION_RE.match(version)
    if m is None:
        raise InvalidVersion(
            f"'{version}' does not match {SCHEMA_REGEX} "
            f"(3-level release or 4-level task w/ 2-digit position)"
        )
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pos_str = m.group(4)
    position = int(pos_str) if pos_str is not None else None
    return major, minor, patch, position


def format(major: int, minor: int, patch: int, position: int | None = None) -> str:
    """Format components back into a canonical string.

    >>> format(0, 2, 0)
    '0.2.0'
    >>> format(0, 2, 0, 1)
    '0.2.0.01'
    >>> format(0, 2, 0, 14)
    '0.2.0.14'
    """
    if position is None:
        return f"{major}.{minor}.{patch}"
    if not (0 <= position <= 99):
        raise InvalidVersion(f"position {position} out of range (0..99)")
    return f"{major}.{minor}.{patch}.{position:02d}"


def is_release(version: str) -> bool:
    """True if `version` is a 3-level release ID (no position)."""
    return parse(version)[3] is None


def is_task(version: str) -> bool:
    """True if `version` is a 4-level task ID (has position)."""
    return parse(version)[3] is not None


def release_of(version: str) -> str:
    """Return the 3-level release portion of a task ID; identity for release IDs.

    >>> release_of("0.2.0.05")
    '0.2.0'
    >>> release_of("0.2.0")
    '0.2.0'
    """
    major, minor, patch, _ = parse(version)
    return format(major, minor, patch)


def compare(a: str, b: str) -> int:
    """Three-way compare: -1 if a<b, 0 if equal, +1 if a>b.

    Tuple compare on (major, minor, patch, position) where None sorts before
    any integer position (release < its earliest task).

    >>> compare("0.1.0", "0.2.0")
    -1
    >>> compare("0.2.0.01", "0.2.0.02")
    -1
    >>> compare("0.2.0", "0.2.0.01")
    -1
    >>> compare("0.2.0.05", "0.2.0.05")
    0
    """
    ta = parse(a)
    tb = parse(b)
    # None (release-level) compares less than any 4-level task.
    ka = (ta[0], ta[1], ta[2], -1 if ta[3] is None else ta[3])
    kb = (tb[0], tb[1], tb[2], -1 if tb[3] is None else tb[3])
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0


def bump(version: str, kind: str) -> str:
    """Return next version after bumping `kind` ('major'|'minor'|'patch').

    Position is dropped (returns a release-level ID). Caller assigns sub-task
    positions separately.

    >>> bump("0.1.0", "patch")
    '0.1.1'
    >>> bump("0.1.5", "minor")
    '0.2.0'
    >>> bump("0.5.7", "major")
    '1.0.0'
    >>> bump("0.2.0.05", "patch")
    '0.2.1'
    """
    major, minor, patch, _ = parse(version)
    if kind == "major":
        return format(major + 1, 0, 0)
    if kind == "minor":
        return format(major, minor + 1, 0)
    if kind == "patch":
        return format(major, minor, patch + 1)
    raise ValueError(f"bump kind must be major|minor|patch (got '{kind}')")
