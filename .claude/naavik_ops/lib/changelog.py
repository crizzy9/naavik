"""changelog — keepachangelog v1.1.0 reader / writer + Conventional Commits.

Per design doc § 3.

Sections per release:
  Added / Changed / Deprecated / Removed / Fixed / Security

Conventional Commits → section classification:

  feat: / feat(scope):                                 → Added
  feat!: / feat(scope)!: / body has BREAKING CHANGE:   → Changed
  fix: / fix(scope):                                   → Fixed
  chore(security): / feat(security):                   → Security
  deprecate: / body has DEPRECATED:                    → Deprecated
  remove: / body has REMOVED:                          → Removed
  chore: / docs: / refactor: / test: / perf: / build:
  ci: / style:                                         → NOT in CHANGELOG
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTIONS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

#: Conventional Commits subject regex (type[(scope)][!]: subject).
COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|chore|docs|refactor|test|perf|build|ci|style|deprecate|remove)"
    r"(?:\((?P<scope>[a-z0-9-]+)\))?"
    r"(?P<breaking>!)?"
    r":\s+(?P<subject>.+)$"
)

#: Subjects with these types are dropped from the CHANGELOG (internal noise).
INTERNAL_TYPES = {"chore", "docs", "refactor", "test", "perf", "build", "ci", "style"}


@dataclass
class ReleaseEntry:
    """One entry within a CHANGELOG section."""

    text: str
    commit_sha: str | None = None


@dataclass
class Release:
    """A single CHANGELOG release block."""

    version: str
    date: str  # YYYY-MM-DD
    summary: str = ""
    sections: dict[str, list[ReleaseEntry]] = field(default_factory=dict)

    def add(self, section: str, entry: ReleaseEntry) -> None:
        if section not in SECTIONS:
            raise ValueError(f"unknown CHANGELOG section: {section}")
        self.sections.setdefault(section, []).append(entry)


def classify_commit(subject: str, body: str = "") -> str | None:
    """Map a Conventional Commit subject + body to a CHANGELOG section.

    Returns None if the commit should NOT appear in the CHANGELOG (internal
    noise like chore: docs: refactor: etc., subject to scope override for
    chore(security)).

    `subject` is the first line (no trailing newline). `body` is the rest.
    """
    m = COMMIT_RE.match(subject.strip())
    if m is None:
        return None
    ctype = m.group("type")
    scope = m.group("scope") or ""
    breaking = m.group("breaking") == "!"

    body_upper = body.upper()
    if ("BREAKING CHANGE:" in body_upper or breaking) and ctype == "feat":
        return "Changed"

    # chore(security) / feat(security) → Security override.
    if scope == "security":
        return "Security"

    if ctype == "feat":
        return "Added"
    if ctype == "fix":
        return "Fixed"
    if ctype == "deprecate" or "DEPRECATED:" in body_upper:
        return "Deprecated"
    if ctype == "remove" or "REMOVED:" in body_upper:
        return "Removed"
    if ctype in INTERNAL_TYPES:
        return None
    return None


def render_release(release: Release) -> str:
    """Render one Release as a CHANGELOG markdown block."""
    lines = [f"## [{release.version}] - {release.date}"]
    if release.summary:
        lines.append("")
        lines.append(release.summary.rstrip())
    for section in SECTIONS:
        entries = release.sections.get(section) or []
        if not entries:
            continue
        lines.append("")
        lines.append(f"### {section}")
        for entry in entries:
            lines.append(f"- {entry.text}")
    return "\n".join(lines) + "\n"


def render_changelog(releases: list[Release], unreleased_summary: str = "") -> str:
    """Render the full CHANGELOG markdown document."""
    lines = ["# Changelog", ""]
    lines.append(
        "All notable changes to Naavik are documented here. Format is based on "
        "[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this "
        "project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)."
    )
    lines.append("")
    lines.append("## [Unreleased]")
    if unreleased_summary:
        lines.append("")
        lines.append(unreleased_summary.rstrip())
    lines.append("")
    for release in releases:
        lines.append(render_release(release))
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Reader — parse an existing CHANGELOG.md back into Release records.
# -----------------------------------------------------------------------------

_RELEASE_HEADER_RE = re.compile(
    r"^##\s+\[(?P<version>[^\]]+)\]\s+-\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
_SECTION_HEADER_RE = re.compile(r"^###\s+(?P<section>[A-Za-z]+)\s*$")
_BULLET_RE = re.compile(r"^-\s+(?P<text>.+)$")


def parse_changelog(text: str) -> list[Release]:
    """Parse a CHANGELOG.md text into a list of Release records.

    Ignores the Unreleased block. Returns releases in document order
    (typically newest first).
    """
    releases: list[Release] = []
    current: Release | None = None
    current_section: str | None = None
    summary_lines: list[str] = []
    in_summary = False

    for raw in text.splitlines():
        line = raw.rstrip("\n")

        m_release = _RELEASE_HEADER_RE.match(line)
        if m_release:
            if current is not None:
                if summary_lines:
                    current.summary = "\n".join(summary_lines).rstrip()
                releases.append(current)
            version = m_release.group("version")
            date = m_release.group("date")
            if version.lower() == "unreleased":
                current = None
                current_section = None
                summary_lines = []
                in_summary = False
                continue
            current = Release(version=version, date=date)
            current_section = None
            summary_lines = []
            in_summary = True
            continue

        if current is None:
            continue

        m_section = _SECTION_HEADER_RE.match(line)
        if m_section:
            if in_summary and summary_lines:
                current.summary = "\n".join(summary_lines).rstrip()
                summary_lines = []
            in_summary = False
            current_section = m_section.group("section")
            continue

        if current_section is not None:
            m_bullet = _BULLET_RE.match(line)
            if m_bullet:
                current.add(current_section, ReleaseEntry(text=m_bullet.group("text")))
                continue

        if in_summary:
            summary_lines.append(line)

    if current is not None:
        if summary_lines:
            current.summary = "\n".join(summary_lines).rstrip()
        releases.append(current)

    return releases
