# Naavik Design System

> **Version:** 1.3
> **Last updated:** 2026-04-30
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

Six stages. The visible pipeline is five (`APPLIED` through `CLOSED`); `DRAFT` and `CLOSED` are hidden by default in Tracking. Closed states (rejected, withdrawn, ghosted) collapse into one bucket via `closed_reason`.

| Status | Dot color | Meaning |
|---|---|---|
| `DRAFT` | `bg-slate-500` | Pre-submission — bundle generated, edits in flight. Hidden in Tracking by default; lives in Discover · review & apply or the Auto-apply queue. |
| `APPLIED` | `bg-indigo-500` | Submitted; awaiting recruiter response |
| `RECRUITER_SCREEN` | `bg-cyan-500` | Recruiter-side conversation underway |
| `ONSITE_LOOP` | `bg-amber-500` | In onsite / interview loop |
| `OFFER` | `bg-emerald-500` | Offer extended (verbal, written, or accepted) |
| `CLOSED` | `bg-rose-500` | Rejected, withdrawn, or ghosted (sub-reason in `closed_reason`) |

Pre-application discovery (find → score → swipe) lives in `/discover`, **not** Tracking. The Job's pre-application queue lifecycle (`unswiped · saved · skipped · queued_for_auto_apply · applied`) is a separate axis on the Job model. The Application row exists from the moment a bundle is generated (auto-apply queue or manual review entry) — `DRAFT` is its initial status; `APPLIED` is set on successful ATS submit.

The five visible stages (`APPLIED` → `CLOSED`) are the **post-submission** pipeline. `DRAFT` is the pre-submission bucket. Document generation, referral status, recruiter engagement, and outreach engagement are tracked as **orthogonal sub-states** on the Application model — not as additional pipeline stages. A single application can be `RECRUITER_SCREEN` + `referral_state=provided` + `docs_state=ready` simultaneously. See `docs/design/DATA_MODEL.md` (graduated from plan 05) for the full multi-axis state model. The flat `FOUND · SCORED · APPROVED · DOCS_GENERATED · INTERVIEWING · REJECTED · WITHDRAWN` enumeration is **not** in the model — those concerns live on dedicated axes (queue_state, docs_state, recruiter_state, closed_reason).

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

**No AI sparkle icon on tag chips.** Sparkles are reserved for AI-generated *content* (cover-letter paragraphs, drafted screener answers, recommended next moves). Tags are metadata; they ship with no decoration beyond the chip itself.

**Selected vs. unselected variant** (used in tag pickers — see Bullet editor modal):
- Selected: `bg-indigo-500/15 text-indigo-200 ring-1 ring-indigo-500/40`
- Unselected: `bg-slate-800 text-slate-300` (the default above)
- Hover: `hover:bg-slate-700 transition`

#### Tag vocabulary

Naavik uses a fixed 9-tag vocabulary. Tags are auto-generated by the LLM during resume parse and on every new bullet/role added; the user can edit them. **Do not invent additional tags.**

`ai-ml` · `backend` · `frontend` · `devops` · `data-eng` · `genai` · `leadership` · `platform` · `product`

### Status Badge

Dot + label:
```html
<span class="inline-flex items-center gap-1.5 text-xs font-medium">
  <span class="h-2 w-2 rounded-full bg-emerald-500"></span>
  Applied
</span>
```

### Sidebar

- Width: 256px on desktop, drawer on mobile
- Background: `bg-slate-900`
- Border right: `border-slate-800`
- Top: brand lockup (compass icon + "Naavik" wordmark in Inter 700)
- Nav items: Lucide icon (20px, stroke 1.5) + label, 12px vertical padding, 8px radius
- Active: `bg-indigo-500 text-white`
- Hover: `bg-slate-800`
- Right-side count badge per item (e.g. Jobs · `47`): `bg-slate-700 text-slate-300 font-mono text-[10px] px-1.5 py-0.5 rounded`
- Bottom: user avatar + name + deployment badge (`self-hosted` emerald-tinted, or `cloud` indigo-tinted). **No theme toggle** — single dark mode in v1.

### Status dot

Used in pipeline strips, status pills, and Kanban column headers.

```html
<span class="inline-block h-2 w-2 rounded-full bg-indigo-500"></span>
```

Color map: see § Color Tokens > Status Pipeline.

Pair with a label:

```html
<span class="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide">
  <span class="h-2 w-2 rounded-full bg-indigo-500"></span>
  Applied
</span>
```

### Score circle

Used on Discover cards, Discover · review, Tracking cards, email signal rows.

- 0–100 number centered in a colored ring. **No `%` mark. No "match" word.**
- Sizes: 40px (compact / inline), 64px (default / cards), 96px (hero / detail screens)
- Ring: 2px stroke, color thresholded by score:
  - `≥ 80` — `stroke-emerald-400` (green)
  - `60–79` — `stroke-indigo-400`
  - `40–59` — `stroke-amber-400`
  - `< 40`  — `stroke-rose-400`
- Background fill: same color at `/10` opacity
- Number: `font-mono font-semibold tabular-nums`, size scales with container

