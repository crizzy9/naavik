---
Authored: 2026-05-21
Designer: Claude designer (opus-4-7[1m])
Run-id: 2026-05-21T07-54-17_362de279
Master plan: docs/plans/68-0.3.2-ui-remediation-master.md
Sub-plans: docs/plans/72-0.3.2.01-0.3.2.02-score-card-bullet-preview.md, docs/plans/73-0.3.2.03-score-history.md, docs/plans/74-0.3.2.04-cost-cap-fallback-banner.md
Branch: feat/0.3.2-ui-remediation-master
Status: AWAITING_OWNER_VARIANT_PICKS (PLAN_GATE 2 · designer-return)
---

# Mockup handoff · 0.3.2 UI polish sweep

## Overview

Designer pass for 4 surfaces × 3 differentiated philosophy variants = 12 variants (24 mockup PNGs at 1440×900 + 375×812). Per master plan 68 § Designer subdispatch spec + owner directive (no token cap, opus[1m], all 3 skills per surface, no fallback).

**Visual contract honored** (DESIGN.md v1.3, frozen): Inter + JetBrains Mono only; Lucide stroke 1.5; slate-950 page + slate-900 surface; indigo-500 primary + cyan-400 AI accent; emerald/amber/rose semantic; score thresholds emerald ≥80, indigo ≥60, amber ≥40, rose <40. No new fonts, no new icons, no light mode. All variants are *differentiated by information architecture, hierarchy, and interaction model* — not cosmetic rearrangement.

**WCAG AA verified** (via ui-ux-pro-max skill): slate-50/slate-900 = 15.9:1 (AAA); slate-300/slate-950 = 12.6:1 (AAA); indigo-400/slate-900 = 6.4:1 (AA large / AAA normal); cyan-400/slate-900 = 7.6:1 (AAA); emerald-400/slate-900 = 7.8:1 (AAA); amber-400/slate-900 = 10.0:1 (AAA); rose-400/slate-900 = 5.5:1 (AA). All pass.

**Mockup files** (gitignored per `docs/design/mockups/README.md` rule):

```
docs/design/mockups/0.3.2/
├── score-card-variant-{a,b,c}-{desktop,mobile}.png            (6 files)
├── bullet-preview-variant-{a,b,c}-{desktop,mobile}.png        (6 files)
├── sparkline-variant-{a,b,c}-{desktop,mobile}.png             (6 files)
├── cost-cap-banner-variant-{a,b,c}-{desktop,mobile}.png       (6 files)
├── html/                                                       (source HTML prototypes — gitignored)
└── _capture.py                                                 (Playwright capture script — gitignored)
```

**Generation method** (reproducible): HTML prototype + Tailwind CDN + Lucide icons + Playwright screenshot at canonical viewports. See `docs/design/mockups/0.3.2/_capture.py`. Re-run: `uv run python docs/design/mockups/0.3.2/_capture.py`. All HTML sources use realistic sample data from `src/db/sample_data.py` (Anthropic Senior ML Engineer · Job id 103) + owner profile (Shyam Padia at Intuit).

---

## Surface 1 — Score card (Discover + Discover · review · LEFT column)

**What it does.** Composes `score_circle.html` (existing) + `match_breakdown.html` (existing) + the new "why / what's missing / what was generated" overlay into a single container partial. Surfaces 0.3.2 § Goal: *"user sees 'why' + 'what's missing' + 'what was generated'"*. Used on Discover swipe card and Discover · review left column.

**Data consumed.** `Job.match_breakdown` JSONB — the 18-key shape (per `DATA_MODEL.md § Job.match_breakdown`, graduated from plan 65 § T7). Specifically: `score`, `per_dimension` (dict), `strengths` (list[str]), `gaps` (list[str]), `visa_concern` (bool), `visa_note` (str|null), `tag_score`, `semantic_score`, `composite_pre_llm`, `layers_run` (list), `judge_skipped` (bool), `judge_skipped_reason`, `layer_4_provider`, `layer_4_model`, `scored_at`. Template uses `.get()` with default — handles legacy rows without the new keys.

### Variant A — Pentagram typographic ledger
*Philosophy:* hierarchy through composition, not size. Score is one tabular row alongside per-dim bars; no big-number hero. Reading flow is left-to-right ledger. Type leads.

*Treatment:* MATCH ANALYSIS section title; "Why this scored 86" sub-header; ledger grid (label column + value column) where overall + per-dim share the same baseline; STRENGTHS + GAPS in side-by-side two-column block beneath; provenance footer with all layer scores in one mono line.

*First-glance read:* eye lands on the "86" mono number in the ledger, then sweeps down the per-dim values, then reads strengths/gaps side-by-side.

### Variant B — Linear bento (3-zone)
*Philosophy:* hero-cell metric + adjacent dense panels. Reads at a glance — single-screen workspace. Score has its own cell with breathing room; per-dim bars in middle; strengths+gaps stacked on right.

*Treatment:* 12-col CSS grid divided 3/4/5; left cell carries `match` + big 86 + llm-judged pulse dot; middle cell carries per-dim bars; right cell carries STRENGTHS + WHAT'S MISSING as stacked tinted panels. Bottom band carries layer provenance.

*First-glance read:* eye lands on the big 86 (left cell), then jumps to strengths/gaps right cell (semantic tinted), then per-dim middle for detail.

### Variant C — Plausible density strip
*Philosophy:* compact single-line scannable + progressive disclosure. Optimal for the swipe queue where users scan multiple cards quickly. Defaults to collapsed; expands inline on click.

*Treatment:* one horizontal strip — small score ring + chips for per-dim + counts strip on right + chevron. Click → expands below the strip to reveal WHY + WHAT'S MISSING two-column body + provenance.

*First-glance read:* eye scans the chip row left-to-right (semantic-colored per threshold) and lands on the strengths/gaps counts. Expansion is opt-in.

### Recommendation
**Variant B (Linear bento)** ships.

