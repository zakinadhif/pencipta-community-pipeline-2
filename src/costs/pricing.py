"""Central, updateable model prices in USD per one million tokens.

Last verified against official OpenAI model pages on 2026-08-20.

Custom OpenAI-compatible providers can declare per-model prices via
`MODEL_PRICE_<NAME>=<input>,<output>` environment variables (cached input
follows the input price). A model without any known price reports estimated
cost 0 rather than raising, so custom models never break the pipeline.
"""
from __future__ import annotations

import os
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


def _custom_prices() -> dict[str, ModelPricing]:
    prices: dict[str, ModelPricing] = {}
    for key, value in os.environ.items():
        if not key.startswith("MODEL_PRICE_"):
            continue
        model = key[len("MODEL_PRICE_"):]
        parts = [part.strip() for part in value.split(",")]
        if len(parts) < 2:
            continue
        try:
            input_price, output_price = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        prices[model] = ModelPricing(input_price, input_price, output_price)
    return prices


def pricing_for(model: str) -> ModelPricing:
    known = {**MODEL_PRICING, **_custom_prices()}
    try:
        return known[model]
    except KeyError:
        return ModelPricing(0.0, 0.0, 0.0)
