---
Status: ARCHIVED
Type: prompt
Authored: 2026-04-30 (rewrite of 2026-04-25 original)
Last updated: 2026-04-30
Used: 2026-04 (drove the Claude Design Prototype iteration that produced the canonical 11-screen MVP mockups)
Archived: 2026-04-30
---

# Claude Design Prompt — Naavik Screens (Phase 1 MVP) (ARCHIVED)

> **Status:** Archived. This prompt drove the Claude Design Prototype project iteration that produced the canonical 11-screen MVP mockups (committed in `docs/design/mockups/`). Kept for reference if a future batch of new screens is added (Phase 2+). To produce new screens, copy this file out of the archive, update the screen list, the version, and the hard-rules section.
>
> **Original last-updated:** 2026-04-30
> **Prerequisite (when active):** The Naavik design system MUST already be set up and published in Claude Design (via "Set up design system", source material `DESIGN.md`). This prompt generates **screens only** — colors, typography, components, voice, and tokens are inherited from the published design system.
>
> **How to use:**
>
> 1. Go to claude.ai/design
> 2. Confirm the Naavik design system is **Published** (org settings → Design System)
> 3. Click **"Create"** → **"Prototype"** → **"High fidelity"**
> 4. Name it "Naavik Phase 1" (or batch name if newer)
> 5. Paste this prompt
> 6. Iterate visually; export when satisfied
>
> **Note:** Screens described here represent the canonical 11-screen MVP. There are no `/generate/*` routes — resume tailoring and cover letter drafting live inside Discover · review & apply.

---

## Product context

Design screens for **Naavik** (Hindi: नाविक, "Navigator"), an open-source self-hosted-first career automation platform.

**Audience:** Tech-savvy professionals (engineers, PMs, designers) who self-host developer tools.

**Vibe:** Linear / Cursor / Plausible — dark mode primary, data-dense, no SaaS bloat. A managed cloud tier ($15/mo, bring-your-own AI credits) exists but is never treated as premium.

**Core flow:** Resume PDF upload → AI extracts profile → job scraping → AI scoring → swipe-style review → tailored resume + cover letter generated inside the apply flow → submit → track via auto-classified email signals → outreach to recruiters/employees for referrals.

**Sample data:** Owner is **Shyam Padia**, Senior Software Engineer at Intuit, San Francisco, H1B requires sponsorship. Companies to use: Stripe, Anthropic, Plaid, Linear, Notion, Figma, Ramp, Discord, Snowflake, Airbnb, Databricks. Roles: Senior ML Engineer, Senior Backend, Staff Engineer, Engineering Manager, Founding Engineer.

---

## Hard rules (do not break)

- **Status pipeline is exactly 5 stages**: `APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED`. Do not introduce intermediate states (no FOUND / SCORED / APPROVED / DOCS_GENERATED / INTERVIEWING / REJECTED / WITHDRAWN as separate stages — those are orthogonal sub-states or close reasons).
- **Tag vocabulary is exactly 9 tags**: `ai-ml · backend · frontend · devops · data-eng · genai · leadership · platform · product`. No others.
- **Score circle**: 0–100 number centered in a colored ring. **No `%` mark, no "match" word.**
- **Tag chips never carry an AI sparkle.** The cyan sparkle is reserved for AI-generated *content* (cover letter paragraphs, drafted screener answers, recommended next moves), not metadata.
- **Bullets are single long-form text** — no oneline/detailed split, no `default_include` toggle, no metric (revenue / percentage / team_size) sub-fields. AI trims to one resume line at apply time.
- **Single dark mode.** No theme switcher. No light variants.
- **Sidebar IA**: Overview · Profile · Jobs (`/discover`) · Tracking · Outreach · Settings. No Resume, Cover Letter, Analytics, or Inbox sidebar items.

---

## Screen batch: Phase 1 MVP (11 screens)

For each screen produce a **desktop mockup (1440×900)** and **mobile mockup (375×812)**. Show realistic data per the Sample data section above. Show realistic state where the screen has multiple states (loading / empty / error).

---

### Screen 1 · Login (`/login`)

Auth shell. No sidebar.

