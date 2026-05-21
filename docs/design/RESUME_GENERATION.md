# Resume Generation Pipeline (FREE tier)

> **Plan:** `docs/plans/archive/66-0.3.1-free-tier-generation.md` (graduates from § B + § C + the synthesized research memo at `docs/design/research/0.3.1-resume-generation-sota.md`).
> **Status:** Canonical for the FREE-tier pipeline (Stages 1-8). PREMIUM-tier Stage 9 (mythos layer) will extend this doc in `0.3.4` — see § Stage 9.
> **Last updated:** 2026-05-21 (initial graduation from plan 66).

The pipeline that turns a `JobScore`-graded job + a candidate profile into an ATS-passable resume + cover letter + screener answers — all in one atomic call from the Discover · review & apply screen.

## Mental model

```
Application + Job + Profile + Settings
  │
  ▼  (cost-cap probe between each stage; voice corpus cached on Anthropic ephemeral prefix)
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ 1. corpus assembly   (services/voice_grounding.assemble_corpus)          │
  │ 2. hiring manager    (services/hiring_manager_extractor.extract_hm)      │
  │ 3. resume            (services/document_generator.generate_resume)       │
  │    ├─ bullet select  (llm/prompts/select_bullets — constitution-grounded)│
  │    ├─ bullet trim    (llm/prompts/trim_bullet — burstiness-aware)        │
  │    ├─ AI-tell strip  (services/ai_tell_blocklist.strip_violations)       │
  │    └─ typst compile  (typst/compiler.compile — onepage_ats.typ or onepage)│
  │ 4. tailored headline (services/recruiter_optimization.tailor_headline)   │
  │    │   (gated on Job.score ≥ 0.50)                                       │
  │ 5. cover letter      (services/document_generator.generate_cover_letter) │
  │    │   uses draft_cover_letter_sota with adaptive Standard/Pain-Letter   │
  │ 6. screener answers  (services/document_generator.answer_screeners)      │
  │ 7. parse fidelity    (services/ats_parser_fidelity.validate)             │
  │ 8. keyword coverage  (services/keyword_coverage.compute_coverage)        │
  │ 9. ethics pre-flight (services/ethics_preflight.preflight_check)         │
  └──────────────────────────────────────────────────────────────────────────┘
  │
  ▼  Persist trace → application.generation_trace JSONB
  BundleResult { resume, cover_letter, screeners, ethics, parse_fidelity, … }
```

All orchestrated by `services/bundle_generator.generate_bundle(session, application, *, settings, …)`.

## A · Voice grounding (Stage 1)

**Why:** every LLM call in the bundle pipeline anchors on the candidate's actual voice — sentence-length distribution, idiomatic phrases, distinctive vocabulary. This is the single highest-ROI lever (research § T1).

**Where:** `services/voice_grounding.assemble_corpus(session, user_id) -> VoiceCorpus`.

**Sources (5, assembled per-call; no caching column):**

1. `Bullet.text` rows — full set across all experiences (≤200, ordered by index).
2. `Profile.summary_full` + `Profile.summary_short`.
3. `ProfileAnswer.answer` rows (per-user screener reuse cache; STRONG voice signal).
4. `Settings.ai_writing_voice_samples` — operator-facing free-form supplemental text (0-5000 chars).
5. Past `GeneratedDocument.bullet_selection.trimmed_lines` from the last 5 successful resumes.

The result `VoiceCorpus` carries:

- `full_text`: concatenated corpus (newline-separated by source).
- `vocab_fingerprint`: top-30 distinctive non-stopword tokens.
- `sentence_length_stats`: `{mean_words, std_dev_words, short_pct, med_pct, long_pct, sentence_count}`.
- `idiomatic_phrases`: top-10 2-gram phrases by frequency.
- `voice_fingerprint_hash`: `sha256:<32-hex-prefix>` over corpus + blocklist version.
- `source_counts`: per-source row counts (audit aid).

**Caching:** per-call assembly via 5 indexed SELECTs (~50ms). The Anthropic prompt cache (T2) carries the cost benefit — when the corpus is stable across the bundle's ~12 LLM calls, the 5-minute ephemeral cache reuses the prefix at 90% cost reduction on subsequent reads.

**Cache invalidation:** `voice_fingerprint_hash` is included in the constitution preamble. When bullets / profile / voice samples mutate, the hash changes, the cache prefix changes, Anthropic auto-invalidates.

