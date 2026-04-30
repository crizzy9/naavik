---
Status: EXECUTED
Type: execution
Authored: 2026-04-30
Last updated: 2026-04-30
Executed: 2026-04-30
Depends on: —
---

# 01 · Docs realignment

## Goal

Bring every doc in the repo into a single self-consistent state before any implementation work begins. Specifically: drop the `/generate/*` standalone routes, finalize the 5-stage pipeline everywhere, finalize the single-bullet long-form model everywhere, replace the stale 19-screen index in ROADMAP.md with the canonical 11-screen MVP, and reorganize `docs/` into `plans / prompts / misc / design`.

## Context / why

Two parallel design iterations have shipped (the original 19-screen, 9-stage, two-form-bullet model and the current 11-screen, 5-stage, single-bullet model). The newer model is correct; the older model is stale but still leaks in 8+ places across SCREENS.md, ROADMAP.md, CLAUDE_DESIGN_PROMPT.md, HANDOFF_PROMPT.md, and DESIGN.md. This causes confusion for any future agent reading the docs cold (it just happened to me on the design handoff). User has authorized:

- Cover letter generation lives inside Discover · review & apply (no `/generate/cover-letter` standalone)
- Resume tailoring lives inside Discover · review & apply (no `/generate/resume` standalone)
- Analytics is folded into Overview (no `/analytics`)
- Jobs is renamed to Discover (no `/jobs`)

After this realignment, the canonical MVP set drops from 12 to 11 screens.

## Proposal

### A · Inconsistency catalogue (full)

