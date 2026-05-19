"""Tests for naavik_ops.task mutating subcommands (plan 25 D.6).

Atomic 3-store mutation = ROADMAP rewrite + Issue title rewrite + map cache
update under flock. These tests stub the gh module surface so no live GitHub
state is touched.

Coverage:
  - insert (shifts rows down + creates new Issue)
  - defer  (shifts within-section)
  - prioritize (priority-only edit)
  - move (cross-release with milestone change)
  - renumber (compact active gaps)
  - rollback on title-rewrite mid-loop failure (R2 guard)
"""

from __future__ import annotations

import json
import textwrap

import pytest
from naavik_ops import gh, task
from naavik_ops.lib import NaavikOpsError, roadmap

SAMPLE_ROADMAP = textwrap.dedent(
    """\
    # Roadmap

    ### 0.2.0 — Phase 2 Core Backend

    | # | Task | Status | Priority | Notes |
    |---|---|---|---|---|
    | 0.2.0.01 | Sunset vault | [ ] | HIGH | env-based secrets |
    | 0.2.0.02 | Sunset CLI | [ ] | HIGH | after 0.2.0.01 |
    | 0.2.0.05 | Auth hardening | [ ] | MEDIUM | post-sunset cleanup |
    | 0.2.0.08 | Discover API | [x] | LOW | frozen done row past gap |

    ### 0.3.0 — Phase 3 Frontend

    | # | Task | Status | Priority | Notes |
    |---|---|---|---|---|
    | 0.3.0.01 | HTMX scaffolds | [ ] | HIGH | mockups in docs/design |
    | 0.3.0.02 | Auth gate | [ ] | MEDIUM | gates 0.2.0.05 |
    """
)


