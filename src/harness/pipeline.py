from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable

from openai import OpenAI

from .prompts import (INTRODUCTION_PROMPT, INTRODUCTION_VERSION, MATCH_JUDGE_PROMPT,
                      MATCH_JUDGE_VERSION, NEED_INTERPRETER_PROMPT, NEED_INTERPRETER_VERSION)
from .storage import ExperimentStore


@dataclass
class PipelineConfig:
    need_model: str = "gpt-4.1-mini"
    judge_model: str = "gpt-4.1-mini"
    introduction_model: str = "gpt-4.1-mini"
    reasoning_effort: str = "none"
    retrieval_count: int = 15
    judge_shortlist: int = 8
    offers_weight: float = 0.45
    interests_weight: float = 0.20
    reciprocity_weight: float = 0.20
    interaction_weight: float = 0.15
    input_per_million: float = 0.0
    cached_input_per_million: float = 0.0
    output_per_million: float = 0.0


def _dump(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


def _usage(response: Any) -> dict[str, int]:
    data = _dump(response) or {}
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    input_details = usage.get("input_tokens_details", {}) or {}
    output_details = usage.get("output_tokens_details", {}) or {}
    return {"input_tokens": int(usage.get("input_tokens", 0) or 0),
            "cached_input_tokens": int(input_details.get("cached_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
            "reasoning_tokens": int(output_details.get("reasoning_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0)}


def _estimate(usage: dict[str, int], config: PipelineConfig) -> float:
    return ((usage["input_tokens"] - usage["cached_input_tokens"]) * config.input_per_million
            + usage["cached_input_tokens"] * config.cached_input_per_million
            + usage["output_tokens"] * config.output_per_million) / 1_000_000


def _tokens(text: str) -> set[str]:
    return {word.lower().strip(".,!?;:()[]{}\"'") for word in text.split() if len(word) > 2}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / math.sqrt(len(a) * len(b)) if a and b else 0.0


def _compact(profile: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "name", "headline", "summary", "knowledge", "experience", "interests",
            "canHelpWith", "lookingFor", "openTo", "location")
    return {key: profile.get(key, []) for key in keys}


class Pipeline:
    def __init__(self, store: ExperimentStore, profiles: list[dict[str, Any]], api_key: str | None) -> None:
        self.store, self.profiles = store, profiles
        self.client = OpenAI(api_key=api_key) if api_key else None

    def _response(self, run_id: str, stage: str, model: str, prompt: str, prompt_version: str,
                  payload: dict[str, Any], config: PipelineConfig,
                  on_delta: Callable[[str], None] | None = None) -> str:
        request: dict[str, Any] = {"model": model, "instructions": prompt,
                                   "input": json.dumps(payload), "stream": True}
        if config.reasoning_effort != "none":
            request["reasoning"] = {"effort": config.reasoning_effort}
        started, first_delta, final_response, output, events, error = time.perf_counter(), None, None, [], [], None
        try:
            if self.client is None:
                raise RuntimeError("Set OPENAI_API_KEY to run the live pipeline.")
            for event in self.client.responses.create(**request):
                at_ms = round((time.perf_counter() - started) * 1000, 2)
                events.append({"at_ms": at_ms, "event": _dump(event)})
                if getattr(event, "type", "") == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    output.append(delta)
                    first_delta = at_ms if first_delta is None else first_delta
                    if on_delta:
                        on_delta(delta)
                if getattr(event, "type", "") == "response.completed":
                    final_response = getattr(event, "response", None)
            if final_response is not None and not output:
                output.append(getattr(final_response, "output_text", ""))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        usage, latency = _usage(final_response), round((time.perf_counter() - started) * 1000, 2)
        self.store.add_call(run_id, {"stage": stage, "model": model, "reasoning_effort": config.reasoning_effort,
            "prompt_version": prompt_version, "request": request, "response": _dump(final_response),
            "stream_events": events, "usage": usage, "ttft_ms": first_delta, "latency_ms": latency,
            "estimated_cost_usd": _estimate(usage, config), "response_id": getattr(final_response, "id", None), "error": error})
        if error:
            raise RuntimeError(error)
        return "".join(output)

    def _need(self, run_id: str, requester: dict[str, Any], query: str, config: PipelineConfig,
              on_delta: Callable[[str], None] | None) -> dict[str, Any]:
        raw = self._response(run_id, "need_interpreter", config.need_model, NEED_INTERPRETER_PROMPT,
            NEED_INTERPRETER_VERSION, {"query": query, "requester": _compact(requester)}, config, on_delta)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Need interpreter returned invalid JSON: {exc}") from exc

    def _retrieve(self, requester: dict[str, Any], need: dict[str, Any], config: PipelineConfig) -> list[dict[str, Any]]:
        rows = []
        for candidate in self.profiles:
            if candidate["id"] == requester["id"]:
                continue
            offers = _similarity(need.get("offers_query", ""), " ".join(candidate.get("canHelpWith", []) + candidate.get("experience", [])))
            interests = _similarity(need.get("interests_query", ""), " ".join(candidate.get("interests", [])))
            reciprocal = _similarity(need.get("needs_query", ""), " ".join(requester.get("canHelpWith", [])))
            interaction = float(bool(set(need.get("interaction_types", [])) & set(candidate.get("openTo", []))))
            prescore = config.offers_weight * offers + config.interests_weight * interests + config.reciprocity_weight * reciprocal + config.interaction_weight * interaction
            rows.append({"candidate": candidate, "offers_similarity": offers, "interests_similarity": interests,
                         "reciprocal_similarity": reciprocal, "interaction_score": interaction, "prescore": prescore})
        rows.sort(key=lambda row: row["prescore"], reverse=True)
        for rank, row in enumerate(rows[:config.retrieval_count], 1):
            row["rank"] = rank
        return rows[:config.retrieval_count]

    def _judge(self, run_id: str, requester: dict[str, Any], query: str, need: dict[str, Any], shortlist: list[dict[str, Any]], config: PipelineConfig, on_delta: Callable[[str], None] | None) -> list[dict[str, Any]]:
        payload = {"query": query, "need": need, "requester": _compact(requester),
                   "candidates": [_compact(row["candidate"]) | {"prescore": row["prescore"]} for row in shortlist]}
        raw = self._response(run_id, "match_judge", config.judge_model, MATCH_JUDGE_PROMPT,
                             MATCH_JUDGE_VERSION, payload, config, on_delta)
        parsed, allowed = json.loads(raw), {row["candidate"]["id"] for row in shortlist}
        return [match for match in parsed.get("matches", []) if match.get("candidate_id") in allowed]

    def _introduction(self, run_id: str, requester: dict[str, Any], query: str, candidate: dict[str, Any], reason: str, config: PipelineConfig) -> dict[str, Any]:
        raw = self._response(run_id, "introduction", config.introduction_model, INTRODUCTION_PROMPT,
            INTRODUCTION_VERSION, {"query": query, "requester": _compact(requester), "candidate": _compact(candidate), "judge_reason": reason}, config)
        return json.loads(raw)

    def run(self, requester_id: str, query: str, config: PipelineConfig, on_delta: Callable[[str, str], None] | None = None) -> dict[str, Any]:
        requester = next(profile for profile in self.profiles if profile["id"] == requester_id)
        run_id, started, need, retrieved = self.store.new_run(requester, query, asdict(config)), time.perf_counter(), None, []
        try:
            need = self._need(run_id, requester, query, config, lambda delta: on_delta and on_delta("need", delta))
            retrieved = self._retrieve(requester, need, config)
            self.store.add_retrieval(run_id, retrieved)
            matches = self._judge(run_id, requester, query, need, retrieved[:config.judge_shortlist], config, lambda delta: on_delta and on_delta("judge", delta))
            profiles = {profile["id"]: profile for profile in self.profiles}
            for rank, match in enumerate(matches, 1):
                match["introduction"] = self._introduction(run_id, requester, query, profiles[match["candidate_id"]], match.get("reason", ""), config)
                self.store.add_match(run_id, match, rank)
            status, error = "completed", None
        except Exception as exc:
            matches, status, error = [], "failed", str(exc)
        latency = round((time.perf_counter() - started) * 1000, 2)
        cost = float(self.store.dataframe("select coalesce(sum(estimated_cost_usd), 0) as cost from llm_calls where run_id = ?", [run_id]).iloc[0]["cost"])
        self.store.finish_run(run_id, need=need, status=status, error=error, latency_ms=latency, estimated_cost=cost)
        return {"run_id": run_id, "status": status, "error": error, "need": need, "retrieval": retrieved, "matches": matches, "total_latency_ms": latency, "estimated_cost_usd": cost}


def sync_authoritative_costs(store: ExperimentStore, admin_key: str, start_time: int, end_time: int | None = None) -> int:
    query = {"start_time": start_time, "bucket_width": "1d", "limit": 180}
    if end_time:
        query["end_time"] = end_time
    url = "https://api.openai.com/v1/organization/costs?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {admin_key}"})
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310: fixed HTTPS endpoint
        buckets = json.load(response).get("data", [])
    store.add_authoritative_costs(buckets)
    return len(buckets)
