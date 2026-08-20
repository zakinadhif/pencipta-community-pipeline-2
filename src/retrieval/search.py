"""Candidate retrieval: directional vectors, hard filters, then a bounded shortlist."""
from __future__ import annotations

from typing import Any

from .embeddings import Embedder, cosine_similarity, lexical_similarity, profile_vectors
from .index import EmbeddingIndex
from .prescore import interaction_score, weighted_prescore


class _DefaultWeights:
    offers_weight = 0.45
    interests_weight = 0.20
    reciprocity_weight = 0.20
    interaction_weight = 0.15


def _matches_hard_filters(candidate: dict[str, Any], filters: dict[str, Any], interaction_types: list[str]) -> bool:
    location = filters.get("location")
    if location and candidate.get("location", "").casefold() != str(location).casefold():
        return False
    required = filters.get("interactionTypes") or interaction_types
    return not required or bool(set(required) & set(candidate.get("openTo", [])))


def search_people(*, profiles: list[dict[str, Any]], requester: dict[str, Any], queries: dict[str, str], filters: dict[str, Any], interaction_types: list[str], limit: int, index: EmbeddingIndex | None = None, embedder: Embedder | None = None, per_dimension_count: int = 50, min_prescore: float | None = None, weights: Any = None) -> list[dict[str, Any]]:
    """Retrieve only candidate profiles; the expensive judge sees a later shortlist.

    With an index, only the three query texts are embedded (one batched call) and
    candidate vectors are read from the precomputed index. Without an index but
    with an embedder, all candidates are embedded per search (dev fallback).
    Without an embedder, a lexical similarity baseline is used.
    """
    if weights is None:
        weights = _DefaultWeights()
    candidates = [profile for profile in profiles if profile["id"] != requester["id"] and _matches_hard_filters(profile, filters, interaction_types)]
    requester_vectors = profile_vectors(requester)
    reciprocal_query_text = queries.get("needs", "").strip() or requester_vectors.offers
    query_texts = [queries.get("offers", ""), queries.get("interests", ""), reciprocal_query_text]

    if index is not None:
        vectors = embedder.embed(query_texts) if embedder else None
        if vectors is None:
            return _rank(_union_top_n(_lexical_rows(candidates, query_texts, requester_vectors), per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types)
        offer_query, interest_query, reciprocal_query = vectors[:3]
        rows = []
        for candidate in candidates:
            pid = candidate["id"]
            rows.append({
                "candidate": candidate,
                "offers_similarity": _cos(index, pid, "offers", offer_query),
                "interests_similarity": _cos(index, pid, "interests", interest_query),
                "reciprocal_similarity": _cos(index, pid, "needs", reciprocal_query),
            })
        return _rank(_union_top_n(rows, per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types)
    if embedder:
        candidate_docs = [profile_vectors(profile) for profile in candidates]
        vectors = embedder.embed(query_texts + [doc for triple in candidate_docs for doc in (triple.offers, triple.interests, triple.needs)])
        offer_query, interest_query, reciprocal_query = vectors[:3]
        rows = []
        for index_, candidate in enumerate(candidates):
            base = 3 + index_ * 3
            rows.append({"candidate": candidate, "offers_similarity": cosine_similarity(offer_query, vectors[base]), "interests_similarity": cosine_similarity(interest_query, vectors[base + 1]), "reciprocal_similarity": cosine_similarity(reciprocal_query, vectors[base + 2])})
        return _rank(_union_top_n(rows, per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types)
    return _rank(_union_top_n(_lexical_rows(candidates, query_texts, requester_vectors), per_dimension_count), weights=weights, limit=limit, min_prescore=min_prescore, interaction_types=interaction_types)


def _cos(index: EmbeddingIndex, profile_id: str, kind: str, query: list[float]) -> float:
    vector = index.vectors.get(kind, {}).get(profile_id)
    return cosine_similarity(query, vector) if vector else 0.0


def _lexical_rows(candidates: list[dict[str, Any]], query_texts: list[str], requester_vectors) -> list[dict[str, Any]]:
    offers, interests, reciprocal = query_texts
    rows = []
    for candidate in candidates:
        vectors = profile_vectors(candidate)
        rows.append({"candidate": candidate, "offers_similarity": lexical_similarity(offers, vectors.offers), "interests_similarity": lexical_similarity(interests, vectors.interests), "reciprocal_similarity": lexical_similarity(reciprocal, vectors.needs)})
    return rows


def _rank(rows: list[dict[str, Any]], *, weights: Any, limit: int, min_prescore: float | None, interaction_types: list[str]) -> list[dict[str, Any]]:
    for row in rows:
        row["interaction_score"] = interaction_score(interaction_types, row["candidate"].get("openTo", []))
        row["prescore"] = weighted_prescore(row["offers_similarity"], row["interests_similarity"], row["reciprocal_similarity"], row["interaction_score"], weights)
    if min_prescore is not None:
        rows = [row for row in rows if row["prescore"] >= min_prescore]
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
