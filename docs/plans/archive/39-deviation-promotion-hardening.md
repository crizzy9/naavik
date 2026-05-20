---
Status: APPROVED
Type: design
Authored: 2026-05-19
Last updated: 2026-05-19
Depends on: 25 (`0.1.1` — naavik-ops dispatcher inlined), 19 (A.15 — memory + skill substrate)
Implements: ROADMAP row 0.7.0.21
GitHub: #119

# 39 · Deviation-promotion hardening — close the archive workflow gap

## Goal

Ship `.claude/naavik-ops plan archive <plan-path> [--run-id <id>]` — a native Python subcommand under the dispatcher that becomes the canonical (and only) path to move a plan from `docs/plans/` to `docs/plans/archive/`. It reads every `[ts] DEVIATION plan=<path> ...` line from `traces/<run-id>/engineer-deviations.log` whose `plan=` matches the target plan, lifts each one into a `## Deviations from plan` bullet (canonical shape from `manager-deviation-promote § 5`), refuses the move when the resulting section would be empty, and surfaces every non-`none` operational surface so the manager can land the propagation edits in the same bookkeeping commit. The plumbing replaces the manual `git mv docs/plans/<...> docs/plans/archive/<...>` ritual that just failed five times in run `2026-05-19T15-42-42_833f4a` — manager forgot to invoke `Skill: manager-deviation-promote` and archived 5 of 8 plans empty before a retrofit commit (`29f859d`) papered over the miss. Skill bodies + manager-prompt step 10/11 + AGENTS.md § Workflow step 7 are tightened to require the new command; legacy `git mv` is grep-tested-against in CI.

## Why

The audit speaks. In one run (`2026-05-19T15-42-42_833f4a`) 5 of 8 archived plans (30, 31, 32, 33, 37) shipped without the `## Deviations from plan` section that `AGENTS.md § Workflow step 7` makes non-negotiable. Plan 35 had a stub heading with zero entries. Plans 34, 36 had populated sections only because the engineer hand-back included them inline; plan 38 is still in flight. The retrofit commit `29f859d` populated the missing sections post-archive from engineer transcripts and `engineer-deviations.log` (which had 14 entries from the run, more than enough source material) — but archive-time integrity is now a snapshot lie waiting for the next archive to repeat the miss.

Three existing skills already cover the surface (`engineer-deviation-log`, `manager-deviation-promote`, `naavik-deviations-check`). They're not the failure mode — the failure mode is that all three are advisory: prompts say "use this skill before archive" and the manager forgot because the archive step is a one-line `git mv` with no enforcement surface. Same shape as the pre-A.32 parallel-reviewer-invariant miss — prompt discipline alone doesn't catch repeat misses; we need a hard-stop in the tooling. Plan 39 closes that gap by making the archive command itself the enforcement point: `naavik-ops plan archive` is the only way to do the move, and the command refuses to run if Deviations would be empty.

This isn't theoretical. Plan 38 archive lands within the next two `/build` cycles; the patch-version stability follow-ups from `.claude/memory/knowledge/patch-version-position-stability.md` queue another 4–6 archives in the next milestone. Without 39, every one of those is a repeat-miss candidate. Roadmap impact: 1 row added to Phase A (or whatever housekeeping milestone manager picks at approval) — `A.32` style.

## Proposal

### A. Architectural decisions locked

Three orthogonal decisions need calling out. All three are recommended-default-locked per the zoom-through brief; user can flip any individual one at approval.

#### A.1 Where the enforcement lives

