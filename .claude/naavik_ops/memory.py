"""memory — agent memory ops (native Python; plan 25 D.8).

Replaces the subprocess wrappers around `scripts/agent-memory.sh` with
native Python. The single-writer contract is preserved: `.claude/memory/*`
writes go through `.claude/naavik-ops memory ...` only.

Stores:
  .claude/memory/decisions.jsonl
  .claude/memory/discussions.jsonl
  .claude/memory/lessons.jsonl
  .claude/memory/recurring-patterns.jsonl
  .claude/memory/knowledge/<slug>.md
  .claude/memory/runs-analysis/<run-id>.md

Lock: `.claude/memory/.lock` (flock -x) — serialized via `lib/flock.acquire`.

# Subcommand surface

  init
  record-decision <id> <verdict> <rationale> [--supersedes <id>] [--run-id ID]
  record-discussion <topic> <surface> [--phase X] [--priority P]
                                       [--filed-as #N] [--run-id ID]
  record-knowledge <slug> <body-source|-> [--aliases "a, b"]
                                          [--confidence H|M|L]
                                          [--supersedes <slug>] [--overwrite]
                                          [--run-id ID]
  record-lesson <id> <pattern> <evidence-runs-csv> [--proposed-action ...]
                                                   [--supersedes <id>]
                                                   [--run-id ID]
  list <decisions|discussions|lessons|patterns|knowledge|runs>
  query <store> '<jq-expr>'                  jq runs via subprocess (preserves
                                              jq semantics 1:1 with bash); env
                                              + getpath etc. denied (A.17
                                              hardening preserved byte-for-byte)
  seed                                        Inventory the seeded knowledge.
  update-index                                Regenerate knowledge/INDEX.md.
  analyze-run <run-id>                        Write runs-analysis/<run-id>.md.
  mine-patterns [--lookback N] [--aliases]    Aggregate ERROR events across
                                              recent runs.
  promote-lesson <pattern_id>                 Threshold 5; create lesson +
                                              knowledge stub.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from naavik_ops.lib import NaavikOpsError, flock

REPO_ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = REPO_ROOT / ".claude" / "memory"
DECISIONS = MEMORY_DIR / "decisions.jsonl"
DISCUSSIONS = MEMORY_DIR / "discussions.jsonl"
LESSONS = MEMORY_DIR / "lessons.jsonl"
PATTERNS = MEMORY_DIR / "recurring-patterns.jsonl"
KNOWLEDGE_DIR = MEMORY_DIR / "knowledge"
RUNS_DIR = MEMORY_DIR / "runs-analysis"
LOCK_FILE = MEMORY_DIR / ".lock"
TRACES_ROOT = REPO_ROOT / "traces"

PROMOTION_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# jq sandbox — byte-for-byte port of the bash regex (A.17 hardening)
# ---------------------------------------------------------------------------

# Char allowlist mirrors `scripts/agent-memory.sh:validate_jq_expr` ALLOWED_RE.
# Original bash regex: ^[][a-zA-Z0-9 _.,:;|&!=<>()/?@$"'-]+$
# In Python: include all chars literally inside character class.
_JQ_ALLOWED_RE = re.compile(r"^[][a-zA-Z0-9 _.,:;|&!=<>()/?@$\"'-]+$")

# Identifier deny-list (env, getpath, input, etc.) — bash word-boundary regex
# was `(^|[^a-zA-Z0-9_])${BAD}([^a-zA-Z0-9_]|$)`. Python equivalent uses
# lookaround / non-word boundaries.
_JQ_BANNED = (
    "env",
    "input",
    "inputs",
    "input_filename",
    "getpath",
    "path",
    "paths",
    "setpath",
    "delpaths",
    "debug",
    "stderr",
)


def _validate_jq_expr(expr: str) -> None:
    """Validate a jq filter expression. Fail-closed on injection attempts.

    Byte-for-byte port of `scripts/agent-memory.sh:validate_jq_expr` per plan
    R11. Bug-for-bug compatible.
    """
    if not _JQ_ALLOWED_RE.match(expr):
        raise NaavikOpsError(
            "jq expression contains disallowed character. See docs/AGENT_OPS.md § 14."
        )
    for bad in _JQ_BANNED:
        pat = rf"(^|[^a-zA-Z0-9_]){re.escape(bad)}([^a-zA-Z0-9_]|$)"
        if re.search(pat, expr):
            raise NaavikOpsError(
                f"jq expression contains disallowed identifier '{bad}'. See docs/AGENT_OPS.md § 14."
            )
    if "$ENV" in expr:
        raise NaavikOpsError("jq expression references '$ENV'. See docs/AGENT_OPS.md § 14.")


def _validate_aliases(aliases: str) -> None:
    """Validate --aliases (A.17 + A.17a hardening: newline / fence / charset)."""
    if not aliases:
        return
    if "\n" in aliases or "\r" in aliases:
        raise NaavikOpsError("--aliases must not contain newlines.")
    if "---" in aliases:
        raise NaavikOpsError("--aliases must not contain front-matter fence '---'.")
    if not re.match(r"^[a-zA-Z0-9 .,/_#-]*$", aliases):
        raise NaavikOpsError(
            f"--aliases must be comma-separated tokens. Allowed chars: "
            f"[a-zA-Z0-9 .,/_#-]. Got: '{aliases}'"
        )


# ---------------------------------------------------------------------------
# Atomic JSONL append (under flock)
# ---------------------------------------------------------------------------


def _append_jsonl_locked(path: Path, record: dict[str, Any]) -> None:
    """Atomically append one JSONL record. MUST hold the memory flock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    payload = existing + json.dumps(record, ensure_ascii=False) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _find_by_id(path: Path, target_id: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id") == target_id:
            return row
    return None


def _mark_superseded(path: Path, old_id: str, new_id: str) -> None:
    """Atomically rewrite the JSONL marking old_id as superseded."""
    if not path.is_file():
        return
    out_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        if isinstance(row, dict) and row.get("id") == old_id:
            row["state"] = "superseded"
            row["superseded_by"] = new_id
            out_lines.append(json.dumps(row, ensure_ascii=False))
        else:
            out_lines.append(json.dumps(row, ensure_ascii=False))
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(rest: Sequence[str]) -> int:
    _ = rest
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for f in (DECISIONS, DISCUSSIONS, LESSONS, PATTERNS):
        if not f.is_file():
            f.touch()
    keep = MEMORY_DIR / ".keep"
    if not keep.is_file():
        keep.touch()
    sys.stdout.write(f"init: {MEMORY_DIR} (4 JSONL stores + knowledge/ + runs-analysis/)\n")
    return 0


# ---------------------------------------------------------------------------
# record-decision
# ---------------------------------------------------------------------------


def cmd_record_decision(rest: Sequence[str]) -> int:
    if len(rest) < 3:
        sys.stderr.write(
            "usage: naavik-ops memory record-decision <id> <verdict> <rationale> "
            "[--supersedes <old-id>] [--run-id <run-id>]\n"
        )
        return 2
    cmd_init([])
    id_, verdict, rationale = rest[0], rest[1], rest[2]
    supersedes = ""
    run_id = ""
    args = list(rest[3:])
    i = 0
    while i < len(args):
        if args[i] == "--supersedes":
            supersedes = args[i + 1]
            i += 2
        elif args[i] == "--run-id":
            run_id = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{args[i]}'")

    existing = _find_by_id(DECISIONS, id_)
    if existing and not supersedes:
        raise NaavikOpsError(f"decision '{id_}' exists. Use --supersedes <old-id> to upgrade.")

    record: dict[str, Any] = {
        "id": id_,
        "verdict": verdict,
        "rationale": rationale,
        "captured_at": _now_iso(),
        "state": "active",
    }
    if supersedes:
        record["supersedes"] = supersedes
    if run_id:
        record["run_id"] = run_id

    with flock.acquire(LOCK_FILE):
        if supersedes:
            _mark_superseded(DECISIONS, supersedes, id_)
        _append_jsonl_locked(DECISIONS, record)
    sys.stdout.write(f"decision: {id_}\n")
    return 0


# ---------------------------------------------------------------------------
# record-discussion
# ---------------------------------------------------------------------------


def cmd_record_discussion(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write(
            "usage: naavik-ops memory record-discussion <topic> <surface> "
            "[--phase X] [--priority P] [--filed-as #N] [--run-id ID]\n"
        )
        return 2
    cmd_init([])
    topic, surface = rest[0], rest[1]
    phase = ""
    priority = "MEDIUM"
    filed = ""
    run_id = ""
    args = list(rest[2:])
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--phase":
            phase = args[i + 1]
            i += 2
        elif a == "--priority":
            priority = args[i + 1].upper()
            i += 2
        elif a == "--filed-as":
            filed = args[i + 1]
            i += 2
        elif a == "--run-id":
            run_id = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")

    auto_id = f"{_today_iso().replace('-', '')}-{secrets.token_hex(3)}"
    record: dict[str, Any] = {
        "id": auto_id,
        "topic": topic,
        "surface": surface,
        "priority": priority,
        "captured_at": _now_iso(),
    }
    if phase:
        record["phase"] = phase
    if filed:
        record["filed_as"] = filed
    if run_id:
        record["run_id"] = run_id

    with flock.acquire(LOCK_FILE):
        _append_jsonl_locked(DISCUSSIONS, record)
    sys.stdout.write(f"discussion: {auto_id}\n")
    return 0


# ---------------------------------------------------------------------------
# record-knowledge
# ---------------------------------------------------------------------------


_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def cmd_record_knowledge(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write(
            "usage: naavik-ops memory record-knowledge <slug> <body-source|-> "
            "[--aliases ...] [--confidence H|M|L] [--supersedes <slug>] "
            "[--overwrite] [--run-id ID]\n"
        )
        return 2
    cmd_init([])
    slug, src = rest[0], rest[1]
    aliases = ""
    confidence = "medium"
    supersedes = "none"
    overwrite = False
    run_id = ""
    args = list(rest[2:])
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--aliases":
            aliases = args[i + 1]
            i += 2
        elif a == "--confidence":
            conf_in = args[i + 1].lower()
            confidence = {"h": "high", "m": "medium", "l": "low"}.get(conf_in, conf_in)
            i += 2
        elif a == "--supersedes":
            supersedes = args[i + 1]
            i += 2
        elif a == "--overwrite":
            overwrite = True
            i += 1
        elif a == "--run-id":
            run_id = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")

    if confidence not in ("high", "medium", "low"):
        raise NaavikOpsError("confidence must be high|medium|low")
    if not _SLUG_RE.match(slug):
        raise NaavikOpsError("slug must be kebab-case [a-z0-9-]")
    _validate_aliases(aliases)

    out = KNOWLEDGE_DIR / f"{slug}.md"
    if out.is_file() and not overwrite:
        raise NaavikOpsError(f"{out} exists. Use --overwrite or --supersedes <slug>.")

    if src == "-":
        body = sys.stdin.read()
    else:
        src_path = Path(src)
        if not src_path.is_file():
            raise NaavikOpsError(f"body-source '{src}' not found")
        body = src_path.read_text(encoding="utf-8")

    today = _today_iso()
    run_suffix = f" (run {run_id})" if run_id else ""

    front_matter = (
        f"---\n"
        f"Topic: {slug}\n"
        f"Aliases: {aliases}\n"
        f"First captured: {today}{run_suffix}\n"
        f"Last referenced: {today}\n"
        f"Supersedes: {supersedes}\n"
        f"Confidence: {confidence}\n"
        f"---\n\n"
    )
    rendered = front_matter + body

    with flock.acquire(LOCK_FILE):
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f"{out.name}.tmp.{os.getpid()}")
        tmp.write_text(rendered, encoding="utf-8")
        os.replace(tmp, out)
        _update_index_inline()
    sys.stdout.write(f"knowledge: {out}\n")
    return 0


# ---------------------------------------------------------------------------
# update-index — regenerate knowledge/INDEX.md
# ---------------------------------------------------------------------------


def _read_front_matter(path: Path) -> dict[str, str]:
    """Pull `^Topic:` / `^Aliases:` / `^Confidence:` / `^First captured:` /
    `^Last referenced:` lines out of a knowledge .md."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        for key in ("Topic", "Aliases", "Confidence", "First captured", "Last referenced"):
            prefix = f"{key}: "
            if line.startswith(prefix):
                out.setdefault(key, line[len(prefix) :])
    return out


def _update_index_inline() -> None:
    """Regenerate knowledge/INDEX.md. MUST hold the memory flock."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    index_path = KNOWLEDGE_DIR / "INDEX.md"

    lines = [
        "# Knowledge Index — `.claude/memory/knowledge/`",
        "",
        "<!-- AUTO-GENERATED by `.claude/naavik-ops memory update-index`. Do NOT hand-edit. -->",
        "<!-- Maintained on every `record-knowledge` invocation. Single-writer rule applies. -->",
        "",
        (
            "Static index of all knowledge entries. Dynamic index: "
            "`.claude/naavik-ops memory list knowledge`."
        ),
        "",
        "Aliases drive `Skill: naavik-memory-lookup` discovery. Add a new entry via:",
        (
            "  `.claude/naavik-ops memory record-knowledge <slug> <body-file> "
            '--aliases "a, b" --confidence H`'
        ),
        "",
        "| Topic | Confidence | Aliases | First captured | Last referenced |",
        "|---|---|---|---|---|",
    ]
    count = 0
    for f in sorted(KNOWLEDGE_DIR.glob("*.md")):
        slug = f.stem
        if slug == "INDEX":
            continue
        fm = _read_front_matter(f)
        lines.append(
            f"| `{slug}` | {fm.get('Confidence', '')} | {fm.get('Aliases', '')} | "
            f"{fm.get('First captured', '')} | {fm.get('Last referenced', '')} |"
        )
        count += 1
    lines.append("")
    lines.append(f"_{count} entries. Generated {_now_iso()}._")

    tmp = index_path.with_name(f"{index_path.name}.tmp.{os.getpid()}")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, index_path)
    sys.stdout.write(f"index: {index_path} ({count} entries)\n")


def cmd_update_index(rest: Sequence[str]) -> int:
    _ = rest
    cmd_init([])
    with flock.acquire(LOCK_FILE):
        _update_index_inline()
    return 0


# ---------------------------------------------------------------------------
# record-lesson
# ---------------------------------------------------------------------------


def cmd_record_lesson(rest: Sequence[str]) -> int:
    if len(rest) < 3:
        sys.stderr.write(
            "usage: naavik-ops memory record-lesson <id> <pattern> "
            "<evidence-runs-csv> [--proposed-action ...] [--supersedes <id>] "
            "[--run-id ID]\n"
        )
        return 2
    cmd_init([])
    id_, pattern, evidence_csv = rest[0], rest[1], rest[2]
    supersedes = ""
    action = ""
    run_id = ""
    args = list(rest[3:])
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--supersedes":
            supersedes = args[i + 1]
            i += 2
        elif a == "--proposed-action":
            action = args[i + 1]
            i += 2
        elif a == "--run-id":
            run_id = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")

    existing = _find_by_id(LESSONS, id_)
    if existing and not supersedes:
        raise NaavikOpsError(f"lesson '{id_}' exists. Use --supersedes <old-id> to upgrade.")

    evidence = [t.strip() for t in evidence_csv.split(",") if t.strip()]
    record: dict[str, Any] = {
        "id": id_,
        "pattern": pattern,
        "evidence_runs": evidence,
        "captured_at": _now_iso(),
        "state": "active",
    }
    if action:
        record["proposed_action"] = action
    if supersedes:
        record["supersedes"] = supersedes
    if run_id:
        record["run_id"] = run_id

    with flock.acquire(LOCK_FILE):
        if supersedes:
            _mark_superseded(LESSONS, supersedes, id_)
        _append_jsonl_locked(LESSONS, record)
    sys.stdout.write(f"lesson: {id_}\n")
    return 0


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def cmd_list(rest: Sequence[str]) -> int:
    if not rest:
        sys.stderr.write(
            "usage: naavik-ops memory list "
            "<decisions|discussions|lessons|patterns|knowledge|runs>\n"
        )
        return 2
    store = rest[0]
    if store == "decisions":
        return _list_jsonl(DECISIONS, "(no decisions yet)", _fmt_decision)
    if store == "discussions":
        return _list_jsonl(DISCUSSIONS, "(no discussions yet)", _fmt_discussion)
    if store == "lessons":
        return _list_jsonl(LESSONS, "(no lessons yet)", _fmt_lesson)
    if store == "patterns":
        return _list_jsonl(PATTERNS, "(no patterns yet)", _fmt_pattern)
    if store == "knowledge":
        return _list_knowledge()
    if store in ("runs", "runs-analysis"):
        return _list_runs()
    raise NaavikOpsError(
        f"unknown store '{store}' (decisions|discussions|lessons|patterns|knowledge|runs)"
    )


def _list_jsonl(path: Path, empty_msg: str, formatter) -> int:
    if not path.is_file():
        sys.stdout.write(empty_msg + "\n")
        return 0
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        sys.stdout.write(empty_msg + "\n")
        return 0
    formatter(rows)
    return 0


def _fmt_decision(rows: list[dict]) -> None:
    sys.stdout.write(f"{'ID':<40} {'VERDICT':<20} {'STATE':<12} {'CAPTURED'}\n")
    for r in rows:
        sys.stdout.write(
            f"{r.get('id', ''):<40} {r.get('verdict', ''):<20} "
            f"{r.get('state', ''):<12} {r.get('captured_at', '')}\n"
        )


def _fmt_discussion(rows: list[dict]) -> None:
    sys.stdout.write(f"{'ID':<22} {'TOPIC':<50} {'PRIORITY':<10} {'FILED-AS'}\n")
    for r in rows:
        sys.stdout.write(
            f"{r.get('id', ''):<22} {r.get('topic', ''):<50} "
            f"{r.get('priority', ''):<10} {r.get('filed_as', '-')}\n"
        )


def _fmt_lesson(rows: list[dict]) -> None:
    sys.stdout.write(f"{'ID':<30} {'PATTERN':<60} {'STATE':<12} {'RUNS'}\n")
    for r in rows:
        runs_n = len(r.get("evidence_runs") or [])
        sys.stdout.write(
            f"{r.get('id', ''):<30} {r.get('pattern', ''):<60} {r.get('state', ''):<12} {runs_n}\n"
        )


def _fmt_pattern(rows: list[dict]) -> None:
    sys.stdout.write(f"{'PATTERN-ID':<40} {'N':<6} {'FIRST-SEEN':<22} {'LAST-SEEN'}\n")
    for r in rows:
        sys.stdout.write(
            f"{r.get('pattern_id', ''):<40} {r.get('occurrence_count', 0):<6} "
            f"{r.get('first_seen', ''):<22} {r.get('last_seen', '')}\n"
        )


def _list_knowledge() -> int:
    if not KNOWLEDGE_DIR.is_dir():
        sys.stdout.write("(no knowledge yet)\n")
        return 0
    sys.stdout.write(f"{'TOPIC':<40} {'CONFIDENCE':<12} {'ALIASES'}\n")
    for f in sorted(KNOWLEDGE_DIR.glob("*.md")):
        slug = f.stem
        if slug == "INDEX":
            continue
        fm = _read_front_matter(f)
        sys.stdout.write(f"{slug:<40} {fm.get('Confidence', ''):<12} {fm.get('Aliases', '')}\n")
    return 0


def _list_runs() -> int:
    if not RUNS_DIR.is_dir():
        sys.stdout.write("(no runs analyzed yet)\n")
        return 0
    sys.stdout.write(f"{'RUN-ID':<40} {'SIZE'}\n")
    for f in sorted(RUNS_DIR.glob("*.md")):
        sys.stdout.write(f"{f.stem:<40} {f.stat().st_size}\n")
    return 0


# ---------------------------------------------------------------------------
# query — runs jq via subprocess for exact semantic parity
# ---------------------------------------------------------------------------


def cmd_query(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write(
            "usage: naavik-ops memory query <decisions|discussions|lessons|patterns> '<jq-expr>'\n"
        )
        return 2
    store, expr = rest[0], rest[1]
    _validate_jq_expr(expr)
    path_map = {
        "decisions": DECISIONS,
        "discussions": DISCUSSIONS,
        "lessons": LESSONS,
        "patterns": PATTERNS,
    }
    if store not in path_map:
        raise NaavikOpsError(f"query not supported for '{store}' (use list)")
    path = path_map[store]
    if not path.is_file():
        sys.stdout.write(f"(empty store: {path})\n")
        return 0

    if shutil.which("jq") is None:
        raise NaavikOpsError("jq not on PATH. nix develop.")
    # `jq -c "select($EXPR)"` — same shape as bash.
    cmd = ["jq", "-c", f"select({expr})", str(path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise NaavikOpsError(f"jq failed (exit {e.returncode}): {e.stderr.strip()}") from e
    sys.stdout.write(result.stdout)
    return 0


# Programmatic helpers used by the rest of the dispatcher / scripts.
def capture_list(store: str) -> str:
    """Return `naavik-ops memory list <store>` as captured stdout."""
    import io

    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        cmd_list([store])
    finally:
        sys.stdout = old_stdout
    return buf.getvalue()


def capture_query(store: str, jq_expr: str) -> str:
    import io

    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        cmd_query([store, jq_expr])
    finally:
        sys.stdout = old_stdout
    return buf.getvalue()


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------


def cmd_seed(rest: Sequence[str]) -> int:
    _ = rest
    cmd_init([])
    sys.stdout.write(
        "seed: 5 initial knowledge entries shipped with A.15. "
        "Files live in .claude/memory/knowledge/.\n"
        "seed: this subcommand is informational — seeds are tracked in git via the "
        "gitignore negation\n"
        "      '!.claude/memory/knowledge/' (PR diff carries the .md files; this dispatcher "
        "is the writer\n"
        "      for new entries going forward).\n"
    )
    if KNOWLEDGE_DIR.is_dir():
        for f in sorted(KNOWLEDGE_DIR.iterdir()):
            sys.stdout.write(f"  {f.name}\n")
    return 0


# ---------------------------------------------------------------------------
# analyze-run
# ---------------------------------------------------------------------------


def cmd_analyze_run(rest: Sequence[str]) -> int:
    if not rest:
        sys.stderr.write("usage: naavik-ops memory analyze-run <run-id>\n")
        return 2
    cmd_init([])
    run_id = rest[0]
    trace_dir = TRACES_ROOT / run_id
    if not trace_dir.is_dir():
        raise NaavikOpsError(f"{trace_dir} not found")

    out = RUNS_DIR / f"{run_id}.md"
    manifest = trace_dir / "MANIFEST.json"
    started = ended = milestone = outcome = halt = "unknown"
    tokens_block = "(no manifest)"
    files_block = ""
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            started = data.get("started_at") or "unknown"
            ended = data.get("ended_at") or "unknown"
            milestone = data.get("milestone") or "unknown"
            outcome = data.get("outcome") or "unknown"
            halt = data.get("halt_reason") if data.get("halt_reason") is not None else "null"
            tokens = data.get("tokens_spent") or {}
            tokens_block = "\n".join(f"{k}: {v}" for k, v in tokens.items())
            files = data.get("files_touched") or []
            files_block = "\n".join(files)
        except json.JSONDecodeError:
            pass

    # ERROR aggregation by kind.
    kinds = ("retry", "skip", "halt", "pivot")
    counts = dict.fromkeys(kinds, 0)
    for log in trace_dir.glob("*.log"):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            for kind in kinds:
                if f"kind={kind}" in line:
                    counts[kind] += 1
                    break

    # Final BUILT / REVIEWED line per agent log.
    summaries: list[str] = []
    for log in sorted(trace_dir.glob("*.log")):
        agent = log.stem
        last: str | None = None
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^\[.*\] (BUILT|REVIEWED) ", line):
                last = line
        if last:
            summaries.append(f"- **{agent}** — {last}")

    deviations: str
    devs_file = trace_dir / "engineer-deviations.log"
    if devs_file.is_file():
        dev_lines = [
            f"- {line}"
            for line in devs_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        deviations = "\n".join(dev_lines) if dev_lines else "(none)"
    else:
        deviations = "(none)"

    err_total = sum(counts.values())
    body = []
    body.append(f"# Run analysis — {run_id}")
    body.append("")
    body.append(f"- started: {started}")
    body.append(f"- ended: {ended}")
    body.append(f"- milestone: {milestone}")
    body.append(f"- outcome: {outcome}")
    body.append(f"- halt_reason: {halt}")
    body.append("")
    body.append("## Per-agent token spend")
    body.append("")
    body.append("```")
    body.append(tokens_block)
    body.append("```")
    body.append("")
    body.append("## ERROR events grouped by kind")
    body.append("")
    for kind in kinds:
        body.append(f"- {kind}: {counts[kind]}")
    body.append(f"- TOTAL: {err_total}")
    body.append("")
    body.append("## BUILT / REVIEWED summaries")
    body.append("")
    body.extend(summaries)
    body.append("")
    body.append("## Files touched")
    body.append("")
    body.append("```")
    body.append(files_block)
    body.append("```")
    body.append("")
    body.append("## Deviations recorded")
    body.append("")
    body.append(deviations)
    body.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.name}.tmp.{os.getpid()}")
    tmp.write_text("\n".join(body), encoding="utf-8")
    os.replace(tmp, out)
    sys.stdout.write(f"analyze-run: {out}\n")
    return 0


# ---------------------------------------------------------------------------
# mine-patterns — aggregate ERROR events across recent runs
# ---------------------------------------------------------------------------


def cmd_mine_patterns(rest: Sequence[str]) -> int:
    cmd_init([])
    lookback = 10
    alias_mode = False
    args = list(rest)
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--lookback":
            lookback = int(args[i + 1])
            i += 2
        elif a == "--aliases":
            alias_mode = True
            i += 1
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")

    if alias_mode:
        return _mine_aliases(lookback)

    if not TRACES_ROOT.is_dir():
        sys.stdout.write("(no traces/)\n")
        return 0

    runs = sorted(
        (p for p in TRACES_ROOT.iterdir() if p.is_dir() and re.match(r"^20\d{2}", p.name)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:lookback]

    # Aggregate by (step, kind).
    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for run in runs:
        for log in run.glob("*.log"):
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                if "] ERROR step=" not in line:
                    continue
                step_m = re.search(r"step=(\S+)", line)
                kind_m = re.search(r"kind=(\S+)", line)
                if not step_m or not kind_m:
                    continue
                step = step_m.group(1)
                kind = kind_m.group(1)
                key = (step, kind)
                entry = agg.setdefault(key, {"count": 0, "runs": []})
                entry["count"] += 1
                if run.name not in entry["runs"]:
                    entry["runs"].append(run.name)

    written = 0
    with flock.acquire(LOCK_FILE):
        for (step, kind), entry in agg.items():
            if entry["count"] < 2:
                continue
            pattern_id = f"{step}__{kind}"

            existing = None
            if PATTERNS.is_file():
                for line in PATTERNS.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("pattern_id") == pattern_id:
                        existing = row
                        break

            first_seen = existing.get("first_seen") if existing else _now_iso()
            last_seen = _now_iso()

            record = {
                "pattern_id": pattern_id,
                "step": step,
                "kind": kind,
                "occurrence_count": entry["count"],
                "runs": entry["runs"],
                "first_seen": first_seen,
                "last_seen": last_seen,
                "proposed_action": (existing or {}).get("proposed_action", ""),
            }

            # Rewrite PATTERNS in place: drop any existing row for this pattern_id then append.
            existing_rows: list[dict] = []
            if PATTERNS.is_file():
                for line in PATTERNS.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("pattern_id") != pattern_id:
                        existing_rows.append(row)
            existing_rows.append(record)
            tmp = PATTERNS.with_name(f"{PATTERNS.name}.tmp.{os.getpid()}")
            tmp.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in existing_rows) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, PATTERNS)
            written += 1
    sys.stdout.write(f"mine-patterns: {written} pattern row(s) written/updated to {PATTERNS}\n")
    return 0


def _mine_aliases(lookback: int) -> int:
    if not TRACES_ROOT.is_dir():
        sys.stdout.write("(no traces/)\n")
        return 0
    runs = sorted(
        (p for p in TRACES_ROOT.iterdir() if p.is_dir() and re.match(r"^20\d{2}", p.name)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:lookback]
    sys.stdout.write(
        f"mine-patterns --aliases: scanning last {lookback} runs for MEMORY_MISS events...\n"
    )
    found = 0
    for run in runs:
        mgr = run / "manager.log"
        if not mgr.is_file():
            continue
        for line in mgr.read_text(encoding="utf-8", errors="replace").splitlines():
            if "] MEMORY_MISS " not in line:
                continue
            topic_m = re.search(r"topic=(\S+)", line)
            phrase_m = re.search(r"phrase='([^']+)'", line)
            if not topic_m or not phrase_m:
                continue
            topic = topic_m.group(1)
            phrase = phrase_m.group(1)
            sys.stdout.write(
                f"  {run.name}: topic={topic} phrase='{phrase}' → suggest adding "
                f"to .claude/memory/knowledge/{topic}.md Aliases\n"
            )
            found += 1
    sys.stdout.write(
        f"mine-aliases: {found} candidate(s). Manager surfaces each via "
        "AskUserQuestion before mutating.\n"
    )
    return 0


# ---------------------------------------------------------------------------
# promote-lesson — threshold 5
# ---------------------------------------------------------------------------


def cmd_promote_lesson(rest: Sequence[str]) -> int:
    if not rest:
        sys.stderr.write("usage: naavik-ops memory promote-lesson <pattern_id>\n")
        return 2
    cmd_init([])
    pid = rest[0]

    pattern: dict[str, Any] | None = None
    if PATTERNS.is_file():
        for line in PATTERNS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("pattern_id") == pid:
                pattern = row
                break
    if pattern is None:
        raise NaavikOpsError(f"pattern '{pid}' not in {PATTERNS}")

    count = int(pattern.get("occurrence_count") or 0)
    if count < PROMOTION_THRESHOLD:
        raise NaavikOpsError(
            f"pattern '{pid}' has count={count} (threshold={PROMOTION_THRESHOLD}). Not promoting."
        )

    lesson_id = f"lesson-{pid.replace('_', '-')}"
    pattern_text = f"{pattern.get('step')} / {pattern.get('kind')}"
    action = pattern.get("proposed_action") or ""
    runs_csv = ",".join(pattern.get("runs") or [])

    record_args = [lesson_id, pattern_text, runs_csv]
    if action:
        record_args.extend(["--proposed-action", action])
    cmd_record_lesson(record_args)

    # knowledge stub.
    slug = pid.split("__", 1)[0].lower()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    stub = KNOWLEDGE_DIR / f"{slug}.md"
    if not stub.is_file():
        action_block = action or "(none captured — update via record-knowledge --overwrite)"
        body = (
            f"\n# {slug}\n\n"
            "## Context\n\n"
            f"Promoted from recurring pattern `{pid}` after {count} occurrences across runs.\n\n"
            "## Pattern\n\n"
            f"{pattern_text}\n\n"
            "## Proposed action\n\n"
            f"{action_block}\n\n"
            "## Related\n\n"
            f"- pattern: {pid}\n"
            f"- lesson: {lesson_id}\n"
            f"- runs: {runs_csv}\n"
        )
        # Use record-knowledge via stdin path to land the file with front-matter.
        old_stdin = sys.stdin
        try:
            import io

            sys.stdin = io.StringIO(body)
            cmd_record_knowledge([slug, "-", "--confidence", "medium", "--aliases", ""])
        finally:
            sys.stdin = old_stdin
        sys.stdout.write(f"promote-lesson: lesson {lesson_id} + knowledge stub {stub}\n")
    else:
        sys.stdout.write(
            f"promote-lesson: lesson {lesson_id} (knowledge stub {stub} already exists; "
            "left as-is)\n"
        )
    return 0


# ---------------------------------------------------------------------------
# Direct invocation
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    sys.exit(0)