- Faint compass-pattern motif on `bg-base`
- Top-left: brand lockup + version pill `v0.4.2 · self-hosted` (mono)
- Top-right: green `API ONLINE` dot pill
- Center card (~440px wide): Naavik compass logo + wordmark, "Welcome back", "Sign in to your Naavik instance.", `EMAIL` input, `PASSWORD` input (eye toggle), "Keep me signed in on this device" checkbox (default checked), full-width **Sign in** primary button
- Indigo-tinted info card with key icon: "**SSO coming soon.** Self-hosted instances will support OIDC providers like Authentik, Keycloak, and Okta."
- Footer row: "Create account · Docs · Source"

States: default · loading (spinner + "Signing in…") · error (rose-tinted alert above the button).

---

### Screen 2 · Onboarding · resume upload (`/onboarding`)

3-step wizard, no sidebar, full-width centered. Routes to Overview (`/`) on completion.

- Top: Naavik logo + `setup` badge. Step indicator: **1 Upload — 2 Extracting — 3 Review** (active = indigo-filled, completed = emerald check).
- **Step 1**: title "Upload your resume", subtitle about local parsing, dashed dropzone (`h-96`) with cloud-upload icon → "Drop your resume here" → **Browse files**, "PDF only · max 10 MB", lock-icon footer hint "Parsed locally · never sent to third parties", "Skip — enter manually" ghost link.
- **Step 2 (the hero)**: cyan sparkle card with faint glow "Reading your resume…" + filename + "est. Ns remaining". Checklist (✓ Reading PDF · ⊙ Identifying experience 2 of 4 · ⊙ Extracting skills · ○ Categorizing bullets queued · ○ Generating summary queued). Gradient progress bar (indigo → cyan). Below: "Extracted so far · AI · 4 of 6 fields" card with confidence-scored rows (mono numbers, emerald): NAME 0.99, TITLE 0.96, LOCATION 0.92, EXPERIENCE 0.88, SKILLS in-progress, EDUCATION skeleton.
- **Step 3**: sectioned preview (Experience / Education / Skills / Projects / Certifications) with "Looks good" / "Edit". Application Readiness gate banner pointing to `/profile/edit#application-qs`. Footer: **Save to profile** primary CTA.

---

### Screen 3 · Overview (`/`)

Sidebar (Overview active) + main. Main is a vertical stack:

1. **Greeting strip**: time-aware "Good morning, Shyam." + sub-line "{N} priority actions queued for today · {M} offer awaiting reply"; right pill `Tue · Apr 29 · 09:14 PT` (mono).
2. **KPI strip (4 cards)**: `ACTIVE APPLICATIONS` 29 / `RESPONSE RATE · 90D` 11.3% +2.1% (3× market avg) / `ONSITE RATE` 4.2% −0.4% / `OFFER RATE` 1.4% +0.7% (2 offers · 1 pending). Funnel KPIs, not raw counts.
3. **Two-column body**: LEFT 2/3 = Priority Actions (numbered list `01..04`, event icon, title, urgency badge `TODAY` rose / `TOMORROW` amber / `14M AGO` slate / `6D SILENT` rose, action CTA, footer "See all 14 in tracking →"). RIGHT 1/3 = Recent email signal (6 rows: company-letter avatar, subject preview, sender, status pill, mono cyan match score, relative time, footer "See all 18 in tracking →").
4. **Pipeline · live** (full width): 5-column mini-Kanban — APPLIED · RECRUITER · ONSITE · OFFER · CLOSED with status dots and counts.

Empty state: hide KPIs, single card "Welcome. Upload your resume to get started." → `/onboarding`.

---

### Screen 4 · Profile (`/profile`)

Sidebar (Profile active) + main + sticky right-rail "ON THIS PAGE" nav (~240px).

- **Hero card**: avatar tile (purple→indigo gradient, initials SP), name "Shyam Padia" (display), title · company subtitle "Senior Software Engineer · Intuit", location pin · "Open to opportunities", contact chips (mail / phone / `/github` / `/in/handle` / portfolio domain), top-right **Edit profile** + **Update resume**.
- **Body sections (anchored)**: Summary (short + full toggle), Experience (`{N} of {M} roles`; per-role card: company-letter tile, title, "Company · Location", "Date — Date · {dur}", bullet list with text + tag chips inline; expand reveals all bullets for the role — bullets are single long-form, AI selects which land on tailored resume), Application details (read-only EEO/visa values), Skills (grouped tag chips), Education (card list), Projects (3-col grid desktop, 1 mobile), Certifications.
- **Right rail**: "ON THIS PAGE" caption + anchor links (Summary · Experience active · Application details · Skills · Education · Projects). Below: **APPLICATION READINESS** card showing missing fields (amber count, ✓ filled / ○ empty rows).
- **Mobile**: stacks. Hero, then tabs (Summary / Experience / Application details / Skills) above content. Visa badge "H1B · Requires sponsorship" rendered prominently in hero.

