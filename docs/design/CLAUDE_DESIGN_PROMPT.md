# Claude Design Prompt — Naavik Screens

> **Last updated:** 2026-04-25
> **Prerequisite:** You MUST have already set up and published the Naavik design system in Claude Design. This prompt is for generating screens ONLY, assuming the design system is already in place.
> 
> **How to use:**
> 1. Go to claude.ai/design
> 2. Your Naavik design system should already be published (set up via "Set up design system")
> 3. Click **"Create"** → **"Prototype"** → **"High fidelity"**
> 4. Name it "Naavik Phase 1"
> 5. Paste this prompt
> 6. Claude will generate screens using the published design system automatically
>
> **Note:** This prompt is much shorter than the full prompt because the design system already defines colors, typography, components, and voice. This prompt only describes screens and layout.

---

## Product Context

Design screens for **Naavik**, an open-source self-hosted career automation platform.

**Self-hosted first, cloud available.** Primary users are tech-savvy professionals (engineers, PMs, designers) who self-host tools. The UI feels like a developer tool — dark mode, data-dense, no SaaS bloat. A cloud tier ($15/mo, bring-your-own AI credits) exists but is never pushed as premium.

**Key features:** Resume PDF upload → AI extracts profile → job scraping → AI scoring → per-job resume/cover letter generation → application tracking → email monitoring.

---

## Screen Batch: Phase 1 MVP (9 screens)

For each screen, produce a **desktop mockup** (1440×900) and **mobile mockup** (375×812). Show real interactivity hints where relevant.

---

### Screen 1: Login / OAuth (`/login`)

**Layout:** Centered card on dark page background.
**Elements:**
- Subtle compass-pattern motif very faint in background
- Brand lockup: compass icon + "Naavik" wordmark (Inter 700)
- Tagline: "Navigate your career with intent."
- Primary button: "Sign in with Google" (white bg, Google logo)
- Footer links: "GitHub", "Documentation"
**States:** Show default state + loading state (button spinner)

---

### Screen 2: Dashboard (`/`)

**Layout:** Sidebar + main content (sidebar inherits from design system).
**Elements:**
- Header: "Welcome back, Shyam" + avatar + date
- **Stat cards row (4):** Jobs Found (142, +12 this week), Applied (47, +8), Interviews (5, +2), Offers (1)
- **Two-column below:**
  - Left (2/3): "Recent activity" feed — 6-8 entries. Each: icon + action + object + relative time. Example: "Scored 'Senior ML Engineer @ Stripe' • 91 • 2h ago"
  - Right (1/3): "Quick actions" card with 3 buttons (Upload resume / Find new jobs / Generate documents) + "Pipeline overview" mini-bars showing count per status
**States:** Populated state + first-run empty state ("Welcome. Upload your resume to get started." with prominent CTA)

---

### Screen 3: Onboarding — Resume Upload (`/onboarding`)

**Layout:** 3-step wizard, full-width centered.
**Show step 2 (AI extracting) as hero — most distinctive moment:**
- Step indicator: 1 ✓ Upload — 2 ● Extracting — 3 Review
- Center card: cyan sparkle icon with glow, animated shimmer
- Status lines: "Reading your resume…" (in progress) → "Identifying experience…" (in progress) → "Extracting skills…" (queued) — show checkmarks for completed
- Below: skeleton preview of extracted sections appearing as parsed
**Secondary mockup:** Step 1 drag-drop zone (large, h-96, PDF only, max 10MB)

---

### Screen 4: Profile View (`/profile`)

**Layout:** Sidebar + main. Main = stacked sections with sticky right-side nav.
**Sections shown:**
- **Hero:** Large avatar (or initials SP), name "Shyam Padia" (display size), title "Senior Software Engineer • Intuit", location "San Francisco, CA", contact icons (email, phone, github, linkedin, portfolio), visa badge "H1B • Requires sponsorship"
- Top right: "Edit profile" (secondary) + "Generate resume" (primary)
- **Summary:** 2 paragraphs, toggleable short/full
- **Experience (show 2 roles):** Timeline cards. Each: company logo placeholder, title, dates, location, bullets as compact list with tag chips inline (ai-ml, backend, leadership)
- Sticky right nav: Summary / Experience / Education / Skills / Projects / Certifications

