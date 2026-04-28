# Naavik Design System — Claude Design Upload

> **Purpose:** This document is formatted specifically for uploading to Claude Design's **"Set up design system"** feature. It contains all brand tokens, typography, components, and visual rules in a format Claude can extract.
> 
> **How to use:**
> 1. Go to claude.ai/design
> 2. Click **"Set up design system"** (the button below the project creation options)
> 3. Upload this file + any screenshots of reference products (Linear, Cursor, Plausible)
> 4. Let Claude extract the design system
> 5. Validate with test prompts
> 6. Publish
> 7. THEN create Prototype projects (they auto-inherit this system)

---

## Brand Positioning

**Naavik** (Hindi: नाविक, "Navigator") — an open-source career automation platform.

**Self-hosted first, cloud available.** The primary experience is self-hosted (Docker Compose or NixOS). A managed cloud tier ($15/month, bring-your-own AI credits) exists for convenience. Both paths are functionally identical. The UI should feel like a developer tool you run in your homelab — never like a SaaS product you're renting.

**Audience:** Tech-savvy professionals — engineers, PMs, designers — who value control over their data.

**Reference products:** Linear, Cursor, Plausible Analytics, Vercel/v0

**Vibe adjectives:** confident, calm, data-dense, tech-savvy, AI-native, editorial, direct
**Avoid:** loud, sterile, corporate, cute, decorative, AI-gimmicky

---

## Color Palette

### Dark Mode (Primary)

| Token | Hex | Tailwind | Usage |
|---|---|---|---|
| Page background | `#020617` | slate-950 | Global page background |
| Surface / card | `#0F172A` | slate-900 | Cards, panels, sidebar |
| Elevated / hover | `#1E293B` | slate-800 | Hover states, modals, dropdowns |
| Border subtle | `#1E293B` | slate-800 | Card borders |
| Border strong | `#334155` | slate-700 | Input borders, dividers |
| Text primary | `#F8FAFC` | slate-50 | Headings, primary text |
| Text secondary | `#CBD5E1` | slate-300 | Body text |
| Text muted | `#94A3B8` | slate-400 | Captions, metadata, placeholders |
| Text disabled | `#475569` | slate-600 | Disabled state |

### Brand Colors

| Token | Hex | Tailwind | Usage |
|---|---|---|---|
| Brand primary | `#6366F1` | indigo-500 | Primary buttons, active nav, key CTAs |
| Brand hover | `#818CF8` | indigo-400 | Hover state of primary |
| Brand subtle | `rgba(99,102,241,0.1)` | indigo-500/10 | Tinted backgrounds |
| Brand ring | `rgba(99,102,241,0.4)` | indigo-500/40 | Focus rings |

### Accent (AI — used sparingly)

| Token | Hex | Tailwind | Usage |
|---|---|---|---|
| Accent primary | `#22D3EE` | cyan-400 | AI-generated content indicators, sparkle effects |
| Accent glow | `rgba(34,211,238,0.2)` | cyan-400/20 | Subtle glow on AI elements |

### Semantic Colors

| Token | Hex | Tailwind | Usage |
|---|---|---|---|
| Success | `#10B981` | emerald-500 | Positive states, offers, applied |
| Warning | `#F59E0B` | amber-500 | Action needed, pending |
| Danger | `#F43F5E` | rose-500 | Errors, rejected, destructive actions |
| Info | `#0EA5E9` | sky-500 | Informational badges |

### Status Pipeline Colors

| Status | Dot color |
|---|---|
| FOUND | `#64748B` slate-500 |
| SCORED | `#0EA5E9` sky-500 |
| APPROVED | `#6366F1` indigo-500 |
| DOCS_GENERATED | `#22D3EE` cyan-400 |
| APPLIED | `#10B981` emerald-500 |
| INTERVIEWING | `#F59E0B` amber-500 |
| OFFER | `#34D399` emerald-400 + ring |
| REJECTED | `#F43F5E` rose-500 |
| WITHDRAWN | `#475569` slate-600 |

