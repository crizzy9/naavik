"""Tool-loop orchestrator — plan 67 (0.3.4) § C.4 / T5.

Claude calls 5 tools in a loop until convergence ("ship" / "ship_with_caveats")
or iteration cap (N=3 per OQ-3). Each iteration:
1. Claude emits zero or more `tool_use` blocks (we may have a final text).
2. We dispatch each tool to its delegate service.
3. We send back `tool_result` blocks; Claude reads + decides next step.
4. Final `text` block starting with "ship" or "ship_with_caveats" exits.

Budget-aware: probes daily cost cap between iterations; exits early with
`final_decision="exhausted"` when approaching cap.

Tools delegate to existing services where possible:
- ats_parse_test            -> ats_parser_fidelity.validate_parse_fidelity
- detector_test             -> detector_loop.run_detector_loop
- recruiter_skim_score      -> inline Claude call (lightweight skim)
- keyword_coverage_check    -> keyword_coverage.compute_coverage
- defensibility_check       -> inline bullet-vs-profile closure

NO `interleaved-thinking-2025-05-14` beta header on Sonnet 4.6 / Opus 4.7
per T5 — adaptive thinking auto-enables there. Conditional header for
older models lives in the AnthropicProvider; we don't override at this
layer.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from llm import get_provider
from llm.anthropic import AnthropicProvider
from llm.base import LLMProviderError
from llm.prompts.orchestrate_refinement import (
    TOOL_DEFINITIONS,
    build_orchestrator_prompt,
)
from services import generation as dg
from services import llm_tracker
from services.ats_parser_fidelity import validate_parse_fidelity
from services.detector_loop import run_detector_loop
from services.keyword_coverage import compute_coverage
from services.llm_tracker import _persist_usage as _persist_apiusage

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from models import Settings

log = logging.getLogger(__name__)

DEFAULT_MAX_ITERS = 3

# Tool inputs carry Claude-controlled text. JD content (scraper-sourced,
# untrusted) can flow through `tool_use.input["text"]` into a fresh LLM call.
# Reject inputs containing obvious prompt-injection markers BEFORE
# interpolating into the prompt — defense-in-depth on top of provider-level
# alignment. List stays short + targeted to avoid over-aggressive filtering.
_INJECTION_MARKERS_BASE = (
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "disregard all",
    "you are now",
    "<|im_start|>",
    "<|im_end|>",
    "###system",
    "### system",
)
_TOOL_TEXT_MAX_CHARS = 3000
_LOG_TRUNC_MAX_BYTES = 200


def _injection_markers_from_env() -> tuple[str, ...]:
    """Plan 75 / 0.3.3.10 — env-var override appends extra markers.

    `NAAVIK_TOOL_LOOP_MARKERS` = comma-separated phrases (case-insensitive
    match). Empty / unset → no extras. Values are lowercased + stripped;
    empties dropped. Operator extensibility hook for future LLM-provider
    tells without code edit.
    """
    raw = os.environ.get("NAAVIK_TOOL_LOOP_MARKERS", "").strip()
    if not raw:
        return ()
    parts = tuple(p.strip().lower() for p in raw.split(",") if p.strip())
    return parts


def _get_injection_markers() -> tuple[str, ...]:
    """Combined marker tuple: baseline + env-var extras.

    Recomputed on every call so test monkeypatches (`monkeypatch.setenv`)
    take effect without import-time caching. Cost is negligible — tool-loop
    runs per-application, not per-request.
    """
    return _INJECTION_MARKERS_BASE + _injection_markers_from_env()


# Back-compat alias: previously _INJECTION_MARKERS was a tuple constant; some
# tests / external consumers reference the name directly. Keep the symbol
# pointing at the BASE list so behavior matches pre-plan-75 when no env var
# is set; the runtime path uses `_get_injection_markers()`.
_INJECTION_MARKERS = _INJECTION_MARKERS_BASE


def _truncate_for_log(s: str, max_bytes: int = _LOG_TRUNC_MAX_BYTES) -> str:
    """Plan 75 / 0.3.3.10 — single source for 200-byte log truncation.

    Mirrors `originality.py:91` which uses `bytes(body[:200]).decode(...)`.
    Centralizes the rule so future log-truncation sites use the same shape.
    """
    if not s:
        return s
    encoded = s.encode("utf-8", errors="ignore")
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _sanitize_tool_text(text: str) -> tuple[str, bool]:
    """Cap length + flag injection markers. Returns (cleaned, rejected)."""
    capped = text[:_TOOL_TEXT_MAX_CHARS]
    lowered = capped.lower()
    for marker in _get_injection_markers():
        if marker in lowered:
            return capped, True
    return capped, False


class SkimScore(BaseModel):
    """Lightweight recruiter-skim simulator output."""

    score: int = Field(ge=0, le=10)
    top_signals: list[str] = Field(default_factory=list, max_length=5)
    missing_signals: list[str] = Field(default_factory=list, max_length=5)


@dataclass(slots=True)
class ToolCallRecord:
    """One tool invocation inside the orchestrator loop."""

    name: str
    input: dict
    result_summary: str


@dataclass(slots=True)
class IterationRecord:
    """Per-iteration audit-trail entry."""

    iter_n: int
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    decision: str = "continue"
    cost_usd: float = 0.0


@dataclass(slots=True)
class ToolLoopReport:
    """Final orchestrator verdict + per-iteration trail."""

    final_decision: str = "exhausted"
    iterations: list[IterationRecord] = field(default_factory=list)
    degraded_reason: str | None = None


def _build_tool_delegates(
    *,
    resume_text: str,
    cover_letter_text: str,
    resume_pdf_path: Path | None,
    job_must_haves: list[str],
    selected_bullet_ids: list[int],
    profile_bullet_ids: set[int],
    settings: Settings,
    user_id: int,
    session: AsyncSession | None,
    application_id: int | None,
    system: str | None,
    cache_system: bool,
) -> dict[str, Any]:
    """Return a dict mapping tool_name -> async callable.

    Each callable accepts the `tool_use.input` dict and returns a JSON-able
    summary that Claude will see as the `tool_result`.
    """

    async def ats_parse_test(_input: dict) -> dict:
        if resume_pdf_path is None or not resume_pdf_path.exists():
            return {"score": None, "tier": "unknown", "fields_missing": ["pdf not available"]}
        report = validate_parse_fidelity(
            resume_pdf_path,
            threshold=settings.parse_fidelity_threshold,
        )
        return {
            "score": report.score,
            "tier": report.tier,
            "fields_missing": [k for k, v in report.fields_found.items() if not v],
        }

    async def detector_test(input_: dict) -> dict:
        raw_text = str(input_.get("text") or resume_text)
        text, rejected = _sanitize_tool_text(raw_text)
        if rejected:
            log.warning("detector_test rejected: suspected prompt injection")
            return {
                "final_confidence": 0.0,
                "target_met": False,
                "iterations": 0,
                "originality_score": None,
                "rejected": "suspected_injection",
            }
        report = await run_detector_loop(
            text,
            session=session,
            user_id=user_id,
            settings=settings,
            application_id=application_id,
            system=system,
            cache_system=cache_system,
            max_iters=2,  # tool-loop inner detector capped tighter
        )
        return {
            "final_confidence": report.final_confidence,
            "target_met": report.target_met,
            "iterations": len(report.iterations),
            "originality_score": report.originality_score,
        }

    async def recruiter_skim_score(input_: dict) -> dict:
        raw_text = str(input_.get("text") or resume_text)
        text, rejected = _sanitize_tool_text(raw_text)
        if rejected:
            log.warning("recruiter_skim_score rejected: suspected prompt injection")
            return {
                "score": 0,
                "top_signals": [],
                "missing_signals": ["rejected_suspected_injection"],
            }
        provider = get_provider(settings)
        prompt = (
            "Simulate a recruiter doing a 6-second skim of this candidate's "
            "resume. Score 0-10 on whether you'd progress them to phone "
            "screen. List top signals captured + missing signals.\n\n"
            f"Resume text:\n{text}"
        )
        try:
            result = await llm_tracker.tracked_call(
                session=session,
                user_id=user_id,
                provider=provider,
                method="structured",
                prompt_name="recruiter_skim_score",
                application_id=application_id,
                prompt=prompt,
                schema=SkimScore,
                max_tokens=600,
                system=system,
                cache_system=cache_system,
            )
            value = result.value or {}
            return {
                "score": int(value.get("score") or 0),
                "top_signals": list(value.get("top_signals") or []),
                "missing_signals": list(value.get("missing_signals") or []),
            }
        except LLMProviderError as exc:
            log.warning("recruiter_skim_score failed: %s", exc)
            return {"score": 0, "top_signals": [], "missing_signals": ["tool_failed"]}

    async def keyword_coverage_check(_input: dict) -> dict:
        cov = compute_coverage(
            job_must_haves,
            resume_text,
            threshold=settings.parse_fidelity_threshold,
        )
        return {
            "score": cov.score,
            "found_keywords": cov.found_keywords,
            "missing_keywords": cov.missing_keywords,
        }

    async def defensibility_check(_input: dict) -> dict:
        selected_set = set(selected_bullet_ids)
        ungrounded = sorted(selected_set - profile_bullet_ids)
        return {
            "all_grounded": len(ungrounded) == 0,
            "ungrounded_count": len(ungrounded),
            "ungrounded_ids": ungrounded,
        }

    return {
        "ats_parse_test": ats_parse_test,
        "detector_test": detector_test,
        "recruiter_skim_score": recruiter_skim_score,
        "keyword_coverage_check": keyword_coverage_check,
        "defensibility_check": defensibility_check,
    }


def _summarize_result(name: str, payload: dict) -> str:
    """One-line summary of a tool result for the audit trail."""
    if name == "ats_parse_test":
        return f"score={payload.get('score')} tier={payload.get('tier')}"
    if name == "detector_test":
        return (
            f"conf={payload.get('final_confidence')} target_met={payload.get('target_met')} "
            f"orig={payload.get('originality_score')}"
        )
    if name == "recruiter_skim_score":
        return f"skim={payload.get('score')}/10"
    if name == "keyword_coverage_check":
        return f"coverage={payload.get('score')}"
    if name == "defensibility_check":
        return (
            f"grounded={payload.get('all_grounded')} ungrounded={payload.get('ungrounded_count')}"
        )
    return json.dumps(payload)[:120]


async def orchestrate_refinement(
    *,
    resume_text: str,
    cover_letter_text: str,
    resume_pdf_path: Path | None,
    job_role: str,
    job_must_haves: list[str],
    selected_bullet_ids: list[int],
    profile_bullet_ids: set[int],
    settings: Settings,
    user_id: int,
    session: AsyncSession | None,
    application_id: int | None = None,
    system: str | None = None,
    cache_system: bool = False,
    max_iters: int = DEFAULT_MAX_ITERS,
) -> ToolLoopReport:
    """Run the tool-loop orchestrator until convergence or cap.

    Only Anthropic providers support tool-use orchestration on this code
    path (OpenAI/Ollama paths land in a follow-up). When the configured
    provider isn't Anthropic, the orchestrator short-circuits with
    `degraded_reason="non_anthropic_provider"`.
    """
    provider = get_provider(settings)
    if not isinstance(provider, AnthropicProvider):
        return ToolLoopReport(
            final_decision="ship",
            iterations=[],
            degraded_reason="non_anthropic_provider",
        )

    delegates = _build_tool_delegates(
        resume_text=resume_text,
        cover_letter_text=cover_letter_text,
        resume_pdf_path=resume_pdf_path,
        job_must_haves=job_must_haves,
        selected_bullet_ids=selected_bullet_ids,
        profile_bullet_ids=profile_bullet_ids,
        settings=settings,
        user_id=user_id,
        session=session,
        application_id=application_id,
        system=system,
        cache_system=cache_system,
    )

    user_message = build_orchestrator_prompt(
        resume_excerpt=resume_text,
        cover_excerpt=cover_letter_text,
        role=job_role,
        skills=job_must_haves,
        selected_ids=selected_bullet_ids,
        max_iters=max_iters,
    )
    messages: list[dict] = [{"role": "user", "content": user_message}]
    iterations: list[IterationRecord] = []
    final_decision = "exhausted"

    for iter_n in range(max_iters):
        if session is not None and await dg.is_cost_capped(session, user_id, settings):
            iterations.append(IterationRecord(iter_n=iter_n, decision="cost_cap"))
            return ToolLoopReport(
                final_decision="exhausted",
                iterations=iterations,
                degraded_reason="cost_cap_reached",
            )

        create_kwargs: dict = {
            "model": provider.model_name,
            "max_tokens": 2048,
            "tools": TOOL_DEFINITIONS,
            "messages": messages,
        }
        if system is not None:
            if cache_system:
                create_kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                create_kwargs["system"] = system

        try:
            # Plan 91 6.4 — through the provider surface, not provider._client.
            response = await provider.tool_use(**create_kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning("tool_loop orchestrator call failed at iter %d: %s", iter_n, exc)
            # Failed orchestrator calls used to vanish from ApiUsage entirely.
            await _persist_apiusage(
                session,
                user_id=user_id,
                provider=provider,
                method="complete",
                prompt_name=f"orchestrate_refinement_iter_{iter_n}",
                application_id=application_id,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=0,
                succeeded=False,
                error_kind="provider_error",
            )
            iterations.append(IterationRecord(iter_n=iter_n, decision="provider_error"))
            return ToolLoopReport(
                final_decision="ship_with_caveats",
                iterations=iterations,
                degraded_reason=f"orchestrator_error: {exc}",
            )

        # Persist orchestrator-iter cost manually (we bypassed tracked_call
        # because tool-use streaming doesn't fit the structured() shape).
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cost = provider.estimate_cost(input_tokens=input_tokens, output_tokens=output_tokens)
        await _persist_apiusage(
            session,
            user_id=user_id,
            provider=provider,
            method="complete",
            prompt_name=f"orchestrate_refinement_iter_{iter_n}",
            application_id=application_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=0,
            succeeded=True,
            error_kind=None,
        )

        iter_record = IterationRecord(iter_n=iter_n, cost_usd=cost)

        content = list(getattr(response, "content", []) or [])

        # Collect tool_use + final text blocks
        tool_use_blocks = [b for b in content if getattr(b, "type", None) == "tool_use"]
        text_blocks = [b for b in content if hasattr(b, "text")]

        # If Claude emitted text and no tool_use, this is the final decision.
        if tool_use_blocks:
            tool_results: list[dict] = []
            for block in tool_use_blocks:
                name = getattr(block, "name", "")
                tool_input = dict(getattr(block, "input", {}) or {})
                delegate = delegates.get(name)
                if delegate is None:
                    payload = {"error": f"unknown tool: {name}"}
                else:
                    try:
                        payload = await delegate(tool_input)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("tool %s raised: %s", name, exc)
                        payload = {"error": str(exc)}
                iter_record.tool_calls.append(
                    ToolCallRecord(
                        name=name,
                        input=tool_input,
                        result_summary=_summarize_result(name, payload),
                    )
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": getattr(block, "id", ""),
                        "content": json.dumps(payload),
                    }
                )

            # Append assistant turn (the model's tool_use) + user turn (results)
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": tool_results})
            iter_record.decision = "tool_calls"
            iterations.append(iter_record)
            continue

        # No tool_use — final text. Inspect prefix for decision.
        final_text = " ".join(getattr(b, "text", "") for b in text_blocks).strip().lower()
        if final_text.startswith("ship_with_caveats"):
            final_decision = "ship_with_caveats"
        elif final_text.startswith("ship"):
            final_decision = "ship"
        else:
            final_decision = "ship_with_caveats"
        iter_record.decision = final_decision
        iterations.append(iter_record)
        return ToolLoopReport(
            final_decision=final_decision,
            iterations=iterations,
        )

    return ToolLoopReport(
        final_decision="exhausted",
        iterations=iterations,
    )
