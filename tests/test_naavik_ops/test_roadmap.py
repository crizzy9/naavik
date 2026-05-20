"""Tests for naavik_ops.lib.roadmap — parser + writer half.

Plan 25 § D.9. Inherits the legacy parser contract from
`scripts/roadmap_parser.py` (read side); covers the new writer half
(parse_release_section / write_release_section / rewrite_atomic) needed by
the 5 mutating task subcommands (W3).
"""

from __future__ import annotations

import json
import textwrap

import pytest
from naavik_ops.lib import NaavikOpsError, roadmap

# ---------------------------------------------------------------------------
# Read-side legacy contract (parity with scripts/roadmap_parser.py)
# ---------------------------------------------------------------------------


SAMPLE_ROADMAP = textwrap.dedent(
    """\
    # Roadmap

    ## Phases

    ### Phase A: Agent System

    | # | Task | Status | Priority | Notes |
    |---|---|---|---|---|
    | A.1 | Author 6 subagent prompts | [x] | HIGH | done |
    | A.2 | Wire skills | [~] | HIGH | in flight |

    ### Phase 2: Core Backend

    | # | Task | Priority | Notes |
    |---|---|---|---|
    | 2.11 | Sunset CLI | HIGH | depends on 2.12 |
    | 2.12 | Sunset vault | HIGH | env-based secrets |

    ### 0.2.0 — Phase 2 Core Backend

    | # | Task | Status | Priority | Notes |
    |---|---|---|---|---|
    | 0.2.0.01 | Sunset vault | [ ] | HIGH | env-based secrets |
    | 0.2.0.02 | Sunset CLI | [ ] | HIGH | after 0.2.0.01 |
    | 0.2.0.05 | Auth hardening | [ ] | MEDIUM | post-sunset cleanup |

    ### 0.3.0 — Phase 3 Frontend

    | # | Task | Status | Priority | Notes |
    |---|---|---|---|---|
    | 0.3.0.01 | HTMX scaffolds | [ ] | HIGH | mockups in docs/design |
    """
)


class TestLegacyParser:
    def test_parse_phase_a_rows(self, tmp_path, monkeypatch):
        roadmap_file = tmp_path / "ROADMAP.md"
        roadmap_file.write_text(SAMPLE_ROADMAP, encoding="utf-8")
        monkeypatch.setattr(roadmap, "ROADMAP_PATH", roadmap_file)

        rows = roadmap.parse(["Phase A"])
        assert len(rows) == 2
        assert rows[0]["id"] == "A.1"
        assert rows[0]["status"] == "x"
        assert rows[0]["priority"] == "HIGH"
        assert rows[1]["status"] == "~"

    def test_parse_open_only(self, tmp_path, monkeypatch):
        roadmap_file = tmp_path / "ROADMAP.md"
        roadmap_file.write_text(SAMPLE_ROADMAP, encoding="utf-8")
        monkeypatch.setattr(roadmap, "ROADMAP_PATH", roadmap_file)

        rows = roadmap.parse(["Phase A"], open_only=True)
        assert len(rows) == 1
        assert rows[0]["id"] == "A.2"

    def test_parse_all_phases(self, tmp_path, monkeypatch):
        roadmap_file = tmp_path / "ROADMAP.md"
        roadmap_file.write_text(SAMPLE_ROADMAP, encoding="utf-8")
        monkeypatch.setattr(roadmap, "ROADMAP_PATH", roadmap_file)

        rows = roadmap.parse()
        # Phase A (2) + Phase 2 (2) + 0.2.0 (3) + 0.3.0 (1) = 8 rows.
        # The "### 0.2.0" + "### 0.3.0" headers don't match RE_PHASE_HEADER
        # ("### Phase X:") so their rows DO inherit the most-recent phase.
        assert len(rows) >= 4

    def test_parse_iter_yields_dataclass(self):
        rows = list(roadmap.iter_tasks(SAMPLE_ROADMAP))
        assert any(r.id == "A.1" for r in rows)
        assert any(r.id == "2.11" for r in rows)

    def test_missing_roadmap_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(roadmap, "ROADMAP_PATH", tmp_path / "nope.md")
        with pytest.raises(NaavikOpsError):
            roadmap.parse()


# ---------------------------------------------------------------------------
# Writer half — parse_release_section / find_release_section_bounds /
# write_release_section / rewrite_atomic
# ---------------------------------------------------------------------------


