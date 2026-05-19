"""Tests for naavik_ops.lib.changelog — keepachangelog + Conventional Commits."""

from __future__ import annotations

import pytest
from naavik_ops.lib import changelog


class TestClassifyCommit:
    def test_feat_to_added(self):
        assert changelog.classify_commit("feat: new thing") == "Added"
        assert changelog.classify_commit("feat(scrapers): linkedin adapter") == "Added"

    def test_fix_to_fixed(self):
        assert changelog.classify_commit("fix: bug") == "Fixed"
        assert changelog.classify_commit("fix(auth): csrf token") == "Fixed"

    def test_chore_security_to_security(self):
        assert changelog.classify_commit("chore(security): rotate keys") == "Security"

    def test_feat_security_to_security(self):
        assert changelog.classify_commit("feat(security): jwt denylist") == "Security"

    def test_deprecate_to_deprecated(self):
        assert changelog.classify_commit("deprecate: legacy api") == "Deprecated"

    def test_remove_to_removed(self):
        assert changelog.classify_commit("remove: dead code") == "Removed"

    def test_chore_dropped(self):
        assert changelog.classify_commit("chore: bump deps") is None

    def test_docs_dropped(self):
        assert changelog.classify_commit("docs: update readme") is None

    def test_refactor_dropped(self):
        assert changelog.classify_commit("refactor: rename module") is None

    def test_breaking_change_marker(self):
        assert (
            changelog.classify_commit("feat!: drop py3.11", "BREAKING CHANGE: drop py") == "Changed"
        )

    def test_breaking_change_body(self):
        assert (
            changelog.classify_commit(
                "feat(api): rewrite endpoint",
                "Some body\n\nBREAKING CHANGE: response shape changed",
            )
            == "Changed"
        )

    def test_invalid_subject(self):
        assert changelog.classify_commit("not conventional") is None
        assert changelog.classify_commit("") is None


class TestRender:
    def test_render_release_with_sections(self):
        release = changelog.Release(version="0.1.0", date="2026-05-18", summary="bundle")
        release.add("Added", changelog.ReleaseEntry(text="thing one"))
        release.add("Added", changelog.ReleaseEntry(text="thing two"))
        release.add("Fixed", changelog.ReleaseEntry(text="bug"))
        out = changelog.render_release(release)
        assert "## [0.1.0] - 2026-05-18" in out
        assert "### Added" in out
        assert "- thing one" in out
        assert "- thing two" in out
        assert "### Fixed" in out
        assert "bundle" in out

    def test_render_release_section_order_canonical(self):
        release = changelog.Release(version="0.2.0", date="2026-06-01")
        release.add("Fixed", changelog.ReleaseEntry(text="bug"))
        release.add("Added", changelog.ReleaseEntry(text="feature"))
        out = changelog.render_release(release)
        # Added must precede Fixed regardless of insertion order.
        assert out.index("### Added") < out.index("### Fixed")


class TestParseRoundtrip:
    def test_parse_then_render(self):
        release = changelog.Release(version="0.1.0", date="2026-05-18", summary="first cut")
        release.add("Added", changelog.ReleaseEntry(text="phase 1"))
        release.add("Security", changelog.ReleaseEntry(text="secret key"))
        rendered = changelog.render_changelog([release], unreleased_summary="wip")

        parsed = changelog.parse_changelog(rendered)
        assert len(parsed) == 1
        assert parsed[0].version == "0.1.0"
        assert parsed[0].date == "2026-05-18"
        assert "first cut" in parsed[0].summary
        added = [e.text for e in parsed[0].sections.get("Added") or []]
        assert "phase 1" in added
        security = [e.text for e in parsed[0].sections.get("Security") or []]
        assert "secret key" in security


class TestSanitize:
    """Per plan 25 D.5 / Issue #74 — CHANGELOG markdown-escape hardening."""

    def test_leading_hash_escaped(self):
        # Header smuggling: `#evil heading` injection.
        entry = changelog.ReleaseEntry(text="#evil header")
        assert entry.text.startswith("\\#")

    def test_link_syntax_escaped(self):
        entry = changelog.ReleaseEntry(text="[click](http://evil.example)")
        # Brackets + parens + dot escaped per CommonMark spec § 2.4.
        assert "\\[click\\]" in entry.text
        assert "\\(http://evil\\.example\\)" in entry.text

    def test_embedded_newline_collapsed(self):
        entry = changelog.ReleaseEntry(text="line 1\nline 2\n  line 3")
        # All whitespace runs collapse to single space, trimmed.
        assert "\n" not in entry.text
        assert entry.text == "line 1 line 2 line 3"

    def test_cr_rejected(self):
        with pytest.raises(ValueError, match="CR"):
            changelog.ReleaseEntry(text="windows\r\nline")

    def test_emphasis_chars_escaped(self):
        # CommonMark spec emphasis: *bold* / _underline_.
        entry = changelog.ReleaseEntry(text="*bold* _under_")
        assert entry.text == "\\*bold\\* \\_under\\_"

    def test_from_rendered_skips_sanitization(self):
        # Round-trip: rendered already-escaped text must not be re-escaped.
        entry = changelog.ReleaseEntry.from_rendered("\\#already escaped")
        assert entry.text == "\\#already escaped"

    def test_0_1_0_existing_block_unchanged(self):
        # Per plan 25 R14: existing CHANGELOG.md blocks (pre-A.31, hand-curated)
        # round-trip through parse_changelog without double-escape on re-render.
        original = (
            "# Changelog\n"
            "\n"
            "## [Unreleased]\n"
            "\n"
            "## [0.1.0] - 2026-05-18\n"
            "\n"
            "### Added\n"
            "- Phase numbering system\n"
            "- `naavik-ops` dispatcher\n"
        )
        releases = changelog.parse_changelog(original)
        assert len(releases) == 1
        # Re-render without mutation.
        rendered = changelog.render_release(releases[0])
        # Backticks should NOT be double-escaped after parse/render cycle.
        assert "`naavik-ops`" in rendered
        assert "\\`naavik-ops\\`" not in rendered
