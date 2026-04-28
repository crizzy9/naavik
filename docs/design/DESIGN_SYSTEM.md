# Naavik Design System

> **Version:** 1.0
> **Last updated:** 2026-04-25
> **Stack:** Tailwind CSS + DaisyUI + HTMX (server-rendered Jinja2)

This is the canonical visual contract for Naavik. Every mockup and every implemented page must conform to it. When the system evolves, update this document **first**, then propagate changes.

---

## Brand Essence

**Naavik** (Hindi: नाविक, "Navigator") is a tool for people who want to navigate their career deliberately, not get tossed by the job market.

**Core positioning: Self-hosted first, cloud available.**

The primary path is **self-hosted** — users deploy Naavik via Docker Compose or NixOS on their own infrastructure. This shapes the entire design: dark mode default, no SaaS bloat, no upsell pressure, data-dense developer-tool aesthetic. The app feels like something you'd run in your homelab, not something you're renting from a startup.

A **managed cloud tier** ($15/month, bring-your-own AI credits) exists for convenience but is never treated as "premium." Both paths are first-class. The Settings page mentions cloud as an option, not a sales pitch.

The product feels like:

- **Linear** — opinionated, fast, keyboard-driven, no clutter
- **Cursor** — AI-native but the AI feels like a co-pilot, not a chatbot
- **Plausible** — pragmatic, data-dense, no dark patterns
- **Vercel/v0** — modern, refined, respects developer taste

### Adjectives (use these to evaluate any mockup)

| Yes | No |
|---|---|
| Confident | Loud |
| Calm | Sterile |
| Data-dense | Overwhelming |
| Tech-savvy | Corporate |
| AI-native | AI-gimmicky |
| Editorial | Decorative |
| Direct | Cute |
| Self-directed | Paternalistic |

---

## Color Tokens

Dark mode is the **primary** experience. Light mode is a polish-pass deliverable for Phase 6.

### Neutrals (Slate — slight blue tint, evokes deep water/night sky)

| Token | Tailwind | Hex | Use |
|---|---|---|---|
| `bg-base` | `slate-950` | `#020617` | Page background |
| `bg-surface` | `slate-900` | `#0F172A` | Cards, panels |
| `bg-elevated` | `slate-800` | `#1E293B` | Hover, active surfaces, modals |
| `border-subtle` | `slate-800` | `#1E293B` | Card borders |
| `border-strong` | `slate-700` | `#334155` | Input borders, dividers |
| `fg-primary` | `slate-50` | `#F8FAFC` | Headings, primary text |
| `fg-secondary` | `slate-300` | `#CBD5E1` | Body text |
| `fg-muted` | `slate-400` | `#94A3B8` | Captions, metadata, placeholders |
| `fg-disabled` | `slate-600` | `#475569` | Disabled state |

### Brand (Indigo — sophistication, AI, professional trust)

| Token | Tailwind | Hex | Use |
|---|---|---|---|
| `brand-primary` | `indigo-500` | `#6366F1` | Primary buttons, key CTAs, active nav |
| `brand-hover` | `indigo-400` | `#818CF8` | Hover state of primary |
| `brand-subtle` | `indigo-500/10` | `rgba(99,102,241,0.1)` | Tinted backgrounds |
| `brand-ring` | `indigo-500/40` | `rgba(99,102,241,0.4)` | Focus rings |

### Accent (Cyan — navigator, water, intelligence — used sparingly for AI features)

| Token | Tailwind | Hex | Use |
|---|---|---|---|
| `accent-primary` | `cyan-400` | `#22D3EE` | AI-generated content indicators, sparkle effects |
| `accent-glow` | `cyan-400/20` | `rgba(34,211,238,0.2)` | Subtle glow on AI elements |

### Semantic

| Token | Tailwind | Hex | Use |
|---|---|---|---|
| `success` | `emerald-500` | `#10B981` | Applied, offer received, positive scores |
| `warning` | `amber-500` | `#F59E0B` | Action needed, pending review |
| `danger` | `rose-500` | `#F43F5E` | Rejected, errors, destructive actions |
| `info` | `sky-500` | `#0EA5E9` | Informational badges, neutral status |

### DaisyUI Theme (drop-in)

