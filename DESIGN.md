# Naavik Design System

> **Version:** 1.0
> **Last updated:** 2026-04-25
> **Stack:** Tailwind CSS + DaisyUI + HTMX (server-rendered Jinja2)
>
> This is the canonical visual contract for Naavik. Every mockup and every implemented page must conform to it.
> This file is also the source material for Claude Design's "Set up design system" feature.

---

## Brand Essence

**Naavik** (Hindi: नाविक, "Navigator") — an open-source career automation platform.

**Core positioning: Self-hosted first, cloud available.**

The primary path is self-hosted — users deploy Naavik via Docker Compose or NixOS on their own infrastructure. This shapes the entire design: dark mode default, no SaaS bloat, no upsell pressure, data-dense developer-tool aesthetic. A managed cloud tier ($15/month, bring-your-own AI credits) exists but is never treated as "premium." Both paths are first-class.

**Audience:** Tech-savvy professionals — engineers, PMs, designers — who value control over their data.

**Reference products:** Linear, Cursor, Plausible Analytics, Vercel/v0

**Vibe adjectives:** confident, calm, data-dense, tech-savvy, AI-native, editorial, direct

**Avoid:** loud, sterile, corporate, cute, decorative, AI-gimmicky

---

## Color Tokens

Dark mode is the **primary** experience. Light mode is Phase 6.

### Neutrals (Slate)

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `bg-base` | `#020617` | `slate-950` | Page background |
| `bg-surface` | `#0F172A` | `slate-900` | Cards, panels, sidebar |
| `bg-elevated` | `#1E293B` | `slate-800` | Hover, active surfaces, modals |
| `border-subtle` | `#1E293B` | `slate-800` | Card borders |
| `border-strong` | `#334155` | `slate-700` | Input borders, dividers |
| `fg-primary` | `#F8FAFC` | `slate-50` | Headings, primary text |
| `fg-secondary` | `#CBD5E1` | `slate-300` | Body text |
| `fg-muted` | `#94A3B8` | `slate-400` | Captions, metadata, placeholders |
| `fg-disabled` | `#475569` | `slate-600` | Disabled state |

### Brand (Indigo)

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `brand-primary` | `#6366F1` | `indigo-500` | Primary buttons, active nav, CTAs |
| `brand-hover` | `#818CF8` | `indigo-400` | Hover state |
| `brand-subtle` | `rgba(99,102,241,0.1)` | `indigo-500/10` | Tinted backgrounds |
| `brand-ring` | `rgba(99,102,241,0.4)` | `indigo-500/40` | Focus rings |

### Accent (Cyan — AI only, used sparingly)

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `accent-primary` | `#22D3EE` | `cyan-400` | AI-generated content indicators |
| `accent-glow` | `rgba(34,211,238,0.2)` | `cyan-400/20` | Subtle glow on AI elements |

### Semantic

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `success` | `#10B981` | `emerald-500` | Applied, offer, positive |
| `warning` | `#F59E0B` | `amber-500` | Action needed, pending |
| `danger` | `#F43F5E` | `rose-500` | Rejected, errors, destructive |
| `info` | `#0EA5E9` | `sky-500` | Informational badges |

### Status Pipeline

| Status | Dot color |
|---|---|
| FOUND | `slate-500` |
| SCORED | `sky-500` |
| APPROVED | `indigo-500` |
| DOCS_GENERATED | `cyan-400` |
| APPLIED | `emerald-500` |
| INTERVIEWING | `amber-500` |
| OFFER | `emerald-400` + ring |
| REJECTED | `rose-500` |
| WITHDRAWN | `slate-600` |

---

## Typography

### Fonts

- **Sans (UI):** Inter — weights 400, 500, 600, 700
- **Mono (data):** JetBrains Mono — weights 400, 500

Load via Google Fonts:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### Scale

| Token | Size | Weight | Tracking | Use |
|---|---|---|---|---|
| Display | 36px | 700 | tight | Page hero (rare) |
| H1 | 30px | 700 | tight | Page title |
| H2 | 20px | 600 | normal | Section heading |
| H3 | 18px | 500 | normal | Card title |
| Body | 16px | 400 | relaxed | Paragraphs |
| Small | 14px | 400 | normal | Secondary info |
| Caption | 12px | 500 | uppercase, wide | Labels, metadata |
| Mono | 14px | 500 | normal | Scores, tags, IDs, dates |

**Numerals:** Always use `tabular-nums` for stat cards, scores, and dates.

---

## Spacing & Layout

