# Design → Implementation Workflow

> **Last updated:** 2026-04-25
>
> This document defines the cohesive pipeline: from design intent → mockup → implemented UI. Every screen ships through this pipeline.

---

## The Pipeline

```
┌────────────────────────┐
│  ROADMAP.md            │  Phase plan: which screens, when
│  + SCREENS.md          │  Per-screen functional spec
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│  DESIGN.md      │  Tokens, components, voice
│  CLAUDE_DESIGN_PROMPT.md  Self-contained prompt
└──────────┬─────────────┘
           │
           ▼ Stage 1: Mockup
┌────────────────────────┐
│  Claude Design         │  ← Paste prompt, generate
│  (or v0 / Galileo)     │
└──────────┬─────────────┘
           │ export
           ▼
┌────────────────────────┐
│ docs/design/mockups/   │  Committed PNG/JPG per screen
│   01-login.png         │
│   02-dashboard.png     │
│   ...                  │
└──────────┬─────────────┘
           │
           ▼ Stage 2: Component derivation
┌────────────────────────┐
│  Claude Code session   │  Reads ALL mockups + design system
│  "Extract components"  │  Produces component library
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────────────────────┐
│  src/ui/                        │
│  ├── static/                           │
│  │   └── tailwind-theme.css            │ ← Tokens applied
│  └── templates/                        │
│      ├── base.html                     │ ← Layout shell
│      ├── components/                   │ ← Reusable partials
│      │   ├── button.html               │
│      │   ├── card.html                 │
│      │   ├── stat_card.html            │
│      │   ├── status_badge.html         │
│      │   ├── tag.html                  │
│      │   ├── bullet_editor.html        │
│      │   ├── score_card.html           │
│      │   └── ...                       │
│      └── pages/                        │ ← Composed screens
│          ├── login.html                │
│          ├── dashboard.html            │
│          └── ...                       │
└────────────────────────────────────────┘
           │
           ▼ Stage 3: Page implementation (per screen)
┌────────────────────────┐
│  Claude Code session   │  One mockup + components → one page
│  "Implement screen X"  │
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│  Visual QA             │  Render localhost → screenshot →
│  (manual or playwright)│  compare to mockup → iterate
└────────────────────────┘
```

---

## Stage 1 — Mockup Generation

**Tool:** Claude Design (claude.ai/design).

### How Claude Design works (correct workflow)

Claude Design has **two distinct phases** that must happen in order:

**Phase A: Set up design system (one-time per organization)**
- Click **"Set up design system"** on the homescreen
- Upload brand/product assets: codebases, screenshots, slide decks, brand PDFs, color palette files
- Claude extracts: color palette, typography, components, layout patterns
- Review, adjust, and **publish** the design system
- Once published, ALL future projects auto-inherit it

**Phase B: Create prototype projects (per screen batch)**
- Click **"Create"** → **"Prototype"** → **"High fidelity"**
- Projects automatically use the published design system
- Paste screen descriptions — no need to redefine tokens
- Iterate visually

**Critical rule from Anthropic docs:** "This guide assumes your organization's design system has already been set up, so everything you create will automatically use your brand's colors, typography, and component patterns."

**Why this matters:** The design system is the single biggest quality lever. Without it, output looks generic. With it, output feels like your product. There is no prompting workaround that compensates for skipping the design system setup.

### Inputs

| File | Purpose | When to use |
|---|---|---|
| `docs/design/DESIGN.md` | Formatted for Claude Design's asset upload | Phase A — upload as source material |
| `docs/design/CLAUDE_DESIGN_PROMPT.md` | Screen descriptions only (tokens already in design system) | Phase B — paste into prototype project |
| `docs/design/SCREENS.md` | Full screen catalog with specs | Reference for which screens to design |

### Process

**Phase A: Design System Setup (one-time)**
1. Go to **claude.ai/design**
2. Click **"Set up design system"** (button below project creation options)
3. Upload `docs/design/DESIGN.md` as source material
4. Optionally upload: screenshots of Linear/Cursor/Plausible as visual references
5. Let Claude extract the design system (~5 minutes)
6. Review extracted tokens — adjust any that look off
7. Validate: create a test project, prompt "design a settings page with sidebar"
8. If output matches brand → **publish** the design system

**Phase B: Generate Screens (per batch)**
1. Identify next batch from `SCREENS.md` (those with `Mockup: [ ]`)
2. Click **"Create"** → **"Prototype"** → **"High fidelity"**
3. Name it (e.g., "Naavik Phase 1")
4. The design system auto-applies — you don't need to select it
5. Paste the screen descriptions from `CLAUDE_DESIGN_PROMPT.md`
6. Iterate: "make stat cards bigger", "redesign login", etc.
7. Export each screen as PNG

**Outputs:** Files committed to `docs/design/mockups/` with naming:
```
{number}-{slug}-desktop.png
{number}-{slug}-mobile.png
```

**Update `SCREENS.md`:** Mark mockup status `[x]` for each completed screen.

---

## Stage 2 — Component Derivation (one-time per batch)

**Tool:** Claude Code, multimodal session (reads images).

**Inputs:**
- All mockups for the current batch in `docs/design/mockups/`
- `docs/design/DESIGN.md`
- Existing `src/ui/templates/components/` (if any)

**Prompt for the Claude Code session:**

