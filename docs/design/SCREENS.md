# Naavik Screen Catalog

> **Last updated:** 2026-05-20 (plan 36 / `0.2.0.11a` — added screen #12 Job detail at `/jobs/{id}`; canonical contract for the Job-UI surface lives at `docs/design/JOB_UI.md`)
> Earlier line: 2026-05-02 (plan 09a · Issue 5A — sidebar label "Jobs" renamed to "Discover" so sidebar / URL / page heading align)
> **Source of truth:** This file. Where this disagrees with mockups, archived prompts (`docs/prompts/archive/`), or older drafts, this wins.
> **Companion files:** `DESIGN.md` (visual contract) · `docs/design/WORKFLOW.md` (UI sub-process pipeline).
>
> **Mockup references** (gitignored, kept locally; see `docs/design/mockups/README.md` for setup):
>
> - **PDF:** `docs/design/mockups/Naavik — MVP screens (print).pdf` — historical 12-section export. PDF sections 1–8 = SCREENS.md sections 1–8; **PDF section 9 (standalone Cover Letter) is orphaned**; PDF sections 10/11/12 → SCREENS.md sections 9/10/11.
> - **Bundle JSX (most detailed visual reference):** `docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx`. Each screen entry below names the JSX file. The bundle's CSS tokens (`naavik-handoff/project/design-system/colors_and_type.css`) match `DESIGN.md` — read DESIGN.md for tokens, not the bundle.
> - **Bundle obsolete files** to ignore: `Analytics.jsx`, `Dashboard.jsx`, `Jobs.jsx`, `ResumeGen.jsx`, `CoverLetter.jsx` (see `docs/design/mockups/README.md`).

---

## How to read this doc

Each screen entry has:

- **# / Title** — section number from the mockup PDF
- **Route** — URL path the FastAPI handler answers
- **Sidebar label** — what shows in the persistent sidebar (may differ from the screen title)
- **Phase** — when it ships, per `ROADMAP.md`
- **Mockup** — `[ ]` not designed · `[~]` in design · `[x]` mockup committed
- **Impl** — `[ ]` not built · `[~]` in progress · `[x]` shipped
- **Purpose** — one sentence
- **Layout** — high-level structure
- **Components** — partials in `src/ui/templates/components/` (specs in `DESIGN.md`)
- **Copy** — exact strings visible in the mockup; treat as locked unless explicitly redesigned
- **Interactions** — HTMX swaps, keyboard, modals, integrations
- **States** — empty / loading / error / variant

---

## Application status pipeline

Naavik tracks applications through six stages. The visible pipeline on Tracking is five (`APPLIED` → `CLOSED`); `DRAFT` and `CLOSED` are hidden by default. Closed states (rejected / withdrawn / ghosted) collapse into one bucket via `closed_reason`.

| Status | Dot color | Meaning |
|---|---|---|
| `DRAFT` | `bg-slate-500` | Pre-submission bundle exists (auto-apply queued OR manual review-and-apply in flight). Hidden in Tracking by default; surfaced in Discover · review & apply and the Auto-apply queue card on Discover. |
| `APPLIED` | `bg-indigo-500` | Submitted; awaiting recruiter response |
| `RECRUITER_SCREEN` | `bg-cyan-500` | Recruiter-side conversation underway |
| `ONSITE_LOOP` | `bg-amber-500` | In onsite / interview loop |
| `OFFER` | `bg-emerald-500` | Offer extended (verbal, written, or accepted) |
| `CLOSED` | `bg-rose-500` | Rejected, withdrawn, or ghosted (sub-reason in `closed_reason`) |

Pre-application discovery (find → score → swipe) lives in Discover (`/discover`), not Tracking. The Job's pre-application queue lifecycle is a separate axis (`unswiped · saved · skipped · queued_for_auto_apply · applied`) on the Job model, not on Application. The Application row exists from the moment a bundle is generated (auto-apply queue or manual review entry) — `DRAFT` is its initial status; `APPLIED` is set on successful ATS submit.

The five visible `Application.status` values (`APPLIED` → `CLOSED`) are the **post-submission** pipeline. `DRAFT` is the pre-submission bucket. **Document generation, referral status, recruiter engagement, and outreach engagement are tracked as orthogonal sub-states on Application — not as additional pipeline stages.** A single application can be `RECRUITER_SCREEN` + `referral_state=provided` + `docs_state=ready` simultaneously. See `docs/design/DATA_MODEL.md` (graduated from plan 05) for the full multi-axis state model. The flat `FOUND · SCORED · APPROVED · DOCS_GENERATED · INTERVIEWING · REJECTED · WITHDRAWN` enumeration is **not** in the model; those concerns live on dedicated axes (queue_state, docs_state, recruiter_state, closed_reason).

**Tracking visibility rule:** Board / List views default to `status IN (APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER)`. Closed bucket toggle adds CLOSED. A `Show drafts` filter (deferred to Phase 1.x) reveals DRAFT rows for users who want to see the queue depth.

---

## Sidebar information architecture

Persistent left sidebar, 256px wide on desktop, drawer on mobile.

| Order | Label | Lucide icon | Route | Badge |
|---|---|---|---|---|
| 1 | Overview | `layout-dashboard` | `/` | — |
| 2 | Profile | `user-round` | `/profile` | — |
| 3 | Discover | `briefcase` | `/discover` | live count of unswiped matches (e.g. `47`) |
| 4 | Tracking | `inbox` | `/tracking` | live count of items needing followup (e.g. `12`) |
| 5 | Outreach | `send` | `/outreach` | — |
| 6 | Settings | `settings` | `/settings` | — |

**Bottom of sidebar:** user avatar + name + deployment badge — `self-hosted` (emerald-tinted) or `cloud` (indigo-tinted).

**Removed from prior IA:** standalone Resume route (folded into Discover · review & apply), standalone Cover Letter route (folded into Discover · review & apply — there is no `/generate/*` route), Analytics route (folded into Overview), Jobs route (renamed to Discover at `/discover`), theme switcher (single dark mode).

---

## Tag vocabulary

Bullets, jobs, and match scores share a 9-tag vocabulary. Tags are auto-generated by the LLM during resume parse and on every new bullet/role added; user can edit.

`ai-ml` · `backend` · `frontend` · `devops` · `data-eng` · `genai` · `leadership` · `platform` · `product`

Tags render as chips: `bg-slate-800 text-slate-300 text-xs font-mono px-2 py-0.5 rounded`. **No AI sparkle icon on tag chips** (sparkle is reserved for AI-generated *content*, not metadata).

---

## Screen Index

| # | Title | Route | Sidebar | Phase | Mockup | Impl |
|---|---|---|---|---|---|---|
| 1 | Login | `/login` | (auth shell, no sidebar) | 1 | [x] | [x] |
| 2 | Onboarding · resume upload | `/onboarding` | (no sidebar) | 1 | [x] | [x] |
| 3 | Overview | `/` | Overview | 1 | [x] | [x] |
| 4 | Profile | `/profile` | Profile | 1 | [x] | [x] |
| 5 | Profile editor | `/profile/edit` | Profile | 1 | [x] | [x] |
| 6 | Bullet editor modal | (component, opens from #5 + #8) | — | 1 | [x] | [x] |
| 7 | Discover | `/discover` | Jobs | 1 | [x] | [x] |
| 8 | Discover · review & apply | `/discover/:id` | Jobs | 1 | [x] | [x] |
| 9 | Tracking | `/tracking` | Tracking | 1 | [x] | [x] |
| 10 | Outreach | `/outreach` | Outreach | 1 | [x] | [x] |
| 11 | Settings | `/settings` (+ tab sub-routes) | Settings | 1 | [x] | [x] |
| 12 | Job detail | `/jobs/{id}` | Discover (active — destination, not list) | 2 | [ ] | [x] |

The MVP set is **11 screens**; screen 12 (Job detail) ships in Phase 2.0 (`0.2.0.11`) as the read-only Job surface distinct from the application workspace at `/discover/{id}`. The historical mockup PDF (committed at `docs/design/mockups/Naavik — MVP screens (print).pdf`) was generated when there were 12 sections; the prior standalone Cover-letter screen has been folded into Section 8 (Discover · review & apply). Once the next Claude Design handoff produces standalone exports, individual PNGs commit alongside the PDF using the naming `{nn}-{slug}-{desktop|mobile}.png`.

---

## Phase 1 (MVP) screens

### 1. Login

- **Mockup:** PDF § 1 · bundle `screens/Login.jsx`
- **Route:** `/login`
- **Sidebar:** none (auth shell)
- **Purpose:** Single sign-in entry point. Establishes the "self-hosted developer tool" feel before any other surface.
- **Layout:** Faint compass-pattern motif on `bg-base`. Top-left: brand lockup with `v0.4.2 · self-hosted` (or `cloud`) version pill. Top-right: green `API ONLINE` dot. Center: `bg-surface` card, ~440px wide.
- **Card:**
  - Naavik logo + wordmark
  - "Welcome back" title
  - "Sign in to your Naavik instance." subtitle
  - `EMAIL` input
  - `PASSWORD` input
  - "Keep me signed in on this device" checkbox (default checked)
  - **Sign in** primary button (full-width)
  - Indigo-tinted info card with key icon: "**SSO coming soon.** Self-hosted instances will support OIDC providers like **Authentik**, Keycloak, and Okta."
  - Footer row: "Create account · Docs · Source"
- **Auth model:** Email + password (bcrypt). OIDC for self-hosted is Phase 2+.
- **Interactions:** Submit `POST /api/v1/auth/login` → HTTP-only JWT cookie → redirect: `/onboarding` if no profile, else `/`.
- **States:**
  - Default — empty form, button enabled
  - Loading — button content swaps to spinner + "Signing in..."
  - Error — rose-tinted alert above the button: "Invalid credentials" / "Server unreachable" / "Account locked — see logs"
- **Components:** `auth_shell.html`, `card.html`, `input.html`, `button.html`, `info_card.html`, `version_pill.html`, `api_status_dot.html`

---

### 2. Onboarding · resume upload

- **Mockup:** PDF § 2 · bundle `screens/Onboarding.jsx`
- **Route:** `/onboarding` (3-step wizard). Routes to `/` on completion.
- **Sidebar:** none (full-width centered)
- **Purpose:** Convert PDF resume → structured profile via local AI extraction. First-run experience.
- **Top:** Naavik logo + `setup` badge. Step indicator: **1 Upload — 2 Extracting — 3 Review**. Active = indigo-filled, completed = emerald check, queued = muted slate.

#### Step 1 · Upload
- Title: "Upload your resume"
- Subtitle: "Drop a PDF and we'll extract your profile. Everything stays on your machine — your file never leaves the container."
- Drop zone (`h-96`, dashed border): cloud-upload icon, "Drop your resume here", "or" divider, **Browse files** primary button. Below: "PDF only · max 10 MB"
- Footer hint with lock icon: "Parsed locally · never sent to third parties"
- Affordance: "Skip — enter manually" ghost link

#### Step 2 · Extracting (the hero state)
- Sparkle-icon card (cyan tint, faint glow): "Reading your resume..." + filename + "est. Ns remaining"
- Checklist with state indicator + per-row count:
  - ✓ Reading PDF structure — "4 pages · 1.2 MB"
  - ⊙ Identifying experience — "2 of 4 roles parsed"
  - ⊙ Extracting skills — "17 found"
  - ○ Categorizing bullets — "queued"
  - ○ Generating summary — "queued"
- Gradient progress bar (indigo → cyan)
- Below: "Extracted so far · `AI` · 4 of 6 fields" card with confidence-scored rows (mono numbers, emerald):
  - `NAME` Shyam Padia — `0.99`
  - `TITLE` Senior Software Engineer · Intuit — `0.96`
  - `LOCATION` San Francisco, CA — `0.92`
  - `EXPERIENCE` 8 years · 4 roles — `0.88`
  - `SKILLS` Python, ML, distributed systems… (in progress)
  - `EDUCATION` (skeleton bar, queued)
- Updates via SSE preferred, HTMX polling fallback.

#### Step 3 · Review
- Sectioned preview (Experience / Education / Skills / Projects / Certifications). Each section: "Looks good" / "Edit" actions.
- Application Readiness gate (info banner): "Add the EEO/visa fields most US applications require." → links to Profile editor's `#application-qs` anchor.
- Footer: **Save to profile** primary CTA → `POST /api/v1/profile/from-extraction` → `/`

- **Components:** `step_indicator.html`, `dropzone.html`, `extraction_checklist.html`, `extracted_field_row.html`, `progress_bar.html`, `ai_badge.html`
- **States:** failure on Step 2 → partial-failure card "Couldn't parse education section — proceed without it?"

---

### 3. Overview

- **Mockup:** PDF § 3 · bundle `screens/Overview.jsx`
- **Route:** `/`
- **Sidebar label:** Overview (active)
- **Purpose:** Daily landing. What to do *today*, KPIs at a glance, live pipeline.
- **Layout:** sidebar + main. Main is a vertical stack:
  1. Header row — greeting + date pill
  2. KPI row — 4 stat cards
  3. Two-column body — left 2/3 priority actions, right 1/3 email signal
  4. Pipeline · live — horizontal mini-Kanban

#### Header
- Time-aware greeting "Good morning, Shyam." / "Good afternoon, …" / "Good evening, …"
- Sub-line: "{N} priority actions queued for today · {M} offer awaiting reply" (variant: "no action items today")
- Top-right pill: `Tue · Apr 29 · 09:14 PT` (mono, current local time)

#### KPI row (4 cards)

| Label | Value | Subtitle / delta |
|---|---|---|
| `ACTIVE APPLICATIONS` | `29` | `across 5 stages` |
| `RESPONSE RATE · 90D` | `11.3%` | `+2.1%` (emerald) · `3× market avg` |
| `ONSITE RATE` | `4.2%` | `-0.4%` (rose) |
| `OFFER RATE` | `1.4%` | `+0.7%` (emerald) · `2 offers · 1 pending` |

These are funnel KPIs, not raw counts. (No "Jobs Found / Applied / Interviews / Offers" cards.)

#### Priority Actions (left, 2/3)
- Header: ☑ "PRIORITY ACTIONS" + cyan `# ranked` chip · right "Mark all done"
- Numbered rows (`01`, `02`, …):
  - Event-type icon (sparkle = offer, video = interview, inbox = reply, clock = silent)
  - Title — e.g., "Respond to Figma offer"
  - Subtitle with context — "$290k base + 0.04% · verbal extended Apr 28 · they expect a reply by Thu"
  - Urgency badge (rose `TODAY`, amber `TOMORROW`, slate `14M AGO`, rose `6D SILENT`)
  - Action CTA — "Open offer" / "Open prep notes" / "Reply" / "Send nudge"
- Footer link: "See all 14 open items in tracking →" (→ `/tracking`)

#### Email signal (right, 1/3)
- Header: "Recent email signal" + subtle `auto-detected · gmail` chip
- 4–6 rows. Each: sender avatar (company-letter tile), subject preview, sender label, status pill (`Offer` emerald · `Interviewing` amber · `Rejected` rose), match score (mono cyan), relative time
- Footer: "See all 18 signals in tracking →"

#### Pipeline · live (full-width, bottom)
- Header: "Pipeline · live" · right "{N} active · last sync 2m ago"
- 5-column strip with status dots and counts (Applied · Recruiter · Onsite · Offer · Closed). Compact card render at this scale.

- **Empty state** (no applications yet): hide KPIs, show single CTA card: "Welcome. Upload your resume to get started." → `/onboarding`
- **Components:** `kpi_card.html`, `priority_action_row.html`, `email_signal_row.html`, `status_dot.html`, `pipeline_strip.html`

---

### 4. Profile

- **Mockup:** PDF § 4 · bundle `screens/Profile.jsx`
- **Route:** `/profile`
- **Sidebar label:** Profile (active)
- **Purpose:** Read-only view of the user's full profile. This IS their CV in the system.
- **Layout:** sidebar + main + sticky right "ON THIS PAGE" nav (~240px).

#### Hero card
- Avatar tile (purple→indigo gradient with initials)
- Name (display size)
- Title · Company subtitle
- Location pin · "Open to opportunities" indicator (when `open_to_opportunities` is true)
- Contact chips (rounded-full): mail / phone / `/handle` (github) / `/in/handle` (linkedin) / portfolio domain
- Top-right: **Edit profile** (secondary, pencil) · **Update resume** (primary, upload icon)

#### Body sections (anchored)
- **Summary** — short + full toggle ("Expand"/"Collapse")
- **Experience** — `{N} of {M} roles` count in subhead. Per-role card: company-letter tile, title, "Company · Location", "Date — Date · {dur}", bullet list (text + tag chips inline). Expand-affordance reveals all bullets for the role (each bullet is a single long-form text — at apply time the AI selects which ones land on the tailored resume based on tag relevance + JD signals + per-bullet `selection_override`).
- **Application details** — read-only display of EEO/visa values (e.g., "Work authorization: US citizen · Visa sponsorship: Not needed · Veteran: Prefer not to say"). Editable in Profile editor's `#application-qs` section.
- **Skills** — grouped by category, tag chips per group
- **Education** — card list
- **Projects** — card grid (3 columns desktop, 1 mobile)
- **Certifications** — compact list

#### Right rail (sticky)
- "ON THIS PAGE" caption
- Anchor links: Summary · Experience (active) · Application details · Skills · Education · Projects
- Below the anchors: **APPLICATION READINESS** card (only if any required fields missing):
  - Title: "{N} missing" (amber count)
  - "Required by most US applications. Without these, jobs needing them will be skipped."
  - Field rows (✓ filled / ○ empty):
    - Work authorization — `US citizen` / `Green card` / `Visa`
    - Visa sponsorship needed — `Yes` / `No`
    - Veteran status — `add`
    - Disability status — `add`
    - Race / ethnicity (EEO) — `add`
    - Gender — `Prefer not to say`
  - "Complete now →" CTA (→ `/profile/edit#application-qs`)

- **Mobile:** stacks. Hero card, then tabs (Summary / Experience / Application details / Skills) above the section content. Visa badge "H1B · Requires sponsorship" rendered prominently in the hero.
- **States:** First-load empty (no profile) → redirect to `/onboarding`. Some sections empty → "+ Add education / certifications / projects" inline affordances.
- **Components:** `profile_hero.html`, `contact_chip.html`, `experience_card.html`, `bullet_row.html`, `tag_chip.html`, `section_anchor_nav.html`, `application_readiness_card.html`

#### Score history sparkline (plan 73 / 0.3.2.03 — graduated 2026-05-21 via plan 75 / 0.3.3.21)

Inline-SVG 14-day score trend strip rendered in the Profile hero (Variant A · hero strip, locked at PLAN_GATE Q73.5).

- **Data source:** `Profile.score_history` JSONB (canonical shape in DATA_MODEL.md § `Profile`). Read via `services.profile_service.get_score_history(session, user_id)`.
- **Render:** 14-day score trend per role family, rendered as inline SVG `<polyline>` — no JS, no Chart.js. Stroke uses indigo-500 (matches DESIGN.md token); fill is `rgba(99, 102, 241, 0.1)` for the underline area.
- **Role-family selector:** dropdown above the sparkline; default = the user's most-active family (highest `scored_count_30d` in `score_history.families`). 9-tag vocabulary (see § Tag vocabulary).
- **Empty state:** when `score_history` is `null`, empty `families` array, OR every `daily_means[i]` is null, render the empty-state placeholder: "Score 0 jobs to see your trend" + a CTA chip linking to `/discover`.
- **HTMX refresh:** Profile page is server-rendered on each visit so sparkline reflects the latest cron run (03:35 UTC daily). No HX-Trigger refresh on this surface today — the cron writeback runs ahead of typical user-load patterns. Future: `HX-Trigger: score-history-updated` emitted by the cron writeback could swap the strip in-place.
- **Mobile:** sparkline scales to container width; role-family selector collapses into a single-line label + arrow tap target.
- **Components:** rendered inline in `profile_hero.html` (no new partial — Q73.4 lock prohibits a new `/scores` route).

---

### 5. Profile editor

- **Mockup:** PDF § 5 · bundle `screens/ProfileEdit.jsx`
- **Route:** `/profile/edit`
- **Sidebar label:** Profile (active)
- **Purpose:** Edit every field. Tag autosuggest, EEO/visa Qs, autosave (no Save button).
- **Layout:** Same shell as Profile. Top breadcrumb "Profile > Edit". Top right: `Auto-saved 12s ago` chip · "Preview" · "Discard".

#### Identity card
- 4-column grid: `FULL NAME` · `HEADLINE` · `CURRENT COMPANY` · `LOCATION`

#### Experience card (one per role)
- Header: "Experience · {Company}" + "Duplicate role" + "Remove" actions
- 3-column inputs: `TITLE` · `START` · `END` (with `Present` sentinel)
- `BULLETS · {N}` list:
  - Each row: drag-handle (`grip-vertical`), bullet text (truncated preview, single long-form), tag chips, edit-pencil + trash icons on hover. If `selection_override` is set, a small `pinned · always` (emerald) or `pinned · never` (slate) chip appears; default null = AI auto-decides per JD with no chip.
  - Edit-pencil opens **Bullet editor modal** (Section 6)
  - "+ Add bullet" ghost button

#### Application questions section (anchor `#application-qs`)
- Section title: "US application questions" · "United States" region pill
- Note: "Most US-based job applications ask these. We answer them once and apply automatically. We never share these outside Naavik."
- Field grid with inline edit: Work authorization · Visa sponsorship needed · Veteran status · Disability status · Race / ethnicity (EEO) · Gender
- Allowed values per field documented in `models/application_questions.py` (Phase 1.x).

- **Interactions:** HTMX `PUT` per field on blur (debounced 500ms). Drag reorder via Sortable.js (the only place we allow JS beyond HTMX). Auto-save status updates with HTMX OOB swap.
- **States:** Saving (spinner + "Saving…"), Saved (emerald check + "Auto-saved Ns ago"), Error (rose alert + "Couldn't save — retry").
- **Mobile:** stacks. Per-role card collapses; "Edit · {Company}" header pinned. Bullet rows show truncated text + tags; bullet edit opens bottom-sheet.
- **Components:** `editor_field.html`, `editor_card.html`, `bullet_edit_row.html`, `application_qs_form.html`, `autosave_indicator.html`

---

### 6. Bullet editor modal

- **Mockup:** PDF § 6 · bundle `screens/BulletModal.jsx`
- **Component, no route.** Opens from Profile editor and from Discover · review & apply.
- **Purpose:** Edit a single bullet. **Single field — no oneline/detailed split.** AI trims at apply time.
- **Layout:** Modal, ~720px wide on desktop; bottom sheet on mobile.

#### Header
- "Edit bullet" + role context "· {Company} · {Title}"
- Close `×`

#### Body
- `BULLET` label, top-right hint: "write the long version — Naavik trims to fit"
- Single textarea (multi-line, autosize, no length cap)
- Sparkle-icon explainer card (cyan-tinted): "At apply time Naavik picks the bullets that fit the JD and rewrites each one to land on a single line — keeping your numbers and verbs intact. You don't need to maintain two versions."
- `TAGS · {N} SELECTED` label, hint right: "used to match jobs · click to toggle"
- Tag picker — the 9-tag vocabulary as chips. Selected = indigo bg, unselected = slate bg. **No sparkle on chips.**

#### Selection override
- Section header: `SELECTION OVERRIDE`
- Two mutually-exclusive option cards (radio behavior):
  - ☐ "Always include this bullet" — "Pin it on every tailored resume regardless of JD match." `auto` chip on right
  - ☐ "Never include this bullet" — "Keep it for context but hide it from outgoing applications." `auto` chip on right
- Default: neither (= AI auto-decides per JD)

#### Footer
- Left: **Rewrite with AI** (sparkle, ghost) · **Delete** (trash, ghost)
- Right: "Cancel" · **Save bullet** (primary)

- **Removed from prior spec:** oneline/detailed split, char counter, live Typst preview, metrics fields (revenue / percentage / team-size), `default_include` toggle.
- **Mobile:** bottom sheet — drag handle, `BULLET` field with "full version" hint chip, tag chip row, full-width Save.
- **Interactions:** `PUT /api/v1/bullets/:id` on Save → swaps the bullet row in parent view via HTMX OOB. Delete → confirm dialog → `DELETE /api/v1/bullets/:id`. "Rewrite with AI" → `POST /api/v1/bullets/:id/rewrite` → swap textarea content, mark `edited` chip.
- **Components:** `modal.html`, `tag_picker.html`, `selection_override.html`, `bullet_textarea.html`

---

### 7. Discover

- **Mockup:** PDF § 7 · bundle `screens/Discover.jsx`
- **Route:** `/discover`
- **Sidebar label:** Jobs (with live unswiped-count badge)
- **Purpose:** Tinder-style swipe queue. ←skip · →auto-apply · ↑save · tap=expand.
- **Layout:** sidebar + main. Main = card-stack center + right rail (~280px).

#### Top
- Title "Discover"
- Subtitle "{N} new matches · sorted by score · swipe through your queue"
- Top-right actions: `Saved · {N}` (bookmark) · **Filters · {N}** (sliders; N = active chip count) · **+ Add by URL** (primary, manual entry)

#### Filter toolbar (plan 36 / `0.2.0.11`)
Sticky chip-row below the header; visible by default. Six chips, each maps 1:1 to a `JobFilter` field. Two are toggles (`remote_only`, `include_duplicates`); four are `<details>` popovers (`source`, `visa`, `seniority`, `score_min`). Each chip's form `hx-get`s `/_fragments/discover/queue?...` with `hx-push-url="true"` so the browser URL mirrors filter state and a refresh restores it. Clear · N affordance appears when any chip is active. The `Filters · N` button in the header toggles the toolbar's `hidden` class via a 2-line inline JS handler. Canonical contract + URL contract + per-axis values: `docs/design/JOB_UI.md` § C + § E.

#### Stats strip
`TODAY · {applied} APPLIED · ⚡ {auto} AUTO · ✏ {manual} MANUAL · 📑 {saved} SAVED · {skipped} SKIPPED` — right "queue refreshes hourly · {scanned} candidates scanned today"

#### Card (center, ~560px wide)

**Top band** (gradient indigo → purple):
- Company logo letter tile
- `COMPANY` (caption)
- "Senior ML Engineer · Atlas" (role + team)
- **Score circle** — green ring with `86` centered. 0–100 scale. **No `%`, no "match" word.** (See `DESIGN.md → score_circle`.)

**Body:**
- Meta row (icons + values, mono): `📍 San Francisco · 💵 $240-290k + 0.05% · 🏠 Hybrid · 📍 SF · 2h ago`
- Tag row: warm-intro chip first when applicable (emerald, "👥 warm intro · {referrer}"), then a conditional `VISA · sponsorship blocked` chip (rose tone) when `match_breakdown.visa_concern = True` (plan 65 / 0.3.0.01 — set by the scorer's deterministic visa filter), then standard tag chips
- Two-column lower body:
  - LEFT: `WHAT THEY WANT` — 3–5 bullets distilled from JD
  - RIGHT: `MATCH · 0.86` overall + per-dimension bars (e.g., `ai-ml 0.95`, `platform 0.88`, `leadership 0.82`, `visa 0.70`)

#### Bottom action bar (4 buttons)
- ✕ **Skip** (rose outline) — keycap `←`
- 📑 **Save** (slate outline) — keycap `↑`
- **Review & apply** (primary, indigo solid) — keycap `tap` / `⏎`
- ⚡ **Auto-apply** (emerald solid) — keycap `→`

Subtitle hint: `← skip · → auto-apply · ↑ save · tap / ⏎ review`

#### Right rail
- **Today** — applied cards (collapsed placeholders showing what's already done today)
- **Up next** (header + count) — 4 queued cards: company tile, role, "$range", match score
- **Stuck in queue · {N}** (only when count > 0) — DRAFT applications whose auto-apply submission hit `captcha` / `auth_required` / `field_mismatch` / `unknown` and now need manual fix-up. Renders `up_next_card.html` with `state="stuck"` (amber border for `auth_required`; rose for the rest). Click → `/discover/{job_id}` shows the DRAFT with a failure banner + retry / discard actions. Added 2026-05-01 per the cross-plan triage so failed auto-applies have a discoverable surface (otherwise they're silently stuck on the DRAFT row).
- **Saved for later · {N} →** card: "You've stashed {N} jobs to revisit. They won't be auto-applied until you decide."
- **Tip** card (lightbulb): "Tap to expand a job and refine the resume / cover letter before applying. Right-swipe lets Naavik tailor and submit on its own."

- **Mobile:** card stack vertical, 4 circular action buttons pinned to bottom (✕ / 📑 / **Review & apply** primary / ⚡), no right rail. Touch swipe (left/right/up) maps to skip/auto-apply/save with directional stamp feedback during drag — see `INTERACTIONS.md § F.4`.
- **Interactions:**
  - Keyboard: `←` skip · `→` auto-apply · `↑` save · `⏎` or `tap` open Review & apply
  - Touch: swipe gestures via pointer events (plan 09a · Issue 3) — left/right/up beyond 80px commits the matching action; below threshold snaps back. Stamp visual reveals at 30px.
  - **Review & apply (plan 09a · Issue 8D · Option D)** → in-place expand the active card into the full review workspace via `GET /_fragments/discover/expanded/:job_id`, swapped into `#discover-main`. The "Back to queue" button inside swaps `#discover-main` back to the swipe grid via `GET /_fragments/discover/queue`. Direct nav to `/discover/:id` still renders the full page (link-shareable URL).
  - Auto-apply → `POST /api/v1/applications/:job_id/auto-submit` (background) → queue advances
  - Skip → `POST /api/v1/discover/:job_id/skip` → next card
  - Save → `POST /api/v1/discover/:job_id/save`
  - Add by URL → modal: paste URL → scrape preview → confirm → enter queue at top
- **States:** Empty queue ("No new matches today. Naavik scans hourly — check back soon."), filtered-zero ("No jobs match these filters." via `empty_state.html` with `icon="search-x"`; plan 36 § A), API offline (rose banner), filter-active dot / `Filters · N` counter on Filters button.
- **Components:** `swipe_card.html`, `score_circle.html`, `match_breakdown.html`, `discover_action_bar.html`, `discover_stats_strip.html`, `up_next_card.html`, `tip_card.html`, `filter_toolbar.html` (plan 36), `_filter_hidden_inputs.html` (plan 36), `filter_chip` macro (plan 36)

---

### 8. Discover · review & apply

- **Mockup:** PDF § 8 · bundle `screens/DiscoverDetail.jsx`
- **Route:** `/discover/:id` (full page — link-shareable) **OR** `/_fragments/discover/expanded/:id` (inline-expand fragment, plan 09a · Issue 8D · Option D)
- **Sidebar label:** Discover (active) — renamed from "Jobs" 2026-05-02 per plan 09a · Issue 5 Option A
- **Purpose:** Full-fidelity application workspace. JD context + tailored resume + cover letter + screener questions, all editable before submission. **Subsumes both prior `/generate/resume` and `/generate/cover-letter` standalone screens — there is no separate `/generate/*` route in the MVP.** All resume tailoring and cover letter drafting happens here.
- **Two-surface delivery (plan 09a · Issue 8D):** the same workspace partial (`pages/_discover_review_workspace.html`) serves both:
  1. The full page at `/discover/:id` (extends `base.html` — sidebar visible, link-shareable).
  2. An inline-expand fragment at `/_fragments/discover/expanded/:id` (no chrome, swapped into `#discover-main` on the Discover page so the active swipe card "expands" in-place without losing queue context). Includes a "← Back to queue" button that swaps `#discover-main` back via `/_fragments/discover/queue`.
  - The default click path from the swipe action bar uses surface (2). Keyboard `↵` and the Review & apply button both go through it. The full page (1) is reachable via the "open as full page →" link inside the inline fragment, browser back, or direct URL.
- **Layout:** Top context bar + 3-column workspace + sticky bottom action bar.

#### Top context bar
- "← Back to queue" link
- Center: company letter tile · "Senior ML Engineer · Atlas / Stripe · San Francisco · $240-290k + 0.05%"
- Right: `match 0.86` (mono cyan) · 🔗 JD · Save · Skip

#### Left column (1/3) — Job context
- `WHAT THEY WANT` bullet list
- `MATCH BREAKDOWN` — 5 dimension bars
- **WARM INTRO AVAILABLE** card (emerald-tinted, only when applicable):
  - "{Referrer name} ({title at company}) is a 1st-degree LinkedIn connection. She's referred {N} hires this year."
  - **Draft intro** CTA → opens Outreach pre-filled
- `JOB DESCRIPTION` collapsible text panel

#### Middle column (1/3) — Tailored resume
- Tab header: **Tailored resume** (active) — `AI · auto-fits 1pg` cyan badge — Regen · Preview PDF on the right
- Status row: "{n} of {N} bullets selected · est. 1 page · all metrics preserved"
- Per-role group:
  - Role header: "{Company} · {Title} · {Date — Date}"
  - Bullets:
    - ☑ Selected — full text + chip row (`# jd`, `# personalization`, `# scale`, or `# edited for jd`, `# you tweaked`)
    - ☐ Excluded — text struck-through and muted, chips like `# duplicate signal`, `# trimmed`, `# older role`
- Click bullet → opens **Bullet editor modal** with the *trimmed-for-this-JD* version pre-filled

#### Right column (1/3) — Cover letter
- Tab header: **Cover letter** — `AI · enthusiastic` cyan badge — Regen on the right
- Sections (each editable inline; click to enter edit mode, indigo ring on active):
  - `INTRO` — short hook
  - `BODY` — main pitch
  - `WHY {COMPANY}` — fit-for-this-company paragraph
  - `CLOSE` — CTA + signoff
- Below the letter:
  - `Screener questions · {N} · need answers` header
  - Per-question card: question text · status chip (`drafted` indigo for AI-drafted requiring review · `auto` slate for auto-filled like start date) · hint "(AI drafted from your profile + JD — review before submit)" when drafted

#### Sticky bottom action bar
- Left: "Ready to apply · resume + cover letter + {N} screeners · est. cost ${cost}" (mono)
- Right: **Download bundle** (ghost) · **Open ATS · {boardname}** (secondary, opens external) · **Submit application** (primary, sparkle)

**Two-step submit (plan 66 / 0.3.1):** the "Submit application" button on the sticky bar
calls `POST /api/v1/applications/{id}/generate-bundle` first (voice-grounded resume +
adaptive cover letter + screener answers + parse-fidelity + ethics pre-flight) THEN
`POST /api/v1/applications/{id}/submit`. The bundle response carries `degraded`,
`parse_fidelity_tier`, `keyword_coverage_score`, and the audit-trail
`generation_trace`. HTMX triggers `bundle-degraded` (amber banner) when cost-cap
fired mid-flight; `parse-fidelity-warning` (info toast) when score lands in the
[0.75, 0.90) tier. Ethics rejection (`> 2` bullets fabricated) returns 422 + a
red-flag list. Full pipeline reference: `docs/design/RESUME_GENERATION.md`.

- **Mobile:** stacks vertically. Sticky `Submit application` at the bottom.
- **Interactions:**
  - Bullet toggle → HTMX swap on counter and selected-bullets list
  - Cover-letter section save → preserves edits, no full re-render
  - Submit → `POST /api/v1/applications` with bundle → optimistic stage `APPLIED` → updates Tracking
  - Download bundle → ZIP with `resume.pdf`, `cover-letter.pdf` (or `.txt`), `screener-answers.json`, `metadata.json`
  - Open ATS → opens external board URL in new tab; user pastes bundle there for boards we can't auto-submit to
- **States:** generating (skeletons + sparkle pulse), edited (`edited` chip on tab), error (rose toast "Couldn't compile resume — see logs in Settings · Deployment")
- **Components:** `apply_topbar.html`, `match_breakdown.html`, `warm_intro_card.html`, `tailored_bullet_row.html`, `cover_letter_section.html`, `screener_question_card.html`, `apply_action_bar.html`

---

### 9. Tracking

- **Mockup:** PDF § 10 (was numbered 10 in the historical 12-section PDF) · bundle `screens/Tracking.jsx`
- **Route:** `/tracking`
- **Sidebar label:** Tracking (with live "needs followup" badge)
- **Purpose:** Application lifecycle from APPLIED → CLOSED. Auto-classified from email signals. Manual entries supported.
- **Layout:** sidebar + main. Main = top status row + integrations + needs-followup banner + Kanban (default) or List view.

#### Top
- Title "Tracking"
- Subtitle: "{active} active · {closed} closed · pulled from gmail every 10 min"
- Right: `gmail · synced 2m ago` · **Board / List** segmented toggle · **+ Add manually**

#### Integrations row (3 cards)
- **Gmail** — connected `shyam@gmail.com` (or "Connect" CTA)
- **Outlook** — "not connected" + **Connect** button
- **Calendar** — "auto-create events"
- Right metadata: "last 90 days · {N} mails parsed · {M} stage updates auto-detected"

#### Needs followup banner (yellow-tinted, when count > 0)
- Header: ⚠️ `NEEDS FOLLOWUP · {N}` · right "open in outreach →"
- Up to 4 cards: sender avatar · "{Name} · {Company}" · "sent {Nd} ago · no reply" / "asked you back {Nd} ago" · per-row `Draft reply` button
- Click → opens that thread in Outreach

#### Board view (default)
- 4 visible columns + collapsed `Closed`:
  - `APPLIED` (indigo dot)
  - `RECRUITER SCREEN` (cyan dot)
  - `ONSITE / LOOP` (amber dot)
  - `OFFER` (emerald dot)
- Each card: company-letter tile, role title, role subtitle, score (mono), `$salary`, status chip (`referral` / `screen Apr 30` / `final round May 8` / `recruiter` / `reply pending`)
- Drag-and-drop between columns to manually update status (Sortable.js)
- Card hover → quick actions menu (View / Add note / Move to)
- Click → application detail (Phase 1.x: slide-over panel; Phase 2: dedicated `/tracking/:id` route)

#### Closed bucket
- Footer link: "📁 {N} closed (rejected · withdrawn · ghosted)" · **Show closed** toggle
- Hidden by default. When shown, appears as a 5th column with rose dot.

#### List view
- Same data, table layout: Company · Role · Stage · Score · Salary · Last activity · Source · Actions
- Sortable columns; bulk actions on selected rows (move stage, archive, export to CSV)

- **Mobile:** stacked stage list (Applied 14, Screen 5, Onsite 3, Offer 1, Closed 6 — each as expandable card row); recent signal cards below.
- **Interactions:**
  - HTMX swap on stage drop
  - SSE stream for new email signals — toast + insert live
  - "Draft reply" → opens Outreach composer pre-filled with thread context
- **States:** empty (no applications), gmail token expired (rose banner + "Reconnect"), outlook not connected (info banner)
- **Components:** `tracking_board.html`, `tracking_card.html`, `integration_card.html`, `followup_banner.html`, `stage_column.html`, `view_toggle.html`

---

### 10. Outreach

- **Mockup:** PDF § 11 (was numbered 11 in the historical 12-section PDF) · bundle `screens/Outreach.jsx`
- **Route:** `/outreach`
- **Sidebar label:** Outreach
- **Purpose:** AI-assisted recruiter / employee follow-ups across LinkedIn + email. Tied to active applications.
- **Layout:** sidebar + main. Main = 2-pane (apps list 1/3 left + selected-app detail 2/3 right).

#### Top
- Title "Outreach"
- Subtitle: "Tied to your {N} active applications · {M} need a nudge today · {K} referrals secured"
- Right: `linkedin · @shyampadia · {N} connections` · `gmail · synced {Nm}`

#### Left pane: applications list
- Search input "Search applications…"
- "All stages" filter pill
- **NEEDS FOLLOWUP · {N}** group (yellow accent) — cards: company tile, role · team, "{contacts} contacts · sent {Nd} ago · no reply", stage chip, state pill (`AWAITING REPLY` / `CALL BOOKED` / `REFERRED` / `NO REPLY · 7D`)
- **ACTIVE · {N}** group — same row layout, less urgent

#### Right pane: selected application detail
- Header: company tile · "{Role} · {Team}" · "applied {N} days ago" · stage chip · "match 0.86" · right "Open in tracking →"
- **RECOMMENDED NEXT MOVE · TODAY** card (amber accent):
  - Title: "Followup with {Contact} · {role}"
  - Meta line: "last touch {Nd} ago · {context} · {tone-recommendation}"
  - **AI DRAFT** body card (cyan-tinted): full message text
  - Actions: **Send via LinkedIn** (primary) · Edit · Regenerate · "Skip · don't suggest again" (ghost)
- **Contacts at {Company} · {N}** card:
  - Right "Find more" button (LinkedIn search)
  - Per-contact row:
    - Avatar
    - Name + degree chip (`1st`, `2nd · via Priya`)
    - School + mutuals count
    - Role + team subtitle
    - Last-activity sentence ("replied 3d ago — referred you" / "sent 7d ago · no reply")
    - State pill (`REFERRED YOU` emerald · `AWAITING REPLY` amber · `NO REPLY · 7D` rose)
    - `…` actions menu

- **Mobile:** stacked. NEEDS FOLLOWUP cards (Send draft / Edit per row), ACTIVE APPLICATIONS list below. Tap card → detail screen.
- **Interactions:**
  - **Send via LinkedIn** → `POST /api/v1/outreach/send` (rate-limited; respects LinkedIn anti-detection)
  - Edit message inline → save before send
  - Regenerate → merge-not-overwrite (same as cover letter)
  - "Find more" → background scrape via LinkedIn API → new contacts appear in list
- **States:** LinkedIn not connected (banner + "Connect LinkedIn"), rate-limit hit (amber toast "Slow down — Naavik will send the next batch in 12m")
- **Components:** `outreach_app_row.html`, `outreach_message_card.html`, `contact_card.html`, `recommended_move_card.html`, `linkedin_status_chip.html`

---

### 11. Settings

- **Mockup:** PDF § 12 (was numbered 12 in the historical 12-section PDF) · bundle `screens/Settings.jsx`
- **Route:** `/settings` (with sub-routes `/settings/{tab}` for deep-linking)
- **Sidebar label:** Settings
- **Purpose:** All configuration in one place. 7 tabs.
- **Layout:** sidebar + main. Main has 7 tabs across the top: **Account · LLM Provider · Notifications · Auto-Apply · Sources · Submissions · Deployment** (Submissions added by plan 54 / `0.2.5.03`).

#### Tab: LLM Provider
- Title "Settings" + subtitle "Configure how Naavik runs."
- "Active provider" card · `{N} selected` right
  - 3 provider cards in a row:
    - **Anthropic Claude** — selected (indigo border + radio dot) — "Recommended · best resume bullet quality" · `CLOUD` chip
    - **OpenAI GPT** — "GPT-4o · faster, slightly cheaper" · `CLOUD` chip
    - **Ollama (Local)** — "Llama 3.1 70B on your machine · private" · `LOCAL` chip
- "API configuration" card:
  - `API KEY` input with show/hide eye + **Test connection** button
  - On success: cyan inline "Connection ok · responded in 412ms · model claude-3.5-sonnet-20250219"
  - On failure: rose inline "Couldn't reach Anthropic API: 401 Unauthorized — check key"
  - `MODEL` dropdown (provider-scoped)
  - 3 cost cards in a row:
    - `THIS MONTH` — `$3.42` — "≈412k tokens"
    - `AVG / GENERATION` — `$0.04` — "resume + cover letter"
    - `RATE LIMIT` — `50 / min` — "tier 2"
  - Footer hint (lock icon): "Your API key is stored encrypted at `~/.naavik/secrets.enc`. Naavik never sends your key to any third party."

#### Tab: Deployment (self-hosted variant)
- Status card: "Self-hosted" emerald badge — "active · v0.4.2 · docker-compose · uptime 14d 6h · last restart Apr 14"
- Right actions: **Restart** (refresh icon) · **Update v0.4.3** (download icon, only when update available)
- **Live log tail** card:
  - Header: macOS-style traffic-light dots · `~/.naavik/logs · live tail` · right `STREAMING` (cyan dot, pulsing) · Pause · Copy
  - Mono terminal display, scrollback. Lines look like:
    ```
    14:02:41 INFO  discover.fetch  · pulled 24 jobs from greenhouse · 312ms
    14:02:41 INFO  discover.match  · scored 24 jobs · avg fit 71%
    14:03:02 INFO  apply.submit    · zed industries / sr fullstack · ok · 4.2s
    14:03:18 INFO  resume.tailor   · llm=claude-3.5-sonnet · 412ms · 1184 tok
    14:03:18 INFO  cover.draft     · llm=claude-3.5-sonnet · 689ms · 2104 tok
    14:04:55 WARN  tracking.imap   · gmail oauth token refreshing · 1 retry
    14:05:14 ERROR apply.submit    · vercel / sr designer · captcha required → moved to review queue
    14:05:30 INFO  outreach.send   · 3 linkedin DMs queued · sending in 4m
    14:05:48 INFO  db.snapshot     · ~/.naavik/data/snapshots/2026-04-29.sql.gz
    ```
- **On disk** card group (4 cards):
  - `DATA DIR` — `~/.naavik/data` — "{size} · {N} jobs · {M} applications"
  - `SECRETS` — `~/.naavik/secrets.enc` — "aes-256-gcm · {N} keys"
  - `CONFIG` — `~/.naavik/config.toml` — "last edited {Nd} ago"
  - `SNAPSHOTS` — `~/.naavik/snapshots/` — "{N} daily · auto-prune at 30"

#### Tab: Deployment (cloud variant)
- Status card: "Cloud" indigo badge — "active · region {region} · plan $15/mo · billing {date}"
- "Logs available in cloud dashboard" external link
- "Bring your own API key" reminder (info)
- The terminal log tail is **self-hosted only** — replaced with the cloud-dashboard link.

#### Tab: Generation (plan 67 / 0.3.4)

- **Route:** `/settings/generation`
- **Template:** `pages/_settings_generation.html` + `components/_audit_trail_viewer.html`
- **Purpose:** opt into the PREMIUM-tier Claude-mythos bundle generation pipeline + view per-bundle audit trail.

Four sections (top to bottom):

1. **Generation tier toggle** — two radio cards (FREE vs PREMIUM) showing per-app cost range. Selected card carries the indigo border. PUT `/api/v1/settings/generation` persists; HTMX swap re-renders the partial with `save_status="saved"` chip.
2. **PREMIUM per-app cost projection** — 5-column grid (Detector / Council / Critique / Tool loop / Originality) + total row in indigo. Sourced from `services.settings_service.compute_premium_cost_projection`. When `>= 10` PREMIUM bundles exist, shows history-based mean; otherwise falls back to the ROADMAP estimate ($0.61 total). Hint line under the projection clarifies which mode is active.
3. **TIER-2 evasion opt-in** — single checkbox bound to `Settings.tier_2_evasion_enabled`. Off by default; amber-text warning notes ATS detection risk.
4. **Originality.ai API key** — password input (does NOT round-trip the existing value; placeholder shows "configured" when set). Empty submit = clear. Per-user opt-in for the real-detector spot-check at convergence.

Below the form:

5. **Generation audit-trail viewer** — last 20 Applications with non-null `generation_trace`, rendered as expandable `<details>` cards. Card header shows tier chip (FREE = slate, PREMIUM = indigo) + company / role + total cost + degraded chip (when `degraded_mode=True`). Card body shows stages run/skipped count, parse-fidelity score, keyword-coverage score, ethics pre-flight verdict. PREMIUM bundles additionally render: council Borda rankings, detector iterations + Originality score, critique persona votes + consensus concerns, tool-loop tool calls per iteration. Renders entirely from `Application.generation_trace` JSONB; no extra DB queries beyond the indexed lookup.

**Per-app override surface:** the Discover · review action bar surfaces a "Try PREMIUM for this job" button when `Job.score >= 0.85`. The button POSTs to the bundle endpoint with `tier=premium` kwarg overriding the user's default. (Discover surface wire-up lands as a follow-up; the bundle endpoint already accepts the kwarg.)

**Components:** existing `settings_tabs.html` extended with `"generation"` tab id. New partials: `pages/_settings_generation.html`, `components/_audit_trail_viewer.html`. Reuses Tailwind/DaisyUI cards + existing accent palette (indigo PREMIUM, amber warnings, emerald success).

#### Other tabs (specs deferred — design pending or implied)
- **Account** — name, email, password change, sign out, "Delete my account" (destructive)
- **Notifications** — Discord webhook URL, Telegram bot token, "Send test", per-event toggles (new high-score job, application sent, interview scheduled, offer received, rejection)
- **Auto-Apply** — master toggle (default OFF), score threshold slider (default 0.85), per-source toggle, daily total cap optional (default unlimited)
- **Sources** — operator-facing surface for per-scraper configured-state + last-run state. Six rows (LinkedIn / Workday / Greenhouse / Lever / Ashby / Indeed); each row renders enable toggle + env-vs-DB configured indicator + last-`JobScrapeRun` status chip + relative timestamp + schedule cron + resolved rate-limit + `<details>` configure popover. **Full contract:** `docs/design/SOURCES_UI.md`. Writable editors for rate-limit JSONB + LinkedIn/Indeed keywords + Workday companies deferred to `0.2.7.06`.
- **Submissions** — recent application submissions feed (auto-apply + manual). Shipped via plan 54 / `0.2.5.03`.

- **Components:** `settings_tabs.html`, `provider_card.html`, `cost_card.html`, `log_tail.html`, `on_disk_card.html`, `deployment_status_card.html`, `_settings_generation.html` (plan 67), `_audit_trail_viewer.html` (plan 67)

---

### 12. Job detail

- **Mockup:** none committed; Playwright capture in `traces/2026-05-19T15-42-42_833f4a/qa/0.2.0.11/` at 1440×900 + 375×812.
- **Route:** `/jobs/{job_id}` (full page) **OR** `/_fragments/jobs/{job_id}` (chrome-less body fragment for future drawer/preview surfaces).
- **Sidebar label:** Discover (active) — `/jobs/{id}` is a destination from Discover, not a sibling nav entry. No `/jobs` list route exists; Discover IS the job list (Tinder-style swipe = filtered list with one big card at a time).
- **Phase:** 2 (`0.2.0.11`, shipped 2026-05-19 via PR #112).
- **Purpose:** Read-only view of a single persisted Job in isolation — distinct from `/discover/{id}` (the tailor + apply application workspace, SCREENS.md § 8). Surfaces source / scrape-run metadata, dedup status, action rail. Reachable from any future Tracking deep-link to a source Job, and (today) via direct URL or browser back from `/discover/{id}`.
- **Layout:** sticky topbar (full-width) + two-column body (`1fr 320px` on lg+; single column on mobile).

#### Topbar (full-width, sticky)
- Left: ← `Back to Discover` link
- Center: company letter tile (`avatar.html`) + role · team · company · location · salary chip
- Right: source-tone chip (e.g. indigo for LinkedIn, cyan for Workday) + match score (mono cyan, tabular-nums) OR `unscored` slate chip when `Job.score == 0.0` + Open posting external link (`hx-boost="false"`)

#### Body left + middle (composite, `1fr` of the grid)
- **Duplicate-of banner** (only when `Job.duplicate_of_id` is non-null): amber inline alert linking to the canonical Job — "This listing is a tier-3 fuzzy duplicate of `job #{N}`. The canonical row is what surfaces in Discover by default."
- **Job description card** — `bg-slate-900` rounded-xl panel. Header right-aligned chip: "extracted Nh ago · `model_name`" when `Job.description_extracted_at` is set. Body: `prose prose-invert` rendered description.
- **What they want / Skills required two-up** (md+): "What they want" bulleted list (from `Job.criteria`) + "Skills required" tag-chip grid (from `Job.skills_required` via `tag_chip` macro).
- **Scrape metadata card** — `<dl>` grid with: source · board · external_id · found_at · posted_at (+ original `posted_at_text` if present) · remote_policy · seniority_level (if set) · visa_restrictions. Below that, when `last_scrape_run_id` resolves: `chip` showing run status (emerald SUCCESS / amber PARTIAL / rose FAILED|TIMED_OUT / indigo RUNNING) + started/finished times + duration_ms + counters (requests · listings · new · updated) + per-error list.

#### Body right rail (`320px` of the grid)
- **Actions card:**
  - **Review & apply** (primary indigo) → `<a href="/discover/{j.id}">` (full page nav to application workspace)
  - **Open on `{SOURCE}`** (slate, external) → `<a href="{j.url}" target="_blank" rel="noopener" hx-boost="false">`
  - **Save for later** (slate) → `hx-post="/api/v1/discover/{j.id}/save"` (pre-existing endpoint; CSRF hardening tracked at `0.2.0.11b`)
  - **Skip** (slate) → `hx-post="/api/v1/discover/{j.id}/skip"` (same)
- **Tags card** (only when `Job.tags` non-empty): tag-chip flex-wrap row via `tag_chip` macro.
- **Status card:** `<dl>` with queue_state (e.g. `UNSWIPED`, `SAVED`, `SKIPPED`) + score (numeric `0.0–1.0` or `—` for unscored). `score_explanation` body paragraph below if non-null.

- **Mobile:** stacks. Topbar wraps; right rail folds below the description card.
- **Interactions:**
  - IDOR boundary: cross-user requests return 404 (not 403); soft-deleted Jobs return 404 — see `docs/design/JOB_UI.md` § F.4 for rationale.
  - Action rail Save / Skip wire to existing `/api/v1/discover/{id}/save` / `/skip` endpoints (`hx-target="closest [data-job-section]"` + `hx-swap="none"` is fire-and-forget today; future polish row adds toast on success).
  - `/_fragments/jobs/{job_id}` returns the same body content as the page without the base layout — forward-compat for plan `0.2.0.12+` that may want to deep-link a Job preview into a Tracking drawer.
- **States:**
  - Default — populated detail page (all sections render conditionally on field presence).
  - 404 — Job ID doesn't exist, belongs to a different user, or is soft-deleted (collapsed signals per IDOR pattern).
  - 401 — fake-session caller without seeded user surrogate; cookie required for non-test paths.
  - Duplicate — amber banner above body; canonical-row link uses `<a href="/jobs/{duplicate_of_id}">`.
  - Unscored — topbar shows `unscored` slate chip; status card shows `—` for score.
- **Components:** `job_topbar.html` (NEW), `avatar.html`, `chip` macro, `tag_chip` macro, `empty_state.html` (if applicable), Lucide icons (`arrow-left`, `external-link`, `sparkles`, `bookmark`, `x`, `copy`).
- **Canonical contract:** `docs/design/JOB_UI.md` (full spec — URL contract, HTMX patterns, data accessors, IDOR boundary).

---

## Phase mapping (vs ROADMAP.md)

The mockups make Tracking and Outreach MVP-essential. ROADMAP.md still puts them in later phases — this needs reconciling in Block C of the design-realignment plan.

**Phase 1 (MVP)** — Login · Onboarding · Overview · Profile · Profile editor · Bullet editor modal · Discover · Discover · review & apply · Tracking · Outreach · Settings (**11 sections**; all mockups committed in the historical 12-section PDF, but the standalone Cover-letter screen has been folded into Discover · review & apply).

**Phase 2 (Job Scraping & Discovery)** — Job detail (screen #12 at `/jobs/{id}`); shipped 2026-05-19 via plan 36 (`0.2.0.11`). Canonical contract: `docs/design/JOB_UI.md`.

**Deferred / Phase 2+** (no mockups yet)
- Application detail slide-over (deeper view of submitted bundle, accessed from Tracking)
- Manual job entry modal (`+ Add by URL` is the partial Phase 1 path; the full modal comes later)
- Score-card / match-explanation as a standalone (currently embedded in Discover · review & apply)
- Cover letter / resume generation as standalone tools (no plan to bring back; both happen inside Discover · review & apply)
- Light mode (Phase 6)
- OIDC for self-hosted (Authentik / Keycloak / Okta)

---

## Update process

1. **New screen:** append to Screen Index + write a full section.
2. **Designed:** Mockup status `[ ] → [~] → [x]`. Commit PNG/PDF to `docs/design/mockups/`.
3. **Implemented:** Impl status `[ ] → [~] → [x]`.
4. **Scope change:** edit the screen section directly. Bump "Last updated" at the top.
5. **Reconcile vs ROADMAP.md:** when phase mapping shifts (e.g., Tracking moving from Phase 4 to Phase 1), update ROADMAP.md in the same commit.
