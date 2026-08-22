"""Token and cost reporting derived from persisted traces."""
from __future__ import annotations

from typing import Any

from src.tracing.storage import ExperimentStore


_TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")


def per_run_tokens(store: ExperimentStore, *, min_tokens: int = 0) -> list[dict[str, Any]]:
    """Token/cost per run, newest first. Set min_tokens>0 to skip legacy runs
    recorded before token estimation (their totals were 0)."""
    calls = store.dataframe("""
        select llm_calls.run_id, runs.requester_id, runs.query, runs.created_at,
               stage, call_type, model, input_tokens, cached_input_tokens,
               output_tokens, reasoning_tokens, total_tokens,
               llm_calls.latency_ms, llm_calls.estimated_cost_usd as call_cost_usd
        from llm_calls join runs on runs.id = llm_calls.run_id
    """)
    rows = []
    for run_id, group in calls.groupby("run_id", sort=False):
        base = {"run_id": run_id, "requester_id": group["requester_id"].iloc[0], "query": group["query"].iloc[0], "created_at": group["created_at"].iloc[0]}
        for field in _TOKEN_FIELDS:
            base[field] = int(group[field].sum())
        base["total_cost_usd"] = float(group["call_cost_usd"].sum())
        if base["total_tokens"] >= min_tokens:
            rows.append(base)
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return rows


def per_requester_tokens(store: ExperimentStore) -> list[dict[str, Any]]:
    rows = per_run_tokens(store)
    agg: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = agg.setdefault(row["requester_id"], {"requester_id": row["requester_id"], "run_count": 0, **{field: 0 for field in _TOKEN_FIELDS}, "estimated_cost_usd": 0.0})
        item["run_count"] += 1
        for field in _TOKEN_FIELDS:
            item[field] += row[field]
        item["estimated_cost_usd"] += row["total_cost_usd"]
    return list(agg.values())
