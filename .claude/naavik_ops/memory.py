"""memory — agent memory ops.

During A.29 transition: subprocess wrappers around `scripts/agent-memory.sh`.
A.30 (0.1.1): native Python rewrite.

The wrapper preserves the single-writer rule — only the bash script writes
`.claude/memory/` stores. This module is the canonical entry point for agents.

# Subcommands

  init
  record-decision <id> <verdict> <rationale> [--supersedes <id>] [--run-id ID]
  record-discussion <topic> <surface> [--phase X] [--priority P] [--filed-as #N]
                                      [--run-id ID]
  record-knowledge <slug> <body-source|-> [--aliases "a, b"] [--confidence H|M|L]
                                          [--supersedes <slug>] [--overwrite]
                                          [--run-id ID]
  record-lesson <id> <pattern> <evidence-runs-csv> [--proposed-action ...]
                                                   [--supersedes <id>]
  list <decisions|discussions|lessons|patterns|knowledge|runs>
  query <store> '<jq-expr>'
  seed
  update-index
  analyze-run <run-id>
  mine-patterns [--lookback N] [--aliases]
  promote-lesson <pattern_id>
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from naavik_ops.lib import NaavikOpsError

# scripts/agent-memory.sh path (pinned during A.29).
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "agent-memory.sh"


def _shim(*args: str) -> int:
    """Invoke scripts/agent-memory.sh streaming."""
    if not SCRIPT_PATH.is_file():
        raise NaavikOpsError(f"agent-memory.sh not found at {SCRIPT_PATH}")
    cmd = ["bash", str(SCRIPT_PATH), *args]
    try:
        return subprocess.run(cmd, check=False).returncode
    except FileNotFoundError as e:
        raise NaavikOpsError(f"bash not on PATH: {e}") from e


def _shim_capture(*args: str) -> str:
    """Invoke scripts/agent-memory.sh capturing stdout."""
    if not SCRIPT_PATH.is_file():
        raise NaavikOpsError(f"agent-memory.sh not found at {SCRIPT_PATH}")
    cmd = ["bash", str(SCRIPT_PATH), *args]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise NaavikOpsError(
            f"agent-memory.sh {' '.join(args)} failed (exit {e.returncode}): {e.stderr.strip()}"
        ) from e
    return result.stdout


def cmd_init(rest: Sequence[str]) -> int:
    return _shim("init", *rest)


def cmd_record_decision(rest: Sequence[str]) -> int:
    return _shim("record-decision", *rest)


def cmd_record_discussion(rest: Sequence[str]) -> int:
    return _shim("record-discussion", *rest)


def cmd_record_knowledge(rest: Sequence[str]) -> int:
    return _shim("record-knowledge", *rest)


def cmd_record_lesson(rest: Sequence[str]) -> int:
    return _shim("record-lesson", *rest)


def cmd_list(rest: Sequence[str]) -> int:
    return _shim("list", *rest)


def cmd_query(rest: Sequence[str]) -> int:
    return _shim("query", *rest)


def cmd_seed(rest: Sequence[str]) -> int:
    return _shim("seed", *rest)


def cmd_update_index(rest: Sequence[str]) -> int:
    return _shim("update-index", *rest)


def cmd_analyze_run(rest: Sequence[str]) -> int:
    return _shim("analyze-run", *rest)


def cmd_mine_patterns(rest: Sequence[str]) -> int:
    return _shim("mine-patterns", *rest)


def cmd_promote_lesson(rest: Sequence[str]) -> int:
    return _shim("promote-lesson", *rest)


# Programmatic helpers — for task.py / release.py composition.


def capture_list(store: str) -> str:
    """Return raw stdout from `agent-memory.sh list <store>`."""
    return _shim_capture("list", store)


def capture_query(store: str, jq_expr: str) -> str:
    """Return raw stdout from `agent-memory.sh query <store> '<jq-expr>'`."""
    return _shim_capture("query", store, jq_expr)


if __name__ == "__main__":
    sys.exit(_shim(*sys.argv[1:]))