## B · Constitution preamble (Stage 1 output → all subsequent stages' system message)

**Where:** `services/constitution.render_preamble(corpus, profile_full_name, *, blocklist, extra_constraints) -> str`.

**Shape:**

```
You are tailoring application materials for {profile_full_name}.

THEIR VOICE — Match this exactly when generating any output:
- Sentence-length distribution: short {N}% / medium {N}% / long {N}% (mean {N} words, std-dev {N})
- Idiomatic phrases they use: {top 10}
- Distinctive vocabulary (top tokens): {top 30}

THEIR EXPERIENCE (corpus follows; everything below is the candidate's own writing):
{voice_corpus.full_text}

HONESTY CONSTRAINTS:
- NEVER claim experience not grounded in the corpus above.
- NEVER inflate titles or fabricate credentials.
- Every bullet you emit must trace to a corpus bullet. If you cannot point to a corpus source, drop the bullet.

STYLE CONSTRAINTS:
- Avoid AI-tell vocabulary (see FORBIDDEN list below).
- Vary sentence length deliberately. Mix short (≤8 words) and long (≥20 words) sentences across the same output.
- Prefer specific verbs over generic. Prefer concrete numbers over qualitative claims.
- Do NOT use em-dashes (—). Use commas or periods.

FORBIDDEN VOCABULARY (case-insensitive; do not use): {effective blocklist}

{extra_constraints}
```

**Caching attachment:** rendered into the `system` argument of `LLMProvider.structured(..., system=..., cache_system=True)`. Anthropic attaches `cache_control={"type": "ephemeral"}` to the system content block; ~12 calls in ~10s ride the same cached prefix.

## C · AI-tell blocklist (Stage 3 + 5 post-process)

**Where:** `services/ai_tell_blocklist`.

**Baked-in blocklist (30 entries):** `delve, delving, leverage, leveraging, leveraged, robust, robustly, moreover, furthermore, in conclusion, underscore, underscores, harness, harnessing, pivotal, paramount, intricate, nuanced, multifaceted, holistic, synergy, synergistic, deeply, comprehensive, extensive, substantial, significantly, particularly, ultimately, tapestry`.

**Dynamic subtraction:** when the user's voice corpus contains a blocklisted term (e.g. they naturally write "leverage"), that term is REMOVED from the active list for this user. Implemented as `effective_blocklist(voice_corpus_text) -> set[str]`.

**Em-dash special handling:** em-dash (` — `) is the single most-common AI tell. `strip_violations` runs a regex first that replaces em-dashes with `. ` (sentence boundary, followed by capital) or `, ` (mid-sentence). Always recorded as `"em-dash"` in the violations list.

**Two-layer enforcement:**

1. Prompt-level — full list rendered into the FORBIDDEN section of the constitution preamble.
2. Post-process strip — `strip_violations(text, blocklist) -> (scrubbed, violations)` regex-sweeps the LLM output. Violations go to the audit trail.

## D · Burstiness validator (Stage 3, post-trim)

**Where:** `services/burstiness_check.check_and_score(bullets) -> BurstinessReport`.

**Threshold:** `std_dev >= 6` reads as human (variance); below reads as AI (uniformity). Research § T1-C source.

**Action on fail:** identify the bullet closest to the mean (the "most-uniform offender"); re-prompt the LLM to rewrite THAT bullet with a target word count pulled AWAY from the mean. Cap at 1 retry per bundle (cost discipline).

## E · ATS-friendly Typst template (Stage 3 output)

**Templates:**

- `src/typst/templates/onepage.typ` — creative (human-recruiter / portfolio); existing.
- `src/typst/templates/onepage_ats.typ` — NEW per plan 66 § T6. Strict single-column, plain `•` bullets, MM/YYYY dates, ligature-disabled Helvetica, PDF/A-1b output. Cross-ATS allowlist headers ("Professional Experience" / "Education" / "Skills" / "Projects").

**Auto-select** (`services/document_generator._select_template`):

| `Settings.resume_template_preference` | Selected template |
|---|---|
| `"ats"` | `onepage_ats.typ` + PDF/A-1b |
| `"creative"` | `onepage.typ` + default PDF |
| `"auto"` (default) AND `Application.board` ∈ {WORKDAY, GREENHOUSE, LEVER, ASHBY, LINKEDIN} | `onepage_ats.typ` + PDF/A-1b |
| `"auto"` AND `Application.board` ∈ {INDEED, COMPANY_DIRECT, MANUAL, None} | `onepage.typ` + default PDF |

