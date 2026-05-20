"""plan — plan-lifecycle ops (archive, validate-deviations).

Subcommands:

  archive <plan-path> [--run-id <id>]
                     [--no-material-deviations "<rationale>"]
                     [--force]
                     [--dry-run]
      Promote `engineer-deviations.log` entries into the plan's
      `## Deviations from plan` section, flip frontmatter `Status:` to
      `EXECUTED`, then `git mv` to `docs/plans/archive/`. Refuses with
      exit 2 if the resulting section would be empty AND neither
      `--no-material-deviations` nor `--force` is set.

  validate-deviations <plan-path>
      Read-only: confirm the plan has a non-empty `## Deviations from
      plan` section. Wraps the binary contract enforced by the
      `naavik-deviations-check` skill. Exit 0 = PASS, 2 = BLOCK.

`plan archive` is the canonical, single-writer entry point for any
`docs/plans/<NN>-...md` → `docs/plans/archive/<NN>-...md` move that the
manager performs at operating-loop step 11. Replaces the manual `git mv`
ritual that let 5 of 8 plans archive empty in run
`2026-05-19T15-42-42_833f4a` (see `docs/plans/39-deviation-promotion-hardening.md`).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = REPO_ROOT / "docs" / "plans"
ARCHIVE_DIR = PLANS_DIR / "archive"
PROMPTS_DIR = REPO_ROOT / "docs" / "prompts"
PROMPTS_ARCHIVE_DIR = PROMPTS_DIR / "archive"
TRACES_DIR = REPO_ROOT / "traces"

_DEVIATIONS_HEADING_RE = re.compile(r"^## Deviations from plan\s*$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"^---\n(?P<body>.*?)\n---\n", re.DOTALL)
_STATUS_LINE_RE = re.compile(r"^Status:\s*(?P<value>\S+)", re.MULTILINE)

# DEVIATION line parser. Engineer log line shape per AGENT_OPS § 7.2:
#   [<ISO-ts>] DEVIATION plan=<path> what=<text> why=<text> impact=<text>
# Fields are unquoted by default; some entries quote with single or double
# quotes (observed in run 2026-05-19T15-42-42_833f4a). Parser accepts both.
_DEV_PREFIX_RE = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+DEVIATION\s+plan=(?P<plan>\S+)\s+(?P<rest>.+)$")


@dataclass(frozen=True)
class DeviationEntry:
    timestamp: str
    plan: str
    what: str
    why: str
    impact: str


# -----------------------------------------------------------------------------
# Argument parsing.
# -----------------------------------------------------------------------------


def _build_archive_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="naavik-ops plan archive",
        description="Promote deviations + archive a plan in one atomic op.",
    )
    p.add_argument("plan_path", help="Path to docs/plans/<NN>-<slug>.md (active).")
    p.add_argument(
        "--run-id",
        default=None,
        help="Trace run-id; defaults to most-recent traces/<run-id>/ dir.",
    )
    p.add_argument(
        "--no-material-deviations",
        metavar="RATIONALE",
        default=None,
        help='Write "No material deviations — <rationale>." in lieu of lifting entries.',
    )
    p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Archive even when the plan's `## Deviations from plan` section "
            "is already non-empty (skip the log-lift step). Use when section "
            "was hand-authored."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen; no file writes or git operations.",
    )
    return p


# -----------------------------------------------------------------------------
# Public dispatch entry points.
# -----------------------------------------------------------------------------


def cmd_archive(rest: Sequence[str]) -> int:
    args = _build_archive_parser().parse_args(rest)
    plan_path = _resolve_plan_path(args.plan_path)

    if _is_already_archived(plan_path):
        sys.stderr.write(f"plan archive: '{plan_path}' is already under docs/plans/archive/\n")
        return 2

    section_already_populated = _has_nonempty_deviations_section(plan_path)

    if args.no_material_deviations is not None:
        if section_already_populated and not args.force:
            sys.stderr.write(
                "plan archive: --no-material-deviations refused — section already "
                "populated. Use --force to override.\n"
            )
            return 2
        bullets = [f"- No material deviations — {args.no_material_deviations.strip()}."]
        entries: list[DeviationEntry] = []
    elif args.force and section_already_populated:
        bullets = []
        entries = []
    else:
        run_id = args.run_id or _pick_latest_run_id()
        entries = _read_deviation_entries(run_id, plan_path) if run_id else []
        if not entries:
            if section_already_populated:
                if not args.force:
                    sys.stderr.write(
                        f"plan archive: '{plan_path}' already has a non-empty "
                        "`## Deviations from plan` section but no matching entries "
                        f"found in engineer-deviations.log for run_id={run_id!r}.\n"
                        "Reconciliation needed: hand-edit the section then re-run "
                        "with --force, or run with --no-material-deviations "
                        '"<rationale>" if truly no material deviations.\n'
                    )
                    return 2
                bullets = []
            else:
                sys.stderr.write(
                    f"plan archive: refusing to archive '{plan_path}' — no entries "
                    f"in engineer-deviations.log matched plan=<{_to_repo_rel(plan_path)}> "
                    f"under run_id={run_id!r} (or no run found under traces/).\n"
                    'Pass --no-material-deviations "<rationale>" if truly none, '
                    "or hand-author the section + re-run with --force.\n"
                )
                return 2
        else:
            bullets = [_entry_to_bullet(e) for e in entries]

    surfaces = _extract_surfaces(entries)

    if args.dry_run:
        _print_dry_run(plan_path, bullets, surfaces)
        return 0

    # 0.7.0.21d — snapshot pre-mutation text for partial-write rollback.
    original_text = plan_path.read_text(encoding="utf-8")
    if bullets:
        _append_deviations_section(plan_path, bullets)
    _update_frontmatter_status(plan_path)
    target_path = _git_mv_plan_and_prompt(plan_path, original_text=original_text)

    _print_archive_summary(plan_path, target_path, len(bullets), surfaces)
    return 0


def cmd_validate_deviations(rest: Sequence[str]) -> int:
    if not rest or rest[0] in ("-h", "--help"):
        sys.stdout.write("usage: naavik-ops plan validate-deviations <plan-path>\n")
        return 0 if rest else 2
    plan_path = _resolve_plan_path(rest[0])
    if _has_nonempty_deviations_section(plan_path):
        sys.stdout.write(f"PASS — {_to_repo_rel(plan_path)} has non-empty Deviations section.\n")
        return 0
    sys.stderr.write(
        f"BLOCK — {_to_repo_rel(plan_path)} missing or empty `## Deviations from plan` "
        "section. Run `naavik-ops plan archive ...` to lift entries from "
        "engineer-deviations.log.\n"
    )
    return 2


# -----------------------------------------------------------------------------
# Plan-path resolution + frontmatter ops.
# -----------------------------------------------------------------------------


def _resolve_plan_path(raw: str) -> Path:
    p = Path(raw)
    p = (REPO_ROOT / raw).resolve() if not p.is_absolute() else p.resolve()
    if not p.exists():
        raise SystemExit(f"plan archive: plan not found: {raw}")
    if not p.name.endswith(".md"):
        raise SystemExit(f"plan archive: plan must be a .md file: {raw}")
    # 0.7.0.21a — path-traversal hardening. Constrain to docs/plans/ subtree
    # (active or archived). Refuses arbitrary repo .md files; refuses paths
    # already under archive/ unless invoked via validate-deviations (caller
    # passes ARCHIVE_DIR-rooted paths intentionally for re-validation).
    try:
        p.relative_to(PLANS_DIR)
    except ValueError as e:
        raise SystemExit(
            f"plan archive: path must live under docs/plans/ subtree: {raw} "
            f"(resolved to {p}). Refusing for path-traversal hygiene."
        ) from e
    return p


def _to_repo_rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def _is_already_archived(plan_path: Path) -> bool:
    try:
        return ARCHIVE_DIR in plan_path.parents
    except ValueError:
        return False


def _has_nonempty_deviations_section(plan_path: Path) -> bool:
    text = plan_path.read_text(encoding="utf-8")
    m = _DEVIATIONS_HEADING_RE.search(text)
    if not m:
        return False
    body = text[m.end() :]
    next_heading = re.search(r"^##\s", body, re.MULTILINE)
    section_body = body[: next_heading.start()] if next_heading else body
    stripped = section_body.strip()
    if not stripped:
        return False
    # 0.7.0.21b — accept bullets (preferred shape).
    has_bullet = re.search(r"^\s*[-*]\s+\S", stripped, re.MULTILINE)
    if has_bullet is not None:
        return True
    # 0.7.0.21c — accept paragraph-style explicit-no-deviations sentinel.
    # Authors may write "No material deviations." prose when nothing diverged.
    # Validate this is meaningful content (not just whitespace) AND contains
    # the sentinel phrase. Substantive prose without the sentinel still BLOCKS
    # because we want explicit signaling, not implicit "this is enough text".
    if re.search(r"no material deviations", stripped, re.IGNORECASE):
        return True
    return False


def _append_deviations_section(plan_path: Path, bullets: Sequence[str]) -> None:
    text = plan_path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    bullets_block = "\n".join(bullets) + "\n"

    m = _DEVIATIONS_HEADING_RE.search(text)
    if m is None:
        if not text.endswith("\n\n"):
            text += "\n"
        text += "## Deviations from plan\n\n" + bullets_block
    else:
        body = text[m.end() :]
        next_heading = re.search(r"^##\s", body, re.MULTILINE)
        section_body = body[: next_heading.start()] if next_heading else body
        section_stripped = section_body.strip()
        if section_stripped:
            new_section = section_body.rstrip() + "\n" + bullets_block + "\n"
        else:
            new_section = "\n" + bullets_block + ("\n" if next_heading else "")
        text = (
            text[: m.end()] + new_section + (body[next_heading.start() :] if next_heading else "")
        )
    plan_path.write_text(text, encoding="utf-8")


def _update_frontmatter_status(plan_path: Path) -> None:
    text = plan_path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return
    body = m.group("body")
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    status_m = _STATUS_LINE_RE.search(body)
    if status_m:
        new_body = body[: status_m.start()] + "Status: EXECUTED" + body[status_m.end() :]
    else:
        new_body = body + "\nStatus: EXECUTED"
    if "Shipped:" not in new_body:
        new_body = new_body.rstrip() + f"\nShipped: {today}"
    new_text = "---\n" + new_body + "\n---\n" + text[m.end() :]
    plan_path.write_text(new_text, encoding="utf-8")


# -----------------------------------------------------------------------------
# git mv (plan + matching prompt).
# -----------------------------------------------------------------------------


def _git_mv_plan_and_prompt(plan_path: Path, *, original_text: str | None = None) -> Path:
    """Atomic-ish archive: git mv plan + prompt (if exists).

    0.7.0.21d — Partial-write rollback. If the plan file was mutated in-place
    (Deviations section appended + Status flipped) and then `git mv` fails
    (dirty tree, file outside repo, permission denied, etc.), restore the
    original text so the working tree isn't left with a mutated-not-archived
    plan. Caller passes `original_text` (pre-mutation snapshot).
    """
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    target = ARCHIVE_DIR / plan_path.name
    try:
        _run_git("mv", str(plan_path), str(target))
    except SystemExit:
        if original_text is not None and plan_path.exists():
            plan_path.write_text(original_text, encoding="utf-8")
        raise

    prompt_src = PROMPTS_DIR / plan_path.name
    if prompt_src.exists():
        PROMPTS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        prompt_target = PROMPTS_ARCHIVE_DIR / plan_path.name
        try:
            _run_git("mv", str(prompt_src), str(prompt_target))
        except SystemExit:
            # Plan already moved successfully; prompt-mv failure is partial.
            # Roll back plan-mv to keep the working tree internally consistent.
            try:
                _run_git("mv", str(target), str(plan_path))
            except SystemExit:
                pass  # Best-effort; surface original error.
            if original_text is not None and plan_path.exists():
                plan_path.write_text(original_text, encoding="utf-8")
            raise
    return target


def _run_git(*args: str) -> None:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"plan archive: `git {' '.join(args)}` failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()}"
        )


# -----------------------------------------------------------------------------
# engineer-deviations.log parser.
# -----------------------------------------------------------------------------


def _pick_latest_run_id() -> str | None:
    if not TRACES_DIR.exists():
        return None
    runs = sorted(
        (p.name for p in TRACES_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")),
        reverse=True,
    )
    return runs[0] if runs else None


def _read_deviation_entries(run_id: str, plan_path: Path) -> list[DeviationEntry]:
    log_path = TRACES_DIR / run_id / "engineer-deviations.log"
    if not log_path.exists():
        return []
    rel = _to_repo_rel(plan_path)
    plan_basename = plan_path.name
    out: list[DeviationEntry] = []
    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _DEV_PREFIX_RE.match(line)
        if not m:
            continue
        log_plan = m.group("plan")
        if not _plan_matches(log_plan, rel, plan_basename):
            continue
        fields = _parse_kv_fields(m.group("rest"))
        what = fields.get("what")
        why = fields.get("why")
        impact = fields.get("impact")
        if not (what and why and impact):
            continue
        out.append(
            DeviationEntry(
                timestamp=m.group("ts"),
                plan=log_plan,
                what=what,
                why=why,
                impact=impact,
            )
        )
    out.sort(key=lambda e: e.timestamp)
    return out


def _plan_matches(log_plan: str, target_rel: str, target_basename: str) -> bool:
    if log_plan == target_rel:
        return True
    if log_plan.endswith("/" + target_basename):
        return True
    return Path(log_plan).name == target_basename


def _parse_kv_fields(rest: str) -> dict[str, str]:
    """Split `what=... why=... impact=...` on top-level `<key>=` markers.

    Accepts unquoted values (the canonical format) AND single/double-quoted
    values (observed in some engineer logs). Quoted values are unwrapped so
    callers don't see the wrapping quote characters in the rendered bullet.
    """
    keys = ("what", "why", "impact")
    starts: list[tuple[int, str]] = []
    for key in keys:
        idx = _find_key_start(rest, key)
        if idx >= 0:
            starts.append((idx, key))
    starts.sort()
    out: dict[str, str] = {}
    for i, (idx, key) in enumerate(starts):
        value_start = idx + len(key) + 1
        value_end = starts[i + 1][0] if i + 1 < len(starts) else len(rest)
        raw = rest[value_start:value_end].strip()
        out[key] = _unwrap_quotes(raw)
    return out


def _find_key_start(rest: str, key: str) -> int:
    needle = f"{key}="
    idx = 0
    while True:
        found = rest.find(needle, idx)
        if found < 0:
            return -1
        if found == 0 or rest[found - 1] in (" ", "\t"):
            return found
        idx = found + 1


def _unwrap_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value


def _entry_to_bullet(e: DeviationEntry) -> str:
    title = _derive_title(e.what)
    surface = _detect_surface(e.impact)
    # 0.7.0.21b — periods between fields for readability (plan 39 § C.7).
    return (
        f"- **{title}** — what: {e.what}. why: {e.why}. "
        f"impact: {e.impact}. surface: {surface}."
    )


def _derive_title(what: str) -> str:
    cleaned = re.sub(r"\s+", " ", what.strip())
    # Drop trailing punctuation from the harvested first chunk.
    words = cleaned.split(" ")
    head = " ".join(words[:6])
    head = head.rstrip(".,;:")
    if len(head) > 60:
        head = head[:57].rstrip() + "..."
    return head or "Deviation"


#: Ordered: more-specific patterns must come before less-specific ones.
_SURFACE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("naavik-ops", "naavik-ops subcommand"),
    ("env var", "env var"),
    ("environment variable", "env var"),
    (".env.example", "env var"),
    (".env ", "env var"),
    (".env\t", "env var"),
    ("~/.naavik", "on-disk path"),
    ("on-disk", "on-disk path"),
    ("mode 0600", "on-disk path"),
    ("port ", "port"),
    ("apscheduler", "cron schedule"),
    ("cron", "cron schedule"),
    ("schedule", "cron schedule"),
    ("alembic", "db migration"),
    ("migration", "db migration"),
    ("subcommand", "cli subcommand"),
    ("cli ", "cli subcommand"),
    ("secret", "secret"),
)


def _detect_surface(impact: str) -> str:
    impact_lower = impact.lower()
    for needle, surface in _SURFACE_PATTERNS:
        if needle in impact_lower:
            return surface
    return "none"


def _extract_surfaces(entries: Sequence[DeviationEntry]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for e in entries:
        s = _detect_surface(e.impact)
        if s != "none" and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# -----------------------------------------------------------------------------
# STDOUT formatters.
# -----------------------------------------------------------------------------


def _print_dry_run(plan_path: Path, bullets: Sequence[str], surfaces: Sequence[str]) -> None:
    sys.stdout.write(f"DRY-RUN plan archive {_to_repo_rel(plan_path)}\n")
    sys.stdout.write(f"  Would write {len(bullets)} bullet(s) to `## Deviations from plan`:\n")
    for b in bullets:
        sys.stdout.write(f"    {b}\n")
    if surfaces:
        sys.stdout.write(f"  Surface propagation required: {', '.join(surfaces)}\n")
    sys.stdout.write(
        f"  Would `git mv` to docs/plans/archive/{plan_path.name} + flip Status: EXECUTED.\n"
    )


def _print_archive_summary(
    plan_path: Path,
    target_path: Path,
    n_bullets: int,
    surfaces: Sequence[str],
) -> None:
    sys.stdout.write(f"ARCHIVED {_to_repo_rel(plan_path)}\n")
    sys.stdout.write(f"  -> {_to_repo_rel(target_path)}\n")
    sys.stdout.write(f"  Deviations promoted: {n_bullets} bullet(s)\n")
    if surfaces:
        sys.stdout.write(
            "  Surface propagation required (manager edits — no auto-apply): "
            f"{', '.join(surfaces)}\n"
        )