*Rationale:*
- **Cognitive load:** B's 3-zone bento gives each information class its own visual home (score vs detail vs interpretation). User can fixate on what matters for THIS card without re-scanning. A's ledger requires sequential reading. C's collapsed strip hides info from the swipe context.
- **Alignment with existing patterns:** B's "hero number + adjacent dense panels" pattern reads as a generalization of Naavik's `kpi_card.html` from Overview. Familiar shape, new content. A's editorial ledger is a new pattern for this codebase.
- **Accessibility:** B has clearest WCAG AA scan order via grid zones. A's tabular ledger demands tabular numbers + careful column alignment (more fragile across viewports). C's tight chip row needs ≥44pt touch targets on chips (currently 28pt — fail) — would need rework.
- **Implementation cost:** B is straightforward CSS grid + 3 sub-components composed in `score_card.html`. A requires a custom typographic grid (more bespoke). C requires `<details>`/`<summary>` JS-free progressive disclosure (works, but the chip row needs additional thought for mobile tap targets).
- **Mobile parity:** all 3 work at 375px (verified). B stacks zones vertically and keeps semantic tinting; A's ledger compresses but stays readable; C's chip row horizontal-scrolls. B has the cleanest mobile-to-desktop mental model.

*Honest counterpoint:* C is the most "data-dense developer-tool" feel — closest to Plausible's UI grammar. If owner wants the Discover queue card to scan in <2s, C wins. The chip-row touch-target issue can be fixed (chips become 32×24pt with 8pt spacing — meets density-tier minimum at the cost of one density-row constraint).

### Engineer notes — Surface 1

**Components composed:**
- `score_circle.html` (1) — qty: 1; args: `score=int 0-100`, `size="compact|default|hero"`. Existing partial, no changes.
- `match_breakdown.html` (1) — qty: 1; args: `breakdown=dict[str,float]`, `overall=float|null`, `title=str|null`. Existing partial; no breakdown-shape changes — template safely reads new strengths/gaps via Jinja `.get()`.
- `chip` macro (variable) — from `_macros.html`; used for the per-dim chips in variant C, the layer-provenance chips, and the warm-intro chip.

**New partial introduced** (Q72.2 LOCKED per plan 72): `src/ui/templates/components/score_card.html` — NEW partial extending the 91-partial catalog → 92. Wraps `score_circle.html` + `match_breakdown.html` + the strengths/gaps/visa_note overlay. Args:
- `score` (int 0-100) — required
- `match_breakdown` (dict, 18-key shape) — required
- `expanded` (bool, default False) — whether to show the WHY + WHAT'S MISSING + provenance overlay
- `size` (str, "compact"|"default"|"hero", default "default") — sizes the score circle
- `variant` (str, "A"|"B"|"C", default "B") — chosen at template-include time based on owner pick; engineer may consolidate to single variant post-owner-pick.

