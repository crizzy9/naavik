---
description: Designer mocks a screen per DESIGN.md + SCREENS.md, using huashu-design / ui-ux-pro-max / frontend-design skills. Exports mockups to docs/design/mockups/.
argument-hint: <screen name from SCREENS.md>
---

Screen: $ARGUMENTS

1. **Spawn `designer` via Task** w/ screen name. Designer reads, in order:
   - `DESIGN.md` (root) — visual contract (tokens, typography, components, voice).
   - `docs/design/SCREENS.md` § section for $ARGUMENTS (functional contract per screen).
   - `docs/design/WORKFLOW.md` (UI sub-process — mockup → component → page).
   - `docs/design/COMPONENTS.md` — 85-component catalog. **NEVER invent component if one exists here.**
   - Recent mockups in `docs/design/mockups/` for style coherence.
   - Existing partials in `src/ui/templates/components/`.

2. **Designer routes to right skill** (per routing table in `.claude/agents/designer.md`):
   - Bold / hero / distinctive → `frontend-design` or `huashu-design`.
   - Component library / token system → `design-system` or `ui-styling`.
   - Quick polish / hierarchy critique → `impeccable` or `ui-ux-pro-max`.

3. **Designer produces:**
   - `docs/design/mockups/{n}-{slug}-desktop.png` (1440×900).
   - `docs/design/mockups/{n}-{slug}-mobile.png` (375×812).
   - Short componentization-notes memo: which existing components compose page, which new variants are introduced, where in `COMPONENTS.md` variant docs should land.
   - Updates relevant section of `docs/design/SCREENS.md` (flip per-screen `Mockup [ ]` row to `[x]`).

4. **Hand off to engineer** (manager invokes `/build` or user pastes screen-impl prompt). Engineer reads mockup + componentization notes + builds page in `src/ui/templates/pages/<slug>.html`.