The ATS template surfaces a `tailored_headline` slot in the JSON payload (10pt line under the 14pt name) — populated by Stage 4 when present, falling back to `Profile.headline` when absent.

## F · Recruiter-priority headline (Stage 4)

**Where:** `services/recruiter_optimization.tailor_headline_for_application` + `llm/prompts/tailor_headline.TailoredHeadline`.

**Gate:** `JobScore.score >= 0.50` (`HEADLINE_SCORE_GATE`). Below threshold the headline call is skipped and the resume falls back to `Profile.headline`.

**Schema:**

```python
class TailoredHeadline(BaseModel):
    title: str                                      # ≤30 chars; JD-matched within ethical bounds
    years: int                                      # 0-50; extracted from Experience spans
    specialty: str                                  # ≤30 chars; 1-2 JD-aligned specialties
    sponsorship_signal: str | None                  # only when work_auth is constrained
    headline_one_line: str                          # ≤100 chars total; clamps on overflow
    keywords_emphasized: list[str]                  # ≤8; for audit
```

**Sponsorship signal:** rendered ONLY when `Profile.work_authorization` ∈ {H1B, OPT_CPT, OTHER_REQUIRES_SPONSORSHIP}. Other auths suppress the signal.

**Render:** `headline_one_line` follows the template `"{title} · {years} yrs · {specialty}" + optional " · {sponsorship_signal}"`. The Pydantic `mode="before"` validator clamps overflow to 99 chars + `…` rather than raising (LLM occasionally over-shoots).

## G · Keyword coverage (Stage 8)

**Where:** `services/keyword_coverage.compute_coverage(must_haves, resume_text, *, top_pct=0.30, threshold=0.75) -> CoverageReport`.

**Must-haves source:** `JobScore.match_breakdown.matched_tags` ∪ `Job.skills_required[:5]`. Caller decides which is authoritative (orchestrator uses both, dedupes case-insensitively).

**Scoring:** fraction of must-haves found in the top 30% (by line count) of the resume text. Tiers:

- `≥ threshold` (default 0.75): pass silently.
- `[0.50, threshold)`: warning chip surfaced to the user.
- `< 0.50`: ONE re-selection cycle with explicit "include bullets containing missing keywords: <list>" instruction (cap 1 retry).

## H · Cover letter SOTA (Stage 5)

**Where:** `llm/prompts/draft_cover_letter_sota.draft_cover_letter_sota` + `services/document_generator.generate_cover_letter`.

**Adaptive format dispatch** (T10):

- Scan JD for pain-point verbiage (`looking to solve | challenges | pain points | frustration | struggling with | issues with | working through | navigate the | break (down|out of) | overcome`). ≥2 matches → **Pain-Letter** format.
- Otherwise → **Standard Hook / Match / Close 3-paragraph**.
- Override via `Settings.cover_letter_format` ∈ {"auto", "standard", "pain_letter"}.

**Schema:** `CoverLetterSota(format_chosen, hook, match, close, hiring_manager_used, verbatim_phrases)`.

**Verbatim phrases:** the LLM is instructed to prefer the candidate's actual words over rephrasing; phrases lifted from the corpus are listed in `verbatim_phrases` as an audit trail for the honesty constraint.

**T15 backward-compat:** `llm/prompts/draft_cover_letter.py` is retained for direct callers (tests, scripts). The bundle endpoint always uses `draft_cover_letter_sota`. Old prompt slated for removal in `0.3.3`.

## I · Hiring manager extractor (Stage 2)

**Where:** `services/hiring_manager_extractor.extract_hiring_manager`.

**Strategy stack:**

1. **Manual override** (UI text field) — `manual_override=` kwarg → `HiringManagerHit(source="manual", confidence=1.0)`.
2. **Regex first** — patterns `Hiring Manager: <name>` / `Reporting to <name>` / `You'll report to <name>` / `Manager: <name>` / `Contact: <name>`. Hit → `source="regex"`, `confidence=0.90`.
3. **LLM fallback** — only when regex misses AND JD ≥200 chars. One structured LLM call returns `{name, title, confidence}`. Hit → `source="llm"`, confidence per LLM.

**Salutation render:** when `name` present + `confidence >= 0.5` → "Dear {first_name},". Else → "Dear {Job.company} Hiring Team,".

## J · ATS parse-fidelity validator (Stage 7)

