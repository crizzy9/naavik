# Naavik Screen Catalog

> **Last updated:** 2026-04-25
> **Product positioning:** Self-hosted first, cloud available ($15/mo, bring-your-own AI credits). The UI feels like a developer tool, not a SaaS product.
> **Design prompt:** See `CLAUDE_DESIGN_PROMPT.md` for screen descriptions (assumes design system already published). See `DESIGN.md` for the design system setup file.
> **Design system:** See `DESIGN.md` for color tokens, typography, components, voice.
> **Workflow:** See `WORKFLOW.md` for the design → implementation pipeline.
>
> **Maintenance:** Update this file when screens are added, removed, or significantly redesigned. Mockup and implementation status columns must reflect reality.

---

## How to read this doc

Each screen entry has:
- **Route** — URL path
- **Phase** — when it's planned for build (per ROADMAP.md)
- **Mockup** — `[ ]` not designed, `[~]` in design, `[x]` mockup committed to `docs/design/mockups/`
- **Impl** — `[ ]` not built, `[~]` in progress, `[x]` shipped
- **Purpose** — one sentence
- **Layout** — high-level structure
- **Components** — key elements (link to `DESIGN.md` components when relevant)
- **Interactions** — HTMX swaps, modals, navigation
- **States** — empty / loading / error variants

---

## Screen Index

| # | Screen | Route | Phase | Mockup | Impl |
|---|---|---|---|---|---|
| 1 | Login / OAuth | `/login` | 1 | [ ] | [ ] |
| 2 | Dashboard | `/` | 1 | [ ] | [~] (placeholder) |
| 3 | Onboarding — Resume Upload | `/onboarding` | 1 | [ ] | [ ] |
| 4 | Profile View | `/profile` | 1 | [ ] | [ ] |
| 5 | Profile Editor | `/profile/edit` | 1 | [ ] | [ ] |
| 6 | Bullet Editor (modal) | (component) | 1 | [ ] | [ ] |
| 7 | Resume Generator | `/generate/resume` | 1 | [ ] | [ ] |
| 8 | Cover Letter Generator | `/generate/cover-letter` | 1 | [ ] | [ ] |
| 9 | Settings | `/settings` | 1 | [ ] | [ ] |
| 10 | Jobs List | `/jobs` | 2 | [ ] | [ ] |
| 11 | Job Detail | `/jobs/:id` | 2 | [ ] | [ ] |
| 12 | Manual Job Entry | `/jobs/new` (modal) | 2 | [ ] | [ ] |
| 13 | Score Card / Match Explanation | (component, in Job Detail) | 3 | [ ] | [ ] |
| 14 | Kanban Pipeline | `/jobs?view=kanban` | 4 | [ ] | [ ] |
| 15 | Analytics Dashboard | `/analytics` | 4 | [ ] | [ ] |
| 16 | Email Inbox | `/inbox` | 5 | [ ] | [ ] |
| 17 | Contacts List | `/contacts` | 5 | [ ] | [ ] |
| 18 | Outreach Composer | `/contacts/:id/compose` | 5 | [ ] | [ ] |
| 19 | Interview Pipeline | `/interviews` | 5 | [ ] | [ ] |

**Phase 1 design batch (next):** Screens 1–9.

---

## Phase 1 Screens (MVP design batch)

### 1. Login / OAuth

- **Route:** `/login`
- **Purpose:** Single sign-in entry point. Builds trust on first impression.
- **Layout:** Centered card on dark background. Subtle compass-pattern background motif (very faint, not distracting).
- **Components:**
  - Brand lockup (compass icon + "Naavik" wordmark)
  - Tagline: "Navigate your career with intent."
  - Single primary button: "Sign in with Google"
  - Footer: small links to GitHub repo, docs
- **Interactions:** OAuth redirect to Google. Loading spinner during redirect.
- **States:**
  - Empty: default
  - Loading: button → spinner
  - Error: inline alert above button (rose tint, dismissible)

---

### 2. Dashboard

