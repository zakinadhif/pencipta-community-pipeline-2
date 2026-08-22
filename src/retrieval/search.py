"""Candidate retrieval: directional vectors, hard filters, then a bounded shortlist."""
from __future__ import annotations

import re
from typing import Any

from .embeddings import Embedder, cosine_similarity, lexical_similarity, profile_vectors
from .index import EmbeddingIndex
from .prescore import avoidance_penalty, interaction_score, normalize_dimensions, soft_preference_score, weighted_prescore


class _DefaultWeights:
    offers_weight = 0.45
    interests_weight = 0.20
    reciprocity_weight = 0.20
    interaction_weight = 0.15


COMPATIBLE_INTERACTIONS: dict[str, list[str]] = {
    "friendship": ["friendship", "meeting_people", "collaboration", "advice"],
    "meeting_people": ["meeting_people", "collaboration", "advice", "friendship"],
    "being_mentored": ["mentoring", "advice", "collaboration", "being_mentored"],
    "mentoring": ["being_mentored", "mentoring", "advice", "collaboration"],
    "collaboration": ["collaboration", "advice", "meeting_people", "friendship"],
    "advice": ["advice", "collaboration", "mentoring", "meeting_people"],
    "recommendations": ["recommendations", "advice", "collaboration"],
    "cofounding": ["cofounding", "collaboration"],
    "hiring": ["hiring", "being_hired", "collaboration", "advice"],
    "being_hired": ["being_hired", "hiring", "collaboration", "advice"],
}


def _matches_hard_filters(candidate: dict[str, Any], filters: dict[str, Any], interaction_types: list[str]) -> bool:
    location = filters.get("location")
    if location and candidate.get("location", "").casefold() != str(location).casefold():
        return False
    required = filters.get("interactionTypes") or interaction_types
    if not required:
        return True
    candidate_open = set(candidate.get("openTo", []))
    expanded = set()
    for req in required:
        expanded.add(req)
        for comp in COMPATIBLE_INTERACTIONS.get(req, []):
            expanded.add(comp)
    return bool(expanded & candidate_open)


