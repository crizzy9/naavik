---
description: Hacker produces a STRIDE threat model for a feature, design doc, or plan. Output saved next to the doc.
argument-hint: <feature name, design doc path, or plan path>
---

Target: $ARGUMENTS

1. **Spawn `hacker` via Task.** Hacker reads:
   - The target (feature description, design doc, or plan).
   - Related code (grep for entry points; trace through to the affected services / API surfaces / templates / migrations).
   - The relevant security-review checkpoints in `docs/plans/POST_PHASE_1.md` § Security review (full).
   - `AGENTS.md` § Key Conventions § CLI (vault / CLI sunset — flag any code that LEANS on these).
   - The hacker agent's **Naavik-specific watch list** (in `.claude/agents/hacker.md`).

2. **Hacker produces** a structured threat model:
   - **STRIDE table** — one row per concrete threat. Columns: Threat | Category (S/T/R/I/D/E) | Attack scenario | Mitigation | Status (mitigated / accepted / open).
   - **Attack tree** — top-level goals an attacker might pursue against this feature, decomposed into sub-goals + concrete attacks.
   - **Top-3 risks summary** — the three highest-impact open / accepted risks, in plain language, with the recommended next step for each.
   - **Defensive design recommendations** — changes to the design doc / plan that would mitigate threats before code is written.

3. **Output** to `docs/design/THREAT_MODEL-<slug>.md` (slug derived from the target). Link the threat model from the source doc (add a `## Security` section referencing the threat model file).

4. **If the target is a plan in `docs/plans/`** that hasn't shipped yet, the hacker's defensive-design recommendations should be reflected back into the plan's Proposal section before approval — ping architect to incorporate.