**Where:** `services/ats_parser_fidelity.validate_parse_fidelity(pdf_path, *, threshold=0.75) -> ParseScoreReport`.

**Approach:** round-trip the generated PDF via `pdfplumber` text extraction + heuristic regex match over 8 canonical fields.

**8 canonical fields:**

1. `name` (first non-empty line).
2. `email` (regex match anywhere).
3. `phone` (US-format regex match anywhere).
4. `first_experience_title` (first line under "Professional Experience" header).
5. `first_experience_company` (same line).
6. `first_experience_start_date` (MM YYYY pattern within first 500 chars of experience body).
7. `education_institution` (first line under "Education" header).
8. `skills_section_present` (header `^Skills$` found).

**Score = `fields_found_count / 8`.**

**Smart-default tiers (`OQ-7` lock):**

- `≥ 0.90` — silent (audit-only).
- `[0.75, 0.90)` — info-toast via HTMX `HX-Trigger: parse-fidelity-warning` header.
- `< 0.75` — orchestrator falls back to conservative template + surface to user via response payload `parse_fidelity_score`.

**Graceful degrade:** when `pdfplumber` import fails, the validator returns `score=1.0` + `notes=["pdfplumber unavailable; validator skipped"]` so the bundle still ships.

## K · Ethics pre-flight (Stage 9)

**Where:** `services/ethics_preflight.preflight_check(selected_ids, trimmed_lines, available_bullet_ids) -> EthicsReport`.

**Mechanic:** any bullet whose ID isn't in the candidate's actual `Bullet.id` set (joined via Profile + Experience + Bullet, all non-deleted) is DROPPED. The orchestrator continues with the surviving bullets.

**Threshold:** `len(dropped) > 2` → `surface_to_user=True`. Orchestrator returns 422 to the route handler; UI shows red-flag list to the user with a "review your profile or regenerate" prompt.

**Why this is the CORE honesty constraint:** the constitution preamble TELLS the LLM not to fabricate; ethics pre-flight VERIFIES the output. Both belt and suspenders.

## L · Audit trail (`Application.generation_trace`)

**Storage:** new JSONB column on `application` table via alembic 0018. Opaque-blob pattern matching `submission_artifacts` precedent — schema enforced in Pydantic `GenerationTrace`, not at the DB layer.

**Lifecycle:** OVERWRITTEN on regenerate (single bundle = single trace). Historical audit lives in `GeneratedDocument` rows (one per resume/cover_letter), not the trace.

**Schema (17 keys + `schema_version`):**

```python
{
  "schema_version": 1,
  "tier": "free",
  "stages_run": ["corpus", "hiring_manager", "resume", "cover_letter", "screeners",
                 "parse_fidelity", "keyword_coverage", "ethics"],
  "stages_skipped": [],
  "stage_costs_usd": {"resume": 0.011, "trim": 0.024, "cover_letter": 0.018, …},
  "total_cost_usd": 0.078,
  "total_latency_ms": 11200,
  "llm_calls": 12,
  "bullet_selections": [{"bullet_id": 47, "jd_signal": "…", "citation": "…"}, …],
  "jd_keywords_extracted": ["Python", "ML platform", "distributed systems"],
  "cover_letter_format": "standard",
  "hiring_manager": {"name": "Jane Smith", "title": "EM",
                     "source": "regex", "confidence": 0.9},
  "voice_fingerprint_hash": "sha256:abc123…",
  "constitution_version": "v1",
  "parse_fidelity_score": 0.92,
  "parse_fidelity_tier": "silent",
  "parse_fidelity_fields_missing": [],
  "keyword_coverage_score": 0.87,
  "keyword_coverage_missing": ["Kubernetes"],
  "ai_tell_violations": [],
  "burstiness_std": 8.4,
  "ethics_pre_flight": {"passed": true, "dropped_bullets": [], "flags": []},
  "degraded_mode": false,
  "cost_cap_at_exhaustion": null,
  "headline_used": "Senior ML Engineer · 8 yrs · ML platform · H1B+i-140",
  "generated_at": "2026-05-21T10:15:42Z"
}
```

## M · Cost-cap mid-flight (`Settings.daily_llm_cost_cap_usd`)

**Where:** `services/document_generator.is_cost_capped` probe between every stage in `services/bundle_generator.generate_bundle`.

**Behavior:**

