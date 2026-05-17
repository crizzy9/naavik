---
description: Append one-liner deviation entries to `traces/<run-id>/engineer-deviations.log` whenever implementation diverges from the plan. Canonical format: `[ISO-timestamp] DEVIATION plan=<path> what=<one-line> why=<one-line> impact=<one-line>`. Manager promotes these into the plan's `## Deviations from plan` section at archive time. Use the moment you realize implementation differs from the plan, not at the end. Triggers on phrases like "deviation from plan", "this doesn't match the plan", "log deviation", "diverged from spec", "spec said X but", "off-plan", "deviation log".
---

# engineer-deviation-log

Plans never land exactly as written. Engineer captures every meaningful divergence in `traces/<run-id>/engineer-deviations.log` as it happens — append-only, one line per deviation. Manager promotes these into the plan's `## Deviations from plan` section at archive time (see `manager-deviation-promote` skill). The log is the lineage that lets future-you trace "what we shipped" back to "what we planned".

## When to invoke

- The moment you realize implementation differs from the plan's spec (sooner is better than later — you'll forget by hand-back time).
- After a quality gate failure forces a different approach than the plan recommended.
- After context7 / nixos research surfaces a library constraint the plan didn't anticipate.
- After a scope reduction or scope expansion.
- After introducing any new operational surface (env var, on-disk path, port, cron schedule, secret-handling rule) that wasn't in the plan.

## What this skill does

1. **Confirm RUN_ID.** Every dispatch carries a RUN_ID in the manager's Task call (e.g. `2026-05-16T21-00-00_a11v2x`). The log lives at `traces/<RUN_ID>/engineer-deviations.log`. If the dir doesn't exist, create it.

2. **Append the line.** Format is frozen:
   ```
   [<ISO-timestamp>] DEVIATION plan=<docs/plans/NN-name.md> what=<one-line> why=<one-line> impact=<one-line>
   ```

   - **Timestamp:** ISO-8601 UTC, second granularity (`date -u +%Y-%m-%dT%H:%M:%SZ`).
   - **plan=:** the canonical plan path. Use the active path `docs/plans/NN-name.md`, not the archived path (the plan hasn't archived yet at this point).
   - **what=:** ONE sentence stating what shipped differently. No padding.
   - **why=:** ONE sentence on root cause. Library constraint, runtime, scope, performance, etc.
   - **impact=:** ONE sentence on downstream impact. References follow-up plans / phases / new operational surfaces.

3. **Append, never overwrite.** Multiple deviations from a single run accumulate:
   ```bash
   echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DEVIATION plan=docs/plans/<NN-name.md> what=<...> why=<...> impact=<...>" >> traces/<RUN_ID>/engineer-deviations.log
   ```

4. **What counts as a deviation** (record):
   - A spec field, file, or behavior the plan called for that didn't ship as written
   - An on-disk artifact, env var, CLI command (fixes only!), or operational invariant introduced that wasn't in the plan
   - A test the plan promised that's now skipped, gated, or restructured
   - A library version / dependency / runtime constraint discovered during implementation
   - A scope reduction (e.g. "Wave 4 implements 12 of 50 accessors; rest fall back to memory")
   - An infrastructure decision (e.g. NullPool engine, sequence-bumping after seed) future plans will care about

5. **What does NOT count** (skip):
   - Routine commit-level cleanups (variable rename, comment fix)
   - Test fixtures added beyond the plan's count when the plan said "≥ N"
   - Lint fixes that don't change behavior
   - Self-correction within the same turn (you tried approach A, switched to B before commit)

## Worked examples (from past runs)

```
[2026-05-03T18:42:11Z] DEVIATION plan=docs/plans/10b-phase-1-finalization.md what=Engine switched from default pool to NullPool why=greenlet bridge race under lifespan shutdown impact=All future db code must import async_session_factory; documented in engineer-stack-invariants

[2026-05-12T16:08:33Z] DEVIATION plan=docs/plans/10c-first-time-setup.md what=Persistence env var added NAAVIK_DEV_PASSWORD why=allow operator to inject a known dev password instead of auto-generated impact=propagated to README + CLAUDE; lifespan emits NAAVIK_PERSISTENCE=db in nix develop

[2026-05-16T18:24:55Z] DEVIATION plan=docs/plans/16-agent-system-v2.md what=Designer agent already had Skill tool; skipped D.4 edit for designer.md why=verified during Phase 1 setup impact=none; designer.md tools line unchanged from prior state
```

## Cross-reference with manager-deviation-promote

The line you append here gets lifted by `manager-deviation-promote` skill into the plan's `## Deviations from plan` section, in this canonical bullet shape:

```markdown
- **<title derived from what>** — what: <what>. why: <why>. impact: <impact>. surface: <operational surface or "none">.
```

If your `impact=...` field hints at a new operational surface (env var, on-disk path, etc.), `manager-deviation-promote` will surface it for propagation to README / CLAUDE / POST_PHASE_1.md. **Make the impact line explicit** about surfaces — say "new env var X" or "new file Y at mode 0600" so the manager catches it.

## Canonical references

- `.claude/agents/engineer.md` § Deviation tracking (mandatory).
- `AGENTS.md` § Workflow step 7 (the deviations contract).
- `AGENTS.md` § "Documenting deviations — what counts, what doesn't" (the filter).
- `CLAUDE.md` § "Deviations workflow — non-negotiable before archive".
- `docs/AGENT_OPS.md` § 7.2 — log format spec.
- `manager-deviation-promote` skill — the promotion flow at archive time.

## When NOT to invoke

- Implementation matches the plan exactly (no deviation to log).
- The "deviation" is one of the filter-skip cases above (rename, lint fix, extra test fixture).
- You're handing back without an active RUN_ID (one-off bug investigation, not a `/build` dispatch).
- Compaction events.

## Forbidden during invocation

- Do NOT skip logging "minor" deviations that future maintainers will care about. The filter is generous; err on the side of recording.
- Do NOT bury an operational surface (env var, on-disk path) in the body of a deviation without naming it in the impact line. Manager's promotion step looks at impact to decide what propagates.
- Do NOT overwrite or edit prior log entries — append-only. Mistakes get corrected by appending a clarifying line, not editing the prior one.
- Do NOT collapse multiple distinct deviations into one line. One thing per line; readability matters when the manager promotes 12 lines from a busy run.
