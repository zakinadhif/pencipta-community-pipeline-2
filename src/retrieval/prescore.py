"""Cheap deterministic score used before the expensive match judge."""
from __future__ import annotations

from typing import Protocol


class RetrievalWeights(Protocol):
    offers_weight: float
    interests_weight: float
    reciprocity_weight: float
    interaction_weight: float


def interaction_score(requested: list[str], candidate_open_to: list[str]) -> float:
    overlap = len(set(requested) & set(candidate_open_to))
    return 1.0 if overlap >= 2 else (0.5 if overlap == 1 else 0.0)


def weighted_prescore(offers: float, interests: float, reciprocity: float, interaction: float, weights: RetrievalWeights) -> float:
    raw = (weights.offers_weight * offers + weights.interests_weight * interests
           + weights.reciprocity_weight * reciprocity + weights.interaction_weight * interaction)
    return max(0.0, min(1.0, raw))
