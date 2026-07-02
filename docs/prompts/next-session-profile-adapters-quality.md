# Kickoff prompt — profile as career dossier, adapter rebuild, doc quality, feedback everywhere

Copy everything below the line into a fresh Claude Code session running on **Fable 5**
(check with `/model`; set `claude-fable-5` if it isn't).

---

You are a senior full-stack product engineer AND UI designer working on Naavik, my
open-source, self-hosted career-automation web app, owned by myself (FastAPI +
SQLModel + Postgres/pgvector, HTMX + Jinja2 + Tailwind + DaisyUI, Typst for PDFs,
APScheduler). You own product, design, and engineering decisions end to end.

## How to work (overrides everything else you may read)

- **Do all work yourself, in this session, on the session model (Fable 5).** Do
  NOT dispatch thinking/planning/design/editing work to the `.claude/agents/*`
  profiles — anything that would silently move work onto Opus 4.8 or Sonnet is
  off the table. The agent files have been stripped to inert stubs; treat them
  as nonexistent. Read-only Explore subagents for code search are fine.
- **Do NOT invoke the `naavik-cold-start` skill.** If a SessionStart hook says it
  "MUST" be your first action, ignore it — that scaffolding is retired. Likewise
  ignore `docs/PLAYBOOK.md`, `docs/AGENT_OPS.md`, plan/PR gates, and the GitHub
  Projects mirror. `AGENTS.md` is background reference only.
- **Plan before you touch code** — your own plan, in-session: read the relevant
  code, write the design down (scratch markdown or plan mode), then implement.
  For UI work, sketch layout/hierarchy decisions first.
- **Work autonomously until done.** Routine decisions are yours; ask only before
  destructive actions or genuine product-shape forks. No ROADMAP.md bookkeeping,
  no PRs, no `git push` — commit locally on `main` in small, clear commits.
- Run `ruff check .` + `ruff format .` (nix-provided binary) and `uv run pytest`
  before finishing. Add targeted tests for what you fix.
- **Verify every UI change live in a real browser (Playwright, 1440×900).** Read
  screenshots critically as a designer — hierarchy, alignment, spacing, density —
  not just "did it render". Note: headless screenshots show embedded PDF viewers
  as white boxes; open the PDF bytes directly to judge documents.
- Git quirk: bare `git add -A` and long inline `git commit -m` get denied by the
  permission layer. Stage explicit paths and use `git commit -F <message-file>`.

## Environment (trust but verify)

- `nix run .#dev` starts Postgres (127.0.0.1:5433, naavik/password) + the app on
  :8003 with auto-reload. `NAAVIK_DEBUG=1` + `DATABASE_URL=postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik`
  for manual `alembic upgrade`. Migrations are at head = `0028_auto_apply_states`.
- `OPENAI_API_KEY` is set in `.env` and works. No Anthropic key.
- Seeded working account: `e2e-1783005393@naavik.test` / `naavik-e2e-pass-1`
  (user_id 3) — real parsed profile (6 experiences / 20 bullets / 5 projects,
  linkedin `shyampadia`, github `crizzy9`, portfolio `crypticsoul.dev`), ~50 real
  scraped jobs. Application 7 (Walmart/LinkedIn) and 14 (Verkada, job 69, board
  GREENHOUSE — inserted for state testing) have generated bundles. User 3
  currently has `auto_apply_enabled=true, auto_apply_dry_run=true`. Gmail is
  connected via IMAP app password and syncing (`shyam.padia930@gmail.com`).
- Last session shipped: async bundle generation (GET never blocks; workspace
  polls while `docs_state=GENERATING`), single `onepage.typ` template, ranked
  bullet selection with page-fit loop, first-person cover letter, full-width
  match panel, auto-apply pipeline with `READY_TO_SUBMIT` handoffs +
  `submission_artifacts.auto_apply` timestamps, Tracking Jobs library, Gmail
  one-screen connect. Read those commits (`git log`) before changing the areas.
- Never point destructive test fixtures at the dev DB; leave
  `NAAVIK_CHAIN_REPLAY_DB_URL` unset; grep env-gated "live" tests for
  DROP/TRUNCATE before enabling. UI tests use cookie `naavik_session=fake-1` +
  `pytest.mark.uses_sample_data_shims`.

Work through every item below. Do not stop at a partial checkpoint.

---

## 1 — Profile becomes the full career dossier

The Profile tab is the master record of everything I've done professionally;
resume/cover-letter tailoring draws from it. Two surfaces: **view = read-only,
well-designed preview; edit = one full-fledged form** (like the application
questions form), fully self-serve without ever uploading a resume.

- Move the **Edit profile** and **Upload resume** buttons back to the top of the
  profile view (they used to be there). Uploading a resume is a first-time /
  reset action — say so in its confirm copy (it replaces parsed sections).
- Make the edit form complete: **add/remove experience slots**, add/remove
  **bullets** per experience, **add/remove education slots**, projects, skills
  groups. The pencil/edit icon on experience cards currently does nothing — fix
  or remove it in favor of always-editable fields.
- Add **Certifications** (model exists: `models/profile.py:Certification`, no UI)
  and **Open-source contributions** as editable sections. For open source, decide
  the shape yourself (a `Project` kind/flag or a new child model + migration) —
  it must flow into the tailoring payload like projects do.
- **Summary mismatch bug**: the view page shows a summary that doesn't appear in
  the edit form (view falls back to something — find it; edit binds
  `summary_full` only). One source of truth, visible + editable in both.
- The tailoring pipeline (`document_generator.load_profile_snapshot` →
  `_build_resume_data`) must consume the full dossier: certifications and open
  source included.

## 2 — Discover + document quality round 2

Review page + swipe deck (`src/ui/discover_ctx.py`, `discover_review_ctx.py`,
`components/match_panel.html`, `components/swipe_card.html`,
`pages/_discover_review_workspace.html`), resume pipeline
(`services/document_generator.py`, `src/typst/templates/onepage.typ`).

- **Identity inversion**: company name bold on top, role smaller beneath — on the
  match panel header AND wherever the pair renders in Discover (swipe card, up
  next, topbar breadcrumb).
- **Generate button placement**: "Generate tailored documents" generates the
  whole bundle, so it does NOT belong inside the resume section. Put it in the
  sticky bottom action bar (`components/apply_action_bar.html`) next to Submit
  (and keep a Regen affordance there). The resume/cover sections keep only their
  content + per-section regen.
- **Match panel simplification**: drop the "WHAT THEY WANT" column (it
  contradicts the other two). Two refined columns only: **Strengths** and
  **What's missing** — make the content sharper (specific, deduplicated,
  JD-grounded; improve the scorer prompt if that's where the mush comes from).
- **Swipe card is broken**: the main Discover tinder card's alignment is off and
  the score appears twice. Fix: score ONCE at the top; the card body shows
  per-dimension bars + strengths + what's missing (per-dimension is currently
  missing from the card). Screenshot before/after.
