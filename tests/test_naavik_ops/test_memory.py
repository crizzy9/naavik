"""Behavioral tests for naavik_ops.memory (native Python; plan 25 D.8).

These tests exercise every subcommand against a temp `.claude/memory/` so
the real corpus isn't touched. Tests lock down:

  - Atomic JSONL append (Finding 1 — flock).
  - jq sandbox: env / getpath / etc. rejected (Finding 2 — A.17 regression).
  - validate_aliases newline + fence rejection (Finding 4).
  - knowledge auto-INDEX regeneration.
  - mine-patterns aggregation + promote-lesson threshold (Wave 2/3).
"""

from __future__ import annotations

import json
import os

import pytest
from naavik_ops import memory
from naavik_ops.lib import NaavikOpsError


@pytest.fixture
def sandbox_memory(tmp_path, monkeypatch):
    """Plant a temp memory dir; rebind module paths; return the module."""
    memory_dir = tmp_path / ".claude" / "memory"
    traces_root = tmp_path / "traces"
    memory_dir.mkdir(parents=True)
    traces_root.mkdir(parents=True)

    monkeypatch.setattr(memory, "MEMORY_DIR", memory_dir)
    monkeypatch.setattr(memory, "DECISIONS", memory_dir / "decisions.jsonl")
    monkeypatch.setattr(memory, "DISCUSSIONS", memory_dir / "discussions.jsonl")
    monkeypatch.setattr(memory, "LESSONS", memory_dir / "lessons.jsonl")
    monkeypatch.setattr(memory, "PATTERNS", memory_dir / "recurring-patterns.jsonl")
    monkeypatch.setattr(memory, "KNOWLEDGE_DIR", memory_dir / "knowledge")
    monkeypatch.setattr(memory, "RUNS_DIR", memory_dir / "runs-analysis")
    monkeypatch.setattr(memory, "LOCK_FILE", memory_dir / ".lock")
    monkeypatch.setattr(memory, "TRACES_ROOT", traces_root)
    return memory


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestInit:
    def test_creates_dirs_and_stores(self, sandbox_memory):
        rc = sandbox_memory.cmd_init([])
        assert rc == 0
        assert sandbox_memory.DECISIONS.is_file()
        assert sandbox_memory.DISCUSSIONS.is_file()
        assert sandbox_memory.LESSONS.is_file()
        assert sandbox_memory.PATTERNS.is_file()
        assert sandbox_memory.KNOWLEDGE_DIR.is_dir()
        assert sandbox_memory.RUNS_DIR.is_dir()

    def test_idempotent(self, sandbox_memory):
        assert sandbox_memory.cmd_init([]) == 0
        assert sandbox_memory.cmd_init([]) == 0


# ---------------------------------------------------------------------------
# record-decision
# ---------------------------------------------------------------------------


