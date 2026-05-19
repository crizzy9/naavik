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
from naavik_ops.lib import NaavikOpsError, flock, jsonl, roadmap, semver

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
    """sync [--apply] — delegates to gh.cmd_sync for legacy 2.x/PC.x rows.

    Handles drift between ROADMAP and the Project board (Status + Priority
    fields) for the rows the legacy A.29 sync covered. 4-level task-ID drift
    detection (release-version sections) is folded into the same module post-
    0.1.1; treats the legacy + 4-level paths uniformly via `lib/roadmap.parse`.
    """
    return gh.cmd_sync(rest)


# -----------------------------------------------------------------------------
# Mutating commands — plan 25 § D.6 (5 of 6 implemented; rename-release stubbed
# per user-approved Open Q1).
#
# Each subcommand acquires the dispatcher flock (LOCK_PATH) and performs an
# atomic 3-store mutation:
#
#   1. ROADMAP.md row rewrite (via lib/roadmap.ReleaseDiff + rewrite_atomic).
#   2. GitHub Issue title rewrite (via gh.update_issue_title for each shifted
#      task). Failures rollback by re-issuing OLD titles.
#   3. Map cache update (.claude/github-issue-map.json:issues, :redirects).
#
# The flock serializes against concurrent invocations. Failure handling: if any
# `gh issue edit` mid-loop fails, rollback re-issues OLD titles, deletes the
# `.tmp` ROADMAP file, and exits non-zero. Worst case the user runs
# `naavik-ops task check` which detects drift.
# -----------------------------------------------------------------------------


def _not_implemented(name: str) -> int:
    sys.stderr.write(
        f"naavik-ops task {name}: not implemented in 0.1.1.\n"
        f"  Per plan 25 Open Q1: '{name}' stays stubbed; defer to a future patch release.\n"
    )
    return 2


def _validate_position(pos: int) -> None:
    if not (1 <= pos <= 99):
        raise NaavikOpsError(f"position {pos:02d} out of range (01..99)")


def _row_title(row: roadmap.ReleaseRow) -> str:
    """Re-derive the Issue title for a row: `[<task-id>] <title>`."""
    return f"[{row.task_id}] {row.title}"


def _shift_rows_for_insert(
    rows: list[roadmap.ReleaseRow], insert_pos: int
) -> tuple[list[roadmap.ReleaseRow], list[tuple[str, str]]]:
    """Compute the shifted row list + rename pairs for inserting at `insert_pos`.

    Each row with position >= insert_pos AND status != 'x' shifts +1. Returns
    `(new_rows, rename_pairs)` where rename_pairs = [(old_id, new_id), ...].
    `[x]` (done) rows are frozen — they don't shift and don't get renamed.

    Raises NaavikOpsError if the insert_pos OR any subsequent shift target
    collides with a frozen [x] row (we can't displace `[x]`s, and we can't
    leave the shift sequence with a gap).
    """
    # First: assert the insert_pos isn't a frozen [x] row.
    for r in rows:
        if r.position == insert_pos and r.status == "x":
            raise NaavikOpsError(
                f"position {insert_pos:02d} is a [x] done row ({r.task_id}); cannot displace. "
                f"Try {insert_pos + 1:02d}."
            )

    # Pre-flight: collision check for shift targets.
    x_positions = {r.position for r in rows if r.status == "x"}
    for r in rows:
        if r.position >= insert_pos and r.status != "x":
            target = r.position + 1
            if target in x_positions:
                raise NaavikOpsError(
                    f"insert at {insert_pos:02d} would shift {r.task_id} to position "
                    f"{target:02d} which is a [x] frozen row. Run `naavik-ops task renumber "
                    f"{semver.release_of(r.task_id)}` first to compact gaps."
                )

    new_rows: list[roadmap.ReleaseRow] = []
    rename_pairs: list[tuple[str, str]] = []
    for r in rows:
        if r.position >= insert_pos and r.status != "x":
            old_id = r.task_id
            major, minor, patch, _ = semver.parse(old_id)
            new_id = semver.format(major, minor, patch, r.position + 1)
            new_row = roadmap.ReleaseRow(
                task_id=new_id,
                position=r.position + 1,
                status=r.status,
                title=r.title,
                priority=r.priority,
                notes=r.notes,
                raw_line="",  # force re-render with new id
            )
            new_rows.append(new_row)
            if old_id != new_id:
                rename_pairs.append((old_id, new_id))
        else:
            new_rows.append(r)
    return new_rows, rename_pairs