---

### Screen 5: Profile Editor (`/profile/edit`)

**Layout:** Same as Profile View, with edit affordances.
**Show Experience section in EDIT mode:**
- Input fields for title, company, dates
- Bullet list with edit/delete/drag-handle per bullet
- "+ Add bullet" ghost button
- Persistent footer: "All changes saved ✓ • [Discard] [Save]"
- Auto-save indicator

---

### Screen 6: Bullet Editor Modal (component)

**Layout:** Modal, ~720px wide, overlaying Profile Editor.
**Header:** "Edit bullet" + close ×
**Two-column body:**
- **Left — Oneline (1-page resume):** Textarea (3 lines), char counter "127 / ~140", Typst preview showing "✓ Fits on 1 line" (emerald) or "✗ Overflows" (rose)
- **Right — Detailed (full CV):** Larger textarea, autosize, multi-sentence example
**Below both:**
- Tag picker: 8 selectable chips, 3 selected (ai-ml, backend, leadership)
- Toggle: "Include in default 1-page resume" (checked)
- Metric inputs: Revenue "$4.2M", Percentage "+23%", Team size "8"
**Footer:** "Cancel" (ghost) + "Save bullet" (primary)

---

### Screen 7: Resume Generator (`/generate/resume`)

**Layout:** Sidebar + main. Main = three-column workspace.
- **Left (1/4):** "Job description" — paste textarea + "Import from URL" input. Below: "Detected tags: ai-ml, backend, leadership, genai" as cyan-tinted chips with sparkle icon.
- **Middle (2/4):** "Bullets" — grouped by experience. Each bullet: oneline + tags + AI badge ("AI included" emerald or "AI excluded — low tag match" muted). Toggle switch on right.
- **Right (1/4):** "Preview" — iframe-style PDF preview of 1-page resume. Template selector dropdown above.
**Top bar:** "← Back" / "Re-suggest with AI" (secondary, sparkle icon) / "Download PDF" (primary)

---

### Screen 8: Cover Letter Generator (`/generate/cover-letter`)

**Layout:** Sidebar + main. Main = two-column workspace.
- **Left (1/2):** Company "Stripe", Role "Senior ML Engineer", Job description textarea, Tone selector (Professional / Enthusiastic / Direct radio chips), "Generate" button
- **Right (1/2):** AI-generated cover letter — 3 editable paragraphs (intro / body / close), each with cyan AI badge. PDF preview thumbnail below.
**Show one paragraph mid-streaming** (partial sentence with cursor) to convey AI generation.

---

### Screen 9: Settings — LLM Provider (`/settings`)

**Layout:** Sidebar + main. Tab bar at top.
**Tabs shown:** Account / **LLM Provider** (active) / Notifications / Auto-Apply / Sources / Deployment
**LLM Provider tab:**
- "Active provider" card: 3 radio options as cards — Anthropic Claude (selected, indigo border) / OpenAI GPT / Ollama (Local). Each: logo + name + description
- "API Configuration" card: masked API key input + "Test connection" button → cyan check or rose error inline
- "Model selection" dropdown: "claude-3.5-sonnet"
- Hint: "Your API key is stored encrypted. Naavik never sends your key to any third party."
**Deployment tab (show as secondary):**
- Badge "Self-hosted" (emerald) with description
- Docker Compose snippet
- Quiet secondary: "Switch to Cloud ($15/mo)"

---

## Output Format

Per screen produce:
1. **Desktop mockup** (1440×900 frame)
2. **Mobile mockup** (375×812 frame)
3. **One sentence** describing the key interaction

After all screens, list:
- Any **new components** introduced (with brief spec)
- **Edge cases** or states to design in follow-up

---

End of prompt.
