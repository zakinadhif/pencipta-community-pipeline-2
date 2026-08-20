"""Structured need-interpreter and retrieval contracts."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalScore:
    candidate_id: str
    offers_similarity: float
    interests_similarity: float
    reciprocal_similarity: float
    interaction_score: float
    prescore: float
    rank: int
