# Hermes Agent Prompt — ERD Audit & Single-Diagram Regeneration

> **Target agent:** Hermes (or any agent with `read`, `grep`, code-analysis capabilities)
> **Prerequisites:** Read `docs/design/ERD.md` (current state), `docs/design/DATA_MODEL.md` (field-level reference), skim `src/models/` (20 model files)

---

## 1. Goal

Verify the existing ERD (`docs/design/ERD.md`) against the actual SQLModel code in `src/models/`, then produce an improved **single unified Mermaid ER diagram** of all 27 tables (no domain categorization; one diagram) saved to `docs/design/ERD_v2.md`. Accompany it with a sharp critique section: identify redundancies, friction points, and architectural pros/cons against Naavik's use cases.

---

## 2. Required Reading (in order)

1. `docs/design/ERD.md` — the current 6-domain categorized ERD + 12 architect observations
2. `docs/design/DATA_MODEL.md` — canonical field-level spec, state transitions, enum vocabularies
3. `AGENTS.md` — project conventions (Python 3.12+, SQLModel, FastAPI, HTMX stack)
4. `src/models/__init__.py` — the canonical model registry (which models are actually imported)
5. All model files in `src/models/` (20 files) — the ground truth for every table, column, FK, and constraint

---

## 3. Phase 1 — Verification Audit

### Step 1: Inventory every SQLModel table

For each of the 20 files in `src/models/`, extract:

- Table name (from `__tablename__`)
- Column names + types + nullability
- Foreign keys (explicit `ForeignKey("table.column")`)
- `sa_column_kwargs` (unique, index, server_default, etc.)
- Relationship declarations (which `Relationship()` back-populates exist)
- Class-level docstrings that describe intent

Produce an internal checklist of "27 tables expected; N found" to ensure no table is missed.

### Step 2: Diff against the current ERD

For every discrepancy between the code and `docs/design/ERD.md`, flag it:

| Category | Example |
|---|---|
| **Missing column** | ERD shows column X but model doesn't have it; or model has Y but ERD omits it |
| **Wrong type** | ERD says `string` but model says `int` / `datetime` / `json` / `array` |
| **Missing FK** | ERD diagram arrow missing that exists in model, or vice versa |
| **Wrong cardinality** | ERD says `\|\|--o{` but model relationship implies `\|\|--o\|` |
| **Missing table** | Model table exists but omitted from all ERD diagrams |
| **Wrong annotation** | ERD note says "UK" but no unique constraint in model; ERD says "nullable" but column is `NOT NULL` |
| **Enum value drift** | ERD lists enum values that differ from `src/models/enums.py` |

**Output:** a verification table with columns: `Table`, `Discrepancy Type`, `ERD Says`, `Code Says`, `Severity (CRITICAL/HIGH/LOW)`, `Action Taken`.

### Step 3: Verify cross-domain relationships

The current ERD diagrams are domain-siloed, so cross-domain FKs may not have been captured. Specifically check:

- `ProfileAnswer.source_screener_answer_id` → `ApplicationScreenerAnswer` (Profile → Applications)
- `Job.warm_intro_contact_id` → `Contact` (Jobs → Contacts)
- `Job.duplicate_of_id` → `Job` (self-FK, tier-3 dedup)
- `ApplicationScreenerAnswer.application_id` → `Application` (cross-domain anchor)
- `ATSCredential.board` — is there a FK or is it a free enum?
- `ContactApplicationLink` bridging Contact ↔ Application
- `OutreachMessage` bridging Contact ↔ Application
- `EmailThread` bridging Contact ↔ Application
- `ApiUsage.application_id` → `Application`
- `AppEvent.application_id` → `Application`

**Output:** note any FK that's missing from the ERD entirely, or that appears only in one domain's diagram but not the other.

---

## 4. Phase 2 — Single Unified ERD (Mermaid)

### Requirements

