# Mockups (gitignored)

> **Heavy artifacts kept locally only.** This directory holds the canonical mockup PDF and any Claude Design handoff bundles. Contents are gitignored — only this README is checked in.
>
> **Regenerate when needed** via Claude Design. The active prompt lives at the root of `docs/prompts/` (currently empty for new mockups; the prior batch's prompt is archived at `docs/prompts/archive/CLAUDE_DESIGN_PROMPT.md`).

## What lives here (locally)

```
docs/design/mockups/
├── README.md                       ← this file (committed)
├── Naavik — MVP screens (print).pdf  (gitignored — heavy)
└── naavik-handoff/                 (gitignored — Claude Design bundle export)
    ├── README.md                   (callout describing stale screens in the bundle)
    ├── chats/                      (conversation transcripts)
    └── project/
        ├── design-canvas.jsx       (canvas wrapper)
        ├── design-system/
        │   └── colors_and_type.css (CSS tokens — same as DESIGN.md)
        ├── index.html              (entry point — drives the canvas)
        ├── index-print.html        (PDF-friendly version)
        ├── kit/
        │   ├── Components.jsx      (atomic components: Button, Tag, StatusBadge, ScoreDonut, etc.)
        │   └── Sidebar.jsx         (sidebar IA)
        └── screens/                (one JSX file per screen — most detailed visual reference)
            ├── Login.jsx
            ├── Onboarding.jsx
            ├── Overview.jsx
            ├── Profile.jsx
            ├── ProfileEdit.jsx
            ├── BulletModal.jsx
            ├── Discover.jsx
            ├── DiscoverDetail.jsx
            ├── Tracking.jsx
            ├── Outreach.jsx
            ├── Settings.jsx
            ├── CoverLetter.jsx     ← OBSOLETE; folded into DiscoverDetail
            ├── Analytics.jsx       ← OBSOLETE; folded into Overview
            ├── Dashboard.jsx       ← OBSOLETE; replaced by Overview
            ├── Jobs.jsx            ← OBSOLETE; replaced by Discover + DiscoverDetail
            ├── ResumeGen.jsx       ← OBSOLETE; folded into DiscoverDetail
            └── Data.jsx            (sample job seed data)
```

## How agents reference these

When implementing a screen, the convention (per `docs/design/SCREENS.md`):

- **PDF**: `docs/design/mockups/Naavik — MVP screens (print).pdf` — section numbers 1–8 match SCREENS.md sections 1–8; PDF section 9 is the orphaned standalone Cover Letter (no longer in SCREENS.md); PDF sections 10/11/12 map to SCREENS.md sections 9/10/11.
- **Bundle JSX**: `docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx` — most detailed visual reference. Use the JSX as the visual source of truth; `SCREENS.md` is the functional contract that wins on conflicts.
- **Tokens / colors / typography**: not from the mockups CSS — read from `DESIGN.md` (root) which is the canonical visual contract.

## Treating obsolete bundle screens

The bundle was exported from a 12-section iteration; some files are obsolete (see top-of-bundle README callout). When implementing, ignore the obsolete files and use the canonical equivalents:

| Obsolete bundle file | Canonical replacement |
|---|---|
| `Analytics.jsx` | folded into `Overview.jsx` |
| `Dashboard.jsx` | replaced by `Overview.jsx` |
| `Jobs.jsx` | replaced by `Discover.jsx` + `DiscoverDetail.jsx` |
| `ResumeGen.jsx` | folded into `DiscoverDetail.jsx` |
| `CoverLetter.jsx` | folded into `DiscoverDetail.jsx` |

## What if the mockups aren't on disk?

If you've cloned the repo fresh and don't have the mockups locally, you'll need to regenerate them:

1. Copy `docs/prompts/archive/CLAUDE_DESIGN_PROMPT.md` to `docs/prompts/CLAUDE_DESIGN_PROMPT.md`, update the prereq notes for the current state, and use it to drive a fresh Claude Design Prototype project.
2. Export the screens to PNG and the canvas-wide PDF.
3. Drop the exports in this folder; gitignore keeps them out of the repo.

Until then, work from `docs/design/SCREENS.md` (functional contract) + `DESIGN.md` (visual contract) and flag anything ambiguous.
