"""roadmap — ROADMAP.md parser + writer.

Per plan 25 § D.9. Rolls the content of `scripts/roadmap_parser.py` (the read
side) into `.claude/naavik_ops/lib/roadmap.py` and extends with a writer half
that the 5 mutating task subcommands (insert / defer / prioritize / move /
renumber) need.

# Read side (replaces scripts/roadmap_parser.py)

  parse(phases=None, *, open_only=False) -> list[dict]
                                  Phase-filtered list of task dicts (legacy shape).

  iter_tasks(text) -> Iterator[TaskRow]
                                  Stream the raw rows out of ROADMAP.md text.

# Writer side (new in plan 25)

  parse_release_section(version) -> list[Row]
                                  Parse a single release-version table (4-level
                                  task IDs scoped to <version>) into editable rows.

  write_release_section(version, rows) -> ReleaseDiff
                                  Compute the text replacement for one release
                                  section without writing to disk.

  rewrite_atomic(diffs: list[ReleaseDiff]) -> None
                                  Apply 1..N ReleaseDiff changes to ROADMAP.md
                                  in one atomic os.replace.

# Output schema (legacy parse) — preserves scripts/roadmap_parser.py contract:

    {
      "phase": "Phase A" | "Phase 2" | "Pre-Phase-2 paper cuts" | "Phase 1.x deferred",
      "id": "A.1" | "2.11" | "PC.5" | "DEF-07",
      "title": "Author 6 subagent prompts ...",
      "status": " " | "~" | "x",
      "priority": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
      "notes": "<verbatim notes column, truncated>",
      "section_anchor": "### Phase A: Agent System"
    }
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

from naavik_ops.lib import NaavikOpsError

REPO_ROOT = Path(__file__).resolve().parents[3]
ROADMAP_PATH = REPO_ROOT / "ROADMAP.md"

# ---------------------------------------------------------------------------
# Legacy parser regex (byte-for-byte from scripts/roadmap_parser.py).
# ---------------------------------------------------------------------------

RE_PHASE_HEADER = re.compile(r"^### Phase ([A-Z0-9]+):\s+(.+?)\s*$")
RE_SUBSECTION_HEADER = re.compile(r"^####\s+(.+?)\s*$")
RE_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
RE_TABLE_DIVIDER = re.compile(r"^\|\s*[:\-]+\s*(\|\s*[:\-]+\s*)+\|\s*$")
RE_TASK_ID = re.compile(r"^(?:PC|[A-Z])\.\d+[a-z]?$|^\d+\.\d+[a-z]?$|^\d+\.\d+\.\d+(?:\.\d{2})?$")
RE_STATUS = re.compile(r"^\[([ ~xX])\]$")
RE_PARENTHETICAL_TAIL = re.compile(r"\s*\([^)]*\)\s*$")

PRIORITY_KEYWORDS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
HEADER_ID_NAMES = {"#", "wave"}
HEADER_TITLE_NAMES = {"task", "item"}
HEADER_NOTES_NAMES = {"notes", "source"}

# ---------------------------------------------------------------------------
# Release-section table shape (writer half).
# ---------------------------------------------------------------------------

#: 4-level task-id pattern (MAJOR.MINOR.PATCH.POSITION).
RE_FOUR_LEVEL = re.compile(r"^(\d+\.\d+\.\d+)\.(\d{2})$")

#: Heading like "### 0.2.0 — Phase 2 Core Backend".
RE_RELEASE_HEADER = re.compile(r"^###\s+(?P<version>\d+\.\d+\.\d+)\s+[—–-]\s+(?P<title>.+?)\s*$")

#: Backlog section heading. Synthetic "release-version" `backlog` for the unprioritized
#: parking-lot section. Plan 40 — first migrant 0.2.0.14 (n8n migration). Tasks inside
#: keep their 4-level release IDs; section is a parser-side filter, not an ID-scheme.
RE_BACKLOG_HEADER = re.compile(r"^##\s+Backlog\b.*$")

#: Synthetic version-name for the backlog section. Used as `version` arg to
#: `parse_release_section` + `task list <BACKLOG_VERSION>` etc.
BACKLOG_VERSION = "backlog"


@dataclass
class TaskRow:
    """Legacy row shape — preserves `scripts/roadmap_parser.py` JSON output."""

    phase: str
    id: str
    title: str
    status: str  # one of " " | "~" | "x"
    priority: str
    notes: str
    section_anchor: str


@dataclass
class ReleaseRow:
    """One row of a release-version task table (4-level task ID).

    Distinguishes from `TaskRow` by being the editable shape for the writer half.
    The `raw_line` carries the original markdown line so re-render preserves any
    column-width quirks the parser didn't capture explicitly.
    """

    task_id: str  # 4-level
    position: int  # 1..99
    status: str  # " " | "~" | "x"
    title: str
    priority: str  # HIGH/MEDIUM/LOW/"" — uppercased on parse
    notes: str
    raw_line: str  # original `| 0.2.0.05 | [ ] | Title | HIGH | notes |` line


@dataclass
class ReleaseDiff:
    """A planned rewrite of a release section.

    `start_line` + `end_line` are 0-indexed line offsets into ROADMAP.md text.
    `new_lines` replaces lines[start_line:end_line] (Python slice semantics).
    """

    version: str
    start_line: int
    end_line: int
    new_lines: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Legacy parser internals — preserves scripts/roadmap_parser.py logic.
# ---------------------------------------------------------------------------


def _cells_of(line: str) -> list[str]:
    inner = line.strip().strip("|")
    return [cell.strip() for cell in inner.split("|")]


def _normalize_phase_name(raw: str) -> str:
    return RE_PARENTHETICAL_TAIL.sub("", raw).strip()


def _is_table_header(cells: list[str]) -> bool:
    if not cells:
        return False
    first = cells[0].strip().lower()
    return first in HEADER_ID_NAMES or first in HEADER_TITLE_NAMES


def _detect_columns(header_cells: list[str]) -> dict[str, int] | None:
    lowered = [c.strip().lower() for c in header_cells]
    if "done" in lowered:
        return None  # Phase 1 wave tables track closed work.

    cols: dict[str, int] = {}
    if not lowered:
        return None
    first = lowered[0]
    if first in HEADER_ID_NAMES:
        cols["id"] = 0
        if len(lowered) > 1:
            cols["title"] = 1
        scan_from = 2
    elif first in HEADER_TITLE_NAMES:
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


def _parse_status_cell(cell: str) -> str | None:
    m = RE_STATUS.match(cell)
    if not m:
        return None
    return m.group(1).lower()


def _parse_row(
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

    if "id" in cols:
        if not id_cell:
            return None
        if not RE_TASK_ID.match(id_cell):
            return None
        task_id = id_cell
        title = title_cell or get("notes")[:120] or id_cell
    else:
        if not title_cell:
            return None
        prefix = "DEF" if "deferred" in phase.lower() else "AUTO"
        task_id = f"{prefix}-{auto_n:02d}"
        title = title_cell

    status_cell = get("status")
    status = _parse_status_cell(status_cell) if status_cell else None
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
    """Stream all task rows out of ROADMAP.md text. Legacy contract."""
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
            in_phase_1_main = phase_id == "1"
            in_table = False
            cols = None
            auto_n = 0
            continue

        m_sub = RE_SUBSECTION_HEADER.match(line)
        if m_sub:
            sub_raw = m_sub.group(1)
            sub_lower = sub_raw.lower()
            if "paper cuts" in sub_lower or "deferred" in sub_lower:
                current_phase = _normalize_phase_name(sub_raw)
                current_anchor = line
                in_phase_1_main = False
                in_table = False
                cols = None
                auto_n = 0
            continue

        if in_phase_1_main:
            continue

        m_row = RE_TABLE_ROW.match(line)
        if m_row and "|" in line:
            if RE_TABLE_DIVIDER.match(line):
                in_table = cols is not None
                continue

            row_cells = _cells_of(line)

            if not in_table:
                if _is_table_header(row_cells):
                    cols = _detect_columns(row_cells)
                continue

            if current_phase is None or current_anchor is None or cols is None:
                continue

            auto_n += 1
            task = _parse_row(row_cells, cols, current_phase, current_anchor, auto_n)
            if task is not None:
                yield task
            continue

        if in_table and not line.strip().startswith("|"):
            in_table = False
            cols = None


# ---------------------------------------------------------------------------
# Public legacy API (replaces subprocess shim to scripts/roadmap_parser.py).
# ---------------------------------------------------------------------------


def parse(phases: list[str] | None = None, *, open_only: bool = False) -> list[dict]:
    """Parse ROADMAP.md and return a list of task dicts.

    `phases` filters by phase name (e.g. ["Phase 2"]); None returns all.
    `open_only` skips rows with status='x'.
    """
    if not ROADMAP_PATH.is_file():
        raise NaavikOpsError(f"ROADMAP.md not found at {ROADMAP_PATH}")

    text = ROADMAP_PATH.read_text(encoding="utf-8")
    phase_set = set(phases) if phases else None

    out: list[dict] = []
    for task in iter_tasks(text):
        if phase_set is not None and task.phase not in phase_set:
            continue
        if open_only and task.status == "x":
            continue
        out.append(asdict(task))
    return out


# ---------------------------------------------------------------------------
# Writer half — parse_release_section + write_release_section + rewrite_atomic.
# ---------------------------------------------------------------------------


def parse_release_section(version: str, *, roadmap_text: str | None = None) -> list[ReleaseRow]:
    """Parse one release-version's task table.

    Returns rows in document order (== position order). Empty list if the
    section has no 4-level task IDs.

    Plan 40: the synthetic version `backlog` reads the `## Backlog (unprioritized)`
    h2 section instead of a `### X.Y.Z — Title` h3 release section. Tasks inside
    Backlog keep their original 4-level release IDs (e.g. `0.2.0.14`); section is
    a parser-side filter, not an ID-scheme.
    """
    text = roadmap_text if roadmap_text is not None else _read_roadmap()
    lines = text.splitlines()

    is_backlog = version == BACKLOG_VERSION
    in_section = False
    in_table = False
    cols: dict[str, int] | None = None
    rows: list[ReleaseRow] = []

    for raw in lines:
        line = raw.rstrip("\n")

        # Backlog section detection (h2). When the requested version is `backlog`,
        # entering the h2 enters the section; entering any OTHER h2 (or any h3 release
        # header) exits it.
        if is_backlog and RE_BACKLOG_HEADER.match(line):
            in_section = True
            in_table = False
            cols = None
            continue

        m_rel = RE_RELEASE_HEADER.match(line)
        if m_rel:
            if is_backlog:
                in_section = False
            else:
                in_section = m_rel.group("version") == version
            in_table = False
            cols = None
            continue

        if not in_section:
            continue

        # Stop at any next top-level ## heading (a NEW release header at ###
        # will have already swapped state via the m_rel match above). When parsing
        # backlog, ENTRY came from RE_BACKLOG_HEADER (also ## ); use a different
        # heading as the stop sentinel.
        if line.startswith("## ") and not line.startswith("### "):
            if is_backlog and RE_BACKLOG_HEADER.match(line):
                # Re-entering the same backlog header (impossible in practice;
                # defensive) — keep state.
                continue
            in_section = False
            continue

        m_tbl = RE_TABLE_ROW.match(line)
        if m_tbl and "|" in line:
            if RE_TABLE_DIVIDER.match(line):
                in_table = cols is not None
                continue
            cells = _cells_of(line)
            if not in_table:
                if _is_table_header(cells):
                    cols = _detect_columns(cells)
                continue
            row = _parse_release_row(cells, cols or {}, raw)
            if row is not None:
                rows.append(row)
            continue

        if in_table and not line.strip().startswith("|"):
            in_table = False
            cols = None
    return rows


def is_in_backlog(task_id: str, *, roadmap_text: str | None = None) -> bool:
    """Return True if `task_id` lives in the `## Backlog (unprioritized)` section.

    Plan 40: used by callers that need to differentiate active release tasks
    from deferred-but-not-deleted ones (e.g. `task next-unblocked` should skip
    backlog rows even when their 4-level ID would otherwise match a release).
    """
    backlog_rows = parse_release_section(BACKLOG_VERSION, roadmap_text=roadmap_text)
    return any(r.task_id == task_id for r in backlog_rows)


def _parse_release_row(cells: list[str], cols: dict[str, int], raw_line: str) -> ReleaseRow | None:
    """Pull a ReleaseRow out of a markdown table row. None on non-task rows."""
    if "id" not in cols:
        return None

    def get(name: str, default: str = "") -> str:
        idx = cols.get(name)
        if idx is None or idx >= len(cells):
            return default
        return cells[idx]

    id_cell = get("id")
    m = RE_FOUR_LEVEL.match(id_cell)
    if not m:
        return None

    status = _parse_status_cell(get("status")) or " "
    title = get("title")
    priority_raw = get("priority").upper().strip()
    priority = priority_raw if priority_raw in PRIORITY_KEYWORDS else ""
    notes = get("notes")

    return ReleaseRow(
        task_id=id_cell,
        position=int(m.group(2)),
        status=status,
        title=title,
        priority=priority,
        notes=notes,
        raw_line=raw_line,
    )


def find_release_section_bounds(
    version: str, *, roadmap_text: str | None = None
) -> tuple[int, int] | None:
    """Return (start_line, end_line) for the release-version section in ROADMAP.md.

    `start_line` is the line index of the `###` release header.
    `end_line` is the line index of the NEXT `##` or `###` header (or len(lines)).
    Both are inclusive of the header at `start_line` but exclusive of the next.
    Returns None if the section isn't present.
    """
    text = roadmap_text if roadmap_text is not None else _read_roadmap()
    lines = text.splitlines()

    start: int | None = None
    for i, line in enumerate(lines):
        m = RE_RELEASE_HEADER.match(line)
        if m and m.group("version") == version:
            start = i
            break

    if start is None:
        return None

    # End scan: next heading line at level ## or ###.
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line.startswith("## ") or line.startswith("### "):
            end = j
            break

    return start, end


def write_release_section(
    version: str,
    rows: list[ReleaseRow],
    *,
    roadmap_text: str | None = None,
) -> ReleaseDiff:
    """Compute the line replacement for one release section.

    `rows` must be position-ordered + position-coherent (caller's responsibility).
    Header + table chrome (title heading, column headers, divider) is preserved
    verbatim; only the body rows are rewritten in `position ASC` order.
    """
    text = roadmap_text if roadmap_text is not None else _read_roadmap()
    bounds = find_release_section_bounds(version, roadmap_text=text)
    if bounds is None:
        raise NaavikOpsError(f"release section for {version} not in ROADMAP.md")
    start, end = bounds
    lines = text.splitlines()
    section = lines[start:end]

    # Locate the table body within the section. Body rows are everything
    # between the divider line and the section end.
    divider_idx: int | None = None
    for i, line in enumerate(section):
        if RE_TABLE_DIVIDER.match(line):
            divider_idx = i
            break

    if divider_idx is None:
        # No table to rewrite — just return an empty diff. Caller should
        # never call this for a missing section.
        return ReleaseDiff(version=version, start_line=start, end_line=end, new_lines=section)

    body_start = divider_idx + 1
    # Body ends at first non-table line OR section end.
    body_end = len(section)
    for j in range(body_start, len(section)):
        line = section[j]
        if line and not line.startswith("|"):
            body_end = j
            break

    # Sort rows by position ASC.
    rows_sorted = sorted(rows, key=lambda r: r.position)
    new_body = [_format_release_row(r) for r in rows_sorted]

    new_section = section[:body_start] + new_body + section[body_end:]
    return ReleaseDiff(
        version=version,
        start_line=start,
        end_line=end,
        new_lines=new_section,
    )


def _format_release_row(row: ReleaseRow) -> str:
    """Render a ReleaseRow back to a markdown table line.

    Re-uses `raw_line` verbatim when the row was untouched (preserves any
    column-width quirks). Falls through to a canonical formatter only when
    caller built a NEW row. Column order matches the ROADMAP table header:
    `# | Task | Status | Priority | Notes`.
    """
    if row.raw_line:
        m = RE_TABLE_ROW.match(row.raw_line.strip())
        if m:
            cells = _cells_of(row.raw_line)
            if cells and cells[0] == row.task_id:
                return row.raw_line.rstrip("\n")
    priority_cell = row.priority or ""
    return f"| {row.task_id} | {row.title} | [{row.status}] | {priority_cell} | {row.notes} |"


def rewrite_atomic(diffs: list[ReleaseDiff], *, path: Path | None = None) -> None:
    """Apply 1..N ReleaseDiffs to ROADMAP.md in one atomic os.replace.

    Diffs are applied in REVERSE start_line order so earlier offsets stay
    valid as we splice. Conflicting / overlapping ranges raise NaavikOpsError.
    """
    target = path or ROADMAP_PATH
    text = target.read_text(encoding="utf-8")
    # Strip trailing newline if any; we add it back on write.
    had_trailing_newline = text.endswith("\n")
    if had_trailing_newline:
        text = text[:-1]
    lines = text.split("\n")

    # Sort diffs by start_line DESC. Detect overlaps first.
    sorted_diffs = sorted(diffs, key=lambda d: d.start_line)
    prev_end = -1
    for d in sorted_diffs:
        if d.start_line < prev_end:
            raise NaavikOpsError(
                f"overlapping ReleaseDiff ranges: {d.version} starts at {d.start_line} "
                f"before prior end {prev_end}"
            )
        prev_end = d.end_line

    for d in sorted(diffs, key=lambda d: d.start_line, reverse=True):
        lines[d.start_line : d.end_line] = d.new_lines

    new_text = "\n".join(lines)
    if had_trailing_newline:
        new_text += "\n"

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=str(target.parent),
        prefix=f".{target.name}.tmp.",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(new_text)
        tmp_path = tmp.name
    os.replace(tmp_path, target)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_roadmap() -> str:
    if not ROADMAP_PATH.is_file():
        raise NaavikOpsError(f"ROADMAP.md not found at {ROADMAP_PATH}")
    return ROADMAP_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI surface for back-compat: replaces `python3 scripts/roadmap_parser.py`.
# Used by `gh.py` bootstrap + sync paths during the transition + as a sanity
# tool. Output schema unchanged from the legacy script.
# ---------------------------------------------------------------------------


def _main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        sys.stdout.write(__doc__ or "")
        return 0

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

    text = _read_roadmap()
    count = 0
    for task in iter_tasks(text):
        if only_phases is not None and task.phase not in only_phases:
            continue
        if open_only and task.status == "x":
            continue
        if pretty:
            sys.stdout.write(json.dumps(asdict(task), ensure_ascii=False, indent=2) + "\n")
        else:
            sys.stdout.write(json.dumps(asdict(task), ensure_ascii=False) + "\n")
        count += 1

    if count == 0:
        sys.stderr.write("warning: no rows emitted; check --phase filter or ROADMAP format\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
