---
description: Quick-reference for DESIGN.md tokens — color palette, typography, iconography, spacing, voice rules. Designer's first lookup before any visual decision; engineer's lookup when mapping mockup to Tailwind classes. Use before mockup generation, before implementing a screen, before reviewing any UI diff for token violations, before voice/microcopy decisions. Triggers on phrases like "design tokens", "color palette", "what's the brand color", "voice", "tailwind classes", "lucide icon", "typography", "what tokens", "design system".
---

# designer-design-tokens

`DESIGN.md` (root) is the frozen visual contract. This skill is the condensed lookup so you don't re-load the full 450-line file every time. For deep cuts (component-specific classes, motion specs), Read `DESIGN.md` directly — this is the cheat sheet, not the contract.

## When to invoke

- Before any mockup generation (the visual contract is the foundation).
- Before implementing a page / partial in `src/ui/templates/`.
- Reviewing a UI diff for token violations (arbitrary hex / wrong stroke / wrong font).
- Voice / microcopy decision (developer tool, NOT SaaS).
- Engineer mapping a mockup to Tailwind classes and needing the canonical token names.

## Color tokens (dark mode primary; light mode = Phase 6)

### Neutrals (Slate)

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `bg-base` | `#020617` | `slate-950` | Page background, `<body>` |
| `bg-surface` | `#0F172A` | `slate-900` | Cards, panels, sidebar |
| `bg-elevated` | `#1E293B` | `slate-800` | Hover, modals, dropdowns |
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
| `brand-subtle` | rgba(99,102,241,0.1) | `indigo-500/10` | Tinted backgrounds |
| `brand-ring` | rgba(99,102,241,0.4) | `indigo-500/40` | Focus rings |

### Accent (Cyan — AI ONLY, used sparingly)

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `accent-primary` | `#22D3EE` | `cyan-400` | AI-generated content indicators |
| `accent-glow` | rgba(34,211,238,0.2) | `cyan-400/20` | Subtle glow on AI elements |

**Important:** sparkle / AI tint reserved for AI-generated *content* (cover letters, screener answers, recommended moves). **Never** on tag chips, status badges, or metadata.

### Semantic

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `success` | `#10B981` | `emerald-500` | Applied, offer, positive |
| `warning` | `#F59E0B` | `amber-500` | Action needed, pending |
| `danger` | `#F43F5E` | `rose-500` | Rejected, errors, destructive |
| `info` | `#0EA5E9` | `sky-500` | Informational badges |

### Status pipeline (6 stages, 5 visible)

| Status | Dot color | Meaning |
|---|---|---|
| `DRAFT` | `bg-slate-500` | Pre-submission (hidden by default in Tracking) |
| `APPLIED` | `bg-indigo-500` | Submitted |
| `RECRUITER_SCREEN` | `bg-cyan-500` | Recruiter conversation |
| `ONSITE_LOOP` | `bg-amber-500` | Interview loop |
| `OFFER` | `bg-emerald-500` | Offer extended |
| `CLOSED` | `bg-rose-500` | Rejected / withdrawn / ghosted |

## Typography

- **Sans (UI):** Inter — weights 400, 500, 600, 700
- **Mono (data):** JetBrains Mono — weights 400, 500
- **Numerals:** always `tabular-nums` for stat cards, scores, dates

| Token | Size | Weight | Use |
|---|---|---|---|
| Display | 36px | 700 | Page hero (rare) |
| H1 | 30px | 700 | Page title |
| H2 | 20px | 600 | Section heading |
| H3 | 18px | 500 | Card title |
| Body | 16px | 400 | Paragraphs |
| Small | 14px | 400 | Secondary info |
| Caption | 12px | 500 | Labels, metadata (uppercase, wide) |
| Mono | 14px | 500 | Scores, tags, IDs, dates |

## Iconography

- **Lucide ONLY.** Stroke width **1.5**. Reference: lucide.dev.
- Pattern: `<i data-lucide="<name>"></i>` + `lucide.createIcons()` post-`htmx:afterSwap`.

Common icons:

| Concept | Icon |
|---|---|
| Brand | `compass` |
| AI / generated | `sparkles` (cyan-400) |
| Quick action | `zap` |
| Overview | `layout-dashboard` |
| Profile | `user-round` |
| Discover | `briefcase` |
| Tracking | `inbox` |
| Outreach | `send` |
| Settings | `settings` |
| Score | `gauge` |
| Search | `search` |
| Filter | `sliders-horizontal` |
| Add | `plus` |
| Edit | `pencil` |
| Delete | `trash-2` |
| Save | `check` |
| Cancel | `x` |
| Success | `check-circle-2` |
| Pending | `clock` |
| Rejected | `x-circle` |
| Upload | `upload-cloud` |
| Download | `download` |

## Spacing + layout

- Page padding: `p-6 lg:p-8`
- Card padding: `p-5` (compact) or `p-6` (standard)
- Section gap: `space-y-6 lg:space-y-8`
- Component gap: `gap-2`
- Sidebar: `w-64` desktop, `w-16` collapsed
- Max content: `max-w-7xl` (pages), `max-w-3xl` (forms)

## Border radius

| Token | Value | Use |
|---|---|---|
| Subtle | 4px | Tags, badges |
| Standard | 8px | Buttons, cards, inputs |
| Prominent | 12px | Modals |
| Full | 9999px | Avatars, pill chips |

## Tag vocabulary (9, fixed — DO NOT invent additional)

`ai-ml` · `backend` · `frontend` · `devops` · `data-eng` · `genai` · `leadership` · `platform` · `product`

## Voice & tone

- **Direct over cute.** "Generate resume" not "Let's craft your resume!"
- **Honest about AI.** Label AI-generated content with cyan sparkle + "AI" tag.
- **Quantify.** "12 jobs found this week" not "Several new jobs"
- **Second person, factual.** "You've applied to 47 jobs this month."
- **Empty states** — three parts: icon + one-line description + primary CTA.
- **Error states** — three parts: what went wrong, why, what to do.

## Voice anti-patterns (do NOT use)

- "Upgrade to Pro" / "Premium" / "Pro tip" — Naavik has no premium tier. Cloud is $15/mo, never an upsell.
- "Let's craft / let's create" — cute SaaS-flavored phrasing.
- Decorative emojis / sparkle on metadata (sparkle ONLY on AI content).
- "Discover your dream job" — flowery copy. The tool finds jobs; the user picks.
- Vague counts ("several", "many"). Always quantify.

## Motion

- Hover: 150ms
- Modal entry: fade + scale 95→100%, 200ms
- Drawer/sidebar: slide, 250ms
- Skeleton: pulse, 1500ms
- AI generation: shimmer on affected area

**Never animate decoratively.**

## Canonical references

- `DESIGN.md` (root) — full visual contract.
- `docs/design/COMPONENTS.md` — 85-partial catalog using these tokens.
- `docs/design/WORKFLOW.md` — read-order + skill routing.
- `docs/design/INTERACTIONS.md` — HTMX motion specs.

## When NOT to invoke

- Token already loaded in this turn (you Read DESIGN.md or invoked this skill).
- Pure backend / data work, no UI surface.
- Compaction events.

## Forbidden during invocation

- Do NOT introduce arbitrary hex values (`[#abc123]`). Use the token's Tailwind class.
- Do NOT change Lucide stroke width — it's 1.5, frozen.
- Do NOT introduce a third font or icon set.
- Do NOT use light-mode tokens in Phase 1–5 code (Phase 6 unlocks light mode).
- Do NOT invent a tag outside the 9-tag vocabulary.
- Do NOT put a sparkle icon on a tag chip / status badge / metadata element.
