from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExperimentStore:
    """DuckDB persistence boundary for immutable pipeline observations."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(self.path)
        self.con.execute("""
            create table if not exists runs (
              id varchar primary key, requester_id varchar, query varchar,
              config_json varchar, requester_snapshot_json varchar,
              need_interpretation_json varchar, status varchar, error varchar,
              created_at varchar, completed_at varchar, total_latency_ms double,
              estimated_cost_usd double
            );
            create table if not exists llm_calls (
              id varchar primary key, run_id varchar, stage varchar, call_type varchar,
              model varchar, reasoning_effort varchar, prompt_version varchar,
              request_json varchar, response_json varchar, stream_events_json varchar,
              input_tokens bigint, cached_input_tokens bigint, output_tokens bigint,
              reasoning_tokens bigint, total_tokens bigint, ttft_ms double, latency_ms double,
              estimated_cost_usd double, response_id varchar, error varchar, created_at varchar
            );
            create table if not exists retrieval_results (
              run_id varchar, candidate_id varchar, retrieval_rank integer,
              offers_similarity double, interests_similarity double, reciprocal_similarity double,
              interaction_score double, prescore double, candidate_snapshot_json varchar
            );
            create table if not exists match_results (
              run_id varchar, candidate_id varchar, judge_rank integer, judge_score double,
              judge_reason varchar, introduction_json varchar, shown boolean
            );
            create table if not exists human_evaluations (
              id varchar primary key, run_id varchar, candidate_id varchar, rating varchar,
              notes varchar, created_at varchar
            );
            create table if not exists authoritative_cost_buckets (
              id varchar primary key, fetched_at varchar, start_time bigint, end_time bigint,
              project_id varchar, line_item varchar, amount_usd double, raw_json varchar
            );
        """)

    def new_run(self, requester: dict[str, Any], query: str, config: dict[str, Any]) -> str:
        run_id = str(uuid.uuid4())
        self.con.execute(
            "insert into runs values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [run_id, requester["id"], query, _json(config), _json(requester), None,
             "running", None, _now(), None, None, 0.0],
        )
        return run_id

    def finish_run(self, run_id: str, *, need: dict[str, Any] | None, status: str,
                   error: str | None, latency_ms: float, estimated_cost: float) -> None:
        self.con.execute(
            "update runs set need_interpretation_json=?, status=?, error=?, completed_at=?, total_latency_ms=?, estimated_cost_usd=? where id=?",
            [_json(need) if need else None, status, error, _now(), latency_ms, estimated_cost, run_id],
        )

    def add_call(self, run_id: str, trace: dict[str, Any]) -> None:
        if hasattr(trace, "to_dict"):
            trace = trace.to_dict()
        usage = trace.get("usage", {})
        if not usage:
            usage = {key: trace.get(key, 0) for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")}
        self.con.execute("insert into llm_calls values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            str(uuid.uuid4()), run_id, trace["stage"], trace.get("call_type", "response"),
            trace.get("model"), trace.get("reasoning_effort"), trace.get("prompt_version"),
            _json(trace.get("request")), _json(trace.get("response")), _json(trace.get("stream_events", [])),
            usage.get("input_tokens", 0), usage.get("cached_input_tokens", 0), usage.get("output_tokens", 0),
            usage.get("reasoning_tokens", 0), usage.get("total_tokens", 0), trace.get("ttft_ms"),
            trace.get("latency_ms"), trace.get("estimated_cost_usd", 0.0), trace.get("response_id"),
            trace.get("error"), _now(),
        ])

    def add_retrieval(self, run_id: str, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.con.execute("insert into retrieval_results values (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                run_id, row["candidate"]["id"], row["rank"], row["offers_similarity"],
                row["interests_similarity"], row["reciprocal_similarity"], row["interaction_score"],
                row["prescore"], _json(row["candidate"]),
            ])

    def add_match(self, run_id: str, match: dict[str, Any], rank: int) -> None:
        self.con.execute("insert into match_results values (?, ?, ?, ?, ?, ?, ?)", [
            run_id, match["candidate_id"], rank, match.get("score"), match.get("reason"),
            _json(match.get("introduction")), True,
        ])

    def add_evaluation(self, run_id: str, candidate_id: str, rating: str, notes: str) -> None:
        self.con.execute("insert into human_evaluations values (?, ?, ?, ?, ?, ?)",
                         [str(uuid.uuid4()), run_id, candidate_id, rating, notes, _now()])

    def add_authoritative_costs(self, buckets: list[dict[str, Any]]) -> None:
        for bucket in buckets:
            for result in bucket.get("results", []):
                self.con.execute("insert into authoritative_cost_buckets values (?, ?, ?, ?, ?, ?, ?, ?)", [
                    str(uuid.uuid4()), _now(), bucket.get("start_time"), bucket.get("end_time"),
                    result.get("project_id"), result.get("line_item"), result.get("amount", {}).get("value"), _json(result),
                ])

    def dataframe(self, sql: str, parameters: list[Any] | None = None):
        return self.con.execute(sql, parameters or []).fetchdf()
