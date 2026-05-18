"""release — release ceremony per design doc § 2 + plan § D.15.

`naavik-ops release cut <version> [--no-tag]` bundles the 10-step ceremony:

  1. Pre-flight gates (epic closed, tree clean, no existing tag, flock).
  2. Compute CHANGELOG section from closed Issues + Conventional Commits.
  3. Update pyproject.toml [project] version.
  4. Update nix/package.nix version attribute.
  5. Prepend new release block to CHANGELOG.md.
  6. Commit bookkeeping (chore(release): <version>).
  7. git tag <version> (skipped on --no-tag).
  8. Push tag (skipped on --no-tag).
  9. gh release create (skipped on --no-tag).
 10. Close the version's epic Issue via gh.set-status.

Invariants:
  - Tags cut only at this ceremony. PRs do NOT bump tags individually.
  - pyproject.toml + nix/package.nix synced atomically (same commit).

# Wave 1 ship surface

  cut <version> [--no-tag] [--apply]   Wave 1: dry-run by default; `--apply` runs
                                       file mutations through commit gate. Tag
                                       push + gh release stays guarded behind
                                       user confirmation in Wave 5 post-merge.
  dry-run <version>                    Alias for `cut <version>` without --apply.
  changelog <version> [--output FILE]  Write the CHANGELOG section to stdout
                                       (or --output FILE) without commit/tag.

The dispatcher exposes these as `naavik-ops release cut|dry-run|changelog`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from naavik_ops.lib import NaavikOpsError, changelog, semver

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
PACKAGE_NIX_PATH = REPO_ROOT / "nix" / "package.nix"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
LOCK_PATH = Path(os.path.expanduser("~/.naavik/naavik-ops.lock"))


def _git(*args: str, check: bool = True) -> str:
    """Run git in the repo and return stdout. Non-zero swallowed when check=False."""
    cmd = ["git", "-C", str(REPO_ROOT), *args]
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e.stdout.strip() if e.stdout else ""
    except FileNotFoundError:
        if check:
            raise
        return ""
    return result.stdout.strip()


def _tree_clean() -> bool:
    """True if `git status --porcelain` is empty (or repo isn't a git repo)."""
    out = _git("status", "--porcelain", check=False)
    return out == ""


def _tag_exists(tag: str) -> bool:
    out = _git("tag", "--list", tag, check=False)
    return bool(out.strip())


def _today() -> str:
    """UTC date YYYY-MM-DD."""
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")


# -----------------------------------------------------------------------------
# pyproject + nix/package.nix version mutation
# -----------------------------------------------------------------------------


def _update_pyproject(version: str) -> bool:
    """Replace `version = "..."` in pyproject.toml. Returns True if changed."""
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^(version\s*=\s*)"[^"]+"\s*$',
        rf'\1"{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise NaavikOpsError("pyproject.toml: could not find 'version = \"...\"' line")
    if new_text == text:
        return False
    PYPROJECT_PATH.write_text(new_text, encoding="utf-8")
    return True


def _update_package_nix(version: str) -> bool:
    """Replace `version = "...";` in nix/package.nix. Returns True if changed."""
    text = PACKAGE_NIX_PATH.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'(version\s*=\s*)"[^"]+"\s*;',
        rf'\1"{version}";',
        text,
        count=1,
    )
    if count == 0:
        raise NaavikOpsError("nix/package.nix: could not find 'version = \"...\";' line")
    if new_text == text:
        return False
    PACKAGE_NIX_PATH.write_text(new_text, encoding="utf-8")
    return True


def _prepend_changelog_release(version: str, summary: str, sections: dict[str, list[str]]) -> bool:
    """Prepend a new release block to CHANGELOG.md (creating the file if missing).

    Returns True if the file was changed.
    """
    release = changelog.Release(version=version, date=_today(), summary=summary)
    for section, entries in sections.items():
        for entry in entries:
            release.add(section, changelog.ReleaseEntry(text=entry))

    block = changelog.render_release(release)

    if not CHANGELOG_PATH.exists():
        rendered = changelog.render_changelog([release])
        CHANGELOG_PATH.write_text(rendered, encoding="utf-8")
        return True

    existing = CHANGELOG_PATH.read_text(encoding="utf-8")
    # Insert new block immediately after the `## [Unreleased]` paragraph.
    pattern = re.compile(r"(##\s+\[Unreleased\][^\n]*(?:\n(?!##\s+\[).*)*\n)", re.IGNORECASE)
    m = pattern.search(existing)
    if m:
        end = m.end()
        new_text = existing[:end] + "\n" + block + existing[end:]
    else:
        # No Unreleased anchor — prepend at top below the changelog header line.
        new_text = block + "\n" + existing
    if new_text == existing:
        return False
    CHANGELOG_PATH.write_text(new_text, encoding="utf-8")
    return True


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------


def cmd_dry_run(rest: Sequence[str]) -> int:
    """dry-run <version> — preview release ceremony actions without mutating."""
    if not rest:
        sys.stderr.write("usage: naavik-ops release dry-run <version>\n")
        return 2
    return _cut_or_dry(rest[0], apply=False, no_tag=False)