---

### Screen 5 · Profile editor (`/profile/edit`)

Same shell as Profile. Top breadcrumb "Profile > Edit". Top right: `Auto-saved 12s ago` chip · "Preview" · "Discard".

- **Identity card**: 4-col grid (FULL NAME / HEADLINE / CURRENT COMPANY / LOCATION).
- **Experience card** (one per role): header "Experience · {Company}" + Duplicate role + Remove. 3-col inputs (TITLE / START / END with `Present` sentinel). `BULLETS · {N}` list — each row: drag-handle (`grip-vertical`), bullet text (truncated preview, single long-form), tag chips, edit-pencil + trash icons on hover. If a bullet has `selection_override`, a small `pinned · always` (emerald) or `pinned · never` (slate) chip appears. "+ Add bullet" ghost button. Edit-pencil opens **Bullet editor modal** (Section 6).
- **Application questions section** (anchor `#application-qs`): title "US application questions" · `United States` region pill. Note: "Most US-based job applications ask these. We answer them once and apply automatically. We never share these outside Naavik." Field grid with inline edit: Work authorization · Visa sponsorship needed · Veteran status · Disability status · Race / ethnicity (EEO) · Gender · Willing to relocate · Notice period · Salary expectation · Earliest start.

States: Saving (spinner + "Saving…"), Saved (emerald check + "Auto-saved Ns ago"), Error (rose alert + "Couldn't save — retry").

---

### Screen 6 · Bullet editor modal (component, no route)

Opens from Profile editor and Discover · review & apply. ~720px wide on desktop; bottom sheet on mobile.

- **Header**: "Edit bullet" + role context "· {Company} · {Title}" + close ×.
- **Body**:
  - `BULLET` label, top-right hint "write the long version — Naavik trims to fit". Single autosize textarea (multi-line, no length cap).
  - Sparkle-icon explainer card (cyan-tinted): "At apply time Naavik picks the bullets that fit the JD and rewrites each one to land on a single line — keeping your numbers and verbs intact. You don't need to maintain two versions."
  - `TAGS · {N} SELECTED` label. Tag picker — the 9-tag vocabulary as chips. Selected = indigo bg, unselected = slate bg. **No sparkle on chips.**
  - **SELECTION OVERRIDE** section: two mutually-exclusive option cards (radio behavior) — "Always include this bullet" / "Never include this bullet" with explanations and right-side `auto` chip. Default: neither (= AI auto-decides).
- **Footer**: Left = **Rewrite with AI** (sparkle, ghost) · **Delete** (trash, ghost). Right = "Cancel" · **Save bullet** (primary).

**Do not include**: oneline/detailed split, character counter, live Typst preview, metric inputs (revenue / percentage / team size), `default_include` toggle. All removed.

---

### Screen 7 · Discover (`/discover`)

Tinder-style swipe queue. Sidebar (Jobs active) + main. Main = card-stack center + right rail (~280px).

- **Top**: title "Discover", subtitle "{N} new matches · sorted by score · swipe through your queue". Top-right: `Saved · {N}` (bookmark) · **Filters** · **+ Add by URL** (primary).
- **Stats strip**: `TODAY · {applied} APPLIED · ⚡ {auto} AUTO · ✏ {manual} MANUAL · 📑 {saved} SAVED · {skipped} SKIPPED` — right "queue refreshes hourly · {scanned} candidates scanned today".
- **Card (center, ~560px wide)**:
  - **Top band** (gradient indigo→purple): company logo letter tile, `COMPANY` caption, role + team, **Score circle** — green ring with `86` centered (0–100, no `%`, no "match" word).
  - **Body**: meta row (`📍 location · 💵 salary · 🏠 remote · 2h ago`); tag row (warm-intro chip first when applicable + standard tag chips, no sparkle); two-column lower body: LEFT `WHAT THEY WANT` (3–5 distilled JD bullets), RIGHT `MATCH · 0.86` overall + per-dimension bars (e.g. `ai-ml 0.95`, `platform 0.88`, `leadership 0.82`, `visa 0.70`).
