---
Type: research
Authored: 2026-05-19
Source: WebSearch + WebFetch on usesprout.com (8 pages) + 2 third-party reviews
Run-id: 2026-05-19T05-40-56_194aa5
Confidence: H (public marketing + 2 independent reviews + privacy policy + employer-side site all directly accessible; only unknowns are internal model/cost structure and exact ATS coverage list)
---

# UseSprout — strategic comparison + lessons for Naavik

## TL;DR

UseSprout (brand: **Sprout**, `usesprout.com`, formerly `Prep AI`) is a closed-source SaaS AI-apply tool at **$19.99–$99.99/mo**, mobile-first with a swipe-to-apply UX, app-quota-metered (80 / 200 / 600 apps per month), 750k+ signups / 150k+ active users, that **also runs an employer side** (`employer.usesprout.com`) charging recruiters **15% of first-year base salary** to access an "850M+ profile" candidate pool — meaning Sprout monetizes both sides of the marketplace, with candidates the data input and employers the buyer. Naavik's strategic positioning sits in the opposite quadrant: **self-hosted, AGPL, BYOK, single-user**, with **no employer-facing surface and no candidate-data monetization path**, which is the moat Sprout structurally cannot copy. The concrete things Naavik should borrow from Sprout — and they are narrow — are the swipe-to-apply UX (already in `SCREENS.md § 7 Discover`, ship it), the **credit-cost-per-apply transparency** ("each submission uses 1-3 credits"), and the **mobile-PWA mindset** as a Phase 6+ consideration; the things to explicitly reject are app-quota pricing, opaque "no manual editing" AI output, and any path that pools candidate data for employer-side analytics.

---

## 1. What UseSprout is

**Canonical identity.**

- Brand name: **Sprout** (formerly *Prep AI* per the Google Play package `ai.magnifex.prepai`).
- Marketing domain: `usesprout.com`. App at `app.usesprout.com`. Employer side at `employer.usesprout.com` (separate domain) + `recruiting.usesprout.com`. Privacy policy at `usesprout.com/legal/privacy-policy`.
- Tagline: **"Stop applying. Start landing interviews."** (homepage hero).
- Stated reach: **750,000+ job seekers**, **150,000+ active users**, **20,000+ interview invitations**, **1M+ applications processed** (about page), **4.8/5 App Store rating**.
- Founded narrative (about page): *"Finding a job today is messy, slow, and overwhelming. Most tools are built for companies — not people."*
- Disambiguation done: this is **NOT** Sprout Social (Twitter/LinkedIn marketing, `sproutsocial.com`), **NOT** Sprouts.ai (B2B sales intelligence, `sprouts.ai`), **NOT** Sprout Network (`sproutnetwork.io`). Confidence: HIGH — README at `README.md:34` already references "Sprout ($20-100/mo) — closest to our vision," confirming this is the entity the user means.

**Audience.** Self-described "active job seekers" spanning new grads to senior executives. The Sprout-for-Employers site targets startups + growth-stage companies that want recruiter-led screening at sub-agency cost. Tier 1 surface (consumer app) is the one Naavik competes with; the employer surface is what Naavik does NOT have (and structurally cannot replicate without becoming a different product).

**Deployment model.** SaaS-only. Web (`app.usesprout.com`) + iOS + Android mobile apps. No self-host, no source available, no browser extension (the marketing claim "Sprout's AI reads each job portal automatically" is the AI-Apply backend running headless, not a Chrome extension).

**Tech stack hints.** Per the privacy policy, Sprout uses **OpenAI, Anthropic, and Google Cloud AI** as third-party AI service providers. The Android package name `ai.magnifex.prepai` suggests an early "Magnifex" product line. iOS bundle ID `id6740011494`. No public source.

---

## 2. Feature surface

Grouped by category. Quoted phrases are exact from `usesprout.com` pages unless tagged `(review)` (third-party `jobcopilot.com` or `autoapplier.com`) or `(unverified)`.

### 2.1 Job discovery

- Aggregated job feed from **"verified company career sites, job boards, and partner networks"** with daily refresh. Marketing claims **"10M+ jobs"** on the homepage.
- Sources are **not named publicly** (no LinkedIn / Workday / Greenhouse list); third-party review (jobcopilot.com) notes Sprout has *"its own"* job board without naming partner ATSes.
- Filters by industry, location, work type (remote / hybrid / on-site). Tinder-style swipe-right indicates interest.
- **"Occasional irrelevant job suggestions"** flagged in the JobCopilot review — matching precision is not their differentiator.

### 2.2 Resume / CV tailoring

- **"Adapts your resume to match each role."** Per-job tailoring is automated, with the AI selecting/rephrasing content to fit the JD.
- **Critical limitation** (JobCopilot review verbatim): *"You can review the documents and request a regeneration, but that's it. There's no way to tweak wording, adjust emphasis, fix small inaccuracies, or tailor content for a specific role."* Manual editing of AI output is unavailable.
- Onboarding collects extensive profile data including **gender, race, full address, disability status, citizenship or visa status, veteran status, sexual orientation, and professional URLs** (JobCopilot review).
- Output is claimed **"ATS-friendly"** with **"no detectable AI signature."** (unverified — no independent ATS-parse rate published.)

