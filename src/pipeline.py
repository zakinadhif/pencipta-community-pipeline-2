from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable

from openai import OpenAI

from .agents.introduction import INTRODUCTION_PROMPT, INTRODUCTION_VERSION
from .agents.match_judge import MATCH_JUDGE_PROMPT, MATCH_JUDGE_VERSION
from .agents.need_interpreter import NEED_INTERPRETER_PROMPT, NEED_INTERPRETER_VERSION
from .retrieval.embeddings import OpenAIEmbedder
from .retrieval.index import EmbeddingIndex
from .retrieval.search import search_people
from .tracing.storage import ExperimentStore
from .tracing.trace import make_trace

NEED_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["goal", "interactionType", "target", "hardFilters", "softPreferences", "retrievalQueries", "avoidMatchingOn"], "properties": {"goal": {"type": "string"}, "interactionType": {"type": "array", "items": {"type": "string"}}, "target": {"type": "object", "additionalProperties": False, "required": ["knowledge", "experience", "interests"], "properties": {"knowledge": {"type": "array", "items": {"type": "string"}}, "experience": {"type": "array", "items": {"type": "string"}}, "interests": {"type": "array", "items": {"type": "string"}}}}, "hardFilters": {"type": "object", "additionalProperties": False, "required": ["location", "interactionTypes"], "properties": {"location": {"type": ["string", "null"]}, "interactionTypes": {"type": "array", "items": {"type": "string"}}}}, "softPreferences": {"type": "array", "items": {"type": "string"}}, "retrievalQueries": {"type": "object", "additionalProperties": False, "required": ["offers", "interests", "needs"], "properties": {"offers": {"type": "string"}, "interests": {"type": "string"}, "needs": {"type": "string"}}}, "avoidMatchingOn": {"type": "array", "items": {"type": "string"}}}}
MATCH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["matches"], "properties": {"matches": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["userId", "score", "reason"], "properties": {"userId": {"type": "string"}, "score": {"type": "number"}, "reason": {"type": "string"}}}}}}
INTRODUCTION_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["whyThisPerson", "whyYou", "possibleOpener"], "properties": {"whyThisPerson": {"type": "string"}, "whyYou": {"type": "string"}, "possibleOpener": {"type": "string"}}}


@dataclass
class PipelineConfig:
    need_model: str = "gpt-5.6-luna"
    judge_model: str = "gpt-5.6-terra"
    introduction_model: str = "gpt-5.6-luna"
    need_reasoning_effort: str = "low"
    judge_reasoning_effort: str = "medium"
    introduction_reasoning_effort: str = "low"
    retrieval_count: int = 30
    judge_shortlist: int = 12
    offers_weight: float = 0.45
    interests_weight: float = 0.20
    reciprocity_weight: float = 0.20
    interaction_weight: float = 0.15
    max_output_tokens: int = 1600
    min_judge_score: float = 0.0


