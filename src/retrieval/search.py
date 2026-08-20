"""Candidate retrieval: directional vectors, hard filters, then a bounded shortlist."""
from __future__ import annotations

from typing import Any

from .embeddings import Embedder, cosine_similarity, lexical_similarity, profile_vectors


def _matches_hard_filters(candidate: dict[str, Any], filters: dict[str, Any], interaction_types: list[str]) -> bool:
    location = filters.get("location")
    if location and candidate.get("location", "").casefold() != str(location).casefold():
        return False
    required = filters.get("interactionTypes", interaction_types)
    return not required or bool(set(required) & set(candidate.get("openTo", [])))


def search_people(*, profiles: list[dict[str, Any]], requester: dict[str, Any], queries: dict[str, str], filters: dict[str, Any], interaction_types: list[str], limit: int, embedder: Embedder | None = None) -> list[dict[str, Any]]:
    """Retrieve only candidate profiles; the expensive judge sees a later shortlist."""
    candidates = [profile for profile in profiles if profile["id"] != requester["id"] and _matches_hard_filters(profile, filters, interaction_types)]
    requester_vectors = profile_vectors(requester)
    if embedder:
        # Reciprocity is directional: what the requester can offer is compared
        # against what a candidate is looking for.
        query_texts = [queries.get("offers", ""), queries.get("interests", ""), requester_vectors.offers]
        candidate_docs = [profile_vectors(profile) for profile in candidates]
        vectors = embedder.embed(query_texts + [doc for triple in candidate_docs for doc in (triple.offers, triple.interests, triple.needs)])
        offer_query, interest_query, reciprocal_query = vectors[:3]
        rows = []
        for index, candidate in enumerate(candidates):
            base = 3 + index * 3
            rows.append({"candidate": candidate, "offers_similarity": cosine_similarity(offer_query, vectors[base]), "interests_similarity": cosine_similarity(interest_query, vectors[base + 1]), "reciprocal_similarity": cosine_similarity(reciprocal_query, vectors[base + 2])})
        return rows[:limit]
    rows = []
    for candidate in candidates:
        vectors = profile_vectors(candidate)
        rows.append({"candidate": candidate, "offers_similarity": lexical_similarity(queries.get("offers", ""), vectors.offers), "interests_similarity": lexical_similarity(queries.get("interests", ""), vectors.interests), "reciprocal_similarity": lexical_similarity(requester_vectors.offers, vectors.needs)})
    return rows[:limit]