- **Route:** `/`
- **Purpose:** First view after sign-in. Snapshot of pipeline + entry to key actions.
- **Layout:** Sidebar (persistent) + main content. Main = top stats row, then activity feed + quick actions side-by-side.
- **Components:**
  - 4 `stat_card`s: Jobs Found, Applied, Interviews Scheduled, Offers (each with delta vs last week)
  - Activity feed: list of recent events (job scored, application submitted, interview scheduled, etc.) — each row shows icon + verb + object + timestamp
  - Quick actions card: 3 primary buttons (Upload resume / Find new jobs / Generate documents)
  - "Pipeline overview" mini-Kanban: count badges per status
- **Interactions:**
  - Stat cards click-through to filtered Jobs List
  - Activity feed items link to relevant detail page (job, application, etc.)
  - Quick actions trigger respective flows
- **States:**
  - First-run empty state: "Welcome. Upload your resume to get started." with prominent CTA
  - Loaded: real data
  - No activity yet (post-onboarding): show getting-started checklist instead of feed

---

### 3. Onboarding — Resume Upload

- **Route:** `/onboarding` (3-step wizard)
- **Purpose:** First experience after sign-in. Convert a raw PDF resume into structured profile data via AI.
- **Layout:** Full-width centered wizard. Progress indicator at top (Step 1/3, 2/3, 3/3).
- **Steps:**
  1. **Upload** — Large drag-drop zone (h-96), accepts PDF only, max 10MB. Sample text on hover. Or "Skip — enter manually".
  2. **Extracting (AI in progress)** — Animated state. Cyan sparkle icon. Status text: "Reading your resume… Identifying experience… Extracting skills…" Each step shimmer-completes.
  3. **Review** — Extracted profile preview, sectioned (Experience / Education / Skills / Projects). Each section has "Looks good" / "Edit" buttons. Bottom: "Save to profile" CTA.
- **Components:** Drag-drop zone, progress steps, AI extraction shimmer, preview sections with `bullet_editor` access
- **Interactions:**
  - HTMX file upload with progress bar
  - SSE or polling during extraction step (show streaming output if possible)
  - Inline edits on review step (HTMX PUT per field)