def search_people(*, profiles: list[dict[str, Any]], requester: dict[str, Any], queries: dict[str, str], filters: dict[str, Any], interaction_types: list[str], limit: int, index: EmbeddingIndex | None = None, embedder: Embedder | None = None, per_dimension_count: int = 50, min_prescore: float | None = None, weights: Any = None, soft_preferences: list[str] | None = None, avoid_terms: list[str] | None = None, normalize: bool = True, diversify: bool = False, mmr_lambda: float = 0.7) -> list[dict[str, Any]]:
    """Retrieve only candidate profiles; the expensive judge sees a later shortlist.

    With an index, only the three query texts are embedded (one batched call) and
    candidate vectors are read from the precomputed index. Without an index but
    with an embedder, all candidates are embedded per search (dev fallback).
    Without an embedder (or when embedding fails), a lexical similarity baseline
    is used so the pipeline never crashes on embedding availability.
    """
    if weights is None:
        weights = _DefaultWeights()
    soft_preferences = soft_preferences or []
    avoid_terms = avoid_terms or []
    candidates, _relaxed = _filtered_with_meta(profiles, requester, filters, interaction_types)
    requester_vectors = profile_vectors(requester)
    reciprocal_query_text = queries.get("needs", "").strip() or requester_vectors.offers
    query_texts = [queries.get("offers", ""), queries.get("interests", ""), reciprocal_query_text]

    def _normalize_if_embedding(rows: list[dict[str, Any]]) -> None:
        # Min-max per dimension only helps embedding cosine scales (~0.7–0.9
        # dense). For sparse lexical similarities (many zeros, tiny values)
        # it inflates noise, so skip when the signal is lexical fallback.
        if normalize and rows and rows[0].get("_source") != "lexical":
            normalize_dimensions(rows)

    if index is not None:
        vectors = _safe_embed(embedder, query_texts)
        if vectors is None:
            lex = _lexical_rows(candidates, query_texts, requester_vectors)
            # lexical branch — never normalize
            return _rank(_union_top_n(lex, per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types, soft_preferences=soft_preferences, avoid_terms=avoid_terms, diversify=diversify, mmr_lambda=mmr_lambda)
        offer_query, interest_query, reciprocal_query = vectors[:3]
        rows = []
        for candidate in candidates:
            pid = candidate["id"]
            rows.append({
                "candidate": candidate,
                "offers_similarity": _cos(index, pid, "offers", offer_query),
                "interests_similarity": _cos(index, pid, "interests", interest_query),
                "reciprocal_similarity": _cos(index, pid, "needs", reciprocal_query),
                "_source": "embedding",
            })
        _normalize_if_embedding(rows)
        return _rank(_union_top_n(rows, per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types, soft_preferences=soft_preferences, avoid_terms=avoid_terms, diversify=diversify, mmr_lambda=mmr_lambda)
    if embedder:
        candidate_docs = [profile_vectors(profile) for profile in candidates]
        vectors = _safe_embed(embedder, query_texts + [doc for triple in candidate_docs for doc in (triple.offers, triple.interests, triple.needs)])
        if vectors is None:
            lex = _lexical_rows(candidates, query_texts, requester_vectors)
            return _rank(_union_top_n(lex, per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types, soft_preferences=soft_preferences, avoid_terms=avoid_terms, diversify=diversify, mmr_lambda=mmr_lambda)
        offer_query, interest_query, reciprocal_query = vectors[:3]
        rows = []
        for index_, candidate in enumerate(candidates):
            base = 3 + index_ * 3
            rows.append({"candidate": candidate, "offers_similarity": cosine_similarity(offer_query, vectors[base]), "interests_similarity": cosine_similarity(interest_query, vectors[base + 1]), "reciprocal_similarity": cosine_similarity(reciprocal_query, vectors[base + 2]), "_source": "embedding"})
        _normalize_if_embedding(rows)
        return _rank(_union_top_n(rows, per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types, soft_preferences=soft_preferences, avoid_terms=avoid_terms, diversify=diversify, mmr_lambda=mmr_lambda)
    lex = _lexical_rows(candidates, query_texts, requester_vectors)
    return _rank(_union_top_n(lex, per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types, soft_preferences=soft_preferences, avoid_terms=avoid_terms, diversify=diversify, mmr_lambda=mmr_lambda)


def _safe_embed(embedder: Embedder | None, texts: list[str]) -> list[list[float]] | None:
    """Embed, returning None on any embedding failure so search falls back to lexical."""
    if embedder is None:
        return None
    try:
        return embedder.embed(texts)
    except Exception:
        return None


def _cos(index: EmbeddingIndex, profile_id: str, kind: str, query: list[float]) -> float:
    vector = index.vectors.get(kind, {}).get(profile_id)
    return cosine_similarity(query, vector) if vector else 0.0


def _lexical_rows(candidates: list[dict[str, Any]], query_texts: list[str], requester_vectors) -> list[dict[str, Any]]:
    offers, interests, reciprocal = query_texts
    rows = []
    for candidate in candidates:
        vectors = profile_vectors(candidate)
        rows.append({"candidate": candidate, "offers_similarity": lexical_similarity(offers, vectors.offers), "interests_similarity": lexical_similarity(interests, vectors.interests), "reciprocal_similarity": lexical_similarity(reciprocal, vectors.needs), "_source": "lexical"})
    return rows


def _filtered_with_meta(profiles: list[dict[str, Any]], requester: dict[str, Any], filters: dict[str, Any], interaction_types: list[str]) -> tuple[list[dict[str, Any]], str]:
    base = [p for p in profiles if p["id"] != requester["id"] and _matches_hard_filters(p, filters, interaction_types)]
    if base:
        return base, "none"
    if filters.get("location"):
        relaxed = [p for p in profiles if p["id"] != requester["id"] and p.get("location", "").casefold() == str(filters["location"]).casefold()]
        if relaxed:
            return relaxed, "interaction_relaxed"
    fallback = [p for p in profiles if p["id"] != requester["id"]]
    return fallback, "location_relaxed" if filters.get("location") else "none"


def _rank(rows: list[dict[str, Any]], *, weights: Any, limit: int, min_prescore: float | None, interaction_types: list[str], soft_preferences: list[str] | None = None, avoid_terms: list[str] | None = None, diversify: bool = False, mmr_lambda: float = 0.7) -> list[dict[str, Any]]:
    soft_preferences = soft_preferences or []
    avoid_terms = avoid_terms or []
    for row in rows:
        row["interaction_score"] = interaction_score(interaction_types, row["candidate"].get("openTo", []))
        row["soft_boost"] = soft_preference_score(row["candidate"], soft_preferences)
        row["avoid_penalty"] = avoidance_penalty(row["candidate"], avoid_terms)
        row["prescore"] = weighted_prescore(row["offers_similarity"], row["interests_similarity"], row["reciprocal_similarity"], row["interaction_score"], weights, soft_boost=row["soft_boost"], avoid_penalty=row["avoid_penalty"])
    if min_prescore is not None:
        rows = [row for row in rows if row["prescore"] >= min_prescore]
    if diversify and len(rows) > 1:
        rows = _mmr_rerank(rows, mmr_lambda)
    else:
        rows.sort(key=lambda row: row["prescore"], reverse=True)
    for rank, row in enumerate(rows[:limit], 1):
        row["rank"] = rank
    return rows[:limit]


def _union_top_n(rows: list[dict[str, Any]], per_dimension_count: int) -> list[dict[str, Any]]:
    """Handoff 10: take top-N per embedding dimension, then weighted union + dedup."""
    keep: set[str] = set()
    for dim in ("offers_similarity", "interests_similarity", "reciprocal_similarity"):
        for row in sorted(rows, key=lambda row: row[dim], reverse=True)[:per_dimension_count]:
            keep.add(row["candidate"]["id"])
    return [row for row in rows if row["candidate"]["id"] in keep]


def _candidate_text_tokens(candidate: dict[str, Any]) -> set[str]:
    text = " ".join([
        " ".join(candidate.get("knowledge", [])),
        " ".join(candidate.get("experience", [])),
        " ".join(candidate.get("interests", [])),
        " ".join(candidate.get("canHelpWith", [])),
        " ".join(candidate.get("lookingFor", [])),
    ])
    return {w.lower() for w in re.findall(r"[a-zA-Z0-9]+", text) if len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b) if a | b else 0.0


def _mmr_rerank(rows: list[dict[str, Any]], mmr_lambda: float) -> list[dict[str, Any]]:
    """Maximal Marginal Relevance: balance prescore relevance vs redundancy.

    Selected incrementally: next = argmax λ*prescore − (1−λ)*max_jaccard(cand, selected).
    """
    remaining = rows[:]
    remaining.sort(key=lambda r: r["prescore"], reverse=True)
    selected: list[dict[str, Any]] = []
    # cache token sets once
    tok = {r["candidate"]["id"]: _candidate_text_tokens(r["candidate"]) for r in remaining}
    while remaining:
        if not selected:
            nxt = remaining.pop(0)
            selected.append(nxt)
            continue
        best_idx, best_score = 0, float("-inf")
        for i, r in enumerate(remaining):
            max_sim = max(_jaccard(tok[r["candidate"]["id"]], tok[s["candidate"]["id"]]) for s in selected)
            mmr = mmr_lambda * r["prescore"] - (1 - mmr_lambda) * max_sim
            if mmr > best_score:
                best_score, best_idx = mmr, i
        selected.append(remaining.pop(best_idx))
    return selected
