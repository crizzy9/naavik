# Naavik · Claude Code handoff prompt

> **Purpose:** This file is the hand-edited `README.md` / `PROMPT.md` that rides inside the Claude Design "Hand off to Claude Code" bundle. It overrides Claude Design's generic default. Paste it into the bundle's prompt slot before triggering the handoff.
>
> **Audience:** the Claude Code agent that receives the bundle. Treat this as instructions to that agent, not to a human.
>
> **Last updated:** 2026-04-29 — reflects current Naavik design system v1.0 + 12 MVP screens.

---

## 1 · You are working in the Naavik repo

**Naavik** (Hindi: नाविक, "Navigator") is an open-source, self-hosted-first career automation platform. Self-host via Docker Compose or NixOS for free; an optional managed cloud tier ($15/mo, bring-your-own AI credits) exists but is **never** treated as premium. License: AGPL-3.0.

**Design principle:** Naavik should feel like a developer tool you self-host (Linear, Cursor, Plausible) — not a SaaS product you rent. Dark mode primary. Data-dense. No SaaS bloat. No upsell pressure anywhere in the core experience.

Before you write any code, read these files in order. They override anything you might otherwise infer from the bundle:

1. `AGENTS.md` — canonical agent guide (architecture, conventions, contact)
2. `CLAUDE.md` — Claude Code-specific notes (deeper repo conventions)
3. `ROADMAP.md` — current phase, what's done, what's next
4. `docs/design/SCREENS.md` — **the canonical screen catalog**. For every screen you implement, this is the spec. The mockups in this bundle are the visual contract; SCREENS.md is the functional contract. Where they conflict, ask before guessing.
5. `DESIGN.md` (root) — visual contract: tokens, typography, components, voice
6. `docs/design/WORKFLOW.md` — Stage 2 (component derivation) and Stage 3 (page implementation) instructions

---

## 2 · Tech stack (do not deviate)

| Layer | Technology | Notes |
|---|---|---|
| Backend | **FastAPI + SQLModel** | Async endpoints; Pydantic for I/O |
| Templates | **Jinja2** | Server-rendered, no client-side router |
| Interactivity | **HTMX** | `hx-get / hx-post / hx-swap`, fragment endpoints |
| Styling | **Tailwind CSS + DaisyUI** | Tokens already mapped to slate / indigo / cyan in `DESIGN.md` § DaisyUI Theme |
| Icons | **Lucide Icons** (stroke `1.5`) | Already pinned. **No mixing icon sets.** Do not import Heroicons, Phosphor, Feather, or anything else. |
| Optional JS | **Alpine.js** for very local state, **Sortable.js** for drag-and-drop only | Do **not** introduce a JS framework. No React, Vue, Svelte, Solid, or build-step JS. |
| Database | PostgreSQL (+ pgvector) — out of scope for this handoff |
| LLM, scrapers, scheduler, Typst | All out of scope for this handoff — UI only |

**Single dark mode.** Light mode is Phase 6 — do not implement light variants. Do not add a theme switcher.

---

## 3 · What's in this bundle

The Claude Design export should include:

- `design.html` — standalone HTML preview of the design canvas
- `screenshots/` — PNG renders of each screen state (desktop 1440×900, mobile 375×812)
- `design-notes.md` — generated commentary
- *(this file)* — `README.md` / `PROMPT.md` — overrides defaults
- A machine-readable component spec + design tokens used on the canvas

**Mockup PDF source of truth** (already committed): `docs/design/mockups/Naavik — MVP screens (print).pdf` (41 pages, 12 sections, 31 artboards). If `screenshots/` and the PDF disagree, the PDF is canonical.

---

## 4 · What we want you to do

Run the WORKFLOW.md pipeline:

### Stage 2 · component derivation (one pass, **first**)

1. Read **all** mockups (PDF + `screenshots/`) and `DESIGN.md`.
2. Identify components that recur across multiple screens (button, card, kpi_card, score_circle, status_dot, tag_chip, swipe_card, priority_action_row, email_signal_row, application_readiness_card, contact_card, log_tail, etc. — see `SCREENS.md` per-screen "Components" lists).
3. Build each as a Jinja partial in `src/ui/templates/components/{name}.html`.
4. Each partial accepts variables via `{% include "components/x.html" with {...} %}` or as macros (`{% macro %}` is fine where it reads cleaner).
5. Update `src/ui/templates/base.html` to match the layout shell visible in the mockups (sidebar IA per `SCREENS.md` § Sidebar IA).
6. Use Tailwind utility classes only. No custom CSS unless required for animation. No inline styles.

Output of Stage 2: a populated component library + an updated `base.html`. Do **not** implement page templates yet.

### Stage 3 · page implementation (one screen at a time)

For each screen in `SCREENS.md` (start with the simpler ones — Settings, Login, Onboarding — before tackling Discover/review which is the most complex):

