---
description: Run the 16-item default-attack-surfaces checklist on every PR — auth, SQL injection, XSS, CSRF, deserialization, file uploads, race conditions, SSRF, template injection, OAuth, LLM prompt injection. Use whenever the hacker is dispatched on a PR review, before merging anything touching auth/secrets/untrusted input/file uploads/scrapers/ATS adapters. Triggers on phrases like "pr security review", "review pr", "security checklist", "owasp", "auth review", "csrf check", "xss check", "injection check", "default attack surfaces", "16-item checklist".
---

# hacker-pr-security-checklist

Every PR review starts with this 16-item canonical surface scan (verbatim from `.claude/agents/hacker.md § Default attack surfaces`). Walk every box in order. Findings flow into the verdict's FINDINGS block. The Naavik-specific watchlist (vault sunset, 10c dev-credentials gate, portfolio allowlist) is layered on top via `hacker-secrets-audit` skill.

## When to invoke

- `/review-pr <N>` slash command.
- Hacker dispatched on a PR that touches auth / secrets / untrusted input / file uploads / scrapers / ATS adapters / external integrations.
- Pre-merge sanity scan on ANY PR (cheap to run; better than missing a defect).
- Self-audit before submitting a PR — engineer can run the same checklist against their own diff.

## What this skill does

Walk the 16 items below. Each is a one-line check. Tick `[x]` if confirmed safe, `[!]` if a finding lands. Findings need `file:line + impact + fix` per the verdict format.

```
[ ] 1. Input validation
       Pydantic models on every API surface (request bodies + query/path params).
       No model bypass via `request.json()` direct read.
       Form parsers (`Form(...)`) for HTMX POSTs.

[ ] 2. Authentication / Authorization
       JWT cookie flags: HttpOnly + Secure + SameSite=Strict
       CSRF double-submit token on every POST/PUT/DELETE
       Brute-force rate limit: 5 attempts per 15 minutes on /api/v1/auth/login
       Authz check on every protected route (current_user dependency, role check if scoped)

[ ] 3. Session / JWT
       HS256 key length ≥ 32 bytes (PC.5 validator enforces this at boot)
       Token expiry sensible (typically 1-7 days for "remember me")
       No `algorithm="none"` accepted by the verifier
       Rotation policy for multi-tenant cloud (Phase 1.x backlog, not Phase 1)

[ ] 4. Secret storage
       Env vars for new operator secrets (post-2.12 pattern)
       Vault sunset: any NEW code leaning on `src/services/vault.py` is a violation
       `~/.naavik/dev-credentials` triple-gate intact (see `hacker-secrets-audit`)
       No secrets in code / git history / .env (only .env.example)

[ ] 5. SQL injection
       SQLModel `select(Model).where(...)` style, parameterized
       No f-string SQL anywhere: `f"SELECT * FROM jobs WHERE id={job_id}"` is a reject
       Raw `text(...)` only with `bindparams(...)`, never string concat

[ ] 6. XSS in Jinja templates
       autoescape ON (default in FastAPI's Jinja config — confirm in `src/ui/__init__.py`)
       Every `|safe` filter line audited: is the source trusted?
       User-supplied content (JD text, bullet text, screener answers) never `|safe` direct

[ ] 7. CSRF on POST routes
       Double-submit token: cookie + body match
       HTMX forms carry `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'`
       No POST route exempts CSRF without a documented reason (none should)

[ ] 8. File upload paths
       Resume parse: PDF size cap (≤ 10MB), MIME sniff (not just Content-Type header)
       Path traversal: no `../` in stored filenames; use UUIDs
       Saved to `~/.naavik/data/documents/<app_id>/...`, never user-controlled subpath

