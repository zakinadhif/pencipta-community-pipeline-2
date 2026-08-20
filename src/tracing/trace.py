"""Standard trace construction shared by every model-backed stage."""
from __future__ import annotations

from typing import Any

from ..costs.calculator import estimate_cost, usage_from_response
from ..schemas.traces import LLMTrace

TRACE_STAGES = ("onboarding", "profile_compiler", "need_interpreter", "embeddings", "retrieval", "match_judge", "introduction")


def _dump(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


def make_trace(*, stage: str, model: str, reasoning_effort: str | None, prompt_version: str, request: Any, response: Any, latency_ms: float, ttft_ms: float | None = None, stream_events: list[dict[str, Any]] | None = None, error: str | None = None, call_type: str = "response") -> LLMTrace:
    usage = usage_from_response(response)
    try:
        cost = estimate_cost(usage, model)
    except ValueError:
        cost = 0.0
    return LLMTrace(
        stage=stage,
        model=model,
        reasoning_effort=reasoning_effort,
        prompt_version=prompt_version,
        request=request,
        response=_dump(response),
        input_tokens=usage["input_tokens"],
        cached_input_tokens=usage["cached_input_tokens"],
        output_tokens=usage["output_tokens"],
        reasoning_tokens=usage["reasoning_tokens"],
        total_tokens=usage["total_tokens"],
        ttft_ms=ttft_ms,
        latency_ms=latency_ms,
        estimated_cost_usd=cost,
        stream_events=stream_events or [],
        response_id=getattr(response, "id", None),
        error=error,
        call_type=call_type,
    )
