---
description: Enforce the engineer Manual QA Gate — per-surface verification that the shipped change actually works through the user's surface, not just that ruff/pytest pass. Use before any "ready for PR" hand-back, after every quality-gate clear, when you catch yourself thinking "this should work". Triggers on phrases like "manual qa", "qa gate", "before hand-back", "before pr", "ready to ship", "verify it works", "smoke test", "exercise the surface".
---

# engineer-manual-qa-gate

`ruff` catches style. `pytest` catches what test authors anticipated. **Neither catches "actually works through user's surface."** This gate = engineer's contract w/ user: done means you exercised deliverable through matching surface + observed it working — within current turn. Reading source + concluding "this should work" does NOT pass.

## When to invoke

- After quality gates clear (`ruff check`, `ruff format --check`, `pytest -x`, optional `NAAVIK_LIVE_DB=1 pytest -x`).
- Before drafting PR description.
- Before saying "ready to ship" / "ready for review" / handing back to manager.
- When you catch yourself writing "this should work" — that's the smell this gate fixes.

## Steps

Walk matching row for your surface. Execute driver script. Capture evidence (output, screenshot, side-effect verification). Note in hand-back Test plan section.

### Per-surface gate matrix

| Surface | Tool | Driver |
|---|---|---|
| **HTMX page / UI** | Playwright via `tests/visual/capture.py` | Capture desktop (1440×900) + mobile (375×812). Compare to mockup. Eyeball swap targets actually rendered. |
| **REST API endpoint** | `curl` or HTTP driver in tests | Hit endpoint w/ realistic payload. Check status + headers + body shape against Pydantic response model. |
| **Cron job** | Direct Python import | `python -c "import asyncio; from src.scheduler.jobs import <job>; asyncio.run(<job>())"`. Observe side effects: DB row, Discord message, file write. |
| **DB migration** | Alembic | `uv run alembic upgrade head` → `psql -h 127.0.0.1 -p 5433 -U naavik -d naavik` to inspect schema → `uv run alembic downgrade -1 && upgrade head` for reversibility. |
| **Service method** | Minimal driver script | Import + call w/ realistic args from seed/sample data. Verify output + persisted state. |
| **Config validator** (e.g. PC.5) | Manual env exercise | Export env vars triggering validation, boot app, observe error message + exit behavior. |
| **CLI (deprecated)** | Direct exec | `uv run naavik vault status`. **DO NOT add new CLI surfaces** — see `engineer.md § CLI + vault sunset`. |
| **No matching surface** | Ask | "How would user discover this works?" Do exactly that. |

### Driver-script templates

**HTMX page:**
```bash
nix run .#dev &   # or rely on running orchestrator
sleep 5            # wait for [app] startup
uv run python tests/visual/capture.py --page /<route> --viewport 1440x900 --out /tmp/qa-desktop.png
uv run python tests/visual/capture.py --page /<route> --viewport 375x812 --out /tmp/qa-mobile.png
```
Visually compare /tmp/qa-{desktop,mobile}.png to `docs/design/mockups/{n}-<slug>-{desktop,mobile}.png`.

**REST API endpoint:**
```bash
curl -i -X POST http://localhost:8000/api/v1/<endpoint> \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${JWT}" \
  -d '<realistic JSON payload>'
```
Verify: HTTP status, response shape matches Pydantic model, headers (Set-Cookie / CSRF / Cache-Control), latency reasonable.

**Cron job manual trigger:**
```bash
uv run python -c "
import asyncio
from src.scheduler.jobs import <job_name>
asyncio.run(<job_name>())
"
```
Inspect side effect via `psql` or relevant log/file.

**DB migration both directions:**
```bash
uv run alembic upgrade head
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c '\d+ <table>'
uv run alembic downgrade -1
uv run alembic upgrade head
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c '\d+ <table>'
```
Verify: schema matches migration's `op.create_*` ops, then matches after round-trip.

**Service method:**
```bash
uv run python -c "
import asyncio
from src.db.session import AsyncSessionLocal
from src.services.<module> import <function>

async def main():
    async with AsyncSessionLocal() as session:
        result = await <function>(session, <realistic args>)
        print(result)

asyncio.run(main())
"
```

**Config validator (e.g. boot-time SECRET_KEY enforcement):**
```bash
export SECRET_KEY='change-me-in-production'
uv run python -c "from src.config import Settings; Settings()"
# Expect: clear validation error pointing at rule violated.

export SECRET_KEY='valid-32-byte-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
uv run python -c "from src.config import Settings; print(Settings().secret_key[:8])"
# Expect: prints first 8 chars cleanly.
```

## Evidence capture for hand-back

Each hand-back `Tests:` section must include manual QA outcome w/ one line of evidence:

```
Tests:
  ruff check .          PASS
  ruff format --check . PASS
  pytest -x             PASS (47 passed, 0 failed)
  manual QA:
    surface=HTMX outcome=pass evidence=/tmp/qa-desktop.png matches mockup 7-discover-desktop.png; mobile likewise
    surface=API  outcome=pass evidence=POST /api/v1/jobs returned 201 + Job(id=42, ...) shape OK
    surface=migration outcome=pass evidence=upgrade + downgrade -1 + upgrade head all clean; \d+ jobs shows new column nullable
```

Format mirrors tracing format in `.claude/agents/engineer.md § Tracing` (`QA_GATE surface=... outcome=...`).

## Canonical references

- `.claude/agents/engineer.md` § Manual QA Gate (canonical table).
- `.claude/agents/engineer.md` § Tracing (`QA_GATE` event format).
- `CLAUDE.md` § Visual QA with Playwright.
- `docs/RUNBOOK.md` § 5 — quality gates (test commands).

## When NOT to invoke

- Pure documentation PRs (no executable surface) — note "no executable surface; QA gate N/A" in hand-back.
- Trivial typo fixes — invariants check covers it.
- Compaction events.

## Forbidden during invocation

- Do NOT write "this should work" without exercising surface. That's the failure mode this gate prevents.
- Do NOT skip matching surface because you tested adjacent one. UI test ≠ API test ≠ cron test.
- Do NOT pass gate w/ screenshot mismatch by saying "close enough" — > 1% pixel delta is regression.
- Do NOT mark migration QA-passed without running both directions (`upgrade` AND `downgrade -1 && upgrade head`).
