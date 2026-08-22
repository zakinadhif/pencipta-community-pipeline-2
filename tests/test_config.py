import pytest

from src.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_INTRO_MODEL, DEFAULT_JUDGE_MODEL, DEFAULT_NEED_MODEL, custom_model_prices, make_client, provider_config
from src.costs.pricing import ModelPricing, pricing_for


def test_pricing_for_unknown_model_returns_zero_rates(monkeypatch):
    monkeypatch.delenv("MODEL_PRICE_unknown-custom", raising=False)
    pricing = pricing_for("unknown-custom")
    assert pricing.input_per_million == 0.0
    assert pricing.output_per_million == 0.0


def test_pricing_reads_custom_model_price_from_env(monkeypatch):
    monkeypatch.setenv("MODEL_PRICE_gpt-4o-mini", "0.15,0.60")
    pricing = pricing_for("gpt-4o-mini")
    assert pricing.input_per_million == pytest.approx(0.15)
    assert pricing.output_per_million == pytest.approx(0.60)
    assert pricing.cached_input_per_million == pytest.approx(0.15)


def test_custom_model_prices_collects_only_valid_entries(monkeypatch):
    monkeypatch.setenv("MODEL_PRICE_alpha", "1.0,2.0")
    monkeypatch.setenv("MODEL_PRICE_beta", "not,a,number")
    prices = custom_model_prices()
    assert prices == {"alpha": {"input_per_million": 1.0, "output_per_million": 2.0}}


def test_provider_config_defaults(monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "NEED_MODEL", "JUDGE_MODEL", "INTRODUCTION_MODEL", "EMBEDDING_MODEL"):
        monkeypatch.delenv(name, raising=False)
    config = provider_config()
    assert config["need_model"] == DEFAULT_NEED_MODEL
    assert config["judge_model"] == DEFAULT_JUDGE_MODEL
    assert config["introduction_model"] == DEFAULT_INTRO_MODEL
    assert config["embedding_model"] == DEFAULT_EMBEDDING_MODEL
    assert config["base_url"] is None


def test_provider_config_reads_custom_values(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("NEED_MODEL", "my-need-model")
    config = provider_config()
    assert config["base_url"] == "https://example.invalid/v1"
    assert config["need_model"] == "my-need-model"


def test_make_client_honors_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = make_client()
    assert client is not None
    assert "example.invalid" in str(client.base_url)