### 2.3 Cover letter generation

- **"Personalized, role-specific cover letters generated in seconds."**
- Same no-manual-edit limitation applies — regenerate is the only knob.

### 2.4 Application tracking

- **"Every application, tracked automatically"** with **"real-time status updates."**
- Tracks via Sprout's own delivery pipeline; status seems derived from submit-success and follow-up signals (the privacy policy mentions email integration).
- **Email integration & categorization** flagged as Available in the JobCopilot feature table — implying inbox classification similar to Naavik's planned `0.5.0.02`.
- No public mention of multi-axis state (`docs_state`, `referral_state`, `recruiter_state` as in Naavik DATA_MODEL.md § A).

### 2.5 Auto-apply

- Three-stage backend pipeline (from `usesprout.com/features/ai-apply`): **Detection** ("recognizes and adapts to different job portal formats instantly"), **Filling** ("automatically fills job forms using your profile and resume data"), **Submission** ("send approved applications instantly — Sprout takes care of delivery").
- **Two operating modes:**
  - **Review-first (default-ish):** *"You review, edit, and approve every document before submission."* The "Require Approval" setting gates submission.
  - **One-tap (speed mode):** *"When you see a role you want, just swipe right... Sprout instantly fills and submits."* No per-job approval gate when Require Approval is off.
- **Cost model:** *"Each completed submission uses 1–3 credits from your plan."* Plan tier sets the credit budget (Basic 80 / Pro 200 / Ultra 600 per month).
- **Anti-detection:** No public disclosure. Third-party reviews flag this as an unanswered risk: *"The review does not address whether Sprout implements delays, randomization, IP rotation, or any anti-detection measures. It also does not discuss rate-limiting warnings or account suspension risks."*

### 2.6 Interview prep / pipeline management

- The Google Play page lists *"Interview prep"* as a feature (the legacy `Prep AI` name hints this was the original product surface).
- Specifics not in the marketing pages we fetched; assume basic question banks + JD-driven question generation. (unverified depth.)

### 2.7 Communication (Discord / Telegram / Email / LinkedIn DM)

- **Email integration:** Available (JobCopilot review confirms classification capability).
- **Discord / Telegram / LinkedIn DM:** None mentioned in any public surface we found. Sprout is a **consumer app**, not a notification-routing developer tool — push notifications are app-native.

### 2.8 Analytics / dashboards

- *"Real-time notifications when your application has updates."*
- Public marketing does not surface a response-rate / interview-rate / offer-rate analytics dashboard like Naavik's `Overview` KPI strip (`SCREENS.md § 3` KPI row — `ACTIVE APPLICATIONS · RESPONSE RATE · ONSITE RATE · OFFER RATE`). May exist in-app; not advertised externally.

### 2.9 Browser extension / mobile app

- **No browser extension.** Sprout's autofill runs server-side via headless detection, not as a Chrome/Firefox plugin.
- **Mobile-first:** iOS + Android apps + web app + cross-device sync. Mobile is the lead surface — "86% of candidates start searches on mobile" is their positioning statement vs. desktop-only competitors.
- **Swipe-to-apply** is the signature mobile UX (Tinder pattern). Naavik already adopts this for desktop via `SCREENS.md § 7 Discover` (keyboard `← skip · → auto-apply · ↑ save · ⏎ review`) and `SCREENS.md § 7 Discover` mobile (pointer-event swipe).

### 2.10 Integrations

- **AI providers (server-side, undisclosed selection):** OpenAI, Anthropic, Google Cloud AI per privacy policy.
- **Job boards:** unnamed publicly.
- **Email:** Gmail/IMAP-style (inferred from classification feature, not explicit).
- **Calendar:** Not advertised on consumer side.
- **Employer side (`recruiting.usesprout.com`):** Sources from **"850M+ profiles"** (external data) plus its own **1.2M candidate network**. This 850M number means Sprout itself doesn't generate these — they ingest external data brokers / scraped public sources (e.g., LinkedIn-style profile aggregation).

### 2.11 Target user persona

- Range claimed: *"new graduates to senior executives."*
- Implicit user: someone willing to trade manual control + data-handling caution for speed + automation. The swipe-and-submit flow rewards high-volume, low-customization candidates.
- **Visa-dependent job seekers**: collected as onboarding data (citizenship + visa status) but **not surfaced as a scoring/filter axis** in public marketing — i.e., Sprout asks the question and includes the answer on applications but does not preferentially route visa-friendly roles. **This is Naavik's clearest unique product axis.**

### 2.12 Pricing

| Plan | Monthly | Apps / month | Cost / app |
|---|---|---|---|
| Basic | **$19.99** | 80 | ~$0.25 |
| Pro | **$39.99** | 200 | ~$0.20 |
| Ultra | **$79.99** (intro: $59.99 w/ 25% off) | 600 | ~$0.13 |

