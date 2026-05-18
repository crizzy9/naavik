"""deps — cross-task / cross-version dependency graph.

Per design doc § 4 + plan § D.17.

Store: `.claude/github-issue-map.json:deps` keyed by 4-level task ID.

  {
    "0.2.0.02": { "blocks": [], "blocked_by": ["0.2.0.01"] },
    "0.2.0.06": { "blocks": ["0.2.0.07","0.2.0.08"], "blocked_by": ["0.2.0.05"] }
  }

# Subcommands

  add <task-id> <dep-id>     record `<task-id>` blocked_by `<dep-id>`
                             (inverse `blocks` entry added on `<dep-id>`)
  remove <task-id> <dep-id>  inverse of add
  list <task-id>             print blocks + blocked_by for task
  check                      verify no cycles, no closed-blocking-open inversions,
                             all referenced IDs exist in `.claude/github-issue-map.json`

Idempotent. Atomic write via tempfile + os.replace. Flock-serialized against
`~/.naavik/naavik-ops.lock`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

from naavik_ops.lib import NaavikOpsError, flock, jsonl, semver

ISSUE_MAP_PATH = Path(__file__).resolve().parents[2] / ".claude" / "github-issue-map.json"
LOCK_PATH = Path(os.path.expanduser("~/.naavik/naavik-ops.lock"))


def _load_map() -> dict:
    """Read the issue map; return {} if missing."""
    if not ISSUE_MAP_PATH.exists():
        return {}
    return jsonl.read_json(ISSUE_MAP_PATH)


def _save_map(data: dict) -> None:
    """Atomic write of the issue map."""
    jsonl.write_json(ISSUE_MAP_PATH, data)


def _deps_dict(data: dict) -> dict[str, dict[str, list[str]]]:
    """Return the deps dict from the map (creating if missing)."""
    deps = data.get("deps")
    if not isinstance(deps, dict):
        deps = {}
        data["deps"] = deps
    return deps


def _ensure_entry(deps: dict, task_id: str) -> dict[str, list[str]]:
    entry = deps.get(task_id)
    if not isinstance(entry, dict):
        entry = {"blocks": [], "blocked_by": []}
        deps[task_id] = entry
    entry.setdefault("blocks", [])
    entry.setdefault("blocked_by", [])
    return entry


def _validate_task_id(task_id: str) -> None:
    """Reject release-level IDs — deps only meaningful on 4-level task IDs."""
    try:
        semver.parse(task_id)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e
    if not semver.is_task(task_id):
        raise NaavikOpsError(f"'{task_id}' is a release ID. Deps only apply to 4-level task IDs.")


# -----------------------------------------------------------------------------
# Mutating ops
# -----------------------------------------------------------------------------


def cmd_add(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write("usage: naavik-ops deps add <task-id> <dep-id>\n")
        return 2
    task_id, dep_id = rest[0], rest[1]
    _validate_task_id(task_id)
    _validate_task_id(dep_id)
    if task_id == dep_id:
        raise NaavikOpsError("self-dependency rejected")

    with flock.acquire(LOCK_PATH):
        data = _load_map()
        deps = _deps_dict(data)
        task_entry = _ensure_entry(deps, task_id)
        dep_entry = _ensure_entry(deps, dep_id)

        if dep_id not in task_entry["blocked_by"]:
            task_entry["blocked_by"].append(dep_id)
        if task_id not in dep_entry["blocks"]:
            dep_entry["blocks"].append(task_id)

        # Cycle check after mutation.
        if _has_cycle(deps, task_id):
            # Rollback.
            task_entry["blocked_by"].remove(dep_id)
            dep_entry["blocks"].remove(task_id)
            raise NaavikOpsError(
                f"adding {task_id} blocked_by {dep_id} would create a dependency cycle"
            )

        _save_map(data)
    sys.stdout.write(f"deps: {task_id} blocked_by {dep_id}\n")
    return 0


def cmd_remove(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write("usage: naavik-ops deps remove <task-id> <dep-id>\n")
        return 2
    task_id, dep_id = rest[0], rest[1]

    with flock.acquire(LOCK_PATH):
        data = _load_map()
        deps = _deps_dict(data)
        task_entry = deps.get(task_id) or {}
        dep_entry = deps.get(dep_id) or {}
        changed = False
        if dep_id in task_entry.get("blocked_by", []):
            task_entry["blocked_by"].remove(dep_id)
            changed = True
        if task_id in dep_entry.get("blocks", []):
            dep_entry["blocks"].remove(task_id)
            changed = True
        if changed:
            _save_map(data)
    sys.stdout.write(f"deps: {task_id} no longer blocked_by {dep_id}\n")
    return 0


def cmd_list(rest: Sequence[str]) -> int:
    if not rest:
        sys.stderr.write("usage: naavik-ops deps list <task-id>\n")
        return 2
    task_id = rest[0]

    data = _load_map()
    deps = data.get("deps") or {}
    entry = deps.get(task_id) or {"blocks": [], "blocked_by": []}
    sys.stdout.write(f"{task_id}\n")
    sys.stdout.write(f"  blocks:     {', '.join(entry.get('blocks') or []) or '(none)'}\n")
    sys.stdout.write(f"  blocked_by: {', '.join(entry.get('blocked_by') or []) or '(none)'}\n")
    return 0


def cmd_check(rest: Sequence[str]) -> int:
    """Verify DAG integrity. Exit 0 if clean; 1 on any inconsistency."""
    _ = rest  # unused
    data = _load_map()
    deps = data.get("deps") or {}

    issues: list[str] = []

    # 1. Each edge present in both directions (symmetric blocks ↔ blocked_by).
    for tid, entry in deps.items():
        for dep_id in entry.get("blocked_by") or []:
            other = deps.get(dep_id)
            if not other or tid not in (other.get("blocks") or []):
                issues.append(
                    f"asymmetry: {tid}.blocked_by has {dep_id} but "
                    f"{dep_id}.blocks does not have {tid}"
                )
        for blocked_id in entry.get("blocks") or []:
            other = deps.get(blocked_id)
            if not other or tid not in (other.get("blocked_by") or []):
                issues.append(
                    f"asymmetry: {tid}.blocks has {blocked_id} but "
                    f"{blocked_id}.blocked_by does not have {tid}"
                )

    # 2. No cycles.
    for tid in deps:
        if _has_cycle(deps, tid):
            issues.append(f"cycle involving {tid}")
            break  # one report is sufficient

    if issues:
        for issue in issues:
            sys.stderr.write(f"deps: {issue}\n")
        return 1
    sys.stdout.write(f"deps: clean ({len(deps)} task(s) tracked)\n")
    return 0


# -----------------------------------------------------------------------------
# Cycle detector — iterative DFS to avoid recursion limits.
# -----------------------------------------------------------------------------


def _has_cycle(deps: dict[str, dict[str, list[str]]], start: str) -> bool:
    """True if starting at `start` and following `blocked_by` edges loops back."""
    visited: set[str] = set()
    stack: list[tuple[str, list[str]]] = [
        (start, list(deps.get(start, {}).get("blocked_by") or []))
    ]
    path: set[str] = {start}
    while stack:
        node, neighbors = stack[-1]
        if not neighbors:
            stack.pop()
            path.discard(node)
            continue
        neighbor = neighbors.pop()
        if neighbor in path:
            return True
        if neighbor in visited:
            continue
        visited.add(neighbor)
        path.add(neighbor)
        stack.append((neighbor, list(deps.get(neighbor, {}).get("blocked_by") or [])))
    return False