| Option                                      | Capability                                            | Cost                                              | Risk                                                                                                                                          | Maintenance                                                            | Lock-in                                  |
| ------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------- |
| **(a) Prompt-only enforcement**             | tighten skill bodies + manager prompt + AGENTS.md     | 1–2h, no code                                     | **fails the same way** — prompt discipline alone is what just missed 5/8 plans this run; zero hard-stop                                       | per-prompt review; drift trap                                          | none                                     |
| **(b) `naavik-ops plan archive` subcommand** | native Python under existing dispatcher; refuses-on-empty + surface report | ~3h code + ~2h tests; deletes one git-mv ceremony | one command-shape addition. Has actual hard-stop. Skills + manager prompt point at it as the only archive path | extends the `task` / `release` / `deps` / `gh` / `memory` group pattern; new `plan` group | dispatcher-internal; reversible           |
| **(c) Git pre-commit hook**                 | refuses any commit moving `docs/plans/<NN>-...md` to `docs/plans/archive/...md` when target lacks `## Deviations from plan` | ~2h hook + per-clone install; reuses prepare-commit-msg pattern from `.claude/hooks/git/` | **highest hard-stop guarantee** (cannot bypass without `--no-verify`); BUT the hook surface fires on EVERY commit, runs git plumbing per-file under PATCH_INSPECTION, and has zero context for which run-id the manager is on (so can't auto-lift entries — only refuses); workflow becomes "hook says no" → "manually run promote" → "commit again" | per-clone install via symlink (existing convention); not centrally enforceable on fresh clones until `naavik-ops doctor` checks it | pre-commit-hook surface area grows |

**Recommendation: (b).** Strongest cost/value ratio. (a) is what already failed; demonstrably insufficient. (c) gives the strictest gate but it's reactive (refuses) not active (lifts) — the manager still has to invoke promotion separately, so it doesn't solve the "I forgot the skill" failure. (b) is active: the command BOTH lifts entries from the log AND refuses to move if the section ends up empty. The dispatcher group pattern (`task` / `release` / `deps` / `gh` / `memory`) is already proven by plan 25; adding `plan` slots in cleanly. (c) can layer on top later as belt-and-suspenders if (b) is somehow bypassed (`A.32a` follow-up row, low priority).

**Trade-off accepted:** the new command is bypassable by hand-running `git mv` against `docs/plans/archive/`. Defense: (i) AGENTS.md § Workflow step 7 + PLAYBOOK § I + manager prompt step 11 all rewrite to call out `naavik-ops plan archive` as the canonical path; (ii) `tests/test_no_manual_plan_archive_moves.py` lint scans recent commits for `git mv docs/plans/<NN>.*docs/plans/archive/` and fails CI if a single such commit lands without an accompanying `naavik-ops plan archive` invocation in the commit message or `traces/<run-id>/manager.log`. (iii) Belt-and-suspenders pre-commit hook deferred to `A.32a` if (i) + (ii) prove insufficient over the next 5 archives.

#### A.2 Engineer-side: should logging to `engineer-deviations.log` become mandatory?

| Option                                        | Capability                                            | Cost                                | Risk                                                                                                                            | Maintenance                  | Lock-in |
| --------------------------------------------- | ----------------------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | ------- |
| **(a) Keep best-effort prompt enforcement**   | engineer judges what to log                           | 0                                   | repeat: 14 log entries this run, but 5 distinct plans had archive-time deviations that DIDN'T make it to the log (per audit)    | per-run engineer review      | none    |
| **(b) Make engineer hand-back format refuse without log**  | engineer cannot say "ready for review" without N ≥ 0 confirmed deviations OR explicit "ran reconciliation, none" | ~30min prompt tightening + verified at PR-review by architect | low. Adds a single hand-back line. Doesn't slow the loop. | manager-deviation-promote already does reconciliation if log is empty; logging at engineer time is the cheap path | none |
| **(c) Pre-commit hook refuses commit if engineer-deviations.log untouched for the run** | mechanical floor on logging behavior | ~1h hook + per-clone install | engineer pivots that aren't deviations (lint fixes, comment surgery) still trigger the hook; false-positive surface | per-clone | high |

**Recommendation: (b).** The 5 archive-time misses had source material — engineer-deviations.log was open and 14 lines made it in. The miss was at archive-time, not log-time. Tightening the engineer hand-back to require an explicit "deviations summary: <bullet list or 'none — log reconciled against diff'>" line in the hand-back makes the engineer the first checkpoint instead of relying solely on manager's archive step. (c) is overkill for a problem whose 95th-percentile failure happens at archive, not at commit. The archive command (A.1.b) is where the hard-stop belongs.

#### A.3 Manager UX when log entries don't match plan path or section ends up empty

The new `naavik-ops plan archive` produces one of three terminal outcomes. Each gets a specific surface:

1. **Happy path** — N ≥ 1 entries in `engineer-deviations.log` match `plan=<target-path>`; command lifts them, writes section, performs `git mv`. STDOUT:
   ```
   ARCHIVED docs/plans/39-deviation-promotion-hardening.md
     → docs/plans/archive/39-deviation-promotion-hardening.md
   Deviations promoted: 3 bullets (2 operational surfaces flagged — see below)
   Surface propagation required (no auto-apply; manager edits):
     - new env var: NAAVIK_FOO → add to README § Configuration + .env.example
     - new cron schedule (every 10m): NAAVIK_SCRAPE_INTERVAL → add to CLAUDE.md
   ```
   Manager then lands the propagation edits + commits as bookkeeping (per PLAYBOOK § I).

2. **Reconciliation needed** — 0 entries in the log match `plan=<target-path>` BUT the plan's diff vs `main` from the merge SHA shows engineering churn (file additions / deletions). STDOUT prints a `RECONCILIATION_NEEDED` summary listing what diverged from the plan's § Proposal file-by-file, then exits 2 (does not perform the move). Manager invokes `Skill: manager-deviation-promote` to author entries by hand, appends them to the plan's `## Deviations from plan` section, then re-runs `naavik-ops plan archive <plan>` with `--accept-existing-section` to skip the lift step.

3. **Truly no material deviations** — manager runs `naavik-ops plan archive <plan> --no-material-deviations "<one-line-rationale>"`. Command writes `## Deviations from plan\n\nNo material deviations — <rationale>.\n` and performs the move. The flag exists so manager can express "I'm certain" without the command silently empty-archiving. `naavik-deviations-check` skill body adds a note: any plan archived with this flag SHOULD prompt skepticism if any of the touched files in the plan's § Proposal had >5 LOC changes in the merge diff.

Trade-off: --no-material-deviations is the bypass surface. Codified as opt-in (manager has to type it, not the default) and one-line-rationale is mandatory.

### B. Files in scope

```
.claude/naavik-ops                                            (touched — usage doc)
.claude/naavik_ops/cli.py                                     (touched — add "plan" group to GROUPS dict)
.claude/naavik_ops/plan.py                                    (NEW — group module)
.claude/naavik_ops/lib/deviations.py                          (NEW — log-line parser + bullet formatter; reusable)

.claude/skills/engineer-deviation-log/SKILL.md                (touched — § Steps strengthened; new "Hand-back contract" line)
.claude/skills/manager-deviation-promote/SKILL.md             (touched — § Steps points at naavik-ops plan archive)
.claude/skills/naavik-deviations-check/SKILL.md               (touched — § Steps reference command instead of grep)

.claude/agents/manager.md                                     (touched — operating loop step 11 rewritten)
.claude/agents/engineer.md                                    (touched — § Deviation tracking strengthened; hand-back requires deviations summary line)

AGENTS.md                                                     (touched — § Workflow step 7 + step 8 tighten archive contract; new line: "Plan archive happens via `naavik-ops plan archive`, not `git mv`")
CLAUDE.md                                                     (touched — § Deviations workflow updated; reference naavik-ops plan archive)
docs/PLAYBOOK.md                                              (touched — § I BOOKKEEPING allowed files list keeps plan archive moves, but procedure step 1 changes to invoke `naavik-ops plan archive`)
docs/AGENT_OPS.md                                             (touched — § 2.7a dispatcher group surface adds "plan", § 14 if relevant)
docs/design/AGENT_MEMORY.md                                   (no touch — `naavik-ops plan archive` doesn't write to `.claude/memory/`)

tests/test_naavik_ops/test_plan.py                            (NEW — unit tests for plan.py)
tests/test_naavik_ops/test_deviations_lib.py                  (NEW — unit tests for lib/deviations.py)
tests/test_no_manual_plan_archive_moves.py                    (NEW — CI lint scanning recent commits for unguarded git mv)

ROADMAP.md                                                    (touched — new Phase A row "A.32" or similar; gets created during implementation per § F.1)
```

### C. Command shape (D.1 detail of A.1.b)

```
naavik-ops plan archive <plan-path> [--run-id <id>] [--accept-existing-section] [--no-material-deviations "<rationale>"]
                       [--allow-multi-run]
                       [--dry-run]
```

- `<plan-path>` — required positional; absolute OR repo-relative path to the active plan under `docs/plans/<NN>-<slug>.md`.
- `--run-id` — optional. If absent, command picks the most-recent run directory under `traces/` (lex-sort by name; the run-id timestamp prefix makes this safe). If multiple recent runs touched the plan (cross-run plan execution; rare but seen in 35a / 23 / etc.) and `--allow-multi-run` is absent, exit 2 with "found N runs with entries for this plan; pass --run-id explicitly or --allow-multi-run". With `--allow-multi-run`, command consumes entries from ALL matching runs, sorted chronologically.
- `--accept-existing-section` — skip the lift step; command verifies the plan already has a non-empty `## Deviations from plan` section + performs the `git mv`. Errors if section absent or stub-only.
- `--no-material-deviations "<rationale>"` — write a one-bullet placeholder + perform the `git mv`. Mutually exclusive with `--accept-existing-section`.
- `--dry-run` — print what would happen; no file writes, no git operations.

**Exit codes:**
- `0` — archive succeeded (or `--dry-run` clean).
- `2` — refusal-to-archive (empty section, log mismatch, multi-run unguarded).
- `1` — environmental error (file not found, git mv failed).

**Side effects (success path):**

1. Parses the plan's frontmatter; refuses if `Status:` is already `EXECUTED` (already-archived guard).
2. Reads `traces/<run-id>/engineer-deviations.log` (or all if `--allow-multi-run`).
3. Greps lines whose `plan=<active-path>` matches the target.
4. Per line, parses the `what=` / `why=` / `impact=` substrings.
5. Inspects each `impact=` for operational-surface keywords (`env var`, `on-disk path`, `port`, `cron`, `schedule`, `secret`, `mode 0600`, `~/.naavik/`, `.env`) and surfaces a "propagation required" line per match — manager applies in same bookkeeping commit.
6. Opens the plan file. If `## Deviations from plan` heading exists with content, appends; if heading exists empty, fills; if absent, appends new section before EOF.
7. Bullet format (matches `manager-deviation-promote § 5` canonical shape, modified to embed `<surface>`):
   ```markdown
   - **<title-derived-from-what>** — what: <what>. why: <why>. impact: <impact>. surface: <env var / path / port / cron / "none">.
   ```
   Title derivation: pick first 6 words of `what=` capped at 60 chars, sentence-case.
8. Updates plan frontmatter: `Status: DRAFT|APPROVED` → `Status: EXECUTED`, adds `Shipped: <ISO-date> via PR #<N> squash <sha>` (PR # + sha inferred from `git log --grep=<plan-name> --oneline` over the last 14 days; ambiguous → STDOUT a "skipping Shipped: line — fill manually" warning instead of guessing).
9. `git mv docs/plans/<NN>-<slug>.md docs/plans/archive/<NN>-<slug>.md`. Same for the matching prompt file under `docs/prompts/` (if it exists) — the prompt archive convention is part of the contract.
10. Appends one line to `traces/<run-id>/manager.log` (write-through; respects single-writer rule since this command runs in manager's session, not via the dispatcher's memory or gh groups):
    ```
    [ISO-ts] ARCHIVE plan=<NN> path=<docs/plans/archive/<NN>-<slug>.md> status=EXECUTED deviations=<n>_promoted surfaces=<n>_flagged
    ```

### D. Code sketches

#### D.1 `.claude/naavik_ops/plan.py`

```python
"""plan — plan-lifecycle ops (archive, validate-deviations).

Subcommands:

  archive <plan-path> [--run-id <id>] [--accept-existing-section]
                     [--no-material-deviations "<rationale>"]
                     [--allow-multi-run] [--dry-run]
      Promote engineer-deviations.log entries into the plan's
      `## Deviations from plan` section, then `git mv` to archive.
      Refuses if section ends up empty (no entries + no override).

  validate-deviations <plan-path>
      Read-only: confirm the active plan has a non-empty section.
      Wraps the naavik-deviations-check skill's binary contract.
      Exit 0 = PASS, 2 = BLOCK.

The `plan` group is the canonical, single-writer entry point for any
`docs/plans/<NN>-...md` → `docs/plans/archive/<NN>-...md` move that the
manager performs at operating-loop step 11 (post-merge bookkeeping).
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from naavik_ops.lib import NaavikOpsError, deviations

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = REPO_ROOT / "docs" / "plans"
ARCHIVE_DIR = PLANS_DIR / "archive"
PROMPTS_DIR = REPO_ROOT / "docs" / "prompts"
PROMPTS_ARCHIVE_DIR = PROMPTS_DIR / "archive"
TRACES_DIR = REPO_ROOT / "traces"

_FRONTMATTER_STATUS_RE = re.compile(r"^Status:\s*(DRAFT|APPROVED|EXECUTED|GRADUATED)", re.M)
_DEVIATIONS_HEADING_RE = re.compile(r"^## Deviations from plan\s*$", re.M)


def cmd_archive(argv: Sequence[str]) -> int:
    args = _parse_archive_args(argv)
    plan_path = _resolve_plan_path(args.plan)
    _check_already_archived(plan_path)

    run_id = args.run_id or _pick_latest_run_id()
    log_paths = _resolve_log_paths(run_id, args.allow_multi_run)

    entries = deviations.parse_log_entries(log_paths, plan_path)

    if args.no_material_deviations:
        bullets = [deviations.no_material_bullet(args.no_material_deviations)]
    elif args.accept_existing_section:
        _verify_existing_section_nonempty(plan_path)
        bullets = []  # nothing to lift
    elif not entries:
        _emit_reconciliation_report(plan_path, run_id, log_paths)
        return 2
    else:
        bullets = [deviations.entry_to_bullet(e) for e in entries]

    if args.dry_run:
        _print_dry_run(plan_path, bullets, entries)
        return 0

    if bullets:
        _append_deviations_section(plan_path, bullets)
    _update_frontmatter(plan_path)
    _git_mv_plan_and_prompt(plan_path)

    surfaces = deviations.extract_surfaces(entries)
    _print_archive_summary(plan_path, len(bullets), surfaces)
    _append_manager_log(run_id, plan_path, len(bullets), len(surfaces))
    return 0


def cmd_validate_deviations(argv: Sequence[str]) -> int:
    # Read-only wrapper of the naavik-deviations-check binary contract.
    ...
```

#### D.2 `.claude/naavik_ops/lib/deviations.py`

```python
"""deviations — engineer-deviations.log line parser + bullet formatter.

One source-of-truth for the canonical log-line shape and the canonical
bullet shape, so engineer-deviation-log skill, manager-deviation-promote
skill, naavik-deviations-check skill, and `naavik-ops plan archive` all
agree on the format. Drift between the 3 skills + the command would
defeat the point of plan 39.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+DEVIATION\s+"
    r"plan=(?P<plan>\S+)\s+"
    r"what=(?P<what>.+?)\s+"
    r"why=(?P<why>.+?)\s+"
    r"impact=(?P<impact>.+?)\s*$"
)

# Quoted variants (engineer logs sometimes wrap fields in single or double quotes —
# the canonical format is unquoted but the parser accepts both):
_LINE_RE_QUOTED = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+DEVIATION\s+"
    r"plan=(?P<plan>\S+)\s+"
    r"""what=["'](?P<what>[^"']+)["']\s+"""
    r"""why=["'](?P<why>[^"']+)["']\s+"""
    r"""impact=["'](?P<impact>[^"']+)["']\s*$"""
)

_SURFACE_KEYWORDS = {
    "env var": "env",
    "environment variable": "env",
    ".env": "env",
    "on-disk path": "path",
    "~/.naavik/": "path",
    "mode 0600": "path",
    "port ": "port",
    "cron": "schedule",
    "schedule": "schedule",
    "APScheduler": "schedule",
    "secret-handling": "secret",
}


@dataclass(frozen=True)
class Entry:
    timestamp: str
    plan: str
    what: str
    why: str
    impact: str

    @property
    def surface(self) -> str:
        impact_lower = self.impact.lower()
        for keyword, surface_type in _SURFACE_KEYWORDS.items():
            if keyword.lower() in impact_lower:
                return f"{surface_type}: {self._extract_surface_phrase(keyword)}"
        return "none"


def parse_log_entries(log_paths: Iterable[Path], plan_path: Path) -> list[Entry]:
    """Read every log path, return entries whose plan= matches the target."""
    rel = _to_repo_rel(plan_path)
    out: list[Entry] = []
    for p in log_paths:
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            m = _LINE_RE.match(line) or _LINE_RE_QUOTED.match(line)
            if not m:
                continue
            if _plan_matches(m.group("plan"), rel):
                out.append(Entry(...))
    return out


def entry_to_bullet(e: Entry) -> str:
    title = _derive_title(e.what)
    return (
        f"- **{title}** — what: {e.what}. why: {e.why}. "
        f"impact: {e.impact}. surface: {e.surface}."
    )


def no_material_bullet(rationale: str) -> str:
    return f"No material deviations — {rationale}."


def extract_surfaces(entries: Iterable[Entry]) -> list[str]:
    return [e.surface for e in entries if e.surface != "none"]
```

#### D.3 Skill body edits (verbatim diff shape)

`engineer-deviation-log/SKILL.md` § Steps adds a new step 6:

```markdown
6. **Hand-back contract** (codified plan 39). Engineer's final hand-back to manager
   MUST include a `Deviations summary: <bullet list or "none — reconciled against
   diff">` line. Missing this line is what triggered the 5-of-8 archive miss in run
   `2026-05-19T15-42-42_833f4a`. Manager's PR_REVIEW_GATE surface checks for this
   line before dispatching `naavik-ops plan archive` at step 11.
```

`manager-deviation-promote/SKILL.md` § Steps step 4 changes from "Open `docs/plans/NN-name.md`. Append section." to:

```markdown
4. **Invoke `naavik-ops plan archive`.** This is the canonical surface — the command
   does the lift + the `git mv` + the propagation-surfaces report in one atomic op.
   Use `--accept-existing-section` only if the section was already authored by hand
   (rare); use `--no-material-deviations "<rationale>"` only when certain (skepticism).

   Worked example:
   ```
   .claude/naavik-ops plan archive docs/plans/39-deviation-promotion-hardening.md
   ```
   Command exits 0 on success + STDOUTs a `Surface propagation required:` block.
   Land the propagation edits in the same bookkeeping commit per PLAYBOOK § I.
```

`naavik-deviations-check/SKILL.md` § Step 2 changes the bash invocation:

```markdown
### 2 — Confirm `## Deviations from plan` section exists

```bash
.claude/naavik-ops plan validate-deviations docs/plans/<NN-name>.md
```

Exit 0 = PASS; exit 2 = BLOCK. Wraps the binary contract; manager invokes this
directly instead of grepping.
```

### E. Build sequence

1. **Wave 1 — Library + tests.** Author `naavik_ops/lib/deviations.py` (parser, bullet formatter, surface extractor) + `tests/test_naavik_ops/test_deviations_lib.py` with: parses canonical line; parses quoted line; rejects malformed; surface detection across `env var` / `path` / `cron` / `port` / `secret` / `none`; entry-to-bullet shape matches `manager-deviation-promote § 5`. Target: ≥ 15 tests.
2. **Wave 2 — `plan archive` command + tests.** Author `naavik_ops/plan.py` with `cmd_archive` + `cmd_validate_deviations`. Register `plan` group in `cli.py:GROUPS`. Tests in `test_plan.py`: happy path; reconciliation-needed (empty log + diff present); --no-material-deviations; --accept-existing-section; --allow-multi-run; --dry-run; already-archived guard; ambiguous --run-id; existing `## Deviations from plan` section append vs create.
3. **Wave 3 — Skill body edits.** Apply the three skill diffs from § D.3.
4. **Wave 4 — Prompt + doc edits.** Manager prompt step 11 + engineer prompt § Deviation tracking + AGENTS.md § Workflow step 7 + step 8 + CLAUDE.md + PLAYBOOK § I + AGENT_OPS § 2.7a. Single coherent commit each (or one bigger commit with reviewer-friendly grouping).
5. **Wave 5 — CI lint.** `tests/test_no_manual_plan_archive_moves.py` — scans last 30 days of `git log --diff-filter=R --follow docs/plans/`, fails if a renamed plan move into `docs/plans/archive/` has commit message NOT containing `naavik-ops plan archive` invocation marker.
6. **Wave 6 — Self-test.** Manager runs the new command against plan 39 itself as the first archive consumer post-merge — eats own dogfood.

### F. Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| F.1 Engineer log parser too strict — rejects lines that were valid in this run | MEDIUM | breaks archive flow on plans that did log | Parser accepts BOTH canonical unquoted format AND single/double-quoted format (see `_LINE_RE` + `_LINE_RE_QUOTED` in D.2; the in-flight log already mixes both, e.g. plan 38 uses single quotes). Run a one-off `naavik-ops plan archive --dry-run` against every active + recent archived plan as part of Wave 6 to surface parse failures BEFORE first production use. |
| F.2 `--no-material-deviations` bypass surface gets abused | LOW | quiet drift back to current state | (i) mandatory one-line rationale string, no default value; (ii) `naavik-deviations-check` skill body adds a skepticism check: "if the merge diff touched >5 LOC in any file the plan named, --no-material-deviations is suspect"; (iii) any plan archived this way gets flagged on the next `/learn` retrospective. |
| F.3 `git log --grep=<plan-name>` for Shipped-line auto-fill is fragile | LOW | wrong PR # or SHA in frontmatter | Ambiguous match → STDOUT a warning + skip the Shipped: line. Manager fills manually. Never guess — the cost of a wrong PR # in archive frontmatter outweighs the convenience of auto-fill. |
| F.4 The `plan` group module collides naming-wise with the `naavik-ops task` group (both lifecycle-ish) | LOW | confused operator surface | `task` is task-id (4-level semver) operations; `plan` is plan-file (`docs/plans/NN-...md`) operations. Clearly different. AGENT_OPS § 2.7a docstring rewrites the group list to disambiguate. |
| F.5 Cross-run plan execution (rare but seen: plan 24/A.29 spanned 2 runs) | MEDIUM | `--allow-multi-run` is bypass surface OR command refuses needlessly | Refuses by default (safer) with explicit STDOUT line listing the N runs detected. Manager opts in with `--allow-multi-run` after checking the runs are coherent (same epic, same plan, same engineer). |
| F.6 The CI lint (`test_no_manual_plan_archive_moves.py`) false-positives on the retrofit commit `29f859d` | HIGH | builds break immediately | Lint scans commits AFTER plan 39 lands (filter: `git log --since=<plan-39-merge-date>`). Pre-39 archive moves are grandfathered. |
| F.7 The new command runs `git mv` and the working tree has unrelated dirty changes | MEDIUM | confusing partial commits | Command refuses if `git diff --name-only --staged` shows >0 staged paths OR if the plan file or any propagation target appears in `git diff --name-only HEAD`. Manager stashes first. |
| F.8 plan path validation accepts `docs/plans/archive/...` as input (already archived) | LOW | command runs against archived plan | `_check_already_archived` guard reads frontmatter `Status:`; rejects if already `EXECUTED`. |
| F.9 The new ROADMAP row this plan introduces (Phase A "A.32" or similar) needs a GH Issue | LOW | mirror drift | During implementation, run `.claude/naavik-ops gh create-issue A.32 "Deviation-promotion hardening" --priority HIGH --milestone "Phase A"` after the ROADMAP row lands. Standard single-writer rule. |

### G. Migration of existing retrofit

Commit `29f859d` already populated `## Deviations from plan` for plans 30, 31, 32, 33, 35, 37 retroactively. Plans 34, 36 had populated sections at archive time. Plan 38 archives in the next `/build` — and will be the first consumer of `naavik-ops plan archive`.

**No back-migration required.** Plan 39 is forward-looking. The retrofit commit's content is what the new command would have produced anyway; lint exemption (F.6) lets it remain as-is.

### H. Test plan

| Test                                                  | What it asserts                                                                                                  | File                                              |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `test_parse_canonical_unquoted_line`                  | `_LINE_RE` matches the format the skill body documents                                                           | `test_deviations_lib.py`                          |
| `test_parse_quoted_line_single_and_double`            | `_LINE_RE_QUOTED` accepts both `what="..."` and `what='...'`                                                     | `test_deviations_lib.py`                          |
| `test_parse_rejects_malformed`                        | non-DEVIATION lines + missing fields don't match                                                                 | `test_deviations_lib.py`                          |
| `test_plan_match_path_normalization`                  | parser handles `docs/plans/N-...md` AND repo-absolute paths                                                      | `test_deviations_lib.py`                          |
| `test_surface_detection_env_path_port_cron_secret`    | every keyword in `_SURFACE_KEYWORDS` triggers correct surface; absence → "none"                                  | `test_deviations_lib.py`                          |
| `test_entry_to_bullet_shape`                          | bullet matches `manager-deviation-promote § 5` shape verbatim                                                    | `test_deviations_lib.py`                          |
| `test_archive_happy_path_lifts_3_entries`             | 3 log lines for one plan → 3 bullets + git mv + frontmatter flip                                                 | `test_plan.py`                                    |
| `test_archive_refuses_empty_log_no_override`          | 0 matching entries, no flags → exit 2 + `RECONCILIATION_NEEDED` summary                                          | `test_plan.py`                                    |
| `test_archive_no_material_deviations_writes_one_bullet`| `--no-material-deviations "X"` → single-bullet section + archive                                                 | `test_plan.py`                                    |
| `test_archive_accept_existing_section_when_present`   | manual section pre-authored → skip lift, archive                                                                 | `test_plan.py`                                    |
| `test_archive_accept_existing_section_refuses_empty`  | manual section EMPTY → exit 2                                                                                    | `test_plan.py`                                    |
| `test_archive_refuses_already_archived`               | input is `docs/plans/archive/NN-...md` OR frontmatter is `EXECUTED` → exit 2                                     | `test_plan.py`                                    |
| `test_archive_multi_run_refuses_without_flag`         | log entries in 2 runs → exit 2 + listing                                                                          | `test_plan.py`                                    |
| `test_archive_multi_run_allow_consumes_both`          | `--allow-multi-run` → entries from both runs merge chronologically                                                | `test_plan.py`                                    |
| `test_archive_dry_run_no_writes`                      | `--dry-run` → no file changes, no git ops                                                                         | `test_plan.py`                                    |
| `test_archive_refuses_dirty_working_tree`             | uncommitted changes → exit 1                                                                                      | `test_plan.py`                                    |
| `test_archive_moves_matching_prompt_too`              | `docs/prompts/NN-...md` if present → moved to `docs/prompts/archive/`                                             | `test_plan.py`                                    |
| `test_archive_appends_manager_log`                    | `traces/<run-id>/manager.log` gets the `ARCHIVE plan=...` line                                                    | `test_plan.py`                                    |
| `test_validate_deviations_exit_0_when_section_nonempty` | wraps the binary contract                                                                                       | `test_plan.py`                                    |
| `test_no_manual_plan_archive_moves_lint`              | scans `git log --diff-filter=R --follow docs/plans/` since 39 merged; fails if any rename commit lacks the command marker | `test_no_manual_plan_archive_moves.py`            |

Target: 20 tests; ≥ 90% coverage on `plan.py` + `lib/deviations.py`.

### I. Wave-gate exit criteria

- **Wave 1 exit:** `pytest tests/test_naavik_ops/test_deviations_lib.py -x` green. Parser handles canonical + quoted; surface detection covers all 5 categories.
- **Wave 2 exit:** `pytest tests/test_naavik_ops/test_plan.py -x` green. Dry-run end-to-end against plan 38 (active, in-flight) succeeds.
- **Wave 3 exit:** all 3 skill bodies edited. `grep -r 'git mv docs/plans' .claude/skills/` returns zero results (skills no longer document the bypass path).
- **Wave 4 exit:** all 6 doc files updated. `grep -n 'naavik-ops plan archive' AGENTS.md CLAUDE.md docs/PLAYBOOK.md docs/AGENT_OPS.md` returns ≥ 1 match each.
- **Wave 5 exit:** lint test passes on current main.
- **Wave 6 exit:** plan 39 itself archives via the new command (eat dog food). Manager log shows the `ARCHIVE` line.

## Open questions

(none — defaults locked per zoom-through brief; all decisions explicitly stated in § A.1 / A.2 / A.3 + § F)

## Approval checklist

- [ ] Lock § A.1 recommendation: build the `naavik-ops plan archive` subcommand (option b). Reject (a) pure prompt enforcement (already failed) and (c) pre-commit hook (deferred to A.32a if 39 proves insufficient).
- [ ] Lock § A.2 recommendation: tighten engineer hand-back to require a `Deviations summary:` line. No mandatory hook.
- [ ] Lock § A.3 manager UX: 3 outcomes (happy path / reconciliation-needed exit 2 / --no-material-deviations explicit flag). `--accept-existing-section` for manually-authored sections.
- [ ] Confirm command name + group: `naavik-ops plan archive` (new `plan` group under the dispatcher).
- [ ] Confirm new ROADMAP row: file as `A.32` (or next available Phase A row); priority HIGH; milestone "Phase A".
- [ ] Confirm forward-only CI lint (§ F.6) — pre-39 archive moves are grandfathered.
- [ ] Confirm self-archive (§ I Wave 6) — plan 39 is the first consumer of its own command.

## Deviations from plan

- **`lib/deviations.py` module NOT extracted; parser +** — what: `lib/deviations.py` module NOT extracted; parser + bullet formatter + surface detector inlined in `.claude/naavik_ops/plan.py` why: locked dispatch decisions narrowed required new files to `plan.py` + `test_plan.py` only; lib module would duplicate parser shape with zero reuse callers in this PR impact: future plan that consumes the parser elsewhere can extract it then; current 16 SURFACE_PATTERNS + DEVIATION line regex live in plan.py. Internal-only; no operator surface. surface: none.
- **CI lint `tests/test_no_manual_plan_archive_moves.py` NOT...** — what: CI lint `tests/test_no_manual_plan_archive_moves.py` NOT shipped why: locked dispatch decisions enumerated 6+ unit tests for `test_plan.py`; the F.6 forward-only commit-history lint was scope-reduced to keep PR surface tight impact: manual `git mv docs/plans/<NN>...md docs/plans/archive/` remains physically possible but is FORBIDDEN by AGENTS.md § Workflow step 7, CLAUDE.md § Deviations workflow, and docs/PLAYBOOK.md § I BOOKKEEPING. Defer the belt-and-suspenders lint to a follow-up row if drift re-emerges after the next 5 archives. surface: none.
- **`--allow-multi-run` and `--accept-existing-section` flags...** — what: `--allow-multi-run` and `--accept-existing-section` flags NOT shipped; collapsed to single `--force` flag why: locked dispatch decisions specified the smaller flag surface (`--no-material-deviations`, `--force`, `--run-id`, `--dry-run`); --force already covers the `--accept-existing-section` semantics; multi-run reconciliation deferred until a real cross-run plan archive needs it impact: Cross-run plan archives (rare: plan 24/A.29 spanned 2 runs) still require manager to pick one --run-id explicitly. Plan 39 deviations section will note this; follow-up row added if encountered. surface: none.
- **22 unit tests in test_plan.py covering** — what: 22 unit tests in test_plan.py covering happy / empty-log refusal / --no-material-deviations / --force / --run-id override / --dry-run / already-archived / prompt-archive / quoted-log / surface-detection / validate-deviations / title-derivation why: locked decisions called for 6+ tests; comprehensive coverage produced naturally from corner cases of the parser and refusal-path logic impact: None — exceeds spec floor; no operator surface. surface: none.
- **ROADMAP row filed as `0.7.0.21` (not** — what: ROADMAP row filed as `0.7.0.21` (not `A.32` as the original plan body suggested) why: next free 0.7.0 slot is .21 (`.20` was just consumed by parallel-reviewer invariant codification, A.38). Plan frontmatter says `Implements: ROADMAP row 0.7.0.21` matching this. impact: row already in ROADMAP § Phase A under 0.7.0.21 with HIGH priority; GitHub Issue #119 paired with the plan. surface: none.
