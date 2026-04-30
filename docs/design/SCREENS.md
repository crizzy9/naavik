# Naavik Screen Catalog

> **Last updated:** 2026-04-30
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
| 3 | Jobs | `briefcase` | `/discover` | live count of unswiped matches (e.g. `47`) |
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
| 1 | Login | `/login` | (auth shell, no sidebar) | 1 | [x] | [ ] |
| 2 | Onboarding · resume upload | `/onboarding` | (no sidebar) | 1 | [x] | [ ] |
| 3 | Overview | `/` | Overview | 1 | [x] | [~] (placeholder) |
| 4 | Profile | `/profile` | Profile | 1 | [x] | [ ] |
| 5 | Profile editor | `/profile/edit` | Profile | 1 | [x] | [ ] |
| 6 | Bullet editor modal | (component, opens from #5 + #8) | — | 1 | [x] | [ ] |
| 7 | Discover | `/discover` | Jobs | 1 | [x] | [ ] |
| 8 | Discover · review & apply | `/discover/:id` | Jobs | 1 | [x] | [ ] |
| 9 | Tracking | `/tracking` | Tracking | 1 | [x] | [ ] |
| 10 | Outreach | `/outreach` | Outreach | 1 | [x] | [ ] |
| 11 | Settings | `/settings` (+ tab sub-routes) | Settings | 1 | [x] | [ ] |

The MVP set is **11 screens**. The historical mockup PDF (committed at `docs/design/mockups/Naavik — MVP screens (print).pdf`) was generated when there were 12 sections; the prior standalone Cover-letter screen has been folded into Section 8 (Discover · review & apply). Once the next Claude Design handoff produces standalone exports, individual PNGs commit alongside the PDF using the naming `{nn}-{slug}-{desktop|mobile}.png`.

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
- Top-right actions: `Saved · {N}` (bookmark) · **Filters** (sliders) · **+ Add by URL** (primary, manual entry)

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
- Tag row: warm-intro chip first when applicable (emerald, "👥 warm intro · {referrer}"), then standard tag chips
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
- **Saved for later · {N} →** card: "You've stashed {N} jobs to revisit. They won't be auto-applied until you decide."
- **Tip** card (lightbulb): "Tap to expand a job and refine the resume / cover letter before applying. Right-swipe lets Naavik tailor and submit on its own."

- **Mobile:** card stack vertical, 4 circular action buttons pinned to bottom (✕ / 📑 / **Review & apply** primary / ⚡), no right rail.
- **Interactions:**
  - Keyboard: `←` skip · `→` auto-apply · `↑` save · `⏎` or `tap` open Review & apply
  - Touch: swipe gestures
  - Auto-apply → `POST /api/v1/applications/:job_id/auto-submit` (background) → queue advances
  - Skip → `POST /api/v1/discover/:job_id/skip` → next card
  - Save → `POST /api/v1/discover/:job_id/save`
  - Add by URL → modal: paste URL → scrape preview → confirm → enter queue at top
- **States:** Empty queue ("No new matches today. Naavik scans hourly — check back soon."), API offline (rose banner), filter-active dot on Filters button.
- **Components:** `swipe_card.html`, `score_circle.html`, `match_breakdown.html`, `discover_action_bar.html`, `discover_stats_strip.html`, `up_next_card.html`, `tip_card.html`

---

### 8. Discover · review & apply

- **Mockup:** PDF § 8 · bundle `screens/DiscoverDetail.jsx`
- **Route:** `/discover/:id`
- **Sidebar label:** Jobs (active)
- **Purpose:** Full-fidelity application workspace. JD context + tailored resume + cover letter + screener questions, all editable before submission. **Subsumes both prior `/generate/resume` and `/generate/cover-letter` standalone screens — there is no separate `/generate/*` route in the MVP.** All resume tailoring and cover letter drafting happens here.
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
- **Purpose:** All configuration in one place. 6 tabs.
- **Layout:** sidebar + main. Main has 6 tabs across the top: **Account · LLM Provider · Notifications · Auto-Apply · Sources · Deployment**.

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

#### Other tabs (specs deferred — design pending or implied)
- **Account** — name, email, password change, sign out, "Delete my account" (destructive)
- **Notifications** — Discord webhook URL, Telegram bot token, "Send test", per-event toggles (new high-score job, application sent, interview scheduled, offer received, rejection)
- **Auto-Apply** — master toggle (default OFF), score threshold slider (default 0.85), per-source toggle, daily total cap optional (default unlimited)
- **Sources** — scraping source list with enable/disable/schedule (LinkedIn / Workday / Greenhouse / Lever / Ashby / Indeed / RSS)

- **Components:** `settings_tabs.html`, `provider_card.html`, `cost_card.html`, `log_tail.html`, `on_disk_card.html`, `deployment_status_card.html`

---

## Phase mapping (vs ROADMAP.md)

The mockups make Tracking and Outreach MVP-essential. ROADMAP.md still puts them in later phases — this needs reconciling in Block C of the design-realignment plan.

**Phase 1 (MVP)** — Login · Onboarding · Overview · Profile · Profile editor · Bullet editor modal · Discover · Discover · review & apply · Tracking · Outreach · Settings (**11 sections**; all mockups committed in the historical 12-section PDF, but the standalone Cover-letter screen has been folded into Discover · review & apply).

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
