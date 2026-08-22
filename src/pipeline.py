from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .agents.introduction import INTRODUCTION_PROMPT, INTRODUCTION_VERSION
from .agents.match_judge import MATCH_JUDGE_PROMPT, MATCH_JUDGE_VERSION
from .agents.need_interpreter import NEED_INTERPRETER_PROMPT, NEED_INTERPRETER_VERSION
from .config import DEFAULT_INTRO_MODEL, DEFAULT_JUDGE_MODEL, DEFAULT_NEED_MODEL, make_client, provider_config
from .retrieval.embeddings import EMBEDDING_MODEL, OpenAIEmbedder
from .retrieval.index import EmbeddingIndex
from .retrieval.search import search_people
from .tracing.storage import ExperimentStore
from .tracing.trace import make_trace

NEED_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["goal", "interactionType", "target", "hardFilters", "softPreferences", "retrievalQueries", "avoidMatchingOn"], "properties": {"goal": {"type": "string"}, "interactionType": {"type": "array", "items": {"type": "string"}}, "target": {"type": "object", "additionalProperties": False, "required": ["knowledge", "experience", "interests"], "properties": {"knowledge": {"type": "array", "items": {"type": "string"}}, "experience": {"type": "array", "items": {"type": "string"}}, "interests": {"type": "array", "items": {"type": "string"}}}}, "hardFilters": {"type": "object", "additionalProperties": False, "required": ["location", "interactionTypes"], "properties": {"location": {"type": ["string", "null"]}, "interactionTypes": {"type": "array", "items": {"type": "string"}}}}, "softPreferences": {"type": "array", "items": {"type": "string"}}, "retrievalQueries": {"type": "object", "additionalProperties": False, "required": ["offers", "interests", "needs"], "properties": {"offers": {"type": "string"}, "interests": {"type": "string"}, "needs": {"type": "string"}}}, "avoidMatchingOn": {"type": "array", "items": {"type": "string"}}}}
MATCH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["matches"], "properties": {"matches": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["userId", "score", "reason"], "properties": {"userId": {"type": "string"}, "score": {"type": "number"}, "reason": {"type": "string"}}}}}}
INTRODUCTION_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["whyThisPerson", "whyYou", "possibleOpener"], "properties": {"whyThisPerson": {"type": "string"}, "whyYou": {"type": "string"}, "possibleOpener": {"type": "string"}}}


@dataclass
class PipelineConfig:
    need_model: str = field(default_factory=lambda: provider_config()["need_model"])
    judge_model: str = field(default_factory=lambda: provider_config()["judge_model"])
    introduction_model: str = field(default_factory=lambda: provider_config()["introduction_model"])
    embedding_model: str = field(default_factory=lambda: provider_config()["embedding_model"])
    need_reasoning_effort: str = "low"
    judge_reasoning_effort: str = "medium"
    introduction_reasoning_effort: str = "low"
    retrieval_count: int = 30
    retrieval_per_dimension: int = 50
    judge_shortlist: int = 12
    offers_weight: float = 0.45
    interests_weight: float = 0.20
    reciprocity_weight: float = 0.20
    interaction_weight: float = 0.15
    max_output_tokens: int = 1600
    min_judge_score: float = 0.0
    min_prescore: float | None = None
    normalize_similarities: bool = True
    diversify_retrieval: bool = False
    mmr_lambda: float = 0.7
    isolate_prescore_from_judge: bool = True
    rerank_prescore_weight: float = 0.3
    rerank_judge_weight: float = 0.7
    parallel_intro: bool = True


def _dump(value: Any) -> Any:
    return value.model_dump() if hasattr(value, "model_dump") else value


def _parse_json_tolerant(text: str) -> Any:
    """Parse model output as JSON, tolerating markdown fences, prose before/after
    a JSON object, or a single top-level JSON value. Raises ValueError on failure."""
    import re

    stripped = text.strip()
    if not stripped:
        raise ValueError("empty model output")
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except (json.JSONDecodeError, ValueError):
                continue
    raise ValueError(f"could not parse model output as JSON: {stripped[:200]!r}")


def _normalize_to_shape(value: Any, shape: str) -> Any:
    """Coerce model output toward the shape a pipeline stage expects.

    Some OpenAI-compatible providers ignore structured-output schemas and return
    JSON with the right keys but wrong value types (e.g. a string where a list is
    expected). This adapts those outputs so the pipeline keeps running.
    """
    if shape == "list":
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [str(value)]
        return [str(value)]
    if shape == "dict":
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"value": value}
        return {"value": str(value)}
    if shape == "string":
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False) if value is not None else ""
    return value


