"""task — release-version task ops.

Per design doc § 1 + plan § D.11. Sole writer for task-ID + release-version
mutations under `.claude/naavik-ops task`.

# Subcommand surface (Wave 1)

  list <version> [--status <s>] [--include-done]
                              Sorted by priority DESC → position ASC
                              (priority DESC: HIGH > MED > LOW > unset; unset
                              ranked lowest)
  check                       Lint ROADMAP vs Issue titles vs map cache vs
                              pyproject vs flake vs git tags
  next-unblocked <version>    Next unblocked task in <version>:
                              priority DESC → position ASC, gated by deps
  sync [--apply]              Rewrite Issue titles + Priority field to match
                              ROADMAP

Mutating (each acquires ~/.naavik/naavik-ops.lock flock):

  insert <version>.<pos> "<title>" [--effort E] [--priority HIGH|MEDIUM|LOW]
  defer <task-id> [--by N=1 | --to <new-pos>]
  prioritize <task-id> [--to-priority HIGH|MEDIUM|LOW|unset]
  move <task-id> <new-version>.<new-pos>
  renumber <version>
  rename-release <old> <new>
  bump <type> [--dry-run]

# Status

Wave 1 ships read-only paths (`list`, `next-unblocked`, `check`) wired
through `gh.py` subprocess wrappers; mutating paths emit a structured plan +
exit 2 (NOT_IMPLEMENTED_YET) since the migration runbook (Wave 2) is the
canonical bulk-mutation surface during A.29. A.30 (0.1.1) finishes the
mutating subcommands as part of the Python rewrite.

# Sort key (REV-3)

  release-version ASC → priority DESC (HIGH=3 > MED=2 > LOW=1 > unset=0)
                     → position ASC, ties broken by Issue number
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from naavik_ops import gh
from naavik_ops.lib import NaavikOpsError, jsonl, semver

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUE_MAP_PATH = REPO_ROOT / ".claude" / "github-issue-map.json"
ROADMAP_PATH = REPO_ROOT / "ROADMAP.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
PACKAGE_NIX_PATH = REPO_ROOT / "nix" / "package.nix"
LOCK_PATH = Path(os.path.expanduser("~/.naavik/naavik-ops.lock"))

PRIORITY_RANK = {
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "": 0,
    "UNSET": 0,
}

_TITLE_PREFIX_RE = re.compile(r"^\[(?P<id>[^\]]+)\]\s+(?P<title>.+)$")
_VERSION_HEADER_RE = re.compile(r"^###\s+(?P<version>\d+\.\d+\.\d+)\s+[—–-]\s+(?P<title>.+?)\s*$")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _load_map() -> dict:
    if not ISSUE_MAP_PATH.exists():
        return {}
    return jsonl.read_json(ISSUE_MAP_PATH)


def _priority_rank(p: str | None) -> int:
    return PRIORITY_RANK.get((p or "").upper(), 0)


def _list_release_tasks(version: str) -> list[dict]:
    """Return tasks for `version` from the issue map, sorted REV-3 priority key.

    Reads `.claude/github-issue-map.json:issues` for keys matching
    `<version>.<NN>`. Priority drawn from the same map's `priorities` sub-dict
    if present (populated by Wave 2 migration); else unset.
    """
    data = _load_map()
    issues = data.get("issues") or {}
    priorities = data.get("priorities") or {}
    deps = data.get("deps") or {}

    rows: list[dict] = []
    for task_id, issue_num in issues.items():
        try:
            major, minor, patch, position = semver.parse(task_id)
        except semver.InvalidVersion:
            continue
        if position is None:
            continue
        if semver.format(major, minor, patch) != version:
            continue
        priority = priorities.get(task_id, "")
        blocked_by = (deps.get(task_id) or {}).get("blocked_by") or []
        rows.append(
            {
                "id": task_id,
                "position": position,
                "priority": priority,
                "issue": issue_num,
                "blocked_by": blocked_by,
            }
        )

    rows.sort(
        key=lambda r: (
            -_priority_rank(r.get("priority")),
            r.get("position", 0),
            r.get("issue", 0),
        )
    )
    return rows


def _read_pyproject_version() -> str | None:
    if not PYPROJECT_PATH.exists():
        return None
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    return m.group(1) if m else None


def _read_package_nix_version() -> str | None:
    if not PACKAGE_NIX_PATH.exists():
        return None
    text = PACKAGE_NIX_PATH.read_text(encoding="utf-8")
    m = re.search(r'version\s*=\s*"([^"]+)"\s*;', text)
    return m.group(1) if m else None


# -----------------------------------------------------------------------------
# Read-only commands
# -----------------------------------------------------------------------------


def cmd_list(rest: Sequence[str]) -> int:
    """list <version> [--status <s>] [--include-done] [--json]"""
    if not rest:
        sys.stderr.write("usage: naavik-ops task list <version> [--json]\n")
        return 2

    version = rest[0]
    args = list(rest[1:])
    as_json = "--json" in args

    try:
        semver.parse(version)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e

    rows = _list_release_tasks(version)

    if as_json:
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
        return 0

    if not rows:
        sys.stdout.write(
            f"(no tasks for release {version} in .claude/github-issue-map.json:issues)\n"
        )
        return 0

    sys.stdout.write(f"{'TASK-ID':<14} {'PRI':<8} {'POS':<4} {'ISSUE':<8} BLOCKED-BY\n")
    for r in rows:
        pri = r.get("priority") or "-"
        blocked = ", ".join(r.get("blocked_by") or []) or "-"
        sys.stdout.write(f"{r['id']:<14} {pri:<8} {r['position']:<4} #{r['issue']:<7} {blocked}\n")
    return 0


def cmd_next_unblocked(rest: Sequence[str]) -> int:
    """next-unblocked <version>"""
    if not rest:
        sys.stderr.write("usage: naavik-ops task next-unblocked <version>\n")
        return 2
    version = rest[0]
    try:
        semver.parse(version)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e

    rows = _list_release_tasks(version)
    data = _load_map()
    statuses = data.get("statuses") or {}

    for row in rows:
        # blocked if any blocked_by entry is open (status != 'x' / 'done').
        blocked = False
        for dep_id in row.get("blocked_by") or []:
            dep_status = (statuses.get(dep_id) or "").lower()
            if dep_status not in ("x", "done"):
                blocked = True
                break
        if blocked:
            continue
        sys.stdout.write(f"{row['id']} {row.get('priority') or 'unset'} #{row['issue']}\n")
        return 0

    sys.stdout.write(f"(no unblocked tasks for release {version})\n")
    return 0


def cmd_check(rest: Sequence[str]) -> int:
    """check — lint ROADMAP / map cache / pyproject / package.nix / tags."""
    _ = rest

    issues: list[str] = []

    if not ISSUE_MAP_PATH.exists():
        issues.append(f"map cache missing: {ISSUE_MAP_PATH}")
    if not ROADMAP_PATH.exists():
        issues.append(f"ROADMAP.md missing: {ROADMAP_PATH}")

    pyproject_ver = _read_pyproject_version()
    package_nix_ver = _read_package_nix_version()

    if pyproject_ver is None:
        issues.append(f"pyproject.toml version not parseable at {PYPROJECT_PATH}")
    if package_nix_ver is None:
        issues.append(f"nix/package.nix version not parseable at {PACKAGE_NIX_PATH}")
    if (
        pyproject_ver is not None
        and package_nix_ver is not None
        and pyproject_ver != package_nix_ver
    ):
        issues.append(
            f"version drift: pyproject={pyproject_ver} but nix/package.nix={package_nix_ver}"
        )

    # Schema-validate every issues key in the map.
    data = _load_map()
    for key in data.get("issues") or {}:
        try:
            semver.parse(key)
        except semver.InvalidVersion as e:
            issues.append(f"map cache 'issues' key '{key}' invalid: {e}")

    if issues:
        for line in issues:
            sys.stderr.write(f"check: {line}\n")
        sys.stderr.write(f"check: {len(issues)} issue(s) found\n")
        return 1

    sys.stdout.write(
        f"check: clean (pyproject={pyproject_ver}, nix/package.nix={package_nix_ver})\n"
    )
    return 0


def cmd_sync(rest: Sequence[str]) -> int:
    """sync [--apply] — forward to scripts/gh-project.sh sync.

    During A.29: the legacy sync handles drift between ROADMAP and the Project
    board (Status + legacy Priority field). New 4-level task-ID drift detection
    lands in A.30.
    """
    return gh.cmd_sync(rest)


# -----------------------------------------------------------------------------
# Mutating commands — Wave 1 stubs.
#
# These are not the canonical path during A.29. The Wave 2 migration runbook
# (`.claude/migrations/A.29-phase-renumber.py`) performs the bulk renumber.
# Day-to-day insert/defer/prioritize ops will be wired in A.30 alongside the
# native Python gh rewrite. For now these exit 2 with a clear message.
# -----------------------------------------------------------------------------


def _not_implemented(name: str) -> int:
    sys.stderr.write(
        f"naavik-ops task {name}: not implemented during A.29 transition.\n"
        f"  Wave 2 migration runbook (.claude/migrations/A.29-phase-renumber.py) handles bulk.\n"
        f"  Per-task ops are scoped for A.30 (0.1.1) Python rewrite.\n"
    )
    return 2


def cmd_insert(rest: Sequence[str]) -> int:
    _ = rest
    return _not_implemented("insert")


def cmd_defer(rest: Sequence[str]) -> int:
    _ = rest
    return _not_implemented("defer")


def cmd_prioritize(rest: Sequence[str]) -> int:
    _ = rest
    return _not_implemented("prioritize")


def cmd_move(rest: Sequence[str]) -> int:
    _ = rest
    return _not_implemented("move")


def cmd_renumber(rest: Sequence[str]) -> int:
    _ = rest
    return _not_implemented("renumber")


def cmd_rename_release(rest: Sequence[str]) -> int:
    _ = rest
    return _not_implemented("rename-release")


def cmd_bump(rest: Sequence[str]) -> int:
    """bump <type> [--dry-run]

    Read-only preview: parses the current pyproject version + bumps per `type`.
    Does NOT mutate any file (that's the `release cut` ceremony's job).
    """
    if not rest:
        sys.stderr.write("usage: naavik-ops task bump <major|minor|patch> [--dry-run]\n")
        return 2
    kind = rest[0]
    if kind not in ("major", "minor", "patch"):
        sys.stderr.write(f"task bump: kind must be major|minor|patch (got '{kind}')\n")
        return 2

    pyproject_ver = _read_pyproject_version() or "0.0.0"
    try:
        next_ver = semver.bump(pyproject_ver, kind)
    except (semver.InvalidVersion, ValueError) as e:
        raise NaavikOpsError(str(e)) from e

    sys.stdout.write(
        f"current: {pyproject_ver}\n"
        f"after {kind} bump: {next_ver}\n"
        f"(use `naavik-ops release cut {next_ver}` to commit + tag)\n"
    )
    return 0
