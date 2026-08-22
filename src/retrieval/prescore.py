"""Cheap deterministic score used before the expensive match judge."""
from __future__ import annotations

import re
from typing import Any, Protocol


class RetrievalWeights(Protocol):
    offers_weight: float
    interests_weight: float
    reciprocity_weight: float
    interaction_weight: float


def interaction_score(requested: list[str], candidate_open_to: list[str]) -> float:
    """Continuous Jaccard over interaction types (0.0–1.0).

    Replaces the old 0/0.5/1.0 step so a 1-of-3 overlap (0.33) scores
    differently from 1-of-2 (0.5).  Backward-compatible: the cases covered
    by the original step (2/2→1.0, 1/2→0.5, 0→0.0) keep identical values.
    """
    if not requested and not candidate_open_to:
        return 0.0
    req, cand = set(requested), set(candidate_open_to)
    union = req | cand
    if not union:
        return 0.0
    return len(req & cand) / len(union)


def _stem(word: str) -> str:
    # tiny stemmer for plural/ing/ed so "beginners"≈"beginner", "mentoring"≈"mentor"
    w = word.lower()
    for suf in ("ing", "ers", "ers", "ies", "es", "s", "ed"):
        if len(w) > 4 and w.endswith(suf):
            stem = w[: -len(suf)]
            if len(stem) > 2:
                # ies -> y
                if suf == "ies":
                    return stem + "y"
                return stem
    return w


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-zA-Z0-9]+", text) if len(w) > 2}


def soft_preference_score(candidate: dict[str, Any], soft_preferences: list[str]) -> float:
    """0–1 boost: fraction of soft preference phrases lexically present in the candidate."""
    if not soft_preferences:
        return 0.0
    haystack = " ".join([
        " ".join(candidate.get("knowledge", [])),
        " ".join(candidate.get("experience", [])),
        " ".join(candidate.get("interests", [])),
        " ".join(candidate.get("canHelpWith", [])),
        candidate.get("location", "") or "",
    ]).lower()
    hay_tokens = _tokens(haystack)
    if not hay_tokens:
        return 0.0
    hits = 0
    for phrase in soft_preferences:
        pt = _tokens(phrase)
        if pt and (pt & hay_tokens):
            # partial credit proportional to token overlap
            hits += len(pt & hay_tokens) / len(pt)
    return min(1.0, hits / max(1, len(soft_preferences)))


def avoidance_penalty(candidate: dict[str, Any], avoid_terms: list[str]) -> float:
    """0–1 penalty: high when the candidate exhibits what the requester wants to avoid.

    A candidate that *offers* the same pivot the requester wants to avoid
    (e.g. both are 'beginners seeking mentors') should be down-ranked.
    Measured as max Jaccard between any avoid phrase and the candidate's
    needs/offers vocabulary.
    """
    if not avoid_terms:
        return 0.0
    cand_text = " ".join([
        " ".join(candidate.get("lookingFor", [])),
        " ".join(candidate.get("canHelpWith", [])),
        " ".join(candidate.get("knowledge", [])),
        " ".join(candidate.get("interests", [])),
    ])
    cand_tokens = _tokens(cand_text)
    if not cand_tokens:
        return 0.0
    best = 0.0
    for phrase in avoid_terms:
        pt = _tokens(str(phrase))
        if not pt:
            continue
        jaccard = len(pt & cand_tokens) / len(pt | cand_tokens) if pt | cand_tokens else 0.0
        # also consider exact substring hit as strong signal
        if phrase.lower().strip() in cand_text.lower():
            jaccard = max(jaccard, 0.7)
        best = max(best, jaccard)
    return best


def normalize_dimensions(rows: list[dict[str, Any]], dims: tuple[str, ...] = ("offers_similarity", "interests_similarity", "reciprocal_similarity")) -> list[dict[str, Any]]:
    """Min-max normalize each similarity dimension in-place to [0,1] so no single
    dimension dominates solely because of embedding scale.  If a dimension has
    zero variance its values are left as-is."""
    for dim in dims:
        vals = [float(r.get(dim, 0.0)) for r in rows]
        if not vals:
            continue
        mn, mx = min(vals), max(vals)
        rng = mx - mn
        if rng < 1e-9:
            continue
        for r in rows:
            r[dim] = (float(r.get(dim, 0.0)) - mn) / rng
    return rows


def weighted_prescore(offers: float, interests: float, reciprocity: float, interaction: float, weights: RetrievalWeights, *, soft_boost: float = 0.0, avoid_penalty: float = 0.0) -> float:
    raw = (weights.offers_weight * offers + weights.interests_weight * interests
           + weights.reciprocity_weight * reciprocity + weights.interaction_weight * interaction)
    # soft preferences act as a capped additive boost (up to +0.12); avoidance is a multiplicative dampener
    if soft_boost:
        raw += min(0.12, soft_boost * 0.15)
    if avoid_penalty:
        raw *= max(0.0, 1.0 - avoid_penalty * 0.8)
    return max(0.0, min(1.0, raw))
