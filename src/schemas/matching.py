"""Structured match-judge and introduction contracts."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchResult:
    candidate_id: str
    score: float
    reason: str
    why_this_person: str
    why_you: str
    possible_opener: str