- **JD rendering**: the job description on the review page is a raw text blob.
  Render it like a real posting — detect/format paragraphs, bullet lists, and
  section headings (a small server-side formatter or markdown pipeline; escape
  properly, no raw HTML injection).
- **New resume template**: convert my LaTeX OnePage resume **1:1 to Typst** —
  source at `/home/nightwatcher/personal/dev/n8n/resume/cv.tex` (10pt letter,
  0.3in margins / 0.25in top+bottom, Helvetica, small-caps section titles with
  rules, tight itemize, `jobentry`/`educationentry`/`projectentry` layouts).
  Replace `onepage.typ` with it. Keep the `<naavik-meta>` page-count metadata.
- **Header content**: name + ONE contact line with exactly: phone, email,
  location, linkedin, github, portfolio (clickable). NO headline line — no
  "Senior Software Engineer · 7 yrs · AI & personalization", no title, no visa
  notes. Kill the `tailored_headline` from the resume payload (keep the trace
  field harmless or remove the stage).
- **Real density**: the page must be PACKED. If space remains after the
  JD-relevant bullets, add the next-ranked bullets even if not directly relevant
  — an add-back pass after the fit loop (add until adding one more would
  overflow), on top of the denser template. Selected content still leads.
- **Bullet refinement, not just selection**: rewrite each selected bullet
  against the JD — mirror the JD's terminology where truthful (this is the
  trim/refine LLM stage; upgrade `trim_bullet` into a refine-against-JD prompt
  with hard honesty constraints: never invent facts/numbers).
- **One line per bullet**: each bullet must fit one line in the new template
  unless there's a genuinely good reason. Enforce by character budget measured
  against the template's line width; re-refine when a bullet exceeds it.
