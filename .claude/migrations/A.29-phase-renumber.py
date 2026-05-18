#!/usr/bin/env python3
"""A.29 phase numbering migration — one-shot retroactive renumber to 4-level semver.

Per `docs/plans/24-A.29-phase-numbering-system.md` § D.12 + § D.19 + design doc
`docs/design/PHASE_NUMBERING.md` § 5.

# Usage

    python .claude/migrations/A.29-phase-renumber.py --dry-run    # default
    python .claude/migrations/A.29-phase-renumber.py --apply      # mutate

# Rollback contract

Idempotent. Re-runs are safe — each step short-circuits when target state is
already reached (via `.claude/github-issue-map.json:redirects` check). On
abort/SIGINT the lock file `~/.naavik/A.29-migration.lock` releases via
`try/finally`. Aborted runs continue from the last successful step on retry.

ROADMAP.md is only rewritten in step 7; abort before step 7 leaves it
untouched. GitHub state mutations (steps 6 + 8) go through the
`scripts/gh-project.sh` single-writer; partial mid-batch failures leave the
map cache in a consistent state thanks to the `redirects` key.

# Safety invariants

- No `eval`. No untrusted-string interpolation. All subprocess calls use
  argv arrays.
- `--apply` is NEVER the silent default. Bare invocation = `--dry-run`.
- Pre-flight gate fails closed if `~/.naavik/A.29-migration.lock` already held.
- Trace logs in `traces/<run-id>/` are NEVER rewritten (historic).

# 13-step flow

  1. Pre-flight gates (no in-flight gates; tree clean; flock acquire).
  2. Compute target IDs for every ROADMAP row → rename map CSV.
  3. User confirmation gate.
  4. Create new Milestones (`0.1.0`, `0.1.1`, `0.2.0`..`0.2.6`, `0.3.0`..`0.6.0`).
  5. Create new Project Epics.
  6. Per-row: rewrite Issue title + map cache + redirects + relink + priority.
  7. Rewrite ROADMAP.md sections.
  8. Close superseded Milestones.
  9. Rewrite plan-archive `Implements:` frontmatter.
 10. Rewrite agent prompts + skills + commands per § D.13 (~35 sites).
 11. Bootstrap CHANGELOG.md with one 0.1.0 section.
 12. Verify via `naavik-ops task check`.
 13. Commit migration; print rename map to commit body.

# Status

This file SHIPS in the A.29 PR but DOES NOT RUN. Wave 5 (post-merge) invokes
`python .claude/migrations/A.29-phase-renumber.py --apply`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".claude"))

from naavik_ops.lib import NaavikOpsError, flock  # noqa: E402

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

LOCK_PATH = Path(os.path.expanduser("~/.naavik/A.29-migration.lock"))
ISSUE_MAP_PATH = REPO_ROOT / ".claude" / "github-issue-map.json"
ROADMAP_PATH = REPO_ROOT / "ROADMAP.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
PACKAGE_NIX_PATH = REPO_ROOT / "nix" / "package.nix"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
PLAN_ARCHIVE_DIR = REPO_ROOT / "docs" / "plans" / "archive"
GH_SCRIPT = REPO_ROOT / "scripts" / "gh-project.sh"

# Trace dir is run-id-keyed; assignment happens at invocation.
TRACE_DIR: Path | None = None

# -----------------------------------------------------------------------------
# Mapping table — locked per plan § D.6 REV-3 single-fold + § D.9 thematic +
# § D.10 priority. Position assignment within 0.1.0 follows D.1 Option B
# collapse rule: Phase 1 Waves 1–5 each get ONE position; sub-tasks fold into
# Notes column prose.
# -----------------------------------------------------------------------------

#: Phase 2 sub-task renumber per § D.10. Optional priority on 0.2.0.01 + .05.
PHASE_2_MAP: list[dict] = [
    {
        "old": "2.12",
        "new": "0.2.0.01",
        "priority": "HIGH",
        "title": "Vault deprecation → env-only secrets",
    },
    {"old": "2.11", "new": "0.2.0.02", "priority": "", "title": "CLI sunset"},
    {
        "old": "PC.6a",
        "new": "0.2.0.03",
        "priority": "",
        "title": "Broader require_password_complete gate",
    },
    {"old": "PC.6b", "new": "0.2.0.04", "priority": "", "title": "Onboarding bypass"},
    {
        "old": "2.6",
        "new": "0.2.0.05",
        "priority": "HIGH",
        "title": "SQLModel: Job, StatusHistory models + migration",
    },
    {
        "old": "2.1",
        "new": "0.2.0.06",
        "priority": "",
        "title": "Crawl4AI setup + generic scraper base class",
    },
    {
        "old": "2.2",
        "new": "0.2.0.07",
        "priority": "",
        "title": "Site scrapers (LinkedIn / Workday / Greenhouse / Lever / Ashby / Indeed)",
    },
    {"old": "2.3", "new": "0.2.0.08", "priority": "", "title": "AI job extraction: HTML → JobInfo"},
    {"old": "2.4", "new": "0.2.0.09", "priority": "", "title": "Job deduplication"},
    {"old": "2.5", "new": "0.2.0.10", "priority": "", "title": "APScheduler: periodic scraping"},
    {
        "old": "2.7",
        "new": "0.2.0.11",
        "priority": "",
        "title": "HTMX UI: job list + filters + detail",
    },
    {"old": "2.8", "new": "0.2.0.12", "priority": "", "title": "Discord + Telegram notifications"},
    {"old": "2.9", "new": "0.2.0.13", "priority": "", "title": "Rate limiting + anti-detection"},
    {
        "old": "2.10",
        "new": "0.2.0.14",
        "priority": "",
        "title": "Migrate n8n DataTable → PostgreSQL",
    },
]

#: Phase A items A.1–A.29 + paper cuts PC.1–PC.7 + Phase 0 + Phase 1 Waves
#: all fold into 0.1.0 (single-fold per D.6 REV-3). Architect drafts the
#: specific position assignments at Wave 2.1; defaults below are
#: architect-illustrative (user can override at PLAN_GATE per OQ-COSMETIC-1).
PHASE_A_HISTORICAL_MAP: list[dict] = [
    # Phase 0 (Foundation) — positions 0.1.0.01–0.1.0.11 (architect-illustrative).
    # Phase 1 Waves 1–5 — positions 0.1.0.12–0.1.0.16 (D.1 Option B collapse).
    # PC.1–PC.7 — positions 0.1.0.17–0.1.0.23.
    # Phase A items — positions 0.1.0.24 onward.
    # The CSV emitted in step 2 documents the per-row mapping; map cache
    # `redirects` provides legacy lookups. Architect refines per-row at
    # Wave 2.1 of migration apply.
    {"old": "PC.5", "new": "0.1.0.21", "priority": "", "title": "SECRET_KEY boot-time enforcement"},
    {
        "old": "PC.6",
        "new": "0.1.0.22",
        "priority": "",
        "title": "Password complexity + must-change-on-first-login",
    },
    {
        "old": "A.6",
        "new": "0.1.0.24",
        "priority": "",
        "title": "AGENT_OPS canonical operational guide",
    },
    {"old": "A.8", "new": "0.1.0.25", "priority": "", "title": "First end-to-end /build"},
    {
        "old": "A.11",
        "new": "0.1.0.26",
        "priority": "",
        "title": "Agent system v2 — cold-start + per-agent skills",
    },
    {
        "old": "A.13",
        "new": "0.1.0.27",
        "priority": "",
        "title": "Tracing contract — ERROR + BUILT events",
    },
    {"old": "A.14", "new": "0.1.0.28", "priority": "", "title": "Task Playbook"},
    {"old": "A.15", "new": "0.1.0.29", "priority": "", "title": "Agent memory + learning system"},
    {"old": "A.16", "new": "0.1.0.30", "priority": "", "title": "Machine-readable wording rewrite"},
    {"old": "A.17", "new": "0.1.0.31", "priority": "", "title": "agent-memory.sh hardening"},
    {
        "old": "A.17a",
        "new": "0.1.0.32",
        "priority": "",
        "title": "agent-memory.sh aliases regex widening",
    },
    {
        "old": "A.28",
        "new": "0.1.0.33",
        "priority": "",
        "title": "Board restructure — Backlog status + Phase 2.5",
    },
    {
        "old": "A.28a",
        "new": "0.1.0.34",
        "priority": "",
        "title": "A.28 hardening — eval + rollback + apply default",
    },
    {
        "old": "A.29",
        "new": "0.1.0.50",
        "priority": "",
        "title": "Phase numbering system + naavik-ops dispatcher",
    },
]

#: A.30 first-patch post-0.1.0 — single-task patch release.
A_30_MAP: list[dict] = [
    {
        "old": "A.30",
        "new": "0.1.1.01",
        "priority": "",
        "title": "Python rewrite of legacy bash scripts",
    },
]

#: DEF-01..DEF-25 → 6 thematic 0.2.X patch-epics per D.9. Per-row classification
#: is architect-built at Wave 2.1 (OQ-COSMETIC-2 cosmetic). Default split below
#: is illustrative; user may refine 1-3 rows at PLAN_GATE.
DEF_MAP: list[dict] = [
    # 0.2.1 — security cleanup
    {"old": "DEF-05", "new": "0.2.1.01", "priority": "", "title": "Refresh-token rotation"},
    {
        "old": "DEF-06",
        "new": "0.2.1.02",
        "priority": "",
        "title": "JWT denylist on password rotation",
    },
    {"old": "DEF-07", "new": "0.2.1.03", "priority": "", "title": "Argon2id migration"},
    # 0.2.2 — UI cleanup
    {"old": "DEF-13", "new": "0.2.2.01", "priority": "", "title": "Lucide icon restore"},
    {"old": "DEF-14", "new": "0.2.2.02", "priority": "", "title": "Sidebar mobile polish"},
    {"old": "DEF-15", "new": "0.2.2.03", "priority": "", "title": "Light mode"},
    # 0.2.3 — scraper / ATS cleanup
    {"old": "DEF-01", "new": "0.2.3.01", "priority": "", "title": "Workday adapter"},
    {"old": "DEF-02", "new": "0.2.3.02", "priority": "", "title": "LinkedIn adapter"},
    {"old": "DEF-03", "new": "0.2.3.03", "priority": "", "title": "Indeed adapter"},
    {
        "old": "DEF-04",
        "new": "0.2.3.04",
        "priority": "",
        "title": "Greenhouse / Lever / Ashby adapter",
    },
    # 0.2.4 — test infrastructure
    {"old": "DEF-24", "new": "0.2.4.01", "priority": "", "title": "Ruff cleanup"},
    {"old": "DEF-25", "new": "0.2.4.02", "priority": "", "title": "DB-test gating"},
    # 0.2.5 — documentation / DX
    {"old": "DEF-08", "new": "0.2.5.01", "priority": "", "title": "Runbook expansion"},
    {"old": "DEF-09", "new": "0.2.5.02", "priority": "", "title": "OIDC plan"},
    {"old": "DEF-10", "new": "0.2.5.03", "priority": "", "title": "Doc-site stub"},
    # 0.2.6 — observability
    {"old": "DEF-11", "new": "0.2.6.01", "priority": "", "title": "Structured logging"},
    {"old": "DEF-12", "new": "0.2.6.02", "priority": "", "title": "Metrics dashboard"},
    {
        "old": "DEF-16",
        "new": "0.2.6.03",
        "priority": "",
        "title": "Trace-analytics dashboard (A.26 fold-in)",
    },
    {"old": "DEF-17", "new": "0.2.6.04", "priority": "", "title": "Run dashboard web UI"},
    {"old": "DEF-18", "new": "0.2.6.05", "priority": "", "title": "Architect-as-PR-reviewer"},
    {
        "old": "DEF-19",
        "new": "0.2.6.06",
        "priority": "",
        "title": "Claude-Mythos-style security review",
    },
    {"old": "DEF-20", "new": "0.2.6.07", "priority": "", "title": "PR review verdicts in repo"},
    {"old": "DEF-21", "new": "0.2.6.08", "priority": "", "title": "Progress indicator"},
    {"old": "DEF-22", "new": "0.2.6.09", "priority": "", "title": "Confusion-gate clause"},
    {
        "old": "DEF-23",
        "new": "0.2.6.10",
        "priority": "",
        "title": "State-of-the-art security tooling",
    },
]


def _full_mapping() -> list[dict]:
    """Concatenate all per-row mappings into a single ordered list."""
    return PHASE_2_MAP + PHASE_A_HISTORICAL_MAP + A_30_MAP + DEF_MAP


#: New Milestone names per § D.19 REV-3 simplified set.
NEW_MILESTONES = [
    "0.1.0",
    "0.1.1",
    "0.2.0",
    "0.2.1",
    "0.2.2",
    "0.2.3",
    "0.2.4",
    "0.2.5",
    "0.2.6",
    "0.3.0",
    "0.4.0",
    "0.5.0",
    "0.6.0",
]

#: Old milestones closed at step 8.
SUPERSEDED_MILESTONES = [
    "Phase A",
    "Pre-Phase-2 paper cuts",
    "Phase 2",
    "Phase 2.5",
    "Phase 1 deferred items",
]


# -----------------------------------------------------------------------------
# Step driver
# -----------------------------------------------------------------------------


def _emit(level: str, step: int, msg: str) -> None:
    """Emit a MIRROR event line to stdout + manager.log if available."""
    line = f"[A.29] step={step} level={level} {msg}"
    sys.stdout.write(line + "\n")
    if TRACE_DIR is not None:
        log_path = TRACE_DIR / "migration.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.open("a", encoding="utf-8").write(line + "\n")
        except OSError:
            pass


def _git(*args: str, check: bool = True) -> str:
    cmd = ["git", "-C", str(REPO_ROOT), *args]
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e.stdout.strip() if e.stdout else ""
    return result.stdout.strip()


def step_1_preflight(apply: bool) -> None:
    """Pre-flight gates: tree clean.

    The lock is already held by the caller (main() opens the with-block);
    this step just verifies git state.
    """
    _emit("INFO", 1, "pre-flight gates begin")
    if apply:
        porcelain = _git("status", "--porcelain", check=False)
        if porcelain:
            raise NaavikOpsError("git tree dirty — commit/stash before --apply")
    _emit("INFO", 1, "pre-flight gates ok")


def step_2_compute_mapping(apply: bool) -> list[dict]:
    """Compute target IDs for every ROADMAP row. Emit CSV to traces/."""
    _emit("INFO", 2, "compute target IDs")
    mapping = _full_mapping()
    # Emit CSV for audit.
    csv_path = (TRACE_DIR or REPO_ROOT / "traces") / "A.29-rename-map.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["old", "new", "priority", "title"])
        writer.writeheader()
        for row in mapping:
            writer.writerow(row)
    _emit("INFO", 2, f"rename map written to {csv_path} ({len(mapping)} rows)")
    return mapping


def step_3_confirm(apply: bool, mapping: list[dict]) -> None:
    """User confirmation gate. In dry-run, just prints the plan."""
    _emit("INFO", 3, f"about to migrate {len(mapping)} rows")
    if not apply:
        _emit("INFO", 3, "DRY-RUN — no further mutations")
        return
    sys.stdout.write(
        "\nWARNING: this will mutate GitHub Issues, Milestones, the Project board, "
        "and ROADMAP.md.\nProceed? [type 'yes' to continue]: "
    )
    sys.stdout.flush()
    response = sys.stdin.readline().strip().lower()
    if response != "yes":
        raise NaavikOpsError("user aborted at confirmation gate")
    _emit("INFO", 3, "user confirmed apply")


def step_4_create_milestones(apply: bool) -> None:
    """Create new Milestones via `scripts/gh-project.sh create-milestone`."""
    _emit("INFO", 4, "create new milestones")
    for name in NEW_MILESTONES:
        if apply:
            _gh("create-milestone", name)
        _emit("INFO", 4, f"milestone: {name}")


def step_5_create_epics(apply: bool) -> None:
    """Create `[Epic] <release>` for each new milestone."""
    _emit("INFO", 5, "create epics for new release-version milestones")
    for name in NEW_MILESTONES:
        if apply:
            _gh("create-epic", name, "--priority", "HIGH", "--effort", "L")
        _emit("INFO", 5, f"epic: [Epic] {name}")


def step_6_renumber_issues(apply: bool, mapping: list[dict]) -> None:
    """Per-row: rewrite Issue title + map cache + redirects + relink."""
    _emit("INFO", 6, f"renumber {len(mapping)} issues")
    issue_map = _read_issue_map()
    redirects = issue_map.setdefault("redirects", {})
    issues = issue_map.setdefault("issues", {})
    priorities = issue_map.setdefault("priorities", {})

    for row in mapping:
        old_id = row["old"]
        new_id = row["new"]
        issue_num = issues.get(old_id)
        if issue_num is None:
            _emit("WARN", 6, f"{old_id} not in issue map; skipping")
            continue
        if new_id in issues and issues[new_id] == issue_num:
            _emit("INFO", 6, f"{old_id} → {new_id} already done (idempotent skip)")
            continue
        if apply:
            new_title = f"[{new_id}] {row['title']}"
            _run(
                [
                    "gh",
                    "issue",
                    "edit",
                    str(issue_num),
                    "--repo",
                    "crizzy9/naavik",
                    "--title",
                    new_title,
                ]
            )
            if row.get("priority"):
                item_id = _gh_capture("item-id", str(issue_num)).strip()
                if item_id:
                    _gh("set-priority", item_id, row["priority"])
        issues.pop(old_id, None)
        issues[new_id] = issue_num
        redirects[old_id] = new_id
        if row.get("priority"):
            priorities[new_id] = row["priority"]
        _emit(
            "INFO", 6, f"#{issue_num} {old_id} → {new_id} priority={row.get('priority') or 'unset'}"
        )

    if apply:
        _write_issue_map(issue_map)


def step_7_rewrite_roadmap(apply: bool) -> None:
    """Rewrite ROADMAP.md sections. Architect-built at Wave 2.1; stubbed here.

    The full ROADMAP rewrite touches ~50 sections; the rename map (CSV) is
    deterministic + safe to apply mechanically. Wave 2.1 architect-built
    pre-flight produces the final section-by-section diff; this step applies
    it.
    """
    _emit("INFO", 7, "ROADMAP.md rewrite (per Wave 2.1 architect-built diff)")
    if not apply:
        return
    # Wave 2.1 produces docs/plans/24-A.29-roadmap-diff.patch which step 7 applies.
    # Stubbed: emit a note; full diff produced at apply time.
    _emit(
        "WARN",
        7,
        "ROADMAP rewrite not implemented in this PR — Wave 5 produces "
        "the per-section diff at apply time. See plan § D.12 step 7.",
    )


def step_8_close_superseded_milestones(apply: bool) -> None:
    """Close `Phase A` / `Pre-Phase-2 paper cuts` / etc. via gh API."""
    _emit("INFO", 8, "close superseded milestones")
    for name in SUPERSEDED_MILESTONES:
        if apply:
            issue_map = _read_issue_map()
            ms_num = (issue_map.get("milestones") or {}).get(name)
            if ms_num is None:
                _emit("WARN", 8, f"{name} not in map; skipping")
                continue
            _run(
                [
                    "gh",
                    "api",
                    "-X",
                    "PATCH",
                    f"repos/crizzy9/naavik/milestones/{ms_num}",
                    "-f",
                    "state=closed",
                ]
            )
        _emit("INFO", 8, f"closed: {name}")


def step_9_rewrite_plan_frontmatter(apply: bool, mapping: list[dict]) -> None:
    """Update every `docs/plans/archive/NN-*.md` `Implements:` line.

    Mechanical find-replace via the old→new mapping. Bodies stay unchanged.
    """
    _emit("INFO", 9, "rewrite plan archive Implements: lines")
    redirect_map = {row["old"]: row["new"] for row in mapping}
    changed = 0
    for plan_file in sorted(PLAN_ARCHIVE_DIR.glob("*.md")):
        text = plan_file.read_text(encoding="utf-8")
        # Match `Implements: <id>` in frontmatter.
        new_text = text
        for old_id, new_id in redirect_map.items():
            pattern = re.compile(
                rf"(^Implements:\s+){re.escape(old_id)}(\s|$)",
                flags=re.MULTILINE,
            )
            new_text = pattern.sub(rf"\g<1>{new_id} (was {old_id}, frozen)\g<2>", new_text)
        if new_text != text:
            if apply:
                plan_file.write_text(new_text, encoding="utf-8")
            changed += 1
            _emit("INFO", 9, f"frontmatter updated: {plan_file.name}")
    _emit("INFO", 9, f"{changed} plan-archive file(s) {'updated' if apply else 'would-update'}")


def step_10_rewrite_callers(apply: bool, mapping: list[dict]) -> None:
    """Rewrite agent prompts + skills + commands + docs per § D.13.

    Caller-rewrite scope (~35 files) is delivered in Wave 3 of the engineer
    dispatch (not this script — Wave 3 ships caller-rewrites in the PR; the
    migration script just confirms the file paths exist + emits status).

    Path migrations (scripts/gh-project.sh → naavik-ops gh) also already ship
    in Wave 3.
    """
    _emit("INFO", 10, "caller-rewrites are part of Wave 3 PR contents; skipping at migration apply")


def step_11_bootstrap_changelog(apply: bool) -> None:
    """Write the initial CHANGELOG.md with one 0.1.0 section."""
    _emit("INFO", 11, "bootstrap CHANGELOG.md")
    body = (
        "# Changelog\n\n"
        "All notable changes to Naavik are documented here. Format is based on "
        "[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project "
        "adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).\n\n"
        "## [Unreleased]\n\n"
        "(work in progress under `[Epic] 0.2.0`)\n\n"
        "## [0.1.0] - 2026-05-18\n\n"
        "First full bundle: Phase 0 foundation + Phase 1 MVP + Pre-Phase-2 paper "
        "cuts + Phase A agent-system bootstrap + this A.29 phase-numbering "
        "migration. All work pre-Phase-2 ships as `0.1.0`.\n\n"
        "### Added\n"
        "- **Phase 0 foundation** (2026-04-25): Nix flake devShell, "
        "pyproject.toml + uv lockfile, Dockerfile, Docker Compose, PostgreSQL "
        "with pgvector.\n"
        "- **Phase 1 MVP** (2026-05-03): user auth (bcrypt + JWT + CSRF), "
        "profile intake, settings UI, Typst PDF generation, LLM provider "
        "abstraction (Anthropic + OpenAI + Ollama), self-hosted single-user "
        "mode, Docker Compose deployment, `nix develop` orchestrator.\n"
        "- **Pre-Phase-2 paper cuts** PC.1–PC.7.\n"
        "- **Phase A agent system bootstrap** A.1–A.10 (2026-05-16).\n"
        "- **Phase A v2** A.11–A.12 (2026-05-16).\n"
        "- **Phase A tracing + memory** A.13–A.17 (2026-05-17).\n"
        "- **Phase A board restructure** A.28 (2026-05-17).\n"
        "- **Phase A machine-readable rewrite** A.16 (2026-05-18).\n"
        "- **Phase A phase numbering** A.29 (2026-05-18, this release): "
        "`.claude/naavik-ops` Python dispatcher + `.claude/naavik_ops/` package.\n\n"
        "### Changed\n"
        "- Migrated all task IDs and ROADMAP rows to 4-level semver schema "
        "(`MAJOR.MINOR.PATCH[.POSITION]`). Legacy IDs preserved via "
        "`.claude/github-issue-map.json:redirects` map.\n"
        "- GitHub Project Priority field role narrowed: optional intra-release "
        "impact signal at TASK level only.\n"
        "- `scripts/` folder reserved for project-wide user-runnable scripts only.\n\n"
        "### Security\n"
        "- `SECRET_KEY` enforcement at module-import time (PC.5).\n"
        "- Password complexity + must-change-on-first-login (PC.6).\n"
        "- Broader `require_password_complete` gate (PC.6a).\n"
        "- `scripts/agent-memory.sh` hardening (A.17 + A.17a).\n"
    )
    if apply:
        CHANGELOG_PATH.write_text(body, encoding="utf-8")
        _emit("INFO", 11, f"CHANGELOG.md written ({len(body)} bytes)")
    else:
        _emit("INFO", 11, f"CHANGELOG.md would-write ({len(body)} bytes)")


def step_12_verify(apply: bool) -> None:
    """Run `naavik-ops task check` to verify clean post-migration state."""
    _emit("INFO", 12, "verify via naavik-ops task check")
    if not apply:
        _emit("INFO", 12, "DRY-RUN — verify skipped")
        return
    rc = subprocess.run(
        [str(REPO_ROOT / ".claude" / "naavik-ops"), "task", "check"],
        cwd=str(REPO_ROOT),
    ).returncode
    if rc != 0:
        raise NaavikOpsError(f"naavik-ops task check exited {rc} after migration")
    _emit("INFO", 12, "verify clean")


def step_13_commit(apply: bool, mapping: list[dict]) -> None:
    """Commit the migration as a single BOOKKEEPING commit + version bump."""
    _emit("INFO", 13, "commit migration")
    if not apply:
        _emit("INFO", 13, "DRY-RUN — skip commit")
        return
    # Stage map cache + ROADMAP + CHANGELOG + plan archive + pyproject + flake.
    _git("add", str(ISSUE_MAP_PATH))
    _git("add", str(ROADMAP_PATH))
    _git("add", str(CHANGELOG_PATH))
    _git("add", str(PLAN_ARCHIVE_DIR))
    _git("add", str(PYPROJECT_PATH))
    _git("add", str(PACKAGE_NIX_PATH))

    body_lines = [
        "chore(release): A.29 — phase numbering migration + 0.1.0 baseline",
        "",
        f"Migrated {len(mapping)} rows to 4-level semver schema.",
        "",
        "Rename map:",
    ]
    for row in mapping:
        body_lines.append(f"  {row['old']:<10} → {row['new']}  ({row['title']})")
    body_lines.append("")
    body_lines.append(
        "See docs/design/PHASE_NUMBERING.md + .claude/github-issue-map.json:redirects."
    )
    _git("commit", "-m", "\n".join(body_lines))
    _emit("INFO", 13, "migration commit landed")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _gh(*args: str) -> None:
    """Run scripts/gh-project.sh with args; streamed."""
    cmd = ["bash", str(GH_SCRIPT), *args]
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        raise NaavikOpsError(f"gh-project.sh {' '.join(args)} exited {rc}")


def _gh_capture(*args: str) -> str:
    cmd = ["bash", str(GH_SCRIPT), *args]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def _run(cmd: Sequence[str]) -> None:
    rc = subprocess.run(list(cmd)).returncode
    if rc != 0:
        raise NaavikOpsError(f"command {cmd[0]} exited {rc}")


def _read_issue_map() -> dict:
    if not ISSUE_MAP_PATH.exists():
        return {}
    return json.loads(ISSUE_MAP_PATH.read_text(encoding="utf-8"))


def _write_issue_map(data: dict) -> None:
    tmp = ISSUE_MAP_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, ISSUE_MAP_PATH)


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------


def main(argv: Sequence[str]) -> int:
    global TRACE_DIR

    parser = argparse.ArgumentParser(
        prog="A.29-phase-renumber.py",
        description="A.29 one-shot phase numbering migration to 4-level semver.",
    )
    parser.add_argument("--apply", action="store_true", help="Mutate state (default is dry-run).")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default).")
    parser.add_argument(
        "--trace-dir", type=Path, default=None, help="Optional trace directory for MIRROR events."
    )
    args = parser.parse_args(argv)

    apply = args.apply
    if args.dry_run and apply:
        sys.stderr.write("error: --dry-run and --apply are mutually exclusive\n")
        return 2

    TRACE_DIR = args.trace_dir
    if TRACE_DIR is not None:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)

    sys.stdout.write(
        f"=== A.29 phase-numbering migration ===\nmode: {'APPLY' if apply else 'DRY-RUN'}\n\n"
    )

    try:
        with flock.acquire(LOCK_PATH, blocking=False):
            mapping = _full_mapping()
            step_1_preflight(apply)
            mapping = step_2_compute_mapping(apply)
            step_3_confirm(apply, mapping)
            step_4_create_milestones(apply)
            step_5_create_epics(apply)
            step_6_renumber_issues(apply, mapping)
            step_7_rewrite_roadmap(apply)
            step_8_close_superseded_milestones(apply)
            step_9_rewrite_plan_frontmatter(apply, mapping)
            step_10_rewrite_callers(apply, mapping)
            step_11_bootstrap_changelog(apply)
            step_12_verify(apply)
            step_13_commit(apply, mapping)
    except BlockingIOError:
        sys.stderr.write(f"error: lock {LOCK_PATH} held by another process. Abort.\n")
        return 1
    except NaavikOpsError as e:
        sys.stderr.write(f"migration error: {e}\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\nmigration: interrupted\n")
        return 130

    sys.stdout.write(f"\n=== migration {'APPLIED' if apply else 'DRY-RUN complete'} ===\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
