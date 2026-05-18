---
description: Append one-liner deviation entries to `traces/<run-id>/engineer-deviations.log` whenever implementation diverges from the plan. Canonical format: `[ISO-timestamp] DEVIATION plan=<path> what=<one-line> why=<one-line> impact=<one-line>`. Manager promotes these into the plan's `## Deviations from plan` section at archive time. Use the moment you realize implementation differs from the plan, not at the end. Triggers on phrases like "deviation from plan", "this doesn't match the plan", "log deviation", "diverged from spec", "spec said X but", "off-plan", "deviation log".
---

# engineer-deviation-log

Plans never land exactly as written. Engineer captures every meaningful divergence in `traces/<run-id>/engineer-deviations.log` as it happens — append-only, one line per. Manager promotes into plan's `## Deviations from plan` at archive (see `manager-deviation-promote`). Log is lineage from "what we shipped" → "what we planned".

## When to invoke

- The moment implementation differs from plan spec (sooner > later — you'll forget by hand-back).
- After quality-gate failure forces different approach than plan.
- After context7/nixos research surfaces library constraint plan didn't anticipate.
- After scope reduction/expansion.
- After introducing new operational surface (env var, on-disk path, port, cron schedule, secret-handling rule) not in plan.

## Steps

1. **Confirm RUN_ID.** Every dispatch carries RUN_ID in manager Task call (e.g. `2026-05-16T21-00-00_a11v2x`). Log lives at `traces/<RUN_ID>/engineer-deviations.log`. Create dir if missing.

2. **Append line.** Format frozen:
   ```
   [<ISO-timestamp>] DEVIATION plan=<docs/plans/NN-name.md> what=<one-line> why=<one-line> impact=<one-line>
   ```

   - **Timestamp:** ISO-8601 UTC, second granularity (`date -u +%Y-%m-%dT%H:%M:%SZ`).
   - **plan=:** active path `docs/plans/NN-name.md`, NOT archived path (plan hasn't archived yet).
   - **what=:** ONE sentence — what shipped differently. No padding.
   - **why=:** ONE sentence — root cause (library constraint, runtime, scope, perf, etc.).
   - **impact=:** ONE sentence — downstream impact. Reference follow-up plans / phases / new operational surfaces.

3. **Append, never overwrite.** Multiple deviations accumulate:
   ```bash
   echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DEVIATION plan=docs/plans/<NN-name.md> what=<...> why=<...> impact=<...>" >> traces/<RUN_ID>/engineer-deviations.log
   ```

4. **What counts** (record):
   - Spec field, file, or behavior plan called for that didn't ship as written
   - On-disk artifact, env var, CLI command (fixes only!), or operational invariant introduced not in plan
   - Test plan promised that's now skipped, gated, or restructured
   - Library version / dependency / runtime constraint discovered during implementation
   - Scope reduction (e.g. "Wave 4 implements 12 of 50 accessors; rest fall back to memory")
   - Infrastructure decision (e.g. NullPool engine, sequence-bumping after seed) future plans care about

5. **What does NOT count** (skip):
   - Routine commit-level cleanups (rename, comment fix)
   - Test fixtures added beyond plan's count when plan said "≥ N"
   - Lint fixes that don't change behavior
   - Self-correction within same turn (tried A, switched to B before commit)

## Worked examples (past runs)

```
[2026-05-03T18:42:11Z] DEVIATION plan=docs/plans/10b-phase-1-finalization.md what=Engine switched from default pool to NullPool why=greenlet bridge race under lifespan shutdown impact=All future db code must import async_session_factory; documented in engineer-stack-invariants

[2026-05-12T16:08:33Z] DEVIATION plan=docs/plans/10c-first-time-setup.md what=Persistence env var added NAAVIK_DEV_PASSWORD why=allow operator to inject known dev password instead of auto-generated impact=propagated to README + CLAUDE; lifespan emits NAAVIK_PERSISTENCE=db in nix develop

[2026-05-16T18:24:55Z] DEVIATION plan=docs/plans/16-agent-system-v2.md what=Designer agent already had Skill tool; skipped D.4 edit for designer.md why=verified during Phase 1 setup impact=none; designer.md tools line unchanged from prior state
```

## Cross-reference w/ manager-deviation-promote

Line you append gets lifted by `manager-deviation-promote` into plan's `## Deviations from plan` in canonical bullet shape:

```markdown
- **<title derived from what>** — what: <what>. why: <why>. impact: <impact>. surface: <operational surface or "none">.
```

If `impact=...` hints at new operational surface (env var, on-disk path, etc.), `manager-deviation-promote` surfaces it for propagation to README / CLAUDE / POST_PHASE_1.md. **Make impact line explicit** about surfaces — say "new env var X" or "new file Y at mode 0600" so manager catches it.

## Canonical references

- `.claude/agents/engineer.md` § Deviation tracking (mandatory).
- `AGENTS.md` § Workflow step 7 (deviations contract).
- `AGENTS.md` § "Documenting deviations — what counts, what doesn't" (filter).
- `CLAUDE.md` § "Deviations workflow — non-negotiable before archive".
- `docs/AGENT_OPS.md` § 7.2 — log format spec.
- `manager-deviation-promote` skill — promotion flow at archive.

## When NOT to invoke

- Implementation matches plan exactly (no deviation to log).
- "Deviation" is filter-skip case above (rename, lint fix, extra test fixture).
- Handing back without active RUN_ID (one-off bug investigation, not `/build`).
- Compaction events.

## Forbidden during invocation

- Do NOT skip logging "minor" deviations future maintainers care about. Filter is generous; err on recording.
- Do NOT bury operational surface (env var, on-disk path) in body without naming in impact line. Manager's promotion looks at impact to decide propagation.
- Do NOT overwrite or edit prior log entries — append-only. Corrections via appending clarifying line.
- Do NOT collapse multiple distinct deviations into one line. One thing per line.