- Page padding: `p-6 lg:p-8`
- Card padding: `p-5` (compact) or `p-6` (standard)
- Section gap: `space-y-6 lg:space-y-8`
- Component gap: `gap-2`
- Sidebar width: `w-64` (collapsed: `w-16`)
- Max content width: `max-w-7xl` (most pages), `max-w-3xl` (forms)

---

## Border Radius

| Token | Value | Use |
|---|---|---|
| Subtle | 4px | Tags, badges, small inputs |
| Standard | 8px | Buttons, cards, inputs |
| Prominent | 12px | Modals, large surfaces |
| Full | 9999px | Avatars, pill chips |

---

## Shadows

Dark mode shadows are subtle. Prefer borders + bg contrast over heavy shadows.

- Card resting: none
- Card hover: `shadow-lg shadow-indigo-500/5`
- Modal: `shadow-2xl shadow-black/40`
- Dropdown: `shadow-xl shadow-black/30`
- AI glow (intentional): `shadow-lg shadow-cyan-400/20`

---

## Iconography

**Lucide Icons exclusively** — stroke width 1.5. Reference: lucide.dev

| Concept | Icon name |
|---|---|
| Brand | `compass` |
| AI / generated | `sparkles` (cyan-400) |
| Quick action | `zap` |
| Dashboard | `layout-dashboard` |
| Profile | `user-round` |
| Jobs | `briefcase` |
| Resume | `file-text` |
| Settings | `settings` |
| Score | `gauge` |
| Search | `search` |
| Filter | `sliders-horizontal` |
| Add | `plus` |
| Edit | `pencil` |
| Delete | `trash-2` |
| Save | `check` |
| Cancel | `x` |
| Status: success | `check-circle-2` |
| Status: pending | `clock` |
| Status: rejected | `x-circle` |
| Upload | `upload-cloud` |
| Download | `download` |

---

## Components

### Button

All: `focus:outline-none focus:ring-2 focus:ring-indigo-500/40`

| Variant | Classes |
|---|---|
| Primary | `bg-indigo-500 hover:bg-indigo-400 text-white font-medium px-4 py-2 rounded-lg transition` |
| Secondary | `bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium px-4 py-2 rounded-lg border border-slate-700` |
| Ghost | `hover:bg-slate-800 text-slate-300 hover:text-slate-50 px-4 py-2 rounded-lg transition` |
| Danger | `bg-rose-500 hover:bg-rose-400 text-white font-medium px-4 py-2 rounded-lg transition` |
| Icon-only | `p-2 rounded-lg hover:bg-slate-800` |

### Card

```html
<div class="bg-slate-900 border border-slate-800 rounded-lg p-6">
  <!-- content -->
</div>
```

Hover: add `hover:border-slate-700 transition`

### Input

```html
<input class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2
              text-slate-100 placeholder-slate-500
              focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20
              transition" />
```

### Tag / Chip

```html
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded
             bg-slate-800 text-slate-300 text-xs font-mono">
  ai-ml
</span>
```

### Status Badge

Dot + label:
```html
<span class="inline-flex items-center gap-1.5 text-xs font-medium">
  <span class="h-2 w-2 rounded-full bg-emerald-500"></span>
  Applied
</span>
```

### Sidebar

- Width: 256px
- Background: slate-900
- Border right: slate-800
- Top: brand lockup (compass icon + "Naavik" in Inter 700)
- Nav items: icon (20px) + label, 12px vertical padding, 8px radius
- Active: bg indigo-500, text white
- Hover: bg slate-800
- Bottom: theme toggle + user avatar

---

## Voice & Tone

### Microcopy

- **Direct over cute.** "Generate resume" not "Let's craft your resume! ✨"
- **Honest about AI.** Label AI-generated content with cyan sparkle icon + "AI" tag.
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

- Hover: 150ms
- Modal entry: fade + scale 95→100%, 200ms
- Drawer/sidebar: slide, 250ms
- Skeleton: pulse, 1500ms
- AI generation: shimmer on affected area

Never animate decoratively.

---

## DaisyUI Theme

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

## File Map

| File | Purpose |
|---|---|
| `DESIGN.md` (this file) | Root-level quick reference for all agents |
| `docs/design/CLAUDE_DESIGN_PROMPT.md` | Screen descriptions for Claude Design prototype projects |
| `docs/design/CLAUDE_DESIGN_PROMPT.md` | Screen descriptions for prototype generation |
| `docs/design/SCREENS.md` | Full screen catalog with specs |
| `docs/design/WORKFLOW.md` | Design → implementation pipeline |
| `docs/design/mockups/` | Committed mockup PNGs |

---

## Version History

- **1.0** (2026-04-25): Initial design system. Indigo/cyan palette, slate neutrals, Inter + JetBrains Mono, Lucide icons.
