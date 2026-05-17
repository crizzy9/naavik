---
description: Wrap every LLM call in `services/llm_tracker.tracked_call(...)` so `ApiUsage` rows persist for cost tracking, latency, and the daily cost cap. Bare `await client.messages.create(...)` / `client.chat.completions.create(...)` / `ollama.chat(...)` is forbidden. Use whenever you call any LLM provider SDK in service code or a route handler, when reviewing a diff for LLM usage, when implementing a new service that talks to Anthropic / OpenAI / Ollama. Triggers on phrases like "llm call", "anthropic", "openai", "ollama", "messages.create", "chat.completions", "track api usage", "cost cap", "tracked_call".
---

# engineer-llm-tracker-wrap

Every LLM call has to flow through `services/llm_tracker.tracked_call(...)` so `ApiUsage` rows persist for the daily cost cap (`Settings.daily_llm_cost_cap_usd`), the cost telemetry SQL queries in `docs/RUNBOOK.md § 3.2`, and the per-provider failure rate monitor. A bare `await client.messages.create(...)` bypasses all of that — and the auto-apply cron's hard cap relies on every call being counted. This is non-negotiable.

## When to invoke

- Implementing a service method that talks to any LLM (Anthropic / OpenAI / Ollama / future provider).
- Touching `src/services/scorer.py`, `src/services/cover_letter.py`, `src/services/resume_tailor.py`, `src/services/extractor.py`, or any service under `src/services/` that uses LLM output.
- Reviewing a diff that introduces an `await client.<something>(...)` call against an LLM SDK.
- Adding a new LLM provider via `src/llm/<provider>.py`.

## What this skill does

1. **Identify the LLM call.** Common patterns to find:
   ```python
   # Anthropic
   response = await anthropic_client.messages.create(...)

   # OpenAI
   response = await openai_client.chat.completions.create(...)

   # Ollama
   response = await ollama.chat(...)
   ```
   Search via `Grep "messages.create|chat.completions.create|ollama.chat" --type py`.

2. **Confirm the wrapper exists.** Read `src/services/llm_tracker.py` to verify the current signature. It looks roughly like:
   ```python
   async def tracked_call(
       session: AsyncSession,
       user_id: int,
       provider: str,           # "anthropic" | "openai" | "ollama"
       model: str,              # "claude-3-5-sonnet-20241022" | "gpt-4o-mini" | "llama3.1:8b"
       operation: str,          # "score_job" | "tailor_resume" | "draft_cover_letter" | ...
       fn: Callable[[], Awaitable[T]],
       prompt_tokens_estimate: int | None = None,
   ) -> T:
       """Wraps an LLM call; persists ApiUsage row (cost_usd, latency_ms, ok, error_code)."""
   ```

3. **Rewrite the call site** to route through the wrapper. Pattern:
   ```python
   # WRONG (bypasses cost tracking)
   response = await anthropic_client.messages.create(
       model="claude-3-5-sonnet-20241022",
       max_tokens=1024,
       messages=[{"role": "user", "content": prompt}],
   )

   # RIGHT
   from src.services.llm_tracker import tracked_call

   response = await tracked_call(
       session=session,
       user_id=current_user.id,
       provider="anthropic",
       model="claude-3-5-sonnet-20241022",
       operation="score_job",
       fn=lambda: anthropic_client.messages.create(
           model="claude-3-5-sonnet-20241022",
           max_tokens=1024,
           messages=[{"role": "user", "content": prompt}],
       ),
   )
   ```

4. **Verify the abstract interface.** `src/llm/base.py` is the abstract LLM interface; the concrete `src/llm/{anthropic,openai,ollama}.py` implementations are what `tracked_call` orchestrates. If you're touching `base.py`, ensure the contract still works for tracked_call's signature.

5. **Provider + model + operation arguments.** Keep `provider` to the 3-name vocabulary (`anthropic` / `openai` / `ollama`). Use the EXACT model string the SDK accepts. `operation` is a free-form short string — match existing values via `grep "operation=" src/services/`; the SQL telemetry groups by it.

6. **Pydantic structured output.** Both Anthropic + OpenAI support native structured output. Use Pydantic models for the response; pass them through the wrapper's return type. Example:
   ```python
   class ScoreResult(BaseModel):
       overall: int
       per_tag: dict[str, float]
       gaps: list[str]

   result: ScoreResult = await tracked_call(
       session=session, user_id=user.id, provider="anthropic",
       model="claude-3-5-sonnet-20241022", operation="score_job",
       fn=lambda: anthropic_client.messages.create(
           model="claude-3-5-sonnet-20241022",
           response_format={"type": "json_schema", "json_schema": ScoreResult.model_json_schema()},
           ...
       ),
   )
   ```

7. **QA gate verification.** After implementation, check the ApiUsage row was written:
   ```bash
   psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c \
     "SELECT provider, model, operation, cost_usd, latency_ms, ok FROM api_usage ORDER BY occurred_at DESC LIMIT 5;"
   ```
   Expect the just-executed call as the top row. If it's missing, `tracked_call` was bypassed or commit() never fired.

## Cost cap enforcement reminder

`Settings.daily_llm_cost_cap_usd` is HARD, not soft. The auto-apply cron (5min) checks the daily total before each call. If a service bypasses `tracked_call`, that service can drain the user's budget invisibly. This is the operational reason the wrapper is mandatory.

## Canonical references

- `src/llm/base.py` — abstract LLM interface.
- `src/services/llm_tracker.py` — the wrapper implementation + ApiUsage write.
- `src/models/api_usage.py` — the SQLModel entity persisted.
- `AGENTS.md` § Key Conventions § LLM Integration.
- `docs/RUNBOOK.md` § 3.2 — cost telemetry SQL queries.
- `docs/plans/POST_PHASE_1.md` § Monitoring playbook — daily check 1 (cost in last 24h).

## When NOT to invoke

- The call is not an LLM call (it's just an HTTP client or a local script).
- You're DELETING an LLM call (not adding/modifying one).
- You're working on `tracked_call` itself (don't recursively wrap).
- Compaction events.

## Forbidden during invocation

- Do NOT bypass `tracked_call` "just for a dev test". The auto-apply cron's cost cap depends on every call counted.
- Do NOT swallow exceptions inside the `fn=...` lambda. Let `tracked_call` see the failure so it sets `ok=False` + `error_code`.
- Do NOT hardcode a provider in a service. The user picks via `Settings.llm_provider`; pull at call time.
- Do NOT skip Pydantic structured output for a one-off LLM call. Structured output reduces re-parse cost and makes failure modes explicit.
