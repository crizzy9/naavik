---
Status: ACTIVE
Type: prompt
Authored: 2026-07-07
Plan: docs/plans/95-tracking-v2-interview-rounds-and-signal-quality.md
---

# Kickoff — Plan 95: Tracking v2 (interview rounds, signal quality, correction loop)

You are implementing an APPROVED plan in the Naavik repo. Read, in order:

1. `CLAUDE.md` — repo conventions (Nix-first commands, service-package
   seams, LLM tracker wrap, fragment granularity, secrets posture).
2. `docs/design/TRACKING_PIPELINE.md` — the tracking architecture you are
   extending. Do not violate its principles (one write path, perception ≠
   policy, asymmetric autonomy, corrections are data).
3. `docs/plans/95-tracking-v2-interview-rounds-and-signal-quality.md` — the
   plan. §§ 3.0–3.10 are the design (all decisions resolved — do NOT re-open
   them); **§ 6 is your work order**: per-slice files, tests, acceptance.

## Execution contract

- Work the slices **in order: 95a → 95b → 95c → 95d → 95e → 95f → 95h →
  95i → 95j → 95k → 95l** (95g is deferred — skip it). One slice = one
  local commit on `main`, prefixed `feat(tracking-v2/95X):` (95a is `fix:`).
- Before each commit: `ruff check . && ruff format .`, `uv run pytest`
  green, and for UI slices real-browser QA via Playwright against
  `nix run .#dev` (mint a session per the repo's dev-session recipe; owner
  is user_id=2 on the dev DB). Shut the dev stack down when finished.
- Migrations are additive and numbered as slices land (0042/0043/0044/0045
  per § 6); `NAAVIK_DEBUG=1` to run them by hand; never edit an
  already-applied migration.
- Every new LLM call goes through `services/llm_tracker.tracked_call`.
  Remember `StructuredResult.value` is a **dict** — validate through the
  Pydantic schema, never `getattr` (this exact bug killed tracking once).
- If implementation must deviate from the plan, log it as you go and append
  a `## Deviations from plan` section to the plan file before finishing.
- Stop and ask only if a decision genuinely contradicts the plan; otherwise
  proceed autonomously slice by slice.

## Done

All slices committed with green gates → update
`docs/design/TRACKING_PIPELINE.md` (rounds, pin contract, sender rules,
staleness, body posture) → flip plan Status to EXECUTED, move the plan to
`docs/plans/archive/` and this prompt to `docs/prompts/archive/`.

If the session runs long, finishing any prefix of the slice order is a valid
stopping point — say clearly which slices landed and which remain.
