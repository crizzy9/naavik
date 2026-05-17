---
description: Promote engineer-deviations.log entries into the plan's `## Deviations from plan` section before archive, per `AGENTS.md § Workflow step 7`. Group by plan, verify each entry has what/why/impact/surface, propagate any new operational surface to README/CLAUDE/POST_PHASE_1. Use at plan archive time, when manager is about to flip a ROADMAP row to `[x]`, or when the user asks to archive a plan. Triggers on phrases like "archive the plan", "promote deviations", "before archive", "finalize the plan", "close out the milestone", "what shipped vs what we planned".
allowed-tools: Read, Edit, Write, Bash(jq:*), Glob
---

# manager-deviation-promote

`AGENTS.md § Workflow step 7` makes the `## Deviations from plan` section non-negotiable before any plan archives. The engineer writes one-liners into `traces/<run-id>/engineer-deviations.log` while implementing; the manager promotes those into the plan's structured Deviations section, fills the 4 dimensions (what / why / impact / surface), and propagates any new operational surface to user-facing docs. This is the contract that keeps plan archives honest.

## When to invoke

- Plan is implementation-complete (PR merged, ROADMAP row `[x]`, before moving to `docs/plans/archive/`).
- User asks to archive a plan / close out a milestone / "promote deviations".
- Pre-archive review of any plan in `docs/plans/` that doesn't yet have a `## Deviations from plan` section.

## What this skill does

1. **Read the deviations log.**
   ```bash
   cat traces/<run-id>/engineer-deviations.log
   ```
   Each line is the canonical format:
   ```
   [<ISO-timestamp>] DEVIATION plan=<docs/plans/NN-name.md> what=<one-line> why=<one-line> impact=<one-line>
   ```

2. **Group by plan.** A run may touch multiple plans (rare but possible — e.g. a plan execution that uncovers a paper cut and fixes both).

3. **For each plan,** verify each line has all 4 fields the AGENTS.md § Workflow step 7 contract requires:
   - **What changed** (one-line)
   - **Why** (root cause / constraint that forced it)
   - **Impact** on dependent plans / phases
   - **Surface** — any new env var / CLI command / on-disk path / port / schedule the implementation introduced (may be `none` if the deviation is internal)

   If a line is missing a dimension, fix it by inferring from engineer.log + the actual diff. Surface a question to the user if inference is ambiguous.

4. **Open the plan file** at `docs/plans/NN-name.md`. If it doesn't yet have a `## Deviations from plan` section, append one. If it does, append the new bullets to it (don't overwrite — earlier waves may have already written entries).

5. **Format each bullet** as:
   ```markdown
   - **<one-line title>** — what: <what>. why: <why>. impact: <impact>. surface: <surface or "none">.
   ```

   For multi-faceted deviations, use a sub-list:
   ```markdown
   - **<title>** — what: <what>. why: <why>.
     - impact: <impact on follow-up plans>
     - surface: <new env var / path / etc.>
   ```

6. **Propagate operational surface.** For any deviation with a non-"none" surface field, ensure it lands in the right user-facing doc(s) in the same change:

   | Surface type | Propagate to |
   |---|---|
   | New env var | `README.md` § Configuration + `.env.example` |
   | New CLI subcommand (fixes only — sunset rule!) | `README.md` § Operations |
   | New on-disk path / secret-handling rule | `CLAUDE.md` + `docs/plans/POST_PHASE_1.md` |
   | New port / cron schedule / runtime invariant | `CLAUDE.md` + `ROADMAP.md` "Last updated" bump |

   If the surface only matters to maintainers (e.g. NullPool engine choice in plan 10b), document in the plan's Deviations section and stop — no doc propagation.

7. **Verify before archive.** Re-read `## Deviations from plan` in the plan file. If you wrote "no material deviations", confirm that's actually true (rare — be skeptical). If the section is empty or missing, **do not archive**.

## Canonical references

- `AGENTS.md` § Workflow step 7 (the contract).
- `AGENTS.md` § "Documenting deviations — what counts, what doesn't".
- `CLAUDE.md` § "Deviations workflow — non-negotiable before archive".
- `docs/AGENT_OPS.md` § 7.2 — log format.
- `.claude/agents/engineer.md` § "Deviation tracking (mandatory)".

## When NOT to invoke

- Mid-implementation (engineer is still appending to the log).
- For trivial commit-level cleanups (variable renames, comment fixes) — those don't count as deviations per the filter in `AGENTS.md § "Not a deviation"`.
- Compaction events.

## Forbidden during invocation

- Do NOT archive a plan without a `## Deviations from plan` section. The check is binary.
- Do NOT write "no material deviations" if engineer-deviations.log has entries for this plan — that's revisionism.
- Do NOT bury an operational surface (env var, on-disk path) in the Deviations section only. It MUST also land in the user-facing doc per the table above. Operational drift is the #1 source of self-hoster pain (codified in `AGENTS.md § Documenting deviations`).
