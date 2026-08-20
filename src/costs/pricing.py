"""Central, updateable model prices in USD per one million tokens.

Last verified against official OpenAI model pages on 2026-08-20.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


MODEL_PRICING = {
    "gpt-5.6-terra": ModelPricing(2.00, 0.20, 12.00),
    "gpt-5.6-luna": ModelPricing(0.20, 0.02, 1.20),
    "text-embedding-3-large": ModelPricing(0.13, 0.13, 0.0),
}


def pricing_for(model: str) -> ModelPricing:
    try:
        return MODEL_PRICING[model]
    except KeyError as exc:
        raise ValueError(f"No centralized pricing configured for model {model!r}.") from exc
