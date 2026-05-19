# Naavik Development Roadmap

> Last updated: 2026-05-19 (**`0.2.0.01` EXECUTED — PR #92 merged at squash `b91f50b`; closes Issue #20; vault deprecated → env-only secrets.** `src/services/vault.py` (436 LOC AES-256-GCM/PBKDF2/audit) + `src/cli/{vault,init}.py` (258 LOC) + `tests/test_vault.py` DELETED. New `src/services/env_secrets.py` exposes per-scope presence indicators sourced from pydantic-settings. Alembic 0004 drops 5 vault-derived `Settings` columns (`llm_api_key_fingerprint` + 4 `*_configured` bools). `PUT /api/v1/settings/{llm,notifications}` reject `api_key` / `discord_webhook_url` / `telegram_bot_token` / `telegram_chat_id` with 422. Settings UI: API-key input + vault-locked banner gone; env-presence indicator cards instead. `.env.example` rewritten w/ 14 slot rows incl. new `TELEGRAM_CHAT_ID`. `naavik vault <...>` + `naavik init` exit 2 w/ deprecation hint pointing at CHANGELOG. On-disk artifacts retired: `~/.naavik/secrets.enc{,.lock,.bak.*}`, `~/.naavik/key.bin`, `~/.naavik/logs/vault-audit.log`. New regression lint `tests/test_no_vault_imports.py`. CHANGELOG `## [0.2.0]` Unreleased section bootstrapped (Removed/Changed/Added/Operations/Security) w/ loud self-hoster migration paragraph. 8 commits W0-W5 + W6/W7/W8 delta. Reviewers (delta cleared): hacker APPROVE (round-1 1 LOW + 2 INFO defer-recommendations stand); architect APPROVE FULL spec match (round-1 2 MEDIUM + 1 LOW resolved in delta W6+W7). 7 substantive engineer deviations promoted into archived plan; `Skill: engineer-deviation-log` miss noted as lesson candidate. Only surviving CLI subcommand: `naavik serve` (dies in `0.2.0.02`). `0.2.1.03` (Argon2id upgrade DEF-17) auto-closed as moot — vault gone. Next: dispatch `0.2.0.05 HIGH #15` (SQLModel Job + StatusHistory models — gates all scrapers `0.2.0.06`–`0.2.0.10`) OR `0.2.0.04 #70` (PC.6b onboarding bypass fix).)
>
> Earlier line: 2026-05-19 (**`0.1.1` EXECUTED — PR #91 merged at squash `494ffae`; tag `0.1.1` + GH release published at https://github.com/crizzy9/naavik/releases/tag/0.1.1.** Legacy bash → native Python migration complete: `.claude/naavik_ops/gh.py` (20 callable subcommands + 1 helper `get_issue()`), `.claude/naavik_ops/memory.py` (12 subcommands w/ A.17 jq sandbox byte-for-byte preserved), `.claude/naavik_ops/lib/roadmap.py` (writer-half + 304-LOC legacy parser inlined). 5 mutating `task` ops shipped native + atomic (`insert`/`defer`/`prioritize`/`move`/`renumber` — closes A.29 Deviation 1). CHANGELOG `ReleaseEntry` CommonMark-sanitized (Issue #74 closed). `scripts/{gh-project.sh,agent-memory.sh,roadmap_parser.py}` + `tests/test_agent_memory.sh` DELETED (-2616 LOC). PR_REVIEW_GATE reviewer pairing refactored from `hacker + devops` → `hacker + architect` (W6; new § PR review mode in `.claude/agents/architect.md`); devops moves to on-demand dispatch for build-gate failures + runtime debugging. Test suite: 210 passing in `tests/test_naavik_ops/` (was 101 baseline). Hacker: APPROVE_WITH_NOTES (2 LOW + 1 INFO; non-exploitable; defer-the-design-intent recommendations). Devops: PASS 12/12 gates (zero regressions). 2 engineer deviations promoted into archived plan. **Post-merge bookkeeping**: 8 stale epics closed via new `close-issue` helper (`#1 Phase A` / `#6 Pre-Phase-2 paper cuts` / `#9 Phase 2` / `#22 Phase 1 deferred` / `#65 Phase 2.5` / `#76 [Epic] 0.1.0` / `#77 [Epic] 0.1.1`); Issue #90 (`0.1.1.03` cleanup task) self-closed by helper. ROADMAP § 0.1.1 all 3 rows `[x]`. Next: dispatch `0.2.0.01 HIGH #20` (vault deprecation → env-only secrets) under new `hacker + architect` review pairing.)
>
> Earlier line: 2026-05-19 (**0.1.1 IN FLIGHT — plan 25 implemented; feat branch `feat/0.1.1.01-bash-to-python` open for PR.** Legacy bash → native Python: `.claude/naavik_ops/gh.py` rewrites 18 subcommands + adds 3 helpers (`update-issue-title` / `close-issue` / `get-issue`); `.claude/naavik_ops/memory.py` rewrites 12 subcommands (A.17 hardening byte-for-byte ported); `.claude/naavik_ops/lib/roadmap.py` inlines `scripts/roadmap_parser.py` + adds writer-half (`ReleaseRow` / `ReleaseDiff` / `parse_release_section` / `write_release_section` / `rewrite_atomic`). 5 mutating `task` subcommands shipped (insert / defer / prioritize / move / renumber) — atomic 3-store mutation under flock w/ rollback. CHANGELOG `ReleaseEntry` CommonMark-sanitized (Issue #74). `scripts/{gh-project.sh,agent-memory.sh,roadmap_parser.py}` + `tests/test_agent_memory.sh` DELETED in W5. Test suite: 210 passing (was 101 baseline). `0.1.1` ceremony pending: maintainer runs `naavik-ops release cut 0.1.1 --apply` post-merge.)
>
> Earlier line: 2026-05-18 (**A.29 Wave 5 APPLIED + `0.1.0` release ceremony cut on feat; PR #75 ready to squash-merge.** Migration `python .claude/migrations/A.29-phase-renumber.py --apply` ran clean on feat via run `2026-05-18T16-00-00_a29w5a`: created 14 new release-version Milestones (`0.1.0` / `0.1.1` / `0.2.0` / `0.2.1`-`0.2.6` / `0.3.0`-`0.6.0` / `0.7.0`) + 14 new Epics; renumbered ~50 GitHub Issues to 4-level semver schema (`MAJOR.MINOR.PATCH[.POSITION]`); applied 738-line ROADMAP-diff patch (Phase 0 + Phase 1 + Pre-Phase-2 paper cuts + Phase A → ONE collapsed `### 0.1.0` section of 50 positions; Phase 2 → `### 0.2.0` w/ vault sunset HIGH at `0.2.0.01` + Job models HIGH at `0.2.0.05`; DEF-01..DEF-25 → 6 thematic patches `0.2.1`-`0.2.6`; Phase 2.5 agent-system follow-ups → `### 0.7.0`; Phase 3-6 → `### 0.3.0`-`### 0.6.0`); closed 5 superseded Milestones (`Phase A`, `Pre-Phase-2 paper cuts`, `Phase 2`, `Phase 2.5`, `Phase 1 deferred items`); bootstrapped `CHANGELOG.md` w/ `## [0.1.0] - 2026-05-18` section. Then `.claude/naavik-ops release cut 0.1.0 --apply` ran ceremony steps 1-6 (pyproject + nix/package.nix already at `0.1.0`; CHANGELOG stub block trimmed in follow-up commit `e5b6953`). Step 5 read-only verify PASSED: `task list 0.1.0` = 50 rows; `task list 0.2.0` = 14 rows w/ HIGH on `0.2.0.01` + `0.2.0.05`; `next-unblocked 0.2.0` → `0.2.0.01 HIGH #20` (vault sunset); `task check` clean. **Next**: squash-merge PR #75 → tag `0.1.0` on main + push + `gh release create` (post-merge tag pacing per release ceremony) → dispatch A.30 (`0.1.1.01` + `0.1.1.02`) immediately per locked sequencing memory `A.29-then-A.30-immediate-sequencing`.
>
> Earlier line: 2026-05-18 (**A.29 Wave 5 patch PR #75 open + reviewed; halted for new-session apply.** Hacker APPROVE_WITH_NOTES (1 LOW worktrees gitignore — folded into A.30); devops PASS 7/7 gates. PR #75 ships 3 architect artifacts: 738-line ROADMAP-diff patch + populated 9 historical maps in migration script + 166-line patch README. **Sequencing locked** (memory `A.29-then-A.30-immediate-sequencing`, supersedes `wave-5-sequencing-verify-before-merge`): (1) NEW SESSION runs Wave 5 apply on feat → cut 0.1.0 release → Step 5 read-only verify (`naavik-ops task list <release>` + `next-unblocked` + `check`) → squash-merge PR #75; (2) A.30 dispatches IMMEDIATELY after merge — Python rewrites of `gh-project.sh` + `agent-memory.sh` + native impls of the mutating task subcommands (`insert`/`defer`/`prioritize`/`move`/`renumber`) stubbed in A.29; ships as 0.1.1; (3) Move-around testing happens AFTER A.30 ships (exercises the now-implemented ops against post-A.29 state). Run trace: `traces/2026-05-18T14-30-53_de60c4/MANIFEST.json` (outcome=halted halt_reason=user_requested_new_session_for_wave_5_apply_verify_before_merge).
>
> Earlier line: 2026-05-18 (**A.29 EXECUTED — Waves 1-4 shipped via PR #73 squash `c5ac58f`; Wave 5 deferred post-merge.** 4-level semver task-ID schema (`MAJOR.MINOR.PATCH[.POSITION]`) + `.claude/naavik-ops` Python dispatcher + `.claude/naavik_ops/` package (5 subcommand groups; gh+memory subprocess-wrap legacy bash during A.29) + `.claude/migrations/A.29-phase-renumber.py` (13-step Python, DRY RUN only; Wave 5 applies) + ~30-site caller rewrites + Conventional Commits enforcement + design doc `docs/design/PHASE_NUMBERING.md` graduated. **Reviewers**: hacker APPROVE_WITH_NOTES (3 LOW: 2 cosmetic dup Bash grants, 1 latent CHANGELOG markdown sanitization — filed as A.31 #74 0.1.1-follow-up); devops PASS 11/11. 8 engineer deviations promoted into archived plan (notable: Wave 1 mutating task subcommands stubbed → A.30; W2 ROADMAP-rewrite needs Wave 5 architect dispatch). **Wave 5 next**: architect dispatch authors `docs/plans/24-A.29-roadmap-diff.patch` → `python .claude/migrations/A.29-phase-renumber.py --apply` → `.claude/naavik-ops release 0.1.0 --cut` cuts first `0.1.0` tag. Cumulative token spend on A.29: ~1.06M of 5M daily ceiling (~21%).
>
> Earlier line: 2026-05-18 (**A.29 PLAN_GATE iter 3 APPROVED — engineer dispatched on Waves 1-4.** Plan 24 (1155 lines) + design doc skeleton (388 lines) locked. User said *"yes looks good go now"* accepting all 24 approval boxes + 3 cosmetic resolutions: OQ-1=B (Phase 1 Waves 1-5 get one position each; sub-tasks fold into Notes column), OQ-2=architect-builds-DEF-mapping-in-W2.1, OQ-3=HIGH priority on `0.2.0.01` (vault sunset) + `0.2.0.05` (Job models). Engineer dispatched on branch `feat/A.29-phase-numbering-system` for Waves 1-4 (~3.25-3.75d): W1 `.claude/naavik-ops` Python dispatcher + `.claude/naavik_ops/` package + tests; W2 `.claude/migrations/A.29-phase-renumber.py` migration runbook (not applied yet); W3 ~35-site caller rewrites; W4 design-doc graduation + plan-archive frontmatter rewrites. Wave 5 (post-merge migration apply + `naavik-ops release cut 0.1.0` tag) deferred. Cumulative token spend on plan authoring: architect ~320k + manager ~200k = ~520k of daily 5M ceiling.
>
> Earlier line: 2026-05-18 (**A.30 filed; A.29 plan 24 in REV-3 architect dispatch.** User-locked direction: (1) scope phasing — A.29 ships new `naavik-ops` dispatcher + new commands; A.30 follows with Python rewrite of legacy `gh-project.sh` + `agent-memory.sh` (ships as `0.1.1` patch post-A.29's `0.1.0`). (2) Priority field REVIVED at task level — tasks within a release optionally carry HIGH/MEDIUM/LOW; mostly unset = equally important; sort = priority first then position; patches not prioritized. (3) Naming: `naavik-ops` (sibling dispatcher; not a `naavik` runtime subcommand). (4) Package location: `.claude/naavik_ops/` (agent-system specific; user doesn't run); `scripts/` reserved for project-wide scripts only. (5) Phase A historical mapping simplified — everything pre-Phase-2 (Phase 0 + Phase 1 + PC.1–PC.7 + A.1–A.29) bundled as one `0.1.0` release; chronological splits (0.1.1/0.1.2/0.1.3) dropped. A.30 ships as `0.1.1`. Architect REV-3 dispatch on run `2026-05-18T11-23-20_8cf822`.
>
> Earlier line: 2026-05-18 (**A.29 dispatched — plan 24 authoring in flight; sequencing override.** Manager invoked /build A.29 per user direction (override of pre-existing "after Tier 2" sequencing). Architect dispatched on run `2026-05-18T11-23-20_8cf822` to author `docs/plans/24-A.29-phase-numbering-system.md` (DRAFT) — must surface option matrices for each of the 8 already-locked design decisions, resolve the user-raised open question (DEF-01..DEF-25 priority-inversion under number-as-priority — three candidates A/B/C in row Notes), propose graduation to `docs/design/PHASE_NUMBERING.md` (new contract = task ID schema). HALT at PLAN_GATE for user review. Manager decision codified in memory (`manager-immediate-requirement-logging` — user requirements file IMMEDIATELY into ROADMAP+Issue, no approval gate; only PLAN/PR/MILESTONE gates remain). Working tree: A.29 ROADMAP row flipped `[ ]` → `[~]`; Project board Status `Todo` → `In Progress` via single-writer mirror.
>
> Earlier line: 2026-05-18 (**A.29 filed — phase numbering system + `scripts/phase-tasks.sh` queued for post-Tier-2.** User brainstormed design but no Issue had been filed; closing bookkeeping gap. 8 design decisions locked at brainstorm (open-ended `1.01-1.99` per phase, three-level sub-phase `1.5.01`, frozen done-item IDs, Project Priority field deprecated, ROADMAP wins on drift, Phase 1 consolidation, retroactive IDs for all items, both heading + row prefix naming). `scripts/phase-tasks.sh` core ops: `insert` / `defer` / `prioritize` / `move` / `list` / `renumber` / `rename-phase`. ~2-3 days engineer + ~0.5d architect plan. Sequenced AFTER Tier 2 (2.12 + 2.11) AND BEFORE Phase 2 scrapers per user "go with sequence change" call. Closes Phase A milestone entirely after merge. Issue #71.
>
> Earlier line: 2026-05-18 (**PC.6a EXECUTED — Tier 1 of pre-Phase-2 close-out FULLY CLOSED.** PR #69 squashed; Issue #62 closed; plan 23 archived to `docs/plans/archive/23-PC.6a-broader-auth-gate.md` with full `## Deviations from plan` section (3 engineer deviations + hacker MEDIUM finding documentation). **41 mutation routes gated** via new `require_authed_session` wrapper (real-JWT-first + fake-session-fallback + must-change redirect). 13 new tests, 0 regressions confirmed via baseline-vs-PR diff. Reviewers: hacker APPROVE_WITH_NOTES (1 MEDIUM onboarding-bypass — explicit not-blocker; filed as PC.6b #70); devops PASS 8/8. **Tier 1 status: 4 of 4 done** (A.28 + A.17 + A.16 + PC.6a). Next: **Tier 2** = 2.12 (vault sunset, ~2-3 days, ~15 files mostly deletions) → 2.11 (CLI sunset, < 1 day).
>
> Earlier line: 2026-05-18 (**A.16 + A.17a EXECUTED — Tier 1 wave 3 of pre-Phase-2 close-out.** PR #68 squashed; Issues #61 + #67 closed; plan 22 archived to `docs/plans/archive/22-A.16-machine-readable-rewrite.md` with full `## Deviations from plan` section (3 entries). **57 files rewritten** across `.claude/agents/*` + `.claude/skills/*/SKILL.md` + `.claude/commands/*` + `.claude/hooks/cold-start.sh` + A.17a fold-in (`.claude/naavik-ops memory:119` regex widening + new test 22c). **Token savings**: 49,090 → 44,334 words = **-9.7% / ~-8.5k tokens per ingest cycle** (below 25% Q1 floor; **user accepted ~10% as realistic structural-preservation ceiling at PR_REVIEW_GATE**). Reviewers: hacker APPROVE 0 findings; devops PASS 11/11 gates. **Tier 1 status: 3 of 4 done** (A.28 + A.17 + A.16). Next: PC.6a (Tier 1 wave 4, ~2-4h, auth-dep extension) → 2.12 (Tier 2 wave 1, vault sunset) → 2.11 (Tier 2 wave 2, CLI sunset).
>
> Earlier line: 2026-05-18 (**A.17 EXECUTED — Tier 1 wave 2 of pre-Phase-2 close-out.** PR #66 squashed; Issue #54 closed; plan 21 archived to `docs/plans/archive/21-A.17-agent-memory-hardening.md` with full `## Deviations from plan` section. 5 hacker findings (2 MEDIUM + 3 LOW) on `.claude/naavik_ops/memory.py` closed end-to-end: flock around 6 writers (30/30 concurrent writes persist, was 13/30 pre-fix); jq sandbox via regex char allowlist + word-boundary identifier deny-list (`env|input|getpath|path|paths|setpath|delpaths|debug|stderr|input_filename|$ENV`); `mapfile -t` for `$RUNS` word-split; `validate_aliases` newline + `---` sentinels + widened regex; MANIFEST.json fenced code block wrap. 14 new test assertions (64/64 pass). Reviewers: hacker APPROVE (0 findings); devops PASS 8/8. A.17a (#67) filed as LOW follow-up to widen aliases regex further for uppercase tokens (fold into A.16). Next: A.16 — machine-readable wording rewrite (Tier 1 wave 3).
>
> Earlier line: 2026-05-17 (**A.28 EXECUTED — Phase A wave 1 of Tier 1 closed.** PR #63 squashed as `28a07d6`; Issue #60 closed; plan 20 archived to `docs/plans/archive/20-A.28-board-restructure.md` with full `## Deviations from plan` section (5 deviations). 4-status board live: Project v2 Status field now has `Backlog` (id=`9f6ecdc6`, GRAY) alongside `Todo` / `In Progress` / `Done`. Phase 2.5 milestone (#5) + epic created. Migration runbook `scripts/A.28-board-restructure.sh --apply` ran post-merge to move ~30 Issues to Backlog (Phase 1 deferred, Phase 2 sub-tasks 2.4–2.10, Phase 2.5 relocated rows). A.28a (#64) filed as LOW follow-up for 3 hacker defense-in-depth findings + 1 devops mirror-conventions note. Next: A.17 (Tier 1 wave 2 — `agent-memory.sh` hardening, ~2h security fix).
>
> Earlier line: 2026-05-17 (**A.28 in flight — plan 20 APPROVED, PR open. ROADMAP surgery landed.** Relocated A.9 + A.10 + A.18–A.27 (12 rows) from `### Phase A` into new `### Phase 2.5: Agent-system follow-ups (deferred from Phase A)` section between Phase A and Agent System mirror conventions. PC.6a row relocated from `### Pre-Phase-2 paper cuts` into `### Phase 2: Job Scraping & Discovery` immediately above 2.12 (Tier 2 sequencing per PLAN_GATE Q2). New top-of-doc `## Priority Queue` section (rank 1–7+ for operator's at-a-glance "what should I work on"). A.28 row flipped to `[~]` in flight. `docs/ROADMAP_OVERVIEW.md § 3` refreshed to mirror the queue.)
>
> Earlier line: 2026-05-17 (**A.28 filed — board restructure + Post-Phase-2 follow-ups epic + Priority Queue section.** User scope cut: lock pre-Phase-2 work to Tier 1 (A.17 + A.16 + PC.6a + A.28) + Tier 2 (2.12 + 2.11); everything else defers to a new Post-Phase-2 follow-ups epic. Backlog status column to be added to Project v2 alongside Todo / In Progress / Done; agent prompts + AGENT_OPS § 6 + PLAYBOOK status references updated for 4-status convention. Bulk-move A.9, A.10, A.18-A.27 (except A.28 itself) into new Post-Phase-2 section + Backlog status. Phase A milestone closes once A.16 + A.17 + A.28 ship; Pre-Phase-2 paper cuts milestone closes once PC.6a folds into 2.12 PR. Architect plan needed (A.28 = ~half-day after PLAN_GATE clears).
>
> Earlier line: 2026-05-17 (**A.17 collision resolved + A.27 develop-branch consideration filed + repo ruleset reverted by user.** User reverted the `pull_request` ruleset on `main` (only `deletion` + `non_fast_forward` rules remain) — direct push to `main` restored for BOOKKEEPING commits per playbook category I. PLAYBOOK § I unchanged (still says direct push); CONTRACT_CHANGE remains PR-required. A.17 collision: line 426 (trace analytics dashboard) renumbered to **A.26**; line 431 (`agent-memory.sh` hardening, Issue #54) keeps canonical A.17 ID per `.claude/github-issue-map.json`. A.27 filed: `develop` branch workflow move (user-flagged future) — PR target shifts from `main` → `develop`; `main` becomes release/stable with periodic promotion. Local-main orphan commit `58eb2d6` cleaned up via `git pull --rebase` (git detected patch already applied as squash `c9ccbc4`, skipped cleanly — no data loss).
>
> Earlier line: 2026-05-17 (**4 more post-Phase-2 follow-up rows filed: A.22–A.25.** User directives captured: A.22 confusion-gate clause (ask user when ambiguous even in auto mode; technical decisions OK, business/critical always user; HIGH); A.23 SoTA security review tools (Semgrep/CodeQL/Snyk/Trivy/gitleaks/pip-audit/ZAP + LLM prompt-injection detectors); A.24 SoTA architect tools (Structurizr/Mermaid/PlantUML/ADR generators); A.25 wire `huashu-design` skill as primary designer surface (it's allowlisted but underused). All deferred until Phase 2 clears. Demonstrates A.15 discussion-capture pattern in practice. **Known drift**: A.17 collision — line 424 (trace analytics, PR #58, ROADMAP-only) vs line 429 (`agent-memory.sh` hardening, Issue #54, canonical per map). Resolution deferred; surfaced for user decision (renumber trace-analytics → A.26 OR leave the collision documented).
>
> Earlier line: 2026-05-17 (**A.15 EXECUTED via PR #53 squash `a63b774`** — agent memory + learning system. 3-Wave scope (substrate + analytics + lesson promotion) shipped in one PR per user deviation; smoke 50/50. Closes #52 + #48 (A.11 board drift reconciled inline). Follow-ups filed pre-merge: A.17 #54 (hacker `agent-memory.sh` hardening, HIGH, ~2h), DEF-24 #55 (pre-existing ruff cleanup, LOW), DEF-25 #56 (pre-existing DB-test gating gap across 11 files, MEDIUM). Plan 19 archived with full `## Deviations from plan` section promoting deviations from PR body + gate report. Full PR_REVIEW_GATE report archived at `traces/2026-05-17T08-40-13_4abef2/pr-review-gate.md` (canonical template for future gate reports per § 9 convention note).
>
> Earlier line: 2026-05-17 (**A.15 in-flight on PR #53; A.17 + DEF-24 + DEF-25 filed pre-merge per follow-up wrap-up.** Hacker `APPROVE_WITH_NOTES` on A.15 surfaced 5 `agent-memory.sh` hardening findings (filed `A.17` Issue #54, HIGH); devops gate review surfaced 65 pre-existing pytest DB-test failures (filed `DEF-25` Issue #56) + 10 pre-existing ruff errors (filed `DEF-24` Issue #55) — both confirmed pre-existing via stash technique, NOT introduced by A.15. A.11 (#48) Project board drift reconciled inline (Todo→Done via close). `.claude/memory/knowledge/INDEX.md` added — auto-maintained by `.claude/naavik-ops memory update-index` on every `record-knowledge`. Full PR review gate report archived at `traces/2026-05-17T08-40-13_4abef2/pr-review-gate.md`. Pending: PR #53 merge decision.)
>
> Earlier line: 2026-05-17 (**Plan 19 APPROVED + A.15 + A.16 filed + repo settings locked to squash-only.** User approved all 7 Q decisions on plan 19 (agent memory + learning system) + selected all-3-Waves-in-one-PR deviation from architect's 3-phased recommendation. Plan 19 status flipped `DRAFT → APPROVED` with decisions locked (`.claude/memory/` JSONL+md stores, single-writer `.claude/naavik_ops/memory.py`, `naavik-memory-lookup` + `naavik-discussion-capture` skills, `/learn` slash command + skill mirror, read-only MEMORY.md integration, 5-occurrence promotion threshold). **A.15 row filed** under Phase A: 3-Wave scope (substrate + analytics + lesson promotion) ships in one PR on `feat/A.15-agent-memory`. **A.16 row filed** as follow-up: machine-readable wording rewrite of `.claude/agents/*`, `.claude/skills/*`, `.claude/commands/*`, `.claude/hooks/*` (docs files stay prose). Per user: *"in the end it's all about you"* — the agent-system instruction surface should minimize tokens while conveying intent efficiently to LLM consumers. A.15 engineer adopts style for new files; A.16 retrofits existing. **Repo merge settings updated** (`gh api -X PATCH repos/crizzy9/naavik`) — `allow_merge_commit=false`, `allow_rebase_merge=false`, `allow_squash_merge=true`, `delete_branch_on_merge=true`, `squash_merge_commit_title=PR_TITLE`, `squash_merge_commit_message=PR_BODY`, `allow_auto_merge=true`. Enforces squash-only at repo level (defense-in-depth backstop on the playbook procedure); future PR squashes use PR title as subject + PR body as message body (no more `* commit-message` noise from individual commits); PR branches auto-delete on merge. User starting fresh session for A.15 implementation — seed text: `/build A.15`.)
>
> Earlier line: 2026-05-17 (**A.14 SHIPPED via PR #51 squash `ab9f2589`** + **plan 19 AUTHORED awaiting PLAN_GATE**. A.14 codifies the **Task Playbook** (`docs/PLAYBOOK.md`) — strict 9-category if-then decision tree the manager consults on every user message; closes the judgment surface that produced `aa2f6a0`. PR #51 took two commits (initial + Path-B re-loop adding default-deny rule + allow-list-only structure per hacker Finding 1); self-validating authorship — the PR followed its own category H procedure. Hacker: APPROVE (Path-B structurally stronger than Path-A). Devops: PASS (7/7 delta checks). Plan 19 (`docs/plans/19-agent-memory-and-learning.md`) authored by architect 2026-05-17 in response to user ask for "storage mechanism + memory + indexed knowledge base + progressive discovery + discussion-to-ROADMAP capture + periodic learning + session analysis + Claude memory integration." Recommends JSONL + markdown stores under `.claude/memory/`, single-writer `.claude/naavik_ops/memory.py`, 3 new skills + 2 new slash commands (`/memory`, `/learn`), read-only integration with `~/.claude/projects/.../memory/MEMORY.md`. 7 open questions, 3-Wave phasing, Wave 1 = ~1 engineer day (substrate + discussion-capture + 5 seeded knowledge entries). Awaiting PLAN_GATE.)
>
> Earlier line: 2026-05-17 (**A.13 SHIPPED via direct push `aa2f6a0` — WORKFLOW MISS.** Tracing contract codified: `ERROR step=<what> kind=<retry|skip|halt|pivot>` events + `BUILT`/`REVIEWED` terminal-line summaries enforced across all 6 agent prompts; MANIFEST schema extended with `outcome` + `halt_reason` + `what_built` + `errors_encountered`. All in response to user feedback after PR #50: "make sure agents write to the trace properly." **The push bypassed PR review** — a process violation called out by the user. Documented as a one-time miss; future source-of-truth changes (agent prompts, skill bodies, AGENT_OPS contract sections, code) go through PR with hacker + devops review per AGENTS.md § Workflow. ROADMAP bookkeeping (this row + Last-updated bump) remains direct-push per existing pattern (compare `c158320` / `7924307`). See ROADMAP § Phase A row A.13 for the full deliverable.)
>
> Earlier line: 2026-05-17 (**PC.6 + A.11 EXECUTED via PR #50** — squash `7c7e12a` = `feat(auth): PC.6 password complexity + must-change-on-first-login`. PR #50 took two commits: initial `baad10c` shipped all 5 architect-recommended decisions verbatim; path-C re-loop `78c6d20` resolved hacker Findings 1 (HIGH — `src/ui/routes/settings.py:411` stub now gated with `Depends(require_password_complete)`) + 2 (MEDIUM — `Depends(require_csrf)` on `post_change_password`); Finding 3 (MEDIUM — stale JWT post-rotation) deferred to Phase 1.x deferred items as "JWT denylist on password rotation" row. PC.6a follow-up filed for broader gate to `api/profile` + `api/settings` (deferred until those routes gain real auth deps). Engineer's `## Deviations from plan` section in plan 18 carries 6 bullets all 4 dimensions (what/why/impact/surface). Hacker delta-review: APPROVE (zero new findings). Devops re-gate: PASS (494 tests / 25 skipped / +3 new tests / migration round-trip clean / `Closes #8` trailer × 2 commits). **Plan 16 EXECUTED** in parallel — A.11 (Agent System v2) complete across all 4 phases: Phase 1 cold-start hook + skill + Skill tool on 6 agents + prepare-commit-msg hook (shipped 2026-05-16); Phase 2 per-agent skill suite (29 skills shipped vs spec'd 28 — `build` skill mirror added mid-Phase-4 codifying dual-surface convention in AGENT_OPS § 10.2); Phase 3 first `/build` (PC.5, PR #49); Phase 4 second `/build` (PC.6, PR #50, this entry). Side artifact: `docs/design/research/LINKEDIN_SCRAPING.md` option matrix (5 options × 10 dimensions, recommends guest-API + Crawl4AI stealth for task 2.2; stickerdaniel MCP flagged as front-runner for Phase 5 task 5.12 outreach). Plans 16 + 18 archived to `docs/plans/archive/`. Token spend across PR #50 = ~2.2M of 5M daily ceiling (engineer 1.05M / architect 535k + 94k LinkedIn / hacker 239k / devops 144k / manager 195k).)
>
> Earlier line: 2026-05-16 (**PC.5 + A.8 EXECUTED via PR #49** — squash `ceca24b`. `Settings._enforce_secret_key` validator at `src/config.py:45-66` refuses module import when `SECRET_KEY` is the shipped default or <32 bytes, unless `NAAVIK_DEBUG=1`. 3 hacker findings folded into the same PR: (1) `Settings.debug` alias narrowed to `NAAVIK_DEBUG` only (dropped generic `DEBUG` foot-gun); (2) `docker-compose.yml` requires `SECRET_KEY` at compose-render time via `${VAR:?...}`; (3) `populate_by_name=True` attempted + reverted (pydantic-settings v2.13 re-enables field-name env-var key, defeats finding 1). Plan 17 archived to `docs/plans/archive/17-pc5-secret-key-enforcement.md`. First end-to-end `/build` of agent-system v2 validated: 5 skills invoked, git hook auto-appended `Closes #7`, deviations promoted, plan archived. Phase 3 of plan 16 complete; Phase 4 (PC.6) is next.)
>
> Earlier line: 2026-05-16 (**Plan 16 AUTHORED** — `docs/plans/16-agent-system-v2.md` DRAFT for ROADMAP row A.11 (Agent System v2). Four phases: (1) cold-start hook + `naavik-cold-start` skill + `Skill` tool on all 6 agents + git `prepare-commit-msg` hook + Project v2 automation guide; (2) ~28-skill per-agent suite under `.claude/skills/<name>/SKILL.md` (manager 4 / architect 4 / engineer 5 / designer 5 / hacker 3 / devops 3 + 4 shared `naavik-*`); (3) first real `/build` shipping PC.5 (satisfies A.8); (4) second `/build` shipping PC.6. Halts after Phase 1 + Phase 2 for user review. All 6 kickoff Open questions resolved in the plan (skill naming = `<agent>-<verb>` + `naavik-<verb>`; cold-start = hook + skill; `SubagentStart` NOT used per anthropics/claude-code#27755; branch regex `^(feat|fix|chore|docs|refactor)/<task-id>-<slug>$`). Plan estimates ~2.1M–2.9M total tokens across all 4 phases.)
>
> Earlier line: 2026-05-16 (**A.11 added + A.12 marked done.** A.12 (map cache + single-writer governance): `.claude/naavik_ops/gh.py` `find_issue_by_prefix` + `ensure_milestone` now consult `.claude/github-issue-map.json` first (eliminates the search-API race that produced duplicate epics #46 dup #6 + #47 dup #7); new `refresh-map` subcommand reconciles from authoritative GitHub state; dry-run reports `exists`/`PLAN` for milestones + epics correctly; bootstrap is fully idempotent (`would create=0 skipped=40`). "GitHub state — single writer" rule codified in `CLAUDE.md` / `AGENTS.md` / `.claude/agents/manager.md` / `.claude/commands/bootstrap.md` / `docs/AGENT_OPS.md`. A.11 (Agent System v2): 4-phase plan kicked off via `docs/prompts/agent-system-v2.md` — cold-start hook + skill + per-agent skill suite under `.claude/skills/<name>/SKILL.md` + git `prepare-commit-msg` hook for auto `Closes #N` linkage from branch name + Project v2 automation guide. Phase 3 of A.11 = A.8 deliverable (first end-to-end `/build`); architect to author `docs/plans/16-agent-system-v2.md` in next session. New file: `docs/prompts/README.md` documents the prompts directory convention (kickoff prompts archive alongside plans).)
>
> Earlier line: 2026-05-16 (**ROADMAP carved to tracking-only.** 807 → 436 lines (-46%). Vision + Competitive Context moved to `README.md`; Architecture diagram + Tech Stack table + Design decisions + Repository Structure + Data Model sketches removed (canonical homes: `docs/ARCHITECTURE.md` + `docs/design/DATA_MODEL.md`); Deployment (4 paths) moved to new `docs/DEPLOYMENT.md`; n8n migration + Portfolio integration narratives moved to `docs/ARCHITECTURE.md` § 4.7 External integrations; UI Screens narrative deleted (canonical was always `docs/design/SCREENS.md`). Pointer table in § Maintenance lists where each section landed. **GitHub Project #4 mirror live** (https://github.com/users/crizzy9/projects/4): 4 epics (#1 Phase A, #6 Pre-Phase-2 paper cuts, #9 Phase 2, #22 Phase 1.x deferred) + 45 Issues + 4 milestones + Status/Priority/Effort single-select fields + `[Epic] <phase>` parent issues + sub-issue linkage via Parent issue field + 13 labels. `.claude/naavik_ops/gh.py` extended with `create-epic`, `--parent` on `create-issue`, `set-priority`, `set-effort`; bootstrap creates Milestone + Epic + sub-issues per phase. Cache at `.claude/github-project.json` (gitignored, per fork).)
>
> Earlier line: 2026-05-16 (**Phase A: Agent System bootstrapped** — 6 specialized Claude Code subagents under `.claude/agents/` + 13 slash commands under `.claude/commands/` + `.claude/naavik_ops/gh.py` (Projects v2 helper) + token budget config + trace system + 3 `.github/ISSUE_TEMPLATE/` forms + PR template. `docs/AGENT_OPS.md` is the canonical operational guide. Phase A is meta (the dev process), tracked separately from product phases 0-6. Fork bootstrap: `gh auth login → .claude/naavik-ops gh init → .claude/naavik-ops gh bootstrap --apply → claude /standup → claude /build "next"`. A.1-A.7 shipped; A.8 (first end-to-end `/build` against PC.5) is the validation step.)
>
> Earlier line: 2026-05-12 (Plan 10c **EXECUTED** — first-time setup ergonomics paper cut shipped. `nix develop` shellHook exports `NAAVIK_PERSISTENCE=db` for orchestrator parity (10c.1); `/login` promotes the "Create account" CTA out of the footer to a prominent affordance below the Sign-in button, and `/login?mode=signup` renders an amber `lock` banner ("This instance already has an account.") instead of a form against a seeded single-user DB (10c.2); seeded dev credential now persists to `~/.naavik/dev-credentials` (mode 0600, gated on `NAAVIK_DEBUG` + generated-password + `Settings.deployment_mode==SELF_HOSTED`) AND is re-echoed by the FastAPI lifespan ~750 ms after startup so it survives the orchestrator's interleaved scrollback (10c.3). Retrieval is plain `cat ~/.naavik/dev-credentials`; **no new CLI subcommand** (CLI sunset per Phase 2 task 2.11). New config field: `Settings.debug` on `src/config.py` reads `NAAVIK_DEBUG` / `DEBUG` via pydantic-settings alias. 478 tests pass (3 new vs the 475 baseline; 2 additional live-DB seed tests under `NAAVIK_LIVE_DB=1`). New baseline snapshot: `tests/visual/baseline/login-signup-banner-desktop.png`. Doc cross-walk: README § "First-time setup", § Dev/test env vars, § Configuration § DATA_DIR comment, § Operations § `naavik` CLI sunset note; CLAUDE.md "Last updated"; POST_PHASE_1.md § "Phase 1 done" step 2.)
>
> Earlier line: 2026-05-10 (Plan 10c **APPROVED** — kickoff prompt at `docs/prompts/10c-first-time-setup.md` ready to paste into a fresh implementation session. Locked decisions: Q1 `signup_disabled` server-side gate, Q2 `app_settings.data_dir / dev-credentials` path, Q3 750 ms lifespan-echo delay, Q4 Wave-4 partial-swap cleanup stays separate, NO CLI extension (CLI sunset per Phase 2 task 2.11) and NO vault changes (vault deprecation per Phase 2 task 2.12). PC.7 stays `[ ]` until implementer flips to `[~]` on start.)
>
> Earlier line: 2026-05-10 (Phase 2 § Architecture-shift tasks added: **2.12 vault deprecation → env-only secrets** (deletes `src/services/vault.py` + AES-GCM + PBKDF2 + audit log + lockfile; switches to gitignored `.env` sourced from devshell + orchestrator + Docker Compose; alembic 0003 drops fingerprint/configured columns; ~2–3 days, ~15 files mostly deletions) and **2.11 CLI sunset** (now sequenced AFTER 2.12 since most of the CLI's reason-to-exist disappears with the vault; `init`/`vault status`/`vault rotate-key` gone, only `serve` remains, then deleted; < 1 day). UX regression to flag in changelog: rotating LLM API keys becomes "edit .env + restart" instead of a Settings UI form — standard self-hosted practice. Plan 10c REVISED earlier today still stands as-is.)
>
> Earlier line: 2026-05-10 (Plan 10c REVISED — first-time setup ergonomics paper cut, scope tightened. Drops the originally-spec'd `naavik dev creds` subcommand: the `naavik` CLI is now on a sunset track per new Phase 2 task 2.11 — operator features migrate INTO Settings UI, the CLI loses surface rather than gains it. Final 10c shape: `nix develop` NAAVIK_PERSISTENCE=db parity (10c.1) + login signup-link promotion + signup-disabled banner gated on `users_exist AND not allow_multiple_users` (10c.2) + persisted `~/.naavik/dev-credentials` (mode 0600, debug + SELF_HOSTED gated) + lifespan echo on app startup (10c.3); retrieval is plain `cat`. AGENTS.md § Key Conventions § CLI codifies the "do not extend" rule. ~5 new tests; ~½ day implementation. Tracking row stays at PC.7 below. Awaiting approval before prompt + execute.)
>
> Earlier line: 2026-05-09 (Plan 10c AUTHORED — first-time setup ergonomics paper cut: `nix develop` NAAVIK_PERSISTENCE=db parity (10c.1) + login signup-link promotion + signup-disabled banner gated on `users_exist AND not allow_multiple_users` (10c.2) + `naavik dev creds [--shred]` CLI subcommand + lifespan credential echo (10c.3). Goal: a fresh self-hoster signs in within 30 s of `nix run .#dev` without reading docs. Tracking row added as PC.7 below. ~6 new tests; < 1 day implementation. Awaiting approval before prompt + execute.)
>
> Earlier line: 2026-05-03 (Wave 5 / plan 10 § C EXECUTED + plan 10b EXECUTED — Phase-1 finalization paper cuts shipped: orchestrator greenlet/`LD_LIBRARY_PATH` fix + `NAAVIK_PERSISTENCE=db` default, working dev credential via `NAAVIK_DEV_PASSWORD` env or random, `POST /api/v1/auth/signup` with single-user gate via new `Settings.allow_multiple_users` field (Alembic 0002), `naavik` CLI subcommands (`init` / `vault status` / `vault rotate-key`), Settings · LLM Provider form-wiring with provider-aware swaps, Settings · Deployment vault-locked banner, README first-time-setup + signup + troubleshooting rewrite. 475 tests pass (~12 new beyond 10's 448 baseline), ruff clean. Phase 1 ✅ Complete and end-to-end testable. Next: `docs/plans/POST_PHASE_1.md` § "Phase 1 testing playbook" → Phase 2-6 plans 11–15.)
>
> Earlier line: 2026-05-02 (Plan 10a EXECUTED — Pre-Phase-2 paper cuts shipped: PC.1 sync alembic env.py + psycopg + flake.nix `--no-sync`/stdin/PYTHONPATH defenses; PC.2 root-`app.py` shim; PC.3 NixOS-friendly playwright + 20-PNG baseline.)
>
> Earlier line: Wave 4 / Backend Wave 3 / plan 10 § B EXECUTED — backend substrate live: 20 SQLModel entities + Alembic + bcrypt+JWT+CSRF auth + AES-256-GCM vault + LLM provider abstraction + 10 prompt skeletons + cost-tracking via ApiUsage + profile/settings/ats_credentials services + per-field profile autosave + DB-backed Settings + `NAAVIK_PERSISTENCE=db` env var for accessor swap + sequence-bumping seed + rotate-key CLI; 348 memory-mode tests + 6 live-DB seed tests pass; ruff clean; security-review checkpoints 1+2+4 written. Plan 10 § B status → WAVE 3 EXECUTED · Wave 6 awaiting.
>
> Earlier line: single-tracking consolidation — all task / backlog / plan-mapping moved here per `AGENTS.md` § Single-doc-tracking principle. Plans 11–15 mapped to Phase 2–6 headers. Pre-Phase-2 paper cuts inlined. Phase 1.x deferred items table is now the canonical extended backlog. Wave 3 / plan 09 EXECUTED + plan 09a EXECUTED + 09a follow-up shipped — 269 tests passing.
>
> **Companion doc:** `docs/plans/POST_PHASE_1.md` — operational guide only (testing playbook, authoring workflow, monitoring, success criteria). All task tracking lives here in ROADMAP.
>
> **This is the single source of truth for project progress.** Phases describe the long arc; per-phase wave/task tables are checked off as work lands. The master plan (formerly `docs/plans/02-mvp-master-plan.md`) is archived — its content lives here, in `AGENTS.md` § Workflow, and in the active session-continue prompt at `docs/prompts/00-session-continue.md`.

## Maintenance

This doc is **tracking-only** (per AGENTS.md § Single-doc-tracking). The maintenance rules live in **`AGENTS.md` § Roadmap Maintenance Rules** — read once, follow always. Quick summary:

- `[ ]` → `[~]` on start. `[~]` → `[x]` + deliverable note on completion.
- Edit the table directly when scope changes — don't bury in commits.
- Bump "Last updated" on every meaningful edit.
- **GitHub Project mirror:** the agent system mirrors this onto GitHub Project #4. See § Agent System (mirror conventions) below. Sync via `.claude/naavik-ops gh sync --apply` after ROADMAP edits.

Pointers for content that USED to be in this doc (carved 2026-05-16 to keep ROADMAP tracking-only):

| Was here | Now lives in |
|---|---|
| Vision + Competitive Context | `README.md` § What is Naavik? + § Why Naavik? |
| Architecture diagram + Tech Stack table + Design decisions | `docs/ARCHITECTURE.md` |
| Data Model sketches | `docs/design/DATA_MODEL.md` (canonical) |
| Repository Structure tree | `docs/ARCHITECTURE.md` § 3 layer responsibilities |
| Deployment (4 paths) | `docs/DEPLOYMENT.md` |
| n8n Migration Strategy | `docs/ARCHITECTURE.md` § 4.7 External integrations |
| Portfolio Integration | `docs/ARCHITECTURE.md` § 4.7 External integrations |
| UI Screens & Design narrative | `docs/design/SCREENS.md` + `DESIGN.md` + `docs/design/WORKFLOW.md` |


---

## Priority Queue (derived view — post-A.29)

**Replaced by `.claude/naavik-ops task next-unblocked 0.2.0` derived view** per A.29 D.13 caller-rewrite scope. The canonical "what should I work on next" surface is now release-version-grouped (`0.2.0` is the active release; `0.1.0` shipped; `0.1.1` queued; `0.2.X` thematic patches interleave with `0.2.0`).

Sort key per `docs/design/PHASE_NUMBERING.md` § 1: **release-version ASC → priority DESC (HIGH > MED > LOW > unset) → position ASC**, gated by deps. The two HIGH markers under `0.2.0` are `0.2.0.01` (vault deprecation, Tier-2 wave 1) and `0.2.0.05` (SQLModel Job models, hard dep for every scraper). All other `0.2.0.NN` tasks are equally required for the `0.2.0` cut.

**Maintenance:** drift-free by construction — `naavik-ops task next-unblocked <version>` reads `.claude/github-issue-map.json:issues` + `:priorities` + `:deps` and emits the sorted view on demand. Manager invokes it at every gate transition; `/standup` consumes it. The canonical source remains the per-release tables below.

---

## Phases

### 0.1.0 — Foundation + MVP + Pre-Phase-2 paper cuts + Phase A bootstrap (legacy Phase 0 + Phase 1 + PC + A.1–A.29)
> **Goal:** First full Naavik bundle — reproducible dev environment + 11-screen MVP UI + backend substrate + 6-subagent system + this A.29 phase-numbering migration.
> **Status:** ✅ Complete (cut as `0.1.0` tag during Wave 5 of A.29 PR).
> **Shipped:** 2026-05-18 (A.29 migration apply; legacy phases shipped 2026-04-25 through 2026-05-18).
> **Plan archive:** `docs/plans/archive/01-…` through `docs/plans/archive/24-…`.
> **Position cap rule:** D.1 Option B collapse — Phase 1's 5 Waves fold to 14 deliverable-level positions; sub-task detail preserved in `docs/plans/archive/10-backend-impl.md` and Notes-column prose. 48 of 99 slots used; 2 reserved (0.1.0.48–0.1.0.49) for future micro-fixes before tag cut.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.1.0.01 | Nix flake: devShell with Python 3.12, uv, typst, postgresql, ruff, pre-commit hooks | [x] | — | 0.1 | `nix/devshell.nix` — verified all tools available in `nix develop` |
| 0.1.0.02 | pyproject.toml + uv lockfile with all Python deps | [x] | — | 0.2 | 56 packages installed via `uv sync` |
| 0.1.0.03 | Dockerfile (multi-stage, uv-based, Python 3.12 slim) | [x] | — | 0.3 | Builder + runtime stages, typst in runtime |
| 0.1.0.04 | Docker Compose: FastAPI app + PostgreSQL (pgvector/pgvector:pg17) | [x] | — | 0.4 | Health check on db, app depends on healthy db |
| 0.1.0.05 | NixOS service module (`nix/module.nix`) — Lumino-compatible | [x] | — | 0.5 | Reads `settings.servicesConfig.apps.tools.naavik`, full systemd hardening, SOPS, Traefik, PostgreSQL ensure |
| 0.1.0.06 | Nix package derivation (`nix/package.nix`) | [x] | — | 0.6 | `nix build` produces `result/bin/naavik`, typst wrapped in PATH |
| 0.1.0.07 | FastAPI app skeleton — main.py + config.py + db/session.py + static files + Jinja2 templates | [x] | — | 0.7 | Sidebar drawer layout (Tailwind + DaisyUI + HTMX), dashboard placeholder, 5 nav stubs |
| 0.1.0.08 | Alembic setup (async, reads DATABASE_URL from settings) | [x] | — | 0.8 | `migrations/env.py` uses async_engine_from_config |
| 0.1.0.09 | .env.example with all env vars documented | [x] | — | 0.9 | DATABASE_URL, SECRET_KEY, all LLM keys, OAuth, integrations |
| 0.1.0.10 | Phase 1 Wave 1 — 5 design docs graduated (COMPONENTS + BACKEND + DATA_MODEL + INTERACTIONS + SAMPLE_DATA) | [x] | — | Phase 1 Wave 1 | Plans 03–07 GRADUATED + archived; ~5300 lines of canonical contract; DESIGN.md bumped v1.3 (DRAFT row added) |
| 0.1.0.11 | Phase 1 Wave 2 — 85-component partial library + base.html + macros + base.js + `/_design/components` fixture page | [x] | — | Phase 1 Wave 2 | All 100 tests pass; `docs/plans/archive/08-stage-2-impl.md` |
| 0.1.0.12 | Phase 1 Wave 3 — 11 page templates + sample_data accessors + stub fragment/JSON endpoints + Discover keyboard map + Playwright snapshots | [x] | — | Phase 1 Wave 3 | All screens render at desktop + mobile; `docs/plans/archive/09-stage-3-impl.md` |
| 0.1.0.13 | Phase 1 Wave 3a — Stage 3 bugfix + Discover redesign triage (Lucide diagnostics, sidebar mobile drawer, typed application questions, scroll-spy, native dialog backdrop, touch swipe) | [x] | — | Phase 1 Wave 3a | `docs/plans/archive/09a-stage-3-bugfix.md` |
| 0.1.0.14 | Phase 1 Wave 4 — 20 SQLModel entities + Alembic 0001_initial + pgvector extension + 25 model tests | [x] | — | Phase 1 Wave 4 (substrate) | `docs/plans/archive/10-backend-impl.md` § B |
| 0.1.0.15 | Phase 1 Wave 4 — Auth (bcrypt + JWT + CSRF + rate limit) + AES-256-GCM vault + key rotation CLI + Settings · Deployment vault-locked banner | [x] | — | Phase 1 Wave 4 (auth+vault) | 18 auth tests + 22 vault tests; cost=12 prod / cost=4 tests; HS256 JWT; HttpOnly+Secure+SameSite=Strict cookies |
| 0.1.0.16 | Phase 1 Wave 4 — LLM provider abstraction (Anthropic + OpenAI + Ollama) + structured-output retry policy + 10 prompt skeletons + `ApiUsage` cost tracker | [x] | — | Phase 1 Wave 4 (LLM) | Anthropic tool-use / OpenAI json_schema / Ollama JSON mode; `tracked_call` wraps every provider call; 15 tests |
| 0.1.0.17 | Phase 1 Wave 4 — Profile + Settings services + per-field autosave + `NAAVIK_PERSISTENCE=db` DB-backed accessor swap (12 high-traffic accessors) | [x] | — | Phase 1 Wave 4 (services+swap) | DB-backed CRUD per tab; PUT /api/v1/settings/llm flows API key through vault |
| 0.1.0.18 | Phase 1 Wave 4 — `db/seed.py` consuming `db/sample_data.py` (idempotent ON CONFLICT DO NOTHING) + `ats_credentials` service | [x] | — | Phase 1 Wave 4 (seed) | 372 rows seeded across 20 entities; bumps every PK sequence after seed; CLI `uv run python -m db.seed` |
| 0.1.0.19 | Phase 1 Wave 5 — `extraction` service (PDF → AI → Profile + SSE event emission) | [x] | — | Phase 1 Wave 5 (extraction) | `services/extraction.py` — PDF parse via pypdf + LLM `extract_resume` + SSE generator |
| 0.1.0.20 | Phase 1 Wave 5 — `document_generator` (bullet selection + AI trim + Typst compile + native page-count validation + DRAFT reuse heuristic) + Typst templates (`onepage.typ`, `cover_letter.typ`) + native page-count validator | [x] | — | Phase 1 Wave 5 (doc-gen) | NEU-style 1-page resume + 4-section letter; both with `<naavik-meta>` page-count label; `typst query <input.typ>` (the spec'd `--emit metadata` flag doesn't exist in 0.14) |
| 0.1.0.21 | Phase 1 Wave 5 — `application_service` (DRAFT lifecycle + submit/discard + ATS dispatch + `validate_submittable` + `process_auto_apply_queue`) + multi-axis state derivation | [x] | — | Phase 1 Wave 5 (application) | Full DRAFT lifecycle + computed-state ownership + 25 unit tests |
| 0.1.0.22 | Phase 1 Wave 5 — `notifications` (Discord webhook + Telegram outbound + in-app toast routing) + `portfolio_sync` (public CV API + filtered + debounced regen + Netlify webhook) | [x] | — | Phase 1 Wave 5 (notif+portfolio) | Discord embed + Telegram + toast queue; Allowlist-based portfolio filter + post-condition assert + 30 tests |
| 0.1.0.23 | Phase 1 Wave 5 — ATS adapters (Greenhouse + Lever + Ashby; Workday / LinkedIn / Indeed / Generic deferred to 0.2.3) + APScheduler cron registration (auto_apply / aggregate_costs / cleanup_stale_docs / daily_db_snapshot / refresh_oauth_tokens) | [x] | — | Phase 1 Wave 5 (ATS+cron) | All 3 adapters with public APIs + factory + 18 mock-HTTP tests; APScheduler with PostgresJobStore lifespan-managed |
| 0.1.0.24 | Pre-Phase-2 paper cut — Process-compose: confirm app logs + cold-start reliability | [x] | — | PC.1 | **Plan 10a (2026-05-02 + orphan-fix 2026-05-03):** `setsid -w` + `coreutils` + `pkill` cleanup; root cause was TTY/SIGTTIN not alembic async wedge |
| 0.1.0.25 | Pre-Phase-2 paper cut — `uv run fastapi dev` (no path) should just work | [x] | — | PC.2 | **Plan 10a:** 2-line `app.py` shim at repo root re-exports `src.main:app` |
| 0.1.0.26 | Pre-Phase-2 paper cut — Playwright local capture on NixOS | [x] | — | PC.3 | **Plan 10a:** `nodejs_22` + `PLAYWRIGHT_NODEJS_PATH`; Playwright pinned `>=1.58.0,<1.59`; 20 baseline PNGs committed |
| 0.1.0.27 | Pre-Phase-2 paper cut — Phase-1 finalization (orchestrator greenlet/libstdc++ + NAAVIK_PERSISTENCE=db default + working dev credential + signup endpoint + `naavik` CLI subcommands + Settings · LLM Provider form-wiring + README rewrite) | [x] | — | PC.4 | **Plan 10b EXECUTED 2026-05-03** — 9 paper cuts shipped; 475 tests pass (~12 new); ruff clean |
| 0.1.0.28 | Pre-Phase-2 paper cut — `SECRET_KEY` boot-time enforcement | [x] | — | PC.5 | **Plan 17 EXECUTED 2026-05-16 via PR #49** — `Settings._enforce_secret_key` validator at `src/config.py:45-66` refuses module import when `SECRET_KEY` is shipped default or <32 bytes unless `NAAVIK_DEBUG=1` |
| 0.1.0.29 | Pre-Phase-2 paper cut — Password complexity (min 12 chars, digit + letter) + must-change-on-first-login flag | [x] | — | PC.6 | **Plan 18 EXECUTED 2026-05-17 via PR #50** — `validate_password_complexity` + `User.must_change_password` (alembic `0003`) + `require_password_complete` dep + `POST /api/v1/auth/change-password` + cookie/CSRF rotation + dev-credential file cleanup on rotation |
| 0.1.0.30 | Pre-Phase-2 paper cut — First-time setup ergonomics (`NAAVIK_PERSISTENCE=db` parity + login signup-link promotion + signup-disabled banner + persisted `~/.naavik/dev-credentials` + lifespan credential echo) | [x] | — | PC.7 | **Plan 10c EXECUTED 2026-05-12** — three sub-items shipped; 478 tests pass (3 new pages tests + 2 new live-DB seed tests); new config field `Settings.debug` |
| 0.1.0.31 | Phase A — 6 subagent prompts (`.claude/agents/`) | [x] | — | A.1 | Frontmatter (name/description/tools/model/color) + body (principles, operating loop, tracing format, escalation); models: manager+architect+hacker on opus-4-7; engineer+devops+designer on sonnet-4-6 |
| 0.1.0.32 | Phase A — 13 slash commands (`.claude/commands/`) | [x] | — | A.2 | `/build`, `/plan`, `/discuss`, `/triage-bug`, `/review-pr`, `/threat-model`, `/design-screen`, `/groom`, `/standup`, `/bootstrap`, `/sync-roadmap`, `/budget`, `/runs` |
| 0.1.0.33 | Phase A — `.claude/naavik_ops/gh.py` Projects v2 helper | [x] | — | A.3 | `init` / `bootstrap` / `sync` / `milestone-status` / `add-item` / `create-issue` / `set-status` / `next-unblocked` / `runs`; idempotent; user-or-org auto-detected |
| 0.1.0.34 | Phase A — Token budget config + ledger | [x] | — | A.4 | `.claude/budget.json` (caps) + `.claude/budget-ledger.json` (manager-managed); halt at projected-spend-exceeds-cap; `/budget` to inspect |
| 0.1.0.35 | Phase A — Trace system + `watch.sh` (tmux) + `runs.log` index + `MANIFEST.json` per run | [x] | — | A.5 | Run-id format `YYYY-MM-DDTHH-MM-SS_<6hash>`; per-agent log format frozen in each agent's prompt; `/runs` to list history |
| 0.1.0.36 | Phase A — `docs/AGENT_OPS.md` — single operational guide | [x] | — | A.6 | Bootstrap → daily workflow → commands reference → agent reference → GitHub Mirror conventions → tracing → budget → troubleshooting → extending |
| 0.1.0.37 | Phase A — `.github/` templates (3 Issue forms + PR template) | [x] | — | A.7 | PR template aligns with AGENTS.md § Workflow step 7 (deviations summary required) |
| 0.1.0.38 | Phase A — First end-to-end `/build` shipping a real paper cut (satisfied via PC.5 PR #49) | [x] | — | A.8 | 5 skills invoked; git `prepare-commit-msg` hook auto-appended `Closes #7`; deviations promoted into plan 17; plan archived. Manager → architect → engineer → hacker → devops → ROADMAP update → Issue close → Project advance loop exercised |
| 0.1.0.39 | Phase A — Agent system v2 (cold-start hook + per-agent skill suite + git commit automation) | [x] | — | A.11 | **Plan 16 EXECUTED 2026-05-17** — `.claude/hooks/cold-start.sh` SessionStart + `.claude/skills/naavik-cold-start/SKILL.md` + Skill tool on all 6 agents + `.claude/hooks/git/prepare-commit-msg` auto-`Closes #N` + 29-skill per-agent suite |
| 0.1.0.40 | Phase A — Map cache + single-writer governance (gh-project.sh hardening) | [x] | — | A.12 | `find_issue_by_prefix` + `ensure_milestone` consult `.claude/github-issue-map.json` first; new `refresh-map` subcommand reconciles from authoritative GitHub state; duplicate epics #46/#47 closed; "GitHub state — single writer" rule codified |
| 0.1.0.41 | Phase A — Tracing contract ERROR + BUILT/REVIEWED event family + MANIFEST schema extensions | [x] | — | A.13 | `ERROR step=<what> kind=<retry\|skip\|halt\|pivot> reason='<line>' attempt=<n>/<max>` + `BUILT` / `REVIEWED` last-line summaries; MANIFEST gains `outcome` / `halt_reason` / `what_built` / `errors_encountered` |
| 0.1.0.42 | Phase A — Task Playbook (`docs/PLAYBOOK.md`) — strict 9-category if-then classification | [x] | — | A.14 | **Shipped 2026-05-17 via PR #51 squash `ab9f2589`** — STATUS / INSPECT / 3 gate responses / PRODUCT_WORK / BUG_TRIAGE / CONTRACT_CHANGE / BOOKKEEPING; default-deny allow-list-only for BOOKKEEPING |
| 0.1.0.43 | Phase A — Agent memory + learning system | [x] | — | A.15 | **Plan 19 EXECUTED 2026-05-17 via PR #53** — `.claude/memory/` substrate (6 stores) + single-writer `.claude/naavik_ops/memory.py` + 4 memory-aware skills + 2 slash commands (`/memory`, `/learn`); 50/50 smoke pass |
| 0.1.0.44 | Phase A — Machine-readable wording rewrite of agent-system files | [x] | — | A.16 | **Plan 22 EXECUTED 2026-05-18 via PR #68** — 57 files rewritten; -9.7% / ~-8.5k tokens per ingest cycle |
| 0.1.0.45 | Phase A — `agent-memory.sh` hardening (flock + jq sandbox + alias regex + manifest escape) | [x] | — | A.17 | **Plan 21 EXECUTED 2026-05-18 via PR #66** — 5 hacker findings closed; 30/30 concurrent writes persist (was 13/30 pre-fix); 14 new test assertions |
| 0.1.0.46 | Phase A — `agent-memory.sh` alias regex widening to include uppercase tokens | [x] | — | A.17a | **EXECUTED 2026-05-18 via PR #68 (A.16 fold-in)** — `ALIASES_RE` widened at `.claude/naavik-ops memory:119`; uppercase + `#` accepted; newline + `---` injection still blocked |
| 0.1.0.47 | Phase A — Board restructure (Backlog status + Phase 2.5 milestone + Priority Queue section) | [x] | — | A.28 | **Plan 20 EXECUTED 2026-05-17 via PR #63** — 5 waves; `Backlog` status added to Project v2; `Phase 2.5` milestone + epic created; ROADMAP surgery; `manager-backlog-promote` skill |
| 0.1.0.48 | (reserved buffer slot) | — | — | — | Reserved for post-A.29 micro-fixes before 0.1.0 tag cut |
| 0.1.0.49 | (reserved buffer slot) | — | — | — | Reserved for post-A.29 micro-fixes before 0.1.0 tag cut |
| 0.1.0.50 | Phase numbering system + `.claude/naavik-ops` Python dispatcher — 4-level semver task IDs replace Project Priority field; full retroactive renumber + release ceremony tooling | [x] | HIGH | A.29 | **Plan 24 EXECUTED 2026-05-18 via PR #73 squash `c5ac58f`** — Waves 1-4 shipped; Wave 5 (migration `--apply` + `0.1.0` release cut) runs post-merge per this diff patch + `step_7_rewrite_roadmap()` in `.claude/migrations/A.29-phase-renumber.py`. **This row is the closer for 0.1.0** — running `.claude/naavik-ops release cut 0.1.0` after Wave 5 cuts the first `0.1.0` tag |

**Deliverable (0.1.0):** Reproducible dev environment + 11-screen MVP + 20-SQLModel-entity backend substrate + 3 ATS adapters + Typst PDF generation + 6-subagent system + agent memory substrate + machine-readable rewrite + board restructure + this A.29 phase-numbering migration. Tag cuts in Wave 5 via `.claude/naavik-ops release cut 0.1.0`. Closes `Phase A` + `Pre-Phase-2 paper cuts` + `Phase 1 deferred items` (whose rows distribute into `0.2.X` thematic patches) + `Phase 2.5` (whose rows defer to `0.7.0`) GitHub Milestones.

**Verification log (Wave 5 post-merge):**
- Migration script applies cleanly: `python .claude/migrations/A.29-phase-renumber.py --apply` exits 0.
- `.claude/naavik-ops task check` exits 0 (no ROADMAP-vs-Issue-title drift; pyproject.toml + nix/package.nix at `0.1.0`; latest tag `0.1.0`).
- `git tag --list 0.1.0` returns `0.1.0` (cut via `.claude/naavik-ops release cut 0.1.0`).
- All 50 ROADMAP-rows-becoming-`0.1.0.NN` have Issue titles rewritten from `[A.X]` / `[PC.X]` to `[0.1.0.NN]` per the migration runbook step 6.
- `.claude/github-issue-map.json:redirects` populated with every legacy ID → new ID mapping.

---

### 0.1.1 — Legacy bash → Python rewrite + CHANGELOG sanitization (legacy A.30 + A.31)
> **Goal:** Replace legacy bash (`scripts/gh-project.sh` 1469 LOC + `scripts/agent-memory.sh` 843 LOC + `scripts/roadmap_parser.py` 304 LOC) with native Python under `.claude/naavik_ops/`; harden CHANGELOG.md markdown escaping before future closed-Issue ingestion lands.
> **Status:** ✅ Complete (2026-05-19). Shipped via PR #91 squash `494ffae`; tag `0.1.1` + GH release published at https://github.com/crizzy9/naavik/releases/tag/0.1.1.
> **Plan:** `docs/plans/archive/25-0.1.1-bash-to-python.md`.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.1.1.01 | Python rewrite of legacy bash scripts (`gh-project.sh` 1469 LOC + `agent-memory.sh` 843 LOC + `roadmap_parser.py`) into `.claude/naavik_ops/` Python modules + full `scripts/` → `.claude/` migration | [x] | MEDIUM | A.30 | **EXECUTED 2026-05-19 via PR #91 squash `494ffae`** (closed Issue #72). 7 commits W0-W6: W0 `.gitignore` + plan 25 + fixture dir; W1 `lib/changelog.py` sanitize + `lib/roadmap.py` writer-half inline; W2 native `gh.py` rewrite (20 callable subcommands + 1 helper `get_issue()`); W3 native `memory.py` (A.17 jq sandbox byte-for-byte) + 5 mutating `task` ops (atomic 3-store mutation + rollback under `~/.naavik/naavik-ops.lock`); W4 ~34 caller rewrites + skill frontmatter cleanup; W5 delete `scripts/{gh-project.sh,agent-memory.sh,roadmap_parser.py}` + `tests/test_agent_memory.sh` + `tests/test_naavik_ops/test_{gh,memory}_wrapper.py` (-2616 LOC); W6 PR_REVIEW_GATE reviewer pairing `hacker + devops` → `hacker + architect` (folded-in contract refactor; new § PR review mode in `.claude/agents/architect.md`). Hacker: APPROVE_WITH_NOTES (2 LOW + 1 INFO, none exploitable; R11 jq sandbox + R12 close-issue argv validated). Devops: PASS 12/12 gates (zero regressions; 210 tests passing in `tests/test_naavik_ops/`). 2 engineer deviations promoted into archived plan (W3 column-order swap + W3 collision guard). Closes A.29 Deviation 1 (mutating subcommands stubbed). |
| 0.1.1.02 | CHANGELOG.md markdown sanitization — escape commit-msg bodies before `.claude/naavik_ops/lib/changelog.py:62` renders to released artifact | [x] | LOW | A.31 | **EXECUTED 2026-05-19 via PR #91 W1 commit `8657655`** (closed Issue #74). `ReleaseEntry.__post_init__` escapes CommonMark special chars + collapses whitespace + rejects CR; `parse_changelog` round-trip avoids double-escape via `ReleaseEntry.from_rendered`. 7 sanitize tests in `tests/test_naavik_ops/test_changelog.py`. Hacker LOW finding from PR #75 review: CommonMark escape regex covers 19/30 spec chars (missing `~`/`=`/`&`); setext-h2 (`---`/`===`) gap defused by whitespace collapse — documented as design intent, no fix needed. |
| 0.1.1.03 | Close stale pre-A.29 epic Issues using new `close-issue` helper | [x] | LOW | — | **EXECUTED 2026-05-19 post-merge bookkeeping** (closed Issue #90). 8 stale epics closed via `naavik-ops gh close-issue <N> --reason completed`: `#1 [Epic] Phase A`, `#6 [Epic] Pre-Phase-2 paper cuts`, `#9 [Epic] Phase 2`, `#22 [Epic] Phase 1 deferred items`, `#65 [Epic] Phase 2.5`, `#76 [Epic] 0.1.0` (release shipped 2026-05-18), `#77 [Epic] 0.1.1` (release shipped 2026-05-19). Permission system blocked raw `gh issue close` at PR #75 (single-writer rule); the new dispatcher subcommand from 0.1.1.01 W2 closes the architectural gap. |

**Deliverable (0.1.1):** Legacy bash scripts deleted; `.claude/naavik_ops/` becomes the sole agent-system tooling surface; `scripts/` reserved for project-wide use only; CHANGELOG.md safe against markdown injection.

---

### 0.2.0 — Job Scraping & Discovery (legacy Phase 2)
> **Goal:** Automated multi-source job discovery with AI extraction; vault deprecation + CLI sunset.
> **Status:** 🟡 Queued (post-0.1.0 tag cut).
> **Plan:** `docs/plans/11-phase-2-scrapers.md` (to be authored after Phase 1 ships). Splits cleanly into 11a (LinkedIn + Greenhouse + Lever + Ashby) and 11b (Workday + Indeed + Generic + n8n migration).
> **Implementation contract:** `docs/design/BACKEND.md` § J (scraping architecture), § I (cron catalog), § K (auto-apply pipeline). Wave 6 services + Phase 2 sub-prompts of plan 10.
> **Estimated effort:** 2–3 weeks.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.0.01 | **Vault deprecation → env-only secrets.** Delete `src/services/vault.py` (AES-256-GCM + PBKDF2 + lockfile + audit log) and the encrypted vault entirely. Switch to standard self-hosted-app pattern: secrets via env vars sourced from a gitignored `.env` (loaded by `nix develop:shellHook`, `flake.nix:devEnv`, and Docker Compose `env_file:`). Ship `.env.example` with all secret slots commented. **DB migration:** alembic 0003 drops `Settings.*_configured` booleans + `Settings.*_fingerprint` columns; secret presence becomes runtime-derived from env. **API surface:** `PUT /api/v1/settings/llm` becomes read-only — exposes "Anthropic configured via env: ✓ / ✗" without an input field. **UI:** drop the API-key input from `_settings_llm.html`; drop the vault-locked banner from `_settings_deployment.html`. **Files removed:** `src/services/vault.py`, `src/cli/vault.py`, `src/cli/init.py`, `tests/test_vault.py`, vault sections of `tests/test_cli.py`. **Operational surface gone:** `~/.naavik/secrets.enc{,.lock,.bak.*}`, `~/.naavik/key.bin`, `~/.naavik/logs/vault-audit.log`. **UX regression to flag in changelog:** rotating an LLM API key is now "edit `.env` + restart". | [x] | HIGH | 2.12 | **Plan 26 EXECUTED 2026-05-19 via PR #92 squash `b91f50b` (closes #20).** Shipped Alembic 0004 instead of 0003 (numbering aligned w/ existing migrations). Migration story: Option A (pure docs path — no shim, no script). Per locked decision recorded in `.claude/memory/decisions.jsonl` (`0.2.0.01-migration-story`). 8 commits W0-W5 + W6/W7/W8 delta. Reviewers cleared at APPROVE (hacker round-1 1 LOW + 2 INFO defer-recommendations; architect FULL spec match post-delta). 7 substantive deviations promoted into archived plan. **Blocks `0.2.0.02`** unlocked — CLI now collapses to `naavik serve` only. **`0.2.1.03` (Argon2id) auto-closes as moot.** |
| 0.2.0.03 | Broader `require_password_complete` gate — extend to `src/api/profile.py` + `src/api/settings.py` + `src/ui/routes/*` | [x] | — | PC.6a | **Plan 23 EXECUTED 2026-05-18 via PR #69 — FROZEN done position.** New `require_authed_session` wrapper in `src/services/auth.py:297-371` applied to **41 mutation routes** across `src/api/profile.py` (7) + `src/api/settings.py` (5) + `src/ui/routes/{settings 9, discover 9, outreach 8, tracking 1, email 1, integrations 2}`. 2 onboarding routes skipped. 13 new tests. Hacker APPROVE_WITH_NOTES (1 MEDIUM onboarding bypass → PC.6b → 0.2.0.04). |
| 0.2.0.04 | Onboarding bypass — `/api/v1/profile/from-extraction` lets flagged user replace real-JWT with fake-session (close hacker MEDIUM from PR #69) | [ ] | — | PC.6b | **Filed 2026-05-18 via PR #69 hacker review** (Issue #70). Fix = add no-existing-user precondition to `post_profile_from_extraction` (`src/ui/routes/auth.py:223`). Also addresses 3 hacker LOW non-blocking notes. ~20-30 min engineer. Must ship before any multi-user expansion. |
| 0.2.0.05 | SQLModel: Job, StatusHistory models + migration | [x] | HIGH | 2.6 | **Plan 27 EXECUTED 2026-05-19 via PR #95 squash `693bb1e` (closes #15).** Reframed from "StatusHistory" → `JobScrapeRun` (scrape-side observability; AppEvent already audits Application.status). Job hardened: 6 new cols + partial-unique constraint + 5 new enums (JobSource 10v / VisaRestriction 4v / RemotePolicy 4v / SeniorityLevel 7v / JobScrapeRunStatus 5v). New `src/services/job_service.py` (8 fns) + Alembic 0005. Graduated to `docs/design/JOB_MODEL.md` (470 LOC × 11 sections). 53 plan-27 tests + 731 full suite passing. Reviewers: architect APPROVE FULL spec match; hacker APPROVE_WITH_NOTES (1 MED + 2 LOW + 2 INFO — all forward-looking, filed as 0.7.0.15-0.7.0.19). 4 engineer deviations promoted to archived plan. **Unblocks `0.2.0.06`–`0.2.0.14`** (scraper chain). |
| 0.2.0.06 | Crawl4AI setup + generic scraper base class | [ ] | — | 2.1 | Replace Browserless |
| 0.2.0.07 | Site scrapers: LinkedIn (**guest API + Crawl4AI stealth; RSShub opt-in fallback** per `docs/design/research/LINKEDIN_SCRAPING.md` — revisit § 8 Revisit checklist before locking option into plan 11a), Workday, Greenhouse, Lever, Ashby, Indeed | [ ] | — | 2.2 | Port from n8n. LinkedIn cell wording shifted 2026-05-17 from the original "RSS via RSShub + guest API" after the architect option matrix landed; the matrix recommendation supersedes the original framing on plan 11a authorship. |
| 0.2.0.08 | AI job extraction: HTML → JobInfo (company, position, location, visa, salary, skills) | [ ] | — | 2.3 | Structured output |
| 0.2.0.09 | Job deduplication (URL-based + fuzzy title/company) | [ ] | — | 2.4 | |
| 0.2.0.10 | APScheduler: periodic scraping per source | [ ] | — | 2.5 | PostgreSQL job store |
| 0.2.0.11 | HTMX UI: job list with filters, job detail view | [ ] | — | 2.7 | |
| 0.2.0.12 | Discord + Telegram notifications for new jobs | [ ] | — | 2.8 | Port from n8n |
| 0.2.0.13 | Rate limiting + anti-detection (random delays, throttling) | [ ] | — | 2.9 | |
| 0.2.0.14 | Migrate existing n8n DataTable + Google Sheets data to PostgreSQL | [ ] | — | 2.10 | Seed script |
**Deliverable (0.2.0):** Jobs scraped on schedule, AI-extracted, deduplicated, shown in dashboard with notifications. Vault deprecated; secrets via `.env`; CLI removed.

---

### 0.2.1 — Security cleanup (legacy DEF security rows)
> **Goal:** Defer-bucket cleanup for security-themed paper cuts from Phase 1 (JWT signing-key rotation, OIDC stub, Argon2id, JWT denylist).
> **Status:** 🟡 Queued (post-0.2.0; can interleave).
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.1.01 | JWT signing-key rotation (multi-tenant cloud tier) | [ ] | — | DEF-13 | Phase 2+; single-key fine for self-hosted. From plan 10 Q7. |
| 0.2.1.02 | OIDC for self-hosted (Authentik / Keycloak / Okta) | [ ] | — | DEF-06 | Phase 2+. From SCREENS.md § Phase mapping > Deferred. |
| 0.2.1.03 | Argon2id vault upgrade (vs PBKDF2) | [x] | — | DEF-17 | **Auto-closed 2026-05-19 as moot — vault deleted in `0.2.0.01` (PR #92 squash `b91f50b`).** No PBKDF2 to upgrade to Argon2id; secrets now read from `.env` via pydantic-settings. Locked decision at PLAN_GATE for plan 26. From plan 10 Q6. |
| 0.2.1.04 | JWT denylist on password rotation (defense-in-depth for stolen pre-rotation JWTs) | [ ] | — | DEF-26 (was unfiled in Phase 1 deferred items table; gets DEF# here) | After successful `POST /api/v1/auth/change-password`, the OLD JWT remains valid for its natural TTL. A stolen pre-rotation JWT survives the rotation. Defense-in-depth fix: maintain a server-side denylist of invalidated `jti`s (or rotate the signing-key prefix per user). Lives in `services/auth.py` + a small DB table. **Filed 2026-05-17 (PR #50 hacker Finding 3).** Distinct from `0.2.1.01` (signing-key rotation, broader scope). |
| 0.2.1.05 | **CLI sunset** — depends on `0.2.0.01`. After vault deprecation ships, the only `naavik` subcommand left is `serve`; `init` / `vault status` / `vault rotate-key` are gone with the vault. Final cleanup: delete `src/cli/`, drop `[project.scripts] naavik = "cli.main:main"` from `pyproject.toml`, collapse the server entrypoint to `python -m main` or the Nix flake's `apps.default` output. Keep `naavik-alembic` (alembic's own CLI surface, not a Naavik feature). | [ ] |  | < 1 day after 0.2.0.01. Independent of scrapers (`0.2.0.06`–`0.2.0.14`). **Policy in AGENTS.md § Key Conventions § CLI:** do NOT extend the CLI in interim plans; new operator features ship in the UI. |
**Deliverable (0.2.1):** Self-hosted OIDC option + post-vault-sunset auth-hardening cleanup.

---

### 0.2.2 — UI cleanup (legacy DEF UI rows)
> **Goal:** UI polish + light mode + icon/sidebar stability paper cuts from Phase 1.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.2.01 | Light mode | [ ] | — | DEF-18 | Phase 6. From DESIGN.md. |
| 0.2.2.02 | Restore Lucide via CDN | [ ] | — | DEF-19 | Self-hosted at `/static/lucide.min.js` for now to fix "no icons render" issue. Production should serve from a CDN — investigate why unpkg failed (content-blocker / CSP / rate-limit), pick a stable URL or fallback chain, drop the local file. From plan 09a follow-up 2026-05-02. |
| 0.2.2.03 | Sidebar mobile-toggle reliability after navigation | [ ] | — | DEF-20 | Idempotent script guards fixed the most common failure mode; user reports it's "still kind of wonky" after navigating away. Repro on real device, isolate the remaining timing issue (likely Tailwind JIT vs HTMX swap order). Not a blocker. From plan 09a follow-up 2026-05-02. |
| 0.2.2.04 | Discover card max-w cap on ultra-wide screens | [ ] | — | DEF-21 | 09a-follow-up dropped the `max-w-7xl` page cap on Discover so the card fills available space. On 4K+ monitors the card may stretch >1500px and feel sparse — add a `2xl:max-w-[1400px]` cap if user feedback comes in. From plan 09a follow-up 2026-05-02. |

**Deliverable (0.2.2):** Light mode shipped; sidebar stable; Lucide CDN-served; Discover card width-capped.

---

### 0.2.3 — ATS / scraper cleanup (legacy DEF scraper rows)
> **Goal:** Long-tail ATS adapters (Workday/LinkedIn/Indeed/Generic) + scraping diagnostics that didn't make 0.2.0.07.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.3.01 | Workday / LinkedIn / Indeed / Generic ATS adapters (Greenhouse / Lever / Ashby shipped in 0.1.0.23) | [ ] | — | DEF-01 | Need credentials + Playwright + manual review queue. Greenhouse / Lever / Ashby ship in 0.1.0.23. From plan 10 § C.4. |
| 0.2.3.02 | Postmortem-on-failure: Playwright screenshot + AI summary on ATS failure | [ ] | — | DEF-03 | Surfaces in stuck-queue card; helps diagnose recurring CAPTCHA / field_mismatch. From this triage 2026-05-01. |
| 0.2.3.03 | LinkedIn proxy support | [ ] | — | DEF-15 | Phase 6+. From BACKEND.md § J.4. |

**Deliverable (0.2.3):** Full ATS coverage + scraper diagnostics + LinkedIn proxy hardening.

---

### 0.2.4 — Tracking cleanup (legacy DEF tracking rows)
> **Goal:** Tracking UI gap-fills + DRAFT-lifecycle hardening + manual-entry modal.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.4.01 | Stale-DRAFT cleanup cron (`admin.cleanup_stale_drafts`) | [ ] | — | DEF-02 | Auto-discard or auto-archive DRAFTs idle >30 days; otherwise queue accumulates. From this triage 2026-05-01. |
| 0.2.4.02 | Manual job entry modal (full) | [ ] | — | DEF-04 | `+ Add by URL` is the partial Phase 1 path. From SCREENS.md § Phase mapping > Deferred. |
| 0.2.4.03 | Application detail slide-over | [ ] | — | DEF-05 | Phase 2 introduces `/tracking/:id` route. From SCREENS.md § Phase mapping > Deferred. |
| 0.2.4.04 | `Show drafts` filter UI on Tracking | [ ] | — | DEF-08 | Endpoint stubbed in Wave 3; UI toggle Phase 1.x. From SCREENS.md § Tracking visibility rule. |
| 0.2.4.05 | Auto-apply immediate dispatch on right-swipe (vs current 5-min cron) | [ ] | — | DEF-10 | Refinement; user expectation may grow once auto-apply ships. From this triage 2026-05-01. |

**Deliverable (0.2.4):** Tracking UI feature-complete vs SCREENS.md spec; stale-DRAFTs auto-cleaned.

---

### 0.2.5 — Observability cleanup (legacy DEF observability rows)
> **Goal:** Cost-cap dashboard + submission-result analytics + rate-limit dial.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.5.01 | `Settings.scraper_aggressiveness` (rate-limit dial) | [ ] | — | DEF-11 | Phase 2+; default conservative. From this triage 2026-05-01. |
| 0.2.5.02 | Submission-result observability dashboard (failure-kind aggregates) | [ ] | — | DEF-16 | Phase 6 — helps user spot recurring board-side failures. From this triage 2026-05-01. |
| 0.2.5.03 | `Settings.daily_llm_cost_cap_usd` dashboard widget | [ ] | — | DEF-22 | Wave 6 ships the enforcement; visible cap-progress UI is a Settings polish item. From POST_PHASE_1 § Tier 3 (consolidated 2026-05-02). |

**Deliverable (0.2.5):** Operator-facing scrape + LLM cost + ATS-failure analytics dashboards.

---

### 0.2.6 — Tooling / paper-cut cleanup (legacy DEF tooling rows + A.28a)
> **Goal:** Pre-existing dev-experience papercuts (ruff cleanup, DB-test gating, NAAVIK_PERSISTENCE removal) + post-A.28 script hardening.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.6.01 | Onboarding offline retry buffer for autosave | [ ] | — | DEF-07 | Optional, not blocking MVP. From INTERACTIONS.md § H.3. |
| 0.2.6.02 | `ProfileAnswer` reuse cache (screener answer memory) | [ ] | — | DEF-09 | Phase 2+ entity. From DATA_MODEL.md § J. |
| 0.2.6.03 | Portfolio API versioning (`/api/portfolio/cv?version=v1`) | [ ] | — | DEF-12 | Lets crypticsoul.dev pin its consumer; Phase 2+. From this triage 2026-05-01. |
| 0.2.6.04 | `JobEmbedding` semantic match (pgvector) | [ ] | — | DEF-14 | Phase 6. From DATA_MODEL.md § H. |
| 0.2.6.05 | Full `NAAVIK_PERSISTENCE` env-var removal — migrate remaining ~20 lower-traffic accessors + page handlers to service-layer DB reads | [ ] | — | DEF-23 | Wave 4 partial-swap + Wave 5 partial-swap left ~20 accessors falling back to memory. Plan 10b sets `NAAVIK_PERSISTENCE=db` as orchestrator default, but the env var still gates the swap. Cleanup deserves its own plan once Phase 1 is fully verified. From this triage 2026-05-03 (post-Wave-5). |
| 0.2.6.06 | Pre-existing ruff errors in `migrations/` + `.claude/naavik_ops/lib/roadmap.py` (UP007 / UP035 / I001) | [ ] | — | DEF-24 | 10 ruff violations confirmed pre-existing via stash technique during A.15 PR review. Files: `migrations/versions/0001_initial.py` (4), `migrations/versions/0002_settings_multi_users.py` (4), `.claude/naavik_ops/lib/roadmap.py` (2). All fixable via `ruff check --fix`. ~30 min. From PR #53 devops review 2026-05-17 (Issue #55). |
| 0.2.6.07 | DB-test gating gap — 11 test files lack `_skip_if_no_db()` (asyncpg `InvalidPasswordError` on `localhost:5432`) | [ ] | — | DEF-25 | 65 pytest failures across 11 test files confirmed pre-existing via stash. Canonical pattern at `tests/test_settings_llm_form.py:17-25`. ~1h to propagate the helper. From PR #53 devops review 2026-05-17 (Issue #56). |
| 0.2.6.08 | `scripts/A.28-board-restructure.sh` hardening — eval pattern + rollback doc + apply default + ROADMAP § Agent System mirror-conventions 4-status refresh | [ ] | — | A.28a | **Filed 2026-05-17 via PR #63 hacker + devops review** (Issue #64). 3 LOW defense-in-depth findings in the migration runbook: (1) `run()` helper uses `eval` against composed string (line 54) — zero exploit today (all callers pass validated numeric Issue#s + node IDs), invites future bug if anyone interpolates Issue titles; fix = arg-array pass-through; (2) no rollback contract documented in header — script IS idempotent but recovery contract not stated; fix = 4-line comment; (3) `--apply` is silent default (lines 23-43) — bare invocation runs APPLY; fix = `DRY_RUN=true` default, require explicit `--apply`. Plus devops informational note. ~30 min engineer paper cut. **Folded to 0.2.6 (tooling/paper-cut) per theme match with rest of this patch's rows.** |

**Deliverable (0.2.6):** Repository-wide tooling cleanup; pre-existing CI/test gaps closed; script hardening complete.

---

### 0.3.0 — Intelligent Scoring & Matching (legacy Phase 3)
> **Goal:** AI compatibility scoring with tag-based profile matching and explainable results.
> **Status:** ⚪ Future.
> **Plan:** `docs/plans/12-phase-3-scoring.md` (to be authored after plan 11 ships).
> **Implementation contract:** `docs/design/BACKEND.md` § H.1 (`scorer` service), § M.3 (`score_job` prompt). DATA_MODEL.md § C (`Job.score`, `Job.score_explanation`, `Job.match_breakdown`).
> **Estimated effort:** 1–2 weeks.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.3.0.01 | Tag-based matching: job desc → identify tags → match against profile bullets | [ ] | — | 3.1 | |
| 0.3.0.02 | AI scoring: structured output (score 0-1, explanation, gap analysis) | [ ] | — | 3.2 | Cloud + local model support |
| 0.3.0.03 | Visa/sponsorship auto-filter (score 0 for citizenship-required / no-sponsorship) | [ ] | — | 3.3 | |
| 0.3.0.04 | Tailored resume preview: show which bullets selected/excluded for a job | [ ] | — | 3.4 | |
| 0.3.0.05 | One-click generation: from job detail → tailored resume + cover letter | [ ] | — | 3.5 | |
| 0.3.0.06 | Score history + analytics | [ ] | — | 3.6 | |
| 0.3.0.07 | HTMX UI: score card, match explanation, bullet selection preview | [ ] | — | 3.7 | |

**Deliverable (0.3.0):** Every job scored with explanation. User sees bullet selection preview and generates tailored docs in one click.

---

### 0.4.0 — Application Tracking & Auto-Apply (legacy Phase 4)
> **Goal:** Full application lifecycle with configurable automation level.
> **Status:** ⚪ Future.
> **Plan:** Most of Phase 4 ships inside plan 10 Wave 6 (DRAFT lifecycle, ATS submit, semi-auto + auto-apply paths). UI polish + analytics dashboard ship as a small follow-up `13a-tracking-polish.md` post-Phase-1.
> **Implementation contract:** `docs/design/BACKEND.md` § K (auto-apply + manual paths), § K.5 (ATS adapters per board), § L.1 (Gmail/Outlook OAuth). `docs/design/DATA_MODEL.md` § A multi-axis state, § E state transitions.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.4.0.01 | Application multi-axis state model: `status` (APPLIED → RECRUITER_SCREEN → ONSITE_LOOP → OFFER → CLOSED) + `closed_reason` + orthogonal sub-states `docs_state`, `referral_state`, `recruiter_state`, computed `outreach_engagement` | [ ] | — | 4.1 | State machine + transitions per axis. See `docs/design/DATA_MODEL.md` (plan 05) for authoritative definitions. |
| 0.4.0.02 | Manual application logger (form for external applications) | [ ] | — | 4.2 | |
| 0.4.0.03 | Semi-auto flow: generate docs → notification → human approves → submit → update status | [ ] | — | 4.3 | Default mode |
| 0.4.0.04 | Auto-apply flow: high-score jobs → generate → submit automatically (user setting, default OFF) | [ ] | — | 4.4 | Configurable threshold |
| 0.4.0.05 | Playwright form filling for supported boards (with optional review step) | [ ] | — | 4.5 | |
| 0.4.0.06 | Google Sheets sync (optional secondary view) | [ ] | — | 4.6 | Keep for shared tracking |
| 0.4.0.07 | Application analytics dashboard | [ ] | — | 4.7 | Response rate, interview rate, by company/role |

**Deliverable (0.4.0):** Full Kanban tracking. Semi-auto or auto-apply based on user preference. Analytics.

---

### 0.5.0 — Email Monitoring & Outreach (legacy Phase 5)
> **Goal:** Monitor emails, classify responses, manage interview prep, and track recruiter/employee outreach.
> **Status:** ⚪ Future.
> **Plans:** `docs/plans/13-phase-5-email.md` (Gmail/Outlook OAuth + classifier) → then `docs/plans/14-phase-5-outreach.md` (LinkedIn DM + Calendar + Discord/Telegram inbound). Both authored after plan 12 ships.
> **Implementation contract:** `docs/design/BACKEND.md` § L.1 (Gmail/Outlook), § L.2 (LinkedIn browser, account-ban risk), § L.3–L.5 (Discord/Telegram/Calendar), § H.1 (`email_classifier`, `outreach_generator`, `contact_tracker`).
> **Estimated effort:** Plan 13 1–2 weeks; plan 14 2–3 weeks (LinkedIn is the most fragile dep).

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.5.0.01 | Gmail API / IMAP email monitoring | [ ] | — | 5.1 | Connect to user's email inbox |
| 0.5.0.02 | AI email classification: INTERVIEW_REQUEST, REJECTION, OFFER, ASSESSMENT, FOLLOW_UP | [ ] | — | 5.2 | |
| 0.5.0.03 | Auto-update job status from email classification | [ ] | — | 5.3 | |
| 0.5.0.04 | Priority notifications (HIGH for interviews/offers) | [ ] | — | 5.4 | |
| 0.5.0.05 | Email thread tracking per application | [ ] | — | 5.5 | |
| 0.5.0.06 | AI draft response generation | [ ] | — | 5.6 | |
| 0.5.0.07 | Interview scheduling integration (Calendly/webhook) — surfaces on Tracking application detail and Overview priority actions | [ ] | — | 5.7 | |
| 0.5.0.08 | Interview prep: role-specific questions from job desc + profile gaps | [ ] | — | 5.8 | |
| 0.5.0.09 | LinkedIn connection tracker: store recruiter/employee contacts per company | [ ] | — | 5.9 | |
| 0.5.0.10 | Outreach template system: personalized messages for recruiters + employees | [ ] | — | 5.10 | Uses profile + job context |
| 0.5.0.11 | AI-generated outreach messages: referral requests, follow-ups, check-ins | [ ] | — | 5.11 | Tone-appropriate, not spammy |
| 0.5.0.12 | LinkedIn automation: send connection requests + messages via API | [ ] | — | 5.12 | Rate-limited, anti-detection. **Re-open `docs/design/research/LINKEDIN_SCRAPING.md` option matrix when authoring plan 14** — § 5 stack-rank flags stickerdaniel/linkedin-mcp-server (1.9k stars, Apache-2.0, Patchright-based) as the front-runner for the outreach surface because authenticated session is unavoidable here, unlike 0.2.0.07 where the guest API wins. |
| 0.5.0.13 | Outreach history tracking: sent messages, responses, acceptance rates | [ ] | — | 5.13 | |
| 0.5.0.14 | Warm intro finder: suggest mutual connections for warm outreach | [ ] | — | 5.14 | LinkedIn API |
| 0.5.0.15 | Interview process accelerator: auto-send thank-you notes, follow-up reminders | [ ] | — | 5.15 | |

**Deliverable (0.5.0):** Email inbox monitored → job statuses auto-updated. Recruiter/employee contacts tracked → AI-assisted outreach → referral requests sent at optimal timing.

---

### 0.6.0 — Optimization & Polish (legacy Phase 6)
> **Goal:** Performance, analytics, and advanced features.
> **Status:** ⚪ Future.
> **Plan:** `docs/plans/15-phase-6-polish.md` — splits cleanly into 15a (observability — Prometheus + Sentry + OTel), 15b (light mode), 15c (LaTeX template + ML scoring calibration). Author after plan 14 ships.
> **Implementation contract:** `docs/design/BACKEND.md` § N (observability — Prometheus, Sentry, OTel), `docs/design/DATA_MODEL.md` § H (`JobEmbedding` pgvector for semantic match), `DESIGN.md` (light mode tokens — Phase 6).
> **Estimated effort:** 3–4 weeks total (split across 15a/b/c).

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.6.0.01 | Resume A/B testing (track which variants get responses) | [ ] | — | 6.1 | |
| 0.6.0.02 | Semantic job matching with pgvector embeddings | [ ] | — | 6.2 | |
| 0.6.0.03 | Weekly summary reports | [ ] | — | 6.3 | |
| 0.6.0.04 | Performance: caching, batch AI calls, parallel scraping | [ ] | — | 6.4 | |
| 0.6.0.05 | ML scoring calibration from application outcomes | [ ] | — | 6.5 | |
| 0.6.0.06 | LaTeX template support alongside Typst (for users who prefer LaTeX) | [ ] | — | 6.6 | NEU template compat, latexmk/tectonic compilation |
| 0.6.0.07 | Additional Typst/LaTeX resume templates (modern, academic, creative) | [ ] | — | 6.7 | Template marketplace |

**Deliverable (0.6.0):** Observability stack live; light mode shipped; LaTeX template parity with Typst; ML-calibrated scoring.

---

### 0.7.0 — Agent-system follow-ups (legacy Phase 2.5)
> **Goal:** Quality-of-life improvements + nice-to-have agent-system features deferred until Phase 2 (job scrapers) clears. None blocks the product; all surfaced during Phase A bring-up.
> **Status:** ⚪ Future (deferred per user lock 2026-05-17; ships post-0.2.0 cycle clears).
> **Plan:** No single plan — each row gets its own plan when scheduled (post-Phase-2 user pickup).
> **Mirror milestone:** `0.7.0` (recreated by migration step 4; supersedes `Phase 2.5`).
> **Mirror epic:** `[Epic] 0.7.0`.
>
> User-locked scope decision 2026-05-17: A.22 carries HIGH priority within Phase 2.5 but still defers — Tier 1 / Tier 2 work clears first per pre-Phase-2 scope lock.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.7.0.01 | Cap retention on `traces/` (auto-delete runs > N days) | [ ] | — | A.9 | Today: manual delete. Add a `traces/.cleanup.sh` cron-style helper once accumulation gets noisy (>50 runs). |
| 0.7.0.02 | Visual run dashboard (web UI for `traces/runs.log`) | [ ] | — | A.10 | Nice-to-have. Current state: `claude /runs` + `./traces/watch.sh` cover the inspection use cases. |
| 0.7.0.03 | Architect-as-PR-reviewer (replaces devops in review role) | [ ] | — | A.18 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"moving forward i want the architect to review the PR and not the devops."* Rationale: architect's option-matrix lens fits PR reviews. Open: does devops stay for build-gate re-verify (ruff/pytest clean-shell) while architect does code-correctness + plan-fidelity, OR does devops fully exit PR-review duty? |
| 0.7.0.04 | Security review bar — Claude-Mythos-style depth | [ ] | — | A.19 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"there will be security review similar to the one that claude mythos provides."* Target: deeper STRIDE per-feature + supply-chain checks (dependency CVE scan, lockfile drift) + secret-rotation hygiene + auth-flow modeling + LLM prompt-injection vectors for scrapers. |
| 0.7.0.05 | PR review verdicts stored in repo (not only GitHub) | [ ] | — | A.20 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"the approved with notes is good but it should be stored in the repo not left on github."* Target: also persist to repo as `traces/<run-id>/pr-reviews/<pr-num>.md` AND/OR `docs/reviews/<pr-num>-<slug>.md`. Survives GitHub data loss; greppable history; works offline. Format: machine-readable per A.16 (now 0.1.0.44). |
| 0.7.0.06 | Progress indicator — flow visualizer like Jenkins pipeline | [ ] | — | A.21 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"somewhere in the PR or in claude code when im building it shows what step we are at."* Three candidate surfaces (architect picks): (a) PR body section auto-updated, (b) chat preamble line, (c) `.claude/current-step.json` file. ~1-2 engineer days. |
| 0.7.0.07 | Confusion-gate clause — ask user on ambiguity even in auto mode; technical decisions OK, business decisions always user | [ ] | HIGH | A.22 | **Filed 2026-05-17 — deferred until after Phase 2 (HIGH within 0.7.0 but cycle defer).** User directive: *"add a clause to always ask questions if the requirement is confusing or there are multiple paths forward."* Scope: extend `docs/PLAYBOOK.md` with explicit confusion-gate clause + decision-class taxonomy (technical vs business vs critical). |
| 0.7.0.08 | State-of-the-art security review tools (replace standard Claude Code hacker tooling) | [ ] | — | A.23 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"instead of using the standard claude code tools for security review."* Target: integrate SoTA SAST/DAST/SCA tools — Semgrep, CodeQL, Snyk/Trivy, gitleaks, pip-audit, OWASP ZAP, plus LLM-specific (prompt-injection detectors, jailbreak scanners). |
| 0.7.0.09 | State-of-the-art architect tools | [ ] | — | A.24 | **Filed 2026-05-17 — deferred until after Phase 2.** Target: add architecture-visualization + ADR tooling — Structurizr (C4 model), Mermaid (sequence + state diagrams, gh-native), PlantUML, diagrams.net, OpenAPI/AsyncAPI generators, dependency graph tools, ADR-tools. |
| 0.7.0.10 | State-of-the-art designer tools — wire huashu-design + similar | [ ] | — | A.25 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"for designer we are not using huashu design tooling. we need to use that."* Target: surface `huashu-design` as PRIMARY designer skill. |
| 0.7.0.11 | Trace analytics dashboard — simple metrics script | [ ] | — | A.26 | **Filed 2026-05-17 — deferred until after Phase 2.** Simple stdout script (`scripts/trace-analytics.py` or `scripts/agent-metrics.sh`) reads `traces/<run-id>/MANIFEST.json` × N + `traces/runs.log` and prints aggregate metrics. NOT a web UI (that's 0.7.0.02). Reads-only the trace logs. ~1 engineer day. |
| 0.7.0.19 | Tighten `JobCreate.source_url` type to `pydantic.HttpUrl` | [ ] | — | A.36 (hacker PR #95 INFO) | **Filed 2026-05-19** — hacker INFO on PR #95. URL validation at boundary catches malformed scraper output. Trivial fix; defer to 0.2.0.06+ when scrapers populate field. |
| 0.7.0.18 | `JobUpdate` schema should `exclude` the `score` field (computed by scoring pipeline) | [ ] | — | A.35 (hacker PR #95 INFO) | **Filed 2026-05-19** — hacker INFO on PR #95. Prevents accidental score overwrite via API. Trivial fix; defer to 0.3.0 scoring sub-task. |
| 0.7.0.17 | `JobScrapeRun.errors[]` ARRAY needs schema guard against secret leakage | [ ] | — | A.34 (hacker PR #95 LOW) | **Filed 2026-05-19** — hacker LOW on PR #95. Forward-looking: Phase 2 scrapers may capture exception messages with tokens/cookies/URL params. Add `_redact_url` helper + cap entries at 200 chars. Fix BEFORE 0.2.0.07 (site scrapers wire exception capture). |
| 0.7.0.16 | Tighten visa_restrictions backfill: replace `LIKE '%sponsorship%'` with exact-match SQL CASE | [ ] | — | A.33 (hacker PR #95 LOW) | **Filed 2026-05-19** — hacker LOW on PR #95. Migration backfill over-broad; misclassifies hypothetical no_sponsorship strings as candidate-friendly. Trivial SQL CASE rewrite; defer to 0.2.5 cleanup cycle. |
| 0.7.0.15 | Add `user_id` boundary check to `archive_job` / `restore_job` (IDOR pattern propagation) | [ ] | MEDIUM | A.32 (hacker PR #95 MEDIUM) | **Filed 2026-05-19** — hacker MEDIUM on PR #95. Mutating ops in `src/services/job_service.py:88-100` lack user_id scope. Non-exploitable today (no routes wire them); fix BEFORE 0.2.0.11 (UI wires routes). Plan should add scoped service helpers. |
| 0.7.0.14 | Fix 2 pre-existing pytest failures on main (`test_lazy_visit_shows_cta_no_draft` + `test_login_signup_mode_renders_signup_form`) | [ ] | — | A.31a (engineer deviation #4 from plan 27) | **Filed 2026-05-19** — discovered during plan 27 PR #95 dispatch. Both fail on a fresh `main` worktree, unrelated to job-models work. PR #95 deselects them for green-bar; this row tracks the proper fix. Likely flaky fixtures / state assumption. |
| 0.7.0.13 | Fix `task move` position-stability + add `gh clear-priority` + codify principle in 5 docs + restore 12 corrupted GH titles | [x] | MEDIUM | A.31 | **Plan 28 EXECUTED 2026-05-19 via PR #94 squash `70ee0d3` (closes #93).** Bug surfaced in run `2026-05-19T05-40-56_194aa5` when `task move 0.2.0.02 0.2.1.05` auto-renumbered ~10 sibling tasks. Shipped: (A) `cmd_move` gap-only on source + reject-on-collision on dest; (B) new `gh clear-priority` subcommand via `clearProjectV2ItemFieldValue` GraphQL mutation; (C) 5-doc codification of patch-position-stability principle; (D) 12 GH titles restored (`#62→[0.2.0.03]`, `#70→[0.2.0.04]`, `#15→[0.2.0.05]`, `#10→[0.2.0.06]`-`#19→[0.2.0.14]`; `#21` correctly at `[0.2.1.05]`). 4 commits W0-W3 + audit anchor; 217 tests passing (+8 new). Hacker APPROVE (2 INFO non-blocking); architect APPROVE FULL spec match (1 INFO naming). Memory knowledge entry at `.claude/memory/knowledge/patch-version-position-stability.md`. 3 deviations promoted to archived plan. |
| 0.7.0.12 | `develop` branch workflow — move PR target away from `main` | [ ] | — | A.27 | **Filed 2026-05-17 — deferred (user-flagged future move).** Action when scheduled: (1) create `develop` branch from `main`; (2) shift PR targets from `main` to `develop`; (3) keep `main` as release/stable + periodic `develop → main` promotion PR; (4) update PLAYBOOK + manager + repo settings. Open: BOOKKEEPING commits routing TBD. **Couples with A.29 release-tag implications** — release branches per MINOR? Release-branch promotion ceremony? A.27 owns the decision. |

**Deliverable (0.7.0):** Pickup queue for quality-of-life work after the scrapers ship. New rows added via `.claude/naavik-ops gh create-issue 0.7.0.NN "..." --milestone "0.7.0"`; rows graduate to active `0.2.X` or `0.3.0`+ release when scheduled.

---

## Agent System (mirror conventions)

> **Companion docs:** `docs/AGENT_OPS.md` (single operational guide), `AGENTS.md` § Agent System (workflow integration), `.claude/agents/` (full agent prompts), `.claude/commands/` (slash commands).
>
> **Reference guides loaded by agents on cold start:**
> - `docs/ROADMAP_OVERVIEW.md` — one-page roadmap digest (faster than this 800-line doc)
> - `docs/ARCHITECTURE.md` — layer responsibilities + cross-cutting concerns + pattern catalog
> - `DESIGN.md` (root) — visual contract (tokens, type, icons, voice; frozen) + `docs/design/WORKFLOW.md` — UI sub-process (skill routing, per-screen checklist, accessibility, common patterns, anti-patterns)
> - `docs/DEPLOYMENT.md` — 4 deployment paths + config + ops checklist
> - `docs/RUNBOOK.md` — devops runbook (known failure modes + diagnostic recipes + recovery)
> - `docs/plans/POST_PHASE_1.md` — testing playbook + monitoring + "when something goes wrong"
> - `docs/design/PHASE_NUMBERING.md` — 4-level semver schema + release ceremony + Conventional Commits (post-A.29)

This ROADMAP is mirrored onto a GitHub Project v2 board for queryability and assignability. **ROADMAP is authoritative** (per AGENTS.md § Single-doc-tracking); the Project is a one-way operational mirror. The mapping is mechanical (post-A.29):

| ROADMAP element | GitHub Project equivalent |
|---|---|
| `### <X.Y.Z> — <Name>` release header | Milestone `<X.Y.Z>` (description = `**Goal:**` line) |
| Task row in a release table | Issue titled `[<X.Y.Z.NN>] <description>`, body links back to ROADMAP |
| `[ ]` / `[~]` / `[x]` status | Project Status field: `Backlog` (deferred) / `Todo` / `In Progress` / `Done` |
| Priority column (`HIGH` / `MEDIUM` / `LOW` / unset; TASK-level only) | Project Priority single-select (4-level IDs only; never on 3-level patches/releases) |
| Release header | Project Milestone single-select (`0.1.0`–`0.6.0`, `0.1.1`, `0.2.1`–`0.2.6`, `0.7.0`) |
| Notes column | Issue body |
| Plan reference (`docs/plans/NN-name.md`) | Label `plan:<NN>` on the Issue |

**Sync flow:** always ROADMAP → Project. Manager updates ROADMAP first (mark `[~]` on start, `[x]` on done), then runs `.claude/naavik-ops gh set-status` to push to Project. `/sync-roadmap --apply` is the bulk reconcile. If the Project drifts from ROADMAP, the Project is wrong — never edit ROADMAP to match a stale board.

**Bootstrap:** `.claude/naavik-ops gh bootstrap [--apply]` parses ROADMAP's task tables and creates Milestones + Issues + Project items for the active releases (defaults to `0.2.0` + `0.2.1`–`0.2.6` + `0.7.0` open releases; closed `0.1.0` is skipped). See `docs/AGENT_OPS.md` § 2 for the full setup walkthrough.

**What to do as a plan / task author:**
1. Write the task row in ROADMAP first (status `[ ]`, with optional Priority on 4-level IDs).
2. Run `/plan <task-id>` — architect drafts the plan, opens the GH Issue (via `.claude/naavik-ops gh create-issue`), adds to Project, links back to ROADMAP.
3. Run `/build <release>` (or `/build "next"`) when ready to implement.

**What to do as an implementer:**
1. Mark the ROADMAP row `[~]` when starting.
2. Reference the Issue in commits: `Closes #<N>` in the last commit triggers GH's auto-close on merge.
3. Mark the ROADMAP row `[x]` + add a one-line deliverable note when done.
4. `/build` handles steps 1 + 3 automatically; manual implementers do them by hand.
