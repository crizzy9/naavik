---
description: Pre-archive verification that a plan at `docs/plans/NN-name.md` has a non-empty `## Deviations from plan` section per `AGENTS.md § Workflow step 7`. Flag empty / missing / "no material deviations" with skepticism (real plans almost always have deviations). Use before archiving any plan, at the close of any milestone, when manager prepares to mirror Project Status → Done. Shared cross-agent skill. Triggers on phrases like "deviations check", "is the plan ready to archive", "before archive", "deviations section", "no material deviations", "missing deviations", "pre-archive", "plan ready".
---

# naavik-deviations-check

`AGENTS.md § Workflow step 7` makes `## Deviations from plan` non-negotiable before plan archive. Empty section, missing section, or "no material deviations" all need scrutiny — real plans almost always diverge. Gating verification before any move from `docs/plans/` → `docs/plans/archive/`.

## When to invoke

- Manager about to archive plan (`docs/plans/NN-name.md` → `docs/plans/archive/NN-name.md`).
- End of any `/build` run, post-merge, before mirroring Project Status → Done.
- User asks to archive plan / finalize milestone.
- Pre-archive sanity on any open plan.
- Review of recently-archived plan for contract compliance.

## Steps

### 1 — Read plan

```
Read docs/plans/<NN-name>.md
```

### 2 — Confirm `## Deviations from plan` section exists

```bash
.claude/naavik-ops plan validate-deviations docs/plans/<NN-name>.md
```

Exit `0` = PASS (non-empty section present); exit `2` = BLOCK (missing OR empty). Wraps the binary contract; this is the canonical read-only check (codified plan 39 / `0.7.0.21`). Don't grep by hand — the subcommand handles both "no heading at all" and "heading with no bullets" uniformly.

On BLOCK, manager invokes `.claude/naavik-ops plan archive docs/plans/<NN-name>.md` (the canonical archive path) which lifts entries from `traces/<run-id>/engineer-deviations.log`. If the log is empty AND there is no material deviation, manager re-runs with `--no-material-deviations "<rationale>"` — skepticism applies.

### 3 — Inspect section content

Three checks:

**3a. Empty?** Heading w/ no bullets fails. BLOCK.

**3b. "no material deviations"?** Be skeptical. AGENTS.md:
> Use "no material deviations" if plan really shipped exactly as spec'd, but that's rare; reviewers should be skeptical when they see it.

Cross-check:
- Read `traces/<run-id>/engineer-deviations.log` for run that shipped this plan. Log has entries → section is lying. BLOCK.
- Eyeball diff: `git log --since='<plan start date>' --oneline -- <plan's file scope>`. Diff doesn't match plan spec exactly → deviations exist. BLOCK.
- Confirm plan's Approval checklist matches what shipped. Mismatches = deviations.

**3c. Bullets carry all 4 dimensions per AGENTS.md § Workflow step 7?**

Every bullet names:
- **What** changed (one-line)
- **Why** (root cause / constraint)
- **Impact** on follow-up plans
- **Surface** (new env var / on-disk path / CLI / port / schedule — or "none")

Missing dimensions = partial fail — flag for manager to fill via `manager-deviation-promote`.

### 4 — Verify operational surfaces propagated

For each non-`none` Surface bullet, confirm propagation to right doc per `manager-deviation-promote § 6`:

| Surface type | Must appear in |
|---|---|
| New env var | `README.md` § Configuration + `.env.example` |
| New CLI subcommand (fixes only — sunset!) | `README.md` § Operations |
| New on-disk path / secret-handling rule | `CLAUDE.md` + `docs/plans/POST_PHASE_1.md` |
| New port / cron schedule / runtime invariant | `CLAUDE.md` + `ROADMAP.md` "Last updated" bump |

Surface named but missing from propagation target → BLOCK archive. Whole point of step 7 = catch operational drift before archive.

### 5 — Emit verdict

**PASS:** plan has Deviations section, non-empty, all 4 dimensions per bullet, surfaces propagated.
```
PASS — plan ready to archive. Deviations: <N> bullets, <M> with operational surfaces (all propagated).
```

**BLOCK:** any failure. Specific reason + recommended fix.
```
BLOCK — <reason>. Recommended fix: <invoke manager-deviation-promote / propagate surface to README / etc>.
```

## Worked examples

### Pass

`docs/plans/10b-phase-1-finalization.md` § Deviations:

```markdown
## Deviations from plan

- **NullPool engine swap** — what: Engine switched from default pool to NullPool. why: greenlet bridge race under lifespan shutdown caused asyncpg connection wedge. impact: All future db code must import async_session_factory; documented in engineer-stack-invariants. surface: none (internal).

- **NAAVIK_PERSISTENCE env var** — what: Added `NAAVIK_PERSISTENCE={memory,db}` to switch between sample-data accessors and SQL accessors at boot. why: Allow dev parity testing w/o breaking memory-mode fast-iteration loop. impact: documented in README + CLAUDE; orchestrator sets to `db` automatically. surface: NAAVIK_PERSISTENCE in .env.example.
```

→ PASS: 2 bullets, all dimensions, NAAVIK_PERSISTENCE confirmed in README + CLAUDE + `.env.example`.

### Block

`docs/plans/10c-first-time-setup.md` has `## Deviations from plan` heading but empty body.

→ BLOCK: Section exists but empty. Recommended fix: invoke `manager-deviation-promote` against `traces/2026-05-12T_*/engineer-deviations.log`.

## Canonical references

- `AGENTS.md` § Workflow step 7 — contract.
- `AGENTS.md` § "Documenting deviations — what counts, what doesn't" — filter.
- `CLAUDE.md` § "Deviations workflow — non-negotiable before archive".
- `manager-deviation-promote` skill — promotion flow.
- `engineer-deviation-log` skill — source log format.

## When NOT to invoke

- Plan still active (`Status: DRAFT` or actively-being-implemented). Deviations live alongside implementation; check at archive, not mid-flight.
- Plan is `Type: design` and graduating (gets deviations once executed; graduation is separate gate).
- Compaction events.

## Forbidden during invocation

- Do NOT pass plan claiming "no material deviations" without verifying against `engineer-deviations.log` + actual diff. Real plans almost always have deviations.
- Do NOT archive plan with missing Deviations section. Binary contract.
- Do NOT skip operational-surface propagation check. Surface field catches self-hoster pain (`AGENTS.md § "Operational drift is the leading source of self-hoster pain"`).
- Do NOT silently fix deviations section by editing yourself — surface gap, let implementer (engineer / manager via `manager-deviation-promote`) write properly.
