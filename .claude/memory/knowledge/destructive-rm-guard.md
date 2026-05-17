---
Topic: destructive-rm-guard
Aliases: auto-mode rm guard, .naavik/db wipe blocked, destructive command, sandbox shared state, devops live-orchestrator pivot, TestClient surrogate
First captured: 2026-05-17 (run 2026-05-17T08-40-13_4abef2)
Last referenced: 2026-05-17
Supersedes: none
Confidence: high
---

# destructive-rm-guard

## Context

Devops's PR #50 dispatch attempted to spot-check the live orchestrator path via `rm -rf .naavik/db && nix run .#dev`. Auto-mode's destructive-rm guard blocked the wipe — correctly, because `.naavik/` also holds `~/.naavik/secrets.enc` and the seeded `~/.naavik/dev-credentials` file, which are shared cross-run state. A blanket wipe would also nuke vault data unrelated to the test. Devops pivoted to FastAPI TestClient as the live-orchestrator surrogate, which exercises the same Starlette routing + dependency injection + CSRF middleware without touching disk state.

## Resolution / pattern

Auto-mode forbids `rm -rf` against any shared-state directory without explicit user confirmation. Devops's default for "exercise the full request path" is the TestClient surrogate, not a clean-slate live orchestrator. If a test truly needs a fresh DB, scope the wipe to `.naavik/db` only (not all of `.naavik/`) AND ask the user before executing. The TestClient path covers ~95% of route-level smoke; full live-orchestrator boot is reserved for migrations or lifespan-specific bugs.

## Related

- traces/2026-05-17T03-16-16_75a522/devops.log — the pivot event
- traces/2026-05-17T03-16-16_75a522/MANIFEST.json:errors_encountered[3]
- docs/RUNBOOK.md § 5 (orchestrator boot)
- docs/plans/POST_PHASE_1.md § "when something goes wrong"