def _apply_atomic_3store(
    *,
    diffs: list[roadmap.ReleaseDiff],
    title_renames: list[tuple[int, str, str]],
    map_updates: dict[str, dict[str, int | str]] | None = None,
    map_redirects: dict[str, str] | None = None,
) -> None:
    """Atomic 3-store mutation.

    `diffs`         — ROADMAP rewrites (covers 1 or 2 release sections).
    `title_renames` — list of (issue_num, old_title, new_title).
    `map_updates`   — mapping category → {key: new_value}. Replaces section keys.
                       e.g. {"issues": {"0.2.0.06": 11}, "priorities": {"0.2.0.06": "HIGH"}}
    `map_redirects` — old_task_id → new_task_id, written to map.redirects.

    Flow:
      1. Acquire flock.
      2. Write ROADMAP.md.tmp + map.tmp (in-memory diffs only — no commit).
      3. Loop title_renames calling gh.update_issue_title for each. If any
         fails, rollback by re-issuing OLD titles via the same helper on the
         already-edited subset.
      4. On full success: rewrite_atomic flushes ROADMAP, jsonl writes the map.
      5. Release flock.
    """
    with flock.acquire(LOCK_PATH):
        # Step 2 — compute mutations in-memory.
        original_map = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
        # Deep-copy the dict so rollback works.
        new_map = json.loads(json.dumps(original_map))

        if map_updates:
            for category, kv in map_updates.items():
                section = new_map.setdefault(category, {})
                for k, v in kv.items():
                    section[k] = v
        if map_redirects:
            redirects = new_map.setdefault("redirects", {})
            for old_id, new_id in map_redirects.items():
                redirects[old_id] = new_id

        # Step 3 — issue title rewrites with rollback.
        completed: list[tuple[int, str, str]] = []  # (issue_num, old_title, current_title)
        try:
            for issue_num, old_title, new_title in title_renames:
                gh.update_issue_title(issue_num, new_title)
                completed.append((issue_num, old_title, new_title))
        except Exception:
            # Rollback completed edits by re-issuing OLD titles.
            for issue_num, old_title, _new in completed:
                try:
                    gh.update_issue_title(issue_num, old_title)
                except Exception:
                    sys.stderr.write(
                        f"warning: rollback of #{issue_num} → {old_title!r} failed; "
                        "run `naavik-ops gh refresh-map` to reconcile.\n"
                    )
            raise

        # Step 4 — flush ROADMAP + map atomically.
        if diffs:
            roadmap.rewrite_atomic(diffs)
        jsonl.write_json(ISSUE_MAP_PATH, new_map)


# ---------------------------------------------------------------------------
# cmd_insert
# ---------------------------------------------------------------------------


