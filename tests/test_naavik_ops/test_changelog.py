"""Tests for naavik_ops.lib.changelog — keepachangelog + Conventional Commits."""

from __future__ import annotations

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