def _coerce_need(need: Any) -> dict[str, Any]:
    """Ensure a parsed need interpretation has the shapes retrieval expects."""
    if not isinstance(need, dict):
        need = {"goal": str(need), "interactionType": [], "target": {}, "hardFilters": {"location": None, "interactionTypes": []}, "softPreferences": [], "retrievalQueries": {}, "avoidMatchingOn": []}
    target = need.get("target")
    if isinstance(target, str):
        target = {"knowledge": [target], "experience": [], "interests": []}
    if not isinstance(target, dict):
        target = {}
    for key in ("knowledge", "experience", "interests"):
        if key not in target or target[key] is None:
            target[key] = []
        if isinstance(target[key], str):
            target[key] = [target[key]]
    hard = need.get("hardFilters")
    if isinstance(hard, str):
        hard = {"location": hard, "interactionTypes": []}
    if not isinstance(hard, dict):
        hard = {}
    hard.setdefault("location", None)
    if isinstance(hard.get("interactionTypes"), str):
        hard["interactionTypes"] = [hard["interactionTypes"]]
    if not isinstance(hard.get("interactionTypes"), list):
        hard["interactionTypes"] = []
    queries = need.get("retrievalQueries")
    if isinstance(queries, str):
        queries = {"offers": queries, "interests": queries, "needs": queries}
    if not isinstance(queries, dict):
        queries = {}
    for key in ("offers", "interests", "needs"):
        queries.setdefault(key, "")
        if not isinstance(queries[key], str):
            queries[key] = json.dumps(queries[key], ensure_ascii=False) if queries[key] else ""
    interaction_type = _coerce_interaction_types(need.get("interactionType")) + _coerce_interaction_types(hard.get("interactionTypes"))
    interaction_type = list(dict.fromkeys(interaction_type))
    hard["interactionTypes"] = interaction_type
    return {
        "goal": _normalize_to_shape(need.get("goal"), "string"),
        "interactionType": interaction_type,
        "target": target,
        "hardFilters": hard,
        "softPreferences": _normalize_to_shape(need.get("softPreferences"), "list"),
        "retrievalQueries": queries,
        "avoidMatchingOn": _normalize_to_shape(need.get("avoidMatchingOn"), "list"),
    }


_INTERACTION_SYNONYMS = {
    "mentorship": "mentoring", "mentor": "mentoring", "being_mentored": "being_mentored",
    "collab": "collaboration", "partner": "collaboration",
    "advice": "advice", "recommendation": "recommendations", "hire": "hiring",
    "meet": "meeting_people", "friendship": "friendship", "cofound": "cofounding",
}


def _coerce_interaction_types(value: Any) -> list[str]:
    from .schemas.profile import INTERACTION_TYPES
    values = _normalize_to_shape(value, "list")
    cleaned = []
    for item in values:
        token = str(item).strip().lower().replace("-", "_").replace(" ", "_")
        token = _INTERACTION_SYNONYMS.get(token, token)
        if token in INTERACTION_TYPES:
            cleaned.append(token)
    return cleaned


def _coerce_matches(judged: Any) -> list[dict[str, Any]]:
    """Ensure a parsed judge result is a list of {userId, score, reason}."""
    if isinstance(judged, dict) and isinstance(judged.get("matches"), list):
        judged = judged["matches"]
    if not isinstance(judged, list):
        return []
    matches = []
    for item in judged:
        if not isinstance(item, dict):
            continue
        user_id = item.get("userId") or item.get("candidateId") or item.get("candidate_id") or item.get("id")
        matches.append({
            "userId": _normalize_to_shape(user_id, "string"),
            "score": float(item.get("score", item.get("matchScore", 0.0)) or 0.0),
            "reason": _normalize_to_shape(item.get("reason"), "string"),
        })
    return matches


def _retryable_stream_error(exc: Exception) -> bool:
    """Streaming to some OpenAI-compatible providers is rejected even though
    non-streaming works; fall back to non-streaming for those errors."""
    name = type(exc).__name__
    message = str(exc).lower()
    return name in {"PermissionDeniedError", "BadRequestError", "AuthenticationError", "APIStatusError"} or "blocked" in message or "stream" in message