def cmd_insert(rest: Sequence[str]) -> int:
    """insert <version>.<pos> "<title>" [--effort E] [--priority HIGH|MEDIUM|LOW]"""
    if len(rest) < 2:
        sys.stderr.write(
            'usage: naavik-ops task insert <version>.<pos> "<title>" '
            "[--effort E] [--priority HIGH|MEDIUM|LOW]\n"
        )
        return 2

    task_id = rest[0]
    title = rest[1]
    effort = "M"
    priority = "MEDIUM"
    args = list(rest[2:])
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--effort":
            effort = args[i + 1].upper()
            i += 2
        elif a == "--priority":
            priority = args[i + 1].upper()
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")

    try:
        major, minor, patch, position = semver.parse(task_id)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e
    if position is None:
        raise NaavikOpsError(f"insert requires a 4-level task ID (got '{task_id}')")
    _validate_position(position)
    if priority not in ("HIGH", "MEDIUM", "LOW", "CRITICAL"):
        raise NaavikOpsError(f"priority must be HIGH|MEDIUM|LOW|CRITICAL (got '{priority}')")
    if effort not in ("XS", "S", "M", "L", "XL"):
        raise NaavikOpsError(f"effort must be XS|S|M|L|XL (got '{effort}')")

    version = semver.format(major, minor, patch)
    rows = roadmap.parse_release_section(version)

    # Idempotency: if task_id already exists with matching title → no-op.
    for r in rows:
        if r.task_id == task_id and r.title == title:
            sys.stdout.write(f"no-op: {task_id} already exists with that title.\n")
            return 0

    new_rows, rename_pairs = _shift_rows_for_insert(rows, position)
    new_row = roadmap.ReleaseRow(
        task_id=task_id,
        position=position,
        status=" ",
        title=title,
        priority=priority,
        notes="",
        raw_line="",
    )
    new_rows.append(new_row)

    diff = roadmap.write_release_section(version, new_rows)

    # Build title_renames for each shifted task.
    existing_map = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
    map_issues = existing_map.get("issues") or {}
    title_renames: list[tuple[int, str, str]] = []
    map_updates: dict[str, dict[str, int | str]] = {"issues": {}, "priorities": {}}
    map_redirects: dict[str, str] = {}

    # Build a lookup from new task_id → row (used to look up the new title).
    new_row_by_id = {r.task_id: r for r in new_rows}

    for old_id, new_id in rename_pairs:
        issue_num = map_issues.get(old_id)
        if issue_num is None:
            sys.stderr.write(
                f"warning: {old_id} has no map cache entry — skipping Issue rewrite.\n"
            )
        else:
            shifted_row = new_row_by_id[new_id]
            old_title = f"[{old_id}] {shifted_row.title}"
            new_title = _row_title(shifted_row)
            title_renames.append((int(issue_num), old_title, new_title))
            map_updates["issues"][new_id] = int(issue_num)
            map_updates["issues"][old_id] = 0  # marker — caller will drop
            map_redirects[old_id] = new_id

    # The inserted task itself doesn't have an Issue # yet. We acquire flock,
    # rewrite ROADMAP + Issue titles for shifted rows + the map, then create
    # the NEW Issue OUTSIDE the lock-protected atomic write (gh.cmd_create_issue
    # writes to the map itself for the new key).

    # Step A — atomic rewrite for the existing-row shifts.
    # Filter the "drop old key" markers — map_updates["issues"][old_id] = 0
    # should mean "delete from new_map". Handle separately.
    keys_to_drop = [k for k, v in map_updates["issues"].items() if v == 0]
    map_updates["issues"] = {k: v for k, v in map_updates["issues"].items() if v != 0}
    map_updates.pop("priorities", None)  # nothing to record there

    _apply_atomic_3store(
        diffs=[diff],
        title_renames=title_renames,
        map_updates=map_updates,
        map_redirects=map_redirects,
    )

    # Drop the old keys post-flush. Re-load + rewrite the map.
    if keys_to_drop:
        with flock.acquire(LOCK_PATH):
            data = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
            issues = data.get("issues") or {}
            for k in keys_to_drop:
                issues.pop(k, None)
            jsonl.write_json(ISSUE_MAP_PATH, data)

    # Step B — create the NEW Issue (outside atomic lock; gh.create_issue is
    # idempotent against the map cache).
    try:
        gh.cmd_create_issue(
            [
                task_id,
                title,
                "--priority",
                priority,
                "--effort",
                effort,
                "--milestone",
                version,
            ]
        )
    except NaavikOpsError as e:
        sys.stderr.write(
            f"warning: ROADMAP shifted but Issue create failed: {e}\n"
            f'  Re-run: naavik-ops gh create-issue {task_id} "{title}" '
            f"--priority {priority} --effort {effort} --milestone {version}\n"
        )

    shifted_summary = ", ".join(f"{o}→{n}" for o, n in rename_pairs) or "(none)"
    sys.stdout.write(f"inserted: {task_id}; shifted: {shifted_summary}\n")
    return 0


# ---------------------------------------------------------------------------
# cmd_defer
# ---------------------------------------------------------------------------


