---
description: Pull the functional contract for a given screen slug from `docs/design/SCREENS.md` — what the screen does, what data it shows, what components compose it, what HTMX interactions wire it up. Use whenever you need a screen's spec before mocking / implementing / reviewing. Triggers on phrases like "screens.md", "screen spec", "what does <screen> do", "screen contract", "discover spec", "tracking spec", "overview spec", "profile spec", "section for <screen>".
---

# designer-screen-lookup

`docs/design/SCREENS.md` = per-screen functional contract — Route / Sidebar label / Phase / Mockup status / Components / Copy / Interactions / States. Points to right section; does NOT duplicate content (drift trap). Read-only.

## When to invoke

- About to mock screen — read section first to ground visual decisions in functional spec.
- About to implement page in `src/ui/templates/pages/<slug>.html` — confirm components list + interactions match spec.
- Reviewing UI PR — compare against screen's `Components` + `Interactions` + `States` rows.
- User asks "what does Discover do" / "spec for Tracking" / "is Overview right place for charts?".

## Steps

1. **Identify screen slug.** Naavik MVP has 11 screens (post-1.2 consolidation):

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

2. **Open section** in `SCREENS.md`:
   ```
   Read docs/design/SCREENS.md
   ```
   Use `Grep` w/ slug to find heading:
   ```
   Grep "^## \\d+\\.|^### " docs/design/SCREENS.md
   ```

3. **Extract canonical fields:**

   | Field | What you'll find |
   |---|---|
   | **Route** | URL path FastAPI handler answers (matches `src/ui/routes/<area>.py`) |
   | **Sidebar label** | Shows in persistent sidebar (may differ from screen title) |
   | **Phase** | Which ROADMAP phase this ships in |
   | **Mockup** | `[ ]` not designed · `[~]` in design · `[x]` committed |
   | **Impl** | `[ ]` not built · `[~]` in progress · `[x]` shipped |
   | **Purpose** | One sentence |
   | **Layout** | High-level structure (left nav + center column + right rail, etc.) |
   | **Components** | Partials in `src/ui/templates/components/` — cross-ref to `docs/design/COMPONENTS.md` |
   | **Copy** | Exact strings visible — locked unless explicitly redesigned |
   | **Interactions** | HTMX swaps, keyboard, modals, SSE — cross-ref to `docs/design/INTERACTIONS.md` |
   | **States** | empty / loading / error / variant |

4. **Use field in work** without re-typing into output. Need components list? Cite `SCREENS.md § <section number>`. Contract is source; work references it.

## Important defaults from SCREENS.md (load if unsure)

- **Sidebar IA** (top of file): 6 nav items — Overview, Profile, Discover, Tracking, Outreach, Settings.
- **Application status pipeline** (top of file): 6 stages w/ 5 visible (DRAFT + CLOSED hidden by default in Tracking).
- **Tag vocabulary** (top of file): 9 tags, fixed (`ai-ml`, `backend`, `frontend`, `devops`, `data-eng`, `genai`, `leadership`, `platform`, `product`).
- **Tracking visibility rule:** Board/List default to `status IN (APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER)`. Closed bucket toggle adds CLOSED.

## Canonical references

- `docs/design/SCREENS.md` — canonical contract.
- `docs/design/COMPONENTS.md` — partial specs (referenced by every Components list).
- `docs/design/INTERACTIONS.md` — HTMX patterns (referenced by every Interactions list).
- `docs/design/WORKFLOW.md` § Read order — SCREENS.md is step 2 in UI work read-order.

## When NOT to invoke

- Already loaded SCREENS.md § relevant section this turn.
- Non-UI work (data model, backend service, infra) where screens aren't load-bearing.
- Compaction events.

## Forbidden during invocation

- Do NOT duplicate screen's contract content into conversation or another file. Cite SCREENS.md; contract has one home.
- Do NOT propose screen change without comparing against current section. Discrepancy between mockup and SCREENS.md → contract wins (per doc's own "Where this disagrees with mockups, this wins" rule).
- Do NOT invent screen-level concept (new pipeline stage, new sidebar item) without proposing architect-led contract update first.
