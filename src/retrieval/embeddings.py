"""Three directional profile documents and embedding helpers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol


EMBEDDING_MODEL = "text-embedding-3-large"


def _joined(values: list[str]) -> str:
    return "; ".join(value.strip() for value in values if value and value.strip())


@dataclass(frozen=True)
class ProfileVectors:
    offers: str
    interests: str
    needs: str


def profile_vectors(profile: dict[str, Any]) -> ProfileVectors:
    """Build the three machine-facing documents defined in the MVP handoff."""
    projects = [project.get("description", "") for project in profile.get("projects", []) if isinstance(project, dict)]
    return ProfileVectors(
        offers=_joined(profile.get("knowledge", []) + profile.get("experience", []) + profile.get("canHelpWith", [])),
        interests=_joined(profile.get("interests", []) + projects),
        needs=_joined(profile.get("lookingFor", []) + profile.get("openTo", [])),
    )


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, client: Any, model: str = EMBEDDING_MODEL) -> None:
        self.client, self.model = client, model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def lexical_similarity(left: str, right: str) -> float:
    """Offline fallback used only when an embedding provider is unavailable."""
    def tokens(text: str) -> set[str]:
        return {word.lower().strip(".,!?;:()[]{}\"'") for word in text.split() if len(word) > 2}
    left_tokens, right_tokens = tokens(left), tokens(right)
    return len(left_tokens & right_tokens) / math.sqrt(len(left_tokens) * len(right_tokens)) if left_tokens and right_tokens else 0.0