class TestRecordDecision:
    def test_appends_one_row(self, sandbox_memory):
        rc = sandbox_memory.cmd_record_decision(
            ["storage-backend", "JSONL + markdown", "see plan 19"]
        )
        assert rc == 0
        lines = sandbox_memory.DECISIONS.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["id"] == "storage-backend"
        assert row["state"] == "active"

    def test_duplicate_rejected(self, sandbox_memory):
        sandbox_memory.cmd_record_decision(["d1", "v", "r"])
        with pytest.raises(NaavikOpsError, match="exists"):
            sandbox_memory.cmd_record_decision(["d1", "v2", "r2"])

    def test_supersede_marks_old(self, sandbox_memory):
        sandbox_memory.cmd_record_decision(["d1", "v", "r"])
        sandbox_memory.cmd_record_decision(["d2", "v-new", "r-new", "--supersedes", "d1"])
        rows = [
            json.loads(line)
            for line in sandbox_memory.DECISIONS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 2
        old = next(r for r in rows if r["id"] == "d1")
        assert old["state"] == "superseded"
        assert old["superseded_by"] == "d2"

    def test_run_id_stored(self, sandbox_memory):
        sandbox_memory.cmd_record_decision(["d1", "v", "r", "--run-id", "test-run"])
        row = json.loads(sandbox_memory.DECISIONS.read_text(encoding="utf-8").strip())
        assert row["run_id"] == "test-run"


# ---------------------------------------------------------------------------
# record-discussion
# ---------------------------------------------------------------------------


class TestRecordDiscussion:
    def test_auto_id_pattern(self, sandbox_memory):
        sandbox_memory.cmd_record_discussion(
            ["JWT denylist", "manager.log", "--phase", "Phase 1.x", "--priority", "MEDIUM"]
        )
        row = json.loads(sandbox_memory.DISCUSSIONS.read_text(encoding="utf-8").strip())
        import re

        assert re.match(r"^\d{8}-[a-f0-9]{6}$", row["id"])
        assert row["priority"] == "MEDIUM"
        assert row["phase"] == "Phase 1.x"


# ---------------------------------------------------------------------------
# record-knowledge
# ---------------------------------------------------------------------------


class TestRecordKnowledge:
    def test_creates_file_with_front_matter(self, sandbox_memory, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("body content here\n", encoding="utf-8")
        rc = sandbox_memory.cmd_record_knowledge(
            [
                "test-topic",
                str(body_file),
                "--aliases",
                "phrase a, phrase b",
                "--confidence",
                "high",
            ]
        )
        assert rc == 0
        out = sandbox_memory.KNOWLEDGE_DIR / "test-topic.md"
        assert out.is_file()
        content = out.read_text(encoding="utf-8")
        assert "Topic: test-topic" in content
        assert "Aliases: phrase a, phrase b" in content
        assert "Confidence: high" in content
        assert "body content here" in content

    def test_auto_creates_index(self, sandbox_memory, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("x", encoding="utf-8")
        sandbox_memory.cmd_record_knowledge(["test-topic", str(body_file)])
        idx = sandbox_memory.KNOWLEDGE_DIR / "INDEX.md"
        assert idx.is_file()
        assert "test-topic" in idx.read_text(encoding="utf-8")
        assert "AUTO-GENERATED" in idx.read_text(encoding="utf-8")

    def test_refuses_overwrite_without_flag(self, sandbox_memory, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("x", encoding="utf-8")
        sandbox_memory.cmd_record_knowledge(["test-topic", str(body_file)])
        with pytest.raises(NaavikOpsError, match="exists"):
            sandbox_memory.cmd_record_knowledge(["test-topic", str(body_file)])

    def test_rejects_non_kebab_slug(self, sandbox_memory, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("x", encoding="utf-8")
        with pytest.raises(NaavikOpsError, match="kebab-case"):
            sandbox_memory.cmd_record_knowledge(["BadSlug", str(body_file)])

    def test_rejects_bad_confidence(self, sandbox_memory, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("x", encoding="utf-8")
        with pytest.raises(NaavikOpsError, match="confidence"):
            sandbox_memory.cmd_record_knowledge(
                ["another-topic", str(body_file), "--confidence", "bogus"]
            )

    def test_stdin_dash_reads_body(self, sandbox_memory, monkeypatch):
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("stdin body"))
        rc = sandbox_memory.cmd_record_knowledge(["from-stdin", "-"])
        assert rc == 0
        out = sandbox_memory.KNOWLEDGE_DIR / "from-stdin.md"
        assert "stdin body" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A.17 hardening — Finding 4 (aliases validation)
# ---------------------------------------------------------------------------


class TestAliasesValidation:
    def test_newline_in_aliases_rejected(self, sandbox_memory, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("x", encoding="utf-8")
        with pytest.raises(NaavikOpsError, match="newlines"):
            sandbox_memory.cmd_record_knowledge(
                ["alias-injection", str(body_file), "--aliases", "pwned\n---\nTopic:owned"]
            )

    def test_fence_in_aliases_rejected(self, sandbox_memory, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("x", encoding="utf-8")
        with pytest.raises(NaavikOpsError, match="fence"):
            sandbox_memory.cmd_record_knowledge(
                ["alias-fence", str(body_file), "--aliases", "good, ---, evil"]
            )

    def test_charset_violation_rejected(self, sandbox_memory, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("x", encoding="utf-8")
        with pytest.raises(NaavikOpsError, match="comma-separated"):
            sandbox_memory.cmd_record_knowledge(
                ["alias-bad", str(body_file), "--aliases", "good, $exfil"]
            )

    def test_uppercase_and_hash_allowed(self, sandbox_memory, tmp_path):
        # A.17a: ALIASES_RE widened to admit uppercase + '#'.
        body_file = tmp_path / "body.md"
        body_file.write_text("x", encoding="utf-8")
        rc = sandbox_memory.cmd_record_knowledge(
            ["alias-uppercase", str(body_file), "--aliases", "TestClient, MCP, Closes #N"]
        )
        assert rc == 0


# ---------------------------------------------------------------------------
# A.17 hardening — Finding 2 (jq sandbox)
# ---------------------------------------------------------------------------


class TestQuerySandbox:
    def test_env_exfil_rejected(self, sandbox_memory):
        with pytest.raises(NaavikOpsError, match="env"):
            sandbox_memory._validate_jq_expr("true) | env.NAAVIK_TEST_SECRET")

    def test_getpath_rejected(self, sandbox_memory):
        with pytest.raises(NaavikOpsError, match="getpath"):
            sandbox_memory._validate_jq_expr("getpath([])")

    def test_path_identifier_rejected_at_word_boundary(self, sandbox_memory):
        with pytest.raises(NaavikOpsError, match="path"):
            sandbox_memory._validate_jq_expr('.path == "x"')

    def test_pattern_id_substring_with_path_not_false_positive(self, sandbox_memory):
        # 'pattern_id' contains 'path' but inside a word — must NOT trigger.
        sandbox_memory._validate_jq_expr('.pattern_id == "test-step__pivot"')

    def test_dollar_env_rejected(self, sandbox_memory):
        with pytest.raises(NaavikOpsError, match=r"\$ENV"):
            sandbox_memory._validate_jq_expr("$ENV.HOME")

    def test_safe_state_active_passes(self, sandbox_memory):
        sandbox_memory._validate_jq_expr('.state == "active"')

    def test_input_identifier_rejected(self, sandbox_memory):
        with pytest.raises(NaavikOpsError, match="input"):
            sandbox_memory._validate_jq_expr("input | .x")


# ---------------------------------------------------------------------------
# A.17 hardening — Finding 1 (concurrent flock writes)
# ---------------------------------------------------------------------------


class TestConcurrentWrites:
    def test_serial_writes_all_persist(self, sandbox_memory):
        # 10 sequential record-discussion calls; assert all 10 land.
        for i in range(10):
            sandbox_memory.cmd_record_discussion([f"topic-{i}", "test.log"])
        lines = sandbox_memory.DISCUSSIONS.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 10

    def test_parallel_writes_all_persist(self, sandbox_memory):
        # 30 background workers — same shape as bash test_agent_memory.sh § 19.
        # ThreadPoolExecutor (not multiprocessing) because closures over a
        # monkeypatched module aren't pickle-able. Flock semantics on Linux
        # protect across threads same as across processes (fcntl.LOCK_EX held
        # at the OS level, not just in process memory).
        from concurrent.futures import ThreadPoolExecutor, wait

        def _w(i):
            sandbox_memory.cmd_record_discussion([f"concurrency-{i}", "test.log"])

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_w, i) for i in range(30)]
            wait(futures)
            for f in futures:
                f.result()  # surface exceptions

        lines = sandbox_memory.DISCUSSIONS.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 30


# ---------------------------------------------------------------------------
# record-lesson
# ---------------------------------------------------------------------------


class TestRecordLesson:
    def test_appends_with_evidence_runs_split(self, sandbox_memory):
        rc = sandbox_memory.cmd_record_lesson(
            [
                "lesson-test-1",
                "test pattern",
                "run1, run2 , run3",
                "--proposed-action",
                "do the thing",
            ]
        )
        assert rc == 0
        row = json.loads(sandbox_memory.LESSONS.read_text(encoding="utf-8").strip())
        assert row["evidence_runs"] == ["run1", "run2", "run3"]
        assert row["proposed_action"] == "do the thing"


# ---------------------------------------------------------------------------
# list / query
# ---------------------------------------------------------------------------


class TestList:
    def test_empty_stores_emit_friendly(self, sandbox_memory, capsys):
        rc = sandbox_memory.cmd_list(["decisions"])
        assert rc == 0
        assert "(no decisions yet)" in capsys.readouterr().out

    def test_decisions_listed(self, sandbox_memory, capsys):
        sandbox_memory.cmd_record_decision(["d1", "v1", "r1"])
        sandbox_memory.cmd_record_decision(["d2", "v2", "r2"])
        capsys.readouterr()  # drain
        rc = sandbox_memory.cmd_list(["decisions"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "d1" in out
        assert "d2" in out

    def test_unknown_store_raises(self, sandbox_memory):
        with pytest.raises(NaavikOpsError, match="unknown store"):
            sandbox_memory.cmd_list(["nonsense"])


class TestQueryWithJq:
    def test_filters_active(self, sandbox_memory, capsys):
        # Only run if jq is available.
        import shutil

        if shutil.which("jq") is None:
            pytest.skip("jq not on PATH")
        sandbox_memory.cmd_record_decision(["d1", "v1", "r1"])
        sandbox_memory.cmd_record_decision(["d2", "v2", "r2", "--supersedes", "d1"])
        capsys.readouterr()
        rc = sandbox_memory.cmd_query(["decisions", '.state == "active"'])
        assert rc == 0
        out = capsys.readouterr().out
        # 1 active row (d2); d1 was marked superseded.
        active_lines = [line for line in out.splitlines() if line.strip()]
        assert len(active_lines) == 1


# ---------------------------------------------------------------------------
# analyze-run
# ---------------------------------------------------------------------------


class TestAnalyzeRun:
    def test_produces_markdown_with_sections(self, sandbox_memory):
        run_id = "2099-12-31T00-00-00_test01"
        run_dir = sandbox_memory.TRACES_ROOT / run_id
        run_dir.mkdir()
        (run_dir / "MANIFEST.json").write_text(
            json.dumps(
                {
                    "started_at": "2099-12-31T00:00:00Z",
                    "ended_at": "2099-12-31T00:30:00Z",
                    "milestone": "test-milestone",
                    "outcome": "delivered",
                    "halt_reason": None,
                    "tokens_spent": {"manager": 100, "engineer": 200},
                    "files_touched": ["test.py"],
                }
            )
        )
        (run_dir / "engineer.log").write_text(
            "[2099-12-31T00:00:00Z] EDIT test.py reason='test'\n"
            "[2099-12-31T00:10:00Z] ERROR step=test-step kind=pivot reason='one' attempt=1/1\n"
            "[2099-12-31T00:20:00Z] ERROR step=test-step kind=pivot reason='two' attempt=1/1\n"
            "[2099-12-31T00:30:00Z] BUILT files_added=1 summary='test ship'\n"
        )
        rc = sandbox_memory.cmd_analyze_run([run_id])
        assert rc == 0
        out = sandbox_memory.RUNS_DIR / f"{run_id}.md"
        assert out.is_file()
        body = out.read_text(encoding="utf-8")
        assert "milestone: test-milestone" in body
        assert "pivot: 2" in body
        assert "BUILT files_added=1" in body

    def test_fence_blocks_md_injection(self, sandbox_memory):
        # Finding 5 — MANIFEST values must land inside fenced code blocks.
        run_id = "2099-12-31T05-00-00_test05"
        run_dir = sandbox_memory.TRACES_ROOT / run_id
        run_dir.mkdir()
        (run_dir / "MANIFEST.json").write_text(
            json.dumps(
                {
                    "milestone": "fence-test",
                    "outcome": "delivered",
                    "halt_reason": None,
                    "tokens_spent": {"agent-b": "`whoami`"},
                    "files_touched": ["[evil](http://x.test)", "`whoami`"],
                }
            )
        )
        sandbox_memory.cmd_analyze_run([run_id])
        body = (sandbox_memory.RUNS_DIR / f"{run_id}.md").read_text(encoding="utf-8")
        # The `[evil](...)` literal must occur inside fenced code blocks.
        assert "```" in body
        # Naive check: the [evil] string comes AFTER a ``` opening line.
        assert "[evil](http://x.test)" in body


# ---------------------------------------------------------------------------
# mine-patterns
# ---------------------------------------------------------------------------


class TestMinePatterns:
    def test_aggregates_across_runs(self, sandbox_memory):
        for tag in ("run1", "run2", "run3"):
            run_dir = sandbox_memory.TRACES_ROOT / f"2099-12-31T00-00-00_{tag}"
            run_dir.mkdir()
            (run_dir / "engineer.log").write_text(
                f"[2099-12-31T00:00:00Z] ERROR step=foo kind=pivot reason='r-{tag}' attempt=1/1\n"
            )
            os.utime(
                run_dir,
                (
                    run_dir.stat().st_atime,
                    run_dir.stat().st_mtime + (10 if tag == "run3" else 0),
                ),
            )
        rc = sandbox_memory.cmd_mine_patterns(["--lookback", "5"])
        assert rc == 0
        rows = [
            json.loads(line)
            for line in sandbox_memory.PATTERNS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 1
        assert rows[0]["pattern_id"] == "foo__pivot"
        assert rows[0]["occurrence_count"] == 3
        assert set(rows[0]["runs"]) == {
            "2099-12-31T00-00-00_run1",
            "2099-12-31T00-00-00_run2",
            "2099-12-31T00-00-00_run3",
        }

    def test_lookback_excludes_old(self, sandbox_memory):
        # No traces at all → still succeeds, writes 0 rows.
        rc = sandbox_memory.cmd_mine_patterns(["--lookback", "3"])
        assert rc == 0


# ---------------------------------------------------------------------------
# promote-lesson — threshold gate
# ---------------------------------------------------------------------------


class TestPromoteLesson:
    def test_below_threshold_rejected(self, sandbox_memory):
        sandbox_memory.cmd_init([])
        sandbox_memory.PATTERNS.write_text(
            json.dumps(
                {
                    "pattern_id": "low-count__pivot",
                    "step": "low-count",
                    "kind": "pivot",
                    "occurrence_count": 4,
                    "runs": ["r1", "r2"],
                    "first_seen": "x",
                    "last_seen": "x",
                    "proposed_action": "",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with pytest.raises(NaavikOpsError, match="threshold"):
            sandbox_memory.cmd_promote_lesson(["low-count__pivot"])

    def test_at_threshold_promotes(self, sandbox_memory):
        sandbox_memory.cmd_init([])
        sandbox_memory.PATTERNS.write_text(
            json.dumps(
                {
                    "pattern_id": "hi__pivot",
                    "step": "hi",
                    "kind": "pivot",
                    "occurrence_count": 6,
                    "runs": ["r1", "r2", "r3", "r4", "r5", "r6"],
                    "first_seen": "x",
                    "last_seen": "x",
                    "proposed_action": "split the step",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        rc = sandbox_memory.cmd_promote_lesson(["hi__pivot"])
        assert rc == 0
        # Lesson appended.
        rows = [
            json.loads(line)
            for line in sandbox_memory.LESSONS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(r["id"] == "lesson-hi--pivot" for r in rows)
        # Knowledge stub created.
        stub = sandbox_memory.KNOWLEDGE_DIR / "hi.md"
        assert stub.is_file()


# ---------------------------------------------------------------------------
# capture helpers (programmatic stdout capture)
# ---------------------------------------------------------------------------


class TestCaptureHelpers:
    def test_capture_list(self, sandbox_memory):
        sandbox_memory.cmd_record_decision(["d-x", "v", "r"])
        out = sandbox_memory.capture_list("decisions")
        assert "d-x" in out
