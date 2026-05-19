# Hand-crafted JSON fixtures for `naavik_ops` tests

Per plan 25 D.4 + Open Q2 (approved 2026-05-18): hand-crafted JSON fixtures
back the behavioral test suite in lieu of VCR.py recordings.

Fixture files mirror the response shapes from:

- `gh api graphql` (GraphQL queries against Projects v2, issues, milestones).
- `gh api repos/<owner>/<repo>/issues?state=all` (REST list).
- `gh api repos/<owner>/<repo>/milestones?state=all` (REST list).

When adding a new fixture, name it after the API call + a single qualifier:

  `project_items_with_priority.json`        — Projects v2 items + Priority field
  `issues_open_with_bracket_titles.json`    — REST issues, only `[TASK-ID]` form
  `milestones_state_all.json`               — REST milestones list

Tests load fixtures via `json.loads((FIXTURE_DIR / "name.json").read_text())`
and monkeypatch `subprocess.run` to return them. No network round-trip in CI.