1. Read that screen's spec in `SCREENS.md`. The spec wins where the mockup is ambiguous.
2. Open the desktop + mobile mockup for that screen.
3. Build `src/ui/templates/pages/{screen-slug}.html` that extends `base.html`.
4. Compose from `src/ui/templates/components/`. If a component is missing, build it (and add to `DESIGN.md` if it's reusable).
5. Add a route handler in `src/main.py` (Phase 1) or the appropriate `src/api/` module.
6. Wire HTMX interactions per the screen's "Interactions" section. Endpoints that return HTML fragments live in the same router as the page; endpoints that return JSON live in `src/api/v1/`.
7. Use the realistic sample data from `DESIGN.md` § Sample Content (Shyam Padia, Stripe / Anthropic / Plaid / etc.). Hard-code for now; backend models come later.
8. Mark the screen `[x]` in `SCREENS.md` Impl column.

---

## 5 · Repository conventions

```
src/
├── main.py                        ← FastAPI app entrypoint, route handlers (Phase 1)
├── config.py                      ← pydantic-settings
├── api/                           ← REST routes (JSON), under /api/v1/
├── ui/
│   ├── static/                    ← Tailwind output (CDN for now), no custom JS files
│   └── templates/
│       ├── base.html              ← Layout shell (sidebar + main area)
│       ├── components/            ← Reusable Jinja partials (this is what you build in Stage 2)
│       └── pages/                 ← Composed screens (this is what you build in Stage 3)
├── models/                        ← Out of scope for this handoff
├── services/                      ← Out of scope for this handoff
└── ...
```

**File naming:**
- Components: `snake_case.html` matching the spec name in `SCREENS.md` (e.g., `score_circle.html`, `priority_action_row.html`).
- Pages: `snake_case.html` matching the route slug (e.g., `pages/login.html`, `pages/profile.html`, `pages/discover.html`, `pages/discover_review.html`).
- One Jinja file per component, even if small. Don't combine components.

**Routes:**
- Page routes return HTML pages — use `templates.TemplateResponse(...)` returning `HTMLResponse`.
- Fragment routes return HTML partials for HTMX — use `templates.TemplateResponse(...)` with the partial template name.
- JSON routes go under `/api/v1/...` and return Pydantic models.

---

## 6 · Design system mapping

`DESIGN.md` is the visual contract. Highlights you must follow:

| Token | Value |
|---|---|
| Page bg | `bg-slate-950` (`#020617`) |
| Surface | `bg-slate-900` (`#0F172A`) — cards, sidebar |
| Elevated | `bg-slate-800` (`#1E293B`) — modals, hover |
| Brand primary | `bg-indigo-500` (`#6366F1`) — primary CTAs, active nav |
| Accent (AI) | `text-cyan-400` (`#22D3EE`) — used **only** for AI-generated content indicators |
| Sans font | Inter 400/500/600/700 |
| Mono font | JetBrains Mono 400/500 (use `font-mono` for scores, tags, dates, metrics) |

**Score format:** 0–100 number centered in a colored ring. **No `%` mark. No "match" word.** Ring color: emerald ≥ 0.80, indigo 0.60–0.79, amber 0.40–0.59, rose < 0.40. Component name: `score_circle.html`. See `DESIGN.md` § score_circle.

**Tag chips:** plain `bg-slate-800 text-slate-300 text-xs font-mono px-2 py-0.5 rounded`. **Never put a sparkle / AI icon on a tag chip.** Sparkles are reserved for AI-generated *content* (cover letter paragraphs, drafted screener answers, suggested moves), not metadata.

**Status pipeline:** `APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED`. Dot colors per `SCREENS.md`. Do **not** introduce intermediate states (no FOUND, SCORED, APPROVED, DOCS_GENERATED, INTERVIEWING, REJECTED, WITHDRAWN as separate stages).

---

## 7 · Conversion rules (canvas → Jinja + Tailwind + HTMX)

| Canvas concept | Implement as |
|---|---|
| Click handler that swaps content | `hx-get="/path" hx-target="#x" hx-swap="innerHTML"` |
| Form submit | `<form hx-post="/path" hx-target="..."> ... </form>` |
| Modal dialog | `<dialog>` element with HTMX-loaded content; backdrop dim via `bg-black/40` |
| Drag-and-drop list | Sortable.js + HTMX `hx-post` on order change |
| Tabs | Either Alpine.js `x-data` for purely-client state, or HTMX swap to `/page/{tab}` for deep-linkable tabs (Settings does the latter) |
| Tooltip | `<div class="tooltip" data-tip="...">` (DaisyUI) |
| Hover transitions | Tailwind `transition` + `duration-150` |
| Generation shimmer | `animate-pulse` on placeholder skeletons |
| AI sparkle glow | `shadow-lg shadow-cyan-400/20` on the relevant card |
| Cover-letter SSE stream | `hx-ext="sse"` with `sse-connect="/path/stream"` and `sse-swap="message"` |
| Animated progress bar | CSS gradient + `transition-all` width updates from HTMX OOB swap |

**Do not** use:
- React, Vue, Svelte, Solid, Lit, or any build-step JS framework
- Bootstrap, Bulma, or any non-Tailwind CSS framework
- Custom icon sets (only Lucide)
- Inline `style="..."` attributes
- Decorative animations (motion only when it carries meaning — generation, transition, shimmer)
- `// removed` / `// kept for compat` / placeholder comments
- Any `console.log` or debug code in shipped templates

---

## 8 · Page-by-page guidance

For every page, **read its section in `SCREENS.md` first**. Each section in SCREENS.md gives you: route, layout, exact copy strings, components to use, interactions, states, and what's been removed from prior specs.

Recommended implementation order (simplest first, let components stabilize before tackling complex screens):

1. **Login** (`/login`) — auth shell, no sidebar
2. **Settings** (`/settings`) — single tabbed page; great for validating the component library
3. **Profile** (`/profile`) — read-only with sticky right rail
4. **Profile editor** (`/profile/edit`) — same shell + autosave + Bullet editor modal
5. **Bullet editor modal** — pure component, opens from #4 and later #8
6. **Onboarding** (`/onboarding`) — wizard shell, step 2 is the hero
7. **Overview** (`/`) — most components, but most stable layout
8. **Tracking** (`/tracking`) — Kanban + List view toggle, gmail status row
9. **Outreach** (`/outreach`) — 2-pane app list + detail
10. **Cover letter generator** (`/generate/cover-letter`) — 2-column tool with SSE streaming
11. **Discover** (`/discover`) — swipe stack + keyboard handlers
12. **Discover · review & apply** (`/discover/:id`) — 3-column workspace, the most complex screen — do this last, after everything else is stable

---

## 9 · Sample data

Use the realistic profile from `AGENTS.md` § Owner Profile and `DESIGN.md` § Sample Content. Hard-code Shyam Padia data into pages for Phase 1 — backend models will replace this in Phase 1.x. Companies to use as samples: Stripe, Databricks, Anthropic, Vercel, Linear, Plaid, Ramp, Notion, Figma, Discord, Snowflake, Airbnb. Roles: Senior ML Engineer, Staff Backend Engineer, Engineering Manager, Founding Engineer.

**Do not invent personas.** Stick to the canonical sample data.

---

## 10 · Quality bar (Definition of Done)

Before reporting any screen as done:

- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format .` makes no changes
- [ ] Page renders at `/` route on `uv run fastapi dev src/main.py` (no template errors)
- [ ] Screenshot via Playwright matches the mockup at desktop (1440×900) and mobile (375×812) — alignment, color, copy, density
- [ ] Empty / loading / error states declared in SCREENS.md exist
- [ ] Tab/keyboard navigation reaches all interactive elements; focus rings visible (`focus:ring-2 focus:ring-indigo-500/40`)
- [ ] Icon-only buttons have `aria-label`
- [ ] Status pipeline + tag vocabulary match `SCREENS.md` exactly
- [ ] No inline styles, no arbitrary `[#abc123]` Tailwind values, no non-Lucide icons
- [ ] Page marked `[x]` in `SCREENS.md` Impl column

---

## 11 · Things that will get rejected at review

- Adding a new top-level sidebar item without updating `SCREENS.md` § Sidebar IA first
- Implementing a screen without a section in `SCREENS.md`
- Re-introducing oneline/detailed bullet split, metric fields, or the `default_include` toggle in the bullet editor (these were removed; see SCREENS.md § Section 6)
- Putting `%` or the word "match" inside the score circle
- Putting an AI sparkle icon on a tag chip
- Bringing back FOUND / SCORED / APPROVED / DOCS_GENERATED / INTERVIEWING / REJECTED / WITHDRAWN as separate pipeline states
- Adding a Resume sidebar item or `/generate/resume` route (folded into Discover/review)
- Adding an Analytics sidebar item (deferred)
- Introducing any JS framework
- Light-mode variants (Phase 6)
- Comments in code that explain what the next-doored line does, or that describe history/refactor context — write self-documenting code, leave history in commit messages and SCREENS.md

---

## 12 · When in doubt

- **Ambiguous spec?** SCREENS.md wins, then DESIGN.md, then the mockup, then ask in your final summary (do not guess).
- **Component already exists?** Use it. Don't duplicate.
- **Component doesn't exist but should?** Build it in `src/ui/templates/components/`, document it in `DESIGN.md`.
- **Backend route doesn't exist?** Stub it in `src/main.py` returning sample data; flag in your summary as "needs Phase 1.x backend hookup".
- **Mockup shows behavior the spec doesn't?** Document it in your summary; we'll fold it into SCREENS.md if it's correct.

---

End of prompt. Begin with Stage 2 (component derivation) before any page work.