---

## Typography

### Fonts

- **Sans (UI):** Inter — weights 400, 500, 600, 700
- **Mono (data, tags, scores, IDs):** JetBrains Mono — weights 400, 500

### Type Scale

| Token | Size | Weight | Tracking | Usage |
|---|---|---|---|---|
| Display | 36px | 700 | tight | Page hero (rare) |
| H1 | 30px | 700 | tight | Page title |
| H2 | 20px | 600 | normal | Section heading |
| H3 | 18px | 500 | normal | Card title |
| Body | 16px | 400 | relaxed | Paragraphs |
| Small | 14px | 400 | normal | Secondary info |
| Caption | 12px | 500 | uppercase, wide | Labels, metadata |
| Mono | 14px | 500 | normal | Scores, tags, IDs, dates |

**Numerals:** Always use tabular-nums for stat cards, scores, dates.

---

## Spacing & Layout

- Page padding: 24px (desktop), 32px (large desktop)
- Card padding: 20px (compact), 24px (standard)
- Section gap: 24px
- Component gap: 8px
- Sidebar width: 256px (collapsed: 64px)
- Max content width: 1280px (most pages), 768px (forms)

---

## Border Radius

| Token | Value | Usage |
|---|---|---|
| Subtle | 4px | Tags, badges, small inputs |
| Standard | 8px | Buttons, cards, inputs |
| Prominent | 12px | Modals, large surfaces |
| Full | 9999px | Avatars, pill chips |

---

## Shadows

Dark mode shadows are subtle. Prefer borders + background contrast over heavy shadows.

- Card resting: none (rely on bg + border)
- Card hover: `0 10px 15px -3px rgba(99,102,241,0.05)`
- Modal: `0 25px 50px -12px rgba(0,0,0,0.4)`
- Dropdown: `0 20px 25px -5px rgba(0,0,0,0.3)`
- AI glow (intentional): `0 10px 15px -3px rgba(34,211,238,0.2)`

---

## Iconography

**Lucide Icons exclusively** — stroke width 1.5.

Key icons by concept:
- Brand: compass (stylized)
- AI: sparkles (cyan-400)
- Dashboard: layout-dashboard
- Profile: user-round
- Jobs: briefcase
- Resume: file-text
- Settings: settings
- Score: gauge
- Search: search
- Filter: sliders-horizontal
- Add: plus
- Edit: pencil
- Delete: trash-2
- Save: check
- Cancel: x
- Upload: upload-cloud
- Download: download
- Success: check-circle-2
- Pending: clock
- Rejected: x-circle

---

## Component Specifications

### Button

- Border radius: 8px
- Padding: 16px horizontal, 8px vertical
- Font: Inter 500

**Variants:**
- Primary: bg `#6366F1`, text `#F8FAFC`, hover bg `#818CF8`
- Secondary: bg `#1E293B`, text `#F1F5F9`, border `#334155`
- Ghost: transparent bg, text `#CBD5E1`, hover bg `#1E293B`
- Danger: bg `#F43F5E`, text white
- Icon-only: padding 8px, rounded-lg

All buttons: focus ring `2px solid rgba(99,102,241,0.4)`

### Card

- Background: `#0F172A`
- Border: 1px solid `#1E293B`
- Border radius: 8px
- Padding: 24px
- Hover: border transitions to `#334155`, subtle indigo shadow

### Input

- Background: `#0F172A`
- Border: 1px solid `#334155`
- Border radius: 8px
- Padding: 12px horizontal, 8px vertical
- Text: `#F8FAFC`
- Placeholder: `#64748B`
- Focus: border `#6366F1`, ring `rgba(99,102,241,0.2)`

### Tag / Chip