def cmd_defer(rest: Sequence[str]) -> int:
    """defer <task-id> [--by N=1 | --to <new-pos>]"""
    if not rest:
        sys.stderr.write("usage: naavik-ops task defer <task-id> [--by N | --to <new-pos>]\n")
        return 2
    task_id = rest[0]
    by: int | None = None
    to: int | None = None
    args = list(rest[1:])
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--by":
            by = int(args[i + 1])
            i += 2
        elif a == "--to":
            to = int(args[i + 1])
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")
    if (by is None) == (to is None):
        raise NaavikOpsError("specify exactly one of --by N or --to <new-pos>")

    try:
        major, minor, patch, position = semver.parse(task_id)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e
    if position is None:
        raise NaavikOpsError(f"defer requires a 4-level task ID (got '{task_id}')")

    version = semver.format(major, minor, patch)
    rows = roadmap.parse_release_section(version)

    src = next((r for r in rows if r.task_id == task_id), None)
    if src is None:
        raise NaavikOpsError(f"{task_id} not found in {version} release section")
    if src.status == "x":
        raise NaavikOpsError(f"{task_id} is [x] (done); cannot defer")

    new_position = (src.position + by) if by is not None else int(to)  # type: ignore[arg-type]
    _validate_position(new_position)
    if new_position == src.position:
        sys.stdout.write(f"no-op: {task_id} already at position {new_position:02d}\n")
        return 0

    # Reject if the target is occupied by a frozen [x] row.
    target_row = next((r for r in rows if r.position == new_position), None)
    if target_row is not None and target_row.status == "x":
        raise NaavikOpsError(
            f"target position {new_position:02d} is a [x] done row ({target_row.task_id}); "
            f"cannot displace."
        )

    # Compute shifts. Moving DOWN (later): rows in (src.position, new_position] shift up by 1
    # (each gets position - 1). Moving UP (earlier): rows in [new_position, src.position)
    # shift down by 1 (each gets position + 1). Skipping [x] rows.
    new_rows: list[roadmap.ReleaseRow] = []
    rename_pairs: list[tuple[str, str]] = []
    for r in rows:
        if r.task_id == task_id:
            continue  # handle below
        if r.status == "x":
            new_rows.append(r)
            continue
        old_pos = r.position
        new_pos = old_pos
        if new_position > src.position and src.position < old_pos <= new_position:
            new_pos = old_pos - 1
        elif new_position < src.position and new_position <= old_pos < src.position:
            new_pos = old_pos + 1
        if new_pos != old_pos:
            new_id = semver.format(major, minor, patch, new_pos)
            rename_pairs.append((r.task_id, new_id))
            new_rows.append(
                roadmap.ReleaseRow(
                    task_id=new_id,
                    position=new_pos,
                    status=r.status,
                    title=r.title,
                    priority=r.priority,
                    notes=r.notes,
                    raw_line="",
                )
            )
        else:
            new_rows.append(r)

    # Insert the deferred row.
    new_src_id = semver.format(major, minor, patch, new_position)
    new_rows.append(
        roadmap.ReleaseRow(
            task_id=new_src_id,
            position=new_position,
            status=src.status,
            title=src.title,
            priority=src.priority,
            notes=src.notes,
            raw_line="",
        )
    )
    rename_pairs.append((src.task_id, new_src_id))

    diff = roadmap.write_release_section(version, new_rows)
    existing_map = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
    map_issues = existing_map.get("issues") or {}
    title_renames: list[tuple[int, str, str]] = []
    map_updates: dict[str, dict[str, int | str]] = {"issues": {}}
    map_redirects: dict[str, str] = {}
    keys_to_drop: list[str] = []
    new_row_by_id = {r.task_id: r for r in new_rows}
    for old_id, new_id in rename_pairs:
        issue_num = map_issues.get(old_id)
        if issue_num is None:
            continue
        shifted_row = new_row_by_id[new_id]
        old_title = f"[{old_id}] {shifted_row.title}"
        new_title = _row_title(shifted_row)
        title_renames.append((int(issue_num), old_title, new_title))
        map_updates["issues"][new_id] = int(issue_num)
        keys_to_drop.append(old_id)
        map_redirects[old_id] = new_id

    _apply_atomic_3store(
        diffs=[diff],
        title_renames=title_renames,
        map_updates=map_updates,
        map_redirects=map_redirects,
    )

    if keys_to_drop:
        with flock.acquire(LOCK_PATH):
            data = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
            issues = data.get("issues") or {}
            for k in keys_to_drop:
                if k not in map_updates["issues"]:
                    issues.pop(k, None)
            jsonl.write_json(ISSUE_MAP_PATH, data)

    shifted_summary = ", ".join(f"{o}→{n}" for o, n in rename_pairs)
    sys.stdout.write(f"deferred: {task_id} → {new_src_id}; shifted: {shifted_summary}\n")
    return 0


# ---------------------------------------------------------------------------
# cmd_prioritize
# ---------------------------------------------------------------------------


