---
Status: DRAFT
Type: design
Authored: 2026-05-19
Last updated: 2026-05-19
Depends on: 39-deviation-promotion-hardening (in flight as PR `0.7.0.21`); 40-roadmap-backlog-section (DRAFT). Does NOT block any 0.2.0 row.
GitHub: (to file at 0.7.0.22 on PLAN_GATE approval)
---

# 41 · Manager evolution + token-based model selection + bookkeeping fold-in + workflow-invariant lints

## Goal

Bundle five interrelated process changes the user surfaced during the `2026-05-19T15-42-42_833f4a` run into one plan, sequenced post-`0.2.0` close: (a) expand the manager's lane to include staff-engineer-level coding for small CONTRACT_CHANGE work (≤2 files, ≤100 LOC, no design ambiguity); (b) introduce token-budget-based model selection so the manager dispatches at `opus` for sub-threshold work and `opus-1m` only when the dispatch genuinely needs the 1M context window; (c) revise the BOOKKEEPING / CONTRACT_CHANGE boundary so post-merge bookkeeping AND user manual edits fold into the active PR's commit chain instead of fragmenting into 14+ stranded direct-push commits per cycle; (d) add a `tests/test_workflow_invariants/` suite that lints recurring workflow violations at commit time instead of burning agent tokens at PR review; (e) sequence the implementation so manager scope expansion + fold-in rule + lint suite ship together (they're one cognitive unit) while model-twin agents ship separately (independent risk).

## Why

The run that produced this plan exposed five paper cuts that share a root cause: process invariants live only in agent prompts + the PLAYBOOK, where they require an active agent reading + interpreting the text to fire. When the agent's attention is split (zoom-through mode, late-session token pressure), invariants miss. The fixes have to move the enforcement out of prompts:

- **Parallel reviewer invariant** violated twice in one run despite living in `manager.md § Parallel reviewer invariant` + `PLAYBOOK § F step 9` + `§ H step 7` + `§ D step 3` (PR #99 codified hard-stop). Same shape: text-only rule, attention-dependent.
- **Deviations section gate** failed 5/8 archived plans in this run despite the agent prompts requiring it. Plan 39 / `0.7.0.21` (currently in flight on this same branch) moves enforcement from prompt → `naavik-ops plan archive` exit-2 hard-stop. Same pattern: code beats prose.
- **Bookkeeping fragmentation.** 14+ post-merge `docs(roadmap):` commits since `0.1.1` (PR #91), each one a direct push to `main`. Per current PLAYBOOK § H + § I, this is correct. Per the user directive that motivated this plan, this is wasteful — those commits are tightly coupled to their PRs, and squashing them into the PR commit would (i) collapse ~14 main commits into ~6, (ii) make the roadmap mark-done atomic with the PR squash, (iii) eliminate the "bookkeeping commit lands AFTER the PR but BEFORE git push is sandbox-denied" failure-mode logged at `[2026-05-19T16:39:28Z]` in this run's manager log.
- **Manager-as-orchestrator-only.** `.claude/agents/manager.md:9` says *"You never write production code yourself"* + Anti-patterns line 289 *"Write production code yourself. You orchestrate; you don't implement."* This was correct when manager was opus-4-1; it's wasteful when manager is opus-4-7 + the work is a 30-LOC text fix to a skill body. Currently the manager dispatches engineer for changes the manager could ship in 2 minutes — burning ~150-200K engineer tokens per round-trip. Plan 39 (the *enclosing* PR for this branch) is itself an instance of this — every line of `cli.py:plan` was authored via engineer dispatch when manager could have written it inline. Manager-as-staff-engineer is the right shape **for small CONTRACT_CHANGE work**, with the hacker+architect parallel review at PR_REVIEW_GATE intact as the protection.
- **Token-budget calibration.** All 6 agents are pinned at `claude-opus-4-7[1m]` (frontmatter line 5 of each `.claude/agents/*.md`). The `[1m]` 1M-context variant carries a higher per-token cost than the standard 200K Opus. For this run's 22 architect dispatches (median ~130K tokens), 15 used <200K context AND <60K dispatch input — `[1m]` was wasted spend. For 4 engineer dispatches that loaded the full `0.2.0.05`/`0.2.0.07` plan + ARCHITECTURE.md + DATA_MODEL.md + 12 service files (~280K tokens cumulative), `[1m]` was load-bearing. The user-stated threshold (50K) is too tight for typical work; this plan recommends 60K w/ data justification + offers a 75K alternative for tighter cost control.

ROADMAP row: this plan files at `0.7.0.22` (next free 0.7.0 position after `0.7.0.21`'s `[~]`). Priority MEDIUM. Depends on `0.7.0.21` (the `naavik-ops plan archive` infrastructure) shipping first — this plan's lint suite reads logs the archive command produces.

## Proposal

Eight design decisions (D.1–D.8) and five open questions (OQ.1–OQ.5) below. Each carries an option matrix where alternatives exist; locked decisions inherit user-direction or the user-stated "zoom-through mode" preference. Wave sequence appears in § Build sequence.

### D.1 — Manager scope expansion: boundary definition

The current line — *"You never write production code yourself"* — is unconditionally restrictive. The user wants manager-as-staff-engineer for small bounded work. The boundary needs explicit numeric edges so manager doesn't have to judge case-by-case (judgment is the failure surface from PR #99's parallel-reviewer miss + PR #39's deviation-section miss).

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. Numeric edges: ≤2 files OR ≤100 LOC AND no new dependency AND no new design contract AND no security-sensitive surface (auth / secrets / migrations / scrapers)** (LOCKED) | Mechanical "yes/no" before manager picks up the pen; no judgment surface | Two-axis check (file count AND line count); manager has to count | Low — clear edges; falls through to engineer on any ambiguity | Low — edges are numbers, not qualitative | Low |
| B. Qualitative: "well-bounded scope, manager confident" | Maximally flexible | Identical to current "manager judges parallel reviewer dispatch" — judgment surface is the failure mode | High — repeats the PR #99 failure pattern at a new surface | Medium | Medium |
| C. List-based: explicit allowlist of "manager may ship X" (skill body tightening / agent-prompt single-line fix / ROADMAP "Last updated" + Notes only / new ROADMAP follow-up row) | Mechanically checkable; familiar (mirrors BOOKKEEPING allow-list shape) | Allowlist diverges from real-world need; every new "small task type" requires PLAYBOOK PR | Medium — drift between allowlist + reality | Medium | Medium |

**Lock: A.** Numeric edges with explicit fall-throughs. The boundary check is:

```
if (files_changed <= 2
    AND lines_changed <= 100
    AND no new dependency in pyproject.toml / nix/package.nix
    AND no new design contract (component / route / data model / interaction / on-disk path / env var / schema)
    AND no security surface (auth / secrets / migrations / scrapers / ATS adapters / LLM prompts / vault)
    AND not a UI mockup or new UI screen):
    manager codes inline
else:
    dispatch engineer
```

Manager-authored code still goes through `hacker + architect` parallel review at PR_REVIEW_GATE — the existing protection stays intact. Manager opens the PR; reviewer pair runs on the diff regardless of who authored it.

### D.2 — Manager.md prompt rewrites

Three lines need surgery:

| File:Line | Current | New |
|---|---|---|
| `.claude/agents/manager.md:9` | `"You + user share one workspace. You receive milestones, not step-by-step instructions, + execute them end-to-end by dispatching specialist agents. You never write production code yourself."` | `"You + user share one workspace. You receive milestones, not step-by-step instructions, + execute them end-to-end. For work matching § Manager coding boundary, you code inline (staff-engineer-level). Else you dispatch specialist agents."` |
| `.claude/agents/manager.md:289` (Anti-patterns) | `"Write production code yourself. You orchestrate; you don't implement."` | `"Code outside § Manager coding boundary. Files ≤ 2 + LOC ≤ 100 + no new dep + no design contract + no security surface = manager's lane. Anything else: dispatch engineer."` |
| New § Manager coding boundary (insert between § Identity invariant and § Parallel reviewer invariant) | n/a | Full text of D.1 boundary check; cite this plan + the `tests/test_workflow_invariants/test_manager_scope.py` lint that catches violations after-the-fact. |

New § Manager coding boundary section text (canonical):

```markdown
# Manager coding boundary

Per `docs/plans/archive/41-manager-evolution-+-model-selection-+-fold-in.md § D.1` (assumes plan executed; if still active, swap path).

You code inline when ALL of:
- `files_changed <= 2` (in the working diff for this CONTRACT_CHANGE)
- `lines_changed <= 100` (added + removed)
- no new entry in `pyproject.toml`, `nix/package.nix`, `flake.nix`, or `uv.lock`
- no new design contract — no new component partial, no new route, no new data model field/table/enum, no new interaction pattern, no new on-disk path, no new env var, no new DB schema (no Alembic migration)
- no security surface touched — no edit to `src/api/auth.py`, `src/services/auth.py`, `src/services/vault.py` (sunset), `src/services/env_secrets.py`, anything under `src/scraper/`, anything under `src/ats/`, anything under `src/llm/prompts/`, anything under `migrations/`
- no UI mockup or new UI screen (existing screen tweaks ≤ 2 files are fine if no new component)

Dispatch engineer when ANY of the above is false. Borderline calls round DOWN to "dispatch engineer" — judgment is the failure surface.

Manager-authored code still goes through `hacker + architect` parallel review at PR_REVIEW_GATE per § Parallel reviewer invariant. Same diff, same reviewers, same gate. Manager opens the PR; reviewer pair runs on the diff regardless of authorship. Manager NEVER self-approves their own PR.
```

### D.3 — Token-based model selection mechanism

Claude Code's Task tool accepts `model` as an enum: `sonnet | opus | haiku` (per [code.claude.com/docs/en/sub-agents](https://code.claude.com/docs/en/sub-agents) + [GitHub issue #34821](https://github.com/anthropics/claude-code/issues/34821) confirming "no custom model aliases" — closed as not planned). The `[1m]` 1M-context variant is a SEPARATE configuration that lives in the subagent's frontmatter `model:` line — NOT a Task-call-time override. This shapes the available options:

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. Model-twin agents: `.claude/agents/architect.md` (default, `claude-opus-4-7`) + `.claude/agents/architect-1m.md` (1M ctx, `claude-opus-4-7[1m]`); manager picks via `subagent_type` at dispatch** (LOCKED) | Manager decides per-dispatch by token estimate; cost saved on small dispatches; agent prompts identical except for the model line | Doubles the agent file count (12 instead of 6); maintenance burden on cross-agent edits (one fix → two files); subagent type list grows | Medium — twin drift if maintainer forgets to edit both | Medium — every prompt fix needs both edits | Low |
| B. Single agent file w/ runtime-selectable model | Claude Code's Task tool does NOT support frontmatter-override at dispatch (per issue #34821). Not viable. | n/a | n/a | n/a | n/a |
| C. Keep all agents at `[1m]` baseline; rely on Anthropic's 1M-context cost graduation (charge only for what's consumed) | No new files; status quo cost is what it is | The `[1m]` variant carries a different per-token base cost regardless of consumption (per Anthropic pricing); status quo wastes spend on small dispatches | Low | None | Low |
| D. Twin agents but only for the two highest-volume dispatchees (architect + engineer); hacker/devops/designer stay `[1m]` | Pareto: 80% of token savings for 33% of the file-count cost | Asymmetric agent surface; manager has to remember which agents have twins | Low — twin maintenance burden halved | Medium | Low |

**Lock: D.** Twin agents for `architect` + `engineer` only (the two with the widest token-spend distribution this run: architect 38K-260K, engineer 95K-391K). Hacker / devops / designer stay `[1m]` baseline — their dispatches cluster tighter (hacker 36-222K, devops typically <100K, designer <50K) + their workload is more uniform. New files: `.claude/agents/architect-1m.md` + `.claude/agents/engineer-1m.md`. Body of each identical to its sibling save for the `model:` line (`claude-opus-4-7[1m]`). Manager picks `subagent_type` by token estimate per D.4.

This is reversible — if 6 months from now Anthropic ships the requested custom-alias feature (issue #34821), collapse the twins back to single files. Until then, file-doubling is the cheapest correct mechanism.

### D.4 — Token threshold for model selection

The user proposed 50K. Empirical data from this run's 30+ dispatches:

| Agent | Dispatch count | Min (K) | Median (K) | Max (K) | % under 50K | % under 60K | % under 75K |
|---|---|---|---|---|---|---|---|
| architect | 22 (incl. plan-author + PR-review variants) | 38 | 130 | 260 | 18% | 27% | 50% |
| engineer | 4 (full PR cycles) | 95 | 210 | 391 | 0% | 0% | 0% |
| hacker | 8 (review-only) | 36 | 130 | 222 | 25% | 38% | 63% |

(Source: `traces/2026-05-19T15-42-42_833f4a/*.log` token return lines; sample is one-run + skewed toward zoom-through mode work — engineer dispatches in this run were unusually large because they bundled `0.2.0.06a` + `0.2.0.07` scope.)

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| A. 50K (user-stated) | Maximally aggressive; saves the most on small architect-delta reviews + hacker re-reviews | Engineer NEVER triggers (median 210K); fewer architect-plan dispatches qualify; 18% architect coverage feels light | Low | None | Low |
| **B. 60K (recommended)** (LOCKED) | Catches the 27% architect-delta + 38% hacker-delta cluster (low-hanging fruit) while leaving engineer + architect-plan-author dispatches on `[1m]`. Conservative move; can tighten to 50K after a cycle's data. | Slightly lower savings than A; doesn't reach the 50% architect-mark at 75K | Low — easy to revisit | None | Low |
| C. 75K | Catches half of architect dispatches + most hacker re-reviews | Risk: occasional `[1m]`→`opus` dispatch needs the bigger context (e.g., a plan-review that re-reads the full plan + ARCHITECTURE.md + design doc spikes past 75K's headroom on the 200K ceiling, leaving little room for reasoning); near-the-edge dispatches will start to truncate or 503 | Medium — false negatives (dispatch picks `opus` then gets cut off, retries on `[1m]`, net-cost-up) | Medium | Low |
| D. Dynamic (manager estimates per-dispatch context size from RUN_ID + plan paths + design-doc paths + caller history) | Maximally adaptive | Estimation requires a model + state; new failure surface | High | High | Medium |

**Lock: B (60K)** with a 0.7.0.NN-style follow-up row to revisit the threshold after one full milestone of telemetry. Threshold expressed as `MANAGER_MODEL_THRESHOLD_TOKENS = 60_000` in manager.md (citable by the lint test).

### D.5 — Manager's per-dispatch estimation heuristic

Manager has to decide between `architect` vs `architect-1m` (and same for `engineer`) at the Task dispatch moment. It does NOT know the runtime tokens-consumed — that's a post-hoc number. It MUST estimate from inputs.

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. Sum-of-pre-reads heuristic: `est = sum(line_counts of all paths in CONTEXT/REQUIRED_READING) * 8 tokens/line + 2K dispatch-prompt overhead`. If est < 60K → `subagent_type = architect`; else `architect-1m`.** (LOCKED) | Mechanical; manager already lists paths in the dispatch prompt; line counts are `wc -l`-cheap | First-order proxy; misses the agent's own dispatch-time reads beyond the listed required-reading | Low — falls back to `[1m]` on any uncertainty (conservative bias) | None | Low |
| B. Static lookup table by dispatch-type ("plan-author=1m, PR-review=opus, plan-revise=1m if iter>1, ...") | Most predictable; readable in dispatcher logic | Doesn't adapt to actual size variation between two plan-author dispatches; "plan-author" of a 10-line execution plan vs a 600-line design plan get the same model | Medium — misses the variance | Medium | Medium |
| C. User-confirmed at every dispatch | Maximally accurate | Adds a gate to every dispatch — destroys autonomous flow | High — every dispatch is a halt | Low | Low |

**Lock: A.** Sum-of-pre-reads heuristic. Manager emits one new line per dispatch in `manager.log`:

```
[ISO-timestamp] MODEL_PICK agent=architect est_tokens=<n> threshold=60000 subagent_type=<architect|architect-1m>
```

`devops-trace-manifest` reads these for the new "tokens estimated vs actual" delta in MANIFEST.json (optional follow-up, deferred to lint suite).

### D.6 — Bookkeeping fold-in rule

The user's directive: when a PR is open AND a BOOKKEEPING change would normally direct-push to `main`, fold it into a commit on the active PR's branch instead. The PR squash carries both. This DIRECTLY CONFLICTS with PLAYBOOK § H step 12 *"Single commit would touch BOTH H and I → split into separate commits / two PRs / one PR + one bookkeeping commit. Don't mix categories in one push."* The rule needs revision.

The revision uses TIMING as the discriminator (PR open vs PR closed), not category mixing per se. While a PR is OPEN, the active branch is the natural carrier for both H (the work) and I (the bookkeeping flowing from the work). When NO PR is open, BOOKKEEPING returns to direct-push-to-main per current § I.

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. Fold-while-PR-open: every BOOKKEEPING edit during an open PR lands as a commit on that PR's branch; on merge the PR squash carries both. No PR open → direct push to main per current § I.** (LOCKED) | Reduces main commits from ~14/cycle → ~6/cycle; atomic merges; eliminates "bookkeeping commit happened but the PR didn't" half-states | Reviewers see bookkeeping changes (roadmap marks) in the same PR diff as the work — slightly noisier; bookkeeping that lands LATE in the PR cycle requires a fresh commit + force-push avoidance (just commit + push to branch tip, no rebase) | Low | Low | Low |
| B. Status quo: always split | Reviewers see clean diff per PR; categories never mixed | 14+ commits/cycle to main; bookkeeping fragility; pattern observed this run | High operational drag | None | Low |
| C. Squash-time fold: PRE-merge, manager rebases the BOOKKEEPING commits from main onto the PR branch + squashes | Maximally tidy | Rebase against main = pull bookkeeping commits OFF main — destructive; not allowed under git safety protocol | High — rewrites main history | High | High |

**Lock: A.** Timing-based fold rule. Specifically:

- **PR open AND BOOKKEEPING edit relates to the PR's work** (e.g., archiving the PR's plan, marking ROADMAP row `[x]`, filing a follow-up row that emerged from the PR's review):
  → commit on the PR branch w/ `docs(roadmap): <change>` or `docs(archive): <change>` prefix. PR squash carries both.
- **PR open AND BOOKKEEPING edit is unrelated** (e.g., a different roadmap row + a different plan + a different milestone):
  → direct push to `main` per current § I. Don't fold cross-cutting bookkeeping.
- **No PR open AND BOOKKEEPING edit**:
  → direct push to `main` per current § I.
- **PR open AND user manual edit appears in working tree**:
  → ask user: *"This change relates to PR #N (foldable) | This change is unrelated to PR #N (direct push) | Skip this change"* via AskUserQuestion. Don't guess.
- **Exceptions that NEVER fold under any condition**:
  - gitignored files (`.env`, `.naavik/`, `traces/<run-id>/`)
  - security-sensitive content (`src/services/vault.py` — sunset but still has its own gate; secret-handling, API-key material in any form)
  - personal data (user's identity files, credential files)
  - `.claude/budget-ledger.json` (gitignored anyway)
  - `.claude/github-issue-map.json` (gitignored anyway)

PLAYBOOK revisions: § H step 12 strikes the "don't mix" prohibition; new § H step 12a + § I gain timing-based language. New worked example in § Worked example.

### D.7 — Workflow-invariant lint suite

New test directory `tests/test_workflow_invariants/` containing pytest modules that run as part of `uv run pytest`. These are CHEAP (read-only file scans, no DB, no LLM) + catch the patterns hacker/architect currently catch at PR review time. The lint suite shifts detection from "burns ~150K tokens at review" to "burns ~0.5s at commit + 0 tokens".

| Lint | Purpose | Mechanism | Cost |
|---|---|---|---|
| **`test_no_legacy_jobsource_imports.py` (already exists)** | Catches re-import of pre-`0.2.0.05` `JobSource.AUTOMATED` | grep-style scan | <100ms |
| **`test_parallel_reviewer_dispatch.py`** (NEW) | Catches sequential reviewer dispatch in `manager.log` for any PR_REVIEW dispatch | Scan latest run's manager.log for `DISPATCH agent=hacker` followed by `AGENT_RETURN agent=hacker` followed by `DISPATCH agent=architect` (with no intervening hacker+architect single-message dispatch) | <500ms |
| **`test_plan_deviations_section.py`** (NEW; complements `0.7.0.21`) | Catches archived plans missing `## Deviations from plan` section | `glob docs/plans/archive/**/*.md; assert each has the section heading + at least one bullet OR explicit "no material deviations" | <300ms |
| **`test_no_cli_extension.py`** (NEW) | Catches new files under `src/cli/` or new subcommands in `src/cli/__init__.py` | grep + diff against `main` baseline | <200ms |
| **`test_no_vault_imports.py` (already exists)** | Catches `from src.services.vault import ...` regression | grep-style | <100ms |
| **`test_bookkeeping_fold_in.py`** (NEW) | Catches "stranded" direct-push bookkeeping commits when an open PR existed at the same timestamp | `git log --pretty=format:"%H %at %s" + gh pr list --state open` cross-join | <2s |
| **`test_no_em_dashes_or_emojis_in_agent_prompts.py`** (NEW, soft) | Catches em dashes (—) + emojis in `.claude/agents/*.md` per AGENTS.md voice guideline | Unicode grep | <100ms |
| **`test_manager_scope_violations.py`** (NEW) | Catches manager-authored commits exceeding D.1 boundary | Walk commits where `git log --author=<manager-author-email>` AND `--shortstat` shows >2 files OR >100 LOC; fails CI if found | <1s |

All lints are advisory-by-default (`pytest.skip` if no relevant state) + hard-fail on real violations. Lint suite runs in `uv run pytest -x` so a CI fail is loud + visible.

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. All 6 new lints in `tests/test_workflow_invariants/`** (LOCKED) | Full coverage of recurring patterns; one home for "workflow lints" | ~2s added to `pytest -x` total | Low — read-only; no flakiness surface | Low | Low |
| B. Subset (parallel-reviewer + deviations + fold-in only — the 3 with empirical evidence this run) | Lower test-suite burden | Misses the cli + manager-scope + em-dash patterns that could fire next | Medium | Low | Low |
| C. Pre-commit-hook variant (`.claude/hooks/git/pre-commit`) | Catches at commit-time before push | Bypassed by `--no-verify`; not enforceable on PRs from forks | Medium | Low | Low |

**Lock: A** with **B's three checked first wave** (parallel-reviewer + deviations + fold-in — they have direct evidence this run), and the other three follow in wave 2. Don't ship a pre-commit hook variant (option C) — pytest is the single source of truth for "did we break the invariant" + Claude Code is the one running pytest before PR open.

### D.8 — Implementation sequencing

Five changes (D.1+D.2 manager scope; D.3+D.4+D.5 model selection; D.6 fold-in; D.7 lints; documentation cascade) — which ship together?

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| **A. Two PRs: (PR-1) manager scope + fold-in + lint suite together (one cognitive unit, all about manager evolution + workflow hardening); (PR-2) model-twin agents (architect-1m + engineer-1m + manager threshold logic) — independent risk surface, gets its own review focus** (LOCKED) | Smaller diffs per PR; clearer review surface; PR-1 can land + bake without PR-2's twin-drift maintenance risk | Two PRs vs one; coordination overhead | Low | Low | Low |
| B. One mega-PR | Atomic landing | Diff > 600 LOC mixing process + model + lint changes; review burden | Medium — reviewer fatigue masks real issues | Low | Medium |
| C. Three PRs (manager / fold-in / model + lints) | Maximally bite-sized | Triples coordination + PR cycle cost; manager-scope + fold-in are coupled (manager codes inline = fold-in matters more) | Medium | Low | Low |

**Lock: A.** Two PRs in sequence:

1. **PR-A (0.7.0.22)** — Manager evolution + fold-in + lint suite. Branch: `chore/0.7.0.22-manager-evolution`. Files: `manager.md` (D.2) + PLAYBOOK.md (D.6 + § H step 12 + worked example) + 6 new lint test files under `tests/test_workflow_invariants/` (D.7) + `engineer.md` (small section noting "manager codes inline for bounded work; you still own everything else" — clarity edit). Est diff: ~300-450 LOC.
2. **PR-B (0.7.0.23)** — Token-based model selection. Branch: `chore/0.7.0.23-model-selection-twins`. Files: `architect-1m.md` + `engineer-1m.md` (new) + `manager.md` § Dispatch grammar gains MODEL_PICK section (D.4 + D.5) + AGENT_OPS.md § Agent reference gains twin row + new follow-up row `0.7.0.NN` for "review threshold after 1 cycle of telemetry." Est diff: ~600-900 LOC (twin files are large; ~80% identical to siblings).

Sequencing: PR-A first (lower-risk, no model change); PR-B once PR-A is on `main` + at least one full milestone of telemetry has run under PR-A's lints (so we're not landing model changes blind to the new invariant data).

## Files in scope

When this plan executes — by PR:

**PR-A (manager evolution + fold-in + lints):**
- `.claude/agents/manager.md` — 3 line edits (D.2) + new § Manager coding boundary (~30 lines) + new MODEL_PICK trace event line (deferred to PR-B; placeholder note only)
- `.claude/agents/engineer.md` — small clarification (one paragraph: "manager codes inline for bounded work; you still own everything else") + reaffirmation of self-running build gates
- `docs/PLAYBOOK.md § H step 12` — strike "don't mix" → revise per D.6 timing-based language
- `docs/PLAYBOOK.md § I` — add "no PR open" precondition + exceptions list per D.6
- `docs/PLAYBOOK.md § Worked example` — new fold-in case
- `tests/test_workflow_invariants/__init__.py` (new, empty)
- `tests/test_workflow_invariants/test_parallel_reviewer_dispatch.py` (new, ~80 LOC)
- `tests/test_workflow_invariants/test_plan_deviations_section.py` (new, ~60 LOC; complements `0.7.0.21`'s in-archive enforcement)
- `tests/test_workflow_invariants/test_bookkeeping_fold_in.py` (new, ~120 LOC; uses `git log` + `gh pr list`)
- `tests/test_workflow_invariants/test_no_cli_extension.py` (new, ~40 LOC; complements vault sunset guard)
- `tests/test_workflow_invariants/test_no_em_dashes_or_emojis_in_agent_prompts.py` (new, ~30 LOC)
- `tests/test_workflow_invariants/test_manager_scope_violations.py` (new, ~70 LOC)
- `docs/AGENT_OPS.md § 7.2` — append MODEL_PICK event format spec (deferred to PR-B but stub line)
- `ROADMAP.md` — `0.7.0.22` row flip `[ ]` → `[~]` on dispatch + `[x]` + "Last updated" on archive
- `AGENTS.md § Workflow` — light touch in step 8 (Archive) noting fold-in compatibility w/ `naavik-ops plan archive`

**PR-B (model selection twins):**
- `.claude/agents/architect-1m.md` (new) — full body of architect.md w/ `model: claude-opus-4-7[1m]` only diff
- `.claude/agents/engineer-1m.md` (new) — same shape as engineer.md
- `.claude/agents/architect.md` — `model:` line `claude-opus-4-7[1m]` → `claude-opus-4-7`
- `.claude/agents/engineer.md` — `model:` line `claude-opus-4-7[1m]` → `claude-opus-4-7`
- `.claude/agents/manager.md` § Dispatch grammar — new MODEL_PICK section + heuristic logic (D.4 + D.5)
- `.claude/agents/manager.md` § Tracing — add MODEL_PICK event row
- `docs/AGENT_OPS.md § 5 Agent reference` — twin rows added; threshold doc'd
- `docs/AGENT_OPS.md § 7.2` — MODEL_PICK event format finalized
- `tests/test_workflow_invariants/test_model_twin_drift.py` (new, ~40 LOC; asserts architect.md ≅ architect-1m.md modulo the `model:` line + ditto for engineer)
- ROADMAP `0.7.0.23` row flip
- New follow-up row `0.7.0.NN+1` filed: "Revisit MANAGER_MODEL_THRESHOLD_TOKENS after 1 full milestone of telemetry"

**Lints content sketches (PR-A):**

```python
# tests/test_workflow_invariants/test_parallel_reviewer_dispatch.py
"""Catches sequential reviewer dispatch — invariant per manager.md § Parallel reviewer invariant.

Scans latest run's manager.log. If a PR_REVIEW dispatch event appears with hacker
dispatched first AND architect dispatched later (with intervening AGENT_RETURN),
that's a violation of the same-message-two-Agent-calls rule.

Skip if no traces/* dir (e.g., fresh clone, no run yet).
"""
from pathlib import Path
import re
import pytest

TRACES = Path("traces")

def test_parallel_reviewer_dispatch_in_latest_run():
    runs = sorted([p for p in TRACES.iterdir() if p.is_dir() and p.name not in {"watch.sh"}])
    if not runs:
        pytest.skip("no traces/ runs yet")
    latest = runs[-1]
    manager_log = latest / "manager.log"
    if not manager_log.exists():
        pytest.skip("no manager.log in latest run")
    # ... scan for "DISPATCH agent=hacker" then "AGENT_RETURN agent=hacker" then "DISPATCH agent=architect"
    #     without a preceding "DISPATCH agent=architect" within 60s of the hacker dispatch
    # Hard fail if violation found.
```

(Full sketches deferred to PR-A's engineer prompt.)

### Build sequence

**PR-A (target merge: post-0.2.0-close, week of 2026-06-XX assuming `0.2.0.14` n8n moves to Backlog per plan 40):**

1. **Wave 1 — manager + engineer prompt edits + PLAYBOOK § H step 12 + § I + worked example.** (~60 min, ~2 file edits if you count the playbook as one file)
2. **Wave 2 — lint scaffolding.** `tests/test_workflow_invariants/__init__.py` + 3 wave-1 lints (parallel-reviewer + deviations + fold-in). (~90 min)
3. **Wave 3 — wave-2 lints.** Other 3 (cli + em-dash + manager-scope). (~60 min)
4. **Wave 4 — AGENT_OPS doc update + ROADMAP `0.7.0.22` flip + Last-updated bump.** (~30 min; this wave is BOOKKEEPING that folds into the PR per D.6's own new rule — dogfood test of PR-A's own fold-in rule)
5. **Wave 5 — PR open + parallel reviewer dispatch + merge.** (PR_REVIEW_GATE; surface; user approval)
6. **Wave 6 — Archive plan 41 via `naavik-ops plan archive` (which by then exists per `0.7.0.21`).**

**PR-B (target merge: 2-4 weeks after PR-A, after 1 milestone of telemetry):**

1. **Wave 1 — twin agent files + drift lint.** Create architect-1m.md + engineer-1m.md by copying siblings; flip model lines. (~30 min)
2. **Wave 2 — manager.md MODEL_PICK section + heuristic.** (~60 min)
3. **Wave 3 — AGENT_OPS update + ROADMAP `0.7.0.23` flip + follow-up `0.7.0.NN+1` filed.** (Fold-in to PR-B per D.6 since PR-B is open.)
4. **Wave 4 — PR open + parallel review + merge.**
5. **Wave 5 — Archive.**

### Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Manager exceeds D.1 boundary subtly (e.g., codes 2 files = 95 LOC but touches a security-adjacent file like `src/services/env_secrets.py` that's not in the explicit allowlist of "security surface") | Medium | High (reviewer pair catches; net cost = wasted manager dispatch + 2 reviewer dispatches + REQUEST_CHANGES round) | D.7's `test_manager_scope_violations.py` lint runs at commit time, fails CI if manager author + boundary violation; reviewer pair still runs but lint catches before push |
| Model-twin agent drift (architect.md and architect-1m.md diverge over time) | High (every edit on either is a coupling point) | Medium (one twin gets a fix, other doesn't; manager dispatches the un-fixed twin and the bug fires) | D.7 PR-B's `test_model_twin_drift.py` lint asserts the two files differ ONLY on the `model:` line; pytest fail = drift; engineer who edits architect.md sees test fail + has to update architect-1m.md in the same commit |
| Fold-in rule causes confusing PR diffs (reviewers see ROADMAP marks they didn't expect) | Medium | Low (review noise; no functional risk) | Worked example in PLAYBOOK + `chore(<scope>):` vs `docs(<scope>):` commit prefix discipline; reviewer reads commit messages + can collapse `docs(roadmap):` commits visually in `gh pr view` |
| Threshold (60K) too tight; common architect-delta-review dispatches truncate or 503 because the 200K opus ceiling leaves no reasoning headroom | Medium | High (dispatch retries on `[1m]`; net-cost-up) | Heuristic biases conservative (sum-of-pre-reads * 8 tokens/line + 2K overhead; any uncertainty → `[1m]`); 0.7.0.NN+1 follow-up row to revisit after 1 cycle of telemetry; manager can manually override `subagent_type` if confidence is low |
| Lint suite's `test_bookkeeping_fold_in.py` flakes on git+gh-cli timing | Medium | Low (lint flap; not a real violation) | Use `git log` against a frozen commit range (last 50 main commits); `gh pr list --state open --json number,createdAt,closedAt`; cross-join is deterministic if inputs are frozen |
| User's "unidentified changes" semantics (manual edits) get classified wrong by the AskUserQuestion in D.6 (user clicks "foldable" but the edit is unrelated to the PR's work) | Low | Medium (PR carries unrelated change; squash absorbs it; future debugger has to read commit messages to untangle) | AskUserQuestion phrasing: "Files <path/list>: do these relate to PR #N <title>? (Foldable / Unrelated → direct push / Skip this change for now)"; user picks; manager logs the decision |
| PR-A merge introduces lint that flags a pre-existing violation in main (e.g., an old archived plan missing deviations section) | High (5/8 archived plans this run already lack the section per the 0.7.0.21 row) | Medium (CI fails immediately on first push) | PR-A's lints run with `--from-commit=<merge-base>` baseline filtering — only NEW archived plans (added on this branch) are checked; pre-existing archives get a separate `tests/test_workflow_invariants/legacy_baseline.json` allowlist that `0.7.0.21` plan archive subcommand populates retroactively (the 0.7.0.21 plan author handles this in its deviation section; this plan inherits the baseline) |
| Manager-authored PR fails hacker BLOCK because manager didn't know about an obscure security check | Low | High (PR rolls back; rework) | D.1's "no security surface" boundary covers the common cases; for the residual risk, hacker still runs at PR_REVIEW_GATE and BLOCK still wins; manager's worst-case is "wasted 30 min coding what engineer would have shipped" |

## Open questions

- [ ] **OQ.1 — Model-twin agent naming.** Recommended: `.claude/agents/architect.md` (default opus, no `[1m]`) + `.claude/agents/architect-1m.md` (1M context). Alternative: invert (`architect.md` stays at `[1m]` as the "default safe" variant; `.claude/agents/architect-200k.md` is the cheaper variant). Naming affects all `subagent_type=` references in manager.md + AGENT_OPS.md. **Default lock: A (`-1m` suffix variant is the explicit-flagged one).** Reasoning: most dispatches stay default; the bigger-context one wears the flag.

- [ ] **OQ.2 — Threshold value at 60K vs 50K vs 75K.** D.4's option matrix recommends 60K based on this run's data. User stated 50K. Picking 50K would mean engineer NEVER triggers (median 210K, min 95K) so engineer-1m.md is the only engineer variant — `.claude/agents/engineer.md` is dead. **Default lock: 60K** (recommended) with a 0.7.0.NN+1 follow-up row to revisit after 1 milestone of telemetry. If user prefers 50K, swap to "engineer.md stays as the 200K variant + just never gets dispatched on small work" — equivalent outcome.

- [ ] **OQ.3 — Lint enforcement vs advisory.** Should `test_manager_scope_violations.py` HARD-FAIL CI or advisory-only? Hard-fail blocks PR-merge; advisory just emits a warning. Hard-fail is what the user wants; advisory is the conservative ship. **Default lock: hard-fail for all 6 lints** — that's the whole point of moving enforcement out of prompts.

- [ ] **OQ.4 — Fold-in rule's "unrelated edit" handling.** D.6 specifies AskUserQuestion for manual edits unrelated to an open PR. Should this also fire for manager-authored bookkeeping edits that turn out to be cross-cutting (e.g., the manager's working on PR-A but separately notices a typo in `0.2.5` section of ROADMAP — does the typo fold or go direct-push)? **Default lock: typo fix is bookkeeping; unrelated to PR-A; direct push.** The rule is "fold ONLY if the bookkeeping flows FROM the PR's work."

- [ ] **OQ.5 — When does this execute?** This plan is DEFERRED. ROADMAP row `0.7.0.22` is filed but `[ ]` until: (a) `0.2.0.14` n8n moves to Backlog per plan 40, (b) `0.7.0.21` `naavik-ops plan archive` is in mainline, (c) `0.2.0` milestone fully closes. **Default lock: post-0.2.0-close (target 2026-06-XX).**

## Approval checklist

- [ ] D.1 — Manager coding boundary edges accepted as numeric (files ≤ 2, LOC ≤ 100, no new dep, no design contract, no security surface)?
- [ ] D.2 — Three manager.md edits as drafted (line 9 + line 289 + new § Manager coding boundary section)?
- [ ] D.3 — Twin-agent mechanism (Option D — twins for architect + engineer only, hacker/devops/designer stay `[1m]`)?
- [ ] D.4 — Threshold at 60K with 0.7.0.NN+1 follow-up to revisit after 1 cycle?
- [ ] D.5 — Sum-of-pre-reads heuristic for manager's per-dispatch estimation + MODEL_PICK trace event?
- [ ] D.6 — Fold-in rule timing-based (PR open + related → fold; PR open + unrelated → direct push; no PR → direct push; exceptions list)?
- [ ] D.7 — All 6 lints under `tests/test_workflow_invariants/`, hard-fail by default (per OQ.3 lock)?
- [ ] D.8 — Two PRs in sequence (PR-A manager+fold-in+lints; PR-B model twins) with 1-milestone telemetry gap between?
- [ ] OQ.1 — `architect-1m.md` / `engineer-1m.md` naming (option A: `-1m` suffix on the bigger-context variant)?
- [ ] OQ.5 — Execution after 0.2.0 close + 0.7.0.21 mainline + plan 40 mainline?

## Empirical evidence (this run)

For reviewer reference; not part of approval:

- **Parallel reviewer invariant violations:** 2 in this run (one before PR #99 codification, one after) — confirmed in `manager.log` between `[2026-05-19T16:39:28Z]` and `[2026-05-20T03:25:00Z]`.
- **Deviations section missing:** 5/8 plans archived this run lacked the section (closed retroactively in `29f859d`).
- **Direct-push bookkeeping commits:** 14 commits matching `docs(roadmap)|docs(archive)` since `0.1.1` (PR #91, `047406e`) through `0.2.0.13` (PR #118, `8c976e6`). At ~1 per PR merge, 11 of these would have folded into their PR squash had the rule existed. The other 3 (`ac281ee` deferral + `645da10` sequencing + `4742166`+`62e2a25` cross-cutting roadmap edits) are genuinely cross-cutting and would have stayed direct-push.
- **Token-use distributions** (per § D.4 above; raw data in `manager.log` `AGENT_RETURN ... tokens=<n>` lines).
- **Manager-could-have-coded-inline examples this run:** the very plan-39 PR currently in flight on this branch shipped ~250 LOC of cli.py + 4 skill body single-paragraph tightenings. Manager dispatched engineer for all of it; under D.1's boundary, the skill body edits (3 files × ~8 LOC = within bounds + no security surface) would have been manager-inline.

## Deviations from plan

(To be filled in by the implementing agent at archive time per `AGENTS.md § Workflow step 7` + enforced by `naavik-ops plan archive` per `0.7.0.21`.)