def _is_official_openai(base_url: str) -> bool:
    """OpenAI's official API supports Structured Outputs; many compatible
    providers do not, so JSON structure is requested via prompt instead."""
    host = base_url.replace("https://", "").replace("http://", "").split("/")[0]
    return host in {"api.openai.com", "openai.com"}


def _json_only_instruction(schema: dict[str, Any]) -> str:
    """Appended instruction for providers that ignore structured outputs."""
    required = schema.get("required", [])
    fields = ", ".join(f'"{field}"' for field in required)
    return ("\n\nRespond with ONLY a single raw JSON object. No markdown, no code fences, no prose. "
            f"The JSON object must contain exactly these keys: {fields}. "
            "Ensure every value uses the correct JSON type (arrays for lists, objects for nested structures, numbers for scores).")


def _compact(profile: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "name", "headline", "summary", "knowledge", "experience", "interests", "canHelpWith", "lookingFor", "openTo", "projects", "location")
    return {key: profile.get(key, [] if key != "location" else None) for key in keys}


def _estimated_usage(request: dict[str, Any], output_text: str) -> dict[str, int]:
    """Approximate token usage for providers that return an empty usage object.
    A rough heuristic: ~4 chars per token; marked as an estimate in tracing."""
    import math

    input_chars = len(request.get("instructions", "")) + len(str(request.get("input", "")))
    input_tokens = max(1, math.ceil(input_chars / 4))
    output_tokens = max(0, math.ceil(len(output_text or "") / 4))
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": 0,
        "output_tokens": output_tokens,
        "reasoning_tokens": 0,
        "total_tokens": input_tokens + output_tokens,
    }


def _with_estimated_usage(response: Any, request: dict[str, Any], output_text: str) -> Any:
    """Return a response with usage populated even when the provider leaves it
    empty, so tracing and cost accounting work. Always returns a dict so
    usage_from_response can read it deterministically."""
    if response is None:
        return {"usage": _estimated_usage(request, output_text)}
    usage = None
    if isinstance(response, dict):
        usage = response.get("usage")
    elif hasattr(response, "usage"):
        usage = response.usage
    empty = False
    if usage is None:
        empty = True
    elif isinstance(usage, dict):
        empty = not usage.get("total_tokens")
    elif hasattr(usage, "total_tokens"):
        empty = not getattr(usage, "total_tokens", 0)
    if empty:
        return {"usage": _estimated_usage(request, output_text)}
    return response