| #   | Issue                                                                                                                                                                                                                                                                       | File                                           | Lines       | Severity                                                  |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ----------- | --------------------------------------------------------- |
| I1  | Section 9 "Cover letter generator" defined as standalone tool at `/generate/cover-letter`                                                                                                                                                                                   | `docs/design/SCREENS.md`                       | 86, 441–479 | High                                                      |
| I2  | "Removed from prior IA" line still says `/generate/cover-letter` "still exists as a tool"                                                                                                                                                                                   | `docs/design/SCREENS.md`                       | 60          | High                                                      |
| I3  | Profile view § 4 says "Expand-affordance reveals 'detailed only' bullets" — incompatible with single-bullet model                                                                                                                                                           | `docs/design/SCREENS.md`                       | 233         | Medium                                                    |
| I4  | Profile editor § 5 bullet edit row shows "✓ in 1-page resume / detailed only" indicator                                                                                                                                                                                     | `docs/design/SCREENS.md`                       | 275         | Medium                                                    |
| I5  | Phase 1 page-by-page guidance lists Cover letter generator at `/generate/cover-letter` as screen #10                                                                                                                                                                        | `docs/design/HANDOFF_PROMPT.md`                | 183         | High                                                      |
| I6  | "Things that will get rejected" only forbids `/generate/resume` route; should also forbid `/generate/cover-letter`                                                                                                                                                          | `docs/design/HANDOFF_PROMPT.md`                | 222         | High                                                      |
| I7  | Recommended implementation order lists Cover letter as screen 10 (before Discover screens)                                                                                                                                                                                  | `docs/design/HANDOFF_PROMPT.md`                | 181–185     | Medium                                                    |
| I8  | Screen Index (lines 599–619) still uses old 19-screen list with `/generate/resume`, `/generate/cover-letter`, `/jobs`, `/analytics`, `/inbox`, `/contacts`, `/interviews`                                                                                                   | `ROADMAP.md`                                   | 599–619     | High                                                      |
| I9  | Phase 1 task D.1 says "Screens 1–9: login, dashboard, onboarding, profile view, profile editor, bullet editor, resume generator, cover letter generator, settings"                                                                                                          | `ROADMAP.md`                                   | 305         | High                                                      |
| I10 | Phase 1 task 1.6 still references "oneline/detailed side-by-side, default_include toggle" bullet editor                                                                                                                                                                     | `ROADMAP.md`                                   | 313         | High                                                      |
| I11 | Phase 1 task 1.1 still uses "`oneline` + `detailed` + `tags` + `default_include`" as the bullet model note                                                                                                                                                                  | `ROADMAP.md`                                   | 309         | High                                                      |
| I12 | Data model diagram (Profile / experience / bullets) still defines `oneline`, `detailed`, `default_include`, `metrics{revenue, percentage, team_size}` fields                                                                                                                | `ROADMAP.md`                                   | 130–138     | High                                                      |
| I13 | Data model diagram (Job) still uses old 9-stage status enum `FOUND → SCORED → APPROVED → DOCS_GENERATED → APPLIED → INTERVIEWING → OFFER → REJECTED → WITHDRAWN`                                                                                                            | `ROADMAP.md`                                   | 152         | High                                                      |
| I14 | Phase 4.1 task description still uses old 9-stage pipeline                                                                                                                                                                                                                  | `ROADMAP.md`                                   | 375         | High                                                      |
| I15 | "Key Design Decisions" #2 still describes "Two-form bullets — Every experience bullet has `oneline` (strict 1-line for 1-page resume) and `detailed` (full description for portfolio/extended CV)"                                                                          | `ROADMAP.md`                                   | 104         | High                                                      |
| I16 | Phase 5 still labelled "Email Monitoring & Interview Pipeline" with sub-section "Interview Pipeline" — Tracking subsumes both per current SCREENS.md                                                                                                                        | `ROADMAP.md`                                   | 387, 399    | Medium                                                    |
| I17 | n8n migration table references `ui/templates/jobs/` (old folder)                                                                                                                                                                                                            | `ROADMAP.md`                                   | 525         | Low                                                       |
| I18 | "Section 9: Cover Letter Generator (`/generate/cover-letter`)" entire screen description block                                                                                                                                                                              | `docs/design/CLAUDE_DESIGN_PROMPT.md`          | 121–…       | High                                                      |
| I19 | "Section 7: Resume Generator (`/generate/resume`)" entire screen description block                                                                                                                                                                                          | `docs/design/CLAUDE_DESIGN_PROMPT.md`          | 111–…       | High                                                      |
| I20 | Bullet description still says "oneline + tags + AI badge"                                                                                                                                                                                                                   | `docs/design/CLAUDE_DESIGN_PROMPT.md`          | 115         | High                                                      |
| I21 | DESIGN.md L85 reads "There is no `FOUND` / `SCORED` / `APPROVED` / `DOCS_GENERATED` / `INTERVIEWING` state" — close but doesn't list `REJECTED` / `WITHDRAWN` (which were also dropped); also doesn't proactively name the 5 valid states.                                  | `DESIGN.md`                                    | 85          | Low                                                       |
| I22 | WORKFLOW.md "First Run" still says "Iterate until satisfied with all 9 screens"                                                                                                                                                                                             | `docs/design/WORKFLOW.md`                      | 263         | Low                                                       |
| I23 | WORKFLOW.md "First Run" only lists Phase 1 screens 1–9; should reference SCREENS.md for the canonical 11-screen MVP set                                                                                                                                                     | `docs/design/WORKFLOW.md`                      | 245–270     | Low                                                       |
| I24 | DESIGN.md File Map still lists `docs/design/CLAUDE_DESIGN_PROMPT.md` in its old form                                                                                                                                                                                        | `DESIGN.md`                                    | 436         | Low (verify after realignment of CLAUDE_DESIGN_PROMPT.md) |
| I25 | Sample bundle stored in `docs/design/mockups/naavik-handoff/` is fine as reference but contains stale screens (Analytics, Dashboard, Jobs, ResumeGen, standalone CoverLetter); should add a note that the bundle is _historical reference only_ and SCREENS.md is canonical | `docs/design/mockups/naavik-handoff/README.md` | (entire)    | Low                                                       |

### B · Edit plan, file by file

> **Convention:** "Drop X" means delete the line(s); "Replace with Y" means rewrite. All edits below are dry runs — they only land after this plan is APPROVED.

#### `docs/design/SCREENS.md` (canonical screen catalog)

| Edit                                                   | Action                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Line 60                                                | Replace "Removed from prior IA" line. New text: `**Removed from prior IA:** standalone Resume route (folded into Discover · review & apply), standalone Cover Letter route (folded into Discover · review & apply), Analytics route (deferred), theme switcher (single dark mode).` |
| Line 76–90 (Screen Index table)                        | Drop row #9 "Cover letter generator". Renumber #10→9, #11→10, #12→11.                                                                                                                                                                                                               |
| Lines 233 (Profile view § 4)                           | Replace "Expand-affordance reveals 'detailed only' bullets that don't appear on the 1-page resume." → "Expand-affordance reveals all bullets for the role; AI auto-selects which ones land on a tailored resume at apply time."                                                     |
| Lines 275 (Profile editor § 5)                         | Drop the "✓ in 1-page resume" or "detailed only" indicator from the bullet row description. New text: `Each row: drag-handle (`grip-vertical`), bullet text (truncated preview), tag chips, edit-pencil + trash icons on hover.`                                                    |
| Lines 441–479 (entire Section 9)                       | Delete the whole "9. Cover letter generator (standalone tool)" section.                                                                                                                                                                                                             |
| Lines 484, 535, 580, 645+                              | Renumber sections: 10 → 9 (Tracking), 11 → 10 (Outreach), 12 → 11 (Settings). Update all anchor refs.                                                                                                                                                                               |
| Phase mapping section                                  | Update "12 sections" → "11 sections" and remove "Cover letter generator" from the Phase 1 list.                                                                                                                                                                                     |
| Add a note under Section 8 (Discover · review & apply) | Confirm cover letter generation is part of this screen's right column — already there. Add a one-liner: "This screen subsumes the prior `/generate/cover-letter` and `/generate/resume` routes."                                                                                    |