```js
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

## Typography

### Fonts

- **Sans (UI)**: [Inter](https://rsms.me/inter/) — variable weight, optical sizing, ubiquitous
- **Mono (data)**: [JetBrains Mono](https://www.jetbrains.com/lp/mono/) — used for scores, tag chips, IDs, code, metrics

Load via Google Fonts in `base.html`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### Scale

| Token | Tailwind | Use |
|---|---|---|
| Display | `text-4xl font-bold tracking-tight` | Page hero (rare) |
| H1 | `text-3xl font-bold tracking-tight` | Page title |
| H2 | `text-xl font-semibold` | Section heading |
| H3 | `text-lg font-medium` | Card title, subsection |
| Body | `text-base leading-relaxed` | Paragraphs |
| Small | `text-sm text-slate-400` | Secondary info |
| Caption | `text-xs text-slate-500 uppercase tracking-wide` | Labels, metadata |
| Mono | `font-mono text-sm` | Scores, tags, IDs |

### Numerals

Always use **tabular-nums** for stat cards, scores, dates: `font-variant-numeric: tabular-nums;` (Tailwind `tabular-nums`).

---

## Spacing & Layout

Use Tailwind's default spacing scale. Anchor values:

- Page padding: `p-6 lg:p-8`
- Card padding: `p-5` (compact) or `p-6` (standard)
- Section gap: `space-y-6 lg:space-y-8`
- Component gap (buttons, chips): `gap-2`
- Sidebar width: `w-64` (collapsed: `w-16`)
- Max content width: `max-w-7xl` (most pages), `max-w-3xl` (forms, focused content)

---

## Border Radius

| Token | Tailwind | Use |
|---|---|---|
| Subtle | `rounded` (4px) | Tags, badges, small inputs |
| Standard | `rounded-lg` (8px) | Buttons, cards, inputs |
| Prominent | `rounded-xl` (12px) | Modals, large surfaces |
| Full | `rounded-full` | Avatar, pill chips |

---

## Shadows

Dark mode shadows are subtle. Prefer **borders + bg contrast** over heavy shadows.

| Use | Class |
|---|---|
| Card resting | (none — rely on bg + border) |
| Card hover | `shadow-lg shadow-indigo-500/5` |
| Modal | `shadow-2xl shadow-black/40` |
| Dropdown | `shadow-xl shadow-black/30` |
| AI glow (rare, intentional) | `shadow-lg shadow-cyan-400/20` |

---

## Iconography

**Lucide Icons** ([lucide.dev](https://lucide.dev)) — exclusively. Do not mix icon sets.

### Loading

CDN for prototyping:
```html
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<script>lucide.createIcons();</script>
```

Production: install `lucide-static` in build or copy SVG strings inline.

### Defaults

- Stroke width: **1.5** (slightly thinner than default 2)
- Sizes: `h-4 w-4` (inline), `h-5 w-5` (button), `h-6 w-6` (nav), `h-8 w-8` (feature)
- Color: inherit `currentColor` — control with text classes

### Icon Vocabulary

| Concept | Lucide name |
|---|---|
| Brand mark | `compass` (stylized in logo lockup) |
| AI / generated content | `sparkles` |
| Quick action | `zap` |
| Navigation: Dashboard | `layout-dashboard` |
| Navigation: Profile | `user-round` |
| Navigation: Jobs | `briefcase` |
| Navigation: Resume | `file-text` |
| Navigation: Inbox | `inbox` |
| Navigation: Contacts | `users-round` |
| Navigation: Analytics | `chart-line` |
| Navigation: Settings | `settings` |
| Search | `search` |
| Filter | `sliders-horizontal` |
| Add | `plus` |
| Edit | `pencil` |
| Delete | `trash-2` |
| Save | `check` |
| Cancel | `x` |
| Score / metric | `gauge` |
| Status: success | `check-circle-2` |
| Status: pending | `clock` |
| Status: rejected | `x-circle` |
| Upload | `upload-cloud` |
| Download | `download` |
| External link | `arrow-up-right` |
| Expand | `chevron-down` |
| Theme toggle | `moon` / `sun` |

---

## Components

All components live in `src/naavik/ui/templates/components/` as Jinja partials. Each component below maps to one partial file.

### `button.html`

| Variant | Classes |
|---|---|
| Primary | `bg-indigo-500 hover:bg-indigo-400 text-white font-medium px-4 py-2 rounded-lg transition` |
| Secondary | `bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium px-4 py-2 rounded-lg transition border border-slate-700` |
| Ghost | `hover:bg-slate-800 text-slate-300 hover:text-slate-50 px-4 py-2 rounded-lg transition` |
| Danger | `bg-rose-500 hover:bg-rose-400 text-white font-medium px-4 py-2 rounded-lg transition` |
| Icon-only | `p-2 rounded-lg hover:bg-slate-800` |

All buttons: `focus:outline-none focus:ring-2 focus:ring-indigo-500/40`.

### `card.html`

```html
<div class="bg-slate-900 border border-slate-800 rounded-lg p-6">
  <!-- content -->
