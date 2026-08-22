import pytest

from src.evaluation.reporting import per_requester_tokens, per_run_tokens


def _store_with_calls(tmp_path):
    from src.tracing.storage import ExperimentStore
    store = ExperimentStore(tmp_path / "runs.duckdb")
    run_id = store.new_run({"id": "adi", "name": "Adi"}, "query", {})
    store.add_call(run_id, {"stage": "need_interpreter", "model": "gpt-5.6-luna", "reasoning_effort": "low", "prompt_version": "v1", "usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 20, "reasoning_tokens": 0, "total_tokens": 120}, "request": {}, "response": {}, "stream_events": [], "latency_ms": 100.0, "estimated_cost_usd": 0.001})
    store.add_call(run_id, {"stage": "embeddings", "model": "text-embedding-3-large", "reasoning_effort": None, "prompt_version": "profile_vectors_v1", "call_type": "embedding", "usage": {"input_tokens": 50, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 50}, "request": {}, "response": {}, "stream_events": [], "latency_ms": 50.0, "estimated_cost_usd": 0.0002})
    store.finish_run(run_id, need=None, status="completed", error=None, latency_ms=150.0, estimated_cost=0.0012)
    return store, run_id


def test_per_run_tokens_sums_stages(tmp_path):
    store, run_id = _store_with_calls(tmp_path)
    rows = per_run_tokens(store)
    assert len(rows) == 1
    assert rows[0]["run_id"] == run_id
    assert rows[0]["total_tokens"] == 170
    assert rows[0]["total_cost_usd"] == pytest.approx(0.0012, abs=1e-6)


def test_per_requester_tokens_aggregates(tmp_path):
    store, _ = _store_with_calls(tmp_path)
    rows = per_requester_tokens(store)
    assert len(rows) == 1
    assert rows[0]["requester_id"] == "adi"
    assert rows[0]["total_tokens"] == 170
    assert rows[0]["run_count"] == 1
