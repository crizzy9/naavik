---
description: Promote engineer-deviations.log entries into the plan's `## Deviations from plan` section before archive, per `AGENTS.md § Workflow step 7`. Group by plan, verify each entry has what/why/impact/surface, propagate any new operational surface to README/CLAUDE/POST_PHASE_1. Use at plan archive time, when manager is about to flip a ROADMAP row to `[x]`, or when the user asks to archive a plan. Triggers on phrases like "archive the plan", "promote deviations", "before archive", "finalize the plan", "close out the milestone", "what shipped vs what we planned".
allowed-tools: Read, Edit, Write, Bash(jq:*), Glob
---

# manager-deviation-promote

`AGENTS.md § Workflow step 7` makes `## Deviations from plan` non-negotiable before plan archive. Engineer writes one-liners into `traces/<run-id>/engineer-deviations.log`; manager promotes into plan's structured section, fills 4 dimensions (what/why/impact/surface), propagates new operational surface to user-facing docs. This is the contract that keeps archives honest.

## When to invoke

- Plan implementation-complete (PR merged, ROADMAP `[x]`, before `docs/plans/archive/` move).
- User asks to archive plan / close milestone / "promote deviations".
- Pre-archive review of any `docs/plans/` plan lacking a `## Deviations from plan` section.

## Steps

1. **Invoke `naavik-ops plan archive`** (codified plan 39 / `0.7.0.21`). This is the canonical, single-writer entry point for any move from `docs/plans/` to `docs/plans/archive/`. The command lifts every matching `DEVIATION` line from `traces/<run-id>/engineer-deviations.log` into the plan's `## Deviations from plan` section using the canonical bullet shape (`- **<title>** — what: ... why: ... impact: ... surface: ...`), flips the frontmatter `Status:` to `EXECUTED`, performs the `git mv` (plus matching prompt sidecar under `docs/prompts/`), and STDOUTs a "Surface propagation required" block listing every operational surface the manager must land in user-facing docs in the same bookkeeping commit.

   ```bash
   .claude/naavik-ops plan archive docs/plans/<NN-name>.md
   #   optional flags:
   #   --run-id <id>                   pick a specific traces/<run-id>/ (default: latest)
   #   --no-material-deviations "X"    explicit-bypass; writes "No material deviations — X."
   #   --force                          archive even if section already non-empty
   #   --dry-run                        preview, no writes
   ```

   Exit codes: `0` = archived, `2` = refused (empty log + no override, or section conflict needing reconciliation), `1` = environmental error.

2. **Read what the command produced** (read-only):
   ```bash
   cat traces/<run-id>/engineer-deviations.log
   ```
   Canonical line:
   ```
   [<ISO-timestamp>] DEVIATION plan=<docs/plans/NN-name.md> what=<one-line> why=<one-line> impact=<one-line>
   ```

3. **Group by plan.** Run may touch multiple plans (rare — e.g. plan execution uncovering paper cut). Invoke `naavik-ops plan archive` once per plan.

4. **Verify 4 fields per line** (AGENTS.md § Workflow step 7 contract):
   - **What changed** (one-line)
   - **Why** (root cause / forcing constraint)
   - **Impact** on dependent plans / phases
   - **Surface** — new env var / CLI / on-disk path / port / schedule (`none` if internal-only)

   Missing dimension → manager hand-edits the section + re-runs with `--force`, OR AskUserQuestion to engineer.

5. **Bullet shape produced by the command** (matches `naavik-deviations-check § 3c`):
   ```markdown
   - **<one-line title>** — what: <what> why: <why> impact: <impact> surface: <surface or "none">.
   ```

   For multi-faceted entries the engineer should log two separate `DEVIATION` lines — one per concern — so each lifts to its own bullet.

6. **Propagate operational surface.** For each non-"none" surface the command flagged in STDOUT, land in the right user-facing doc(s) in the same bookkeeping commit:

   | Surface type | Propagate to |
   |---|---|
   | New env var | `README.md` § Configuration + `.env.example` |
   | New CLI subcommand (fixes only — sunset!) | `README.md` § Operations |
   | New on-disk path / secret-handling rule | `CLAUDE.md` + `docs/plans/POST_PHASE_1.md` |
   | New port / cron schedule / runtime invariant | `CLAUDE.md` + `ROADMAP.md` "Last updated" bump |

   Maintainer-only surface (e.g. NullPool engine choice plan 10b) → plan Deviations only, no propagation.

7. **Verify after archive.** Re-read the archived plan's `## Deviations from plan` section. `naavik-ops plan archive` refuses (exit 2) on empty sections, so a successful exit guarantees non-empty. If `--no-material-deviations` was used, be skeptical and confirm against the diff. `naavik-deviations-check` skill is the read-only verification wrapper.

## Canonical references

- `AGENTS.md` § Workflow step 7 (contract).
- `AGENTS.md` § "Documenting deviations — what counts, what doesn't".
- `CLAUDE.md` § "Deviations workflow — non-negotiable before archive".
- `docs/AGENT_OPS.md` § 7.2 — log format.
- `.claude/agents/engineer.md` § "Deviation tracking (mandatory)".

## When NOT to invoke

- Mid-implementation (engineer still appending).
- Trivial commit cleanups (renames, comment fixes) — `AGENTS.md § "Not a deviation"`.
- Compaction events.

## Forbidden during invocation

- Do NOT archive plan without `## Deviations from plan` section. Binary check.
- Do NOT write "no material deviations" if engineer-deviations.log has entries — revisionism.
- Do NOT bury operational surface (env var, on-disk path) in Deviations only. MUST also land in user-facing doc per table. Operational drift is #1 source of self-hoster pain (`AGENTS.md § Documenting deviations`).