- Weekly billing offered at ~25% premium per JobCopilot.
- **No free tier with actual application capability** (jobcopilot: *"No free trial — requires payment before testing core features"*).
- **AI cost model:** Subsidized — credit pricing is the user-visible knob; no BYOK option.
- **Cancellation:** *"No contracts. No surprises"* + a refund link exists; specific policy not surfaced on pricing page.

### 2.13 Trust / safety positioning

- *"Your data and applications stay encrypted and protected"* + a "Secure by Design" label on the homepage.
- Privacy policy explicitly states: **"will not sell or share personal information"** for the consumer side.
- **BUT** the policy also discloses: AI inputs are shared with **OpenAI, Anthropic, Google Cloud AI**; and information **"may be shared with affiliates and business partners to offer users certain products, services, or promotions."** The employer-facing 850M-profile claim plus the consumer-side data collection (including EEO/visa) raises a real **information-asymmetry concern**: Sprout's privacy stance is good vs. data brokers, but the boundary between "our employer service" and "our candidate data" is structurally porous.

### 2.14 Employer-side business model (DOUBLE-SIDED MARKETPLACE)

- **Recruitment-as-a-service** at **15% of first-year base salary** on hire (vs. 20-30% traditional agencies). $500 activation deposit per role.
- AI does *"prep, notes, and skill verification in the background"* during human-led recruiter screening calls.
- 90-day replacement guarantee + fraud detection.
- **Strategic read:** Sprout's economics work because the candidate-side $20-100/mo is acquisition + qualifying funnel; the real revenue lever is the employer-side hire fee. This means Sprout's product incentives diverge from candidate optimization — they want **engaged candidates** (signups, applies, interviews) more than they want **placed candidates** (where hires are concentrated into Sprout's recruiting service rather than auto-applies to external boards).

---

## 3. Comparison table

Naavik's column splits "current" (shipped per ROADMAP `0.1.0` foundation + MVP) from "planned" (`0.2.0`–`0.6.0`). UseSprout's column reflects publicly-verifiable state as of 2026-05-19.

| Capability | Naavik (current — 0.1.0) | Naavik (planned 0.2.0–0.6.0) | UseSprout | Gap / Lesson |
|---|---|---|---|---|
| **Job discovery sources** | None scraped yet; n8n legacy feed running | LinkedIn (guest API + Crawl4AI stealth + RSShub fallback), Workday, Greenhouse, Lever, Ashby, Indeed (`0.2.0.07`) | "Verified company sites + job boards + partner networks" — undisclosed | UseSprout doesn't name sources, which is a **trust gap** Naavik should exploit: ship a public per-source coverage matrix in `docs/DEPLOYMENT.md` or a `/sources` page. |
| **Job dedup** | n/a | URL + fuzzy title/company (`0.2.0.09`) | Implicit, not advertised | No lesson — Naavik already plans this. |
| **AI extraction (HTML → structured job)** | n/a | Crawl4AI + LLM structured output (`0.2.0.08`) | Server-side, undisclosed | No public gap. |
| **Score / explainability** | n/a | Tag-based + LLM with structured `Job.score_explanation` + per-dimension breakdown rendered as bars (`0.3.0.01` + `SCREENS.md § 7` `MATCH · 0.86` + per-dim) | Implicit matching; "irrelevant suggestions" per JobCopilot review; no explainability | **Naavik's moat.** Sprout swipes; Naavik shows *why* a job is 0.86 with `ai-ml 0.95 / platform 0.88 / leadership 0.82 / visa 0.70`. Ship the score-explanation bar early in `0.2.0.11`. |
| **Visa / sponsorship filter** | EEO/visa Qs captured in onboarding + Profile editor (`#application-qs`) and **rendered prominently** in Profile mobile hero as "H1B · Requires sponsorship" | Auto-filter: **score 0 for citizenship-required / no-sponsorship** (`0.3.0.03`) | **Collects visa status as form data; does NOT score on it** | **Largest competitive differentiator.** Naavik's owner profile is H1B+i140-pending (`AGENTS.md § Owner Profile`); the visa-aware scoring axis is uniquely valuable to ~1M H1B holders and millions of OPT/STEM-OPT users that Sprout treats as homogeneous. Lead with this in marketing copy and in `Discover` per-dimension match bar. |
| **Resume tailoring** | Phase 1 Typst pipeline; single long-form bullet + AI trim at apply time + 9-tag selection + `selection_override` (`SCREENS.md § 6`) | Tag-based bullet selection per JD; preview which bullets shipped (`0.3.0.04`) | Auto-tailored; **no manual edit of AI output** | **Naavik wins on user control.** Sprout users cannot adjust AI emphasis; Naavik's bullet editor (Section 6) is the explicit counter — long-form source + AI trim + override pins. Document this in README "Why Naavik wins" row. |
| **Cover letter** | Typst pipeline shipped in Phase 1; manual edits supported | LaTeX deferred to `0.6.0.06` | "Personalized, role-specific cover letters generated in seconds"; **no manual edit** | Same lesson — user-edit is Naavik's lever. |
| **Application tracking** | Multi-axis state (`status` + `closed_reason` + `docs_state` + `referral_state` + `recruiter_state`) per `DATA_MODEL.md § A` | Polish + analytics (`13a-tracking-polish`) | Single-status timeline; auto-updated from email | Naavik already richer. Ship the multi-axis state visualization in `Tracking` board view. |
| **Auto-apply** | Phase 1 Wave 6: semi-auto + auto-apply via Greenhouse / Lever / Ashby ATS adapters; DRAFT-lifecycle state machine | Workday + LinkedIn + Indeed + Generic adapters (`0.2.3.01`); postmortem-on-failure (Playwright screenshot + AI summary, `0.2.3.02`); rate-limit dial (`0.2.5.01`) | Two modes (review-first vs. one-tap), credit-cost 1-3 per submit, no anti-detection disclosure | **Audit-trail differentiation.** Sprout users don't know what shipped; Naavik's per-application `services/llm_tracker` + DRAFT lifecycle + ATS adapter logs give a forensic trail self-hosters can grep. Make this a visible Settings tab in `0.4.0`. |
| **Email monitoring + classification** | n/a | Gmail/Outlook OAuth + AI classifier (`0.5.0.01`–`0.5.0.03`) | Available (per JobCopilot) — auto-updates app status from email | **Naavik gap to close.** Sprout has shipped what Naavik plans for `0.5.0`. Don't defer — once `0.2.0.X` clears, email is the next "this just works" moment. |
| **Outreach (LinkedIn / referral)** | n/a | LinkedIn DM + referral request templates (`0.5.0.10`–`0.5.0.14`) | None mentioned | **Naavik's planned moat.** Sprout has no outreach surface. If Naavik ships `0.5.0` outreach + the warm-intro finder (`0.5.0.14`), that's a capability Sprout would need a separate product to match. |
| **Browser extension** | None | None planned | None (server-side autofill instead) | No lesson. |
| **Mobile app** | None — responsive web (HTMX + Tailwind, mobile tested per `SCREENS.md` mobile specs) | None on roadmap | iOS + Android + web, cross-device sync; lead surface | **Strategic question for Phase 6+:** does Naavik need a mobile app? Likely not — self-hosters access via mobile browser to their Tailscale/VPN'd instance. **But:** a PWA manifest + offline-aware swipe UX would close 80% of the mobile gap for ~1 engineer-week, no native build required. File as `0.6.0.08` consideration. |
| **Self-hosting** | Docker Compose + NixOS module + `nix run .#dev` orchestrator (`README.md § Quick Start`) | Add OIDC self-hosted (`0.2.1.02`) | **None** — SaaS only | **The moat.** Sprout cannot self-host without becoming a different company. Privacy-conscious, EU/GDPR-mindful, enterprise-air-gapped users have no path to Sprout. |
| **Cost model** | $0 self-hosted; cloud tier $15/mo BYOK | Same | $19.99 / $39.99 / $79.99 — **app-quota-metered, no BYOK** | **Naavik's BYOK is a structural win.** Self-hoster uses Ollama for $0 / month; cloud user pays Anthropic/OpenAI directly for actual usage. Sprout's model rewards them for under-delivering (low credit consumption = high margin). |
| **Data ownership** | Yours — Postgres on user infra | Same | Sprout-hosted; users have data-subject-access rights but data is co-mingled with their AI vendors (OpenAI/Anthropic/Google Cloud) + employer recruiting pipeline | **Trust delta.** Naavik can never share your data with employers because there's no Naavik to share it with. |
| **License** | AGPL-3.0 | Same | Proprietary | Open source signal matters less than self-host capability but matters for B2B + enterprise adoption. |
| **Profile data collection scope** | Resume-extracted + EEO/visa Qs (kept private per `SCREENS.md § 5` note: *"We never share these outside Naavik"*) | Same | Includes gender, race, full address, disability, visa, **sexual orientation**, veteran status (JobCopilot review) | **Naavik must NEVER collect orientation/race/disability beyond EEO compliance fields.** Sprout's onboarding collects more than Naavik does — Naavik's narrower scope is a feature, not a gap. |
| **AI provider choice** | Anthropic + OpenAI + Ollama (`AGENTS.md § Tech Stack`) | Same | OpenAI + Anthropic + Google Cloud AI — **server-side, no user choice** | Naavik's BYOK + Ollama is the response to "lock-in concerns." |
| **Auto-detection / anti-bot** | Phase 1: random delays + crawl4ai stealth | Anti-detection (`0.2.0.13`) + rate-limit dial (`0.2.5.01`) | Undisclosed | Both have it; Sprout's opacity is the lesson — Naavik should be **transparent** about rate limits in Settings UI ("scraper aggressiveness: conservative / normal / aggressive" with the implications spelled out). |
| **Cost transparency / tracking** | Per-LLM-call `ApiUsage` rows via `services/llm_tracker.tracked_call(...)`; `Settings.daily_llm_cost_cap_usd` enforcement (Wave 6) | Settings cap-progress UI (`0.2.5.03`) | Credits abstraction — user sees "X credits left" not "$Y in AI spend" | **Naavik's per-call dollar visibility is a developer-tool advantage.** Make the Wave 6 cost-cap widget visible early. |
| **Employer-side surface** | None | None | **15% hire fee on the employer recruiting service** at `employer.usesprout.com` | **Naavik must NEVER add this.** Single-user self-host + AGPL precludes the marketplace model structurally. Document this as a non-goal in `README.md § Why Naavik wins`. |

---

## 4. Strategic insights

### 4.1 What to consider adopting

**Credit-cost transparency per apply.** Sprout publishes *"each completed submission uses 1-3 credits"* — a per-apply cost they own. Naavik already tracks LLM cost per call via `services/llm_tracker.tracked_call`, but exposes it as a daily cap not a per-application figure. Adding a per-application USD readout in the `Tracking` row footer (or in the Discover card before swipe) — *"this application will cost ~$0.18 in AI"* — closes the Sprout transparency gap and underlines Naavik's BYOK story (users see the actual provider invoice, not a markup). One-line addition to `services/llm_tracker.py` rendering layer; can land alongside `0.2.0.11` Discover UI or after as a polish item.

**One-tap-vs-review mode toggle.** Sprout's two modes (Require Approval ON vs. OFF) is the cleanest UX framing of the same thing Naavik has in Phase 1 Wave 6's semi-auto vs auto-apply (`0.4.0.03` + `0.4.0.04`). The naming "Review-first" / "One-tap" is more intuitive than "semi-auto / auto-apply." Borrow the wording for `Settings.auto_apply_threshold` UI.

**Mobile PWA as a `0.6.0.08` candidate.** Naavik's stance is "self-hosters use a mobile browser to their VPN'd instance." That's correct, but the friction is real — no home-screen icon, no offline-aware swipe queue, no push notifications. A PWA manifest + service-worker for the Discover queue is ~3-5 days of engineer work and turns the mobile experience from "open browser, type URL, log in" into "tap icon." Don't build a native app, but **don't leave mobile at "responsive web only" forever.** File as `0.6.0.08` (new row) under `0.6.0`.

**Email classification ships sooner.** Sprout already classifies inbound email and auto-updates application status (per JobCopilot review). Naavik plans this for `0.5.0.02` — after `0.2.0` (scrapers), `0.3.0` (scoring), `0.4.0` (auto-apply polish). That's two phases of delay before users get a feature Sprout shipped. Consider pulling `0.5.0.01`+`0.5.0.02`+`0.5.0.03` (Gmail/Outlook + classifier + auto-status-update) earlier — possibly into a `0.4.0`/`0.5.0` overlap — once `0.2.0` scrapers stabilize. The friction is OAuth scope review + classifier accuracy tuning, not architecture.

### 4.2 What to explicitly reject

**Reject app-quota / credit pricing.** Sprout's tier structure (80 / 200 / 600 apps / month) is a margin-defense mechanism, not a user benefit — apps cost them ~$0 marginal (an LLM call + an HTTP POST). For Naavik, BYOK eliminates the upstream margin question entirely: users pay their AI provider directly, Naavik takes $15/mo flat (cloud tier) regardless of usage. Never introduce per-application metering. ROADMAP doesn't propose this; the rejection here is a guardrail against future feature creep that would erode the BYOK story.

**Reject server-side opaque AI output without manual edit.** Sprout's "regenerate is the only knob" is a UX defect dressed up as automation. Naavik's `SCREENS.md § 6` bullet editor (long-form source + AI trim + selection_override pins) is the explicit anti-pattern. Maintain "the AI is your collaborator, you are the author" as a product principle in `DESIGN.md § voice` (already implicit in the dark-mode-developer-tool ethos; make it explicit).

**Reject any employer-side surface or candidate data pooling.** Sprout's 850M profile pool feeding the 15% hire fee is the real revenue model. The structural risk for a SaaS career platform is exactly this: candidate data becomes inventory for recruiter sales. Naavik's AGPL + self-host stance means it physically cannot do this — there's no central inventory to monetize. Codify in `README.md § Why Naavik wins` as a non-goal: "Naavik will never have an employer-facing product. Your data does not become inventory for anyone."

**Reject undisclosed source lists.** Sprout's *"verified career sites + partner networks"* without naming names is a trust gap. Naavik should publish per-source coverage in `docs/DEPLOYMENT.md` (or a dedicated `docs/SOURCES.md`) with: source name, scraping method (guest API / Crawl4AI / Playwright), refresh cadence, known limitations, anti-detection notes. This is the documentation Sprout structurally cannot match because their list is competitive surface.

**Reject onboarding data collection beyond EEO necessity.** Sprout collects sexual orientation and disability status. Naavik's profile editor already limits the EEO section to U.S.-application-required fields (`SCREENS.md § 5` `#application-qs`). Hold this line — orientation and disability are sensitive even when the user "consents" during onboarding. Document the data-minimization stance in `docs/design/PROFILE.md` or as a `# scope` note in `models/application_questions.py`.

### 4.3 Naavik's moat (what UseSprout structurally cannot do)

1. **Self-host first.** Sprout would need to rewrite as on-prem to match; they have no incentive because their 15% hire-fee model requires SaaS data centralization. Self-host removes 100% of the data-leak risk profile that Sprout's privacy policy admits exists (OpenAI/Anthropic/Google Cloud co-mingling + employer-side affiliates).

2. **Visa-aware scoring as a first-class axis.** Sprout collects visa status; Naavik **scores on it** (`0.3.0.03` — score 0 for citizenship-required). The H1B / OPT / STEM-OPT cohort is 1M+ U.S. job seekers, all currently underserved by generic auto-apply tools. The owner-as-target-user (`AGENTS.md § Owner Profile`: Shyam Padia, H1B+i140) is itself the design lens.

3. **BYOK, single-flat-fee economics.** $15/mo cloud OR $0 self-host with bring-your-own AI key — Sprout cannot match without canceling their gross margin model. Naavik's cost story scales with user AI usage (which the user pays directly), not with platform subscription seat count.

4. **No marketplace data flywheel.** AGPL + self-host means there's no candidate pool that can be monetized to employers. Sprout's 850M profile inventory is what funds their 15% hire fee; Naavik structurally can't accumulate this. Frame as a feature: *"Your data does not become someone else's product."*

5. **Multi-axis state + audit trail.** Naavik's `DATA_MODEL.md § A` multi-axis Application state + `services/llm_tracker` per-call cost audit + per-application ATS adapter logs is grepable forensic detail Sprout's consumer-app UX hides. Self-hosters who need to debug a stuck application or audit a recruiter-facing submission have everything; Sprout users have a status pill.

6. **Owner-as-target-user.** Naavik's owner is the primary user and the design eats his pain (H1B visa scoring, NEU resume template, 5.5+ years at Intuit narrative). Sprout serves an abstract "active job seeker." The narrower the persona, the sharper the product. (Marketing copy already names this in `README.md § Why Naavik`.)

### 4.4 Roadmap implications

**`0.2.0` (scrapers, current queue) — no structural change.** UseSprout's existence doesn't argue for a different scraping strategy. The LinkedIn guest API + Crawl4AI stealth + RSShub fallback recommendation per `docs/design/research/LINKEDIN_SCRAPING.md` is unchanged. Publish a per-source coverage matrix when shipping `0.2.0.11` (Discover UI) so users see the gap between "we support LinkedIn" and "we successfully scraped 87% of LinkedIn JD pages in the last 24h."

**`0.2.0.11` (Discover UI) — borrow the swipe-card cost readout.** Add a *"~$0.18 AI to apply"* line near the auto-apply button on the swipe card. ~30 LOC. Lands as a deviation of the existing `0.2.0.11` plan or as a follow-up paper-cut row.

**`0.3.0` (scoring) — lean hard into visa-aware scoring + per-dimension explainability bars.** The marketing copy and screenshot of the Discover card's `MATCH · 0.86` breakdown is the single strongest "why Naavik over Sprout" image. Make sure `0.3.0.02` ships the per-dimension bars not just an overall score; make sure `0.3.0.03` (visa filter) ships as a hard score-zero with a visible "filtered: requires citizenship" badge, not a hidden filter.

**`0.4.0` (auto-apply polish) — adopt Sprout's "Require Approval" wording.** Rename Naavik's semi-auto / auto-apply toggle to "Review first" / "One-tap" or similar — Sprout's framing is clearer. UI string only.

**`0.5.0` (email + outreach) — consider pull-in.** Sprout already ships email classification + auto-status. Naavik's plan is sequenced after `0.4.0`. If `0.2.0` and `0.3.0` clear faster than budgeted, consider overlapping `0.5.0.01`–`0.5.0.03` (Gmail/Outlook + classifier + auto-status-update) into the tail of `0.4.0`. Outreach (`0.5.0.10`–`0.5.0.15`) is the moat extension and stays sequenced.

**`0.6.0` (polish) — add `0.6.0.08` PWA manifest + service worker.** New row, ~3-5 engineer days. Closes the mobile gap without a native build. Push notifications via web-push to existing Discord/Telegram is a Phase 6 polish; PWA manifest is the price of admission.

**New non-goal to document.** Add to `README.md § Why Naavik wins` (or as a "What Naavik will never be" section): *"Naavik is single-user, self-hosted, candidate-first. It will not have an employer-facing surface. Your data does not become inventory for anyone."* This is the Sprout-counter-positioning made explicit.

---

## 5. Implications for `0.2.0.05` Job + StatusHistory model design

**Soft input — non-blocking** for plan 27 (which architect B is authoring in parallel for `0.2.0.05`). Surface as suggestions, not directives.

### 5.1 Fields the Sprout surface implies Naavik's Job model should carry

Most of these are already in Naavik's planned schema per `docs/design/DATA_MODEL.md`; flagging for explicit cross-check during plan 27 review:

- **`posted_at`** (datetime, indexed): Sprout claims "daily refreshed" feeds; Naavik wants this for stale-job filtering + cron freshness signals. Index on this for "show me jobs posted in last 48h" queries.
- **`source`** (enum: `linkedin` / `workday` / `greenhouse` / `lever` / `ashby` / `indeed` / `manual` / `n8n_legacy` / `rsshub`): Per-source coverage matrix needs this for the public/internal dashboard.
- **`source_url`** (str, unique): Canonical apply-on URL. Dedup key per `0.2.0.09`.
- **`apply_url`** (str, nullable): Direct apply endpoint if different from listing. Some ATSes split listing-URL from apply-URL.
- **`ats_type`** (enum or nullable str): `greenhouse_io` / `lever_co` / `ashby_hq` / `workday` / `custom`. Required for ATS adapter dispatch (`0.4.0.05`).
- **`visa_friendly`** (nullable bool, default null = unknown): NOT extracted from JD text in `0.2.0.08` initial cut; populated by `0.3.0.03` scoring pass. Three states: True (sponsors), False (requires US citizen / GC / no sponsorship — score 0 here), Null (unknown — assume sponsors until contradicted in JD text).
- **`requires_us_citizen`** + **`requires_security_clearance`** (bool, default false): Subset of visa-not-friendly; some defense/govt roles have stronger requirements than just "no sponsorship." Surface as a separate signal so the Application Readiness card can route accordingly.
- **`salary_min` / `salary_max` / `salary_currency`** (numeric + str): Sprout shows salary on cards; Naavik plans to ($240-290k + 0.05% per `SCREENS.md § 7` Discover card meta row).
- **`remote_policy`** (enum: `remote` / `hybrid` / `onsite` / `unknown`): Already in mockup.
- **`equity`** (nullable str — free-text like "0.04% to 0.05%" — equity hits don't normalize well to a number).
- **`scraped_at`** + **`last_seen_at`** (datetime): Different signals. Use `last_seen_at` for "still open" inference; close jobs not seen in 14 days.
- **`queue_state`** (enum: `unswiped` / `saved` / `skipped` / `queued_for_auto_apply` / `applied`): Already in `DATA_MODEL.md` Job model per `SCREENS.md § Application status pipeline` (separate axis from Application.status). Naavik already has this — Sprout's swipe-first UX confirms this lifecycle distinction is correct.

### 5.2 StatusHistory transitions worth mirroring

Sprout's email-classifier auto-updates application status; Naavik plans the same in `0.5.0.02`–`0.5.0.03`. For `0.2.0.05` StatusHistory schema, ensure:

- **Indexed `(application_id, transitioned_at)`** for "show me the latest" reads and timeline rendering on `/tracking/:id`.
- **`source` column** (enum: `manual_user` / `email_classifier` / `ats_adapter_callback` / `cron_stale_inference` / `auto_apply_pipeline`): Where the status change came from. Important for debugging — if the email classifier mis-categorized a "We'll be in touch" email as `REJECTED`, you need to know which transition was machine-inferred vs. user-confirmed.
- **`prior_status`** + **`new_status`** columns (denormalized, even though derivable from sequence — saves a window function on every render).
- **`reason`** column (free-text, nullable): For `CLOSED` transitions especially — closed_reason from `DATA_MODEL.md § A` (`rejected` / `withdrawn` / `ghosted` / `position_filled`) lives on Application; the `reason` here is the trigger ("recruiter email subject: 'Update on your application'", "user manually marked withdrawn").
- **`raw_signal`** (jsonb, nullable): The classifier's input — email subject + first 200 chars, or the ATS adapter's webhook payload. Forensic detail Sprout hides; Naavik exposes for self-host debugging.

### 5.3 Auto-apply guardrails Sprout publicizes (or doesn't) — match in `0.2.0.13` + `0.2.5.01`

- **App-velocity cap:** Sprout meters at 80 / 200 / 600 per month — implicit cap. Naavik should publish a default rate (e.g., `Settings.max_auto_applies_per_day` = 50, `max_per_hour` = 10) tunable via `0.2.5.01` (rate-limit dial). Surface as a Settings field with explanatory copy: "Naavik throttles auto-applies to avoid ATS rate-limits and account flags. Tune up at your own risk."
- **Anti-detection knob:** Sprout discloses zero on rate-limit / randomization / IP rotation. Naavik should ship the opposite — `Settings.scraper_aggressiveness` (conservative / normal / aggressive) with the spec written down: conservative = 3-8s random delay, single concurrent request; aggressive = 0.5-2s delay, 3 concurrent. Document in `docs/RUNBOOK.md` so users know what trade-offs they're choosing.
- **Stuck-queue surface:** `SCREENS.md § 7` already specs the "Stuck in queue · {N}" card on Discover for DRAFT applications that hit `captcha` / `auth_required` / `field_mismatch` / `unknown`. This is the forensic surface Sprout users don't have — make sure `0.2.0.11` ships this card, not as a v2 deviation.
- **Postmortem-on-failure (`0.2.3.02`):** Playwright screenshot + AI summary on every auto-apply failure. This is the operator-debug surface that lets a self-hoster figure out why LinkedIn rejected their bot session at 3am — Sprout's "support contact form" cannot match this.

---

## 6. Open questions

These remained ambiguous after research; surface for user disposition:

1. **Confirm: does the user want this comparison memo to drive any ROADMAP additions** — specifically (a) `0.6.0.08` PWA manifest row, (b) a new "non-goal" section in `README.md § Why Naavik wins` codifying "no employer-facing surface, no candidate-data marketplace", and/or (c) pulling `0.5.0.01`–`0.5.0.03` earlier in the schedule? Architect can author rows + plan stubs if yes.

2. **Confirm: is the Sprout README reference at `README.md:34` ("$20-100/mo") still accurate?** Sprout's pricing surface from this research is $19.99 / $39.99 / $79.99 monthly (or $99.99 Ultra full price). The README line is correct as a range but understates the top tier. Worth a one-line README touch-up alongside this memo.

3. **Sprout's exact ATS coverage list is undisclosed.** Third-party reviewers cannot name which ATSes Sprout reliably auto-applies on. If Naavik wants a head-to-head per-source coverage comparison (e.g., "Naavik supports Greenhouse + Lever + Ashby in shipped Phase 1; Sprout claims but doesn't name"), it needs the user (or a future engineer) to test-apply via Sprout on each target ATS as ground truth. Out of scope for this research memo; flag if user wants it as a follow-up dispatch.

4. **Sprout's employer-side recruiter flow seems to surface candidate profiles from their app user base.** The privacy policy says "will not sell personal information" but explicitly allows sharing with "affiliates and business partners." Whether app users' profiles are visible to `recruiting.usesprout.com` recruiters is not stated unambiguously. If this is true, it's the strongest "Naavik wouldn't" talking point; if false, the moat narrative shifts slightly. Cannot resolve without paying for both sides or a privacy-policy lawyer's read.

5. **Confidence calibration:** the H rating reflects the marketing + 2 third-party reviews + privacy policy as primary sources. The Achilles' heel is internal product details (model selection, exact prompts, exact AS reliability rates, the actual mobile-app UX) which we'd need an account to verify. Worth a future "buy a 1-month Basic + log everything" research dispatch if a competitor-deep-dive becomes important pre-launch.

---

## 7. Sources

**Primary marketing surfaces (WebFetch — authoritative for Sprout's own framing):**

- [Sprout homepage — usesprout.com](https://www.usesprout.com/) — tagline, feature inventory, target user, deployment model
- [Sprout pricing — usesprout.com/pricing](https://www.usesprout.com/pricing) — Basic $19.99 / Pro $39.99 / Ultra $79.99 tiers with 80/200/600 monthly apps
- [Sprout AI Apply feature — usesprout.com/features/ai-apply](https://www.usesprout.com/features/ai-apply) — three-stage pipeline (Detection / Filling / Submission) + Require Approval setting + credit cost 1-3 per submit
- [Sprout About — usesprout.com/about](https://www.usesprout.com/about) — origin story, principles, 750k+ signups / 150k+ active stats
- [Sprout Mobile — usesprout.com/mobile](https://www.usesprout.com/mobile) — swipe-to-apply UX, iOS + Android + web sync
- [Sprout Employer side — employer.usesprout.com](https://employer.usesprout.com/) — 15% hire fee, 850M profiles, AI recruiter
- [Sprout's competitive analysis blog — best-job-search-automation-tools](https://www.usesprout.com/blog/best-job-search-automation-tools) — names LazyApply / Careerflow / AIApply / Sonara as competitors
- [Sprout Swipe-for-jobs blog — blog/swipe-for-jobs](https://www.usesprout.com/blog/swipe-for-jobs) — swipe UX flow

**Third-party reviews (independent — for confidence calibration):**

- [JobCopilot 2026 review — sprout-ai-job-search-review](https://jobcopilot.com/sprout-ai-job-search-review/) — verified pricing, data-collection scope (race / disability / orientation / visa / veteran in onboarding), no-manual-edit limitation
- [AutoApplier review — autoapplier.com/blog/sprout-job-app](https://www.autoapplier.com/blog/sprout-job-app) — weekly-cap critique, form-detection variability, vs-competitor matrix

**WebSearch queries used (for ground-truth identity + privacy):**

- `usesprout job search tool career platform` — confirmed identity + 4.8 App Store + 150k users
- `"usesprout" site:usesprout.com OR site:usesprout.ai OR site:usesprout.io` — confirmed canonical domain
- `"usesprout" OR "sprout AI" browser extension chrome firefox autofill` — confirmed no browser extension surface
- `"usesprout" privacy policy data sharing recruiter` — privacy-policy disclosures re: OpenAI / Anthropic / Google Cloud AI + affiliates / business partners

**Naavik canonical references (for the comparison column):**

- `AGENTS.md § Project` + `§ Owner Profile` + `§ Key Conventions § CLI`
- `README.md § What is Naavik` + `§ Why Naavik?` (line 34 already references Sprout) + `§ Features`
- `docs/ROADMAP_OVERVIEW.md` § 2 phase status + § 3 priority queue
- `ROADMAP.md` § 0.2.0 — § 0.7.0 task ledgers
- `docs/design/SCREENS.md` § 3 Overview + § 5 Profile editor + § 7 Discover (multi-axis state pipeline, application questions, swipe UX, score circle / match breakdown)
- `docs/design/research/LINKEDIN_SCRAPING.md` (existing research doc; referenced for scraping-strategy context)
