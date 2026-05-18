---
description: STRIDE threat-model scaffold — attack tree + STRIDE table + top-3 risks + defensive design recommendations, written to `docs/design/THREAT_MODEL-<slug>.md` and linked from the source design doc. Use whenever `/threat-model` is invoked, before any feature ships that touches auth / secrets / untrusted input / OAuth / scraping / ATS adapters, when a design doc enters review. Triggers on phrases like "threat model", "stride", "attack tree", "security review of design", "before this ships", "spoofing", "tampering", "repudiation", "information disclosure", "denial of service", "elevation of privilege".
---

# hacker-stride-template

STRIDE = threat-modeling rubric Naavik uses for any new feature w/ non-trivial attack surface. Output = structured doc at `docs/design/THREAT_MODEL-<slug>.md` future engineers + hacker re-reference. Template + workflow.

## When to invoke

- User invokes `/threat-model <target>`.
- Hacker dispatched on design doc / plan touching auth, secrets, untrusted input, deserialization, OAuth flows, scraping, ATS adapters, or any externally-controlled input path.
- Before ANY feature ships crossing authentication boundary or persisting secrets.
- Architect requests pre-implementation threat model as part of `Type: design` plan.

## Steps

### 1. Read target

- Design doc / plan / feature description you're modeling against.
- Related existing code (callers, auth middleware, existing CSRF + rate-limit middleware, vault audit log if applicable).
- `docs/ARCHITECTURE.md` § 4.1 + § 4.2 — auth + secret-handling conventions to compare against.
- `docs/plans/POST_PHASE_1.md` § Security review — Naavik-specific watchlist.

### 2. Build attack tree

Top-level attacker goal → sub-goals → concrete attacks. Indent visually. Example shape:

```
Goal: Extract user's stored LLM API keys via the cloud tier
├── Sub-goal A: Bypass authentication
│   ├── A1: JWT forgery via weak SECRET_KEY (< 32 bytes)
│   ├── A2: Session fixation via CSRF bypass
│   └── A3: Brute-force password (< 5/15min rate limit)
├── Sub-goal B: Read keys despite authentication
│   ├── B1: Settings API leaks key in response body (allowlist failure)
│   ├── B2: Audit log captures key value (vault audit log spec violation)
│   └── B3: Template renders `{{ api_key }}` accidentally
└── Sub-goal C: Sidecar exfiltration
    ├── C1: SSRF via Discord webhook URL → attacker-controlled internal endpoint
    └── C2: LLM prompt injection extracts SECRET_KEY from system context
```

Tree is deliberately concrete — each leaf = attack w/ specific code path, not "attacker does something bad".

### 3. STRIDE table

One row per concrete threat from tree. Map each to STRIDE category:

| Category | What it covers |
|---|---|
| **S** — Spoofing | Identity confusion (impersonating user / service / device) |
| **T** — Tampering | Modifying data in transit, at rest, or in memory |
| **R** — Repudiation | Doing something then denying it; missing audit trail |
| **I** — Information disclosure | Leaking data to parties that shouldn't see it |
| **D** — Denial of service | Resource exhaustion, lock-out, rate-limit bypass |
| **E** — Elevation of privilege | User → admin, anonymous → user, sandbox → host |

Table shape:

```markdown
| Threat | Category | Attack scenario | Mitigation | Status |
| ------ | -------- | --------------- | ---------- | ------ |
| A1: JWT forgery via weak SECRET_KEY | S | attacker mints valid token if SECRET_KEY < 32 bytes | PC.5 boot-time validator refuses startup | mitigated |
| B2: Audit log captures key value | I | log file readable by services group → key value leaks | vault audit log spec excludes `value` field | mitigated |
| C1: SSRF via Discord webhook | I | webhook URL points to internal AWS metadata endpoint | scheme + host allowlist on webhook setter | open |
```

**Status values:** `mitigated` (today's code defends) / `accepted` (residual risk acknowledged) / `open` (mitigation needed before ship).

### 4. Top-3 risks (rank-ordered)

Surface most-impactful + most-likely as bullets:

```markdown
## Top 3 risks (rank-ordered)

1. **<threat title>** — <impact in attacker's terms>. Recommended next step: <concrete action — code change, env var, doc update, or new control>.
2. ...
3. ...
```

Rank by `severity × likelihood`, where severity uses calibration from `.claude/agents/hacker.md § Verdict format § Severity calibration`:

- **critical** — actively exploitable in production by unauthenticated remote attacker
- **high** — exploitable by authenticated user against another user's data, OR unauthenticated against system integrity
- **medium** — unlikely preconditions OR limited to operational annoyance
- **low** — defense-in-depth gap; not actively exploitable

### 5. Defensive design recommendations

Changes to design doc / plan that mitigate threats **before code is written**. Highest-leverage section — fixing flaw at design time costs orders of magnitude less than at PR time.

```markdown
## Defensive design recommendations

- <recommendation 1 — name file/section change applies to>
- <recommendation 2>
```

### 6. Write doc

Save to `docs/design/THREAT_MODEL-<slug>.md`:

```markdown
# Threat Model — <feature name>

> Authored: YYYY-MM-DD
> Target: <design doc / plan / feature description path>
> Status: DRAFT | ACCEPTED

## Attack tree

<as above>

## STRIDE table

<as above>

## Top 3 risks (rank-ordered)

<as above>

## Defensive design recommendations

<as above>
```

### 7. Link from source

Edit source design doc / plan to add `## Security` section pointing at threat model:

```markdown
## Security

Threat model: `docs/design/THREAT_MODEL-<slug>.md` (top 3 risks summarized inline)
```

## Worked-example anchors

- `docs/ARCHITECTURE.md § 4.1` (auth) — patterns threat model checks against.
- `.claude/agents/hacker.md § "Naavik-specific watchlist"` — Naavik-specific threats:
  - Vault deprecation track (don't add new vault scopes)
  - CLI sunset (don't add new subcommands)
  - `~/.naavik/dev-credentials` mode 0600 + env-gated triple condition
  - LLM provider keys in Settings — allowlist-not-blocklist response filter
  - Portfolio public API — allowlist (no email, phone, EEO, visa, salary)
  - ATS adapter screener-answer XSS safety
  - Auto-apply cron rate-limit + cost-cap enforcement
  - Scraper anti-detection (per-source backoff)

## Canonical references

- `.claude/agents/hacker.md` § "Threat model output" — canonical doc template.
- `.claude/agents/hacker.md` § "Operating loop (threat modeling)".
- `.claude/agents/hacker.md` § "Default attack surfaces" — 16-item checklist informing STRIDE table.
- `.claude/agents/hacker.md` § "Naavik-specific watchlist".
- `docs/ARCHITECTURE.md` § 4.1 + § 4.2.
- `docs/plans/POST_PHASE_1.md` § Security review (full).

## When NOT to invoke

- Trivial bug fixes without attack-surface impact.
- Pure styling / doc PRs.
- Compaction events.

## Forbidden during invocation

- Do NOT write abstract risks without exploit paths. Every leaf in attack tree must name concrete code path or data flow.
- Do NOT mark threat `mitigated` without citing file:line that mitigates it.
- Do NOT skip "Defensive design recommendations" section — fixing at design time is entire point of STRIDE pre-implementation.
- Do NOT soften severity because someone pushed back. Severity is impact-based, not consensus-based.
