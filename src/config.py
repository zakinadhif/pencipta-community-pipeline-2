"""Runtime configuration from environment variables.

All values fall back to defaults so the pipeline works without a custom
provider. Only a custom model price may be declared per model via
`MODEL_PRICE_<NAME>=<input>,<output>` (USD per one million tokens).
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_NEED_MODEL = "gpt-5.6-luna"
DEFAULT_JUDGE_MODEL = "gpt-5.6-terra"
DEFAULT_INTRO_MODEL = "gpt-5.6-luna"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


def _env(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def provider_config() -> dict[str, Any]:
    return {
        "api_key": os.getenv("OPENAI_API_KEY", "").strip(),
        "base_url": os.getenv("OPENAI_BASE_URL", "").strip() or None,
        "need_model": _env("NEED_MODEL", DEFAULT_NEED_MODEL),
        "judge_model": _env("JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
        "introduction_model": _env("INTRODUCTION_MODEL", DEFAULT_INTRO_MODEL),
        "embedding_model": _env("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        "custom_prices": custom_model_prices(),
    }


def custom_model_prices() -> dict[str, dict[str, float]]:
    prices: dict[str, dict[str, float]] = {}
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
        prices[model] = {"input_per_million": input_price, "output_per_million": output_price}
    return prices


def make_client(api_key: str | None = None, base_url: str | None = None) -> Any:
    """Build an OpenAI client honoring a custom base URL when configured."""
    from openai import OpenAI
    resolved_key = api_key or provider_config()["api_key"]
    resolved_url = base_url or provider_config()["base_url"]
    if not resolved_key:
        return None
    kwargs = {"api_key": resolved_key}
    if resolved_url:
        kwargs["base_url"] = resolved_url
    return OpenAI(**kwargs)