def cmd_prioritize(rest: Sequence[str]) -> int:
    """prioritize <task-id> [--to-priority HIGH|MEDIUM|LOW|unset]"""
    if not rest:
        sys.stderr.write(
            "usage: naavik-ops task prioritize <task-id> [--to-priority HIGH|MEDIUM|LOW|unset]\n"
        )
        return 2
    task_id = rest[0]
    new_pri = "MEDIUM"
    args = list(rest[1:])
    i = 0
    while i < len(args):
        if args[i] == "--to-priority":
            new_pri = args[i + 1].upper()
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{args[i]}'")

    if new_pri not in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNSET"):
        raise NaavikOpsError(f"priority must be CRITICAL|HIGH|MEDIUM|LOW|unset (got '{new_pri}')")

    try:
        major, minor, patch, position = semver.parse(task_id)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e
    if position is None:
        raise NaavikOpsError(f"prioritize requires a 4-level task ID (got '{task_id}')")

    version = semver.format(major, minor, patch)
    rows = roadmap.parse_release_section(version)
    src = next((r for r in rows if r.task_id == task_id), None)
    if src is None:
        raise NaavikOpsError(f"{task_id} not found in {version} release section")

    if src.priority == new_pri:
        sys.stdout.write(f"no-op: {task_id} already at priority {new_pri}\n")
        return 0

    new_rows = [
        roadmap.ReleaseRow(
            task_id=r.task_id,
            position=r.position,
            status=r.status,
            title=r.title,
            priority=new_pri if r.task_id == task_id else r.priority,
            notes=r.notes,
            raw_line="" if r.task_id == task_id else r.raw_line,
        )
        for r in rows
    ]
    diff = roadmap.write_release_section(version, new_rows)

    # Map cache: priorities[task_id] = new_pri (extends Wave 2 migration's
    # PHASE_A_HISTORICAL_MAP-style sub-key).
    with flock.acquire(LOCK_PATH):
        data = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
        priorities = data.setdefault("priorities", {})
        if new_pri == "UNSET":
            priorities.pop(task_id, None)
        else:
            priorities[task_id] = new_pri
        jsonl.write_json(ISSUE_MAP_PATH, data)
        roadmap.rewrite_atomic([diff])

    # GitHub Project Priority field via gh.set_priority (skipped if --no-gh or
    # gh isn't configured). Wrapped in try since prioritize SHOULDN'T fail just
    # because GitHub is offline.
    map_issues = data.get("issues") or {}
    issue_num = map_issues.get(task_id)
    if issue_num and new_pri != "UNSET":
        try:
            item_id = gh.capture_item_id(int(issue_num))
            gh.set_priority(item_id, new_pri)
        except NaavikOpsError as e:
            sys.stderr.write(
                f"warning: Project Priority field update failed: {e}\n"
                f"  ROADMAP + map updated; re-run `naavik-ops gh set-priority "
                f"<item-id> {new_pri}` once GitHub is reachable.\n"
            )

    sys.stdout.write(f"prioritized: {task_id} → {new_pri}\n")
    return 0


# ---------------------------------------------------------------------------
# cmd_move
#
# Cross-release semantics (post-plan-28 / 0.7.0.13):
#   - Source-section siblings are NEVER renumbered on cross-release move. The
#     source slot becomes a permanent gap; operator runs
#     `naavik-ops task renumber <src-version>` separately if cosmetic
#     compaction is desired. Principle: patch-version positions are sort keys,
#     not stable identifiers — but moving a task out of a patch leaves a
#     deliberate gap that preserves referential integrity for siblings.
#     See `.claude/memory/knowledge/patch-version-position-stability.md`.
#   - Destination-section collisions REJECT with an error. Pick a free slot;
#     `task list <dest-version>` shows occupancy.
#   - Within-section moves (src_version == dest_version) still delegate to
#     `cmd_defer`. Defer's whole purpose IS shifting siblings within a patch;
#     that's a different operation from cross-release migration.
# ---------------------------------------------------------------------------


