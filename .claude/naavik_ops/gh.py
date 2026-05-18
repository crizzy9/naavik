"""gh — GitHub Project + Issue ops.

During A.29 transition: subprocess wrappers around `scripts/gh-project.sh`.
A.30 (0.1.1): native Python rewrite.

The wrapper is intentionally thin — no business logic, just argument
forwarding + error translation. The legacy bash script remains the single
writer for `.claude/github-issue-map.json` per AGENTS.md § GitHub state.

Bash error semantics: `scripts/gh-project.sh` uses `set -euo pipefail`. Non-zero
exit propagates via `subprocess.CalledProcessError` → re-raised as
`NaavikOpsError` with bash stderr captured.

# Subcommands

  bootstrap [--apply] [--phase=X]
  init                                   (interactive; rarely invoked from agents)
  sync [--apply]
  milestone-status [name]
  add-item <issue-url>
  add-subissue <parent-num> <child-num>
  create-issue <id> <title> [...]
  create-epic <phase> [...]
  create-milestone <name> [--description "..."]
  item-id <issue-num>
  set-status <item-id> <status>
  set-priority <item-id> <pri>
  set-effort <item-id> <effort>
  add-status <name> [--color C] [--description "..."]
  next-unblocked
  backlog-by-epic [--top N]
  runs [count]
  refresh-map

# Naming

Wave 1 mirrors the bash subcommand surface 1:1. Commands invoked via dashes
(`set-status`) map to Python function names with underscores (`cmd_set_status`).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from naavik_ops.lib import NaavikOpsError

# scripts/gh-project.sh path (pinned during A.29; A.30 deletes this file).
# .claude/naavik_ops/gh.py → repo root → scripts/gh-project.sh
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "gh-project.sh"


def _shim(*args: str) -> int:
    """Invoke scripts/gh-project.sh with args; stream stdout/stderr; return rc.

    Output is streamed (not captured) so callers see live progress. For tests
    that need captured output, use `_shim_capture`.
    """
    if not SCRIPT_PATH.is_file():
        raise NaavikOpsError(f"gh-project.sh not found at {SCRIPT_PATH}")
    cmd = ["bash", str(SCRIPT_PATH), *args]
    try:
        return subprocess.run(cmd, check=False).returncode
    except FileNotFoundError as e:
        raise NaavikOpsError(f"bash not on PATH: {e}") from e


def _shim_capture(*args: str) -> str:
    """Invoke scripts/gh-project.sh with args; return captured stdout."""
    if not SCRIPT_PATH.is_file():
        raise NaavikOpsError(f"gh-project.sh not found at {SCRIPT_PATH}")
    cmd = ["bash", str(SCRIPT_PATH), *args]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise NaavikOpsError(
            f"gh-project.sh {' '.join(args)} failed (exit {e.returncode}): {e.stderr.strip()}"
        ) from e
    return result.stdout


# Each cmd_* function forwards remaining argv to the bash subcommand by the
# same name. Wave 1 ships parity; downstream task / release / deps modules
# compose these primitives.


def cmd_bootstrap(rest: Sequence[str]) -> int:
    return _shim("bootstrap", *rest)


def cmd_init(rest: Sequence[str]) -> int:
    return _shim("init", *rest)


def cmd_sync(rest: Sequence[str]) -> int:
    return _shim("sync", *rest)


def cmd_milestone_status(rest: Sequence[str]) -> int:
    return _shim("milestone-status", *rest)


def cmd_add_item(rest: Sequence[str]) -> int:
    return _shim("add-item", *rest)


def cmd_add_subissue(rest: Sequence[str]) -> int:
    return _shim("add-subissue", *rest)


def cmd_create_issue(rest: Sequence[str]) -> int:
    return _shim("create-issue", *rest)


def cmd_create_epic(rest: Sequence[str]) -> int:
    return _shim("create-epic", *rest)


def cmd_create_milestone(rest: Sequence[str]) -> int:
    return _shim("create-milestone", *rest)


def cmd_item_id(rest: Sequence[str]) -> int:
    return _shim("item-id", *rest)


def cmd_set_status(rest: Sequence[str]) -> int:
    return _shim("set-status", *rest)


def cmd_set_priority(rest: Sequence[str]) -> int:
    return _shim("set-priority", *rest)


def cmd_set_effort(rest: Sequence[str]) -> int:
    return _shim("set-effort", *rest)


def cmd_add_status(rest: Sequence[str]) -> int:
    return _shim("add-status", *rest)


def cmd_next_unblocked(rest: Sequence[str]) -> int:
    return _shim("next-unblocked", *rest)


def cmd_backlog_by_epic(rest: Sequence[str]) -> int:
    return _shim("backlog-by-epic", *rest)


def cmd_runs(rest: Sequence[str]) -> int:
    return _shim("runs", *rest)


def cmd_refresh_map(rest: Sequence[str]) -> int:
    return _shim("refresh-map", *rest)


# -----------------------------------------------------------------------------
# Programmatic helpers — used by task.py / release.py composition.
# -----------------------------------------------------------------------------


def capture_next_unblocked() -> str:
    """Return raw JSON output from `gh-project.sh next-unblocked`."""
    return _shim_capture("next-unblocked")


def capture_item_id(issue_num: int | str) -> str:
    """Resolve Issue # → Project item id. Stripped of trailing whitespace."""
    return _shim_capture("item-id", str(issue_num)).strip()


def set_status(item_id: str, status: str) -> None:
    """Programmatic set-status (raises NaavikOpsError on non-zero)."""
    if not item_id or not status:
        raise NaavikOpsError("set_status requires non-empty item_id + status")
    _shim_capture("set-status", item_id, status)


def set_priority(item_id: str, priority: str) -> None:
    """Programmatic set-priority. Accepts CRITICAL / HIGH / MEDIUM / LOW."""
    _shim_capture("set-priority", item_id, priority)


def set_effort(item_id: str, effort: str) -> None:
    """Programmatic set-effort. Accepts XS / S / M / L / XL."""
    _shim_capture("set-effort", item_id, effort)


# Print help/dispatch when invoked directly (debug aid).
if __name__ == "__main__":
    sys.exit(_shim(*sys.argv[1:]))