> Look at all mockups in `docs/design/mockups/`. Read `docs/design/DESIGN.md`. Identify reusable components that appear across multiple screens. For each component:
> 1. Confirm it matches the spec in DESIGN.md (or propose updates if mockups suggest a refinement)
> 2. Create the Jinja partial in `src/ui/templates/components/{name}.html`
> 3. Use Tailwind utility classes only — no custom CSS unless necessary for animations
> 4. Each component should accept variables via `{% include "components/x.html" with {...} %}`
>
> Do NOT yet implement page templates — just the component library + base.html.
> Output: list of components created, any DESIGN.md proposed changes.

**Outputs:**
- `src/ui/templates/components/` populated with partials
- Optional updates to `DESIGN.md` (commit alongside)
- Updated `base.html` if layout changed

---

## Stage 3 — Page Implementation (per screen)

**Tool:** Claude Code, multimodal session.

**Inputs:**
- One specific mockup (desktop + mobile) from `docs/design/mockups/`
- That screen's spec from `docs/design/SCREENS.md`
- `src/ui/templates/components/` (built in Stage 2)
- `docs/design/DESIGN.md`

**Prompt for the Claude Code session:**

> Implement Screen N (`{screen-name}`) per `docs/design/SCREENS.md`.
> Mockup: `docs/design/mockups/{n}-{slug}-desktop.png` and `-mobile.png`.
> Use existing components from `src/ui/templates/components/`. If a component is missing, build it (and add to DESIGN.md).
> Wire HTMX interactions per the **Interactions** section of the screen spec.
> Add a route handler in the appropriate `src/api/` or `src/ui/` module.
> Use realistic sample data (Phase 1: hard-coded; later phases: from DB models).
> After implementation, take a screenshot via Playwright and compare to the mockup.

**Outputs:**
- `src/ui/templates/pages/{screen}.html`
- Route handler in `src/main.py` (Phase 1) or domain-specific module
- HTMX endpoints if needed (return component partials)
- Screen marked `[x]` in `SCREENS.md` Impl column

---

## Quality Checks

Run before merging any screen implementation:

| Check | How |
|---|---|
| Visual match to mockup | Playwright screenshot compared side-by-side with mockup |
| Token compliance | All colors via Tailwind classes (no arbitrary values like `[#abc123]`); no inline styles |
| Component reuse | New page uses existing components where applicable; new components added to library |
| HTMX correctness | All interactive elements use `hx-*` attributes; no bespoke JS unless documented |
| Accessibility | Keyboard reachable, focus rings visible, ARIA labels on icon buttons |
| Responsive | Desktop and mobile match their respective mockups; no broken layouts in between |
| Dark mode | Looks correct (light mode is Phase 6) |
| Empty / loading / error states | Each declared state in SCREENS.md exists |

---

## When to Revisit / Update

**Trigger → Action**

- New screen needed → add to `SCREENS.md` → next mockup batch
- Token change requested (e.g. "indigo feels too cool, try violet") → update `DESIGN.md` + `CLAUDE_DESIGN_PROMPT.md` → bump design system version → re-mockup affected screens
- Mockup looks better than spec → update `SCREENS.md` to match (or push back to design)
- Existing page needs visual refresh → mark `Mockup: [~]`, re-run Stage 1 for that screen, then Stage 3
- New component pattern emerges across pages → extract to component → add to `DESIGN.md`

---

## File Reference

| File | Owner | Update when |
|---|---|---|
| `docs/design/DESIGN.md` | Designer + Implementer | Tokens or components change |
| `docs/design/SCREENS.md` | Designer + PM | Screens added, designed, or implemented |
| `docs/design/CLAUDE_DESIGN_PROMPT.md` | Designer | Design system version bumps; new batch screens added |
| `docs/design/WORKFLOW.md` (this file) | All | Process changes |
| `docs/design/mockups/*.png` | Designer | New mockup generated |
| `src/ui/templates/components/*.html` | Implementer | Component library evolves |
| `src/ui/templates/pages/*.html` | Implementer | Per-screen, after mockup exists |
| `ROADMAP.md` | All | Phase progress, scope changes |

---

## First Run (Phase 1 — happening now)

### Phase A: Design System Setup (CRITICAL — do not skip)

1. ✅ Design system documented (`DESIGN.md` + `DESIGN.md`)
2. ✅ Screens cataloged (`SCREENS.md`)
3. ✅ Screen prompt prepared (`CLAUDE_DESIGN_PROMPT.md`)
4. ⏳ **YOU ARE HERE:**
   - Go to **claude.ai/design**
   - Click **"Set up design system"**
   - Upload `docs/design/DESIGN.md`
   - Optionally upload screenshots of Linear, Cursor, or Plausible as visual references
   - Let Claude extract (~5 min)
   - Validate with test prompt
   - **Publish** the design system

### Phase B: Generate Screens

5. ⏳ Click **"Create"** → **"Prototype"** → **"High fidelity"** → Name: "Naavik Phase 1"
6. ⏳ Paste screen descriptions from `CLAUDE_DESIGN_PROMPT.md`
7. ⏳ Iterate until satisfied with all 9 screens
8. ⏳ Export mockups → commit to `docs/design/mockups/`

### Phase C: Implementation

9. ⏳ Run Stage 2 (Claude Code component derivation) → builds component library
10. ⏳ Run Stage 3 per screen → ships Phase 1 UI
11. ⏳ Phase 1 backend work (models, API, services) plugs into the components

The UI shell can be built in parallel with the data/AI layer; integration happens at Stage 3 when routes get real handlers.

**Design principle throughout:** Self-hosted first. The UI should feel like a developer tool you run in your homelab — dark mode, data-dense, no SaaS bloat. The cloud tier ($15/mo, bring-your-own AI credits) is mentioned in Settings as a deployment option, never as a premium upsell.
