"""Cheap deterministic score used before the expensive match judge."""
from __future__ import annotations

from typing import Protocol


class RetrievalWeights(Protocol):
    offers_weight: float
    interests_weight: float
    reciprocity_weight: float
    interaction_weight: float


def weighted_prescore(offers: float, interests: float, reciprocity: float, interaction: float, weights: RetrievalWeights) -> float:
    return (weights.offers_weight * offers + weights.interests_weight * interests
            + weights.reciprocity_weight * reciprocity + weights.interaction_weight * interaction)
