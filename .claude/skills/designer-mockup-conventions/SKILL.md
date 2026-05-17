---
description: Enforce mockup export conventions — path `docs/design/mockups/{n}-{slug}-{desktop|mobile}.png`, dimensions 1440×900 (desktop) + 375×812 (mobile), sequential ordinal numbering, mockups gitignored locally. Use before exporting from Claude Design / a prototype tool, before committing a mockup to git (you shouldn't — only the PNG paths flow forward via the bundle), when naming a new mockup file. Triggers on phrases like "mockup conventions", "export mockup", "mockup naming", "what dimensions", "where do mockups go", "mockup path", "1440", "375", "viewport".
---

# designer-mockup-conventions

Naavik's mockups are produced via Claude Design's prototype pipeline + exported as PNGs to `docs/design/mockups/`. The mockups themselves are **gitignored** (large binary churn), so the discipline is the path naming + dimension consistency: every page in `src/ui/templates/pages/` has a matching `{n}-{slug}-desktop.png` + `{slug}-mobile.png` reference. Engineer reads those to know what to build.

## When to invoke

- About to export a new mockup from Claude Design / v0 / Galileo.
- Naming a new mockup file (verify the ordinal + slug).
- About to commit a mockup to git (don't — read the gitignore rule below).
- Engineer asks "where's the mockup for X?" — point to the canonical path.

## What this skill does

### Path convention (frozen)

```
docs/design/mockups/{n}-{slug}-{desktop|mobile}.png
```

- `n` = sequential ordinal (2-digit zero-padded; MVP is 01–11, add 12+ for new screens).
- `slug` = kebab-case screen identifier matching `docs/design/SCREENS.md § the screen`. Examples:
  - `overview`, `profile`, `bullet-editor`, `discover`, `discover-review`, `tracking`, `outreach`, `settings`, `login`, `onboarding`, `auth`
- `desktop` / `mobile` = the viewport variant (both required for every screen).

### Dimensions (frozen)

- **Desktop:** 1440 × 900
- **Mobile:** 375 × 812

These match the Playwright capture viewports at `tests/visual/capture.py` so visual QA can compare apples-to-apples.

### File format

- **PNG only.** No JPG / WebP / SVG.
- Color space: sRGB.
- Compression: standard (no need for `optipng` heroics — mockups are gitignored).

### What's gitignored vs what's committed

| Path | Tracked? | Notes |
|---|---|---|
| `docs/design/mockups/*.png` | **Gitignored** | Large binary; per-fork local copy. Author keeps a local archive; share via Drive/Notion if needed. |
| `docs/design/mockups/naavik-handoff/project/screens/*.jsx` | **Gitignored** | Claude Design bundle JSX (the "source" of the mockup). |
| `docs/design/mockups/README.md` | Committed | Bootstrap instructions for "how to regenerate mockups from scratch". |
| `docs/design/mockups/Naavik — MVP screens (print).pdf` | **Gitignored** | Historical 12-section export. |

Verify by reading `docs/design/mockups/README.md` if uncertain.

### Numbering convention

MVP screens own ordinals 01–11 (per `docs/design/SCREENS.md`):

| # | Slug | Section in SCREENS.md |
|---|---|---|
| 01 | `login` | Section 1 |
| 02 | `onboarding` | Section 2 |
| 03 | `overview` | Section 3 |
| 04 | `profile` | Section 4 |
| 05 | `bullet-editor` | Section 5 (modal from Profile) |
| 06 | `discover` | Section 6 |
| 07 | `discover-review` | Section 7 |
| 08 | `tracking` | Section 8 |
| 09 | `outreach` | Section 9 |
| 10 | `settings` | Section 10 |
| 11 | `auth` | Section 11 (signup/forgot) |

New screens (Phase 2+) start at 12.

### Re-export workflow

When a mockup needs an update (visual polish, voice fix, missing state):

1. Open the source bundle JSX at `docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx`.
2. Edit in Claude Design (or hand-edit JSX if the change is small).
3. Re-export at the canonical dimensions.
4. Replace the PNG file in-place at `docs/design/mockups/{n}-{slug}-{desktop|mobile}.png`.
5. **Do not** create `{n}-{slug}-v2-desktop.png` — overwrite. The bundle JSX is the version history.

### Visual QA cross-reference

Engineer's Playwright capture (`tests/visual/capture.py`) takes screenshots at the same viewports. Comparing `tests/visual/screenshots/<slug>-desktop.png` against `docs/design/mockups/{n}-{slug}-desktop.png` is the canonical "did we implement what was designed" check. Diff threshold: < 1% pixel delta. Larger = regression.

## Canonical references

- `AGENTS.md` § Design Agents — mockup conventions.
- `docs/design/WORKFLOW.md` § Pipeline — the mockup → component → page flow.
- `docs/design/mockups/README.md` — local-setup + regeneration instructions.
- `.claude/agents/designer.md` § "Mockup conventions".
- `tests/visual/capture.py` — viewport sources of truth.

## When NOT to invoke

- You're polishing an existing implementation without changing the mockup.
- Pure backend / data work.
- Compaction events.

## Forbidden during invocation

- Do NOT commit `*.png` from `docs/design/mockups/` to git. They're gitignored for a reason. The author's archive is the canonical store.
- Do NOT export at non-standard dimensions (e.g. 1920 × 1080). Playwright QA uses 1440 × 900 / 375 × 812 — diffing would be meaningless.
- Do NOT use `{slug}-desktop.png` without the ordinal prefix. Sorted directory listings rely on the ordinal.
- Do NOT mix font / icon styles by exporting a mockup that's not in the published Claude Design system. The system inherits DESIGN.md tokens; freelance mockups drift.
