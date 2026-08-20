"""Per-call usage and estimated cost helpers."""
from __future__ import annotations

from typing import Any, Protocol

from .pricing import pricing_for


class CostRates(Protocol):
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


def usage_from_response(response: Any) -> dict[str, int]:
    data = response.model_dump() if hasattr(response, "model_dump") else (response or {})
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    input_details = usage.get("input_tokens_details", {}) or {}
    output_details = usage.get("output_tokens_details", {}) or {}
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    return {"input_tokens": int(input_tokens or 0), "cached_input_tokens": int(input_details.get("cached_tokens", 0) or 0), "output_tokens": int(usage.get("output_tokens", 0) or 0), "reasoning_tokens": int(output_details.get("reasoning_tokens", 0) or 0), "total_tokens": int(usage.get("total_tokens", 0) or 0)}


def estimate_cost(usage: dict[str, int], rates: CostRates | str) -> float:
    if isinstance(rates, str):
        rates = pricing_for(rates)
    return ((usage["input_tokens"] - usage["cached_input_tokens"]) * rates.input_per_million + usage["cached_input_tokens"] * rates.cached_input_per_million + usage["output_tokens"] * rates.output_per_million) / 1_000_000