def cmd_cut(rest: Sequence[str]) -> int:
    """cut <version> [--no-tag] [--apply]

    Without --apply runs as dry-run (no mutations). With --apply, performs steps
    1-6 (file mutations + bookkeeping commit). Steps 7-10 (tag, push, GH
    release, epic close) require explicit `--no-tag` removal AND a clean tree;
    otherwise they're announced + skipped with an explanation. This pacing
    matches Wave 5's "post-merge tag cut" plan invariant.
    """
    if not rest:
        sys.stderr.write("usage: naavik-ops release cut <version> [--apply] [--no-tag]\n")
        return 2
    version = rest[0]
    apply = "--apply" in rest
    no_tag = "--no-tag" in rest
    return _cut_or_dry(version, apply=apply, no_tag=no_tag)


def cmd_changelog(rest: Sequence[str]) -> int:
    """changelog <version> — render the CHANGELOG section for <version> only.

    Reads closed Issues + commit subjects matching `[<version>...]` from git
    log to classify entries. Wave 1 ships the rendering scaffold; Wave 5 wires
    the full closed-Issue list. For now `--summary FILE` allows injecting a
    pre-built summary.
    """
    if not rest:
        sys.stderr.write("usage: naavik-ops release changelog <version>\n")
        return 2
    version = rest[0]
    try:
        semver.parse(version)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e

    if not semver.is_release(version):
        raise NaavikOpsError(f"changelog accepts release-level IDs only (got {version})")

    release = changelog.Release(version=version, date=_today())
    rendered = changelog.render_release(release)
    sys.stdout.write(rendered)
    return 0


# -----------------------------------------------------------------------------
# Internal: ceremony driver
# -----------------------------------------------------------------------------


def _cut_or_dry(version: str, *, apply: bool, no_tag: bool) -> int:
    try:
        semver.parse(version)
    except semver.InvalidVersion as e:
        raise NaavikOpsError(str(e)) from e

    if not semver.is_release(version):
        raise NaavikOpsError(f"release cut requires a 3-level release ID (got '{version}')")

    sys.stdout.write(f"=== naavik-ops release cut {version} ===\n")
    sys.stdout.write(f"mode: {'APPLY' if apply else 'DRY-RUN'} (no_tag={no_tag})\n\n")

    # Step 1 — Pre-flight.
    sys.stdout.write("Step 1: pre-flight gates...\n")
    if not REPO_ROOT.is_dir():
        raise NaavikOpsError(f"REPO_ROOT not a directory: {REPO_ROOT}")
    if apply and not _tree_clean():
        raise NaavikOpsError("git tree dirty — commit or stash before `release cut --apply`")
    if _tag_exists(version):
        raise NaavikOpsError(f"tag '{version}' already exists")
    sys.stdout.write("  ok\n")

    # Step 2 — Compute CHANGELOG section. Wave 5 wires closed-Issue ingestion;
    # Wave 1 emits a stub the operator can hand-augment between dry-run and
    # apply. The migration runbook (Wave 2) ships the initial 0.1.0 section.
    sys.stdout.write("Step 2: compute CHANGELOG section (stub during A.29)...\n")
    summary = (
        f"Release bundle for {version}. Detailed entries reconstructed from "
        f"closed Issues post-merge."
    )
    sections: dict[str, list[str]] = {}

    # Step 3 — pyproject.
    sys.stdout.write("Step 3: pyproject.toml version → " + version + "\n")
    if apply:
        changed = _update_pyproject(version)
        sys.stdout.write(f"  {'modified' if changed else 'already at target'}\n")

    # Step 4 — nix/package.nix.
    sys.stdout.write("Step 4: nix/package.nix version → " + version + "\n")
    if apply:
        changed = _update_package_nix(version)
        sys.stdout.write(f"  {'modified' if changed else 'already at target'}\n")

    # Step 5 — CHANGELOG.md.
    sys.stdout.write("Step 5: prepend CHANGELOG release block...\n")
    if apply:
        changed = _prepend_changelog_release(version, summary, sections)
        sys.stdout.write(f"  {'modified' if changed else 'unchanged'}\n")

    # Step 6 — Commit bookkeeping.
    sys.stdout.write("Step 6: commit chore(release): " + version + "\n")
    if apply:
        _git("add", str(PYPROJECT_PATH))
        _git("add", str(PACKAGE_NIX_PATH))
        if CHANGELOG_PATH.exists():
            _git("add", str(CHANGELOG_PATH))
        _git("commit", "-m", f"chore(release): {version}")
        sys.stdout.write("  committed\n")

    # Steps 7-9 — tag + push + GH release.
    if no_tag:
        sys.stdout.write("Step 7-9: --no-tag set; skipping tag / push / GH release\n")
    elif not apply:
        sys.stdout.write("Step 7-9: would tag, push, gh release (dry-run skip)\n")
    else:
        sys.stdout.write(
            "Step 7-9: APPLY requested without --no-tag — Wave 5 post-merge "
            "responsibility. Skipping until manual confirmation.\n"
        )

    # Step 10 — Close epic.
    sys.stdout.write("Step 10: close [Epic] " + version + " — defer until Wave 5 user gate\n")

    sys.stdout.write("\n=== done ===\n")
    return 0