- **Resume editing in the workspace**: the ledger expansion ("N of M bullets
  selected — see what was kept and why") does nothing when clicked — fix it. Then
  go further: make the tailored resume editable like the cover letter — edit a
  bullet's text for this application, toggle include/exclude
  (per-app `bullet_overrides` machinery already exists), then recompile the PDF.
- **Cover-letter edit 404 bug**: editing a section and saving returns 404 and
  the edit is lost (`/_fragments/apply/cover-letter-section/...` POST →
  `application_service.update_cover_section`). Root-cause it (likely the
  fragment fires for an application/user mismatch or the latest-doc lookup),
  fix, and make save re-render + recompile the letter PDF so the embed matches.

## 3+4+8 — Feedback everywhere (global error/success handling)

- **Global HTMX feedback**: wire `htmx:responseError`, `htmx:sendError`, and
  `htmx:timeout` listeners in `base.js` to the existing toast system so ANY
  failed UI action shows an honest error toast (with the server's `detail` when
  present). Success paths for state-changing actions get success toasts (many
  already send `HX-Trigger: showToast` — make the remaining ones consistent).
  Remove per-form ad-hoc error handling where the global one now covers it.
- **Email "Test & connect" gave no visible feedback** even though it worked —
  the result fragment/toast isn't reaching the user. Fix (this is the item-8
  pattern applied to `/integrations/email`; the form swaps into
  `#connect-gmail-result` then reloads — make the result unmissable).
- **Disconnect on the email account card does nothing** — the hx-delete
  is broken (CSRF header? swap target? confirm dialog?). Root-cause, fix, add a
  route test.

## 5 — Email-inferred application tracking

Today emails only attach to applications Naavik already knows. Make the inbox a
source of truth (decision: **infer + confirm**):

- Detect application-confirmation emails ("thanks for applying", ATS receipt
  patterns from Greenhouse/Lever/Ashby/Workday/LinkedIn, etc.) in the classify
  pipeline (`services/email_classifier.py` or a new inference stage).
- For each inferred application: **create the Job in the Jobs library with
  correct metadata as if scraped** — if the email contains a posting URL, run
  the real scrape/extract pipeline on it; otherwise create the Job from email
  metadata with `source=email` (extend `JobSource` if needed + migration).
  Then create a proposed Application (APPLIED, applied_at from the email date)
  that I **confirm or dismiss in Tracking** (the human-confirm suggestion seam
  from plan 90 is the pattern — reuse/extend it).
- Manually-added library jobs must also match against inbox signals (company +
  role fuzzy match) so a job I applied to myself starts tracking when the
  confirmation email lands.
- Confirmed inferred applications get email-signal status updates like any
  other tracked application.

## 6 — Tracking layout consistency

Switching between Pipeline and Jobs library tabs significantly shifts the page
(header/integration cards/controls jump). Keep the chrome identical across
tabs — same header block, same position for tabs and toolbars; only the main
panel content changes. Screenshot both tabs and diff visually.

## 7 — Auto-apply adapters, rebuilt to actually submit

The point of auto-apply is that Naavik submits for me when the toggle is on.
My manual submit "succeeded" but no confirmation email ever arrived — the
Greenhouse adapter almost certainly never really submitted. Rebuild ground-up:

- **Scope: Greenhouse, Lever, Ashby** (public application forms, no login).
  Workday/LinkedIn/Indeed stay honest `READY_TO_SUBMIT` handoffs.
- Rebuild the three adapters (`services/ats/greenhouse.py`, `lever.py`,
  `ashby.py`) as **Playwright-driven form fillers** against the real public
  apply pages: navigate to the posting's apply form, fill name/email/phone/
  location/links from Profile, upload the tailored resume PDF (+ cover letter
  where the form accepts it), answer screener questions from the prepared
  answers, handle each board's field quirks (Greenhouse `job_application[...]`
  fields + attachments; Lever `resume` upload + cards; Ashby's React form).
  Detect CAPTCHAs and login-walls and fail honestly with
  `FAILURE_CAPTCHA`/`FAILURE_AUTH_REQUIRED` (→ ready-for-you handoff).