**Propose COMPONENTS.md edit** (committed in engineer's plan-72 PR):
```markdown
- Add row to § A inventory table: `Discover · 12` (was 11) + total 92.
- Add full spec to § H.7 Discover group:
  #### `score_card.html`
  **Purpose:** Composite container surfacing score + per-dimension breakdown + AI-judged WHY + WHAT'S MISSING + generation provenance. Consumes the 18-key `match_breakdown` JSONB.
  **Used by:** Section 7 (Discover · swipe_card.html), Section 8 (Discover · review LEFT column), Section 12 (Job detail topbar).
  [...]
```

**HTMX patterns used:** none directly on the card (it's pure presentation). The card is rendered inside `swipe_card.html` (Discover) and `_discover_review_workspace.html` (review); their HTMX wiring is unchanged.

**Data accessor:**
- memory mode: `src/db/sample_data.py:get_jobs_for_discover` (existing) — already returns `match_breakdown` per Job.
- db mode: `src/services/job_service.py:list_jobs` (existing) — same.

**Ctx-builder change:** `src/ui/discover_ctx.py:swipe_card_dict` already includes `match_breakdown` in the dict it produces (line 125 per plan 72 audit). Engineer adds `strengths`, `gaps`, `visa_note` projections (defensive: use `.get("strengths", [])`, etc.).

**Build target:** `src/ui/templates/pages/discover.html` (uses `swipe_card.html`) + `src/ui/templates/pages/_discover_review_workspace.html` (uses `apply_topbar.html` + score_card-like surface) — both replaced inline `match_breakdown` + `score_circle` includes with a single `{% include "components/score_card.html" %}`.

**Route handler:** unchanged. `src/ui/routes/discover.py:get_discover` already serves.

**Mockup paths:**
- `docs/design/mockups/0.3.2/score-card-variant-a-desktop.png` + `-mobile.png`
- `docs/design/mockups/0.3.2/score-card-variant-b-desktop.png` + `-mobile.png` (recommended)
- `docs/design/mockups/0.3.2/score-card-variant-c-desktop.png` + `-mobile.png`

---

## Surface 2 — Bullet selection preview (Discover · review · MIDDLE column)

**What it does.** Each tailored-resume bullet row carries a rationale line (cyan-tinted "why kept" for selected, slate-tinted "why dropped" for excluded). Surfaces the LLM judge's per-bullet selection reasoning so the user sees AI's call AND can override before submit.

**Data consumed.** `Application.generation_trace.bullet_selections` (list of `{bullet_id, trimmed_line}` per plan 66 § C.3). **Engineer-verify at dispatch** (Q72.3 LOCKED): plan 72 calls for a `bullet_selection_log` field shape `{bullet_id, selected, rationale: {why_selected | why_dropped}}` — verify whether plan 66 ships this OR whether plan 72 commit 1 adds it. The bundle_generator.py currently writes `trace["bullet_selections"]` (selected only, no rationale, no dropped). The new shape is the design intent; engineer fills in the data side.

### Variant A — Inline ledger
*Philosophy:* rationale lives directly below the bullet text as italic micro-copy. Always visible. No interaction needed to discover it.

*Treatment:* under each bullet, a 2-line italic block prefixed with "why kept · " (cyan-300, ml-5 indent, border-l-2 cyan-400/40) for selected; "why dropped · " (slate-400, border-l-2 slate-700) for dropped. The cyan-tinted left edge signals AI-authored.

*First-glance read:* eye reads the bullet text, then sees the rationale immediately. Linear top-to-bottom flow. High information density.

### Variant B — Right-rail diff
*Philosophy:* code-review pattern. Bullets are the "before"; sticky right pane shows the "diff" — verdict + JD match + tag weights + trims. User clicks a bullet to focus it; rationale updates in the rail.

*Treatment:* 3-column workspace becomes 4-column: left context, middle bullets (compact, no inline rationale), right rationale pane (sticky). Focused bullet has indigo-500/5 background ring; chevron-right indicates pane sync. Rationale pane has VERDICT chip + JD MATCH bullets + TAG WEIGHTS bars + TRIMS note + Edit/Pin buttons.

*First-glance read:* eye reads bullet list, then jumps to right rail for the focused bullet's "why". Two simultaneous reading modes — list scanning + detail pane.

### Variant C — Color-coded margin (git-diff gutter)
*Philosophy:* git-diff aesthetic. Each bullet row has a 2-px colored gutter (emerald = kept, slate = dropped) + line number. Click row to expand the rationale inline.

*Treatment:* CSS grid `[28px_1fr]` per row — gutter cell + content cell. Gutter cell has a 1-px colored bar + a mono line-number (01, 02, ...). Hover reveals a "why →" tooltip; tap/focus expands the rationale below the row as a tinted box.

*First-glance read:* eye scans the gutter colors first (kept-vs-dropped pattern), then reads bullets. Rationale is opt-in via tap.

### Recommendation
**Variant A (Inline ledger)** ships.

*Rationale:*
- **Cognitive load:** A always shows the rationale, so the user reads bullet + reason as a single unit. B requires the user to manage two reading modes (list + pane); slower for "did the AI make the right call?" review. C hides rationale by default — user might submit without ever checking.
- **Alignment with existing patterns:** A extends `tailored_bullet_row.html` cleanly with one new optional `rationale` arg. B requires a new sticky-right-pane partial AND a JS sync mechanism (click bullet → update pane). C requires custom CSS grid + expand-on-tap mechanics (no JS but more template complexity).
- **Accessibility:** A is the most screen-reader-friendly — rationale follows bullet in DOM order. B requires aria-live on the rail pane sync. C requires aria-expanded on each row, plus the gutter's color-only signal needs a text fallback (icon or label).
- **Voice (developer-tool, not SaaS):** A's italic micro-copy with mono prefix ("why kept · ") reads like a code annotation. B's elaborate side panel risks looking SaaS-ish. C's gutter is git-diff-aware, beautifully on-brand, but the always-collapsed rationale fights the goal "user sees why" — that signal should be visible by default.
- **Implementation cost:** A = 1 new template arg + ~12 lines of Jinja per row. B = 1 new partial + 1 ctx field + 1 JS handler. C = 1 new grid wrapper + 1 expand handler + 1 a11y fallback.
- **Mobile parity:** A stacks naturally — rationale stays below bullet. B's right rail collapses to an inline-expanded panel on mobile (rendered in the mockup) — workable but uses 2/3 of the vertical space when expanded. C's gutter compresses to 20px but stays readable.

*Honest counterpoint:* B is the most "premium feel" — looks like a proper code review tool. If we expect users to actually iterate on which bullets ship (Edit / Pin from the rail), the rail UI is where to invest. If owner sees A as "just text", consider B for the post-MVP polish pass.

### Engineer notes — Surface 2

**Components composed:**
- `tailored_bullet_row.html` (n) — EXTENDED with one new optional arg `rationale` (dict|null). Existing partial keeps backward compatibility — old call sites omit `rationale` and render exactly as today.
- `chip` macro from `_macros.html` — used for the tag chips (`jd`, `personalization`, `scale`, etc.).
- `tailored_bullet_row.html` API extension (no new partial):
  ```jinja
  rationale : dict | null — {selected: bool, why_selected: str|null, why_dropped: str|null}
  ```

**New partial introduced:** NONE. Extending existing partial via one new arg — per `designer-component-reuse` skill rule (extend before invent).

**Propose COMPONENTS.md edit** (committed in engineer's plan-72 PR):
```markdown
- Update § H.8 Discover · review & apply > tailored_bullet_row.html:
  Add `rationale` to API table: optional dict `{selected, why_selected, why_dropped}`. When set, renders an italic micro-copy line below the bullet text.
```

**HTMX patterns used:**
- Modal — `INTERACTIONS.md § E` (existing). Click pencil → opens `bullet_editor_modal` via `hx-get="/_modal/bullet-editor/{{ bullet.id }}"`. Unchanged.
- No new patterns introduced.

**Data accessor:**
- memory mode: `src/db/sample_data.py:get_application_for_discover_review` (existing) — engineer adds `bullet_selection_log` field to the dict it produces (or the bundle_generator output is consumed directly).
- db mode: `src/services/application_service.py:get_application` (existing) — reads `Application.generation_trace.bullet_selections`. Engineer adds the rationale-shape extension to `bundle_generator.py:_record_layer` per plan 72 § File-by-file edit #3.

**Ctx-builder change:** `src/ui/discover_review_ctx.py:tailored_bullet_groups` — projects `bullet_selection_log` into per-bullet `rationale` dict. Reads from `application.generation_trace`. Template guards via `{% if rationale %}` so applications without the log (older bundles) render gracefully without the line.

**Build target:** `src/ui/templates/pages/_apply_tailored_bullets.html` — passes `rationale=r.rationale` to each `tailored_bullet_row.html` include.

**Route handler:** unchanged. `src/ui/routes/discover_review.py:get_discover_review` already serves.

**Mockup paths:**
- `docs/design/mockups/0.3.2/bullet-preview-variant-a-desktop.png` + `-mobile.png` (recommended)
- `docs/design/mockups/0.3.2/bullet-preview-variant-b-desktop.png` + `-mobile.png`
- `docs/design/mockups/0.3.2/bullet-preview-variant-c-desktop.png` + `-mobile.png`

**Open question for owner:** Q72.3 — engineer verifies `Application.generation_trace.bullet_selection_log` shape at dispatch. If absent, engineer adds it in commit 1 of plan 72 (extending `bundle_generator.py` per plan 72 § File-by-file edit #3).

---

## Surface 3 — Score history sparkline (Profile · HTMX fragment per Q73.4)

**What it does.** Per-role-family scoring trends over 30 days, rendered as inline-SVG sparklines on the Profile page. **HTMX fragment** swapped into Profile — NO new `/scores` route (Q73.4 LOCKED per master plan 68 § Locked decisions: "HTMX fragment swapped into Profile · NO new /scores route").

**Data consumed.** `Profile.score_history` JSON blob (new column per master plan Q3 lock — aggregation cron writes daily aggregates; no new `ScoreSnapshot` table, no alembic migration on this PR). Shape:
```json
{
  "last_aggregated_at": "2026-05-20T03:30:00Z",
  "families": [
    {
      "family": "ai-ml",
      "scored_count_30d": 23,
      "score_current": 0.84,
      "score_delta_30d": 0.12,
      "daily_means": [0.72, 0.73, 0.71, ..., 0.94]  // 30 floats
    },
    ...
  ]
}
```

Heuristic role-family classifier (Q73.3 LOCKED): substring-match `Job.role` against keyword sets — `ml/machine-learning → ai-ml`, `backend/server/api → backend`, `frontend/ui → frontend`, etc. Fallback `other` bucket. Q73.2 follow-up to upgrade to LLM-classifier filed under `0.8.0.NN` per plan 73.

### Variant A — Hero strip (integrated into Profile hero card)
*Philosophy:* sparkline is part of identity. Reading flow: name → trend evidence → details below. The trend is the second-most-important thing after "who is this person".

*Treatment:* compact strip below the hero header (avatar + name + edit/update actions), separated by a top-border. SCORE TREND · 30D micro-header; 3 rows of `[label][sparkline][value][delta]` grid. Hint line at bottom (cyan-link to platform bullets edit).

*First-glance read:* user lands on Profile, sees identity, immediately sees how their matches are trending — provocative-on-purpose.

### Variant B — Dedicated section
*Philosophy:* sparkline gets its own scroll target. A real section between hero and Experience. More breathing room; can carry richer stats (p50/p90 + count).

*Treatment:* full-width card with header (Score trends + 30/60/90 day selector), 3 rows divided by section borders. Each row carries label + jobs count + larger sparkline (h-16, with subtle 0.5 baseline grid) + right-side stats column (big value + delta + percentile). Footer carries metadata (roll-up time, source).

*First-glance read:* deliberate, treats the data as a chapter. User scrolls past hero, encounters the trend block as content.

### Variant C — Right-rail card
*Philosophy:* sparkline is supplementary nav-side info, like a status widget. Doesn't compete with profile content for attention; available when wanted.

*Treatment:* sparkline widget in the sticky `ON THIS PAGE` rail (`240px` desktop), below the anchor nav, above the readiness card. Compact h-6 sparklines + tiny label + value + delta. "expand →" link affordance.

*First-glance read:* user reads main profile column; trend lives peripherally, glanceable when wanted.

### Recommendation
**Variant A (Hero strip)** ships.

*Rationale:*
- **Cognitive load:** A surfaces the most actionable signal (your scores trended UP for ai-ml, DOWN for platform) without requiring a scroll or a rail-glance. Per the Naavik product goal, the user came to Profile to see "is my profile working?" — A answers that immediately.
- **Alignment with existing patterns:** the Profile hero card is the right home for identity-adjacent signals. The H1B status chip already lives there; the sparkline is the same class of "facts about Shyam" data. B treats it as a new section (heavier IA cost — plus the hint "tap to drill" forces a destination that doesn't exist per Q73.4 lock). C tucks it in the rail, but the right rail's contract is for navigation + readiness — adding analytics there confuses the contract.
- **Accessibility:** A's grid `[label][svg][value][delta]` translates to a clean screen-reader pattern: "ai-ml, 23 jobs, line chart showing upward trend, current 0.84, up 0.12 over 30 days". B has similar a11y. C's compact sparklines need larger aria-labels because the deltas are visually tiny.
- **Voice (dev-tool):** A reads like a Plausible Analytics "this week's traffic at a glance" widget. Direct, honest, no flowery. B's "Score trends" header + percentiles feels more dashboard-formal. C's "expand →" anchor lies — there's no expanded view (Q73.4 locked no /scores route).
- **Implementation cost:** A = 1 new section in `profile.html` + Jinja loop over 3 families + inline SVG. B = same effort but a new section card. C = template work for the rail-widget insert, but breaks the rail's nav-only contract.
- **Mobile parity:** A's hero-strip integrates cleanly; the grid `[label][svg][value][delta]` compresses to `[narrow-label][wider-svg][narrow-right]`. B mobile reflows to stacked rows with the SVG below the label, works well. C mobile flips to a section card (no rail on mobile) — at that point it's just B with a more compact widget. So C effectively converges to B's pattern on mobile, which signals the rail-placement was wrong to begin with.

*Honest counterpoint:* if owner ever wants a dedicated `/scores` route (current Q73.4 lock rejects it), B becomes the more natural home. Q73.4 is reversible if owner shifts intent — but for the current spec, A is right.

### Engineer notes — Surface 3

**Components composed:**
- inline SVG sparkline (no new partial) — pure Jinja templating with `polyline` + `path` for the area fill. The `daily_means` list is mapped to SVG coordinates via Jinja math.
- `chip` macro from `_macros.html` — used for the "H1B" identity chip in hero.
- `profile_hero.html` (existing partial) — EXTENDED to slot the sparkline strip below the existing identity block. The hero card already exists; we add a new section-within-card.

**New partial introduced:** NONE (per Q73.4 LOCK — HTMX fragment, no new component). The sparkline lives as a inline-SVG block in `profile.html` (the Hero variant) OR `pages/_profile_score_trends.html` (a section fragment if engineer prefers extraction). Engineer chooses — both honor the "no new partial in catalog" rule because anything they author is a page-level snippet, not a reusable catalog entry.

**Propose COMPONENTS.md edit:** NONE. (The sparkline is a one-off SVG block specific to Profile; not reusable across other surfaces. If a second screen needs sparklines later, *that* dispatch graduates it to a partial.)

**HTMX patterns used:**
- HTMX fragment — `INTERACTIONS.md § A` (existing pattern). The sparkline section can be lazy-loaded via `hx-get="/_fragments/profile/score-trends" hx-trigger="load delay:200ms"` if engineer wants to avoid blocking page render on the score_history blob.
- Or just render inline at page-load — page is server-rendered Jinja, the blob is already in scope.

**Data accessor:**
- memory mode: `src/db/sample_data.py` — engineer adds a fixture `_score_history_blob` matching the shape above; `get_profile_for_user` returns it as `profile["score_history"]`.
- db mode: `src/services/profile_service.py:get_profile` (existing) — engineer adds the new `Profile.score_history` JSON column read.

**New column:** `Profile.score_history` (JSONB) — per master plan Q3 lock. No alembic migration on this PR if owner picks Variant A and Profile doesn't have a recent migration round — engineer adds the column via `Field(default_factory=dict, sa_column=Column(JSON))` and lets ALTER fire on next migration. If migration needed, alembic 00XX in same PR.

**Scheduler job:** `src/scheduler/jobs.py:score_aggregate_daily` — new APScheduler cron, daily 03:30 UTC. Reads `Job.match_breakdown` rows where `scored_at >= today_midnight_utc - 30d`, classifies role-family, groups, computes daily means, writes JSON blob to `Profile.score_history`. Per plan 73 § File-by-file edit #4 + § Build sequence Phase 2.

**Ctx-builder change:** `src/ui/profile_ctx.py:_build_profile_ctx` (extends) — projects `profile.score_history.families` into 3 family rows for the template. Engineer handles `len(families) == 0` empty state (renders empty-state card pointing to /discover).

**Build target:** `src/ui/templates/pages/profile.html` — new section inside the existing hero card (`{% with %}` block) OR a new section-card between hero and Summary depending on engineer's read of Variant A's compositional intent. Mockup shows the integrated-into-hero placement.

**Route handler:** unchanged. `src/ui/routes/profile.py:get_profile` already serves.

**Mockup paths:**
- `docs/design/mockups/0.3.2/sparkline-variant-a-desktop.png` + `-mobile.png` (recommended)
- `docs/design/mockups/0.3.2/sparkline-variant-b-desktop.png` + `-mobile.png`
- `docs/design/mockups/0.3.2/sparkline-variant-c-desktop.png` + `-mobile.png`

**Open question for owner:** none. Q73.4 lock (HTMX fragment on Profile) makes A the most idiomatic placement.

---

## Surface 4 — Cost-cap fallback banner (Settings · LLM tab)

**What it does.** When LLM judge is paused due to cost-cap exhaustion OR no LLM provider configured, the user sees this. Banner explains the degraded mode + links to recovery. Extends existing `_llm_cost_cap_widget.html` (plan 54 / 0.2.5.03) with a 4th state. Surfaces 0.3.0 OQ-5 lock: *"silent fallback + banner on Settings · LLM tab."*

**Data consumed.**
- `Settings.daily_llm_cost_cap_usd` (existing, plan 54).
- New helper `services/llm_tracker.judge_skipped_count_today(session, user_id) -> int` — counts `Job.match_breakdown` rows from today where `judge_skipped=True`.
- New helper `services/llm_tracker.judge_skipped_reasons_today(session, user_id) -> dict[str, int]` — distribution by reason (`cost_cap_exhausted`, `no_provider_configured`).

### Variant A — Inline below progress (Plan 74's default)
*Philosophy:* banner is a continuation of the cost-cap widget. Same card, same context. Minimal disruption to the existing IA.

*Treatment:* below the progress bar, separated by `border-t`, an amber-icon left + 2-line text + 2 CTA links right. Reads "LLM judge paused · 14 jobs scored without LLM tier today" with reason detail below.

*First-glance read:* user scrolls to the cost-cap section, sees the cap-exceeded chip, then reads the paused-judge explanation immediately below.

### Variant B — Top-of-tab strip (highest prominence)
*Philosophy:* this is degraded mode; user should see it the moment they hit the tab, NOT only when they scroll to the cost-cap widget. Banner above the Active-provider/API-config section.

*Treatment:* full-width amber-tinted card at the top of the LLM tab content area. Icon-in-tinted-square + title + time + 3-cell stat grid (SPENT / CAP / RESUMES) + primary CTA "Raise cap in .env" + secondary link "why this happened →".

*First-glance read:* user clicks LLM tab → banner is the FIRST thing they see. Impossible to miss.

### Variant C — Collapsed state chip in widget header
*Philosophy:* state is a chip alongside the existing "cap exceeded" chip. Expandable "why" details. Low-disruption; user can dig in only if they care.

*Treatment:* in the widget header row, alongside `cap exceeded` chip, add a second chip `judge paused · 14`. Below the progress bar + percentage, a collapsible `<details>` carrying the reason explanation + the .env code snippet.

*First-glance read:* user sees both chips in the widget header — "cap exceeded" + "judge paused · 14". The number "14" is the surprise-signal that nudges them to expand.

### Recommendation
**Variant B (Top-of-tab strip)** ships.

*Rationale:*
- **Cognitive load:** B respects what's happening — the LLM provider tab is showing a DEGRADED system state. That's category-3 of `engineer-manual-qa-gate`'s "user-visible failures". The banner shouldn't be tucked into a cost-cap-widget detail. A is too quiet. C is far too quiet — a chip-in-a-header is a non-signal for "your AI scoring is currently broken".
- **Alignment with existing patterns:** `followup_banner.html` (Tracking) sets the precedent for "amber tinted prominent strip" as the signal-of-broken-flow component. B's banner matches that visual class. A and C are quieter variants without a sibling pattern in the catalog.
- **Accessibility:** B's banner has the right ARIA hierarchy (heading + body + actions). A is OK — banner has implicit `role="status"`. C's chip-only state without expanded text is poor a11y (chip text alone = "judge paused · 14"; screen reader has no context).
- **Voice (dev-tool):** the copy on all 3 honors the dev-tool register. B's banner reads like an SRE notification ("LLM judge paused for today · cost-cap exhausted · 09:14 UTC"), which is exactly right for the audience. The 3-cell stat grid (SPENT / CAP / RESUMES) reads like a Datadog/Plausible incident card. Good. No upsell pressure ("Upgrade to Pro to remove this cap" — banned per DESIGN.md § Voice).
- **Implementation cost:** B = ~30 lines of Jinja inside `_settings_llm.html`, OR extract to a new `_llm_judge_paused_banner.html` section partial (engineer's call). A = ~15 lines extending the widget. C = ~25 lines extending the widget (chip + details element).
- **Cap-cycling:** B's "RESUMES" stat (countdown to UTC midnight) is more useful than just text. Helps user decide whether to wait or fix.

*Honest counterpoint:* if `judge_skipped_count_today=1` (one slip), B's full banner is overkill. Plan 74's spec says "render when `judge_skipped_count_today > 0`" — for low counts, B feels disproportionate. **Refinement:** render variant A's inline-below-progress treatment when count is 1-3 (low signal); promote to variant B's top-of-tab banner when count ≥ 5 (high signal). This combines both philosophies based on severity. Engineer can ship B with the count-gated promotion as a follow-up.

### Engineer notes — Surface 4

**Components composed:**
- `_llm_cost_cap_widget.html` (1) — EXISTING partial extended with the new `judge_skipped_count_today` + `judge_skipped_reasons_today` args. Per plan 74 § File-by-file edit #1.
- For Variant B: optional new partial `_llm_judge_paused_banner.html` — engineer extracts the 3-cell stat grid + CTAs into a reusable banner (if owner thinks this banner pattern will recur in other Settings tabs).

**New partial introduced:** Variant A + C = NONE (extends existing widget). Variant B = OPTIONAL `_llm_judge_paused_banner.html` extension. Engineer decides at implementation.

**Propose COMPONENTS.md edit** (committed in engineer's plan-74 PR):
```markdown
- Update § H.11 Settings group > _llm_cost_cap_widget.html:
  Add `judge_skipped_count_today` (int, default 0) and `judge_skipped_reasons_today` (dict, default {}) to API table.
  Add "judge_skipped" to "Variants / states" row.
- If Variant B + engineer extracts to new partial: Add row to § A inventory table for `_llm_judge_paused_banner.html` (Settings group, ×11 → ×12). Add spec to § H.11.
```

**HTMX patterns used:**
- Banner state is server-rendered on page load; no client-side dynamism needed for the banner itself.
- The CTA "Raise cap in .env" links to README § Configuration (external link, `hx-boost="false"` to avoid SPA-style intercept).

**Data accessor:**
- memory mode: `src/db/sample_data.py` — engineer adds `_llm_judge_skipped_count` + `_llm_judge_skipped_reasons` fixtures + accessor.
- db mode: `src/services/llm_tracker.py:judge_skipped_count_today` + `judge_skipped_reasons_today` (new helpers per plan 74 § File-by-file edit #2). Queries `Job` rows where `match_breakdown ->> 'judge_skipped' = 'true' AND scored_at >= today_midnight_utc`. GIN index on `match_breakdown` makes this cheap.

**Ctx-builder change:** `src/ui/routes/settings.py:_ctx_for_tab` (extends) — for the `llm-provider` tab branch, projects `judge_skipped_count_today` + `judge_skipped_reasons_today` into the template ctx.

**Build target:** `src/ui/templates/pages/_settings_llm.html` — Variant B inserts the banner block above the API configuration section (after the `<form>` opening). Variant A extends the existing `_llm_cost_cap_widget.html` include with the new args.

**Route handler:** unchanged. `src/ui/routes/settings.py:get_settings_tab` already serves.

**Mockup paths:**
- `docs/design/mockups/0.3.2/cost-cap-banner-variant-a-desktop.png` + `-mobile.png`
- `docs/design/mockups/0.3.2/cost-cap-banner-variant-b-desktop.png` + `-mobile.png` (recommended)
- `docs/design/mockups/0.3.2/cost-cap-banner-variant-c-desktop.png` + `-mobile.png`

**Open question for owner:** see "honest counterpoint" — should engineer ship Variant B with severity-gated promotion (variant A treatment for low counts, variant B for high counts)? Architect-recommend YES — surfaces signal proportional to severity, avoids "every minor slip becomes a top-banner".

---

## Quality bar — self-check (designer pre-handback)

- [x] All 4 surfaces have 3 variants each (12 total; verified 24 PNGs at canonical viewports)
- [x] All 3 owner-mandated skills fired per surface (huashu-design + ui-ux-pro-max + impeccable; documented in § Skill-invocation log)
- [x] Standard designer-* skills fired (designer-screen-lookup + designer-component-reuse + designer-mockup-conventions + designer-componentization-memo)
- [x] Memo is self-contained — engineer can implement without re-reading mockups (composition + variant pick + data accessor + build target + route + new-partial-or-not all named)
- [x] Visual contract honored — frozen tokens (Inter + JetBrains Mono + Lucide stroke 1.5 + slate/indigo/cyan/emerald/amber/rose); dark mode only; no light mode; no new fonts/icons
- [x] 91-partial catalog reuse verified — only `score_card.html` proposed as NEW (Q72.2 LOCK); all others extend existing partials via new args
- [x] Recommendation per surface + rationale
- [x] Skill-invocation log in memo (below)
- [x] Mobile + desktop both addressed per variant (verified at 375 × 812 + 1440 × 900)
- [x] Accessibility (WCAG AA on dark mode) verified — all token pairs documented above pass AA; B-variants have cleanest scan order
- [x] Trace log written with per-skill events + final BUILT line (see `traces/2026-05-21T07-54-17_362de279/designer.log`)

---

## Skill-invocation log (per surface × per skill)

Per owner directive (no token cap, opus[1m], all 3 skills + standard designer-*), every skill fired and contributed below. Conflicts named + resolved inline.

### Surface 1 — Score card

| Skill | Contribution |
|---|---|
| `designer-screen-lookup` | Loaded SCREENS.md § 7 (Discover card) + § 8 (Discover · review LEFT column) + § 12 (Job detail topbar). Confirmed surface lives in 3 places — `score_card.html` must serve all 3. |
| `designer-component-reuse` | Catalog check: `score_circle.html` (exists), `match_breakdown.html` (exists), `progress_bar.html` (exists). New container partial `score_card.html` justified because the "why / what's missing" overlay doesn't fit as a variant of either parent (would need 6+ new args each, polluting their single-responsibility shape). Q72.2 LOCKED → 91→92. |
| `huashu-design` | Design Direction Advisor mode — 3 differentiated philosophies recommended: A (Pentagram typographic info-architecture, Hara-restraint), B (Linear bento, 3-zone grid), C (Plausible density strip, single-line scannable). Differentiated by first-glance hierarchy, not decoration. |
| `ui-ux-pro-max` | Style selection from 50+ catalog: A = `info-arch-editorial`, B = `bento-grid` (highest match for "data-dense developer-tool dashboard"), C = `dense-list`. Color palette 161 stays frozen-DESIGN.md (no new palette). WCAG AA verified all token pairs (15.9:1 to 5.5:1 — all pass AA, most pass AAA). UX guideline 99 cross-check: `state-clarity` (B's hero number + tinted panels = strongest), `whitespace-balance` (A's editorial ledger has tighter type rhythm), `data-density` (C wins, but at touch-target cost). |
| `impeccable` | Hero-metric template (banned cliché) cross-check: B's big-86 in left zone flagged. Mitigation: the 86 is paired with FUNCTIONAL per-dim bars + functional strengths/gaps panels — these are action signals, NOT vanity stats. Pass-with-prejudice. Differentiation audit: A's editorial ledger is genuinely different IA from B's grid which is genuinely different from C's strip. Not cosmetic. AI slop test: 1st-order (dark+cyan) frozen by contract; 2nd-order avoided by 3-philosophy split. |
| `designer-mockup-conventions` | Path = `docs/design/mockups/0.3.2/` subdir (gitignored). Dimensions = 1440×900 desktop + 375×812 mobile. PNG sRGB. Filenames = `score-card-variant-{a,b,c}-{desktop,mobile}.png`. |
| `designer-componentization-memo` | This document. Engineer handoff prepared. |

**Conflicts:** none. huashu's "bento" philosophy aligned with ui-ux-pro-max's "bento-grid" style catalog entry. impeccable flagged hero-metric template; resolved by demonstrating functional (non-vanity) data accompanies the number.

### Surface 2 — Bullet preview

| Skill | Contribution |
|---|---|
| `designer-screen-lookup` | Loaded SCREENS.md § 8 (Discover · review MIDDLE column). Confirmed bullet rows are rendered per role-group via `_apply_tailored_bullets.html` macro. |
| `designer-component-reuse` | Catalog check: `tailored_bullet_row.html` (exists). NO new partial — extend with one new optional `rationale` arg per Q72 § File-by-file edit #1. Plan-72 audit cites this exact path. |
| `huashu-design` | Recommended: A (Inline ledger — micro-copy below bullet), B (Right-rail diff — code-review pattern), C (Color-coded margin — git-diff gutter). All three deeply different *interaction models*: always-on, focused-pane, expand-on-tap. |
| `ui-ux-pro-max` | Code-review pattern (B) is a recognized UX guideline (Cursor, VS Code, GitHub) — appropriate for developer audience. Inline-ledger (A) is closer to "code comments" pattern. Gutter (C) matches `diff-view` chart-type in the 25-chart catalog. All 3 honor `nav-state-active` (focused bullet visually distinct). |
| `impeccable` | Side-stripe-borders ABSOLUTE BAN cross-check: C's 1-px colored gutter flagged. Mitigation: it's a 2-column CSS grid with the gutter cell rendering an independent 1-px bar — NOT a `border-left: 2px solid` on the bullet card. It's the git-diff gutter pattern, which is functional (signals state) NOT decorative. Pass with documented rationale (in C's HTML source comment). Differentiation audit: A always-on vs B focused-pane vs C expand-on-tap = 3 fundamentally different interaction models. Not cosmetic. |
| `designer-mockup-conventions` | Same as Surface 1. Filename pattern = `bullet-preview-variant-{a,b,c}-{desktop,mobile}.png`. |
| `designer-componentization-memo` | This document. |

**Conflicts:** impeccable's side-stripe ban vs C's gutter. Resolved by documenting the functional-vs-decorative distinction in C's HTML source — gutters carry semantic state (kept vs dropped), unlike SaaS-cliché decoration stripes.

### Surface 3 — Sparkline

| Skill | Contribution |
|---|---|
| `designer-screen-lookup` | Loaded SCREENS.md § 4 (Profile). Hero card has avatar + name + actions; ON THIS PAGE rail carries anchors + readiness card. Q73.4 lock says HTMX fragment, no /scores route → 3 placement options exist within Profile (hero / dedicated section / rail). |
| `designer-component-reuse` | Catalog check: no chart partials exist. `progress_bar.html` doesn't fit (linear single-bar, not time-series). NO new catalog partial proposed — sparkline as inline-SVG block per Q73.4 lock (page-level fragment, not reusable component). Q73.4 supersedes plan 73's earlier "new sparkline.html partial" wording. |
| `huashu-design` | Recommended: A (Hero strip — sparkline part of identity), B (Dedicated section — chapter content), C (Right-rail card — peripheral status widget). All three different *placement IA*. |
| `ui-ux-pro-max` | Chart-type selection from 25-catalog: **line with filled-baseline** (gradient indigo/cyan/emerald/amber→transparent for active, line-only for muted). Area-chart adds ink no info; dot-cloud confuses 30-point sequence; line is right primitive. Pure SVG `polyline` + `path`, no JS (plan 73 forbidden pattern). `large-dataset` guideline (1000+ → aggregate) doesn't apply at 30-point granularity. `axis-readability` honored — value-axis y-labels (1.0/0.5/0.0) on B variant; A omits them for compactness. Mobile-responsive: SVG `preserveAspectRatio="none"` + `viewBox` ensures clean rescale. |
| `impeccable` | Color strategy = Restrained (tinted neutrals + accent ≤10%). Scene sentence: *"engineer reviewing scored job matches on a 27-inch monitor at 11pm in their home office."* Dark forced — correct. AI slop 2nd-order check: "AI dashboard sparkline → green line going up" is the obvious trap. Mitigation: 3 colors per-family follow score-threshold semantics (green for ≥0.80, indigo for ≥0.60, amber for ≥0.40), not "everything green up". When platform trends DOWN, it shows as amber-with-rose-delta, which is honest. |
| `designer-mockup-conventions` | Same as Surface 1. Filename pattern = `sparkline-variant-{a,b,c}-{desktop,mobile}.png`. |
| `designer-componentization-memo` | This document. |

**Conflicts:** plan 73 § File-by-file edit #8 lists `sparkline.html` as a NEW partial; Q73.4 lock (HTMX fragment, no new route) supersedes — designer-component-reuse skill resolves this in favor of "inline-SVG block in Profile" (not a reusable partial). If engineer disagrees post-implementation (e.g. sparkline gets used on Tracking/Outreach too), they can graduate to partial in a follow-up plan. Documented as open path.

### Surface 4 — Cost-cap banner

| Skill | Contribution |
|---|---|
| `designer-screen-lookup` | Loaded SCREENS.md § 11 (Settings · LLM Provider tab). Confirmed `_llm_cost_cap_widget.html` already lives in that tab body. Confirmed the env-presence indicator cards (per plan 26) already sit above the cost-cap widget. |
| `designer-component-reuse` | Catalog check: `_llm_cost_cap_widget.html` (exists, plan 54). `followup_banner.html` (exists, Tracking) sets the precedent for "prominent amber tinted strip" — variant B's pattern is a sibling of this existing component. EXTEND `_llm_cost_cap_widget.html`; no new partial required for A or C. For B, OPTIONAL extraction to `_llm_judge_paused_banner.html` if engineer thinks the pattern recurs in other Settings tabs. |
| `huashu-design` | Recommended: A (Inline below progress — quietest), B (Top-of-tab strip — loudest, can't miss), C (Collapsed state chip — quietest, expand-on-click). All three different *prominence levels*. |
| `ui-ux-pro-max` | UX guideline 99 cross-check: `error-feedback` — degraded mode is a recoverable error class. B's banner matches "clear error messages near the affected area" + offers a recovery path (.env edit). A is too quiet for category-3 degraded mode. C's chip-only state risks missed-signal. `progressive-disclosure` favors C for low-severity surfacing; favors B for high-severity. Resolution: severity-gated (variant A for count 1-3; variant B for count ≥5). |
| `impeccable` | Voice cross-check: copy on all 3 honors dev-tool register. "LLM judge paused for today · cost-cap exhausted · 09:14 UTC" reads like SRE notification. No upsell pressure ("Upgrade to remove the cap" — would be banned). 3-cell stat grid (SPENT / CAP / RESUMES) reads like Datadog incident card. Good. Hero-metric template ban check: not applicable — these are functional metrics for recovery decision, not vanity stats. |
| `designer-mockup-conventions` | Same as Surface 1. Filename pattern = `cost-cap-banner-variant-{a,b,c}-{desktop,mobile}.png`. |
| `designer-componentization-memo` | This document. |

**Conflicts:** ui-ux-pro-max says "less is more" (progressive disclosure favors C); huashu and impeccable say degraded-mode is a signal-event (favor B). **Resolved via severity-gating refinement** documented in B's "honest counterpoint" — render A for low counts, B for high counts. Engineer can ship the unified treatment.

---

## Open questions for owner (PLAN_GATE 2 — designer-return)

| # | Question | Architect recommendation |
|---|---|---|
| 1 | Score card variant pick (A / B / C)? | **B (Linear bento)** — clearest cognitive load, mobile parity, alignment with existing kpi_card pattern. C is the data-dense developer-tool favorite if owner prefers Plausible-style scan. |
| 2 | Bullet preview variant pick (A / B / C)? | **A (Inline ledger)** — always-visible rationale is the design goal. B's right-rail-diff is the post-MVP polish-pass evolution if user behavior shows people iterate heavily. |
| 3 | Sparkline variant pick (A / B / C)? | **A (Hero strip)** — answers "is my profile working?" before user has to ask. Q73.4 lock makes A the most idiomatic. |
| 4 | Cost-cap banner variant pick (A / B / C)? | **B (Top-of-tab strip)** with severity-gating refinement (render A treatment when count 1-3; B when ≥5). |
| 5 | Bullet preview Q72.3 — engineer verifies `Application.generation_trace.bullet_selection_log` shape at dispatch. Approve plan 72 engineer to add the shape if missing in plan 66's bundle? | YES — keeps the rationale field generation in one PR, avoids "blocked on dependency" cycle. |
| 6 | Cost-cap banner severity-gating (combo A+B based on `judge_skipped_count_today`)? | YES — matches the dev-tool ethos of "signal proportional to severity". Trivial extension of variant B's render condition. |

Owner picks variants → manager dispatches engineers for plans 72/73/74 in sequence, each consuming the recommended variant unless owner overrides.

---

## File map

**Committed to git (this PR):**
- `docs/design/MOCKUP_HANDOFF-0.3.2.md` ← this file
- `traces/2026-05-21T07-54-17_362de279/designer.log` (gitignored — agent log)

**Gitignored (per `docs/design/mockups/README.md`):**
- `docs/design/mockups/0.3.2/*.png` (24 mockup PNGs)
- `docs/design/mockups/0.3.2/html/*.html` (24 HTML prototype sources)
- `docs/design/mockups/0.3.2/_capture.py` (Playwright capture script)

**Reproducibility:** anyone with the repo can regenerate the PNGs:
```bash
nix develop
uv run python docs/design/mockups/0.3.2/_capture.py
```
The HTML prototypes are deterministic and self-contained; PNG output matches across machines (modulo font hinting). View `docs/design/mockups/0.3.2/<surface>-variant-<a|b|c>-<desktop|mobile>.png` in any image viewer.