- **Bottom action bar (4 buttons)**: ✕ **Skip** (rose, keycap `←`) · 📑 **Save** (slate, keycap `↑`) · **Review & apply** (primary indigo, keycap `tap`/`⏎`) · ⚡ **Auto-apply** (emerald, keycap `→`).
- **Right rail**: "Today" applied cards (collapsed); "Up next" 4 queued cards (company tile, role, salary, mono match score); "Saved for later · {N} →" card; "Tip" lightbulb card explaining tap-to-expand vs right-swipe-auto-apply.
- **Mobile**: card stack vertical, 4 circular action buttons pinned to bottom (✕ / 📑 / **Review & apply** primary / ⚡), no right rail.

---

### Screen 8 · Discover · review & apply (`/discover/:id`)

The most complex screen. **Subsumes the prior `/generate/resume` and `/generate/cover-letter` standalone routes.** Sidebar (Jobs active) + 3-column workspace + sticky bottom action bar.

- **Top context bar**: "← Back to queue", center company letter tile · "Senior ML Engineer · Atlas / Stripe · San Francisco · $240-290k + 0.05%", right `match 0.86` (mono cyan) · 🔗 JD · Save · Skip.
- **Left column (1/3) — Job context**: `WHAT THEY WANT` bullet list; `MATCH BREAKDOWN` 5 dimension bars; **WARM INTRO AVAILABLE** card (emerald-tinted, only when applicable) with referrer name, role, mutual context, and **Draft intro** CTA → opens Outreach pre-filled; `JOB DESCRIPTION` collapsible text panel.
- **Middle column (1/3) — Tailored resume**: tab header **Tailored resume** + cyan badge `AI · auto-fits 1pg` + Regen + Preview PDF. Status row "{n} of {N} bullets selected · est. 1 page · all metrics preserved". Per-role group: role header, then bullets — selected (full text + chips like `# jd`, `# personalization`, `# scale`, or `# edited for jd`) and excluded (struck-through, muted, chips like `# duplicate signal`, `# trimmed`, `# older role`). Click bullet → opens Bullet editor modal with the JD-trimmed version pre-filled.
- **Right column (1/3) — Cover letter + screeners**: tab header **Cover letter** + cyan `AI · enthusiastic` badge + Regen. Sections (each editable inline, click to enter edit mode with indigo ring): `INTRO` · `BODY` · `WHY {COMPANY}` · `CLOSE`. Below: `Screener questions · {N} · need answers` — per-question cards with status chip (`drafted` indigo for AI-drafted requiring review · `auto` slate for auto-filled like start date) and hint "(AI drafted from your profile + JD — review before submit)" when drafted.
- **Sticky bottom action bar**: left "Ready to apply · resume + cover letter + {N} screeners · est. cost $0.04" (mono); right **Download bundle** (ghost) · **Open ATS · {boardname}** (secondary, opens external) · **Submit application** (primary, sparkle).
- **Mobile**: stacks vertically. Sticky `Submit application` at bottom.

---

### Screen 9 · Tracking (`/tracking`)

Sidebar (Tracking active) + main. Main = top status row + integrations + needs-followup banner + Kanban (default) or List view.

- **Top**: title "Tracking", subtitle "{active} active · {closed} closed · pulled from gmail every 10 min". Right: `gmail · synced 2m ago` · **Board / List** segmented toggle · **+ Add manually**.
- **Integrations row**: Gmail (connected), Outlook (not connected + Connect), Calendar (auto-create events). Right metadata: "last 90 days · {N} mails parsed · {M} stage updates auto-detected".
- **Needs followup banner** (yellow-tinted, when count > 0): ⚠️ `NEEDS FOLLOWUP · {N}` · right "open in outreach →". Up to 4 cards: sender avatar · "{Name} · {Company}" · "sent {Nd} ago · no reply" / "asked you back {Nd} ago" · per-row `Draft reply` button.
- **Board view (default)**: 4 visible columns + collapsed `Closed`. Columns: APPLIED (indigo dot) · RECRUITER SCREEN (cyan dot) · ONSITE / LOOP (amber dot) · OFFER (emerald dot, glow on cards). Each card: company-letter tile, role title, role subtitle, score (mono), `$salary`, status chip (`referral` / `screen Apr 30` / `final round May 8` / `recruiter` / `reply pending`). Drag-and-drop between columns. **Closed bucket** footer link "📁 {N} closed (rejected · withdrawn · ghosted)" + **Show closed** toggle (hidden by default).
- **List view**: same data as table — Company · Role · Stage · Score · Salary · Source · Last activity · Actions. Sortable columns; bulk actions on selected rows.
- **Mobile**: stacked stage list (each as expandable card row); recent signal cards below.

