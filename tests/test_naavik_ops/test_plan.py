"""Tests for naavik_ops.plan — `naavik-ops plan archive` subcommand."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def sandbox_plan(tmp_path, monkeypatch):
    """Sandbox the plan module against a tmp repo with git + minimal layout."""
    from naavik_ops import plan as plan_mod

    repo = tmp_path / "repo"
    (repo / "docs" / "plans" / "archive").mkdir(parents=True)
    (repo / "docs" / "prompts" / "archive").mkdir(parents=True)
    (repo / "traces").mkdir(parents=True)

    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / ".gitkeep").write_text("")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=str(repo), check=True)

    monkeypatch.setattr(plan_mod, "REPO_ROOT", repo)
    monkeypatch.setattr(plan_mod, "PLANS_DIR", repo / "docs" / "plans")
    monkeypatch.setattr(plan_mod, "ARCHIVE_DIR", repo / "docs" / "plans" / "archive")
    monkeypatch.setattr(plan_mod, "PROMPTS_DIR", repo / "docs" / "prompts")
    monkeypatch.setattr(plan_mod, "PROMPTS_ARCHIVE_DIR", repo / "docs" / "prompts" / "archive")
    monkeypatch.setattr(plan_mod, "TRACES_DIR", repo / "traces")
    return plan_mod, repo


def _write_plan(repo: Path, slug: str, body: str | None = None) -> Path:
    p = repo / "docs" / "plans" / f"{slug}.md"
    text = textwrap.dedent(
        f"""\
        ---
        Status: APPROVED
        Type: design
        Authored: 2026-05-19
        Last updated: 2026-05-19
        ---

        # {slug}

        ## Goal

        Demo plan body for tests.

        ## Proposal

        Stub.
        """
    )
    if body:
        text = text + body
    p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", str(p)], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-qm", f"add {slug}"], cwd=str(repo), check=True)
    return p


def _write_devlog(repo: Path, run_id: str, lines: list[str]) -> Path:
    log_dir = repo / "traces" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / "engineer-deviations.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


# -----------------------------------------------------------------------------
# Happy path — entries lift, git mv, frontmatter flip.
# -----------------------------------------------------------------------------


class TestArchiveHappyPath:
    def test_lifts_entries_and_mv_to_archive(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "99-demo"
        plan_path = _write_plan(repo, slug)
        run_id = "2026-05-19T20-00-00_aaaaaa"
        _write_devlog(
            repo,
            run_id,
            [
                f"[2026-05-19T20:00:00Z] DEVIATION plan=docs/plans/{slug}.md "
                f"what=NullPool engine swap why=greenlet race impact=internal only",
                f"[2026-05-19T20:00:05Z] DEVIATION plan=docs/plans/{slug}.md "
                f"what=Added NAAVIK_FOO env var why=dev parity impact=propagated to .env.example",
            ],
        )

        rc = plan_mod.cmd_archive([str(plan_path), "--run-id", run_id])

        assert rc == 0
        archived = repo / "docs" / "plans" / "archive" / f"{slug}.md"
        assert archived.exists()
        assert not plan_path.exists()
        text = archived.read_text()
        assert "## Deviations from plan" in text
        assert "NullPool engine swap" in text
        assert "Added NAAVIK_FOO env var" in text
        assert "Status: EXECUTED" in text
        out = capsys.readouterr().out
        assert "ARCHIVED" in out
        assert "Deviations promoted: 2" in out
        assert "env var" in out  # surface propagation surfaced


# -----------------------------------------------------------------------------
# Refusals — empty log w/o override.
# -----------------------------------------------------------------------------


class TestArchiveRefusesEmpty:
    def test_no_entries_and_no_section_exits_2(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "98-empty"
        plan_path = _write_plan(repo, slug)
        run_id = "2026-05-19T20-00-00_emptyy"
        _write_devlog(repo, run_id, [])

        rc = plan_mod.cmd_archive([str(plan_path), "--run-id", run_id])
        assert rc == 2
        # Plan was NOT moved.
        assert plan_path.exists()
        err = capsys.readouterr().err
        assert "refusing to archive" in err
        assert "engineer-deviations.log" in err

    def test_no_run_id_and_no_traces_dir_still_refuses(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "97-no-traces"
        plan_path = _write_plan(repo, slug)
        # No trace dir written.

        rc = plan_mod.cmd_archive([str(plan_path)])
        assert rc == 2
        assert plan_path.exists()


# -----------------------------------------------------------------------------
# --no-material-deviations — explicit-bypass surface.
# -----------------------------------------------------------------------------


class TestNoMaterialDeviations:
    def test_writes_placeholder_bullet_and_archives(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "96-trivial"
        plan_path = _write_plan(repo, slug)

        rc = plan_mod.cmd_archive([str(plan_path), "--no-material-deviations", "doc-only typo fix"])
        assert rc == 0
        archived = repo / "docs" / "plans" / "archive" / f"{slug}.md"
        assert archived.exists()
        text = archived.read_text()
        assert "## Deviations from plan" in text
        assert "No material deviations — doc-only typo fix." in text


# -----------------------------------------------------------------------------
# --force — manually authored section.
# -----------------------------------------------------------------------------


class TestForceFlag:
    def test_force_archives_when_section_populated_and_no_log(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "95-hand-authored"
        body = textwrap.dedent(
            """\

            ## Deviations from plan

            - **Hand-authored bullet** — what: X. why: Y. impact: Z. surface: none.
            """
        )
        plan_path = _write_plan(repo, slug, body=body)

        rc = plan_mod.cmd_archive([str(plan_path), "--force"])
        assert rc == 0
        archived = repo / "docs" / "plans" / "archive" / f"{slug}.md"
        assert archived.exists()
        text = archived.read_text()
        # Existing bullet preserved.
        assert "Hand-authored bullet" in text

    def test_section_populated_no_log_no_force_exits_2(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "94-needs-force"
        body = textwrap.dedent(
            """\

            ## Deviations from plan

            - **Existing** — what: a. why: b. impact: c. surface: none.
            """
        )
        plan_path = _write_plan(repo, slug, body=body)
        run_id = "2026-05-19T20-00-00_xxxxx"
        _write_devlog(repo, run_id, [])

        rc = plan_mod.cmd_archive([str(plan_path), "--run-id", run_id])
        assert rc == 2
        assert plan_path.exists()
        err = capsys.readouterr().err
        assert "--force" in err


# -----------------------------------------------------------------------------
# --run-id override.
# -----------------------------------------------------------------------------


class TestRunIdOverride:
    def test_explicit_run_id_picks_specific_log(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "93-run-id"
        plan_path = _write_plan(repo, slug)
        # Two runs; later run has NO entries for this plan; earlier run does.
        earlier = "2026-05-18T10-00-00_oldold"
        later = "2026-05-19T20-00-00_newnew"
        _write_devlog(
            repo,
            earlier,
            [
                f"[2026-05-18T10:00:00Z] DEVIATION plan=docs/plans/{slug}.md "
                f"what=From earlier run why=ok impact=internal"
            ],
        )
        _write_devlog(repo, later, [])

        # Without --run-id picks "later" (lex-latest), should refuse.
        rc = plan_mod.cmd_archive([str(plan_path)])
        assert rc == 2
        assert plan_path.exists()

        # With explicit --run-id earlier, lifts the entry.
        rc = plan_mod.cmd_archive([str(plan_path), "--run-id", earlier])
        assert rc == 0
        archived = repo / "docs" / "plans" / "archive" / f"{slug}.md"
        assert "From earlier run" in archived.read_text()


# -----------------------------------------------------------------------------
# --dry-run — no writes / no git ops.
# -----------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_no_file_changes(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "92-dry"
        plan_path = _write_plan(repo, slug)
        run_id = "2026-05-19T20-00-00_dryrun"
        _write_devlog(
            repo,
            run_id,
            [f"[2026-05-19T20:00:00Z] DEVIATION plan=docs/plans/{slug}.md what=x why=y impact=z"],
        )

        before = plan_path.read_text()
        rc = plan_mod.cmd_archive([str(plan_path), "--run-id", run_id, "--dry-run"])
        assert rc == 0
        # Plan unchanged; archived target absent.
        assert plan_path.read_text() == before
        assert not (repo / "docs" / "plans" / "archive" / f"{slug}.md").exists()
        out = capsys.readouterr().out
        assert "DRY-RUN" in out


# -----------------------------------------------------------------------------
# Already-archived guard.
# -----------------------------------------------------------------------------


class TestAlreadyArchived:
    def test_refuses_path_under_archive_dir(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        already_archived = repo / "docs" / "plans" / "archive" / "90-old.md"
        already_archived.write_text(
            "---\nStatus: EXECUTED\n---\n\n# 90-old\n\n## Deviations from plan\n\n- x\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", str(already_archived)], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=str(repo), check=True)

        rc = plan_mod.cmd_archive([str(already_archived)])
        assert rc == 2
        err = capsys.readouterr().err
        assert "already" in err.lower()


# -----------------------------------------------------------------------------
# Prompt sidecar archives alongside the plan.
# -----------------------------------------------------------------------------


class TestPromptArchive:
    def test_matching_prompt_moves_too(self, sandbox_plan):
        plan_mod, repo = sandbox_plan
        slug = "89-with-prompt"
        plan_path = _write_plan(repo, slug)
        prompt_path = repo / "docs" / "prompts" / f"{slug}.md"
        prompt_path.write_text("# kickoff prompt\n", encoding="utf-8")
        subprocess.run(["git", "add", str(prompt_path)], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-qm", "add prompt"], cwd=str(repo), check=True)
        run_id = "2026-05-19T20-00-00_prompt"
        _write_devlog(
            repo,
            run_id,
            [f"[2026-05-19T20:00:00Z] DEVIATION plan=docs/plans/{slug}.md what=x why=y impact=z"],
        )

        rc = plan_mod.cmd_archive([str(plan_path), "--run-id", run_id])
        assert rc == 0
        assert (repo / "docs" / "plans" / "archive" / f"{slug}.md").exists()
        assert (repo / "docs" / "prompts" / "archive" / f"{slug}.md").exists()
        assert not prompt_path.exists()


# -----------------------------------------------------------------------------
# Quoted log lines + non-DEVIATION lines.
# -----------------------------------------------------------------------------


class TestDeviationParser:
    def test_quoted_values_are_unwrapped(self, sandbox_plan):
        plan_mod, repo = sandbox_plan
        slug = "88-quoted"
        plan_path = _write_plan(repo, slug)
        run_id = "2026-05-19T20-00-00_quoted"
        _write_devlog(
            repo,
            run_id,
            [
                f"[2026-05-19T20:00:00Z] DEVIATION plan=docs/plans/{slug}.md "
                f"what='changed thing X' why='reason Y' impact='downstream Z'",
                # Skipped: not a DEVIATION line.
                "[2026-05-19T20:00:01Z] EDIT path=src/foo.py reason='one liner'",
            ],
        )

        rc = plan_mod.cmd_archive([str(plan_path), "--run-id", run_id])
        assert rc == 0
        archived = repo / "docs" / "plans" / "archive" / f"{slug}.md"
        text = archived.read_text()
        # Quote characters should be stripped from values.
        assert "'changed thing X'" not in text
        assert "changed thing X" in text


# -----------------------------------------------------------------------------
# Surface detection — env / on-disk / cron / cli / none.
# -----------------------------------------------------------------------------


class TestSurfaceDetection:
    @pytest.mark.parametrize(
        "impact,expected",
        [
            ("new env var FOO added", "env var"),
            ("new on-disk path ~/.naavik/credentials", "on-disk path"),
            ("APScheduler cron schedule for nightly job", "cron schedule"),
            ("naavik-ops plan archive subcommand added", "naavik-ops subcommand"),
            ("alembic migration 0009 added", "db migration"),
            ("purely internal refactor, no operator surface", "none"),
        ],
    )
    def test_detect_surface(self, sandbox_plan, impact, expected):
        plan_mod, _ = sandbox_plan
        assert plan_mod._detect_surface(impact) == expected


# -----------------------------------------------------------------------------
# validate-deviations subcommand — read-only PASS / BLOCK.
# -----------------------------------------------------------------------------


class TestValidateDeviations:
    def test_pass_when_section_nonempty(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "87-valid-pass"
        body = "\n## Deviations from plan\n\n- **X** — what: a. why: b. impact: c. surface: none.\n"
        plan_path = _write_plan(repo, slug, body=body)

        rc = plan_mod.cmd_validate_deviations([str(plan_path)])
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_block_when_section_missing(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "86-valid-block"
        plan_path = _write_plan(repo, slug)

        rc = plan_mod.cmd_validate_deviations([str(plan_path)])
        assert rc == 2
        assert "BLOCK" in capsys.readouterr().err

    def test_block_when_section_empty(self, sandbox_plan, capsys):
        plan_mod, repo = sandbox_plan
        slug = "85-empty-section"
        body = "\n## Deviations from plan\n\n"  # heading w/ no bullets
        plan_path = _write_plan(repo, slug, body=body)

        rc = plan_mod.cmd_validate_deviations([str(plan_path)])
        assert rc == 2


# -----------------------------------------------------------------------------
# Title derivation.
# -----------------------------------------------------------------------------


class TestTitleDerivation:
    @pytest.mark.parametrize(
        "what,expected_prefix",
        [
            (
                "NullPool engine swap fixes greenlet race",
                "NullPool engine swap fixes greenlet race",
            ),
            (
                "Engineer log parser accepts both quoted and unquoted variants in the canonical line",
                "Engineer log parser accepts both quoted",
            ),
        ],
    )
    def test_derive_title_truncates_to_first_six_words(self, sandbox_plan, what, expected_prefix):
        plan_mod, _ = sandbox_plan
        assert plan_mod._derive_title(what).startswith(expected_prefix.split("...")[0])


# ---------------------------------------------------------------------------
# 0.7.0.21c — anchored sentinel after hacker MEDIUM (PR #127)
# ---------------------------------------------------------------------------


class TestNoMaterialDeviationsSentinelAnchored:
    """Closes hacker MEDIUM from PR #127 review: substring regex bypassable.

    Original 21c shipped `r"no material deviations"` substring match —
    accepted negation-bypass prose like "we don't have NO MATERIAL DEVIATIONS".
    Anchored multiline regex rejects this.
    """

    def _has_section(self, content: str, tmp_path):
        from naavik_ops.plan import _has_nonempty_deviations_section
        p = tmp_path / "test_plan.md"
        p.write_text(f"# Plan\n\n## Deviations from plan\n\n{content}\n", encoding="utf-8")
        return _has_nonempty_deviations_section(p)

    def test_anchored_accepts_canonical_sentinel(self, tmp_path):
        assert self._has_section("No material deviations.", tmp_path)

    def test_anchored_accepts_with_em_dash_trailing(self, tmp_path):
        assert self._has_section("No material deviations — all 3 fixes shipped per spec.", tmp_path)

    def test_anchored_accepts_with_colon_trailing(self, tmp_path):
        assert self._has_section("No material deviations: spec matched verbatim.", tmp_path)

    def test_anchored_rejects_negation_bypass(self, tmp_path):
        # Pre-fix substring match would PASS this; anchored MUST reject.
        assert not self._has_section(
            "we don't have NO MATERIAL DEVIATIONS because there are many", tmp_path
        )

    def test_anchored_rejects_embedded_substring(self, tmp_path):
        # Embedded substring inside otherwise-empty-shaped prose.
        assert not self._has_section(
            "This plan claims no material deviations but actually has 5 unsaid ones.",
            tmp_path,
        )

    def test_anchored_rejects_misleading_prefix(self, tmp_path):
        assert not self._has_section(
            "Despite the title 'no material deviations', the work diverged on every axis.",
            tmp_path,
        )

    def test_bullets_still_PASS(self, tmp_path):
        # Regression — bullet-form still works after anchor change.
        assert self._has_section(
            "- **What** Real deviation. **Why** Because. **Impact** Some.", tmp_path
        )
