"""Regression lint + smoke for `.claude/migrations/A.28-board-restructure.sh`.

Plan 55 / 0.2.6.08 (A.28a, Issue #64): the one-shot board-restructure runbook
got three defense-in-depth fixes — eval-string replaced with arg-array
pass-through, rollback contract documented in the header, and the silent
`--apply` default flipped to `--dry-run`.

These shape tests assert each invariant without invoking the script against
live GitHub state. The smoke test runs the script in dry-run twice and on
bare invocation to prove dry-run is idempotent and the new default.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent / ".claude" / "migrations" / "A.28-board-restructure.sh"
)


def test_script_exists_and_executable() -> None:
    assert _SCRIPT.is_file(), f"missing migration runbook at {_SCRIPT}"
    assert _SCRIPT.stat().st_mode & 0o111, "script must be executable"


def test_header_contains_rollback_contract() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    head = text[: text.find("set -euo pipefail")]
    assert "Rollback contract:" in head, "header must document the rollback contract"
    # Must point operators at the dispatcher for manual revert.
    assert ".claude/naavik-ops gh set-status" in head


def test_run_helper_uses_arg_array_not_eval() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    # Slice the run() body, then drop comment-only lines so eval-mentions in
    # comments (e.g. "no eval") don't false-positive against the executable
    # body check.
    start = text.index("run() {")
    end = text.index("\n}\n", start)
    body = text[start:end]
    code_lines = [
        ln for ln in body.splitlines() if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert '"$@"' in code, "run() must pass-through via arg array"
    assert "eval " not in code, "run() must not invoke eval"
    assert "%q" in code, "dry-run path must shell-quote args via printf %q"


def test_dry_run_is_the_default() -> None:
    """DRY_RUN=true must appear before any DRY_RUN=false assignment so the
    default branch is dry-run; `--apply` is now opt-in."""
    text = _SCRIPT.read_text(encoding="utf-8")
    first_true = text.find("DRY_RUN=true")
    first_false = text.find("DRY_RUN=false")
    assert first_true != -1, "script must initialize DRY_RUN=true"
    assert first_false != -1, "script must still toggle DRY_RUN=false on --apply"
    assert first_true < first_false, "dry-run must be the default (assignment-before-toggle)"


def test_help_text_advertises_dry_run_default() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "(default: dry-run only)" in text, "help text must surface the new default"


def test_no_composed_string_run_callers_remain() -> None:
    """Any `run "$@-style composed string"` invocation slipped the arg-array
    refactor — block it."""
    text = _SCRIPT.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("run ") and stripped.startswith('run "'):
            pytest.fail(f"composed-string run() caller still present: {line!r}")


def test_dry_run_smoke_exit_zero_and_banner() -> None:
    """Bare invocation defaults to dry-run; explicit --dry-run also dry-run.
    Both exit 0 and emit the DRY-RUN banner. We never invoke --apply in CI
    (that would mutate live GitHub state)."""
    for argv in ([], ["--dry-run"]):
        proc = subprocess.run(
            ["bash", str(_SCRIPT), *argv],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, (
            f"argv={argv!r} exit={proc.returncode} stderr={proc.stderr!r}"
        )
        assert "Mode: DRY-RUN" in proc.stdout, (
            f"argv={argv!r} stdout missing DRY-RUN banner: {proc.stdout!r}"
        )
        # APPLY banner must NOT fire in the default-dry-run paths.
        assert "Mode: APPLY" not in proc.stdout
