#!/usr/bin/env python3
"""roadmap_parser.py — extract task rows from ROADMAP.md as JSONL.

Each output line:

    {
      "phase": "Phase A" | "Phase 2" | "Pre-Phase-2 paper cuts" | "Phase 1.x deferred",
      "id": "A.1" | "2.11" | "PC.5" | "DEF-07",
      "title": "Author 6 subagent prompts ...",
      "status": " " | "~" | "x",
      "priority": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
      "notes": "<verbatim notes column, truncated>",
      "section_anchor": "### Phase A: Agent System"
    }

Used by scripts/gh-project.sh bootstrap + sync.

Flags:
  --phase=<name>     emit only rows in this phase (repeatable)
  --open-only        skip rows with status='x'
  --pretty           indented JSON (one record per object, not JSONL)

Handled table shapes:
  | # | Task | Status | Priority | Notes |       (Phase A; new style)
  | # | Task | Priority | Notes |                  (Phase 2-6; status defaulted)
  | # | Item | Status | Notes |                    (Pre-Phase-2 paper cuts)
  | Item | Source | Notes |                        (Phase 1.x deferred; auto-id)

Tables with a `Done` column (Phase 1 wave tables) are SKIPPED — closed work.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
ROADMAP = ROOT / "ROADMAP.md"

RE_PHASE_HEADER = re.compile(r"^### Phase ([A-Z0-9]+):\s+(.+?)\s*$")
RE_SUBSECTION_HEADER = re.compile(r"^####\s+(.+?)\s*$")
RE_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
RE_TABLE_DIVIDER = re.compile(r"^\|\s*[:\-]+\s*(\|\s*[:\-]+\s*)+\|\s*$")
RE_TASK_ID = re.compile(r"^(?:PC|[A-Z])\.\d+[a-z]?$|^\d+\.\d+[a-z]?$")
RE_STATUS = re.compile(r"^\[([ ~xX])\]$")
RE_PARENTHETICAL_TAIL = re.compile(r"\s*\([^)]*\)\s*$")

PRIORITY_KEYWORDS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
HEADER_ID_NAMES = {"#", "wave"}
HEADER_TITLE_NAMES = {"task", "item"}
HEADER_NOTES_NAMES = {"notes", "source"}


@dataclass
class TaskRow:
    phase: str
    id: str
    title: str
    status: str  # one of " " | "~" | "x"
    priority: str
    notes: str
    section_anchor: str


def cells_of(line: str) -> list[str]:
    inner = line.strip().strip("|")
    return [cell.strip() for cell in inner.split("|")]


def normalize_phase_name(raw: str) -> str:
    """Strip trailing parentheticals so milestone names are clean."""
    return RE_PARENTHETICAL_TAIL.sub("", raw).strip()


def is_table_header(cells: list[str]) -> bool:
    if not cells:
        return False
    first = cells[0].strip().lower()
    return first in HEADER_ID_NAMES or first in HEADER_TITLE_NAMES


def detect_columns(header_cells: list[str]) -> dict[str, int] | None:
    """Map column roles to indices.

    Returns None if the table should be skipped (e.g., has a 'Done' column from
    Phase 1 wave tables — those track closed work).
    """
    lowered = [c.strip().lower() for c in header_cells]

    if "done" in lowered:
        return None  # Phase 1 wave table — closed.

    cols: dict[str, int] = {}

    if not lowered:
        return None

    first = lowered[0]
    if first in HEADER_ID_NAMES:
        # First col is an id slot; second col (if present) is the title.
        cols["id"] = 0
        if len(lowered) > 1:
            cols["title"] = 1
        scan_from = 2
    elif first in HEADER_TITLE_NAMES:
        # First col is the title; we'll auto-assign an id later.
        cols["title"] = 0
        scan_from = 1
    else:
        return None

    for idx in range(scan_from, len(lowered)):
        name = lowered[idx]
        if name == "status" and "status" not in cols:
            cols["status"] = idx
        elif name == "priority" and "priority" not in cols:
            cols["priority"] = idx
        elif name in HEADER_NOTES_NAMES and "notes" not in cols:
            cols["notes"] = idx

    return cols


def parse_status_cell(cell: str) -> str | None:
    m = RE_STATUS.match(cell)
    if not m:
        return None
    return m.group(1).lower()


def parse_row(
    cells: list[str],
    cols: dict[str, int],
    phase: str,
    anchor: str,
    auto_n: int,
) -> TaskRow | None:
    def get(name: str, default: str = "") -> str:
        idx = cols.get(name)
        if idx is None or idx >= len(cells):
            return default
        return cells[idx]

    id_cell = get("id")
    title_cell = get("title")

    # Case 1: explicit id column.
    if "id" in cols:
        if not id_cell:
            return None
        if not RE_TASK_ID.match(id_cell):
            return None  # Not a valid task row (probably a divider or header echo)
        task_id = id_cell
        title = title_cell or get("notes")[:120] or id_cell
    else:
        # Case 2: no id column — auto-generate from the title.
        if not title_cell:
            return None
        # Synthesize an id from the phase prefix.
        prefix = "DEF" if "deferred" in phase.lower() else "AUTO"
        task_id = f"{prefix}-{auto_n:02d}"
        title = title_cell

    status_cell = get("status")
    status = parse_status_cell(status_cell) if status_cell else None
    if status is None:
        status = " "

    priority_cell = get("priority").upper().strip()
    if priority_cell in PRIORITY_KEYWORDS:
        priority = priority_cell
    elif "deferred" in phase.lower():
        priority = "LOW"
    else:
        priority = "MEDIUM"

    notes = get("notes")[:1000]

    # Title truncate for GitHub Issue titles (70 chars left for `[<id>] ` prefix).
    return TaskRow(
        phase=phase,
        id=task_id,
        title=title[:140],
        status=status,
        priority=priority,
        notes=notes,
        section_anchor=anchor,
    )


def iter_tasks(roadmap_text: str) -> Iterator[TaskRow]:
    lines = roadmap_text.splitlines()

    current_phase: str | None = None
    current_anchor: str | None = None
    in_phase_1_main = False
    in_table = False
    cols: dict[str, int] | None = None
    auto_n = 0

    for raw in lines:
        line = raw.rstrip("\n")

        m_phase = RE_PHASE_HEADER.match(line)
        if m_phase:
            phase_id, _ = m_phase.group(1), m_phase.group(2)
            current_phase = f"Phase {phase_id}"
            current_anchor = line
            in_phase_1_main = (phase_id == "1")
            in_table = False
            cols = None
            auto_n = 0
            continue

        m_sub = RE_SUBSECTION_HEADER.match(line)
        if m_sub:
            sub_raw = m_sub.group(1)
            sub_lower = sub_raw.lower()
            if "paper cuts" in sub_lower or "deferred" in sub_lower:
                current_phase = normalize_phase_name(sub_raw)
                current_anchor = line
                in_phase_1_main = False
                in_table = False
                cols = None
                auto_n = 0
            continue

        if in_phase_1_main:
            # Skip Phase-1 wave + completion-log tables entirely.
            continue

        m_row = RE_TABLE_ROW.match(line)
        if m_row and "|" in line:
            if RE_TABLE_DIVIDER.match(line):
                in_table = cols is not None
                continue

            row_cells = cells_of(line)

            if not in_table:
                if is_table_header(row_cells):
                    cols = detect_columns(row_cells)
                continue

            if current_phase is None or current_anchor is None or cols is None:
                continue

            auto_n += 1
            task = parse_row(row_cells, cols, current_phase, current_anchor, auto_n)
            if task is not None:
                yield task
            continue

        if in_table and not line.strip().startswith("|"):
            in_table = False
            cols = None


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in {"-h", "--help"}:
        print(__doc__)
        return 0

    if not ROADMAP.exists():
        print(f"error: {ROADMAP} not found", file=sys.stderr)
        return 1

    text = ROADMAP.read_text(encoding="utf-8")

    only_phases: set[str] | None = None
    open_only = False
    pretty = False
    for arg in argv[1:]:
        if arg.startswith("--phase="):
            only_phases = (only_phases or set()) | {arg.split("=", 1)[1]}
        elif arg == "--open-only":
            open_only = True
        elif arg == "--pretty":
            pretty = True

    count = 0
    for task in iter_tasks(text):
        if only_phases is not None and task.phase not in only_phases:
            continue
        if open_only and task.status == "x":
            continue
        if pretty:
            print(json.dumps(asdict(task), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(asdict(task), ensure_ascii=False))
        count += 1

    if count == 0:
        print("warning: no rows emitted; check --phase filter or ROADMAP format", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
