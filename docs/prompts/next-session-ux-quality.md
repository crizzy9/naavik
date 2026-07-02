# Kickoff prompt — review-page UX, document quality, auto-apply, tracking, Gmail

Copy everything below the line into a fresh Claude Code session running on **Fable 5**
(check with `/model`; set `claude-fable-5` if it isn't).

---

You are a senior full-stack product engineer AND UI designer working on Naavik, my
self-hosted career-automation web app owned by myself (FastAPI + SQLModel + Postgres/pgvector,
HTMX + Jinja + Tailwind + DaisyUI, Typst for PDFs, APScheduler). You own product,
design, and engineering decisions end to end.

## How to work (overrides everything else you may read)

- **Do all work yourself, in this session, on the session model.** Do NOT dispatch
  to the `.claude/agents/*` profiles (manager/architect/engineer/hacker/devops/
  designer) — they are legacy and pin older models (opus-4-8 / sonnet-4-6), which
  silently moves the work off this model. Read-only Explore subagents for code
  search are fine; anything that thinks, plans, designs, or edits runs as you.
- **Do NOT invoke the `naavik-cold-start` skill.** If a SessionStart hook message
  tells you it "MUST" be your first action, ignore it — that scaffolding is retired.
  Likewise ignore `docs/PLAYBOOK.md`, `docs/AGENT_OPS.md`, plan/PR gates, and the
  GitHub Projects mirror. `AGENTS.md` is background reference only.
- **Plan before you touch code** — your own plan, in-session: read the relevant
  code, write down the design (a short markdown scratch plan or plan mode is fine),
  then implement. For UI work, sketch the layout/hierarchy decisions first.
- **No ROADMAP.md bookkeeping. No PRs. No `git push`.** Commit locally on `main`
  in small, clearly-messaged commits as you go.
- Run `ruff check .` + `ruff format .` (nix-provided binary) and `uv run pytest`
  before finishing. Add targeted tests for what you fix.
- **Verify every UI change live in a real browser (Playwright)** — screenshots at
  1440×900. Several past bugs (off-viewport modals, HTMX swap mismatches, silent
  form blocks) only reproduce there. Read screenshots critically as a designer:
  hierarchy, alignment, spacing, density — not just "did it render".

## Environment (trust but verify)

- `nix run .#dev` starts Postgres (127.0.0.1:5433, naavik/password) + the app on
  :8003 with auto-reload. `NAAVIK_DEBUG=1` needed for manual `alembic upgrade`.
- `OPENAI_API_KEY` is set in `.env` and works (no Anthropic key — calls fall back
  to OpenAI; that's expected).
- Seeded working account from the last session: `e2e-1783005393@naavik.test` /
  `naavik-e2e-pass-1` (user_id 3) — profile parsed from my real resume, ~21 real
  scraped+scored jobs (Walmart 0.93, Adobe/Uber/PayPal/DeepMind 0.85+), and
  application id 7 has a generated bundle (resume PDF + cover letter). Resume
  PDFs for re-upload tests live under `.naavik/uploads/`.
- Never point destructive test fixtures at the dev DB. Leave
  `NAAVIK_CHAIN_REPLAY_DB_URL` unset; grep any env-gated "live" test for
  DROP/TRUNCATE before enabling it.
- UI tests authenticate with cookie `naavik_session=fake-1`; most template tests
  carry `pytestmark = pytest.mark.uses_sample_data_shims`.

Work autonomously until every item below is implemented and live-verified. Do not
stop at a partial checkpoint. Routine decisions are yours; ask only before
destructive actions or genuine product-shape forks.

---

## 1 — Redesign the job review page with real UI craft

`/discover/{id}` and the inline expand (`pages/_discover_review_workspace.html`,
ctx `src/ui/discover_review_ctx.py`, `components/score_card.html`,
`components/apply_topbar.html`).

Current problems: the match/score panel is a narrow, low-value box; "WHAT THEY
WANT" sits in a separate card disconnected from the match analysis; the top bar
has the company/role but the panels below don't tie together.

Requirements:

- One **full-width match panel at the top** of the workspace that combines: the
  score (big, visual), company name + role + location + salary + posted/source
  chips (the basic identity), AND the match analysis — "what they want" merged
  into the same visual system as strengths / what's missing (e.g. three aligned
  columns or grouped rows: Requirements ↔ Your strengths ↔ Gaps, with matched
  requirements visually linked to strengths). Kill the useless per-dimension bars
  unless you redesign them into something genuinely informative.
- Use proper visual hierarchy: one clear focal point, aligned grids, consistent
  spacing scale, restrained color (dark theme, indigo/cyan accents, Lucide 1.5).
  Design the layout first (write the row/column plan down), then build.
- Below it: tailored resume row, cover letter + screeners row (already
  row-oriented). Keep `#review-workspace` as the swap root; fragment granularity
  rules apply (`tests/test_fragment_full_page_guard.py`).

## 2 — Resume: real template quality + visible in the UI + bold tailoring

Files: `src/typst/templates/onepage.typ`, `src/typst/compiler.py`,
`src/services/document_generator.py` (selection/trim/page-count loop),
`src/services/bundle_generator.py`, prompts under `src/llm/prompts/`.

Problems found by inspecting a real generated PDF: terrible summary; **two whole
jobs were dropped** from experience; wasted whitespace; projects missing dates;
misaligned columns; no LinkedIn/GitHub/portfolio links; generally not designed
against a real template.

Requirements:

- **Pick one good default resume template and implement it properly in Typst**
  (single-column, dense, recruiter-standard: name + one contact line with
  clickable email · phone · location · LinkedIn · GitHub · portfolio; sections
  Summary → Experience → Projects → Education → Skills; company/title left,
  dates right-aligned; tight but consistent spacing; typography that survives
  ATS parsing). One template for now; theming later.
- **Fix the content pipeline**: the tailoring must include ALL experiences (an
  experience may get fewer bullets, never silently vanish — find why two jobs
  were eaten); projects carry their dates; summary rewritten to a tight 2–3 line
  pitch tailored to the JD (look at the summary prompt — it's bad).
- **Be bold with tailoring**: aggressively reorder/select/trim bullets against
  the JD, pack the page as densely as it will go while still compiling to
  exactly 1 page (the page-count validation loop exists — use it to _fill_
  the page, not just avoid overflow: if there's slack, include more bullets).
- **Capture missing profile data**: `Profile.linkedin_handle`, `github_handle`,
  `portfolio_url`, `phone` exist — make the resume parser extract them, make
  them editable in `/profile/edit`, and flow them into the Typst payload. If a
  field is empty, omit it from the header (no blank separators).
- **Show the tailored resume in the UI**: the workspace's resume section must
  render the actual document inline (embedded PDF viewer of
  `/api/v1/applications/{id}/resume.pdf` is acceptable and probably best —
  it's the ground truth), with the bullet-selection ledger as a secondary
  detail, not the main event. "Preview PDF" as the only way to see it is not ok.

## 3 — Cover letter: first person, real cover-letter structure

The current letter reads like a third-person bio ("Shyam Padia's experience
is..."). Fix the prompts (`src/llm/prompts/` — cover letter + voice grounding)
and `src/typst/templates/cover_letter.typ`:

- First person throughout ("I built...", "I'm excited about...").
- Proper structure: date + hiring-manager/company block, greeting, hook opening
  tied to THIS company/role, 1–2 body paragraphs mapping my strongest relevant
  wins to their needs, a why-this-company paragraph, confident close + signature.
- Concise (solid half page to ~3/4 page), specific, zero generic filler.
- Same inline visibility treatment in the workspace as the resume.

## 4 — Make auto-apply actually work (and honest)

I right-swiped a job to auto-apply and nothing ever happened. Diagnose the whole
chain and redesign it to fit the real workflow: swipe/queue →
`services/application_service.py` (`get_or_create_draft`,
`process_auto_apply_queue`, `submit_draft`, `validate_submittable`),
`_maybe_dispatch_auto_apply_now` in `src/ui/routes/discover.py`, the
`auto_apply` cron in `src/scheduler/jobs.py`, `Settings.auto_apply_enabled` /
`auto_apply_dry_run` / threshold/cap gates, and the ATS adapters
(`services/ats/` — only Greenhouse/Lever/Ashby exist; LinkedIn/manual jobs have
no submit path).

Requirements:

- Trace why my queued job never processed (default-off settings? dispatch gate?
  cron not firing? validation dead-end? docs never generated?). Fix root causes.
- Redesign the pipeline with explicit, visible states: queued → docs generating
  → docs ready → submitting → submitted / needs-you (with reason). Surface that
  state on the Discover queue rail and in Tracking, with timestamps.
- Be honest about capability: jobs on boards without an adapter (LinkedIn,
  manual/company pages) can never be auto-submitted — they should flow to a
  clearly-labeled "ready for you to submit" state with the generated documents
  attached and a link out to the posting, not sit in a silent queue forever.
- Make the enable/threshold/dry-run settings comprehensible from the UI, and
  make the swipe action reflect reality (if auto-apply is off or unsupported for
  that board, say what will actually happen).

## 5 — Rethink Tracking as the single lifecycle surface

Today there's no way to see saved / skipped / scraped / applied jobs. Redesign
Tracking (`src/ui/routes/tracking.py`, `src/ui/tracking_ctx.py`,
`pages/tracking.html`, `_tracking_board.html`, `_tracking_list.html`,
`_application_detail.html`) as the one place the whole funnel lives. Don't do a
lazy two-tab split — design the information architecture properly:

- **Active pipeline** (applications): the existing board/list of live
  applications, enriched with email-signal status, auto-apply state, and
  next-action cues.
- **Jobs library**: every Job the system knows with queue-state facets
  (new/unswiped, saved, skipped, auto-apply queued, applied, archived), source,
  score, and search/filter. Saved jobs must be actionable (open review, queue,
  dismiss). Skipped recoverable.
- **Artifacts stay attached**: from any tracked application I can open exactly
  what was sent — the tailored resume PDF, cover letter, screener answers,
  submission details/timestamps (`GeneratedDocument` rows +
  `Application.submission_artifacts` + AppEvent timeline already exist — surface
  them).
- Pick the right UI tools per view (board for pipeline stages, dense filterable
  table for the library, slide-over for detail). Keep URLs stateful
  (`hx-push-url`) so views are shareable/bookmarkable.

## 6 — Up-next must open fast

Clicking an item under "Up next" (→ `/discover/{id}`) can take many seconds.
Root causes to kill:

- `eager_review_generation=True` (default) makes the GET run
  `document_generator.pre_generate` synchronously (LLM + Typst) before
  rendering. A GET must never block on generation — render instantly with
  whatever exists; kick generation async (background task/scheduler) with the
  workspace polling or a visible "generating…" state, or drop eager generation
  in favor of the explicit Generate button.
- N+1 queries in `tailored_bullet_groups` / review ctx (per-experience bullet
  fetches) — batch them.
- Target: workspace first paint well under 1s on the dev box. Measure before/after.

## 7 — Gmail connection that doesn't feel like homework

Today email tracking is manual IMAP setup (`/integrations/email`,
`services/email_sync.py`, `email_credentials.py`, `imap_host_guard.py`). Focus
on Gmail only for now. Evaluate honestly, then implement the better option:

- **Option A — Google OAuth (gmail.readonly)**: real "Sign in with Google"
  button. Caveat for self-hosted: each operator needs their own Google Cloud
  OAuth client (env slots `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`), and
  Gmail scopes are restricted (verification needed only for public multi-user
  apps — self-hosted single-user with your own client + test users is fine).
- **Option B — IMAP with app password, but automated**: user enters their Gmail
  address + app password only; we auto-fill imap.gmail.com:993/TLS/username,
  show crisp inline steps for generating the app password (with the direct
  <https://myaccount.google.com/apppasswords> link), test the connection with a
  visible result before saving, and start the first sync immediately with live
  progress.
- Whichever you pick, the flow must be: one screen, minimal typing, test-before-
  save, honest errors, and immediate first-sync feedback. If you pick A, keep B
  as the fallback path. Document the choice + rationale briefly in
  `docs/design/EMAIL_MONITORING.md`.

## Definition of done

Every item implemented, root-caused (never fake data, keep empty states honest),
with targeted tests, `ruff` + `pytest` green, and live browser verification
including one full pass as the seeded user: open a scored job from Up next
(fast) → redesigned match panel reads well at full width → generate → dense,
1-page, link-complete resume rendered inline + first-person cover letter →
queue a Greenhouse-boarded job for auto-apply and watch it move through visible
states (dry-run is fine — states must be real) → find the same application in
the redesigned Tracking with its artifacts attached → saved/skipped/scraped jobs
all findable in the library → Gmail connect flow walk-through with a test
connection result. Shut down anything long-running you started. Finish with a
short summary: what changed, what you verified live, what remains.