@pytest.fixture
def sandbox_mutating(tmp_path, monkeypatch):
    """Plant ROADMAP + map + lock; stub the gh module surface."""
    roadmap_file = tmp_path / "ROADMAP.md"
    roadmap_file.write_text(SAMPLE_ROADMAP, encoding="utf-8")
    issue_map = tmp_path / ".claude" / "github-issue-map.json"
    issue_map.parent.mkdir(parents=True)
    issue_map.write_text(
        json.dumps(
            {
                "_meta": {"owner": "crizzy9", "repo": "naavik"},
                "milestones": {"0.2.0": 8, "0.3.0": 15},
                "epics": {"0.2.0": 78, "0.3.0": 85},
                "issues": {
                    "0.2.0.01": 20,
                    "0.2.0.02": 21,
                    "0.2.0.05": 15,
                    "0.2.0.08": 10,
                    "0.3.0.01": 30,
                    "0.3.0.02": 31,
                },
                "priorities": {
                    "0.2.0.01": "HIGH",
                    "0.2.0.05": "MEDIUM",
                    "0.3.0.01": "HIGH",
                },
            }
        ),
        encoding="utf-8",
    )
    lock_path = tmp_path / "naavik-ops.lock"

    monkeypatch.setattr(task, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(task, "ROADMAP_PATH", roadmap_file)
    monkeypatch.setattr(task, "ISSUE_MAP_PATH", issue_map)
    monkeypatch.setattr(task, "LOCK_PATH", lock_path)
    monkeypatch.setattr(roadmap, "ROADMAP_PATH", roadmap_file)

    # Mock the gh helpers the mutating ops call.
    issue_title_log: list[tuple[int, str]] = []

    def _stub_update_title(issue_num, new_title):
        issue_title_log.append((int(issue_num), new_title))

    def _stub_create_issue(rest):
        # Simulate gh create-issue: add the new task_id → fake issue number.
        # task.cmd_create_issue invokes gh.cmd_create_issue, which writes to
        # the map cache. We mock by directly mutating the map.
        task_id = rest[0]
        data = json.loads(issue_map.read_text(encoding="utf-8"))
        issues = data.setdefault("issues", {})
        # Pick a new issue # not already used.
        used = set(issues.values())
        new_num = 99
        while new_num in used:
            new_num += 1
        issues[task_id] = new_num
        issue_map.write_text(json.dumps(data), encoding="utf-8")
        return 0

    def _stub_capture_item_id(issue_num):
        return f"PVT_item_{issue_num}"

    def _stub_set_priority(item_id, priority):
        pass

    def _stub_gh(*args, **kwargs):
        # Tolerate gh CLI calls (issue edit --milestone, etc.).
        return ""

    monkeypatch.setattr(gh, "update_issue_title", _stub_update_title)
    monkeypatch.setattr(gh, "cmd_create_issue", _stub_create_issue)
    monkeypatch.setattr(gh, "capture_item_id", _stub_capture_item_id)
    monkeypatch.setattr(gh, "set_priority", _stub_set_priority)
    monkeypatch.setattr(gh, "_gh", _stub_gh)
    monkeypatch.setattr(gh, "_load_cache", lambda: {"owner": "crizzy9", "repo": "naavik"})

    return {
        "task": task,
        "roadmap_file": roadmap_file,
        "issue_map": issue_map,
        "title_log": issue_title_log,
    }


# ---------------------------------------------------------------------------
# insert
# ---------------------------------------------------------------------------


class TestInsert:
    def test_inserts_and_shifts_active_rows(self, sandbox_mutating):
        rc = sandbox_mutating["task"].cmd_insert(
            ["0.2.0.02", "Inserted task", "--priority", "HIGH", "--effort", "S"]
        )
        assert rc == 0

        # ROADMAP must contain the new 0.2.0.02 row and shift 0.2.0.02 → 0.2.0.03.
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        assert "Inserted task" in text
        assert "| 0.2.0.03 |" in text  # was 0.2.0.02 (Sunset CLI) shifted down

        # Frozen 0.2.0.08 [x] NOT renamed.
        assert "| 0.2.0.08 |" in text

        # Map cache: old 0.2.0.02 → 0.2.0.03; new 0.2.0.02 (the inserted task)
        # got a fresh issue number.
        map_data = json.loads(sandbox_mutating["issue_map"].read_text(encoding="utf-8"))
        assert map_data["issues"]["0.2.0.03"] == 21  # was 0.2.0.02 → 21
        assert "0.2.0.02" in map_data["issues"]  # new insertion got a new #
        # Redirects record the shift.
        assert map_data["redirects"]["0.2.0.02"] == "0.2.0.03"

        # gh.update_issue_title was called for #21 with new title.
        edits = sandbox_mutating["title_log"]
        assert (21, "[0.2.0.03] Sunset CLI") in edits

    def test_idempotent_same_title_reinsertion(self, sandbox_mutating, capsys):
        # First insert at position 10 (well past the [x] at position 6;
        # no collision with frozen rows).
        sandbox_mutating["task"].cmd_insert(["0.2.0.10", "Brand new", "--priority", "LOW"])
        capsys.readouterr()
        # Same task_id + same title → no-op.
        rc = sandbox_mutating["task"].cmd_insert(["0.2.0.10", "Brand new", "--priority", "LOW"])
        assert rc == 0
        assert "no-op" in capsys.readouterr().out

    def test_shift_collision_with_done_rejected(self, sandbox_mutating, tmp_path):
        # Stage a denser fixture where the shift would collide.
        denser = textwrap.dedent(
            """\
            # Roadmap

            ### 0.2.0 — Phase 2 Core Backend

            | # | Task | Status | Priority | Notes |
            |---|---|---|---|---|
            | 0.2.0.05 | Active | [ ] | MEDIUM | shifts on insert |
            | 0.2.0.06 | Done frozen | [x] | LOW | cannot shift onto |
            """
        )
        sandbox_mutating["roadmap_file"].write_text(denser, encoding="utf-8")
        with pytest.raises(NaavikOpsError, match="renumber"):
            sandbox_mutating["task"].cmd_insert(["0.2.0.05", "Will collide"])

    def test_rejects_displacing_frozen_done_row(self, sandbox_mutating):
        # Position 08 is [x] in fixture — cannot displace.
        with pytest.raises(NaavikOpsError, match="done row"):
            sandbox_mutating["task"].cmd_insert(["0.2.0.08", "Will fail"])

    def test_rejects_invalid_priority(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="priority must be"):
            sandbox_mutating["task"].cmd_insert(["0.2.0.10", "Title", "--priority", "BOGUS"])

    def test_rejects_invalid_effort(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="effort must be"):
            sandbox_mutating["task"].cmd_insert(["0.2.0.10", "Title", "--effort", "HUGE"])

    def test_missing_args_returns_2(self, sandbox_mutating, capsys):
        rc = sandbox_mutating["task"].cmd_insert(["0.2.0.05"])
        assert rc == 2
        assert "usage" in capsys.readouterr().err

    def test_3_level_rejected(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="4-level"):
            sandbox_mutating["task"].cmd_insert(["0.2.0", "Title"])


# ---------------------------------------------------------------------------
# defer
# ---------------------------------------------------------------------------


class TestDefer:
    def test_defer_by_2_shifts_intermediates(self, sandbox_mutating):
        rc = sandbox_mutating["task"].cmd_defer(["0.2.0.01", "--by", "2"])
        assert rc == 0
        # 0.2.0.01 → 0.2.0.03; intermediate 0.2.0.02 → 0.2.0.01.
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        assert "| 0.2.0.03 | Sunset vault | [ ]" in text
        # The displaced 0.2.0.02 (Sunset CLI) gets shifted UP by 1 (filling
        # the gap left by 0.2.0.01).
        assert "| 0.2.0.01 | Sunset CLI | [ ]" in text

    def test_defer_to_absolute(self, sandbox_mutating):
        rc = sandbox_mutating["task"].cmd_defer(["0.2.0.01", "--to", "4"])
        assert rc == 0
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        assert "| 0.2.0.04 | Sunset vault | [ ]" in text

    def test_defer_done_row_rejected(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="cannot defer"):
            sandbox_mutating["task"].cmd_defer(["0.2.0.08", "--by", "1"])

    def test_defer_into_done_position_rejected(self, sandbox_mutating):
        # Position 08 is [x]. Try to defer 0.2.0.01 → position 08.
        with pytest.raises(NaavikOpsError, match="done row"):
            sandbox_mutating["task"].cmd_defer(["0.2.0.01", "--to", "8"])

    def test_defer_requires_one_of_by_or_to(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="exactly one of"):
            sandbox_mutating["task"].cmd_defer(["0.2.0.01"])
        with pytest.raises(NaavikOpsError, match="exactly one of"):
            sandbox_mutating["task"].cmd_defer(["0.2.0.01", "--by", "1", "--to", "3"])


# ---------------------------------------------------------------------------
# prioritize
# ---------------------------------------------------------------------------


class TestPrioritize:
    def test_changes_priority_in_roadmap_and_map(self, sandbox_mutating):
        rc = sandbox_mutating["task"].cmd_prioritize(["0.2.0.05", "--to-priority", "CRITICAL"])
        assert rc == 0
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        # The row should now have CRITICAL priority cell.
        assert "| 0.2.0.05 | Auth hardening | [ ] | CRITICAL" in text

        map_data = json.loads(sandbox_mutating["issue_map"].read_text(encoding="utf-8"))
        assert map_data["priorities"]["0.2.0.05"] == "CRITICAL"

    def test_unset_drops_priority_key(self, sandbox_mutating):
        sandbox_mutating["task"].cmd_prioritize(["0.2.0.05", "--to-priority", "UNSET"])
        map_data = json.loads(sandbox_mutating["issue_map"].read_text(encoding="utf-8"))
        assert "0.2.0.05" not in map_data.get("priorities", {})

    def test_no_op_when_priority_unchanged(self, sandbox_mutating, capsys):
        rc = sandbox_mutating["task"].cmd_prioritize(["0.2.0.05", "--to-priority", "MEDIUM"])
        assert rc == 0
        assert "no-op" in capsys.readouterr().out

    def test_invalid_priority_rejected(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="priority must be"):
            sandbox_mutating["task"].cmd_prioritize(["0.2.0.05", "--to-priority", "BOGUS"])


# ---------------------------------------------------------------------------
# move (cross-release)
# ---------------------------------------------------------------------------


class TestMove:
    def test_cross_release_move(self, sandbox_mutating):
        rc = sandbox_mutating["task"].cmd_move(["0.2.0.05", "0.3.0.02"])
        assert rc == 0
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        # 0.2.0.05 vanishes from source section.
        assert "| 0.2.0.05 |" not in text
        # 0.3.0.02 in dest now is the moved task.
        assert "| 0.3.0.02 | Auth hardening | [ ]" in text
        # Old 0.3.0.02 (Auth gate) shifted to 0.3.0.03.
        assert "| 0.3.0.03 | Auth gate | [ ]" in text

        map_data = json.loads(sandbox_mutating["issue_map"].read_text(encoding="utf-8"))
        # Issue # 15 (was 0.2.0.05) now keyed under 0.3.0.02.
        assert map_data["issues"]["0.3.0.02"] == 15
        # Old key dropped.
        assert "0.2.0.05" not in map_data["issues"]
        # Redirects record.
        assert map_data["redirects"]["0.2.0.05"] == "0.3.0.02"

    def test_within_section_move_delegates_to_defer(self, sandbox_mutating):
        rc = sandbox_mutating["task"].cmd_move(["0.2.0.01", "0.2.0.03"])
        assert rc == 0
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        assert "| 0.2.0.03 | Sunset vault | [ ]" in text

    def test_done_row_rejected(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="cannot move"):
            sandbox_mutating["task"].cmd_move(["0.2.0.08", "0.3.0.03"])

    def test_3_level_dest_rejected(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="4-level"):
            sandbox_mutating["task"].cmd_move(["0.2.0.05", "0.3.0"])

    def test_priority_follows_task(self, sandbox_mutating):
        # 0.2.0.01 is HIGH. After moving to 0.3.0.05, the moved row's priority
        # remains HIGH (per Open Q5: "priority follows the task across the
        # shift, not the position").
        sandbox_mutating["task"].cmd_move(["0.2.0.01", "0.3.0.05"])
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        assert "| 0.3.0.05 | Sunset vault | [ ] | HIGH" in text


# ---------------------------------------------------------------------------
# renumber
# ---------------------------------------------------------------------------


class TestRenumber:
    def test_compacts_gaps(self, sandbox_mutating):
        # Fixture: 0.2.0.01, 0.2.0.02, 0.2.0.05, 0.2.0.08 [x].
        # Compact: 0.2.0.01, 0.2.0.02 stay; 0.2.0.05 (active) → 0.2.0.03;
        # 0.2.0.08 [x] preserved at position 08.
        rc = sandbox_mutating["task"].cmd_renumber(["0.2.0"])
        assert rc == 0
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        assert "| 0.2.0.03 | Auth hardening | [ ]" in text
        # Original 0.2.0.05 should be gone (now 0.2.0.03).
        assert "| 0.2.0.05 |" not in text
        # 0.2.0.08 [x] preserved.
        assert "| 0.2.0.08 |" in text and "Discover API" in text

    def test_no_op_when_compact(self, sandbox_mutating, capsys):
        # Run twice — second is a no-op.
        sandbox_mutating["task"].cmd_renumber(["0.2.0"])
        capsys.readouterr()
        rc = sandbox_mutating["task"].cmd_renumber(["0.2.0"])
        assert rc == 0
        assert "no-op" in capsys.readouterr().out

    def test_rejects_4_level(self, sandbox_mutating):
        with pytest.raises(NaavikOpsError, match="3-level"):
            sandbox_mutating["task"].cmd_renumber(["0.2.0.05"])


# ---------------------------------------------------------------------------
# Failure rollback (R2 guard)
# ---------------------------------------------------------------------------


class TestInsertFailureRollback:
    def test_title_rewrite_mid_failure_rolls_back(self, sandbox_mutating, monkeypatch):
        # Make the 2nd update_issue_title call fail mid-loop.
        call_count = [0]
        rollback_log: list[tuple[int, str]] = []

        def _failing_title(issue_num, new_title):
            call_count[0] += 1
            # First call succeeds; second raises. Subsequent calls (rollback)
            # are accepted.
            if call_count[0] == 2 and not new_title.startswith("[0.2.0.02]"):
                # Mid-loop failure on a non-rollback edit.
                raise NaavikOpsError("simulated rate-limit")
            rollback_log.append((int(issue_num), new_title))

        monkeypatch.setattr(gh, "update_issue_title", _failing_title)
        # Insert at position 01 — would shift 0.2.0.01, 0.2.0.02, 0.2.0.05.
        with pytest.raises(NaavikOpsError, match="rate-limit"):
            sandbox_mutating["task"].cmd_insert(["0.2.0.01", "Will fail mid-loop"])

        # Rollback log must include re-issuance of OLD title for the one that
        # succeeded before the failure.
        assert any(t.startswith("[0.2.0.01]") for _, t in rollback_log), (
            "rollback must re-issue OLD title on already-edited issues"
        )

        # ROADMAP must NOT have been overwritten (atomicity).
        text = sandbox_mutating["roadmap_file"].read_text(encoding="utf-8")
        assert "Will fail mid-loop" not in text