Implementation: SVG with `stroke-dasharray` for the ring fraction, absolute-positioned `<span>` for the number.

Per-dimension match bars (e.g. `ai-ml 0.95`) reuse the same color thresholding, rendered as horizontal bars. They appear adjacent to the score circle in match-breakdown panels.

### KPI card

Used on Overview. Compact, dense, surfaces one number plus a delta.

```html
<div class="bg-slate-900 border border-slate-800 rounded-lg p-5">
  <div class="text-xs uppercase tracking-wide text-slate-400 font-medium">RESPONSE RATE · 90D</div>
  <div class="mt-2 flex items-baseline gap-2">
    <span class="font-sans text-3xl font-semibold tabular-nums text-slate-50">11.3%</span>
    <span class="font-mono text-xs text-emerald-400">+2.1%</span>
  </div>
  <div class="mt-1 text-xs text-slate-400">3× market avg</div>
</div>
```

Delta colors: positive `text-emerald-400`, negative `text-rose-400`, neutral subtitle `text-slate-400`.

### AI badge

Used to label AI-generated content: cover-letter paragraphs, drafted screener answers, recommended outreach moves, extracted profile fields, model attribution chips.

```html
<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded
             bg-cyan-400/10 text-cyan-300 text-[11px] font-mono uppercase tracking-wide">
  <svg class="h-3 w-3" ...><!-- Lucide sparkles --></svg>
  AI
</span>
```

Variants:
- `AI · enthusiastic` — appends a tone qualifier (mono, lowercase)
- `AI · claude-3.5-sonnet` — model attribution chip
- `AI draft` — pre-content card label (outreach, screener answers)

**Never** put the AI sparkle on a tag chip, status badge, or any metadata element. Sparkles are reserved for AI-generated *content*.

### Followup banner

Used on Tracking, and compactly on Outreach, to surface stalled threads.

```html
<div class="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
  <div class="flex items-center justify-between mb-3">
    <div class="text-xs uppercase tracking-wide text-amber-300 font-medium">
      <span class="inline-block h-2 w-2 rounded-full bg-amber-400 mr-1"></span>
      NEEDS FOLLOWUP · 4
    </div>
    <a class="text-xs text-amber-200 hover:text-amber-100">open in outreach →</a>
  </div>
  <!-- per-row cards: avatar + name + company + state + "Draft reply" CTA -->
</div>
```

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
- **Tags (vocabulary):** see § Components > Tag / Chip > Tag vocabulary
- **Sample bullet (long form — AI trims to fit at apply time):** "Built and shipped Intuit's ML personalization platform from prototype to production, serving 100M+ users across QuickBooks and TurboTax surfaces. Owned the full stack — feature pipelines in Airflow, ranking models in PyTorch, online inference in Go. Lifted homepage CTR by 23% and recovered an estimated $4.2M in annual revenue based on lift-tested A/B reads."

---

## File Map

DESIGN.md is the **visual contract** only — tokens, typography, components, motion, voice. Process artifacts (plans, prompts, agent guides) and other design contracts (screens, routes, data model, interactions) live elsewhere.

For directory layout and where everything lives, see `AGENTS.md` § Documentation locations. For the lifecycle that produces design contracts and feeds them into implementation, see `AGENTS.md` § Workflow.

The other always-present design docs to know about:

- `docs/design/SCREENS.md` — screen catalog
- `docs/design/WORKFLOW.md` — UI sub-process pipeline
- `docs/design/mockups/` — visual reference (gitignored, locally only)

Other docs in `docs/design/` (COMPONENTS.md, ROUTES.md, DATA_MODEL.md, INTERACTIONS.md, SAMPLE_DATA.md) graduate from approved plans in `docs/plans/`. List the directory when you need to see what's currently there.

---

## Version History

- **1.3** (2026-04-30): `DRAFT` added as a sixth status (hidden in Tracking by default) so the pre-submission bundle has a persistent home — auto-apply pipeline pre-submit + manual review-and-apply pre-submit. APPLIED+ remain post-submission. Cascaded to DATA_MODEL.md, BACKEND.md, SAMPLE_DATA.md, INTERACTIONS.md, SCREENS.md.
- **1.2** (2026-04-30): Status pipeline clarified as multi-axis: 5-stage `Application.status` is post-submission only; document generation / referral / recruiter engagement / outreach engagement live on orthogonal sub-states. Standalone `/generate/cover-letter` and `/generate/resume` routes removed (folded into Discover · review & apply). MVP screen count: 12 → 11. Prompts moved to `docs/prompts/`. New design docs queued via plans 03–07.
- **1.1** (2026-04-29): Aligned to MVP-screens mockups. New 5-stage pipeline (`APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED`). Tag vocabulary fixed at 9 (added `product`). Added components: `score_circle`, `status_dot`, `kpi_card`, `ai_badge`, `followup_banner`. Tag chips clarified as no-sparkle. Sidebar bottom: deployment badge instead of theme toggle.
- **1.0** (2026-04-25): Initial design system. Indigo/cyan palette, slate neutrals, Inter + JetBrains Mono, Lucide icons.