[ ] 9. File-system writes outside expected roots
       Allowed roots:
         ~/.naavik/data/documents/<app_id>/
         ~/.naavik/data/documents/portfolio/
         ~/.naavik/data/snapshots/
         ~/.naavik/secrets.enc + ~/.naavik/key.bin (vault — sunset)
         ~/.naavik/dev-credentials (mode 0600, env-gated)
         ~/.naavik/logs/*.log
       Any write outside these → reject + explain why.

[ ] 10. Pydantic deserialization of untrusted input
       No `parse_obj_as(SomeModel, untrusted_json)` without schema validation
       No `**dict` unpacking of attacker-controlled dicts into model constructors
       Discriminated unions for polymorphic payloads (scoring results, job extractions)

[ ] 11. Race conditions in async code
       Connection pool: NullPool engine per plan 10b deviation — confirm session boundaries
       Write-after-read on Settings: row lock or optimistic concurrency
       Lifespan shutdown: schedulers stopped before sessions closed
       Concurrent auto-apply cron: ensure one job at a time per application

[ ] 12. SSRF
       Webhook URLs user-controlled (Discord, Telegram, Netlify rebuild) — validate:
         - scheme in {http, https} only
         - host NOT in {localhost, 127.0.0.1, 169.254.169.254, internal CIDRs}
         - resolved IP NOT private (DNS rebinding protection)
       LLM provider base_url (Ollama) — same allowlist scheme

[ ] 13. Template injection in Typst
       Untrusted JD text → escape via Typst's `box("...")` or text-content node
       No string concatenation of user content into Typst doc body
       Test: render a JD with `#raw("malicious")` payload + confirm no execution

[ ] 14. Logging
       No secrets in any log line (passwords / API keys / tokens / SECRET_KEY)
       vault-audit.log never carries values (only {caller, key, op, scope, ts})
       Access log scrubs Authorization headers + cookies
       ApiUsage rows: prompt/response content stays out of logs (`tracked_call` per `engineer-llm-tracker-wrap`)

[ ] 15. OAuth flows (Gmail / Outlook / Google — Phase 5)
       state parameter generated + verified (CSRF protection on OAuth)
       PKCE on public clients
       Redirect URI strict allowlist (no wildcards, no userland subdomains)
       Token refresh: encrypted at rest (post-2.12 = env-scoped per-user, NOT vault)

[ ] 16. LLM prompt injection
       Untrusted user content (JD text, profile bullets, screener answers) flows into prompts
       Verify structured-output contract holds: the model can't escape JSON schema
       No `system_prompt + user_content` concatenation where user_content can override system
       Test: paste a "ignore previous instructions" prompt fragment + confirm structured output still validates
```

## Naavik-specific layered checks

After the 16 above, layer the Naavik-specific watchlist from `.claude/agents/hacker.md`:

- Vault deprecation track — flag any new code that leans on `src/services/vault.py` / `src/cli/vault.py` / `src/cli/init.py`
- CLI sunset — flag new `naavik <subcommand>`
- `~/.naavik/dev-credentials` triple-gate (NAAVIK_DEBUG + NAAVIK_DEV_PASSWORD unset + SELF_HOSTED + mode 0600)
- `NAAVIK_DEV_PASSWORD` / `SECRET_KEY` non-leak
- LLM provider keys in `Settings.api_keys` — allowlist-style response filter
- Portfolio public API allowlist (no email, phone, EEO, visa, salary, screener answers)
- ATS adapter screener-answer XSS safety into downstream board UIs
- Auto-apply cron rate-limit + cost-cap enforcement
- Scraper anti-detection (per-source backoff, no aggressive parallelization)

See `hacker-secrets-audit` skill for the deep-dive on the secrets-related Naavik items.

## Verdict + posting

Once findings consolidated, post via github MCP:

```
1. mcp__github__pull_request_review_write(method="create", body=verdict_header)
2. For each finding:
     mcp__github__add_comment_to_pending_review(path=<file>, line=<n>, body=finding_text)
3. mcp__github__pull_request_review_write(
     method="submit_pending",
     event="APPROVE" | "REQUEST_CHANGES" | "COMMENT"
   )
```

Event mapping:
- `APPROVE` / `APPROVE_WITH_NOTES` → `APPROVE` or `COMMENT`
- `REQUEST_CHANGES` / `BLOCK` → `REQUEST_CHANGES`

Verdict gates (calibrated):
- 0 critical/high findings + everything allowlist-style → `APPROVE`
- 0 critical/high but ≥ 1 medium/low → `APPROVE_WITH_NOTES`
- ≥ 1 high finding → `REQUEST_CHANGES`
- ≥ 1 critical finding OR systemic auth/secret issue → `BLOCK`

## Canonical references

- `.claude/agents/hacker.md` § "Default attack surfaces" — the 16-item source.
- `.claude/agents/hacker.md` § "Naavik-specific watchlist".
- `.claude/agents/hacker.md` § "Verdict format" + § "Severity calibration".
- `.claude/agents/hacker.md` § "PR review workflow (github MCP)".
- `docs/plans/POST_PHASE_1.md` § Security review.
- `docs/ARCHITECTURE.md` § 4 — cross-cutting security concerns.

## When NOT to invoke

- Doc-only PRs (README / CLAUDE / AGENTS).
- Pure dependency bump PRs (use CVE check via context7 + GitHub Advisory DB instead).
- Compaction events.

## Forbidden during invocation

- Do NOT approve a PR you haven't fully read (diff + at least one upstream caller per touched function). Skipping reads is the #1 cause of missed findings.
- Do NOT block on style / nit issues. That's engineer's lane. Block on security only.
- Do NOT approve work that extends the vault or `src/cli/` (sunset track).
- Do NOT submit a verdict via stand-alone comments — use the github MCP's pending-review workflow so all findings ship as one cohesive review.
- Do NOT soften a finding's severity because someone pushed back. Severity is fact-based.