- Background: `#1E293B`
- Text: `#CBD5E1`
- Border radius: 4px
- Padding: 4px horizontal, 2px vertical
- Font: JetBrains Mono, 12px
- Removable variant: add × button

### Status Badge

Dot + label pattern:
- Dot: 8px circle
- Label: 12px, medium weight
- Colors match status pipeline table above

### Stat Card

```
[Caption: 12px uppercase muted]
[Value: 30px bold tabular-nums]
[Delta: 14px colored]
```

### Sidebar

- Width: 256px
- Background: `#0F172A`
- Border right: 1px solid `#1E293B`
- Top: brand lockup (compass icon + "Naavik" in Inter 700)
- Nav items: icon (20px) + label, 12px vertical padding, 8px border radius
- Active item: bg `#6366F1`, text white
- Hover item: bg `#1E293B`
- Bottom: theme toggle + user avatar

---

## Voice & Tone

### Microcopy Rules

- **Direct over cute.** "Generate resume" not "Let's craft your resume! ✨"
- **Honest about AI.** Label AI-generated content with cyan sparkle icon + "AI" tag
- **Quantify.** "12 jobs found this week" not "Several new jobs"
- **Second person, factual.** "You've applied to 47 jobs this month."

### Empty States

Three parts: icon + one-line description + primary CTA.
Example: "No jobs scored yet. Run a scrape to find matches → [Find jobs]"

### Error States

Three parts: what went wrong, why, what to do.
Example: "Couldn't reach Claude API. Check your API key in Settings → [Open settings]"

---

## Motion

- Hover transitions: 150ms
- Modal entry: fade + scale 95%→100%, 200ms
- Drawer slide: 250ms
- Skeleton loaders: pulse, 1500ms
- AI generation: shimmer on affected area

Never animate decoratively. Every animation communicates state change.

---

## Accessibility

- WCAG AA contrast in dark mode
- Visible focus rings (indigo-tinted)
- Keyboard navigation for all interactive elements
- ARIA labels on icon-only buttons
- Form labels never rely on placeholder alone
- HTMX swaps: `aria-live="polite"` on dynamic content

---

## Anti-patterns

- No emoji for status indicators (use Lucide + colored dots)
- No mixing icon stroke widths
- No heavy shadows for hierarchy in dark mode
- No full-saturation colors for large surfaces
- No decorative animations
- No chatbot-style AI UI (show structured output, not transcripts)
- No SaaS upsell pressure (cloud tier mentioned quietly in Settings only)

---

## Sample Content

Use this realistic data in all mockups:

- **User:** Shyam Padia, Senior Software Engineer at Intuit, San Francisco, CA
- **Visa:** H1B (requires sponsorship)
- **Companies:** Stripe, Databricks, Anthropic, Vercel, Linear, Plaid, Ramp, Notion, Figma
- **Roles:** Senior ML Engineer, Staff Backend Engineer, Engineering Manager, Founding Engineer
- **Tags:** ai-ml, backend, devops, frontend, leadership, genai, data-eng, platform
- **Sample bullet (oneline):** "Built ML personalization platform serving 100M+ users at Intuit, lifting CTR by 23% and revenue by $4.2M annually."

---

## DaisyUI Theme Config

```javascript
{
  "naavik": {
    "color-scheme": "dark",
    "primary": "#6366F1",
    "primary-content": "#F8FAFC",
    "secondary": "#22D3EE",
    "secondary-content": "#020617",
    "accent": "#22D3EE",
    "neutral": "#1E293B",
    "base-100": "#020617",
    "base-200": "#0F172A",
    "base-300": "#1E293B",
    "base-content": "#F8FAFC",
    "info": "#0EA5E9",
    "success": "#10B981",
    "warning": "#F59E0B",
    "error": "#F43F5E",
    "--rounded-box": "0.75rem",
    "--rounded-btn": "0.5rem",
    "--rounded-badge": "0.375rem"
  }
}
```