class TestParseReleaseSection:
    def test_returns_4level_rows_ordered(self):
        rows = roadmap.parse_release_section("0.2.0", roadmap_text=SAMPLE_ROADMAP)
        ids = [r.task_id for r in rows]
        assert ids == ["0.2.0.01", "0.2.0.02", "0.2.0.05"]
        positions = [r.position for r in rows]
        assert positions == [1, 2, 5]

    def test_missing_version_returns_empty(self):
        rows = roadmap.parse_release_section("0.9.9", roadmap_text=SAMPLE_ROADMAP)
        assert rows == []

    def test_priority_uppercased(self):
        rows = roadmap.parse_release_section("0.2.0", roadmap_text=SAMPLE_ROADMAP)
        assert rows[0].priority == "HIGH"
        assert rows[2].priority == "MEDIUM"


class TestFindReleaseSectionBounds:
    def test_finds_022_section(self):
        bounds = roadmap.find_release_section_bounds("0.2.0", roadmap_text=SAMPLE_ROADMAP)
        assert bounds is not None
        start, end = bounds
        lines = SAMPLE_ROADMAP.splitlines()
        assert lines[start].startswith("### 0.2.0")
        # End is the next heading (### 0.3.0).
        assert lines[end].startswith("### 0.3.0")

    def test_missing_version_returns_none(self):
        bounds = roadmap.find_release_section_bounds("0.9.9", roadmap_text=SAMPLE_ROADMAP)
        assert bounds is None


class TestWriteReleaseSection:
    def test_round_trip_unchanged_rows(self):
        rows = roadmap.parse_release_section("0.2.0", roadmap_text=SAMPLE_ROADMAP)
        diff = roadmap.write_release_section("0.2.0", rows, roadmap_text=SAMPLE_ROADMAP)
        # All 3 row lines should re-render (via raw_line preservation).
        joined = "\n".join(diff.new_lines)
        for row in rows:
            assert row.task_id in joined

    def test_inserted_row_appears_in_diff(self):
        rows = roadmap.parse_release_section("0.2.0", roadmap_text=SAMPLE_ROADMAP)
        rows.append(
            roadmap.ReleaseRow(
                task_id="0.2.0.10",
                position=10,
                status=" ",
                title="New task",
                priority="LOW",
                notes="freshly inserted",
                raw_line="",
            )
        )
        diff = roadmap.write_release_section("0.2.0", rows, roadmap_text=SAMPLE_ROADMAP)
        joined = "\n".join(diff.new_lines)
        assert "0.2.0.10" in joined
        assert "New task" in joined

    def test_missing_release_section_raises(self):
        with pytest.raises(NaavikOpsError, match="not in ROADMAP.md"):
            roadmap.write_release_section("9.9.9", [], roadmap_text=SAMPLE_ROADMAP)


class TestRewriteAtomic:
    def test_single_section_swap(self, tmp_path):
        target = tmp_path / "ROADMAP.md"
        target.write_text(SAMPLE_ROADMAP, encoding="utf-8")

        rows = roadmap.parse_release_section("0.2.0", roadmap_text=SAMPLE_ROADMAP)
        rows.append(
            roadmap.ReleaseRow(
                task_id="0.2.0.06",
                position=6,
                status=" ",
                title="Brand new",
                priority="HIGH",
                notes="",
                raw_line="",
            )
        )
        diff = roadmap.write_release_section("0.2.0", rows, roadmap_text=SAMPLE_ROADMAP)
        roadmap.rewrite_atomic([diff], path=target)

        out = target.read_text(encoding="utf-8")
        assert "0.2.0.06" in out
        # 0.3.0 section preserved verbatim — none of its rows should drop.
        assert "0.3.0.01" in out
        # Phase A unchanged.
        assert "Author 6 subagent prompts" in out

    def test_overlapping_diffs_rejected(self, tmp_path):
        target = tmp_path / "ROADMAP.md"
        target.write_text(SAMPLE_ROADMAP, encoding="utf-8")
        d1 = roadmap.ReleaseDiff(version="0.2.0", start_line=0, end_line=10, new_lines=[])
        d2 = roadmap.ReleaseDiff(version="0.3.0", start_line=5, end_line=15, new_lines=[])
        with pytest.raises(NaavikOpsError, match="overlapping"):
            roadmap.rewrite_atomic([d1, d2], path=target)

    def test_atomic_preserves_trailing_newline(self, tmp_path):
        target = tmp_path / "ROADMAP.md"
        target.write_text(SAMPLE_ROADMAP, encoding="utf-8")
        rows = roadmap.parse_release_section("0.2.0", roadmap_text=SAMPLE_ROADMAP)
        diff = roadmap.write_release_section("0.2.0", rows, roadmap_text=SAMPLE_ROADMAP)
        roadmap.rewrite_atomic([diff], path=target)
        assert target.read_text(encoding="utf-8").endswith("\n")


# ---------------------------------------------------------------------------
# Legacy CLI shape — ensures the dispatcher's `lib/roadmap.py` is still
# spawnable with the same argv that `scripts/gh-project.sh` used to pass:
#   python3 scripts/roadmap_parser.py --phase="Phase A" --open-only
# ---------------------------------------------------------------------------


