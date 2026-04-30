# Design → Implementation Workflow (UI sub-process)

> **Last updated:** 2026-04-30
>
> **This is the UI sub-process.** The master workflow — plan → review → design doc → prompt → implement → archive — lives in `AGENTS.md` § Workflow. That's the lifecycle every non-trivial change goes through. WORKFLOW.md describes the screen-design pipeline (mockup → component derivation → page implementation) that runs *inside* the master workflow's "implement" step for UI tasks.
>
> Companion: `docs/plans/README.md` for plan-file conventions.

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

- **Phase A (design system setup)** uses `DESIGN.md` (root) as source material uploaded to Claude Design.
- **Phase B (screen-batch prompt)** is authored fresh under `docs/prompts/NN-name.md` per `AGENTS.md` § Workflow. The prior batch's prompt is archived under `docs/prompts/archive/` for reference.
- **Phase C (handoff)** uses a similarly-authored prompt; the prior handoff prompt is also archived.
- **Reference for scope:** `docs/design/SCREENS.md` (which screens to design).

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

For the full directory layout, see `AGENTS.md` § Documentation locations. Touch points specific to the UI sub-process:

- `DESIGN.md` (root) — visual contract; update when tokens or component primitives change.
- `docs/design/SCREENS.md` — screen catalog; update when screens are added, designed, or marked implemented.
- `docs/design/mockups/` — mockup PDFs / bundle JSX (gitignored, locally only); regenerate via Claude Design when needed.
- `src/ui/templates/components/*.html` — component library produced in Stage 2.
- `src/ui/templates/pages/*.html` — page templates produced in Stage 3.
- `ROADMAP.md` — phase progress.

---

## First Run (Phase 1 — current state, 2026-04-30)

### Phase A: Design System Setup ✅ DONE

1. ✅ Design system documented (`DESIGN.md`)
2. ✅ Screens cataloged (`docs/design/SCREENS.md`)
3. ✅ Screen prompt authored and used (now archived at `docs/prompts/archive/CLAUDE_DESIGN_PROMPT.md`)
4. ✅ Design system uploaded and **Published** in claude.ai/design

### Phase B: Generate Screens ✅ DONE

5. ✅ Prototype project created in claude.ai/design
6. ✅ Screen descriptions iterated through multiple revisions
7. ✅ All 11 MVP screens approved
8. ✅ Mockups exported and committed to `docs/design/mockups/` (the historical 12-section PDF, with the prior standalone Cover-letter screen folded into Discover · review & apply)

### Phase C: Implementation 🟡 IN PROGRESS

The implementation now follows the Wave-based plan in `docs/plans/02-mvp-master-plan.md`. Summary:

- **Wave 0** ✅ Doc realignment (plan 01 — executed 2026-04-30)
- **Wave 1** 🟡 Author 4 design docs in `docs/design/`: COMPONENTS.md, ROUTES.md, DATA_MODEL.md, INTERACTIONS.md, plus SAMPLE_DATA.md (plans 03–07)
- **Wave 2** ⏳ Stage 2 component library implementation (plan 08)
- **Wave 3** ⏳ Backend models + initial routes (plan 10)
- **Wave 4** ⏳ Stage 3 page implementation (plan 09)
- **Wave 5** ⏳ Wire interactions per INTERACTIONS.md
- **Wave 6** ⏳ Real backend integration (replaces hardcoded sample data)

The UI shell can be built in parallel with the data/AI layer; integration happens at Stage 3 when routes get real handlers.

**Design principle throughout:** Self-hosted first. The UI should feel like a developer tool you run in your homelab — dark mode, data-dense, no SaaS bloat. The cloud tier ($15/mo, bring-your-own AI credits) is mentioned in Settings as a deployment option, never as a premium upsell.
