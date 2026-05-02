---
Status: EXECUTED
Type: execution
Authored: 2026-05-02
Approved: 2026-05-02
Executed: 2026-05-02 (12 issues fixed: 1 Lucide diagnostics; 2 sidebar mobile drawer + close button + a11y; 3 touch swipe via pointer events + stamp visual; 4 typed dropdowns + practical labels; 5A "Jobs"→"Discover" sidebar rename; 6 action-bar button sizing; 7 swipe card 560px on lg; 8D in-place card expansion via /_fragments/discover/expanded/{id} + Back to queue + URL-shareable full page preserved; 9 IntersectionObserver scroll-spy on Profile right-rail; 10 mobile fixes 10.a–10.g; 11 button ID namespace rename; 14 native <dialog> backdrop click. 259 tests passing, ruff clean.)
Last updated: 2026-05-02 (executed)
Depends on: 09-stage-3-impl (executed)
---

# 09a · Stage 3 bugfix + Discover-redesign triage

## Goal

Fix the 10 paper cuts and design-tension items the user surfaced after Wave 3 / plan 09 EXECUTED on 2026-05-02 — broken Lucide icons, sidebar mobile-toggle one-shot bug, missing touch-swipe on Discover, freeform-text application questions that should be typed enums, "Jobs"-vs-`/discover` label/route confusion, action-bar buttons too big, swipe card too small to read JD inline, full-page `/discover/:id` workspace that the user expected as in-place expansion, hardcoded scroll-spy state on Profile right-rail nav, and unspecified mobile breakage on multiple pages. Plus an expanded testing pass to surface anything else that the user-reported list missed.

This plan stays inside the plan-09 surface — it does **not** touch plan 10 / Wave 4 territory (DB models, JWT auth, real LLM, Typst, ATS adapters), and it does not touch the dev-orchestrator paper cuts in `docs/plans/POST_PHASE_1.md` § Immediate paper cuts.

## Context / why

Wave 3 / plan 09 EXECUTED on 2026-05-02 — 11 Phase 1 page templates, sample data accessors, stub fragment + JSON endpoints, Discover keyboard map, 225 tests passing. Smoke-testing the shipped surface, the user surfaced 10 paper cuts and design-tension items spanning broken JS, missing interactions, wrong input types, and design conflicts with `docs/design/SCREENS.md` (sidebar label, swipe-card width, full-page review workspace).

Wave 4 (plan 10 § B) swap will replace the stub bodies in-place; if the UI surface stays broken, Wave 4 inherits the bugs and downstream waves blame the wrong layer. Fix the UI seams now, then Wave 4 swaps clean handlers underneath.

**Approval flow (per AGENTS.md § Workflow):**

1. Plan author writes this file. ✅ (this file)
2. User ticks the per-issue approval checklist + answers § H open questions.
3. Agent boots dev server and reproduces every issue at desktop + mobile, runs through INTERACTIONS.md § J interaction recap per screen, folds new findings into a new § A.11+ block.
4. User re-ticks the (now expanded) checklist.
5. Agent authors `docs/prompts/09a-stage-3-bugfix.md` kickoff and implementation begins.

## Required reading (during implementation)

In order:

1. `AGENTS.md` § Workflow + § Tech Stack
2. `CLAUDE.md`
3. `ROADMAP.md` § Phase 1
4. `docs/plans/POST_PHASE_1.md` § Immediate paper cuts (skip #3 — its own track)
5. `docs/plans/archive/09-stage-3-impl.md` (the plan that just shipped — ground truth on what exists)
6. `docs/design/SCREENS.md` (issues 5, 7, 8 may amend this)
7. `DESIGN.md`
8. `docs/design/INTERACTIONS.md` § F + § A + § I.1
9. `docs/design/COMPONENTS.md` § J + § H.1 (sidebar) + § H.7 (Discover) + § H.3 (Profile/Bullet)
10. `docs/design/DATA_MODEL.md` § C + § D (typed enums for application questions)

---

## Proposal

## A · Issues from user report

Each issue: **Symptom · Reproduction · Root cause · Fix proposal (with options where applicable) · Spec impact · Test plan · Effort.**

Effort scale: **XS** (≤30 min) · **S** (½ day) · **M** (1 day) · **L** (>1 day).

---

### Issue 1 — Lucide icons don't render

**Symptom.** All `<i data-lucide="…">` placeholders ship as empty inline elements. Sidebar nav has no icons; Discover badges/score circles have empty placeholders; resume / cover-letter sparkles missing.

**Reproduction.** Boot dev (`nix run .#dev`), open `http://localhost:8000/login`. View source: `<i data-lucide="menu">` should be replaced by an `<svg class="lucide …">` after page load. Likely it isn't.

**Root cause (suspected).** `src/ui/templates/base.html:52` loads `https://unpkg.com/[email protected]/dist/umd/lucide.min.js` synchronously before HTMX / Sortable / keys.js / base.js. `src/ui/static/base.js:14-21` calls `lucide.createIcons()` on `DOMContentLoaded` and `htmx:afterSwap` / `htmx:oobAfterSwap`. Three failure modes are plausible — implementer must confirm with DevTools:

- (a) **CDN URL stale.** `[email protected]` may not exist or `dist/umd/lucide.min.js` may not be the right path for that version. UMD globals shifted between Lucide 0.x releases — recent versions sometimes ship the global as `LucideIcons` or `lucide.icons` rather than `lucide`.
- (b) **Silent guard.** `lucide.createIcons()` runs but `window.lucide` is undefined, and the silent guard `if (window.lucide && …)` swallows the failure without logging.
- (c) **DOMContentLoaded race.** Scripts load in order `lucide → htmx → sortable → keys.js → base.js`, all at end of `<body>`. If `DOMContentLoaded` already fired by the time base.js runs, the listener never executes — but `htmx:afterSwap` should still cover later renders, so initial paint would be the only break.

**Fix proposal.**

1. Add explicit error logging to `reinitLucide()` so silent failures surface to console: `if (!window.lucide) console.warn('[naavik] window.lucide missing — icons will not render');`.
2. Pin to a known-good Lucide version. Switch to `https://unpkg.com/lucide@latest/dist/umd/lucide.js` (drop `.min`) OR pin to a specific known-working version after validating in browser. Validate by hitting the URL in a browser tab and checking the response is JS (not 404 / wrong MIME).
3. Add a fallback after registering the `DOMContentLoaded` handler:

   ```javascript
   if (document.readyState !== "loading") reinitLucide();
   else document.addEventListener("DOMContentLoaded", reinitLucide);
   ```

4. Add a single Playwright test: hit `/login` headless, wait for `networkidle`, assert `document.querySelectorAll('svg.lucide').length > 0`.

**Spec impact.** Touches `INTERACTIONS.md` § I.1 row 1 (Lucide CDN + post-swap reinit) — note the version pin if we change it. No SCREENS.md / DESIGN.md change.

**Test plan.** Headless Playwright assertion (above) + manual confirm at `/profile` (lots of icons) and after triggering an HTMX swap (e.g., Discover skip → next card swap should still render icons).

**Effort.** S — diagnose CDN, edit one URL, add 4 lines of JS, write the test.

---

### Issue 2 — Sidebar mobile toggle works once then dies

**Symptom.** On viewport <1024px, hamburger button (`[data-sidebar-toggle]` at `src/ui/templates/components/sidebar.html:22-28`) opens drawer once. Subsequent clicks have no effect.

**Reproduction.** DevTools mobile emulation 375×812, navigate to `/` (Overview). Click hamburger top-left: drawer slides in. Click hamburger again or backdrop: drawer should close. It doesn't.

**Root cause (suspected, confirm with DevTools).** Two candidates:

- (a) **z-index occlusion.** Hamburger is `z-30` (`sidebar.html:26`); aside is `z-40` (`sidebar.html:36`). When drawer is open, `<aside>` covers the hamburger area (`fixed left-0 w-64`), so subsequent clicks land on `<aside>`, not the hamburger. The handler at `base.js:104-119` looks for `[data-sidebar-toggle]` via `e.target.closest()` — won't match if the aside intercepts the click and the hamburger is behind the aside.
- (b) **Backdrop CSS missing.** Backdrop element (`sidebar.html:31-34`) ships with Tailwind `hidden` (`display: none`). It needs a CSS rule to flip to `display: block` when `body[data-sidebar-open="true"]`. Implementer must read `src/ui/static/styles.css` and confirm the rule exists with high enough specificity to beat `.hidden`. If missing, backdrop is never visible, so backdrop-click-to-close never fires.

**Fix proposal.**

1. Add an explicit close button inside the `<aside>` (top-right `×` icon, `lg:hidden`) with `data-sidebar-toggle` so users have a visible affordance to close from inside the open drawer.
2. Verify `styles.css` has the backdrop + transform rules; if missing, add:

   ```css
   @media (max-width: 1023px) {
     aside.sidebar {
       transform: translateX(-100%);
       transition: transform 250ms ease;
     }
     body[data-sidebar-open="true"] aside.sidebar {
       transform: translateX(0);
     }
     body[data-sidebar-open="true"] [data-sidebar-backdrop] {
       display: block;
     }
   }
   ```

3. Confirm hamburger keeps a higher effective z-index than aside when drawer is closed (it currently is, because aside is translated off-screen — but worth confirming).
4. Add `aria-expanded` + `aria-controls` on the toggle button for a11y.

**Spec impact.** Touches `COMPONENTS.md` § H.1 (sidebar mobile drawer spec — clarify close-button-inside-drawer + backdrop rule). No SCREENS.md change.

**Test plan.** Playwright at 375×812: open `/`, click hamburger, assert `body[data-sidebar-open]="true"`, click hamburger or close button, assert it flips back. Add `tests/test_mobile_sidebar.py`.

**Effort.** S — one DevTools session + 2 CSS rules + one new close button.

---

### Issue 3 — Tinder-style touch swipe missing on Discover

**Symptom.** Card stack at `/discover` only responds to keyboard (← / → / ↑ / ⏎). Touch / pointer drag does nothing.

**Reproduction.** DevTools mobile emulation 375×812 → `/discover`. Try to drag the card horizontally. No movement, no action.

**Root cause.** `src/ui/static/keys.js:66-71` registers keyboard handlers only. No `touchstart` / `touchmove` / `touchend` / `pointer*` listeners exist anywhere in the codebase. SCREENS.md § 7 line 391 explicitly promises "Touch: swipe gestures" — the spec was written, the implementation never landed. INTERACTIONS.md § F catalogue is keyboard-only.

**Fix proposal.** Implement pointer-event-based swipe (no library needed). Pattern (lives in `src/ui/static/keys.js`):

```javascript
function attachSwipe() {
  const card = document.getElementById("discover-card");
  if (!card || card._swipeAttached) return;
  card._swipeAttached = true;
  let startX = 0,
    startY = 0,
    dx = 0,
    dy = 0,
    dragging = false;
  card.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse") return; // mouse uses keyboard/buttons
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    dx = 0;
    dy = 0;
    card.setPointerCapture(e.pointerId);
  });
  card.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    dx = e.clientX - startX;
    dy = e.clientY - startY;
    card.style.transform = `translate(${dx}px, ${dy}px) rotate(${dx * 0.05}deg)`;
  });
  card.addEventListener("pointerup", () => {
    if (!dragging) return;
    dragging = false;
    const T = 80;
    if (dx < -T) document.getElementById("discover-skip-btn")?.click();
    else if (dx > T)
      document.getElementById("discover-auto-apply-btn")?.click();
    else if (dy < -T) document.getElementById("discover-save-btn")?.click();
    else card.style.transform = ""; // snap back
  });
}
document.addEventListener("DOMContentLoaded", attachSwipe);
document.body.addEventListener("htmx:afterSwap", attachSwipe); // re-attach after next-card swap
```

**Why pointer events not Hammer.js:**

- Pointer events are native (no 35KB CDN dep).
- The card is a single element; we don't need momentum or velocity physics — discrete threshold check is enough.
- Sortable.js (already loaded) is for list reorder, wrong primitive for directional swipe.

**Spec impact.** Add **INTERACTIONS.md § F.4 — Touch swipe conventions** documenting the pattern + thresholds. SCREENS.md § 7 line 391 already promises it; no change there.

**Test plan.** Manual at 375×812 in real-mobile-style emulation (pointer events fire). Playwright doesn't simulate pointer drag well — note in hand-back. Add `tests/test_keys_js.py` that asserts `attachSwipe` is registered (string check on the served `/static/keys.js`).

**Effort.** M — write swipe handler, wire IDs (already exist per plan 09 § F), update INTERACTIONS.md, smoke on real device.

---

### Issue 4 — Application questions are freeform; should be typed dropdowns

**Symptom.** `src/ui/templates/components/application_qs_form.html` renders all 9 EEO/visa fields as `<input type="text">`. User can type "Citizen of the Moon" instead of picking from the enum.

**Reproduction.** `/profile/edit` → scroll to `#application-qs` → all dropdowns are text inputs.

**Root cause.** `editor_field.html` defaults to `type="text"`. The enums exist (`src/models/enums.py:83-132` per the explore agent's read — `WorkAuthorization`, `VisaSponsorship`, `RelocateOpenness`, `VeteranStatus`, `DisabilityStatus`, `Race`, `Gender`); `src/db/sample_data_models.py` uses them; the UI just ignores them.

**Enum inventory** (from `src/models/enums.py`):

| Field                     | Type | Values                                                                                                           |
| ------------------------- | ---- | ---------------------------------------------------------------------------------------------------------------- |
| `work_authorization`      | enum | `us_citizen`, `green_card`, `h1b`, `opt_cpt`, `other_requires_sponsorship`                                       |
| `visa_sponsorship_needed` | enum | `not_needed`, `needed_now`, `needed_future`                                                                      |
| `willing_to_relocate`     | enum | `open`, `open_to_list`, `remote_only`, `no`                                                                      |
| `notice_period_days`      | int  | (already number input)                                                                                           |
| `salary_expectation_usd`  | int  | (already number input)                                                                                           |
| `earliest_start`          | date | (already date input)                                                                                             |
| `veteran_status`          | enum | `not_veteran`, `veteran`, `prefer_not_to_say`                                                                    |
| `disability_status`       | enum | `no`, `yes`, `prefer_not_to_say`                                                                                 |
| `race_ethnicity`          | enum | `asian`, `black`, `hispanic`, `native_american`, `pacific_islander`, `white`, `two_or_more`, `prefer_not_to_say` |
| `gender_identity`         | enum | `male`, `female`, `non_binary`, `prefer_not_to_say`                                                              |

**Fix proposal.**

1. Extend `components/editor_field.html` to support `type="select"` with an `options` arg accepting `[(value, label), …]`. Reuse the existing label / autosave-indicator / validation classes — no new component needed.
2. Add a small Python helper (`src/ui/template_helpers.py` — new file, or extend an existing utility module) that maps enum class → `[(value, human_label)]` so templates don't hardcode label text. Register the helper as a Jinja global so templates can call it.
3. In `application_qs_form.html`, replace each text-input include with a `type="select"` include passing the matching label list.
4. Update Profile read-only display (`src/ui/templates/pages/profile.html` § Application details) to render the enum value via the human label, not the raw `h1b`.
5. Per-field PUT autosave keeps working (the API accepts the enum string; `<select name="…">` submits the same payload).

**Spec impact.** None — DATA_MODEL.md § C / § D already specifies the enums; SCREENS.md § 5 says "Allowed values per field documented in `models/application_questions.py` (Phase 1.x)" which still holds. We're surfacing what was already canonical.

**Test plan.** Add `tests/test_application_qs_form.py`: GET `/profile/edit`, parse HTML, assert each field renders as `<select>` with the expected options and the seeded value pre-selected. Manual smoke: change a value, observe autosave indicator cycle saving → saved.

**Effort.** S — one component extension + 9 template swaps + label map + 1 read-only display fix.

---

### Issue 5 — Sidebar label "Jobs" vs route `/discover` is confusing

**Symptom.** Sidebar nav item 3 reads "Jobs" but routes to `/discover`. Page title there says "Discover". User finds the label-route mismatch jarring.

**Reproduction.** `/` → look at sidebar item 3 → click → URL is `/discover` and page reads "Discover".

**Root cause.** Historical drift: SCREENS.md § Sidebar IA (line 63) explicitly canonicalizes `Jobs → /discover` with reasoning that "Jobs" is the user-facing concept and "Discover" is the activity name. The page title leaked through as "Discover" because that's the action-oriented heading. Now the user finds the split confusing.

**Fix proposal — three options.** Spec change required either way; we surface the trade-off and let the user pick.

| Option                                           | Change                                                                                                                                                                                                                                                                                          | Trade-off                                                                                                                                                                      |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **A · Rename label to "Discover"**               | sidebar.html:64 `Jobs` → `Discover`; SCREENS.md § Sidebar IA line 63 update                                                                                                                                                                                                                     | Lower effort. Loses "Jobs" affordance for users who think in terms of "job search". Page heading + sidebar + URL all align on "Discover".                                      |
| **B · Rename route to `/jobs`**                  | All `/discover` → `/jobs` in routes, templates, links, plan 09 build artifacts. Page heading → "Jobs". SCREENS.md § Sidebar IA + § 7 + § 8 + § 11 + the screen index update; sample data unchanged. Keep `/discover/:id` as `/jobs/:id`. Update sidebar `active='jobs'` value to stay matching. | Higher effort. Familiar mental model for job seekers. Breaks any external links/bookmarks (none exist yet — pre-launch).                                                       |
| **C · Keep both, change page heading to "Jobs"** | Update `pages/discover.html` heading text to "Jobs". Sidebar stays "Jobs". URL stays `/discover`. SCREENS.md unchanged.                                                                                                                                                                         | Lowest effort. Sidesteps the URL-vs-label split — the label and heading match, URL is the only outlier. URL-vs-label split is a much milder issue than label-vs-heading split. |

**Recommendation.** **Option C** is the cheapest "fix" of the user complaint with no spec churn. **Option B** is the cleanest long-term semantics. **Option A** is the smallest spec change that resolves it. Implementer should defer to user pick at § H.

**Spec impact.** Whichever option chosen — SCREENS.md update (line 63 row label or row route, depending). If Option B, plan 09 archive needs a corrigendum line acknowledging the rename happened in 09a.

**Test plan.** Update existing `tests/test_pages.py` Discover assertions; if Option B, also update `tests/test_stub_endpoints.py` route prefixes.

**Effort.** A: XS. B: M (broad search + replace + spec edit + verify HTMX `hx-get`/`hx-post` references update too). C: XS.

---

### Issue 6 — Discover action bar buttons too big

**Symptom.** Four action buttons (`Skip · Save · Review & apply · Auto-apply`) stretch full-width via `flex-1` (`src/ui/templates/components/swipe_action_btn.html:39`). Buttons take more visual real estate than necessary, especially with the card at ~460px.

**Reproduction.** `/discover` desktop 1440×900. Buttons span the full card width as four equal columns.

**Root cause.** `swipe_action_btn.html:39` carries `flex-1` so each button claims `1fr` of the parent flex row. With a 460px parent + 3×12px gaps, each button gets ~106px. Adding the icon + label + keycap stacked vertically makes them tall and visually heavy.

**Fix proposal.**

1. Drop `flex-1` from `swipe_action_btn.html:39`. Add `min-w-[88px]` so buttons don't shrink below tap-target size.
2. Update `discover_action_bar.html:7` to `flex items-center justify-center gap-3` (so buttons size to content and the row centers under the card).
3. On mobile (<lg), keep buttons evenly-distributed at the bottom (matches SCREENS.md § 7 mobile note: "4 circular action buttons pinned to bottom"). Toggle: `flex-1 lg:flex-initial lg:min-w-[88px]` on the button class.
4. Update COMPONENTS.md § H.7 `swipe_action_btn` Visual spec to drop `flex-1` from the canonical class string and document the responsive variant.

**Spec impact.** COMPONENTS.md § H.7 (swipe_action_btn) — swap `flex-1` for `flex-1 lg:flex-initial lg:min-w-[88px]`. No SCREENS.md change.

**Test plan.** Manual at 1440×900: assert buttons size-to-content, centered. At 375×812: assert buttons fill row evenly. Update `tests/test_pages.py` if it asserts on this class string.

**Effort.** XS.

---

### Issue 7 — Discover swipe card too small to read JD inline

**Symptom.** Card hits `max-w-[460px]` at `src/ui/templates/components/swipe_card.html:17`. SCREENS.md § 7 line 358 explicitly specifies "Card (center, ~560px wide)" — implementation undershot.

**Reproduction.** `/discover` desktop. Compare card width against bundle JSX `screens/Discover.jsx`. Right rail is 280px; card is 460px; total = 740px in a viewport that's typically 1024–1440px wide. Lots of whitespace, JD bullets cramped in the 2-col card body.

**Root cause.** `swipe_card.html:17` hardcodes 460px against a spec calling for 560px. Plan 09 implementer was conservative.

**Fix proposal — three options.**

| Option                                                      | Change                                                                                                                                         | Trade-off                                                                                                                                                                                                                                         |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A · Match spec at 560px (recommended)**                   | `max-w-[460px]` → responsive `max-w-[460px] lg:max-w-[560px]`. Right rail at 280px stays. On desktop ≥1024px the layout fits cleanly.          | Aligns with spec. JD bullets get more breathing room. Mobile unchanged.                                                                                                                                                                           |
| **B · Bigger desktop, swipe-stack on mobile** (user's hint) | A + reorganize Discover layout: desktop = wide card with adjacent right-rail; mobile = swipe-stack center-aligned, no rail (already the spec). | Same as A in practice; the "mobile = swipe stack" already matches SCREENS.md § 7 mobile note. No additional work beyond A.                                                                                                                        |
| **C · Substantially larger card (700–800px)**               | Makes Discover feel like a hybrid card+detail view.                                                                                            | **Conflicts with SCREENS.md § 7** — the spec keeps Discover-as-swipe-queue and Discover-detail as `/discover/:id`. Going wider blurs the boundary; users may stop clicking through to the full workspace. Not recommended without spec amendment. |

**Recommendation.** Option A (= effectively Option B). Spec already accounts for the right behavior; we're catching up.

**Spec impact.** None for Option A — we're conforming to the existing spec. COMPONENTS.md § H.7 (swipe_card) Visual spec needs the width updated from `w-[460px]` to `max-w-[560px]`.

**Test plan.** Visual diff at desktop 1440×900 against bundle JSX.

**Effort.** XS.

---

### Issue 8 — `/discover/:id` is a separate full-page workspace; user expects in-place expansion

**Symptom.** Clicking "Review & apply" (or pressing ⏎) on a Discover card navigates to `/discover/:id` — a brand-new full-page 3-column workspace at `src/ui/templates/pages/discover_review.html`. User expects the workspace to expand in-place from the swipe card or open as a slide-over without losing the Discover queue context.

**Reproduction.** `/discover` → click Review & apply → URL changes, page replaces. Browser-back returns to queue but without state continuity.

**Root cause.** SCREENS.md § 8 line 406 spec mandates a full-page workspace — explicit phrasing: "Full-fidelity application workspace … Subsumes both prior `/generate/resume` and `/generate/cover-letter` standalone screens." `discover_review.html` returns a full page via `templates.TemplateResponse(...)` at `src/ui/routes/discover.py`. The user's intuition conflicts with the spec.

**Fix proposal — four options.**

| Option                                                               | Change                                                                                                                                                                                                                                                                                                                                                       | Trade-off                                                                                                                                                                                                                             |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A · Keep spec, polish the navigation**                             | Add a clear "← Back to queue" affordance (already present at `discover_review.html:409` per agent read; verify it's prominent + sticky). Add a fade/slide micro-animation on entry to signal "sub-page" rather than hard navigation. **No route change.**                                                                                                    | Smallest change. Spec stays. User gets visual continuity without architecture churn. May not satisfy the in-place-expansion expectation.                                                                                              |
| **B · Slide-over on top of Discover**                                | `/discover/:id` returns a fragment when called via HTMX (`hx-target="#review-overlay"`) that mounts as a full-height right-anchored panel on top of the Discover queue. Direct URL access still renders the full page (server detects no `HX-Request` header). Requires: split `discover_review.html` into `_overlay` + `_page` variants, route conditional. | Best matches user expectation. Bigger change. Spec amendment required (SCREENS.md § 8 — add overlay variant; INTERACTIONS.md § E — extend modal pattern to cover slide-overs). URL-shareable workspace UX still works via direct nav. |
| **C · Bottom-sheet on mobile, full-page on desktop**                 | Desktop: keep full page. Mobile: render as a `<dialog>` bottom sheet that swipes up from the card.                                                                                                                                                                                                                                                           | Inconsistent UX across devices. Hard to test. Not recommended.                                                                                                                                                                        |
| **D (Hybrid) · Inline expansion on Discover (single card "expand")** | Click on swipe card → card itself expands to show JD + tabs (resume / cover letter / screeners) in-place. `/discover/:id` page stays as direct-link target for sharing.                                                                                                                                                                                      | Closest to the "in-place expansion" wording. Requires major rework of `swipe_card.html` + `pages/discover.html` to host the expanded variant. SCREENS.md § 7 + § 8 both amend. Highest effort.                                        |

**Recommendation.** **Option B** is the cleanest match to the user's "in-place expansion" expectation and is implementable without a routing rewrite (server returns different responses based on `HX-Request` header). Option A is the cheap polish path if user is OK accepting the spec as-is.

**Spec impact.** Option A: none. Option B: SCREENS.md § 8 amend (add slide-over variant + URL-direct-load behavior); INTERACTIONS.md § E.4 amend or new § E.5 (slide-over pattern).

**Test plan.** Option A: manual click-through; assert "← Back to queue" is sticky and visible. Option B: Playwright at 1440×900 — open `/discover`, click Review, assert `#review-overlay` appears with the workspace; click backdrop, assert it closes; verify direct nav to `/discover/123` still renders full page.

**Effort.** A: XS. B: M-L. D: L+ (not recommended).

---

### Issue 9 — Profile right-rail anchor nav doesn't scroll-spy or highlight on click

**Symptom.** `/profile` right-rail "ON THIS PAGE" anchors render but the active state is hardcoded to "experience" at `src/ui/templates/pages/profile.html:141` (`active_id="experience"`). Clicking an anchor scrolls to the section but no highlight follows; scrolling doesn't update the active anchor.

**Reproduction.** `/profile` desktop ≥1024px. Right rail visible. Click "Skills" — page scrolls to skills, but "Experience" remains highlighted. Manually scroll — no change.

**Root cause.** `section_anchor_nav.html` renders `_is_active = a.id == active_id` once at template render time. COMPONENTS.md § H.3 spec says active state is "set via small JS in base.js" — but no scroll-spy code was ever added to base.js.

**Fix proposal.**

1. Add an IntersectionObserver to base.js that watches every `<section id="…">` on the current page and updates a `[data-active-anchor]` attribute on the nav element when a section enters the viewport (threshold 0.3, root margin `-20% 0% -60% 0%` so the active section is the one near the top of the viewport).
2. Update `section_anchor_nav.html` to use `[data-active-anchor]` for the active class instead of (or in addition to) `active_id`. CSS: `nav[data-active-anchor="skills"] a[href="#skills"] { …active styles… }`.
3. On anchor click, immediately set `data-active-anchor` to the clicked target (don't wait for scroll-end).
4. Initialize the observer on DOMContentLoaded and re-init on `htmx:afterSwap` (the nav itself doesn't get swapped, but profile content might via OOB updates).

**Spec impact.** COMPONENTS.md § H.3 `section_anchor_nav` — clarify "set via JS scroll-spy in base.js" with the threshold + margin spec. INTERACTIONS.md § I.1 — add row 8 "Anchor scroll-spy".

**Test plan.** `tests/test_pages.py` assert nav element exists with anchor links matching section IDs. Manual: scroll through `/profile`, assert active anchor follows. Playwright is shaky for scroll-spy testing — note in hand-back.

**Effort.** S — ~30 lines of JS + CSS update + spec amendment.

---

### Issue 10 — Mobile broken on multiple pages

**Symptom (vague — needs per-page reproduction).** Various mobile layout breakages. Implementer must reproduce at 375×812 and produce a per-page breakdown.

**Provisional issue list** from explore agent's static scan (severity-ordered):

| #    | Page            | Symptom                                                                                                                                   | Severity |
| ---- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| 10.a | `/discover/:id` | 3-column workspace stacks into a very tall single column with no nav between sections (JD / resume / cover letter / screeners)            | M        |
| 10.b | `/onboarding`   | Step content `min-h-[520px]` may overflow short mobile screens; form inputs don't compress                                                | M        |
| 10.c | `/tracking`     | Board/list sub-templates (`_tracking_board.html`, `_tracking_list.html`) need responsive audit — Kanban may not collapse to stacked cards | M        |
| 10.d | `/discover`     | 4-button action bar (resolved by Issue 6 fix) — verify after that lands                                                                   | S        |
| 10.e | `/` (Overview)  | Stacked sections (Priority actions + Email signal) get very tall, no max-height/scroll bound                                              | S        |
| 10.f | `/profile/edit` | Sortable.js bullet drag-handle isn't touch-friendly (drag-handle is small)                                                                | S        |
| 10.g | `/outreach`     | Left pane `min-h-[520px]` may overflow mobile                                                                                             | S        |

**Fix proposal.**

- **10.a (M):** Add a mobile-only tab nav at the top of `pages/discover_review.html` that switches between JD / Resume / Cover letter / Screeners sections (`hidden lg:hidden` on desktop; `block` on mobile). Each tab toggles a section's `hidden` class. No HTMX needed — pure JS or `<details>`/`<summary>` accordion.
- **10.b (M):** Drop `min-h-[520px]` on mobile (use `lg:min-h-[520px]` instead). Verify Onboarding extraction step doesn't overflow.
- **10.c (M):** Audit `_tracking_board.html` and `_tracking_list.html`. Add responsive collapse: Board view → stacked column list on mobile; list view → already wraps.
- **10.d (S):** Resolved by Issue 6 fix. Verify after.
- **10.e (S):** Add `lg:max-h-screen lg:overflow-y-auto` to the priority/signal sections so they're scrollable inside their column on desktop AND don't add page-length on mobile.
- **10.f (S):** Increase drag-handle tap target on mobile (`md:h-5 md:w-5` → `h-8 w-8 md:h-5 md:w-5`).
- **10.g (S):** Same pattern as 10.b — `lg:min-h-[520px]`.

**Spec impact.** SCREENS.md per-screen mobile annotations are placeholders today; harden them as we fix. Notably § 8 needs an explicit "Mobile: tab nav between JD / Resume / Cover letter / Screeners" line.

**Test plan.** `tests/test_pages.py` mobile-viewport variants: assert no horizontal overflow, assert key elements visible. Manual smoke at 375×812 across all 11 pages.

**Effort.** M (10.a, 10.c) + S (rest) ≈ 1.5 days.

---

## A.11 · Findings from the expanded testing pass

> **Status:** EXECUTED 2026-05-02 (server-side reproduction via `nix develop -c uv run fastapi dev src/main.py --port 8765` + curl + static analysis). Live browser DevTools verification of JS-runtime issues (1, 2) deferred to implementation phase since plan-mode forbade writing.
>
> **Baseline confirmed.** `uv run pytest tests/` → 225 passed, 33 warnings, 2.37s. `uv run ruff check .` → all checks passed. **No regressions to defend against.**

### A.11.1 — Per-page page-load smoke (all 11 screens GET 200)

| Screen            | Route                     | HTTP | Lucide `<i>` count | Notable                                            |
| ----------------- | ------------------------- | ---- | ------------------ | -------------------------------------------------- |
| Login             | `/login`                  | 200  | 1                  | one `key-round` icon in SSO info card              |
| Onboarding        | `/onboarding`             | 200  | 2                  | step indicator, dropzone                           |
| Overview          | `/`                       | 200  | many               | KPI strip + signals + pipeline render              |
| Profile           | `/profile`                | 200  | many               | hero + sections + right-rail                       |
| Profile editor    | `/profile/edit`           | 200  | **65**             | most icon-dense — Lucide failure most visible here |
| Discover          | `/discover`               | 200  | many               | swipe queue + right rail render                    |
| Discover · review | `/discover/101`           | 200  | many               | full 3-col workspace renders                       |
| Tracking          | `/tracking`               | 200  | many               | board view default                                 |
| Outreach          | `/outreach`               | 200  | many               | 2-pane renders                                     |
| Settings          | `/settings`               | 200  | 12                 | LLM tab default                                    |
| Bullet modal      | `/_modal/bullet-editor/1` | 200  | —                  | dialog renders inline                              |
| Confirm modal     | `/_modal/confirm?...`     | 200  | —                  | dialog renders                                     |

**Bonus check:** `/static/{base.js,keys.js,styles.css}` all 200. CDN preflights — Lucide `[email protected]/dist/umd/lucide.min.js` returns HTTP 302 → resolves to a working JS bundle (License header confirmed). Sortable JS, htmx CDN both responsive. **No CSP headers** sent by FastAPI → rules out CSP as a cause of Issue 1.

### A.11.2 — Issue corrections (from static + live audit)

**Correction to Issue 3 swipe-handler example.** Plan 09 § F documented button IDs as `discover-skip-btn` etc., but the **shipped templates use `skip-btn`, `save-btn`, `review-btn`, `auto-apply-btn`** (no `discover-` prefix). `keys.js` matches the shipped IDs. The Issue 3 swipe handler in this plan must use those actual IDs:

```javascript
if (dx < -T) document.getElementById("skip-btn")?.click();
else if (dx > T) document.getElementById("auto-apply-btn")?.click();
else if (dy < -T) document.getElementById("save-btn")?.click();
```

**Bonus visual feedback for Issue 3.** `swipe_card.html` already supports a `swiping_dir` argument (`"left" | "right" | "up"`) that renders a directional stamp ("SKIP" / "APPLY" / "SAVE"). The Issue 3 fix should also trigger this stamp visual during pointer-drag (toggle a CSS class on the card based on `dx`/`dy` sign + magnitude crossing a "stamp threshold" smaller than the action threshold — e.g., 30px to show stamp, 80px to commit). Tiny addition, big UX win — makes the gesture feel responsive before the action commits.

**Correction to Issue 1 root-cause ordering.** Live audit showed:

- Lucide CDN URL responds 302→200 with valid Lucide JS containing `lucide.createIcons` export.
- `<script src=".../lucide.min.js">` is in the served HTML (line 233 of /login response).
- `<i data-lucide="…">` placeholders ARE in the served HTML.
- No CSP headers sent — script will execute.

So the root cause is NOT (a) CDN broken or (c) script-tag missing — both ruled out. Most likely candidates remain: (b) `window.lucide` not exposed correctly OR a DOMContentLoaded race. **Implementer must confirm with browser DevTools first**: open `/profile`, type `typeof window.lucide` in console. If `"undefined"`, the bundle isn't exposing `window.lucide` (try a different version). If `"object"` and icons still don't render, the listener didn't fire — add the `readyState` fallback.

**Correction to Issue 2 root-cause ordering.** `styles.css:122-138` has the correct mobile-drawer CSS (`transform: translateX(0)` on `body[data-sidebar-open="true"] aside.sidebar`, `display: block` on the backdrop). So root cause (b) "missing CSS" is ruled out. **Confirmed root cause: z-index occlusion** (option a). When the drawer is open:

- Hamburger button (`fixed top-3 left-3 z-30`)
- Aside (`fixed top-0 left-0 z-40 w-64`) covers the hamburger area
- Click on hamburger area lands on aside → no `[data-sidebar-toggle]` match → handler does nothing

The fix is: add a close button INSIDE the drawer (not just outside it). Without that, users can only close via the backdrop (visible to the right of the open drawer) or by clicking a sidebar nav link. Both work, but neither is discoverable.

### A.11.3 — Verification of pre-existing issues (5–10)

All confirmed via served HTML:

- **Issue 5 (sidebar label):** `<span class="flex-1">Jobs</span>` at served `sidebar.html` line 64. URL is `/discover`. Page heading is "Discover".
- **Issue 6 (action bar):** `swipe_action_btn` rendered with `class="… flex-1 min-w-0 …"` at served line 427.
- **Issue 7 (card width):** `swipe_card` rendered with `class="… max-w-[460px] …"` at served line 201.
- **Issue 8 (full-page workspace):** `discover.py:36` returns `templates.TemplateResponse(request, "pages/discover_review.html", ctx)` — full page. Confirmed `/discover/101` returns 200 with full HTML payload (not a fragment).
- **Issue 9 (scroll-spy):** `pages/profile.html:141` passes `active_id="experience"`. `section_anchor_nav.html:13` uses `_is_active = a.id == active_id` set once at template render.
- **Issue 10 mobile:** Spot-checked `discover_review.html` for responsive utility classes — only **4** `lg:`/`md:`/`sm:` variants in the entire serialized response, vs 30+ on Profile editor. **Confirmed:** mobile layout is severely under-responsive on this screen specifically.

### A.11.4 — New issues found during expanded testing pass

These are the **new** items that warrant fixing in 09a (folded into the build sequence). Each gets the same treatment as issues 1–10.

#### Issue 11 — `discover_action_bar` button IDs are `skip-btn` / `save-btn` / `review-btn` / `auto-apply-btn` — global, not scoped

**Symptom.** The IDs are bare (no namespace prefix). If any future page uses an `id="skip-btn"` on a different button, the keyboard `←` shortcut would fire the wrong element. Also, the IDs leak the action verb without context — accessibility tools list them as ambiguous.

**Reproduction.** N/A today (no collision exists). Latent bug: any page that introduces a `Skip` / `Save` / `Review` / `Auto-apply` button with the obvious ID would conflict.

**Root cause.** Plan 09 chose unprefixed IDs against SCREENS.md spec (which suggested `discover-` prefix). It works today; it's brittle.

**Fix proposal.** Two options:

- **A · Leave as-is.** Add a code comment in `keys.js` + `discover_action_bar.html` noting the convention. **Spec impact:** SCREENS.md updates the prefix recommendation to "no prefix on Discover bar; namespace if reused elsewhere."
- **B · Rename to `discover-skip-btn` etc.** Update keys.js + the 4 button IDs + any tests that hardcode them. **Spec impact:** none (matches original spec).

**Recommendation.** B. Tiny rename, future-proof, matches plan-09 spec.

**Test plan.** Existing tests grep for the IDs; update them.

**Effort.** XS.

#### Issue 12 — Discover page rendered with `id="review-btn"` triggers Enter key BUT swipe card omits the button when card has `hx-get` to `/discover/{id}` — link wraps the card

**Symptom.** Card center is wrapped by `<a href="/discover/{id}">` (lines 553, 610, 667 in served Discover HTML — the "Up next" cards), but the swipe card itself uses a button row. Inconsistent affordance: clicking anywhere on the card body might behave differently between active and queued cards.

**Reproduction.** Hover/click queued card vs active card on /discover.

**Root cause.** Mixed convention — active card surfaces buttons; queued cards in the right rail use anchor wrappers. By design, but the user might find it inconsistent.

**Fix proposal.** Document the convention; not actually a bug. Defer to user judgment.

**Effort.** XS — could close with no code change + a note in COMPONENTS.md.

#### Issue 13 — Lucide CDN fingerprint check should also verify load-success

**Symptom.** No instrumentation to detect when CDN fails (e.g., user behind a corporate proxy that blocks unpkg.com). Icons silently don't render.

**Fix proposal.** Add a `<noscript>` fallback message? No — useless for users with JS who can't reach unpkg. Better: in `base.js`, after a small timeout (300ms), check if `window.lucide` exists; if not, log a console.error AND surface a single inline tooltip at the top of the page ("Icons couldn't load — check your network connection"). Users who can't reach unpkg get a clue.

**Recommendation.** Defer to Phase 1.x — over-engineering for MVP. Add a simple `console.warn` in 09a (already in Issue 1 fix proposal); the fancier UX detection is Phase 1.x.

**Effort.** N/A in this plan (deferred).

#### Issue 14 — `<dialog>` element backdrop click handler

**Symptom.** The bullet-editor modal serves `<dialog id="bullet-editor-modal" open>` with a backdrop `<div class="fixed inset-0 -z-10 bg-black/40">` and `hx-on:click="this.closest('dialog').close()"`. With `-z-10`, the backdrop sits BEHIND the dialog parent — but `<dialog>` inside `<dialog>` (the dialog is its own stacking context). Clicking outside the dialog content but inside the dialog's stacking context might not fire the close.

**Reproduction.** Open bullet-editor modal in a real browser; click outside the dialog content (in the gray overlay area); expect close.

**Root cause.** Native `<dialog>` element handles backdrop click ONLY via `dialog::backdrop` CSS pseudo-element (which IS clickable but the click event doesn't bubble through it). The custom `<div class="modal-backdrop">` pattern from INTERACTIONS.md § E.1 was designed for non-`<dialog>` modals. Since `<dialog>` is being used, the `-z-10` div's click handler may not fire reliably.

**Fix proposal.** Use the native `dialog::backdrop` pseudo-element + a top-level `<dialog>` close-on-backdrop pattern:

```javascript
dialog.addEventListener("click", (e) => {
  if (e.target === dialog) dialog.close(); // click landed on dialog itself, not its content
});
```

Add this to `base.js` as a global dialog-backdrop handler. Update INTERACTIONS.md § E.1/E.2 to reflect the native pattern.

**Spec impact.** INTERACTIONS.md § E.1, § E.2 — clarify backdrop handling for native `<dialog>`.

**Test plan.** Add a Playwright test (when local capture works) that opens any modal, clicks at viewport coordinates outside the dialog content, asserts dialog closes.

**Effort.** S — global handler + spec edit.

#### Issue 15 — Scroll-spy could also benefit Profile editor (optional)

**Symptom.** Profile editor (`/profile/edit`) doesn't have a right-rail anchor nav (per the spec it's not required), but as the page scales it might benefit. **Marked deferred** — not in 09a scope.

**Effort.** N/A (deferred to Phase 1.x).

### A.11.5 — Cross-cutting environment notes

- `uv run pytest` requires `uv sync --extra dev` to install pytest etc. The pyproject lists pytest under `[project.optional-dependencies] dev`. Without the `--extra dev`, `uv run pytest` falls back to nix-store pytest (Python 3.13) which can't import the venv's site-packages (Python 3.12). **Note for the implementation prompt:** include `uv sync --extra dev` in the boot checklist. Or have `uv sync` install dev by default — small README/devshell change worth considering as a Phase 1.x paper cut, NOT in 09a.

- Sample-data Job IDs are integers in the **101–127** range (27 jobs). Any test that hardcodes Job ID 1 will 404. Plan 09a tests should use `await sd.get_jobs()[:1].id` or fixture-derived IDs.

### A.11.6 — Things tested but no issue found

- Modal trigger URLs (`/_modal/bullet-editor/{id}`, `/_modal/confirm?...`) → 200, render correctly.
- Discover stub endpoints (`POST /api/v1/discover/124/skip`, `GET /_fragments/discover/next-card`) → 200, return HTML fragments of expected shape.
- All 11 page handlers respond 200 with valid HTML.
- Static assets (`/static/base.js`, `/static/keys.js`, `/static/styles.css`) → 200.
- CSP headers absent → rules out CSP as cause of any JS issue.
- SSE endpoints respond on GET (verified via Allow header in 405 response to HEAD).

---

## B · Build sequence (simplest first)

Updated 2026-05-02 after the testing pass folded in Issues 11 + 14 from § A.11.4.

1. **Issue 1 (Lucide)** — XS-S. Fix first because every other fix is easier to verify when icons render.
2. **Issue 2 (Sidebar toggle)** — S. Mobile fixes downstream depend on a working drawer.
3. **Issue 6 (Action bar sizing)** — XS. Tiny and resolves part of Issue 10.
4. **Issue 7 (Card width to 560px)** — XS. Conforms to existing spec.
5. **Issue 11 (Button ID rename)** — XS. Drop-in rename `skip-btn` → `discover-skip-btn` etc.; lands before Issue 3 so the swipe handler picks the new IDs.
6. **Issue 4 (Typed dropdowns)** — S. Self-contained.
7. **Issue 9 (Scroll-spy)** — S. JS-only; doesn't touch templates.
8. **Issue 14 (Dialog backdrop click)** — S. JS-only addition to base.js + spec edit.
9. **Issue 10 (Mobile, the rest of it)** — M. 7 sub-fixes (10.a–10.g).
10. **Issue 3 (Touch swipe)** — M. After Issue 10 because mobile fixes may surface adjacent Discover issues; uses the renamed IDs from Issue 11.
11. **Issue 5 (Sidebar label / route rename)** — XS or M depending on user pick.
12. **Issue 8 (Discover review in-place)** — XS or M-L depending on user pick. Last because biggest spec implication.

Reorder the build only if user re-prioritizes during plan review.

---

## C · Out of scope (forbidden patterns)

- Plan 10 / Wave 4 territory: DB models, JWT auth, real LLM, Typst, ATS adapters
- Paper cut #3: Playwright local capture on NixOS (its own track, POST_PHASE_1.md § Immediate paper cut #3)
- Don't break the 225 existing tests; add tests for each fix
- Don't refactor adjacent code unless blocking the fix
- Don't change SCREENS.md without surfacing the change in this plan first
- Don't touch CI / GitHub Actions
- Don't alter the dev orchestrator (`flake.nix`, `nix run .#dev`)

---

## D · Spec touch summary

| Issue | SCREENS.md                    | DESIGN.md | COMPONENTS.md                                | INTERACTIONS.md                        | DATA_MODEL.md |
| ----- | ----------------------------- | --------- | -------------------------------------------- | -------------------------------------- | ------------- |
| 1     | —                             | —         | —                                            | § I.1 (Lucide row)                     | —             |
| 2     | —                             | —         | § H.1 (sidebar mobile drawer + close button) | —                                      | —             |
| 3     | —                             | —         | —                                            | **new § F.4** (touch swipe)            | —             |
| 4     | —                             | —         | (editor_field type=select variant added)     | —                                      | —             |
| 5     | § Sidebar IA (one row)        | —         | —                                            | —                                      | —             |
| 6     | —                             | —         | § H.7 (swipe_action_btn class string)        | —                                      | —             |
| 7     | —                             | —         | § H.7 (swipe_card width)                     | —                                      | —             |
| 8     | § 8 (if Option B)             | —         | —                                            | § E (if Option B — slide-over pattern) | —             |
| 9     | —                             | —         | § H.3 (anchor nav active behavior)           | § I.1 (anchor scroll-spy row)          | —             |
| 10    | per-screen Mobile annotations | —         | —                                            | —                                      | —             |
| 11    | —                             | —         | (key.js + button-template ID rename)         | —                                      | —             |
| 12    | —                             | —         | —                                            | —                                      | —             |
| 13    | —                             | —         | —                                            | —                                      | —             |
| 14    | —                             | —         | —                                            | § E.1/E.2 (native dialog backdrop)     | —             |

---

## E · Phase 1.x deferred items (explicitly NOT in this plan)

If discovered during the testing pass, these go to `docs/plans/POST_PHASE_1.md` § Phase 1.x deferred — not into the active plan:

- Onboarding offline retry buffer for autosave (INTERACTIONS.md § H.3 — already deferred)
- `Show drafts` UI toggle on Tracking (already deferred)
- Application detail slide-over on Tracking (already deferred — Phase 2)
- Manual `+ Add` full modal on Tracking (already deferred)
- Scroll-spy across Profile editor (separate from Profile read-only, lower priority)
- Per-screen visual regression CI gate (depends on Playwright NixOS fix)

---

## F · Critical files

| Surface               | Files (with reason)                                                                                                                                                                                                                                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lucide / scripts      | `src/ui/templates/base.html:52` (CDN URL), `src/ui/static/base.js:14-21` (reinit)                                                                                                                                                                                                                                                     |
| Sidebar               | `src/ui/templates/components/sidebar.html:22-34` (toggle button + backdrop), `src/ui/static/styles.css` (read first, possibly add CSS), `src/ui/static/base.js:104-119` (handlers)                                                                                                                                                    |
| Discover surface      | `src/ui/templates/components/swipe_card.html:17` (width), `src/ui/templates/components/swipe_action_btn.html:39` (flex-1), `src/ui/templates/components/discover_action_bar.html:7` (gap), `src/ui/templates/pages/discover.html` (layout), `src/ui/static/keys.js:66-71` (add swipe handler)                                         |
| Discover review       | `src/ui/templates/pages/discover_review.html` (full page; if Option B, split into overlay + page), `src/ui/routes/discover.py` (response shape)                                                                                                                                                                                       |
| Application questions | `src/ui/templates/components/application_qs_form.html` (selects), `src/ui/templates/components/editor_field.html` (add type=select), `src/ui/templates/pages/profile.html` (read-only labels), new `src/ui/template_helpers.py` (label maps)                                                                                          |
| Profile anchor nav    | `src/ui/templates/components/section_anchor_nav.html` (data-active-anchor), `src/ui/templates/pages/profile.html:141` (drop hardcoded active_id), `src/ui/static/base.js` (add scroll-spy)                                                                                                                                            |
| Mobile (Issue 10)     | `src/ui/templates/pages/discover_review.html` (10.a), `src/ui/templates/pages/onboarding.html` (10.b), `src/ui/templates/components/_tracking_board.html` (10.c), `src/ui/templates/pages/overview.html` (10.e), `src/ui/templates/components/bullet_edit_row.html` (10.f drag-handle), `src/ui/templates/pages/outreach.html` (10.g) |
| Specs                 | `docs/design/SCREENS.md` (Sidebar IA, § 8, per-screen mobile), `docs/design/COMPONENTS.md` (§ H.1, H.3, H.7), `docs/design/INTERACTIONS.md` (§ I.1, new § F.4)                                                                                                                                                                        |
| Tests                 | `tests/test_pages.py` (extend), new `tests/test_mobile_sidebar.py`, new `tests/test_application_qs_form.py`, new `tests/test_swipe_handler.py` (string-check on keys.js)                                                                                                                                                              |

---

## G · Verification (end-to-end)

Per-fix: reproduce original symptom in browser → fix → confirm gone at desktop + mobile → run targeted pytest case.

After all fixes:

1. `uv run pytest tests/` — 225 + new tests, all green
2. `uv run ruff check .` clean
3. `uv run ruff format --check .` clean
4. Manual smoke at 1440×900 + 375×812 across all 11 pages
5. Hand-back report: per-issue verification (symptom gone? confirmed at both viewports?), file list, test results, any deviations from approved plan
6. Bump `ROADMAP.md` § Wave 3 row with a "Plan 09a follow-up applied 2026-MM-DD" note
7. Archive plan to `docs/plans/archive/09a-stage-3-bugfix.md` with `Status: EXECUTED`

---

## Open questions

1. **Issue 5 — label vs route rename.** Which option do you want? A (rename label "Jobs" → "Discover"), B (rename route `/discover` → `/jobs`), or C (rename heading on Discover page to "Jobs", keep label + URL)?
2. **Issue 8 — full-page vs slide-over.** Which option do you want? A (cheap polish; keep spec) or B (slide-over via HTMX fragment + direct-load fallback; matches user expectation better)?
3. **Issue 4 — read-only Profile display.** Should the read-only Profile show human labels (e.g., "H1B · Requires sponsorship") or raw enum values (e.g., "h1b")? Recommend human labels.
4. **Issue 10.a — Discover review mobile nav.** Tab nav vs accordion (`<details>`)? Recommend tabs (matches the desktop tab metaphor).
5. **Test coverage.** Add new tests inline with each fix, or one consolidated `test_09a_bugfix.py` at the end? Recommend inline.

---

## Approval checklist

User ticks each item before plan moves to APPROVED. Agent does NOT begin implementation until all relevant items are ticked.

### Per-issue approval

- [x] Issue 1 — Lucide fix approach (start with DevTools diagnosis: `typeof window.lucide`; then add `console.warn` in the silent guard + `readyState` fallback in base.js; revisit CDN URL only if `window.lucide` is undefined)
- [x] Issue 2 — Sidebar toggle fix (**confirmed root cause is z-index occlusion; CSS is correct**) — add close button INSIDE drawer with `data-sidebar-toggle`; add `aria-expanded`/`aria-controls`; consider a fade for the backdrop
- [x] Issue 3 — Touch swipe via pointer events (no Hammer.js); use **shipped IDs `skip-btn`/`save-btn`/`review-btn`/`auto-apply-btn`** OR the renamed IDs after Issue 11 lands; wire the existing `swiping_dir` stamp visual into the drag
- [x] Issue 4 — Typed dropdowns via `editor_field` `type="select"` extension + label maps
- [x] **Issue 5 — pick one:**
  - [x] Option A (rename label "Jobs" → "Discover")
  - [ ] Option B (rename route `/discover` → `/jobs`)
  - [ ] Option C (rename heading on Discover page to "Jobs", keep label + URL)
- [x] Issue 6 — Drop `flex-1` on action buttons; `lg:flex-initial lg:min-w-[88px]` + center on desktop
- [x] Issue 7 — Bump card width to 560px on `lg+` (`max-w-[460px] lg:max-w-[560px]`)
- [x] **Issue 8 — pick one:**
  - [ ] Option A (keep spec; polish back-to-queue affordance)
  - [ ] Option B (slide-over over Discover via HTMX fragment + direct-load fallback)
  - [x] Option D (in-place card expansion — note: highest effort, biggest spec change)
- [x] Issue 9 — IntersectionObserver scroll-spy + nav `data-active-anchor`
- [x] Issue 10 — Per-page mobile fixes (10.a–10.g)
- [x] **Issue 11 (NEW) — Discover button IDs:** Option B (rename to `discover-skip-btn` / etc., matches plan-09 spec) — recommended; OR Option A (leave bare, add code comment)
- [x] **Issue 14 (NEW) — Dialog backdrop click:** add native `<dialog>` click-on-self handler in base.js; spec amendment to INTERACTIONS.md § E.1/E.2

### Process

- [ ] Build sequence (§ B) ordering acceptable
- [ ] Out-of-scope (§ C) — nothing missing
- [ ] Spec touches (§ D) — all amendments authorized
- [ ] Phase 1.x deferred items (§ E) — these stay deferred
- [x] ✅ **Plan author ran the expanded testing pass; § A.11 documents 4 new actionable findings (Issues 11, 12, 13, 14) + verifies/corrects root causes for issues 1–10. Awaiting user re-tick of expanded checklist before code lands.**

### Open questions

- [x] Q1 — Issue 5 option pick recorded - go with A
- [x] Q2 — Issue 8 option pick recorded - go with D
- [x] Q3 — Read-only Profile display: human labels (recommended) or raw enum - this must be a predefined set of enums that we will have in the db or somewhere which defines what are the different options that can be present. We will start with a good set of default options and then add to it later. i dont know if thats human labels or raw enum. for example h1b doesnt make sense. what is usually asked in job applications is will you require sponsorship now or in the future - yes/no etc
- [x] Q4 — Issue 10.a mobile nav: tabs (recommended) or accordion - tabs
- [x] Q5 — Test coverage layout: inline (recommended) or consolidated - inline

---

## Hand-back format (after implementation)

- File list (all changes)
- Test results: pytest counts before/after, ruff status
- Per-issue verification table: 10 (+ A.11) rows, each with symptom-gone-at-desktop? symptom-gone-at-mobile? test added?
- Any deviations from this approved plan
- ROADMAP.md + SCREENS.md / COMPONENTS.md / INTERACTIONS.md diff summary
- Archive instructions executed