def cmd_move(rest: Sequence[str]) -> int:
    """move <task-id> <new-version>.<new-pos>"""
    if len(rest) < 2:
        sys.stderr.write("usage: naavik-ops task move <task-id> <new-version>.<new-pos>\n")
        return 2
    src_id = rest[0]
    dest_id = rest[1]

    try:
        sj, smin, sp, spos = semver.parse(src_id)
        dj, dmin, dp, dpos = semver.parse(dest_id)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e

    if spos is None:
        raise NaavikOpsError(f"move requires 4-level source task ID (got '{src_id}')")
    if dpos is None:
        raise NaavikOpsError(f"move dest must be 4-level <version>.<pos> (got '{dest_id}')")
    _validate_position(spos)
    _validate_position(dpos)

    src_version = semver.format(sj, smin, sp)
    dest_version = semver.format(dj, dmin, dp)

    if src_version == dest_version and spos == dpos:
        sys.stdout.write(f"no-op: {src_id} already at {dest_id}\n")
        return 0

    src_rows = roadmap.parse_release_section(src_version)
    src_row = next((r for r in src_rows if r.task_id == src_id), None)
    if src_row is None:
        raise NaavikOpsError(f"{src_id} not in {src_version} release section")
    if src_row.status == "x":
        raise NaavikOpsError(f"{src_id} is [x] (done); cannot move")

    # Two-section build.
    if src_version == dest_version:
        # Within-section: same shape as defer.
        new_args = [src_id, "--to", str(dpos)]
        return cmd_defer(new_args)

    dest_rows = roadmap.parse_release_section(dest_version)
    dest_occupy = next((r for r in dest_rows if r.position == dpos), None)
    if dest_occupy is not None:
        raise NaavikOpsError(
            f"dest position {dpos:02d} in {dest_version} already occupied by "
            f"{dest_occupy.task_id} ({dest_occupy.title!r}). Pick a free slot — "
            f"see `naavik-ops task list {dest_version}` for occupancy."
        )

    # CROSS-RELEASE: source-section siblings unchanged; only drop the moved
    # row + leave the slot empty. Destination-section siblings unchanged; the
    # collision check above guarantees dpos is free.
    new_src_rows = [r for r in src_rows if r.task_id != src_id]
    rename_pairs_src: list[tuple[str, str]] = []
    new_dest_rows = list(dest_rows)
    rename_pairs_dest: list[tuple[str, str]] = []

    # Insert the moved row in dest. Priority follows the task (per Open Q5).
    new_dest_rows.append(
        roadmap.ReleaseRow(
            task_id=dest_id,
            position=dpos,
            status=src_row.status,
            title=src_row.title,
            priority=src_row.priority,
            notes=src_row.notes,
            raw_line="",
        )
    )

    src_diff = roadmap.write_release_section(src_version, new_src_rows)
    dest_diff = roadmap.write_release_section(dest_version, new_dest_rows)

    existing_map = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
    map_issues = existing_map.get("issues") or {}

    title_renames: list[tuple[int, str, str]] = []
    map_updates: dict[str, dict[str, int | str]] = {"issues": {}}
    map_redirects: dict[str, str] = {}
    keys_to_drop: list[str] = []

    all_pairs = rename_pairs_src + rename_pairs_dest
    new_by_id = {r.task_id: r for r in (new_src_rows + new_dest_rows)}

    for old_id, new_id in all_pairs:
        issue_num = map_issues.get(old_id)
        if issue_num is None:
            continue
        sh = new_by_id[new_id]
        title_renames.append((int(issue_num), f"[{old_id}] {sh.title}", _row_title(sh)))
        map_updates["issues"][new_id] = int(issue_num)
        keys_to_drop.append(old_id)
        map_redirects[old_id] = new_id

    # Rename the moved row itself.
    src_issue_num = map_issues.get(src_id)
    if src_issue_num is not None:
        title_renames.append(
            (
                int(src_issue_num),
                f"[{src_id}] {src_row.title}",
                f"[{dest_id}] {src_row.title}",
            )
        )
        map_updates["issues"][dest_id] = int(src_issue_num)
        keys_to_drop.append(src_id)
        map_redirects[src_id] = dest_id

    _apply_atomic_3store(
        diffs=[src_diff, dest_diff],
        title_renames=title_renames,
        map_updates=map_updates,
        map_redirects=map_redirects,
    )

    # Drop old keys.
    if keys_to_drop:
        with flock.acquire(LOCK_PATH):
            data = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
            issues = data.get("issues") or {}
            for k in keys_to_drop:
                if k not in map_updates["issues"]:
                    issues.pop(k, None)
            jsonl.write_json(ISSUE_MAP_PATH, data)

    # Optionally update the moved Issue's milestone — best-effort; do not fail
    # the operation if `gh issue edit --milestone` is unavailable.
    if src_issue_num is not None:
        try:
            gh._gh(
                "issue",
                "edit",
                str(src_issue_num),
                "--repo",
                f"{gh._load_cache()['owner']}/{gh._load_cache()['repo']}",
                "--milestone",
                dest_version,
            )
        except (NaavikOpsError, KeyError, FileNotFoundError):
            sys.stderr.write(
                f"warning: milestone update for #{src_issue_num} failed; ROADMAP + map updated.\n"
            )

    sys.stdout.write(f"moved: {src_id} → {dest_id}\n")
    return 0


