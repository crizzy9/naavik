---
description: Pre-archive verification that a plan at `docs/plans/NN-name.md` has a non-empty `## Deviations from plan` section per `AGENTS.md § Workflow step 7`. Flag empty / missing / "no material deviations" with skepticism (real plans almost always have deviations). Use before archiving any plan, at the close of any milestone, when manager prepares to mirror Project Status → Done. Shared cross-agent skill. Triggers on phrases like "deviations check", "is the plan ready to archive", "before archive", "deviations section", "no material deviations", "missing deviations", "pre-archive", "plan ready".
---

# naavik-deviations-check

`AGENTS.md § Workflow step 7` makes the `## Deviations from plan` section non-negotiable before any plan archives. Empty section, missing section, or "no material deviations" all need scrutiny — real plans almost always diverge from spec. This skill is the gating verification, run before any move from `docs/plans/` → `docs/plans/archive/`.

## When to invoke

- Manager about to archive a plan (move from `docs/plans/NN-name.md` → `docs/plans/archive/NN-name.md`).
- End of any `/build` run, post-merge, before mirroring Project Status → Done.
- User asks to archive a plan / finalize a milestone.
- Pre-archive sanity check on any open plan.
- Reviewing a recently-archived plan for compliance with the contract.

## What this skill does

### Step 1 — Read the plan

```
Read docs/plans/<NN-name>.md
```

### Step 2 — Confirm a `## Deviations from plan` section exists

```bash
Grep "^## Deviations from plan" docs/plans/<NN-name>.md
```

**No match** → BLOCK archive. The contract is binary: no section, no archive. Tell the user / manager to invoke `manager-deviation-promote` skill to lift entries from `traces/<run-id>/engineer-deviations.log` into the plan.

### Step 3 — Inspect the section content

Read the section body. Check three things:

**3a. Is it empty?** A heading with no bullets fails the contract. BLOCK archive.

**3b. Does it just say "no material deviations"?** Be skeptical. The AGENTS.md contract explicitly notes this is rare:
> Use "no material deviations" if the plan really shipped exactly as spec'd, but that's rare; reviewers should be skeptical when they see it.

Cross-check by:
- Reading `traces/<run-id>/engineer-deviations.log` for the run that shipped this plan. If the log has entries, the section is lying. BLOCK archive.
- Eyeballing the actual diff via `git log --since='<plan start date>' --oneline -- <plan's file scope>`. If the diff doesn't match the plan's spec exactly, there are deviations to record. BLOCK archive.
- Confirming the plan's Approval checklist matches what shipped. Mismatches are deviations.

**3c. Do bullets carry all 4 dimensions per AGENTS.md § Workflow step 7?**

Every deviation bullet should name:
- **What** changed (one-line)
- **Why** (root cause / constraint)
- **Impact** on follow-up plans
- **Surface** (new env var / on-disk path / CLI / port / schedule — or "none")

Missing dimensions are a partial fail — flag for the manager to fill in via `manager-deviation-promote` before archive.

### Step 4 — Verify operational surfaces propagated

For any bullet with a non-`none` Surface field, confirm the surface was propagated to the right user-facing doc. See `manager-deviation-promote § 6` for the propagation table:

| Surface type | Must appear in |
|---|---|
| New env var | `README.md` § Configuration + `.env.example` |
| New CLI subcommand (fixes only — sunset!) | `README.md` § Operations |
| New on-disk path / secret-handling rule | `CLAUDE.md` + `docs/plans/POST_PHASE_1.md` |
| New port / cron schedule / runtime invariant | `CLAUDE.md` + `ROADMAP.md` "Last updated" bump |

If a Surface is named in the Deviations section but missing from the propagation target, BLOCK archive. The whole point of step 7 is to catch operational drift before plans archive.

### Step 5 — Emit verdict

**PASS:** plan has Deviations section, non-empty, all 4 dimensions per bullet, surfaces propagated.
```
PASS — plan ready to archive. Deviations section: <N> bullets, <M> with operational surfaces (all propagated).
```

**BLOCK:** any failure above. Emit specific reason + recommended fix.
```
BLOCK — <reason>. Recommended fix: <invoke manager-deviation-promote / propagate surface to README / etc>.
```

## Worked examples

### Pass case

Plan `docs/plans/10b-phase-1-finalization.md` § Deviations from plan:

```markdown
## Deviations from plan

- **NullPool engine swap** — what: Engine switched from default pool to NullPool. why: greenlet bridge race under lifespan shutdown caused asyncpg connection wedge. impact: All future db code must import async_session_factory; documented in engineer-stack-invariants. surface: none (internal).

- **NAAVIK_PERSISTENCE env var** — what: Added `NAAVIK_PERSISTENCE={memory,db}` to switch between sample-data accessors and SQL accessors at boot. why: Allow dev parity testing without breaking memory-mode fast-iteration loop. impact: documented in README + CLAUDE; orchestrator sets to `db` automatically. surface: NAAVIK_PERSISTENCE in .env.example.
```

→ PASS: 2 bullets, all dimensions present, NAAVIK_PERSISTENCE confirmed in README + CLAUDE + `.env.example`.

### Block case

Plan `docs/plans/10c-first-time-setup.md` has `## Deviations from plan` heading but the section body is empty.

→ BLOCK: Section exists but empty. Recommended fix: invoke `manager-deviation-promote` against `traces/2026-05-12T_*/engineer-deviations.log` to lift entries.

## Canonical references

- `AGENTS.md` § Workflow step 7 — the contract.
- `AGENTS.md` § "Documenting deviations — what counts, what doesn't" — the filter.
- `CLAUDE.md` § "Deviations workflow — non-negotiable before archive".
- `manager-deviation-promote` skill — the promotion flow.
- `engineer-deviation-log` skill — the source log format.

## When NOT to invoke

- The plan is still active (`Status: DRAFT` or actively-being-implemented). Deviations live alongside implementation; check at archive time, not mid-flight.
- The plan is `Type: design` and graduating (still gets a deviations section once executed, but graduation is a separate gate).
- Compaction events.

## Forbidden during invocation

- Do NOT pass a plan that says "no material deviations" without verifying against `engineer-deviations.log` + the actual diff. Real plans almost always have deviations.
- Do NOT archive a plan with a missing Deviations section. The contract is binary.
- Do NOT skip the operational-surface propagation check. The surface field is what catches self-hoster pain (codified in AGENTS.md § "Operational drift is the leading source of self-hoster pain").
- Do NOT silently fix a deviations section by editing it yourself — surface the gap, let the implementer (engineer / manager via `manager-deviation-promote`) write the section properly.
