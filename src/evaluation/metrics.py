from __future__ import annotations

from statistics import mean
from typing import Any, Iterable

GOOD_RATINGS = frozenset({"good", "great"})


def ranking_metrics(ratings: Iterable[str], ks: tuple[int, ...] = (1, 3, 5)) -> dict[str, float]:
    ordered = [str(rating).strip().lower() for rating in ratings]
    metrics: dict[str, float] = {}
    for k in ks:
        window = ordered[:k]
        good = sum(rating in GOOD_RATINGS for rating in window)
        metrics[f"Good@{k}"] = good / len(window) if window else 0.0
        metrics[f"AnyGood@{k}"] = float(good > 0)
    return metrics


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def aggregate_metrics(runs: Iterable[dict[str, Any]]) -> dict[str, float | int]:
    rows = list(runs)
    costs = [float(row.get("estimated_cost_usd") or 0.0) for row in rows]
    latencies = [float(row.get("total_latency_ms") or 0.0) for row in rows]
    completed = sum(row.get("status") == "completed" for row in rows)
    return {
        "runs": len(rows), "completion_rate": completed / len(rows) if rows else 0.0,
        "average_cost_usd": mean(costs) if costs else 0.0,
        "p50_cost_usd": _percentile(costs, 0.50), "p95_cost_usd": _percentile(costs, 0.95),
        "average_latency_ms": mean(latencies) if latencies else 0.0,
        "p50_latency_ms": _percentile(latencies, 0.50), "p95_latency_ms": _percentile(latencies, 0.95),
    }