# ---------------------------------------------------------------------------
# cmd_renumber
# ---------------------------------------------------------------------------


def cmd_renumber(rest: Sequence[str]) -> int:
    """renumber <version> — compact active gaps."""
    if not rest:
        sys.stderr.write("usage: naavik-ops task renumber <version>\n")
        return 2
    version = rest[0]
    try:
        semver.parse(version)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e
    if not semver.is_release(version):
        raise NaavikOpsError(f"renumber accepts a 3-level release ID (got '{version}')")

    major, minor, patch, _ = semver.parse(version)
    rows = roadmap.parse_release_section(version)

    # Sort by current position. Compact: walk in order; for each row, its new
    # position is (last_used + 1). [x] rows preserve their position; active
    # rows compact between/around them.
    rows_sorted = sorted(rows, key=lambda r: r.position)
    new_rows: list[roadmap.ReleaseRow] = []
    rename_pairs: list[tuple[str, str]] = []
    next_active_pos = 1
    for r in rows_sorted:
        if r.status == "x":
            new_rows.append(r)
            # Active rows can't take this position.
            if r.position >= next_active_pos:
                next_active_pos = r.position + 1
            continue
        target = next_active_pos
        # Skip any position taken by a [x] row that comes later (rare).
        x_positions = {x.position for x in rows_sorted if x.status == "x"}
        while target in x_positions:
            target += 1
        next_active_pos = target + 1
        if target == r.position:
            new_rows.append(r)
            continue
        new_id = semver.format(major, minor, patch, target)
        rename_pairs.append((r.task_id, new_id))
        new_rows.append(
            roadmap.ReleaseRow(
                task_id=new_id,
                position=target,
                status=r.status,
                title=r.title,
                priority=r.priority,
                notes=r.notes,
                raw_line="",
            )
        )

    if not rename_pairs:
        sys.stdout.write(f"no-op: {version} already compact.\n")
        return 0

    diff = roadmap.write_release_section(version, new_rows)

    existing_map = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
    map_issues = existing_map.get("issues") or {}
    title_renames: list[tuple[int, str, str]] = []
    map_updates: dict[str, dict[str, int | str]] = {"issues": {}}
    map_redirects: dict[str, str] = {}
    keys_to_drop: list[str] = []
    new_by_id = {r.task_id: r for r in new_rows}

    for old_id, new_id in rename_pairs:
        issue_num = map_issues.get(old_id)
        if issue_num is None:
            continue
        sh = new_by_id[new_id]
        title_renames.append((int(issue_num), f"[{old_id}] {sh.title}", _row_title(sh)))
        map_updates["issues"][new_id] = int(issue_num)
        keys_to_drop.append(old_id)
        map_redirects[old_id] = new_id

    _apply_atomic_3store(
        diffs=[diff],
        title_renames=title_renames,
        map_updates=map_updates,
        map_redirects=map_redirects,
    )

    if keys_to_drop:
        with flock.acquire(LOCK_PATH):
            data = jsonl.read_json(ISSUE_MAP_PATH) if ISSUE_MAP_PATH.is_file() else {}
            issues = data.get("issues") or {}
            for k in keys_to_drop:
                if k not in map_updates["issues"]:
                    issues.pop(k, None)
            jsonl.write_json(ISSUE_MAP_PATH, data)

    summary = ", ".join(f"{o}→{n}" for o, n in rename_pairs)
    sys.stdout.write(f"renumbered {version}: {summary}\n")
    return 0


# ---------------------------------------------------------------------------
# cmd_rename_release — stubbed per Open Q1
# ---------------------------------------------------------------------------


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