def _dump(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


def _compact(profile: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "name", "headline", "summary", "knowledge", "experience", "interests", "canHelpWith", "lookingFor", "openTo", "projects", "location")
    return {key: profile.get(key, [] if key != "location" else None) for key in keys}


class Pipeline:
    def __init__(self, store: ExperimentStore, profiles: list[dict[str, Any]], api_key: str | None, *, index: EmbeddingIndex | None = None) -> None:
        self.store, self.profiles = store, profiles
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.index = index

    def _response(self, run_id: str, stage: str, model: str, prompt: str, prompt_version: str, payload: dict[str, Any], schema_name: str, schema: dict[str, Any], reasoning_effort: str, config: PipelineConfig, on_delta: Callable[[str], None] | None = None) -> dict[str, Any]:
        request: dict[str, Any] = {"model": model, "instructions": prompt, "input": json.dumps(payload), "stream": True, "max_output_tokens": config.max_output_tokens, "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}}}
        if reasoning_effort != "none":
            request["reasoning"] = {"effort": reasoning_effort}
        started, first_delta, final_response, output, events = time.perf_counter(), None, None, [], []
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
            parsed = json.loads("".join(output) or getattr(final_response, "output_text", ""))
        except Exception as exc:
            trace = make_trace(stage=stage, model=model, reasoning_effort=reasoning_effort, prompt_version=prompt_version, request=request, response=final_response, stream_events=events, ttft_ms=first_delta, latency_ms=round((time.perf_counter() - started) * 1000, 2), error=f"{type(exc).__name__}: {exc}")
            self.store.add_call(run_id, trace)
            raise RuntimeError(f"{stage} failed: {exc}") from exc
        trace = make_trace(stage=stage, model=model, reasoning_effort=reasoning_effort, prompt_version=prompt_version, request=request, response=final_response, stream_events=events, ttft_ms=first_delta, latency_ms=round((time.perf_counter() - started) * 1000, 2))
        self.store.add_call(run_id, trace)
        return parsed

    def _retrieve(self, run_id: str, requester: dict[str, Any], need: dict[str, Any], config: PipelineConfig) -> list[dict[str, Any]]:
        embedder = OpenAIEmbedder(self.client) if self.client else None
        rows = search_people(profiles=self.profiles, requester=requester, queries=need["retrievalQueries"], filters=need["hardFilters"], interaction_types=need["interactionType"], limit=len(self.profiles), index=self.index, embedder=embedder, per_dimension_count=config.retrieval_count, min_prescore=config.min_prescore, weights=config)
        if embedder and embedder.last_trace:
            self.store.add_call(run_id, embedder.last_trace)
        return rows[:config.retrieval_count]

    def run_judge_experiment(self, requester_id: str, query: str, need: dict[str, Any], candidates: list[dict[str, Any]], config: PipelineConfig, *, include_requester: bool = True, include_prescore: bool = True, on_delta: Callable[[str], None] | None = None) -> dict[str, Any]:
        requester = next(profile for profile in self.profiles if profile["id"] == requester_id)
        candidate_payload = []
        for row in candidates[:config.judge_shortlist]:
            item = _compact(row["candidate"])
            if include_prescore:
                item["prescore"] = row.get("prescore", 0.0)
            candidate_payload.append(item)
        payload = {"query": query, "need": need, "candidates": candidate_payload}
        if include_requester:
            payload["requester"] = _compact(requester)
        run_id = self.store.new_run(requester, query, asdict(config) | {"experiment": "isolated_judge", "include_requester": include_requester, "include_prescore": include_prescore})
        started = time.perf_counter()
        try:
            judged = self._response(run_id, "match_judge", config.judge_model, MATCH_JUDGE_PROMPT, MATCH_JUDGE_VERSION, payload, "match_results", MATCH_SCHEMA, config.judge_reasoning_effort, config, on_delta)
            allowed = {row["candidate"]["id"] for row in candidates[:config.judge_shortlist]}
            invalid_ids = sorted({item["userId"] for item in judged["matches"]} - allowed)
            if invalid_ids:
                raise RuntimeError(f"match_judge returned candidate IDs outside its shortlist: {', '.join(invalid_ids)}")
            visible = []
            for rank, match in enumerate(judged["matches"], 1):
                hidden = match["score"] < config.min_judge_score
                self.store.add_match(run_id, {"candidate_id": match["userId"], "score": match["score"], "reason": match["reason"], "introduction": None if hidden else None}, rank)
                if not hidden:
                    visible.append(match)
            status, error = "completed", None
        except Exception as exc:
            judged, status, error = {"matches": []}, "failed", str(exc)
        latency = round((time.perf_counter() - started) * 1000, 2)
        cost = float(self.store.dataframe("select coalesce(sum(estimated_cost_usd), 0) as cost from llm_calls where run_id = ?", [run_id]).iloc[0]["cost"])
        self.store.finish_run(run_id, need=need, status=status, error=error, latency_ms=latency, estimated_cost=cost)
        return {"run_id": run_id, "status": status, "error": error, "input": payload, "matches": visible, "latency_ms": latency, "estimated_cost_usd": cost}

    def run(self, requester_id: str, query: str, config: PipelineConfig, on_delta: Callable[[str, str], None] | None = None) -> dict[str, Any]:
        requester = next(profile for profile in self.profiles if profile["id"] == requester_id)
        run_id, started, need, retrieved, matches = self.store.new_run(requester, query, asdict(config)), time.perf_counter(), None, [], []
        try:
            need = self._response(run_id, "need_interpreter", config.need_model, NEED_INTERPRETER_PROMPT, NEED_INTERPRETER_VERSION, {"query": query, "requester": _compact(requester)}, "need_interpretation", NEED_SCHEMA, config.need_reasoning_effort, config, lambda d: on_delta and on_delta("need", d))
            retrieved = self._retrieve(run_id, requester, need, config)
            self.store.add_retrieval(run_id, retrieved)
            if not retrieved:
                raise RuntimeError("retrieval returned no compatible candidates")
            judged = self._response(run_id, "match_judge", config.judge_model, MATCH_JUDGE_PROMPT, MATCH_JUDGE_VERSION, {"query": query, "need": need, "requester": _compact(requester), "candidates": [_compact(row["candidate"]) | {"prescore": row["prescore"]} for row in retrieved[:config.judge_shortlist]]}, "match_results", MATCH_SCHEMA, config.judge_reasoning_effort, config, lambda d: on_delta and on_delta("judge", d))
            allowed, profiles = {row["candidate"]["id"] for row in retrieved[:config.judge_shortlist]}, {profile["id"]: profile for profile in self.profiles}
            invalid_ids = sorted({item["userId"] for item in judged["matches"]} - allowed)
            if invalid_ids:
                raise RuntimeError(f"match_judge returned candidate IDs outside its shortlist: {', '.join(invalid_ids)}")
            for rank, match in enumerate((item for item in judged["matches"] if item["userId"] in allowed and item["score"] >= config.min_judge_score), 1):
                intro = self._response(run_id, "introduction", config.introduction_model, INTRODUCTION_PROMPT, INTRODUCTION_VERSION, {"query": query, "requester": _compact(requester), "candidate": _compact(profiles[match["userId"]]), "judge_reason": match["reason"]}, "match_introduction", INTRODUCTION_SCHEMA, config.introduction_reasoning_effort, config)
                result = {"candidate_id": match["userId"], "score": match["score"], "reason": match["reason"], "introduction": {"why_this_person": intro["whyThisPerson"], "why_you": intro["whyYou"], "possible_opener": intro["possibleOpener"]}}
                matches.append(result)
                self.store.add_match(run_id, result, rank)
            for rank, match in enumerate((item for item in judged["matches"] if item["userId"] in allowed and item["score"] < config.min_judge_score), len(matches) + 1):
                self.store.add_match(run_id, {"candidate_id": match["userId"], "score": match["score"], "reason": match["reason"], "introduction": None}, rank)
            status, error = "completed", None
        except Exception as exc:
            status, error = "failed", str(exc)
        latency = round((time.perf_counter() - started) * 1000, 2)
        cost = float(self.store.dataframe("select coalesce(sum(estimated_cost_usd), 0) as cost from llm_calls where run_id = ?", [run_id]).iloc[0]["cost"])
        self.store.finish_run(run_id, need=need, status=status, error=error, latency_ms=latency, estimated_cost=cost)
        return {"run_id": run_id, "status": status, "error": error, "need": need, "retrieval": retrieved, "matches": matches, "total_latency_ms": latency, "estimated_cost_usd": cost}


def sync_authoritative_costs(store: ExperimentStore, admin_key: str, start_time: int, end_time: int | None = None) -> int:
    query = {"start_time": start_time, "bucket_width": "1d", "limit": 180}
    if end_time:
        query["end_time"] = end_time
    request = urllib.request.Request("https://api.openai.com/v1/organization/costs?" + urllib.parse.urlencode(query), headers={"Authorization": f"Bearer {admin_key}"})
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310: fixed HTTPS endpoint
        buckets = json.load(response).get("data", [])
    store.add_authoritative_costs(buckets)
    return len(buckets)
