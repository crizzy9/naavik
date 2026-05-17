---
description: Designer mocks a screen per DESIGN.md + SCREENS.md, using huashu-design / ui-ux-pro-max / frontend-design skills. Exports mockups to docs/design/mockups/.
argument-hint: <screen name from SCREENS.md>
---

Screen: $ARGUMENTS

1. **Spawn `designer` via Task** with the screen name. Designer reads, in order:
   - `DESIGN.md` (root) — visual contract (tokens, typography, components, voice).
   - `docs/design/SCREENS.md` § the section for $ARGUMENTS (functional contract per screen).
   - `docs/design/WORKFLOW.md` (UI sub-process — mockup → component → page).
   - `docs/design/COMPONENTS.md` — the 85-component catalog. **NEVER invent a component if one exists here.**
   - Recent mockups in `docs/design/mockups/` for style coherence.
   - Existing partials in `src/ui/templates/components/`.

2. **Designer routes to the right skill** (per the routing table in `.claude/agents/designer.md`):
   - Bold / hero / distinctive → `frontend-design` or `huashu-design`.
   - Component library / token system → `design-system` or `ui-styling`.
   - Quick polish / hierarchy critique → `impeccable` or `ui-ux-pro-max`.

3. **Designer produces:**
   - `docs/design/mockups/{n}-{slug}-desktop.png` (1440×900).
   - `docs/design/mockups/{n}-{slug}-mobile.png` (375×812).
   - A short componentization-notes memo: which existing components compose the page, which new variants are introduced, where in `COMPONENTS.md` the variant docs should land.
   - Updates the relevant section of `docs/design/SCREENS.md` (flip the per-screen `Mockup [ ]` row to `[x]`).

4. **Hand off to engineer** (manager invokes `/build` or the user pastes the screen-impl prompt). Engineer reads the mockup + componentization notes + builds the page in `src/ui/templates/pages/<slug>.html`.