1. **Pre-flight probe (before stage 1):** when capped, return immediately with `BundleResult(skipped_reason="cost_cap_reached", degraded=True)`. Every stage marked `stages_skipped`. No LLM spend.
2. **Mid-flight probe (between each stage):** when capped, complete the current stage if mid-call, then skip remaining stages. Set `degraded_mode=True` in the trace. PDFs from earlier stages survive; UI renders an amber banner.
3. **Audit trail:** `degraded_mode: bool` + `cost_cap_at_exhaustion: float | null` + `stages_skipped: list[str]`.

## N · Settings (`Settings.*`)

| Field | Type | Default | Surface |
|---|---|---|---|
| `ai_writing_voice_samples` | TEXT | `""` | Settings · Generation tab — textarea |
| `cover_letter_format` | str(20) `"auto"\|"standard"\|"pain_letter"` | `"auto"` | Settings · Generation tab — radio |
| `resume_template_preference` | str(20) `"auto"\|"ats"\|"creative"` | `"auto"` | Settings · Generation tab — radio |
| `tier_2_evasion_enabled` | bool | `false` | Settings · Advanced — opt-in checkbox |
| `parse_fidelity_threshold` | float | `0.75` | Settings · Advanced — slider |

All ship in alembic 0018 with safe server defaults (no data backfill needed).

## O · One-click endpoint

**Route:** `POST /api/v1/applications/{id}/generate-bundle`.

**Request body (optional):**

```json
{ "hiring_manager_override": "Alice Custom" }
```

**Response:**

```json
{
  "resume_id": 1,
  "cover_letter_id": 2,
  "screeners_count": 3,
  "degraded": false,
  "degraded_reason": null,
  "parse_fidelity_score": 0.92,
  "parse_fidelity_tier": "silent",
  "keyword_coverage_score": 0.87,
  "hiring_manager": {"name": "Jane Smith", "source": "regex", "confidence": 0.9},
  "generation_trace": { /* see § L */ }
}
```

**Security:**

- CSRF via the existing `require_password_complete` dependency chain.
- IDOR via `application.user_id == current_user.id` (404 on cross-user).
- 422 on ethics rejection (`ethics_pre_flight.surface_to_user=True`).
- 409 on missing Settings row (operator misconfiguration).
- 404 on missing Application (matches existing pattern).

**HTMX trigger headers:**

- `HX-Trigger: bundle-degraded` on `degraded=True`.
- `HX-Trigger: parse-fidelity-warning` on `parse_fidelity_tier=="toast"`.

## P · Cost math (Sonnet 4.6)

Per research § T2 + Anthropic 2026 pricing ($3/MTok input, $15/MTok output, $0.30/MTok cache_read, $3.75/MTok cache_write):

- Stage 1 cache write: ~25K input tokens × $3.75/MTok = $0.094.
- Stages 2-12 cache reads: 11 × (25K × $0.30/MTok) = $0.082.
- Output: ~3K tokens × $15/MTok = $0.045.
- **Total ~$0.22 per bundle.**

Worst case (no cache hit, fresh each call): ~$0.90. Best case (cold stage 1 only): ~$0.12.

## Q · Stage 9 — PREMIUM (Claude-mythos layer)

**Status:** OUT OF SCOPE for plan 66 / 0.3.1. Scheduled for `0.3.4` (PREMIUM tier). When that plan ships, it extends this doc with:

- `Stage 9.1 — Originality.ai polish loop` (3rd-party detection check + iterate).
- `Stage 9.2 — TIER-2 evasion features` (gated on `Settings.tier_2_evasion_enabled`).
- `Stage 9.3 — Claude-mythos voice doubling` (additional grounding via `manager-promote-lesson` knowledge entries).

The FREE tier (Stages 1-8) is independently shippable and complete. PREMIUM extends; it does not replace.

## R · Cross-references

- `docs/design/BACKEND.md § K.4` — pipeline catalog (forward-pointer here).
- `docs/design/DATA_MODEL.md § Application` — `generation_trace` column.
- `docs/design/DATA_MODEL.md § Settings` — 5 new Settings fields.
- `docs/design/SCREENS.md § 8` — Discover · review & apply (action bar wires to this endpoint).
- `docs/design/JOB_MODEL.md` — `JobScore` (consumed for `matched_tags` + score gate).
- `docs/design/research/0.3.1-resume-generation-sota.md` — full research synthesis (option matrices, source citations).
- `AGENTS.md § Resume/CV Data Model` — 9-tag vocab + selection override semantics.