1. **ONE `erDiagram` block** — all 27 tables in a single diagram, not 6 separate ones.
2. **Relationships are flat** — use Mermaid's `erDiagram` relationship syntax (`||--o{`, `||--||`, `||--o|`, `}o--o|`, etc.) to connect every FK pair, regardless of "domain."
3. **Columns shown: PK, FKs, and semantically significant columns only.** Do NOT list every column — the full column inventory exists in `DATA_MODEL.md`. Show enough columns that a reader understands what each table *is* and how it connects. Aim for 3-8 columns per table.
4. **Mermaid syntax must render cleanly** — no special characters in entity names, no unsupported column types, no stray backticks inside the `erDiagram` block. Test render viability.
5. **Annotations** — use Mermaid `"comment"` syntax after column types to add brief notes (e.g., `string UK "unique per user"`, `datetime "soft delete"`).
6. **Grouping hint** — if Mermaid renders better with a layout hint, use `%%{init: {'theme': 'base'}}%%` at the top to set a clean theme.

### Structure of ERD_v2.md

```markdown
# Naavik — Unified Entity-Relationship Diagram v2

> **Authored:** YYYY-MM-DD — Hermes audit + single-diagram regeneration from `docs/design/ERD.md`
> **Source of truth:** `src/models/**.py` (verified YYYY-MM-DD against commit <SHA>)
> **Companion:** `docs/design/DATA_MODEL.md` (field-level + state-transition reference)
> **Diff from v1:** Single `erDiagram` block (was 6 categorized diagrams); N discrepancies fixed (see § Verification)

---

## Verification Summary

| Table | Discrepancy | Severity | Fixed? |
|---|---|---|---|
| ... | ... | ... | ... |

---

## Unified ERD

```mermaid
erDiagram
    %% All 27 tables in a single flat diagram
    ...
```

---

## Critique

### Redundancies That Can Be Eliminated
1. ...
2. ...

### Friction Points (What Slows Down New Features)
1. ...
2. ...

### Pros of This Design
1. ...
2. ...

### Cons / Risks
1. ...
2. ...

### Recommendations (Top 5)
1. ...
```
```

---

## 5. Phase 3 — Critique Section

Write a sharp, honest assessment of the data model. This is NOT a checkbox exercise — identify real problems that will cause pain.

### 5.1 Redundancies

Flag every denormalized field, duplicated FK, or structural redundancy. For each:

- **What** is duplicated
- **Why** the author chose denormalization (query from `DATA_MODEL.md` or model docstrings if available)
- **Do you agree?** — is the denormalization worth it for the stated reason?
- **Alternative** if you disagree

**Known redundancies to evaluate** (from ERD.md Obs 3, 5, 10):

| Redundancy | ERD Assessment | Your Take |
|---|---|---|
| `JobEmbedding.user_id` duplicates `Job.user_id` | Plan 61 D5: perf index for per-user vector search | — |
| `Profile.email` duplicates `User.email` | Intentional denormalization for resume rendering | — |
| `Application.company/role/team/location/salary_*` duplicate `Job.*` | Snapshot pattern — Application is what you applied to, resilient to Job mutation | — |
| `Contact.company` duplicates `Job.company` / `Application.company` | Free-form string, no Company entity | — |
| `Tenant` table with 1 row on all self-hosted instances | Forward-looking for multi-tenant SaaS | — |

Also scan for redundancies NOT already called out:
- Are there columns that always co-occur and could be a separate table?
- Are there JSONB columns that duplicate structured data available elsewhere?
- Are there `order_index` columns that could be derived from a linked list or timestamp instead?

### 5.2 Friction Points

Identify what **slows down feature development** given this schema:

- **Query complexity:** any common query that requires 4+ JOINs when it shouldn't?
- **Write anomalies:** any denormalization that requires updating N rows when 1 fact changes?
- **Schema rigidity:** any column type that's too narrow for the use case (e.g., string where it should be json)?
- **Missing indices:** any FK column without an index that would make common queries slow?
- **Soft-delete inconsistency:** ERD Obs 9 notes `deleted_at` on 9 tables but not on 18 others — does this create bugs?
- **Cross-domain JOIN pain:** any query that crosses 3+ of the 6 domains regularly?
- **Enum rigidity:** any enum that changes during normal operations (e.g., adding a new ATS source, a new application status) requiring an alembic migration?

### 5.3 Use Case Walkthrough

Pick 5 representative Naavik use cases and trace them through the schema. For each:

1. **What the user wants to do** (one sentence)
2. **SQL query needed** (pseudocode: which tables joined, filtered, sorted)
3. **Is this natural or convoluted?**
4. **What would make it better?**

**Use cases to trace:**

- **UC1:** "Show me all jobs at Stripe, sorted by score, with contact warm-intro badges"
- **UC2:** "Generate a tailored resume for this job — which bullets should I include?"
- **UC3:** "What's my application pipeline status for all active applications?"
- **UC4:** "Find all outreach messages to recruiters at Google that I haven't followed up on in 7 days"
- **UC5:** "How much did I spend on LLM calls for resume generation in the last 30 days?"

### 5.4 Pros

Acknowledge what's genuinely good about this schema:

- **Consistency:** naming conventions (snake_case), FK scoping (user_id everywhere), soft-delete pattern
- **Denormalization choices:** which ones are smart trade-offs
- **Extensibility:** JSONB columns that leave room for future fields without migrations
- **pgvector integration:** embedding columns well-structured for vector search
- **Observability:** ApiUsage table + AppEvent timeline for audit trails

### 5.5 Cons / Risks

Be blunt:

- **Missing Company entity** (Obs 3) — fuzzy string matching for every company query
- **No multi-tenant isolation at DB level** — row-level security not enforced in Postgres; depends on service-layer WHERE clauses
- **JSONB abuse risk** — `settings` columns (e.g., `auto_apply_per_board_daily_caps`, `score_per_dim_weights`, `consecutive_scrape_failures`) have no schema enforcement at the DB level
- **EmailThread.messages as JSONB** (Obs 8) — will need a migration when Phase 5 lands
- **Soft-delete inconsistency** — half the tables have `deleted_at`, half don't
- **Vestigial fields** (`is_admin`, `allow_multiple_users`) — clutter the schema and mislead contributors
- **Enum value casing inconsistency** — UPPER vs lower_snake_case
- **Tenant over-engineering** — 2 tables for a single-tenant app

### 5.6 Recommendations (Ranked)

Rank the top 5 schema improvements by ROI (impact ÷ effort):

| # | Recommendation | Impact | Effort | Rationale |
|---|---|---|---|---|
| 1 | ... | HIGH | LOW | ... |
| 2 | ... | ... | ... | ... |

---

## 6. Output

Save the final deliverable as `docs/design/ERD_v2.md` with the structure defined in § 4.

---

## 7. Quality Bar

- [ ] All 27 tables verified against `src/models/` code (not `DATA_MODEL.md` — the code is ground truth)
- [ ] Every FK from code appears as a relationship line in the unified ERD
- [ ] The Mermaid `erDiagram` block renders in GitHub Markdown preview without errors
- [ ] Verification table lists every discrepancy found (empty table only if ERD.md was 100% accurate)
- [ ] Critique section is specific and actionable — no vague "consider normalizing" without a concrete cost/benefit
- [ ] Use case walkthrough includes actual pseudocode SQL, not hand-waving
- [ ] Recommendations are ranked by ROI, with effort estimates in hours/days

---

## 8. Forbidden Patterns

- Do NOT copy-paste the existing ERD and just re-label sections. Regenerate from code.
- Do NOT skip tables because they "seem trivial" — `RevokedJwt`, `TenantSigningKey`, etc. must be in the diagram.
- Do NOT invent columns or FKs that don't exist in `src/models/`.
- Do NOT reference the ERD's self-claims as verification — verify against the code.
- Do NOT produce a half-finished diagram with `...` or TODO markers.
- Do NOT mark discrepancies as "INFO" and skip them — every discrepancy gets an Action (fixed in diagram, or documented in critique).