#### `ROADMAP.md`

| Edit                                  | Action                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| L104 (Key Design Decisions #2)        | Replace "Two-form bullets" decision with a single-form decision. Suggested text: `**Single long-form bullets** — Every experience bullet has one canonical text (the long, full version). AI trims to a single resume line at apply time using tags + JD signals. User can pin via per-bullet selection_override (always_include / never_include / null = auto).`                       |
| L130–138 (Profile data model diagram) | Rewrite the experience bullet sub-tree to: `bullets[] ├── id ├── text (long form, no length cap) ├── tags[] (9 vocab) └── selection_override (always_include / never_include / null)`. Drop `oneline`, `detailed`, `default_include`, `metrics{}`.                                                                                                                                      |
| L152 (Job status enum)                | Replace the flat `status (FOUND → SCORED → … → WITHDRAWN)` line with the **multi-axis Application state model**, ROADMAP rendering it as a short bullet sketch and pointing readers to plan 05's design doc for full detail. Suggested replacement: `Job lifecycle is multi-axis — see docs/plans/02-mvp-master-plan.md § B → "Lifecycle modeling principle" and plan 05. Job (pre-application): queue_state in {unswiped, saved, skipped, queued_for_auto_apply, applied}. Application (post-submission): status in {APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER, CLOSED} + closed_reason in {rejected_by_them, withdrawn_by_me, ghosted, accepted_other}; orthogonal sub-states docs_state, referral_state, recruiter_state, outreach_engagement (computed); see plan 05.` |
| L305 (Phase 1 task D.1)               | Replace "Screens 1–9: login, dashboard, onboarding, profile view, profile editor, bullet editor, resume generator, cover letter generator, settings" with "Screens 1–11 per `docs/design/SCREENS.md`: login, onboarding, overview, profile, profile editor, bullet editor (modal), discover, discover · review & apply, tracking, outreach, settings".                                  |
| L309 (Phase 1 task 1.1)               | Replace `oneline + detailed + tags + default_include` note with `text + tags[] + selection_override`.                                                                                                                                                                                                                                                                                   |
| L313 (Phase 1 task 1.6)               | Replace task with `Bullet editor modal (single-text + 9-tag picker + selection_override; opens from Profile editor and Discover · review & apply)`.                                                                                                                                                                                                                                     |
| L375 (Phase 4.1)                      | Replace `Status pipeline: FOUND → SCORED → … → WITHDRAWN` with the multi-axis state task: `Application state model: post-submission status (APPLIED → RECRUITER_SCREEN → ONSITE_LOOP → OFFER → CLOSED) + closed_reason. Orthogonal sub-states: docs_state, referral_state, recruiter_state, outreach_engagement. State machine + transitions per axis. See docs/design/DATA_MODEL.md (graduated from plan 05) for authoritative definitions.` |
| L387 (Phase 5 header)                 | Rename "Phase 5: Email Monitoring & Interview Pipeline" → "Phase 5: Email Monitoring & Outreach". Drop the "Interview Pipeline" sub-section header (its tasks fold under Tracking auto-classification).                                                                                                                                                                                 |
| L399                                  | Drop the "**Interview Pipeline**" sub-section header; tasks 5.7, 5.8 either move into Phase 4 (Tracking) or Phase 5 main flow.                                                                                                                                                                                                                                                          |
| L525 (n8n migration row)              | Replace `ui/templates/jobs/` → `ui/templates/pages/discover.html` + `ui/templates/pages/tracking.html`.                                                                                                                                                                                                                                                                                 |
| L596–620 (Screen Index table)         | Replace the entire 19-row table. New table is just a pointer: `**Canonical screen index lives in [`docs/design/SCREENS.md`](docs/design/SCREENS.md).** That document tracks per-screen mockup status (`Mockup [ ]`/`[~]`/`[x]`) and impl status (`Impl [ ]`/`[~]`/`[x]`). ROADMAP.md tracks phase progress; SCREENS.md tracks per-screen progress.` This avoids two drift-prone tables. |

#### `docs/design/HANDOFF_PROMPT.md`

| Edit                                             | Action                                                                                                                                                                                                                                       |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| L181–185 (Recommended implementation order)      | Drop "Cover letter generator (`/generate/cover-letter`) — 2-column tool with SSE streaming" entry. Renumber subsequent items so the list reads 1..11.                                                                                        |
| L222 (Things that will get rejected)             | Replace "Adding a Resume sidebar item or `/generate/resume` route" with "Adding a Resume or Cover Letter sidebar item or any `/generate/*` route (resume tailoring and cover letter drafting both happen inside Discover · review & apply)". |
| Section 1 ("You are working in the Naavik repo") | Move HANDOFF_PROMPT.md path reference: any docs that link to it as `docs/design/HANDOFF_PROMPT.md` need to update if we move the file. Per directory restructure below, this becomes `docs/prompts/HANDOFF_PROMPT.md`.                       |

#### `docs/design/CLAUDE_DESIGN_PROMPT.md`

This file is the prompt for Claude Design's Prototype project. It's now stale on multiple fronts (screen list, bullet model, status enum). Two options:

- **Option A (recommended):** Rewrite end-to-end to match the canonical 11-screen MVP. Move to `docs/prompts/CLAUDE_DESIGN_PROMPT.md` after rewrite.
- **Option B:** Leave the rewrite for when we next regenerate mockups. Move as-is to `docs/prompts/CLAUDE_DESIGN_PROMPT.md` with a top-of-file warning that contents are stale.

I propose **Option A**, but it can land in a follow-up plan if you'd rather defer — the prompt isn't blocking anything until we want a fresh Claude Design batch.

#### `DESIGN.md` (root)

| Edit                       | Action                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| L85 (Status Pipeline note) | Replace "Pre-application discovery (find → score → swipe) lives in `/discover`, **not** Tracking. There is no `FOUND` / `SCORED` / `APPROVED` / `DOCS_GENERATED` / `INTERVIEWING` state." with a positive enumeration: "Pre-application discovery (find → score → swipe) lives in `/discover`, not Tracking. The application pipeline has exactly five states: `APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED`. The states `FOUND` / `SCORED` / `APPROVED` / `DOCS_GENERATED` / `INTERVIEWING` / `REJECTED` / `WITHDRAWN` are **not** in the model — closed sub-reasons (rejected / withdrawn / ghosted) live in `closed_reason` when `status=CLOSED`." |
| L436 (File Map)            | Update path of `HANDOFF_PROMPT.md` to `docs/prompts/HANDOFF_PROMPT.md` (post-move). Update path of `CLAUDE_DESIGN_PROMPT.md` to `docs/prompts/CLAUDE_DESIGN_PROMPT.md`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

#### `docs/design/WORKFLOW.md`

| Edit                       | Action                                                                                                                                                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| L263 ("First Run" Phase B) | Update "Iterate until satisfied with all 9 screens" → "Iterate until satisfied with all 11 MVP screens per SCREENS.md".                                                                                                  |
| L245–275 ("First Run")     | Update phase progress markers — Phase A (system setup) and Phase B (mockups) are both complete; mark with checkmarks. The next thing is Phase C (Stage 2 component derivation), which is what this realignment unblocks. |
| Top of file                | Add a note: "Updated 2026-04-30 to reflect 11-screen MVP."                                                                                                                                                               |

#### `docs/design/mockups/naavik-handoff/README.md`

Append a top-of-file callout:

> **2026-04-30 update:** This bundle is the historical Claude Design export. Its `screens/` folder includes obsolete files (`Analytics.jsx`, `Dashboard.jsx`, `Jobs.jsx`, `ResumeGen.jsx`, standalone `CoverLetter.jsx`) which were superseded during iteration. Treat the bundle as **reference only** — `docs/design/SCREENS.md` is canonical. The MVP is 11 screens (no standalone `/generate/*` routes).

#### `CLAUDE.md`

No edits identified beyond what's already correct. Verify after the rest land.

#### `AGENTS.md`

No edits identified. AGENTS.md already reflects the single-bullet model and 5-stage pipeline correctly.

#### `README.md`

L64 says "Compatibility scoring (0-1) with detailed explanation" — "detailed" is used as a generic adjective, not as the bullet model term. **No change needed**, but flagging for confirmation.

### C · Directory restructure

| Move                    | From                                                                                     | To                                     | Reason                                                                                                                           |
| ----------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| HANDOFF_PROMPT.md       | `docs/design/HANDOFF_PROMPT.md`                                                          | `docs/prompts/HANDOFF_PROMPT.md`       | It's a hand-edited prompt that rides inside a Claude Design handoff bundle. Per the new layout, prompts live in `docs/prompts/`. |
| CLAUDE_DESIGN_PROMPT.md | `docs/design/CLAUDE_DESIGN_PROMPT.md`                                                    | `docs/prompts/CLAUDE_DESIGN_PROMPT.md` | Same — it's a prompt for Claude Design's Prototype project.                                                                      |
| (No move)               | `docs/design/SCREENS.md`, `DESIGN.md`, `docs/design/WORKFLOW.md`, `docs/design/mockups/` | (stay)                                 | These are canonical design contracts and output artifacts.                                                                       |
| (No move)               | `ROADMAP.md`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`                           | (stay at repo root)                    | Convention; tools and external links rely on root location.                                                                      |
| (No move)               | `TODO.md` (root, gitignored / untracked)                                                 | (stay)                                 | Personal scratchpad per its own header.                                                                                          |

After moves, update every cross-reference. The cross-references to find and update:

```bash
# References to HANDOFF_PROMPT.md
- docs/design/SCREENS.md (no direct ref; OK)
- docs/design/WORKFLOW.md (file map ref)
- DESIGN.md (file map ref)
- AGENTS.md (no direct ref; OK)
- CLAUDE.md (no direct ref; OK)
- placeholder.html (template — needs update)

# References to CLAUDE_DESIGN_PROMPT.md
- docs/design/SCREENS.md (mentions but doesn't link)
- docs/design/WORKFLOW.md (links from Inputs and First Run sections)
- DESIGN.md (file map ref)
- AGENTS.md (Documentation Map table)
- ROADMAP.md (Design Documents table)
```

I'll grep for the exact lines in the execution step and fix every reference.

### D · `placeholder.html`

`src/ui/templates/placeholder.html` references `docs/design/HANDOFF_PROMPT.md` on line 34. Update to `docs/prompts/HANDOFF_PROMPT.md`.

### E · Mockup PDF

`docs/design/mockups/Naavik — MVP screens (print).pdf` was generated when there were 12 sections. After realignment we have 11. The PDF is reference material; we don't regenerate it as part of this plan. Add the bundle README callout from § B above so it's clear the standalone Cover letter artboard is orphaned.

## Open questions

1. **CLAUDE_DESIGN_PROMPT.md rewrite** — Option A (rewrite now) or Option B (move stale, defer rewrite)? My recommendation: **A**, and I'll fold the rewrite into this plan's execution step.
2. **ROADMAP.md screen index** — replace with a one-line pointer to SCREENS.md (my proposal) or keep a parallel table (extra maintenance, but useful for quick scanning)? My recommendation: **pointer only** — duplicating creates drift, and the existing 19-row table is already drifting.
3. **Phase 5 task split** — `5.7 Interview scheduling` and `5.8 Interview prep` belonged to the deleted "Interview Pipeline" sub-section. Move under Tracking (Phase 4) or keep in Phase 5 main flow? My recommendation: keep in Phase 5 main flow (interview prep AI is independent of tracking auto-classification).
4. **README.md L64** — change "detailed explanation" → "concise explanation" to avoid the bullet-model semantic collision? My recommendation: **no change** (it's plain English, no collision risk).
5. **Mockup PDF regeneration** — defer until we run the next Claude Design batch (after backend models exist and we want to spec deferred screens like Manual job entry)? My recommendation: **defer**.

## Approval checklist

Tick to approve each. Anything unticked blocks execution.

- [x] Inconsistency catalogue (§ A) is complete; no missing items
- [x] Per-file edit plan (§ B) is correct
- [x] Directory restructure (§ C) — move HANDOFF_PROMPT.md and CLAUDE_DESIGN_PROMPT.md to `docs/prompts/`
- [x] CLAUDE_DESIGN_PROMPT.md → Option A (rewrite now)
- [x] ROADMAP.md screen index → pointer only
- [x] Phase 5 task split → keep in Phase 5 main flow
- [x] README.md L64 → no change
- [x] Mockup PDF regeneration → defer
- [x] Add the bundle README callout to flag obsolete artboards
- [x] Update `placeholder.html` line 34 path
- [x] After execution: bump "Last updated" on all touched docs and commit as a single `docs:` commit
