---
description: Pull the functional contract for a given screen slug from `docs/design/SCREENS.md` — what the screen does, what data it shows, what components compose it, what HTMX interactions wire it up. Use whenever you need a screen's spec before mocking / implementing / reviewing. Triggers on phrases like "screens.md", "screen spec", "what does <screen> do", "screen contract", "discover spec", "tracking spec", "overview spec", "profile spec", "section for <screen>".
---

# designer-screen-lookup

`docs/design/SCREENS.md` is the per-screen functional contract — Route / Sidebar label / Phase / Mockup status / Components / Copy / Interactions / States. This skill points to the right section; it does NOT duplicate the content (drift trap if it did). Reads only.

## When to invoke

- About to mock a screen — read the screen's section first to ground the visual decisions in the functional spec.
- About to implement a page in `src/ui/templates/pages/<slug>.html` — confirm the components list + interactions match what's already specced.
- Reviewing a UI PR — compare against the screen's `Components` + `Interactions` + `States` rows.
- User asks "what does Discover do" / "what's the spec for Tracking" / "is Overview the right place for charts?".

## What this skill does

1. **Identify the screen slug.** Naavik MVP has 11 screens (post-1.2 consolidation):

   | # | Title | Sidebar label | Route | Slug |
   |---|---|---|---|---|
   | 1 | Login | (auth) | `/login` | `login` |
   | 2 | Onboarding | (auth) | `/onboarding` | `onboarding` |
   | 3 | Overview | Overview | `/` | `overview` |
   | 4 | Profile | Profile | `/profile` | `profile` |
   | 5 | Bullet editor | (modal from Profile) | `/profile/bullet/<id>` | `bullet-editor` |
   | 6 | Discover | Discover | `/discover` | `discover` |
   | 7 | Discover · review & apply | (sub-route) | `/discover/<job-id>/review` | `discover-review` |
   | 8 | Tracking | Tracking | `/tracking` | `tracking` |
   | 9 | Outreach | Outreach | `/outreach` | `outreach` |
   | 10 | Settings | Settings | `/settings` | `settings` |
   | 11 | Auth shell | (signup/forgot) | `/signup`, `/forgot-password` | `auth` |

2. **Open the section** in `SCREENS.md`:
   ```
   Read docs/design/SCREENS.md
   ```
   Use `Grep` with the slug to find the section heading:
   ```
   Grep "^## \\d+\\.|^### " docs/design/SCREENS.md
   ```

3. **Extract the canonical fields:**

   | Field | What you'll find |
   |---|---|
   | **Route** | URL path the FastAPI handler answers (matches `src/ui/routes/<area>.py`) |
   | **Sidebar label** | What shows in the persistent sidebar (may differ from screen title) |
   | **Phase** | Which ROADMAP phase this ships in |
   | **Mockup** | `[ ]` not designed · `[~]` in design · `[x]` committed |
   | **Impl** | `[ ]` not built · `[~]` in progress · `[x]` shipped |
   | **Purpose** | One sentence |
   | **Layout** | High-level structure (left nav + center column + right rail, etc.) |
   | **Components** | Partials in `src/ui/templates/components/` — cross-ref to `docs/design/COMPONENTS.md` for specs |
   | **Copy** | Exact strings visible — treat as locked unless explicitly redesigned |
   | **Interactions** | HTMX swaps, keyboard, modals, SSE — cross-ref to `docs/design/INTERACTIONS.md` |
   | **States** | empty / loading / error / variant |

4. **Use the field in your work** without re-typing it into your output. If you need the components list, cite `SCREENS.md § <section number>`. The contract is the source; your work references it.

## Important defaults from SCREENS.md (load if unsure)

- **Sidebar IA** (top of file): 6 nav items — Overview, Profile, Discover, Tracking, Outreach, Settings.
- **Application status pipeline** (top of file): 6 stages with 5 visible (DRAFT + CLOSED hidden by default in Tracking).
- **Tag vocabulary** (top of file): 9 tags, fixed (`ai-ml`, `backend`, `frontend`, `devops`, `data-eng`, `genai`, `leadership`, `platform`, `product`).
- **Tracking visibility rule:** Board/List default to `status IN (APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER)`. Closed bucket toggle adds CLOSED.

## Canonical references

- `docs/design/SCREENS.md` — the canonical contract.
- `docs/design/COMPONENTS.md` — partial specs (referenced by every screen's Components list).
- `docs/design/INTERACTIONS.md` — HTMX patterns (referenced by every screen's Interactions list).
- `docs/design/WORKFLOW.md` § Read order — SCREENS.md is step 2 in the UI work read-order.

## When NOT to invoke

- Already loaded SCREENS.md § the relevant section in this turn.
- Non-UI work (data model, backend service, infra) where screens aren't load-bearing.
- Compaction events.

## Forbidden during invocation

- Do NOT duplicate the screen's contract content into the conversation or another file. Cite SCREENS.md; the contract has one home.
- Do NOT propose a screen change without comparing against the current section. If you find a discrepancy between mockup and SCREENS.md, the contract wins (per the doc's own "Where this disagrees with mockups, this wins" rule).
- Do NOT invent a screen-level concept (new pipeline stage, new sidebar item) without proposing an architect-led contract update first.