class Pipeline:
    def __init__(self, store: ExperimentStore, profiles: list[dict[str, Any]], api_key: str | None, *, index: EmbeddingIndex | None = None, base_url: str | None = None) -> None:
        self.store, self.profiles = store, profiles
        cfg = provider_config()
        self.api_key = api_key or cfg["api_key"] or None
        self.base_url = (base_url or cfg["base_url"] or "https://api.openai.com/v1").rstrip("/")
        self.client = make_client(api_key=self.api_key, base_url=self.base_url) if self.api_key else None
        self.index = index

    def _post_responses(self, request: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
        """POST /responses over plain HTTP. Some OpenAI-compatible providers
        (behind Cloudflare) block Python SDK / urllib User-Agents but accept a
        curl-like UA; urllib lets us set that header, the SDK does not."""
        import urllib.error
        import urllib.request

        url = self.base_url + "/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "curl/8.5.0",
        }
        body = json.dumps(request).encode("utf-8")
        http_request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("error"):
            raise RuntimeError(payload["error"].get("message", str(payload["error"])))
        return payload

    def _response(self, run_id: str, stage: str, model: str, prompt: str, prompt_version: str, payload: dict[str, Any], schema_name: str, schema: dict[str, Any], reasoning_effort: str, config: PipelineConfig, on_delta: Callable[[str], None] | None = None) -> dict[str, Any]:
        request: dict[str, Any] = {"model": model, "instructions": prompt, "input": json.dumps(payload), "stream": True, "max_output_tokens": config.max_output_tokens}
        if _is_official_openai(self.base_url):
            request["text"] = {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}}
        else:
            request["instructions"] = prompt + _json_only_instruction(schema)
        if reasoning_effort != "none":
            request["reasoning"] = {"effort": reasoning_effort}
        started, first_delta, final_response, output, events = time.perf_counter(), None, None, [], []
        parsed = None
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
            output_text = "".join(output) or getattr(final_response, "output_text", "")
            parsed = _parse_json_tolerant(output_text)
            final_response = _with_estimated_usage(final_response, request, output_text)
        except Exception as exc:
            if _retryable_stream_error(exc):
                # Fallback for providers that reject the SDK's streaming request
                # (e.g. Cloudflare-blocked Python User-Agent): plain HTTP, non-stream.
                request["stream"] = False
                try:
                    data = self._post_responses(request)
                    final_response = data
                    stream_text = ""
                    for choice in data.get("choices", []):
                        content = choice.get("message", {}).get("content") or choice.get("text") or ""
                        stream_text += content or ""
                    if on_delta:
                        on_delta(stream_text)
                    parsed = _parse_json_tolerant(stream_text)
                    final_response = _with_estimated_usage(final_response, request, stream_text)
                except Exception as fallback_exc:
                    trace = make_trace(stage=stage, model=model, reasoning_effort=reasoning_effort, prompt_version=prompt_version, request=request, response=final_response, stream_events=events, ttft_ms=first_delta, latency_ms=round((time.perf_counter() - started) * 1000, 2), error=f"{type(fallback_exc).__name__}: {fallback_exc}")
                    self.store.add_call(run_id, trace)
                    raise RuntimeError(f"{stage} failed: {fallback_exc}") from fallback_exc
            else:
                trace = make_trace(stage=stage, model=model, reasoning_effort=reasoning_effort, prompt_version=prompt_version, request=request, response=final_response, stream_events=events, ttft_ms=first_delta, latency_ms=round((time.perf_counter() - started) * 1000, 2), error=f"{type(exc).__name__}: {exc}")
                self.store.add_call(run_id, trace)
                raise RuntimeError(f"{stage} failed: {exc}") from exc
        trace = make_trace(stage=stage, model=model, reasoning_effort=reasoning_effort, prompt_version=prompt_version, request=request, response=final_response, stream_events=events, ttft_ms=first_delta, latency_ms=round((time.perf_counter() - started) * 1000, 2))
        self.store.add_call(run_id, trace)
        return parsed

    def _retrieve(self, run_id: str, requester: dict[str, Any], need: dict[str, Any], config: PipelineConfig) -> list[dict[str, Any]]:
        embedder = OpenAIEmbedder(self.client, model=getattr(config, "embedding_model", EMBEDDING_MODEL)) if self.client else None
        rows = search_people(
            profiles=self.profiles, requester=requester,
            queries=need["retrievalQueries"], filters=need["hardFilters"],
            interaction_types=need["interactionType"], limit=len(self.profiles),
            index=self.index, embedder=embedder,
            per_dimension_count=getattr(config, "retrieval_per_dimension", config.retrieval_count),
            min_prescore=getattr(config, "min_prescore", None), weights=config,
            soft_preferences=need.get("softPreferences", []),
            avoid_terms=need.get("avoidMatchingOn", []),
            normalize=getattr(config, "normalize_similarities", True),
            diversify=getattr(config, "diversify_retrieval", False),
            mmr_lambda=getattr(config, "mmr_lambda", 0.7),
        )
        if embedder and embedder.last_trace:
            self.store.add_call(run_id, embedder.last_trace)
        # record relax meta if filtering was softened
        if rows and "_relax" not in rows[0]:
            pass
        return rows[:config.retrieval_count]

    @staticmethod
    def _rerank_with_prescore(prescores: dict[str, float], matches: list[dict[str, Any]], config: PipelineConfig) -> list[dict[str, Any]]:
        """Blend judge score with deterministic prescore for final ranking.

        combined = w_judge * judge_score + w_pre * prescore.  Weights default
        to 0.7/0.3 so judge judgment dominates but prescore breaks ties and
        rescues near-misses when retrieval was strong.
        """
        wj = getattr(config, "rerank_judge_weight", 0.7)
        wp = getattr(config, "rerank_prescore_weight", 0.3)
        for m in matches:
            m["combined_score"] = round(wj * float(m.get("score", 0)) + wp * float(prescores.get(m["userId"], 0.0)), 4)
            m["prescore"] = float(prescores.get(m["userId"], 0.0))
        matches.sort(key=lambda m: m["combined_score"], reverse=True)
        return matches

    def run_judge_experiment(self, requester_id: str, query: str, need: dict[str, Any], candidates: list[dict[str, Any]], config: PipelineConfig, *, include_requester: bool = True, include_prescore: bool = True, on_delta: Callable[[str], None] | None = None) -> dict[str, Any]:
        requester = next(profile for profile in self.profiles if profile["id"] == requester_id)
        need = _coerce_need(need)
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
            judged_matches = _coerce_matches(judged)
            allowed = {row["candidate"]["id"] for row in candidates[:config.judge_shortlist]}
            invalid_ids = sorted({item["userId"] for item in judged_matches} - allowed)
            if invalid_ids:
                raise RuntimeError(f"match_judge returned candidate IDs outside its shortlist: {', '.join(invalid_ids)}")
            prescores = {row["candidate"]["id"]: float(row.get("prescore", 0.0)) for row in candidates[:config.judge_shortlist]}
            judged_matches = self._rerank_with_prescore(prescores, judged_matches, config)
            visible = []
            for rank, match in enumerate(judged_matches, 1):
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
            need = _coerce_need(need)
            retrieved = self._retrieve(run_id, requester, need, config)
            self.store.add_retrieval(run_id, retrieved)
            if not retrieved:
                raise RuntimeError("retrieval returned no compatible candidates")
            isolate = getattr(config, "isolate_prescore_from_judge", True)
            judge_candidates = ([_compact(row["candidate"]) for row in retrieved[:config.judge_shortlist]]
                                if isolate else
                                [_compact(row["candidate"]) | {"prescore": row["prescore"]} for row in retrieved[:config.judge_shortlist]])
            judged = self._response(run_id, "match_judge", config.judge_model, MATCH_JUDGE_PROMPT, MATCH_JUDGE_VERSION, {"query": query, "need": need, "requester": _compact(requester), "candidates": judge_candidates}, "match_results", MATCH_SCHEMA, config.judge_reasoning_effort, config, lambda d: on_delta and on_delta("judge", d))
            judged_matches = _coerce_matches(judged)
            allowed, profiles = {row["candidate"]["id"] for row in retrieved[:config.judge_shortlist]}, {profile["id"]: profile for profile in self.profiles}
            invalid_ids = sorted({item["userId"] for item in judged_matches} - allowed)
            if invalid_ids:
                raise RuntimeError(f"match_judge returned candidate IDs outside its shortlist: {', '.join(invalid_ids)}")
            # rerank by combined judge*prescore signal before intro generation
            prescores = {row["candidate"]["id"]: float(row.get("prescore", 0.0)) for row in retrieved[:config.judge_shortlist]}
            judged_matches = self._rerank_with_prescore(prescores, judged_matches, config)
            visible_judged = [m for m in judged_matches if m["userId"] in allowed and m["score"] >= config.min_judge_score]
            hidden_judged = [m for m in judged_matches if m["userId"] in allowed and m["score"] < config.min_judge_score]

            # introductions: parallel when enabled, sequential otherwise
            def _intro_for(match: dict[str, Any]) -> dict[str, Any]:
                intro = self._response(run_id, "introduction", config.introduction_model, INTRODUCTION_PROMPT, INTRODUCTION_VERSION, {"query": query, "requester": _compact(requester), "candidate": _compact(profiles[match["userId"]]), "judge_reason": match["reason"]}, "match_introduction", INTRODUCTION_SCHEMA, config.introduction_reasoning_effort, config)
                return {"candidate_id": match["userId"], "score": match["score"], "combined_score": match.get("combined_score"), "reason": match["reason"], "introduction": {"why_this_person": intro["whyThisPerson"], "why_you": intro["whyYou"], "possible_opener": intro["possibleOpener"]}}

            if getattr(config, "parallel_intro", True) and len(visible_judged) > 1:
                import concurrent.futures as _fut
                with _fut.ThreadPoolExecutor(max_workers=min(4, len(visible_judged))) as ex:
                    futs = {ex.submit(_intro_for, m): m for m in visible_judged}
                    tmp: dict[str, dict[str, Any]] = {}
                    for fut in _fut.as_completed(futs):
                        res = fut.result()
                        tmp[res["candidate_id"]] = res
                    for rank, match in enumerate(visible_judged, 1):
                        result = tmp[match["userId"]]
                        matches.append(result)
                        self.store.add_match(run_id, result, rank)
            else:
                for rank, match in enumerate(visible_judged, 1):
                    result = _intro_for(match)
                    matches.append(result)
                    self.store.add_match(run_id, result, rank)
            for rank, match in enumerate(hidden_judged, len(matches) + 1):
                self.store.add_match(run_id, {"candidate_id": match["userId"], "score": match["score"], "combined_score": match.get("combined_score"), "reason": match["reason"], "introduction": None}, rank)
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