- **States:**
  - Upload: idle / dragging-over / uploading / error (rejected file type, too large, etc.)
  - Extraction: in-progress / complete / partial-failure (some sections couldn't be parsed)
  - Review: clean extraction / had errors (show flagged fields)

---

### 4. Profile View

- **Route:** `/profile`
- **Purpose:** Read-only display of full profile (this IS the user's CV in the system).
- **Layout:** Sidebar + main. Main = profile sections stacked vertically with sticky section nav on right side.
- **Sections (in order):**
  - **Hero**: Avatar, name, title, location, contact links (email, phone, portfolio, github, linkedin), visa status badge
  - **Summary**: short + full versions toggleable
  - **Experience**: timeline-style cards. Each role: company logo, title, dates, location, bullets (oneline shown by default; click to expand to detailed).
  - **Education**: card list
  - **Skills**: grouped by category, each as tag chips
  - **Projects**: card grid (3 cols on desktop) with title, oneline, tags
  - **Certifications**: compact list
  - **Open Source**: compact list
- **Components:** All sections are reusable; bullet display = compact, with `tag` chips inline
- **Interactions:**
  - "Edit profile" button → `/profile/edit`
  - Click a bullet to expand to detailed view
  - Section nav scrolls to anchor
  - "Generate resume from this profile" CTA in hero
- **States:**
  - Empty (just signed up, hasn't uploaded): redirect to `/onboarding`
  - Partial: some sections missing → "Add education" affordance per section

---

### 5. Profile Editor

- **Route:** `/profile/edit`
- **Purpose:** Edit every field of the profile.
- **Layout:** Same as Profile View, but with inline edit affordances. Persistent "Save / Cancel" footer bar.
- **Components:**
  - All sections from Profile View, but with edit modes
  - Add/remove buttons per section
  - Drag handles for reordering experiences, bullets, projects
  - "Auto-save" indicator (checkmark when saved, spinner when in flight)
- **Interactions:**
  - HTMX inline updates per field (debounced 500ms)
  - Click "Add experience" → new card with empty fields
  - Click bullet → opens Bullet Editor modal (Screen 6)
  - Drag-and-drop via Sortable.js (only place we allow JS beyond HTMX)
- **States:**
  - All-clean: green checkmark, "All changes saved"
  - In-flight: spinner, "Saving…"
  - Error: rose alert, "Couldn't save — retry"

---

### 6. Bullet Editor (modal)

- **Component (no route)** — opens from anywhere a bullet is editable
- **Purpose:** Edit a single experience bullet's two forms (oneline + detailed) with tag and validation.
- **Layout:** Modal, ~720px wide. Two-column body.
- **Components:**
  - **Left column**: "Oneline (1-page resume)"
    - Textarea, max 3 lines high
    - Live char counter
    - **Live Typst render preview** showing if it overflows 1 line in the actual resume template — green checkmark or rose warning
  - **Right column**: "Detailed (full CV / portfolio)"
    - Larger textarea, autosize
    - No length limit
  - **Below both columns**:
    - Tag picker (multi-select chips from fixed vocabulary: ai-ml, backend, devops, frontend, leadership, genai, data-eng, platform)
    - "Default include in 1-page resume" toggle
    - Optional metrics fields: Revenue (number), Percentage (number), Team size (number)
  - **Footer**: "Cancel" (ghost) and "Save" (primary, disabled until valid)
- **Interactions:**
  - HTMX POST on save → updates bullet in DB → swaps the bullet display in parent view
  - Live validation: if oneline overflows → rose border + warning text
  - Tag picker: typeahead, can't add tags outside vocabulary
- **States:** valid / invalid (oneline overflow) / saving / error

---

### 7. Resume Generator

- **Route:** `/generate/resume`
- **Purpose:** Produce a tailored 1-page resume PDF for a specific job. Show the user exactly which bullets are selected and why.
- **Layout:** Three columns (responsive: collapses to tabs on mobile).
  - **Left (1/4)**: Job Description input — paste text or fetch by URL. Tag detection result shown below ("Detected tags: ai-ml, backend, leadership").
  - **Middle (2/4)**: Bullet selection list. Grouped by experience. Each bullet shows: oneline, tags, AI-included/AI-excluded badge with reason. User can manually toggle.
  - **Right (1/4)**: Live PDF preview (iframe of compiled Typst). Updates on every change with debounce.
- **Top bar:** Template selector (1-page / Full CV), profile selector (if multi-profile), download button.
- **Components:** Job desc input, bullet selector list, PDF preview iframe, "AI re-suggest" button (refreshes selection based on current job desc)
- **Interactions:**
  - HTMX POST on job desc change → triggers AI tag detection + bullet selection
  - Toggle bullet → HTMX swap on preview iframe
  - "Generate PDF" → final compile + download
- **States:** idle / detecting tags / re-selecting / preview-rendering / preview-stale / error (Typst compile failure → show error in preview pane)

---

### 8. Cover Letter Generator

- **Route:** `/generate/cover-letter`
- **Purpose:** AI-generate a personalized cover letter for a specific job, then refine it.
- **Layout:** Two columns (responsive: stacks on mobile).
  - **Left (1/2)**: Job description input + company name + role title. "Tone" selector (Professional / Enthusiastic / Direct).
  - **Right (1/2)**: AI-generated paragraphs (intro / body / close), each editable in-place. PDF preview below the editable text or as a toggle.
- **Top bar:** "Re-generate", "Clear", "Download PDF".
- **Components:** Inputs, paragraph editors with cyan AI badge, PDF preview iframe
- **Interactions:**
  - "Generate" button → AI streams paragraphs into the right pane (use SSE)
  - Each paragraph editable inline; edits persist
  - Tone change re-generates
- **States:** empty / generating (streaming) / ready / regenerating / error

---

### 9. Settings

- **Route:** `/settings` (with sub-routes for tabs)
- **Purpose:** All configuration in one place.
- **Layout:** Sidebar + main. Main has secondary tabs across the top.
- **Tabs:**
  - **Account**: name, email, password change, sign-out, "Delete my account" (destructive)
  - **LLM Provider**: Radio: Anthropic / OpenAI / Ollama. API key input (masked). "Test connection" button. Currently-selected provider shown in main nav as cyan badge.
  - **Notifications**: Discord webhook URL, Telegram bot token, "Send test notification" button. Toggles per event type (new high-score job, application sent, interview scheduled, etc.).
  - **Auto-Apply**: Master toggle (default OFF). Score threshold slider (default 0.85). Per-source toggle (Greenhouse on / LinkedIn off / etc.). Daily cap.
  - **Sources** (Phase 2+): scraping source list with enable/disable/schedule
  - **Deployment**: Shows current deployment mode (Self-hosted badge in emerald, or Cloud badge in indigo). For self-hosted: Docker Compose / NixOS config snippets, restart button. For cloud: usage stats, "bring your own API key" reminder. Cloud upgrade option ($15/mo) presented as a quiet secondary action — never pushy.
- **Components:** Tab nav, form inputs, secret inputs (with show/hide), test buttons, deployment badge
- **Interactions:**
  - HTMX form submit per tab (no full page reload)
  - "Test connection" → HTMX POST → cyan check or rose error inline
  - Deployment tab: read-only status display, config copy-to-clipboard
- **States:** clean / unsaved-changes (footer alerts) / saving / saved / error

---

## Phase 2+ Screens (later design batches)

### 10. Jobs List

- **Route:** `/jobs`
- **Purpose:** Browse, filter, and act on the entire job pipeline.
- **Layout:** Sidebar + main. Main = filter rail (left, ~280px) + job list (right).
- **Filter rail:** status checkboxes, score range slider, source checkboxes, tags multi-select, location text, visa filter (auto-checked for users requiring sponsorship), date range.
- **Job list:** dense table OR card view (toggle). Each row: company logo, position, location, score badge, status pill, posted/found date, action menu.
- **Top bar:** Search input, view toggle (Table / Kanban → links to Screen 14), bulk action menu when rows selected.

### 11. Job Detail

- **Route:** `/jobs/:id`
- **Purpose:** Everything about a single job in one place.
- **Layout:** Hero (company + position + status pipeline bar) → Score Card (Screen 13) → Tabs (Description / Activity / Documents / Notes / Contacts).
- **Action bar:** Generate tailored resume / Generate cover letter / Mark as applied / Reject / Archive.

### 12. Manual Job Entry

- **Route:** `/jobs/new` (modal preferred, full route as fallback)
- **Purpose:** Quickly log a job applied externally or seen elsewhere.
- **Layout:** Modal form. URL-first: paste URL → AI auto-fills fields.

### 13. Score Card / Match Explanation (component)

- **Embedded in Job Detail.** Big score donut (0–100), strengths list, gaps list, matched bullets, "Generate tailored resume" CTA.

### 14. Kanban Pipeline

- **Route:** `/jobs?view=kanban`
- **Purpose:** Visual pipeline. Drag-drop to change status.
- **Layout:** Horizontal scroll of columns, one per status. Compact job cards. Filters in collapsible top bar.

### 15. Analytics Dashboard

- **Route:** `/analytics`
- **Purpose:** Outcomes data. What's working, what isn't.
- **Layout:** Funnel chart at top (Found → Applied → Interview → Offer). Below: response rate by company, time-to-response distribution, resume A/B variants.

### 16. Email Inbox

- **Route:** `/inbox`
- **Purpose:** AI-classified email threads tied to applications.
- **Layout:** Two-pane email client. List left, thread right. Classification badges on each thread (Interview / Rejection / Offer / Assessment / Follow-up / Other).

### 17. Contacts List

- **Route:** `/contacts`
- **Purpose:** Recruiters, employees, hiring managers per company.
- **Layout:** Grouped by company. Type filter at top. Cards with name, title, type badge, last-contacted date.

### 18. Outreach Composer

- **Route:** `/contacts/:id/compose`
- **Purpose:** AI-assisted personalized outreach.
- **Layout:** Template picker on left, drafted message on right with edit-in-place. "Send via LinkedIn" / "Copy to clipboard" / "Mark as sent manually".

### 19. Interview Pipeline

- **Route:** `/interviews`
- **Purpose:** Calendar of upcoming interviews + prep materials per interview.
- **Layout:** Calendar view (week/month toggle). Sidebar with prep checklist for selected interview.

---

## Update Process

1. When adding a new screen: append to Screen Index table + write a full section.
2. When designing: change Mockup status `[ ] → [~] → [x]`.
3. When implementing: change Impl status `[ ] → [~] → [x]`.
4. When changing scope: edit the screen section directly. Bump "Last updated" date.
