from src.agents.profile_compiler import PROFILE_SCHEMA
from src.costs.calculator import estimate_cost
from src.costs.pricing import pricing_for
from src.pipeline import PipelineConfig, INTRODUCTION_SCHEMA, MATCH_SCHEMA, NEED_SCHEMA
from src.schemas.profile import INTERACTION_TYPES
from src.tracing.trace import make_trace
from src.evaluation.metrics import aggregate_metrics, ranking_metrics


def test_pipeline_config_defaults_keep_legacy_judge_behavior():
    config = PipelineConfig()
    assert config.min_judge_score == 0.0
    assert config.retrieval_count == 30
    assert config.judge_shortlist == 12


def strict_schema_errors(schema, path="$"):
    errors = []
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            properties = schema.get("properties", {})
            missing = set(properties) - set(schema.get("required", []))
            if missing:
                errors.append((path, missing))
            if schema.get("additionalProperties") is not False:
                errors.append((path, {"additionalProperties"}))
            for name, child in properties.items():
                errors.extend(strict_schema_errors(child, f"{path}.{name}"))
        if schema.get("type") == "array":
            errors.extend(strict_schema_errors(schema.get("items", {}), f"{path}[]"))
    return errors


def test_all_structured_output_schemas_are_strict_compatible():
    for schema in (PROFILE_SCHEMA, NEED_SCHEMA, MATCH_SCHEMA, INTRODUCTION_SCHEMA):
        assert strict_schema_errors(schema) == []


def test_profile_schema_restricts_open_to_to_supported_interactions():
    open_to_items = PROFILE_SCHEMA["properties"]["openTo"]["items"]
    assert set(open_to_items["enum"]) == INTERACTION_TYPES


def test_centralized_pricing_and_trace_cost():
    usage = {
        "input_tokens": 1000,
        "cached_input_tokens": 100,
        "output_tokens": 100,
        "reasoning_tokens": 0,
        "total_tokens": 1100,
    }
    assert pricing_for("gpt-5.6-luna").output_per_million > 0
    assert estimate_cost(usage, "gpt-5.6-luna") > 0
    trace = make_trace(
        stage="test", model="gpt-5.6-luna", reasoning_effort="low",
        prompt_version="test_v1", request={}, response={"usage": usage}, latency_ms=5,
    )
    assert trace.estimated_cost_usd > 0
    assert trace.input_tokens == 1000


def test_human_ranking_and_run_aggregate_metrics():
    metrics = ranking_metrics(["Good", "Bad", "Great", "Unrated", "Good"])
    assert metrics["Good@1"] == 1.0
    assert metrics["Good@3"] == 2 / 3
    assert metrics["AnyGood@5"] == 1.0
    aggregate = aggregate_metrics([
        {"status": "completed", "estimated_cost_usd": 1.0, "total_latency_ms": 100},
        {"status": "failed", "estimated_cost_usd": 3.0, "total_latency_ms": 300},
    ])
    assert aggregate["completion_rate"] == 0.5
    assert aggregate["average_cost_usd"] == 2.0
    assert aggregate["p50_latency_ms"] == 200.0
