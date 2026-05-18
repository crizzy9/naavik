---
description: Wrap every LLM call in `services/llm_tracker.tracked_call(...)` so `ApiUsage` rows persist for cost tracking, latency, and the daily cost cap. Bare `await client.messages.create(...)` / `client.chat.completions.create(...)` / `ollama.chat(...)` is forbidden. Use whenever you call any LLM provider SDK in service code or a route handler, when reviewing a diff for LLM usage, when implementing a new service that talks to Anthropic / OpenAI / Ollama. Triggers on phrases like "llm call", "anthropic", "openai", "ollama", "messages.create", "chat.completions", "track api usage", "cost cap", "tracked_call".
---

# engineer-llm-tracker-wrap

Every LLM call flows through `services/llm_tracker.tracked_call(...)` so `ApiUsage` rows persist for daily cost cap (`Settings.daily_llm_cost_cap_usd`), cost telemetry SQL (`docs/RUNBOOK.md § 3.2`), and per-provider failure-rate monitor. Bare `await client.messages.create(...)` bypasses all of that — auto-apply cron's hard cap relies on every call being counted. Non-negotiable.

## When to invoke

- Implementing service method talking to any LLM (Anthropic / OpenAI / Ollama / future).
- Touching `src/services/scorer.py`, `cover_letter.py`, `resume_tailor.py`, `extractor.py`, or any `src/services/` using LLM output.
- Reviewing diff introducing `await client.<...>(...)` against LLM SDK.
- Adding new LLM provider via `src/llm/<provider>.py`.

## Steps

1. **Identify LLM call.** Common patterns:
   ```python
   # Anthropic
   response = await anthropic_client.messages.create(...)

   # OpenAI
   response = await openai_client.chat.completions.create(...)

   # Ollama
   response = await ollama.chat(...)
   ```
   Search: `Grep "messages.create|chat.completions.create|ollama.chat" --type py`.

2. **Confirm wrapper exists.** Read `src/services/llm_tracker.py`. Signature roughly:
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

3. **Rewrite call site** to route through wrapper:
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

4. **Verify abstract interface.** `src/llm/base.py` = abstract LLM interface; concrete `src/llm/{anthropic,openai,ollama}.py` impls = what `tracked_call` orchestrates. Touching `base.py` → ensure contract still works for tracked_call signature.

5. **Args.** Keep `provider` to 3-name vocabulary (`anthropic` / `openai` / `ollama`). Use EXACT model string SDK accepts. `operation` = free-form short string — match existing via `grep "operation=" src/services/`; SQL telemetry groups by it.

6. **Pydantic structured output.** Anthropic + OpenAI both support natively. Pydantic models for response; pass through wrapper's return type:
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

7. **QA gate.** After implementation, check ApiUsage row written:
   ```bash
   psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c \
     "SELECT provider, model, operation, cost_usd, latency_ms, ok FROM api_usage ORDER BY occurred_at DESC LIMIT 5;"
   ```
   Just-executed call as top row expected. Missing → `tracked_call` bypassed or commit() never fired.

## Cost cap enforcement reminder

`Settings.daily_llm_cost_cap_usd` is HARD, not soft. Auto-apply cron (5min) checks daily total before each call. Service bypassing `tracked_call` can drain user budget invisibly. Operational reason wrapper is mandatory.

## Canonical references

- `src/llm/base.py` — abstract LLM interface.
- `src/services/llm_tracker.py` — wrapper impl + ApiUsage write.
- `src/models/api_usage.py` — SQLModel entity persisted.
- `AGENTS.md` § Key Conventions § LLM Integration.
- `docs/RUNBOOK.md` § 3.2 — cost telemetry SQL.
- `docs/plans/POST_PHASE_1.md` § Monitoring playbook — daily check 1.

## When NOT to invoke

- Call is not LLM (HTTP client or local script).
- DELETING LLM call (not adding/modifying).
- Working on `tracked_call` itself (don't recursively wrap).
- Compaction events.

## Forbidden during invocation

- Do NOT bypass `tracked_call` "just for dev test". Auto-apply cron's cost cap depends on every call counted.
- Do NOT swallow exceptions inside `fn=...` lambda. Let `tracked_call` see failure so it sets `ok=False` + `error_code`.
- Do NOT hardcode provider in service. User picks via `Settings.llm_provider`; pull at call time.
- Do NOT skip Pydantic structured output for one-off LLM call. Structured output reduces re-parse cost + makes failure modes explicit.