---

### Screen 10 · Outreach (`/outreach`)

Sidebar (Outreach active) + main = 2-pane (apps list 1/3 left + selected-app detail 2/3 right).

- **Top**: title "Outreach", subtitle "Tied to your {N} active applications · {M} need a nudge today · {K} referrals secured". Right: `linkedin · @shyampadia · {N} connections` · `gmail · synced {Nm}`.
- **Left pane: applications list** — search input "Search applications…", "All stages" filter pill. Grouped: **NEEDS FOLLOWUP · {N}** (yellow accent; cards with company tile, role · team, "{contacts} contacts · sent {Nd} ago · no reply", stage chip, state pill `AWAITING REPLY` / `CALL BOOKED` / `REFERRED` / `NO REPLY · 7D`) → **ACTIVE · {N}** → **COLD · {N}**.
- **Right pane: selected application detail** — header (company tile · role · "applied {N} days ago" · stage chip · "match 0.86" · right "Open in tracking →"). **RECOMMENDED NEXT MOVE · TODAY** card (amber accent): "Followup with {Contact} · {role}", meta line, **AI DRAFT** body card (cyan-tinted) with full message text, action row **Send via LinkedIn** (primary) · Edit · Regenerate · "Skip · don't suggest again" (ghost). **Contacts at {Company} · {N}** card (Find more button on right): per-contact row — avatar, name + degree chip (`1st`, `2nd · via Priya`), school + mutuals, role + team, last-activity sentence, state pill (`REFERRED YOU` emerald · `AWAITING REPLY` amber · `NO REPLY · 7D` rose), `…` actions. **Timeline** below: vertical timeline of touches across LinkedIn + email + system events with dot color per event kind.

---

### Screen 11 · Settings (`/settings`)

Sidebar (Settings active) + main. 6 tabs across the top: **Account · LLM Provider · Notifications · Auto-Apply · Sources · Deployment**.

- **LLM Provider tab**: title "Settings" + subtitle "Configure how Naavik runs." "Active provider" card (3 provider cards in a row): Anthropic Claude (selected, indigo border + radio dot, `Recommended · best resume bullet quality`, `CLOUD` chip) / OpenAI GPT (`GPT-4o · faster, slightly cheaper`, `CLOUD` chip) / Ollama Local (`Llama 3.1 70B on your machine · private`, `LOCAL` chip emerald). "API configuration" card: API key input with show/hide eye + **Test connection** button (success: cyan inline "Connection ok · responded in 412ms · model claude-3.5-sonnet-20250219"; failure: rose inline). MODEL dropdown (provider-scoped). 3 cost cards in a row: `THIS MONTH` $3.42 (≈412k tokens) / `AVG / GENERATION` $0.04 (resume + cover letter) / `RATE LIMIT` 50/min (tier 2). Footer hint with lock icon: "Your API key is stored encrypted at `~/.naavik/secrets.enc`."
- **Deployment tab (self-hosted variant)**: status card "Self-hosted" emerald badge — "active · v0.4.2 · docker-compose · uptime 14d 6h · last restart Apr 14"; right **Restart** + **Update v0.4.3** (when available). **Live log tail** card: header with macOS traffic-light dots · `~/.naavik/logs · live tail` · right `STREAMING` (cyan dot pulsing) · Pause · Copy. Mono terminal display with realistic log lines (info / warn / error mix). **On disk** card group (4 cards): `DATA DIR` ~/.naavik/data ({size} · {N} jobs · {M} applications); `SECRETS` ~/.naavik/secrets.enc (aes-256-gcm); `CONFIG` ~/.naavik/config.toml (last edited Nd ago); `SNAPSHOTS` ~/.naavik/snapshots/ (N daily · auto-prune at 30).
- **Other tabs (specs deferred — design pending)**: Account (name, email, password, sign out, "Delete my account" destructive); Notifications (Discord webhook, Telegram bot token, "Send test", per-event toggles); Auto-Apply (master toggle default OFF, score threshold slider default 0.85, per-source toggle, daily total cap optional); Sources (scraping source list with enable/disable/schedule).

---

## Output format

Per screen produce:

1. **Desktop mockup** (1440×900 frame)
2. **Mobile mockup** (375×812 frame)
3. **One sentence** describing the key interaction

After all screens, list:

- **New components introduced** beyond the design system (with brief spec)
- **Edge cases / states** to design in follow-up

End of prompt.
