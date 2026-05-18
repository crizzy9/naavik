"""roadmap — ROADMAP.md parser.

During A.29: wraps `scripts/roadmap_parser.py` via subprocess (preserving the
single-writer rule + idempotency). A.30 (0.1.1) inlines the parser as native
Python.

Output schema matches `scripts/roadmap_parser.py`:
  {phase, id, title, status, priority, notes, section_anchor}
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from naavik_ops.lib import NaavikOpsError

# Resolve scripts/roadmap_parser.py relative to this module's location.
# .claude/naavik_ops/lib/roadmap.py → repo root → scripts/roadmap_parser.py
REPO_ROOT = Path(__file__).resolve().parents[3]
PARSER_PATH = REPO_ROOT / "scripts" / "roadmap_parser.py"


def parse(phases: list[str] | None = None, *, open_only: bool = False) -> list[dict]:
    """Parse ROADMAP.md and return a list of task dicts.

    `phases` filters by phase name (e.g. ["Phase 2"]); None returns all.
    `open_only` skips rows with status='x'.
    """
    if not PARSER_PATH.is_file():
        raise NaavikOpsError(f"roadmap parser not found at {PARSER_PATH}")

    cmd = [sys.executable, str(PARSER_PATH)]
    for p in phases or []:
        cmd.append(f"--phase={p}")
    if open_only:
        cmd.append("--open-only")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise NaavikOpsError(
            f"roadmap_parser.py failed (exit {e.returncode}): {e.stderr.strip()}"
        ) from e

    rows: list[dict] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows
