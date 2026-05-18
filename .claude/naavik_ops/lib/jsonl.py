"""jsonl — atomic JSON / JSONL read+write with tempfile + os.replace.

Used by naavik_ops to mutate `.claude/github-issue-map.json` and similar
single-writer JSON stores without leaving partial files visible.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: str | os.PathLike[str]) -> Any:
    """Read JSON from `path`. Returns the parsed value (dict / list / etc.).

    Raises FileNotFoundError if path missing. ValueError on invalid JSON.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | os.PathLike[str], data: Any, *, indent: int = 2) -> None:
    """Write `data` as JSON to `path` atomically.

    Writes to a sibling tempfile (same dir, so os.replace is atomic across
    POSIX) then renames. Partial-write windows are impossible.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=str(p.parent),
        prefix=f".{p.name}.tmp.",
        suffix="",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(data, tmp, indent=indent, ensure_ascii=False)
        tmp.write("\n")
        tmp_path = tmp.name
    os.replace(tmp_path, p)


def read_jsonl(path: str | os.PathLike[str]) -> list[Any]:
    """Read JSONL from `path`. One JSON value per non-empty line.

    Empty / missing file → returns []. Blank lines skipped.
    """
    p = Path(path)
    if not p.exists():
        return []
    out: list[Any] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def append_jsonl(path: str | os.PathLike[str], record: Any) -> None:
    """Append one JSON record to `path` as a JSONL line.

    NOT atomic against concurrent writers; callers must hold a flock.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fp:
        json.dump(record, fp, ensure_ascii=False)
        fp.write("\n")