</div>
```

Hover variant: add `hover:border-slate-700 transition`.

### `input.html`

```html
<input class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2
              text-slate-100 placeholder-slate-500
              focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20
              transition" />
```

### `tag.html` (chip)

```html
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded
             bg-slate-800 text-slate-300 text-xs font-mono">
  ai-ml
</span>
```

Removable variant: add `<button>` with `x` icon.

### `status_badge.html`

Dot + label pattern:

```html
<span class="inline-flex items-center gap-1.5 text-xs font-medium">
  <span class="h-2 w-2 rounded-full bg-emerald-500"></span>
  Applied
</span>
```

| Status | Dot color |
|---|---|
| FOUND | `bg-slate-500` |
| SCORED | `bg-sky-500` |
| APPROVED | `bg-indigo-500` |
| DOCS_GENERATED | `bg-cyan-400` |
| APPLIED | `bg-emerald-500` |
| INTERVIEWING | `bg-amber-500` |
| OFFER | `bg-emerald-400 ring-2 ring-emerald-400/30` (emphasized) |
| REJECTED | `bg-rose-500` |
| WITHDRAWN | `bg-slate-600` |

### `score_card.html`

Gauge-style score 0–100. AI-emphasized with subtle cyan glow when high.

### `stat_card.html`

```html
<div class="bg-slate-900 border border-slate-800 rounded-lg p-5">
  <div class="text-xs uppercase tracking-wide text-slate-400">Jobs Found</div>
  <div class="mt-2 text-3xl font-bold tabular-nums">142</div>
  <div class="mt-1 text-xs text-emerald-400">+12 this week</div>
</div>
```

### `bullet_editor.html`

Two-pane: oneline (left, char counter, line-fit indicator) + detailed (right, rich textarea). Tag chips below. See `SCREENS.md` for full spec.

### `sidebar.html`

Already exists in `base.html`. To extract into a partial during implementation.

---

## Voice & Tone

### Microcopy

- **Direct over cute.** "Generate resume" beats "Let's craft your resume! ✨"
- **Honest about AI.** When AI did something, say so: "AI extracted this from your PDF — review and edit". Use the cyan accent + sparkle icon for AI-generated content.
- **Quantify when possible.** "12 jobs found this week" > "Several new jobs"
- **Acknowledge the human.** "You've applied to 47 jobs this month." (second person, factual)

### Empty states

Three parts: icon, one-line description, primary CTA.
- ❌ "Nothing here yet."
- ✅ "No jobs scored yet. Run a scrape to find matches → [Find jobs]"

### Error states

Three parts: what went wrong, why (if known), what to do.
- ❌ "Error 500"
- ✅ "Couldn't reach Claude API. Check your API key in Settings → [Open settings]"

---

## Motion

Subtle, purposeful, fast. **150–200ms** for most transitions.

- Hover: `transition` (default 150ms)
- Modal entry: fade + scale 95→100, 200ms
- Drawer/sidebar: slide, 250ms
- Skeleton loaders: pulse, 1500ms (Tailwind `animate-pulse`)
- AI generation: shimmer effect on the affected area (optional)

Never animate decoratively. Every animation must communicate state change.

---

## Accessibility

- Color contrast: meet WCAG AA in dark mode (most slate/indigo combinations pass; verify with [contrast-ratio.com](https://contrast-ratio.com))
- Focus rings: always visible, indigo-tinted
- Keyboard navigation: all interactive elements reachable via Tab
- ARIA labels on icon-only buttons
- Form labels: never rely on placeholder alone
- HTMX swaps: announce live regions for screen readers (`aria-live="polite"` on dynamic content)

---

## Anti-patterns

| Don't | Why |
|---|---|
| Use emoji for status indicators | Inconsistent across platforms; use Lucide |
| Mix icon stroke widths | Visual noise |
| Use shadows for hierarchy in dark mode | Use bg/border contrast instead |
| Use full-saturation colors for large surfaces | Muted/tinted backgrounds only; saturation reserved for accents |
| Animate everything | Distraction tax |
| Chatbot-style AI UI | We're a tool, not an assistant — show structured AI output, not transcripts |

---

## Versioning

When tokens change, bump the version at the top and add a changelog entry below.

### Changelog

- **1.0** (2026-04-25): Initial design system. Indigo/cyan palette, slate neutrals, Inter + JetBrains Mono, Lucide icons.