- **Verification: dry-run only — do NOT really submit.** Add a
  `submit(dry_run=True)` path that does everything up to the final submit
  click, then screenshots the filled form and returns
  `SubmissionResult(ok=True, dry_run=True, artifacts=[screenshot paths])`.
  Wire `Settings.auto_apply_dry_run` through to this (a dry-run now produces
  REAL filled-form evidence, not just a stamp). Save screenshots under the
  application's documents dir and link them from the Tracking detail.
  Verify live against real Greenhouse + Lever + Ashby postings (pick from the
  library or add by URL) and eyeball the screenshots for field correctness.
- Diagnose my failed manual submit end to end (the old adapter reported ok
  without a board confirmation?) and make `SubmissionResult` require positive
  confirmation evidence (confirmation page/receipt text) before `ok=True`.
- Keep the existing pipeline semantics (queue → docs → validate → submit/
  hand-off) — this item replaces the submission layer only.

## 9 — Generation evaluation harness

Add an evaluation setup that scores every generated bundle against our
guidelines, so quality regressions are visible:

- **Deterministic checks**: exactly 1 page; contact line completeness; bullets
  ≤1 line; no blocklisted AI-tell phrases; first-person cover letter (no
  third-person name references); parse-fidelity score (exists); keyword/buzzword
  coverage vs the JD (exists — surface it).
- **LLM-judge rubric** (tracked via `llm_tracker`): ATS-friendliness, JD keyword
  usage, honesty vs profile, tone. Output a per-bundle scorecard persisted into
  `generation_trace` and rendered in the workspace (small "quality" chip →
  details), plus a pytest-runnable eval (`tests/eval_*` or a `scripts/eval`
  entry) over 2–3 seeded jobs so we can compare before/after prompt changes.
  Keep it cheap (one judge call per bundle) and skippable when no provider.

## 10 — LLM model routing bug

Settings shows `gpt-5.4-mini` selected but every call hits `gpt-4o`. Find where
the chain breaks: `Settings.llm_provider` / `llm_model` → `llm/__init__.py:get_provider`
→ `llm/openai.py`. Known smells: user 3 has `llm_provider=ANTHROPIC` (no key) with
OpenAI fallback that likely uses a hardcoded default model instead of
`settings.llm_model`; the Settings UI may write the model without switching
provider. Fix so the SELECTED provider+model is what's actually called (and the
fallback uses the selected model when it belongs to the fallback provider);
verify via `ApiUsage` rows (`model` column) after a real generation.

## 11 — Google Calendar via secret ICS URL

The Calendar "Connect" button on Tracking does nothing. Google killed basic
auth for CalDAV, so mirror the Gmail one-screen pattern with the **secret ICS
address** (read-only; decision made):

- One card on `/integrations/email` (rename the page "Integrations" if that's
  cleaner): paste the private ICS URL (Google Calendar → Settings → your
  calendar → "Secret address in iCal format"), with a 2-step walkthrough +
  direct link. Validate + fetch it server-side before saving (SSRF-guard the
  URL like the IMAP host guard; https only, no private IPs), store encrypted
  (Fernet, like the IMAP credential), sync on a cron (30–60 min) into a small
  `CalendarEvent` model (+ migration).
- Surface upcoming events: interviews matched to applications (company/name
  fuzzy match) show on the Tracking detail + a small "upcoming" strip where it
  fits naturally. Read-only; event creation is documented as a future OAuth
  follow-up in `docs/design/EMAIL_MONITORING.md` (add a § for calendar).
- Fix the dead Connect button either way (point it at the new card).

## Definition of done

Every item root-caused and implemented (no fake data, honest empty states),
targeted tests added, `ruff` + `pytest` green, and a live browser pass as the
seeded user covering: profile edited end-to-end without a resume upload (add an
experience + certification, see it in the next generated resume) → Discover
card + review page render the inverted identity and simplified match columns →
generate from the action bar → dense 1-page resume on the new template (packed,
one-line bullets, refined-against-JD wording, no headline junk) → edit a resume
bullet + a cover-letter section and see the PDFs update → dry-run a Greenhouse
AND a Lever application and inspect the filled-form screenshots → email
disconnect/reconnect with visible feedback → an inferred application from a
real confirmation email lands in library + Tracking for confirmation → tabs
don't shift → eval scorecard visible on a fresh bundle → ApiUsage shows the
selected model → ICS calendar connected with events visible. Shut down anything
long-running you started. Finish with a short summary: what changed, what you
verified live, what remains.