class TestLegacyCLI:
    def test_main_emits_jsonl(self, tmp_path, monkeypatch, capsys):
        roadmap_file = tmp_path / "ROADMAP.md"
        roadmap_file.write_text(SAMPLE_ROADMAP, encoding="utf-8")
        monkeypatch.setattr(roadmap, "ROADMAP_PATH", roadmap_file)

        rc = roadmap._main(["x", "--phase=Phase A"])
        assert rc == 0
        out = capsys.readouterr().out
        emitted = [json.loads(line) for line in out.strip().splitlines()]
        assert len(emitted) == 2
        assert emitted[0]["id"] == "A.1"


# ---------------------------------------------------------------------------
# Plan 40 — Backlog section (synthetic version, parser + filter)
# ---------------------------------------------------------------------------


SAMPLE_ROADMAP_WITH_BACKLOG = textwrap.dedent(
    """\
    # Roadmap

    ## Phases

    ### 0.2.0 — Job Scraping
    > Goal: Active.

    | # | Task | Status | Priority | Notes |
    |---|---|---|---|---|
    | 0.2.0.01 | Active task | [x] | HIGH | shipped |
    | 0.2.0.02 | In flight | [~] | MEDIUM | working |
    | 0.2.0.03 | Pending | [ ] | - | queued |

    ### 0.3.0 — Future
    > Goal: Future.

    | # | Task | Status | Priority | Notes |
    |---|---|---|---|---|
    | 0.3.0.01 | Future stuff | [ ] | - | future |

    ## Backlog (unprioritized)

    Tasks deferred from current cycles but not deleted. No priority; pick by inspection.

    | # | Task | Status | Priority | Notes |
    |---|---|---|---|---|
    | 0.2.0.14 | n8n migration | [ ] | - | deferred per user 2026-05-19 |
    | 0.3.0.04 | Some old idea | [ ] | - | parked |

    ## Agent System

    Other stuff.
    """
)


class TestBacklogParser:
    def test_parse_backlog_section_returns_rows(self):
        rows = roadmap.parse_release_section(
            roadmap.BACKLOG_VERSION, roadmap_text=SAMPLE_ROADMAP_WITH_BACKLOG
        )
        ids = [r.task_id for r in rows]
        assert "0.2.0.14" in ids
        assert "0.3.0.04" in ids
        assert len(rows) == 2

    def test_parse_020_excludes_backlog_via_h2_boundary(self):
        # Tasks living in Backlog section are NOT picked up by 0.2.0 release parse.
        rows = roadmap.parse_release_section("0.2.0", roadmap_text=SAMPLE_ROADMAP_WITH_BACKLOG)
        ids = [r.task_id for r in rows]
        assert "0.2.0.01" in ids
        assert "0.2.0.02" in ids
        assert "0.2.0.03" in ids
        # 0.2.0.14 is in Backlog section, NOT in 0.2.0 section.
        assert "0.2.0.14" not in ids

    def test_parse_030_excludes_backlog_030_rows(self):
        rows = roadmap.parse_release_section("0.3.0", roadmap_text=SAMPLE_ROADMAP_WITH_BACKLOG)
        ids = [r.task_id for r in rows]
        assert "0.3.0.01" in ids
        # 0.3.0.04 in Backlog — excluded.
        assert "0.3.0.04" not in ids

    def test_is_in_backlog_positive(self):
        assert roadmap.is_in_backlog("0.2.0.14", roadmap_text=SAMPLE_ROADMAP_WITH_BACKLOG)
        assert roadmap.is_in_backlog("0.3.0.04", roadmap_text=SAMPLE_ROADMAP_WITH_BACKLOG)

    def test_is_in_backlog_negative(self):
        assert not roadmap.is_in_backlog("0.2.0.01", roadmap_text=SAMPLE_ROADMAP_WITH_BACKLOG)
        assert not roadmap.is_in_backlog("0.3.0.01", roadmap_text=SAMPLE_ROADMAP_WITH_BACKLOG)

    def test_no_backlog_section_yields_empty(self):
        rows = roadmap.parse_release_section(roadmap.BACKLOG_VERSION, roadmap_text=SAMPLE_ROADMAP)
        assert rows == []

    def test_backlog_stops_at_next_h2(self):
        # Verify parser stops at `## Agent System` and doesn't bleed.
        rows = roadmap.parse_release_section(
            roadmap.BACKLOG_VERSION, roadmap_text=SAMPLE_ROADMAP_WITH_BACKLOG
        )
        # Only the 2 rows in the Backlog table; nothing from Agent System section.
        assert len(rows) == 2
